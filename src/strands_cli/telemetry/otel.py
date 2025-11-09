"""OpenTelemetry tracing integration.

Provides OTEL tracing with:
- TracerProvider with configurable sampling (TraceIdRatioBased)
- OTLP/Console exporters based on endpoint configuration
- Auto-instrumentation for httpx and logging
- Structlog trace context injection
- Redaction of sensitive data per telemetry.redact config

The CLI's global TracerProvider is set before any SDK calls, ensuring
Strands SDK's automatic agent/model/tool spans nest under CLI workflow spans.

Span Architecture:
- CLI creates workflow-level spans (execute.<pattern>, build_agent, etc.)
- SDK automatically creates nested agent/model/tool spans
- Both share the same TracerProvider for unified traces
- Attributes used for queryable metadata (spec.name, pattern.type)
- Events used for timestamped execution milestones (step_start, step_complete)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

from strands_cli.telemetry.redaction import RedactionEngine

logger = structlog.get_logger(__name__)


class TraceCollector:
    """Thread-safe in-memory span collector for trace export.

    Captures spans as they are exported by BatchSpanProcessor,
    storing them for later retrieval as trace artifacts.

    Thread-safe for concurrent span collection.
    """

    def __init__(self) -> None:
        """Initialize empty trace collector."""
        self._spans: list[dict[str, Any]] = []
        self._lock = Lock()
        self._trace_id: str | None = None

    def add_span(self, span: ReadableSpan, redacted_attrs: dict[str, Any] | None = None) -> None:
        """Add span to collection.

        Args:
            span: ReadableSpan to store
            redacted_attrs: Optional redacted attributes to use instead of span.attributes
        """
        with self._lock:
            # Extract trace_id from first span
            if self._trace_id is None and span.context:
                self._trace_id = format(span.context.trace_id, "032x")

            # Use redacted attributes if provided, otherwise use original
            attributes = (
                redacted_attrs
                if redacted_attrs is not None
                else (dict(span.attributes) if span.attributes else {})
            )

            # Convert span to serializable dict
            span_data = {
                "name": span.name,
                "start_time": self._format_timestamp(span.start_time),
                "end_time": self._format_timestamp(span.end_time),
                "duration_ms": (
                    (span.end_time - span.start_time) / 1_000_000
                    if span.end_time and span.start_time
                    else 0
                ),
                "attributes": attributes,
                "events": [
                    {
                        "name": event.name,
                        "timestamp": self._format_timestamp(event.timestamp),
                        "attributes": dict(event.attributes) if event.attributes else {},
                    }
                    for event in (span.events or [])
                ],
                "status": {
                    "status_code": span.status.status_code.name if span.status else "UNSET",
                    "description": span.status.description
                    if span.status and span.status.description
                    else None,
                },
            }

            self._spans.append(span_data)

    def get_trace_data(
        self, spec_name: str | None = None, pattern: str | None = None
    ) -> dict[str, Any]:
        """Get complete trace data as JSON-serializable dict.

        Args:
            spec_name: Name of spec for metadata
            pattern: Pattern type for metadata

        Returns:
            Trace data with trace_id, spans, metadata
        """
        with self._lock:
            total_duration = sum(span.get("duration_ms", 0) for span in self._spans)

            return {
                "trace_id": self._trace_id or "unknown",
                "spec_name": spec_name or "unknown",
                "pattern": pattern or "unknown",
                "duration_ms": round(total_duration, 3),
                "span_count": len(self._spans),
                "spans": self._spans.copy(),
            }

    def clear(self) -> None:
        """Clear all collected spans."""
        with self._lock:
            self._spans.clear()
            self._trace_id = None

    @staticmethod
    def _format_timestamp(ns: int | None) -> str:
        """Convert nanosecond timestamp to ISO 8601 string.

        Args:
            ns: Timestamp in nanoseconds since epoch

        Returns:
            ISO 8601 formatted timestamp with millisecond precision
        """
        if ns is None:
            return ""
        # Convert nanoseconds to seconds with microsecond precision
        dt = datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC)
        return dt.isoformat(timespec="milliseconds")


class CollectingSpanExporter(SpanExporter):
    """Span exporter that captures spans to TraceCollector.

    Wraps another exporter to pass spans through while collecting them.
    Optionally applies redaction to span attributes before collection.
    """

    def __init__(
        self,
        collector: TraceCollector,
        wrapped_exporter: SpanExporter,
        redaction_engine: RedactionEngine | None = None,
        redact_tool_inputs: bool = False,
        redact_tool_outputs: bool = False,
    ) -> None:
        """Initialize collecting exporter.

        Args:
            collector: TraceCollector to store spans in
            wrapped_exporter: Underlying exporter to pass spans to
            redaction_engine: Optional RedactionEngine for PII scrubbing
            redact_tool_inputs: Whether to redact tool.input.* attributes
            redact_tool_outputs: Whether to redact tool.output.* attributes
        """
        self._collector = collector
        self._wrapped = wrapped_exporter
        self._redaction_engine = redaction_engine
        self._redact_tool_inputs = redact_tool_inputs
        self._redact_tool_outputs = redact_tool_outputs
        self._redaction_count = 0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans to collector and wrapped exporter.

        Applies redaction to span attributes before storing in collector.

        Args:
            spans: Sequence of ReadableSpan objects

        Returns:
            Export result from wrapped exporter
        """
        # Collect spans for artifact export (with optional redaction)
        for span in spans:
            # Apply redaction if configured
            if self._redaction_engine and span.attributes:
                attrs = dict(span.attributes)
                redacted_attrs, was_redacted = self._redaction_engine.redact_span_attributes(
                    attrs,
                    redact_tool_inputs=self._redact_tool_inputs,
                    redact_tool_outputs=self._redact_tool_outputs,
                )

                if was_redacted:
                    self._redaction_count += 1
                    # Create a modified span copy for collection
                    # Note: We modify the attributes in the collected data, not the original span
                    self._collector.add_span(span, redacted_attrs)
                    logger.debug(
                        "span_redacted",
                        span_name=span.name,
                        redaction_count=self._redaction_engine.get_redaction_count(),
                    )
                else:
                    self._collector.add_span(span)
            else:
                self._collector.add_span(span)

        # Pass through to wrapped exporter (original spans, unredacted)
        return self._wrapped.export(spans)

    def shutdown(self) -> None:
        """Shutdown wrapped exporter and log redaction summary."""
        if self._redaction_engine and self._redaction_count > 0:
            logger.info(
                "redaction_summary",
                total_spans_redacted=self._redaction_count,
                total_pii_instances=self._redaction_engine.get_redaction_count(),
            )
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush wrapped exporter.

        Args:
            timeout_millis: Timeout in milliseconds

        Returns:
            True if flush succeeded
        """
        if hasattr(self._wrapped, "force_flush"):
            return self._wrapped.force_flush(timeout_millis)
        return True


class NoOpTracerProvider:
    """No-op tracer provider for when telemetry is disabled."""

    def get_tracer(self, name: str) -> NoOpTracer:
        """Return no-op tracer."""
        return NoOpTracer()

    def shutdown(self) -> None:
        """No-op shutdown."""
        pass


class NoOpTracer:
    """No-op tracer that does nothing."""

    def start_span(self, name: str, **kwargs: Any) -> NoOpSpan:
        """Return no-op span."""
        return NoOpSpan()

    def start_as_current_span(self, name: str, **kwargs: Any) -> NoOpSpan:
        """Return no-op span (context manager)."""
        return NoOpSpan()


class NoOpSpan:
    """No-op span context manager."""

    def __enter__(self) -> NoOpSpan:
        """Enter context."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context."""
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op set attribute."""
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op add event."""
        pass

    def set_status(self, status: Any) -> None:
        """No-op set status."""
        pass


# Global tracer provider (initially no-op)
_tracer_provider: TracerProvider | NoOpTracerProvider = NoOpTracerProvider()

# Global trace collector (initially None)
_trace_collector: TraceCollector | None = None


def get_tracer(name: str) -> trace.Tracer | NoOpTracer:
    """Get tracer for instrumenting code.

    Args:
        name: Tracer name (usually __name__)

    Returns:
        Tracer instance (real or no-op based on configuration)
    """
    return _tracer_provider.get_tracer(name)


def get_trace_collector() -> TraceCollector | None:
    """Get global trace collector.

    Returns:
        TraceCollector instance if telemetry configured, else None
    """
    return _trace_collector


def configure_telemetry(spec_telemetry: dict[str, Any] | None = None) -> None:
    """Configure OpenTelemetry tracing.

    Sets up global TracerProvider with sampling, OTLP/Console exporters,
    and auto-instrumentation for httpx and logging.

    Args:
        spec_telemetry: Telemetry config from spec (otel, redact)
    """
    global _tracer_provider, _trace_collector

    # Skip if no telemetry config
    if not spec_telemetry or not spec_telemetry.get("otel"):
        logger.debug("telemetry_disabled", reason="no_otel_config")
        return

    otel_config = spec_telemetry["otel"]
    redact_config = spec_telemetry.get("redact", {})

    endpoint = otel_config.get("endpoint")
    service_name = otel_config.get("service_name", "strands-cli")
    sample_ratio = otel_config.get("sample_ratio", 1.0)

    logger.info(
        "telemetry_configuring",
        endpoint=endpoint or "console",
        service_name=service_name,
        sample_ratio=sample_ratio,
    )

    # Create tracer provider with deterministic sampling
    sampler = TraceIdRatioBased(rate=sample_ratio)
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(sampler=sampler, resource=resource)

    # Create trace collector for artifact export
    collector = TraceCollector()
    _trace_collector = collector

    # Create redaction engine if redaction configured
    redaction_engine: RedactionEngine | None = None
    redact_tool_inputs = False
    redact_tool_outputs = False

    if redact_config:
        redact_tool_inputs = redact_config.get("tool_inputs", False)
        redact_tool_outputs = redact_config.get("tool_outputs", False)
        custom_patterns = redact_config.get("custom_patterns", [])

        if redact_tool_inputs or redact_tool_outputs or custom_patterns:
            redaction_engine = RedactionEngine(custom_patterns=custom_patterns)
            logger.info(
                "redaction_configured",
                tool_inputs=redact_tool_inputs,
                tool_outputs=redact_tool_outputs,
                custom_patterns_count=len(custom_patterns),
            )

    # Setup OTLP exporter if endpoint provided, otherwise console
    base_exporter: SpanExporter
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            base_exporter = OTLPSpanExporter(endpoint=endpoint)
            collecting_exporter = CollectingSpanExporter(
                collector,
                base_exporter,
                redaction_engine=redaction_engine,
                redact_tool_inputs=redact_tool_inputs,
                redact_tool_outputs=redact_tool_outputs,
            )
            provider.add_span_processor(BatchSpanProcessor(collecting_exporter))
            logger.info("otlp_exporter_configured", endpoint=endpoint)
        except Exception as e:
            logger.warning("otlp_exporter_failed", error=str(e), fallback="console")
            base_exporter = ConsoleSpanExporter()
            collecting_exporter = CollectingSpanExporter(
                collector,
                base_exporter,
                redaction_engine=redaction_engine,
                redact_tool_inputs=redact_tool_inputs,
                redact_tool_outputs=redact_tool_outputs,
            )
            provider.add_span_processor(BatchSpanProcessor(collecting_exporter))
    else:
        # Console exporter for local dev
        base_exporter = ConsoleSpanExporter()
        collecting_exporter = CollectingSpanExporter(
            collector,
            base_exporter,
            redaction_engine=redaction_engine,
            redact_tool_inputs=redact_tool_inputs,
            redact_tool_outputs=redact_tool_outputs,
        )
        provider.add_span_processor(BatchSpanProcessor(collecting_exporter))
        logger.info("console_exporter_configured")

    # Set as global provider BEFORE any SDK calls
    # This ensures Strands SDK reuses our provider and nests spans correctly
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # Auto-instrument httpx (all HTTP calls in doctor command and HTTP executors)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.info("httpx_instrumented")
    except Exception as e:
        logger.warning("httpx_instrumentation_failed", error=str(e))

    # Auto-instrument logging (inject trace context into log records)
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=True)
        logger.info("logging_instrumented")
    except Exception as e:
        logger.warning("logging_instrumentation_failed", error=str(e))

    logger.info("telemetry_configured", provider_type=type(provider).__name__)


def force_flush_telemetry(timeout_millis: int = 30000) -> bool:
    """Force flush pending spans to exporters.

    This ensures all queued spans in BatchSpanProcessor are exported
    before proceeding. Critical for trace artifact generation.

    Args:
        timeout_millis: Maximum time to wait for flush (default: 30 seconds)

    Returns:
        True if flush succeeded within timeout, False otherwise
    """
    global _tracer_provider

    if hasattr(_tracer_provider, "force_flush"):
        logger.debug("telemetry_force_flush_start", timeout_ms=timeout_millis)
        result = _tracer_provider.force_flush(timeout_millis)
        logger.debug("telemetry_force_flush_complete", success=result)
        return result
    return True  # No-op provider, nothing to flush


def shutdown_telemetry() -> None:
    """Shutdown telemetry and flush pending spans."""
    global _tracer_provider

    if hasattr(_tracer_provider, "shutdown"):
        logger.debug("telemetry_shutting_down")
        _tracer_provider.shutdown()
        logger.info("telemetry_shutdown_complete")


def add_otel_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor to inject OTEL trace context.

    Extracts trace_id and span_id from current span and adds to event dict.

    Args:
        logger: Logger instance
        method_name: Log method name
        event_dict: Event dictionary

    Returns:
        Event dict with trace_id and span_id added
    """
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

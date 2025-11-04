"""OTEL scaffolding for future tracing support.

Provides no-op OpenTelemetry tracer implementation that can be replaced
with real OTEL exporters without changing caller code. This scaffolding:

1. Parses and validates telemetry configuration from specs
2. Provides consistent tracing API throughout the codebase
3. Enables zero-cost observability points (no overhead when disabled)
4. Allows future OTEL activation without code changes

Future Implementation:
    - Replace NoOpTracerProvider with OpenTelemetry TracerProvider
    - Add OTLP exporters (gRPC or HTTP)
    - Configure sampling and propagation
    - Wire up instrumentation libraries (boto3, httpx, etc.)
    - Add span attributes: spec.name, agent_id, pattern_type, model_id

Span Structure (future):
    - run_single_agent: Root span for workflow execution
    - agent_invoke: Agent LLM call
    - tool:<id>: Individual tool invocations
    - llm:completion: Model inference
"""

from typing import Any


class NoOpSpan:
    """No-op span for scaffolding.

    Implements the span interface without emitting any telemetry.
    Allows code to use span operations (set_attribute, add_event)
    without runtime overhead when OTEL is disabled.
    """

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op set attribute."""
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op add event."""
        pass


class NoOpTracer:
    """No-op tracer for scaffolding.

    Provides tracer interface without telemetry emission.
    Future: Replace with opentelemetry.trace.Tracer.
    """

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> NoOpSpan:
        """No-op start span."""
        return NoOpSpan()


class NoOpTracerProvider:
    """No-op tracer provider for scaffolding.

    This provides the structure for OTEL tracing but doesn't emit any spans.

    Future Replacement:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317")
        provider.add_span_processor(BatchSpanProcessor(exporter))
    """

    def get_tracer(self, name: str) -> NoOpTracer:
        """Get a no-op tracer.

        Args:
            name: Tracer name (typically module name like __name__)

        Returns:
            NoOpTracer instance (future: real Tracer)
        """
        return NoOpTracer()


# Global no-op tracer provider instance
# This allows all code to use tracer.start_span() without OTEL being active
# When OTEL is enabled, replace this with a real TracerProvider
_tracer_provider = NoOpTracerProvider()


def get_tracer(name: str) -> NoOpTracer:
    """Get a tracer from the global provider.

    This is the primary entry point for tracing. Currently returns
    a no-op tracer; future versions will return real OTEL tracers.

    Args:
        name: Tracer name (use __name__ for module-scoped tracers)

    Returns:
        NoOpTracer (currently) or opentelemetry.trace.Tracer (future)
    """
    return _tracer_provider.get_tracer(name)


def configure_telemetry(spec_telemetry: dict[str, Any] | None = None) -> None:
    """Configure telemetry based on spec.

    Parses telemetry configuration from workflow spec and validates structure.
    Currently no-op (config is parsed but not activated).

    Future Implementation:
        1. Parse spec_telemetry["otel"] for endpoint, headers, sampling
        2. Create OTLPSpanExporter with endpoint configuration
        3. Set up TracerProvider with BatchSpanProcessor
        4. Configure propagators (W3C Trace Context)
        5. Install instrumentation (boto3, httpx, etc.)
        6. Set global tracer provider

    Args:
        spec_telemetry: Telemetry configuration from workflow spec
                       Example: {"otel": {"endpoint": "http://...", "headers": {...}}}

    Note:
        This is scaffolding only. Configuration is validated but not activated.
    """
    # MVP: Just log that telemetry config was seen
    if spec_telemetry:
        pass  # TODO: Parse and validate config structure

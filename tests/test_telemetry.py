"""Tests for telemetry module (trace collection and export).

Tests trace collection infrastructure, $TRACE template variable rendering,
and --trace flag functionality.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, TraceFlags

from strands_cli.artifacts import write_artifacts
from strands_cli.telemetry.otel import (
    CollectingSpanExporter,
    TraceCollector,
    configure_telemetry,
    get_trace_collector,
)


@pytest.fixture
def trace_collector() -> TraceCollector:
    """Create a fresh TraceCollector for testing."""
    return TraceCollector()


@pytest.fixture
def mock_span() -> ReadableSpan:
    """Create a mock ReadableSpan for testing."""
    span = Mock(spec=ReadableSpan)
    span.name = "test_span"
    span.start_time = 1000000000  # 1 second in nanoseconds
    span.end_time = 2000000000  # 2 seconds in nanoseconds
    span.context = SpanContext(
        trace_id=12345678901234567890123456789012,
        span_id=1234567890123456,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    span.attributes = {"test.key": "test_value", "spec.name": "test-spec"}
    span.events = []
    span.status = Mock()
    span.status.status_code.name = "OK"
    span.status.description = None
    return span


class TestTraceCollector:
    """Test TraceCollector class."""

    def test_collector_starts_empty(self, trace_collector: TraceCollector) -> None:
        """Test that a new collector has no spans."""
        data = trace_collector.get_trace_data()
        assert data["span_count"] == 0
        assert data["spans"] == []
        assert data["trace_id"] == "unknown"

    def test_add_span_stores_span_data(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that add_span stores span data correctly."""
        trace_collector.add_span(mock_span)

        data = trace_collector.get_trace_data()
        assert data["span_count"] == 1
        assert len(data["spans"]) == 1

        span_data = data["spans"][0]
        assert span_data["name"] == "test_span"
        assert span_data["duration_ms"] == 1000.0  # 1 second
        assert span_data["attributes"] == {"test.key": "test_value", "spec.name": "test-spec"}
        assert span_data["status"]["status_code"] == "OK"

    def test_add_span_extracts_trace_id(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that add_span extracts trace_id from first span."""
        trace_collector.add_span(mock_span)

        data = trace_collector.get_trace_data()
        # Trace ID should be formatted as 32-character hex string
        assert data["trace_id"] == format(12345678901234567890123456789012, "032x")

    def test_add_multiple_spans(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test adding multiple spans."""
        # Add first span
        trace_collector.add_span(mock_span)

        # Add second span with different name
        span2 = Mock(spec=ReadableSpan)
        span2.name = "second_span"
        span2.start_time = 3000000000
        span2.end_time = 4000000000
        span2.context = mock_span.context  # Same trace
        span2.attributes = {"key2": "value2"}
        span2.events = []
        span2.status = mock_span.status

        trace_collector.add_span(span2)

        data = trace_collector.get_trace_data()
        assert data["span_count"] == 2
        assert len(data["spans"]) == 2
        assert data["spans"][0]["name"] == "test_span"
        assert data["spans"][1]["name"] == "second_span"

    def test_get_trace_data_includes_metadata(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that get_trace_data includes spec metadata."""
        trace_collector.add_span(mock_span)

        data = trace_collector.get_trace_data(spec_name="my-workflow", pattern="chain")
        assert data["spec_name"] == "my-workflow"
        assert data["pattern"] == "chain"

    def test_get_trace_data_calculates_total_duration(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that total duration is sum of all span durations."""
        # Add two spans with 1s duration each
        trace_collector.add_span(mock_span)

        span2 = Mock(spec=ReadableSpan)
        span2.name = "span2"
        span2.start_time = 5000000000
        span2.end_time = 6000000000  # 1s duration
        span2.context = mock_span.context
        span2.attributes = {}
        span2.events = []
        span2.status = mock_span.status

        trace_collector.add_span(span2)

        data = trace_collector.get_trace_data()
        assert data["duration_ms"] == 2000.0  # 2 seconds total

    def test_clear_removes_all_spans(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that clear() removes all collected spans."""
        trace_collector.add_span(mock_span)
        assert trace_collector.get_trace_data()["span_count"] == 1

        trace_collector.clear()

        data = trace_collector.get_trace_data()
        assert data["span_count"] == 0
        assert data["spans"] == []
        assert data["trace_id"] == "unknown"
        assert data["evicted_count"] == 0

    def test_span_limit_eviction(self, mock_span: ReadableSpan) -> None:
        """Verify FIFO eviction with configurable limit."""
        collector = TraceCollector(max_spans=10)

        # Add 15 spans
        for i in range(15):
            span = Mock(spec=ReadableSpan)
            span.name = f"span-{i}"
            span.start_time = i * 1000000000
            span.end_time = (i + 1) * 1000000000
            span.context = mock_span.context
            span.attributes = {"index": i}
            span.events = []
            span.status = mock_span.status
            collector.add_span(span)

        trace_data = collector.get_trace_data()

        # Should have exactly 10 spans (oldest 5 evicted)
        assert trace_data["span_count"] == 10
        assert trace_data["evicted_count"] == 5

        # Verify oldest spans evicted (span-0 to span-4 gone)
        span_names = [s["name"] for s in trace_data["spans"]]
        assert "span-0" not in span_names
        assert "span-4" not in span_names
        assert "span-5" in span_names  # First kept span
        assert "span-14" in span_names  # Most recent preserved

    def test_span_limit_from_env_var(self, mock_span: ReadableSpan, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify max_spans can be set via environment variable."""
        monkeypatch.setenv("STRANDS_MAX_TRACE_SPANS", "5")

        collector = TraceCollector()

        # Add 8 spans
        for i in range(8):
            span = Mock(spec=ReadableSpan)
            span.name = f"span-{i}"
            span.start_time = i * 1000000000
            span.end_time = (i + 1) * 1000000000
            span.context = mock_span.context
            span.attributes = {}
            span.events = []
            span.status = mock_span.status
            collector.add_span(span)

        trace_data = collector.get_trace_data()

        # Should respect env var limit of 5
        assert trace_data["span_count"] == 5
        assert trace_data["evicted_count"] == 3

    def test_format_timestamp_converts_nanoseconds(self, trace_collector: TraceCollector) -> None:
        """Test that _format_timestamp converts nanoseconds to ISO 8601."""
        # 1 second = 1_000_000_000 nanoseconds
        timestamp = TraceCollector._format_timestamp(1000000000)
        # Should be ISO 8601 format with UTC timezone
        assert "1970-01-01T00:00:01" in timestamp
        # Note: timezone format may vary by system (+00:00 or Z)
        assert timestamp.endswith("Z") or timestamp.endswith("+00:00")

    def test_format_timestamp_handles_none(self, trace_collector: TraceCollector) -> None:
        """Test that _format_timestamp returns empty string for None."""
        assert TraceCollector._format_timestamp(None) == ""


class TestCollectingSpanExporter:
    """Test CollectingSpanExporter class."""

    def test_exporter_collects_and_forwards_spans(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that CollectingSpanExporter collects spans and forwards to wrapped exporter."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        wrapped = Mock()
        wrapped.export.return_value = SpanExportResult.SUCCESS

        exporter = CollectingSpanExporter(trace_collector, wrapped)
        result = exporter.export([mock_span])

        # Should collect span
        assert trace_collector.get_trace_data()["span_count"] == 1

        # Should forward to wrapped exporter
        wrapped.export.assert_called_once_with([mock_span])
        assert result == SpanExportResult.SUCCESS

    def test_exporter_shutdown_calls_wrapped(self, trace_collector: TraceCollector) -> None:
        """Test that shutdown() calls wrapped exporter shutdown."""
        wrapped = Mock()
        exporter = CollectingSpanExporter(trace_collector, wrapped)

        exporter.shutdown()
        wrapped.shutdown.assert_called_once()

    def test_exporter_force_flush_calls_wrapped(self, trace_collector: TraceCollector) -> None:
        """Test that force_flush() calls wrapped exporter force_flush."""
        wrapped = Mock()
        wrapped.force_flush.return_value = True
        exporter = CollectingSpanExporter(trace_collector, wrapped)

        result = exporter.force_flush(5000)
        wrapped.force_flush.assert_called_once_with(5000)
        assert result is True


class TestTelemetryConfiguration:
    """Test telemetry configuration and global state."""

    def test_configure_telemetry_sets_global_collector(self) -> None:
        """Test that configure_telemetry sets global trace collector."""
        # Reset global state
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        # Configure with minimal config
        config = {"otel": {"service_name": "test-service"}}
        configure_telemetry(config)

        # Should have created global collector
        collector = get_trace_collector()
        assert collector is not None
        assert isinstance(collector, TraceCollector)

        # Cleanup
        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None

    def test_configure_telemetry_skips_without_config(self) -> None:
        """Test that configure_telemetry does nothing without otel config."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        configure_telemetry(None)
        assert get_trace_collector() is None

        configure_telemetry({})
        assert get_trace_collector() is None

    def test_force_flush_timeout_returns_false(self, mocker: pytest.Mock) -> None:
        """Verify timeout detection and logging."""
        from strands_cli.telemetry import otel
        from strands_cli.telemetry.otel import force_flush_telemetry

        mock_provider = mocker.Mock()
        mock_provider.force_flush.return_value = False  # Simulate timeout
        otel._tracer_provider = mock_provider

        # Mock the logger to verify warning was called
        mock_logger_instance = mocker.Mock()
        mocker.patch("strands_cli.telemetry.otel.logger", mock_logger_instance)

        result = force_flush_telemetry(timeout_millis=1000)

        assert result is False
        mock_provider.force_flush.assert_called_once_with(1000)
        # Verify warning was logged
        assert mock_logger_instance.warning.called

    def test_force_flush_success_returns_true(self, mocker: pytest.Mock) -> None:
        """Verify successful flush returns True."""
        from strands_cli.telemetry import otel
        from strands_cli.telemetry.otel import force_flush_telemetry

        mock_provider = mocker.Mock()
        mock_provider.force_flush.return_value = True
        otel._tracer_provider = mock_provider

        result = force_flush_telemetry(timeout_millis=5000)

        assert result is True
        mock_provider.force_flush.assert_called_once_with(5000)


class TestTraceArtifacts:
    """Test trace artifact generation via $TRACE template variable."""

    def test_write_artifacts_includes_trace_variable(
        self, tmp_path: Path, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that write_artifacts includes TRACE variable when collector available."""
        from strands_cli.telemetry import otel

        # Setup global collector
        trace_collector.add_span(mock_span)
        otel._trace_collector = trace_collector

        try:
            # Create artifact that uses TRACE
            artifacts = [
                Mock(path="trace.json", from_="{{ TRACE }}"),
            ]

            written = write_artifacts(
                artifacts,
                "test response",
                output_dir=tmp_path,
                spec_name="test-spec",
                pattern_type="chain",
            )

            assert len(written) == 1
            trace_file = Path(written[0])
            assert trace_file.exists()

            # Verify JSON content
            content = trace_file.read_text()
            data = json.loads(content)

            assert data["spec_name"] == "test-spec"
            assert data["pattern"] == "chain"
            assert data["span_count"] == 1
            assert len(data["spans"]) == 1
            assert data["spans"][0]["name"] == "test_span"

        finally:
            # Cleanup
            otel._trace_collector = None

    def test_write_artifacts_trace_variable_empty_without_collector(self, tmp_path: Path) -> None:
        """Test that TRACE is empty when no trace collector configured."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        artifacts = [
            Mock(path="trace.json", from_="{{ TRACE }}"),
        ]

        written = write_artifacts(
            artifacts,
            "test response",
            output_dir=tmp_path,
        )

        assert len(written) == 1
        trace_file = Path(written[0])

        # Should be empty string (no trace data)
        assert trace_file.read_text() == ""

    def test_trace_json_structure(
        self, tmp_path: Path, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that trace JSON has correct structure and formatting."""
        from strands_cli.telemetry import otel

        trace_collector.add_span(mock_span)
        otel._trace_collector = trace_collector

        try:
            artifacts = [Mock(path="trace.json", from_="{{ TRACE }}")]

            written = write_artifacts(
                artifacts, "", tmp_path, spec_name="test", pattern_type="workflow"
            )

            trace_file = Path(written[0])
            data = json.loads(trace_file.read_text())

            # Verify structure
            assert "trace_id" in data
            assert "spec_name" in data
            assert "pattern" in data
            assert "duration_ms" in data
            assert "span_count" in data
            assert "spans" in data

            # Verify span structure
            span = data["spans"][0]
            assert "name" in span
            assert "start_time" in span
            assert "end_time" in span
            assert "duration_ms" in span
            assert "attributes" in span
            assert "events" in span
            assert "status" in span

        finally:
            otel._trace_collector = None


class TestTraceFlag:
    """Test --trace CLI flag functionality (integration with write_trace_artifact)."""

    def test_trace_artifact_json_formatting(
        self, tmp_path: Path, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that trace artifact has pretty-printed JSON (indent=2)."""
        trace_collector.add_span(mock_span)

        trace_data = trace_collector.get_trace_data(spec_name="test", pattern="chain")
        trace_json = json.dumps(trace_data, indent=2, ensure_ascii=False)

        # Should have newlines and indentation
        assert "\n" in trace_json
        assert "  " in trace_json  # 2-space indent

        # Should be valid JSON
        reparsed = json.loads(trace_json)
        assert reparsed["spec_name"] == "test"
        assert reparsed["pattern"] == "chain"


class TestTracerProviderConfiguration:
    """Test TracerProvider setup with OTLP and Console exporters."""

    def test_configure_with_otlp_endpoint(self) -> None:
        """Test that OTLP exporter is configured when endpoint provided."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        config = {
            "otel": {
                "endpoint": "http://localhost:4318",
                "service_name": "test-service",
                "sample_ratio": 0.5,
            }
        }

        # Note: May fail if OTLP not available, should fallback to console
        try:
            configure_telemetry(config)
            collector = get_trace_collector()
            assert collector is not None
        finally:
            from strands_cli.telemetry import shutdown_telemetry

            shutdown_telemetry()
            otel._trace_collector = None

    def test_configure_with_console_exporter(self) -> None:
        """Test that console exporter is used when no endpoint provided."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        config = {
            "otel": {
                "service_name": "console-test",
                "sample_ratio": 1.0,
            }
        }

        configure_telemetry(config)
        collector = get_trace_collector()
        assert collector is not None

        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None

    def test_configure_with_redaction_enabled(self) -> None:
        """Test that redaction is configured when redact config provided."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        config = {
            "otel": {
                "service_name": "redaction-test",
            },
            "redact": {
                "tool_inputs": True,
                "tool_outputs": True,
                "custom_patterns": [r"SECRET-\d{4}"],
            },
        }

        configure_telemetry(config)
        collector = get_trace_collector()
        assert collector is not None

        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None

    def test_sample_ratio_configuration(self) -> None:
        """Test that sample ratio is applied to TracerProvider."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        # Configure with 10% sampling
        config = {
            "otel": {
                "service_name": "sampling-test",
                "sample_ratio": 0.1,
            }
        }

        configure_telemetry(config)

        # Verify tracer provider exists (sample ratio internal to provider)
        tracer = otel.get_tracer("test")
        assert tracer is not None

        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None


class TestAutoInstrumentation:
    """Test auto-instrumentation for httpx and logging."""

    def test_httpx_instrumentation_configured(self) -> None:
        """Test that httpx auto-instrumentation is enabled."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        config = {
            "otel": {
                "service_name": "httpx-test",
            }
        }

        # Configure telemetry (enables httpx instrumentation)
        configure_telemetry(config)

        # Verify instrumentation was attempted (may log warning if fails)
        # We can't easily verify instrumentation is active without making HTTP calls

        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None

    def test_logging_instrumentation_configured(self) -> None:
        """Test that logging auto-instrumentation is enabled."""
        from strands_cli.telemetry import otel

        otel._trace_collector = None

        config = {
            "otel": {
                "service_name": "logging-test",
            }
        }

        # Configure telemetry (enables logging instrumentation)
        configure_telemetry(config)

        # Verify instrumentation was attempted
        # We can't easily test trace context injection without active spans

        from strands_cli.telemetry import shutdown_telemetry

        shutdown_telemetry()
        otel._trace_collector = None


class TestRedactionIntegration:
    """Test redaction integration with CollectingSpanExporter."""

    def test_collecting_exporter_applies_redaction(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that CollectingSpanExporter redacts PII in span attributes."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        from strands_cli.telemetry.redaction import RedactionEngine

        # Create span with PII in attributes
        mock_span.attributes = {
            "tool.input.email": "user@example.com",
            "tool.input.api_key": "sk_live_abc123def456ghi789jkl",
            "other.attribute": "safe_value",
        }

        # Use mock exporter instead of ConsoleSpanExporter
        wrapped = Mock()
        wrapped.export.return_value = SpanExportResult.SUCCESS

        redaction_engine = RedactionEngine()

        exporter = CollectingSpanExporter(
            trace_collector,
            wrapped,
            redaction_engine=redaction_engine,
            redact_tool_inputs=True,
            redact_tool_outputs=False,
        )

        result = exporter.export([mock_span])
        assert result == SpanExportResult.SUCCESS

        # Verify span was collected with redacted attributes
        trace_data = trace_collector.get_trace_data()
        assert trace_data["span_count"] == 1

        collected_span = trace_data["spans"][0]
        # PII should be redacted
        assert collected_span["attributes"]["tool.input.email"] == "***REDACTED***"
        assert collected_span["attributes"]["tool.input.api_key"] == "***REDACTED***"
        # Non-PII should be unchanged
        assert collected_span["attributes"]["other.attribute"] == "safe_value"
        # Redaction flag should be set
        assert collected_span["attributes"]["redacted"] is True

    def test_collecting_exporter_no_redaction_when_disabled(
        self, trace_collector: TraceCollector, mock_span: ReadableSpan
    ) -> None:
        """Test that redaction is skipped when redaction_engine is None."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_span.attributes = {
            "tool.input.email": "user@example.com",
            "other.attribute": "value",
        }

        # Use mock exporter
        wrapped = Mock()
        wrapped.export.return_value = SpanExportResult.SUCCESS

        # No redaction engine provided
        exporter = CollectingSpanExporter(trace_collector, wrapped, redaction_engine=None)

        result = exporter.export([mock_span])
        assert result == SpanExportResult.SUCCESS

        # Verify original attributes preserved
        trace_data = trace_collector.get_trace_data()
        collected_span = trace_data["spans"][0]
        assert collected_span["attributes"]["tool.input.email"] == "user@example.com"
        assert "redacted" not in collected_span["attributes"]


class TestConcurrentSpanCollection:
    """Tests for concurrent span collection (Phase 2.3)."""

    @pytest.mark.asyncio
    async def test_concurrent_span_collection(self) -> None:
        """Verify TraceCollector thread-safety with 100 parallel adds."""
        import asyncio

        from opentelemetry.sdk.trace import ReadableSpan
        from opentelemetry.trace import SpanContext, TraceFlags

        collector = TraceCollector()

        def create_test_span(span_id: int) -> ReadableSpan:
            """Create a mock span for testing."""
            span = Mock(spec=ReadableSpan)
            span.name = f"span-{span_id}"
            span.start_time = 1000000000 + span_id
            span.end_time = 2000000000 + span_id
            span.context = SpanContext(
                trace_id=12345678901234567890123456789012,
                span_id=1234567890123456 + span_id,
                is_remote=False,
                trace_flags=TraceFlags(0x01),
            )
            span.attributes = {"span.id": span_id, "test.concurrent": True}
            span.events = []
            span.status = Mock()
            span.status.status_code.name = "OK"
            span.status.description = None
            return span

        async def add_spans(start_idx: int) -> None:
            """Add 10 spans starting from start_idx."""
            for i in range(start_idx, start_idx + 10):
                span = create_test_span(i)
                collector.add_span(span)

        # Execute 10 concurrent tasks, each adding 10 spans
        await asyncio.gather(*[add_spans(i * 10) for i in range(10)])

        trace_data = collector.get_trace_data()
        assert trace_data["span_count"] == 100

        # Verify all span IDs are present (no data corruption)
        span_ids = {span["attributes"]["span.id"] for span in trace_data["spans"]}
        assert span_ids == set(range(100))


"""Integration tests for redaction with telemetry."""

from __future__ import annotations

import pytest

from strands_cli.telemetry.otel import (
    CollectingSpanExporter,
    TraceCollector,
    configure_telemetry,
    shutdown_telemetry,
)
from strands_cli.telemetry.redaction import RedactionEngine


@pytest.fixture
def mock_span_data():
    """Create mock span data with PII."""
    return {
        "name": "test_span",
        "start_time": 1000000000000000000,  # nanoseconds
        "end_time": 1000000001000000000,
        "attributes": {
            "tool.input.email": "user@example.com",
            "tool.input.phone": "555-123-4567",
            "tool.output.result": "Contact admin@example.com",
            "other.attribute": "normal data",
        },
    }


class TestRedactionIntegration:
    """Integration tests for redaction with OTEL."""

    def test_redaction_engine_with_span_attributes(self) -> None:
        """Test that redaction engine properly redacts span attributes."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.email": "user@example.com",
            "tool.input.api_key": "sk_live_abcdef1234567890",
            "tool.output.phone": "555-123-4567",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=True
        )

        assert was_redacted is True
        assert redacted["tool.input.email"] == "***REDACTED***"
        assert redacted["tool.input.api_key"] == "***REDACTED***"
        assert redacted["tool.output.phone"] == "***REDACTED***"
        assert redacted["redacted"] is True

    def test_collecting_exporter_with_redaction(self) -> None:
        """Test that CollectingSpanExporter applies redaction."""
        from unittest.mock import Mock

        # Create mock exporter that doesn't actually write
        mock_exporter = Mock()
        mock_exporter.export = Mock(return_value=Mock(SUCCESS=True))

        # Create mock span with PII in attributes
        mock_span = Mock()
        mock_span.name = "test_span"
        mock_span.context = Mock()
        mock_span.context.trace_id = 12345678901234567890
        mock_span.start_time = 1000000000000000000
        mock_span.end_time = 1000000001000000000
        mock_span.attributes = {
            "tool.input.email": "user@example.com",
            "tool.output.result": "Contact admin@example.com",
            "normal.attribute": "data",
        }
        mock_span.events = []
        mock_span.status = Mock()
        mock_span.status.status_code = Mock()
        mock_span.status.status_code.name = "OK"
        mock_span.status.description = None

        # Create collector and exporter with redaction
        collector = TraceCollector()
        engine = RedactionEngine()
        exporter = CollectingSpanExporter(
            collector=collector,
            wrapped_exporter=mock_exporter,
            redaction_engine=engine,
            redact_tool_inputs=True,
            redact_tool_outputs=True,
        )

        # Export span
        exporter.export([mock_span])

        # Check that span was collected with redacted attributes
        trace_data = collector.get_trace_data()
        assert trace_data["span_count"] == 1

        span_data = trace_data["spans"][0]
        assert span_data["attributes"]["tool.input.email"] == "***REDACTED***"
        assert "***REDACTED***" in span_data["attributes"]["tool.output.result"]
        assert span_data["attributes"]["normal.attribute"] == "data"
        assert span_data["attributes"]["redacted"] is True

    def test_configure_telemetry_with_redaction(self) -> None:
        """Test that configure_telemetry properly sets up redaction."""
        spec_telemetry = {
            "otel": {
                "endpoint": None,  # Console exporter
                "service_name": "test-service",
                "sample_ratio": 1.0,
            },
            "redact": {
                "tool_inputs": True,
                "tool_outputs": True,
                "custom_patterns": ["CUSTOM-\\d{5}"],
            },
        }

        # Configure telemetry with redaction
        configure_telemetry(spec_telemetry)

        # Cleanup
        shutdown_telemetry()

    def test_no_redaction_when_disabled(self) -> None:
        """Test that redaction doesn't occur when not configured."""
        from unittest.mock import Mock

        # Create mock exporter
        mock_exporter = Mock()
        mock_exporter.export = Mock(return_value=Mock(SUCCESS=True))

        mock_span = Mock()
        mock_span.name = "test_span"
        mock_span.context = Mock()
        mock_span.context.trace_id = 12345678901234567890
        mock_span.start_time = 1000000000000000000
        mock_span.end_time = 1000000001000000000
        mock_span.attributes = {
            "tool.input.email": "user@example.com",
            "normal.attribute": "data",
        }
        mock_span.events = []
        mock_span.status = Mock()
        mock_span.status.status_code = Mock()
        mock_span.status.status_code.name = "OK"
        mock_span.status.description = None

        # Create collector and exporter WITHOUT redaction
        collector = TraceCollector()
        exporter = CollectingSpanExporter(
            collector=collector,
            wrapped_exporter=mock_exporter,
            redaction_engine=None,  # No redaction
            redact_tool_inputs=False,
            redact_tool_outputs=False,
        )

        # Export span
        exporter.export([mock_span])

        # Check that span was collected WITHOUT redaction
        trace_data = collector.get_trace_data()
        span_data = trace_data["spans"][0]

        # Email should NOT be redacted when redaction disabled
        assert span_data["attributes"]["tool.input.email"] == "user@example.com"
        assert "redacted" not in span_data["attributes"]

    def test_partial_redaction_tool_inputs_only(self) -> None:
        """Test redaction of only tool inputs."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.email": "user@example.com",
            "tool.output.email": "admin@example.com",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=False
        )

        assert was_redacted is True
        assert redacted["tool.input.email"] == "***REDACTED***"
        # Output should still be scanned for PII (conservative)
        assert redacted["tool.output.email"] == "***REDACTED***"
        assert redacted["redacted"] is True

    def test_redaction_with_custom_patterns(self) -> None:
        """Test redaction with custom regex patterns."""
        engine = RedactionEngine(custom_patterns=[r"SECRET-\d{4}"])
        attrs = {
            "tool.input.code": "SECRET-1234",
            "tool.input.data": "normal data",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=False
        )

        assert was_redacted is True
        assert redacted["tool.input.code"] == "***REDACTED***"
        assert redacted["tool.input.data"] == "normal data"
        assert redacted["redacted"] is True

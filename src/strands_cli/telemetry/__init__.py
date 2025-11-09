"""Telemetry module with OTEL scaffolding."""

from strands_cli.telemetry.otel import (
    NoOpSpan,
    NoOpTracer,
    NoOpTracerProvider,
    TraceCollector,
    add_otel_context,
    configure_telemetry,
    get_trace_collector,
    get_tracer,
    shutdown_telemetry,
)

__all__ = [
    "NoOpSpan",
    "NoOpTracer",
    "NoOpTracerProvider",
    "TraceCollector",
    "add_otel_context",
    "configure_telemetry",
    "get_trace_collector",
    "get_tracer",
    "shutdown_telemetry",
]

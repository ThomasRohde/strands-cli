"""Telemetry module with OTEL scaffolding."""

from strands_cli.telemetry.otel import (
    NoOpSpan,
    NoOpTracer,
    NoOpTracerProvider,
    configure_telemetry,
    get_tracer,
)

__all__ = [
    "NoOpSpan",
    "NoOpTracer",
    "NoOpTracerProvider",
    "configure_telemetry",
    "get_tracer",
]

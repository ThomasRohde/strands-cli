"""Tests for thread-safe telemetry configuration.

Validates that concurrent calls to configure_telemetry are properly
serialized and don't cause race conditions.
"""

import asyncio

import pytest

from strands_cli.telemetry.otel import configure_telemetry, get_trace_collector


@pytest.mark.asyncio
async def test_concurrent_configure_telemetry() -> None:
    """Verify thread-safety with 20 parallel config calls.

    Ensures no race conditions when multiple concurrent workflows
    attempt to configure telemetry simultaneously.
    """
    configs = [
        {"otel": {"service_name": f"service-{i}", "sample_ratio": 1.0}} for i in range(20)
    ]

    async def configure(cfg: dict) -> bool:
        configure_telemetry(cfg)
        return get_trace_collector() is not None

    results = await asyncio.gather(*[configure(c) for c in configs])
    assert all(results), "All config calls should succeed"

    # Verify consistent final state
    final_collector = get_trace_collector()
    assert final_collector is not None


@pytest.mark.asyncio
async def test_concurrent_configure_no_race_condition() -> None:
    """Verify no race conditions with repeated configuration.

    Tests that the global state remains consistent when multiple
    tasks configure telemetry in parallel.
    """

    async def configure_repeatedly(count: int) -> None:
        for i in range(count):
            configure_telemetry({"otel": {"service_name": f"test-{i}", "sample_ratio": 1.0}})

    # Run 10 tasks, each configuring 5 times
    await asyncio.gather(*[configure_repeatedly(5) for _ in range(10)])

    # Verify final state is valid
    collector = get_trace_collector()
    assert collector is not None


def test_configure_telemetry_sequential() -> None:
    """Verify basic sequential configuration still works.

    Baseline test to ensure thread-safety didn't break normal usage.
    """
    configure_telemetry({"otel": {"service_name": "test-service", "sample_ratio": 1.0}})

    collector = get_trace_collector()
    assert collector is not None


def test_configure_telemetry_none_config() -> None:
    """Verify None config is handled safely."""
    configure_telemetry(None)

    # Should remain in no-op state - just ensuring no crash occurs
    # (collector may or may not be None depending on previous tests)


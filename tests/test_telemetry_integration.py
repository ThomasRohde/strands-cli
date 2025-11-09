"""Integration tests for Phase 10 telemetry fixes.

Verifies that:
1. Executors emit spans when telemetry is configured
2. Trace artifacts contain all spans after force_flush
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from strands_cli.telemetry import configure_telemetry, force_flush_telemetry, get_trace_collector


@pytest.mark.asyncio
async def test_chain_executor_emits_spans_with_telemetry(
    mocker,
    tmp_path: Path,
) -> None:
    """Test that chain executor emits spans when telemetry configured.

    Regression test for Phase 10 bug where tracer was initialized at module level
    before configure_telemetry() was called, resulting in no-op tracer.
    """
    from strands_cli.exec.chain import run_chain
    from strands_cli.types import Spec

    # Create a minimal spec with telemetry config
    spec_dict = {
        "name": "test-chain",
        "version": 1,
        "runtime": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "model_id": "gpt-oss",
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "test_agent",
                        "input": "Test input: {{ topic }}",
                    }
                ]
            },
        },
        "telemetry": {
            "otel": {
                "service_name": "test-chain",
                "sample_ratio": 1.0,
            }
        },
    }

    spec = Spec(**spec_dict)

    # Configure telemetry BEFORE importing/running executor
    configure_telemetry(spec.telemetry.model_dump())

    # Mock the agent execution
    mock_agent = Mock()
    mock_agent.invoke_async = mocker.AsyncMock(return_value="test response")

    mocker.patch(
        "strands_cli.exec.chain.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Run chain executor
    result = await run_chain(spec, variables={"topic": "test"})

    assert result.success is True

    # Verify spans were collected
    collector = get_trace_collector()
    assert collector is not None

    # Force flush to ensure all spans are exported
    force_flush_telemetry(timeout_millis=5000)

    trace_data = collector.get_trace_data()
    assert trace_data["span_count"] > 0, (
        "Chain executor should emit spans when telemetry configured"
    )

    # Verify we have the execute.chain span
    span_names = [span["name"] for span in trace_data["spans"]]
    assert "execute.chain" in span_names, "Should have execute.chain root span"

    # Cleanup
    from strands_cli.telemetry import shutdown_telemetry

    shutdown_telemetry()


@pytest.mark.asyncio
async def test_workflow_executor_emits_spans_with_telemetry(
    mocker,
    tmp_path: Path,
) -> None:
    """Test that workflow executor emits spans when telemetry configured.

    Regression test for Phase 10 bug where tracer was initialized at module level.
    """
    from strands_cli.exec.workflow import run_workflow
    from strands_cli.types import Spec

    # Create a minimal spec with telemetry config
    spec_dict = {
        "name": "test-workflow",
        "version": 1,
        "runtime": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "model_id": "gpt-oss",
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "workflow",
            "config": {
                "tasks": [
                    {
                        "id": "task1",
                        "agent": "test_agent",
                        "input": "Test input: {{ topic }}",
                    }
                ]
            },
        },
        "telemetry": {
            "otel": {
                "service_name": "test-workflow",
                "sample_ratio": 1.0,
            }
        },
    }

    spec = Spec(**spec_dict)

    # Configure telemetry BEFORE running executor
    configure_telemetry(spec.telemetry.model_dump())

    # Mock the agent execution
    mock_agent = Mock()
    mock_agent.invoke_async = mocker.AsyncMock(return_value="test response")

    mocker.patch(
        "strands_cli.exec.workflow.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Run workflow executor
    result = await run_workflow(spec, variables={"topic": "test"})

    assert result.success is True

    # Verify spans were collected
    collector = get_trace_collector()
    assert collector is not None

    # Force flush to ensure all spans are exported
    force_flush_telemetry(timeout_millis=5000)

    trace_data = collector.get_trace_data()
    assert trace_data["span_count"] > 0, (
        "Workflow executor should emit spans when telemetry configured"
    )

    # Verify we have the execute.workflow span
    span_names = [span["name"] for span in trace_data["spans"]]
    assert "execute.workflow" in span_names, "Should have execute.workflow root span"

    # Cleanup
    from strands_cli.telemetry import shutdown_telemetry

    shutdown_telemetry()


@pytest.mark.asyncio
async def test_force_flush_exports_all_spans(mocker, tmp_path: Path) -> None:
    """Test that force_flush_telemetry ensures all spans are exported.

    Verifies the fix for trace artifact generation - spans must be flushed
    before collecting trace data, otherwise BatchSpanProcessor may not have
    exported them yet.
    """
    from strands_cli.telemetry import configure_telemetry, get_trace_collector

    # Configure telemetry with console exporter
    config = {
        "otel": {
            "service_name": "flush-test",
            "sample_ratio": 1.0,
        }
    }

    configure_telemetry(config)

    # Get tracer and create a test span
    from strands_cli.telemetry import get_tracer

    tracer = get_tracer(__name__)

    with tracer.start_span("test_span") as span:
        span.set_attribute("test.attr", "test_value")

    # Without force_flush, spans may not be in collector yet (background export)
    # With force_flush, spans should be guaranteed to be exported

    force_flush_telemetry(timeout_millis=5000)

    collector = get_trace_collector()
    assert collector is not None

    trace_data = collector.get_trace_data()
    assert trace_data["span_count"] >= 1, "Force flush should ensure spans are exported"

    span_names = [span["name"] for span in trace_data["spans"]]
    assert "test_span" in span_names, "Should find the test span after force_flush"

    # Cleanup
    from strands_cli.telemetry import shutdown_telemetry

    shutdown_telemetry()


@pytest.mark.asyncio
async def test_context_propagation_to_logs(mocker, tmp_path: Path) -> None:
    """Test that trace context propagates to structured logs.

    Regression test for Phase 10 fix: start_as_current_span ensures that
    trace_id and span_id are injected into log entries via add_otel_context processor.
    """
    import structlog

    from strands_cli.exec.chain import run_chain
    from strands_cli.types import Spec

    # Create a minimal spec with telemetry config
    spec_dict = {
        "name": "test-context-propagation",
        "version": 1,
        "runtime": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "model_id": "gpt-oss",
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "test_agent",
                        "input": "Test input",
                    }
                ]
            },
        },
        "telemetry": {
            "otel": {
                "service_name": "test-context",
                "sample_ratio": 1.0,
            }
        },
    }

    spec = Spec(**spec_dict)

    # Capture log output to verify trace_id injection
    log_entries = []

    def capture_processor(logger, method_name, event_dict):
        log_entries.append(event_dict.copy())
        return event_dict

    # Reconfigure structlog with capture processor
    from strands_cli.telemetry import add_otel_context

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_otel_context,  # Inject trace_id and span_id
            capture_processor,  # Capture for assertion
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Configure telemetry BEFORE running executor
    configure_telemetry(spec.telemetry.model_dump())

    # Mock the agent execution
    mock_agent = Mock()
    mock_agent.invoke_async = mocker.AsyncMock(return_value="test response")

    mocker.patch(
        "strands_cli.exec.chain.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Run chain executor
    result = await run_chain(spec)

    assert result.success is True

    # Verify that log entries have trace_id and span_id
    # Filter log entries from the chain executor
    chain_logs = [log for log in log_entries if "chain_execution" in log.get("event", "")]

    assert len(chain_logs) > 0, "Should have chain execution logs"

    # Check that at least one log entry has trace context
    logs_with_trace = [log for log in chain_logs if "trace_id" in log and "span_id" in log]

    assert len(logs_with_trace) > 0, (
        "At least one chain log should have trace_id and span_id injected. "
        "This verifies that start_as_current_span properly propagates context to logs."
    )

    # Verify trace_id format (32 hex chars)
    for log in logs_with_trace:
        trace_id = log["trace_id"]
        assert len(trace_id) == 32, f"trace_id should be 32 hex chars, got {trace_id}"
        assert all(c in "0123456789abcdef" for c in trace_id), (
            f"trace_id should be hex, got {trace_id}"
        )

    # Cleanup
    from strands_cli.telemetry import shutdown_telemetry

    shutdown_telemetry()

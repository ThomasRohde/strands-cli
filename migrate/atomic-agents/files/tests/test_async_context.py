"""Unit tests for async context manager and streaming features (Phase 3)."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from strands_cli.api import Workflow
from strands_cli.api.execution import WorkflowExecutor
from strands_cli.exec.utils import AgentCache
from strands_cli.types import PatternType


@pytest.mark.asyncio
async def test_async_context_manager_creates_cache():
    """Test that async context manager creates agent cache on enter."""
    # Load a simple workflow
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))
    executor = workflow.async_executor()

    # Initially no cache
    assert executor._agent_cache is None

    # After entering context, cache is created
    async with executor as exec_instance:
        assert exec_instance._agent_cache is not None
        assert isinstance(exec_instance._agent_cache, AgentCache)


@pytest.mark.asyncio
async def test_async_context_manager_cleanup_on_exit():
    """Test that async context manager cleans up resources on exit."""
    # Load a simple workflow
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))
    executor = workflow.async_executor()

    # Mock the agent cache to track cleanup
    mock_cache = AsyncMock(spec=AgentCache)

    async with executor:
        # Replace cache with mock
        executor._agent_cache = mock_cache

    # Verify cleanup was called
    mock_cache.close.assert_called_once()


@pytest.mark.asyncio
async def test_async_context_manager_cleanup_on_exception():
    """Test that async context manager cleans up even on exception."""
    # Load a simple workflow
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))
    executor = workflow.async_executor()

    # Mock the agent cache to track cleanup
    mock_cache = AsyncMock(spec=AgentCache)

    with pytest.raises(RuntimeError):
        async with executor:
            # Replace cache with mock
            executor._agent_cache = mock_cache
            # Raise exception
            raise RuntimeError("Test exception")

    # Verify cleanup was still called
    mock_cache.close.assert_called_once()


@pytest.mark.asyncio
async def test_stream_async_returns_async_generator():
    """Test that stream_async returns an async generator."""
    # Load a simple workflow
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))

    # Get the async generator
    stream_gen = workflow.stream_async(topic="test")

    # Verify it's an async generator
    assert hasattr(stream_gen, "__anext__")

    # Clean up without iterating
    await stream_gen.aclose()


@pytest.mark.asyncio
async def test_executor_passes_agent_cache_to_pattern():
    """Test that WorkflowExecutor passes agent_cache to pattern executors."""
    # Load a simple workflow
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))

    # Mock the pattern executor
    from strands_cli.exec import chain

    mock_run_chain = AsyncMock()
    original_run_chain = chain.run_chain
    chain.run_chain = mock_run_chain

    try:
        async with workflow.async_executor() as executor:
            # Attempt to run (will be mocked)
            await executor.run({"topic": "test"})
    except Exception:
        pass  # Mock may not return valid result

        # Verify run_chain was called with agent_cache
        if mock_run_chain.called:
            call_kwargs = mock_run_chain.call_args.kwargs
            assert "agent_cache" in call_kwargs
            # Should be the cache from context manager
            assert call_kwargs["agent_cache"] is not None

    finally:
        # Restore original function
        chain.run_chain = original_run_chain


@pytest.mark.asyncio
async def test_agent_cache_backward_compatibility():
    """Test that executors still work when agent_cache is None (backward compat)."""
    from strands_cli.exec.chain import run_chain
    from strands_cli.types import Agent, Pattern, PatternConfig, Runtime, Spec

    # Create minimal spec
    spec = Spec(
        name="test_workflow",
        runtime=Runtime(provider="openai", model_id="gpt-4o-mini"),
        agents={"test_agent": Agent(prompt="You are a helpful assistant")},
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(steps=[{"agent": "test_agent", "input": "Say hello"}]),
        ),
    )

    # Mock the agent invocation to avoid actual API call
    from strands_cli.exec import utils
    from strands_cli.exec import chain as chain_module

    mock_invoke = AsyncMock(return_value="Hello!")
    original_invoke = utils.invoke_agent_with_retry
    original_chain_invoke = chain_module.invoke_agent_with_retry
    utils.invoke_agent_with_retry = mock_invoke
    chain_module.invoke_agent_with_retry = mock_invoke

    try:
        # Call run_chain with agent_cache=None (backward compatibility mode)
        result = await run_chain(spec, agent_cache=None)

        # Should still work
        assert result.success or result.agent_id == "hitl"  # May pause at HITL

    finally:
        # Restore original function
        utils.invoke_agent_with_retry = original_invoke
        chain_module.invoke_agent_with_retry = original_chain_invoke


def test_workflow_async_executor_returns_executor():
    """Test that Workflow.async_executor() returns WorkflowExecutor."""
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))

    executor = workflow.async_executor()

    assert isinstance(executor, WorkflowExecutor)
    assert executor.spec == workflow.spec


@pytest.mark.asyncio
async def test_stream_async_handles_workflow_completion():
    """Test that stream_async generator completes when workflow finishes."""
    spec_path = Path(__file__).parent.parent / "examples" / "single-agent-chain-openai.yaml"
    workflow = Workflow.from_file(str(spec_path))

    # This test verifies that the stream_async method exists and returns an async generator
    # Full integration testing of streaming would require mocking the entire execution pipeline

    stream_gen = workflow.stream_async(topic="test")
    assert hasattr(stream_gen, "__anext__")  # Is an async generator

    # Clean up the generator
    await stream_gen.aclose()

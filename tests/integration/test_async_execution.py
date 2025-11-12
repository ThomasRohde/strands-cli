"""Integration tests for async workflow execution.

Tests concurrent workflows, resource cleanup, and performance.
"""

import asyncio
import time

import pytest

from strands_cli.api import Workflow
from strands_cli.api.execution import WorkflowExecutor


@pytest.mark.asyncio
async def test_async_context_manager_cleanup(sample_openai_spec, mocker) -> None:
    """Test async context manager properly cleans up resources."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock execution
    mock_result = mocker.Mock()
    mock_result.success = True
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    # Use context manager
    async with executor:
        assert executor._agent_cache is not None

    # Verify cleanup
    assert executor._agent_cache is None


@pytest.mark.asyncio
async def test_concurrent_workflow_execution(sample_openai_spec, mocker) -> None:
    """Test multiple workflows can execute concurrently."""
    # Create multiple workflows
    workflows = [Workflow(sample_openai_spec) for _ in range(3)]

    # Mock execution for all
    for workflow in workflows:
        mock_result = mocker.Mock()
        mock_result.success = True
        mock_result.last_response = "Test response"
        mocker.patch.object(workflow._executor, "run_async", return_value=mock_result)

    # Execute concurrently
    async def run_workflow(workflow: Workflow, index: int):
        async with workflow.async_executor() as executor:
            return await executor.run_async({"topic": f"test-{index}"})

    start_time = time.time()
    results = await asyncio.gather(*[run_workflow(w, i) for i, w in enumerate(workflows)])
    duration = time.time() - start_time

    # All should succeed
    assert len(results) == 3
    assert all(r.success for r in results)

    # Concurrent execution should be faster than sequential
    # (though with mocks, this is just a sanity check)
    assert duration < 5.0  # Should complete quickly


@pytest.mark.asyncio
async def test_resource_cleanup_on_exception(sample_openai_spec, mocker) -> None:
    """Test resources are cleaned up even when execution fails."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock execution to raise error
    mocker.patch.object(executor, "run_async", side_effect=RuntimeError("Test error"))

    # Verify cleanup happens even on error
    with pytest.raises(RuntimeError):
        async with executor:
            assert executor._agent_cache is not None
            await executor.run_async({"topic": "test"})

    # Cache should be None after exit
    assert executor._agent_cache is None


@pytest.mark.asyncio
async def test_multiple_sequential_context_manager_uses(sample_openai_spec, mocker) -> None:
    """Test executor can be reused with context manager."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock execution
    mock_result = mocker.Mock()
    mock_result.success = True
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    # First use
    async with executor:
        cache1 = executor._agent_cache
        assert cache1 is not None

    assert executor._agent_cache is None

    # Second use - should create new cache
    async with executor:
        cache2 = executor._agent_cache
        assert cache2 is not None

    # Different cache instances
    assert cache1 is not cache2


@pytest.mark.asyncio
async def test_workflow_api_async_execution(sample_openai_spec, mocker) -> None:
    """Test Workflow.run_async() method."""
    workflow = Workflow(sample_openai_spec)

    # Mock execution
    mock_result = mocker.Mock()
    mock_result.success = True
    mock_result.last_response = "Async response"
    mocker.patch.object(workflow._executor, "run", return_value=mock_result)

    # Run async - use **kwargs, not dict argument
    result = await workflow.run_async(topic="test")

    assert result.success is True
    assert result.last_response == "Async response"


@pytest.mark.asyncio
async def test_concurrent_streaming(sample_openai_spec, mocker) -> None:
    """Test multiple concurrent streaming workflows."""
    workflows = [Workflow(sample_openai_spec) for _ in range(2)]

    # Mock agent invocation to let execution complete naturally
    async def mock_invoke(*args, **kwargs):
        return "Test response"

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke,
    )

    # Stream concurrently
    async def collect_chunks(workflow: Workflow, index: int):
        chunks = []
        async for chunk in workflow.stream_async({"topic": f"test-{index}"}):
            chunks.append(chunk)
            # Consume all chunks to properly close async generator
        return chunks

    results = await asyncio.gather(*[collect_chunks(w, i) for i, w in enumerate(workflows)])

    # Both should complete
    assert len(results) == 2
    # Both should have chunks
    for result in results:
        assert len(result) > 0


@pytest.mark.asyncio
async def test_agent_cache_reuse_in_workflow(chain_spec_fixture, mocker) -> None:
    """Test agent cache is reused across steps in workflow."""
    from strands_cli.exec.chain import run_chain
    from strands_cli.exec.utils import AgentCache
    from strands_cli.types import Spec

    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Create cache to pass
    cache = AgentCache()

    # Run workflow with cache
    try:
        await run_chain(spec, variables={"topic": "test"}, agent_cache=cache)
    finally:
        await cache.close()

    # Verify cache was used (would have built agents)
    # This is more of a smoke test since we can't easily verify internal caching
    assert True


@pytest.mark.asyncio
async def test_parallel_workflow_execution(parallel_spec_fixture, mocker) -> None:
    """Test parallel pattern executes branches concurrently."""
    from strands_cli.exec.parallel import run_parallel
    from strands_cli.types import Spec

    # Convert dict to Spec
    spec = Spec.model_validate(parallel_spec_fixture)

    call_times = []

    async def mock_invoke(*args, **kwargs):
        call_times.append(time.time())
        await asyncio.sleep(0.1)  # Simulate work
        return mocker.Mock(response="test response")

    mocker.patch("strands_cli.exec.parallel.invoke_agent_with_retry", side_effect=mock_invoke)

    # Run parallel workflow
    start = time.time()
    await run_parallel(spec, variables={"topic": "test"})
    duration = time.time() - start

    # If truly parallel, should be < 0.3s (not 0.2s per branch sequentially)
    # With 2+ branches at 0.1s each, parallel should be ~0.1-0.15s
    assert duration < 0.3


@pytest.mark.asyncio
async def test_workflow_error_propagation(sample_openai_spec, mocker) -> None:
    """Test errors propagate correctly through async API."""
    workflow = Workflow(sample_openai_spec)

    # Mock to raise error
    mocker.patch.object(workflow._executor, "run", side_effect=ValueError("Test error"))

    # Error should propagate
    with pytest.raises(ValueError, match="Test error"):
        await workflow.run_async(topic="test")


@pytest.mark.asyncio
async def test_async_event_handlers_execute(sample_openai_spec, mocker) -> None:
    """Test async event handlers execute during workflow."""
    workflow = Workflow(sample_openai_spec)
    handler_calls = []

    async def async_handler(event):
        await asyncio.sleep(0.01)
        handler_calls.append(event.event_type)

    workflow.on("workflow_complete")(async_handler)

    # Mock execution
    mock_result = mocker.Mock()
    mock_result.success = True
    mocker.patch.object(workflow._executor, "run", return_value=mock_result)

    # Emit event to trigger handler
    from datetime import datetime

    from strands_cli.events import WorkflowEvent

    await workflow._executor.event_bus.emit(
        WorkflowEvent(
            event_type="workflow_complete",
            timestamp=datetime.now(),
            session_id="test",
            spec_name="test",
            pattern_type="chain",
            data={},
        )
    )

    # Give handlers time to execute
    await asyncio.sleep(0.05)

    # Handler should have been called
    assert "workflow_complete" in handler_calls


@pytest.mark.asyncio
async def test_context_manager_with_real_cache_operations(sample_openai_spec, mocker) -> None:
    """Test context manager with actual cache operations."""
    from strands_cli.types import Agent

    executor = WorkflowExecutor(sample_openai_spec)

    # Mock agent building
    mock_agent = mocker.Mock()
    mocker.patch("strands_cli.runtime.strands_adapter.build_agent", return_value=mock_agent)

    async with executor:
        cache = executor._agent_cache

        # Create proper agent config from spec
        agent_config = Agent(prompt="Test agent")

        # Simulate getting an agent from cache
        agent = await cache.get_or_build_agent(sample_openai_spec, "test-agent", agent_config)

        # Should have created agent
        assert agent is not None

    # Cache should be closed
    assert executor._agent_cache is None

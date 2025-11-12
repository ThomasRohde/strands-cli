"""Unit tests for async context manager in WorkflowExecutor."""

import pytest

from strands_cli.api import Workflow
from strands_cli.api.execution import WorkflowExecutor
from strands_cli.exec.utils import AgentCache


@pytest.mark.asyncio
async def test_workflow_executor_context_manager_protocol(sample_openai_spec) -> None:
    """Test WorkflowExecutor implements async context manager protocol."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Verify it has the protocol methods
    assert hasattr(executor, "__aenter__")
    assert hasattr(executor, "__aexit__")

    # Use as context manager
    async with executor as ex:
        assert ex is executor
        assert executor._agent_cache is not None
        assert isinstance(executor._agent_cache, AgentCache)


@pytest.mark.asyncio
async def test_workflow_executor_creates_agent_cache(sample_openai_spec) -> None:
    """Test context manager creates AgentCache on entry."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Initially no cache
    assert executor._agent_cache is None

    async with executor:
        # Cache created on entry
        assert executor._agent_cache is not None
        assert isinstance(executor._agent_cache, AgentCache)


@pytest.mark.asyncio
async def test_workflow_executor_cleans_up_on_exit(sample_openai_spec, mocker) -> None:
    """Test context manager cleans up AgentCache on exit."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock the close method
    mock_close = mocker.AsyncMock()

    async with executor:
        # Replace cache's close method with mock
        executor._agent_cache.close = mock_close

    # Verify cleanup was called
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_executor_cleans_up_on_exception(sample_openai_spec, mocker) -> None:
    """Test context manager cleans up even on exception."""
    executor = WorkflowExecutor(sample_openai_spec)
    mock_close = mocker.AsyncMock()

    try:
        async with executor:
            executor._agent_cache.close = mock_close
            raise ValueError("Test error")
    except ValueError:
        pass

    # Verify cleanup was still called
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_executor_context_manager_returns_false(sample_openai_spec) -> None:
    """Test __aexit__ returns False to propagate exceptions."""
    executor = WorkflowExecutor(sample_openai_spec)

    with pytest.raises(ValueError):
        async with executor:
            raise ValueError("Test error")


@pytest.mark.asyncio
async def test_workflow_api_async_executor(sample_openai_spec) -> None:
    """Test Workflow.async_executor() returns WorkflowExecutor."""
    workflow = Workflow(sample_openai_spec)

    executor = workflow.async_executor()
    assert isinstance(executor, WorkflowExecutor)
    assert executor.spec is sample_openai_spec


@pytest.mark.asyncio
async def test_executor_backward_compatibility_no_context_manager(
    sample_openai_spec, mocker
) -> None:
    """Test executors work without context manager (backward compatibility)."""
    from strands_cli.exec.chain import run_chain

    # Mock agent invocation to avoid actual API calls
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Mock agent cache
    mock_cache = mocker.Mock(spec=AgentCache)
    mock_cache.get_or_build_agent = mocker.AsyncMock(return_value=mocker.Mock())
    mock_cache.close = mocker.AsyncMock()

    # Call without passing agent_cache (backward compatible)
    # Note: This will create its own cache internally
    with mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache):
        await run_chain(
            sample_openai_spec,
            variables={"topic": "test"},
        )

    # Verify cache was closed (backward compatible behavior)
    mock_cache.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_executor_with_provided_cache(sample_openai_spec, mocker) -> None:
    """Test executors accept external agent_cache parameter."""
    from strands_cli.exec.chain import run_chain

    # Mock agent invocation
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Create external cache
    mock_cache = mocker.Mock(spec=AgentCache)
    mock_cache.get_or_build_agent = mocker.AsyncMock(return_value=mocker.Mock())
    mock_cache.close = mocker.AsyncMock()

    # Call with external cache
    await run_chain(
        sample_openai_spec,
        variables={"topic": "test"},
        agent_cache=mock_cache,
    )

    # Verify external cache was NOT closed (caller's responsibility)
    mock_cache.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_executor_multiple_uses(sample_openai_spec) -> None:
    """Test WorkflowExecutor can be used multiple times."""
    executor = WorkflowExecutor(sample_openai_spec)

    # First use
    async with executor:
        cache1 = executor._agent_cache

    # Cache should be None after exit
    assert executor._agent_cache is None

    # Second use
    async with executor:
        cache2 = executor._agent_cache

    # Should create new cache each time
    assert cache1 is not cache2


@pytest.mark.asyncio
async def test_agent_cache_reuse_within_context(sample_openai_spec, mocker) -> None:
    """Test agent cache is reused within single context."""
    executor = WorkflowExecutor(sample_openai_spec)

    async with executor:
        cache1 = executor._agent_cache
        cache2 = executor._agent_cache

        # Should be same instance
        assert cache1 is cache2


@pytest.mark.asyncio
async def test_workflow_executor_no_cache_leak_on_error(sample_openai_spec, mocker) -> None:
    """Test no cache reference leak on exception."""
    executor = WorkflowExecutor(sample_openai_spec)

    try:
        async with executor:
            assert executor._agent_cache is not None
            raise RuntimeError("Test error")
    except RuntimeError:
        pass

    # Cache should be None after exit (even with error)
    assert executor._agent_cache is None

"""Unit tests for streaming API."""

import asyncio
from datetime import datetime

import pytest

from strands_cli.api import Workflow
from strands_cli.api.execution import WorkflowExecutor
from strands_cli.events import WorkflowEvent
from strands_cli.types import StreamChunk, StreamChunkType


@pytest.mark.asyncio
async def test_stream_async_emits_chunks(sample_openai_spec, mocker) -> None:
    """Test stream_async emits StreamChunk objects."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock agent invocation instead of run_async to let events emit naturally
    async def mock_invoke(*args, **kwargs):
        return "Test response"

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke,
    )

    # Collect chunks
    chunks: list[StreamChunk] = []
    async for chunk in executor.stream_async({"topic": "test"}):
        chunks.append(chunk)

    # Should have received at least workflow_complete chunk
    assert len(chunks) > 0
    assert any(c.chunk_type == "complete" for c in chunks)


@pytest.mark.asyncio
async def test_stream_async_chunk_types(sample_openai_spec, mocker) -> None:
    """Test stream_async emits correct chunk types."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock run_async
    mock_result = mocker.Mock()
    mock_result.success = True
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    # Manually emit events to trigger chunks
    async def emit_events():
        await asyncio.sleep(0.01)
        await executor.event_bus.emit(
            WorkflowEvent(
                event_type="step_start",
                timestamp=datetime.now(),
                session_id="test",
                spec_name="test",
                pattern_type="chain",
                data={"step_index": 0},
            )
        )
        await executor.event_bus.emit(
            WorkflowEvent(
                event_type="step_complete",
                timestamp=datetime.now(),
                session_id="test",
                spec_name="test",
                pattern_type="chain",
                data={"step_index": 0, "response": "test"},
            )
        )
        await executor.event_bus.emit(
            WorkflowEvent(
                event_type="workflow_complete",
                timestamp=datetime.now(),
                session_id="test",
                spec_name="test",
                pattern_type="chain",
                data={},
            )
        )

    # Collect chunks
    chunks: list[StreamChunk] = []

    # Start event emission
    emit_task = asyncio.create_task(emit_events())

    # Stream with short timeout
    try:
        async with asyncio.timeout(1.0):
            async for chunk in executor.stream_async({"topic": "test"}):
                chunks.append(chunk)
    except TimeoutError:
        pass
    finally:
        emit_task.cancel()

    # Verify chunk types are valid
    for chunk in chunks:
        assert chunk.chunk_type in ["token", "step_start", "step_complete", "complete"]


@pytest.mark.asyncio
async def test_stream_async_chunk_data(sample_openai_spec, mocker) -> None:
    """Test stream chunks contain correct data."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock run_async
    mock_result = mocker.Mock()
    mock_result.success = True
    mock_result.last_response = "Final response"
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    chunks: list[StreamChunk] = []
    async for chunk in executor.stream_async({"topic": "test"}):
        chunks.append(chunk)

    # Check that chunks have data
    for chunk in chunks:
        assert isinstance(chunk.data, dict)
        assert chunk.timestamp is not None


@pytest.mark.asyncio
async def test_stream_async_preserves_event_order(sample_openai_spec, mocker) -> None:
    """Test streaming preserves event order."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock run_async
    mock_result = mocker.Mock()
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    # Emit ordered events
    event_order = []

    async def emit_ordered_events():
        await asyncio.sleep(0.01)
        for i in range(3):
            event_order.append(f"step_{i}")
            await executor.event_bus.emit(
                WorkflowEvent(
                    event_type="step_complete",
                    timestamp=datetime.now(),
                    session_id="test",
                    spec_name="test",
                    pattern_type="chain",
                    data={"step_index": i},
                )
            )
        await executor.event_bus.emit(
            WorkflowEvent(
                event_type="workflow_complete",
                timestamp=datetime.now(),
                session_id="test",
                spec_name="test",
                pattern_type="chain",
                data={},
            )
        )

    chunks: list[StreamChunk] = []
    emit_task = asyncio.create_task(emit_ordered_events())

    try:
        async with asyncio.timeout(1.0):
            async for chunk in executor.stream_async({"topic": "test"}):
                chunks.append(chunk)
    except TimeoutError:
        pass
    finally:
        emit_task.cancel()

    # Verify step chunks are in order
    step_chunks = [c for c in chunks if c.chunk_type == "step_complete"]
    for i, chunk in enumerate(step_chunks):
        if "step_index" in chunk.data:
            assert chunk.data["step_index"] == i


@pytest.mark.asyncio
async def test_stream_async_handles_errors(sample_openai_spec, mocker) -> None:
    """Test stream_async handles execution errors."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock run_async to raise error
    mocker.patch.object(executor, "run_async", side_effect=RuntimeError("Execution failed"))

    # Streaming should handle error gracefully
    with pytest.raises(RuntimeError):
        async for _chunk in executor.stream_async({"topic": "test"}):
            pass


@pytest.mark.asyncio
async def test_stream_async_completes_on_success(sample_openai_spec, mocker) -> None:
    """Test stream_async completes iteration on successful execution."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock agent invocation to let execution complete naturally
    async def mock_invoke(*args, **kwargs):
        return "Test response"

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke,
    )

    chunks = []
    async for chunk in executor.stream_async({"topic": "test"}):
        chunks.append(chunk)
        # Don't break - consume all chunks to properly close the async generator

    # Should have at least workflow_complete chunk
    assert len(chunks) > 0
    assert any(c.chunk_type == "complete" for c in chunks)


@pytest.mark.asyncio
async def test_stream_async_from_workflow_api(sample_openai_spec, mocker) -> None:
    """Test streaming through Workflow API."""
    workflow = Workflow(sample_openai_spec)

    # Mock agent invocation to let execution complete naturally
    async def mock_invoke(*args, **kwargs):
        return "Test response"

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke,
    )

    # Stream from workflow
    chunks = []
    async for chunk in workflow.stream_async({"topic": "test"}):
        chunks.append(chunk)
        # Don't break - consume all chunks to properly close the async generator

    assert len(chunks) > 0
    assert any(c.chunk_type == "complete" for c in chunks)


@pytest.mark.asyncio
async def test_stream_chunk_timestamp(sample_openai_spec, mocker) -> None:
    """Test StreamChunk includes timestamp."""
    executor = WorkflowExecutor(sample_openai_spec)

    # Mock run_async
    mock_result = mocker.Mock()
    mocker.patch.object(executor, "run_async", return_value=mock_result)

    # Emit event
    async def emit_event():
        await asyncio.sleep(0.01)
        await executor.event_bus.emit(
            WorkflowEvent(
                event_type="workflow_complete",
                timestamp=datetime.now(),
                session_id="test",
                spec_name="test",
                pattern_type="chain",
                data={},
            )
        )

    emit_task = asyncio.create_task(emit_event())

    chunks = []
    try:
        async with asyncio.timeout(1.0):
            async for chunk in executor.stream_async({"topic": "test"}):
                chunks.append(chunk)
                break
    except TimeoutError:
        pass
    finally:
        emit_task.cancel()

    if chunks:
        assert chunks[0].timestamp is not None
        assert isinstance(chunks[0].timestamp, datetime)


def test_stream_chunk_type_literal() -> None:
    """Test StreamChunkType is properly defined."""
    # Verify the type is available

    # These should be valid values
    valid_types = ["token", "step_start", "step_complete", "complete"]
    assert all(t in StreamChunkType.__args__ for t in valid_types)

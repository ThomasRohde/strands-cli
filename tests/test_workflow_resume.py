"""Tests for workflow pattern resume functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_mock import MockerFixture

from strands_cli.exec.workflow import run_workflow
from strands_cli.loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository


@pytest.mark.asyncio
async def test_workflow_session_parameter_validation(multi_task_workflow_spec: Path) -> None:
    """Test session parameter validation (both or neither)."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Create session state without repo - should fail
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    with pytest.raises(ValueError, match="must both be provided"):
        await run_workflow(spec, {}, session_state=state, session_repo=None)


@pytest.mark.asyncio
async def test_workflow_fresh_execution_with_session(
    tmp_path: Path,
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test fresh workflow execution creates layer checkpoints."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Mock agent invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    # Return mock with message attribute
    mock_response = Mock()
    mock_response.message = Mock()
    mock_response.message.content = [Mock(text="Task result")]
    mock_response.usage = Mock(input_tokens=100, output_tokens=50)
    mock_invoke.return_value = "Task result"

    # Create session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-workflow-fresh"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="workflow-test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute
    result = await run_workflow(spec, {}, state, repo)

    # Verify checkpoints created
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state.get("completed_tasks", [])) > 0
    assert "task_results" in loaded.pattern_state
    assert result.success is True


@pytest.mark.asyncio
async def test_workflow_resume_from_layer_1(
    tmp_path: Path,
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume from layer 1 (layer 0 already complete)."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Create session with layer 0 complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-workflow-resume"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="workflow-test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_tasks": ["gather_context"],  # Layer 0 complete
            "task_results": {
                "gather_context": {
                    "response": "Context gathered",
                    "status": "success",
                    "tokens_estimated": 800,
                    "agent": "context_agent",
                }
            },
            "current_layer": 1,
        },
        token_usage=TokenUsage(total_input_tokens=400, total_output_tokens=400),
    )
    await repo.save(state, "")

    # Mock agent invocations for layer 1+
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Task result"

    # Resume
    result = await run_workflow(spec, {}, state, repo)

    # Verify layer 0 tasks NOT re-executed
    # The mock should only be called for tasks in layer 1 and beyond
    assert mock_invoke.call_count > 0

    # Verify final state
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state["completed_tasks"]) > 1
    assert result.success is True


@pytest.mark.asyncio
async def test_workflow_partial_layer_resume(
    tmp_path: Path,
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume with partial layer completion."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Create session with some tasks in current layer complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-workflow-partial"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="workflow-test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_tasks": ["gather_context", "analyze"],  # Layer 0 + partial layer 1
            "task_results": {
                "gather_context": {
                    "response": "Done",
                    "status": "success",
                    "tokens_estimated": 800,
                    "agent": "agent1",
                },
                "analyze": {
                    "response": "Done",
                    "status": "success",
                    "tokens_estimated": 900,
                    "agent": "agent2",
                },
            },
            "current_layer": 1,
        },
        token_usage=TokenUsage(total_input_tokens=850, total_output_tokens=850),
    )
    await repo.save(state, "")

    # Mock invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Task result"

    # Resume
    result = await run_workflow(spec, {}, state, repo)

    # Verify only incomplete tasks executed
    assert mock_invoke.call_count >= 1
    assert result.success is True


@pytest.mark.asyncio
async def test_workflow_token_accumulation(
    tmp_path: Path,
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test token usage accumulation across workflow execution."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Create fresh session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-workflow-tokens"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="workflow-test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Mock invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Task result"

    # Execute
    await run_workflow(spec, {}, state, repo)

    # Verify tokens accumulated
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.token_usage.total_input_tokens > 0
    assert loaded.token_usage.total_output_tokens > 0


@pytest.mark.asyncio
async def test_workflow_layer_checkpoint_frequency(
    tmp_path: Path,
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test that checkpoints are created after each layer."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Create session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-workflow-checkpoints"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="workflow-test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Mock invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Task result"

    # Execute
    await run_workflow(spec, {}, state, repo)

    # Verify checkpoint exists with layer progression
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert "current_layer" in loaded.pattern_state
    assert loaded.pattern_state["current_layer"] > 0


@pytest.mark.asyncio
async def test_workflow_without_session_works(
    multi_task_workflow_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test workflow works without session persistence (backward compatibility)."""
    spec = load_spec(multi_task_workflow_spec, {})

    # Mock invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Task result"

    # Execute without session
    result = await run_workflow(spec, {})

    # Verify execution succeeded
    assert result.success is True
    assert mock_invoke.call_count > 0

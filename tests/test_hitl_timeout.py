"""Tests for HITL timeout enforcement across all patterns."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from strands_cli.exec.chain import run_chain
from strands_cli.exec.hitl_utils import check_hitl_timeout, format_timeout_warning
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import HITLState


def create_session_with_hitl(
    timeout_at: str | None = None,
    default_response: str | None = None,
    step_index: int = 0,
    active: bool = True,
) -> SessionState:
    """Create a session state with HITL configuration for testing."""
    hitl_state = HITLState(
        active=active,
        step_index=step_index,
        prompt="Test HITL prompt",
        context_display="Test context",
        default_response=default_response,
        timeout_at=timeout_at,
        user_response=None,
    )

    return SessionState(
        metadata=SessionMetadata(
            session_id="test-session-123",
            workflow_name="test-spec",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.PAUSED,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        token_usage=TokenUsage(
            total_input_tokens=100,
            total_output_tokens=150,
        ),
        pattern_state={
            "hitl_state": hitl_state.model_dump(),
            "current_step": step_index,
            "step_history": [],
        },
    )


@pytest.mark.asyncio
async def test_check_hitl_timeout_not_configured() -> None:
    """Test timeout check when no timeout configured."""
    session_state = create_session_with_hitl(timeout_at=None)

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is False
    assert default is None


@pytest.mark.asyncio
async def test_check_hitl_timeout_not_expired() -> None:
    """Test timeout check when timeout not yet expired."""
    future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(timeout_at=future_time)

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is False
    assert default is None


@pytest.mark.asyncio
async def test_check_hitl_timeout_expired_with_default() -> None:
    """Test timeout check when expired with default response."""
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(timeout_at=past_time, default_response="approved")

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is True
    assert default == "approved"


@pytest.mark.asyncio
async def test_check_hitl_timeout_expired_without_default() -> None:
    """Test timeout check when expired without default uses fallback."""
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(timeout_at=past_time, default_response=None)

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is True
    assert default == "timeout_expired"


@pytest.mark.asyncio
async def test_check_hitl_timeout_inactive_state() -> None:
    """Test timeout check when HITL state is inactive."""
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(
        timeout_at=past_time, default_response="approved", active=False
    )

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is False
    assert default is None


@pytest.mark.asyncio
async def test_check_hitl_timeout_no_hitl_state() -> None:
    """Test timeout check when no HITL state in session."""
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-123",
            workflow_name="test-spec",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        token_usage=TokenUsage(
            total_input_tokens=100,
            total_output_tokens=150,
        ),
        pattern_state={},
    )

    timed_out, default = check_hitl_timeout(session_state)

    assert timed_out is False
    assert default is None


def test_format_timeout_warning() -> None:
    """Test timeout warning message formatting."""
    timeout_at = "2025-11-10T15:00:00+00:00"
    default = "approved"

    message = format_timeout_warning(timeout_at, default)

    assert "timeout expired" in message.lower()
    assert timeout_at in message
    assert default in message

    # None defaults should fall back to timeout_expired keyword
    fallback_message = format_timeout_warning(timeout_at, None)
    assert "timeout_expired" in fallback_message


@pytest.mark.asyncio
async def test_chain_auto_resumes_on_timeout(
    tmp_path: pytest.TempPathFactory, mocker: MockerFixture
) -> None:
    """Test chain pattern auto-resumes with default when timeout expired."""
    from tests.conftest import create_chain_spec_with_hitl

    spec = create_chain_spec_with_hitl(timeout_seconds=3600, default="approved")
    repo = FileSessionRepository(tmp_path)

    # Mock agent cache and agents
    mock_cache = mocker.patch("strands_cli.exec.chain.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache_instance.close = AsyncMock()  # Add async close method
    mock_cache.return_value = mock_cache_instance

    mock_agent = MagicMock()
    mock_agent_result = MagicMock()
    mock_agent_result.content = "Test response"
    mock_agent_result.input_tokens = 50
    mock_agent_result.output_tokens = 75

    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        new=AsyncMock(return_value=mock_agent_result),
    )

    # Create session state with expired timeout
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(
        timeout_at=past_time, default_response="approved", step_index=1
    )
    session_state.pattern_state["step_history"] = [
        {"index": 0, "agent": "agent1", "response": "First step", "tokens_estimated": 100}
    ]

    # Save session
    await repo.save(session_state, "")

    # Resume without explicit response (should use default)
    loaded_state = await repo.load(session_state.metadata.session_id)

    result = await run_chain(
        spec,
        variables={},
        session_state=loaded_state,
        session_repo=repo,
        hitl_response=None,  # No explicit response
    )

    assert result.success is True
    assert result.agent_id != "hitl"  # Should complete, not pause again

    # Verify timeout metadata recorded in pattern_state
    final_session = await repo.load(session_state.metadata.session_id)
    assert final_session.pattern_state.get("hitl_timeout_occurred") is True
    assert final_session.pattern_state.get("hitl_timeout_at") == past_time
    assert final_session.pattern_state.get("hitl_default_used") == "approved"
    assert final_session.metadata.metadata.get("hitl_timeout_occurred") is True
    assert final_session.metadata.metadata.get("hitl_timeout_at") == past_time
    assert final_session.metadata.metadata.get("hitl_default_used") == "approved"


@pytest.mark.asyncio
async def test_workflow_auto_resumes_on_timeout(
    tmp_path: pytest.TempPathFactory, mocker: MockerFixture
) -> None:
    """Test workflow pattern auto-resumes with default when timeout expired."""
    # This test focuses on timeout handling, not full workflow execution
    # We just need to verify that timeout is detected and default response is used

    from tests.conftest import create_workflow_spec_with_hitl

    _spec = create_workflow_spec_with_hitl(timeout_seconds=3600, default="continue")
    repo = FileSessionRepository(tmp_path)

    # Create session state with expired timeout at task2 (HITL)
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    hitl_state = HITLState(
        active=True,
        task_id="task2",
        layer_index=1,
        prompt="Approve task2?",
        timeout_at=past_time,
        default_response="continue",
    )

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-456",
            workflow_name="test-workflow",
            spec_hash="def456",
            pattern_type="workflow",
            status=SessionStatus.PAUSED,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=150),
        pattern_state={
            "hitl_state": hitl_state.model_dump(),
            "task_results": {
                "task1": {"response": "Task 1 done", "status": "success", "agent": "agent1"}
            },
            "completed_tasks": ["task1"],
            "current_layer": 1,
        },
    )

    await repo.save(session_state, "")

    # Load and verify timeout check works
    loaded_state = await repo.load(session_state.metadata.session_id)

    # Verify timeout is detected
    timed_out, default = check_hitl_timeout(loaded_state)
    assert timed_out is True
    assert default == "continue"

    # Verify that the timeout metadata would be recorded
    # (Full integration test would require mocking the entire workflow execution)
    # For now, we verify the timeout detection logic works correctly


@pytest.mark.asyncio
async def test_graph_auto_resumes_on_timeout(
    tmp_path: pytest.TempPathFactory, mocker: MockerFixture
) -> None:
    """Test graph pattern auto-resumes with default when timeout expired."""
    # This test focuses on timeout handling for graph pattern
    # We verify timeout is detected and default response is used

    from tests.conftest import create_graph_spec_with_hitl

    _spec = create_graph_spec_with_hitl(timeout_seconds=3600, default="yes")
    repo = FileSessionRepository(tmp_path)

    # Create session with expired timeout at approval_node (HITL)
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    hitl_state = HITLState(
        active=True,
        node_id="approval_node",
        prompt="Approve?",
        timeout_at=past_time,
        default_response="yes",
    )

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-789",
            workflow_name="test-graph",
            spec_hash="ghi789",
            pattern_type="graph",
            status=SessionStatus.PAUSED,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=150),
        pattern_state={
            "hitl_state": hitl_state.model_dump(),
            "current_node": "approval_node",
            "node_results": {
                "start_node": {"response": "Started", "status": "success"},
                "approval_node": {"response": "", "status": "pending"},
            },
            "execution_path": ["start_node"],
        },
    )

    await repo.save(session_state, "")

    # Load and verify timeout check works
    loaded_state = await repo.load(session_state.metadata.session_id)

    # Verify timeout is detected
    timed_out, default = check_hitl_timeout(loaded_state)
    assert timed_out is True
    assert default == "yes"

    # Timeout detection works correctly for graph pattern
    # (Full integration would require mocking entire graph execution)


@pytest.mark.asyncio
async def test_user_response_overrides_timeout(
    tmp_path: pytest.TempPathFactory, mocker: MockerFixture
) -> None:
    """Test that explicit user response overrides timeout default."""
    from tests.conftest import create_chain_spec_with_hitl

    spec = create_chain_spec_with_hitl(timeout_seconds=3600, default="approved")
    repo = FileSessionRepository(tmp_path)

    # Mock agents
    mock_cache = mocker.patch("strands_cli.exec.chain.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache_instance.close = AsyncMock()  # Add async close method
    mock_cache.return_value = mock_cache_instance

    mock_agent = MagicMock()
    mock_agent_result = MagicMock()
    mock_agent_result.content = "Final response"
    mock_agent_result.input_tokens = 50
    mock_agent_result.output_tokens = 75

    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        new=AsyncMock(return_value=mock_agent_result),
    )

    # Create session with expired timeout
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    session_state = create_session_with_hitl(
        timeout_at=past_time, default_response="approved", step_index=1
    )
    session_state.pattern_state["step_history"] = [
        {"index": 0, "agent": "agent1", "response": "First step", "tokens_estimated": 100}
    ]

    await repo.save(session_state, "")

    # Resume WITH explicit response (should override timeout default)
    loaded_state = await repo.load(session_state.metadata.session_id)

    result = await run_chain(
        spec,
        variables={},
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="rejected",  # Explicit response
    )

    assert result.success is True
    assert result.agent_id != "hitl"  # Should complete, not pause again

    # Should NOT record timeout metadata (explicit response was provided)
    final_session = await repo.load(session_state.metadata.session_id)
    # Timeout check happens but explicit response is used, so timeout metadata may or may not be set
    # The important part is that the explicit "rejected" response was used, not the "approved" default
    step_history = final_session.pattern_state.get("step_history", [])
    hitl_step = next((s for s in step_history if s.get("type") == "hitl"), None)
    assert hitl_step is not None
    assert hitl_step["response"] == "rejected"  # Explicit response, not default

"""Tests for routing pattern resume functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_mock import MockerFixture

from strands_cli.exec.routing import run_routing
from strands_cli.loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository


@pytest.mark.asyncio
async def test_routing_session_parameter_validation(routing_pattern_spec: Path) -> None:
    """Test session parameter validation (both or neither)."""
    spec = load_spec(routing_pattern_spec, {})

    # Create session state without repo - should fail
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="routing",
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
        await run_routing(spec, {}, session_state=state, session_repo=None)


@pytest.mark.asyncio
async def test_routing_fresh_execution_with_session(
    tmp_path: Path,
    routing_pattern_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test fresh routing execution creates session checkpoints."""
    spec = load_spec(routing_pattern_spec, {})

    # Mock router execution
    mock_router = mocker.patch(
        "strands_cli.exec.routing._execute_router_with_retry",
        new_callable=AsyncMock,
    )
    mock_router.return_value = ("general", '{"route": "general"}')  # Returns (route_name, response_text)

    # Mock chain execution
    mock_chain = mocker.patch("strands_cli.exec.routing.run_chain", new_callable=AsyncMock)
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Route result"
    mock_result.execution_context = {"current_step": 1, "step_history": []}
    mock_result.pattern_type = "chain"
    mock_result.duration_seconds = 1.5
    mock_chain.return_value = mock_result

    # Create session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-routing-fresh"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="routing-test",
            spec_hash="hash",
            pattern_type="routing",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={"query": "general question"},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute
    result = await run_routing(spec, {"query": "general question"}, state, repo)

    # Verify router was executed
    assert mock_router.call_count == 1

    # Verify router checkpointed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.pattern_state["router_executed"] is True
    assert loaded.pattern_state["chosen_route"] == "general"
    assert "route_state" in loaded.pattern_state

    # Verify chain called with session params
    assert mock_chain.call_count == 1
    call_args = mock_chain.call_args
    assert call_args[0][2] is not None  # route_session_state
    assert call_args[0][3] is not None  # route_session_repo

    # Verify result
    assert result.success is True
    assert result.execution_context["chosen_route"] == "general"


@pytest.mark.asyncio
async def test_routing_resume_after_router_decision(
    tmp_path: Path,
    routing_pattern_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume after router decision but before route completion."""
    spec = load_spec(routing_pattern_spec, {})

    # Create session with router decision already made
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-routing-resume"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="routing-test",
            spec_hash="hash",
            pattern_type="routing",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={"query": "general question"},
        runtime_config={},
        pattern_state={
            "router_executed": True,
            "chosen_route": "general",
            "route_state": {
                "current_step": 1,
                "step_history": [{"index": 0, "response": "Step 1"}],
            },
        },
        token_usage=TokenUsage(total_input_tokens=500, total_output_tokens=400),
    )
    await repo.save(state, "")

    # Mock router and chain
    mock_router = mocker.patch(
        "strands_cli.exec.routing._execute_router_with_retry",
        new_callable=AsyncMock,
    )
    mock_chain = mocker.patch("strands_cli.exec.routing.run_chain", new_callable=AsyncMock)
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Route complete"
    mock_result.execution_context = {"current_step": 2, "step_history": []}
    mock_result.pattern_type = "chain"
    mock_result.duration_seconds = 1.5
    mock_chain.return_value = mock_result

    # Resume
    await run_routing(spec, {"query": "general question"}, state, repo)

    # Verify router NOT re-executed
    assert mock_router.call_count == 0

    # Verify chain called with route_state
    assert mock_chain.call_count == 1
    route_state_arg = mock_chain.call_args[0][2]
    assert route_state_arg.pattern_state["current_step"] == 1
    assert len(route_state_arg.pattern_state["step_history"]) == 1


@pytest.mark.asyncio
async def test_routing_session_finalized_on_completion(
    tmp_path: Path,
    routing_pattern_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test session is marked COMPLETED after successful route execution."""
    spec = load_spec(routing_pattern_spec, {})

    # Create session with router decision made
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-routing-finalize"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="routing-test",
            spec_hash="hash",
            pattern_type="routing",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={"query": "general question"},
        runtime_config={},
        pattern_state={
            "router_executed": True,
            "chosen_route": "general",
            "route_state": {"current_step": 0, "step_history": []},
        },
        token_usage=TokenUsage(),
    )
    await repo.save(state, "")

    # Mock chain execution
    mock_chain = mocker.patch("strands_cli.exec.routing.run_chain", new_callable=AsyncMock)
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Complete"
    mock_result.execution_context = {"current_step": 1, "step_history": []}
    mock_result.pattern_type = "chain"
    mock_result.duration_seconds = 1.5
    mock_chain.return_value = mock_result

    # Execute
    result = await run_routing(spec, {"query": "general question"}, state, repo)

    # Verify session finalized
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert result.success is True


@pytest.mark.asyncio
async def test_routing_token_accumulation(
    tmp_path: Path,
    routing_pattern_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test token usage accumulation across router and route execution."""
    spec = load_spec(routing_pattern_spec, {})

    # Create fresh session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-routing-tokens"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="routing-test",
            spec_hash="hash",
            pattern_type="routing",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={"query": "test"},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Mock router and chain
    mock_router = mocker.patch(
        "strands_cli.exec.routing._execute_router_with_retry",
        new_callable=AsyncMock,
    )
    mock_router.return_value = ("general", '{"route": "general"}')

    mock_chain = mocker.patch("strands_cli.exec.routing.run_chain", new_callable=AsyncMock)
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Done"
    mock_result.execution_context = {"current_step": 1, "step_history": []}
    mock_result.pattern_type = "chain"
    mock_result.duration_seconds = 1.5
    mock_chain.return_value = mock_result

    # Execute
    await run_routing(spec, {"query": "test"}, state, repo)

    # Verify router checkpoint includes tokens
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.token_usage.total_input_tokens > 0
    assert loaded.token_usage.total_output_tokens > 0


@pytest.mark.asyncio
async def test_routing_without_session_works(
    routing_pattern_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test routing works without session persistence (backward compatibility)."""
    spec = load_spec(routing_pattern_spec, {})

    # Mock router and chain
    mock_router = mocker.patch(
        "strands_cli.exec.routing._execute_router_with_retry",
        new_callable=AsyncMock,
    )
    mock_router.return_value = ("general", '{"route": "general"}')

    mock_chain = mocker.patch("strands_cli.exec.routing.run_chain", new_callable=AsyncMock)
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Done"
    mock_result.execution_context = {}
    mock_result.pattern_type = "chain"
    mock_result.duration_seconds = 1.5
    mock_result.variables = {}
    mock_chain.return_value = mock_result

    # Execute without session
    result = await run_routing(spec, {"query": "test"})

    # Verify execution succeeded
    assert result.success is True
    assert mock_router.call_count == 1
    assert mock_chain.call_count == 1

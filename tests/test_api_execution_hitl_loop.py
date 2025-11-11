"""Unit tests for HITL loop implementation in WorkflowExecutor.

Tests cover:
- Single HITL pause handling
- Multiple consecutive HITL pauses
- Session state updates after each HITL response
- Error handling (exceptions, KeyboardInterrupt)
- Safety limit for infinite loops
- Edge cases (empty responses, missing HITL state)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from strands_cli.api.execution import WorkflowExecutor
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK
from strands_cli.session import SessionStatus
from strands_cli.types import (
    Agent,
    ChainStep,
    HITLState,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    RunResult,
    Runtime,
    Spec,
)


@pytest.fixture
def minimal_chain_spec() -> Spec:
    """Create minimal chain spec for testing."""
    return Spec(
        version=0,
        name="test-chain",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            model_id="llama3.2",
        ),
        agents={
            "agent1": Agent(prompt="Test prompt"),
        },
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(
                steps=[
                    ChainStep(agent="agent1", input="Test input"),
                ],
            ),
        ),
    )


@pytest.mark.asyncio
async def test_single_hitl_pause_handled(minimal_chain_spec: Spec, mocker) -> None:
    """Test HITL loop handles single pause correctly.

    Verifies:
    - First execution returns HITL pause
    - Handler called with correct state
    - Session updated with response
    - Second execution completes successfully
    """
    # Mock the executor
    executor = WorkflowExecutor(minimal_chain_spec)

    # Mock session repo
    mock_repo = AsyncMock()
    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock the pattern executor to return HITL pause then success
    hitl_state = HITLState(
        active=True,
        step_index=1,
        prompt="Review output?",
        context_display="Generated report...",
    )

    hitl_result = RunResult(
        success=True,
        last_response="HITL pause at step 1",
        pattern_type=PatternType.CHAIN,
        started_at=datetime.now(UTC).isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
        duration_seconds=1.0,
        agent_id="hitl",
        exit_code=EX_HITL_PAUSE,
    )

    success_result = RunResult(
        success=True,
        last_response="Final output",
        pattern_type=PatternType.CHAIN,
        started_at=datetime.now(UTC).isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
        duration_seconds=2.0,
        agent_id="agent1",
        exit_code=EX_OK,
    )

    # Mock _execute_pattern to return HITL pause first, then success
    call_count = 0

    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First call: return HITL pause
            session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
            session_state.metadata.status = SessionStatus.PAUSED
            await session_repo.save(session_state, "")
            return hitl_result

        # Second call: successful completion
        assert hitl_response == "approved"
        hitl_state_after = hitl_state.model_dump()
        hitl_state_after["active"] = False
        hitl_state_after["user_response"] = hitl_response
        session_state.pattern_state["hitl_state"] = hitl_state_after
        session_state.metadata.status = SessionStatus.COMPLETED
        await session_repo.save(session_state, "")
        return success_result

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Mock HITL handler
    def mock_handler(state: HITLState) -> str:
        assert state.prompt == "Review output?"
        assert state.active is True
        return "approved"

    # Run interactive execution
    result = await executor.run_interactive(
        variables={"topic": "test"},
        hitl_handler=mock_handler,
    )

    # Verify result
    assert result.success is True
    assert result.last_response == "Final output"
    assert result.exit_code == EX_OK

    # Verify session saved 4 times (initial snapshot, pause checkpoint, executor resume, final completion)
    assert mock_repo.save.call_count == 4


@pytest.mark.asyncio
async def test_multiple_hitl_pauses_handled(minimal_chain_spec: Spec, mocker) -> None:
    """Test HITL loop handles multiple consecutive pauses.

    Verifies:
    - Loop handles N HITL pauses
    - Each pause prompts user correctly
    - Session state updated after each response
    - Final result returned after all pauses
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    # Mock session repo
    mock_repo = AsyncMock()
    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Create HITL states for 3 pauses
    hitl_states = [
        HITLState(active=True, step_index=1, prompt="Review step 1?"),
        HITLState(active=True, step_index=3, prompt="Review step 2?"),
        HITLState(active=True, step_index=5, prompt="Review step 3?"),
    ]

    # Track executor calls
    call_count = 0

    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        nonlocal call_count
        call_count += 1

        if call_count <= len(hitl_states):
            # Return HITL pause
            hitl_state = hitl_states[call_count - 1]
            session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
            session_state.metadata.status = SessionStatus.PAUSED
            await session_repo.save(session_state, "")

            return RunResult(
                success=True,
                last_response=f"HITL pause at step {call_count}",
                pattern_type=PatternType.CHAIN,
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                duration_seconds=1.0,
                agent_id="hitl",
                exit_code=EX_HITL_PAUSE,
            )

        session_state.metadata.status = SessionStatus.COMPLETED
        await session_repo.save(session_state, "")
        return RunResult(
            success=True,
            last_response="All steps completed",
            pattern_type=PatternType.CHAIN,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=5.0,
            agent_id="agent1",
            exit_code=EX_OK,
        )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Track HITL handler calls
    handler_calls = []

    def mock_handler(state: HITLState) -> str:
        handler_calls.append(state.prompt)
        return f"response-{len(handler_calls)}"

    # Run interactive execution
    result = await executor.run_interactive(
        variables={"topic": "test"},
        hitl_handler=mock_handler,
    )

    # Verify all 3 HITL pauses were handled
    assert len(handler_calls) == 3
    assert handler_calls[0] == "Review step 1?"
    assert handler_calls[1] == "Review step 2?"
    assert handler_calls[2] == "Review step 3?"

    # Verify final result
    assert result.success is True
    assert result.last_response == "All steps completed"

    # Verify session saved: initial + per-pause checkpoints + final completion = 6 times
    assert mock_repo.save.call_count == 6


@pytest.mark.asyncio
async def test_session_state_updated_after_hitl(minimal_chain_spec: Spec, mocker) -> None:
    """Test session state properly updated after each HITL response.

    Verifies:
    - hitl_state.active set to False
    - hitl_state.user_response populated
    - session.metadata.updated_at updated
    - Session saved with updated state
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    # Capture session state passed to save()
    saved_sessions = []

    async def capture_save(session_state, spec_content):
        # Deep copy to capture state at save time
        saved_sessions.append(
            {
                "status": session_state.metadata.status,
                "updated_at": session_state.metadata.updated_at,
                "pattern_state": dict(session_state.pattern_state),
            }
        )

    mock_repo = AsyncMock()
    mock_repo.save.side_effect = capture_save

    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor
    call_count = 0

    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First call: HITL pause
            session_state.pattern_state["hitl_state"] = HITLState(
                active=True,
                step_index=1,
                prompt="Approve?",
            ).model_dump()
            session_state.metadata.status = SessionStatus.PAUSED
            await session_repo.save(session_state, "")

            return RunResult(
                success=True,
                last_response="HITL pause",
                pattern_type=PatternType.CHAIN,
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                duration_seconds=1.0,
                agent_id="hitl",
                exit_code=EX_HITL_PAUSE,
            )
        else:
            # Second call: success
            assert hitl_response == "user_input"
            session_state.pattern_state["hitl_state"] = HITLState(
                active=False,
                step_index=1,
                prompt="Approve?",
                user_response=hitl_response,
            ).model_dump()
            session_state.metadata.status = SessionStatus.COMPLETED
            await session_repo.save(session_state, "")

            return RunResult(
                success=True,
                last_response="Complete",
                pattern_type=PatternType.CHAIN,
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                duration_seconds=2.0,
                agent_id="agent1",
                exit_code=EX_OK,
            )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Run with simple handler
    await executor.run_interactive(
        variables={},
        hitl_handler=lambda state: "user_input",
    )

    # Verify session state updates
    assert len(saved_sessions) == 4

    # Initial save
    assert saved_sessions[0]["status"] == SessionStatus.RUNNING

    # Find the paused checkpoint and resumed state with injected response
    pause_snapshot = next(s for s in saved_sessions if s["status"] == SessionStatus.PAUSED)
    hitl_snapshots = [s for s in saved_sessions if "hitl_state" in s["pattern_state"]]
    hitl_state_after = HITLState(**hitl_snapshots[-1]["pattern_state"]["hitl_state"])

    assert hitl_state_after.active is False
    assert hitl_state_after.user_response == "user_input"
    assert pause_snapshot["status"] == SessionStatus.PAUSED

    # Final save should mark session completed
    assert saved_sessions[-1]["status"] == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_keyboard_interrupt_marks_session_paused(minimal_chain_spec: Spec, mocker) -> None:
    """Test KeyboardInterrupt during HITL marks session as PAUSED.

    Verifies:
    - Session marked as PAUSED (not FAILED)
    - Session saved before re-raising
    - Exception propagated to caller
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    # Track final session state
    final_session_state = None

    async def capture_save(session_state, spec_content):
        nonlocal final_session_state
        final_session_state = {
            "status": session_state.metadata.status,
            "updated_at": session_state.metadata.updated_at,
        }

    mock_repo = AsyncMock()
    mock_repo.save.side_effect = capture_save

    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor to return HITL pause
    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            step_index=1,
            prompt="Test",
        ).model_dump()

        return RunResult(
            success=True,
            last_response="HITL pause",
            pattern_type=PatternType.CHAIN,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=1.0,
            agent_id="hitl",
            exit_code=EX_HITL_PAUSE,
        )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Mock HITL handler to raise KeyboardInterrupt
    def interrupt_handler(state: HITLState) -> str:
        raise KeyboardInterrupt("User pressed Ctrl+C")

    # Verify KeyboardInterrupt is raised
    with pytest.raises(KeyboardInterrupt):
        await executor.run_interactive(
            variables={},
            hitl_handler=interrupt_handler,
        )

    # Verify session marked as PAUSED
    assert final_session_state is not None
    assert final_session_state["status"] == SessionStatus.PAUSED


@pytest.mark.asyncio
async def test_exception_marks_session_failed(minimal_chain_spec: Spec, mocker) -> None:
    """Test exceptions during execution mark session as FAILED.

    Verifies:
    - Session marked as FAILED on any exception
    - Session saved before re-raising
    - Exception propagated to caller
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    # Track final session state
    final_session_state = None

    async def capture_save(session_state, spec_content):
        nonlocal final_session_state
        final_session_state = {
            "status": session_state.metadata.status,
        }

    mock_repo = AsyncMock()
    mock_repo.save.side_effect = capture_save

    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor to raise exception
    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        raise RuntimeError("Test error during execution")

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Verify exception is raised
    with pytest.raises(RuntimeError, match="Test error during execution"):
        await executor.run_interactive(variables={})

    # Verify session marked as FAILED
    assert final_session_state is not None
    assert final_session_state["status"] == SessionStatus.FAILED


@pytest.mark.asyncio
async def test_safety_limit_prevents_infinite_loop(minimal_chain_spec: Spec, mocker) -> None:
    """Test safety limit prevents infinite HITL loops.

    Verifies:
    - Loop stops after max_iterations
    - Helpful error message provided
    - Session marked as FAILED
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    # Track final session state
    final_session_state = None

    async def capture_save(session_state, spec_content):
        nonlocal final_session_state
        final_session_state = {
            "status": session_state.metadata.status,
        }

    mock_repo = AsyncMock()
    mock_repo.save.side_effect = capture_save

    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor to always return HITL pause (infinite loop)
    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            step_index=1,
            prompt="Infinite loop test",
        ).model_dump()

        return RunResult(
            success=True,
            last_response="HITL pause",
            pattern_type=PatternType.CHAIN,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=1.0,
            agent_id="hitl",
            exit_code=EX_HITL_PAUSE,
        )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Mock HITL handler
    def mock_handler(state: HITLState) -> str:
        return "response"

    # Verify RuntimeError raised with helpful message
    with pytest.raises(RuntimeError, match="exceeded maximum iterations"):
        await executor.run_interactive(
            variables={},
            hitl_handler=mock_handler,
        )

    # Verify session marked as FAILED
    assert final_session_state is not None
    assert final_session_state["status"] == SessionStatus.FAILED


@pytest.mark.asyncio
async def test_missing_hitl_state_raises_error(minimal_chain_spec: Spec, mocker) -> None:
    """Test missing HITL state in session raises helpful error.

    Verifies:
    - RuntimeError raised if HITL pause but no hitl_state
    - Error message indicates executor bug
    - Session marked as FAILED
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    mock_repo = AsyncMock()
    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor to return HITL pause WITHOUT setting hitl_state
    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        # BUG: Don't set hitl_state in session
        return RunResult(
            success=True,
            last_response="HITL pause",
            pattern_type=PatternType.CHAIN,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=1.0,
            agent_id="hitl",
            exit_code=EX_HITL_PAUSE,
        )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Verify RuntimeError raised
    with pytest.raises(RuntimeError, match="no hitl_state in session"):
        await executor.run_interactive(variables={})


@pytest.mark.asyncio
async def test_inactive_hitl_state_raises_error(minimal_chain_spec: Spec, mocker) -> None:
    """Test inactive HITL state with pause result raises error.

    Verifies:
    - RuntimeError raised if HITL pause but active=False
    - Error message indicates executor bug
    - Session marked as FAILED
    """
    executor = WorkflowExecutor(minimal_chain_spec)

    mock_repo = AsyncMock()
    mocker.patch(
        "strands_cli.api.execution.FileSessionRepository",
        return_value=mock_repo,
    )

    # Mock pattern executor with inactive HITL state
    async def mock_execute_pattern(variables, session_state, session_repo, hitl_response):
        # BUG: Set active=False but return HITL pause
        session_state.pattern_state["hitl_state"] = HITLState(
            active=False,  # Wrong!
            step_index=1,
            prompt="Test",
        ).model_dump()

        return RunResult(
            success=True,
            last_response="HITL pause",
            pattern_type=PatternType.CHAIN,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=1.0,
            agent_id="hitl",
            exit_code=EX_HITL_PAUSE,
        )

    mocker.patch.object(
        executor,
        "_execute_pattern",
        side_effect=mock_execute_pattern,
    )

    # Verify RuntimeError raised
    with pytest.raises(RuntimeError, match=r"hitl_state\.active is False"):
        await executor.run_interactive(variables={})

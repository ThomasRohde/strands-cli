"""Tests for shared checkpoint utilities."""

from pathlib import Path

import pytest

from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.checkpoint_utils import (
    checkpoint_pattern_state,
    fail_session,
    finalize_session,
    get_cumulative_tokens,
    validate_session_params,
)
from strands_cli.session.file_repository import FileSessionRepository


def test_validate_session_params_both_none() -> None:
    """Test validation passes when both params are None."""
    validate_session_params(None, None)  # Should not raise


def test_validate_session_params_both_provided(tmp_path: Path) -> None:
    """Test validation passes when both params are provided."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    validate_session_params(state, repo)  # Should not raise


def test_validate_session_params_only_state() -> None:
    """Test validation fails when only state provided."""
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="chain",
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
        validate_session_params(state, None)


def test_validate_session_params_only_repo(tmp_path: Path) -> None:
    """Test validation fails when only repo provided."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    with pytest.raises(ValueError, match="must both be provided"):
        validate_session_params(None, repo)


@pytest.mark.asyncio
async def test_checkpoint_pattern_state(tmp_path: Path) -> None:
    """Test pattern state checkpointing."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test-checkpoint",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="workflow",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={"completed_tasks": []},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
    )

    # Checkpoint with updates
    await checkpoint_pattern_state(
        state,
        repo,
        pattern_state_updates={"completed_tasks": ["task1"]},
        token_increment=300,
        status=SessionStatus.RUNNING,
    )

    # Verify state updated
    assert state.pattern_state["completed_tasks"] == ["task1"]
    assert state.token_usage.total_input_tokens == 250  # 100 + 150
    assert state.token_usage.total_output_tokens == 200  # 50 + 150

    # Verify persisted
    loaded = await repo.load("test-checkpoint")
    assert loaded is not None
    assert loaded.pattern_state["completed_tasks"] == ["task1"]


@pytest.mark.asyncio
async def test_finalize_session(tmp_path: Path) -> None:
    """Test session finalization clears error and sets status to COMPLETED."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test-finalize",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
            error="RuntimeError: Previous failure",  # Stale error from previous attempt
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    await finalize_session(state, repo)

    # Verify status and error cleared
    assert state.metadata.status == SessionStatus.COMPLETED
    assert state.metadata.error is None, "Error should be cleared on successful completion"

    # Verify persisted
    loaded = await repo.load("test-finalize")
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert loaded.metadata.error is None, "Persisted error should be cleared"


def test_get_cumulative_tokens_none() -> None:
    """Test cumulative tokens with no session."""
    assert get_cumulative_tokens(None) == 0


def test_get_cumulative_tokens_with_usage() -> None:
    """Test cumulative tokens with existing usage."""
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(total_input_tokens=1000, total_output_tokens=800),
    )
    assert get_cumulative_tokens(state) == 1800


@pytest.mark.asyncio
async def test_fail_session_sets_error(tmp_path: Path) -> None:
    """Test that fail_session sets error field with exception details."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    state = SessionState(
        metadata=SessionMetadata(
            session_id="test-fail",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Fail with an exception
    error = RuntimeError("Test failure message")
    await fail_session(state, repo, error)

    # Verify status and error set
    assert state.metadata.status == SessionStatus.FAILED
    assert state.metadata.error is not None, "Error should be set"
    assert "RuntimeError: Test failure message" in state.metadata.error

    # Verify persisted
    loaded = await repo.load("test-fail")
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.FAILED
    assert loaded.metadata.error is not None, "Persisted error should be set"
    assert "RuntimeError: Test failure message" in loaded.metadata.error

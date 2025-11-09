"""Tests for session Pydantic models.

Tests SessionStatus, SessionMetadata, TokenUsage, and SessionState
validation, serialization, and exception handling.
"""

import pytest
from pydantic import ValidationError

from strands_cli.session import (
    SessionAlreadyCompletedError,
    SessionCorruptedError,
    SessionError,
    SessionMetadata,
    SessionNotFoundError,
    SessionState,
    SessionStatus,
    TokenUsage,
)


def test_session_status_enum():
    """Test SessionStatus enum values."""
    assert SessionStatus.RUNNING == "running"
    assert SessionStatus.PAUSED == "paused"
    assert SessionStatus.COMPLETED == "completed"
    assert SessionStatus.FAILED == "failed"


def test_session_metadata_validation():
    """Test SessionMetadata Pydantic validation."""
    # Valid metadata
    metadata = SessionMetadata(
        session_id="abc-123",
        workflow_name="test-workflow",
        spec_hash="abc123def456",
        pattern_type="chain",
        status=SessionStatus.RUNNING,
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:00:00Z",
    )

    assert metadata.session_id == "abc-123"
    assert metadata.workflow_name == "test-workflow"
    assert metadata.status == SessionStatus.RUNNING
    assert metadata.error is None


def test_session_metadata_with_error():
    """Test SessionMetadata with error field."""
    metadata = SessionMetadata(
        session_id="abc-123",
        workflow_name="test-workflow",
        spec_hash="abc123def456",
        pattern_type="chain",
        status=SessionStatus.FAILED,
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:00:00Z",
        error="Provider error: Connection timeout",
    )

    assert metadata.status == SessionStatus.FAILED
    assert metadata.error == "Provider error: Connection timeout"


def test_session_metadata_missing_required_field():
    """Test SessionMetadata validation fails with missing required field."""
    with pytest.raises(ValidationError) as exc_info:
        SessionMetadata(
            session_id="abc-123",
            workflow_name="test-workflow",
            # Missing spec_hash
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        )

    assert "spec_hash" in str(exc_info.value)


def test_token_usage_defaults():
    """Test TokenUsage default values."""
    usage = TokenUsage()

    assert usage.total_input_tokens == 0
    assert usage.total_output_tokens == 0
    assert usage.by_agent == {}


def test_token_usage_with_values():
    """Test TokenUsage with custom values."""
    usage = TokenUsage(
        total_input_tokens=5000,
        total_output_tokens=3000,
        by_agent={"researcher": 2000, "analyst": 3000},
    )

    assert usage.total_input_tokens == 5000
    assert usage.total_output_tokens == 3000
    assert usage.by_agent["researcher"] == 2000


def test_session_state_complete():
    """Test complete SessionState construction."""
    metadata = SessionMetadata(
        session_id="abc-123",
        workflow_name="test-workflow",
        spec_hash="abc123def456",
        pattern_type="chain",
        status=SessionStatus.RUNNING,
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:00:00Z",
    )

    state = SessionState(
        metadata=metadata,
        variables={"topic": "AI", "format": "markdown"},
        runtime_config={"provider": "ollama", "model_id": "llama2"},
        pattern_state={"current_step": 2, "step_history": []},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
        artifacts_written=["./output/step1.md"],
    )

    assert state.metadata.session_id == "abc-123"
    assert state.variables["topic"] == "AI"
    assert state.runtime_config["provider"] == "ollama"
    assert state.pattern_state["current_step"] == 2
    assert state.token_usage.total_input_tokens == 100
    assert len(state.artifacts_written) == 1


def test_session_state_default_artifacts():
    """Test SessionState with default artifacts_written."""
    metadata = SessionMetadata(
        session_id="abc-123",
        workflow_name="test-workflow",
        spec_hash="abc123def456",
        pattern_type="chain",
        status=SessionStatus.RUNNING,
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:00:00Z",
    )

    state = SessionState(
        metadata=metadata,
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    assert state.artifacts_written == []


def test_session_state_serialization():
    """Test SessionState model_dump() for JSON serialization."""
    metadata = SessionMetadata(
        session_id="abc-123",
        workflow_name="test-workflow",
        spec_hash="abc123def456",
        pattern_type="chain",
        status=SessionStatus.RUNNING,
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:00:00Z",
    )

    state = SessionState(
        metadata=metadata,
        variables={"topic": "AI"},
        runtime_config={"provider": "ollama"},
        pattern_state={"current_step": 1},
        token_usage=TokenUsage(total_input_tokens=100),
    )

    dumped = state.model_dump()

    assert dumped["metadata"]["session_id"] == "abc-123"
    assert dumped["variables"]["topic"] == "AI"
    assert dumped["token_usage"]["total_input_tokens"] == 100


def test_session_error_inheritance():
    """Test exception class hierarchy."""
    assert issubclass(SessionNotFoundError, SessionError)
    assert issubclass(SessionCorruptedError, SessionError)
    assert issubclass(SessionAlreadyCompletedError, SessionError)


def test_session_not_found_error():
    """Test SessionNotFoundError exception."""
    with pytest.raises(SessionNotFoundError) as exc_info:
        raise SessionNotFoundError("Session abc-123 not found")

    assert "abc-123" in str(exc_info.value)


def test_session_corrupted_error():
    """Test SessionCorruptedError exception."""
    with pytest.raises(SessionCorruptedError) as exc_info:
        raise SessionCorruptedError("Invalid JSON in session.json")

    assert "Invalid JSON" in str(exc_info.value)


def test_session_already_completed_error():
    """Test SessionAlreadyCompletedError exception."""
    with pytest.raises(SessionAlreadyCompletedError) as exc_info:
        raise SessionAlreadyCompletedError("Session abc-123 already completed")

    assert "abc-123" in str(exc_info.value)
    assert "completed" in str(exc_info.value)

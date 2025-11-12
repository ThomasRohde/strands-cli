"""Unit tests for SessionManager API."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from strands_cli.api.session_manager import SessionManager
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.file_repository import FileSessionRepository


@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    """Create temporary storage directory."""
    storage = tmp_path / "sessions"
    storage.mkdir()
    return storage


@pytest.fixture
def session_manager(temp_storage: Path) -> SessionManager:
    """Create SessionManager with temp storage."""
    return SessionManager(storage_dir=temp_storage)


@pytest.mark.asyncio
async def test_session_manager_list_empty(session_manager: SessionManager) -> None:
    """Test listing sessions when none exist."""
    sessions = await session_manager.list()
    assert sessions == []


@pytest.mark.asyncio
async def test_session_manager_list_with_pagination(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test pagination of session listing."""
    # Create multiple sessions
    repo = FileSessionRepository(temp_storage)
    for i in range(15):
        state = SessionState(
            metadata={
                "session_id": f"session-{i:02d}",
                "workflow_name": "test-workflow",
                "spec_hash": "test-hash-123",
                "pattern_type": "chain",
                "status": SessionStatus.COMPLETED,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
            pattern_state={"step_history": []},
            token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
        )
        await repo.save(state)

    # Test default pagination
    sessions = await session_manager.list(offset=0, limit=10)
    assert len(sessions) == 10

    # Test offset
    sessions = await session_manager.list(offset=10, limit=10)
    assert len(sessions) == 5

    # Test all
    sessions = await session_manager.list(offset=0, limit=100)
    assert len(sessions) == 15


@pytest.mark.asyncio
async def test_session_manager_list_filter_by_status(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test filtering sessions by status."""
    repo = FileSessionRepository(temp_storage)

    # Create sessions with different statuses
    for status in [SessionStatus.COMPLETED, SessionStatus.PAUSED, SessionStatus.FAILED]:
        for i in range(3):
            state = SessionState(
                metadata={
                    "session_id": f"{status.value}-{i}",
                    "workflow_name": "test-workflow",
                    "spec_hash": "test-hash-123",
                    "pattern_type": "chain",
                    "status": status,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                variables={},
                runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
                pattern_state={"step_history": []},
                token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
            )
            await repo.save(state)

    # Filter by status
    paused = await session_manager.list(status=SessionStatus.PAUSED)
    assert len(paused) == 3
    assert all(s.metadata.status == SessionStatus.PAUSED for s in paused)

    completed = await session_manager.list(status=SessionStatus.COMPLETED)
    assert len(completed) == 3
    assert all(s.metadata.status == SessionStatus.COMPLETED for s in completed)


@pytest.mark.asyncio
async def test_session_manager_list_filter_by_workflow_name(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test filtering sessions by workflow name."""
    repo = FileSessionRepository(temp_storage)

    # Create sessions with different workflows
    for workflow in ["workflow-a", "workflow-b"]:
        for i in range(3):
            state = SessionState(
                metadata={
                    "session_id": f"{workflow}-{i}",
                    "workflow_name": workflow,
                    "spec_hash": "test-hash-123",
                    "pattern_type": "chain",
                    "status": SessionStatus.COMPLETED,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                variables={},
                runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
                pattern_state={"step_history": []},
                token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
            )
            await repo.save(state)

    # Filter by workflow name
    workflow_a = await session_manager.list(workflow_name="workflow-a")
    assert len(workflow_a) == 3
    assert all(s.metadata.workflow_name == "workflow-a" for s in workflow_a)


@pytest.mark.asyncio
async def test_session_manager_get_existing_session(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test getting existing session by ID."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        variables={"var": "value"},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # Get session
    retrieved = await session_manager.get("test-session")
    assert retrieved.metadata.session_id == "test-session"
    assert retrieved.variables["var"] == "value"


@pytest.mark.asyncio
async def test_session_manager_get_nonexistent_session(
    session_manager: SessionManager,
) -> None:
    """Test getting nonexistent session returns None."""
    loaded = await session_manager.get("nonexistent")
    assert loaded is None


@pytest.mark.asyncio
async def test_session_manager_caching(session_manager: SessionManager, temp_storage: Path) -> None:
    """Test session caching reduces disk I/O."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # First get - should read from disk
    session1 = await session_manager.get("test-session")

    # Second get - should use cache
    with patch.object(FileSessionRepository, "load", side_effect=Exception("Should not be called")):
        session2 = await session_manager.get("test-session")

    assert session1.metadata.session_id == session2.metadata.session_id


@pytest.mark.asyncio
async def test_session_manager_cache_ttl(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test cache TTL expires old entries."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # Get session to populate cache
    await session_manager.get("test-session")

    # Manually expire cache entry
    cache_key = "test-session"
    if cache_key in session_manager._cache:
        cached_state, _ = session_manager._cache[cache_key]
        expired_timestamp = datetime.now(UTC) - timedelta(minutes=10)
        session_manager._cache[cache_key] = (cached_state, expired_timestamp)

    # Next get should refresh from disk
    session = await session_manager.get("test-session")
    assert session.metadata.session_id == "test-session"


@pytest.mark.asyncio
async def test_session_manager_delete(session_manager: SessionManager, temp_storage: Path) -> None:
    """Test deleting session."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # Delete session
    await session_manager.delete("test-session")

    # Verify it's gone (get returns None)
    loaded = await session_manager.get("test-session")
    assert loaded is None


@pytest.mark.asyncio
async def test_session_manager_delete_invalidates_cache(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test deleting session invalidates cache."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # Get session to populate cache
    await session_manager.get("test-session")
    assert "test-session" in session_manager._cache

    # Delete should invalidate cache
    await session_manager.delete("test-session")
    assert "test-session" not in session_manager._cache


@pytest.mark.asyncio
async def test_session_manager_cleanup_old_sessions(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test cleanup of old sessions."""
    repo = FileSessionRepository(temp_storage)

    # Create old and new sessions
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    new_time = datetime.now(UTC).isoformat()

    old_state = SessionState(
        metadata={
            "session_id": "old-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": old_time,
            "updated_at": old_time,
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    new_state = SessionState(
        metadata={
            "session_id": "new-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": new_time,
            "updated_at": new_time,
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )

    await repo.save(old_state)
    await repo.save(new_state)

    # Cleanup sessions older than 7 days
    removed = await session_manager.cleanup(older_than_days=7)
    assert removed == 1

    # Verify only old session was removed
    sessions = await session_manager.list()
    assert len(sessions) == 1
    assert sessions[0].metadata.session_id == "new-session"


@pytest.mark.asyncio
async def test_session_manager_cleanup_with_status_filter(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test cleanup with status filtering."""
    repo = FileSessionRepository(temp_storage)
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    # Create old sessions with different statuses
    for i, status in enumerate([SessionStatus.COMPLETED, SessionStatus.FAILED]):
        state = SessionState(
            metadata={
                "session_id": f"old-{status.value}-{i}",
                "workflow_name": "test-workflow",
                "spec_hash": "test-hash-123",
                "pattern_type": "chain",
                "status": status,
                "created_at": old_time,
                "updated_at": old_time,
            },
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
            pattern_state={"step_history": []},
            token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
        )
        await repo.save(state)

    # Cleanup only failed sessions
    removed = await session_manager.cleanup(older_than_days=7, status_filter=[SessionStatus.FAILED])
    assert removed == 1

    # Verify completed session still exists
    sessions = await session_manager.list()
    assert len(sessions) == 1
    assert sessions[0].metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_session_manager_resume_integration(
    session_manager: SessionManager, temp_storage: Path, mocker
) -> None:
    """Test resume integration with run_resume."""
    repo = FileSessionRepository(temp_storage)
    state = SessionState(
        metadata={
            "session_id": "paused-session",
            "workflow_name": "test-workflow",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.PAUSED,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        spec={"name": "test"},
        variables={"var": "value"},
        results={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )
    await repo.save(state)

    # Mock run_resume to avoid actual execution
    mock_result = Mock()
    mock_result.success = True
    mock_result.last_response = "Resumed"
    mock_resume = mocker.patch(
        "strands_cli.api.session_manager.run_resume",
        return_value=mock_result,
    )

    # Resume session
    result = await session_manager.resume("paused-session", hitl_response="approved")

    # Verify run_resume was called correctly
    mock_resume.assert_called_once()
    assert result.success is True
    assert result.last_response == "Resumed"


@pytest.mark.asyncio
async def test_session_manager_max_limit(
    session_manager: SessionManager, temp_storage: Path
) -> None:
    """Test max limit enforced for pagination."""
    repo = FileSessionRepository(temp_storage)

    # Create many sessions
    for i in range(50):
        state = SessionState(
            metadata={
                "session_id": f"session-{i:03d}",
                "workflow_name": "test-workflow",
                "spec_hash": "test-hash-123",
                "pattern_type": "chain",
                "status": SessionStatus.COMPLETED,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
            pattern_state={"step_history": []},
            token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
        )
        await repo.save(state)

    # Request beyond max limit (should raise ValueError)
    with pytest.raises(ValueError, match="limit must be <= 1000"):
        await session_manager.list(limit=2000)

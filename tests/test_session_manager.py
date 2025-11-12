"""Tests for SessionManager API with pagination and caching.

Tests SessionManager's high-level API methods including list(), get(),
resume(), cleanup(), delete() with LRU caching and pagination support.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from strands_cli.api.session_manager import SessionManager
from strands_cli.session import (
    SessionMetadata,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.utils import generate_session_id


@pytest.fixture
def session_manager(tmp_path: Path) -> SessionManager:
    """Create SessionManager with temporary storage."""
    return SessionManager(storage_dir=tmp_path)


def create_test_session(
    session_id: str,
    workflow_name: str = "test-workflow",
    status: SessionStatus = SessionStatus.RUNNING,
    updated_at: str | None = None,
) -> SessionState:
    """Create a test session state."""
    if updated_at is None:
        updated_at = datetime.now(UTC).isoformat()

    return SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=workflow_name,
            spec_hash="abc123",
            pattern_type="chain",
            status=status,
            created_at=updated_at,
            updated_at=updated_at,
        ),
        variables={"topic": "AI"},
        runtime_config={"provider": "ollama"},
        pattern_state={"current_step": 1},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
    )


@pytest.mark.asyncio
async def test_get_session(session_manager: SessionManager):
    """Test getting a session by ID."""
    session_id = generate_session_id()
    state = create_test_session(session_id)

    # Save session
    await session_manager.repo.save(state, "spec content")

    # Get session
    loaded = await session_manager.get(session_id)
    assert loaded is not None
    assert loaded.metadata.session_id == session_id
    assert loaded.metadata.workflow_name == "test-workflow"


@pytest.mark.asyncio
async def test_get_nonexistent_session(session_manager: SessionManager):
    """Test getting non-existent session returns None."""
    loaded = await session_manager.get("nonexistent-id")
    assert loaded is None


@pytest.mark.asyncio
async def test_get_session_caching(session_manager: SessionManager):
    """Test that get() caches sessions."""
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec content")

    # First call - cache miss
    loaded1 = await session_manager.get(session_id)
    assert loaded1 is not None
    assert session_id in session_manager._cache

    # Second call - cache hit
    loaded2 = await session_manager.get(session_id)
    assert loaded2 is not None
    assert loaded1.metadata.session_id == loaded2.metadata.session_id


@pytest.mark.asyncio
async def test_cache_expiration(session_manager: SessionManager):
    """Test that cache entries expire after TTL."""
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec content")

    # Load and cache
    await session_manager.get(session_id)
    assert session_id in session_manager._cache

    # Manually expire cache entry
    cached_state, _ = session_manager._cache[session_id]
    expired_time = datetime.now(UTC) - timedelta(minutes=6)
    session_manager._cache[session_id] = (cached_state, expired_time)

    # Next get should reload from disk
    loaded = await session_manager.get(session_id)
    assert loaded is not None
    # Cache should be updated with new timestamp
    _, timestamp = session_manager._cache[session_id]
    assert datetime.now(UTC) - timestamp < timedelta(seconds=1)


@pytest.mark.asyncio
async def test_list_sessions_empty(session_manager: SessionManager):
    """Test listing sessions when none exist."""
    sessions = await session_manager.list()
    assert sessions == []


@pytest.mark.asyncio
async def test_list_sessions_basic(session_manager: SessionManager):
    """Test listing sessions with basic pagination."""
    # Create 3 sessions
    session_ids = []
    for i in range(3):
        session_id = generate_session_id()
        session_ids.append(session_id)
        state = create_test_session(
            session_id,
            workflow_name=f"workflow-{i}",
        )
        await session_manager.repo.save(state, "spec content")

    # List all sessions
    sessions = await session_manager.list()
    assert len(sessions) == 3
    # Should be sorted by updated_at descending
    assert all(isinstance(s, SessionState) for s in sessions)


@pytest.mark.asyncio
async def test_list_sessions_pagination(session_manager: SessionManager):
    """Test pagination with offset and limit."""
    # Create 5 sessions with different timestamps
    session_ids = []
    for i in range(5):
        session_id = generate_session_id()
        session_ids.append(session_id)
        # Create with different timestamps (older to newer)
        updated_at = (datetime.now(UTC) - timedelta(hours=5 - i)).isoformat()
        state = create_test_session(session_id, updated_at=updated_at)
        await session_manager.repo.save(state, "spec content")

    # Get first page (limit=2)
    page1 = await session_manager.list(offset=0, limit=2)
    assert len(page1) == 2

    # Get second page
    page2 = await session_manager.list(offset=2, limit=2)
    assert len(page2) == 2

    # Get third page (only 1 item)
    page3 = await session_manager.list(offset=4, limit=2)
    assert len(page3) == 1

    # Verify no overlap
    all_ids = [s.metadata.session_id for s in page1 + page2 + page3]
    assert len(all_ids) == 5
    assert len(set(all_ids)) == 5  # All unique


@pytest.mark.asyncio
async def test_list_sessions_filter_by_status(session_manager: SessionManager):
    """Test filtering sessions by status."""
    # Create sessions with different statuses
    paused_id = generate_session_id()
    completed_id = generate_session_id()
    running_id = generate_session_id()

    await session_manager.repo.save(
        create_test_session(paused_id, status=SessionStatus.PAUSED),
        "spec",
    )
    await session_manager.repo.save(
        create_test_session(completed_id, status=SessionStatus.COMPLETED),
        "spec",
    )
    await session_manager.repo.save(
        create_test_session(running_id, status=SessionStatus.RUNNING),
        "spec",
    )

    # Filter by paused
    paused = await session_manager.list(status=SessionStatus.PAUSED)
    assert len(paused) == 1
    assert paused[0].metadata.status == SessionStatus.PAUSED

    # Filter by completed
    completed = await session_manager.list(status=SessionStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].metadata.status == SessionStatus.COMPLETED

    # Filter by running
    running = await session_manager.list(status=SessionStatus.RUNNING)
    assert len(running) == 1
    assert running[0].metadata.status == SessionStatus.RUNNING


@pytest.mark.asyncio
async def test_list_sessions_filter_by_workflow_name(session_manager: SessionManager):
    """Test filtering sessions by workflow name."""
    # Create sessions with different workflow names
    for i in range(3):
        session_id = generate_session_id()
        workflow_name = f"workflow-{i % 2}"  # workflow-0 or workflow-1
        state = create_test_session(session_id, workflow_name=workflow_name)
        await session_manager.repo.save(state, "spec")

    # Filter by workflow-0
    sessions = await session_manager.list(workflow_name="workflow-0")
    assert len(sessions) == 2
    assert all(s.metadata.workflow_name == "workflow-0" for s in sessions)

    # Filter by workflow-1
    sessions = await session_manager.list(workflow_name="workflow-1")
    assert len(sessions) == 1
    assert sessions[0].metadata.workflow_name == "workflow-1"


@pytest.mark.asyncio
async def test_list_sessions_combined_filters(session_manager: SessionManager):
    """Test combining multiple filters."""
    # Create sessions
    session_id1 = generate_session_id()
    session_id2 = generate_session_id()
    session_id3 = generate_session_id()

    await session_manager.repo.save(
        create_test_session(
            session_id1,
            workflow_name="workflow-A",
            status=SessionStatus.PAUSED,
        ),
        "spec",
    )
    await session_manager.repo.save(
        create_test_session(
            session_id2,
            workflow_name="workflow-A",
            status=SessionStatus.COMPLETED,
        ),
        "spec",
    )
    await session_manager.repo.save(
        create_test_session(
            session_id3,
            workflow_name="workflow-B",
            status=SessionStatus.PAUSED,
        ),
        "spec",
    )

    # Filter by workflow-A AND paused
    sessions = await session_manager.list(
        workflow_name="workflow-A",
        status=SessionStatus.PAUSED,
    )
    assert len(sessions) == 1
    assert sessions[0].metadata.workflow_name == "workflow-A"
    assert sessions[0].metadata.status == SessionStatus.PAUSED


@pytest.mark.asyncio
async def test_list_sessions_validates_pagination_params(session_manager: SessionManager):
    """Test that list() validates pagination parameters."""
    # Negative offset
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await session_manager.list(offset=-1)

    # Zero limit
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await session_manager.list(limit=0)

    # Limit too large
    with pytest.raises(ValueError, match="limit must be <= 1000"):
        await session_manager.list(limit=1001)


@pytest.mark.asyncio
async def test_delete_session(session_manager: SessionManager):
    """Test deleting a session."""
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec content")

    # Verify exists
    loaded = await session_manager.get(session_id)
    assert loaded is not None

    # Delete
    await session_manager.delete(session_id)

    # Verify deleted
    loaded = await session_manager.get(session_id)
    assert loaded is None


@pytest.mark.asyncio
async def test_delete_invalidates_cache(session_manager: SessionManager):
    """Test that delete() invalidates cache."""
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec content")

    # Load into cache
    await session_manager.get(session_id)
    assert session_id in session_manager._cache

    # Delete
    await session_manager.delete(session_id)

    # Cache should be invalidated
    assert session_id not in session_manager._cache


@pytest.mark.asyncio
async def test_cleanup_old_sessions(session_manager: SessionManager):
    """Test cleaning up old sessions."""
    # Create old and new sessions
    old_id = generate_session_id()
    new_id = generate_session_id()

    # Old session (10 days ago)
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    await session_manager.repo.save(
        create_test_session(old_id, updated_at=old_time),
        "spec",
    )

    # New session (1 day ago)
    new_time = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await session_manager.repo.save(
        create_test_session(new_id, updated_at=new_time),
        "spec",
    )

    # Cleanup sessions older than 7 days
    deleted = await session_manager.cleanup(older_than_days=7)
    assert deleted == 1

    # Verify old deleted, new kept
    assert await session_manager.get(old_id) is None
    assert await session_manager.get(new_id) is not None


@pytest.mark.asyncio
async def test_cleanup_with_status_filter(session_manager: SessionManager):
    """Test cleanup with status filter."""
    # Create old sessions with different statuses
    failed_id = generate_session_id()
    completed_id = generate_session_id()

    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    await session_manager.repo.save(
        create_test_session(failed_id, status=SessionStatus.FAILED, updated_at=old_time),
        "spec",
    )
    await session_manager.repo.save(
        create_test_session(completed_id, status=SessionStatus.COMPLETED, updated_at=old_time),
        "spec",
    )

    # Cleanup only failed sessions
    deleted = await session_manager.cleanup(
        older_than_days=7,
        status_filter=[SessionStatus.FAILED],
    )
    assert deleted == 1

    # Verify failed deleted, completed kept
    assert await session_manager.get(failed_id) is None
    assert await session_manager.get(completed_id) is not None


@pytest.mark.asyncio
async def test_cleanup_invalidates_cache(session_manager: SessionManager):
    """Test that cleanup invalidates cache for deleted sessions."""
    session_id = generate_session_id()
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    await session_manager.repo.save(
        create_test_session(session_id, updated_at=old_time),
        "spec",
    )

    # Load into cache
    await session_manager.get(session_id)
    assert session_id in session_manager._cache

    # Cleanup
    deleted = await session_manager.cleanup(older_than_days=7)
    assert deleted == 1

    # Cache should be invalidated
    assert session_id not in session_manager._cache


@pytest.mark.asyncio
async def test_resume_delegates_to_run_resume(session_manager: SessionManager, mocker):
    """Test that resume() delegates to run_resume()."""
    from strands_cli.types import PatternType, RunResult

    # Mock run_resume
    mock_result = RunResult(
        success=True,
        pattern_type=PatternType.CHAIN,
        agent_id="test-agent",
        last_response="test response",
        started_at="2025-11-12T00:00:00Z",
        completed_at="2025-11-12T00:00:01Z",
        duration_seconds=1.0,
    )
    mock_run_resume = mocker.patch(
        "strands_cli.api.session_manager.run_resume",
        new=AsyncMock(return_value=mock_result),
    )

    # Create and cache a session
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec")
    await session_manager.get(session_id)  # Load into cache

    # Resume
    result = await session_manager.resume(
        session_id,
        hitl_response="approved",
        debug=True,
        verbose=True,
        trace=False,
    )

    # Verify delegation
    mock_run_resume.assert_called_once_with(
        session_id=session_id,
        hitl_response="approved",
        debug=True,
        verbose=True,
        trace=False,
    )
    assert result.success is True
    assert result.last_response == "test response"

    # Verify cache invalidated
    assert session_id not in session_manager._cache


@pytest.mark.asyncio
async def test_session_sorting_by_updated_at(session_manager: SessionManager):
    """Test that sessions are sorted by updated_at descending."""
    # Create sessions with different timestamps
    ids_and_times = []
    for i in range(3):
        session_id = generate_session_id()
        # Create timestamps: i=0 is oldest, i=2 is newest
        updated_at = (datetime.now(UTC) - timedelta(hours=3 - i)).isoformat()
        ids_and_times.append((session_id, updated_at))
        await session_manager.repo.save(
            create_test_session(session_id, updated_at=updated_at),
            "spec",
        )

    # List sessions
    sessions = await session_manager.list()

    # Should be sorted newest first
    assert len(sessions) == 3
    # First session should be the newest (i=2)
    assert sessions[0].metadata.session_id == ids_and_times[2][0]
    # Last session should be the oldest (i=0)
    assert sessions[2].metadata.session_id == ids_and_times[0][0]

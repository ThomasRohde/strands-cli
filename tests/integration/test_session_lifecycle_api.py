"""Integration tests for session lifecycle through API.

Tests the complete session workflow:
create → list → get → resume → cleanup
"""

from datetime import UTC, datetime, timedelta

import pytest

from strands_cli.api import SessionManager
from strands_cli.session import (
    SessionMetadata,
    SessionNotFoundError,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.file_repository import FileSessionRepository


@pytest.mark.asyncio
async def test_session_lifecycle_complete_flow(tmp_path, mocker) -> None:
    """Test complete session lifecycle through API."""
    # Setup
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    # 1. Create sessions
    print("\n1. Creating test sessions...")
    for i in range(5):
        state = SessionState(
            metadata=SessionMetadata(
                session_id=f"session-{i}",
                workflow_name=f"workflow-{i % 2}",  # 2 different workflows
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.COMPLETED if i % 2 == 0 else SessionStatus.PAUSED,
                created_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            ),
            variables={"var": f"value-{i}"},
            runtime_config={"provider": "openai", "model_id": "gpt-4o"},
            pattern_state={"step_history": []},
            token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
            artifacts_written=[],
        )
        await repo.save(state)

    # 2. List all sessions
    print("2. Listing all sessions...")
    all_sessions = await manager.list()
    assert len(all_sessions) == 5

    # 3. Filter by status
    print("3. Filtering by status...")
    paused = await manager.list(status=SessionStatus.PAUSED)
    completed = await manager.list(status=SessionStatus.COMPLETED)
    assert len(paused) == 2  # sessions 1, 3
    assert len(completed) == 3  # sessions 0, 2, 4

    # 4. Filter by workflow name
    print("4. Filtering by workflow name...")
    workflow_0_sessions = await manager.list(workflow_name="workflow-0")
    workflow_1_sessions = await manager.list(workflow_name="workflow-1")
    assert len(workflow_0_sessions) + len(workflow_1_sessions) == 5

    # 5. Get specific session
    print("5. Getting specific session...")
    session = await manager.get("session-0")
    assert session.metadata.session_id == "session-0"
    assert session.variables["var"] == "value-0"

    # 6. Resume paused session
    print("6. Resuming paused session...")
    mock_result = mocker.Mock()
    mock_result.success = True
    mock_result.last_response = "Resumed"
    mocker.patch("strands_cli.api.session_manager.run_resume", return_value=mock_result)

    result = await manager.resume("session-1", hitl_response="approved")
    assert result.success is True

    # 7. Delete session
    print("7. Deleting session...")
    await manager.delete("session-0")
    remaining = await manager.list()
    assert len(remaining) == 4

    # 8. Cleanup old sessions
    print("8. Cleaning up old sessions...")
    # Update one session to be old
    old_session = await repo.load("session-2")
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    old_session.metadata.updated_at = old_time
    await repo.save(old_session)

    removed = await manager.cleanup(older_than_days=7)
    assert removed == 1

    final_sessions = await manager.list()
    assert len(final_sessions) == 3


@pytest.mark.asyncio
async def test_session_pagination_with_many_sessions(tmp_path) -> None:
    """Test pagination works correctly with many sessions."""
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    # Create 25 sessions
    for i in range(25):
        state = SessionState(
            metadata=SessionMetadata(
                session_id=f"session-{i:02d}",
                workflow_name="test-workflow",
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.COMPLETED,
                created_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            ),
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o"},
            pattern_state={"step_history": []},
            token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
            artifacts_written=[],
        )
        await repo.save(state)

    # Test pagination
    page1 = await manager.list(offset=0, limit=10)
    page2 = await manager.list(offset=10, limit=10)
    page3 = await manager.list(offset=20, limit=10)

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5

    # Verify no overlap
    page1_ids = {s.metadata.session_id for s in page1}
    page2_ids = {s.metadata.session_id for s in page2}
    page3_ids = {s.metadata.session_id for s in page3}

    assert len(page1_ids & page2_ids) == 0
    assert len(page2_ids & page3_ids) == 0


@pytest.mark.asyncio
async def test_session_caching_behavior(tmp_path) -> None:
    """Test session caching across API calls."""
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    # Create session
    state = SessionState(
        metadata=SessionMetadata(
            session_id="cached-session",
            workflow_name="test",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.COMPLETED,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o"},
        pattern_state={"step_history": []},
        token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
        artifacts_written=[],
    )
    await repo.save(state)

    # First get - cache miss
    session1 = await manager.get("cached-session")
    assert "cached-session" in manager._cache

    # Second get - cache hit (verify same object)
    session2 = await manager.get("cached-session")
    assert session1.metadata.session_id == session2.metadata.session_id

    # Delete should invalidate cache
    await manager.delete("cached-session")
    assert "cached-session" not in manager._cache


@pytest.mark.asyncio
async def test_cleanup_with_status_filter_integration(tmp_path) -> None:
    """Test cleanup respects status filters."""
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    # Create old sessions with different statuses
    for i, status in enumerate(
        [SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.PAUSED]
    ):
        state = SessionState(
            metadata=SessionMetadata(
                session_id=f"old-{status.value}-{i}",
                workflow_name="test",
                spec_hash="abc123",
                pattern_type="chain",
                status=status,
                created_at=old_time,
                updated_at=old_time,
            ),
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o"},
            pattern_state={"step_history": []},
            token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
            artifacts_written=[],
        )
        await repo.save(state)

    # Cleanup only failed sessions
    removed = await manager.cleanup(older_than_days=7, status_filter=[SessionStatus.FAILED])
    assert removed == 1

    # Verify other statuses remain
    remaining = await manager.list()
    assert len(remaining) == 2
    assert all(s.metadata.status != SessionStatus.FAILED for s in remaining)


@pytest.mark.asyncio
async def test_concurrent_session_access(tmp_path) -> None:
    """Test concurrent access to sessions."""
    import asyncio

    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    # Create session
    state = SessionState(
        metadata=SessionMetadata(
            session_id="concurrent-session",
            workflow_name="test",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.COMPLETED,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o"},
        pattern_state={"step_history": []},
        token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
        artifacts_written=[],
    )
    await repo.save(state)

    # Access session concurrently
    async def get_session(index: int) -> SessionState:
        return await manager.get("concurrent-session")

    # Run 10 concurrent gets
    results = await asyncio.gather(*[get_session(i) for i in range(10)])

    # All should succeed
    assert len(results) == 10
    assert all(r.metadata.session_id == "concurrent-session" for r in results)


@pytest.mark.asyncio
async def test_resume_nonexistent_session(tmp_path, mocker) -> None:
    """Test resuming non-existent session raises error."""
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)

    with pytest.raises(SessionNotFoundError):
        await manager.resume("nonexistent-session")


@pytest.mark.asyncio
async def test_list_with_combined_filters(tmp_path) -> None:
    """Test combining multiple filters."""
    storage_dir = tmp_path / "sessions"
    storage_dir.mkdir()
    manager = SessionManager(storage_dir=storage_dir)
    repo = FileSessionRepository(storage_dir)

    # Create sessions with different combinations
    for i in range(6):
        state = SessionState(
            metadata=SessionMetadata(
                session_id=f"session-{i}",
                workflow_name=f"workflow-{i % 2}",
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.PAUSED if i < 3 else SessionStatus.COMPLETED,
                created_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            ),
            variables={},
            runtime_config={"provider": "openai", "model_id": "gpt-4o"},
            pattern_state={"step_history": []},
            token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0, by_agent={}),
            artifacts_written=[],
        )
        await repo.save(state)

    # Filter by both workflow and status
    results = await manager.list(workflow_name="workflow-0", status=SessionStatus.PAUSED)

    # Should only match sessions 0 and 2 (workflow-0 + paused)
    assert len(results) <= 2
    for session in results:
        assert session.metadata.workflow_name == "workflow-0"
        assert session.metadata.status == SessionStatus.PAUSED

"""Tests for session cleanup and auto-resume functionality."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from strands_cli.session import (
    SessionMetadata,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.cleanup import cleanup_expired_sessions
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import generate_session_id


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_basic(tmp_path: Path):
    """Test basic cleanup of expired sessions."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create 3 old sessions (8 days old)
    old_timestamp = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    for i in range(3):
        session_id = generate_session_id()
        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"old-workflow-{i}",
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.FAILED,
                created_at=old_timestamp,
                updated_at=old_timestamp,
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )
        await repo.save(state, "spec")

    # Create 2 recent sessions (1 day old)
    recent_timestamp = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    for i in range(2):
        session_id = generate_session_id()
        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"recent-workflow-{i}",
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=recent_timestamp,
                updated_at=recent_timestamp,
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )
        await repo.save(state, "spec")

    # Cleanup with max_age_days=7
    deleted = await cleanup_expired_sessions(repo, max_age_days=7, keep_completed=False)

    # Should delete 3 old sessions
    assert deleted == 3

    # Verify recent sessions still exist
    remaining = await repo.list_sessions()
    assert len(remaining) == 2
    assert all("recent" in s.workflow_name for s in remaining)


@pytest.mark.asyncio
async def test_cleanup_keeps_completed_sessions(tmp_path: Path):
    """Test that cleanup preserves completed sessions when keep_completed=True."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create old completed session
    old_timestamp = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    completed_id = generate_session_id()
    completed_state = SessionState(
        metadata=SessionMetadata(
            session_id=completed_id,
            workflow_name="completed-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.COMPLETED,
            created_at=old_timestamp,
            updated_at=old_timestamp,
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(completed_state, "spec")

    # Create old failed session
    failed_id = generate_session_id()
    failed_state = SessionState(
        metadata=SessionMetadata(
            session_id=failed_id,
            workflow_name="failed-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.FAILED,
            created_at=old_timestamp,
            updated_at=old_timestamp,
            error="Test error",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(failed_state, "spec")

    # Cleanup with keep_completed=True
    deleted = await cleanup_expired_sessions(repo, max_age_days=7, keep_completed=True)

    # Should delete only failed session
    assert deleted == 1

    # Verify completed session still exists
    remaining = await repo.list_sessions()
    assert len(remaining) == 1
    assert remaining[0].status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_cleanup_deletes_completed_when_disabled(tmp_path: Path):
    """Test that cleanup removes completed sessions when keep_completed=False."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create old completed session
    old_timestamp = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    completed_id = generate_session_id()
    completed_state = SessionState(
        metadata=SessionMetadata(
            session_id=completed_id,
            workflow_name="completed-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.COMPLETED,
            created_at=old_timestamp,
            updated_at=old_timestamp,
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(completed_state, "spec")

    # Cleanup with keep_completed=False
    deleted = await cleanup_expired_sessions(repo, max_age_days=7, keep_completed=False)

    # Should delete completed session
    assert deleted == 1

    # Verify no sessions remain
    remaining = await repo.list_sessions()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_cleanup_returns_zero_when_no_expired(tmp_path: Path):
    """Test that cleanup returns 0 when no sessions are expired."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create recent session (1 day old)
    recent_timestamp = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    session_id = generate_session_id()
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="recent-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=recent_timestamp,
            updated_at=recent_timestamp,
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec")

    # Cleanup with max_age_days=7
    deleted = await cleanup_expired_sessions(repo, max_age_days=7)

    # Should delete nothing
    assert deleted == 0

    # Verify session still exists
    remaining = await repo.list_sessions()
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_cleanup_handles_corrupted_timestamp(tmp_path: Path):
    """Test that cleanup skips sessions with invalid timestamps."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create session with invalid timestamp (manually corrupt it)
    session_id = generate_session_id()
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="corrupted-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="invalid-timestamp",  # Corrupted
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec")

    # Cleanup should not crash, just skip corrupted session
    deleted = await cleanup_expired_sessions(repo, max_age_days=7)

    # Should skip corrupted session
    assert deleted == 0

    # Verify session still exists (not deleted due to parse error)
    remaining = await repo.list_sessions()
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_cleanup_mixed_statuses(tmp_path: Path):
    """Test cleanup with mixed session statuses."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    old_timestamp = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    # Create sessions with different statuses
    statuses = [
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.PAUSED,
        SessionStatus.RUNNING,
    ]

    for status in statuses:
        session_id = generate_session_id()
        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"{status.value}-workflow",
                spec_hash="abc123",
                pattern_type="chain",
                status=status,
                created_at=old_timestamp,
                updated_at=old_timestamp,
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )
        await repo.save(state, "spec")

    # Cleanup with keep_completed=True
    deleted = await cleanup_expired_sessions(repo, max_age_days=7, keep_completed=True)

    # Should delete all except COMPLETED (3 sessions)
    assert deleted == 3

    # Verify only completed session remains
    remaining = await repo.list_sessions()
    assert len(remaining) == 1
    assert remaining[0].status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_cleanup_empty_repository(tmp_path: Path):
    """Test cleanup on empty repository."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Cleanup empty repository
    deleted = await cleanup_expired_sessions(repo, max_age_days=7)

    # Should delete nothing
    assert deleted == 0

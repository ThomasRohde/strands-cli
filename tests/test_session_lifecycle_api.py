"""Integration tests for SessionManager API session lifecycle.

Tests end-to-end session management flows:
- Create → list → get → resume
- Pagination with large session counts
- Concurrent session access
- Full lifecycle with cleanup
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
from strands_cli.types import RunResult


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
async def test_full_session_lifecycle(session_manager: SessionManager, mocker):
    """Test complete session lifecycle: create → list → get → resume → cleanup."""
    from strands_cli.types import PatternType

    # Mock run_resume for resume step
    mock_result = RunResult(
        success=True,
        pattern_type=PatternType.CHAIN,
        agent_id="test-agent",
        last_response="Resumed successfully",
        started_at="2025-11-12T00:00:00Z",
        completed_at="2025-11-12T00:00:01Z",
        duration_seconds=1.0,
    )
    mocker.patch(
        "strands_cli.api.session_manager.run_resume",
        new=AsyncMock(return_value=mock_result),
    )

    # 1. Create session
    session_id = generate_session_id()
    state = create_test_session(session_id, status=SessionStatus.PAUSED)
    await session_manager.repo.save(state, "spec content")

    # 2. List sessions - should find our session
    sessions = await session_manager.list()
    assert len(sessions) == 1
    assert sessions[0].metadata.session_id == session_id

    # 3. Get specific session
    retrieved = await session_manager.get(session_id)
    assert retrieved is not None
    assert retrieved.metadata.status == SessionStatus.PAUSED

    # 4. Resume session
    result = await session_manager.resume(session_id)
    assert result.success is True
    assert result.last_response == "Resumed successfully"

    # 5. Cleanup old sessions (should not delete recent one)
    deleted = await session_manager.cleanup(older_than_days=7)
    assert deleted == 0

    # 6. Delete session manually
    await session_manager.delete(session_id)
    deleted_session = await session_manager.get(session_id)
    assert deleted_session is None


@pytest.mark.asyncio
async def test_pagination_with_large_session_count(session_manager: SessionManager):
    """Test pagination handles large numbers of sessions correctly."""
    # Create 150 sessions
    session_ids = []
    for i in range(150):
        session_id = generate_session_id()
        session_ids.append(session_id)
        # Vary timestamps to test sorting
        updated_at = (datetime.now(UTC) - timedelta(hours=i)).isoformat()
        state = create_test_session(
            session_id,
            workflow_name=f"workflow-{i % 5}",  # 5 different workflows
            status=SessionStatus.RUNNING if i % 2 == 0 else SessionStatus.PAUSED,
            updated_at=updated_at,
        )
        await session_manager.repo.save(state, "spec")

    # Test pagination
    page_size = 50

    # Get first page
    page1 = await session_manager.list(offset=0, limit=page_size)
    assert len(page1) == page_size

    # Get second page
    page2 = await session_manager.list(offset=page_size, limit=page_size)
    assert len(page2) == page_size

    # Get third page
    page3 = await session_manager.list(offset=page_size * 2, limit=page_size)
    assert len(page3) == page_size

    # Verify no duplicates across pages
    all_ids = (
        [s.metadata.session_id for s in page1]
        + [s.metadata.session_id for s in page2]
        + [s.metadata.session_id for s in page3]
    )
    assert len(all_ids) == 150
    assert len(set(all_ids)) == 150  # All unique

    # Verify sorting (newest first)
    # Page 1 should have most recent sessions
    assert all(
        datetime.fromisoformat(page1[i].metadata.updated_at)
        >= datetime.fromisoformat(page1[i + 1].metadata.updated_at)
        for i in range(len(page1) - 1)
    )


@pytest.mark.asyncio
async def test_filter_and_pagination_combination(session_manager: SessionManager):
    """Test combining filters with pagination."""
    # Create 20 paused sessions and 20 running sessions
    paused_ids = []
    running_ids = []

    for _ in range(20):
        # Paused sessions
        paused_id = generate_session_id()
        paused_ids.append(paused_id)
        await session_manager.repo.save(
            create_test_session(
                paused_id,
                workflow_name="test-workflow",
                status=SessionStatus.PAUSED,
            ),
            "spec",
        )

        # Running sessions
        running_id = generate_session_id()
        running_ids.append(running_id)
        await session_manager.repo.save(
            create_test_session(
                running_id,
                workflow_name="test-workflow",
                status=SessionStatus.RUNNING,
            ),
            "spec",
        )

    # Filter by paused status with pagination
    page1 = await session_manager.list(
        status=SessionStatus.PAUSED,
        offset=0,
        limit=10,
    )
    assert len(page1) == 10
    assert all(s.metadata.status == SessionStatus.PAUSED for s in page1)

    page2 = await session_manager.list(
        status=SessionStatus.PAUSED,
        offset=10,
        limit=10,
    )
    assert len(page2) == 10
    assert all(s.metadata.status == SessionStatus.PAUSED for s in page2)

    # Verify all paused sessions retrieved across pages
    all_paused = page1 + page2
    assert len(all_paused) == 20


@pytest.mark.asyncio
async def test_concurrent_session_access(session_manager: SessionManager):
    """Test concurrent access to the same session (caching)."""
    import asyncio

    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec")

    # Simulate concurrent access to same session
    async def get_session():
        return await session_manager.get(session_id)

    # Run 10 concurrent gets
    results = await asyncio.gather(*[get_session() for _ in range(10)])

    # All should return the session
    assert len(results) == 10
    assert all(r is not None for r in results)
    assert all(r.metadata.session_id == session_id for r in results)

    # Cache should only contain one entry
    assert session_id in session_manager._cache


@pytest.mark.asyncio
async def test_cleanup_with_multiple_criteria(session_manager: SessionManager):
    """Test cleanup with age and status filters."""
    now = datetime.now(UTC)

    # Create sessions with various ages and statuses
    sessions_to_create = [
        # Old failed (should be deleted)
        (
            generate_session_id(),
            SessionStatus.FAILED,
            (now - timedelta(days=10)).isoformat(),
        ),
        # Old completed (should be kept)
        (
            generate_session_id(),
            SessionStatus.COMPLETED,
            (now - timedelta(days=10)).isoformat(),
        ),
        # Old running (should be kept)
        (
            generate_session_id(),
            SessionStatus.RUNNING,
            (now - timedelta(days=10)).isoformat(),
        ),
        # Recent failed (should be kept)
        (
            generate_session_id(),
            SessionStatus.FAILED,
            (now - timedelta(days=1)).isoformat(),
        ),
    ]

    for session_id, status, updated_at in sessions_to_create:
        await session_manager.repo.save(
            create_test_session(session_id, status=status, updated_at=updated_at),
            "spec",
        )

    # Cleanup old failed sessions only
    deleted = await session_manager.cleanup(
        older_than_days=7,
        status_filter=[SessionStatus.FAILED],
    )
    assert deleted == 1

    # Verify correct sessions remain
    remaining = await session_manager.list()
    assert len(remaining) == 3

    # All remaining should be either recent or not failed
    for session in remaining:
        assert session.metadata.status != SessionStatus.FAILED or datetime.fromisoformat(
            session.metadata.updated_at
        ) > now - timedelta(days=7)


@pytest.mark.asyncio
async def test_list_after_updates(session_manager: SessionManager):
    """Test that list reflects session updates correctly."""
    session_id = generate_session_id()

    # Create session with RUNNING status
    state = create_test_session(session_id, status=SessionStatus.RUNNING)
    await session_manager.repo.save(state, "spec")

    # List - should show RUNNING
    sessions = await session_manager.list()
    assert len(sessions) == 1
    assert sessions[0].metadata.status == SessionStatus.RUNNING

    # Update session to PAUSED
    state.metadata.status = SessionStatus.PAUSED
    state.metadata.updated_at = datetime.now(UTC).isoformat()
    await session_manager.repo.save(state, "")  # Empty spec = don't update spec

    # Invalidate cache to force reload
    session_manager._invalidate_cache(session_id)

    # List - should show PAUSED
    sessions = await session_manager.list()
    assert len(sessions) == 1
    assert sessions[0].metadata.status == SessionStatus.PAUSED


@pytest.mark.asyncio
async def test_workflow_name_filtering_accuracy(session_manager: SessionManager):
    """Test that workflow name filtering is exact and case-sensitive."""
    # Create sessions with similar names
    workflows = [
        "my-workflow",
        "my-workflow-v2",
        "My-Workflow",  # Different case
        "other-workflow",
    ]

    for workflow_name in workflows:
        session_id = generate_session_id()
        await session_manager.repo.save(
            create_test_session(session_id, workflow_name=workflow_name),
            "spec",
        )

    # Filter for exact match
    sessions = await session_manager.list(workflow_name="my-workflow")
    assert len(sessions) == 1
    assert sessions[0].metadata.workflow_name == "my-workflow"

    # Filter for different workflow
    sessions = await session_manager.list(workflow_name="my-workflow-v2")
    assert len(sessions) == 1
    assert sessions[0].metadata.workflow_name == "my-workflow-v2"

    # Case-sensitive check
    sessions = await session_manager.list(workflow_name="My-Workflow")
    assert len(sessions) == 1
    assert sessions[0].metadata.workflow_name == "My-Workflow"


@pytest.mark.asyncio
async def test_empty_results_pagination(session_manager: SessionManager):
    """Test pagination with no matching results."""
    # Create 5 running sessions
    for _ in range(5):
        session_id = generate_session_id()
        await session_manager.repo.save(
            create_test_session(session_id, status=SessionStatus.RUNNING),
            "spec",
        )

    # Filter by paused (should find nothing)
    sessions = await session_manager.list(status=SessionStatus.PAUSED)
    assert len(sessions) == 0

    # Paginate beyond available results
    sessions = await session_manager.list(offset=100, limit=10)
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_cache_behavior_across_operations(session_manager: SessionManager):
    """Test cache invalidation across various operations."""
    session_id = generate_session_id()
    state = create_test_session(session_id)
    await session_manager.repo.save(state, "spec")

    # Load into cache
    await session_manager.get(session_id)
    assert session_id in session_manager._cache

    # Delete should invalidate
    await session_manager.delete(session_id)
    assert session_id not in session_manager._cache

    # Recreate session
    await session_manager.repo.save(state, "spec")

    # Load into cache again
    await session_manager.get(session_id)
    assert session_id in session_manager._cache

    # Cleanup should invalidate
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    state.metadata.updated_at = old_time
    await session_manager.repo.save(state, "")
    session_manager._invalidate_cache(session_id)  # Simulate cache invalidation

    deleted = await session_manager.cleanup(older_than_days=7)
    assert deleted == 1
    assert session_id not in session_manager._cache

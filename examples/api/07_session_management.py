#!/usr/bin/env python3
"""Session management API example.

Demonstrates:
- Listing sessions with pagination and filtering
- Getting specific session details
- Resuming paused sessions
- Cleaning up old sessions
- Session caching behavior

This example shows how to programmatically manage workflow sessions
using the SessionManager API.

Usage:
    python examples/api/07_session_management.py

Requirements:
    - Some existing sessions in the default storage directory
    - Or run examples that create sessions first
"""

import asyncio
from datetime import datetime

from strands_cli.api import SessionManager
from strands_cli.session import SessionStatus


async def list_sessions_example():
    """Demonstrate listing sessions with pagination and filtering."""
    print("\n" + "=" * 60)
    print("1. Listing Sessions")
    print("=" * 60)

    manager = SessionManager()

    # List all sessions (first page)
    print("\nAll sessions (limit 10):")
    sessions = await manager.list(limit=10)
    print(f"Found {len(sessions)} sessions")

    for i, session in enumerate(sessions, 1):
        print(
            f"  {i}. {session.metadata.workflow_name} "
            f"({session.metadata.status.value}) - "
            f"{session.metadata.session_id[:8]}..."
        )

    # Filter by status
    print("\nPaused sessions only:")
    paused = await manager.list(status=SessionStatus.PAUSED)
    print(f"Found {len(paused)} paused sessions")

    for session in paused:
        print(f"  - {session.metadata.workflow_name} - {session.metadata.session_id[:8]}...")

    # Filter by workflow name
    if sessions:
        first_workflow = sessions[0].metadata.workflow_name
        print(f"\nSessions for workflow '{first_workflow}':")
        workflow_sessions = await manager.list(workflow_name=first_workflow)
        print(f"Found {len(workflow_sessions)} sessions")

    # Pagination example
    print("\nPagination (2 sessions per page):")
    page1 = await manager.list(offset=0, limit=2)
    print(f"Page 1: {len(page1)} sessions")

    page2 = await manager.list(offset=2, limit=2)
    print(f"Page 2: {len(page2)} sessions")


async def get_session_example():
    """Demonstrate getting session details."""
    print("\n" + "=" * 60)
    print("2. Getting Session Details")
    print("=" * 60)

    manager = SessionManager()

    # Get first session
    sessions = await manager.list(limit=1)
    if not sessions:
        print("No sessions found")
        return

    session_id = sessions[0].metadata.session_id
    print(f"\nRetrieving session: {session_id[:8]}...")

    # Get session (will be cached)
    session = await manager.get(session_id)
    if session:
        print(f"Workflow: {session.metadata.workflow_name}")
        print(f"Status: {session.metadata.status.value}")
        print(f"Pattern: {session.metadata.pattern_type}")
        print(f"Created: {session.metadata.created_at}")
        print(f"Updated: {session.metadata.updated_at}")
        print(f"Variables: {session.variables}")

        # Get again (should use cache)
        print("\nRetrieving same session again (from cache)...")
        session2 = await manager.get(session_id)
        print(f"Retrieved: {session2.metadata.session_id[:8]}...")

    # Try non-existent session
    print("\nTrying non-existent session:")
    fake_session = await manager.get("nonexistent-id")
    print(f"Result: {fake_session}")


async def resume_session_example():
    """Demonstrate resuming a paused session."""
    print("\n" + "=" * 60)
    print("3. Resuming Sessions")
    print("=" * 60)

    manager = SessionManager()

    # Find paused sessions
    paused = await manager.list(status=SessionStatus.PAUSED, limit=1)

    if not paused:
        print("No paused sessions found to resume")
        print("(This is expected if no workflows are currently paused)")
        return

    session = paused[0]
    session_id = session.metadata.session_id

    print(f"\nFound paused session: {session_id[:8]}...")
    print(f"Workflow: {session.metadata.workflow_name}")
    print(f"Pattern: {session.metadata.pattern_type}")

    # Ask user for confirmation
    print("\nTo resume this session, you would call:")
    print(f'  result = await manager.resume("{session_id}")')
    print("\nNote: Skipping actual resume to avoid side effects in example")

    # Uncomment to actually resume:
    # try:
    #     result = await manager.resume(session_id, verbose=True)
    #     print(f"\nResume result:")
    #     print(f"  Success: {result.success}")
    #     print(f"  Duration: {result.duration_seconds:.2f}s")
    # except Exception as e:
    #     print(f"Resume failed: {e}")


async def cleanup_sessions_example():
    """Demonstrate cleaning up old sessions."""
    print("\n" + "=" * 60)
    print("4. Cleaning Up Sessions")
    print("=" * 60)

    manager = SessionManager()

    # Count current sessions
    all_sessions = await manager.list()
    print(f"\nCurrent total sessions: {len(all_sessions)}")

    # Show what would be cleaned (dry run by checking ages)
    print("\nAnalyzing session ages...")
    now = datetime.now()
    old_count = 0

    for session in all_sessions:
        try:
            updated = datetime.fromisoformat(session.metadata.updated_at)
            age_days = (now - updated).days
            if age_days > 30:
                old_count += 1
        except ValueError:
            pass

    print(f"Sessions older than 30 days: {old_count}")

    # Cleanup example (commented out to avoid deleting user sessions)
    print("\nTo cleanup old sessions, you would call:")
    print("  deleted = await manager.cleanup(older_than_days=30)")
    print("\nNote: Skipping actual cleanup to preserve your sessions")

    # Uncomment to actually cleanup:
    # deleted = await manager.cleanup(older_than_days=30)
    # print(f"Deleted {deleted} old sessions")

    # Cleanup only failed sessions
    print("\nTo cleanup only failed sessions:")
    print(
        "  deleted = await manager.cleanup(\n"
        "      older_than_days=7,\n"
        "      status_filter=[SessionStatus.FAILED]\n"
        "  )"
    )


async def delete_session_example():
    """Demonstrate deleting a specific session."""
    print("\n" + "=" * 60)
    print("5. Deleting Sessions")
    print("=" * 60)

    manager = SessionManager()

    # Get completed sessions
    completed = await manager.list(status=SessionStatus.COMPLETED, limit=1)

    if not completed:
        print("No completed sessions found to delete")
        return

    session_id = completed[0].metadata.session_id
    print(f"\nFound completed session: {session_id[:8]}...")
    print(f"Workflow: {completed[0].metadata.workflow_name}")

    print("\nTo delete this session, you would call:")
    print(f'  await manager.delete("{session_id}")')
    print("\nNote: Skipping actual deletion to preserve your sessions")

    # Uncomment to actually delete:
    # await manager.delete(session_id)
    # print(f"Deleted session {session_id[:8]}...")


async def cache_behavior_example():
    """Demonstrate caching behavior."""
    print("\n" + "=" * 60)
    print("6. Cache Behavior")
    print("=" * 60)

    manager = SessionManager()

    sessions = await manager.list(limit=1)
    if not sessions:
        print("No sessions found")
        return

    session_id = sessions[0].metadata.session_id

    print(f"\nSession ID: {session_id[:8]}...")
    print(f"Cache TTL: {manager._cache_ttl.total_seconds() / 60:.0f} minutes")

    # Load into cache
    print("\n1. First get (cache miss):")
    await manager.get(session_id)
    print(f"   Session cached: {session_id in manager._cache}")

    # Get from cache
    print("\n2. Second get (cache hit):")
    await manager.get(session_id)
    print(f"   Session cached: {session_id in manager._cache}")

    # Delete invalidates cache
    print("\n3. After delete (cache invalidated):")
    print("   (Simulating cache invalidation)")
    manager._invalidate_cache(session_id)
    print(f"   Session cached: {session_id in manager._cache}")


async def main():
    """Run all session management examples."""
    print("\n" + "=" * 70)
    print(" " * 15 + "Session Management API Examples")
    print("=" * 70)

    try:
        await list_sessions_example()
        await get_session_example()
        await resume_session_example()
        await cleanup_sessions_example()
        await delete_session_example()
        await cache_behavior_example()

        print("\n" + "=" * 70)
        print(" " * 20 + "✓ All examples completed")
        print("=" * 70)
        print("\nKey takeaways:")
        print("  • Use list() with filters for targeted session retrieval")
        print("  • Sessions are cached for 5 minutes to improve performance")
        print("  • Pagination supports large session counts (max limit: 1000)")
        print("  • Cache is automatically invalidated on delete/resume")
        print("  • Cleanup supports age and status filters")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

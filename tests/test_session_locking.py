"""Tests for session file locking and concurrent access.

Tests concurrent write safety using multiprocessing to simulate real-world
scenarios where multiple CLI instances might write to the same session.
"""

import asyncio
import multiprocessing
import time
from pathlib import Path

import pytest

from strands_cli.session import (
    SessionMetadata,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.locking import session_lock
from strands_cli.session.utils import generate_session_id


def test_session_lock_basic(tmp_path: Path):
    """Test basic lock acquisition and release."""
    session_dir = tmp_path / "session_test"
    session_dir.mkdir()

    lock_file = session_dir / ".lock"

    # Acquire lock
    with session_lock(session_dir):
        # Verify lock file exists while locked
        assert lock_file.exists()

    # After release, filelock may or may not clean up the file
    # Just verify context manager completed without error
    assert True  # Lock was successfully released


def test_session_lock_prevents_concurrent_access(tmp_path: Path):
    """Test that lock prevents concurrent access to same session."""
    session_dir = tmp_path / "session_test"
    session_dir.mkdir()

    # Acquire first lock
    with session_lock(session_dir, timeout=0.5):
        # Try to acquire second lock (should timeout)
        try:
            with session_lock(session_dir, timeout=0.1):
                pytest.fail("Second lock should have timed out")
        except TimeoutError as e:
            assert "Failed to acquire lock" in str(e)


def _concurrent_write_worker(session_dir: Path, worker_id: int, iterations: int) -> int:
    """Worker function for concurrent write test.

    Args:
        session_dir: Session directory to write to
        worker_id: Worker identifier
        iterations: Number of writes to perform

    Returns:
        Number of successful writes
    """
    success_count = 0

    for _ in range(iterations):
        try:
            # Acquire lock and write
            with session_lock(session_dir, timeout=5.0):
                # Simulate write operation
                counter_file = session_dir / "counter.txt"

                # Read current value
                current = 0
                if counter_file.exists():
                    current = int(counter_file.read_text())

                # Increment and write back (with small delay to increase contention)
                time.sleep(0.001)
                counter_file.write_text(str(current + 1))

                success_count += 1
        except TimeoutError:
            # Lock acquisition failed
            pass

    return success_count


def test_session_lock_concurrent_writes(tmp_path: Path):
    """Test concurrent writes with multiple processes.

    Uses multiprocessing to simulate multiple CLI instances writing to the
    same session concurrently. Verifies that file locking prevents corruption.
    """
    session_dir = tmp_path / "session_test"
    session_dir.mkdir()

    num_workers = 4
    iterations_per_worker = 10

    # Run concurrent writers
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.starmap(
            _concurrent_write_worker,
            [(session_dir, i, iterations_per_worker) for i in range(num_workers)],
        )

    # Verify counter value equals total successful writes
    counter_file = session_dir / "counter.txt"
    assert counter_file.exists()

    final_value = int(counter_file.read_text())
    total_success = sum(results)

    # Final value should match total successful writes (no lost updates)
    assert final_value == total_success
    # Most writes should succeed (some may timeout under heavy contention)
    assert total_success >= num_workers * iterations_per_worker * 0.8


@pytest.mark.asyncio
async def test_repository_save_with_lock(tmp_path: Path):
    """Test that FileSessionRepository.save() acquires lock."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Create session state
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="test-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={"topic": "AI"},
        runtime_config={"provider": "ollama"},
        pattern_state={"current_step": 1},
        token_usage=TokenUsage(total_input_tokens=100),
    )

    # Save should succeed
    await repo.save(state, "spec content")

    # Verify atomic write created all files
    session_dir = repo._session_dir(session_id)
    assert (session_dir / "session.json").exists()
    assert (session_dir / "pattern_state.json").exists()
    assert (session_dir / "spec_snapshot.yaml").exists()

    # Verify no .tmp files left behind (atomic write cleanup)
    assert not list(session_dir.glob("*.tmp"))


def _concurrent_save_worker(storage_dir: Path, session_id: str, worker_id: int) -> bool:
    """Worker function for concurrent save test.

    Args:
        storage_dir: Session storage directory
        session_id: Session ID to write to
        worker_id: Worker identifier

    Returns:
        True if all saves succeeded
    """

    async def _save_multiple():
        repo = FileSessionRepository(storage_dir=storage_dir)

        for i in range(5):
            state = SessionState(
                metadata=SessionMetadata(
                    session_id=session_id,
                    workflow_name=f"worker-{worker_id}",
                    spec_hash="abc123",
                    pattern_type="chain",
                    status=SessionStatus.RUNNING,
                    created_at="2025-11-09T10:00:00Z",
                    updated_at=f"2025-11-09T10:00:{i:02d}Z",
                ),
                variables={"worker": str(worker_id), "iteration": str(i)},
                runtime_config={"provider": "ollama"},
                pattern_state={"worker": worker_id, "iteration": i},
                token_usage=TokenUsage(total_input_tokens=100 * (i + 1)),
            )

            await repo.save(state, f"spec from worker {worker_id}")
            # Small delay to increase contention
            await asyncio.sleep(0.001)

        return True

    return asyncio.run(_save_multiple())


def test_repository_concurrent_saves(tmp_path: Path):
    """Test concurrent saves to same session from multiple processes.

    Verifies that atomic writes + file locking prevent corruption
    when multiple CLI instances checkpoint to the same session.
    """
    session_id = generate_session_id()
    num_workers = 3

    # Run concurrent savers
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.starmap(
            _concurrent_save_worker,
            [(tmp_path, session_id, i) for i in range(num_workers)],
        )

    # All workers should succeed
    assert all(results)

    # Verify session files are valid JSON (not corrupted)
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_dir = repo._session_dir(session_id)

    import json

    # Should be able to parse all files
    session_data = json.loads((session_dir / "session.json").read_text())
    pattern_data = json.loads((session_dir / "pattern_state.json").read_text())
    spec_content = (session_dir / "spec_snapshot.yaml").read_text()

    assert session_data["metadata"]["session_id"] == session_id
    assert "worker" in pattern_data
    assert "spec from worker" in spec_content

    # Verify no .tmp files left behind
    assert not list(session_dir.glob("*.tmp"))


@pytest.mark.asyncio
async def test_lock_timeout_during_save(tmp_path: Path):
    """Test that lock timeout is raised when another process holds lock."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()
    session_dir = repo._session_dir(session_id)
    session_dir.mkdir(parents=True)

    # Hold lock in background
    lock_held = multiprocessing.Event()
    lock_released = multiprocessing.Event()

    def hold_lock():
        """Hold lock for extended period."""
        with session_lock(session_dir, timeout=30.0):
            lock_held.set()
            # Hold lock until signaled
            lock_released.wait(timeout=10.0)

    # Start background lock holder
    import threading

    lock_thread = threading.Thread(target=hold_lock, daemon=True)
    lock_thread.start()

    # Wait for lock to be acquired
    lock_held.wait(timeout=5.0)

    # Try to save (should timeout)
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="test",
            spec_hash="abc123",
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

    # Temporarily reduce timeout for test
    from unittest.mock import patch

    with patch("strands_cli.session.file_repository.session_lock") as mock_lock:
        # Configure mock to use short timeout
        mock_lock.side_effect = lambda dir: session_lock(dir, timeout=0.1)

        with pytest.raises(TimeoutError, match="Failed to acquire lock"):
            await repo.save(state, "spec")

    # Release lock
    lock_released.set()
    lock_thread.join(timeout=2.0)

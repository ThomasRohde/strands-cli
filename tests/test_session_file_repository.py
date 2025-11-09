"""Tests for file-based session repository.

Tests FileSessionRepository save, load, delete, list operations
with async execution and error handling.
"""

import json
from pathlib import Path

import pytest

from strands_cli.session import (
    SessionCorruptedError,
    SessionMetadata,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import generate_session_id


@pytest.mark.asyncio
async def test_save_and_load_session(tmp_path: Path):
    """Test saving and loading a session."""
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
        pattern_state={"current_step": 1, "step_history": []},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
    )

    # Save
    await repo.save(state, "version: 0\nname: test")

    # Verify session directory created
    session_dir = repo._session_dir(session_id)
    assert session_dir.exists()
    assert (session_dir / "session.json").exists()
    assert (session_dir / "pattern_state.json").exists()
    assert (session_dir / "spec_snapshot.yaml").exists()

    # Load
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.session_id == session_id
    assert loaded.variables["topic"] == "AI"
    assert loaded.pattern_state["current_step"] == 1
    assert loaded.token_usage.total_input_tokens == 100


@pytest.mark.asyncio
async def test_load_nonexistent_session(tmp_path: Path):
    """Test loading non-existent session returns None."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    loaded = await repo.load("nonexistent-session-id")
    assert loaded is None


@pytest.mark.asyncio
async def test_exists(tmp_path: Path):
    """Test session existence check."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Not exists initially
    exists = await repo.exists(session_id)
    assert not exists

    # Create session
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
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec content")

    # Now exists
    exists = await repo.exists(session_id)
    assert exists


@pytest.mark.asyncio
async def test_delete_session(tmp_path: Path):
    """Test session deletion."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Create session
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
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec content")

    # Verify exists
    assert await repo.exists(session_id)

    # Delete
    await repo.delete(session_id)

    # Verify deleted
    assert not await repo.exists(session_id)


@pytest.mark.asyncio
async def test_delete_nonexistent_session(tmp_path: Path):
    """Test deleting non-existent session doesn't raise error."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Should not raise
    await repo.delete("nonexistent-session-id")


@pytest.mark.asyncio
async def test_list_sessions(tmp_path: Path):
    """Test listing all sessions."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create 3 sessions
    session_ids = []
    for i in range(3):
        session_id = generate_session_id()
        session_ids.append(session_id)

        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"workflow-{i}",
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
        await repo.save(state, "spec content")

    # List
    sessions = await repo.list_sessions()
    assert len(sessions) == 3
    assert all(s.status == SessionStatus.RUNNING for s in sessions)

    # Verify all session IDs present
    listed_ids = {s.session_id for s in sessions}
    assert set(session_ids) == listed_ids


@pytest.mark.asyncio
async def test_list_sessions_empty(tmp_path: Path):
    """Test listing sessions when none exist."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    sessions = await repo.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_session_json_structure(tmp_path: Path):
    """Test session.json file structure."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

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
        variables={"key": "value"},
        runtime_config={"provider": "ollama"},
        pattern_state={"step": 1},
        token_usage=TokenUsage(total_input_tokens=100),
        artifacts_written=["output.txt"],
    )
    await repo.save(state, "spec content")

    # Read raw JSON
    session_json = repo._session_dir(session_id) / "session.json"
    data = json.loads(session_json.read_text(encoding="utf-8"))

    assert "metadata" in data
    assert "variables" in data
    assert "runtime_config" in data
    assert "token_usage" in data
    assert "artifacts_written" in data

    assert data["metadata"]["session_id"] == session_id
    assert data["variables"]["key"] == "value"
    assert data["runtime_config"]["provider"] == "ollama"
    assert data["token_usage"]["total_input_tokens"] == 100
    assert data["artifacts_written"] == ["output.txt"]


@pytest.mark.asyncio
async def test_pattern_state_json_structure(tmp_path: Path):
    """Test pattern_state.json file structure."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    pattern_state = {
        "current_step": 2,
        "step_history": [
            {"index": 0, "agent": "researcher", "response": "...", "tokens": 1000},
            {"index": 1, "agent": "analyst", "response": "...", "tokens": 1200},
        ],
    }

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
        variables={},
        runtime_config={},
        pattern_state=pattern_state,
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec content")

    # Read raw JSON
    pattern_json = repo._session_dir(session_id) / "pattern_state.json"
    data = json.loads(pattern_json.read_text(encoding="utf-8"))

    assert data["current_step"] == 2
    assert len(data["step_history"]) == 2
    assert data["step_history"][0]["agent"] == "researcher"


@pytest.mark.asyncio
async def test_spec_snapshot_content(tmp_path: Path):
    """Test spec_snapshot.yaml preserves original content."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    spec_content = "version: 0\nname: test-workflow\npattern:\n  type: chain"

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
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, spec_content)

    # Read spec snapshot
    spec_file = repo._session_dir(session_id) / "spec_snapshot.yaml"
    saved_content = spec_file.read_text(encoding="utf-8")

    assert saved_content == spec_content


@pytest.mark.asyncio
async def test_corrupted_session_json(tmp_path: Path):
    """Test loading session with corrupted JSON raises error."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Create valid session first
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
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )
    await repo.save(state, "spec content")

    # Corrupt session.json
    session_json = repo._session_dir(session_id) / "session.json"
    session_json.write_text("{invalid json", encoding="utf-8")

    # Load should raise SessionCorruptedError
    with pytest.raises(SessionCorruptedError) as exc_info:
        await repo.load(session_id)

    assert "Invalid JSON" in str(exc_info.value)
    assert session_id in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_agents_dir(tmp_path: Path):
    """Test get_agents_dir returns correct path."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-session-123"

    agents_dir = repo.get_agents_dir(session_id)

    expected = tmp_path / f"session_{session_id}" / "agents"
    assert agents_dir == expected


@pytest.mark.asyncio
async def test_get_spec_snapshot_path(tmp_path: Path):
    """Test get_spec_snapshot_path returns correct path."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-session-123"

    spec_path = await repo.get_spec_snapshot_path(session_id)

    expected = tmp_path / f"session_{session_id}" / "spec_snapshot.yaml"
    assert spec_path == expected


@pytest.mark.asyncio
async def test_list_sessions_skips_corrupted(tmp_path: Path):
    """Test list_sessions skips corrupted sessions and continues."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create 2 valid sessions
    for i in range(2):
        session_id = generate_session_id()
        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"workflow-{i}",
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
        await repo.save(state, "spec content")

    # Create corrupted session
    corrupted_dir = tmp_path / "session_corrupted"
    corrupted_dir.mkdir()
    (corrupted_dir / "session.json").write_text("{invalid json}", encoding="utf-8")

    # List should skip corrupted and return 2 valid sessions
    sessions = await repo.list_sessions()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_save_preserves_spec_snapshot(tmp_path: Path):
    """Test that repeated saves don't overwrite spec_snapshot.yaml when empty content is passed.
    
    This is critical for checkpoint functionality - the spec snapshot is written once
    during session creation, then all subsequent checkpoint saves pass empty string
    to skip spec update and preserve the original snapshot.
    """
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Original spec content
    original_spec = "version: 0\nname: test-workflow\npattern:\n  type: chain\nsteps:\n  - agent: test"

    # Create initial session state
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
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(total_input_tokens=0, total_output_tokens=0),
    )

    # Save with original spec content (session creation)
    await repo.save(state, original_spec)

    # Verify spec snapshot created
    spec_file = repo._session_dir(session_id) / "spec_snapshot.yaml"
    assert spec_file.exists()
    assert spec_file.read_text(encoding="utf-8") == original_spec

    # Update session state (simulate checkpoint after step 1)
    state.pattern_state["current_step"] = 1
    state.pattern_state["step_history"] = [
        {"index": 0, "agent": "test", "response": "Step 1 output", "tokens": 1000}
    ]
    state.token_usage.total_input_tokens = 500
    state.token_usage.total_output_tokens = 500
    state.metadata.updated_at = "2025-11-09T10:05:00Z"

    # Save with empty spec_content (checkpoint - should NOT update spec snapshot)
    await repo.save(state, "")

    # Verify spec snapshot is UNCHANGED
    assert spec_file.exists()
    assert spec_file.read_text(encoding="utf-8") == original_spec

    # Verify other state was updated
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.pattern_state["current_step"] == 1
    assert len(loaded.pattern_state["step_history"]) == 1
    assert loaded.token_usage.total_input_tokens == 500

    # Update again (simulate checkpoint after step 2)
    state.pattern_state["current_step"] = 2
    state.pattern_state["step_history"].append(
        {"index": 1, "agent": "test", "response": "Step 2 output", "tokens": 1200}
    )
    state.token_usage.total_input_tokens = 1100
    state.token_usage.total_output_tokens = 1100
    state.metadata.updated_at = "2025-11-09T10:10:00Z"

    # Save with empty spec_content again (another checkpoint)
    await repo.save(state, "")

    # Verify spec snapshot STILL unchanged after multiple checkpoints
    assert spec_file.exists()
    assert spec_file.read_text(encoding="utf-8") == original_spec

    # Verify latest state was updated
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.pattern_state["current_step"] == 2
    assert len(loaded.pattern_state["step_history"]) == 2
    assert loaded.token_usage.total_input_tokens == 1100

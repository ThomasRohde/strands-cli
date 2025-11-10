"""Tests for session failure handling when executors encounter exceptions.

Verifies that sessions are properly marked as FAILED when exceptions occur
during workflow execution, preventing orphaned RUNNING sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.chain import ChainExecutionError, run_chain
from strands_cli.loader.yaml_loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import compute_spec_hash, generate_session_id, now_iso8601


@pytest.fixture
def chain_spec_file(tmp_path: Path) -> Path:
    """Create a minimal chain spec for testing."""
    spec_content = (
        "version: 0\n"
        'name: "test-chain"\n'
        "runtime:\n"
        "  provider: ollama\n"
        '  model_id: "test"\n'
        "agents:\n"
        "  agent1:\n"
        '    prompt: "Test prompt"\n'
        "pattern:\n"
        "  type: chain\n"
        "  config:\n"
        "    steps:\n"
        "      - agent: agent1\n"
        '        input: "test"\n'
    )
    spec_file = tmp_path / "test-chain.yaml"
    spec_file.write_text(spec_content)
    return spec_file


@pytest.mark.asyncio
async def test_chain_executor_marks_session_failed_on_exception(
    tmp_path: Path, chain_spec_file: Path, mocker: Any
) -> None:
    """Test that chain executor marks session as FAILED when an exception occurs."""
    # Load spec
    spec = load_spec(str(chain_spec_file))
    spec_content = chain_spec_file.read_text()

    # Create session repository
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Initialize session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash=compute_spec_hash(chain_spec_file),
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={},
        runtime_config=spec.runtime.model_dump(),
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(),
    )

    # Save initial session
    await repo.save(session_state, spec_content)

    # Mock agent to raise an exception
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("Simulated agent failure"))

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Mock AgentCache.close to avoid cleanup errors
    mocker.patch("strands_cli.exec.utils.AgentCache.close", new_callable=AsyncMock)

    # Execute chain (should fail and mark session as FAILED)
    with pytest.raises(ChainExecutionError, match="Simulated agent failure"):
        await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify session was marked as FAILED
    loaded = await repo.load(session_id)
    assert loaded is not None, "Session should still exist"
    assert loaded.metadata.status == SessionStatus.FAILED, (
        f"Session should be FAILED, got {loaded.metadata.status}"
    )
    # Verify error message was captured
    assert loaded.metadata.error is not None, "Error should be set"
    assert "RuntimeError: Simulated agent failure" in loaded.metadata.error


@pytest.mark.asyncio
async def test_session_failure_saved_even_if_save_fails(
    tmp_path: Path, chain_spec_file: Path, mocker: Any
) -> None:
    """Test that executor handles errors gracefully if session save fails."""
    # Load spec
    spec = load_spec(str(chain_spec_file))
    spec_content = chain_spec_file.read_text()

    # Create session repository
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Initialize session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash=compute_spec_hash(chain_spec_file),
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={},
        runtime_config=spec.runtime.model_dump(),
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(),
    )

    # Save initial session
    await repo.save(session_state, spec_content)

    # Mock agent to raise an exception
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("Agent failure"))

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Mock AgentCache.close
    mocker.patch("strands_cli.exec.utils.AgentCache.close", new_callable=AsyncMock)

    # Mock repo.save to fail when trying to save FAILED status
    original_save = repo.save
    save_call_count = [0]

    async def mock_save(state: SessionState, content: str) -> None:
        save_call_count[0] += 1
        if state.metadata.status == SessionStatus.FAILED:
            raise OSError("Simulated save failure")
        await original_save(state, content)

    mocker.patch.object(repo, "save", side_effect=mock_save)

    # Execute chain (should fail, try to mark as FAILED, but save fails)
    # The executor should still raise the original ChainExecutionError
    with pytest.raises(ChainExecutionError, match="Agent failure"):
        await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify that save was attempted for FAILED status
    assert save_call_count[0] > 0, "Save should have been attempted"

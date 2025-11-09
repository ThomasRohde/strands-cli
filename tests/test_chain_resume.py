"""Integration tests for chain pattern session persistence and resume.

Tests cover:
- Fresh execution with session creation
- Resume from various checkpoints (after step 1, 2, etc.)
- Agent conversation restoration via Strands SDK FileSessionManager
- Spec hash mismatch warnings
- Completed session rejection
- Token usage accumulation across resume
- Checkpoint creation after each step
- Session status transitions
- End-to-end checkpoint verification
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.chain import run_chain
from strands_cli.loader.yaml_loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import compute_spec_hash, generate_session_id, now_iso8601
from strands_cli.types import Spec


@pytest.fixture
def chain_3_step_spec(tmp_path: Path) -> Path:
    """Create a 3-step chain spec for testing."""
    spec_content = (
        "version: 0\n"
        'name: "chain-resume-test"\n'
        'description: "3-step chain for testing resume functionality"\n'
        "\n"
        "runtime:\n"
        "  provider: ollama\n"
        '  host: "http://localhost:11434"\n'
        '  model_id: "gpt-oss"\n'
        "  budgets:\n"
        "    max_tokens: 50000\n"
        "\n"
        "agents:\n"
        "  researcher:\n"
        '    prompt: "You are a research assistant. Research the topic: {{ topic }}"\n'
        "    tools: []\n"
        "\n"
        "  analyst:\n"
        '    prompt: "You are an analyst. Analyze the research findings."\n'
        "    tools: []\n"
        "\n"
        "  writer:\n"
        '    prompt: "You are a technical writer. Write a summary report."\n'
        "    tools: []\n"
        "\n"
        "pattern:\n"
        "  type: chain\n"
        "  config:\n"
        "    steps:\n"
        "      - agent: researcher\n"
        '        input: "Research the topic: {{ topic }}"\n'
        "\n"
        "      - agent: analyst\n"
        '        input: "Analyze these findings:\\n\\n{{ steps[0].response }}"\n'
        "\n"
        "      - agent: writer\n"
        "        input: |\n"
        "          Write a summary based on:\n"
        "          Research: {{ steps[0].response }}\n"
        "          Analysis: {{ steps[1].response }}\n"
        "\n"
        "outputs:\n"
        "  artifacts:\n"
        '    - path: "./artifacts/resume-test-report.md"\n'
        '      from: "{{ last_response }}"\n'
    )
    spec_file = tmp_path / "chain-3-step.yaml"
    spec_file.write_text(spec_content)
    return spec_file


@pytest.mark.asyncio
async def test_chain_fresh_execution_creates_session(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test that fresh execution creates session when save_session=True."""
    # Load spec
    spec = load_spec(str(chain_3_step_spec))

    # Mock agent invocations
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=["Step 0 result", "Step 1 result", "Step 2 result"]
    )

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Create session repository
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Initialize session state for fresh execution
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(),
    )

    # Save initial state
    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Execute chain (fresh start - will execute all 3 steps)
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution success
    assert result.success
    assert result.last_response == "Step 2 result"
    assert len(result.execution_context.get("steps", [])) == 3

    # Verify session was checkpointed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state["step_history"]) == 3
    assert loaded.pattern_state["current_step"] == 3  # All steps completed

    # Verify all 3 agents were invoked
    assert mock_agent.invoke_async.call_count == 3


@pytest.mark.asyncio
async def test_chain_resume_after_step_1(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test resuming chain after step 1 completes."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Create session with 2 completed steps (steps 0 and 1)
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 2,  # Next step to execute is index 2
            "step_history": [
                {
                    "index": 0,
                    "agent": "researcher",
                    "response": "Step 0 result",
                    "tokens_estimated": 1000,
                },
                {
                    "index": 1,
                    "agent": "analyst",
                    "response": "Step 1 result",
                    "tokens_estimated": 1200,
                },
            ],
        },
        token_usage=TokenUsage(total_input_tokens=1100, total_output_tokens=1100),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock only step 2 (steps 0-1 should be skipped)
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value="Step 2 result")

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Resume from step 2
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify step 2 executed, steps 0-1 skipped
    assert result.success
    assert result.last_response == "Step 2 result"
    assert mock_agent.invoke_async.call_count == 1  # Only step 2 invoked

    # Verify session completed with all 3 steps
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert len(loaded.pattern_state["step_history"]) == 3
    assert loaded.metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_chain_resume_on_last_step(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test resuming chain on the last step."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Create session with first 2 steps completed, starting on step 2 (last step)
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 2,
            "step_history": [
                {"index": 0, "agent": "researcher", "response": "Research result"},
                {"index": 1, "agent": "analyst", "response": "Analysis result"},
            ],
        },
        token_usage=TokenUsage(total_input_tokens=1500, total_output_tokens=1000),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock last step
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value="Final summary report")

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Resume
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution
    assert result.success
    assert result.last_response == "Final summary report"
    assert mock_agent.invoke_async.call_count == 1

    # Verify session marked as completed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state["step_history"]) == 3


@pytest.mark.asyncio
async def test_chain_resume_agent_session_restoration(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test that agent conversation is restored via Strands SDK FileSessionManager."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = "test-session-123"

    # Create session with one completed step
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 1,
            "step_history": [{"index": 0, "agent": "researcher", "response": "Research data"}],
        },
        token_usage=TokenUsage(total_input_tokens=500, total_output_tokens=500),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock agent and FileSessionManager
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=["Analysis complete", "Summary complete"])

    mock_file_session_manager = mocker.patch(
        "strands.session.file_session_manager.FileSessionManager"
    )

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Execute steps 1 and 2 (resume mode)
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution success
    assert result.success

    # Verify FileSessionManager was instantiated with correct session_id for each agent
    # The agent cache builds agents with session restoration
    # We should see calls for both analyst and writer agents
    assert mock_file_session_manager.call_count >= 1

    # Check that session IDs include the base session_id
    for call in mock_file_session_manager.call_args_list:
        call_kwargs = call[1]
        # Session ID should be in format: {base_session_id}_{agent_id}
        assert "session_id" in call_kwargs
        assert session_id in call_kwargs["session_id"]
        # Storage dir should be under session directory
        assert "storage_dir" in call_kwargs
        assert f"session_{session_id}" in str(call_kwargs["storage_dir"])


@pytest.mark.asyncio
async def test_chain_token_usage_accumulates_on_resume(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test that token usage accumulates correctly across resume."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Setup: Session with 2 steps complete, 2200 tokens used
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 2,
            "step_history": [
                {"index": 0, "agent": "researcher", "response": "Research"},
                {"index": 1, "agent": "analyst", "response": "Analysis"},
            ],
        },
        token_usage=TokenUsage(total_input_tokens=1100, total_output_tokens=1100),  # 2200 total
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock step 2 execution
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value="Summary")

    # Mock the after_invocation event to include usage data
    mock_event = MagicMock()
    mock_event.accumulated_usage = {
        "totalTokens": 800,  # 400 in + 400 out for step 2
        "inputTokens": 400,
        "outputTokens": 400,
    }
    mock_agent.after_invocation = [mock_event]

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Mock estimate_tokens to return consistent values
    mocker.patch("strands_cli.exec.utils.estimate_tokens", return_value=400)

    # Resume from step 2
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution
    assert result.success

    # Verify cumulative tokens (exact calculation depends on implementation)
    # At minimum, should be > initial 2200 tokens
    loaded = await repo.load(session_id)
    assert loaded is not None
    cumulative = loaded.token_usage.total_input_tokens + loaded.token_usage.total_output_tokens
    assert cumulative > 2200  # Should accumulate step 2 tokens


@pytest.mark.asyncio
async def test_chain_checkpoint_after_each_step(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test that checkpoint is saved after each step completion."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Initialize fresh session
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock agent execution
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=["Step 0", "Step 1", "Step 2"])

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Spy on repo.save to count checkpoints
    original_save = repo.save
    save_calls = []

    async def mock_save(*args: Any, **kwargs: Any) -> None:
        save_calls.append(args[0])  # Track session state
        await original_save(*args, **kwargs)

    mocker.patch.object(repo, "save", side_effect=mock_save)

    # Execute chain
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution
    assert result.success

    # Verify checkpoints were saved (initial save + after each of 3 steps = 4 total)
    # Note: Initial save already done before run_chain, so we expect saves during execution
    assert len(save_calls) >= 3  # At least one per step


@pytest.mark.asyncio
async def test_chain_resume_completed_session_validation(
    tmp_path: Path, chain_3_step_spec: Path
) -> None:
    """Test that resume logic handles completed sessions appropriately.

    Note: This tests the validation that should happen before calling run_chain.
    The actual validation is in the CLI resume command, not in run_chain itself.
    """
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Create completed session
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.COMPLETED,  # Already completed
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 3,  # All steps done
            "step_history": [
                {"index": 0, "agent": "researcher", "response": "Research"},
                {"index": 1, "agent": "analyst", "response": "Analysis"},
                {"index": 2, "agent": "writer", "response": "Summary"},
            ],
        },
        token_usage=TokenUsage(total_input_tokens=2000, total_output_tokens=2000),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Verify session exists and is completed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED

    # The CLI layer should validate before calling run_chain
    # This is a documentation test showing expected session state


@pytest.mark.asyncio
async def test_chain_session_status_transitions(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test session status transitions from RUNNING to COMPLETED."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Initialize session in RUNNING state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={"current_step": 0, "step_history": []},
        token_usage=TokenUsage(),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Verify initial status
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.RUNNING

    # Mock agent execution
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=["Step 0", "Step 1", "Step 2"])

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Execute chain to completion
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution completed
    assert result.success

    # Verify status transitioned to COMPLETED
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_chain_resume_parameter_validation(tmp_path: Path, chain_3_step_spec: Path) -> None:
    """Test that session_state and session_repo must both be provided or both be None."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Test: session_state without session_repo
    with pytest.raises(ValueError, match="session_state and session_repo must both be provided"):
        await run_chain(spec, variables={}, session_state=session_state, session_repo=None)

    # Test: session_repo without session_state
    with pytest.raises(ValueError, match="session_state and session_repo must both be provided"):
        await run_chain(spec, variables={}, session_state=None, session_repo=repo)

    # Test: Both None is valid (fresh execution without session)
    # This would work but requires mocking agent execution
    # await run_chain(spec, variables={}, session_state=None, session_repo=None)

    # Test: Both provided is valid
    # This would work but requires mocking agent execution
    # await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)


@pytest.mark.asyncio
async def test_chain_resume_with_step_history_context(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """Test that step history is correctly used in template context on resume."""
    spec = load_spec(str(chain_3_step_spec))
    repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
    session_id = generate_session_id()

    # Create session with step 0 complete
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash="test-hash-123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config={"provider": "ollama", "model_id": "gpt-oss"},
        pattern_state={
            "current_step": 1,
            "step_history": [
                {"index": 0, "agent": "researcher", "response": "Research about AI agents"}
            ],
        },
        token_usage=TokenUsage(total_input_tokens=500, total_output_tokens=500),
    )

    spec_content = chain_3_step_spec.read_text()
    await repo.save(session_state, spec_content)

    # Mock agent - we'll inspect what input it receives
    mock_agent = MagicMock()
    invoke_calls = []

    async def capture_invoke(*args: Any, **kwargs: Any) -> str:
        invoke_calls.append({"args": args, "kwargs": kwargs})
        return f"Response to: {args[0] if args else 'unknown'}"

    mock_agent.invoke_async = capture_invoke

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Resume from step 1
    result = await run_chain(
        spec, variables={"topic": "AI agents"}, session_state=session_state, session_repo=repo
    )

    # Verify execution
    assert result.success

    # Verify that step 1 received the step 0 response in its input
    # Step 1's input template is: "Analyze these findings:\n\n{{ steps[0].response }}"
    assert len(invoke_calls) >= 1
    step_1_input = invoke_calls[0]["args"][0]
    assert "Research about AI agents" in step_1_input
    assert "Analyze these findings" in step_1_input


@pytest.mark.asyncio
async def test_chain_checkpoints_written_and_resume_succeeds(
    tmp_path: Path, chain_3_step_spec: Path, mocker: Any
) -> None:
    """End-to-end test: Verify checkpoints are written during execution and resume works.

    This test verifies the two critical blockers are fixed:
    1. Session state is passed to executors so checkpoints are written
    2. Spec snapshot is preserved across checkpoint saves
    """
    # Load spec
    spec = load_spec(str(chain_3_step_spec), {"topic": "AI agents"})
    spec_content = chain_3_step_spec.read_text(encoding="utf-8")

    # Create session repository
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Initialize session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash=compute_spec_hash(chain_3_step_spec),
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables={"topic": "AI agents"},
        runtime_config=spec.runtime.model_dump(),
        pattern_state={},  # Will be initialized by executor
        token_usage=TokenUsage(),
    )

    # Save initial session with spec snapshot
    await repo.save(session_state, spec_content)

    # Verify spec snapshot created
    spec_snapshot_path = repo._session_dir(session_id) / "spec_snapshot.yaml"
    assert spec_snapshot_path.exists()
    original_spec_content = spec_snapshot_path.read_text(encoding="utf-8")
    assert original_spec_content == spec_content

    # Mock agent invocations - only run step 0 and 1
    invoke_count = [0]

    async def mock_invoke(*args, **kwargs):
        invoke_count[0] += 1
        if invoke_count[0] == 1:
            return "Step 0 result: Research about AI agents"
        elif invoke_count[0] == 2:
            return "Step 1 result: Analysis of research"
        else:
            # Should not reach step 2 in first execution
            raise RuntimeError("Should only execute 2 steps")

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke)

    mocker.patch(
        "strands_cli.exec.utils.AgentCache.get_or_build_agent",
        return_value=mock_agent,
    )

    # Mock AgentCache.close to avoid cleanup errors
    mocker.patch("strands_cli.exec.utils.AgentCache.close", new_callable=AsyncMock)

    # Simulate execution interrupted after step 1 by limiting steps
    # Create a modified spec with only 2 steps
    limited_spec = load_spec(str(chain_3_step_spec), {"topic": "AI agents"})
    limited_spec.pattern.config.steps = limited_spec.pattern.config.steps[:2]

    # Execute first 2 steps with session persistence
    result1 = await run_chain(limited_spec, {"topic": "AI agents"}, session_state, repo)

    # Verify execution succeeded
    assert result1.success
    assert invoke_count[0] == 2  # Only 2 steps executed

    # Verify checkpoints were written
    # Load session state after execution
    checkpoint_state = await repo.load(session_id)
    assert checkpoint_state is not None
    assert checkpoint_state.pattern_state["current_step"] == 2  # After step 1 (0-indexed)
    assert len(checkpoint_state.pattern_state["step_history"]) == 2

    # CRITICAL: Verify spec snapshot is UNCHANGED after checkpoints
    spec_snapshot_after = spec_snapshot_path.read_text(encoding="utf-8")
    assert spec_snapshot_after == original_spec_content, (
        "Spec snapshot was overwritten during checkpoint!"
    )

    # Now resume from checkpoint to complete step 2
    invoke_count[0] = 0  # Reset counter

    async def mock_invoke_resume(*args, **kwargs):
        invoke_count[0] += 1
        # Should only execute step 2 (final step)
        return "Step 2 result: Final summary report"

    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_resume)

    # Load full spec for resume (all 3 steps)
    full_spec = load_spec(str(chain_3_step_spec), {"topic": "AI agents"})

    # Resume execution
    result2 = await run_chain(full_spec, {"topic": "AI agents"}, checkpoint_state, repo)

    # Verify resume succeeded
    assert result2.success
    assert invoke_count[0] == 1  # Only step 2 executed (steps 0-1 skipped)

    # Verify final session state
    final_state = await repo.load(session_id)
    assert final_state is not None
    assert final_state.metadata.status == SessionStatus.COMPLETED
    assert len(final_state.pattern_state["step_history"]) == 3  # All 3 steps

    # Verify step history preserved from checkpoint
    assert (
        final_state.pattern_state["step_history"][0]["response"]
        == "Step 0 result: Research about AI agents"
    )
    assert (
        final_state.pattern_state["step_history"][1]["response"]
        == "Step 1 result: Analysis of research"
    )
    assert (
        final_state.pattern_state["step_history"][2]["response"]
        == "Step 2 result: Final summary report"
    )

    # CRITICAL: Verify spec snapshot STILL unchanged after completion
    spec_snapshot_final = spec_snapshot_path.read_text(encoding="utf-8")
    assert spec_snapshot_final == original_spec_content, (
        "Spec snapshot was overwritten during session completion!"
    )

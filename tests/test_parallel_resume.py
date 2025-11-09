"""Tests for parallel pattern resume functionality.

Tests verify:
- Session parameter validation
- Fresh execution with session checkpointing
- Resume after all branches (before reduce)
- Resume with partial branch completion
- Resume with reduce already executed
- Token accumulation across resume
- Reduce gate (execute only once)
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from strands_cli.exec.parallel import run_parallel
from strands_cli.loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository


@pytest.fixture
def parallel_with_reduce_spec(tmp_path: Path) -> Path:
    """Create a 3-branch parallel spec with reduce for testing."""
    spec_content = (
        "version: 0\n"
        "name: parallel-resume-test\n"
        "runtime:\n"
        "  provider: ollama\n"
        "  host: http://localhost:11434\n"
        "  model_id: gpt-oss\n"
        "agents:\n"
        "  web:\n"
        "    prompt: Research from web\n"
        "  docs:\n"
        "    prompt: Research from docs\n"
        "  academic:\n"
        "    prompt: Research from academic\n"
        "  synthesizer:\n"
        "    prompt: Synthesize all findings\n"
        "pattern:\n"
        "  type: parallel\n"
        "  config:\n"
        "    branches:\n"
        "      - id: web\n"
        "        steps:\n"
        "          - agent: web\n"
        '            input: "Research web"\n'
        "      - id: docs\n"
        "        steps:\n"
        "          - agent: docs\n"
        '            input: "Research docs"\n'
        "      - id: academic\n"
        "        steps:\n"
        "          - agent: academic\n"
        '            input: "Research academic"\n'
        "    reduce:\n"
        "      agent: synthesizer\n"
        '      input: "Synthesize"\n'
    )
    spec_file = tmp_path / "parallel-test.yaml"
    spec_file.write_text(spec_content)
    return spec_file


@pytest.mark.asyncio
async def test_parallel_session_parameter_validation(parallel_with_reduce_spec: Path) -> None:
    """Test session parameter validation (both or neither)."""
    spec = load_spec(parallel_with_reduce_spec, {})

    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    with pytest.raises(ValueError, match="must both be provided"):
        await run_parallel(spec, {}, session_state=state, session_repo=None)


@pytest.mark.asyncio
async def test_parallel_fresh_execution_with_session(
    tmp_path: Path,
    parallel_with_reduce_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test fresh execution creates checkpoints."""
    spec = load_spec(parallel_with_reduce_spec, {})

    # Mock agent invocations
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Web result", "Docs result", "Academic result", "Synthesized"]

    # Create session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-parallel-fresh"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="parallel-test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute
    result = await run_parallel(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Synthesized"

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state.get("completed_branches", [])) == 3
    assert loaded.pattern_state.get("reduce_executed") is True

    # All branches + reduce should be invoked
    assert mock_invoke.call_count == 4


@pytest.mark.asyncio
async def test_parallel_resume_after_branches_before_reduce(
    tmp_path: Path,
    parallel_with_reduce_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume after all branches complete but before reduce."""
    spec = load_spec(parallel_with_reduce_spec, {})

    # Create session with all branches complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-parallel-resume-reduce"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="parallel-test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_branches": ["web", "docs", "academic"],
            "branch_results": {
                "web": {
                    "response": "Web result",
                    "status": "success",
                    "tokens_estimated": 1000,
                    "step_history": [{"index": 0, "agent": "web", "response": "Web result", "tokens_estimated": 1000}],
                },
                "docs": {
                    "response": "Docs result",
                    "status": "success",
                    "tokens_estimated": 1100,
                    "step_history": [{"index": 0, "agent": "docs", "response": "Docs result", "tokens_estimated": 1100}],
                },
                "academic": {
                    "response": "Academic result",
                    "status": "success",
                    "tokens_estimated": 1200,
                    "step_history": [
                        {"index": 0, "agent": "academic", "response": "Academic result", "tokens_estimated": 1200}
                    ],
                },
            },
            "reduce_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=1650, total_output_tokens=1650),
    )
    await repo.save(state, "")

    # Mock only reduce
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Synthesized"

    # Resume
    result = await run_parallel(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Synthesized"

    # Only reduce should be executed
    assert mock_invoke.call_count == 1

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert loaded.pattern_state["reduce_executed"] is True


@pytest.mark.asyncio
async def test_parallel_resume_with_partial_branches(
    tmp_path: Path,
    parallel_with_reduce_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume when only some branches are complete."""
    spec = load_spec(parallel_with_reduce_spec, {})

    # Create session with 2 of 3 branches complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-parallel-partial"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="parallel-test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_branches": ["web", "docs"],
            "branch_results": {
                "web": {
                    "response": "Web result",
                    "status": "success",
                    "tokens_estimated": 1000,
                    "step_history": [{"index": 0, "agent": "web", "response": "Web result", "tokens_estimated": 1000}],
                },
                "docs": {
                    "response": "Docs result",
                    "status": "success",
                    "tokens_estimated": 1100,
                    "step_history": [{"index": 0, "agent": "docs", "response": "Docs result", "tokens_estimated": 1100}],
                },
            },
            "reduce_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=1050, total_output_tokens=1050),
    )
    await repo.save(state, "")

    # Mock academic + reduce
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Academic result", "Synthesized"]

    # Resume
    result = await run_parallel(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Synthesized"

    # Academic + reduce should be executed
    assert mock_invoke.call_count == 2

    # Verify all branches completed
    loaded = await repo.load(session_id)
    assert len(loaded.pattern_state["completed_branches"]) == 3
    assert loaded.pattern_state["reduce_executed"] is True


@pytest.mark.asyncio
async def test_parallel_resume_with_reduce_already_executed(
    tmp_path: Path,
    parallel_with_reduce_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume when reduce already executed (reduce gate)."""
    spec = load_spec(parallel_with_reduce_spec, {})

    # Create session with everything complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-parallel-reduce-done"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="parallel-test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_branches": ["web", "docs", "academic"],
            "branch_results": {
                "web": {"response": "Web result", "status": "success", "tokens_estimated": 1000, "step_history": []},
                "docs": {"response": "Docs result", "status": "success", "tokens_estimated": 1100, "step_history": []},
                "academic": {
                    "response": "Academic result",
                    "status": "success",
                    "tokens_estimated": 1200,
                    "step_history": [],
                },
            },
            "reduce_executed": True,
            "final_response": "Synthesized",
        },
        token_usage=TokenUsage(total_input_tokens=2000, total_output_tokens=2000),
    )
    await repo.save(state, "")

    # Mock agent (should not be called)
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )

    # Resume
    result = await run_parallel(spec, {}, state, repo)

    # Verify success with restored response
    assert result.success is True
    assert result.last_response == "Synthesized"

    # No agents should be invoked
    assert mock_invoke.call_count == 0

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_parallel_token_accumulation(
    tmp_path: Path,
    parallel_with_reduce_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test token usage accumulates correctly across resume."""
    spec = load_spec(parallel_with_reduce_spec, {})

    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-parallel-tokens"

    # Phase 1: 2 branches complete (2100 tokens)
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="parallel-test",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_branches": ["web", "docs"],
            "branch_results": {
                "web": {"response": "Web", "status": "success", "tokens_estimated": 1000, "step_history": []},
                "docs": {"response": "Docs", "status": "success", "tokens_estimated": 1100, "step_history": []},
            },
            "reduce_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=1050, total_output_tokens=1050),
    )
    await repo.save(state, "")

    # Mock academic (1200) + reduce (800)
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Academic", "Synthesized"]

    # Patch estimate_tokens
    mocker.patch("strands_cli.exec.parallel.estimate_tokens", side_effect=[1200, 800])

    # Resume
    result = await run_parallel(spec, {}, state, repo)

    assert result.success is True

    # Verify token accumulation: 2100 + 1200 + 800 = 4100
    loaded = await repo.load(session_id)
    total = loaded.token_usage.total_input_tokens + loaded.token_usage.total_output_tokens
    assert total == 4100


@pytest.mark.asyncio
async def test_parallel_without_reduce(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Test parallel without reduce step (aggregation)."""
    # Create spec without reduce
    spec_content = (
        "version: 0\n"
        "name: parallel-no-reduce\n"
        "runtime:\n"
        "  provider: ollama\n"
        "  host: http://localhost:11434\n"
        "  model_id: gpt-oss\n"
        "agents:\n"
        "  agent1:\n"
        "    prompt: Agent 1\n"
        "  agent2:\n"
        "    prompt: Agent 2\n"
        "pattern:\n"
        "  type: parallel\n"
        "  config:\n"
        "    branches:\n"
        "      - id: branch1\n"
        "        steps:\n"
        "          - agent: agent1\n"
        '            input: "Input 1"\n'
        "      - id: branch2\n"
        "        steps:\n"
        "          - agent: agent2\n"
        '            input: "Input 2"\n'
    )
    spec_file = tmp_path / "no-reduce.yaml"
    spec_file.write_text(spec_content)
    spec = load_spec(spec_file, {})

    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-no-reduce"

    # Session with both branches complete
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="no-reduce",
            spec_hash="hash",
            pattern_type="parallel",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "completed_branches": ["branch1", "branch2"],
            "branch_results": {
                "branch1": {"response": "Result 1", "status": "success", "tokens_estimated": 500, "step_history": []},
                "branch2": {"response": "Result 2", "status": "success", "tokens_estimated": 600, "step_history": []},
            },
            "reduce_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=550, total_output_tokens=550),
    )
    await repo.save(state, "")

    # Mock (should not be called)
    mock_invoke = mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )

    # Resume
    result = await run_parallel(spec, session_state=state, session_repo=repo)

    # Verify aggregated response
    assert result.success is True
    assert "Branch branch1" in result.last_response
    assert "Branch branch2" in result.last_response

    # No invocations
    assert mock_invoke.call_count == 0



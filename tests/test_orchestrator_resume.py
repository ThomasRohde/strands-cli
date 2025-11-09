"""Tests for orchestrator-workers pattern resume functionality.

Tests verify:
- Session parameter validation
- Fresh execution with session checkpointing
- Resume after workers (before reduce/writeup)
- Resume with reduce executed
- Resume with writeup executed
- Token accumulation across resume
- Reduce/writeup gates (execute only once)
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from strands_cli.exec.orchestrator_workers import run_orchestrator_workers
from strands_cli.loader import load_spec
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository


@pytest.fixture
def orchestrator_with_reduce_writeup_spec(tmp_path: Path) -> Path:
    """Create an orchestrator spec with reduce and writeup for testing."""
    spec_content = (
        "version: 0\n"
        "name: orchestrator-resume-test\n"
        "runtime:\n"
        "  provider: ollama\n"
        "  host: http://localhost:11434\n"
        "  model_id: gpt-oss\n"
        "agents:\n"
        "  planner:\n"
        "    prompt: Plan tasks\n"
        "  worker:\n"
        "    prompt: Execute task\n"
        "  reducer:\n"
        "    prompt: Reduce results\n"
        "  writer:\n"
        "    prompt: Write final report\n"
        "pattern:\n"
        "  type: orchestrator_workers\n"
        "  config:\n"
        "    orchestrator:\n"
        "      agent: planner\n"
        "      limits:\n"
        "        max_workers: 3\n"
        "        max_rounds: 1\n"
        "    worker_template:\n"
        "      agent: worker\n"
        "    reduce:\n"
        "      agent: reducer\n"
        "    writeup:\n"
        "      agent: writer\n"
    )
    spec_file = tmp_path / "orchestrator-test.yaml"
    spec_file.write_text(spec_content)
    return spec_file


@pytest.mark.asyncio
async def test_orchestrator_session_parameter_validation(orchestrator_with_reduce_writeup_spec: Path) -> None:
    """Test session parameter validation (both or neither)."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    state = SessionState(
        metadata=SessionMetadata(
            session_id="test",
            workflow_name="test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
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
        await run_orchestrator_workers(spec, {}, session_state=state, session_repo=None)


@pytest.mark.asyncio
async def test_orchestrator_fresh_execution_with_session(
    tmp_path: Path,
    orchestrator_with_reduce_writeup_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test fresh execution creates checkpoints."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    # Mock orchestrator to return 2 tasks
    mock_orchestrator = mocker.patch(
        "strands_cli.exec.orchestrator_workers._invoke_orchestrator_with_retry",
        new_callable=AsyncMock,
    )
    mock_orchestrator.return_value = ([{"task": "Task 1"}, {"task": "Task 2"}], 500)

    # Mock workers
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Worker 1 result", "Worker 2 result", "Reduced", "Final report"]

    # Patch token estimation
    mocker.patch("strands_cli.exec.orchestrator_workers.estimate_tokens", return_value=100)

    # Create session
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-orchestrator-fresh"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="orchestrator-test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
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
    result = await run_orchestrator_workers(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Final report"

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert loaded.pattern_state.get("workers_executed") is True
    assert loaded.pattern_state.get("reduce_executed") is True
    assert loaded.pattern_state.get("writeup_executed") is True

    # Orchestrator + 2 workers + reduce + writeup
    assert mock_orchestrator.call_count == 1
    assert mock_invoke.call_count == 4


@pytest.mark.asyncio
async def test_orchestrator_resume_after_workers_before_reduce(
    tmp_path: Path,
    orchestrator_with_reduce_writeup_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume after workers complete but before reduce."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    # Create session with workers complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-orchestrator-resume-reduce"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="orchestrator-test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "workers_executed": True,
            "worker_results": [
                {"response": "Worker 1 result", "status": "success", "tokens": 600, "task": "Task 1"},
                {"response": "Worker 2 result", "status": "success", "tokens": 700, "task": "Task 2"},
            ],
            "reduce_executed": False,
            "writeup_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=650, total_output_tokens=650),
    )
    await repo.save(state, "")

    # Mock only reduce and writeup
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Reduced", "Final report"]

    # Patch token estimation
    mocker.patch("strands_cli.exec.orchestrator_workers.estimate_tokens", return_value=100)

    # Resume
    result = await run_orchestrator_workers(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Final report"

    # Only reduce + writeup should be executed
    assert mock_invoke.call_count == 2

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert loaded.pattern_state["reduce_executed"] is True
    assert loaded.pattern_state["writeup_executed"] is True


@pytest.mark.asyncio
async def test_orchestrator_resume_with_reduce_executed(
    tmp_path: Path,
    orchestrator_with_reduce_writeup_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume when reduce already executed (reduce gate)."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    # Create session with reduce complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-orchestrator-reduce-done"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="orchestrator-test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "workers_executed": True,
            "worker_results": [
                {"response": "Worker 1", "status": "success", "tokens": 600, "task": "Task 1"},
                {"response": "Worker 2", "status": "success", "tokens": 700, "task": "Task 2"},
            ],
            "reduce_executed": True,
            "reduce_response": "Reduced",
            "writeup_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=1000, total_output_tokens=1000),
    )
    await repo.save(state, "")

    # Mock only writeup
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = "Final report"

    # Patch token estimation
    mocker.patch("strands_cli.exec.orchestrator_workers.estimate_tokens", return_value=100)

    # Resume
    result = await run_orchestrator_workers(spec, {}, state, repo)

    # Verify success
    assert result.success is True
    assert result.last_response == "Final report"

    # Only writeup should be executed
    assert mock_invoke.call_count == 1

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert loaded.pattern_state["writeup_executed"] is True


@pytest.mark.asyncio
async def test_orchestrator_resume_with_all_executed(
    tmp_path: Path,
    orchestrator_with_reduce_writeup_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test resume when everything already executed (writeup gate)."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    # Create session with everything complete
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-orchestrator-all-done"
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="orchestrator-test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "workers_executed": True,
            "worker_results": [
                {"response": "Worker 1", "status": "success", "tokens": 600, "task": "Task 1"},
            ],
            "reduce_executed": True,
            "reduce_response": "Reduced",
            "writeup_executed": True,
            "writeup_response": "Final report",
        },
        token_usage=TokenUsage(total_input_tokens=1200, total_output_tokens=1200),
    )
    await repo.save(state, "")

    # Mock (should not be called)
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )

    # Resume
    result = await run_orchestrator_workers(spec, {}, state, repo)

    # Verify success with restored response
    assert result.success is True
    assert result.last_response == "Final report"

    # No agents should be invoked
    assert mock_invoke.call_count == 0

    # Verify session completed
    loaded = await repo.load(session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_orchestrator_token_accumulation(
    tmp_path: Path,
    orchestrator_with_reduce_writeup_spec: Path,
    mocker: MockerFixture,
) -> None:
    """Test token usage accumulates correctly across resume."""
    spec = load_spec(orchestrator_with_reduce_writeup_spec, {})

    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-orchestrator-tokens"

    # Phase 1: workers complete (1300 tokens)
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="orchestrator-test",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "workers_executed": True,
            "worker_results": [
                {"response": "Worker 1", "status": "success", "tokens": 600, "task": "Task 1"},
                {"response": "Worker 2", "status": "success", "tokens": 700, "task": "Task 2"},
            ],
            "reduce_executed": False,
            "writeup_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=650, total_output_tokens=650),
    )
    await repo.save(state, "")

    # Mock reduce (400) + writeup (500)
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.side_effect = ["Reduced", "Final"]

    # Patch estimate_tokens
    mocker.patch("strands_cli.exec.orchestrator_workers.estimate_tokens", side_effect=[400, 500])

    # Resume
    result = await run_orchestrator_workers(spec, {}, state, repo)

    assert result.success is True

    # Verify token accumulation: 1300 + 400 + 500 = 2200
    loaded = await repo.load(session_id)
    total = loaded.token_usage.total_input_tokens + loaded.token_usage.total_output_tokens
    assert total == 2200


@pytest.mark.asyncio
async def test_orchestrator_without_reduce_writeup(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Test orchestrator without reduce/writeup (aggregation)."""
    # Create spec without reduce/writeup
    spec_content = (
        "version: 0\n"
        "name: orchestrator-minimal\n"
        "runtime:\n"
        "  provider: ollama\n"
        "  host: http://localhost:11434\n"
        "  model_id: gpt-oss\n"
        "agents:\n"
        "  planner:\n"
        "    prompt: Plan\n"
        "  worker:\n"
        "    prompt: Work\n"
        "pattern:\n"
        "  type: orchestrator_workers\n"
        "  config:\n"
        "    orchestrator:\n"
        "      agent: planner\n"
        "      limits:\n"
        "        max_rounds: 1\n"
        "    worker_template:\n"
        "      agent: worker\n"
    )
    spec_file = tmp_path / "minimal-orchestrator.yaml"
    spec_file.write_text(spec_content)
    spec = load_spec(spec_file, {})

    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = "test-minimal"

    # Session with workers complete
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="minimal",
            spec_hash="hash",
            pattern_type="orchestrator-workers",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z",
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "workers_executed": True,
            "worker_results": [
                {"response": "Result 1", "status": "success", "tokens": 500, "task": "Task 1"},
                {"response": "Result 2", "status": "success", "tokens": 600, "task": "Task 2"},
            ],
            "reduce_executed": False,
            "writeup_executed": False,
        },
        token_usage=TokenUsage(total_input_tokens=550, total_output_tokens=550),
    )
    await repo.save(state, "")

    # Mock (should not be called)
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )

    # Resume
    result = await run_orchestrator_workers(spec, session_state=state, session_repo=repo)

    # Verify aggregated response
    assert result.success is True
    assert "Worker 0" in result.last_response
    assert "Worker 1" in result.last_response

    # No invocations
    assert mock_invoke.call_count == 0

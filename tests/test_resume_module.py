"""Unit tests for session resume module.

Tests the core resume.py functions that load and validate sessions
and dispatch to pattern executors.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.session import (
    SessionAlreadyCompletedError,
    SessionMetadata,
    SessionNotFoundError,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.resume import (
    _dispatch_pattern_executor,
    _load_and_validate_session,
    _load_spec_from_snapshot,
    run_resume,
)
from strands_cli.types import PatternType, RunResult


def _create_session_state(
    session_id: str = "test-123",
    workflow_name: str = "test-workflow",
    pattern_type: str = "chain",
    status: SessionStatus = SessionStatus.RUNNING,
) -> SessionState:
    """Helper to create valid SessionState with required fields."""
    return SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=workflow_name,
            pattern_type=pattern_type,
            status=status,
            spec_hash="abc123",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )


def _create_run_result(
    success: bool = True,
    response: str = "test",
    pattern_type: PatternType = PatternType.CHAIN,
    variables: dict[str, Any] | None = None,
) -> RunResult:
    """Helper to create valid RunResult with required fields."""
    now = datetime.now().isoformat()
    return RunResult(
        success=success,
        response=response,
        pattern_type=pattern_type,
        agent_id="test_agent",
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        variables=variables,
    )


@pytest.mark.asyncio
async def test_load_and_validate_session_success(mocker: Any) -> None:
    """Test loading and validating a valid session."""
    mock_repo = mocker.Mock(spec=FileSessionRepository)
    session_state = _create_session_state()
    mock_repo.load = AsyncMock(return_value=session_state)

    result = await _load_and_validate_session("test-123", mock_repo, verbose=False)

    assert result == session_state
    mock_repo.load.assert_awaited_once_with("test-123")


@pytest.mark.asyncio
async def test_load_and_validate_session_not_found(mocker: Any) -> None:
    """Test loading a session that doesn't exist."""
    mock_repo = mocker.Mock(spec=FileSessionRepository)
    mock_repo.load = AsyncMock(return_value=None)

    with pytest.raises(SessionNotFoundError, match="Session 'test-123' not found"):
        await _load_and_validate_session("test-123", mock_repo, verbose=False)


@pytest.mark.asyncio
async def test_load_and_validate_session_already_completed(mocker: Any) -> None:
    """Test loading a completed session."""
    mock_repo = mocker.Mock(spec=FileSessionRepository)
    session_state = _create_session_state(status=SessionStatus.COMPLETED)
    mock_repo.load = AsyncMock(return_value=session_state)

    with pytest.raises(SessionAlreadyCompletedError, match="already completed"):
        await _load_and_validate_session("test-123", mock_repo, verbose=False)


@pytest.mark.asyncio
async def test_load_and_validate_session_verbose(mocker: Any, capsys: Any) -> None:
    """Test verbose output when loading session."""
    mock_repo = mocker.Mock(spec=FileSessionRepository)
    session_state = _create_session_state()
    mock_repo.load = AsyncMock(return_value=session_state)

    # Mock console to avoid actual output
    mocker.patch("strands_cli.session.resume.console")

    await _load_and_validate_session("test-123", mock_repo, verbose=True)

    # Session was loaded successfully
    mock_repo.load.assert_awaited_once()


def test_load_spec_from_snapshot_success(tmp_path: Path, mocker: Any) -> None:
    """Test loading spec from snapshot file."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text(
        """version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: gpt-oss
  host: http://localhost:11434
agents:
  main:
    prompt: Test
pattern:
  type: chain
  config:
    steps:
      - agent: main
        input: test
outputs:
  artifacts:
    - path: ./output.txt
      from: '{{ last_response }}'
"""
    )

    mock_repo = mocker.Mock(spec=FileSessionRepository)
    mock_repo._session_dir = MagicMock(return_value=session_dir)

    session_state = _create_session_state()

    # Mock load_spec
    mock_spec = mocker.Mock()
    mock_spec.name = "test-workflow"
    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)

    # Mock compute_spec_hash
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="abc123")

    result = _load_spec_from_snapshot("test-123", mock_repo, session_state)

    assert result == mock_spec


def test_load_spec_from_snapshot_not_found(tmp_path: Path, mocker: Any) -> None:
    """Test loading spec when snapshot doesn't exist."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    mock_repo = mocker.Mock(spec=FileSessionRepository)
    mock_repo._session_dir = MagicMock(return_value=session_dir)

    session_state = _create_session_state()

    with pytest.raises(SessionNotFoundError, match="Spec snapshot not found"):
        _load_spec_from_snapshot("test-123", mock_repo, session_state)


def test_load_spec_from_snapshot_hash_mismatch(tmp_path: Path, mocker: Any) -> None:
    """Test loading spec when hash doesn't match (should warn but continue)."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text("version: 0\nname: test\n")

    mock_repo = mocker.Mock(spec=FileSessionRepository)
    mock_repo._session_dir = MagicMock(return_value=session_dir)

    session_state = _create_session_state()
    session_state.metadata.spec_hash = "original_hash"

    mock_spec = mocker.Mock()
    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="different_hash")

    # Mock logger and console to verify warning
    mock_logger = mocker.patch("strands_cli.session.resume.logger")
    mocker.patch("strands_cli.session.resume.console")

    result = _load_spec_from_snapshot("test-123", mock_repo, session_state)

    # Should still return spec despite hash mismatch
    assert result == mock_spec
    # Should have logged warning
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_chain(mocker: Any) -> None:
    """Test dispatching to chain executor."""

    mock_run_chain = mocker.patch(
        "strands_cli.exec.chain.run_chain", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_chain.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.CHAIN, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_chain.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_workflow(mocker: Any) -> None:
    """Test dispatching to workflow executor."""
    mock_run_workflow = mocker.patch(
        "strands_cli.exec.workflow.run_workflow", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_workflow.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.WORKFLOW, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_routing(mocker: Any) -> None:
    """Test dispatching to routing executor."""
    mock_run_routing = mocker.patch(
        "strands_cli.exec.routing.run_routing", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_routing.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.ROUTING, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_routing.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_parallel(mocker: Any) -> None:
    """Test dispatching to parallel executor."""
    mock_run_parallel = mocker.patch(
        "strands_cli.exec.parallel.run_parallel", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_parallel.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.PARALLEL, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_parallel.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_evaluator_optimizer(mocker: Any) -> None:
    """Test dispatching to evaluator-optimizer executor."""
    mock_run_eo = mocker.patch(
        "strands_cli.exec.evaluator_optimizer.run_evaluator_optimizer",
        new_callable=AsyncMock,
    )
    mock_result = _create_run_result()
    mock_run_eo.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.EVALUATOR_OPTIMIZER, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_eo.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_orchestrator_workers(mocker: Any) -> None:
    """Test dispatching to orchestrator-workers executor."""
    mock_run_ow = mocker.patch(
        "strands_cli.exec.orchestrator_workers.run_orchestrator_workers",
        new_callable=AsyncMock,
    )
    mock_result = _create_run_result()
    mock_run_ow.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.ORCHESTRATOR_WORKERS, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_ow.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_graph(mocker: Any) -> None:
    """Test dispatching to graph executor."""
    mock_run_graph = mocker.patch(
        "strands_cli.exec.graph.run_graph", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_graph.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.GRAPH, mock_spec, {}, mock_session_state, mock_repo, None
    )

    assert result == mock_result
    mock_run_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pattern_executor_with_hitl_response(mocker: Any) -> None:
    """Test dispatching with HITL response passes it through."""
    mock_run_chain = mocker.patch(
        "strands_cli.exec.chain.run_chain", new_callable=AsyncMock
    )
    mock_result = _create_run_result()
    mock_run_chain.return_value = mock_result

    mock_spec = mocker.Mock()
    mock_session_state = mocker.Mock()
    mock_repo = mocker.Mock()

    result = await _dispatch_pattern_executor(
        PatternType.CHAIN,
        mock_spec,
        {},
        mock_session_state,
        mock_repo,
        hitl_response="approved",
    )

    assert result == mock_result
    # Verify hitl_response was passed
    call_args = mock_run_chain.call_args
    assert call_args[0][4] == "approved"


@pytest.mark.asyncio
async def test_run_resume_success(tmp_path: Path, mocker: Any) -> None:
    """Test successful resume flow."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text(
        """version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: gpt-oss
  host: http://localhost:11434
agents:
  main:
    prompt: Test
pattern:
  type: chain
  config:
    steps:
      - agent: main
        input: test
outputs:
  artifacts:
    - path: ./output.txt
      from: '{{ last_response }}'
"""
    )

    # Mock FileSessionRepository
    mock_repo_class = mocker.patch("strands_cli.session.resume.FileSessionRepository")
    mock_repo_instance = mocker.Mock()
    mock_repo_class.return_value = mock_repo_instance

    session_state = _create_session_state()
    session_state.variables = {"key": "value"}

    mock_repo_instance.load = AsyncMock(return_value=session_state)
    mock_repo_instance._session_dir = MagicMock(return_value=session_dir)

    # Mock load_spec
    mock_spec = mocker.Mock()
    mock_spec.name = "test-workflow"
    mock_spec.telemetry = None
    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)

    # Mock compute_spec_hash
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="abc123")

    # Mock executor
    mock_result = _create_run_result(variables={})
    mock_run_chain = mocker.patch(
        "strands_cli.exec.chain.run_chain", new_callable=AsyncMock
    )
    mock_run_chain.return_value = mock_result

    # Mock console
    mocker.patch("strands_cli.session.resume.console")

    result = await run_resume("test-123", debug=False, verbose=False, trace=False)

    assert result.success is True
    assert result.spec == mock_spec
    assert result.variables == {"key": "value"}


@pytest.mark.asyncio
async def test_run_resume_with_hitl_response(tmp_path: Path, mocker: Any) -> None:
    """Test resume with HITL response."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text("version: 0\nname: test\n")

    mock_repo_class = mocker.patch("strands_cli.session.resume.FileSessionRepository")
    mock_repo_instance = mocker.Mock()
    mock_repo_class.return_value = mock_repo_instance

    session_state = _create_session_state()

    mock_repo_instance.load = AsyncMock(return_value=session_state)
    mock_repo_instance._session_dir = MagicMock(return_value=session_dir)

    mock_spec = mocker.Mock()
    mock_spec.name = "test-workflow"
    mock_spec.telemetry = None
    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="abc123")

    mock_result = _create_run_result(variables={})
    mock_run_chain = mocker.patch(
        "strands_cli.exec.chain.run_chain", new_callable=AsyncMock
    )
    mock_run_chain.return_value = mock_result

    mocker.patch("strands_cli.session.resume.console")

    result = await run_resume("test-123", hitl_response="approved")

    assert result.success is True
    # Verify HITL response was passed to executor
    call_args = mock_run_chain.call_args
    assert call_args[0][4] == "approved"


@pytest.mark.asyncio
async def test_run_resume_merges_variables(tmp_path: Path, mocker: Any) -> None:
    """Test resume merges session and result variables correctly."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text("version: 0\nname: test\n")

    mock_repo_class = mocker.patch("strands_cli.session.resume.FileSessionRepository")
    mock_repo_instance = mocker.Mock()
    mock_repo_class.return_value = mock_repo_instance

    session_state = _create_session_state()
    session_state.variables = {"session_key": "session_value", "shared": "from_session"}

    mock_repo_instance.load = AsyncMock(return_value=session_state)
    mock_repo_instance._session_dir = MagicMock(return_value=session_dir)

    mock_spec = mocker.Mock()
    mock_spec.name = "test-workflow"
    mock_spec.telemetry = None
    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="abc123")

    # Result has different variables (should merge with precedence)
    mock_result = _create_run_result(variables={"result_key": "result_value", "shared": "from_result"})
    mock_run_chain = mocker.patch(
        "strands_cli.exec.chain.run_chain", new_callable=AsyncMock
    )
    mock_run_chain.return_value = mock_result

    mocker.patch("strands_cli.session.resume.console")

    result = await run_resume("test-123")

    # Should merge with result taking precedence
    assert result.variables == {
        "session_key": "session_value",
        "result_key": "result_value",
        "shared": "from_result",
    }


@pytest.mark.asyncio
async def test_run_resume_with_telemetry(tmp_path: Path, mocker: Any) -> None:
    """Test resume configures telemetry if specified in spec."""
    session_dir = tmp_path / "sessions" / "test-123"
    session_dir.mkdir(parents=True)

    spec_snapshot = session_dir / "spec_snapshot.yaml"
    spec_snapshot.write_text("version: 0\nname: test\n")

    mock_repo_class = mocker.patch("strands_cli.session.resume.FileSessionRepository")
    mock_repo_instance = mocker.Mock()
    mock_repo_class.return_value = mock_repo_instance

    session_state = _create_session_state()

    mock_repo_instance.load = AsyncMock(return_value=session_state)
    mock_repo_instance._session_dir = MagicMock(return_value=session_dir)

    # Spec with telemetry
    mock_spec = mocker.Mock()
    mock_spec.name = "test-workflow"
    mock_telemetry = mocker.Mock()
    mock_telemetry.model_dump.return_value = {"enabled": True}
    mock_spec.telemetry = mock_telemetry

    mocker.patch("strands_cli.session.resume.load_spec", return_value=mock_spec)
    mocker.patch("strands_cli.session.resume.compute_spec_hash", return_value="abc123")

    # Mock configure_telemetry
    mock_configure = mocker.patch("strands_cli.session.resume.configure_telemetry")

    mock_result = _create_run_result(variables={})
    mocker.patch(
        "strands_cli.exec.chain.run_chain",
        new_callable=AsyncMock,
        return_value=mock_result,
    )

    mocker.patch("strands_cli.session.resume.console")

    await run_resume("test-123")

    # Should have configured telemetry
    mock_configure.assert_called_once_with({"enabled": True})


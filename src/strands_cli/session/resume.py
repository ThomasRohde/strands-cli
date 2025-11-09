"""Resume workflow execution from saved session.

Phase 2 Implementation:
Provides resume logic for chain pattern with agent session restoration
via Strands SDK FileSessionManager. Extended in Phase 3 for multi-pattern
support (workflow, parallel, routing, graph, etc.).

Functions:
    run_resume: Main resume entry point called from CLI

Phase 2 Features:
    - Load session from FileSessionRepository
    - Validate session state (not completed, spec hash check)
    - Load spec from snapshot
    - Restore agent conversation history
    - Resume execution from last checkpoint

Phase 3 Extensions:
    - Pattern-specific resume handlers for all 7 patterns
    - DAG dependency restoration for workflow pattern
    - Branch completion tracking for parallel pattern
    - Node history restoration for graph pattern
"""

from typing import Any

import structlog
from rich.console import Console

from strands_cli.loader import load_spec
from strands_cli.session import (
    SessionAlreadyCompletedError,
    SessionNotFoundError,
    SessionState,
    SessionStatus,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import compute_spec_hash
from strands_cli.telemetry import configure_telemetry
from strands_cli.types import PatternType, RunResult, Spec

logger = structlog.get_logger(__name__)
console = Console()


async def _load_and_validate_session(
    session_id: str, repo: FileSessionRepository, verbose: bool
) -> SessionState:
    """Load session and validate it can be resumed.

    Args:
        session_id: Session ID to load
        repo: Session repository
        verbose: Enable verbose output

    Returns:
        Validated session state

    Raises:
        SessionNotFoundError: If session doesn't exist
        SessionAlreadyCompletedError: If session already completed
    """
    state = await repo.load(session_id)

    if not state:
        raise SessionNotFoundError(f"Session '{session_id}' not found")

    if state.metadata.status == SessionStatus.COMPLETED:
        raise SessionAlreadyCompletedError(
            f"Session '{session_id}' already completed. Cannot resume."
        )

    if verbose:
        console.print(f"[dim]Session status: {state.metadata.status.value}[/dim]")
        console.print(f"[dim]Workflow: {state.metadata.workflow_name}[/dim]")
        console.print(f"[dim]Pattern: {state.metadata.pattern_type}[/dim]")

    return state


def _load_spec_from_snapshot(
    session_id: str, repo: FileSessionRepository, state: SessionState
) -> Spec:
    """Load spec from snapshot and validate hash.

    Args:
        session_id: Session ID
        repo: Session repository
        state: Session state with variables

    Returns:
        Loaded spec

    Raises:
        SessionNotFoundError: If snapshot file not found
    """
    session_dir = repo._session_dir(session_id)
    spec_snapshot_path = session_dir / "spec_snapshot.yaml"

    if not spec_snapshot_path.exists():
        raise SessionNotFoundError(
            f"Spec snapshot not found for session '{session_id}' at {spec_snapshot_path}"
        )

    spec = load_spec(str(spec_snapshot_path), state.variables)

    # Validate spec hash (warn if changed)
    current_hash = compute_spec_hash(spec_snapshot_path)
    if current_hash != state.metadata.spec_hash:
        logger.warning(
            "spec_changed",
            session_id=session_id,
            original=state.metadata.spec_hash[:8],
            current=current_hash[:8],
        )
        console.print(
            "[yellow]⚠ Warning:[/yellow] Spec file has changed since session creation. "
            "Resume may behave unexpectedly."
        )

    return spec


async def _dispatch_pattern_executor(
    pattern_type: PatternType,
    spec: Spec,
    variables: dict[str, Any],
    session_state: SessionState,
    session_repo: FileSessionRepository,
) -> RunResult:
    """Dispatch to pattern-specific executor with session resume support.

    Args:
        pattern_type: Pattern type to execute
        spec: Workflow spec
        variables: User variables
        session_state: Session state for resume
        session_repo: Session repository for checkpointing

    Returns:
        RunResult from executor

    Raises:
        NotImplementedError: If pattern doesn't support resume yet

    Phase 3.2 Implementation:
        - Chain: ✅ Phase 2 complete
        - Routing: ✅ Phase 3.1 complete
        - Workflow: ✅ Phase 3.1 complete
        - Parallel: ✅ Phase 3.2 complete
        - Orchestrator-Workers: ✅ Phase 3.2 complete
        - Evaluator-Optimizer: ✅ Phase 3.3 complete
        - Graph: ✅ Phase 3.3 complete
    """
    # Import executors on-demand to avoid circular imports
    if pattern_type == PatternType.CHAIN:
        from strands_cli.exec.chain import run_chain

        return await run_chain(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.ROUTING:
        from strands_cli.exec.routing import run_routing

        return await run_routing(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.WORKFLOW:
        from strands_cli.exec.workflow import run_workflow

        return await run_workflow(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.PARALLEL:
        from strands_cli.exec.parallel import run_parallel

        return await run_parallel(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.EVALUATOR_OPTIMIZER:
        from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer

        return await run_evaluator_optimizer(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.ORCHESTRATOR_WORKERS:
        from strands_cli.exec.orchestrator_workers import run_orchestrator_workers

        return await run_orchestrator_workers(spec, variables, session_state, session_repo)

    elif pattern_type == PatternType.GRAPH:
        from strands_cli.exec.graph import run_graph

        return await run_graph(spec, variables, session_state, session_repo)

    else:
        raise NotImplementedError(
            f"Resume not yet supported for pattern '{pattern_type}'. "
            "Only chain, routing, and workflow patterns are supported."
        )


async def run_resume(
    session_id: str,
    debug: bool = False,
    verbose: bool = False,
    trace: bool = False,
) -> RunResult:
    """Resume workflow execution from saved session.

    Phase 2 Implementation:
    Loads session state, validates resumability, loads spec from snapshot,
    and dispatches to pattern-specific executor with resume state.

    Args:
        session_id: Session ID to resume
        debug: Enable debug logging
        verbose: Enable verbose output
        trace: Enable trace export

    Returns:
        RunResult from resumed execution with spec and variables attached

    Raises:
        SessionNotFoundError: If session ID doesn't exist
        SessionAlreadyCompletedError: If session already finished
        ValueError: If spec hash mismatch or other validation failure

    Example:
        >>> # From CLI: strands run --resume abc-123
        >>> result = await run_resume("abc-123", debug=True)
        >>> if result.success:
        ...     print("Resume successful")

    Phase 2 Implementation:
        - ✅ Load session from FileSessionRepository
        - ✅ Validate session state (check status != COMPLETED)
        - ✅ Load spec from spec_snapshot.yaml
        - ✅ Validate spec hash (warn if changed)
        - ✅ Dispatch to pattern-specific executor (run_chain, etc.)
        - 🔄 Pass session_state and session_repo for checkpointing (Task 2.2)

    Phase 3 TODO:
        - Add pattern-specific resume handlers for all 7 patterns
        - Implement DAG dependency restoration for workflow
        - Implement branch completion tracking for parallel
        - Implement node history restoration for graph
    """
    logger.info("resume_requested", session_id=session_id)

    if verbose:
        console.print(f"[dim]Loading session: {session_id}[/dim]")

    # Load and validate session
    repo = FileSessionRepository()
    state = await _load_and_validate_session(session_id, repo, verbose)

    # Load spec from snapshot and validate hash
    spec = _load_spec_from_snapshot(session_id, repo, state)

    # Configure telemetry if specified
    if spec.telemetry:
        configure_telemetry(spec.telemetry.model_dump() if spec.telemetry else None)

    # Show resume info
    if verbose:
        console.print(f"[bold green]Resuming workflow:[/bold green] {spec.name}")
        console.print(f"[dim]Pattern: {state.metadata.pattern_type}[/dim]")

    # Dispatch to pattern executor
    pattern_type = PatternType(state.metadata.pattern_type)
    result = await _dispatch_pattern_executor(pattern_type, spec, state.variables, state, repo)

    # Attach spec and variables to result for artifact writing
    result.spec = spec
    result.variables = state.variables

    return result

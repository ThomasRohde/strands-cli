"""Multi-task workflow executor with DAG support.

Executes workflows with task dependencies using topological sort.
Tasks execute in dependency order with parallel execution where possible.

Execution Flow:
    1. Validate workflow configuration (at least 1 task, no cycles)
    2. Build task dependency graph and topological sort
    3. Execute tasks in layers (parallel where deps allow):
        a. Build template context (completed task responses + user variables)
        b. Render task input with Jinja2
        c. Build agent for task
        d. Execute agent asynchronously
        e. Track token budget and warn at 80% threshold
        f. Capture task response and timing
    4. Return RunResult with final task response (or aggregated result)

Dependency Resolution:
    - Topological sort ensures tasks run after all dependencies complete
    - Parallel execution within each dependency layer (respecting max_parallel)
    - Fail-fast: Stop on first task failure

Context Threading:
    - {{ tasks.<id>.response }} - Access completed task outputs
    - {{ tasks.<id>.status }} - Task completion status (success/failed)
"""

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from rich.console import Console
from rich.panel import Panel

from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState, SessionStatus, TokenUsage
from strands_cli.session.checkpoint_utils import (
    checkpoint_pattern_state,
    fail_session,
    finalize_session,
    get_cumulative_tokens,
    validate_session_params,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.telemetry import get_tracer
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import HITLState, PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


logger = structlog.get_logger(__name__)
console = Console()


def _topological_sort(tasks: list[Any]) -> list[list[str]]:
    """Perform topological sort on tasks to determine execution order.

    Uses Kahn's algorithm to build layers of tasks that can execute in parallel.
    Each layer contains tasks whose dependencies have all been satisfied.

    Args:
        tasks: List of WorkflowTask objects with id and deps fields

    Returns:
        List of task ID layers: [[layer0_ids...], [layer1_ids...], ...]
        Each layer can execute in parallel.

    Raises:
        WorkflowExecutionError: If cycle detected (should be caught earlier by capability checker)
    """
    # Build adjacency list and in-degree count
    task_map = {task.id: task for task in tasks}
    in_degree = {task.id: 0 for task in tasks}
    adj_list: dict[str, list[str]] = {task.id: [] for task in tasks}

    # Calculate in-degrees
    for task in tasks:
        if task.deps:
            for dep_id in task.deps:
                if dep_id not in task_map:
                    raise WorkflowExecutionError(
                        f"Task '{task.id}' depends on non-existent task '{dep_id}'"
                    )
                adj_list[dep_id].append(task.id)
                in_degree[task.id] += 1

    # Build execution layers
    layers = []
    queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])

    while queue:
        # Current layer: all tasks with in-degree 0
        layer_size = len(queue)
        current_layer = []

        for _ in range(layer_size):
            task_id = queue.popleft()
            current_layer.append(task_id)

            # Reduce in-degree for neighbors
            for neighbor in adj_list[task_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        layers.append(current_layer)

    # Verify all tasks processed (cycle check)
    total_processed = sum(len(layer) for layer in layers)
    if total_processed < len(tasks):
        raise WorkflowExecutionError("Cycle detected in task dependencies")

    return layers


def _build_task_context(
    spec: Spec,
    task_results: dict[str, dict[str, Any]],
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build template context for a task.

    Args:
        spec: Workflow spec
        task_results: Map of task_id -> {response, status, type, ...}
        variables: User-provided variables from --var flags

    Returns:
        Template context dictionary with tasks{}, user variables, hitl_response
    """
    context = {}

    # Add user-provided variables from spec.inputs.values
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])

    # Override with CLI --var variables
    if variables:
        context.update(variables)

    # Add task results as tasks{} dictionary
    context["tasks"] = task_results

    # Add hitl_response convenience variable (most recent HITL task response)
    # Walk task_results to find most recent HITL task
    for task_id, result in task_results.items():
        if result.get("type") == "hitl":
            context["hitl_response"] = result.get("response", "")
            # Continue walking to find the LAST hitl task (most recent)

    return context


def _check_layer_for_hitl(
    layer_task_ids: list[str],
    task_map: dict[str, Any],
    completed_tasks: set[str],
) -> str | None:
    """Check if layer contains a HITL task that hasn't been completed.

    MVP constraint: Only one HITL task allowed per layer.

    Args:
        layer_task_ids: Task IDs in this layer
        task_map: Map of task ID to task object
        completed_tasks: Set of already completed task IDs

    Returns:
        Task ID of first HITL task found, or None if no HITL tasks

    Raises:
        WorkflowExecutionError: If multiple HITL tasks found in same layer (MVP constraint)
    """
    hitl_tasks = []
    for task_id in layer_task_ids:
        if task_id in completed_tasks:
            continue  # Skip completed tasks
        task = task_map[task_id]
        if hasattr(task, "type") and task.type == "hitl":
            hitl_tasks.append(task_id)

    if len(hitl_tasks) > 1:
        raise WorkflowExecutionError(
            f"Multiple HITL tasks found in same execution layer (MVP constraint): {hitl_tasks}. "
            "Please restructure workflow so HITL tasks are in separate layers using dependencies."
        )

    return hitl_tasks[0] if hitl_tasks else None


async def _execute_hitl_pause(
    spec: Spec,
    task_id: str,
    hitl_task: Any,
    task_results: dict[str, dict[str, Any]],
    variables: dict[str, str] | None,
    session_state: SessionState,
    session_repo: FileSessionRepository,
    layer_index: int,
    completed_tasks: set[str],
) -> RunResult:
    """Execute HITL pause logic and save session.

    Args:
        spec: Workflow spec
        task_id: ID of the HITL task
        hitl_task: HITL task object
        task_results: Existing task results
        variables: User variables
        session_state: Session state to update
        session_repo: Repository for saving session
        layer_index: Current execution layer index
        completed_tasks: Set of completed task IDs

    Returns:
        RunResult with EX_HITL_PAUSE exit code
    """
    # Build context for rendering context_display
    task_context = _build_task_context(spec, task_results, variables)

    # Render context_display template if provided
    context_text = ""
    if hitl_task.context_display:
        try:
            context_text = render_template(hitl_task.context_display, task_context)
        except Exception as e:
            logger.warning(
                "hitl_context_render_failed",
                task_id=task_id,
                error=str(e),
            )
            context_text = "(Context rendering failed)"

    # Calculate timeout if specified
    timeout_at = None
    if hitl_task.timeout_seconds and hitl_task.timeout_seconds > 0:
        timeout_dt = datetime.now(UTC) + timedelta(seconds=hitl_task.timeout_seconds)
        timeout_at = timeout_dt.isoformat()

    # Create HITL state
    hitl_state = HITLState(
        active=True,
        task_id=task_id,
        layer_index=layer_index,
        prompt=hitl_task.prompt,
        context_display=context_text,
        default_response=hitl_task.default,
        timeout_at=timeout_at,
        user_response=None,
        step_index=None,  # Not used in workflow pattern
    )

    # Save session with HITL state
    session_state.pattern_state["current_layer"] = layer_index
    session_state.pattern_state["task_results"] = task_results
    session_state.pattern_state["completed_tasks"] = list(completed_tasks)
    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
    session_state.metadata.status = SessionStatus.PAUSED
    session_state.metadata.updated_at = datetime.now(UTC).isoformat()

    await session_repo.save(session_state, "")

    logger.info(
        "hitl_pause_initiated",
        session_id=session_state.metadata.session_id,
        task_id=task_id,
        layer=layer_index,
    )

    # Display HITL prompt to user
    console.print()
    console.print(
        Panel(
            f"[bold yellow]🤝 HUMAN INPUT REQUIRED[/bold yellow]\\n\\n{hitl_task.prompt}",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    if context_text:
        console.print(
            Panel(
                f"[bold]Context for Review:[/bold]\\n\\n{context_text}",
                border_style="dim",
                padding=(1, 2),
            )
        )

    console.print(f"\\n[dim]Session ID: {session_state.metadata.session_id}[/dim]")
    console.print(
        f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} "
        "--hitl-response 'your response'"
    )
    console.print()

    # Return with HITL pause exit code
    return RunResult(
        success=True,
        message="Workflow paused for human input",
        exit_code=EX_HITL_PAUSE,
        pattern_type=PatternType.WORKFLOW,
        session_id=session_state.metadata.session_id,
        agent_id="hitl",
        last_response="",
        error=None,
        tokens_estimated=0,
        started_at=session_state.metadata.created_at,
        completed_at=datetime.now(UTC).isoformat(),
        duration_seconds=0.0,
    )


async def _execute_task(
    spec: Spec,
    task: Any,
    task_context: dict[str, Any],
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    cache: AgentCache,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> tuple[str, int]:
    """Execute a single task asynchronously.

    Args:
        spec: Workflow spec
        task: WorkflowTask object
        task_context: Template context for task input
        max_attempts: Max retry attempts
        wait_min: Min retry wait (seconds)
        wait_max: Max retry wait (seconds)

    Returns:
        Tuple of (response_text, estimated_tokens)

    Raises:
        WorkflowExecutionError: If task execution fails
    """
    # Render task input
    task_input_template = task.input or ""
    try:
        task_input = render_template(task_input_template, task_context)
    except Exception as e:
        raise WorkflowExecutionError(f"Failed to render task '{task.id}' input: {e}") from e

    # Get agent configuration for this task (supports multi-agent workflows)
    task_agent_id = task.agent
    if task_agent_id not in spec.agents:
        raise WorkflowExecutionError(
            f"Task '{task.id}' references unknown agent '{task_agent_id}'. "
            f"Available agents: {', '.join(spec.agents.keys())}"
        )
    task_agent_config = spec.agents[task_agent_id]

    # Phase 5: Use cached agent instead of rebuilding per task
    try:
        # Use task's tool_overrides if provided, else use agent's tools
        tools_for_task = (
            task.tool_overrides if hasattr(task, 'tool_overrides') and task.tool_overrides else None
        )

        # Phase 6.2: Inject last N notes into agent context
        injected_notes = None
        if notes_manager and spec.context_policy and spec.context_policy.notes:
            injected_notes = notes_manager.get_last_n_for_injection(
                spec.context_policy.notes.include_last
            )

        agent = await cache.get_or_build_agent(
            spec,
            task_agent_id,
            task_agent_config,
            tool_overrides=tools_for_task,
            conversation_manager=context_manager,
            hooks=hooks,
            injected_notes=injected_notes,
            worker_index=None,
        )
    except Exception as e:
        raise WorkflowExecutionError(f"Failed to build agent for task '{task.id}': {e}") from e

    # Execute with retry logic
    try:
        task_response = await invoke_agent_with_retry(
            agent, task_input, max_attempts, wait_min, wait_max
        )
    except Exception as e:
        error_msg = f"Task '{task.id}' failed: {e}"
        logger.error("workflow_task_failed", task=task.id, error=str(e))
        raise WorkflowExecutionError(error_msg) from e

    # Extract response text
    response_text = task_response if isinstance(task_response, str) else str(task_response)

    # Estimate tokens using shared estimator
    estimated_tokens = estimate_tokens(task_input, response_text)

    return response_text, estimated_tokens


def _validate_workflow_config(spec: Spec) -> dict[str, Any]:
    """Validate workflow configuration and build task map.

    Args:
        spec: Workflow spec with workflow pattern

    Returns:
        Dictionary mapping task IDs to task objects

    Raises:
        WorkflowExecutionError: If workflow has no tasks
    """
    if not spec.pattern.config.tasks:
        raise WorkflowExecutionError("Workflow pattern has no tasks")

    return {task.id: task for task in spec.pattern.config.tasks}


def _initialize_workflow_state(spec: Spec) -> tuple[int, int | None]:
    """Initialize workflow execution state.

    Args:
        spec: Workflow spec

    Returns:
        Tuple of (cumulative_tokens, max_tokens)
    """
    cumulative_tokens = 0
    max_tokens = None
    if spec.runtime.budgets:
        max_tokens = spec.runtime.budgets.get("max_tokens")

    return cumulative_tokens, max_tokens


async def _execute_workflow_layer(
    spec: Spec,
    layer_task_ids: list[str],
    task_map: dict[str, Any],
    task_results: dict[str, dict[str, Any]],
    variables: dict[str, str] | None,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    cache: AgentCache,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> list[tuple[str, int]]:
    """Execute all tasks in a workflow layer (potentially in parallel).

    Args:
        spec: Workflow spec
        layer_task_ids: Task IDs to execute in this layer
        task_map: Map of task ID to task object
        task_results: Existing task results
        variables: User variables
        max_attempts: Max retry attempts
        wait_min: Min retry wait
        wait_max: Max retry wait

    Returns:
        List of (response_text, estimated_tokens) for each task

    Raises:
        WorkflowExecutionError: If any task fails
    """
    # Build context with completed tasks
    task_context = _build_task_context(spec, task_results, variables)

    # Build tasks to execute with context captured
    tasks_to_execute = []
    for task_id in layer_task_ids:
        tasks_to_execute.append((task_id, task_map[task_id], dict(task_context)))

    # Get max_parallel limit from runtime configuration
    max_parallel = spec.runtime.max_parallel

    async def _execute_layer(
        tasks_with_context: list[tuple[str, Any, dict[str, Any]]],
    ) -> list[tuple[str, int]]:
        # Create semaphore for max_parallel if configured
        semaphore = asyncio.Semaphore(max_parallel) if max_parallel else None

        async def _execute_with_semaphore(
            task_id: str, task_obj: Any, context: dict[str, Any]
        ) -> tuple[str, int]:
            if semaphore:
                async with semaphore:
                    return await _execute_task(
                        spec,
                        task_obj,
                        context,
                        max_attempts,
                        wait_min,
                        wait_max,
                        cache,
                        context_manager,
                        hooks,
                        notes_manager,
                    )
            else:
                return await _execute_task(
                    spec,
                    task_obj,
                    context,
                    max_attempts,
                    wait_min,
                    wait_max,
                    cache,
                    context_manager,
                    hooks,
                    notes_manager,
                )  # Execute all tasks in layer (parallel where possible)

        results = await asyncio.gather(
            *[_execute_with_semaphore(tid, tobj, ctx) for tid, tobj, ctx in tasks_with_context],
            return_exceptions=False,  # Fail-fast on first error
        )
        return results

    # Run layer execution
    return await _execute_layer(tasks_to_execute)


async def run_workflow(  # noqa: C901
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,  # NEW: User's response when resuming from HITL pause
) -> RunResult:
    """Execute a multi-task workflow with DAG dependencies, HITL support, and optional session persistence.

    Executes tasks in topological order with parallel execution within each layer.
    Tasks can reference completed task outputs via {{ tasks.<id>.response }}.

    Phase 5 Performance Optimizations:
        - Agent caching: Reuses agents across tasks with same (agent_id, tools)
        - Single event loop: No per-layer asyncio.run() overhead
        - HTTP client cleanup: Proper resource management via AgentCache.close()

    Phase 3.1 Session Support:
        - Resume from checkpoint: Skip completed tasks on resume
        - Layer checkpointing: Save state after each layer completes
        - Partial layer resume: Handle tasks completed mid-layer

    Phase 2.1 HITL Support:
        - HITL tasks pause execution for user input
        - Session auto-enabled when HITL task detected
        - Resume with --hitl-response flag
        - Template context includes hitl_response variable

    Args:
        spec: Workflow spec with workflow pattern
        variables: Optional CLI --var overrides
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)
        hitl_response: User response for resuming from HITL pause

    Returns:
        RunResult with final task response and execution metadata

    Raises:
        WorkflowExecutionError: If workflow execution fails
        ValueError: If session_state and session_repo not both provided or both None
    """
    # Validate session parameters (both or neither)
    validate_session_params(session_state, session_repo)

    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    # Phase 10: Create root span for workflow execution with attributes
    with tracer.start_as_current_span("execute.workflow") as span:
        # Set span attributes (queryable metadata)
        span.set_attribute("spec.name", spec.name)
        span.set_attribute("spec.version", spec.version or 0)
        span.set_attribute("pattern.type", "workflow")
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id or "default")
        span.set_attribute("agent.count", len(spec.agents))
        if spec.pattern.config.tasks:
            span.set_attribute("workflow.task_count", len(spec.pattern.config.tasks))
        if session_state:
            span.set_attribute("session.id", session_state.metadata.session_id)
            span.set_attribute("session.resume", True)

        logger.info(
            "workflow_execution_start",
            spec_name=spec.name,
            resume=session_state is not None,
        )
        span.add_event("execution_start", {"spec_name": spec.name})

        # Validate and prepare workflow
        task_map = _validate_workflow_config(spec)

        # Get retry config
        max_attempts, wait_min, wait_max = get_retry_config(spec)

        # Perform topological sort
        try:
            tasks = spec.pattern.config.tasks
            assert tasks is not None, "Workflow pattern must have tasks"
            execution_layers = _topological_sort(tasks)
        except Exception as e:
            raise WorkflowExecutionError(f"Failed to build execution plan: {e}") from e

        logger.info(
            "workflow_execution_plan",
            total_tasks=len(task_map),
            layers=len(execution_layers),
            layer_sizes=[len(layer) for layer in execution_layers],
        )

        # Restore or initialize execution state
        if session_state:
            # Resume mode: restore completed tasks and results
            task_results = session_state.pattern_state.get("task_results", {})
            completed_tasks = set(session_state.pattern_state.get("completed_tasks", []))
            current_layer = session_state.pattern_state.get("current_layer", 0)
            cumulative_tokens = get_cumulative_tokens(session_state)
            started_at = session_state.metadata.created_at
            
            # HITL: Check if resuming from HITL pause
            hitl_state_dict = session_state.pattern_state.get("hitl_state")
            if hitl_state_dict:
                hitl_state = HITLState(**hitl_state_dict)
                if hitl_state.active:
                    # Validate HITL response provided
                    logger.debug(
                        "hitl_validation_check",
                        hitl_response=repr(hitl_response),
                        is_none=hitl_response is None,
                        is_falsy=not hitl_response,
                    )
                    if not hitl_response:
                        raise WorkflowExecutionError(
                            f"Session {session_state.metadata.session_id} is waiting for HITL response. "
                            f"Resume with: strands run --resume {session_state.metadata.session_id} "
                            "--hitl-response 'your response'"
                        )

                    # Inject HITL response into task_results
                    task_results[hitl_state.task_id] = {
                        "type": "hitl",
                        "prompt": hitl_state.prompt,
                        "response": hitl_response,
                        "status": "success",
                        "tokens_estimated": 0,
                    }
                    completed_tasks.add(hitl_state.task_id)

                    # Mark HITL as no longer active
                    hitl_state.active = False
                    hitl_state.user_response = hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()

                    # CRITICAL: Checkpoint after injection (prevents re-prompt on crash)
                    session_state.pattern_state["task_results"] = task_results
                    session_state.pattern_state["completed_tasks"] = list(completed_tasks)
                    # Note: current_layer stays same (resume from same layer)
                    await session_repo.save(session_state, "")

                    logger.info(
                        "hitl_response_injected",
                        session_id=session_state.metadata.session_id,
                        task_id=hitl_state.task_id,
                        response=hitl_response[:100],
                    )
            
            logger.info(
                "workflow_resume",
                session_id=session_state.metadata.session_id,
                completed_tasks=len(completed_tasks),
                current_layer=current_layer,
                total_layers=len(execution_layers),
            )
            span.add_event(
                "workflow_resume",
                {
                    "session_id": session_state.metadata.session_id,
                    "completed_tasks": len(completed_tasks),
                    "current_layer": current_layer,
                },
            )
        else:
            # Fresh start
            task_results = {}
            completed_tasks = set()
            current_layer = 0
            cumulative_tokens = 0
            started_at = datetime.now(UTC).isoformat()

        # Initialize workflow state
        _, max_tokens = _initialize_workflow_state(spec)

        # Phase 6.1: Create context manager and hooks for compaction
        context_manager = create_from_policy(spec.context_policy, spec)
        hooks: list[Any] = []
        if (
            spec.context_policy
            and spec.context_policy.compaction
            and spec.context_policy.compaction.enabled
        ):
            threshold = spec.context_policy.compaction.when_tokens_over or 60000
            hooks.append(
                ProactiveCompactionHook(threshold_tokens=threshold, model_id=spec.runtime.model_id)
            )
            logger.info("compaction_enabled", threshold_tokens=threshold)

        # Phase 6.4: Add budget enforcer hook (runs AFTER compaction to allow token reduction)
        if spec.runtime.budgets and spec.runtime.budgets.get("max_tokens"):
            from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

            max_tokens_val = spec.runtime.budgets["max_tokens"]
            # Ensure max_tokens is int (spec validation should guarantee this)
            max_tokens = int(max_tokens_val) if max_tokens_val is not None else 0
            warn_threshold = spec.runtime.budgets.get("warn_threshold", 0.8)
            hooks.append(BudgetEnforcerHook(max_tokens=max_tokens, warn_threshold=warn_threshold))
            logger.info(
                "budget_enforcer_enabled", max_tokens=max_tokens, warn_threshold=warn_threshold
            )

        # Phase 6.2: Initialize notes manager and hook for structured notes
        notes_manager = None
        task_counter = [0]  # Mutable container for hook to track task count
        if spec.context_policy and spec.context_policy.notes:
            notes_manager = NotesManager(spec.context_policy.notes.file)

            # Build agent_id → tools mapping for notes hook
            agent_tools: dict[str, list[str]] = {}
            for agent_id, agent_config in spec.agents.items():
                if agent_config.tools:
                    agent_tools[agent_id] = agent_config.tools

            hooks.append(NotesAppenderHook(notes_manager, task_counter, agent_tools))
            logger.info("notes_enabled", notes_file=spec.context_policy.notes.file)

        # Phase 5: Create AgentCache for agent reuse across tasks
        cache = AgentCache()
        try:
            # Execute each layer starting from current_layer
            for layer_index in range(current_layer, len(execution_layers)):
                layer_task_ids = execution_layers[layer_index]

                # Filter out completed tasks
                pending_tasks = [tid for tid in layer_task_ids if tid not in completed_tasks]

                if not pending_tasks:
                    logger.debug(
                        "workflow_layer_skipped",
                        layer=layer_index,
                        all_completed=True,
                    )
                    continue  # Layer already complete

                logger.info(
                    "workflow_layer_start",
                    layer=layer_index,
                    pending_tasks=pending_tasks,
                    total_tasks=len(layer_task_ids),
                )

                # HITL: Check if layer contains HITL task (MVP: only one HITL per layer)
                hitl_task_id = _check_layer_for_hitl(layer_task_ids, task_map, completed_tasks)
                
                if hitl_task_id:
                    # HITL task detected - ensure session persistence is enabled
                    if not session_state or not session_repo:
                        # Auto-enable sessions for HITL support
                        from pathlib import Path
                        from platformdirs import user_cache_dir
                        from strands_cli.session import SessionMetadata
                        
                        cache_dir = Path(user_cache_dir("strands-cli")) / "sessions"
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        
                        session_repo = FileSessionRepository(storage_dir=cache_dir)
                        
                        # Create new session state
                        session_id = f"{spec.name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
                        # Simple hash for auto-created HITL sessions (MVP)
                        import hashlib
                        import json

                        spec_hash = hashlib.sha256(
                            json.dumps(spec.model_dump(), sort_keys=True).encode()
                        ).hexdigest()

                        session_metadata = SessionMetadata(
                            session_id=session_id,
                            workflow_name=spec.name,
                            spec_hash=spec_hash,
                            pattern_type=PatternType.WORKFLOW,
                            status=SessionStatus.RUNNING,
                            created_at=started_at,
                            updated_at=datetime.now(UTC).isoformat(),
                        )
                        session_state = SessionState(
                            metadata=session_metadata,
                            runtime_config={},
                            pattern_state={
                                "task_results": task_results,
                                "completed_tasks": list(completed_tasks),
                                "current_layer": layer_index,
                            },
                            variables=variables or {},
                            token_usage=TokenUsage(),
                        )
                        
                        logger.info(
                            "hitl_auto_enabled_sessions",
                            session_id=session_id,
                            storage_dir=str(cache_dir),
                            task_id=hitl_task_id,
                        )
                    
                    # Execute tasks before HITL sequentially
                    pre_hitl_tasks = []
                    for tid in pending_tasks:
                        if tid == hitl_task_id:
                            break
                        pre_hitl_tasks.append(tid)
                    
                    # Execute pre-HITL tasks if any
                    if pre_hitl_tasks:
                        logger.info(
                            "hitl_executing_pre_tasks",
                            layer=layer_index,
                            pre_hitl_tasks=pre_hitl_tasks,
                        )
                        try:
                            pre_hitl_results = await _execute_workflow_layer(
                                spec,
                                pre_hitl_tasks,
                                task_map,
                                task_results,
                                variables,
                                max_attempts,
                                wait_min,
                                wait_max,
                                cache,
                                context_manager,
                                hooks,
                                notes_manager,
                            )
                        except Exception as e:
                            raise WorkflowExecutionError(
                                f"Pre-HITL tasks in layer {layer_index} failed: {e}"
                            ) from e
                        
                        # Store pre-HITL results
                        for task_id, (response_text, estimated_tokens) in zip(
                            pre_hitl_tasks, pre_hitl_results, strict=True
                        ):
                            cumulative_tokens += estimated_tokens
                            task_results[task_id] = {
                                "response": response_text,
                                "status": "success",
                                "tokens_estimated": estimated_tokens,
                                "agent": task_map[task_id].agent,
                            }
                            completed_tasks.add(task_id)
                    
                    # Execute HITL pause
                    hitl_task = task_map[hitl_task_id]
                    return await _execute_hitl_pause(
                        spec,
                        hitl_task_id,
                        hitl_task,
                        task_results,
                        variables,
                        session_state,
                        session_repo,
                        layer_index,
                        completed_tasks,
                    )

                # Phase 5: Direct await instead of asyncio.run() per layer
                try:
                    layer_results = await _execute_workflow_layer(
                        spec,
                        pending_tasks,  # Only execute pending tasks
                        task_map,
                        task_results,
                        variables,
                        max_attempts,
                        wait_min,
                        wait_max,
                        cache,
                        context_manager,
                        hooks,
                        notes_manager,
                    )
                except Exception as e:
                    raise WorkflowExecutionError(
                        f"Layer {layer_index} execution failed: {e}"
                    ) from e

                # Process results for pending tasks only
                layer_tokens = 0
                for task_id, (response_text, estimated_tokens) in zip(
                    pending_tasks, layer_results, strict=True
                ):
                    cumulative_tokens += estimated_tokens
                    layer_tokens += estimated_tokens

                    # Store result with agent ID for tracking
                    task_results[task_id] = {
                        "response": response_text,
                        "status": "success",
                        "tokens_estimated": estimated_tokens,
                        "agent": task_map[task_id].agent,  # Track which agent executed this task
                    }
                    completed_tasks.add(task_id)

                    logger.info(
                        "workflow_task_complete",
                        task=task_id,
                        agent=task_map[task_id].agent,
                        response_length=len(response_text),
                        cumulative_tokens=cumulative_tokens,
                    )
                    span.add_event(
                        "task_complete",
                        {
                            "task_id": task_id,
                            "agent_id": task_map[task_id].agent,
                            "response_length": len(response_text),
                            "cumulative_tokens": cumulative_tokens,
                        },
                    )

                # Checkpoint after layer completion
                if session_state and session_repo:
                    await checkpoint_pattern_state(
                        session_state,
                        session_repo,
                        pattern_state_updates={
                            "task_results": task_results,
                            "completed_tasks": list(completed_tasks),
                            "current_layer": layer_index + 1,
                        },
                        token_increment=layer_tokens,
                    )
                    logger.debug(
                        "workflow_layer_checkpointed",
                        layer=layer_index,
                        session_id=session_state.metadata.session_id,
                    )

                logger.info(
                    "workflow_layer_complete",
                    layer=layer_index,
                    tasks_completed=len(pending_tasks),
                )

            completed_at = datetime.now(UTC).isoformat()
            started_dt = datetime.fromisoformat(started_at)
            completed_dt = datetime.fromisoformat(completed_at)
            duration = (completed_dt - started_dt).total_seconds()

            # Finalize session if persistence enabled
            if session_state and session_repo:
                await finalize_session(session_state, session_repo)

            # Final response is from last executed task
            last_task_id = execution_layers[-1][-1]
            final_response = task_results[last_task_id]["response"]
            final_agent_id = task_results[last_task_id]["agent"]

            logger.info(
                "workflow_execution_complete",
                spec_name=spec.name,
                tasks_executed=len(task_results),
                duration_seconds=duration,
                cumulative_tokens=cumulative_tokens,
            )
            span.add_event(
                "execution_complete",
                {
                    "duration_seconds": duration,
                    "tasks_executed": len(task_results),
                    "cumulative_tokens": cumulative_tokens,
                },
            )

            return RunResult(
                success=True,
                last_response=final_response,
                error=None,
                agent_id=final_agent_id,
                pattern_type=PatternType.WORKFLOW,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                artifacts_written=[],
                execution_context={"tasks": task_results},
            )
        except Exception as e:
            # Mark session as failed before re-raising
            if session_state and session_repo:
                await fail_session(session_state, session_repo, e)

            # Re-raise workflow execution errors
            if isinstance(e, WorkflowExecutionError):
                raise
            raise WorkflowExecutionError(f"Workflow execution failed: {e}") from e
        finally:
            # Phase 5: Clean up cached agents and HTTP clients
            await cache.close()

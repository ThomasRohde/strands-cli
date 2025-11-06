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
from datetime import UTC, datetime
from typing import Any

import structlog

from strands_cli.exec.utils import (
    AgentCache,
    check_budget_threshold,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.loader import render_template
from strands_cli.types import PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


logger = structlog.get_logger(__name__)


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
        task_results: Map of task_id -> {response, status, ...}
        variables: User-provided variables from --var flags

    Returns:
        Template context dictionary with tasks{}, user variables
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

    return context


async def _execute_task(
    spec: Spec,
    task: Any,
    task_context: dict[str, Any],
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    cache: AgentCache,
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
        agent = await cache.get_or_build_agent(
            spec, task_agent_id, task_agent_config, tool_overrides=tools_for_task
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
                )

        # Execute all tasks in layer (parallel where possible)
        results = await asyncio.gather(
            *[_execute_with_semaphore(tid, tobj, ctx) for tid, tobj, ctx in tasks_with_context],
            return_exceptions=False,  # Fail-fast on first error
        )
        return results

    # Run layer execution
    return await _execute_layer(tasks_to_execute)


async def run_workflow(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a multi-task workflow with DAG dependencies.

    Executes tasks in topological order with parallel execution within each layer.
    Tasks can reference completed task outputs via {{ tasks.<id>.response }}.

    Phase 5 Performance Optimizations:
        - Agent caching: Reuses agents across tasks with same (agent_id, tools)
        - Single event loop: No per-layer asyncio.run() overhead
        - HTTP client cleanup: Proper resource management via AgentCache.close()

    Args:
        spec: Workflow spec with workflow pattern
        variables: Optional CLI --var overrides

    Returns:
        RunResult with final task response and execution metadata

    Raises:
        WorkflowExecutionError: If workflow execution fails
    """
    logger.info("workflow_execution_start", spec_name=spec.name)

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

    # Initialize execution state
    cumulative_tokens, max_tokens = _initialize_workflow_state(spec)
    task_results: dict[str, dict[str, Any]] = {}
    started_at = datetime.now(UTC).isoformat()

    # Phase 5: Create AgentCache for agent reuse across tasks
    cache = AgentCache()
    try:
        # Execute each layer
        for layer_index, layer_task_ids in enumerate(execution_layers):
            logger.info(
                "workflow_layer_start",
                layer=layer_index,
                tasks=layer_task_ids,
            )

            # Phase 5: Direct await instead of asyncio.run() per layer
            try:
                layer_results = await _execute_workflow_layer(
                    spec,
                    layer_task_ids,
                    task_map,
                    task_results,
                    variables,
                    max_attempts,
                    wait_min,
                    wait_max,
                    cache,
                )
            except Exception as e:
                raise WorkflowExecutionError(f"Layer {layer_index} execution failed: {e}") from e

            # Process results
            for task_id, (response_text, estimated_tokens) in zip(
                layer_task_ids, layer_results, strict=True
            ):
                cumulative_tokens += estimated_tokens

                # Check budget
                if max_tokens:
                    check_budget_threshold(cumulative_tokens, max_tokens, task_id)

                # Store result with agent ID for tracking
                task_results[task_id] = {
                    "response": response_text,
                    "status": "success",
                    "tokens_estimated": estimated_tokens,
                    "agent": task_map[task_id].agent,  # Track which agent executed this task
                }

                logger.info(
                    "workflow_task_complete",
                    task=task_id,
                    agent=task_map[task_id].agent,
                    response_length=len(response_text),
                    cumulative_tokens=cumulative_tokens,
                )

            logger.info(
                "workflow_layer_complete",
                layer=layer_index,
                tasks_completed=len(layer_task_ids),
            )

        completed_at = datetime.now(UTC).isoformat()
        started_dt = datetime.fromisoformat(started_at)
        completed_dt = datetime.fromisoformat(completed_at)
        duration = (completed_dt - started_dt).total_seconds()

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
    finally:
        # Phase 5: Clean up cached agents and HTTP clients
        await cache.close()

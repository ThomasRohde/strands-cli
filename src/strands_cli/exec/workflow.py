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
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.loader import render_template
from strands_cli.runtime import build_agent
from strands_cli.types import PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


# Transient errors that should trigger retries
_TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
)


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


def _get_retry_config(spec: Spec) -> tuple[int, int, int]:
    """Get retry configuration from spec.

    Args:
        spec: Workflow spec with optional failure_policy

    Returns:
        Tuple of (max_attempts, wait_min, wait_max) in seconds
    """
    max_attempts = 3
    wait_min = 1
    wait_max = 60

    if spec.runtime.failure_policy:
        policy = spec.runtime.failure_policy
        retries = policy.get("retries", max_attempts - 1)

        if retries < 0:
            raise WorkflowExecutionError(
                f"Invalid retry config: retries must be >= 0, got {retries}"
            )

        max_attempts = retries + 1
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            if wait_min > wait_max:
                raise WorkflowExecutionError(
                    f"Invalid retry config: wait_min ({wait_min}s) must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


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


def _check_budget_warning(
    cumulative_tokens: int,
    max_tokens: int | None,
    task_id: str,
) -> None:
    """Check token budget and log warnings.

    Args:
        cumulative_tokens: Total tokens used so far
        max_tokens: Maximum tokens allowed (from budgets.max_tokens)
        task_id: Current task ID for logging
    """
    if max_tokens is None:
        return

    usage_percent = (cumulative_tokens / max_tokens) * 100

    if usage_percent >= 100:
        logger.error(
            "token_budget_exceeded",
            task=task_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_percent=usage_percent,
        )
        raise WorkflowExecutionError(
            f"Token budget exceeded: {cumulative_tokens}/{max_tokens} tokens (100%)"
        )
    elif usage_percent >= 80:
        logger.warning(
            "token_budget_warning",
            task=task_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_percent=f"{usage_percent:.1f}",
        )


async def _execute_task(
    spec: Spec,
    task: Any,
    agent_id: str,
    agent_config: Any,
    task_context: dict[str, Any],
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[str, int]:
    """Execute a single task asynchronously.

    Args:
        spec: Workflow spec
        task: WorkflowTask object
        agent_id: Agent ID to use
        agent_config: Agent configuration
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

    # Build agent for this task
    try:
        agent = build_agent(spec, task.agent, agent_config)
    except Exception as e:
        raise WorkflowExecutionError(f"Failed to build agent for task '{task.id}': {e}") from e

    # Execute with retry logic
    async def _execute_with_retry(agent_instance: Any, input_text: str) -> AgentResult:
        """Execute agent with retry logic."""
        return await agent_instance.invoke_async(input_text)

    retry_decorator = retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=wait_min, max=wait_max),
        retry=retry_if_exception_type(_TRANSIENT_ERRORS),
        reraise=True,
    )
    _execute_fn = retry_decorator(_execute_with_retry)

    try:
        task_response = await _execute_fn(agent, task_input)
    except _TRANSIENT_ERRORS as e:
        error_msg = f"Task '{task.id}' failed after {max_attempts} attempts: {e}"
        logger.error("workflow_task_failed", task=task.id, error=str(e))
        raise WorkflowExecutionError(error_msg) from e
    except Exception as e:
        error_msg = f"Task '{task.id}' failed: {e}"
        logger.error("workflow_task_failed", task=task.id, error=str(e))
        raise WorkflowExecutionError(error_msg) from e

    # Extract response text
    response_text = task_response if isinstance(task_response, str) else str(task_response)

    # Estimate tokens
    estimated_tokens = len(task_input.split()) + len(response_text.split())

    return response_text, estimated_tokens


def run_workflow(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a multi-task workflow with DAG dependencies.

    Executes tasks in topological order with parallel execution within each layer.
    Tasks can reference completed task outputs via {{ tasks.<id>.response }}.

    Args:
        spec: Workflow spec with workflow pattern
        variables: Optional CLI --var overrides

    Returns:
        RunResult with final task response and execution metadata

    Raises:
        WorkflowExecutionError: If workflow execution fails
    """
    logger.info("workflow_execution_start", spec_name=spec.name)

    if not spec.pattern.config.tasks:
        raise WorkflowExecutionError("Workflow pattern has no tasks")

    # Extract single agent (Phase 1 limitation)
    agent_id = next(iter(spec.agents.keys()))
    agent_config = spec.agents[agent_id]

    # Get retry config
    max_attempts, wait_min, wait_max = _get_retry_config(spec)

    # Build task map
    task_map = {task.id: task for task in spec.pattern.config.tasks}

    # Perform topological sort
    try:
        execution_layers = _topological_sort(spec.pattern.config.tasks)
    except Exception as e:
        raise WorkflowExecutionError(f"Failed to build execution plan: {e}") from e

    logger.info(
        "workflow_execution_plan",
        total_tasks=len(task_map),
        layers=len(execution_layers),
        layer_sizes=[len(layer) for layer in execution_layers],
    )

    # Track execution state
    task_results: dict[str, dict[str, Any]] = {}  # task_id -> {response, status, tokens}
    cumulative_tokens = 0
    max_tokens = None
    if spec.runtime.budgets:
        max_tokens = spec.runtime.budgets.get("max_tokens")

    # Get max_parallel limit from runtime configuration
    max_parallel = spec.runtime.max_parallel

    started_at = datetime.now(UTC).isoformat()

    # Execute each layer
    for layer_index, layer_task_ids in enumerate(execution_layers):
        logger.info(
            "workflow_layer_start",
            layer=layer_index,
            tasks=layer_task_ids,
        )

        # Build context with completed tasks
        task_context = _build_task_context(spec, task_results, variables)

        # Execute tasks in this layer (potentially in parallel)
        # Build tasks to execute with context captured
        tasks_to_execute = []
        for task_id in layer_task_ids:
            tasks_to_execute.append((task_id, task_map[task_id], dict(task_context)))

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
                            agent_id,
                            agent_config,
                            context,
                            max_attempts,
                            wait_min,
                            wait_max,
                        )
                else:
                    return await _execute_task(
                        spec,
                        task_obj,
                        agent_id,
                        agent_config,
                        context,
                        max_attempts,
                        wait_min,
                        wait_max,
                    )

            # Execute all tasks in layer (parallel where possible)
            results = await asyncio.gather(
                *[_execute_with_semaphore(tid, tobj, ctx) for tid, tobj, ctx in tasks_with_context],
                return_exceptions=False,  # Fail-fast on first error
            )
            return results

        # Run layer execution
        try:
            layer_results = asyncio.run(_execute_layer(tasks_to_execute))
        except Exception as e:
            raise WorkflowExecutionError(f"Layer {layer_index} execution failed: {e}") from e

        # Process results
        for task_id, (response_text, estimated_tokens) in zip(
            layer_task_ids, layer_results, strict=True
        ):
            cumulative_tokens += estimated_tokens

            # Check budget
            if max_tokens:
                _check_budget_warning(cumulative_tokens, max_tokens, task_id)

            # Store result
            task_results[task_id] = {
                "response": response_text,
                "status": "success",
                "tokens_estimated": estimated_tokens,
            }

            logger.info(
                "workflow_task_complete",
                task=task_id,
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
        agent_id=agent_id,
        pattern_type=PatternType.WORKFLOW,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        artifacts_written=[],
        execution_context={"tasks": task_results},
    )

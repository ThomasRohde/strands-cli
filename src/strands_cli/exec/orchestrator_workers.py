"""Orchestrator-workers executor.

Implements dynamic task delegation with worker pools. The orchestrator agent
breaks down tasks into subtasks and delegates to workers for parallel execution.

Execution Flow:
    1. Orchestrator invocation: Request JSON array of subtasks
    2. Worker execution: Execute subtasks in parallel (respecting max_workers)
    3. Track rounds: Count orchestrator delegation cycles (not worker count)
    4. Optional reduce: Aggregate worker outputs
    5. Optional writeup: Final synthesis step

Orchestrator Protocol:
    - Expected JSON response: [{"task": "description"}, ...]
    - Retry on malformed JSON (up to 2 retries with clarification)
    - Empty array [] signals "no work needed" (success)

Worker Execution:
    - Workers execute in parallel batches (semaphore control via max_workers)
    - Indexed template access: {{ workers[0].response }}, {{ workers[1].status }}
    - Fail-fast: First worker failure cancels all remaining workers

Round Semantics:
    - Round = orchestrator delegation cycle (not individual worker executions)
    - max_rounds limits total orchestrator invocations
    - Single round can spawn multiple workers

Budget Enforcement:
    - Cumulative token tracking across orchestrator + workers + reduce + writeup
    - Warn at 80%, hard stop at 100%
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry import trace

from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class OrchestratorExecutionError(Exception):
    """Raised when orchestrator execution fails."""

    pass


logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


def _parse_orchestrator_json(response_text: str) -> list[dict[str, Any]] | None:
    """Parse orchestrator response JSON with multi-strategy fallback.

    Attempts:
        1. Direct JSON parse
        2. Extract from code blocks (```json ... ```)
        3. Regex extraction of array [...] or object {...}

    Args:
        response_text: Orchestrator agent response

    Returns:
        Parsed list of task dicts, or None if parsing fails
    """
    # Strategy 1: Direct parse
    parsed = _try_direct_json_parse(response_text)
    if parsed is not None:
        return parsed

    # Strategy 2: Extract from code blocks
    parsed = _try_code_block_extraction(response_text)
    if parsed is not None:
        return parsed

    # Strategy 3: Regex extraction
    parsed = _try_regex_extraction(response_text)
    return parsed


def _try_direct_json_parse(response_text: str) -> list[dict[str, Any]] | None:
    """Try to parse response as direct JSON."""
    try:
        parsed = json.loads(response_text.strip())
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            # If dict returned, wrap in list
            return [parsed]
    except json.JSONDecodeError:
        pass
    return None


def _try_code_block_extraction(response_text: str) -> list[dict[str, Any]] | None:
    """Try to extract JSON from code blocks."""
    code_block_pattern = r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```"
    match = re.search(code_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass
    return None


def _try_regex_extraction(response_text: str) -> list[dict[str, Any]] | None:
    """Try to extract JSON array using regex."""
    array_pattern = r"\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]"
    match = re.search(array_pattern, response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


async def _invoke_orchestrator_with_retry(
    cache: AgentCache,
    spec: Spec,
    orchestrator_agent_id: str,
    prompt: str,
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    max_json_retries: int = 2,
) -> tuple[list[dict[str, Any]], int]:
    """Invoke orchestrator agent with JSON parsing retry logic.

    Args:
        cache: AgentCache for agent reuse
        spec: Workflow spec
        orchestrator_agent_id: Orchestrator agent ID
        prompt: Orchestrator prompt
        context_manager: Context manager instance
        hook_factory: Factory function that creates fresh hooks
        notes_manager: Notes manager instance
        max_attempts: Max retry attempts
        wait_min: Min wait time (seconds)
        wait_max: Max wait time (seconds)
        max_json_retries: Max retries for malformed JSON (default: 2)

    Returns:
        Tuple of (subtasks_list, tokens_used)

    Raises:
        OrchestratorExecutionError: If JSON parsing fails after retries
    """
    agent_config = spec.agents[orchestrator_agent_id]
    injected_notes = (
        notes_manager.get_last_n_for_injection(spec.context_policy.notes.include_last)
        if notes_manager and spec.context_policy and spec.context_policy.notes
        else None
    )

    # Track retry history for diagnostics
    retry_history: list[dict[str, Any]] = []

    for retry_attempt in range(max_json_retries + 1):
        # Create fresh hooks for this agent invocation
        hooks = hook_factory()

        # Build or reuse agent
        agent = await cache.get_or_build_agent(
            spec,
            orchestrator_agent_id,
            agent_config,
            tool_overrides=None,
            conversation_manager=context_manager,
            hooks=hooks,
            injected_notes=injected_notes,
            worker_index=None,
        )

        # Invoke orchestrator
        result = await invoke_agent_with_retry(agent, prompt, max_attempts, wait_min, wait_max)

        # Extract response text
        response_text = result if isinstance(result, str) else str(result)
        tokens_used = estimate_tokens(prompt, response_text)

        # Parse JSON
        subtasks = _parse_orchestrator_json(response_text)

        if subtasks is not None:
            logger.info(
                "Orchestrator returned subtasks",
                num_subtasks=len(subtasks),
                retry_attempt=retry_attempt,
            )
            return subtasks, tokens_used

        # Track failed attempt
        retry_history.append(
            {
                "attempt": retry_attempt + 1,
                "response_preview": response_text[:200],
                "tokens_used": tokens_used,
            }
        )

        # Malformed JSON - retry with clarification
        if retry_attempt < max_json_retries:
            logger.warning(
                "orchestrator_json_parse_failed",
                retry_attempt=retry_attempt + 1,
                max_retries=max_json_retries + 1,
                response_preview=response_text[:200],
            )
            prompt = f"""Your previous response was not valid JSON. Please respond with ONLY a JSON array of tasks.

Expected format:
[
  {{"task": "description of subtask 1"}},
  {{"task": "description of subtask 2"}}
]

Do not include any text before or after the JSON array. If there are no subtasks, return an empty array: []

Previous response that failed to parse:
{response_text[:500]}
"""

    # All retries exhausted - raise structured error
    import json

    raise OrchestratorExecutionError(
        f"Failed to parse orchestrator response as valid JSON after {max_json_retries + 1} attempts. "
        f"Expected format: [{{'task': 'description'}}, ...]. "
        f"Retry history: {json.dumps(retry_history, indent=2)}"
    )


async def _execute_worker(
    cache: AgentCache,
    spec: Spec,
    worker_agent_id: str,
    task: dict[str, Any],
    worker_index: int,
    tool_overrides: list[str] | None,
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> dict[str, Any]:
    """Execute a single worker task.

    Args:
        cache: AgentCache for agent reuse
        spec: Workflow spec
        worker_agent_id: Worker agent ID
        task: Task dictionary from orchestrator
        worker_index: Worker index (0-based)
        tool_overrides: Worker tool overrides from worker_template
        context_manager: Context manager instance
        hook_factory: Factory function that creates fresh hooks
        notes_manager: Notes manager instance
        max_attempts: Max retry attempts
        wait_min: Min wait time (seconds)
        wait_max: Max wait time (seconds)

    Returns:
        Worker result dict with response, status, tokens

    Raises:
        Exception: If worker execution fails after retries
    """
    logger.info(
        "Executing worker task",
        worker_index=worker_index,
        task=task,
    )

    # Add worker_assigned event
    span = trace.get_current_span()
    if span.is_recording():
        task_description = task.get("task", str(task))
        span.add_event(
            "worker_assigned", {"worker_id": worker_index, "task_id": f"task_{worker_index}"}
        )

    agent_config = spec.agents[worker_agent_id]
    injected_notes = (
        notes_manager.get_last_n_for_injection(spec.context_policy.notes.include_last)
        if notes_manager and spec.context_policy and spec.context_policy.notes
        else None
    )

    # Create fresh hooks for this worker
    hooks = hook_factory()

    # Build or reuse agent with tool overrides
    # Include worker_index to ensure each worker gets isolated agent instance
    agent = await cache.get_or_build_agent(
        spec,
        worker_agent_id,
        agent_config,
        tool_overrides=tool_overrides,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=injected_notes,
        worker_index=worker_index,
    )

    # Invoke worker with task description
    task_description = task.get("task", str(task))
    result = await invoke_agent_with_retry(
        agent, task_description, max_attempts, wait_min, wait_max
    )

    response_text = result if isinstance(result, str) else str(result)
    tokens_used = estimate_tokens(task_description, response_text)

    # Add worker_complete event
    if span.is_recording():
        span.add_event(
            "worker_complete",
            {"worker_id": worker_index, "task_id": f"task_{worker_index}", "success": True},
        )

    return {
        "response": response_text,
        "status": "success",
        "tokens": tokens_used,
        "task": task_description,
    }


async def _execute_workers_batch(
    cache: AgentCache,
    spec: Spec,
    worker_agent_id: str,
    subtasks: list[dict[str, Any]],
    tool_overrides: list[str] | None,
    max_workers: int | None,
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[list[dict[str, Any]], int]:
    """Execute all worker tasks in parallel with semaphore control.

    Args:
        cache: AgentCache for agent reuse
        spec: Workflow spec
        worker_agent_id: Worker agent ID
        subtasks: List of subtask dicts from orchestrator
        tool_overrides: Worker tool overrides
        max_workers: Maximum concurrent workers (None = unlimited)
        context_manager: Context manager instance
        hook_factory: Factory function that creates fresh hooks
        notes_manager: Notes manager instance
        max_attempts: Max retry attempts
        wait_min: Min wait time (seconds)
        wait_max: Max wait time (seconds)

    Returns:
        Tuple of (worker_results_list, cumulative_tokens)

    Raises:
        Exception: If any worker fails (fail-fast semantics)
    """
    if not subtasks:
        logger.info("No subtasks to execute (empty array from orchestrator)")
        return [], 0

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_workers) if max_workers else None

    async def _execute_with_semaphore(task: dict[str, Any], index: int) -> dict[str, Any]:
        if semaphore:
            async with semaphore:
                return await _execute_worker(
                    cache,
                    spec,
                    worker_agent_id,
                    task,
                    index,
                    tool_overrides,
                    context_manager,
                    hook_factory,
                    notes_manager,
                    max_attempts,
                    wait_min,
                    wait_max,
                )
        else:
            return await _execute_worker(
                cache,
                spec,
                worker_agent_id,
                task,
                index,
                tool_overrides,
                context_manager,
                hook_factory,
                notes_manager,
                max_attempts,
                wait_min,
                wait_max,
            )

    logger.info(
        "Executing workers in parallel",
        num_workers=len(subtasks),
        max_workers=max_workers or "unlimited",
    )

    # Execute all workers in parallel (fail-fast)
    worker_results = await asyncio.gather(
        *[_execute_with_semaphore(task, i) for i, task in enumerate(subtasks)],
        return_exceptions=False,  # Fail-fast: first worker error cancels remaining workers
    )

    # Calculate cumulative tokens
    cumulative_tokens = sum(result.get("tokens", 0) for result in worker_results)

    logger.info(
        "Workers completed",
        num_workers=len(worker_results),
        cumulative_tokens=cumulative_tokens,
    )

    return list(worker_results), cumulative_tokens


async def run_orchestrator_workers(
    spec: Spec, variables: dict[str, str] | None = None
) -> RunResult:
    """Execute orchestrator-workers pattern workflow.

    Args:
        spec: Validated workflow specification
        variables: CLI variable overrides (from --var flags)

    Returns:
        RunResult with final response and execution metadata

    Raises:
        OrchestratorExecutionError: If orchestrator or worker execution fails
    """
    with tracer.start_as_current_span("execute.orchestrator_workers") as span:
        start_time = datetime.now(UTC)
        config = spec.pattern.config

        # Set span attributes
        span.set_attribute("spec.name", spec.name)
        if spec.version:
            span.set_attribute("spec.version", spec.version)
        span.set_attribute("pattern.type", spec.pattern.type.value)
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id)
        if spec.runtime.region:
            span.set_attribute("runtime.region", spec.runtime.region)

        if config.orchestrator:
            span.set_attribute("orchestrator_workers.orchestrator_agent", config.orchestrator.agent)
            if config.orchestrator.limits and config.orchestrator.limits.max_workers:
                span.set_attribute(
                    "orchestrator_workers.worker_pool_size", config.orchestrator.limits.max_workers
                )

        # Add execution_start event
        span.add_event("execution_start")

        # Validate required configuration
        if not config.orchestrator or not config.worker_template:
            raise OrchestratorExecutionError(
                "Orchestrator-workers pattern requires orchestrator and worker_template configuration"
            )

        # Setup execution parameters
        execution_params = _setup_execution_parameters(spec, config, variables)

        # Setup context and hook factory
        context_manager, hook_factory, notes_manager, cache = await _setup_context_and_hooks(spec)

        try:
            # Execute orchestrator round
            subtasks, cumulative_tokens = await _execute_orchestrator_round(
                cache, spec, execution_params, context_manager, hook_factory, notes_manager
            )

            # Add orchestrator_planning event
            span.add_event("orchestrator_planning", {"task_count": len(subtasks)})
            span.set_attribute("orchestrator_workers.worker_count", len(subtasks))

            # Execute workers
            worker_results, cumulative_tokens = await _execute_workers_round(
                cache,
                spec,
                execution_params,
                subtasks,
                context_manager,
                hook_factory,
                notes_manager,
                cumulative_tokens,
            )

            # Build execution context
            execution_context = _build_execution_context(
                worker_results, execution_params["user_variables"]
            )

            # Execute reduce step if configured
            final_response, cumulative_tokens = await _execute_reduce_step_if_needed(
                cache,
                spec,
                config,
                execution_context,
                context_manager,
                hook_factory,
                notes_manager,
                cumulative_tokens,
            )

            # Add orchestrator_synthesis event
            span.add_event("orchestrator_synthesis", {"results_count": len(worker_results)})

            # Execute writeup step if configured
            final_response, cumulative_tokens = await _execute_writeup_step_if_needed(
                cache,
                spec,
                config,
                execution_context,
                context_manager,
                hook_factory,
                notes_manager,
                cumulative_tokens,
                final_response,
            )

            # Build final response if no reduce/writeup
            if not final_response:
                final_response = _aggregate_worker_responses(worker_results)

            end_time = datetime.now(UTC)
            duration_seconds = (end_time - start_time).total_seconds()

            # Add execution_complete event
            span.add_event(
                "execution_complete",
                {"total_tasks": len(worker_results), "duration_seconds": duration_seconds},
            )

            # Build and return result
            return _build_run_result(
                spec,
                config,
                execution_params,
                start_time,
                final_response,
                execution_context,
                cumulative_tokens,
            )

        finally:
            # CRITICAL: Clean up resources
            await cache.close()


def _setup_execution_parameters(
    spec: Spec, config: Any, variables: dict[str, str] | None
) -> dict[str, Any]:
    """Setup execution parameters from spec and config."""
    orchestrator_agent_id = config.orchestrator.agent
    worker_agent_id = config.worker_template.agent
    tool_overrides = config.worker_template.tools
    max_workers = config.orchestrator.limits.max_workers if config.orchestrator.limits else None
    max_rounds = config.orchestrator.limits.max_rounds if config.orchestrator.limits else None

    # Phase 7 MVP: Only single round supported
    if max_rounds is not None and max_rounds != 1:
        raise OrchestratorExecutionError(
            f"Multi-round orchestration not yet supported (max_rounds={max_rounds}). "
            "Set max_rounds to 1 or omit for default single-round execution."
        )

    # Get retry config
    max_attempts, wait_min, wait_max = get_retry_config(spec)

    # Merge user variables (spec.inputs.values + CLI --var)
    user_variables: dict[str, Any] = {}
    if spec.inputs:
        user_variables.update(spec.inputs.get("values", {}))
    if variables:
        user_variables.update(variables)

    return {
        "orchestrator_agent_id": orchestrator_agent_id,
        "worker_agent_id": worker_agent_id,
        "tool_overrides": tool_overrides,
        "max_workers": max_workers,
        "max_rounds": 1,  # Hardcoded for Phase 7
        "max_attempts": max_attempts,
        "wait_min": wait_min,
        "wait_max": wait_max,
        "user_variables": user_variables,
    }


async def _setup_context_and_hooks(spec: Spec) -> tuple[Any, Any, Any, AgentCache]:
    """Setup context manager, hook factory, notes manager, and agent cache.

    Returns a hook factory function instead of a shared hooks list to ensure
    each agent gets fresh hook instances (critical for compaction and budget hooks).
    """
    from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

    # Create context manager (Phase 6)
    context_manager = create_from_policy(spec.context_policy, spec)

    # Add notes manager if enabled
    notes_manager = None
    step_counter: list[int] = [0]  # Shared counter for notes (list[int] for NotesAppenderHook)
    if spec.context_policy and spec.context_policy.notes:
        notes_config = spec.context_policy.notes
        notes_manager = NotesManager(notes_config.file)

    # Define hook factory that creates fresh instances per agent invocation
    def create_hooks() -> list[Any]:
        """Create fresh hook instances for each agent.

        Critical: Compaction and budget hooks are stateful and single-fire.
        Each agent must get its own instances to avoid interference.
        """
        hooks: list[Any] = []

        # Fresh compaction hook per agent (single-fire after first trigger)
        if (
            spec.context_policy
            and spec.context_policy.compaction
            and spec.context_policy.compaction.enabled
        ):
            threshold = spec.context_policy.compaction.when_tokens_over or 60000
            hooks.append(
                ProactiveCompactionHook(threshold_tokens=threshold, model_id=spec.runtime.model_id)
            )

        # Fresh budget enforcer hook per agent (runs AFTER compaction to allow token reduction)
        if spec.runtime.budgets and spec.runtime.budgets.get("max_tokens"):
            max_tokens = spec.runtime.budgets["max_tokens"]
            warn_threshold = spec.runtime.budgets.get("warn_threshold", 0.8)
            hooks.append(BudgetEnforcerHook(max_tokens=max_tokens, warn_threshold=warn_threshold))
            logger.info(
                "budget_enforcer_enabled", max_tokens=max_tokens, warn_threshold=warn_threshold
            )

        # Shared notes hook (OK to share - stateless except for step counter)
        if notes_manager:
            hooks.append(NotesAppenderHook(notes_manager, step_counter))

        return hooks

    # Create AgentCache (single instance for entire workflow)
    cache = AgentCache()

    return context_manager, create_hooks, notes_manager, cache


async def _execute_orchestrator_round(
    cache: AgentCache,
    spec: Spec,
    execution_params: dict[str, Any],
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
) -> tuple[list[dict[str, Any]], int]:
    """Execute orchestrator round and return subtasks and cumulative tokens."""
    round_count = 1
    cumulative_tokens = 0

    logger.info(
        "Starting orchestrator round",
        round=round_count,
        max_rounds=execution_params["max_rounds"] or "unlimited",
    )

    # Build orchestrator prompt
    orchestrator_prompt = _build_orchestrator_prompt(execution_params["user_variables"])

    # Invoke orchestrator with retry
    subtasks, orchestrator_tokens = await _invoke_orchestrator_with_retry(
        cache,
        spec,
        execution_params["orchestrator_agent_id"],
        orchestrator_prompt,
        context_manager,
        hook_factory,
        notes_manager,
        execution_params["max_attempts"],
        execution_params["wait_min"],
        execution_params["wait_max"],
    )

    cumulative_tokens += orchestrator_tokens
    return subtasks, cumulative_tokens


def _build_orchestrator_prompt(user_variables: dict[str, Any]) -> str:
    """Build the orchestrator prompt."""
    return f"""You are an orchestrator agent. Break down the following task into subtasks for worker agents to execute.

Respond with ONLY a JSON array of tasks. Each task should have a "task" field with the description.

Example format:
[
  {{"task": "Subtask 1 description"}},
  {{"task": "Subtask 2 description"}},
  {{"task": "Subtask 3 description"}}
]

If there are no subtasks needed, return an empty array: []

User input variables:
{json.dumps(user_variables, indent=2)}

Now break down the task into subtasks:"""


async def _execute_workers_round(
    cache: AgentCache,
    spec: Spec,
    execution_params: dict[str, Any],
    subtasks: list[dict[str, Any]],
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    cumulative_tokens: int,
) -> tuple[list[dict[str, Any]], int]:
    """Execute workers and return results and updated cumulative tokens."""
    # Execute workers
    worker_results, worker_tokens = await _execute_workers_batch(
        cache,
        spec,
        execution_params["worker_agent_id"],
        subtasks,
        execution_params["tool_overrides"],
        execution_params["max_workers"],
        context_manager,
        hook_factory,
        notes_manager,
        execution_params["max_attempts"],
        execution_params["wait_min"],
        execution_params["wait_max"],
    )

    cumulative_tokens += worker_tokens
    return worker_results, cumulative_tokens


def _build_execution_context(
    worker_results: list[dict[str, Any]], user_variables: dict[str, Any]
) -> dict[str, Any]:
    """Build execution context for reduce/writeup steps."""
    execution_context: dict[str, Any] = {
        "workers": worker_results,  # Indexed access: workers[0].response
        "num_workers": len(worker_results),
        "round_count": 1,  # MVP: single round
    }
    execution_context.update(user_variables)
    return execution_context


async def _execute_reduce_step_if_needed(
    cache: AgentCache,
    spec: Spec,
    config: Any,
    execution_context: dict[str, Any],
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    cumulative_tokens: int,
) -> tuple[str, int]:
    """Execute reduce step if configured and return response and updated tokens."""
    if not config.reduce:
        return "", cumulative_tokens

    logger.info("Executing reduce step", agent=config.reduce.agent)

    reduce_context = execution_context.copy()
    reduce_input = render_template(config.reduce.input or "", reduce_context)

    reduce_agent_config = spec.agents[config.reduce.agent]
    reduce_injected_notes = _get_injected_notes(notes_manager, spec.context_policy)

    # Create fresh hooks for reduce agent
    hooks = hook_factory()

    reduce_agent = await cache.get_or_build_agent(
        spec,
        config.reduce.agent,
        reduce_agent_config,
        tool_overrides=None,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=reduce_injected_notes,
        worker_index=None,
    )

    max_attempts, wait_min, wait_max = get_retry_config(spec)
    reduce_result = await invoke_agent_with_retry(
        reduce_agent, reduce_input, max_attempts, wait_min, wait_max
    )

    reduce_response = reduce_result if isinstance(reduce_result, str) else str(reduce_result)
    reduce_tokens = estimate_tokens(reduce_input, reduce_response)
    cumulative_tokens += reduce_tokens

    execution_context["reduce_response"] = reduce_response
    return reduce_response, cumulative_tokens


async def _execute_writeup_step_if_needed(
    cache: AgentCache,
    spec: Spec,
    config: Any,
    execution_context: dict[str, Any],
    context_manager: Any,
    hook_factory: Any,
    notes_manager: Any,
    cumulative_tokens: int,
    current_response: str,
) -> tuple[str, int]:
    """Execute writeup step if configured and return response and updated tokens."""
    if not config.writeup:
        return current_response, cumulative_tokens

    logger.info("Executing writeup step", agent=config.writeup.agent)

    writeup_context = execution_context.copy()
    writeup_input = render_template(config.writeup.input or "", writeup_context)

    writeup_agent_config = spec.agents[config.writeup.agent]
    writeup_injected_notes = _get_injected_notes(notes_manager, spec.context_policy)

    # Create fresh hooks for writeup agent
    hooks = hook_factory()

    writeup_agent = await cache.get_or_build_agent(
        spec,
        config.writeup.agent,
        writeup_agent_config,
        tool_overrides=None,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=writeup_injected_notes,
        worker_index=None,
    )

    max_attempts, wait_min, wait_max = get_retry_config(spec)
    writeup_result = await invoke_agent_with_retry(
        writeup_agent, writeup_input, max_attempts, wait_min, wait_max
    )

    writeup_response = writeup_result if isinstance(writeup_result, str) else str(writeup_result)
    writeup_tokens = estimate_tokens(writeup_input, writeup_response)
    cumulative_tokens += writeup_tokens

    execution_context["writeup_response"] = writeup_response
    return writeup_response, cumulative_tokens


def _get_injected_notes(notes_manager: Any, context_policy: Any) -> Any:
    """Get injected notes for agent if notes are enabled."""
    if notes_manager and context_policy and context_policy.notes:
        include_last = context_policy.notes.include_last or 0
        if include_last > 0:
            return notes_manager.get_last_n_for_injection(include_last)
    return None


def _aggregate_worker_responses(worker_results: list[dict[str, Any]]) -> str:
    """Aggregate worker responses into a single string."""
    if not worker_results:
        return ""
    return "\n\n".join(
        f"Worker {i}: {result['response']}" for i, result in enumerate(worker_results)
    )


def _build_run_result(
    spec: Spec,
    config: Any,
    execution_params: dict[str, Any],
    start_time: datetime,
    final_response: str,
    execution_context: dict[str, Any],
    cumulative_tokens: int,
) -> RunResult:
    """Build and return the final RunResult."""
    end_time = datetime.now(UTC)
    duration_seconds = (end_time - start_time).total_seconds()

    # Determine final agent ID (writeup > reduce > orchestrator)
    if config.writeup:
        final_agent_id = config.writeup.agent
    elif config.reduce:
        final_agent_id = config.reduce.agent
    else:
        final_agent_id = execution_params["orchestrator_agent_id"]

    logger.info(
        "Orchestrator-workers execution complete",
        duration_seconds=duration_seconds,
        total_tokens=cumulative_tokens,
        num_workers=len(execution_context.get("workers", [])),
        rounds=1,  # MVP: single round
    )

    return RunResult(
        success=True,
        last_response=final_response,
        agent_id=final_agent_id,
        pattern_type=PatternType.ORCHESTRATOR_WORKERS,
        started_at=start_time.isoformat(),
        completed_at=end_time.isoformat(),
        duration_seconds=duration_seconds,
        execution_context=execution_context,
    )

"""Parallel branch executor.

Executes parallel branches concurrently with optional reduce step for aggregation.
Each branch executes its steps sequentially while branches run in parallel.

Execution Flow:
    1. Validate parallel configuration (at least 2 branches)
    2. Execute all branches concurrently:
        a. Build branch context (user variables only - isolated from other branches)
        b. Execute branch steps sequentially (like chain)
        c. Track tokens per branch
        d. Respect max_parallel limit via semaphore
    3. Collect all branch results in alphabetical order by branch ID
    4. Optionally execute reduce step with {{ branches.<id>.response }} context
    5. Return RunResult with final response (reduced or aggregated)

Branch Execution:
    - Each branch is independent (no cross-branch context during execution)
    - Steps within a branch execute sequentially with {{ steps[n].response }} access
    - Fail-fast: First branch failure stops all branches (asyncio.gather with return_exceptions=False)

Budget Enforcement:
    - Track cumulative tokens across all branches and reduce step
    - Warn at 80% of budgets.max_tokens
    - Hard stop at 100% (if configured)

Reduce Step:
    - Aggregates all branch outputs via template context
    - Template access: {{ branches.web.response }}, {{ branches['docs'].status }}
    - Branch results ordered alphabetically by branch ID for determinism
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

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
from strands_cli.types import ParallelBranch, PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class ParallelExecutionError(Exception):
    """Raised when parallel execution fails."""

    pass


logger = structlog.get_logger(__name__)


def _build_branch_step_context(
    spec: Spec,
    step_index: int,
    step_history: list[dict[str, Any]],
    user_variables: dict[str, Any],
    step_vars: dict[str, str | int | bool] | None = None,
) -> dict[str, Any]:
    """Build template context for a step within a branch.

    Args:
        spec: Workflow spec
        step_index: Current step index within this branch (0-based)
        step_history: List of prior step results in THIS branch
        user_variables: User-provided variables (spec.inputs.values + CLI --var)
        step_vars: Per-step variable overrides from step.vars

    Returns:
        Template context with steps[], user variables, and step.vars
    """
    context = {}

    # Start with user variables
    context.update(user_variables)

    # Add step history from THIS branch only
    context["steps"] = step_history

    # Add last_response for convenience (most recent step's response)
    if step_history:
        context["last_response"] = step_history[-1]["response"]

    # Add per-step variable overrides
    if step_vars:
        context.update(step_vars)

    return context


async def _execute_branch(
    spec: Spec,
    branch: ParallelBranch,
    user_variables: dict[str, Any],
    cache: AgentCache,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> tuple[str, int]:
    """Execute all steps in a branch sequentially.

    Args:
        spec: Workflow spec
        branch: ParallelBranch configuration
        user_variables: User-provided variables (spec + CLI)
        cache: Shared AgentCache for agent reuse
        max_attempts: Maximum retry attempts per step
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)

    Returns:
        Tuple of (final_response, cumulative_tokens)

    Raises:
        ParallelExecutionError: If any step fails after retries
    """
    step_history: list[dict[str, Any]] = []
    cumulative_tokens = 0

    logger.info(
        "Executing branch",
        branch_id=branch.id,
        num_steps=len(branch.steps),
    )

    for step_index, step in enumerate(branch.steps):
        logger.info(
            "Executing branch step",
            branch_id=branch.id,
            step_index=step_index,
            agent=step.agent,
        )

        # Build context with prior steps in THIS branch
        step_context = _build_branch_step_context(
            spec=spec,
            step_index=step_index,
            step_history=step_history,
            user_variables=user_variables,
            step_vars=step.vars,
        )

        # Render input template
        step_input = render_template(step.input or "", step_context)

        # Build agent for step (using cache to avoid rebuilds)
        if step.agent not in spec.agents:
            raise ParallelExecutionError(
                f"Branch '{branch.id}' step {step_index} references unknown agent '{step.agent}'"
            )

        agent_config = spec.agents[step.agent]

        # Phase 6.2: Inject last N notes into agent context
        injected_notes = None
        if notes_manager and spec.context_policy and spec.context_policy.notes:
            injected_notes = notes_manager.get_last_n_for_injection(
                spec.context_policy.notes.include_last
            )

        agent = await cache.get_or_build_agent(
            spec=spec,
            agent_id=step.agent,
            agent_config=agent_config,
            tool_overrides=step.tool_overrides,
            conversation_manager=context_manager,
            hooks=hooks,
            injected_notes=injected_notes,
            worker_index=None,
        )

        # Execute with retry logic
        try:
            response = await invoke_agent_with_retry(
                agent, step_input, max_attempts, wait_min, wait_max
            )
            response_text = response if isinstance(response, str) else str(response)
        except Exception as e:
            logger.error(
                "Branch step failed",
                branch_id=branch.id,
                step_index=step_index,
                agent=step.agent,
                error=str(e),
            )
            raise ParallelExecutionError(
                f"Branch '{branch.id}' step {step_index} (agent '{step.agent}') failed: {e}"
            ) from e

        # Estimate tokens using shared estimator
        estimated_tokens = estimate_tokens(step_input, response_text)
        cumulative_tokens += estimated_tokens

        # Record step result
        step_result = {
            "index": step_index,
            "agent": step.agent,
            "response": response_text,
            "tokens_estimated": estimated_tokens,
        }
        step_history.append(step_result)

        logger.info(
            "Branch step completed",
            branch_id=branch.id,
            step_index=step_index,
            agent=step.agent,
            tokens_estimated=estimated_tokens,
        )

    # Return final response from last step
    final_response = step_history[-1]["response"]
    logger.info(
        "Branch completed",
        branch_id=branch.id,
        total_steps=len(step_history),
        cumulative_tokens=cumulative_tokens,
    )

    return final_response, cumulative_tokens


async def _execute_reduce_step(
    spec: Spec,
    reduce_config: Any,
    user_vars: dict[str, Any],
    branches_dict: dict[str, dict[str, Any]],
    cache: AgentCache,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> tuple[str, int]:
    """Execute reduce step to aggregate branch results.

    Args:
        spec: Workflow spec
        reduce_config: Reduce step configuration
        user_vars: User-provided variables
        branches_dict: Dictionary of branch results
        cache: Shared AgentCache for agent reuse
        max_attempts: Maximum retry attempts
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)

    Returns:
        Tuple of (reduce_response, tokens_estimated)

    Raises:
        ParallelExecutionError: If reduce step fails
    """
    logger.info("Executing reduce step", agent=reduce_config.agent)

    # Build reduce context with branches dictionary
    reduce_context = {
        **user_vars,
        "branches": branches_dict,
    }

    # Render reduce input
    reduce_input = render_template(reduce_config.input or "", reduce_context)

    # Build reduce agent (using cache to avoid rebuilds)
    if reduce_config.agent not in spec.agents:
        raise ParallelExecutionError(
            f"Reduce step references unknown agent '{reduce_config.agent}'"
        )

    reduce_agent_config = spec.agents[reduce_config.agent]

    # Phase 6.2: Inject last N notes into agent context
    injected_notes = None
    if notes_manager and spec.context_policy and spec.context_policy.notes:
        injected_notes = notes_manager.get_last_n_for_injection(
            spec.context_policy.notes.include_last
        )

    reduce_agent = await cache.get_or_build_agent(
        spec=spec,
        agent_id=reduce_config.agent,
        agent_config=reduce_agent_config,
        tool_overrides=reduce_config.tool_overrides,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=injected_notes,
        worker_index=None,
    )

    # Execute reduce with retry
    try:
        reduce_response = await invoke_agent_with_retry(
            reduce_agent, reduce_input, max_attempts, wait_min, wait_max
        )
        final_response = (
            reduce_response if isinstance(reduce_response, str) else str(reduce_response)
        )

        # Track reduce tokens using shared estimator
        reduce_tokens = estimate_tokens(reduce_input, final_response)

        logger.info(
            "Reduce step completed",
            agent=reduce_config.agent,
            tokens_estimated=reduce_tokens,
        )

        return final_response, reduce_tokens

    except Exception as e:
        logger.error("Reduce step failed", error=str(e))
        raise ParallelExecutionError(f"Reduce step failed: {e}") from e


async def _execute_all_branches_async(
    spec: Spec,
    branches: list[ParallelBranch],
    user_vars: dict[str, Any],
    cache: AgentCache,
    max_parallel: int | None,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> list[tuple[str, int]]:
    """Execute all branches with semaphore control.

    Args:
        spec: Workflow spec
        branches: List of branches to execute
        user_vars: User-provided variables
        cache: Shared AgentCache for agent reuse
        max_parallel: Maximum concurrent branches (None for unlimited)
        max_attempts: Maximum retry attempts per step
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)

    Returns:
        List of (response, tokens) tuples for each branch

    Raises:
        ParallelExecutionError: If any branch fails (fail-fast)
    """
    semaphore = asyncio.Semaphore(max_parallel) if max_parallel else None

    async def _execute_with_semaphore(branch: ParallelBranch) -> tuple[str, int]:
        """Execute branch with semaphore limit."""
        if semaphore:
            async with semaphore:
                return await _execute_branch(
                    spec,
                    branch,
                    user_vars,
                    cache,
                    max_attempts,
                    wait_min,
                    wait_max,
                    context_manager,
                    hooks,
                    notes_manager,
                )
        else:
            return await _execute_branch(
                spec,
                branch,
                user_vars,
                cache,
                max_attempts,
                wait_min,
                wait_max,
                context_manager,
                hooks,
                notes_manager,
            )

    # Execute all branches in parallel (fail-fast with return_exceptions=False)
    results = await asyncio.gather(
        *[_execute_with_semaphore(branch) for branch in branches],
        return_exceptions=False,  # Fail-fast on first error
    )
    return results


async def run_parallel(  # noqa: C901 - Complexity acceptable for multi-branch orchestration
    spec: Spec,
    variables: dict[str, str] | None = None,
) -> RunResult:
    """Execute parallel pattern with concurrent branches.

    Phase 6 Performance Optimization:
    - Async execution with shared AgentCache across all branches and reduce step
    - Single event loop eliminates per-branch loop churn
    - Agents reused when branches use same agent configuration

    Args:
        spec: Validated workflow spec with parallel pattern
        variables: CLI --var overrides

    Returns:
        RunResult with final response (reduced or aggregated)

    Raises:
        ParallelExecutionError: If validation, execution, or reduce fails
    """
    start_time = datetime.now(UTC)

    # Validate configuration
    if not spec.pattern.config.branches or len(spec.pattern.config.branches) < 2:
        raise ParallelExecutionError("Parallel pattern requires at least 2 branches")

    # Get retry configuration
    max_attempts, wait_min, wait_max = get_retry_config(spec)

    # Build user variables (spec.inputs.values + CLI --var)
    user_vars: dict[str, Any] = {}
    if spec.inputs and spec.inputs.get("values"):
        user_vars.update(spec.inputs["values"])
    if variables:
        user_vars.update(variables)

    # Get max_parallel limit
    max_parallel = spec.runtime.max_parallel

    # Get budget configuration
    max_tokens = None
    if spec.runtime.budgets:
        max_tokens = spec.runtime.budgets.get("max_tokens")

    logger.info(
        "Starting parallel execution",
        num_branches=len(spec.pattern.config.branches),
        max_parallel=max_parallel,
        max_tokens=max_tokens,
    )

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

        max_tokens = spec.runtime.budgets["max_tokens"]
        warn_threshold = spec.runtime.budgets.get("warn_threshold", 0.8)
        hooks.append(BudgetEnforcerHook(max_tokens=max_tokens, warn_threshold=warn_threshold))
        logger.info("budget_enforcer_enabled", max_tokens=max_tokens, warn_threshold=warn_threshold)

    # Phase 6.2: Initialize notes manager and hook for structured notes
    notes_manager = None
    step_counter = [0]  # Mutable container for hook to track step count across all branches
    if spec.context_policy and spec.context_policy.notes:
        notes_manager = NotesManager(spec.context_policy.notes.file)

        # Build agent_id → tools mapping for notes hook
        agent_tools: dict[str, list[str]] = {}
        for agent_id, agent_config in spec.agents.items():
            if agent_config.tools:
                agent_tools[agent_id] = agent_config.tools

        hooks.append(NotesAppenderHook(notes_manager, step_counter, agent_tools))
        logger.info("notes_enabled", notes_file=spec.context_policy.notes.file)

    # Create AgentCache for this execution
    cache = AgentCache()

    try:
        # Execute all branches concurrently
        try:
            branch_results = await _execute_all_branches_async(
                spec,
                spec.pattern.config.branches,
                user_vars,
                cache,
                max_parallel,
                max_attempts,
                wait_min,
                wait_max,
                context_manager,
                hooks,
                notes_manager,
            )
        except Exception as e:
            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            logger.error(
                "Parallel execution failed",
                error=str(e),
                duration_seconds=duration,
            )

            return RunResult(
                success=False,
                error=str(e),
                agent_id="parallel",
                pattern_type=PatternType.PARALLEL,
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
            )

        # Build branches dictionary (alphabetically ordered by branch ID)
        branches_dict: dict[str, dict[str, Any]] = {}
        cumulative_tokens = 0

        for branch, (response, tokens) in zip(
            spec.pattern.config.branches, branch_results, strict=True
        ):
            cumulative_tokens += tokens
            branches_dict[branch.id] = {
                "response": response,
                "status": "success",
                "tokens_estimated": tokens,
            }

        logger.info(
            "All branches completed",
            num_branches=len(branches_dict),
            cumulative_tokens=cumulative_tokens,
        )

        # Execute reduce step if present or aggregate branches
        final_response: str
        final_agent_id: str

        if spec.pattern.config.reduce:
            reduce_response, reduce_tokens = await _execute_reduce_step(
                spec,
                spec.pattern.config.reduce,
                user_vars,
                branches_dict,
                cache,
                max_attempts,
                wait_min,
                wait_max,
                context_manager,
                hooks,
                notes_manager,
            )
            final_response = reduce_response
            final_agent_id = spec.pattern.config.reduce.agent
            cumulative_tokens += reduce_tokens
        else:
            # No reduce step - aggregate branch responses alphabetically
            logger.info("No reduce step - aggregating branch responses")

            aggregated_parts = [
                f"Branch {bid}:\n{bdata['response']}"
                for bid, bdata in sorted(branches_dict.items())
            ]
            final_response = "\n\n---\n\n".join(aggregated_parts)
            final_agent_id = "parallel"

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        logger.info(
            "Parallel execution completed",
            duration_seconds=duration,
            cumulative_tokens=cumulative_tokens,
        )

        return RunResult(
            success=True,
            last_response=final_response,
            agent_id=final_agent_id,
            pattern_type=PatternType.PARALLEL,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat(),
            duration_seconds=duration,
            execution_context={"branches": branches_dict},
        )
    finally:
        # Clean up cached resources
        await cache.close()

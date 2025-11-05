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
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.loader import render_template
from strands_cli.runtime import build_agent
from strands_cli.types import ParallelBranch, PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class ParallelExecutionError(Exception):
    """Raised when parallel execution fails."""

    pass


# Transient errors that should trigger retries
_TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
)


logger = structlog.get_logger(__name__)


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
            raise ParallelExecutionError(f"Invalid retry config: retries must be >= 0, got {retries}")

        max_attempts = retries + 1
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            if wait_min > wait_max:
                raise ParallelExecutionError(
                    f"Invalid retry config: wait_min ({wait_min}s) must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


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


def _check_budget_warning(
    cumulative_tokens: int,
    max_tokens: int | None,
    branch_id: str,
) -> None:
    """Check token budget and log warnings.

    Args:
        cumulative_tokens: Total tokens used across all branches so far
        max_tokens: Maximum tokens allowed (from budgets.max_tokens)
        branch_id: Current branch ID for logging
    """
    if max_tokens is None:
        return

    usage_pct = (cumulative_tokens / max_tokens) * 100

    if usage_pct >= 100:
        logger.error(
            "Token budget exceeded",
            cumulative_tokens=cumulative_tokens,
            max_tokens=max_tokens,
            usage_pct=usage_pct,
            branch_id=branch_id,
        )
        raise ParallelExecutionError(
            f"Token budget exceeded: {cumulative_tokens}/{max_tokens} tokens (100%)"
        )
    elif usage_pct >= 80:
        logger.warning(
            "Token budget warning",
            cumulative_tokens=cumulative_tokens,
            max_tokens=max_tokens,
            usage_pct=usage_pct,
            branch_id=branch_id,
        )


async def _execute_branch(
    spec: Spec,
    branch: ParallelBranch,
    user_variables: dict[str, Any],
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[str, int]:
    """Execute all steps in a branch sequentially.

    Args:
        spec: Workflow spec
        branch: ParallelBranch configuration
        user_variables: User-provided variables (spec + CLI)
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

        # Build agent for step
        if step.agent not in spec.agents:
            raise ParallelExecutionError(
                f"Branch '{branch.id}' step {step_index} references unknown agent '{step.agent}'"
            )

        agent_config = spec.agents[step.agent]
        agent = build_agent(
            spec=spec,
            agent_id=step.agent,
            agent_config=agent_config,
            tool_overrides=step.tool_overrides,
        )

        # Execute with retry logic
        @retry(
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            reraise=True,
        )
        async def _invoke_with_retry(agent_instance: Any, input_text: str) -> Any:
            return await agent_instance.invoke_async(input_text)

        try:
            response = await _invoke_with_retry(agent, step_input)
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

        # Estimate tokens (simple word count heuristic)
        estimated_tokens = len(step_input.split()) + len(response_text.split())
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
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[str, int]:
    """Execute reduce step to aggregate branch results.

    Args:
        spec: Workflow spec
        reduce_config: Reduce step configuration
        user_vars: User-provided variables
        branches_dict: Dictionary of branch results
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

    # Build reduce agent
    if reduce_config.agent not in spec.agents:
        raise ParallelExecutionError(
            f"Reduce step references unknown agent '{reduce_config.agent}'"
        )

    reduce_agent_config = spec.agents[reduce_config.agent]
    reduce_agent = build_agent(
        spec=spec,
        agent_id=reduce_config.agent,
        agent_config=reduce_agent_config,
        tool_overrides=reduce_config.tool_overrides,
    )

    # Execute reduce with retry
    @retry(
        retry=retry_if_exception_type(_TRANSIENT_ERRORS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        reraise=True,
    )
    async def _invoke_reduce(agent_instance: Any, input_text: str) -> Any:
        return await agent_instance.invoke_async(input_text)

    try:
        reduce_response = await _invoke_reduce(reduce_agent, reduce_input)
        final_response = reduce_response if isinstance(reduce_response, str) else str(reduce_response)

        # Track reduce tokens
        reduce_tokens = len(reduce_input.split()) + len(final_response.split())

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
    max_parallel: int | None,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> list[tuple[str, int]]:
    """Execute all branches with semaphore control.

    Args:
        spec: Workflow spec
        branches: List of branches to execute
        user_vars: User-provided variables
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
                    spec, branch, user_vars, max_attempts, wait_min, wait_max
                )
        else:
            return await _execute_branch(
                spec, branch, user_vars, max_attempts, wait_min, wait_max
            )

    # Execute all branches in parallel (fail-fast with return_exceptions=False)
    results = await asyncio.gather(
        *[_execute_with_semaphore(branch) for branch in branches],
        return_exceptions=False,  # Fail-fast on first error
    )
    return results


def run_parallel(
    spec: Spec,
    variables: dict[str, str] | None = None,
) -> RunResult:
    """Execute parallel pattern with concurrent branches.

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
    max_attempts, wait_min, wait_max = _get_retry_config(spec)

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

    # Execute all branches concurrently
    try:
        branch_results = asyncio.run(
            _execute_all_branches_async(
                spec,
                spec.pattern.config.branches,
                user_vars,
                max_parallel,
                max_attempts,
                wait_min,
                wait_max,
            )
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

    for branch, (response, tokens) in zip(spec.pattern.config.branches, branch_results, strict=True):
        cumulative_tokens += tokens
        branches_dict[branch.id] = {
            "response": response,
            "status": "success",
            "tokens_estimated": tokens,
        }

    # Check budget after all branches complete
    if max_tokens:
        _check_budget_warning(cumulative_tokens, max_tokens, "all_branches")

    logger.info(
        "All branches completed",
        num_branches=len(branches_dict),
        cumulative_tokens=cumulative_tokens,
    )

    # Execute reduce step if present or aggregate branches
    final_response: str
    final_agent_id: str

    if spec.pattern.config.reduce:
        reduce_response, reduce_tokens = asyncio.run(
            _execute_reduce_step(
                spec,
                spec.pattern.config.reduce,
                user_vars,
                branches_dict,
                max_attempts,
                wait_min,
                wait_max,
            )
        )
        final_response = reduce_response
        final_agent_id = spec.pattern.config.reduce.agent
        cumulative_tokens += reduce_tokens

        # Check budget after reduce
        if max_tokens:
            _check_budget_warning(cumulative_tokens, max_tokens, "reduce")
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

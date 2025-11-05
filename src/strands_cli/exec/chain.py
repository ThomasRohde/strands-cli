"""Multi-step chain executor.

Executes sequential multi-step chains with context passing between steps.
Each step receives the outputs of previous steps via template variables.

Execution Flow:
    1. Validate chain configuration (at least 1 step)
    2. For each step in sequence:
        a. Build template context (prior step responses + user variables + step.vars)
        b. Render step input with Jinja2
        c. Build/reuse agent for step (with optional tool_overrides)
        d. Execute agent asynchronously with retry logic
        e. Track token budget and warn at 80% threshold
        f. Capture step response and timing
    3. Return RunResult with final step response and all step history

Context Threading:
    - Explicit step references: {{ steps[0].response }}, {{ steps[1].response }}
    - Each step receives all prior step outputs in template context
    - Optional per-step variable overrides via step.vars
    - Fail-fast: Stop on first step failure

Budget Enforcement:
    - Track cumulative tokens across all steps
    - Warn at 80% of budgets.max_tokens
    - Hard stop at 100% (if configured)
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
from strands_cli.types import PatternType, RunResult, Spec


class ChainExecutionError(Exception):
    """Raised when chain execution fails."""

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
            raise ChainExecutionError(f"Invalid retry config: retries must be >= 0, got {retries}")

        max_attempts = retries + 1
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            if wait_min > wait_max:
                raise ChainExecutionError(
                    f"Invalid retry config: wait_min ({wait_min}s) must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


def _build_step_context(
    spec: Spec,
    step_index: int,
    step_history: list[dict[str, Any]],
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build template context for a step.

    Args:
        spec: Workflow spec
        step_index: Current step index (0-based)
        step_history: List of prior step results [{response: str, ...}, ...]
        variables: User-provided variables from --var flags

    Returns:
        Template context dictionary with steps[], user variables, and step.vars
    """
    context = {}

    # Add user-provided variables from spec.inputs.values
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])

    # Override with CLI --var variables
    if variables:
        context.update(variables)

    # Add step history as steps[] array
    # Each entry is {response: str, agent: str, index: int}
    context["steps"] = step_history

    # Add per-step variable overrides from step.vars
    if spec.pattern.config.steps is not None:
        step = spec.pattern.config.steps[step_index]
        if step.vars:
            context.update(step.vars)

    return context


def _check_budget_warning(
    cumulative_tokens: int,
    max_tokens: int | None,
    step_index: int,
) -> None:
    """Check token budget and log warnings.

    Args:
        cumulative_tokens: Total tokens used so far
        max_tokens: Maximum tokens allowed (from budgets.max_tokens)
        step_index: Current step index for logging
    """
    if max_tokens is None:
        return

    usage_percent = (cumulative_tokens / max_tokens) * 100

    if usage_percent >= 100:
        logger.error(
            "token_budget_exceeded",
            step=step_index,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_percent=usage_percent,
        )
        raise ChainExecutionError(
            f"Token budget exceeded: {cumulative_tokens}/{max_tokens} tokens (100%)"
        )
    elif usage_percent >= 80:
        logger.warning(
            "token_budget_warning",
            step=step_index,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_percent=f"{usage_percent:.1f}",
        )


def run_chain(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a multi-step chain workflow.

    Executes steps sequentially with context passing. Each step receives
    all prior step responses via {{ steps[n].response }} template variables.

    Args:
        spec: Workflow spec with chain pattern
        variables: Optional CLI --var overrides

    Returns:
        RunResult with final step response and execution metadata

    Raises:
        ChainExecutionError: If chain execution fails at any step
    """
    logger.info("chain_execution_start", spec_name=spec.name)

    if not spec.pattern.config.steps:
        raise ChainExecutionError("Chain pattern has no steps")

    # Get retry config
    max_attempts, wait_min, wait_max = _get_retry_config(spec)

    # Track execution state
    step_history: list[dict[str, Any]] = []
    cumulative_tokens = 0
    max_tokens = None
    if spec.runtime.budgets:
        max_tokens = spec.runtime.budgets.get("max_tokens")

    started_at = datetime.now(UTC).isoformat()

    # Execute each step sequentially
    for step_index, step in enumerate(spec.pattern.config.steps):
        logger.info(
            "chain_step_start",
            step=step_index,
            total_steps=len(spec.pattern.config.steps),
            agent=step.agent,
        )

        # Build context with prior step responses
        template_context = _build_step_context(spec, step_index, step_history, variables)

        # Render step input (default to empty if not provided)
        step_input_template = step.input or ""
        try:
            step_input = render_template(step_input_template, template_context)
        except Exception as e:
            raise ChainExecutionError(f"Failed to render step {step_index} input: {e}") from e

        # Get the correct agent config for this step (Phase 2: support multi-agent chains)
        step_agent_id = step.agent
        if step_agent_id not in spec.agents:
            raise ChainExecutionError(
                f"Step {step_index} references unknown agent '{step_agent_id}'"
            )
        step_agent_config = spec.agents[step_agent_id]

        # Build agent for this step (with optional tool overrides)
        try:
            # Use step's tool_overrides if provided, else use agent's tools
            tools_for_step = step.tool_overrides if step.tool_overrides else None
            agent = build_agent(
                spec, step_agent_id, step_agent_config, tool_overrides=tools_for_step
            )
        except Exception as e:
            raise ChainExecutionError(f"Failed to build agent for step {step_index}: {e}") from e

        # Execute with retry logic
        async def _execute_step(agent_instance: Any, input_text: str) -> Any:
            from strands_cli.utils import suppress_stdout

            with suppress_stdout():
                return await agent_instance.invoke_async(input_text)

        retry_decorator = retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(min=wait_min, max=wait_max),
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            reraise=True,
        )
        _execute_step_with_retry = retry_decorator(_execute_step)

        try:
            step_response = asyncio.run(_execute_step_with_retry(agent, step_input))
        except _TRANSIENT_ERRORS as e:
            error_msg = f"Step {step_index} failed after {max_attempts} attempts: {e}"
            logger.error("chain_step_failed", step=step_index, error=str(e))
            raise ChainExecutionError(error_msg) from e
        except Exception as e:
            error_msg = f"Step {step_index} failed: {e}"
            logger.error("chain_step_failed", step=step_index, error=str(e))
            raise ChainExecutionError(error_msg) from e

        # Extract response text
        response_text = step_response if isinstance(step_response, str) else str(step_response)

        # Track token usage (estimate based on response length)
        # TODO: Get actual token counts from provider when available
        estimated_tokens = len(step_input.split()) + len(response_text.split())
        cumulative_tokens += estimated_tokens

        # Check budget and warn if needed
        if max_tokens:
            _check_budget_warning(cumulative_tokens, max_tokens, step_index)

        # Record step result
        step_result = {
            "index": step_index,
            "agent": step.agent,
            "response": response_text,
            "tokens_estimated": estimated_tokens,
        }
        step_history.append(step_result)

        logger.info(
            "chain_step_complete",
            step=step_index,
            response_length=len(response_text),
            cumulative_tokens=cumulative_tokens,
        )

    completed_at = datetime.now(UTC).isoformat()
    started_dt = datetime.fromisoformat(started_at)
    completed_dt = datetime.fromisoformat(completed_at)
    duration = (completed_dt - started_dt).total_seconds()

    # Final response is from last step
    final_response = step_history[-1]["response"]
    # Agent ID is from the last step that produced the final response
    final_agent_id = step_history[-1]["agent"]

    logger.info(
        "chain_execution_complete",
        spec_name=spec.name,
        steps_executed=len(step_history),
        duration_seconds=duration,
        cumulative_tokens=cumulative_tokens,
    )

    return RunResult(
        success=True,
        last_response=final_response,
        error=None,
        agent_id=final_agent_id,
        pattern_type=PatternType.CHAIN,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        artifacts_written=[],
        execution_context={"steps": step_history},
    )

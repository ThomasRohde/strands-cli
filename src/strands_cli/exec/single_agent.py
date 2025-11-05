"""Single-agent workflow executor.

Executes single-agent workflows with retry logic and error handling.
Supports both chain and workflow patterns (limited to 1 step/task).

Execution Flow:
    1. Extract agent and pattern configuration
    2. Render task input with Jinja2 template (inject variables)
    3. Build Strands Agent with tools and model
    4. Execute agent asynchronously with retry logic
    5. Capture response and timing information
    6. Return RunResult with success/error status

Retry Strategy:
    - Exponential backoff for transient errors (timeout, connection)
    - Configurable via spec.runtime.failure_policy
    - Default: 3 attempts, 1s-60s backoff
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
from strands_cli.telemetry import get_tracer
from strands_cli.types import PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class ExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


# Transient errors that should trigger retries
_TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
    # Add provider-specific transient errors as needed
)


def _get_retry_config(spec: Spec) -> tuple[int, int, int]:
    """Get retry configuration from spec.

    Extracts retry policy from spec.runtime.failure_policy or uses defaults.
    Supports exponential backoff configuration.

    Args:
        spec: Workflow spec with optional failure_policy

    Returns:
        Tuple of (max_attempts, wait_min, wait_max) in seconds

    Raises:
        ExecutionError: If retry configuration is invalid
    """
    # Default retry config
    max_attempts = 3
    wait_min = 1
    wait_max = 60

    if spec.runtime.failure_policy:
        policy = spec.runtime.failure_policy
        retries = policy.get("retries", max_attempts - 1)

        # Validation: retries must be non-negative
        if retries < 0:
            raise ExecutionError(f"Invalid retry config: retries must be >= 0, got {retries}")

        max_attempts = retries + 1  # +1 for initial attempt
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            # Validation: wait_min must be <= wait_max
            if wait_min > wait_max:
                raise ExecutionError(
                    f"Invalid retry config: wait_min ({wait_min}s) must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


def run_single_agent(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a single-agent workflow.

    Complete execution workflow:
    1. Extract agent configuration and pattern details
    2. Render task input using Jinja2 with variables from spec.inputs.values
    3. Build Strands Agent with model, tools, and system prompt
    4. Configure retry policy from spec.runtime.failure_policy
    5. Execute agent asynchronously with exponential backoff retry
    6. Capture timing (start, end, duration) and response
    7. Return RunResult with success status and artifacts

    Args:
        spec: Validated workflow spec (must pass capability check first)
        variables: Optional variables from CLI (already merged into spec.inputs)

    Returns:
        RunResult with:
        - success: True if agent executed without errors
        - last_response: Agent's final output (for artifact templating)
        - error: Error message if execution failed
        - Timing information (started_at, completed_at, duration_seconds)

    Raises:
        ExecutionError: If pattern is unsupported, template rendering fails,
                       or agent construction fails (not for agent runtime errors)
    """
    tracer = get_tracer(__name__)
    logger = structlog.get_logger(__name__)
    started_at = datetime.now(UTC)

    with tracer.start_span("run_single_agent"):
        # Extract normalized values (assuming capability check passed)
        agent_id = next(iter(spec.agents.keys()))
        agent_config = spec.agents[agent_id]

        logger.info(
            "workflow_started",
            workflow_name=spec.name,
            agent_id=agent_id,
            pattern=spec.pattern.type.value,
            provider=spec.runtime.provider.value,
        )

        # Extract pattern info
        if spec.pattern.type == PatternType.CHAIN:
            step = spec.pattern.config.steps[0]  # type: ignore
            task_input_template = step.input
        elif spec.pattern.type == PatternType.WORKFLOW:
            task = spec.pattern.config.tasks[0]  # type: ignore
            task_input_template = task.input
        else:
            raise ExecutionError(f"Unsupported pattern type: {spec.pattern.type}")

        # Build template variables
        template_vars = {}
        if spec.inputs and spec.inputs.get("values"):
            template_vars.update(spec.inputs["values"])

        # Render task input
        try:
            task_input = render_template(task_input_template or "", template_vars)
        except Exception as e:
            raise ExecutionError(f"Failed to render task input: {e}") from e

        # Build the agent
        try:
            agent = build_agent(spec, agent_id, agent_config)
        except Exception as e:
            raise ExecutionError(f"Failed to build agent: {e}") from e

        # Get retry configuration
        max_attempts, wait_min, wait_max = _get_retry_config(spec)

        # Execute with retries
        # Uses tenacity for exponential backoff on transient errors (timeout, connection)
        @retry(
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=wait_min, max=wait_max),
            reraise=True,
        )
        async def _execute_agent() -> AgentResult:
            """Execute agent with retry logic."""
            from strands_cli.utils import capture_and_display_stdout

            with tracer.start_span("agent_invoke"):
                # Invoke the agent asynchronously
                with capture_and_display_stdout():
                    response = await agent.invoke_async(task_input)
                return response

        # Run the agent
        # asyncio.run() creates new event loop for this execution
        try:
            logger.debug(
                "agent_execution_started", agent_id=agent_id, task_input_length=len(task_input)
            )
            response = asyncio.run(_execute_agent())
        except Exception as e:
            completed_at = datetime.now(UTC)
            duration = (completed_at - started_at).total_seconds()

            logger.error(
                "workflow_failed",
                workflow_name=spec.name,
                agent_id=agent_id,
                error=str(e),
                duration_s=duration,
            )

            return RunResult(
                success=False,
                error=str(e),
                agent_id=agent_id,
                pattern_type=spec.pattern.type,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_seconds=duration,
            )

        # Extract last response
        # Strands Agent.invoke_async() returns a string or Response object
        last_response = response if isinstance(response, str) else str(response)

        completed_at = datetime.now(UTC)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            "workflow_completed",
            workflow_name=spec.name,
            agent_id=agent_id,
            duration_s=duration,
            response_length=len(last_response),
        )

        return RunResult(
            success=True,
            last_response=last_response,
            agent_id=agent_id,
            pattern_type=spec.pattern.type,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=duration,
        )

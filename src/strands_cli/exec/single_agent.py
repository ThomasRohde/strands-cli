"""Single-agent workflow executor.

Executes single-agent workflows with retry logic and error handling.
Supports both chain and workflow patterns (limited to 1 step/task).

Execution Flow:
    1. Extract agent and pattern configuration
    2. Render task input with Jinja2 template (inject variables)
    3. Get or build Strands Agent with tools and model (via AgentCache)
    4. Execute agent asynchronously with retry logic
    5. Capture response and timing information
    6. Return RunResult with success/error status

Phase 3 Optimizations:
    - Converted to async function to eliminate per-call event loop creation
    - Integrated AgentCache to enable agent reuse (preparation for future multi-step)
    - Proper cleanup of HTTP clients via AgentCache.close()

Retry Strategy:
    - Exponential backoff for transient errors (timeout, connection)
    - Configurable via spec.runtime.failure_policy
    - Default: 3 attempts, 1s-60s backoff
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from strands_cli.exec.utils import AgentCache, get_retry_config, invoke_agent_with_retry
from strands_cli.loader import render_template
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


async def run_single_agent(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a single-agent workflow asynchronously.

    Complete execution workflow:
    1. Extract agent configuration and pattern details
    2. Render task input using Jinja2 with variables from spec.inputs.values
    3. Get or build Strands Agent with model, tools, and system prompt (via AgentCache)
    4. Configure retry policy from spec.runtime.failure_policy
    5. Execute agent asynchronously with exponential backoff retry
    6. Capture timing (start, end, duration) and response
    7. Clean up HTTP clients and cached resources
    8. Return RunResult with success status and artifacts

    Phase 3 Changes:
    - Converted to async function (no more asyncio.run() inside executor)
    - Added AgentCache for agent reuse and proper cleanup
    - HTTP clients properly closed in finally block

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
        # Extract pattern info and determine which agent to use
        # Use the agent referenced in the step/task, not just the first agent in the spec
        if spec.pattern.type == PatternType.CHAIN:
            assert spec.pattern.config.steps is not None, "Chain pattern must have steps"
            step = spec.pattern.config.steps[0]
            agent_id = step.agent
            task_input_template = step.input
        elif spec.pattern.type == PatternType.WORKFLOW:
            assert spec.pattern.config.tasks is not None, "Workflow pattern must have tasks"
            task = spec.pattern.config.tasks[0]
            agent_id = task.agent
            task_input_template = task.input
        else:
            raise ExecutionError(f"Unsupported pattern type: {spec.pattern.type}")

        # Validate agent exists and get configuration
        if agent_id not in spec.agents:
            raise ExecutionError(
                f"Agent '{agent_id}' referenced by {spec.pattern.type} not found in agents map"
            )
        agent_config = spec.agents[agent_id]

        logger.info(
            "workflow_started",
            workflow_name=spec.name,
            agent_id=agent_id,
            pattern=spec.pattern.type.value,
            provider=spec.runtime.provider.value,
        )

        # Build template variables
        # Start with spec inputs, then merge CLI variables so CLI overrides win
        template_vars = {}
        if spec.inputs and spec.inputs.get("values"):
            template_vars.update(spec.inputs["values"])
        if variables:
            template_vars.update(variables)

        # Render task input
        try:
            task_input = render_template(task_input_template or "", template_vars)
        except Exception as e:
            raise ExecutionError(f"Failed to render task input: {e}") from e

        # Get retry configuration
        max_attempts, wait_min, wait_max = get_retry_config(spec)

        # Create agent cache for this execution
        # Phase 3: Single executor-scoped cache (cleanup in finally)
        cache = AgentCache()
        try:
            # Get or build the agent (cache enables future multi-step reuse)
            agent = await cache.get_or_build_agent(spec, agent_id, agent_config)

            # Run the agent with retry logic
            # Phase 3: Direct await instead of asyncio.run() (no event loop churn)
            logger.debug(
                "agent_execution_started", agent_id=agent_id, task_input_length=len(task_input)
            )
            with tracer.start_span("agent_invoke"):
                response = await invoke_agent_with_retry(
                    agent, task_input, max_attempts, wait_min, wait_max
                )
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
        finally:
            # Phase 3: Cleanup HTTP clients and cached resources
            await cache.close()

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

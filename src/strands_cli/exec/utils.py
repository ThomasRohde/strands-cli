"""Shared execution utilities for all pattern executors.

Provides common helpers for retry configuration, budget tracking,
and agent execution patterns used across chain, workflow, routing,
parallel, and single-agent executors.

This module eliminates code duplication across executors and ensures
consistent behavior for retry logic, budget enforcement, and error handling.

Phase 2 Additions:
    - AgentCache: Executor-scoped agent caching to eliminate redundant builds
"""

from typing import Any

import structlog
from strands.agent import Agent
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.runtime.strands_adapter import build_agent
from strands_cli.runtime.tools import HttpExecutorAdapter
from strands_cli.types import Agent as AgentConfig
from strands_cli.types import Spec

logger = structlog.get_logger(__name__)

# Transient errors that should trigger retries across all executors
TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
)


class ExecutionUtilsError(Exception):
    """Raised when execution utility operations fail."""

    pass


def get_retry_config(spec: Spec) -> tuple[int, int, int]:
    """Get retry configuration from spec.

    Extracts retry policy from spec.runtime.failure_policy or uses defaults.
    Used by all executors for consistent retry behavior.

    Args:
        spec: Workflow spec with optional failure_policy

    Returns:
        Tuple of (max_attempts, wait_min, wait_max) in seconds

    Raises:
        ExecutionUtilsError: If retry configuration is invalid
    """
    max_attempts = 3
    wait_min = 1
    wait_max = 60

    if spec.runtime.failure_policy:
        policy = spec.runtime.failure_policy
        retries = policy.get("retries", max_attempts - 1)

        if retries < 0:
            raise ExecutionUtilsError(f"Invalid retry config: retries must be >= 0, got {retries}")

        max_attempts = retries + 1
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            if wait_min > wait_max:
                raise ExecutionUtilsError(
                    f"Invalid retry config: wait_min ({wait_min}s) "
                    f"must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


def check_budget_threshold(
    cumulative_tokens: int,
    max_tokens: int | None,
    context_id: str,
    warn_threshold: float = 0.8,
) -> None:
    """Check token budget and log warnings or raise on exceed.

    Args:
        cumulative_tokens: Total tokens used so far
        max_tokens: Maximum tokens allowed (from budgets.max_tokens)
        context_id: Identifier for logging (step, task, branch)
        warn_threshold: Threshold for warning (default 0.8 = 80%)

    Raises:
        ExecutionUtilsError: If budget exceeded (100%)
    """
    if max_tokens is None:
        return

    usage_pct = (cumulative_tokens / max_tokens) * 100

    if usage_pct >= 100:
        logger.error(
            "token_budget_exceeded",
            context=context_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_pct=usage_pct,
        )
        raise ExecutionUtilsError(
            f"Token budget exceeded: {cumulative_tokens}/{max_tokens} tokens (100%)"
        )
    elif usage_pct >= (warn_threshold * 100):
        logger.warning(
            "token_budget_warning",
            context=context_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_pct=f"{usage_pct:.1f}",
            threshold=f"{warn_threshold * 100:.0f}%",
        )


def create_retry_decorator(
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> Any:
    """Create a retry decorator with exponential backoff.

    Centralizes retry decorator creation for consistent behavior
    across all executors.

    Args:
        max_attempts: Maximum number of attempts
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds

    Returns:
        Configured retry decorator from tenacity
    """
    return retry(
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        reraise=True,
    )


async def invoke_agent_with_retry(
    agent: Any,
    input_text: str,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> Any:
    """Invoke an agent asynchronously with retry logic.

    Wraps agent invocation with stdout capture and retry handling.
    Used across all executors for consistent agent execution.

    Args:
        agent: Strands Agent instance
        input_text: Input prompt for the agent
        max_attempts: Maximum retry attempts
        wait_min: Minimum backoff wait (seconds)
        wait_max: Maximum backoff wait (seconds)

    Returns:
        Agent response (string or AgentResult)

    Raises:
        TRANSIENT_ERRORS: After all retry attempts exhausted
        Exception: For non-transient errors (fail immediately)
    """
    from strands_cli.utils import capture_and_display_stdout

    retry_decorator = create_retry_decorator(max_attempts, wait_min, wait_max)

    @retry_decorator  # type: ignore[misc]
    async def _execute() -> Any:
        with capture_and_display_stdout():
            return await agent.invoke_async(input_text)

    return await _execute()


def estimate_tokens(input_text: str, output_text: str) -> int:
    """Estimate token count from text (simple word-based heuristic).

    This is a simple estimation based on word count. In production,
    this should be replaced with actual token counting from the provider.

    Args:
        input_text: Input prompt
        output_text: Agent response

    Returns:
        Estimated token count
    """
    return len(input_text.split()) + len(output_text.split())


class AgentCache:
    """Executor-scoped agent cache to eliminate redundant builds.

    Phase 2 Performance Optimization:
    Caches agents by (agent_id, frozenset(tool_ids)) to reuse agent instances
    across multiple steps/tasks in the same workflow execution. This eliminates
    redundant model client creation and agent initialization overhead.

    Key Features:
    - Cache keying: (agent_id, frozenset(tool_ids)) ensures correct reuse
    - Tool tracking: Maintains separate tool instances for cleanup
    - Async cleanup: Properly closes HTTP executor clients on workflow completion
    - Observability: Logs cache hits/misses for debugging

    Lifecycle:
    1. Created at start of executor (run_chain, run_workflow, etc.)
    2. Used via get_or_build_agent() for each step/task
    3. Cleaned up via close() in finally block

    Example:
        cache = AgentCache()
        try:
            agent = await cache.get_or_build_agent(spec, "agent-1", agent_config)
            result = await agent.invoke_async(prompt)
        finally:
            await cache.close()
    """

    def __init__(self) -> None:
        """Initialize empty agent cache."""
        # Cache key: (agent_id, frozenset(tool_ids)) -> Agent instance
        self._agents: dict[tuple[str, frozenset[str]], Agent] = {}

        # Track HTTP executor tools separately for cleanup
        # Key: executor ID -> HttpExecutorAdapter instance
        self._http_executors: dict[str, HttpExecutorAdapter] = {}

        logger.debug("agent_cache_initialized")

    async def get_or_build_agent(
        self,
        spec: Spec,
        agent_id: str,
        agent_config: AgentConfig,
        tool_overrides: list[str] | None = None,
    ) -> Agent:
        """Get cached agent or build new one.

        Checks cache for existing agent with matching (agent_id, tools).
        If found, returns cached instance (cache hit). Otherwise, builds
        new agent and caches it (cache miss).

        Args:
            spec: Full workflow spec for agent construction
            agent_id: Agent identifier from spec.agents
            agent_config: Agent configuration
            tool_overrides: Optional tool ID list (overrides agent_config.tools)

        Returns:
            Cached or newly-built Agent instance

        Raises:
            AdapterError: If agent build fails (from build_agent)
        """
        # Determine which tools this agent uses
        tools_to_use = tool_overrides if tool_overrides is not None else agent_config.tools
        tools_key = frozenset(tools_to_use) if tools_to_use else frozenset()

        # Create cache key
        cache_key = (agent_id, tools_key)

        # Check cache
        if cache_key in self._agents:
            logger.debug(
                "agent_cache_hit",
                agent_id=agent_id,
                tools=sorted(tools_key) if tools_key else None,
            )
            return self._agents[cache_key]

        # Cache miss - build new agent
        logger.debug(
            "agent_cache_miss",
            agent_id=agent_id,
            tools=sorted(tools_key) if tools_key else None,
        )

        agent = build_agent(spec, agent_id, agent_config, tool_overrides=tool_overrides)

        # Cache the agent
        self._agents[cache_key] = agent

        # Track HTTP executors for cleanup (extract from agent.tools)
        if hasattr(agent, "tools") and agent.tools:
            for tool in agent.tools:
                if (
                    isinstance(tool, HttpExecutorAdapter)
                    and hasattr(tool, "config")
                    and hasattr(tool.config, "id")
                ):
                    # Use HTTP executor's config.id as key
                    self._http_executors[tool.config.id] = tool

        return agent

    async def close(self) -> None:
        """Clean up cached resources.

        Closes all HTTP executor clients to release sockets and prevent
        resource leaks. Should be called in finally block of executor.

        This is critical for long-running workflows with many agents/tools
        to avoid socket exhaustion.
        """
        logger.debug(
            "agent_cache_cleanup",
            cached_agents=len(self._agents),
            http_executors=len(self._http_executors),
        )

        # Close all HTTP executor clients
        for executor_id, executor in self._http_executors.items():
            try:
                executor.close()
                logger.debug("http_executor_closed", executor_id=executor_id)
            except Exception as e:
                logger.warning(
                    "http_executor_cleanup_failed",
                    executor_id=executor_id,
                    error=str(e),
                )

        # Clear caches
        self._agents.clear()
        self._http_executors.clear()

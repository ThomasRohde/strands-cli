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

# Phase 9: Import MCPClient for instance checking and cleanup
try:
    from strands.tools.mcp import MCPClient

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCPClient = None  # type: ignore

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.runtime.strands_adapter import build_agent
from strands_cli.tools.http_executor_factory import close_http_executor_tool
from strands_cli.types import Agent as AgentConfig
from strands_cli.types import Spec

logger = structlog.get_logger(__name__)

# Token budget warning threshold (warn at 80% usage)
TOKEN_WARNING_THRESHOLD = 0.8

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
        # Cache key: (agent_id, frozenset(tool_ids), conversation_manager_type, worker_index) -> Agent instance
        # Notes are injected at invocation time (not build time), so they don't affect caching
        # Worker index ensures isolation for orchestrator-workers pattern
        self._agents: dict[
            tuple[str, frozenset[str], str | None, int | None], Agent
        ] = {}

        # Track HTTP executor tool modules separately for cleanup
        # Key: executor ID -> Module with _http_client
        self._http_executors: dict[str, Any] = {}

        # Track MCP clients for proper cleanup (Phase 9)
        # Dict: server_id -> MCPClient instance (deduplicated)
        self._mcp_clients: dict[str, Any] = {}

        logger.debug("agent_cache_initialized")

    async def get_or_build_agent(
        self,
        spec: Spec,
        agent_id: str,
        agent_config: AgentConfig,
        tool_overrides: list[str] | None = None,
        conversation_manager: Any | None = None,
        hooks: list[Any] | None = None,
        injected_notes: str | None = None,
        worker_index: int | None = None,
    ) -> Agent:
        """Get cached agent or build new one.

        Checks cache for existing agent with matching (agent_id, tools, conversation_manager_type, worker_index).
        If found, returns cached instance (cache hit). Otherwise, builds
        new agent and caches it (cache miss).

        Note: injected_notes is passed through to build_agent but NOT included in cache key,
        as notes change per step. Agents are cached by identity and tools only.

        Args:
            spec: Full workflow spec for agent construction
            agent_id: Agent identifier from spec.agents
            agent_config: Agent configuration
            tool_overrides: Optional tool ID list (overrides agent_config.tools)
            conversation_manager: Optional conversation manager for context compaction
            hooks: Optional list of hooks (e.g., ProactiveCompactionHook, NotesAppenderHook)
            injected_notes: Optional Markdown notes from previous steps (Phase 6.2)
            worker_index: Optional worker index for orchestrator-workers pattern isolation

        Returns:
            Cached or newly-built Agent instance

        Raises:
            AdapterError: If agent build fails (from build_agent)
        """
        # Determine which tools this agent uses
        tools_to_use = tool_overrides if tool_overrides is not None else agent_config.tools
        tools_key = frozenset(tools_to_use) if tools_to_use else frozenset()

        # Include conversation manager type in cache key to prevent collisions
        cm_type = type(conversation_manager).__name__ if conversation_manager else None

        # Create cache key including worker_index for orchestrator-workers isolation
        # Notes are excluded - they're injected at invocation time, not build time
        cache_key = (agent_id, tools_key, cm_type, worker_index)

        # Check cache
        if cache_key in self._agents:
            logger.debug(
                "agent_cache_hit",
                agent_id=agent_id,
                tools=sorted(tools_key) if tools_key else None,
                conversation_manager=cm_type,
                worker_index=worker_index,
            )
            return self._agents[cache_key]

        # Cache miss - build new agent
        logger.debug(
            "agent_cache_miss",
            agent_id=agent_id,
            tools=sorted(tools_key) if tools_key else None,
            conversation_manager=cm_type,
            worker_index=worker_index,
        )

        # Pass self to build_agent so it can track MCP clients
        agent = build_agent(
            spec,
            agent_id,
            agent_config,
            tool_overrides=tool_overrides,
            conversation_manager=conversation_manager,
            hooks=hooks,
            injected_notes=injected_notes,
            agent_cache=self,  # Pass cache for MCP client tracking
        )

        # Cache the agent
        self._agents[cache_key] = agent

        # Track HTTP executor tool modules for cleanup (extract from agent.tools)
        # Note: MCP clients are tracked in build_agent before Agent construction
        if hasattr(agent, "tools") and agent.tools:
            logger.debug(
                "inspecting_agent_tools",
                agent_id=agent_id,
                tool_count=len(agent.tools),
                tool_types=[type(t).__name__ for t in agent.tools],
            )
            for tool in agent.tools:
                # Check for module-based HTTP executor tools (created by factory)
                if (
                    hasattr(tool, "TOOL_SPEC")
                    and hasattr(tool, "_http_client")
                    and hasattr(tool, "_http_config")
                ):
                    # Extract executor ID from config
                    executor_id = tool._http_config.id
                    self._http_executors[executor_id] = tool

        return agent

    async def close(self) -> None:
        """Clean up cached resources.

        Closes all HTTP executor clients and MCP server connections to release
        sockets and prevent resource leaks. Should be called in finally block of executor.

        Phase 9: MCP clients need explicit cleanup despite ToolProvider interface.
        Without this, MCP server processes remain running and the program hangs.

        This is critical for long-running workflows with many agents/tools
        to avoid socket exhaustion and hanging processes.
        """
        logger.debug(
            "agent_cache_cleanup",
            cached_agents=len(self._agents),
            http_executors=len(self._http_executors),
            mcp_clients=len(self._mcp_clients),
        )

        # Phase 9: Stop MCP clients FIRST (before HTTP cleanup)
        # MCP servers may use HTTP internally (streamable_http transport)
        # Closing HTTP clients first could break MCP cleanup
        for server_id, mcp_client in self._mcp_clients.items():
            try:
                # MCPClient uses context manager protocol - call __exit__ with None args
                if hasattr(mcp_client, "__exit__"):
                    mcp_client.__exit__(None, None, None)
                    logger.debug("mcp_client_stopped", server_id=server_id)
                elif hasattr(mcp_client, "stop"):
                    # Fallback: try stop() with context manager args
                    mcp_client.stop(None, None, None)
                    logger.debug("mcp_client_stopped", server_id=server_id)
            except Exception as e:
                logger.warning(
                    "mcp_client_stop_failed",
                    server_id=server_id,
                    error=str(e),
                )

        # THEN close HTTP executor tool modules (after MCP cleanup)
        for executor_id, tool_module in self._http_executors.items():
            try:
                close_http_executor_tool(tool_module)
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
        self._mcp_clients.clear()

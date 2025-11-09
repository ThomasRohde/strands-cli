"""Strands agent adapter — map workflow Spec to Strands Agent.

Transforms validated workflow specifications into executable Strands Agent instances.
Handles:

1. System prompt construction (agent prompt + skills + runtime context)
2. Model client creation (provider-specific)
3. Tool loading and validation (Python callables, HTTP executors)
4. Agent assembly with Strands SDK

The adapter pattern isolates Strands SDK specifics from workflow spec logic,
making it easier to support alternative agent frameworks in the future.
"""

import os
from typing import Any

from strands.agent import Agent

# Phase 9: MCP integration using Strands SDK native support
try:
    from mcp import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCPClient = None  # type: ignore
    stdio_client = None  # type: ignore
    streamablehttp_client = None  # type: ignore
    StdioServerParameters = None  # type: ignore

from strands_cli.runtime.providers import create_model
from strands_cli.runtime.tools import load_python_callable
from strands_cli.tools import get_registry
from strands_cli.tools.http_executor_factory import create_http_executor_tool
from strands_cli.types import Agent as AgentConfig
from strands_cli.types import Spec


class AdapterError(Exception):
    """Raised when agent construction fails."""

    pass


def build_system_prompt(
    agent_config: AgentConfig, spec: Spec, agent_id: str, injected_notes: str | None = None
) -> str:
    """Build the system prompt for an agent.

    Combines multiple sources into a comprehensive system prompt:
    1. Agent's base prompt (agent.prompt) - core instructions
    2. Structured notes (optional) - previous workflow steps for continuity
    3. Skills metadata injection - available tools/capabilities
    4. Runtime banner - workflow context, budgets, tags

    Skills are injected as metadata only (id, path, description).
    No code execution occurs; this provides context to the LLM.

    Args:
        agent_config: Agent configuration from spec.agents[agent_id]
        spec: Full workflow spec for context
        agent_id: ID of this agent
        injected_notes: Optional Markdown notes from previous steps (Phase 6.2)

    Returns:
        Complete system prompt for agent initialization
    """
    sections = []

    # 1. Base agent prompt
    sections.append(agent_config.prompt)

    # 2. Structured notes injection (Phase 6.2)
    if injected_notes:
        sections.append(f"\n# Previous Workflow Steps\n{injected_notes}")

    # 3. Skills metadata injection
    if spec.skills:
        skills_lines = ["", "# Available Skills", ""]
        for skill in spec.skills:
            skill_line = f"- **{skill.id}**"
            if skill.path:
                skill_line += f" (path: `{skill.path}`)"
            if skill.description:
                skill_line += f": {skill.description}"
            skills_lines.append(skill_line)
        sections.append("\n".join(skills_lines))

    # 4. Runtime banner
    banner_lines = ["", "# Runtime Context", ""]
    banner_lines.append(f"- **Workflow:** {spec.name}")
    if spec.description:
        banner_lines.append(f"- **Description:** {spec.description}")
    if spec.tags:
        banner_lines.append(f"- **Tags:** {', '.join(spec.tags)}")
    banner_lines.append(f"- **Agent ID:** {agent_id}")

    # Budgets (logged only)
    if spec.runtime.budgets:
        banner_lines.append("- **Budgets:**")
        for key, value in spec.runtime.budgets.items():
            banner_lines.append(f"  - {key}: {value}")

    sections.append("\n".join(banner_lines))

    return "\n\n".join(sections)


def _load_python_tools(
    spec: Spec, tools_to_use: list[str] | None, loaded_tool_ids: set[str] | None = None
) -> list[Any]:
    """Load Python callable tools based on spec and filter.

    Args:
        spec: Workflow spec containing tool definitions
        tools_to_use: Optional list of tool IDs to filter by
        loaded_tool_ids: Set of tool IDs already loaded from native registry (to avoid duplicates)

    Returns:
        List of loaded Python callable objects

    Raises:
        AdapterError: If tool loading fails
    """
    if loaded_tool_ids is None:
        loaded_tool_ids = set()

    tools: list[Any] = []
    if spec.tools and spec.tools.python:
        for py_tool in spec.tools.python:
            # Skip if tool was already loaded from native registry
            if py_tool.callable in loaded_tool_ids:
                continue

            if tools_to_use is None or py_tool.callable in tools_to_use:
                try:
                    callable_obj = load_python_callable(py_tool.callable)
                    tools.append(callable_obj)
                except Exception as e:
                    raise AdapterError(
                        f"Failed to load Python tool '{py_tool.callable}': {e}"
                    ) from e
    return tools


def _load_http_executors(spec: Spec, tools_to_use: list[str] | None) -> list[Any]:
    """Load HTTP executor tools based on spec and filter.

    Args:
        spec: Workflow spec containing HTTP executor definitions
        tools_to_use: Optional list of tool IDs to filter by

    Returns:
        List of Strands SDK-compatible HTTP executor tool modules

    Raises:
        AdapterError: If executor creation fails
    """
    tools = []
    if spec.tools and spec.tools.http_executors:
        for http_exec in spec.tools.http_executors:
            if tools_to_use is None or http_exec.id in tools_to_use:
                try:
                    # Create Strands SDK-compatible module-based tool with secret resolution
                    tool_module = create_http_executor_tool(http_exec, spec)
                    tools.append(tool_module)
                except Exception as e:
                    raise AdapterError(
                        f"Failed to create HTTP executor '{http_exec.id}': {e}"
                    ) from e
    return tools


def _load_native_tools(tools_to_use: list[str] | None) -> list[Any]:
    """Load native tools from the registry.

    Native tools are auto-discovered via TOOL_SPEC exports and include
    JIT retrieval tools (grep, head, tail, search).

    Args:
        tools_to_use: Optional list of tool IDs to filter by

    Returns:
        List of loaded native tool module objects

    Raises:
        AdapterError: If tool loading fails
    """
    import importlib

    tools: list[Any] = []
    if tools_to_use is None:
        return tools

    registry = get_registry()
    for tool_id in tools_to_use:
        tool_info = registry.get(tool_id)
        if tool_info:
            try:
                # Import the actual module
                module = importlib.import_module(tool_info.module_path)
                tools.append(module)
            except Exception as e:
                raise AdapterError(
                    f"Failed to load native tool '{tool_id}' from '{tool_info.module_path}': {e}"
                ) from e

    return tools


def _load_mcp_tools(spec: Spec, tools_to_use: list[str] | None) -> list[tuple[str, Any]]:
    """Load MCP server tools using Strands SDK MCPClient.

    Phase 9: Uses native Strands SDK MCP support with MCPClient.
    The MCPClient implements ToolProvider interface and can be passed directly
    to Agent(tools=[...]) for automatic lifecycle management (experimental).

    Supports two transport types:
    1. stdio: Command-based MCP servers (npx, uvx, python, etc.)
    2. HTTPS: Remote MCP servers via streamable HTTP

    Args:
        spec: Full workflow spec (for spec.tools.mcp configuration)
        tools_to_use: Optional list of tool IDs to filter by (currently ignored for MCP -
                     all tools from configured MCP servers are loaded)

    Returns:
        List of tuples: (server_id, MCPClient instance) for deduplication

    Raises:
        AdapterError: If MCP dependencies not installed or client creation fails
    """
    import structlog
    from rich.console import Console

    logger = structlog.get_logger(__name__)
    console = Console()

    # Get MCP startup timeout from environment (default 30s)
    # Note: Actual timeout enforcement requires async refactoring (Phase 9.1)
    # This is configured but not yet enforced - servers may still hang
    mcp_timeout = int(os.getenv("MCP_STARTUP_TIMEOUT_S", "30"))

    mcp_clients: list[tuple[str, Any]] = []
    failed_servers: list[tuple[str, str]] = []

    if not spec.tools or not spec.tools.mcp:
        return mcp_clients

    if not MCP_AVAILABLE:
        raise AdapterError(
            "MCP tools configured but 'mcp' package not installed. "
            "Install with: pip install mcp strands-agents[mcp]"
        )

    for mcp_config in spec.tools.mcp:
        try:
            # Determine transport type based on config
            if mcp_config.command:
                # stdio transport
                server_params = StdioServerParameters(
                    command=mcp_config.command,
                    args=mcp_config.args or [],
                    env=mcp_config.env or {},
                )

                # Create MCPClient with stdio transport
                # TODO Phase 9.1: Add timeout enforcement via asyncio.wait_for
                # Current limitation: MCP SDK uses sync client creation, hung servers will block
                # Configured timeout: {mcp_timeout}s (via MCP_STARTUP_TIMEOUT_S env var)
                mcp_client = MCPClient(lambda params=server_params: stdio_client(params))

                logger.info(
                    "mcp_client_created",
                    id=mcp_config.id,
                    transport="stdio",
                    command=mcp_config.command,
                    args=mcp_config.args,
                    timeout_s=mcp_timeout,
                )

            elif mcp_config.url:
                # HTTPS transport (streamable HTTP)
                url = mcp_config.url
                headers = mcp_config.headers or None

                # Create transport callable for streamable HTTP
                def create_http_transport(
                    endpoint: str = url, custom_headers: dict[str, str] | None = headers
                ) -> Any:
                    return streamablehttp_client(endpoint, headers=custom_headers)

                # Create MCPClient with HTTPS transport
                mcp_client = MCPClient(create_http_transport)

                logger.info(
                    "mcp_client_created",
                    id=mcp_config.id,
                    transport="https",
                    url=mcp_config.url,
                )

            else:
                logger.warning(
                    "mcp_config_invalid",
                    id=mcp_config.id,
                    error="MCP config must have either 'command' or 'url'",
                )
                failed_servers.append(
                    (mcp_config.id, "MCP config must have either 'command' or 'url'")
                )
                continue

            mcp_clients.append((mcp_config.id, mcp_client))

        except Exception as e:
            logger.warning(
                "mcp_client_creation_failed",
                id=mcp_config.id,
                command=mcp_config.command if mcp_config.command else None,
                url=mcp_config.url if mcp_config.url else None,
                error=str(e),
            )
            failed_servers.append((mcp_config.id, str(e)))

    # Warn user about failed servers (visible in console, not just logs)
    if failed_servers:
        console.print("[yellow]⚠ Warning: Failed to load MCP servers:[/yellow]")
        for server_id, error in failed_servers:
            console.print(f"  - {server_id}: {error}")

    return mcp_clients


def build_agent(  # noqa: C901 - Complexity acceptable for agent construction orchestration
    spec: Spec,
    agent_id: str,
    agent_config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
    agent_cache: Any | None = None,
) -> Agent:
    """Build a Strands Agent from a spec.

    Complete agent construction workflow:
    1. Create provider-specific model client (Bedrock or Ollama)
    2. Build system prompt from agent config, skills, notes, and runtime context
    3. Load and validate Python callable tools (allowlist check)
    4. Create HTTP executor adapters
    5. Assemble Strands Agent with all components
    6. Attach conversation manager and hooks (for context management)

    Args:
        spec: Full workflow spec (used for runtime, tools, skills)
        agent_id: ID of the agent to build from spec.agents
        agent_config: Configuration for this agent
        tool_overrides: Optional list of tool IDs to use instead of agent's default tools
                       (used for per-step tool_overrides in chain pattern)
        conversation_manager: Optional conversation manager for context compaction
        hooks: Optional list of hooks (e.g., ProactiveCompactionHook, NotesAppenderHook)
        injected_notes: Optional Markdown notes from previous steps (Phase 6.2)
        agent_cache: Optional AgentCache instance for tracking MCP clients (Phase 9)

    Returns:
        Configured Strands Agent ready for invoke_async()

    Raises:
        AdapterError: If model creation, tool loading, or agent assembly fails
    """
    import structlog

    logger = structlog.get_logger(__name__)

    # Determine which model_id to use (agent override takes precedence)
    effective_model_id = agent_config.model_id or spec.runtime.model_id

    logger.debug(
        "building_agent",
        agent_id=agent_id,
        provider=spec.runtime.provider.value,
        model_id=effective_model_id,
        tool_overrides=tool_overrides,
    )

    # Create the model with agent-level model_id override if specified
    try:
        if agent_config.model_id:
            # Create a modified runtime with agent's model_id
            runtime_with_override = spec.runtime.model_copy(
                update={"model_id": agent_config.model_id}
            )
            model = create_model(runtime_with_override)
        else:
            model = create_model(spec.runtime)
    except Exception as e:
        raise AdapterError(f"Failed to create model: {e}") from e

    # Build system prompt with optional notes injection
    system_prompt = build_system_prompt(agent_config, spec, agent_id, injected_notes)

    # Determine which tools to use
    tools_to_use = tool_overrides if tool_overrides is not None else agent_config.tools

    # Phase 6.3: Auto-inject JIT retrieval tools if context_policy.retrieval is set
    if spec.context_policy and spec.context_policy.retrieval:
        retrieval = spec.context_policy.retrieval
        if retrieval.jit_tools:
            # Merge JIT tools into tools_to_use (preserving None if no tools)
            if tools_to_use is None:
                tools_to_use = retrieval.jit_tools.copy()
            else:
                # Avoid duplicates
                existing_tools = set(tools_to_use)
                for jit_tool in retrieval.jit_tools:
                    if jit_tool not in existing_tools:
                        tools_to_use.append(jit_tool)

            logger.info(
                "jit_tools_injected",
                agent=agent_id,
                jit_tools=retrieval.jit_tools,
                final_tools=tools_to_use,
            )

    # Load all tools (native/JIT, Python callables, HTTP executors)
    # Track which tool IDs have been loaded from native registry to avoid duplicates
    tools: list[Any] = []
    loaded_tool_ids: set[str] = set()

    # Load native tools first (JIT tools, python_exec, etc.)
    registry = get_registry()
    if tools_to_use:
        for tool_id in tools_to_use:
            if registry.get(tool_id):
                loaded_tool_ids.add(tool_id)

    tools.extend(_load_native_tools(tools_to_use))
    tools.extend(_load_python_tools(spec, tools_to_use, loaded_tool_ids))
    tools.extend(_load_http_executors(spec, tools_to_use))

    # Phase 9: Load MCP server tools (uses Strands SDK MCPClient with ToolProvider interface)
    # Returns list of (server_id, client) tuples for deduplication
    mcp_clients_with_ids = _load_mcp_tools(spec, tools_to_use)

    # Extract clients for agent tools and track in cache by server_id (deduplication)
    if agent_cache and mcp_clients_with_ids:
        for server_id, mcp_client in mcp_clients_with_ids:
            # Deduplicate by server_id (prevents duplicate server processes)
            if server_id not in agent_cache._mcp_clients:
                agent_cache._mcp_clients[server_id] = mcp_client
                logger.debug(
                    "mcp_client_tracked_pre_agent",
                    agent_id=agent_id,
                    server_id=server_id,
                    mcp_clients_count=len(agent_cache._mcp_clients),
                )
            # Always add to tools (even if cached) so agent has access
            tools.append(mcp_client)
    else:
        # No cache - just add clients to tools
        tools.extend([client for _, client in mcp_clients_with_ids])

    # Create the agent
    try:
        agent = Agent(
            name=agent_id,
            model=model,
            system_prompt=system_prompt,
            tools=tools if tools else None,
            conversation_manager=conversation_manager,
            hooks=hooks,
        )
    except Exception as e:
        raise AdapterError(f"Failed to create Strands Agent: {e}") from e

    return agent

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

from typing import Any

from strands.agent import Agent

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


def build_agent(  # noqa: C901 - Complexity acceptable for agent construction orchestration
    spec: Spec,
    agent_id: str,
    agent_config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
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
                final_tools=tools_to_use
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

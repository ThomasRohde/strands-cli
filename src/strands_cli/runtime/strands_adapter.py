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

from strands.agent import Agent

from strands_cli.runtime.providers import create_model
from strands_cli.runtime.tools import HttpExecutorAdapter, load_python_callable
from strands_cli.types import Agent as AgentConfig
from strands_cli.types import Spec


class AdapterError(Exception):
    """Raised when agent construction fails."""

    pass


def build_system_prompt(agent_config: AgentConfig, spec: Spec, agent_id: str) -> str:
    """Build the system prompt for an agent.

    Combines multiple sources into a comprehensive system prompt:
    1. Agent's base prompt (agent.prompt) - core instructions
    2. Skills metadata injection - available tools/capabilities
    3. Runtime banner - workflow context, budgets, tags

    Skills are injected as metadata only (id, path, description).
    No code execution occurs; this provides context to the LLM.

    Args:
        agent_config: Agent configuration from spec.agents[agent_id]
        spec: Full workflow spec for context
        agent_id: ID of this agent

    Returns:
        Complete system prompt for agent initialization
    """
    sections = []

    # 1. Base agent prompt
    sections.append(agent_config.prompt)

    # 2. Skills metadata injection
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

    # 3. Runtime banner
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


def build_agent(
    spec: Spec,
    agent_id: str,
    agent_config: AgentConfig,
    tool_overrides: list[str] | None = None,
) -> Agent:
    """Build a Strands Agent from a spec.

    Complete agent construction workflow:
    1. Create provider-specific model client (Bedrock or Ollama)
    2. Build system prompt from agent config, skills, and runtime context
    3. Load and validate Python callable tools (allowlist check)
    4. Create HTTP executor adapters
    5. Assemble Strands Agent with all components

    Args:
        spec: Full workflow spec (used for runtime, tools, skills)
        agent_id: ID of the agent to build from spec.agents
        agent_config: Configuration for this agent
        tool_overrides: Optional list of tool IDs to use instead of agent's default tools
                       (used for per-step tool_overrides in chain pattern)

    Returns:
        Configured Strands Agent ready for invoke_async()

    Raises:
        AdapterError: If model creation, tool loading, or agent assembly fails
    """
    import structlog

    logger = structlog.get_logger(__name__)

    logger.debug(
        "building_agent",
        agent_id=agent_id,
        provider=spec.runtime.provider.value,
        model_id=spec.runtime.model_id or agent_config.model_id,
        tool_overrides=tool_overrides,
    )

    # Create the model
    try:
        model = create_model(spec.runtime)
    except Exception as e:
        raise AdapterError(f"Failed to create model: {e}") from e

    # Build system prompt
    system_prompt = build_system_prompt(agent_config, spec, agent_id)

    # Determine which tools to use
    tools_to_use = tool_overrides if tool_overrides is not None else agent_config.tools

    # Create tools list
    tools = []

    # Add Python callables
    if spec.tools and spec.tools.python:
        for py_tool in spec.tools.python:
            # Only add if in tools_to_use (or if no tool filtering)
            if tools_to_use is None or py_tool.callable in tools_to_use:
                try:
                    callable_obj = load_python_callable(py_tool.callable)
                    tools.append(callable_obj)
                except Exception as e:
                    raise AdapterError(
                        f"Failed to load Python tool '{py_tool.callable}': {e}"
                    ) from e

    # Add HTTP executors
    if spec.tools and spec.tools.http_executors:
        for http_exec in spec.tools.http_executors:
            # Only add if in tools_to_use (or if no tool filtering)
            if tools_to_use is None or http_exec.id in tools_to_use:
                try:
                    adapter = HttpExecutorAdapter(http_exec)
                    tools.append(adapter)
                except Exception as e:
                    raise AdapterError(
                        f"Failed to create HTTP executor '{http_exec.id}': {e}"
                    ) from e

    # Create the agent
    try:
        agent = Agent(
            name=agent_id,
            model=model,
            system_prompt=system_prompt,
            tools=tools if tools else None,  # type: ignore[arg-type]
        )
    except Exception as e:
        raise AdapterError(f"Failed to create Strands Agent: {e}") from e

    return agent

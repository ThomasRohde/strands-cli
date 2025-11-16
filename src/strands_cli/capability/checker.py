"""Capability checking for compatibility analysis.

Analyzes validated workflow specs to determine if they can be executed
with current capabilities. Gracefully rejects unsupported features with
structured error reports rather than silently ignoring them.

Supported Features (Phase 9):
    - Multiple agents (for all pattern types)
    - Pattern: chain (multi-step), workflow (multi-task with DAG), routing, parallel, evaluator_optimizer, orchestrator_workers, graph
    - Providers: bedrock, ollama, openai
    - Python tools: strands_tools.{http_request, file_read, file_write, calculator, current_time}.{function}
    - HTTP executors: full support
    - MCP tools: stdio and HTTPS transports
    - Secrets: source=env only
    - Skills: metadata injection (no code execution)

Unsupported (with remediation):
    - Non-env secret sources
    - Non-allowlisted Python callables
"""

import os
from collections import deque
from typing import Any

import structlog

from strands_cli.types import (
    CapabilityIssue,
    CapabilityReport,
    GraphEdge,
    OrchestratorLimits,
    PatternConfig,
    PatternType,
    ProviderType,
    Spec,
)

logger = structlog.get_logger(__name__)

# Allowlisted Python callable paths for security
# Only these imports are permitted to prevent arbitrary code execution
# Supports both old format (strands_tools.http_request) and new format
# (strands_tools.http_request.http_request) for backward compatibility
ALLOWED_PYTHON_CALLABLES = {
    # New format (full path)
    "strands_tools.http_request.http_request",
    "strands_tools.file_read.file_read",
    "strands_tools.file_write.file_write",
    "strands_tools.calculator.calculator",
    "strands_tools.current_time.current_time",
    # Old format (backward compatibility)
    "strands_tools.http_request",
    "strands_tools.file_read",
    "strands_tools.file_write",
    "strands_tools.calculator",
    "strands_tools.current_time",
}


def detect_cycles_in_dag(tasks: list[Any]) -> list[str]:
    """Detect cycles in workflow task dependencies using Kahn's algorithm.

    Args:
        tasks: List of WorkflowTask objects with id and deps fields

    Returns:
        List of error messages describing cycles found (empty if no cycles)
    """
    # Build adjacency list and in-degree count
    task_map = {task.id: task for task in tasks}
    in_degree = {task.id: 0 for task in tasks}
    adj_list: dict[str, list[str]] = {task.id: [] for task in tasks}

    # Calculate in-degrees and build adjacency list
    for task in tasks:
        if task.deps:
            for dep_id in task.deps:
                if dep_id not in task_map:
                    # Invalid dependency - will be caught by separate validation
                    continue
                adj_list[dep_id].append(task.id)
                in_degree[task.id] += 1

    # Kahn's algorithm for topological sort
    queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
    processed = []

    while queue:
        current = queue.popleft()
        processed.append(current)

        for neighbor in adj_list[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If not all tasks processed, there's a cycle
    errors = []
    if len(processed) < len(tasks):
        unprocessed = [task_id for task_id in task_map if task_id not in processed]
        errors.append(
            f"Cycle detected in task dependencies. Tasks involved: {', '.join(unprocessed)}"
        )

    return errors


def _validate_agents(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate agent configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if len(spec.agents) < 1:
        issues.append(
            CapabilityIssue(
                pointer="/agents",
                reason="No agents defined",
                remediation="Add at least one agent to the agents map",
            )
        )


def _validate_provider(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate runtime provider and provider-specific requirements.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    # Provider must be bedrock, ollama, or openai
    if spec.runtime.provider not in {
        ProviderType.BEDROCK,
        ProviderType.OLLAMA,
        ProviderType.OPENAI,
    }:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/provider",
                reason=f"Provider '{spec.runtime.provider}' not supported",
                remediation="Use 'bedrock', 'ollama', or 'openai'",
            )
        )

    # Bedrock requires region
    if spec.runtime.provider == ProviderType.BEDROCK and not spec.runtime.region:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/region",
                reason="Bedrock provider requires 'region' field",
                remediation="Add 'runtime.region' (e.g., 'us-east-1')",
            )
        )

    # Ollama requires host
    if spec.runtime.provider == ProviderType.OLLAMA and not spec.runtime.host:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/host",
                reason="Ollama provider requires 'host' field",
                remediation="Add 'runtime.host' (e.g., 'http://localhost:11434')",
            )
        )

    # OpenAI requires API key in environment
    if spec.runtime.provider == ProviderType.OPENAI:
        import os

        if not os.environ.get("OPENAI_API_KEY"):
            issues.append(
                CapabilityIssue(
                    pointer="/runtime/provider",
                    reason="OpenAI provider requires OPENAI_API_KEY environment variable",
                    remediation="Set environment variable: export OPENAI_API_KEY=your-api-key",
                )
            )


def _validate_inference_compatibility(spec: Spec, issues: list[CapabilityIssue]) -> None:  # noqa: C901
    """Validate inference parameter compatibility with provider.

    Issues always-on warnings when inference parameters are used with
    providers that don't support them (Bedrock/Ollama). OpenAI/Azure
    fully support temperature, top_p, max_tokens.

    Args:
        spec: Workflow spec
        issues: List to append warning issues to
    """
    # Check runtime-level inference parameters
    if spec.runtime.provider in {ProviderType.BEDROCK, ProviderType.OLLAMA}:
        runtime_params = []
        if spec.runtime.temperature is not None:
            runtime_params.append("temperature")
        if spec.runtime.top_p is not None:
            runtime_params.append("top_p")
        if spec.runtime.max_tokens is not None:
            runtime_params.append("max_tokens")

        if runtime_params:
            provider_name = spec.runtime.provider.value
            if spec.runtime.provider == ProviderType.BEDROCK:
                support_msg = "limited by SDK"
                workaround = "Configure inference via AWS Bedrock console or use OpenAI provider"
            else:  # OLLAMA
                support_msg = "not supported"
                workaround = "Configure parameters in Ollama Modelfile or use OpenAI provider"

            for param in runtime_params:
                issues.append(
                    CapabilityIssue(
                        pointer=f"/runtime/{param}",
                        reason=f"Warning: Inference parameter '{param}' is {support_msg} for {provider_name} provider. "
                        f"Parameter will be logged but not applied. "
                        f"Fully supported on OpenAI/Azure providers only.",
                        remediation=workaround,
                    )
                )

    # Check agent-level inference overrides
    for agent_id, agent_config in spec.agents.items():
        if agent_config.inference and spec.runtime.provider in {
            ProviderType.BEDROCK,
            ProviderType.OLLAMA,
        }:
            agent_params = []
            if agent_config.inference.temperature is not None:
                agent_params.append("temperature")
            if agent_config.inference.top_p is not None:
                agent_params.append("top_p")
            if agent_config.inference.max_tokens is not None:
                agent_params.append("max_tokens")

            if agent_params:
                provider_name = spec.runtime.provider.value
                if spec.runtime.provider == ProviderType.BEDROCK:
                    support_msg = "limited by SDK"
                    workaround = (
                        "Configure inference via AWS Bedrock console or use OpenAI provider"
                    )
                else:  # OLLAMA
                    support_msg = "not supported"
                    workaround = "Configure parameters in Ollama Modelfile or use OpenAI provider"

                for param in agent_params:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/agents/{agent_id}/inference/{param}",
                            reason=f"Warning: Agent '{agent_id}' inference parameter '{param}' is {support_msg} "
                            f"for {provider_name} provider. Parameter will be logged but not applied. "
                            f"Fully supported on OpenAI/Azure providers only.",
                            remediation=workaround,
                        )
                    )


def _validate_pattern_type(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate pattern type is supported.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type not in {
        PatternType.CHAIN,
        PatternType.WORKFLOW,
        PatternType.ROUTING,
        PatternType.PARALLEL,
        PatternType.EVALUATOR_OPTIMIZER,
        PatternType.ORCHESTRATOR_WORKERS,
        PatternType.GRAPH,
    }:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/type",
                reason=f"Pattern type '{spec.pattern.type}' not supported yet",
                remediation="Use 'chain', 'workflow', 'routing', 'parallel', 'evaluator_optimizer', 'orchestrator_workers', or 'graph'",
            )
        )


def _validate_evaluator_optimizer_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate evaluator-optimizer pattern configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.EVALUATOR_OPTIMIZER:
        return

    config = spec.pattern.config

    # Check producer agent exists
    if not config.producer:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/producer",
                reason="Evaluator-optimizer pattern requires producer agent",
                remediation="Add 'producer' field with agent ID",
            )
        )
    elif config.producer not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/producer",
                reason=f"Producer agent '{config.producer}' not found in agents map",
                remediation=f"Add agent '{config.producer}' to agents section or use existing agent",
            )
        )

    # Check evaluator agent exists
    if not config.evaluator:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/evaluator",
                reason="Evaluator-optimizer pattern requires evaluator configuration",
                remediation="Add 'evaluator' field with agent and optional input",
            )
        )
    elif config.evaluator.agent not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/evaluator/agent",
                reason=f"Evaluator agent '{config.evaluator.agent}' not found in agents map",
                remediation=f"Add agent '{config.evaluator.agent}' to agents section or use existing agent",
            )
        )

    # Check accept criteria exists
    if not config.accept:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/accept",
                reason="Evaluator-optimizer pattern requires accept criteria",
                remediation="Add 'accept' field with min_score and optional max_iters",
            )
        )


def _validate_orchestrator_workers_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate orchestrator-workers pattern configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.ORCHESTRATOR_WORKERS:
        return

    config = spec.pattern.config

    _validate_orchestrator_config(spec, config, issues)
    _validate_worker_template_config(spec, config, issues)
    _validate_reduce_agent(spec, config, issues)
    _validate_writeup_agent(spec, config, issues)


def _validate_orchestrator_config(
    spec: Spec, config: PatternConfig, issues: list[CapabilityIssue]
) -> None:
    """Validate orchestrator configuration."""
    # Check orchestrator config exists
    if not config.orchestrator:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/orchestrator",
                reason="Orchestrator-workers pattern requires orchestrator configuration",
                remediation="Add 'orchestrator' field with agent and optional limits",
            )
        )
        return  # Can't validate further without orchestrator

    # Check orchestrator agent exists
    if config.orchestrator.agent not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/orchestrator/agent",
                reason=f"Orchestrator agent '{config.orchestrator.agent}' not found in agents map",
                remediation=f"Add agent '{config.orchestrator.agent}' to agents section or use existing agent",
            )
        )

    # Validate limits if present
    if config.orchestrator.limits:
        _validate_orchestrator_limits(config.orchestrator.limits, issues)


def _validate_orchestrator_limits(
    limits: OrchestratorLimits, issues: list[CapabilityIssue]
) -> None:
    """Validate orchestrator limits."""
    if limits.max_workers is not None and limits.max_workers < 1:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/orchestrator/limits/max_workers",
                reason=f"max_workers must be >= 1, got {limits.max_workers}",
                remediation="Set max_workers to a positive integer or omit for unlimited",
            )
        )
    if limits.max_rounds is not None and limits.max_rounds < 1:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/orchestrator/limits/max_rounds",
                reason=f"max_rounds must be >= 1, got {limits.max_rounds}",
                remediation="Set max_rounds to a positive integer or omit for unlimited",
            )
        )

    # Phase 7 MVP: Only single round supported
    if limits.max_rounds is not None and limits.max_rounds > 1:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/orchestrator/limits/max_rounds",
                reason="Multi-round orchestration not yet supported (Phase 7 MVP limitation)",
                remediation="Set max_rounds to 1 or omit for default single-round execution. "
                "Multi-round support planned for future release.",
            )
        )


def _validate_worker_template_config(
    spec: Spec, config: PatternConfig, issues: list[CapabilityIssue]
) -> None:
    """Validate worker template configuration."""
    # Check worker_template config exists
    if not config.worker_template:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/worker_template",
                reason="Orchestrator-workers pattern requires worker_template configuration",
                remediation="Add 'worker_template' field with agent and optional tools",
            )
        )
        return  # Can't validate further without worker_template

    # Check worker agent exists
    if config.worker_template.agent not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/worker_template/agent",
                reason=f"Worker agent '{config.worker_template.agent}' not found in agents map",
                remediation=f"Add agent '{config.worker_template.agent}' to agents section or use existing agent",
            )
        )


def _validate_reduce_agent(
    spec: Spec, config: PatternConfig, issues: list[CapabilityIssue]
) -> None:
    """Validate reduce agent if present."""
    if config.reduce and config.reduce.agent not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/reduce/agent",
                reason=f"Reduce agent '{config.reduce.agent}' not found in agents map",
                remediation=f"Add agent '{config.reduce.agent}' to agents section or use existing agent",
            )
        )


def _validate_writeup_agent(
    spec: Spec, config: PatternConfig, issues: list[CapabilityIssue]
) -> None:
    """Validate writeup agent if present."""
    if config.writeup and config.writeup.agent not in spec.agents:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/writeup/agent",
                reason=f"Writeup agent '{config.writeup.agent}' not found in agents map",
                remediation=f"Add agent '{config.writeup.agent}' to agents section or use existing agent",
            )
        )


def _validate_graph_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:  # noqa: C901
    """Validate graph pattern configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.GRAPH:
        return

    config = spec.pattern.config

    # Check nodes exist
    if not config.nodes:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/nodes",
                reason="Graph pattern requires at least one node",
                remediation="Add nodes to pattern.config.nodes",
            )
        )
        return  # Can't validate further without nodes

    # Check edges exist
    if not config.edges:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/edges",
                reason="Graph pattern requires at least one edge",
                remediation="Add edges to pattern.config.edges",
            )
        )
        return  # Can't validate further without edges

    # Validate node agents exist (skip HITL nodes)
    for node_id, node in config.nodes.items():
        # Skip validation for HITL nodes (they don't have an agent field)
        if node.type == "hitl":
            continue

        if node.agent and node.agent not in spec.agents:
            issues.append(
                CapabilityIssue(
                    pointer=f"/pattern/config/nodes/{node_id}/agent",
                    reason=f"Node '{node_id}' references non-existent agent '{node.agent}'",
                    remediation=f"Add agent '{node.agent}' to agents section or use existing agent",
                )
            )

    # Collect all node IDs for edge validation
    node_ids = set(config.nodes.keys())

    # Validate edges
    for edge_idx, edge in enumerate(config.edges):
        # Validate 'from' node exists
        if edge.from_ not in node_ids:
            issues.append(
                CapabilityIssue(
                    pointer=f"/pattern/config/edges/{edge_idx}/from",
                    reason=f"Edge references non-existent node '{edge.from_}'",
                    remediation=f"Use existing node ID from: {', '.join(sorted(node_ids))}",
                )
            )

        # Validate static 'to' nodes if present
        if edge.to:
            # Warn if multiple targets (only first is executed)
            if len(edge.to) > 1:
                issues.append(
                    CapabilityIssue(
                        pointer=f"/pattern/config/edges/{edge_idx}/to",
                        reason=f"Static edge has {len(edge.to)} targets, but only first will execute",
                        remediation="Use multiple separate edges or conditional 'choose' for multi-target transitions",
                    )
                )

            for to_node in edge.to:
                if to_node not in node_ids:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/edges/{edge_idx}/to",
                            reason=f"Edge 'to' references non-existent node '{to_node}'",
                            remediation=f"Use existing node ID from: {', '.join(sorted(node_ids))}",
                        )
                    )

        # Validate conditional 'choose' targets if present
        if edge.choose:
            for choice_idx, choice in enumerate(edge.choose):
                if choice.to not in node_ids:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/edges/{edge_idx}/choose/{choice_idx}/to",
                            reason=f"Conditional choice references non-existent node '{choice.to}'",
                            remediation=f"Use existing node ID from: {', '.join(sorted(node_ids))}",
                        )
                    )

    # Check for at least one terminal node (no outgoing edges)
    nodes_with_outgoing = set()
    for edge in config.edges:
        nodes_with_outgoing.add(edge.from_)

    terminal_nodes = node_ids - nodes_with_outgoing
    if not terminal_nodes:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/edges",
                reason="Graph has no terminal nodes (all nodes have outgoing edges)",
                remediation="Ensure at least one node has no outgoing edges to serve as workflow completion point",
            )
        )

    # Check for unreachable nodes (nodes not reachable from entry node)
    entry_node = next(iter(config.nodes.keys()))  # First node in YAML order
    reachable = _find_reachable_nodes(entry_node, config.edges)
    unreachable = node_ids - reachable
    if unreachable:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/nodes",
                reason=f"Unreachable nodes detected: {', '.join(sorted(unreachable))}",
                remediation=f"Add edges to make these nodes reachable from entry node '{entry_node}', or remove them",
            )
        )


def _find_reachable_nodes(entry_node: str, edges: list[GraphEdge]) -> set[str]:
    """Find all nodes reachable from entry node via BFS.

    Args:
        entry_node: Starting node ID
        edges: List of GraphEdge objects

    Returns:
        Set of reachable node IDs
    """
    reachable = {entry_node}
    queue = [entry_node]

    while queue:
        current = queue.pop(0)
        for edge in edges:
            if edge.from_ == current:
                # Add static targets
                if edge.to:
                    for target in edge.to:
                        if target not in reachable:
                            reachable.add(target)
                            queue.append(target)
                # Add conditional targets
                if edge.choose:
                    for choice in edge.choose:
                        if choice.to not in reachable:
                            reachable.add(choice.to)
                            queue.append(choice.to)

    return reachable


def _validate_secrets(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate secret configurations.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    # Import here to avoid circular dependency
    from strands_cli.types import SecretSource

    if spec.env and spec.env.secrets:
        for i, secret in enumerate(spec.env.secrets):
            if secret.source != SecretSource.ENV:
                issues.append(
                    CapabilityIssue(
                        pointer=f"/env/secrets/{i}/source",
                        reason=f"Secret source '{secret.source}' not supported in MVP",
                        remediation="Use source: env",
                    )
                )


def _build_available_tools_set(spec: Spec) -> set[str]:
    """Build set of available tool IDs from spec.

    Args:
        spec: Workflow spec

    Returns:
        Set of tool IDs (Python callables, HTTP executor IDs, and MCP server IDs)
    """
    available_tools: set[str] = set()
    if spec.tools:
        if spec.tools.python:
            available_tools.update(tool.callable for tool in spec.tools.python)
        if spec.tools.http_executors:
            available_tools.update(executor.id for executor in spec.tools.http_executors)
        if spec.tools.mcp:
            available_tools.update(server.id for server in spec.tools.mcp)
    return available_tools


def _validate_chain_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate chain-specific configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.CHAIN:
        return

    # Chain must have at least 1 step
    if not spec.pattern.config.steps:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/steps",
                reason="Chain pattern has no steps",
                remediation="Add at least 1 step to pattern.config.steps",
            )
        )
        return

    # Validate tool_overrides in chain steps reference defined tools
    available_tools = _build_available_tools_set(spec)
    for i, step in enumerate(spec.pattern.config.steps):
        if step.tool_overrides:
            for tool_id in step.tool_overrides:
                if tool_id not in available_tools:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/steps/{i}/tool_overrides",
                            reason=f"Step {i} references undefined tool '{tool_id}' in tool_overrides",
                            remediation=f"Define '{tool_id}' in tools.python or tools.http_executors, or remove from tool_overrides",
                        )
                    )


def _validate_task_dependencies(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate workflow task dependencies.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if not spec.pattern.config.tasks:
        return

    task_ids = {task.id for task in spec.pattern.config.tasks}
    for i, task in enumerate(spec.pattern.config.tasks):
        if task.deps:
            for dep in task.deps:
                if dep not in task_ids:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/tasks/{i}/deps",
                            reason=f"Task '{task.id}' depends on non-existent task '{dep}'",
                            remediation=f"Ensure dependency '{dep}' exists in tasks list",
                        )
                    )


def _validate_workflow_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate workflow-specific configuration including DAG.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.WORKFLOW:
        return

    # Workflow must have at least 1 task
    if not spec.pattern.config.tasks:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/tasks",
                reason="Workflow pattern has no tasks",
                remediation="Add at least 1 task to pattern.config.tasks",
            )
        )
        return

    # Validate task dependencies
    _validate_task_dependencies(spec, issues)

    # Check for cycles in DAG (only if no dependency errors)
    has_dep_errors = any("/deps" in issue.pointer for issue in issues)
    if not has_dep_errors:
        cycle_errors = detect_cycles_in_dag(spec.pattern.config.tasks)
        for error in cycle_errors:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/tasks",
                    reason=error,
                    remediation="Remove circular dependencies to form a valid DAG",
                )
            )


def _validate_route(
    route_name: str,
    route: Any,
    spec: Spec,
    issues: list[CapabilityIssue],
) -> None:
    """Validate a single route configuration.

    Args:
        route_name: Name of the route
        route: Route configuration
        spec: Workflow spec
        issues: List to append issues to
    """
    if not route.then or len(route.then) == 0:
        issues.append(
            CapabilityIssue(
                pointer=f"/pattern/config/routes/{route_name}/then",
                reason=f"Route '{route_name}' has no steps",
                remediation=f"Add at least one step to route '{route_name}'",
            )
        )
        return

    # Validate each step's agent exists
    for i, step in enumerate(route.then):
        if step.agent not in spec.agents:
            issues.append(
                CapabilityIssue(
                    pointer=f"/pattern/config/routes/{route_name}/then/{i}/agent",
                    reason=f"Route step agent '{step.agent}' not found in agents map",
                    remediation=f"Define agent '{step.agent}' in agents section",
                )
            )


def _validate_routing_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate routing-specific configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.ROUTING:
        return

    # Validate router configuration
    if not spec.pattern.config.router:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/router",
                reason="Routing pattern requires router configuration",
                remediation="Add pattern.config.router with agent and optional input",
            )
        )
    else:
        # Validate router agent exists
        router_agent_id = spec.pattern.config.router.agent
        if router_agent_id not in spec.agents:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/router/agent",
                    reason=f"Router agent '{router_agent_id}' not found in agents map",
                    remediation=f"Define agent '{router_agent_id}' in agents section",
                )
            )

    # Validate routes exist and have valid agents
    if not spec.pattern.config.routes:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/routes",
                reason="Routing pattern requires at least one route",
                remediation="Add routes to pattern.config.routes",
            )
        )
    else:
        for route_name, route in spec.pattern.config.routes.items():
            _validate_route(route_name, route, spec, issues)


def _validate_parallel_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate parallel-specific configuration.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    if spec.pattern.type != PatternType.PARALLEL:
        return

    # Parallel requires at least 2 branches
    if not spec.pattern.config.branches or len(spec.pattern.config.branches) < 2:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/branches",
                reason="Parallel pattern requires at least 2 branches",
                remediation="Add at least 2 branches to pattern.config.branches",
            )
        )
        return

    # Validate unique branch IDs and steps
    branch_ids: set[str] = set()
    for i, branch in enumerate(spec.pattern.config.branches):
        # Check for duplicate branch IDs
        if branch.id in branch_ids:
            issues.append(
                CapabilityIssue(
                    pointer=f"/pattern/config/branches/{i}/id",
                    reason=f"Duplicate branch ID '{branch.id}'",
                    remediation="Branch IDs must be unique",
                )
            )
        branch_ids.add(branch.id)

        # Validate branch has at least one step
        if not branch.steps or len(branch.steps) == 0:
            issues.append(
                CapabilityIssue(
                    pointer=f"/pattern/config/branches/{i}/steps",
                    reason=f"Branch '{branch.id}' has no steps",
                    remediation="Add at least one step to the branch",
                )
            )
        else:
            # Validate all step agents exist (skip HITL steps)
            for j, step in enumerate(branch.steps):
                # Skip HITL steps (they don't have agents)
                if hasattr(step, "type") and step.type == "hitl":
                    continue
                if step.agent not in spec.agents:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/branches/{i}/steps/{j}/agent",
                            reason=f"Branch '{branch.id}' step {j} references unknown agent '{step.agent}'",
                            remediation=f"Define agent '{step.agent}' in agents section",
                        )
                    )

    # Validate reduce step agent if present (skip HITL reduce)
    if spec.pattern.config.reduce:
        # Skip HITL reduce steps (they don't have agents)
        is_hitl_reduce = (
            hasattr(spec.pattern.config.reduce, "type")
            and spec.pattern.config.reduce.type == "hitl"
        )
        if not is_hitl_reduce and spec.pattern.config.reduce.agent not in spec.agents:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/reduce/agent",
                    reason=f"Reduce step references unknown agent '{spec.pattern.config.reduce.agent}'",
                    remediation=f"Define agent '{spec.pattern.config.reduce.agent}' in agents section",
                )
            )


def _validate_tools(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate tool configurations.

    Args:
        spec: Workflow spec
        issues: List to append issues to
    """
    # Python tools must be in allowlist (hardcoded + registry)
    if spec.tools and spec.tools.python:
        # Import registry here to avoid circular imports
        from strands_cli.tools import get_registry

        registry = get_registry()
        # Combine hardcoded allowlist (strands_tools.*) with native tools from registry
        allowed = ALLOWED_PYTHON_CALLABLES | registry.get_allowlist()

        for i, tool in enumerate(spec.tools.python):
            if tool.callable not in allowed:
                # Build helpful remediation message
                native_tools = ', '.join(sorted(t.id for t in registry.list_all()))
                remediation = (
                    f"Use existing tools or native tools: {native_tools}"
                    if native_tools
                    else f"Use one of: {', '.join(sorted(ALLOWED_PYTHON_CALLABLES))}"
                )

                issues.append(
                    CapabilityIssue(
                        pointer=f"/tools/python/{i}/callable",
                        reason=f"Python callable '{tool.callable}' not in allowlist",
                        remediation=remediation,
                    )
                )

    # MCP tools are now supported (Phase 9) - no validation needed


def _build_normalized_values(spec: Spec) -> dict[str, Any]:
    """Build normalized execution parameters from spec.

    Args:
        spec: Workflow spec

    Returns:
        Dictionary with normalized execution parameters
    """
    agent_id = next(iter(spec.agents.keys()))
    agent = spec.agents[agent_id]

    return {
        "agent_id": agent_id,
        "agent": agent,
        "pattern_type": spec.pattern.type,
        "provider": spec.runtime.provider,
        "model_id": spec.runtime.model_id,
        "region": spec.runtime.region,
        "host": spec.runtime.host,
    }


def check_capability(spec: Spec) -> CapabilityReport:
    """Check if a spec is compatible with current capabilities.

    Orchestrates validation across all feature areas:
    - Agent configuration
    - Provider requirements
    - Pattern type and configuration
    - Secrets and tools

    For supported specs, extracts normalized execution parameters.
    For unsupported specs, generates detailed issues with JSONPointer locations.

    Args:
        spec: Loaded and validated workflow spec (passed schema validation)

    Returns:
        CapabilityReport with:
        - supported: True if fully compatible, False otherwise
        - issues: List of incompatibilities with remediation guidance
        - normalized: Extracted parameters for execution (if supported)
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    if debug:
        logger.debug(
            "capability_check_start",
            spec_name=spec.name,
            pattern_type=spec.pattern.type if spec.pattern else None,
            agent_count=len(spec.agents),
            provider=spec.runtime.provider,
        )

    issues: list[CapabilityIssue] = []

    # Run all validation checks
    _validate_agents(spec, issues)
    _validate_provider(spec, issues)
    _validate_inference_compatibility(spec, issues)
    _validate_pattern_type(spec, issues)
    _validate_chain_pattern(spec, issues)
    _validate_workflow_pattern(spec, issues)
    _validate_routing_pattern(spec, issues)
    _validate_parallel_pattern(spec, issues)
    _validate_evaluator_optimizer_pattern(spec, issues)
    _validate_orchestrator_workers_pattern(spec, issues)
    _validate_graph_pattern(spec, issues)
    _validate_secrets(spec, issues)
    _validate_tools(spec, issues)

    if debug:
        logger.debug(
            "capability_check_complete",
            supported=len(issues) == 0,
            issue_count=len(issues),
            issues=[{"pointer": i.pointer, "reason": i.reason} for i in issues[:5]],
        )

    # Build normalized values if supported
    normalized = None
    if not issues:
        normalized = _build_normalized_values(spec)

    return CapabilityReport(
        supported=len(issues) == 0,
        issues=issues,
        normalized=normalized,
    )

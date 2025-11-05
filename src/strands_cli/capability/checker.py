"""Capability checking for compatibility analysis.

Analyzes validated workflow specs to determine if they can be executed
with current capabilities. Gracefully rejects unsupported features with
structured error reports rather than silently ignoring them.

Supported Features (Phase 2):
    - Multiple agents (for routing pattern)
    - Pattern: chain (multi-step), workflow (multi-task with DAG), OR routing
    - Providers: bedrock, ollama, openai
    - Python tools: strands_tools.http_request, strands_tools.file_read
    - HTTP executors: full support
    - Secrets: source=env only
    - Skills: metadata injection (no code execution)

Unsupported (with remediation):
    - Patterns: parallel, orchestrator_workers, evaluator_optimizer, graph
    - MCP tools
    - Non-env secret sources
    - Non-allowlisted Python callables
"""

from collections import deque
from typing import Any

from strands_cli.types import (
    CapabilityIssue,
    CapabilityReport,
    PatternType,
    ProviderType,
    SecretSource,
    Spec,
)

# Allowlisted Python callable paths for security
# Only these imports are permitted to prevent arbitrary code execution
ALLOWED_PYTHON_CALLABLES = {
    "strands_tools.http_request",
    "strands_tools.file_read",
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


def check_capability(spec: Spec) -> CapabilityReport:
    """Check if a spec is compatible with current capabilities.

    Performs systematic compatibility analysis across all workflow features:
    1. Agent count (must be exactly 1)
    2. Provider support (bedrock or ollama)
    3. Provider-specific requirements (region for Bedrock, host for Ollama)
    4. Pattern type (chain or workflow only)
    5. Pattern configuration (1 step for chain, 1 task for workflow)
    6. Secret sources (env only)
    7. Python tool allowlist enforcement
    8. MCP tool rejection

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
    issues: list[CapabilityIssue] = []

    # Check 1: Must have at least one agent
    if len(spec.agents) < 1:
        issues.append(
            CapabilityIssue(
                pointer="/agents",
                reason="No agents defined",
                remediation="Add at least one agent to the agents map",
            )
        )

    # Check 2: Provider must be bedrock, ollama, or openai
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

    # Check 3: Bedrock requires region
    if spec.runtime.provider == ProviderType.BEDROCK and not spec.runtime.region:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/region",
                reason="Bedrock provider requires 'region' field",
                remediation="Add 'runtime.region' (e.g., 'us-east-1')",
            )
        )

    # Check 4: Ollama requires host
    if spec.runtime.provider == ProviderType.OLLAMA and not spec.runtime.host:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/host",
                reason="Ollama provider requires 'host' field",
                remediation="Add 'runtime.host' (e.g., 'http://localhost:11434')",
            )
        )

    # Check 4b: OpenAI requires API key in environment
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

    # Check 5: Pattern type must be chain, workflow, or routing
    if spec.pattern.type not in {PatternType.CHAIN, PatternType.WORKFLOW, PatternType.ROUTING}:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/type",
                reason=f"Pattern type '{spec.pattern.type}' not supported yet",
                remediation="Use 'chain', 'workflow', or 'routing'",
            )
        )

    # Check 6: Chain must have at least 1 step
    if spec.pattern.type == PatternType.CHAIN and not spec.pattern.config.steps:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/config/steps",
                reason="Chain pattern has no steps",
                remediation="Add at least 1 step to pattern.config.steps",
            )
        )

    # Check 7: Workflow must have at least 1 task with valid dependencies
    if spec.pattern.type == PatternType.WORKFLOW:
        if not spec.pattern.config.tasks:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/tasks",
                    reason="Workflow pattern has no tasks",
                    remediation="Add at least 1 task to pattern.config.tasks",
                )
            )
        else:
            # Validate task dependencies
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

            # Check for cycles in DAG
            if not issues:  # Only check cycles if dependencies are valid
                cycle_errors = detect_cycles_in_dag(spec.pattern.config.tasks)
                for error in cycle_errors:
                    issues.append(
                        CapabilityIssue(
                            pointer="/pattern/config/tasks",
                            reason=error,
                            remediation="Remove circular dependencies to form a valid DAG",
                        )
                    )

    # Check 7b: Routing pattern validations
    if spec.pattern.type == PatternType.ROUTING:
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
                if not route.then or len(route.then) == 0:
                    issues.append(
                        CapabilityIssue(
                            pointer=f"/pattern/config/routes/{route_name}/then",
                            reason=f"Route '{route_name}' has no steps",
                            remediation=f"Add at least one step to route '{route_name}'",
                        )
                    )
                else:
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

    # Check 7a: Validate tool_overrides in chain steps reference defined tools
    if spec.pattern.type == PatternType.CHAIN and spec.pattern.config.steps:
        # Build set of available tool IDs
        available_tools: set[str] = set()
        if spec.tools:
            if spec.tools.python:
                available_tools.update(tool.callable for tool in spec.tools.python)
            if spec.tools.http_executors:
                available_tools.update(executor.id for executor in spec.tools.http_executors)

        # Validate each step's tool_overrides
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

    # Check 8: Secrets must use source=env
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

    # Check 9: Python tools must be in allowlist
    if spec.tools and spec.tools.python:
        for i, tool in enumerate(spec.tools.python):
            if tool.callable not in ALLOWED_PYTHON_CALLABLES:
                issues.append(
                    CapabilityIssue(
                        pointer=f"/tools/python/{i}/callable",
                        reason=f"Python callable '{tool.callable}' not in MVP allowlist",
                        remediation=f"Use one of: {', '.join(ALLOWED_PYTHON_CALLABLES)}",
                    )
                )

    # Check 10: MCP tools not supported in MVP
    if spec.tools and spec.tools.mcp:
        issues.append(
            CapabilityIssue(
                pointer="/tools/mcp",
                reason="MCP tools not supported in MVP",
                remediation="Remove tools.mcp section",
            )
        )

    # Build normalized values for executor
    # These pre-extracted values simplify the execution path for supported specs
    normalized = None
    if not issues:
        # Extract the single agent
        agent_id = next(iter(spec.agents.keys()))
        agent = spec.agents[agent_id]

        normalized = {
            "agent_id": agent_id,
            "agent": agent,
            "pattern_type": spec.pattern.type,
            "provider": spec.runtime.provider,
            "model_id": spec.runtime.model_id,
            "region": spec.runtime.region,
            "host": spec.runtime.host,
        }

    return CapabilityReport(
        supported=len(issues) == 0,
        issues=issues,
        normalized=normalized,
    )

"""Capability checking for compatibility analysis.

Analyzes validated workflow specs to determine if they can be executed
with current capabilities. Gracefully rejects unsupported features with
structured error reports rather than silently ignoring them.

Supported Features:
    - Exactly 1 agent in agents map
    - Pattern: chain (1 step) OR workflow (1 task)
    - Providers: bedrock, ollama
    - Python tools: strands_tools.http_request, strands_tools.file_read
    - HTTP executors: full support
    - Secrets: source=env only
    - Skills: metadata injection (no code execution)

Unsupported (with remediation):
    - Multiple agents
    - Multi-step chains or multi-task workflows
    - Patterns: routing, parallel, orchestrator_workers, evaluator_optimizer, graph
    - MCP tools
    - Non-env secret sources
    - Non-allowlisted Python callables
"""

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

    # Check 1: Must have exactly one agent (single-agent execution only)
    if len(spec.agents) != 1:
        agent_keys = list(spec.agents.keys())
        issues.append(
            CapabilityIssue(
                pointer="/agents",
                reason=f"Found {len(spec.agents)} agents, but MVP supports exactly 1",
                remediation=f"Keep only one agent (e.g., '{agent_keys[0]}' if available)",
            )
        )

    # Check 2: Provider must be bedrock or ollama
    if spec.runtime.provider not in {ProviderType.BEDROCK, ProviderType.OLLAMA}:
        issues.append(
            CapabilityIssue(
                pointer="/runtime/provider",
                reason=f"Provider '{spec.runtime.provider}' not supported in MVP",
                remediation="Use 'bedrock' or 'ollama'",
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

    # Check 5: Pattern type must be chain or workflow
    if spec.pattern.type not in {PatternType.CHAIN, PatternType.WORKFLOW}:
        issues.append(
            CapabilityIssue(
                pointer="/pattern/type",
                reason=f"Pattern type '{spec.pattern.type}' not supported in MVP",
                remediation="Use 'chain' or 'workflow'",
            )
        )

    # Check 6: Chain must have exactly 1 step
    if spec.pattern.type == PatternType.CHAIN:
        if not spec.pattern.config.steps:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/steps",
                    reason="Chain pattern has no steps",
                    remediation="Add exactly 1 step to pattern.config.steps",
                )
            )
        elif len(spec.pattern.config.steps) > 1:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/steps",
                    reason=f"Chain has {len(spec.pattern.config.steps)} steps, but MVP supports only 1",
                    remediation="Reduce to 1 step in pattern.config.steps",
                )
            )

    # Check 7: Workflow must have exactly 1 task
    if spec.pattern.type == PatternType.WORKFLOW:
        if not spec.pattern.config.tasks:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/tasks",
                    reason="Workflow pattern has no tasks",
                    remediation="Add exactly 1 task to pattern.config.tasks",
                )
            )
        elif len(spec.pattern.config.tasks) > 1:
            issues.append(
                CapabilityIssue(
                    pointer="/pattern/config/tasks",
                    reason=f"Workflow has {len(spec.pattern.config.tasks)} tasks, but MVP supports only 1",
                    remediation="Reduce to 1 task in pattern.config.tasks",
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

        # Extract the single step/task
        if spec.pattern.type == PatternType.CHAIN:
            step = spec.pattern.config.steps[0]  # type: ignore
            task_input = step.input
        else:  # WORKFLOW
            task = spec.pattern.config.tasks[0]  # type: ignore
            task_input = task.input

        normalized = {
            "agent_id": agent_id,
            "agent": agent,
            "pattern_type": spec.pattern.type,
            "task_input": task_input,
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

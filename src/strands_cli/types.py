"""Type definitions for the Strands CLI.

All workflow specs and internal data structures use Pydantic v2 models
for strict validation and type safety. These models map directly from
the validated JSON Schema to typed Python objects.

Key Models:
    Spec: Top-level workflow specification
    Runtime: Model provider and execution configuration
    Agent: Individual agent configuration with prompt and tools
    Pattern: Workflow execution pattern (chain, workflow, etc.)
    Tools: Tool configurations (Python callables, HTTP executors, MCP)
    CapabilityReport: Compatibility analysis results
    RunResult: Execution outcome with timing and artifacts
"""

import re
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)

# Default blocked URL patterns for HTTP executors (SSRF prevention)
# Blocks localhost, private IPs (RFC1918), AWS metadata, and non-HTTP protocols
DEFAULT_BLOCKED_URL_PATTERNS = [
    r"^https?://127\.0\.0\.1.*$",  # Localhost IPv4
    r"^https?://localhost.*$",  # Localhost hostname
    r"^https?://\[::1\].*$",  # Localhost IPv6
    r"^https?://169\.254\.169\.254.*$",  # AWS/Azure metadata
    r"^https?://10\..*$",  # RFC1918 private (10.0.0.0/8)
    r"^https?://172\.(1[6-9]|2\d|3[01])\..*$",  # RFC1918 private (172.16.0.0/12)
    r"^https?://192\.168\..*$",  # RFC1918 private (192.168.0.0/16)
    r"^file:///.*$",  # File protocol
    r"^ftp://.*$",  # FTP protocol
    r"^gopher://.*$",  # Gopher protocol
]


class ProviderType(str, Enum):
    """Supported model providers.

    Defines the LLM providers that can execute workflows.
    Each provider requires specific runtime configuration.
    """

    BEDROCK = "bedrock"  # AWS Bedrock (requires region)
    OLLAMA = "ollama"  # Ollama local/self-hosted (requires host)
    OPENAI = "openai"  # OpenAI API (future support)
    AZURE_OPENAI = "azure_openai"  # Azure OpenAI (future support)


class PatternType(str, Enum):
    """Supported workflow patterns.

    Defines how agents are orchestrated to complete tasks.
    Phase 1 supports multi-step chain and multi-task workflow patterns.
    Future patterns enable multi-agent collaboration and advanced routing.
    """

    CHAIN = "chain"  # Sequential multi-step execution with context threading
    WORKFLOW = "workflow"  # DAG-based multi-task execution with parallel support
    ROUTING = "routing"  # Conditional agent routing (future support)
    PARALLEL = "parallel"  # Parallel agent execution (future support)
    ORCHESTRATOR_WORKERS = "orchestrator_workers"  # Leader-worker pattern (future support)
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"  # Evaluation-driven optimization (future support)
    GRAPH = "graph"  # Graph-based execution with conditionals (future support)


class SecretSource(str, Enum):
    """Supported secret sources.

    Defines where secrets (API keys, credentials) are retrieved from.
    Currently only environment variables are supported.
    """

    ENV = "env"  # Environment variables (currently supported)
    SECRETS_MANAGER = "secrets_manager"  # AWS Secrets Manager (future support)
    SSM = "ssm"  # AWS Systems Manager Parameter Store (future support)
    FILE = "file"  # File-based secrets (future support)


class ToolType(str, Enum):
    """Supported tool types.

    Defines the types of tools that agents can invoke during execution.
    Python tools must be in the allowlist for security.
    """

    PYTHON = "python"  # Python callables (allowlisted imports only)
    HTTP_EXECUTORS = "http_executors"  # HTTP API clients
    MCP = "mcp"  # Model Context Protocol servers (future support)


class Runtime(BaseModel):
    """Runtime configuration for model execution.

    Specifies which LLM provider to use, model selection, inference parameters,
    and execution policies. Budget and failure policies are logged but not enforced.
    """

    provider: ProviderType = Field(default=ProviderType.OLLAMA)
    model_id: str | None = None  # Provider-specific model identifier
    region: str | None = None  # AWS region (required for Bedrock)
    host: str | None = None  # Host URL (required for Ollama)
    temperature: float | None = None  # Sampling temperature for generation
    top_p: float | None = None  # Nucleus sampling parameter
    max_tokens: int | None = None  # Maximum tokens to generate
    max_parallel: int | None = Field(default=None, ge=1)  # Max concurrent tasks/workers
    budgets: dict[str, Any] | None = None  # Token/cost budgets (logged only)
    failure_policy: dict[str, Any] | None = None  # Retry and backoff configuration


class Secret(BaseModel):
    """Secret configuration."""

    source: SecretSource
    key: str
    name: str | None = None


class Skill(BaseModel):
    """Skill metadata for injection into system prompt."""

    id: str
    path: str | None = None
    description: str | None = None


class PythonTool(BaseModel):
    """Python callable tool configuration."""

    callable: str  # Import path like "strands_tools.http_request"


class HttpExecutor(BaseModel):
    """HTTP executor configuration."""

    id: str
    base_url: str
    headers: dict[str, str] | None = None
    timeout: int = 30

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base_url to prevent SSRF attacks.

        Blocks localhost, private IPs, AWS metadata endpoint, and non-HTTP protocols.
        Additional patterns can be configured via STRANDS_HTTP_BLOCKED_PATTERNS env var.

        Args:
            v: The base_url value to validate

        Returns:
            The validated base_url

        Raises:
            ValueError: If base_url matches a blocked pattern
        """
        from strands_cli.config import StrandsConfig

        config = StrandsConfig()

        # Combine default blocked patterns with user-configured ones
        blocked_patterns = DEFAULT_BLOCKED_URL_PATTERNS + config.http_blocked_patterns

        # Check against blocked patterns
        for pattern in blocked_patterns:
            if re.match(pattern, v, re.IGNORECASE):
                logger.warning(
                    "http_url_blocked",
                    violation_type="ssrf_attempt",
                    blocked_url=v,
                    matched_pattern=pattern,
                )
                raise ValueError(
                    f"base_url '{v}' matches blocked pattern (potential SSRF): {pattern}"
                )

        # If allowed domains are configured, enforce allowlist
        if config.http_allowed_domains:
            allowed = False
            for pattern in config.http_allowed_domains:
                if re.match(pattern, v, re.IGNORECASE):
                    allowed = True
                    break
            if not allowed:
                logger.warning(
                    "http_url_not_allowed",
                    violation_type="domain_not_in_allowlist",
                    url=v,
                )
                raise ValueError(
                    f"base_url '{v}' not in allowed domains. "
                    f"Configure STRANDS_HTTP_ALLOWED_DOMAINS to allow this domain."
                )

        return v


class McpServer(BaseModel):
    """MCP server configuration (future)."""

    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


class Tools(BaseModel):
    """Tool configurations."""

    python: list[PythonTool] | None = None
    http_executors: list[HttpExecutor] | None = None
    mcp: list[McpServer] | None = None

    @field_validator("python", mode="before")
    @classmethod
    def convert_python_tools(
        cls, v: list[str | dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        """Convert string format to PythonTool dict format.

        JSON Schema accepts strings, but Pydantic model expects dicts.
        This validator bridges the gap.

        Args:
            v: List of strings or dicts

        Returns:
            List of dicts suitable for PythonTool validation
        """
        if v is None:
            return None

        result = []
        for item in v:
            if isinstance(item, str):
                # Convert string to dict format
                result.append({"callable": item})
            else:
                # Already a dict
                result.append(item)

        return result


class Agent(BaseModel):
    """Agent configuration."""

    prompt: str
    tools: list[str] | None = None  # Tool IDs to use
    model_id: str | None = None  # Override runtime model


class ChainStep(BaseModel):
    """Single step in a chain pattern.

    Attributes:
        agent: Reference to an agent key in the agents map
        input: Prompt supplement or instruction (template allowed)
        vars: Per-step variable overrides for template rendering
        tool_overrides: Override agent's default tools for this step
    """

    agent: str  # Agent ID
    input: str | None = None  # Prompt template (optional)
    vars: dict[str, str | int | bool] | None = None  # Per-step variables
    tool_overrides: list[str] | None = None  # Tool ID overrides


class WorkflowTask(BaseModel):
    """Single task in a workflow pattern.

    Attributes:
        id: Unique identifier for the task
        agent: Reference to an agent key in the agents map
        deps: List of task IDs this task depends on
        description: Human-readable task description
        input: Prompt supplement or instruction (template allowed)
    """

    id: str  # Unique task identifier (required)
    agent: str  # Agent ID (required)
    deps: list[str] | None = None  # Task dependencies
    description: str | None = None  # Human-readable description
    input: str | None = None  # Prompt template (optional)


class Route(BaseModel):
    """Single route in a routing pattern.

    Attributes:
        then: Chain of steps to execute if this route is selected
    """

    then: list[ChainStep] | None = None  # Steps to execute for this route


class RouterConfig(BaseModel):
    """Router configuration for routing pattern.

    Attributes:
        agent: Agent ID that performs classification
        input: Prompt template for router agent
        max_retries: Maximum retry attempts for malformed JSON (default: 2)
    """

    agent: str  # Agent ID for classification
    input: str | None = None  # Router prompt template
    max_retries: int = Field(default=2, ge=0)  # Retry limit for malformed responses


class RouterDecision(BaseModel):
    """Router agent decision output.

    Attributes:
        route: Name of the selected route
    """

    route: str  # Selected route name


class RoutingConfig(BaseModel):
    """Routing pattern configuration.

    Attributes:
        router: Router agent configuration
        routes: Map of route names to route definitions
    """

    router: RouterConfig
    routes: dict[str, Route]  # route_name -> Route definition


class ParallelBranch(BaseModel):
    """Single branch in a parallel pattern.

    Attributes:
        id: Unique branch identifier
        steps: Chain of steps to execute in this branch
    """

    id: str  # Unique branch identifier (required)
    steps: list[ChainStep]  # Steps to execute sequentially (min 1)


class EvaluatorConfig(BaseModel):
    """Evaluator configuration for evaluator-optimizer pattern.

    Attributes:
        agent: Evaluator agent ID (required)
        input: Evaluation prompt template (optional)
    """

    agent: str  # Evaluator agent ID (required)
    input: str | None = None  # Evaluation prompt template (optional)


class AcceptConfig(BaseModel):
    """Acceptance criteria for evaluator-optimizer pattern.

    Attributes:
        min_score: Minimum score (0-100) to accept output
        max_iters: Maximum iterations (default: 3)
    """

    min_score: int = Field(ge=0, le=100)  # Minimum score (0-100, required)
    max_iters: int = Field(default=3, ge=1)  # Maximum iterations (default: 3)


class EvaluatorDecision(BaseModel):
    """Evaluator agent decision output.

    Expected JSON format from evaluator agent:
    {"score": 85, "issues": ["Issue 1", ...], "fixes": ["Fix 1", ...]}

    Attributes:
        score: Quality score (0-100)
        issues: Identified issues (optional)
        fixes: Suggested fixes (optional)
    """

    score: int = Field(ge=0, le=100)  # Quality score (0-100)
    issues: list[str] | None = None  # Identified issues (optional)
    fixes: list[str] | None = None  # Suggested fixes (optional)


class PatternConfig(BaseModel):
    """Pattern-specific configuration."""

    steps: list[ChainStep] | None = None  # For chain
    tasks: list[WorkflowTask] | None = None  # For workflow
    router: RouterConfig | None = None  # For routing
    routes: dict[str, Route] | None = None  # For routing
    branches: list[ParallelBranch] | None = None  # For parallel
    reduce: ChainStep | None = None  # For parallel reduce step

    # Evaluator-optimizer fields
    producer: str | None = None  # Producer agent ID
    evaluator: EvaluatorConfig | None = None  # Evaluator config
    accept: AcceptConfig | None = None  # Accept criteria
    revise_prompt: str | None = None  # Revision prompt template


class Pattern(BaseModel):
    """Workflow execution pattern."""

    type: PatternType
    config: PatternConfig


class Artifact(BaseModel):
    """Output artifact configuration."""

    path: str
    from_: str = Field(alias="from")  # Template like "{{ last_response }}"


class Outputs(BaseModel):
    """Output configuration."""

    artifacts: list[Artifact] | None = None


class Telemetry(BaseModel):
    """Telemetry configuration (parsed but no-op in MVP)."""

    otel: dict[str, Any] | None = None
    redact: dict[str, Any] | None = None


class Security(BaseModel):
    """Security configuration (parsed but not enforced in MVP)."""

    guardrails: dict[str, Any] | None = None


class ContextPolicy(BaseModel):
    """Context management policy (parsed but no-op in MVP)."""

    compaction: dict[str, Any] | None = None
    notes: dict[str, Any] | None = None
    retrieval: dict[str, Any] | None = None


class Environment(BaseModel):
    """Environment configuration."""

    secrets: list[Secret] | None = None
    mounts: dict[str, str] | None = None


class Spec(BaseModel):
    """Complete workflow specification.

    This is the top-level Pydantic model for a workflow spec,
    mapped from validated YAML/JSON input after JSON Schema validation.

    Structure:
        - Runtime: Model provider and execution settings
        - Agents: Map of agent_id -> Agent configuration
        - Pattern: Orchestration pattern (chain, workflow, etc.)
        - Tools: Python callables, HTTP executors, MCP servers
        - Outputs: Artifact generation templates
        - Environment: Secrets and mounts
        - Telemetry: OTEL configuration (parsed but not emitted)
    """

    version: int | str = 0
    name: str
    description: str | None = None
    tags: list[str] | None = None
    runtime: Runtime
    inputs: dict[str, Any] | None = None
    env: Environment | None = None
    telemetry: Telemetry | None = None
    context_policy: ContextPolicy | None = None
    skills: list[Skill] | None = None
    tools: Tools | None = None
    agents: dict[str, Agent]
    pattern: Pattern
    outputs: Outputs | None = None
    security: Security | None = None


class CapabilityIssue(BaseModel):
    """A single capability issue detected in a spec."""

    pointer: str  # JSONPointer to the problematic location
    reason: str  # Human-readable explanation
    remediation: str  # How to fix it


class CapabilityReport(BaseModel):
    """Report of capability compatibility for a spec.

    Analyzes whether a workflow can be executed with current capabilities.
    If unsupported features are detected, provides detailed issues with
    JSONPointer locations and remediation instructions.

    Attributes:
        supported: True if spec is fully compatible
        issues: List of compatibility problems (empty if supported)
        normalized: Extracted execution parameters for supported specs
        spec_fingerprint: SHA-256 hash of spec content for tracking
    """

    supported: bool
    issues: list[CapabilityIssue] = Field(default_factory=list)
    normalized: dict[str, Any] | None = None  # Normalized values executor will use
    spec_fingerprint: str | None = None  # SHA-256 of spec content


class RunResult(BaseModel):
    """Result of executing a single-agent workflow.

    Captures execution outcome, timing, and artifact locations.
    Used for both successful and failed executions.

    Attributes:
        success: True if workflow completed without errors
        last_response: Final agent response text (for artifact templating)
        error: Error message if execution failed
        agent_id: ID of the agent that executed
        pattern_type: Pattern used for execution
        started_at: ISO 8601 timestamp of execution start
        completed_at: ISO 8601 timestamp of execution completion
        duration_seconds: Total execution time
        artifacts_written: Paths to generated artifact files
        execution_context: Additional context for artifact templating (steps, tasks, etc.)
    """

    success: bool
    last_response: str | None = None
    error: str | None = None
    agent_id: str
    pattern_type: PatternType
    started_at: str  # ISO 8601 timestamp
    completed_at: str  # ISO 8601 timestamp
    duration_seconds: float
    artifacts_written: list[str] = Field(default_factory=list)
    execution_context: dict[str, Any] = Field(default_factory=dict)

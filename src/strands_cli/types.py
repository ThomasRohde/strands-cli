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
    StreamChunk: Streaming response chunk for async execution
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

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


# ===== Streaming Types (Phase 3) =====

StreamChunkType = Literal["token", "workflow_start", "step_start", "step_complete", "complete"]


@dataclass
class StreamChunk:
    """Streaming response chunk for async workflow execution.

    Emitted during workflow execution to provide real-time progress updates.
    Note: Token-by-token streaming not yet implemented in Phase 3.
    Returns complete responses as 'complete' chunks for now.

    Chunk Types:
        - token: Individual token from LLM response (future)
        - workflow_start: Workflow execution begins
        - step_start: Step/task/branch/node begins
        - step_complete: Step/task/branch/node completes
        - complete: Workflow execution finishes

    Attributes:
        chunk_type: Type of chunk
        data: Chunk-specific data (varies by chunk_type)
        timestamp: When the chunk was generated
    """

    chunk_type: StreamChunkType
    data: dict[str, Any]
    timestamp: datetime


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
    """HTTP executor configuration with agent guidance metadata.

    Metadata fields (description, examples, common_endpoints) are used to generate
    richer TOOL_SPEC descriptions that help LLM agents understand:
    - What the API does and when to use it
    - How to construct valid requests with examples
    - Which endpoints are available and what they return
    - Expected response formats and authentication requirements
    """

    id: str
    base_url: str
    headers: dict[str, str] | None = None
    timeout: int = 30

    # Agent guidance metadata (optional)
    description: str | None = Field(
        None,
        description="Human-readable description of what this HTTP executor does and when to use it",
    )
    examples: list[dict[str, Any]] | None = Field(
        None,
        description="Example requests showing how to use this executor (method, path, json_data)",
    )
    common_endpoints: list[dict[str, str]] | None = Field(
        None,
        description="List of common endpoints with path and description for agent guidance",
    )
    response_format: str | None = Field(
        None,
        description="Expected response format (e.g., 'JSON', 'XML', 'plain text')",
    )
    authentication_info: str | None = Field(
        None,
        description="Information about authentication requirements (for documentation, not credentials)",
    )

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
    """MCP server configuration (Phase 9).

    Supports two transport types:
    1. stdio: command-based MCP servers (npx, uvx, etc.)
    2. HTTPS: remote MCP servers via HTTPS endpoint
    """

    id: str
    # stdio transport fields
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # HTTPS transport fields
    url: str | None = None
    headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> "McpServer":
        """Validate that either command or url is provided, but not both."""
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError("MCP server must have either 'command' or 'url'")
        if has_command and has_url:
            raise ValueError("MCP server cannot have both 'command' and 'url'")

        return self


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


class HITLStep(BaseModel):
    """Human-in-the-loop pause point.

    Pauses workflow execution to request user input or approval.
    Session is automatically saved and execution exits with EX_HITL_PAUSE.
    User resumes with --hitl-response flag.

    Attributes:
        type: Must be "hitl" to identify this as a HITL step
        prompt: Message displayed to user requesting input
        context_display: Context to show user (supports templates)
        default: Default response if user provides empty input (Phase 2)
        timeout_seconds: Seconds before timeout (0=no timeout, Phase 2)
    """

    type: str = Field(default="hitl", pattern="^hitl$")  # Must be "hitl"
    prompt: str = Field(..., description="Message to display to user")
    context_display: str | None = Field(
        None, description="Context to show user (supports templates like {{ steps[0].response }})"
    )
    default: str | None = Field(
        None, description="Default response if empty (enforcement in Phase 2)"
    )
    timeout_seconds: int = Field(
        default=0, ge=0, description="Seconds before timeout (0=no timeout, enforcement in Phase 2)"
    )


class HITLState(BaseModel):
    """HITL execution state stored in pattern_state.

    Tracks the state of an active HITL pause, including the prompt shown
    to the user and the response (when provided).

    Supports chain (step_index), workflow (task_id + layer_index),
    parallel (branch_id + step_type), and graph (node_id) patterns.

    Attributes:
        active: Whether HITL is currently waiting for user input
        step_index: Index of the HITL step (chain/parallel branch patterns)
        task_id: ID of the HITL task (workflow pattern, optional)
        layer_index: Index of execution layer (workflow pattern, optional)
        branch_id: ID of the branch with HITL step (parallel pattern, optional)
        step_type: Type of parallel HITL: 'branch' or 'reduce' (parallel pattern, optional)
        node_id: ID of the HITL node (graph pattern, optional)
        prompt: Prompt displayed to user
        context_display: Rendered context shown to user
        default_response: Default if empty (Phase 2)
        timeout_at: ISO 8601 timeout timestamp (Phase 2)
        user_response: User's response when resumed
    """

    active: bool = Field(..., description="Whether HITL is currently waiting")

    # Chain pattern fields
    step_index: int | None = Field(None, description="Index of HITL step (chain/parallel branch)")

    # Workflow pattern fields
    task_id: str | None = Field(None, description="ID of HITL task (workflow pattern)")
    layer_index: int | None = Field(None, description="Execution layer index (workflow pattern)")

    # Parallel pattern fields
    branch_id: str | None = Field(None, description="Branch ID (parallel pattern)")
    step_type: str | None = Field(
        None, description="HITL step type: 'branch' or 'reduce' (parallel pattern)"
    )

    # Graph pattern fields
    node_id: str | None = Field(None, description="ID of HITL node (graph pattern)")

    # Evaluator-optimizer pattern fields
    iteration_index: int | None = Field(
        None, description="Iteration index (evaluator-optimizer pattern)"
    )

    # Orchestrator-workers pattern fields
    phase: str | None = Field(
        None,
        description="Orchestrator phase: 'decomposition' or 'reduce' (orchestrator-workers pattern)",
    )
    worker_count: int | None = Field(
        None, ge=0, description="Number of workers (orchestrator-workers pattern)"
    )

    # Routing pattern fields
    router_review: bool | None = Field(
        None, description="Router review HITL gate (routing pattern)"
    )

    # Common fields
    prompt: str = Field(..., description="Prompt displayed to user")
    context_display: str | None = Field(None, description="Context shown to user")
    default_response: str | None = Field(None, description="Default if empty")
    timeout_at: str | None = Field(None, description="ISO 8601 timeout timestamp")
    user_response: str | None = Field(None, description="User's response when resumed")

    @model_validator(mode="after")
    def validate_pattern_fields(self) -> "HITLState":
        """Validate pattern-specific fields are present and consistent."""
        has_chain_fields = self.step_index is not None and self.branch_id is None
        has_workflow_fields = self.task_id is not None or self.layer_index is not None
        has_parallel_fields = self.branch_id is not None or self.step_type is not None
        has_graph_fields = self.node_id is not None
        has_evaluator_fields = self.iteration_index is not None
        has_orchestrator_fields = self.phase is not None or self.worker_count is not None
        has_routing_fields = self.router_review is not None

        # Count how many pattern field sets are present
        pattern_count = sum(
            [
                has_chain_fields,
                has_workflow_fields,
                has_parallel_fields,
                has_graph_fields,
                has_evaluator_fields,
                has_orchestrator_fields,
                has_routing_fields,
            ]
        )

        if pattern_count == 0:
            raise ValueError(
                "HITLState must have fields for one pattern: "
                "step_index (chain) OR task_id+layer_index (workflow) OR "
                "branch_id/step_type (parallel) OR node_id (graph) OR "
                "iteration_index (evaluator-optimizer) OR phase/worker_count (orchestrator-workers) OR "
                "router_review (routing)"
            )
        if pattern_count > 1:
            raise ValueError(
                "HITLState cannot mix fields from multiple patterns. "
                "Use only chain OR workflow OR parallel OR graph OR evaluator-optimizer OR orchestrator-workers OR routing fields."
            )

        # Workflow pattern requires both task_id and layer_index
        if has_workflow_fields and (self.task_id is None or self.layer_index is None):
            raise ValueError("Workflow HITL requires both task_id and layer_index")

        # Parallel pattern validation
        if has_parallel_fields:
            if self.step_type not in ["branch", "reduce", None]:
                raise ValueError("Parallel HITL step_type must be 'branch' or 'reduce'")
            # Branch HITL requires both branch_id and step_type='branch'
            if self.step_type == "branch" and not self.branch_id:
                raise ValueError("Parallel branch HITL requires branch_id")
            # Branch HITL also needs step_index
            if self.step_type == "branch" and self.step_index is None:
                raise ValueError("Parallel branch HITL requires step_index")
            # Reduce HITL requires step_type='reduce' but no branch_id
            if self.step_type == "reduce" and self.branch_id:
                raise ValueError("Parallel reduce HITL should not have branch_id")

        # Orchestrator pattern validation
        if has_orchestrator_fields and self.phase not in ["decomposition", "reduce", None]:
            raise ValueError("Orchestrator HITL phase must be 'decomposition' or 'reduce'")

        return self


class ChainStep(BaseModel):
    """Single step in a chain pattern.

    Supports two step types:
    1. Agent step: Executes an agent with optional input template
    2. HITL step: Pauses for human input/approval

    Exactly one of (agent) or (type="hitl") must be present.

    Attributes:
        agent: Reference to an agent key in the agents map (agent step)
        input: Prompt supplement or instruction (template allowed, agent step)
        vars: Per-step variable overrides for template rendering (agent step)
        tool_overrides: Override agent's default tools for this step (agent step)
        type: Must be "hitl" for HITL steps
        prompt: Message to display to user (HITL step)
        context_display: Context to show user (HITL step)
        default: Default response if empty (HITL step)
        timeout_seconds: Timeout in seconds (HITL step)
    """

    # Agent step fields
    agent: str | None = None  # Agent ID (agent step)
    input: str | None = None  # Prompt template (agent step, optional)
    vars: dict[str, str | int | bool] | None = None  # Per-step variables (agent step)
    tool_overrides: list[str] | None = None  # Tool ID overrides (agent step)

    # HITL step fields
    type: str | None = None  # "hitl" for HITL steps
    prompt: str | None = None  # HITL prompt
    context_display: str | None = None  # HITL context
    default: str | None = None  # HITL default (Phase 2)
    timeout_seconds: int | None = None  # HITL timeout (Phase 2)

    @model_validator(mode="after")
    def validate_step_type(self) -> "ChainStep":
        """Validate exactly one of agent or HITL type is present."""
        is_agent_step = self.agent is not None
        is_hitl_step = self.type == "hitl"

        if not is_agent_step and not is_hitl_step:
            raise ValueError(
                "ChainStep must have either 'agent' (agent step) or 'type: hitl' (HITL step)"
            )

        if is_agent_step and is_hitl_step:
            raise ValueError(
                "ChainStep cannot have both 'agent' and 'type: hitl'. "
                "Use separate steps for agent execution and HITL pauses."
            )

        # HITL step validation
        if is_hitl_step:
            if not self.prompt:
                raise ValueError("HITL step must have 'prompt' field")
            if self.timeout_seconds is not None and self.timeout_seconds < 0:
                raise ValueError("HITL timeout_seconds must be >= 0")

        return self


class HITLTask(BaseModel):
    """Human-in-the-loop pause task for workflow pattern.

    Pauses workflow execution at a specific task to request user input or approval.
    Session is automatically saved and execution exits with EX_HITL_PAUSE.
    User resumes with --hitl-response flag.

    Attributes:
        id: Unique identifier for the task (required for dependency tracking)
        type: Must be "hitl" to identify this as a HITL task
        deps: List of task IDs this task depends on
        prompt: Message displayed to user requesting input
        context_display: Context to show user (supports templates)
        default: Default response if user provides empty input (Phase 2)
        timeout_seconds: Seconds before timeout (0=no timeout, Phase 2)
    """

    id: str  # Unique task identifier (required)
    type: str = Field(default="hitl", pattern="^hitl$")  # Must be "hitl"
    deps: list[str] | None = None  # Task dependencies
    prompt: str = Field(..., description="Message to display to user")
    context_display: str | None = Field(
        None,
        description="Context to show user (supports templates like {{ tasks.task_id.response }})",
    )
    default: str | None = Field(
        None, description="Default response if empty (enforcement in Phase 2)"
    )
    timeout_seconds: int = Field(
        default=0, ge=0, description="Seconds before timeout (0=no timeout, enforcement in Phase 2)"
    )


class WorkflowTask(BaseModel):
    """Single task in a workflow pattern.

    Supports two task types:
    1. Agent task: Executes an agent with optional input template
    2. HITL task: Pauses for human input/approval

    Exactly one of (agent) or (type="hitl") must be present.

    Attributes:
        id: Unique identifier for the task (required)
        agent: Reference to an agent key in the agents map (agent task)
        deps: List of task IDs this task depends on
        description: Human-readable task description (agent task)
        input: Prompt supplement or instruction (agent task, template allowed)
        type: Must be "hitl" for HITL tasks
        prompt: Message to display to user (HITL task)
        context_display: Context to show user (HITL task)
        default: Default response if empty (HITL task)
        timeout_seconds: Timeout in seconds (HITL task)
    """

    id: str  # Unique task identifier (required for all task types)

    # Agent task fields
    agent: str | None = None  # Agent ID (agent task, required if not HITL)
    description: str | None = None  # Human-readable description (agent task)
    input: str | None = None  # Prompt template (agent task, optional)

    # HITL task fields
    type: str | None = None  # "hitl" for HITL tasks
    prompt: str | None = None  # HITL prompt
    context_display: str | None = None  # HITL context
    default: str | None = None  # HITL default (Phase 2)
    timeout_seconds: int | None = None  # HITL timeout (Phase 2)

    # Common fields
    deps: list[str] | None = None  # Task dependencies (both task types)

    @model_validator(mode="after")
    def validate_task_type(self) -> "WorkflowTask":
        """Validate exactly one of agent or HITL type is present."""
        has_agent = self.agent is not None
        has_hitl = self.type == "hitl"

        if has_agent and has_hitl:
            raise ValueError("Task cannot have both 'agent' and 'type: hitl'")
        if not has_agent and not has_hitl:
            raise ValueError("Task must have either 'agent' or 'type: hitl'")

        # Validate HITL-specific requirements
        if has_hitl:
            if not self.prompt:
                raise ValueError("HITL task must have 'prompt' field")
            if self.timeout_seconds is not None and self.timeout_seconds < 0:
                raise ValueError("HITL timeout_seconds must be >= 0")
            # Agent-specific fields not allowed on HITL tasks
            if self.agent is not None:
                raise ValueError("HITL task cannot have 'agent' field")
            if self.description is not None:
                raise ValueError(
                    "HITL task cannot have 'description' field (reserved for agent tasks)"
                )
            if self.input is not None:
                raise ValueError(
                    "HITL task cannot have 'input' field (use 'context_display' instead)"
                )

        # Validate agent-specific requirements
        if has_agent:
            # HITL-specific fields not allowed on agent tasks
            if self.prompt is not None:
                raise ValueError("Agent task cannot have 'prompt' field (HITL-only)")
            if self.context_display is not None:
                raise ValueError("Agent task cannot have 'context_display' field (HITL-only)")
            if self.default is not None:
                raise ValueError("Agent task cannot have 'default' field (HITL-only)")
            if self.timeout_seconds is not None:
                raise ValueError("Agent task cannot have 'timeout_seconds' field (HITL-only)")

        return self


class Route(BaseModel):
    """Single route in a routing pattern.

    Attributes:
        then: Chain of steps to execute if this route is selected
    """

    then: list[ChainStep] | None = None  # Steps to execute for this route

    @property
    def steps(self) -> list[ChainStep] | None:
        """Alias for route steps to maintain backward compatibility."""

        return self.then


class RouterConfig(BaseModel):
    """Router configuration for routing pattern.

    Attributes:
        agent: Agent ID that performs classification
        input: Prompt template for router agent
        max_retries: Maximum retry attempts for malformed JSON (default: 2)
        review_router: Optional HITL step for router decision review/override
    """

    agent: str  # Agent ID for classification
    input: str | None = None  # Router prompt template
    max_retries: int = Field(default=2, ge=0)  # Retry limit for malformed responses
    review_router: "ChainStep | None" = None  # Optional HITL review of router decision


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


class ConditionalChoice(BaseModel):
    """Conditional edge choice for graph pattern.

    Represents a single condition-target pair in a conditional edge.
    The 'when' field is either an expression or the literal string "else".

    Attributes:
        when: Condition expression or "else" for default fallback
        to: Target node ID to transition to if condition is true
    """

    when: str  # Condition expression or "else"
    to: str  # Target node ID


class GraphEdge(BaseModel):
    """Edge definition for graph pattern.

    Represents a transition between nodes. Must have either 'to' (static)
    or 'choose' (conditional), but not both.

    Attributes:
        from_: Source node ID
        to: Static target node IDs (sequential execution)
        choose: Conditional choices with expressions
    """

    from_: str = Field(alias="from")  # Source node ID
    to: list[str] | None = None  # Static targets (sequential)
    choose: list[ConditionalChoice] | None = None  # Conditional choices


class GraphNode(BaseModel):
    """Node definition for graph pattern (agent or HITL).

    Represents a single execution node in the graph.
    Each node is either an agent execution node or a HITL pause node.

    Agent node attributes:
        agent: Agent ID to execute at this node
        input: Optional input template (defaults to auto-generated)

    HITL node attributes:
        type: Node type identifier ("hitl")
        prompt: Message displayed to user
        context_display: Context template for review
        default: Default response on timeout
        timeout_seconds: Timeout in seconds (0 = no timeout)
    """

    # Agent node fields
    agent: str | None = Field(None, description="Agent ID")
    input: str | None = Field(None, description="Input template")

    # HITL node fields
    type: str | None = Field(None, description="Node type (hitl)")
    prompt: str | None = Field(None, description="HITL prompt")
    context_display: str | None = Field(None, description="Context template")
    default: str | None = Field(None, description="Default response")
    timeout_seconds: int | None = Field(None, ge=0, description="Timeout")

    @model_validator(mode="after")
    def validate_node_type(self) -> "GraphNode":
        """Validate node is either agent or HITL."""
        is_agent = self.agent is not None
        is_hitl = self.type == "hitl" and self.prompt is not None

        if not (is_agent or is_hitl):
            raise ValueError(
                "Node must be agent (with 'agent' field) or HITL (with 'type: hitl' and 'prompt')"
            )

        if is_agent and is_hitl:
            raise ValueError("Node cannot be both agent and HITL")

        # HITL-specific validation
        if is_hitl:
            if self.timeout_seconds is not None and self.timeout_seconds < 0:
                raise ValueError("HITL timeout_seconds must be >= 0")
            # Agent-specific fields not allowed on HITL nodes
            if self.agent is not None:
                raise ValueError("HITL node cannot have 'agent' field")
            if self.input is not None:
                raise ValueError(
                    "HITL node cannot have 'input' field (use 'context_display' instead)"
                )

        # Agent-specific validation
        if is_agent:
            # HITL-specific fields not allowed on agent nodes
            if self.type is not None:
                raise ValueError("Agent node cannot have 'type' field (HITL-only)")
            if self.prompt is not None:
                raise ValueError("Agent node cannot have 'prompt' field (HITL-only)")
            if self.context_display is not None:
                raise ValueError("Agent node cannot have 'context_display' field (HITL-only)")
            if self.default is not None:
                raise ValueError("Agent node cannot have 'default' field (HITL-only)")
            if self.timeout_seconds is not None:
                raise ValueError("Agent node cannot have 'timeout_seconds' field (HITL-only)")

        return self


class OrchestratorLimits(BaseModel):
    """Orchestrator execution limits.

    Controls concurrency and iteration bounds for orchestrator-workers pattern.

    Attributes:
        min_workers: Minimum concurrent workers (default: 1 when specified)
        max_workers: Maximum concurrent workers (default: unlimited)
        max_rounds: Maximum orchestrator delegation cycles (default: unlimited)
    """

    min_workers: int | None = Field(None, ge=1)  # Minimum concurrent workers
    max_workers: int | None = Field(None, ge=1)  # Max concurrent workers
    max_rounds: int | None = Field(None, ge=1)  # Max delegation rounds

    @model_validator(mode="after")
    def _validate_worker_bounds(self) -> "OrchestratorLimits":
        """Ensure min/max worker bounds are consistent."""

        if (
            self.min_workers is not None
            and self.max_workers is not None
            and self.min_workers > self.max_workers
        ):
            raise ValueError("min_workers cannot be greater than max_workers")
        return self


class OrchestratorConfig(BaseModel):
    """Orchestrator configuration for orchestrator-workers pattern.

    The orchestrator agent breaks down tasks into subtasks and delegates
    to workers. Expected JSON format from orchestrator:
    [{"task": "description"}, ...]

    Attributes:
        agent: Orchestrator agent ID (required)
        limits: Execution limits (optional)
    """

    agent: str  # Orchestrator agent ID (required)
    limits: OrchestratorLimits | None = None  # Execution limits (optional)


class WorkerTemplate(BaseModel):
    """Worker template configuration for orchestrator-workers pattern.

    Defines the agent and tools used by all workers in the pool.

    Attributes:
        agent: Worker agent ID (required)
        tools: Tool overrides for workers (optional)
    """

    agent: str  # Worker agent ID (required)
    tools: list[str] | None = None  # Tool overrides (optional)


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
    review_gate: HITLStep | None = None  # HITL pause between iterations (optional)

    # Orchestrator-workers fields
    orchestrator: OrchestratorConfig | None = None  # Orchestrator config
    decomposition_review: HITLStep | None = None  # HITL pause after task decomposition (optional)
    worker_template: WorkerTemplate | None = None  # Worker template
    reduce_review: HITLStep | None = None  # HITL pause before reduce step (optional)
    writeup: ChainStep | None = None  # Optional final synthesis step

    # Graph fields
    nodes: dict[str, GraphNode] | None = None  # For graph pattern
    edges: list[GraphEdge] | None = None  # For graph pattern
    max_iterations: int = Field(default=10, ge=1)  # Per-node iteration limit


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


class OTELConfig(BaseModel):
    """OpenTelemetry configuration."""

    endpoint: str | None = Field(
        None, description="OTLP endpoint URL (e.g., http://localhost:4317)"
    )
    service_name: str | None = Field(None, description="Service name for traces")
    sample_ratio: float = Field(1.0, ge=0.0, le=1.0, description="Trace sampling ratio (0.0-1.0)")


class RedactionConfig(BaseModel):
    """Telemetry redaction configuration."""

    tool_inputs: bool = Field(True, description="Redact tool inputs from spans")
    tool_outputs: bool = Field(False, description="Redact tool outputs from spans")


class Telemetry(BaseModel):
    """Telemetry configuration."""

    otel: OTELConfig | None = None
    redact: RedactionConfig | None = None


class Security(BaseModel):
    """Security configuration (parsed but not enforced in MVP)."""

    guardrails: dict[str, Any] | None = None


class Compaction(BaseModel):
    """Context compaction configuration.

    Controls when and how conversation context is compressed using
    SummarizingConversationManager to prevent token overflow.

    Attributes:
        enabled: Enable proactive context compaction (default: True)
        when_tokens_over: Trigger compaction before reaching this token threshold
        summary_ratio: Proportion of older messages to summarize (0.0-1.0, default: 0.35)
        preserve_recent_messages: Number of recent messages to keep intact (default: 12)
        summarization_model: Optional cheaper model for summarization (e.g., "gpt-4o-mini")
    """

    enabled: bool = True
    when_tokens_over: int | None = Field(None, ge=1000)  # Minimum 1K tokens
    summary_ratio: float = Field(0.35, ge=0.0, le=1.0)  # 0-100% of context
    preserve_recent_messages: int = Field(12, ge=1)  # At least 1 message
    summarization_model: str | None = None  # Optional cheaper model

    @field_validator("summary_ratio")
    @classmethod
    def validate_summary_ratio(cls, v: float) -> float:
        """Validate summary_ratio is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"summary_ratio must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("preserve_recent_messages")
    @classmethod
    def validate_preserve_recent_messages(cls, v: int) -> int:
        """Validate preserve_recent_messages is at least 1."""
        if v < 1:
            raise ValueError(f"preserve_recent_messages must be at least 1, got {v}")
        return v

    @field_validator("when_tokens_over")
    @classmethod
    def validate_when_tokens_over(cls, v: int | None) -> int | None:
        """Validate when_tokens_over is at least 1000 if set."""
        if v is not None and v < 1000:
            raise ValueError(f"when_tokens_over must be at least 1000, got {v}")
        return v


class Notes(BaseModel):
    """Structured notes configuration.

    Enables persistent note-taking across workflow execution steps for
    cross-step continuity and multi-session workflow resumption.

    Attributes:
        file: Path to notes file (e.g., "artifacts/notes.md")
        include_last: Number of recent notes to inject into agent context (default: 12)
        format: Output format for notes (default: "markdown")
    """

    file: str  # Path to notes file
    include_last: int = Field(12, ge=1)  # At least 1 note
    format: str = "markdown"  # Future: support JSON

    @field_validator("include_last")
    @classmethod
    def validate_include_last(cls, v: int) -> int:
        """Validate include_last is at least 1."""
        if v < 1:
            raise ValueError(f"include_last must be at least 1, got {v}")
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate format is supported."""
        supported_formats = {"markdown", "json"}
        if v not in supported_formats:
            raise ValueError(f"format must be one of {supported_formats}, got '{v}'")
        return v


class Retrieval(BaseModel):
    """JIT retrieval configuration.

    Enables just-in-time context retrieval tools for workflows to access
    file and shell operations without loading entire files into context.
    Tools are explicitly enabled via jit_tools list for security.

    Attributes:
        jit_tools: List of JIT tool IDs to enable (e.g., ["grep", "head", "tail", "search"])
        mcp_servers: List of MCP server IDs from tools.mcp (Phase 9 - not yet implemented)
    """

    jit_tools: list[str] | None = Field(
        None, description="JIT tool IDs to enable (grep, head, tail, search)"
    )
    mcp_servers: list[str] | None = Field(
        None, description="MCP server IDs (Phase 9 - not yet implemented)"
    )

    @field_validator("jit_tools")
    @classmethod
    def validate_jit_tools(cls, v: list[str] | None) -> list[str] | None:
        """Validate JIT tool names to prevent injection attacks."""
        if v is None:
            return None

        # Allowed tool IDs (alphanumeric, underscore, hyphen only)
        import re

        valid_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

        for tool_id in v:
            if not valid_pattern.match(tool_id):
                raise ValueError(
                    f"Invalid JIT tool ID '{tool_id}': must contain only "
                    "alphanumeric characters, underscores, or hyphens"
                )

        return v


class ContextPolicy(BaseModel):
    """Context management policy.

    Configures intelligent context management for long-running workflows:
    - Compaction: Automatic context compression when token thresholds are reached
    - Notes: Structured note-taking for cross-step continuity
    - Retrieval: JIT context retrieval tools for on-demand file access

    Phase 6.1 implements compaction; Phase 6.2 implements notes; Phase 6.3 implements retrieval.
    """

    compaction: Compaction | None = None
    notes: Notes | None = None
    retrieval: Retrieval | None = None


class ContextNote(BaseModel):
    """Structured context note for cross-step continuity.

    Captures key information during workflow execution that should be
    persisted and made available to subsequent steps or future workflow runs.

    Attributes:
        timestamp: ISO 8601 timestamp when note was created
        step_id: Step/task/branch identifier (e.g., "step_0", "task_analyze", "branch_research")
        agent_id: Agent that created the note
        content: Note content (markdown or plain text)
        metadata: Optional metadata (tags, importance, etc.)
    """

    timestamp: str  # ISO 8601 timestamp
    step_id: str  # Step/task/branch identifier
    agent_id: str  # Agent ID
    content: str  # Note content
    metadata: dict[str, Any] | None = None  # Optional metadata


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
        message: Human-readable status message (optional)
        exit_code: Exit code (e.g., EX_OK, EX_HITL_PAUSE)
        pattern_type: Pattern used for execution
        session_id: Session ID for resumable workflows (HITL pauses)
        agent_id: ID of the agent that executed
        last_response: Final agent response text (for artifact templating)
        error: Error message if execution failed
        tokens_estimated: Estimated token count for execution
        started_at: ISO 8601 timestamp of execution start
        completed_at: ISO 8601 timestamp of execution completion
        duration_seconds: Total execution time
        artifacts_written: Paths to generated artifact files
        execution_context: Additional context for artifact templating (steps, tasks, etc.)
        spec: Optional workflow spec (attached during resume for artifact writing)
        variables: Optional user variables (attached during resume for artifact writing)
    """

    success: bool
    message: str | None = None
    exit_code: int | None = None
    pattern_type: PatternType
    session_id: str | None = None
    agent_id: str
    last_response: str | None = None
    error: str | None = None
    tokens_estimated: int = 0
    started_at: str  # ISO 8601 timestamp
    completed_at: str  # ISO 8601 timestamp
    duration_seconds: float
    artifacts_written: list[str] = Field(default_factory=list)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    spec: "Spec | None" = None  # Attached during resume for artifact writing
    variables: dict[str, Any] | None = None  # Attached during resume for artifact writing

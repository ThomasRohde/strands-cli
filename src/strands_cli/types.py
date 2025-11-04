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

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
    Currently supports single-agent patterns (chain, workflow).
    Future patterns enable multi-agent collaboration.
    """

    CHAIN = "chain"  # Sequential steps (currently limited to 1 step)
    WORKFLOW = "workflow"  # Task-based execution (currently limited to 1 task)
    ROUTING = "routing"  # Conditional agent routing (future support)
    PARALLEL = "parallel"  # Parallel agent execution (future support)
    ORCHESTRATOR_WORKERS = "orchestrator_workers"  # Leader-worker pattern (future support)
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"  # Evaluation-driven optimization (future support)
    GRAPH = "graph"  # DAG-based execution (future support)


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


class PatternConfig(BaseModel):
    """Pattern-specific configuration."""

    steps: list[ChainStep] | None = None  # For chain
    tasks: list[WorkflowTask] | None = None  # For workflow
    # Future: routing rules, parallel config, graph DAG, etc.


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

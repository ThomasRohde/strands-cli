"""Fluent builder API for programmatic workflow construction.

This module provides type-safe, fail-fast builders for all 7 workflow patterns.
Builders validate configuration at build time using Pydantic, catching errors
early with actionable messages.

Design Principles:
1. **Fail fast**: Validate on .build() using Pydantic (catch errors early)
2. **Explicit agent calls**: Require .agent() definition before use (no implicit creation)
3. **Explicit runtime**: Require .runtime() call (no environment variable fallback)
4. **Pattern-specific HITL**: Use pattern-specific methods (.review_gate(), etc.) not generic .hitl()

Example:
    >>> from strands_cli.api.builders import FluentBuilder
    >>> workflow = (
    ...     FluentBuilder("research-workflow")
    ...     .runtime("openai", model="gpt-4o-mini")
    ...     .agent("researcher", "You are a research assistant...")
    ...     .chain()
    ...     .step("researcher", "Research: {{topic}}")
    ...     .step("researcher", "Analyze: {{ steps[0].response }}")
    ...     .artifact("output.md", "# Results\\n{{ last_response }}")
    ...     .build()
    ... )
    >>> result = workflow.run_interactive(topic="AI")
"""

from __future__ import annotations

import difflib
from collections import deque
from typing import TYPE_CHECKING, Any

import structlog
from jinja2 import Environment, TemplateSyntaxError

from strands_cli.api.exceptions import BuildError

if TYPE_CHECKING:
    from strands_cli.api import Workflow

from strands_cli.types import (
    AcceptConfig,
    Agent,
    Artifact,
    ChainStep,
    EvaluatorConfig,
    GraphEdge,
    GraphNode,
    HITLStep,
    OrchestratorConfig,
    OrchestratorLimits,
    Outputs,
    ParallelBranch,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    Route,
    RouterConfig,
    Runtime,
    Spec,
    WorkerTemplate,
    WorkflowTask,
)

logger = structlog.get_logger(__name__)


def _validate_template_syntax(template: str) -> None:
    """Validate Jinja2 template syntax (but not variable references).

    Variable references are validated at execution time since they depend
    on runtime context (e.g., {{ steps[0].response }}).

    Args:
        template: Jinja2 template string to validate

    Raises:
        BuildError: If template has syntax errors
    """
    try:
        env = Environment()
        env.parse(template)
    except TemplateSyntaxError as e:
        raise BuildError(f"Invalid template syntax at line {e.lineno}: {e.message}") from e


class FluentBuilder:
    """Base builder for all workflow patterns.

    Provides core functionality for:
    - Runtime configuration (provider, model, parameters)
    - Agent definitions (id, prompt, tools)
    - Artifact output templates
    - Pattern selection (chain, workflow, parallel, etc.)

    All methods return self for fluent chaining except .build() which
    returns a Workflow instance ready to execute.

    Example:
        >>> builder = (
        ...     FluentBuilder("my-workflow")
        ...     .runtime("bedrock", model="anthropic.claude-3-sonnet-20240229-v1:0")
        ...     .agent("assistant", "You are a helpful assistant")
        ...     .chain()
        ...     .step("assistant", "Hello!")
        ...     .build()
        ... )
    """

    def __init__(self, name: str, description: str | None = None):
        """Initialize builder with workflow metadata.

        Args:
            name: Workflow name (used in logs and artifacts)
            description: Optional workflow description
        """
        self.name = name
        self._description = description
        self._runtime: dict[str, Any] | None = None
        self._agents: dict[str, dict[str, Any]] = {}
        self._artifacts: list[dict[str, str]] = []
        self._pattern_builder: (
            ChainBuilder
            | WorkflowBuilder
            | ParallelBuilder
            | GraphBuilder
            | RoutingBuilder
            | EvaluatorOptimizerBuilder
            | OrchestratorWorkersBuilder
            | None
        ) = None

        logger.debug("fluent_builder_created", name=name, description=description)

    def description(self, description: str) -> FluentBuilder:
        """Set workflow description.

        Args:
            description: Workflow description

        Returns:
            Self for method chaining

        Example:
            >>> builder.description("A workflow for research")
        """
        self._description = description
        logger.debug("description_set", description=description)
        return self

    def runtime(
        self,
        provider: str,
        model: str | None = None,
        region: str | None = None,
        host: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        max_parallel: int | None = None,
        **kwargs: Any,
    ) -> FluentBuilder:
        """Configure runtime (model provider and execution parameters).

        Validates provider immediately for fail-fast behavior. Provider-specific
        parameters (region, host) are validated during .build().

        Args:
            provider: Model provider ("bedrock", "ollama", "openai")
            model: Model ID (provider-specific, e.g., "gpt-4o-mini")
            region: AWS region (required for Bedrock)
            host: Host URL (required for Ollama)
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter (0.0-1.0)
            max_tokens: Maximum tokens to generate
            max_parallel: Maximum concurrent tasks/workers
            **kwargs: Additional provider-specific parameters

        Returns:
            Self for method chaining

        Raises:
            BuildError: If provider is invalid

        Example:
            >>> builder.runtime("bedrock", model="claude-3-sonnet", region="us-east-1")
        """
        # Immediate validation for fail-fast
        valid_providers = {p.value for p in ProviderType}
        if provider not in valid_providers:
            raise BuildError(
                f"Invalid provider '{provider}'. Must be one of: {sorted(valid_providers)}"
            )

        self._runtime = {
            "provider": provider,
            "model_id": model,
            "region": region,
            "host": host,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "max_parallel": max_parallel,
            **kwargs,
        }

        # Filter out None values
        self._runtime = {k: v for k, v in self._runtime.items() if v is not None}

        logger.debug("runtime_configured", provider=provider, model=model)
        return self

    def agent(
        self,
        id: str,
        prompt: str,
        tools: list[str] | None = None,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> FluentBuilder:
        """Define an agent for use in workflow steps.

        Agent must be defined before being referenced in steps. Duplicate
        agent IDs will raise an error.

        Args:
            id: Unique agent identifier (referenced in steps)
            prompt: System prompt for the agent
            tools: Optional tool IDs to enable for this agent
            model_id: Optional model override for this agent
            **kwargs: Additional agent configuration

        Returns:
            Self for method chaining

        Raises:
            BuildError: If agent ID already exists

        Example:
            >>> builder.agent("researcher", "You are a research assistant", tools=["http_request"])
        """
        if id in self._agents:
            raise BuildError(f"Agent '{id}' already defined. Each agent must have a unique ID.")

        self._agents[id] = {
            "prompt": prompt,
            "tools": tools,
            "model_id": model_id,
            **kwargs,
        }

        # Filter out None values
        self._agents[id] = {k: v for k, v in self._agents[id].items() if v is not None}

        logger.debug("agent_defined", agent_id=id, tools=tools)
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define an output artifact with template.

        Artifacts are written after workflow execution completes successfully.
        Templates can reference execution context like {{ last_response }},
        {{ steps[0].response }}, etc.

        Args:
            path: Output file path (supports templates, e.g., "{{ topic }}-report.md")
            template: Content template (Jinja2 syntax)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If template has syntax errors

        Example:
            >>> builder.artifact("report.md", "# Report\\n{{ last_response }}")
        """
        # Validate template syntax (not variable references)
        _validate_template_syntax(template)
        _validate_template_syntax(path)  # Path can also use templates

        self._artifacts.append({"path": path, "from": template})

        logger.debug("artifact_defined", path=path)
        return self

    def chain(self) -> ChainBuilder:
        """Start building a chain pattern workflow.

        Chain executes steps sequentially, passing context between steps.
        Each step can reference previous step outputs via {{ steps[n].response }}.

        Returns:
            ChainBuilder for defining steps

        Example:
            >>> builder.chain()
            ...     .step("agent1", "First step")
            ...     .step("agent2", "Second step: {{ steps[0].response }}")
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = ChainBuilder(self)
        logger.debug("pattern_selected", pattern="chain")
        return self._pattern_builder

    def workflow(self) -> WorkflowBuilder:
        """Start building a workflow pattern (DAG-based execution).

        Workflow pattern executes tasks with dependency tracking, enabling
        parallel execution where possible. Tasks reference dependencies via deps.

        Returns:
            WorkflowBuilder for defining tasks

        Example:
            >>> builder.workflow()
            ...     .task("research", "researcher", "Research: {{topic}}")
            ...     .task("analyze", "analyst", "Analyze: {{ tasks.research.response }}",
            ...           depends_on=["research"])
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = WorkflowBuilder(self)
        logger.debug("pattern_selected", pattern="workflow")
        return self._pattern_builder

    def parallel(self) -> ParallelBuilder:
        """Start building a parallel pattern workflow.

        Parallel pattern executes multiple branches concurrently, with optional
        reduce step to synthesize results.

        Returns:
            ParallelBuilder for defining branches

        Example:
            >>> builder.parallel()
            ...     .branch("technical", "researcher", "Analyze technical aspects")
            ...     .branch("business", "analyst", "Analyze business impact")
            ...     .reduce("writer", "Synthesize: {{ branches.technical.response }}")
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = ParallelBuilder(self)
        logger.debug("pattern_selected", pattern="parallel")
        return self._pattern_builder

    def graph(self) -> GraphBuilder:
        """Start building a graph pattern workflow (state machine).

        Graph pattern executes nodes as a state machine with conditional
        transitions between nodes based on node outputs.

        Returns:
            GraphBuilder for defining nodes and edges

        Example:
            >>> builder.graph()
            ...     .node("classify", "classifier", "Classify: {{input}}")
            ...     .node("process_a", "processor_a", "Process type A")
            ...     .node("process_b", "processor_b", "Process type B")
            ...     .edge("classify", "process_a", when="type_a")
            ...     .edge("classify", "process_b", when="type_b")
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = GraphBuilder(self)
        logger.debug("pattern_selected", pattern="graph")
        return self._pattern_builder

    def routing(self) -> RoutingBuilder:
        """Start building a routing pattern workflow.

        Routing pattern uses a classifier agent to select which route to execute
        based on input analysis.

        Returns:
            RoutingBuilder for defining router and routes

        Example:
            >>> builder.routing()
            ...     .router("classifier", "Classify the input: {{query}}")
            ...     .route("technical").step("tech_expert", "Answer: {{query}}").done()
            ...     .route("business").step("business_expert", "Answer: {{query}}").done()
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = RoutingBuilder(self)
        logger.debug("pattern_selected", pattern="routing")
        return self._pattern_builder

    def evaluator_optimizer(self) -> EvaluatorOptimizerBuilder:
        """Start building an evaluator-optimizer pattern workflow.

        Evaluator-optimizer pattern iteratively refines output through feedback loop:
        producer generates, evaluator scores, and producer revises until acceptable.

        Returns:
            EvaluatorOptimizerBuilder for defining producer, evaluator, and acceptance criteria

        Example:
            >>> builder.evaluator_optimizer()
            ...     .producer("writer", "Write an essay on: {{topic}}")
            ...     .evaluator("critic", "Rate this essay (0-10): {{ current_response }}")
            ...     .accept(min_score=8, max_iterations=3)
            ...     .revise_prompt("Improve based on: {{ evaluation_response }}")
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = EvaluatorOptimizerBuilder(self)
        logger.debug("pattern_selected", pattern="evaluator-optimizer")
        return self._pattern_builder

    def orchestrator_workers(self) -> OrchestratorWorkersBuilder:
        """Start building an orchestrator-workers pattern workflow.

        Orchestrator-workers pattern decomposes a complex task into subtasks,
        executes them in parallel with worker agents, then synthesizes results.

        Returns:
            OrchestratorWorkersBuilder for defining orchestrator, workers, and reduce

        Example:
            >>> builder.orchestrator_workers()
            ...     .orchestrator("planner", "Break down: {{task}}")
            ...     .worker_template("executor", tools=["python"])
            ...     .reduce_step("synthesizer", "Combine: {{ workers }}")
        """
        if self._pattern_builder is not None:
            raise BuildError("Pattern already defined. Only one pattern per workflow.")

        self._pattern_builder = OrchestratorWorkersBuilder(self)
        logger.debug("pattern_selected", pattern="orchestrator-workers")
        return self._pattern_builder

    def build(self) -> Workflow:
        """Build and validate the complete workflow specification.

        Performs comprehensive validation:
        - Runtime configuration is present and valid
        - At least one agent is defined
        - Pattern is configured
        - All agent references in steps exist
        - All templates have valid syntax

        Returns:
            Workflow instance ready to execute

        Raises:
            BuildError: If validation fails with actionable error message

        Example:
            >>> workflow = builder.build()
            >>> result = workflow.run_interactive()
        """
        # Validate runtime is configured
        if self._runtime is None:
            raise BuildError("Runtime not configured. Call .runtime(provider, ...) before .build()")

        # Validate at least one agent
        if not self._agents:
            raise BuildError(
                "No agents defined. Call .agent(id, prompt, ...) at least once before .build()"
            )

        # Validate pattern is configured
        if self._pattern_builder is None:
            raise BuildError("No pattern defined. Call .chain(), .workflow(), etc. before .build()")

        # Build pattern config (delegates to pattern builder)
        pattern_config = self._pattern_builder._build_config()

        # Construct Spec using Pydantic (validates structure)
        try:
            # Build runtime
            runtime = Runtime(**self._runtime)

            # Build agents
            agents = {agent_id: Agent(**config) for agent_id, config in self._agents.items()}

            # Build pattern
            pattern = Pattern(
                type=self._pattern_builder._pattern_type(),
                config=pattern_config,
            )

            # Build outputs
            outputs = None
            if self._artifacts:
                artifacts = [Artifact(**artifact) for artifact in self._artifacts]
                outputs = Outputs(artifacts=artifacts)

            # Construct full spec
            spec = Spec(
                name=self.name,
                description=self._description,
                runtime=runtime,
                agents=agents,
                pattern=pattern,
                outputs=outputs,
            )

            logger.info(
                "workflow_built",
                name=self.name,
                pattern=self._pattern_builder._pattern_type().value,
                agents=len(agents),
                artifacts=len(self._artifacts),
            )

            # Import Workflow here to avoid circular dependency
            from strands_cli.api import Workflow

            return Workflow(spec)

        except Exception as e:
            # Wrap Pydantic validation errors in BuildError
            raise BuildError(f"Failed to build workflow: {e}") from e


class ChainBuilder:
    """Builder for chain pattern workflows.

    Chain pattern executes steps sequentially, passing context between steps.
    Supports both agent steps and HITL (human-in-the-loop) pause points.

    Example:
        >>> builder.chain()
        ...     .step("researcher", "Research: {{topic}}")
        ...     .hitl("Review the research above. Proceed?")
        ...     .step("writer", "Write summary: {{ steps[0].response }}")
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize chain builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self.steps: list[dict[str, Any]] = []

    def step(
        self,
        agent: str,
        input: str | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> ChainBuilder:
        """Add an agent execution step to the chain.

        Step will execute the specified agent with optional input template.
        Agent must be defined via .agent() before being referenced.

        Args:
            agent: Agent ID (must be defined via .agent())
            input: Optional input template (Jinja2 syntax)
            vars: Optional per-step variable overrides
            tool_overrides: Optional tool ID overrides for this step

        Returns:
            Self for method chaining

        Raises:
            BuildError: If agent doesn't exist or template is invalid

        Example:
            >>> .step("researcher", "Research: {{topic}}", vars={"depth": "detailed"})
        """
        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template syntax if provided
        if input is not None:
            _validate_template_syntax(input)

        step_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            step_config["input"] = input
        if vars is not None:
            step_config["vars"] = vars
        if tool_overrides is not None:
            step_config["tool_overrides"] = tool_overrides

        self.steps.append(step_config)

        logger.debug("chain_step_added", agent=agent, step_index=len(self.steps) - 1)
        return self

    def hitl(
        self,
        prompt: str,
        context_display: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> ChainBuilder:
        """Add a human-in-the-loop pause point to the chain.

        Workflow will pause at this step and request user input. In interactive
        mode, prompts user in terminal. In non-interactive mode, saves session
        and exits with EX_HITL_PAUSE.

        Args:
            prompt: Message to display to user
            context_display: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If template is invalid or timeout is negative

        Example:
            >>> .hitl("Review research above. Should we proceed?",
            ...       context_display="{{ steps[0].response }}")
        """
        # Validate templates
        _validate_template_syntax(prompt)
        if context_display is not None:
            _validate_template_syntax(context_display)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        hitl_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if context_display is not None:
            hitl_config["context_display"] = context_display
        if default is not None:
            hitl_config["default"] = default
        if timeout_seconds is not None:
            hitl_config["timeout_seconds"] = timeout_seconds

        self.steps.append(hitl_config)

        logger.debug("chain_hitl_added", step_index=len(self.steps) - 1)
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Convenience method to add artifact without breaking chain.

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Convenience method to build without breaking chain.

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            # Use difflib to suggest similar agent names
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing in .step()."

            raise BuildError(msg)

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for chain pattern.

        Returns:
            PatternConfig with steps list

        Raises:
            BuildError: If no steps defined
        """
        if not self.steps:
            raise BuildError("Chain must have at least one step. Call .step() or .hitl().")

        # Convert to ChainStep objects (Pydantic validates)
        try:
            chain_steps = [ChainStep(**step) for step in self.steps]
            return PatternConfig(steps=chain_steps)
        except Exception as e:
            raise BuildError(f"Failed to build chain config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.CHAIN
        """
        return PatternType.CHAIN


class WorkflowBuilder:
    """Builder for workflow pattern (DAG-based execution).

    Workflow pattern executes tasks with dependency tracking, enabling
    parallel execution where dependencies allow. Validates task dependencies
    and detects circular dependencies at build time.

    Example:
        >>> builder.workflow()
        ...     .task("research", "researcher", "Research: {{topic}}")
        ...     .task("analyze", "analyst", "Analyze: {{ tasks.research.response }}",
        ...           depends_on=["research"])
        ...     .hitl_task("review", "Review analysis?", show="{{ tasks.analyze.response }}",
        ...                depends_on=["analyze"])
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize workflow builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self.tasks: list[dict[str, Any]] = []
        self._task_ids: set[str] = set()

    def _validate_task_id_unique(self, id: str) -> None:
        """Validate task ID is unique.

        Args:
            id: Task ID to validate

        Raises:
            BuildError: If task ID already exists
        """
        if id in self._task_ids:
            raise BuildError(f"Task ID '{id}' already exists. Each task must have a unique ID.")

    def _validate_task_dependencies(self, id: str, depends_on: list[str] | None) -> None:
        """Validate all task dependencies exist.

        Args:
            id: Task ID being validated
            depends_on: List of dependency task IDs

        Raises:
            BuildError: If any dependency doesn't exist
        """
        if depends_on is not None:
            for dep_id in depends_on:
                if dep_id not in self._task_ids:
                    raise BuildError(
                        f"Dependency '{dep_id}' not found for task '{id}'. "
                        f"Tasks must be defined before being referenced in depends_on."
                    )

    def _build_task_config(
        self,
        id: str,
        agent: str,
        input: str | None = None,
        description: str | None = None,
        depends_on: list[str] | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build task configuration dictionary.

        Args:
            id: Task identifier
            agent: Agent ID
            input: Optional input template
            description: Optional description
            depends_on: Optional dependencies
            vars: Optional variables
            tool_overrides: Optional tool overrides

        Returns:
            Task configuration dictionary
        """
        task_config: dict[str, Any] = {"id": id, "agent": agent}
        if input is not None:
            task_config["input"] = input
        if description is not None:
            task_config["description"] = description
        if depends_on is not None:
            task_config["deps"] = depends_on
        if vars is not None:
            task_config["vars"] = vars
        if tool_overrides is not None:
            task_config["tool_overrides"] = tool_overrides
        return task_config

    def task(
        self,
        id: str,
        agent: str,
        input: str | None = None,
        description: str | None = None,
        depends_on: list[str] | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> WorkflowBuilder:
        """Add an agent execution task to the workflow.

        Task will execute the specified agent. Dependencies control execution order
        and enable parallel execution where possible.

        Args:
            id: Unique task identifier (used in dependencies)
            agent: Agent ID (must be defined via .agent())
            input: Optional input template (Jinja2 syntax)
            description: Optional human-readable task description
            depends_on: Optional list of task IDs this task depends on
            vars: Optional per-task variable overrides
            tool_overrides: Optional tool ID overrides for this task

        Returns:
            Self for method chaining

        Raises:
            BuildError: If task ID is duplicate, agent doesn't exist, or dependency is invalid

        Example:
            >>> .task("research", "researcher", "Research: {{topic}}")
            >>> .task("analyze", "analyst", input="{{ tasks.research.response }}",
            ...       depends_on=["research"])
        """
        self._validate_task_id_unique(id)
        self._validate_agent_exists(agent)

        if input is not None:
            _validate_template_syntax(input)

        self._validate_task_dependencies(id, depends_on)

        task_config = self._build_task_config(
            id, agent, input, description, depends_on, vars, tool_overrides
        )
        self.tasks.append(task_config)
        self._task_ids.add(id)

        logger.debug("workflow_task_added", task_id=id, agent=agent, deps=depends_on)
        return self

    def _build_hitl_task_config(
        self,
        id: str,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build HITL task configuration dictionary.

        Args:
            id: Task identifier
            prompt: HITL prompt
            show: Optional context to show
            default: Optional default response
            timeout_seconds: Optional timeout
            depends_on: Optional dependencies

        Returns:
            HITL task configuration dictionary
        """
        hitl_config: dict[str, Any] = {"id": id, "type": "hitl", "prompt": prompt}
        if show is not None:
            hitl_config["context_display"] = show
        if default is not None:
            hitl_config["default"] = default
        if timeout_seconds is not None:
            hitl_config["timeout_seconds"] = timeout_seconds
        if depends_on is not None:
            hitl_config["deps"] = depends_on
        return hitl_config

    def hitl_task(
        self,
        id: str,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
        depends_on: list[str] | None = None,
    ) -> WorkflowBuilder:
        """Add a human-in-the-loop task to the workflow.

        Workflow will pause at this task and request user input. In interactive
        mode, prompts user in terminal. In non-interactive mode, saves session
        and exits with EX_HITL_PAUSE.

        Args:
            id: Unique task identifier
            prompt: Message to display to user
            show: Optional context template to show user (alias for context_display)
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)
            depends_on: Optional list of task IDs this task depends on

        Returns:
            Self for method chaining

        Raises:
            BuildError: If task ID is duplicate, template is invalid, or timeout is negative

        Example:
            >>> .hitl_task("review", "Review analysis?",
            ...            show="{{ tasks.analyze.response }}",
            ...            depends_on=["analyze"])
        """
        self._validate_task_id_unique(id)

        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        self._validate_task_dependencies(id, depends_on)

        hitl_config = self._build_hitl_task_config(
            id, prompt, show, default, timeout_seconds, depends_on
        )
        self.tasks.append(hitl_config)
        self._task_ids.add(id)

        logger.debug("workflow_hitl_task_added", task_id=id, deps=depends_on)
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Convenience method to add artifact without breaking workflow chain.

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Convenience method to build without breaking workflow chain.

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing in .task()."

            raise BuildError(msg)

    def _detect_circular_dependencies(self) -> None:
        """Detect circular dependencies in task graph using topological sort.

        Raises:
            BuildError: If circular dependencies detected
        """
        # Build adjacency list
        graph: dict[str, list[str]] = {task["id"]: [] for task in self.tasks}
        in_degree: dict[str, int] = {task["id"]: 0 for task in self.tasks}

        for task in self.tasks:
            task_id = task["id"]
            deps = task.get("deps", [])
            for dep in deps:
                graph[dep].append(task_id)
                in_degree[task_id] += 1

        # Topological sort using Kahn's algorithm
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        sorted_tasks: list[str] = []

        while queue:
            current = queue.popleft()
            sorted_tasks.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If not all tasks were processed, there's a cycle
        if len(sorted_tasks) != len(self.tasks):
            remaining = set(in_degree.keys()) - set(sorted_tasks)
            raise BuildError(
                f"Circular dependency detected in tasks: {', '.join(sorted(remaining))}. "
                f"Tasks cannot depend on themselves directly or indirectly."
            )

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for workflow pattern.

        Returns:
            PatternConfig with tasks list

        Raises:
            BuildError: If no tasks defined or circular dependencies detected
        """
        if not self.tasks:
            raise BuildError("Workflow must have at least one task. Call .task() or .hitl_task().")

        # Detect circular dependencies
        self._detect_circular_dependencies()

        # Convert to WorkflowTask objects (Pydantic validates)
        try:
            workflow_tasks = [WorkflowTask(**task) for task in self.tasks]
            return PatternConfig(tasks=workflow_tasks)
        except Exception as e:
            raise BuildError(f"Failed to build workflow config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.WORKFLOW
        """
        return PatternType.WORKFLOW


class ParallelBuilder:
    """Builder for parallel pattern workflows.

    Parallel pattern executes multiple branches concurrently, with optional
    reduce step to synthesize results. Each branch executes its steps sequentially.

    Example:
        >>> builder.parallel()
        ...     .branch("technical").step("researcher", "Technical analysis").done()
        ...     .branch("business").step("analyst", "Business analysis").done()
        ...     .reduce("writer", "Synthesize both analyses")
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize parallel builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self.branches: list[dict[str, Any]] = []
        self._branch_ids: set[str] = set()
        self._reduce_step: dict[str, Any] | None = None
        self._current_branch: _BranchBuilder | None = None

    def branch(self, id: str) -> _BranchBuilder:
        """Start defining a new parallel branch.

        Each branch executes its steps sequentially. All branches execute
        concurrently with other branches.

        Args:
            id: Unique branch identifier (used in templates like {{ branches.id.response }})

        Returns:
            BranchBuilder for defining branch steps

        Raises:
            BuildError: If branch ID is duplicate or previous branch not completed

        Example:
            >>> .branch("technical")
            ...     .step("researcher", "Analyze technical aspects")
            ...     .hitl("Review technical analysis?")
            ...     .done()
        """
        # Validate unique branch ID
        if id in self._branch_ids:
            raise BuildError(f"Branch ID '{id}' already exists. Each branch must have a unique ID.")

        # Ensure previous branch is completed
        if self._current_branch is not None:
            raise BuildError(
                f"Previous branch '{self._current_branch.id}' not completed. "
                f"Call .done() before starting a new branch."
            )

        self._current_branch = _BranchBuilder(self, id)
        self._branch_ids.add(id)

        logger.debug("parallel_branch_started", branch_id=id)
        return self._current_branch

    def reduce(
        self,
        agent: str,
        input: str | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> ParallelBuilder:
        """Add a reduce step to synthesize branch results.

        Reduce step executes after all branches complete. Optional - if not
        specified, workflow returns raw branch results.

        Args:
            agent: Agent ID for reduce step (must be defined via .agent())
            input: Optional input template (can reference {{ branches.id.response }})
            vars: Optional variable overrides for reduce step
            tool_overrides: Optional tool ID overrides for reduce step

        Returns:
            Self for method chaining

        Raises:
            BuildError: If reduce already defined, agent doesn't exist, or template invalid

        Example:
            >>> .reduce("writer", "Synthesize: {{ branches.technical.response }} and {{ branches.business.response }}")
        """
        # Validate reduce not already defined
        if self._reduce_step is not None:
            raise BuildError(
                "Reduce step already defined. Only one reduce step allowed per workflow."
            )

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        reduce_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            reduce_config["input"] = input
        if vars is not None:
            reduce_config["vars"] = vars
        if tool_overrides is not None:
            reduce_config["tool_overrides"] = tool_overrides

        self._reduce_step = reduce_config

        logger.debug("parallel_reduce_added", agent=agent)
        return self

    def hitl_in_reduce(
        self,
        prompt: str,
        context_display: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> ParallelBuilder:
        """Add HITL pause in reduce step (before reduce executes).

        Note: This is a pattern-specific HITL method for parallel reduce.
        For HITL within branches, use .branch().hitl().done()

        Args:
            prompt: Message to display to user
            context_display: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If reduce HITL already defined or template invalid

        Example:
            >>> .hitl_in_reduce("Review all branch results before synthesis?",
            ...                  context_display="{{ branches.technical.response }}")
        """
        # For MVP, this could be implemented as a reduce step with type: hitl
        # For now, raise BuildError as it's not yet implemented
        raise BuildError(
            "hitl_in_reduce() not yet implemented. "
            "Use .branch().hitl().done() for HITL within branches."
        )

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Convenience method to add artifact without breaking parallel chain.

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Convenience method to build without breaking parallel chain.

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing."

            raise BuildError(msg)

    def _finalize_branch(self, branch: _BranchBuilder) -> None:
        """Finalize a branch and add to branches list.

        Args:
            branch: BranchBuilder instance to finalize
        """
        if not branch.steps:
            raise BuildError(f"Branch '{branch.id}' must have at least one step.")

        self.branches.append({"id": branch.id, "steps": branch.steps})
        self._current_branch = None

        logger.debug("parallel_branch_finalized", branch_id=branch.id, steps=len(branch.steps))

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for parallel pattern.

        Returns:
            PatternConfig with branches and optional reduce

        Raises:
            BuildError: If no branches defined or branch not completed
        """
        # Ensure no uncompleted branch
        if self._current_branch is not None:
            raise BuildError(
                f"Branch '{self._current_branch.id}' not completed. Call .done() before .build()."
            )

        if not self.branches:
            raise BuildError("Parallel must have at least one branch. Call .branch().")

        # Convert to ParallelBranch objects (Pydantic validates)
        try:
            parallel_branches = []
            for branch_data in self.branches:
                # Convert steps to ChainStep objects
                chain_steps = [ChainStep(**step) for step in branch_data["steps"]]
                parallel_branches.append(ParallelBranch(id=branch_data["id"], steps=chain_steps))

            config_data: dict[str, Any] = {"branches": parallel_branches}

            # Add reduce step if defined
            if self._reduce_step is not None:
                reduce_step = ChainStep(**self._reduce_step)
                config_data["reduce"] = reduce_step

            return PatternConfig(**config_data)
        except Exception as e:
            raise BuildError(f"Failed to build parallel config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.PARALLEL
        """
        return PatternType.PARALLEL


class _BranchBuilder:
    """Internal builder for parallel branch steps.

    This is a helper class used by ParallelBuilder to provide a fluent
    interface for defining steps within a branch.
    """

    def __init__(self, parent: ParallelBuilder, id: str):
        """Initialize branch builder.

        Args:
            parent: Parent ParallelBuilder instance
            id: Branch identifier
        """
        self.parent = parent
        self.id = id
        self.steps: list[dict[str, Any]] = []

    def step(
        self,
        agent: str,
        input: str | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> _BranchBuilder:
        """Add an agent execution step to this branch.

        Args:
            agent: Agent ID (must be defined via .agent())
            input: Optional input template (Jinja2 syntax)
            vars: Optional per-step variable overrides
            tool_overrides: Optional tool ID overrides for this step

        Returns:
            Self for method chaining

        Raises:
            BuildError: If agent doesn't exist or template is invalid

        Example:
            >>> .step("researcher", "Analyze: {{topic}}")
        """
        # Validate agent exists
        self.parent._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        step_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            step_config["input"] = input
        if vars is not None:
            step_config["vars"] = vars
        if tool_overrides is not None:
            step_config["tool_overrides"] = tool_overrides

        self.steps.append(step_config)

        logger.debug(
            "branch_step_added", branch_id=self.id, agent=agent, step_index=len(self.steps) - 1
        )
        return self

    def hitl(
        self,
        prompt: str,
        context_display: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> _BranchBuilder:
        """Add HITL pause point within this branch.

        Args:
            prompt: Message to display to user
            context_display: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If template is invalid or timeout is negative

        Example:
            >>> .hitl("Review branch results?", context_display="{{ steps[0].response }}")
        """
        # Validate templates
        _validate_template_syntax(prompt)
        if context_display is not None:
            _validate_template_syntax(context_display)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        hitl_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if context_display is not None:
            hitl_config["context_display"] = context_display
        if default is not None:
            hitl_config["default"] = default
        if timeout_seconds is not None:
            hitl_config["timeout_seconds"] = timeout_seconds

        self.steps.append(hitl_config)

        logger.debug("branch_hitl_added", branch_id=self.id, step_index=len(self.steps) - 1)
        return self

    def done(self) -> ParallelBuilder:
        """Complete this branch and return to parallel builder.

        Returns:
            Parent ParallelBuilder for continued chaining

        Raises:
            BuildError: If branch has no steps

        Example:
            >>> .branch("technical").step("researcher", "Analyze").done()
        """
        self.parent._finalize_branch(self)
        return self.parent

    def build(self) -> Workflow:
        """Delegate build to parent parallel builder."""

        return self.parent.build()


class GraphBuilder:
    """Builder for graph pattern workflows (state machine).

    Graph pattern executes nodes as a state machine with conditional
    transitions. Nodes can be agent execution steps or HITL pause points.

    Example:
        >>> builder.graph()
        ...     .node("start", "classifier", "Classify: {{input}}")
        ...     .node("technical", "tech_expert", "Technical answer")
        ...     .node("business", "biz_expert", "Business answer")
        ...     .conditional_edge("start", [
        ...         ("type == 'tech'", "technical"),
        ...         ("type == 'biz'", "business"),
        ...     ])
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize graph builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._max_iterations: int = 10

    def node(
        self,
        id: str,
        agent: str,
        input: str | None = None,
    ) -> GraphBuilder:
        """Add an agent execution node to the graph.

        Args:
            id: Unique node identifier
            agent: Agent ID (must be defined via .agent())
            input: Optional input template (Jinja2 syntax)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If node ID is duplicate or agent doesn't exist

        Example:
            >>> .node("classify", "classifier", "Classify: {{input}}")
        """
        # Validate unique node ID
        if id in self.nodes:
            raise BuildError(f"Node ID '{id}' already exists. Each node must have a unique ID.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        node_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            node_config["input"] = input

        self.nodes[id] = node_config

        logger.debug("graph_node_added", node_id=id, agent=agent)
        return self

    def hitl_node(
        self,
        id: str,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> GraphBuilder:
        """Add a HITL pause node to the graph.

        Args:
            id: Unique node identifier
            prompt: Message to display to user
            show: Optional context template to show user (alias for context_display)
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If node ID is duplicate or template is invalid

        Example:
            >>> .hitl_node("review", "Review classification?", show="{{ nodes.classify.response }}")
        """
        # Validate unique node ID
        if id in self.nodes:
            raise BuildError(f"Node ID '{id}' already exists. Each node must have a unique ID.")

        # Validate templates
        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        hitl_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if show is not None:
            hitl_config["context_display"] = show
        if default is not None:
            hitl_config["default"] = default
        if timeout_seconds is not None:
            hitl_config["timeout_seconds"] = timeout_seconds

        self.nodes[id] = hitl_config

        logger.debug("graph_hitl_node_added", node_id=id)
        return self

    def edge(self, from_node: str, to_node: str | list[str]) -> GraphBuilder:
        """Add a static edge between nodes.

        Static edges always transition to the specified target(s).
        Multiple targets execute sequentially.

        Args:
            from_node: Source node ID
            to_node: Target node ID or list of target IDs (sequential execution)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If node doesn't exist

        Example:
            >>> .edge("node1", "node2")
            >>> .edge("node1", ["node2", "node3"])  # Sequential execution
        """
        # Validate nodes exist
        if from_node not in self.nodes:
            raise BuildError(
                f"Source node '{from_node}' not found. Define nodes before adding edges."
            )

        to_nodes = [to_node] if isinstance(to_node, str) else to_node
        for node_id in to_nodes:
            if node_id not in self.nodes:
                raise BuildError(
                    f"Target node '{node_id}' not found. Define nodes before adding edges."
                )

        edge_config: dict[str, Any] = {"from": from_node, "to": to_nodes}
        self.edges.append(edge_config)

        logger.debug("graph_edge_added", from_node=from_node, to_nodes=to_nodes)
        return self

    def conditional_edge(
        self,
        from_node: str,
        choices: list[tuple[str, str]],
    ) -> GraphBuilder:
        """Add a conditional edge with multiple choices.

        Evaluates conditions in order and transitions to first matching target.
        Use "else" as last condition for default fallback.

        Args:
            from_node: Source node ID
            choices: List of (condition, target) tuples
                     condition: Expression like "type == 'tech'" or "else"
                     target: Target node ID

        Returns:
            Self for method chaining

        Raises:
            BuildError: If node doesn't exist or choices are empty

        Example:
            >>> .conditional_edge("classify", [
            ...     ("type == 'tech'", "technical"),
            ...     ("type == 'biz'", "business"),
            ...     ("else", "fallback"),
            ... ])
        """
        # Validate source node exists
        if from_node not in self.nodes:
            raise BuildError(
                f"Source node '{from_node}' not found. Define nodes before adding edges."
            )

        # Validate choices not empty
        if not choices:
            raise BuildError("Conditional edge must have at least one choice.")

        # Validate target nodes exist
        for _condition, target in choices:
            if target not in self.nodes:
                raise BuildError(
                    f"Target node '{target}' not found. Define nodes before adding edges."
                )

        # Convert to ConditionalChoice format
        choose_list = [{"when": condition, "to": target} for condition, target in choices]

        edge_config: dict[str, Any] = {"from": from_node, "choose": choose_list}
        self.edges.append(edge_config)

        logger.debug("graph_conditional_edge_added", from_node=from_node, choices=len(choices))
        return self

    def max_iterations(self, count: int) -> GraphBuilder:
        """Set maximum iterations per node (prevents infinite loops).

        Args:
            count: Maximum iterations (must be >= 1)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If count < 1

        Example:
            >>> .max_iterations(20)
        """
        if count < 1:
            raise BuildError("max_iterations must be >= 1")

        self._max_iterations = count

        logger.debug("graph_max_iterations_set", max_iterations=count)
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing in .node()."

            raise BuildError(msg)

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for graph pattern.

        Returns:
            PatternConfig with nodes, edges, and max_iterations

        Raises:
            BuildError: If no nodes defined or no edges defined
        """
        if not self.nodes:
            raise BuildError("Graph must have at least one node. Call .node() or .hitl_node().")

        if not self.edges:
            raise BuildError(
                "Graph must have at least one edge. Call .edge() or .conditional_edge()."
            )

        # Convert to GraphNode objects (Pydantic validates)
        try:
            graph_nodes = {node_id: GraphNode(**config) for node_id, config in self.nodes.items()}
            graph_edges = [GraphEdge(**edge) for edge in self.edges]

            return PatternConfig(
                nodes=graph_nodes,
                edges=graph_edges,
                max_iterations=self._max_iterations,
            )
        except Exception as e:
            raise BuildError(f"Failed to build graph config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.GRAPH
        """
        return PatternType.GRAPH


class RoutingBuilder:
    """Builder for routing pattern workflows.

    Routing pattern uses a classifier agent to select which route to execute.
    Router analyzes input and returns route name, then selected route executes.

    Example:
        >>> builder.routing()
        ...     .router("classifier", "Classify query: {{query}}")
        ...     .route("technical").step("tech_expert", "Answer: {{query}}").done()
        ...     .route("business").step("biz_expert", "Answer: {{query}}").done()
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize routing builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self._router_agent: str | None = None
        self._router_input: str | None = None
        self._router_max_retries: int = 2
        self._router_review: dict[str, Any] | None = None
        self.routes: dict[str, list[dict[str, Any]]] = {}
        self._current_route: _RouteBuilder | None = None

    def router(
        self,
        agent: str,
        input: str | None = None,
        max_retries: int = 2,
    ) -> RoutingBuilder:
        """Configure the router agent that selects routes.

        Router agent must return JSON: {"route": "route_name"}

        Args:
            agent: Agent ID for classification (must be defined via .agent())
            input: Optional input template for router (Jinja2 syntax)
            max_retries: Maximum retry attempts for malformed JSON (default: 2)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If router already defined, agent doesn't exist, or template invalid

        Example:
            >>> .router("classifier", "Classify this query: {{query}}", max_retries=3)
        """
        # Validate router not already defined
        if self._router_agent is not None:
            raise BuildError("Router already defined. Only one router per routing workflow.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        # Validate max_retries
        if max_retries < 0:
            raise BuildError("max_retries must be >= 0")

        self._router_agent = agent
        self._router_input = input
        self._router_max_retries = max_retries

        logger.debug("routing_router_configured", agent=agent, max_retries=max_retries)
        return self

    def review_router(
        self,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> RoutingBuilder:
        """Add HITL review of router decision (pattern-specific HITL).

        Allows user to review/override router's route selection before execution.

        Args:
            prompt: Message to display to user
            show: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If router review already defined or template invalid

        Example:
            >>> .review_router("Confirm route selection?", show="{{ router_decision.route }}")
        """
        # Validate router review not already defined
        if self._router_review is not None:
            raise BuildError("Router review already defined. Only one review per router.")

        # Validate templates
        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        review_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if show is not None:
            review_config["context_display"] = show
        if default is not None:
            review_config["default"] = default
        if timeout_seconds is not None:
            review_config["timeout_seconds"] = timeout_seconds

        self._router_review = review_config

        logger.debug("routing_router_review_added")
        return self

    def route(self, id: str) -> _RouteBuilder:
        """Start defining a new route.

        Routes are selected by router agent's decision. Each route contains
        a chain of steps to execute if selected.

        Args:
            id: Unique route identifier (must match router's output)

        Returns:
            RouteBuilder for defining route steps

        Raises:
            BuildError: If route ID is duplicate or previous route not completed

        Example:
            >>> .route("technical")
            ...     .step("tech_expert", "Answer technical question: {{query}}")
            ...     .done()
        """
        # Validate unique route ID
        if id in self.routes:
            raise BuildError(f"Route ID '{id}' already exists. Each route must have a unique ID.")

        # Ensure previous route is completed
        if self._current_route is not None:
            raise BuildError(
                f"Previous route '{self._current_route.id}' not completed. "
                f"Call .done() before starting a new route."
            )

        self._current_route = _RouteBuilder(self, id)

        logger.debug("routing_route_started", route_id=id)
        return self._current_route

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing."

            raise BuildError(msg)

    def _finalize_route(self, route: _RouteBuilder) -> None:
        """Finalize a route and add to routes dict.

        Args:
            route: RouteBuilder instance to finalize
        """
        if not route.steps:
            raise BuildError(f"Route '{route.id}' must have at least one step.")

        self.routes[route.id] = route.steps
        self._current_route = None

        logger.debug("routing_route_finalized", route_id=route.id, steps=len(route.steps))

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for routing pattern.

        Returns:
            PatternConfig with router and routes

        Raises:
            BuildError: If router not configured, no routes defined, or route not completed
        """
        # Validate router configured
        if self._router_agent is None:
            raise BuildError("Router not configured. Call .router() before .build().")

        # Ensure no uncompleted route
        if self._current_route is not None:
            raise BuildError(
                f"Route '{self._current_route.id}' not completed. Call .done() before .build()."
            )

        if not self.routes:
            raise BuildError("Routing must have at least one route. Call .route().")

        # Build RouterConfig
        try:
            router_config_data: dict[str, Any] = {
                "agent": self._router_agent,
                "max_retries": self._router_max_retries,
            }
            if self._router_input is not None:
                router_config_data["input"] = self._router_input
            if self._router_review is not None:
                router_config_data["review_router"] = ChainStep(**self._router_review)

            router_config = RouterConfig(**router_config_data)

            # Build routes
            routes_dict = {}
            for route_id, steps_data in self.routes.items():
                chain_steps = [ChainStep(**step) for step in steps_data]
                routes_dict[route_id] = Route(then=chain_steps)

            return PatternConfig(router=router_config, routes=routes_dict)
        except Exception as e:
            raise BuildError(f"Failed to build routing config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.ROUTING
        """
        return PatternType.ROUTING


class _RouteBuilder:
    """Internal builder for routing route steps.

    Helper class for RoutingBuilder to provide fluent interface for
    defining steps within a route.
    """

    def __init__(self, parent: RoutingBuilder, id: str):
        """Initialize route builder.

        Args:
            parent: Parent RoutingBuilder instance
            id: Route identifier
        """
        self.parent = parent
        self.id = id
        self.steps: list[dict[str, Any]] = []

    def step(
        self,
        agent: str,
        input: str | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> _RouteBuilder:
        """Add an agent execution step to this route.

        Args:
            agent: Agent ID (must be defined via .agent())
            input: Optional input template (Jinja2 syntax)
            vars: Optional per-step variable overrides
            tool_overrides: Optional tool ID overrides for this step

        Returns:
            Self for method chaining

        Raises:
            BuildError: If agent doesn't exist or template is invalid

        Example:
            >>> .step("tech_expert", "Answer: {{query}}")
        """
        # Validate agent exists
        self.parent._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        step_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            step_config["input"] = input
        if vars is not None:
            step_config["vars"] = vars
        if tool_overrides is not None:
            step_config["tool_overrides"] = tool_overrides

        self.steps.append(step_config)

        logger.debug(
            "route_step_added", route_id=self.id, agent=agent, step_index=len(self.steps) - 1
        )
        return self

    def hitl(
        self,
        prompt: str,
        context_display: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> _RouteBuilder:
        """Add HITL pause point within this route.

        Args:
            prompt: Message to display to user
            context_display: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If template is invalid or timeout is negative

        Example:
            >>> .hitl("Review answer?", context_display="{{ steps[0].response }}")
        """
        # Validate templates
        _validate_template_syntax(prompt)
        if context_display is not None:
            _validate_template_syntax(context_display)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        hitl_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if context_display is not None:
            hitl_config["context_display"] = context_display
        if default is not None:
            hitl_config["default"] = default
        if timeout_seconds is not None:
            hitl_config["timeout_seconds"] = timeout_seconds

        self.steps.append(hitl_config)

        logger.debug("route_hitl_added", route_id=self.id, step_index=len(self.steps) - 1)
        return self

    def done(self) -> RoutingBuilder:
        """Complete this route and return to routing builder.

        Returns:
            Parent RoutingBuilder for continued chaining

        Raises:
            BuildError: If route has no steps

        Example:
            >>> .route("technical").step("expert", "Answer").done()
        """
        self.parent._finalize_route(self)
        return self.parent


class EvaluatorOptimizerBuilder:
    """Builder for evaluator-optimizer pattern workflows.

    Evaluator-optimizer pattern iteratively refines output through feedback loop:
    1. Producer generates initial output
    2. Evaluator scores output (0-100)
    3. If score >= min_score: accept and complete
    4. If score < min_score and iterations < max: producer revises based on feedback
    5. Repeat until accepted or max iterations reached

    Example:
        >>> builder.evaluator_optimizer()
        ...     .producer("writer", "Write essay on: {{topic}}")
        ...     .evaluator("critic", "Rate essay (0-100): {{ current_response }}")
        ...     .accept(min_score=8, max_iterations=3)
        ...     .revise_prompt("Improve based on: {{ evaluation_response }}")
        ...     .review_gate("Review iteration?", show="{{ iteration }}/{{ max_iterations }}")
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize evaluator-optimizer builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self._producer_agent: str | None = None
        self._producer_input: str | None = None
        self._evaluator_agent: str | None = None
        self._evaluator_input: str | None = None
        self._min_score: int | None = None
        self._max_iterations: int = 3
        self._revise_prompt: str | None = None
        self._review_gate: dict[str, Any] | None = None

    def producer(
        self,
        agent: str,
        input: str | None = None,
    ) -> EvaluatorOptimizerBuilder:
        """Configure producer agent that generates/revises output.

        Args:
            agent: Agent ID for production (must be defined via .agent())
            input: Optional input template for initial production (Jinja2 syntax)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If producer already defined, agent doesn't exist, or template invalid

        Example:
            >>> .producer("writer", "Write an essay on: {{topic}}")
        """
        # Validate producer not already defined
        if self._producer_agent is not None:
            raise BuildError("Producer already defined. Only one producer per workflow.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        self._producer_agent = agent
        self._producer_input = input

        logger.debug("evaluator_optimizer_producer_configured", agent=agent)
        return self

    def evaluator(
        self,
        agent: str,
        input: str | None = None,
    ) -> EvaluatorOptimizerBuilder:
        """Configure evaluator agent that scores output.

        Evaluator must return JSON: {"score": 0-100, "issues": [...], "fixes": [...]}

        Args:
            agent: Agent ID for evaluation (must be defined via .agent())
            input: Optional input template for evaluation (Jinja2 syntax)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If evaluator already defined, agent doesn't exist, or template invalid

        Example:
            >>> .evaluator("critic", "Rate this essay (0-100): {{ current_response }}")
        """
        # Validate evaluator not already defined
        if self._evaluator_agent is not None:
            raise BuildError("Evaluator already defined. Only one evaluator per workflow.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        self._evaluator_agent = agent
        self._evaluator_input = input

        logger.debug("evaluator_optimizer_evaluator_configured", agent=agent)
        return self

    def accept(
        self,
        min_score: int,
        max_iterations: int = 3,
    ) -> EvaluatorOptimizerBuilder:
        """Configure acceptance criteria.

        Args:
            min_score: Minimum score (0-100) to accept output
            max_iterations: Maximum iterations (default: 3)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If criteria already defined or values invalid

        Example:
            >>> .accept(min_score=8, max_iterations=5)
        """
        # Validate acceptance not already defined
        if self._min_score is not None:
            raise BuildError("Acceptance criteria already defined. Call .accept() only once.")

        # Validate min_score range
        if not 0 <= min_score <= 100:
            raise BuildError("min_score must be between 0 and 100")

        # Validate max_iterations
        if max_iterations < 1:
            raise BuildError("max_iterations must be >= 1")

        self._min_score = min_score
        self._max_iterations = max_iterations

        logger.debug(
            "evaluator_optimizer_accept_configured",
            min_score=min_score,
            max_iterations=max_iterations,
        )
        return self

    def revise_prompt(self, template: str) -> EvaluatorOptimizerBuilder:
        """Configure revision prompt template for producer.

        Template is used when producer revises output based on evaluator feedback.
        Can reference {{ evaluation_response }}, {{ current_response }}, etc.

        Args:
            template: Revision prompt template (Jinja2 syntax)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If revise_prompt already defined or template invalid

        Example:
            >>> .revise_prompt("Improve based on feedback: {{ evaluation_response }}")
        """
        # Validate revise_prompt not already defined
        if self._revise_prompt is not None:
            raise BuildError("Revise prompt already defined. Call .revise_prompt() only once.")

        # Validate template syntax
        _validate_template_syntax(template)

        self._revise_prompt = template

        logger.debug("evaluator_optimizer_revise_prompt_configured")
        return self

    def review_gate(
        self,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> EvaluatorOptimizerBuilder:
        """Add HITL review gate between iterations (pattern-specific HITL).

        Pauses between evaluator feedback and producer revision to allow
        user review/intervention.

        Args:
            prompt: Message to display to user
            show: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If review gate already defined or template invalid

        Example:
            >>> .review_gate("Continue iteration?", show="Score: {{ evaluation_response.score }}")
        """
        # Validate review gate not already defined
        if self._review_gate is not None:
            raise BuildError("Review gate already defined. Only one review gate per workflow.")

        # Validate templates
        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        review_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if show is not None:
            review_config["context_display"] = show
        if default is not None:
            review_config["default"] = default
        if timeout_seconds is not None:
            review_config["timeout_seconds"] = timeout_seconds

        self._review_gate = review_config

        logger.debug("evaluator_optimizer_review_gate_added")
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing."

            raise BuildError(msg)

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for evaluator-optimizer pattern.

        Returns:
            PatternConfig with producer, evaluator, accept, and optional revise_prompt/review_gate

        Raises:
            BuildError: If producer, evaluator, or acceptance criteria not configured
        """
        # Validate required components
        if self._producer_agent is None:
            raise BuildError("Producer not configured. Call .producer() before .build().")

        if self._evaluator_agent is None:
            raise BuildError("Evaluator not configured. Call .evaluator() before .build().")

        if self._min_score is None:
            raise BuildError("Acceptance criteria not configured. Call .accept() before .build().")

        if self._revise_prompt is None:
            raise BuildError("Revise prompt not configured. Call .revise_prompt() before .build().")

        # Build config
        try:
            # Build evaluator config
            evaluator_config_data: dict[str, Any] = {"agent": self._evaluator_agent}
            if self._evaluator_input is not None:
                evaluator_config_data["input"] = self._evaluator_input
            evaluator_config = EvaluatorConfig(**evaluator_config_data)

            # Build accept config
            accept_config = AcceptConfig(min_score=self._min_score, max_iters=self._max_iterations)

            # Build pattern config
            config_data: dict[str, Any] = {
                "producer": self._producer_agent,
                "evaluator": evaluator_config,
                "accept": accept_config,
            }

            if self._producer_input is not None:
                # Producer input is stored at pattern level (not in config)
                # This is handled by the executor using initial context
                pass

            if self._revise_prompt is not None:
                config_data["revise_prompt"] = self._revise_prompt

            if self._review_gate is not None:
                config_data["review_gate"] = HITLStep(**self._review_gate)

            return PatternConfig(**config_data)
        except Exception as e:
            raise BuildError(f"Failed to build evaluator-optimizer config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.EVALUATOR_OPTIMIZER
        """
        return PatternType.EVALUATOR_OPTIMIZER


class OrchestratorWorkersBuilder:
    """Builder for orchestrator-workers pattern workflows.

    Orchestrator-workers pattern decomposes complex tasks into subtasks,
    executes them in parallel with worker agents, then optionally synthesizes results:
    1. Orchestrator analyzes input and generates subtasks (JSON array)
    2. (Optional) HITL review of decomposition
    3. Worker pool executes subtasks in parallel
    4. (Optional) HITL review before reduce
    5. (Optional) Reduce step synthesizes worker results

    Example:
        >>> builder.orchestrator_workers()
        ...     .orchestrator("planner", "Break down task: {{task}}", max_workers=5, max_rounds=2)
        ...     .decomposition_review("Approve subtasks?", show="{{ subtasks }}")
        ...     .worker_template("executor", tools=["python"])
        ...     .reduce_review("Review worker results?")
        ...     .reduce_step("synthesizer", "Combine: {{ workers }}")
    """

    def __init__(self, parent: FluentBuilder):
        """Initialize orchestrator-workers builder.

        Args:
            parent: Parent FluentBuilder instance
        """
        self.parent = parent
        self._orchestrator_agent: str | None = None
        self._orchestrator_input: str | None = None
        self._min_workers: int | None = None
        self._max_workers: int | None = None
        self._max_rounds: int | None = None
        self._decomposition_review: dict[str, Any] | None = None
        self._worker_agent: str | None = None
        self._worker_tools: list[str] | None = None
        self._reduce_review: dict[str, Any] | None = None
        self._reduce_step: dict[str, Any] | None = None

    def orchestrator(
        self,
        agent: str,
        input: str | None = None,
        min_workers: int | None = None,
        max_workers: int | None = None,
        max_rounds: int | None = None,
    ) -> OrchestratorWorkersBuilder:
        """Configure orchestrator agent that decomposes tasks.

        Orchestrator must return JSON: [{"task": "subtask description"}, ...]

        Args:
            agent: Agent ID for orchestration (must be defined via .agent())
            input: Optional input template for orchestrator (Jinja2 syntax)
            max_workers: Maximum concurrent workers (None = unlimited)
            max_rounds: Maximum orchestrator delegation cycles (None = unlimited)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If orchestrator already defined, agent doesn't exist, or template invalid

        Example:
            >>> .orchestrator("planner", "Break down: {{task}}", min_workers=2, max_workers=10, max_rounds=2)
        """
        # Validate orchestrator not already defined
        if self._orchestrator_agent is not None:
            raise BuildError("Orchestrator already configured. Only one orchestrator per workflow.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        # Validate limits
        if min_workers is not None and min_workers < 1:
            raise BuildError("min_workers must be >= 1")
        if max_workers is not None and max_workers < 1:
            raise BuildError("max_workers must be >= 1")
        if min_workers is not None and max_workers is not None and min_workers > max_workers:
            raise BuildError("min_workers cannot be greater than max_workers")
        if max_rounds is not None and max_rounds < 1:
            raise BuildError("max_rounds must be >= 1")

        self._orchestrator_agent = agent
        self._orchestrator_input = input
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._max_rounds = max_rounds

        logger.debug("orchestrator_workers_orchestrator_configured", agent=agent)
        return self

    def decomposition_review(
        self,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> OrchestratorWorkersBuilder:
        """Add HITL review of task decomposition (pattern-specific HITL).

        Pauses after orchestrator decomposes task to allow user review/modification
        of subtasks before worker execution.

        Args:
            prompt: Message to display to user
            show: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If decomposition review already defined or template invalid

        Example:
            >>> .decomposition_review("Approve subtasks?", show="{{ subtasks }}")
        """
        # Validate decomposition review not already defined
        if self._decomposition_review is not None:
            raise BuildError(
                "Decomposition review already defined. Only one review per orchestrator."
            )

        # Validate templates
        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        review_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if show is not None:
            review_config["context_display"] = show
        if default is not None:
            review_config["default"] = default
        if timeout_seconds is not None:
            review_config["timeout_seconds"] = timeout_seconds

        self._decomposition_review = review_config

        logger.debug("orchestrator_workers_decomposition_review_added")
        return self

    def worker_template(
        self,
        agent: str,
        tools: list[str] | None = None,
    ) -> OrchestratorWorkersBuilder:
        """Configure worker agent template for subtask execution.

        All workers use the same agent and tool configuration. Workers execute
        subtasks in parallel based on orchestrator's decomposition.

        Args:
            agent: Agent ID for workers (must be defined via .agent())
            tools: Optional tool overrides for workers

        Returns:
            Self for method chaining

        Raises:
            BuildError: If worker already defined or agent doesn't exist

        Example:
            >>> .worker_template("executor", tools=["python", "http_request"])
        """
        # Validate worker not already defined
        if self._worker_agent is not None:
            raise BuildError(
                "Worker template already defined. Only one worker template per workflow."
            )

        # Validate agent exists
        self._validate_agent_exists(agent)

        self._worker_agent = agent
        self._worker_tools = tools

        logger.debug("orchestrator_workers_worker_configured", agent=agent, tools=tools)
        return self

    def reduce_review(
        self,
        prompt: str,
        show: str | None = None,
        default: str | None = None,
        timeout_seconds: int | None = None,
    ) -> OrchestratorWorkersBuilder:
        """Add HITL review before reduce step (pattern-specific HITL).

        Pauses after all workers complete to allow user review of worker
        results before final synthesis.

        Args:
            prompt: Message to display to user
            show: Optional context template to show user
            default: Optional default response if user provides empty input
            timeout_seconds: Optional timeout in seconds (0 = no timeout)

        Returns:
            Self for method chaining

        Raises:
            BuildError: If reduce review already defined or template invalid

        Example:
            >>> .reduce_review("Review worker results?", show="{{ workers }}")
        """
        # Validate reduce review not already defined
        if self._reduce_review is not None:
            raise BuildError("Reduce review already defined. Only one reduce review per workflow.")

        # Validate templates
        _validate_template_syntax(prompt)
        if show is not None:
            _validate_template_syntax(show)

        # Validate timeout
        if timeout_seconds is not None and timeout_seconds < 0:
            raise BuildError("timeout_seconds must be >= 0")

        review_config: dict[str, Any] = {"type": "hitl", "prompt": prompt}
        if show is not None:
            review_config["context_display"] = show
        if default is not None:
            review_config["default"] = default
        if timeout_seconds is not None:
            review_config["timeout_seconds"] = timeout_seconds

        self._reduce_review = review_config

        logger.debug("orchestrator_workers_reduce_review_added")
        return self

    def reduce_step(
        self,
        agent: str,
        input: str | None = None,
        vars: dict[str, str | int | bool] | None = None,
        tool_overrides: list[str] | None = None,
    ) -> OrchestratorWorkersBuilder:
        """Add reduce step to synthesize worker results.

        Reduce step executes after all workers complete. Optional - if not
        specified, workflow returns raw worker results.

        Args:
            agent: Agent ID for reduce (must be defined via .agent())
            input: Optional input template (can reference {{ workers }})
            vars: Optional variable overrides for reduce step
            tool_overrides: Optional tool ID overrides for reduce step

        Returns:
            Self for method chaining

        Raises:
            BuildError: If reduce already defined, agent doesn't exist, or template invalid

        Example:
            >>> .reduce_step("synthesizer", "Combine results: {{ workers }}")
        """
        # Validate reduce not already defined
        if self._reduce_step is not None:
            raise BuildError("Reduce step already defined. Only one reduce per workflow.")

        # Validate agent exists
        self._validate_agent_exists(agent)

        # Validate input template if provided
        if input is not None:
            _validate_template_syntax(input)

        reduce_config: dict[str, Any] = {"agent": agent}
        if input is not None:
            reduce_config["input"] = input
        if vars is not None:
            reduce_config["vars"] = vars
        if tool_overrides is not None:
            reduce_config["tool_overrides"] = tool_overrides

        self._reduce_step = reduce_config

        logger.debug("orchestrator_workers_reduce_configured", agent=agent)
        return self

    def artifact(self, path: str, template: str) -> FluentBuilder:
        """Define output artifact (delegates to parent builder).

        Args:
            path: Output file path
            template: Content template

        Returns:
            Parent FluentBuilder for continued chaining
        """
        return self.parent.artifact(path, template)

    def build(self) -> Workflow:
        """Build workflow (delegates to parent builder).

        Returns:
            Workflow instance ready to execute
        """
        return self.parent.build()

    def _validate_agent_exists(self, agent: str) -> None:
        """Validate agent exists, suggest similar names if not found.

        Args:
            agent: Agent ID to validate

        Raises:
            BuildError: If agent doesn't exist (with suggestions)
        """
        if agent not in self.parent._agents:
            suggestions = difflib.get_close_matches(
                agent, self.parent._agents.keys(), n=3, cutoff=0.6
            )

            msg = f"Agent '{agent}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
            msg += f" Use .agent('{agent}', ...) to define it before referencing."

            raise BuildError(msg)

    def _build_orchestrator_config(self) -> OrchestratorConfig:
        """Build orchestrator configuration.

        Returns:
            OrchestratorConfig with agent and optional limits
        """
        orchestrator_config_data: dict[str, Any] = {"agent": self._orchestrator_agent}

        # Add limits if specified
        if (
            self._min_workers is not None
            or self._max_workers is not None
            or self._max_rounds is not None
        ):
            limits_data: dict[str, Any] = {}
            if self._min_workers is not None:
                limits_data["min_workers"] = self._min_workers
            if self._max_workers is not None:
                limits_data["max_workers"] = self._max_workers
            if self._max_rounds is not None:
                limits_data["max_rounds"] = self._max_rounds
            orchestrator_config_data["limits"] = OrchestratorLimits(**limits_data)

        return OrchestratorConfig(**orchestrator_config_data)

    def _build_config(self) -> PatternConfig:
        """Build PatternConfig for orchestrator-workers pattern.

        Returns:
            PatternConfig with orchestrator, worker_template, and optional reviews/reduce

        Raises:
            BuildError: If orchestrator or worker not configured
        """
        # Validate required components
        if self._orchestrator_agent is None:
            raise BuildError("Orchestrator not configured. Call .orchestrator() before .build().")

        if self._worker_agent is None:
            raise BuildError(
                "Worker template not configured. Call .worker_template() before .build()."
            )

        # Build config
        try:
            orchestrator_config = self._build_orchestrator_config()

            # Build worker template
            worker_template_data: dict[str, Any] = {"agent": self._worker_agent}
            if self._worker_tools is not None:
                worker_template_data["tools"] = self._worker_tools
            worker_template = WorkerTemplate(**worker_template_data)

            # Build pattern config
            config_data: dict[str, Any] = {
                "orchestrator": orchestrator_config,
                "worker_template": worker_template,
            }

            if self._decomposition_review is not None:
                config_data["decomposition_review"] = HITLStep(**self._decomposition_review)

            if self._reduce_review is not None:
                config_data["reduce_review"] = HITLStep(**self._reduce_review)

            if self._reduce_step is not None:
                config_data["writeup"] = ChainStep(**self._reduce_step)

            return PatternConfig(**config_data)
        except Exception as e:
            raise BuildError(f"Failed to build orchestrator-workers config: {e}") from e

    def _pattern_type(self) -> PatternType:
        """Return pattern type for this builder.

        Returns:
            PatternType.ORCHESTRATOR_WORKERS
        """
        return PatternType.ORCHESTRATOR_WORKERS

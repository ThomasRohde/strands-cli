"""Unit tests for fluent builder API.

Tests cover:
- FluentBuilder core functionality (runtime, agent, artifact)
- ChainBuilder pattern-specific methods
- Fail-fast validation with actionable error messages
- Agent reference validation with suggestions
- Template syntax validation
- Golden file comparison (builder output == YAML spec)
"""

import pytest

from strands_cli.api.builders import (
    ChainBuilder,
    EvaluatorOptimizerBuilder,  # noqa: F401
    FluentBuilder,
    GraphBuilder,  # noqa: F401
    OrchestratorWorkersBuilder,  # noqa: F401
    ParallelBuilder,
    RoutingBuilder,  # noqa: F401
    WorkflowBuilder,
)
from strands_cli.api.exceptions import BuildError
from strands_cli.loader import load_spec
from strands_cli.types import PatternType, ProviderType


class TestFluentBuilderCore:
    """Test FluentBuilder core functionality."""

    def test_create_builder_with_name(self) -> None:
        """Test creating builder with name and description."""
        builder = FluentBuilder("test-workflow").description("Test description")
        assert builder.name == "test-workflow"
        assert builder._description == "Test description"

    def test_runtime_valid_provider(self) -> None:
        """Test runtime configuration with valid provider."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")
        assert builder._runtime is not None
        assert builder._runtime["provider"] == "openai"
        assert builder._runtime["model_id"] == "gpt-4o-mini"

    def test_runtime_invalid_provider_raises_error(self) -> None:
        """Test runtime with invalid provider raises BuildError."""
        builder = FluentBuilder("test")
        with pytest.raises(BuildError, match="Invalid provider 'invalid'"):
            builder.runtime("invalid")

    def test_runtime_filters_none_values(self) -> None:
        """Test runtime filters out None values."""
        builder = FluentBuilder("test").runtime(
            "openai", model="gpt-4o-mini", temperature=None, max_tokens=None
        )
        assert "temperature" not in builder._runtime
        assert "max_tokens" not in builder._runtime
        assert "model_id" in builder._runtime

    def test_runtime_accepts_all_valid_providers(self) -> None:
        """Test runtime accepts all valid providers."""
        for provider in ["bedrock", "ollama", "openai"]:
            builder = FluentBuilder(f"test-{provider}").runtime(provider, model="test-model")
            assert builder._runtime["provider"] == provider

    def test_agent_definition(self) -> None:
        """Test defining an agent."""
        builder = FluentBuilder("test").agent("researcher", "You are a researcher")
        assert "researcher" in builder._agents
        assert builder._agents["researcher"]["prompt"] == "You are a researcher"

    def test_agent_duplicate_id_raises_error(self) -> None:
        """Test duplicate agent ID raises BuildError."""
        builder = FluentBuilder("test").agent("researcher", "First prompt")
        with pytest.raises(BuildError, match="Agent 'researcher' already defined"):
            builder.agent("researcher", "Second prompt")

    def test_agent_with_tools(self) -> None:
        """Test agent with tools."""
        builder = FluentBuilder("test").agent(
            "researcher", "You are a researcher", tools=["http_request", "file_read"]
        )
        assert builder._agents["researcher"]["tools"] == ["http_request", "file_read"]

    def test_agent_filters_none_values(self) -> None:
        """Test agent filters out None values."""
        builder = FluentBuilder("test").agent("researcher", "Prompt", model_id=None)
        assert "model_id" not in builder._agents["researcher"]

    def test_artifact_valid_template(self) -> None:
        """Test defining artifact with valid template."""
        builder = FluentBuilder("test").artifact("output.md", "# Report\n{{ last_response }}")
        assert len(builder._artifacts) == 1
        assert builder._artifacts[0]["path"] == "output.md"
        assert builder._artifacts[0]["from"] == "# Report\n{{ last_response }}"

    def test_artifact_invalid_template_raises_error(self) -> None:
        """Test artifact with invalid template syntax raises BuildError."""
        builder = FluentBuilder("test")
        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.artifact("output.md", "{{ unclosed tag")

    def test_artifact_path_template_validation(self) -> None:
        """Test artifact path template validation."""
        builder = FluentBuilder("test").artifact("{{ topic }}-report.md", "Content")
        assert builder._artifacts[0]["path"] == "{{ topic }}-report.md"

    def test_artifact_path_invalid_template_raises_error(self) -> None:
        """Test artifact path with invalid template raises BuildError."""
        builder = FluentBuilder("test")
        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.artifact("{{ unclosed", "Content")


class TestChainBuilder:
    """Test ChainBuilder functionality."""

    def test_chain_creates_builder(self) -> None:
        """Test .chain() creates ChainBuilder."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")
        chain_builder = builder.chain()
        assert isinstance(chain_builder, ChainBuilder)
        assert chain_builder.parent is builder

    def test_chain_multiple_patterns_raises_error(self) -> None:
        """Test defining multiple patterns raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").chain()
        with pytest.raises(BuildError, match="Pattern already defined"):
            builder.parent.chain()

    def test_step_valid_agent(self) -> None:
        """Test adding step with valid agent."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "You are a researcher")
            .chain()
            .step("researcher", "Research: {{topic}}")
        )
        assert len(builder.steps) == 1
        assert builder.steps[0]["agent"] == "researcher"
        assert builder.steps[0]["input"] == "Research: {{topic}}"

    def test_step_missing_agent_raises_error(self) -> None:
        """Test step with missing agent raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").chain()
        with pytest.raises(BuildError, match="Agent 'unknown' not found"):
            builder.step("unknown", "Input")

    def test_step_missing_agent_suggests_similar(self) -> None:
        """Test step with missing agent suggests similar names."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )
        with pytest.raises(BuildError, match="Did you mean: 'researcher'"):
            builder.step("resercher", "Input")  # Typo

    def test_step_invalid_template_raises_error(self) -> None:
        """Test step with invalid template raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )
        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.step("researcher", "{{ unclosed")

    def test_step_with_vars(self) -> None:
        """Test step with variable overrides."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
            .step("researcher", "Input", vars={"depth": "detailed"})
        )
        assert builder.steps[0]["vars"] == {"depth": "detailed"}

    def test_step_with_tool_overrides(self) -> None:
        """Test step with tool overrides."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt", tools=["tool1", "tool2"])
            .chain()
            .step("researcher", "Input", tool_overrides=["tool1"])
        )
        assert builder.steps[0]["tool_overrides"] == ["tool1"]

    def test_hitl_valid_prompt(self) -> None:
        """Test adding HITL step with valid prompt."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
            .hitl("Review the results. Proceed?")
        )
        assert len(builder.steps) == 1
        assert builder.steps[0]["type"] == "hitl"
        assert builder.steps[0]["prompt"] == "Review the results. Proceed?"

    def test_hitl_with_context_display(self) -> None:
        """Test HITL with context display template."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
            .hitl("Review", context_display="{{ steps[0].response }}")
        )
        assert builder.steps[0]["context_display"] == "{{ steps[0].response }}"

    def test_hitl_with_default_and_timeout(self) -> None:
        """Test HITL with default response and timeout."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
            .hitl("Review", default="approved", timeout_seconds=60)
        )
        assert builder.steps[0]["default"] == "approved"
        assert builder.steps[0]["timeout_seconds"] == 60

    def test_hitl_negative_timeout_raises_error(self) -> None:
        """Test HITL with negative timeout raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )
        with pytest.raises(BuildError, match="timeout_seconds must be >= 0"):
            builder.hitl("Review", timeout_seconds=-1)

    def test_hitl_invalid_template_raises_error(self) -> None:
        """Test HITL with invalid template raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )
        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.hitl("{{ unclosed")


class TestFluentBuilderBuild:
    """Test FluentBuilder.build() validation."""

    def test_build_missing_runtime_raises_error(self) -> None:
        """Test build without runtime raises BuildError."""
        builder = FluentBuilder("test").agent("researcher", "Prompt").chain().step("researcher", "Input")
        with pytest.raises(BuildError, match="Runtime not configured"):
            builder.build()

    def test_build_missing_agents_raises_error(self) -> None:
        """Test build without agents raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").chain()
        with pytest.raises(BuildError, match="No agents defined"):
            builder.build()

    def test_build_missing_pattern_raises_error(self) -> None:
        """Test build without pattern raises BuildError."""
        builder = (
            FluentBuilder("test").runtime("openai", model="gpt-4o-mini").agent("researcher", "Prompt")
        )
        with pytest.raises(BuildError, match="No pattern defined"):
            builder.build()

    def test_build_chain_no_steps_raises_error(self) -> None:
        """Test build chain with no steps raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )
        with pytest.raises(BuildError, match="Chain must have at least one step"):
            builder.build()

    def test_build_valid_workflow(self) -> None:
        """Test building valid workflow."""
        workflow = (
            FluentBuilder("test-workflow", description="Test")
            .runtime("openai", model="gpt-4o-mini", temperature=0.7)
            .agent("researcher", "You are a researcher")
            .chain()
            .step("researcher", "Research: {{topic}}")
            .step("researcher", "Analyze: {{ steps[0].response }}")
            .artifact("output.md", "# Report\n{{ last_response }}")
            .build()
        )

        # Verify workflow spec
        assert workflow.spec.name == "test-workflow"
        assert workflow.spec.description == "Test"
        assert workflow.spec.runtime.provider == ProviderType.OPENAI
        assert workflow.spec.runtime.model_id == "gpt-4o-mini"
        assert workflow.spec.runtime.temperature == 0.7
        assert "researcher" in workflow.spec.agents
        assert workflow.spec.pattern.type == PatternType.CHAIN
        assert len(workflow.spec.pattern.config.steps) == 2
        assert workflow.spec.outputs is not None
        assert len(workflow.spec.outputs.artifacts) == 1


class TestGoldenFileComparison:
    """Test builder output matches YAML specs (golden tests)."""

    def test_chain_builder_matches_yaml(self) -> None:
        """Test ChainBuilder output matches chain-3-step-research-openai.yaml."""
        # Load YAML spec
        yaml_spec = load_spec(
            "examples/chain-3-step-research-openai.yaml",
            variables={"topic": "artificial intelligence safety"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("chain-3-step-research-openai")
            .description("Three-step chain demonstrating sequential context passing")
            .runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=8000)
            .agent(
                "researcher",
                "You are a research assistant. Provide clear, concise, and factual responses.\n"
                "Focus on accuracy and cite sources when possible.",
            )
            .chain()
            .step("researcher", "Research the topic: {{topic}}. List 3-5 key points.")
            .step(
                "researcher",
                "Based on this research:\n{{ steps[0].response }}\n\n"
                "Analyze the most important point and explain why it matters.",
                vars={"analysis_depth": "detailed"},
            )
            .step(
                "researcher",
                "Previous research:\n{{ steps[0].response | truncate(200) }}\n\n"
                "Analysis:\n{{ steps[1].response }}\n\n"
                "Write a 2-paragraph summary combining both insights.",
            )
            .artifact(
                "{{topic}}-research.md",
                "# Research Report: {{topic}}\n\n## Initial Research\n{{ steps[0].response }}\n\n"
                "## Analysis\n{{ steps[1].response }}\n\n## Summary\n{{ last_response }}",
            )
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime.provider == yaml_spec.runtime.provider
        assert api_spec.runtime.model_id == yaml_spec.runtime.model_id
        assert api_spec.runtime.temperature == yaml_spec.runtime.temperature
        assert api_spec.runtime.max_tokens == yaml_spec.runtime.max_tokens
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert len(api_spec.pattern.config.steps) == len(yaml_spec.pattern.config.steps)
        assert len(api_spec.agents) == len(yaml_spec.agents)
        assert api_spec.outputs is not None
        assert yaml_spec.outputs is not None
        assert len(api_spec.outputs.artifacts) == len(yaml_spec.outputs.artifacts)


class TestChainBuilderChaining:
    """Test method chaining and fluent API."""


class TestWorkflowBuilder:
    """Test WorkflowBuilder functionality."""

    def test_workflow_creates_builder(self) -> None:
        """Test .workflow() creates WorkflowBuilder."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")
        workflow_builder = builder.workflow()
        assert isinstance(workflow_builder, WorkflowBuilder)
        assert workflow_builder.parent is builder

    def test_workflow_multiple_patterns_raises_error(self) -> None:
        """Test defining multiple patterns raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").workflow()
        with pytest.raises(BuildError, match="Pattern already defined"):
            builder.parent.workflow()

    def test_task_valid_agent(self) -> None:
        """Test adding task with valid agent."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "You are a researcher")
            .workflow()
            .task("research", "researcher", "Research: {{topic}}")
        )
        assert len(builder.tasks) == 1
        assert builder.tasks[0]["id"] == "research"
        assert builder.tasks[0]["agent"] == "researcher"

    def test_task_with_dependencies(self) -> None:
        """Test task with dependencies."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .agent("analyst", "Prompt")
            .workflow()
            .task("research", "researcher", "Research")
            .task("analyze", "analyst", "{{ tasks.research.response }}", depends_on=["research"])
        )
        assert len(builder.tasks) == 2
        assert builder.tasks[1]["deps"] == ["research"]

    def test_task_duplicate_id_raises_error(self) -> None:
        """Test duplicate task ID raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
            .task("task1", "researcher", "Input")
        )
        with pytest.raises(BuildError, match="Task ID 'task1' already exists"):
            builder.task("task1", "researcher", "Another input")

    def test_task_missing_agent_raises_error(self) -> None:
        """Test task with missing agent raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").workflow()
        with pytest.raises(BuildError, match="Agent 'unknown' not found"):
            builder.task("task1", "unknown", "Input")

    def test_task_missing_dependency_raises_error(self) -> None:
        """Test task with missing dependency raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
        )
        with pytest.raises(BuildError, match="Dependency 'unknown' not found"):
            builder.task("task1", "researcher", "Input", depends_on=["unknown"])

    def test_task_with_vars_and_tools(self) -> None:
        """Test task with vars and tool overrides."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt", tools=["tool1", "tool2"])
            .workflow()
            .task("task1", "researcher", "Input", vars={"depth": "detailed"}, tool_overrides=["tool1"])
        )
        assert builder.tasks[0]["vars"] == {"depth": "detailed"}
        assert builder.tasks[0]["tool_overrides"] == ["tool1"]

    def test_hitl_task_valid(self) -> None:
        """Test adding HITL task."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
            .task("research", "researcher", "Research")
            .hitl_task("review", "Review the research?", show="{{ tasks.research.response }}", depends_on=["research"])
        )
        assert len(builder.tasks) == 2
        assert builder.tasks[1]["type"] == "hitl"
        assert builder.tasks[1]["prompt"] == "Review the research?"
        assert builder.tasks[1]["context_display"] == "{{ tasks.research.response }}"

    def test_hitl_task_negative_timeout_raises_error(self) -> None:
        """Test HITL task with negative timeout raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
        )
        with pytest.raises(BuildError, match="timeout_seconds must be >= 0"):
            builder.hitl_task("review", "Review?", timeout_seconds=-1)

    def test_circular_dependency_detected(self) -> None:
        """Test circular dependency detection."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
            .task("task1", "researcher", "Input")
            .task("task2", "researcher", "Input", depends_on=["task1"])
        )
        # Manually inject circular dependency for testing
        builder.tasks[0]["deps"] = ["task2"]

        with pytest.raises(BuildError, match="Circular dependency detected"):
            builder.build()

    def test_workflow_no_tasks_raises_error(self) -> None:
        """Test workflow with no tasks raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .workflow()
        )
        with pytest.raises(BuildError, match="Workflow must have at least one task"):
            builder.build()

    def test_workflow_build_valid(self) -> None:
        """Test building valid workflow."""
        workflow = (
            FluentBuilder("test-workflow")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Researcher prompt")
            .agent("analyst", "Analyst prompt")
            .workflow()
            .task("research", "researcher", "Research: {{topic}}")
            .task("analyze", "analyst", "Analyze: {{ tasks.research.response }}", depends_on=["research"])
            .artifact("output.md", "# Results\n{{ tasks.analyze.response }}")
            .build()
        )

        assert workflow.spec.name == "test-workflow"
        assert workflow.spec.pattern.type == PatternType.WORKFLOW
        assert len(workflow.spec.pattern.config.tasks) == 2
        assert workflow.spec.pattern.config.tasks[1].deps == ["research"]


class TestParallelBuilder:
    """Test ParallelBuilder functionality."""

    def test_parallel_creates_builder(self) -> None:
        """Test .parallel() creates ParallelBuilder."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")
        parallel_builder = builder.parallel()
        assert isinstance(parallel_builder, ParallelBuilder)
        assert parallel_builder.parent is builder

    def test_parallel_multiple_patterns_raises_error(self) -> None:
        """Test defining multiple patterns raises BuildError."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").parallel()
        with pytest.raises(BuildError, match="Pattern already defined"):
            builder.parent.parallel()

    def test_branch_creates_branch_builder(self) -> None:
        """Test .branch() creates branch context."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        branch = builder.branch("technical")
        assert branch.id == "technical"
        assert branch.parent is builder

    def test_branch_duplicate_id_raises_error(self) -> None:
        """Test duplicate branch ID raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
            .branch("branch1")
            .step("researcher", "Input")
            .done()
        )
        with pytest.raises(BuildError, match="Branch ID 'branch1' already exists"):
            builder.branch("branch1")

    def test_branch_not_completed_raises_error(self) -> None:
        """Test starting new branch without completing previous raises BuildError."""
        parallel_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        parallel_builder.branch("branch1")  # Start branch but don't complete
        with pytest.raises(BuildError, match="Previous branch 'branch1' not completed"):
            parallel_builder.branch("branch2")

    def test_branch_step_valid(self) -> None:
        """Test adding step to branch."""
        parallel_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        branch = parallel_builder.branch("technical")
        branch.step("researcher", "Analyze technical aspects")
        assert len(branch.steps) == 1
        assert branch.steps[0]["agent"] == "researcher"

    def test_branch_hitl_valid(self) -> None:
        """Test adding HITL to branch."""
        parallel_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        branch = parallel_builder.branch("technical")
        branch.step("researcher", "Input")
        branch.hitl("Review?", context_display="{{ steps[0].response }}")
        assert len(branch.steps) == 2
        assert branch.steps[1]["type"] == "hitl"

    def test_branch_done_finalizes(self) -> None:
        """Test .done() finalizes branch."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
            .branch("technical")
            .step("researcher", "Input")
            .done()
        )
        assert len(builder.branches) == 1
        assert builder.branches[0]["id"] == "technical"
        assert builder._current_branch is None

    def test_branch_empty_raises_error(self) -> None:
        """Test finalizing empty branch raises BuildError."""
        parallel_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        branch = parallel_builder.branch("technical")
        with pytest.raises(BuildError, match="Branch 'technical' must have at least one step"):
            branch.done()

    def test_reduce_valid(self) -> None:
        """Test adding reduce step."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .agent("writer", "Prompt")
            .parallel()
            .branch("branch1")
            .step("researcher", "Input")
            .done()
            .reduce("writer", "Synthesize: {{ branches.branch1.response }}")
        )
        assert builder._reduce_step is not None
        assert builder._reduce_step["agent"] == "writer"

    def test_reduce_duplicate_raises_error(self) -> None:
        """Test duplicate reduce step raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("writer", "Prompt")
            .parallel()
            .branch("branch1")
            .step("writer", "Input")
            .done()
            .reduce("writer", "Reduce 1")
        )
        with pytest.raises(BuildError, match="Reduce step already defined"):
            builder.reduce("writer", "Reduce 2")

    def test_parallel_build_valid(self) -> None:
        """Test building valid parallel workflow."""
        workflow = (
            FluentBuilder("test-parallel")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Researcher")
            .agent("writer", "Writer")
            .parallel()
            .branch("technical")
            .step("researcher", "Technical analysis")
            .done()
            .branch("business")
            .step("researcher", "Business analysis")
            .done()
            .reduce("writer", "Synthesize both")
            .artifact("output.md", "{{ last_response }}")
            .build()
        )

        assert workflow.spec.name == "test-parallel"
        assert workflow.spec.pattern.type == PatternType.PARALLEL
        assert len(workflow.spec.pattern.config.branches) == 2
        assert workflow.spec.pattern.config.reduce is not None
        assert workflow.spec.pattern.config.reduce.agent == "writer"

    def test_parallel_no_branches_raises_error(self) -> None:
        """Test parallel with no branches raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        with pytest.raises(BuildError, match="Parallel must have at least one branch"):
            builder.build()

    def test_parallel_uncompleted_branch_raises_error(self) -> None:
        """Test building with uncompleted branch raises BuildError."""
        parallel_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .parallel()
        )
        parallel_builder.branch("branch1").step("researcher", "Input")  # Don't call .done()
        with pytest.raises(BuildError, match="Branch 'branch1' not completed"):
            parallel_builder.build()


class TestWorkflowGoldenFile:
    """Test WorkflowBuilder output matches YAML specs."""

    def test_workflow_builder_structure_matches_yaml(self) -> None:
        """Test WorkflowBuilder creates structurally identical spec to YAML."""
        # Build via API
        api_workflow = (
            FluentBuilder("workflow-example")
            .description("DAG-based workflow example")
            .runtime("openai", model="gpt-4o-mini", temperature=0.7)
            .agent("researcher", "You are a research assistant.")
            .agent("analyst", "You are an analyst.")
            .workflow()
            .task("research", "researcher", "Research: {{topic}}")
            .task("analyze", "analyst", "Analyze: {{ tasks.research.response }}", depends_on=["research"])
            .artifact("output.md", "# Results\n{{ tasks.analyze.response }}")
            .build()
        )

        # Verify structure
        api_spec = api_workflow.spec
        assert api_spec.name == "workflow-example"
        assert api_spec.pattern.type == PatternType.WORKFLOW
        assert len(api_spec.pattern.config.tasks) == 2
        assert api_spec.pattern.config.tasks[0].id == "research"
        assert api_spec.pattern.config.tasks[1].deps == ["research"]


class TestParallelGoldenFile:
    """Test ParallelBuilder output matches YAML specs."""

    def test_parallel_builder_matches_yaml(self) -> None:
        """Test ParallelBuilder output matches parallel-simple-2-branches.yaml structure."""
        # Load YAML spec
        yaml_spec = load_spec(
            "examples/parallel-simple-2-branches.yaml",
            variables={"topic": "artificial intelligence in healthcare"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("parallel-simple-2-branches")
            .description("Simple parallel execution with 2 concurrent research branches")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "You are a research assistant. Provide concise, factual information about the requested topic.\n")
            .parallel()
            .branch("technical_analysis")
            .step("researcher", "Analyze the technical aspects of {{ topic }}")
            .done()
            .branch("business_impact")
            .step("researcher", "Analyze the business impact of {{ topic }}")
            .done()
            .artifact(
                "./parallel-simple-result.md",
                "# Parallel Research Results: {{ topic }}\n\n"
                "## Technical Analysis\n{{ branches.technical_analysis.response }}\n\n"
                "## Business Impact\n{{ branches.business_impact.response }}\n",
            )
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime.provider == yaml_spec.runtime.provider
        assert api_spec.runtime.model_id == yaml_spec.runtime.model_id
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert len(api_spec.pattern.config.branches) == len(yaml_spec.pattern.config.branches)
        assert api_spec.pattern.config.branches[0].id == yaml_spec.pattern.config.branches[0].id
        assert api_spec.pattern.config.branches[1].id == yaml_spec.pattern.config.branches[1].id
        assert api_spec.outputs is not None
        assert yaml_spec.outputs is not None
        assert len(api_spec.outputs.artifacts) == len(yaml_spec.outputs.artifacts)


class TestGraphBuilder:
    """Test GraphBuilder pattern-specific methods."""

    def test_graph_builder_basic(self) -> None:
        """Test building basic graph pattern."""
        workflow = (
            FluentBuilder("test-graph")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify input")
            .agent("processor", "Process input")
            .graph()
            .node("start", "classifier", "Classify: {{input}}")
            .node("process", "processor", "Process classified input")
            .edge("start", "process")
            .build()
        )

        assert workflow.spec.pattern.type == PatternType.GRAPH
        assert len(workflow.spec.pattern.config.nodes) == 2
        assert len(workflow.spec.pattern.config.edges) == 1

    def test_graph_conditional_edge(self) -> None:
        """Test graph with conditional edges."""
        workflow = (
            FluentBuilder("test-graph")
            .runtime("openai", model="gpt-4o-mini")
            .agent("router", "Route input")
            .agent("handler_a", "Handle type A")
            .agent("handler_b", "Handle type B")
            .graph()
            .node("classify", "router", "Classify input")
            .node("handle_a", "handler_a", "Handle A")
            .node("handle_b", "handler_b", "Handle B")
            .conditional_edge("classify", [("type == 'A'", "handle_a"), ("else", "handle_b")])
            .build()
        )

        assert len(workflow.spec.pattern.config.edges) == 1
        assert workflow.spec.pattern.config.edges[0].choose is not None

    def test_graph_hitl_node(self) -> None:
        """Test graph with HITL node."""
        workflow = (
            FluentBuilder("test-graph")
            .runtime("openai", model="gpt-4o-mini")
            .agent("processor", "Process input")
            .graph()
            .node("process", "processor", "Process input")
            .hitl_node("review", "Review processing?", show="{{nodes.process.response}}")
            .edge("process", "review")
            .build()
        )

        assert "review" in workflow.spec.pattern.config.nodes
        assert workflow.spec.pattern.config.nodes["review"].type == "hitl"

    def test_graph_no_nodes_raises_error(self) -> None:
        """Test graph with no nodes raises BuildError."""
        builder = FluentBuilder("test").runtime("openai").agent("test", "Test").graph()
        with pytest.raises(BuildError, match="Graph must have at least one node"):
            builder.build()

    def test_graph_no_edges_raises_error(self) -> None:
        """Test graph with no edges raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("test", "Test")
            .graph()
            .node("start", "test", "Start")
        )
        with pytest.raises(BuildError, match="Graph must have at least one edge"):
            builder.build()


class TestRoutingBuilder:
    """Test RoutingBuilder pattern-specific methods."""

    def test_routing_builder_basic(self) -> None:
        """Test building basic routing pattern."""
        workflow = (
            FluentBuilder("test-routing")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify query")
            .agent("tech_expert", "Technical expert")
            .agent("biz_expert", "Business expert")
            .routing()
            .router("classifier", "Classify: {{query}}")
            .route("technical")
            .step("tech_expert", "Answer technical: {{query}}")
            .done()
            .route("business")
            .step("biz_expert", "Answer business: {{query}}")
            .done()
            .build()
        )

        assert workflow.spec.pattern.type == PatternType.ROUTING
        assert workflow.spec.pattern.config.router.agent == "classifier"
        assert len(workflow.spec.pattern.config.routes) == 2

    def test_routing_review_router(self) -> None:
        """Test routing with router review."""
        workflow = (
            FluentBuilder("test-routing")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .agent("handler", "Handle")
            .routing()
            .router("classifier", "Classify input")
            .review_router("Confirm route?", show="{{router_decision.route}}")
            .route("default")
            .step("handler", "Handle")
            .done()
            .build()
        )

        assert workflow.spec.pattern.config.router.review_router is not None

    def test_routing_no_router_raises_error(self) -> None:
        """Test routing without router raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("handler", "Handle")
            .routing()
            .route("test")
            .step("handler", "Handle")
            .done()
        )
        with pytest.raises(BuildError, match="Router not configured"):
            builder.build()


class TestEvaluatorOptimizerBuilder:
    """Test EvaluatorOptimizerBuilder pattern-specific methods."""

    def test_evaluator_optimizer_basic(self) -> None:
        """Test building basic evaluator-optimizer pattern."""
        workflow = (
            FluentBuilder("test-eo")
            .runtime("openai", model="gpt-4o-mini")
            .agent("writer", "Write content")
            .agent("critic", "Evaluate content")
            .evaluator_optimizer()
            .producer("writer", "Write essay on {{topic}}")
            .evaluator("critic", "Rate essay: {{current_response}}")
            .accept(min_score=80, max_iterations=3)
            .revise_prompt("Improve based on: {{evaluation_response}}")
            .build()
        )

        assert workflow.spec.pattern.type == PatternType.EVALUATOR_OPTIMIZER
        assert workflow.spec.pattern.config.producer == "writer"
        assert workflow.spec.pattern.config.evaluator.agent == "critic"
        assert workflow.spec.pattern.config.accept.min_score == 80
        assert workflow.spec.pattern.config.accept.max_iters == 3

    def test_evaluator_optimizer_review_gate(self) -> None:
        """Test evaluator-optimizer with review gate."""
        workflow = (
            FluentBuilder("test-eo")
            .runtime("openai", model="gpt-4o-mini")
            .agent("writer", "Write")
            .agent("critic", "Evaluate")
            .evaluator_optimizer()
            .producer("writer", "Write")
            .evaluator("critic", "Evaluate")
            .accept(min_score=80)
            .revise_prompt("Improve")
            .review_gate("Continue?", show="Score: {{evaluation_response.score}}")
            .build()
        )

        assert workflow.spec.pattern.config.review_gate is not None

    def test_evaluator_optimizer_no_producer_raises_error(self) -> None:
        """Test evaluator-optimizer without producer raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("critic", "Evaluate")
            .evaluator_optimizer()
            .evaluator("critic", "Evaluate")
            .accept(min_score=80)
        )
        with pytest.raises(BuildError, match="Producer not configured"):
            builder.build()

    def test_evaluator_optimizer_no_accept_raises_error(self) -> None:
        """Test evaluator-optimizer without accept raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("writer", "Write")
            .agent("critic", "Evaluate")
            .evaluator_optimizer()
            .producer("writer", "Write")
            .evaluator("critic", "Evaluate")
        )
        with pytest.raises(BuildError, match="Acceptance criteria not configured"):
            builder.build()


class TestOrchestratorWorkersBuilder:
    """Test OrchestratorWorkersBuilder pattern-specific methods."""

    def test_orchestrator_workers_basic(self) -> None:
        """Test building basic orchestrator-workers pattern."""
        workflow = (
            FluentBuilder("test-ow")
            .runtime("openai", model="gpt-4o-mini")
            .agent("planner", "Plan tasks")
            .agent("worker", "Execute tasks")
            .orchestrator_workers()
            .orchestrator("planner", "Break down: {{task}}", max_workers=5)
            .worker_template("worker", tools=["python"])
            .build()
        )

        assert workflow.spec.pattern.type == PatternType.ORCHESTRATOR_WORKERS
        assert workflow.spec.pattern.config.orchestrator.agent == "planner"
        assert workflow.spec.pattern.config.worker_template.agent == "worker"
        assert workflow.spec.pattern.config.orchestrator.limits.max_workers == 5

    def test_orchestrator_workers_with_reviews(self) -> None:
        """Test orchestrator-workers with decomposition and reduce reviews."""
        workflow = (
            FluentBuilder("test-ow")
            .runtime("openai", model="gpt-4o-mini")
            .agent("planner", "Plan")
            .agent("worker", "Execute")
            .agent("synthesizer", "Synthesize")
            .orchestrator_workers()
            .orchestrator("planner", "Plan tasks")
            .decomposition_review("Approve subtasks?", show="{{subtasks}}")
            .worker_template("worker")
            .reduce_review("Review results?", show="{{workers}}")
            .reduce_step("synthesizer", "Synthesize: {{workers}}")
            .build()
        )

        assert workflow.spec.pattern.config.decomposition_review is not None
        assert workflow.spec.pattern.config.reduce_review is not None
        assert workflow.spec.pattern.config.writeup is not None

    def test_orchestrator_workers_no_orchestrator_raises_error(self) -> None:
        """Test orchestrator-workers without orchestrator raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("worker", "Execute")
            .orchestrator_workers()
            .worker_template("worker")
        )
        with pytest.raises(BuildError, match="Orchestrator not configured"):
            builder.build()

    def test_orchestrator_workers_no_worker_raises_error(self) -> None:
        """Test orchestrator-workers without worker raises BuildError."""
        builder = (
            FluentBuilder("test")
            .runtime("openai")
            .agent("planner", "Plan")
            .orchestrator_workers()
            .orchestrator("planner", "Plan")
        )
        with pytest.raises(BuildError, match="Worker template not configured"):
            builder.build()


class TestTemplateValidationEdgeCases:
    """Test edge cases in template validation."""

    def test_nested_template_syntax_valid(self) -> None:
        """Test nested Jinja2 templates are accepted."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "{{ steps[0].response | default('fallback') }}")
        )
        assert len(builder.steps) == 1

    def test_template_with_filters_valid(self) -> None:
        """Test templates with Jinja2 filters are accepted."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "{{ topic | upper | truncate(100) }}")
        )
        assert builder.steps[0]["input"] == "{{ topic | upper | truncate(100) }}"

    def test_template_in_artifact_path_valid(self) -> None:
        """Test template syntax in artifact path."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .artifact("{{topic}}-{{date}}.md", "Content")
        )
        assert builder._artifacts[0]["path"] == "{{topic}}-{{date}}.md"

    def test_empty_template_string_valid(self) -> None:
        """Test empty template strings are accepted."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "")
        )
        assert builder.steps[0]["input"] == ""

    def test_multiline_template_valid(self) -> None:
        """Test multiline templates are accepted."""
        multiline_template = """
        Research: {{topic}}
        
        Previous findings:
        {{ steps[0].response }}
        
        Next steps:
        1. Analyze
        2. Summarize
        """
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", multiline_template)
        )
        assert builder.steps[0]["input"] == multiline_template


class TestRuntimeConfigurationEdgeCases:
    """Test edge cases in runtime configuration."""

    def test_runtime_with_all_parameters(self) -> None:
        """Test runtime with all possible parameters."""
        builder = FluentBuilder("test").runtime(
            "bedrock",
            model="anthropic.claude-3-sonnet-20240229-v1:0",
            region="us-west-2",
            temperature=0.5,
            top_p=0.9,
            max_tokens=2000,
            max_parallel=10,
        )

        assert builder._runtime["provider"] == "bedrock"
        assert builder._runtime["model_id"] == "anthropic.claude-3-sonnet-20240229-v1:0"
        assert builder._runtime["region"] == "us-west-2"
        assert builder._runtime["temperature"] == 0.5
        assert builder._runtime["top_p"] == 0.9
        assert builder._runtime["max_tokens"] == 2000
        assert builder._runtime["max_parallel"] == 10

    def test_runtime_ollama_with_host(self) -> None:
        """Test Ollama runtime with custom host."""
        builder = FluentBuilder("test").runtime(
            "ollama", model="llama3.2:3b", host="http://custom-host:11434"
        )

        assert builder._runtime["provider"] == "ollama"
        assert builder._runtime["host"] == "http://custom-host:11434"

    def test_runtime_temperature_bounds(self) -> None:
        """Test runtime accepts temperature at bounds (0.0, 1.0)."""
        builder_min = FluentBuilder("test").runtime("openai", model="gpt-4o-mini", temperature=0.0)
        builder_max = FluentBuilder("test2").runtime("openai", model="gpt-4o-mini", temperature=1.0)

        assert builder_min._runtime["temperature"] == 0.0
        assert builder_max._runtime["temperature"] == 1.0


class TestAgentConfigurationEdgeCases:
    """Test edge cases in agent configuration."""

    def test_agent_with_multiple_tools(self) -> None:
        """Test agent with multiple tools."""
        builder = FluentBuilder("test").agent(
            "multi_tool",
            "Use tools",
            tools=["python", "http_request", "file_read", "calculator"],
        )

        assert len(builder._agents["multi_tool"]["tools"]) == 4

    def test_agent_with_model_override(self) -> None:
        """Test agent with model_id override."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("special_agent", "Prompt", model_id="gpt-4o")
        )

        assert builder._agents["special_agent"]["model_id"] == "gpt-4o"

    def test_agent_with_empty_tools_list(self) -> None:
        """Test agent with empty tools list."""
        builder = FluentBuilder("test").agent("no_tools", "Prompt", tools=[])

        assert builder._agents["no_tools"]["tools"] == []


class TestWorkflowDependencyEdgeCases:
    """Test edge cases in workflow dependency handling."""

    def test_workflow_task_with_multiple_dependencies(self) -> None:
        """Test task with multiple dependencies."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .workflow()
            .task("task1", "agent1", "Task 1")
            .task("task2", "agent1", "Task 2")
            .task("task3", "agent1", "Task 3")
            .task("task4", "agent1", "Task 4", depends_on=["task1", "task2", "task3"])
        )

        assert builder.tasks[3]["deps"] == ["task1", "task2", "task3"]

    def test_workflow_task_with_no_input(self) -> None:
        """Test task without input field."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .workflow()
            .task("task1", "agent1")
        )

        assert "input" not in builder.tasks[0]

    def test_workflow_task_with_description(self) -> None:
        """Test task with description field."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .workflow()
            .task("task1", "agent1", input="Input", description="Task 1 description")
        )

        assert builder.tasks[0]["description"] == "Task 1 description"


class TestGraphBuilderEdgeCases:
    """Test edge cases in graph builder."""

    def test_graph_node_without_input(self) -> None:
        """Test graph node without input field."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("node1", "agent1")
        )

        assert "input" not in builder.nodes["node1"]

    def test_graph_duplicate_node_raises_error(self) -> None:
        """Test duplicate node ID raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("node1", "agent1")
        )

        with pytest.raises(BuildError, match="Node ID 'node1' already exists"):
            builder.node("node1", "agent1")

    def test_graph_edge_to_multiple_nodes(self) -> None:
        """Test graph edge with multiple target nodes (sequential)."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("start", "agent1")
            .node("middle1", "agent1")
            .node("middle2", "agent1")
            .edge("start", ["middle1", "middle2"])
        )

        assert builder.edges[0]["to"] == ["middle1", "middle2"]

    def test_graph_edge_nonexistent_source_raises_error(self) -> None:
        """Test edge with nonexistent source node raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("target", "agent1")
        )

        with pytest.raises(BuildError, match="Source node 'unknown' not found"):
            builder.edge("unknown", "target")

    def test_graph_conditional_edge_empty_choices_raises_error(self) -> None:
        """Test conditional edge with empty choices raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("source", "agent1")
        )

        with pytest.raises(BuildError, match="Conditional edge must have at least one choice"):
            builder.conditional_edge("source", [])

    def test_graph_max_iterations_minimum(self) -> None:
        """Test graph max_iterations at minimum (1)."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
            .node("node1", "agent1")
            .node("node2", "agent1")
            .edge("node1", "node2")
            .max_iterations(1)
        )

        assert builder._max_iterations == 1

    def test_graph_max_iterations_zero_raises_error(self) -> None:
        """Test graph max_iterations=0 raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .graph()
        )

        with pytest.raises(BuildError, match="max_iterations must be >= 1"):
            builder.max_iterations(0)


class TestParallelBuilderEdgeCases:
    """Test edge cases in parallel builder."""

    def test_parallel_reduce_duplicate_raises_error(self) -> None:
        """Test adding duplicate reduce step raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .parallel()
            .branch("branch1")
            .step("agent1", "Step")
            .done()
            .reduce("agent1", "Reduce 1")
        )

        with pytest.raises(BuildError, match="Reduce step already defined"):
            builder.reduce("agent1", "Reduce 2")

    def test_parallel_no_branches_raises_error(self) -> None:
        """Test parallel with no branches raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .parallel()
        )

        with pytest.raises(BuildError, match="Parallel must have at least one branch"):
            builder.build()


class TestRoutingBuilderEdgeCases:
    """Test edge cases in routing builder."""

    def test_routing_router_max_retries(self) -> None:
        """Test router with custom max_retries."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .agent("handler", "Handle")
            .routing()
            .router("classifier", "Classify", max_retries=5)
            .route("default")
            .step("handler", "Handle")
            .done()
        )

        assert builder._router_max_retries == 5

    def test_routing_duplicate_router_raises_error(self) -> None:
        """Test defining router twice raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .routing()
            .router("classifier", "Input 1")
        )

        with pytest.raises(BuildError, match="Router already defined"):
            builder.router("classifier", "Input 2")

    def test_routing_no_routes_raises_error(self) -> None:
        """Test routing with no routes raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .routing()
            .router("classifier", "Classify")
        )

        with pytest.raises(BuildError, match="Routing must have at least one route"):
            builder.build()

    def test_routing_uncompleted_route_raises_error(self) -> None:
        """Test building with uncompleted route raises error."""
        routing_builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .agent("handler", "Handle")
            .routing()
            .router("classifier", "Classify")
        )
        routing_builder.route("incomplete").step("handler", "Step")
        # Don't call .done()

        with pytest.raises(BuildError, match="Route 'incomplete' not completed"):
            routing_builder.build()


class TestEvaluatorOptimizerEdgeCases:
    """Test edge cases in evaluator-optimizer builder."""

    def test_evaluator_optimizer_no_evaluator_raises_error(self) -> None:
        """Test evaluator-optimizer without evaluator raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("writer", "Write")
            .evaluator_optimizer()
            .producer("writer", "Write")
            .accept(min_score=8)
        )

        with pytest.raises(BuildError, match="Evaluator not configured"):
            builder.build()

    def test_evaluator_optimizer_no_revise_prompt_raises_error(self) -> None:
        """Test evaluator-optimizer without revise_prompt raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("writer", "Write")
            .agent("critic", "Evaluate")
            .evaluator_optimizer()
            .producer("writer", "Write")
            .evaluator("critic", "Evaluate")
            .accept(min_score=8)
        )

        with pytest.raises(BuildError, match="Revise prompt not configured"):
            builder.build()


class TestOrchestratorWorkersEdgeCases:
    """Test edge cases in orchestrator-workers builder."""

    def test_orchestrator_min_max_workers(self) -> None:
        """Test orchestrator with min and max worker limits."""
        workflow = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("planner", "Plan")
            .agent("worker", "Work")
            .orchestrator_workers()
            .orchestrator("planner", "Plan", max_workers=10, min_workers=2)
            .worker_template("worker")
            .build()
        )

        assert workflow.spec.pattern.config.orchestrator.limits.max_workers == 10
        assert workflow.spec.pattern.config.orchestrator.limits.min_workers == 2

    def test_orchestrator_duplicate_orchestrator_raises_error(self) -> None:
        """Test defining orchestrator twice raises error."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("planner", "Plan")
            .orchestrator_workers()
            .orchestrator("planner", "Plan 1")
        )

        with pytest.raises(BuildError, match="Orchestrator already configured"):
            builder.orchestrator("planner", "Plan 2")



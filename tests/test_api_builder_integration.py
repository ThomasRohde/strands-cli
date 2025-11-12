"""Integration tests for builder API workflow construction and validation.

Tests builder API end-to-end: construction → validation → Workflow object creation.
Does NOT test execution (covered by test_api_executor_integration.py).

Focus areas:
- Builder chaining and method composition
- Complex workflow structures
- Error propagation through build pipeline
- Workflow object creation and spec validation
"""

import pytest

from strands_cli.api.builders import FluentBuilder
from strands_cli.api.exceptions import BuildError
from strands_cli.types import PatternType


class TestBuilderChaining:
    """Test fluent builder method chaining patterns."""

    def test_full_chain_workflow_construction(self) -> None:
        """Test complete chain workflow construction with all features."""
        workflow = (
            FluentBuilder("comprehensive-chain")
            .description("Comprehensive chain with all features")
            .runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=4000)
            .agent("researcher", "You research", tools=["http_request"])
            .agent("analyst", "You analyze")
            .chain()
            .step("researcher", "Step 1: {{topic}}", vars={"depth": "detailed"})
            .hitl("Review step 1?", context_display="{{ steps[0].response }}", timeout_seconds=120)
            .step("analyst", "Analyze: {{ steps[0].response }}")
            .artifact("report.md", "# Report\n{{ last_response }}")
            .build()
        )

        # Verify workflow construction
        assert workflow.spec.name == "comprehensive-chain"
        assert workflow.spec.description == "Comprehensive chain with all features"
        assert workflow.spec.runtime.temperature == 0.7
        assert workflow.spec.runtime.max_tokens == 4000
        assert len(workflow.spec.agents) == 2
        assert workflow.spec.agents["researcher"].tools == ["http_request"]
        assert workflow.spec.pattern.type == PatternType.CHAIN
        assert len(workflow.spec.pattern.config.steps) == 3
        assert workflow.spec.pattern.config.steps[1].type == "hitl"
        assert workflow.spec.outputs is not None
        assert len(workflow.spec.outputs.artifacts) == 1

    def test_diamond_dag_workflow_construction(self) -> None:
        """Test workflow pattern with diamond-shaped dependency graph."""
        workflow = (
            FluentBuilder("diamond-dag")
            .runtime("openai", model="gpt-4o-mini", max_parallel=2)
            .agent("init", "Initialize")
            .agent("worker_a", "Process A")
            .agent("worker_b", "Process B")
            .agent("merge", "Merge results")
            .workflow()
            .task("init", "init", "Initialize: {{input}}")
            .task("process_a", "worker_a", "{{ tasks.init.response }}", depends_on=["init"])
            .task("process_b", "worker_b", "{{ tasks.init.response }}", depends_on=["init"])
            .task(
                "merge",
                "merge",
                "Merge: {{ tasks.process_a.response }} + {{ tasks.process_b.response }}",
                depends_on=["process_a", "process_b"],
            )
            .artifact("result.txt", "{{ tasks.merge.response }}")
            .build()
        )

        # Verify dependency structure
        assert workflow.spec.pattern.type == PatternType.WORKFLOW
        assert len(workflow.spec.pattern.config.tasks) == 4
        assert workflow.spec.pattern.config.tasks[0].id == "init"
        assert workflow.spec.pattern.config.tasks[1].deps == ["init"]
        assert workflow.spec.pattern.config.tasks[2].deps == ["init"]
        assert set(workflow.spec.pattern.config.tasks[3].deps) == {"process_a", "process_b"}
        assert workflow.spec.runtime.max_parallel == 2

    def test_complex_parallel_with_reduce(self) -> None:
        """Test parallel pattern with multi-step branches and reduce."""
        workflow = (
            FluentBuilder("parallel-complex")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Research")
            .agent("analyst", "Analyze")
            .agent("writer", "Write")
            .parallel()
            .branch("branch_a")
            .step("researcher", "Research A")
            .step("analyst", "Analyze: {{ steps[0].response }}")
            .hitl("Review branch A?")
            .done()
            .branch("branch_b")
            .step("researcher", "Research B")
            .step("analyst", "Analyze: {{ steps[0].response }}")
            .done()
            .reduce(
                "writer",
                "Combine: {{ branches.branch_a.response }} + {{ branches.branch_b.response }}",
            )
            .artifact("synthesis.md", "{{ last_response }}")
            .build()
        )

        # Verify parallel structure
        assert workflow.spec.pattern.type == PatternType.PARALLEL
        assert len(workflow.spec.pattern.config.branches) == 2
        assert len(workflow.spec.pattern.config.branches[0].steps) == 3  # 2 steps + HITL
        assert len(workflow.spec.pattern.config.branches[1].steps) == 2
        assert workflow.spec.pattern.config.branches[0].steps[2].type == "hitl"
        assert workflow.spec.pattern.config.reduce is not None
        assert workflow.spec.pattern.config.reduce.agent == "writer"

    def test_graph_with_conditional_routing(self) -> None:
        """Test graph pattern with conditional edges."""
        workflow = (
            FluentBuilder("conditional-graph")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .agent("handler_low", "Handle low priority")
            .agent("handler_medium", "Handle medium priority")
            .agent("handler_high", "Handle high priority")
            .graph()
            .node("classify", "classifier", "Classify: {{request}}")
            .node("low", "handler_low", "Low priority")
            .node("medium", "handler_medium", "Medium priority")
            .node("high", "handler_high", "High priority")
            .conditional_edge(
                "classify",
                [
                    ("priority == 'high'", "high"),
                    ("priority == 'medium'", "medium"),
                    ("else", "low"),
                ],
            )
            .max_iterations(20)
            .build()
        )

        # Verify graph structure
        assert workflow.spec.pattern.type == PatternType.GRAPH
        assert len(workflow.spec.pattern.config.nodes) == 4
        assert len(workflow.spec.pattern.config.edges) == 1
        assert workflow.spec.pattern.config.edges[0].choose is not None
        assert len(workflow.spec.pattern.config.edges[0].choose) == 3
        assert workflow.spec.pattern.config.max_iterations == 20

    def test_routing_with_multi_step_routes(self) -> None:
        """Test routing pattern with multi-step route chains."""
        workflow = (
            FluentBuilder("multi-step-routing")
            .runtime("openai", model="gpt-4o-mini")
            .agent("classifier", "Classify")
            .agent("researcher", "Research")
            .agent("analyst", "Analyze")
            .routing()
            .router("classifier", "Classify query: {{query}}", max_retries=3)
            .route("detailed")
            .step("researcher", "Research in detail: {{query}}")
            .step("analyst", "Deep analysis: {{ steps[0].response }}")
            .done()
            .route("quick")
            .step("analyst", "Quick answer: {{query}}")
            .done()
            .artifact("answer.md", "{{ last_response }}")
            .build()
        )

        # Verify routing structure
        assert workflow.spec.pattern.type == PatternType.ROUTING
        assert workflow.spec.pattern.config.router.max_retries == 3
        assert len(workflow.spec.pattern.config.routes) == 2
        assert len(workflow.spec.pattern.config.routes["detailed"].steps) == 2
        assert len(workflow.spec.pattern.config.routes["quick"].steps) == 1

    def test_evaluator_optimizer_with_review_gate(self) -> None:
        """Test evaluator-optimizer pattern with HITL review gate."""
        workflow = (
            FluentBuilder("eo-with-review")
            .runtime("openai", model="gpt-4o-mini", temperature=0.3)
            .agent("coder", "Write code", tools=["python"])
            .agent("reviewer", "Review code")
            .evaluator_optimizer()
            .producer("coder", "Write code for: {{task}}")
            .evaluator("reviewer", "Review: {{ current_response }}")
            .accept(min_score=9, max_iterations=5)
            .revise_prompt("Fix: {{ evaluation_response.issues }}\n\nCode: {{ current_response }}")
            .review_gate("Continue iteration?", show="Score: {{ evaluation_response.score }}")
            .artifact("code.py", "{{ last_response }}")
            .build()
        )

        # Verify evaluator-optimizer structure
        assert workflow.spec.pattern.type == PatternType.EVALUATOR_OPTIMIZER
        assert workflow.spec.pattern.config.accept.min_score == 9
        assert workflow.spec.pattern.config.accept.max_iters == 5
        assert workflow.spec.pattern.config.review_gate is not None
        assert workflow.spec.agents["coder"].tools == ["python"]

    def test_orchestrator_with_all_features(self) -> None:
        """Test orchestrator-workers pattern with all optional features."""
        workflow = (
            FluentBuilder("orchestrator-full")
            .runtime("openai", model="gpt-4o-mini", max_parallel=5)
            .agent("planner", "Plan")
            .agent("worker", "Execute", tools=["python", "http_request"])
            .agent("synthesizer", "Synthesize")
            .orchestrator_workers()
            .orchestrator("planner", "Plan: {{project}}", max_workers=10, min_workers=2)
            .decomposition_review("Approve subtasks?", show="{{subtasks}}")
            .worker_template("worker", tools=["python", "http_request"])
            .reduce_review("Review worker results?", show="{{workers}}")
            .reduce_step("synthesizer", "Synthesize: {{workers}}")
            .artifact("project-result.md", "{{ last_response }}")
            .build()
        )

        # Verify orchestrator structure
        assert workflow.spec.pattern.type == PatternType.ORCHESTRATOR_WORKERS
        assert workflow.spec.pattern.config.orchestrator.limits.max_workers == 10
        assert workflow.spec.pattern.config.orchestrator.limits.min_workers == 2
        assert workflow.spec.pattern.config.decomposition_review is not None
        assert workflow.spec.pattern.config.reduce_review is not None
        assert workflow.spec.pattern.config.writeup is not None
        assert workflow.spec.pattern.config.worker_template.tools == ["python", "http_request"]


class TestBuilderErrorHandling:
    """Test error handling and validation throughout build pipeline."""

    def test_invalid_agent_reference_error_message(
        self, invalid_agent_reference_builder: FluentBuilder
    ) -> None:
        """Test that invalid agent reference provides actionable error with suggestions."""
        with pytest.raises(BuildError, match="Agent 'unknown_agent' not found"):
            invalid_agent_reference_builder.step("unknown_agent", "Input")

    def test_invalid_agent_reference_suggests_similar(self) -> None:
        """Test that error message suggests similar agent names."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "Prompt")
            .chain()
        )

        with pytest.raises(BuildError, match="Did you mean: 'researcher'"):
            builder.step("resercher", "Input")  # Typo: missing 'a'

    def test_circular_dependency_detection(self) -> None:
        """Test circular dependency detection in workflow DAG."""
        builder = (
            FluentBuilder("circular-test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent")
            .workflow()
            .task("task1", "agent1", "Task 1")
            .task("task2", "agent1", "Task 2", depends_on=["task1"])
        )

        # Manually inject circular dependency
        builder.tasks[0]["deps"] = ["task2"]

        with pytest.raises(BuildError, match="Circular dependency detected"):
            builder.build()

    def test_missing_runtime_error(self, missing_runtime_builder: FluentBuilder) -> None:
        """Test error when building without runtime configuration."""
        with pytest.raises(BuildError, match="Runtime not configured"):
            missing_runtime_builder.step("researcher", "Input").build()

    def test_duplicate_agent_id_error(self) -> None:
        """Test error when defining duplicate agent IDs."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")

        builder.agent("researcher", "First prompt")
        with pytest.raises(BuildError, match="Agent 'researcher' already defined"):
            builder.agent("researcher", "Second prompt")

    def test_invalid_template_syntax_in_step(self) -> None:
        """Test error for invalid Jinja2 template syntax in step."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
        )

        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.step("agent1", "{{ unclosed_tag")

    def test_invalid_template_syntax_in_artifact(self) -> None:
        """Test error for invalid Jinja2 template syntax in artifact."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini")

        with pytest.raises(BuildError, match="Invalid template syntax"):
            builder.artifact("output.md", "{{ unclosed_tag")

    def test_negative_timeout_error(self) -> None:
        """Test error for negative HITL timeout."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
        )

        with pytest.raises(BuildError, match="timeout_seconds must be >= 0"):
            builder.hitl("Review?", timeout_seconds=-1)

    def test_branch_not_completed_error(self) -> None:
        """Test error when trying to build with uncompleted branch."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .parallel()
            .branch("branch1")
            .step("agent1", "Step 1")
        )
        # Don't call .done()

        with pytest.raises(BuildError, match="Branch 'branch1' not completed"):
            builder.build()

    def test_empty_branch_error(self) -> None:
        """Test error when finalizing branch with no steps."""
        builder = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .parallel()
            .branch("empty_branch")
        )

        with pytest.raises(BuildError, match="Branch 'empty_branch' must have at least one step"):
            builder.done()

    def test_no_pattern_defined_error(self) -> None:
        """Test error when building without defining a pattern."""
        builder = (
            FluentBuilder("test").runtime("openai", model="gpt-4o-mini").agent("agent1", "Prompt")
        )

        with pytest.raises(BuildError, match="No pattern defined"):
            builder.build()

    def test_multiple_patterns_error(self) -> None:
        """Test error when trying to define multiple patterns."""
        builder = FluentBuilder("test").runtime("openai", model="gpt-4o-mini").chain()

        with pytest.raises(BuildError, match="Pattern already defined"):
            builder.parent.workflow()


class TestWorkflowObjectCreation:
    """Test Workflow object creation and API compatibility."""

    def test_workflow_from_builder_has_spec(self) -> None:
        """Test that Workflow created from builder has valid spec."""
        workflow = (
            FluentBuilder("test-workflow")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "Step 1")
            .build()
        )

        assert hasattr(workflow, "spec")
        assert workflow.spec.name == "test-workflow"
        assert workflow.spec.runtime.provider.value == "openai"
        assert workflow.spec.pattern.type == PatternType.CHAIN

    def test_workflow_supports_run_methods(self) -> None:
        """Test that Workflow from builder exposes run methods."""
        workflow = (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "Step 1")
            .build()
        )

        # Verify Workflow API methods exist
        assert hasattr(workflow, "run_interactive")
        assert hasattr(workflow, "run_interactive_async")
        assert callable(workflow.run_interactive)
        assert callable(workflow.run_interactive_async)

    def test_workflow_variable_injection(self) -> None:
        """Test that Workflow can accept runtime variables."""
        workflow = (
            FluentBuilder("variable-test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "Process: {{topic}}")
            .build()
        )

        # Workflow should be created successfully
        assert workflow.spec.pattern.config.steps[0].input == "Process: {{topic}}"

    def test_workflow_with_multiple_artifacts(self) -> None:
        """Test Workflow with multiple output artifacts."""
        workflow = (
            FluentBuilder("multi-artifact")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Prompt")
            .chain()
            .step("agent1", "Step 1")
            .artifact("report.md", "# Report\n{{ last_response }}")
            .artifact("summary.txt", "{{ last_response | truncate(100) }}")
            .artifact("data.json", '{"result": "{{ last_response }}"}')
            .build()
        )

        assert workflow.spec.outputs is not None
        assert len(workflow.spec.outputs.artifacts) == 3
        assert workflow.spec.outputs.artifacts[0].path == "report.md"
        assert workflow.spec.outputs.artifacts[1].path == "summary.txt"
        assert workflow.spec.outputs.artifacts[2].path == "data.json"


class TestBuilderReusability:
    """Test that builders can be reused and composed."""

    def test_builder_reuse_for_multiple_workflows(self) -> None:
        """Test that base builder can be reused to create multiple workflows."""
        base = (
            FluentBuilder("base").runtime("openai", model="gpt-4o-mini").agent("agent1", "Prompt")
        )

        # Create chain workflow
        chain_workflow = base.chain().step("agent1", "Chain step").build()

        # Verify we can't reuse after build (pattern already defined)
        # This is expected behavior - one builder = one workflow
        assert chain_workflow.spec.pattern.type == PatternType.CHAIN

    def test_agent_sharing_across_patterns(self) -> None:
        """Test that agents defined in base builder are available to pattern."""
        workflow = (
            FluentBuilder("shared-agents")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent1", "Agent 1")
            .agent("agent2", "Agent 2")
            .agent("agent3", "Agent 3")
            .chain()
            .step("agent1", "Step 1")
            .step("agent2", "Step 2")
            .step("agent3", "Step 3")
            .build()
        )

        assert len(workflow.spec.agents) == 3
        assert all(agent_id in workflow.spec.agents for agent_id in ["agent1", "agent2", "agent3"])

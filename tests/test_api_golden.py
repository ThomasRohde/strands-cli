"""Golden file tests for builder API.

Compares builder-generated specs with YAML golden files to ensure
programmatic API produces identical workflow specifications.

Tests all 7 patterns:
- Chain
- Workflow (DAG)
- Parallel
- Graph
- Routing
- Evaluator-Optimizer
- Orchestrator-Workers
"""

from strands_cli.api.builders import FluentBuilder
from strands_cli.loader import load_spec
from strands_cli.types import Agent, PatternType, Runtime


def _runtime_kwargs(runtime: Runtime) -> dict[str, object]:
    """Convert Runtime model to FluentBuilder.runtime kwargs."""

    kwargs: dict[str, object] = {
        "model": runtime.model_id,
        "region": runtime.region,
        "host": runtime.host,
        "temperature": runtime.temperature,
        "top_p": runtime.top_p,
        "max_tokens": runtime.max_tokens,
        "max_parallel": runtime.max_parallel,
    }

    if runtime.budgets is not None:
        kwargs["budgets"] = runtime.budgets
    if runtime.failure_policy is not None:
        kwargs["failure_policy"] = runtime.failure_policy

    return {key: value for key, value in kwargs.items() if value is not None}


def _register_agents(builder: FluentBuilder, agents: dict[str, Agent]) -> FluentBuilder:
    """Register agents on builder mirroring YAML spec."""

    for agent_id, agent in agents.items():
        kwargs: dict[str, object] = {}
        if agent.tools is not None:
            kwargs["tools"] = agent.tools
        if agent.model_id is not None:
            kwargs["model_id"] = agent.model_id
        builder = builder.agent(agent_id, agent.prompt, **kwargs)

    return builder


class TestChainGoldenFiles:
    """Test ChainBuilder output matches YAML golden files."""

    def test_chain_3_step_research_openai(self) -> None:
        """Test ChainBuilder matches chain-3-step-research-openai.yaml exactly."""
        # Load YAML golden file
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
            .output_dir("artifacts")
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
        assert api_spec.pattern.type == PatternType.CHAIN
        assert len(api_spec.pattern.config.steps) == len(yaml_spec.pattern.config.steps)
        assert len(api_spec.pattern.config.steps) == 3
        assert len(api_spec.agents) == len(yaml_spec.agents)
        assert api_spec.outputs is not None
        assert yaml_spec.outputs is not None
        assert len(api_spec.outputs.artifacts) == len(yaml_spec.outputs.artifacts)
        assert len(api_spec.outputs.artifacts) == 1

    def test_chain_calculator_openai(self) -> None:
        """Test ChainBuilder matches chain-calculator-openai.yaml (with tools)."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/chain-calculator-openai.yaml",
            variables={"expression": "25 * 4 + 100"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        steps = yaml_spec.pattern.config.steps or []
        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected at least one artifact in YAML spec"

        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)
        chain_builder = builder.chain()

        for step in steps:
            chain_builder = chain_builder.step(
                step.agent,
                step.input,
                vars=step.vars,
                tool_overrides=step.tool_overrides,
            )

        chain_builder = chain_builder.artifact(artifacts[0].path, artifacts[0].from_)
        api_workflow = chain_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.steps is not None
        assert len(api_spec.pattern.config.steps) == len(steps)
        for api_step, yaml_step in zip(api_spec.pattern.config.steps, steps, strict=True):
            assert api_step.agent == yaml_step.agent
            assert api_step.input == yaml_step.input
            assert api_step.vars == yaml_step.vars


class TestWorkflowGoldenFiles:
    """Test WorkflowBuilder output matches YAML golden files."""

    def test_workflow_linear_dag_openai(self) -> None:
        """Test WorkflowBuilder matches workflow-linear-dag-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/workflow-linear-dag-openai.yaml",
            variables={"topic": "quantum computing"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        workflow_builder = builder.workflow()
        tasks = yaml_spec.pattern.config.tasks or []
        for task in tasks:
            task_data = task.model_dump(by_alias=True, exclude_none=True)
            workflow_builder = workflow_builder.task(
                task_data["id"],
                task_data["agent"],
                input=task_data.get("input"),
                description=task_data.get("description"),
                depends_on=task_data.get("deps"),
                vars=task_data.get("vars"),
                tool_overrides=task_data.get("tool_overrides"),
            )

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected workflow artifacts defined in YAML"
        fluent_builder = workflow_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.tasks is not None
        assert len(api_spec.pattern.config.tasks) == len(tasks)
        for api_task, yaml_task in zip(api_spec.pattern.config.tasks, tasks, strict=True):
            assert api_task.id == yaml_task.id
            assert api_task.agent == yaml_task.agent
            assert api_task.deps == yaml_task.deps
            assert api_task.description == yaml_task.description

    def test_workflow_parallel_research_openai(self) -> None:
        """Test WorkflowBuilder matches workflow-parallel-research-openai.yaml (diamond DAG)."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/workflow-parallel-research-openai.yaml",
            variables={"topic": "renewable energy"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        workflow_builder = builder.workflow()
        tasks = yaml_spec.pattern.config.tasks or []
        for task in tasks:
            task_data = task.model_dump(by_alias=True, exclude_none=True)
            workflow_builder = workflow_builder.task(
                task_data["id"],
                task_data["agent"],
                input=task_data.get("input"),
                description=task_data.get("description"),
                depends_on=task_data.get("deps"),
                vars=task_data.get("vars"),
                tool_overrides=task_data.get("tool_overrides"),
            )

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected workflow artifacts defined in YAML"
        fluent_builder = workflow_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.tasks is not None
        assert len(api_spec.pattern.config.tasks) == len(tasks)
        for api_task, yaml_task in zip(api_spec.pattern.config.tasks, tasks, strict=True):
            assert api_task.id == yaml_task.id
            assert api_task.agent == yaml_task.agent
            assert api_task.deps == yaml_task.deps


class TestParallelGoldenFiles:
    """Test ParallelBuilder output matches YAML golden files."""

    def test_parallel_simple_2_branches(self) -> None:
        """Test ParallelBuilder matches parallel-simple-2-branches.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/parallel-simple-2-branches.yaml",
            variables={"topic": "artificial intelligence in healthcare"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("parallel-simple-2-branches")
            .description("Simple parallel execution with 2 concurrent research branches")
            .runtime("openai", model="gpt-4o-mini")
            .agent(
                "researcher",
                "You are a research assistant. Provide concise, factual information about the requested topic.\n",
            )
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
            .output_dir("artifacts")
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime.provider == yaml_spec.runtime.provider
        assert api_spec.pattern.type == PatternType.PARALLEL
        assert len(api_spec.pattern.config.branches) == 2
        assert api_spec.pattern.config.branches[0].id == "technical_analysis"
        assert api_spec.pattern.config.branches[1].id == "business_impact"
        assert len(api_spec.pattern.config.branches[0].steps) == 1
        assert len(api_spec.pattern.config.branches[1].steps) == 1

    def test_parallel_with_reduce(self) -> None:
        """Test ParallelBuilder matches parallel-with-reduce.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/parallel-with-reduce.yaml",
            variables={"topic": "blockchain technology"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("parallel-with-reduce")
            .description("Parallel branches with reduce step for synthesis")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "You are a research assistant.")
            .agent("synthesizer", "You synthesize information.")
            .parallel()
            .branch("technical")
            .step("researcher", "Analyze technical aspects of {{ topic }}")
            .done()
            .branch("business")
            .step("researcher", "Analyze business aspects of {{ topic }}")
            .done()
            .branch("social")
            .step("researcher", "Analyze social impact of {{ topic }}")
            .done()
            .reduce(
                "synthesizer",
                "Synthesize all analyses:\n"
                "Technical: {{ branches.technical.response }}\n"
                "Business: {{ branches.business.response }}\n"
                "Social: {{ branches.social.response }}",
            )
            .artifact("parallel-reduce-{{topic}}.md", "# Synthesis\n{{ last_response }}")
            .output_dir("artifacts")
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.pattern.type == PatternType.PARALLEL
        assert len(api_spec.pattern.config.branches) == 3
        assert api_spec.pattern.config.reduce is not None
        assert api_spec.pattern.config.reduce.agent == "synthesizer"

    def test_parallel_multi_step_branches(self) -> None:
        """Test ParallelBuilder matches parallel-multi-step-branches.yaml (multi-step per branch)."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/parallel-multi-step-branches.yaml",
            variables={"product": "electric vehicle"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("parallel-multi-step-branches")
            .description("Parallel branches with multiple steps per branch")
            .runtime("openai", model="gpt-4o-mini")
            .agent("researcher", "You research products.")
            .agent("analyst", "You analyze data.")
            .parallel()
            .branch("market_research")
            .step("researcher", "Research market for {{ product }}")
            .step("analyst", "Analyze market data: {{ steps[0].response }}")
            .done()
            .branch("technical_specs")
            .step("researcher", "Research technical specifications of {{ product }}")
            .step("analyst", "Analyze technical feasibility: {{ steps[0].response }}")
            .done()
            .artifact(
                "parallel-analysis-{{product}}.md",
                "# Product Analysis: {{ product }}\n\n"
                "## Market\n{{ branches.market_research.response }}\n\n"
                "## Technical\n{{ branches.technical_specs.response }}",
            )
            .output_dir("artifacts")
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.pattern.type == PatternType.PARALLEL
        assert len(api_spec.pattern.config.branches) == 2
        # Each branch has 2 steps
        assert len(api_spec.pattern.config.branches[0].steps) == 2
        assert len(api_spec.pattern.config.branches[1].steps) == 2


class TestGraphGoldenFiles:
    """Test GraphBuilder output matches YAML golden files."""

    def test_graph_decision_tree_openai(self) -> None:
        """Test GraphBuilder matches graph-decision-tree-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/graph-decision-tree-openai.yaml",
            variables={"query": "What is machine learning?"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        graph_builder = builder.graph()
        nodes = yaml_spec.pattern.config.nodes or {}
        for node_id, node in nodes.items():
            if node.agent is not None:
                graph_builder = graph_builder.node(node_id, node.agent, node.input)
            else:
                graph_builder = graph_builder.hitl_node(
                    node_id,
                    node.prompt or "",
                    show=node.context_display,
                    default=node.default,
                    timeout_seconds=node.timeout_seconds,
                )

        edges = yaml_spec.pattern.config.edges or []
        for edge in edges:
            if edge.choose is not None:
                choices = [(choice.when, choice.to) for choice in edge.choose]
                graph_builder = graph_builder.conditional_edge(edge.from_, choices)
            elif edge.to is not None:
                graph_builder = graph_builder.edge(edge.from_, edge.to)

        graph_builder = graph_builder.max_iterations(yaml_spec.pattern.config.max_iterations)

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected graph artifacts defined in YAML"
        fluent_builder = graph_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.nodes is not None
        assert set(api_spec.pattern.config.nodes.keys()) == set(nodes.keys())
        assert api_spec.pattern.config.edges is not None
        assert len(api_spec.pattern.config.edges) == len(edges)
        assert api_spec.pattern.config.max_iterations == yaml_spec.pattern.config.max_iterations

    def test_graph_state_machine_openai(self) -> None:
        """Test GraphBuilder matches graph-state-machine-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/graph-state-machine-openai.yaml",
            variables={"task": "process customer order"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        graph_builder = builder.graph()
        nodes = yaml_spec.pattern.config.nodes or {}
        for node_id, node in nodes.items():
            if node.agent is not None:
                graph_builder = graph_builder.node(node_id, node.agent, node.input)
            else:
                graph_builder = graph_builder.hitl_node(
                    node_id,
                    node.prompt or "",
                    show=node.context_display,
                    default=node.default,
                    timeout_seconds=node.timeout_seconds,
                )

        edges = yaml_spec.pattern.config.edges or []
        for edge in edges:
            if edge.choose is not None:
                choices = [(choice.when, choice.to) for choice in edge.choose]
                graph_builder = graph_builder.conditional_edge(edge.from_, choices)
            elif edge.to is not None:
                graph_builder = graph_builder.edge(edge.from_, edge.to)

        graph_builder = graph_builder.max_iterations(yaml_spec.pattern.config.max_iterations)

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected graph artifacts defined in YAML"
        fluent_builder = graph_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.nodes is not None
        assert set(api_spec.pattern.config.nodes.keys()) == set(nodes.keys())
        assert api_spec.pattern.config.edges is not None
        assert len(api_spec.pattern.config.edges) == len(edges)
        assert api_spec.pattern.config.max_iterations == yaml_spec.pattern.config.max_iterations


class TestRoutingGoldenFiles:
    """Test RoutingBuilder output matches YAML golden files."""

    def test_routing_task_classification_openai(self) -> None:
        """Test RoutingBuilder matches routing-task-classification-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/routing-task-classification-openai.yaml",
            variables={"query": "Explain neural networks"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        routing_builder = builder.routing()
        router_config = yaml_spec.pattern.config.router
        routing_builder = routing_builder.router(
            router_config.agent,
            router_config.input,
            max_retries=router_config.max_retries,
        )

        routes = yaml_spec.pattern.config.routes or {}
        for route_id, route in routes.items():
            route_builder = routing_builder.route(route_id)
            for step in route.then or []:
                route_builder = route_builder.step(
                    step.agent,
                    step.input,
                    vars=step.vars,
                    tool_overrides=step.tool_overrides,
                )
            routing_builder = route_builder.done()

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected routing artifacts defined in YAML"
        fluent_builder = routing_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.router == yaml_spec.pattern.config.router
        assert api_spec.pattern.config.routes is not None
        assert set(api_spec.pattern.config.routes.keys()) == set(routes.keys())

    def test_routing_customer_support_openai(self) -> None:
        """Test RoutingBuilder matches routing-customer-support-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/routing-customer-support-openai.yaml",
            variables={"customer_query": "How do I reset my password?"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        routing_builder = builder.routing()
        router_config = yaml_spec.pattern.config.router
        routing_builder = routing_builder.router(
            router_config.agent,
            router_config.input,
            max_retries=router_config.max_retries,
        )

        routes = yaml_spec.pattern.config.routes or {}
        for route_id, route in routes.items():
            route_builder = routing_builder.route(route_id)
            for step in route.then or []:
                route_builder = route_builder.step(
                    step.agent,
                    step.input,
                    vars=step.vars,
                    tool_overrides=step.tool_overrides,
                )
            routing_builder = route_builder.done()

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected routing artifacts defined in YAML"
        fluent_builder = routing_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == yaml_spec.pattern.type
        assert api_spec.pattern.config.routes is not None
        assert set(api_spec.pattern.config.routes.keys()) == set(routes.keys())


class TestEvaluatorOptimizerGoldenFiles:
    """Test EvaluatorOptimizerBuilder output matches YAML golden files."""

    def test_evaluator_optimizer_writing_openai(self) -> None:
        """Test EvaluatorOptimizerBuilder matches evaluator-optimizer-writing-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/evaluator-optimizer-writing-openai.yaml",
            variables={"topic": "renewable energy", "min_score": 8},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        pattern_config = yaml_spec.pattern.config
        evaluator_cfg = pattern_config.evaluator
        accept_cfg = pattern_config.accept
        assert evaluator_cfg is not None, "Evaluator configuration missing from YAML"
        assert accept_cfg is not None, "Acceptance configuration missing from YAML"
        assert pattern_config.revise_prompt is not None, "Revise prompt required in YAML spec"

        eo_builder = builder.evaluator_optimizer()
        eo_builder = eo_builder.producer(pattern_config.producer)
        eo_builder = eo_builder.evaluator(evaluator_cfg.agent, evaluator_cfg.input)
        eo_builder = eo_builder.accept(
            min_score=accept_cfg.min_score,
            max_iterations=accept_cfg.max_iters,
        )
        eo_builder = eo_builder.revise_prompt(pattern_config.revise_prompt)

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected evaluator-optimizer artifacts defined in YAML"
        fluent_builder = eo_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.pattern.type == PatternType.EVALUATOR_OPTIMIZER
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.config.producer == pattern_config.producer
        assert api_spec.pattern.config.evaluator == evaluator_cfg
        assert api_spec.pattern.config.accept == accept_cfg
        assert api_spec.pattern.config.revise_prompt == pattern_config.revise_prompt

    def test_evaluator_optimizer_code_review_openai(self) -> None:
        """Test EvaluatorOptimizerBuilder matches evaluator-optimizer-code-review-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/evaluator-optimizer-code-review-openai.yaml",
            variables={"language": "Python", "task": "quicksort algorithm"},
        )

        # Build equivalent via API
        api_workflow = (
            FluentBuilder("evaluator-optimizer-code-review-openai")
            .description("Code generation with iterative review")
            .runtime("openai", model="gpt-4o-mini", temperature=0.3)
            .agent("coder", "You write clean, efficient code.", tools=["python"])
            .agent(
                "reviewer",
                "You review code for correctness, efficiency, style.\n"
                "Return JSON: {\"score\": <0-10>, \"issues\": [\"<issue1>\", ...]}",
            )
            .evaluator_optimizer()
            .producer("coder", "Write {{language}} code for: {{task}}")
            .evaluator("reviewer", "Review this code:\n{{ current_response }}")
            .accept(min_score=9, max_iterations=5)
            .revise_prompt(
                "Fix these issues:\n{{ evaluation_response.issues }}\n\n"
                "Current code:\n{{ current_response }}"
            )
            .artifact("code-{{language}}-{{task}}.py", "{{ last_response }}")
            .output_dir("artifacts")
            .build()
        )

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.pattern.type == PatternType.EVALUATOR_OPTIMIZER
        assert api_spec.pattern.config.accept.min_score == 9
        assert api_spec.pattern.config.accept.max_iters == 5
        assert api_spec.runtime.temperature == 0.3


class TestOrchestratorWorkersGoldenFiles:
    """Test OrchestratorWorkersBuilder output matches YAML golden files."""

    def test_orchestrator_minimal_openai(self) -> None:
        """Test OrchestratorWorkersBuilder matches orchestrator-minimal-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/orchestrator-minimal-openai.yaml",
            variables={"task": "analyze quarterly sales data"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        pattern_config = yaml_spec.pattern.config
        orchestrator_cfg = pattern_config.orchestrator
        worker_template = pattern_config.worker_template
        assert orchestrator_cfg is not None, "Orchestrator configuration missing from YAML"
        assert worker_template is not None, "Worker template missing from YAML"

        ow_builder = builder.orchestrator_workers()
        limits = orchestrator_cfg.limits
        ow_builder = ow_builder.orchestrator(
            orchestrator_cfg.agent,
            min_workers=limits.min_workers if limits else None,
            max_workers=limits.max_workers if limits else None,
            max_rounds=limits.max_rounds if limits else None,
        )
        ow_builder = ow_builder.worker_template(worker_template.agent, tools=worker_template.tools)

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected orchestrator artifacts defined in YAML"
        fluent_builder = ow_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == PatternType.ORCHESTRATOR_WORKERS
        assert api_spec.pattern.config.orchestrator == orchestrator_cfg
        assert api_spec.pattern.config.worker_template == worker_template

    def test_orchestrator_data_processing_openai(self) -> None:
        """Test OrchestratorWorkersBuilder matches orchestrator-data-processing-openai.yaml."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/orchestrator-data-processing-openai.yaml",
            variables={"dataset": "customer feedback"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        pattern_config = yaml_spec.pattern.config
        orchestrator_cfg = pattern_config.orchestrator
        worker_template = pattern_config.worker_template
        reduce_step_cfg = pattern_config.writeup or pattern_config.reduce
        assert orchestrator_cfg is not None, "Orchestrator configuration missing from YAML"
        assert worker_template is not None, "Worker template missing from YAML"
        assert reduce_step_cfg is not None, "Reduce step missing from YAML"

        ow_builder = builder.orchestrator_workers()
        limits = orchestrator_cfg.limits
        ow_builder = ow_builder.orchestrator(
            orchestrator_cfg.agent,
            min_workers=limits.min_workers if limits else None,
            max_workers=limits.max_workers if limits else None,
            max_rounds=limits.max_rounds if limits else None,
        )
        ow_builder = ow_builder.worker_template(
            worker_template.agent,
            tools=worker_template.tools,
        )

        if pattern_config.decomposition_review is not None:
            review = pattern_config.decomposition_review
            ow_builder = ow_builder.decomposition_review(
                review.prompt,
                show=review.context_display,
                default=review.default,
                timeout_seconds=review.timeout_seconds,
            )

        if pattern_config.reduce_review is not None:
            review = pattern_config.reduce_review
            ow_builder = ow_builder.reduce_review(
                review.prompt,
                show=review.context_display,
                default=review.default,
                timeout_seconds=review.timeout_seconds,
            )

        reduce_data = reduce_step_cfg.model_dump(by_alias=True, exclude_none=True)
        ow_builder = ow_builder.reduce_step(
            reduce_data["agent"],
            input=reduce_data.get("input"),
            vars=reduce_data.get("vars"),
            tool_overrides=reduce_data.get("tool_overrides"),
        )

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected orchestrator artifacts defined in YAML"
        fluent_builder = ow_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == PatternType.ORCHESTRATOR_WORKERS
        assert api_spec.pattern.config.orchestrator == orchestrator_cfg
        assert api_spec.pattern.config.worker_template == worker_template
        expected_reduce = pattern_config.writeup or pattern_config.reduce
        assert api_spec.pattern.config.writeup == expected_reduce


class TestMixedPatternsGoldenFiles:
    """Test builder combinations and edge cases."""

    def test_chain_with_hitl(self) -> None:
        """Test ChainBuilder with HITL steps matches YAML."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/chain-hitl-approval-demo.yaml",
            variables={"project": "web application"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        chain_builder = builder.chain()
        steps = yaml_spec.pattern.config.steps or []
        for step in steps:
            if step.agent is not None:
                chain_builder = chain_builder.step(
                    step.agent,
                    step.input,
                    vars=step.vars,
                    tool_overrides=step.tool_overrides,
                )
            else:
                chain_builder = chain_builder.hitl(
                    step.prompt or "",
                    context_display=step.context_display,
                    default=step.default,
                    timeout_seconds=step.timeout_seconds,
                )

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected chain artifacts defined in YAML"
        fluent_builder = chain_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == PatternType.CHAIN
        assert len(api_spec.pattern.config.steps) == len(steps)
        assert api_spec.pattern.config.steps[1].type == "hitl"

    def test_workflow_with_hitl_task(self) -> None:
        """Test WorkflowBuilder with HITL tasks matches YAML."""
        # Load YAML golden file
        yaml_spec = load_spec(
            "examples/workflow-hitl-approval-demo.yaml",
            variables={"feature": "user authentication"},
        )

        # Build equivalent via API
        runtime = yaml_spec.runtime
        builder = (
            FluentBuilder(yaml_spec.name)
            .description(yaml_spec.description)
            .runtime(runtime.provider.value, **_runtime_kwargs(runtime))
        )
        builder = _register_agents(builder, yaml_spec.agents)

        workflow_builder = builder.workflow()
        tasks = yaml_spec.pattern.config.tasks or []
        for task in tasks:
            task_dict = task.model_dump(by_alias=True, exclude_none=True)
            if task_dict.get("type") == "hitl":
                workflow_builder = workflow_builder.hitl_task(
                    task_dict["id"],
                    task_dict["prompt"],
                    show=task_dict.get("context_display"),
                    default=task_dict.get("default"),
                    timeout_seconds=task_dict.get("timeout_seconds"),
                    depends_on=task_dict.get("deps"),
                )
            else:
                workflow_builder = workflow_builder.task(
                    task_dict["id"],
                    task_dict["agent"],
                    input=task_dict.get("input"),
                    description=task_dict.get("description"),
                    depends_on=task_dict.get("deps"),
                    vars=task_dict.get("vars"),
                    tool_overrides=task_dict.get("tool_overrides"),
                )

        artifacts = yaml_spec.outputs.artifacts or []
        assert artifacts, "Expected workflow artifacts defined in YAML"
        fluent_builder = workflow_builder
        for artifact in artifacts:
            fluent_builder = fluent_builder.artifact(artifact.path, artifact.from_)

        api_workflow = fluent_builder.output_dir("artifacts").build()

        # Compare specs structurally
        api_spec = api_workflow.spec
        assert api_spec.name == yaml_spec.name
        assert api_spec.description == yaml_spec.description
        assert api_spec.runtime == yaml_spec.runtime
        assert api_spec.pattern.type == PatternType.WORKFLOW
        assert api_spec.pattern.config.tasks == tasks

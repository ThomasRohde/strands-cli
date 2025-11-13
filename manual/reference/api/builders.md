# Builder API Reference

Complete API documentation for the **Strands fluent builder API**, which enables programmatic workflow construction without YAML.

## Overview

The builder API provides type-safe, fail-fast workflow construction for all 7 workflow patterns. Builders validate configuration at build time, catching errors early with actionable messages.

**Key Features:**

- ✅ **Type-safe** - Full IDE autocomplete and type hints
- ✅ **Fail-fast** - Validation at `.build()` with clear error messages
- ✅ **Explicit** - No implicit agent creation or runtime defaults
- ✅ **Fluent** - Method chaining for readable code
- ✅ **Pattern-specific** - Dedicated builders for each workflow pattern

## Quick Reference

```python
from strands_cli.api import FluentBuilder

# Create workflow
workflow = (
    FluentBuilder("workflow-name")
    .runtime("openai", model="gpt-4o-mini")
    .agent("agent-id", "System prompt")
    .chain()  # or .workflow(), .parallel(), .graph(), etc.
    .step("agent-id", "Input template")
    .artifact("output.md", "{{ last_response }}")
    .build()
)

# Execute
result = workflow.run_interactive(var1="value1")
```

## FluentBuilder

**Base builder for all workflow patterns.**

### Constructor

```python
FluentBuilder(name: str, description: str | None = None)
```

**Parameters:**

- `name` (str, required) - Workflow name (used in logs, artifacts, session IDs)
- `description` (str, optional) - Human-readable workflow description

**Returns:** `FluentBuilder` instance

**Example:**

```python
builder = FluentBuilder("data-pipeline", "ETL workflow for customer data")
```

---

### Core Methods

#### `.runtime()`

Configure LLM provider and execution parameters.

```python
.runtime(
    provider: str,
    model: str | None = None,
    region: str | None = None,
    host: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    max_parallel: int | None = None,
    **kwargs: Any
) -> FluentBuilder
```

**Parameters:**

- `provider` (str, **required**) - Model provider: `"bedrock"`, `"ollama"`, or `"openai"`
- `model` (str, optional) - Model ID (provider-specific)
  - Bedrock: `"anthropic.claude-3-sonnet-20240229-v1:0"`
  - OpenAI: `"gpt-4o-mini"`, `"gpt-4o"`, `"o1-mini"`
  - Ollama: `"llama3.2"`, `"mistral"`
- `region` (str, optional) - AWS region (required for Bedrock)
- `host` (str, optional) - Ollama host URL (default: `http://localhost:11434`)
- `temperature` (float, optional) - Sampling temperature (0.0-1.0)
- `top_p` (float, optional) - Nucleus sampling (0.0-1.0)
- `max_tokens` (int, optional) - Maximum tokens to generate
- `max_parallel` (int, optional) - Maximum concurrent tasks/workers
- `**kwargs` - Additional provider-specific parameters (budgets, retries, etc.)

**Returns:** `self` for chaining

**Raises:** `BuildError` if provider is invalid

**Examples:**

```python
# OpenAI
.runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=8000)

# Bedrock with region
.runtime("bedrock", 
         model="anthropic.claude-3-sonnet-20240229-v1:0",
         region="us-east-1",
         temperature=0.8)

# Ollama with custom host
.runtime("ollama", model="llama3.2", host="http://192.168.1.100:11434")

# With budgets
.runtime("openai",
         model="gpt-4o-mini",
         budgets={
             "token_budget": {
                 "max_input_tokens": 100000,
                 "max_output_tokens": 20000
             }
         })
```

---

#### `.agent()`

Define an agent for use in workflow steps.

```python
.agent(
    id: str,
    prompt: str,
    tools: list[str] | None = None,
    model_id: str | None = None,
    **kwargs: Any
) -> FluentBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique agent identifier (used in step references)
- `prompt` (str, **required**) - System prompt for the agent
- `tools` (list[str], optional) - Tool IDs to enable: `["python", "http_get", ...]`
- `model_id` (str, optional) - Model override for this agent
- `**kwargs` - Additional agent configuration (temperature, max_tokens, etc.)

**Returns:** `self` for chaining

**Raises:** `BuildError` if agent ID already exists

**Examples:**

```python
# Basic agent
.agent("researcher", "You are a thorough research assistant. Be factual.")

# Agent with tools
.agent("developer", 
       "You are a Python developer",
       tools=["python", "http_get"])

# Agent with model override
.agent("creative_writer",
       "You are a creative storyteller",
       model_id="gpt-4o",  # Override runtime model
       temperature=0.9)
```

---

#### `.artifact()`

Define output artifact with content template. **Requires `.output_dir()` to be set first.**

```python
.artifact(path: str, template: str) -> FluentBuilder
```

**Parameters:**

- `path` (str, **required**) - Output file path (supports Jinja2 templates)
- `template` (str, **required**) - Content template (Jinja2 syntax)

**Returns:** `self` for chaining

**Raises:** 
- `BuildError` if template syntax is invalid
- `BuildError` at build time if `.output_dir()` not called

**Prerequisites:**
- **Must call `.output_dir()` before using `.artifact()`**

**Template Variables:**

- `{{ last_response }}` - Final agent response
- `{{ steps[n].response }}` - Chain step N response
- `{{ tasks.<id>.response }}` - Workflow task response
- `{{ branches.<id>.response }}` - Parallel branch response
- `{{ nodes.<id>.response }}` - Graph node response
- `{{ workers[n] }}` - Orchestrator worker N result
- Any input variables passed to `.run_interactive()`

**Examples:**

```python
# Simple artifact
.artifact("report.md", "# Report\n\n{{ last_response }}")

# Path with variables
.artifact("{{topic}}-analysis.md", 
          "# Analysis: {{topic}}\n\n{{ last_response }}")

# Multi-step chain results
.artifact("research-summary.md",
          """# Research Summary
          
          ## Initial Research
          {{ steps[0].response }}
          
          ## Analysis
          {{ steps[1].response }}
          
          ## Conclusion
          {{ last_response }}
          """)

# JSON output
.artifact("result.json",
          '{"topic": "{{topic}}", "result": {{ last_response | tojson }}}')
```

---

#### `.description()`

Set workflow description.

```python
.description(description: str) -> FluentBuilder
```

**Parameters:**

- `description` (str, **required**) - Human-readable description

**Returns:** `self` for chaining

**Example:**

```python
.description("Three-step research workflow with iterative refinement")
```

---

#### `.output_dir()`

**Required when using artifacts.** Configure the directory where artifact files will be written.

```python
.output_dir(path: str) -> FluentBuilder
```

**Parameters:**

- `path` (str, **required**) - Output directory path (relative or absolute)

**Returns:** `self` for chaining

**Raises:** 
- `BuildError` if called more than once
- `BuildError` at build time if artifacts defined without output_dir

**Examples:**

```python
# Relative path (created if doesn't exist)
.output_dir("./artifacts")

# Absolute path
.output_dir("/tmp/workflow-outputs")

# User home directory
.output_dir("~/workflows/outputs")
```

**Important:**
- Must be called **before** `.artifact()` calls
- Can only be called **once** per workflow
- Directory is created automatically if it doesn't exist
- Path is resolved relative to current working directory

**Error scenarios:**

```python
# ❌ Multiple calls raise BuildError
.output_dir("./artifacts")
.output_dir("./outputs")  # BuildError: output_dir already set

# ❌ Artifact without output_dir raises BuildError at build()
.artifact("report.md", "...")  # BuildError: output_dir required

# ✅ Correct usage
.output_dir("./artifacts")
.artifact("report.md", "...")
.artifact("summary.json", "...")
```

---

#### `.force_overwrite()`

Control whether to overwrite existing artifact files. **Default is True (overwrite enabled).**

```python
.force_overwrite(enabled: bool = True) -> FluentBuilder
```

**Parameters:**

- `enabled` (bool, optional) - Whether to overwrite existing files (default: `True`)

**Returns:** `self` for chaining

**Examples:**

```python
# Default behavior: overwrite existing files
.output_dir("./artifacts")
.artifact("report.md", "{{ last_response }}")
# If report.md exists, it will be overwritten

# Prevent overwriting (raises error if file exists)
.output_dir("./artifacts")
.force_overwrite(False)
.artifact("report.md", "{{ last_response }}")
# If report.md exists, workflow execution fails with error

# Explicitly enable overwriting (same as default)
.output_dir("./artifacts")
.force_overwrite(True)
.artifact("report.md", "{{ last_response }}")
```

**When to use `force_overwrite(False)`:**
- Prevent accidental data loss
- Ensure unique outputs (add timestamps to filenames)
- Multi-run environments where each run should produce unique files

**Note:** Overwrite checking happens at **execution time**, not build time.

---

### Pattern Selection Methods

Each method returns a pattern-specific builder with its own methods.

#### `.single_agent()`

**Not yet implemented** - Use `.chain()` with one step as workaround.

---

#### `.chain()`

Start building a sequential chain pattern.

```python
.chain() -> ChainBuilder
```

**Returns:** `ChainBuilder` instance

**Example:**

```python
.chain()
.step("agent1", "Step 1")
.step("agent2", "Step 2: {{ steps[0].response }}")
```

See [ChainBuilder](#chainbuilder) for available methods.

---

#### `.workflow()`

Start building a DAG-based workflow pattern.

```python
.workflow() -> WorkflowBuilder
```

**Returns:** `WorkflowBuilder` instance

**Example:**

```python
.workflow()
.task("task1", "agent1", "Task 1")
.task("task2", "agent2", "Task 2", depends_on=["task1"])
```

See [WorkflowBuilder](#workflowbuilder) for available methods.

---

#### `.parallel()`

Start building a parallel execution pattern.

```python
.parallel() -> ParallelBuilder
```

**Returns:** `ParallelBuilder` instance

**Example:**

```python
.parallel()
.branch("branch1").step("agent1", "Branch 1").done()
.branch("branch2").step("agent2", "Branch 2").done()
.reduce("synthesizer", "Combine: {{ branches | tojson }}")
```

See [ParallelBuilder](#parallelbuilder) for available methods.

---

#### `.graph()`

Start building a state machine (graph) pattern.

```python
.graph() -> GraphBuilder
```

**Returns:** `GraphBuilder` instance

**Example:**

```python
.graph()
.node("start", "agent1", "Start")
.node("process", "agent2", "Process")
.edge("start", "process")
```

See [GraphBuilder](#graphbuilder) for available methods.

---

#### `.routing()`

Start building a dynamic routing pattern.

```python
.routing() -> RoutingBuilder
```

**Returns:** `RoutingBuilder` instance

**Example:**

```python
.routing()
.router("classifier", "Classify: {{input}}")
.route("route1").step("handler1", "Handle 1").done()
.route("route2").step("handler2", "Handle 2").done()
```

See [RoutingBuilder](#routingbuilder) for available methods.

---

#### `.evaluator_optimizer()`

Start building an iterative refinement pattern.

```python
.evaluator_optimizer() -> EvaluatorOptimizerBuilder
```

**Returns:** `EvaluatorOptimizerBuilder` instance

**Example:**

```python
.evaluator_optimizer()
.producer("writer", "Write: {{topic}}")
.evaluator("critic", "Rate (0-10): {{ iteration.response }}")
.accept(min_score=8, max_iterations=3)
```

See [EvaluatorOptimizerBuilder](#evaluatoroptimizerbuilder) for available methods.

---

#### `.orchestrator_workers()`

Start building a task decomposition pattern.

```python
.orchestrator_workers() -> OrchestratorWorkersBuilder
```

**Returns:** `OrchestratorWorkersBuilder` instance

**Example:**

```python
.orchestrator_workers()
.orchestrator("planner", "Plan: {{project}}")
.worker_template("executor", tools=["python"])
.reduce_step("synthesizer", "Combine: {{ workers }}")
```

See [OrchestratorWorkersBuilder](#orchestratorworkersbuilder) for available methods.

---

#### `.build()`

Build and validate the complete workflow.

```python
.build() -> Workflow
```

**Returns:** `Workflow` instance ready to execute

**Raises:** `BuildError` with actionable message if validation fails

**Validation checks:**

- ✅ Runtime is configured
- ✅ At least one agent defined
- ✅ Pattern is selected and configured
- ✅ All referenced agents exist
- ✅ All templates have valid syntax
- ✅ No circular dependencies (workflow pattern)
- ✅ All task/node/branch IDs are unique

**Example:**

```python
try:
    workflow = builder.build()
except BuildError as e:
    print(f"Build failed: {e}")
    # Fix errors and retry
```

---

## ChainBuilder

**Sequential step execution with context passing.**

### Methods

#### `.step()`

Add an agent execution step.

```python
.step(
    agent: str,
    input: str | None = None,
    vars: dict[str, str | int | bool] | None = None,
    tool_overrides: list[str] | None = None
) -> ChainBuilder
```

**Parameters:**

- `agent` (str, **required**) - Agent ID (must be defined via `.agent()`)
- `input` (str, optional) - Input template (Jinja2)
- `vars` (dict, optional) - Per-step variable overrides
- `tool_overrides` (list[str], optional) - Override agent's tools for this step

**Returns:** `self` for chaining

**Raises:** `BuildError` if agent doesn't exist or template is invalid

**Examples:**

```python
# Basic step
.step("researcher", "Research: {{topic}}")

# Reference previous step
.step("analyst", "Analyze this: {{ steps[0].response }}")

# With variables
.step("writer", "Write at {{depth}} depth", vars={"depth": "detailed"})

# Tool override
.step("developer", "Write code", tool_overrides=["python"])
```

---

#### `.hitl()`

Add a human-in-the-loop pause point.

```python
.hitl(
    prompt: str,
    show: str | None = None,
    default: str | None = None
) -> ChainBuilder
```

**Parameters:**

- `prompt` (str, **required**) - HITL prompt text shown to user
- `show` (str, optional) - Context to display (template)
- `default` (str, optional) - Default response value

**Returns:** `self` for chaining

**Examples:**

```python
# Simple approval gate
.hitl("Approve the research above to continue?")

# With context display
.hitl("Review and approve:",
      show="{{ steps[0].response }}",
      default="approved")

# Review intermediate results
.chain()
.step("researcher", "Research {{topic}}")
.hitl("Review research. Type 'continue' to proceed.",
      show="## Research Results\n{{ steps[0].response }}")
.step("writer", "Write article based on: {{ steps[0].response }}")
```

---

#### `.build()`

Complete chain configuration and return to parent.

```python
.build() -> Workflow
```

Delegates to `FluentBuilder.build()` for final validation.

---

## WorkflowBuilder

**DAG-based task execution with dependency tracking.**

### Methods

#### `.task()`

Add a task to the workflow DAG.

```python
.task(
    id: str,
    agent: str,
    input: str | None = None,
    depends_on: list[str] | None = None,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> WorkflowBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique task identifier
- `agent` (str, **required**) - Agent ID
- `input` (str, optional) - Input template
- `depends_on` (list[str], optional) - Task IDs this task depends on
- `vars` (dict, optional) - Per-task variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Raises:** 
- `BuildError` if agent doesn't exist
- `BuildError` if task ID is duplicate
- `BuildError` if circular dependency detected
- `BuildError` if dependency task doesn't exist

**Examples:**

```python
# Independent tasks (run in parallel)
.task("gather_sources", "researcher", "Gather sources on {{topic}}")
.task("gather_data", "analyst", "Gather data on {{topic}}")

# Dependent task (waits for both)
.task("synthesize", "writer",
      """Sources: {{ tasks.gather_sources.response }}
      Data: {{ tasks.gather_data.response }}""",
      depends_on=["gather_sources", "gather_data"])
```

---

#### `.hitl_task()`

Add a HITL pause point as a task.

```python
.hitl_task(
    id: str,
    prompt: str,
    show: str | None = None,
    default: str | None = None,
    depends_on: list[str] | None = None
) -> WorkflowBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique task ID
- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template
- `default` (str, optional) - Default response
- `depends_on` (list[str], optional) - Dependency tasks

**Returns:** `self` for chaining

**Example:**

```python
.workflow()
.task("draft", "writer", "Draft article on {{topic}}")
.hitl_task("approval", 
           "Approve the draft?",
           show="{{ tasks.draft.response }}",
           depends_on=["draft"])
.task("publish", "publisher", "Publish approved content",
      depends_on=["approval"])
```

---

#### `.build()`

Complete workflow configuration.

```python
.build() -> Workflow
```

Validates DAG for cycles using topological sort.

---

## ParallelBuilder

**Concurrent branch execution with optional reduce step.**

### Methods

#### `.branch()`

Start defining a parallel branch.

```python
.branch(id: str) -> _BranchBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique branch identifier

**Returns:** `_BranchBuilder` for adding steps to branch

**Example:**

```python
.parallel()
.branch("technical")  # Returns _BranchBuilder
    .step("tech_writer", "Write technical overview")
    .done()  # Return to ParallelBuilder
.branch("business")
    .step("biz_writer", "Write business case")
    .done()
```

---

#### `.reduce()`

Add optional reduce step to synthesize branch results.

```python
.reduce(
    agent: str,
    input: str,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> ParallelBuilder
```

**Parameters:**

- `agent` (str, **required**) - Agent ID
- `input` (str, **required**) - Input template (can reference `{{ branches.<id>.response }}`)
- `vars` (dict, optional) - Variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Example:**

```python
.reduce("synthesizer",
        """Technical: {{ branches.technical.response }}
        Business: {{ branches.business.response }}
        
        Combine these perspectives into a unified recommendation.""")
```

---

#### `.hitl_in_branch()`

Add HITL to specific branch (called on `_BranchBuilder`).

```python
# Inside branch
.branch("review")
    .step("reviewer", "Review {{topic}}")
    .hitl_in_branch("Approve review?")
    .step("finalizer", "Finalize")
    .done()
```

---

#### `.hitl_in_reduce()`

**⚠️ NOT YET IMPLEMENTED** - Raises `BuildError`.

```python
# This method is documented but not yet implemented
.hitl_in_reduce("Review all branch results before synthesis",
                show="{{ branches | tojson }}")
.reduce("synthesizer", "Combine: {{ branches }}")
```

**Note:** This feature is planned for a future release. Currently raises `BuildError` with message "hitl_in_reduce not yet implemented".

---

#### `.build()`

Complete parallel configuration.

```python
.build() -> Workflow
```

---

## GraphBuilder

**State machine with conditional transitions.**

### Methods

#### `.node()`

Add a node (state) to the graph.

```python
.node(
    id: str,
    agent: str,
    input: str | None = None,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> GraphBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique node ID
- `agent` (str, **required**) - Agent ID
- `input` (str, optional) - Input template
- `vars` (dict, optional) - Variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Example:**

```python
.node("classify", "classifier", "Classify: {{input}}")
.node("process_urgent", "urgent_handler", "Handle urgent")
.node("process_normal", "normal_handler", "Handle normal")
```

---

#### `.hitl_node()`

Add a HITL pause node.

```python
.hitl_node(
    id: str,
    prompt: str,
    show: str | None = None,
    default: str | None = None
) -> GraphBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique node ID
- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template
- `default` (str, optional) - Default response

**Returns:** `self` for chaining

**Example:**

```python
.node("draft", "writer", "Draft proposal")
.hitl_node("approval", "Approve draft?", show="{{ nodes.draft.response }}")
.node("publish", "publisher", "Publish")
```

---

#### `.edge()`

Add unconditional edge between nodes.

```python
.edge(from_node: str, to_node: str) -> GraphBuilder
```

**Parameters:**

- `from_node` (str, **required**) - Source node ID
- `to_node` (str, **required**) - Target node ID

**Returns:** `self` for chaining

**Raises:** `BuildError` if nodes don't exist

**Example:**

```python
.edge("start", "process")
.edge("process", "end")
```

---

#### `.conditional_edge()`

Add conditional edge with multiple choices.

```python
.conditional_edge(
    from_node: str,
    choices: list[tuple[str, str]]
) -> GraphBuilder
```

**Parameters:**

- `from_node` (str, **required**) - Source node ID
- `choices` (list[tuple[str, str]], **required**) - List of (condition, target) tuples
  - condition: Expression like `"type == 'tech'"` or `"else"` (catch-all)
  - target: Target node ID

**Returns:** `self` for chaining

**Example:**

```python
.conditional_edge("classify", [
    ("{{ 'urgent' in nodes.classify.response | lower }}", "urgent"),
    ("{{ 'normal' in nodes.classify.response | lower }}", "normal"),
    ("else", "default")  # Fallback
])
```

---

#### `.build()`

Complete graph configuration.

```python
.build() -> Workflow
```

Validates all edge references.

---

## RoutingBuilder

**Dynamic agent selection based on classifier.**

### Methods

#### `.router()`

Configure the routing classifier agent.

```python
.router(
    agent: str,
    input: str,
    vars: dict[str, Any] | None = None
) -> RoutingBuilder
```

**Parameters:**

- `agent` (str, **required**) - Classifier agent ID
- `input` (str, **required**) - Classification prompt template
- `vars` (dict, optional) - Variables

**Returns:** `self` for chaining

**Example:**

```python
.router("classifier", "Classify this query: {{query}}")
```

---

#### `.review_router()`

Add HITL review after router classification.

```python
.review_router(
    prompt: str,
    show: str | None = None
) -> RoutingBuilder
```

**Parameters:**

- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template

**Returns:** `self` for chaining

**Example:**

```python
.review_router("Review classification before routing",
               show="{{ router.response }}")
```

---

#### `.route()`

Define a route (execution path).

```python
.route(id: str) -> _RouteBuilder
```

**Parameters:**

- `id` (str, **required**) - Unique route ID

**Returns:** `_RouteBuilder` for adding steps to route

**Example:**

```python
.route("technical")
    .step("tech_expert", "Answer technical: {{query}}")
    .done()
.route("business")
    .step("biz_expert", "Answer business: {{query}}")
    .done()
```

---

#### `.build()`

Complete routing configuration.

```python
.build() -> Workflow
```

---

## EvaluatorOptimizerBuilder

**Iterative refinement with feedback loop.**

### Methods

#### `.producer()`

Configure the producer agent (generates initial output).

```python
.producer(
    agent: str,
    input: str | None = None,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> EvaluatorOptimizerBuilder
```

**Parameters:**

- `agent` (str, **required**) - Producer agent ID
- `input` (str, optional) - Initial prompt template
- `vars` (dict, optional) - Variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Example:**

```python
.producer("writer", "Write an essay on: {{topic}}")
```

---

#### `.evaluator()`

Configure the evaluator agent (scores output).

```python
.evaluator(
    agent: str,
    input: str,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> EvaluatorOptimizerBuilder
```

**Parameters:**

- `agent` (str, **required**) - Evaluator agent ID
- `input` (str, **required**) - Evaluation prompt (references `{{ iteration.response }}`)
- `vars` (dict, optional) - Variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Example:**

```python
.evaluator("critic",
           "Rate this essay (0-10) and explain: {{ iteration.response }}")
```

---

#### `.accept()`

Configure acceptance criteria (when to stop iterating).

```python
.accept(
    min_score: int | float,
    max_iterations: int
) -> EvaluatorOptimizerBuilder
```

**Parameters:**

- `min_score` (int | float, **required**) - Minimum score to accept (0-10)
- `max_iterations` (int, **required**) - Maximum iterations before giving up

**Returns:** `self` for chaining

**Example:**

```python
.accept(min_score=8, max_iterations=5)
```

---

#### `.revise_prompt()`

Configure the revision prompt (how to improve based on feedback).

```python
.revise_prompt(template: str) -> EvaluatorOptimizerBuilder
```

**Parameters:**

- `template` (str, **required**) - Revision prompt template

**Template variables:**

- `{{ iteration.response }}` - Current output
- `{{ iteration.score }}` - Evaluator score
- `{{ iteration.evaluation }}` - Evaluator feedback
- `{{ iteration.number }}` - Current iteration number

**Returns:** `self` for chaining

**Example:**

```python
.revise_prompt(
    """Original output: {{ iteration.response }}
    
    Score: {{ iteration.score }}/10
    Feedback: {{ iteration.evaluation }}
    
    Improve the output to address the feedback above."""
)
```

---

#### `.review_gate()`

Add HITL review between iterations.

```python
.review_gate(
    prompt: str,
    show: str | None = None
) -> EvaluatorOptimizerBuilder
```

**Parameters:**

- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template

**Returns:** `self` for chaining

**Example:**

```python
.review_gate("Review iteration {{ iteration.number }} before continuing",
             show="{{ iteration.response }}")
```

---

#### `.build()`

Complete evaluator-optimizer configuration.

```python
.build() -> Workflow
```

---

## OrchestratorWorkersBuilder

**Task decomposition with parallel worker execution.**

### Methods

#### `.orchestrator()`

Configure the orchestrator agent (decomposes task into subtasks).

```python
.orchestrator(
    agent: str,
    input: str | None = None,
    min_workers: int | None = None,
    max_workers: int | None = None,
    max_rounds: int | None = None
) -> OrchestratorWorkersBuilder
```

**Parameters:**

- `agent` (str, **required**) - Orchestrator agent ID
- `input` (str, optional) - Decomposition prompt
- `min_workers` (int, optional) - Minimum concurrent workers
- `max_workers` (int, optional) - Maximum concurrent workers
- `max_rounds` (int, optional) - Maximum orchestration rounds

**Returns:** `self` for chaining

**Example:**

```python
.orchestrator("planner",
              "Break down this project into 3-5 independent tasks: {{project}}",
              min_workers=2,
              max_workers=5,
              max_rounds=3)
```

---

#### `.decomposition_review()`

Add HITL review after task decomposition.

```python
.decomposition_review(
    prompt: str,
    show: str | None = None
) -> OrchestratorWorkersBuilder
```

**Parameters:**

- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template

**Returns:** `self` for chaining

**Example:**

```python
.decomposition_review("Review task breakdown before execution",
                       show="{{ orchestrator.subtasks }}")
```

---

#### `.worker_template()`

Configure worker agent template (executes subtasks).

```python
.worker_template(
    agent: str,
    tools: list[str] | None = None,
    vars: dict[str, Any] | None = None
) -> OrchestratorWorkersBuilder
```

**Parameters:**

- `agent` (str, **required**) - Worker agent ID
- `tools` (list[str], optional) - Tools for workers
- `vars` (dict, optional) - Variables

**Returns:** `self` for chaining

**Example:**

```python
.worker_template("executor", tools=["python", "http_get"])
```

---

#### `.reduce_step()`

Configure reduce step (synthesizes worker results).

```python
.reduce_step(
    agent: str,
    input: str,
    vars: dict[str, Any] | None = None,
    tool_overrides: list[str] | None = None
) -> OrchestratorWorkersBuilder
```

**Parameters:**

- `agent` (str, **required**) - Synthesizer agent ID
- `input` (str, **required**) - Synthesis prompt (references `{{ workers }}`)
- `vars` (dict, optional) - Variables
- `tool_overrides` (list[str], optional) - Tool overrides

**Returns:** `self` for chaining

**Example:**

```python
.reduce_step("synthesizer",
             """Worker results:
             {% for result in workers %}
             - {{ result }}
             {% endfor %}
             
             Combine these into a final report.""")
```

---

#### `.reduce_review()`

Add HITL review before reduce step.

```python
.reduce_review(
    prompt: str,
    show: str | None = None
) -> OrchestratorWorkersBuilder
```

**Parameters:**

- `prompt` (str, **required**) - HITL prompt
- `show` (str, optional) - Context template

**Returns:** `self` for chaining

**Example:**

```python
.reduce_review("Review worker results before synthesis",
               show="{{ workers | tojson }}")
```

---

#### `.build()`

Complete orchestrator-workers configuration.

```python
.build() -> Workflow
```

---

## Workflow Class

**Executable workflow instance returned by `.build()`.**

### Methods

#### `.run_interactive()`

Execute workflow with terminal prompts for HITL.

```python
.run_interactive(**variables: Any) -> RunResult
```

**Parameters:**

- `**variables` - Workflow input variables (passed as keyword arguments)

**Returns:** `RunResult` with execution details

**Example:**

```python
result = workflow.run_interactive(topic="AI", depth="detailed")
```

---

#### `.run_interactive_async()`

Execute workflow asynchronously with terminal prompts.

```python
async .run_interactive_async(**variables: Any) -> RunResult
```

**Parameters:**

- `**variables` - Workflow input variables

**Returns:** `RunResult` (awaitable)

**Example:**

```python
result = await workflow.run_interactive_async(topic="AI")
```

---

#### `.run()`

Execute workflow non-interactively (session-based HITL).

```python
.run(**variables: Any) -> RunResult
```

**Parameters:**

- `**variables` - Workflow input variables

**Returns:** `RunResult`

**Note:** Workflow pauses at HITL points and saves session for later resumption.

---

#### `.run_async()`

Execute workflow asynchronously (session-based HITL).

```python
async .run_async(**variables: Any) -> RunResult
```

**Parameters:**

- `**variables` - Workflow input variables

**Returns:** `RunResult` (awaitable)

---

## RunResult

**Execution result object.**

### Attributes

- `success` (bool) - Whether workflow completed successfully
- `exit_code` (int) - Exit code (0 = success)
- `agent_id` (str | None) - Last agent executed
- `last_response` (str | None) - Final agent response
- `duration_seconds` (float) - Execution time
- `artifacts_written` (list[str]) - Paths to written artifact files
- `error` (str | None) - Error message if failed

**Example:**

```python
result = workflow.run_interactive(topic="AI")

if result.success:
    print(f"✓ Success in {result.duration_seconds:.2f}s")
    print(f"Output: {result.last_response}")
    print(f"Artifacts: {result.artifacts_written}")
else:
    print(f"✗ Failed: {result.error}")
```

---

## BuildError Exception

**Raised when workflow build validation fails.**

### Usage

```python
from strands_cli.api.exceptions import BuildError

try:
    workflow = builder.build()
except BuildError as e:
    print(f"Validation failed: {e}")
    # Fix errors and retry
```

### Common Errors

#### Agent not found

```
BuildError: Agent 'researcher' not found. Did you mean 'research_agent'?
Use .agent('researcher', ...) to define it.
```

**Fix:** Define agent before referencing:

```python
.agent("researcher", "You are a researcher")
.chain()
.step("researcher", "...")
```

---

#### Invalid provider

```
BuildError: Invalid provider 'azure'. Must be one of: ['bedrock', 'ollama', 'openai']
```

**Fix:** Use valid provider:

```python
.runtime("openai", model="gpt-4o-mini")
```

---

#### Circular dependency

```
BuildError: Circular dependency detected: task_a -> task_b -> task_a
```

**Fix:** Remove circular dependency:

```python
.task("task_a", "agent", "...")
.task("task_b", "agent", "...", depends_on=["task_a"])
# Don't make task_a depend on task_b!
```

---

#### Template syntax error

```
BuildError: Invalid template syntax at line 1: unexpected '}'
```

**Fix:** Fix template syntax:

```python
# Wrong
.step("agent", "Process {{ unclosed")

# Correct
.step("agent", "Process {{ variable }}")
```

---

## Examples

### Complete Chain Workflow

```python
from strands_cli.api import FluentBuilder

workflow = (
    FluentBuilder("research-workflow")
    .description("Three-step research with approval gates")
    .runtime("openai", model="gpt-4o-mini", temperature=0.7)
    .agent("researcher", "You are a thorough research assistant")
    .agent("analyst", "You are a critical analyst")
    .agent("writer", "You are a technical writer")
    .chain()
    .step("researcher", "Research {{topic}} thoroughly")
    .hitl("Review research. Type 'continue' to proceed.",
          show="{{ steps[0].response }}")
    .step("analyst", "Analyze: {{ steps[0].response }}")
    .step("writer",
          """Research: {{ steps[0].response }}
          Analysis: {{ steps[2].response }}
          Write a comprehensive report.""")
    .output_dir("./artifacts")
    .artifact("{{topic}}-report.md",
              "# {{topic}} Report\n\n{{ last_response }}")
    .build()
)

result = workflow.run_interactive(topic="quantum computing")
```

### Complete Workflow (DAG) Pattern

```python
workflow = (
    FluentBuilder("data-pipeline")
    .runtime("openai", model="gpt-4o-mini")
    .agent("gatherer", "You gather data")
    .agent("processor", "You process data")
    .agent("visualizer", "You create visualizations")
    .agent("reporter", "You write reports")
    .workflow()
    .task("gather_api", "gatherer", "Fetch data from API for {{dataset}}")
    .task("gather_db", "gatherer", "Query database for {{dataset}}")
    .task("process", "processor",
          """API data: {{ tasks.gather_api.response }}
          DB data: {{ tasks.gather_db.response }}
          Process and clean this data.""",
          depends_on=["gather_api", "gather_db"])
    .task("visualize", "visualizer",
          "Create charts from: {{ tasks.process.response }}",
          depends_on=["process"])
    .task("report", "reporter",
          """Data: {{ tasks.process.response }}
          Charts: {{ tasks.visualize.response }}
          Write executive summary.""",
          depends_on=["process", "visualize"])
    .output_dir("./artifacts")
    .artifact("{{dataset}}-report.html",
              "<h1>{{dataset}}</h1>{{ tasks.report.response }}")
    .build()
)
```

### Complete Parallel Pattern

```python
workflow = (
    FluentBuilder("multi-perspective-analysis")
    .runtime("openai", model="gpt-4o-mini")
    .agent("tech_analyst", "You analyze technical aspects")
    .agent("biz_analyst", "You analyze business aspects")
    .agent("security_analyst", "You analyze security aspects")
    .agent("synthesizer", "You synthesize multiple perspectives")
    .parallel()
    .branch("technical")
        .step("tech_analyst", "Analyze technical: {{topic}}")
        .hitl_in_branch("Review technical analysis")
        .done()
    .branch("business")
        .step("biz_analyst", "Analyze business: {{topic}}")
        .done()
    .branch("security")
        .step("security_analyst", "Analyze security: {{topic}}")
        .done()
    .reduce("synthesizer",
            """Technical: {{ branches.technical.response }}
            Business: {{ branches.business.response }}
            Security: {{ branches.security.response }}
            
            Create unified recommendation.""")
    .output_dir("./artifacts")
    .artifact("{{topic}}-analysis.md",
              "# Analysis: {{topic}}\n\n{{ last_response }}")
    .build()
)
```

## See Also

- [Builder API Tutorial](../../tutorials/builder-api.md) - Learning guide
- [Pattern Documentation](../../explanation/patterns.md) - Pattern overview
- [Python API Reference](python-api.md) - High-level API
- [Workflow Manual](../workflow-manual.md) - YAML specification

---

**Need Help?**

- Check [Troubleshooting Guide](../troubleshooting.md)
- Review [examples/api/](https://github.com/ThomasRohde/strands-cli/tree/main/examples/api) directory
- Open an issue on [GitHub](https://github.com/ThomasRohde/strands-cli/issues)

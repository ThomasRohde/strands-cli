# Strands Python API Examples

This directory contains example scripts demonstrating the **Strands Python API** for programmatic workflow execution and construction.

## Overview

The Strands Python API provides two powerful interfaces:

1. **Workflow Execution API**: Load YAML workflows and execute them programmatically
2. **Builder API**: Construct workflows entirely in Python without YAML (fluent/builder pattern)

Use the API to:

- Run workflows as Python programs (no CLI required)
- Build workflows programmatically with type safety
- Handle HITL (Human-in-the-Loop) interactively in terminal
- Build custom approval logic and integrations
- Use async/await for high-performance applications

## Examples

### Phase 1: Workflow Execution API (Load YAML + Execute)

### 01_interactive_hitl.py

**Basic interactive HITL workflow execution**

```python
from strands import Workflow

workflow = Workflow.from_file("examples/chain-hitl-business-proposal-openai.yaml")
result = workflow.run_interactive(topic="quantum computing")
print(result.last_response)
```

**Demonstrates:**
- Loading workflows from YAML files
- Running with interactive terminal prompts for HITL
- Accessing execution results and artifacts

**Usage:**
```powershell
python examples/api/01_interactive_hitl.py
```

---

### Phase 2: Builder API (Construct Workflows in Python)

#### 02_chain_builder.py

**Build chain pattern workflows programmatically**

```python
from strands_cli.api import FluentBuilder

workflow = (
    FluentBuilder("research-workflow")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a research assistant...")
    .chain()
    .step("researcher", "Research: {{topic}}")
    .step("researcher", "Analyze: {{ steps[0].response }}")
    .artifact("output.md", "{{ last_response }}")
    .build()
)

result = await workflow.run_interactive_async(topic="AI")
```

**Demonstrates:**
- Fluent builder API for chain pattern
- Sequential step execution
- Template variable references ({{ steps[n].response }})
- No YAML required

**Usage:**
```powershell
python examples/api/02_chain_builder.py
```

---

#### 03_workflow_builder.py

**Build DAG workflows with parallel task execution**

```python
workflow = (
    FluentBuilder("parallel-research")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a research assistant...")
    .workflow()
    .task("overview", "researcher", "Overview of: {{topic}}")
    .task("technical", "researcher", "Technical analysis...", depends_on=["overview"])
    .task("applications", "researcher", "Use cases...", depends_on=["overview"])
    .task("synthesis", "researcher", "Combine insights...", depends_on=["technical", "applications"])
    .build()
)
```

**Demonstrates:**
- DAG-based workflow pattern
- Task dependencies with `depends_on`
- Automatic parallel execution where possible
- Topological sort validation (detects circular dependencies)

**Usage:**
```powershell
python examples/api/03_workflow_builder.py
```

---

#### 04_parallel_builder.py

**Build parallel branch execution with reduce step**

```python
workflow = (
    FluentBuilder("parallel-analysis")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "Domain expert...")
    .agent("synthesizer", "Synthesis expert...")
    .parallel()
    .branch("academic").step("researcher", "Academic perspective").done()
    .branch("industry").step("researcher", "Industry perspective").done()
    .branch("regulatory").step("researcher", "Regulatory perspective").done()
    .reduce("synthesizer", "Synthesize: {{ branches.academic.response }}")
    .build()
)
```

**Demonstrates:**
- Parallel pattern with concurrent branch execution
- Branch context isolation
- Optional reduce step for synthesis
- Reference branch outputs via {{ branches.id.response }}

**Usage:**
```powershell
python examples/api/04_parallel_builder.py
```

---

#### 05_graph_builder.py

**Build state machine workflows with conditional edges**

```python
workflow = (
    FluentBuilder("support-router")
    .runtime("openai", model="gpt-4o-mini")
    .agent("intake", "Customer support intake...")
    .agent("technical_support", "Technical support engineer...")
    .graph()
    .node("intake", "intake", "{{ input_request }}")
    .node("technical", "technical_support")
    .node("billing", "billing_support")
    .conditional_edge("intake", [
        ("{{ 'technical' in nodes.intake.response.lower() }}", "technical"),
        ("{{ 'billing' in nodes.intake.response.lower() }}", "billing"),
        ("else", "general"),
    ])
    .max_iterations(5)
    .build()
)
```

**Demonstrates:**
- Graph pattern (state machine)
- Conditional transitions between nodes
- Node output references via {{ nodes.id.response }}
- Cycle prevention with max_iterations

**Usage:**
```powershell
python examples/api/05_graph_builder.py
```

---

#### 06_routing_builder.py

**Build routing workflows with classifier-based agent selection**

```python
workflow = (
    FluentBuilder("task-classifier")
    .runtime("openai", model="gpt-4o-mini")
    .agent("router", "Classify tasks...")
    .agent("coder", "Expert software engineer...")
    .agent("researcher", "Thorough researcher...")
    .routing()
    .router("router", "Classify: {{ task }}", max_retries=3)
    .route("coding").step("coder", "Implement: {{ task }}").done()
    .route("research").step("researcher", "Research: {{ task }}").done()
    .build()
)
```

**Demonstrates:**
- Routing pattern with dynamic agent selection
- Router agent returns JSON: {"route": "route_name"}
- Multi-step routes
- Configurable retry logic for malformed JSON

**Usage:**
```powershell
python examples/api/06_routing_builder.py
```

---

#### 07_evaluator_optimizer_builder.py

**Build iterative refinement loops with producer-evaluator feedback**

```python
workflow = (
    FluentBuilder("content-refinement")
    .runtime("openai", model="gpt-4o-mini")
    .agent("writer", "Expert content writer...")
    .agent("critic", "Critical editor...")
    .evaluator_optimizer()
    .producer("writer")
    .evaluator("critic", "Evaluate: {{ draft }}")
    .accept(min_score=85, max_iterations=3)
    .revise_prompt("Improve based on: {{ evaluation.score }}/100...")
    .build()
)
```

**Demonstrates:**
- Evaluator-optimizer pattern
- Iterative refinement with feedback loop
- Evaluator returns JSON: {"score": 0-100, "issues": [...], "fixes": [...]}
- Custom revision prompts
- Acceptance criteria (min_score, max_iterations)

**Usage:**
```powershell
python examples/api/07_evaluator_optimizer_builder.py
```

---

#### 08_orchestrator_builder.py

**Build task decomposition workflows with parallel worker execution**

```python
workflow = (
    FluentBuilder("research-swarm")
    .runtime("openai", model="gpt-4o-mini")
    .agent("orchestrator", "Break down complex tasks...")
    .agent("researcher", "Research specialist...")
    .agent("report_writer", "Technical writer...")
    .orchestrator_workers()
    .orchestrator("orchestrator", max_workers=3, max_rounds=1)
    .worker_template("researcher", tools=["http_executors"])
    .reduce_step("report_writer")
    .build()
)
```

**Demonstrates:**
- Orchestrator-workers pattern
- Task decomposition (orchestrator returns JSON array of subtasks)
- Parallel worker pool execution
- Optional synthesis/reduce step
- Worker limits (max_workers, max_rounds)

**Usage:**
```powershell
python examples/api/08_orchestrator_builder.py
```

---

### 02_simple_chain.py

**Minimal chain workflow with HITL approval**

```python
from strands import Workflow

workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
result = workflow.run_interactive(topic="AI in healthcare")

if result.success:
    print(f"✓ Completed in {result.duration_seconds:.2f}s")
```

**Demonstrates:**
- Simplest possible API usage
- Chain pattern with single HITL step
- Variable substitution with `--var` equivalent

**Usage:**
```powershell
python examples/api/02_simple_chain.py
```

---

### 03_async_execution.py

**Async workflow execution with run_interactive_async()**

```python
import asyncio
from strands import Workflow

async def main():
    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
    result = await workflow.run_interactive_async(topic="machine learning")
    print(result.last_response)

asyncio.run(main())
```

**Demonstrates:**
- Async API usage for high-performance applications
- Running multiple workflows with proper async patterns
- When to use async vs sync execution

**Usage:**
```powershell
python examples/api/03_async_execution.py
```

---

### 04_custom_hitl_handler.py

**Custom HITL handler with automated approval logic**

```python
from strands import Workflow
from strands_cli.types import HITLState

def auto_approve_handler(hitl_state: HITLState) -> str:
    print(f"Auto-approving: {hitl_state.prompt}")
    return "APPROVED"

workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
result = workflow.run_interactive(
    topic="blockchain",
    hitl_handler=auto_approve_handler,
)
```

**Demonstrates:**
- Creating custom HITL handlers
- Automated approval based on business rules
- Accessing HITL state (prompt, context, defaults)
- Useful for testing and custom integrations

**Usage:**
```powershell
python examples/api/04_custom_hitl_handler.py
```

---

## Requirements

All examples require:

- **Python 3.12+**
- **strands-cli** installed (`uv pip install -e .` from project root)
- **OpenAI API key** set in `OPENAI_API_KEY` environment variable (for OpenAI examples)
- **Ollama** running locally (for Ollama examples, if using those workflows)

## Installation

From the project root:

```powershell
# Install strands-cli in development mode
uv pip install -e .

# Set OpenAI API key (for examples using OpenAI)
$env:OPENAI_API_KEY = "your-api-key-here"
```

## Running Examples

```powershell
# Run individual examples
python examples/api/01_interactive_hitl.py
python examples/api/02_simple_chain.py
python examples/api/03_async_execution.py
python examples/api/04_custom_hitl_handler.py

# Or from uv
uv run python examples/api/01_interactive_hitl.py
```

## Interactive vs Non-Interactive Mode

### Interactive Mode (Terminal Prompts)

Use `run_interactive()` for local development and debugging:

```python
# User is prompted in terminal for HITL responses
result = workflow.run_interactive()
```

**Best for:**
- Local development and testing
- Manual approval workflows
- Interactive debugging
- Quick prototyping

### Non-Interactive Mode (Session Persistence)

Use `run()` for production workflows with external approval systems:

```python
# Saves session and exits at HITL steps
result = workflow.run()

# Later, resume with approval from external system
# (CLI: strands resume <session-id> --response "approved")
```

**Best for:**
- Production deployments
- Integration with approval systems (Slack, email, etc.)
- Long-running workflows
- Distributed systems

## API Quick Reference

### Workflow Execution API

```python
from strands_cli import Workflow

# Load from file
workflow = Workflow.from_file("workflow.yaml", **variables)

# Run interactively (sync)
result = workflow.run_interactive(**variables)

# Run interactively (async)
result = await workflow.run_interactive_async(**variables)

# Run non-interactive (session-based)
result = workflow.run(**variables)

# Run non-interactive (async)
result = await workflow.run_async(**variables)
```

### Builder API (Fluent Pattern)

```python
from strands_cli.api import FluentBuilder

# Core workflow setup
workflow = (
    FluentBuilder("workflow-name")
    .description("Optional description")
    .runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=4000)
    .agent("agent_id", "System prompt...", tools=["tool1", "tool2"])
    
    # Select pattern (pick one):
    .chain()           # Sequential steps
    .workflow()        # DAG with dependencies
    .parallel()        # Concurrent branches
    .graph()           # State machine
    .routing()         # Classifier-based routing
    .evaluator_optimizer()   # Iterative refinement
    .orchestrator_workers()  # Task decomposition
    
    # Pattern-specific methods... (see examples)
    
    .artifact("output.md", "{{ last_response }}")
    .build()
)

# Execute
result = await workflow.run_interactive_async(**variables)
```

#### Chain Pattern Methods

```python
.chain()
  .step(agent, input, vars=None, tool_overrides=None)
  .hitl(prompt, context_display=None, default=None, timeout_seconds=None)
  .build()
```

#### Workflow Pattern Methods

```python
.workflow()
  .task(id, agent, input, description=None, depends_on=None, vars=None)
  .hitl_task(id, prompt, show=None, default=None, depends_on=None)
  .build()
```

#### Parallel Pattern Methods

```python
.parallel()
  .branch(id)
    .step(agent, input, vars=None)
    .hitl(prompt, context_display=None, default=None)
    .done()
  .reduce(agent, input, vars=None)
  .build()
```

#### Graph Pattern Methods

```python
.graph()
  .node(id, agent, input=None)
  .hitl_node(id, prompt, show=None, default=None)
  .edge(from_node, to_node)
  .conditional_edge(from_node, [(condition, target), ...])
  .max_iterations(count)
  .build()
```

#### Routing Pattern Methods

```python
.routing()
  .router(agent, input, max_retries=2)
  .route(id)
    .step(agent, input, vars=None)
    .hitl(prompt, context_display=None)
    .done()
  .build()
```

#### Evaluator-Optimizer Pattern Methods

```python
.evaluator_optimizer()
  .producer(agent, input=None)
  .evaluator(agent, input)
  .accept(min_score, max_iterations=3)
  .revise_prompt(template)
  .review_gate(prompt, show=None)
  .build()
```

#### Orchestrator-Workers Pattern Methods

```python
.orchestrator_workers()
  .orchestrator(agent, input=None, max_workers=None, max_rounds=None)
  .worker_template(agent, tools=None)
  .reduce_step(agent, input=None, vars=None)
  .decomposition_review(prompt, show=None)
  .reduce_review(prompt, show=None)
  .build()
```

### Custom HITL Handler

```python
from strands_cli.types import HITLState

def my_handler(hitl_state: HITLState) -> str:
    """Custom HITL handler.
    
    Args:
        hitl_state: HITL pause state with:
            - prompt: str - HITL prompt text
            - context_display: str | None - Optional context
            - default_response: str | None - Optional default
            - user_response: str | None - Previous response (if any)
    
    Returns:
        User's response string
    """
    print(f"HITL Prompt: {hitl_state.prompt}")
    return "my response"

# Use with workflow
result = workflow.run_interactive(hitl_handler=my_handler)
```

### RunResult

```python
# Access execution results
result = workflow.run_interactive()

result.success                # bool - Whether workflow succeeded
result.exit_code             # int - Exit code (0 = success)
result.agent_id              # str - Last agent executed
result.last_response         # str - Final LLM response
result.duration_seconds      # float - Execution time
result.artifacts_written     # list[str] - Artifact file paths
```

## Supported Workflow Patterns

All 7 workflow patterns work with both Execution API (YAML) and Builder API (Python):

- ✅ **chain** - Sequential multi-step execution (examples: 02_chain_builder.py, 02_simple_chain.py)
- ✅ **workflow** - Multi-task DAG with dependencies (example: 03_workflow_builder.py)
- ✅ **routing** - Dynamic agent selection (example: 06_routing_builder.py)
- ✅ **parallel** - Concurrent branch execution (example: 04_parallel_builder.py)
- ✅ **evaluator-optimizer** - Iterative refinement (example: 07_evaluator_optimizer_builder.py)
- ✅ **orchestrator-workers** - Task decomposition (example: 08_orchestrator_builder.py)
- ✅ **graph** - State machine with transitions (example: 05_graph_builder.py)

## Key Differences: Execution API vs Builder API

| Feature | Execution API | Builder API |
|---------|---------------|-------------|
| **Definition** | Load YAML files | Python fluent builder |
| **Type Safety** | Runtime validation only | IDE autocomplete + Pydantic validation |
| **Flexibility** | Declarative, version-controlled | Programmatic, dynamic |
| **Best For** | Shareable workflows, GitOps | Custom integrations, programmatic generation |
| **Example** | `Workflow.from_file("spec.yaml")` | `FluentBuilder("name").chain().build()` |

## Additional Resources

- **Full API Documentation**: See `docs/API.md`
- **HITL Documentation**: See `docs/HITL.md`
- **Workflow Manual**: See `docs/strands-workflow-manual.md`
- **CLI Documentation**: See `README.md`

## Troubleshooting

### "No module named 'strands'"

Install strands-cli in development mode:

```powershell
uv pip install -e .
```

### "OPENAI_API_KEY not set"

Set your OpenAI API key:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### "Workflow file not found"

Run examples from project root:

```powershell
cd c:\Users\thoma\Projects\artifacts\Projects\strands-cli
python examples/api/01_interactive_hitl.py
```

### "Event loop already running"

If you see `RuntimeError: asyncio.run() cannot be called from a running event loop`:

- Use `run_interactive_async()` instead of `run_interactive()` in async contexts
- Or use `asyncio.create_task()` instead of `asyncio.run()`

## Contributing

When adding new examples:

1. Follow naming convention: `NN_descriptive_name.py`
2. Include comprehensive docstring with usage instructions
3. Add example to this README
4. Test with both OpenAI and Ollama providers (where applicable)
5. Keep examples focused on single concept

## License

MIT License - See LICENSE file in project root

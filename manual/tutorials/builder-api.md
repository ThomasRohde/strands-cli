---
title: Building Workflows Programmatically
description: Learn to build workflows using the Python builder API without YAML
keywords: builder, api, python, programmatic, fluent, chain, code-first
---

# Building Workflows Programmatically

This tutorial teaches you how to build complete Strands workflows in Python code using the **fluent builder API** — no YAML required. Perfect for developers who prefer code-first workflows with full type safety and IDE autocomplete.

## What You'll Learn

- How to construct workflows programmatically with the builder API
- Migration patterns from YAML to Python builders
- Type-safe workflow construction with fail-fast validation
- All 7 workflow patterns via fluent interfaces
- Best practices for code-first workflow development

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **Strands CLI 0.14.0+** installed (`uv pip install strands-cli`)
- Basic understanding of Strands workflow concepts
- Familiarity with one provider (Bedrock, Ollama, or OpenAI)

## Why Use the Builder API?

### YAML Workflows (Traditional)

```yaml
version: 0
name: my-workflow
description: Example workflow

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  researcher:
    prompt: You are a research assistant...

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
```

### Builder API (Code-First)

```python
from strands_cli.api import FluentBuilder

workflow = (
    FluentBuilder("my-workflow")
    .description("Example workflow")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a research assistant...")
    .chain()
    .step("researcher", "Research {{topic}}")
    .build()
)

result = workflow.run_interactive(topic="AI")
```

### Benefits

✅ **Type safety** - IDE autocomplete and compile-time checking  
✅ **Fail fast** - Errors caught at build time, not runtime  
✅ **Refactoring** - Safe code transformations with IDE support  
✅ **Modularity** - Compose workflows from reusable components  
✅ **Testing** - Unit test workflow construction logic  
✅ **Dynamic** - Generate workflows from data or user input  

## Quick Start: Your First Builder Workflow

Let's create a simple single-agent workflow:

```python
"""Simple research workflow using builder API."""
from strands_cli.api import FluentBuilder

# Build workflow
workflow = (
    FluentBuilder("research-assistant")
    .description("A simple research workflow")
    .runtime("openai", model="gpt-4o-mini", temperature=0.7)
    .agent(
        "researcher",
        "You are a helpful research assistant. Provide clear, "
        "factual responses with examples."
    )
    .single_agent()
    .prompt("researcher", "Explain {{topic}} in simple terms with 2-3 examples.")
    .artifact("{{topic}}-explanation.md", "# {{topic}}\n\n{{ last_response }}")
    .build()
)

# Execute workflow
result = workflow.run_interactive(topic="quantum computing")

# Access results
if result.success:
    print(f"✓ Success! Output: {result.last_response}")
    print(f"Artifacts: {result.artifacts_written}")
else:
    print(f"✗ Failed: {result.error}")
```

Save this as `my_workflow.py` and run:

```bash
uv run python my_workflow.py
```

**What just happened?**

1. Created a `FluentBuilder` with workflow name
2. Configured runtime (OpenAI, GPT-4o mini model)
3. Defined an agent with a prompt
4. Selected single-agent pattern
5. Added input prompt with variable (`{{topic}}`)
6. Configured artifact output
7. Built the workflow (validates everything)
8. Executed with `run_interactive()` passing variables

## Core Concepts

### 1. FluentBuilder - The Foundation

Every workflow starts with `FluentBuilder`:

```python
from strands_cli.api import FluentBuilder

builder = FluentBuilder("workflow-name")
```

**Always required:**
- Workflow name (unique identifier)
- At least one agent definition
- Runtime configuration
- Pattern selection

### 2. Runtime Configuration

Explicitly configure your LLM provider:

```python
# OpenAI
.runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=8000)

# Bedrock
.runtime("bedrock", model="anthropic.claude-3-sonnet-20240229-v1:0", region="us-east-1")

# Ollama
.runtime("ollama", model="llama3.2", host="http://localhost:11434")
```

**No default fallback** - runtime is always explicit in builder API.

### 3. Agent Definitions

Define agents before using them:

```python
.agent(
    "researcher",                    # Agent ID (must be unique)
    "You are a research assistant",  # System prompt
    tools=["python", "http_get"],    # Optional tools
    temperature=0.8,                 # Optional overrides
)
```

**Fail-fast validation:**
- Duplicate agent IDs raise `BuildError`
- Referenced agents that don't exist suggest similar names
- Tool names validated against registry

### 4. Pattern Selection

Choose one of 7 workflow patterns:

```python
.single_agent()              # Simple single-agent workflow
.chain()                     # Sequential multi-step
.workflow()                  # DAG with task dependencies
.parallel()                  # Concurrent branches
.graph()                     # State machine
.routing()                   # Dynamic agent selection
.evaluator_optimizer()       # Iterative refinement
.orchestrator_workers()      # Task decomposition
```

Each pattern returns a pattern-specific builder with its own methods.

### 5. Build and Execute

```python
# Build workflow (validates everything)
workflow = builder.build()

# Execute interactively (sync)
result = workflow.run_interactive(topic="AI", depth="detailed")

# Execute interactively (async)
result = await workflow.run_interactive_async(topic="AI")

# Execute non-interactive (session-based)
result = workflow.run(topic="AI")
```

### 6. Accessing Results

All execution methods return a `RunResult` object with comprehensive execution data:

```python
result = workflow.run_interactive(topic="AI")

# Basic result fields
print(f"Success: {result.success}")
print(f"Duration: {result.duration_seconds:.2f}s")
print(f"Final output: {result.last_response}")

# Artifact file paths
if result.artifacts_written:
    print(f"Generated {len(result.artifacts_written)} files:")
    for path in result.artifacts_written:
        print(f"  - {path}")

# Token usage by agent
total_tokens = sum(result.token_usage.values())
print(f"Total tokens consumed: {total_tokens}")
```

#### Accessing Intermediate Results

Use `execution_context` to access step/task/branch/node outputs:

**Chain Pattern:**
```python
# Access individual step outputs
steps = result.execution_context["steps"]
print(f"Step 0: {steps[0]['response'][:100]}...")
print(f"Step 1: {steps[1]['response'][:100]}...")

# Iterate through all steps
for i, step in enumerate(steps):
    print(f"Step {i} consumed {step['tokens']} tokens")
```

**Workflow Pattern:**
```python
# Access task results by ID
tasks = result.execution_context["tasks"]
research = tasks["gather_data"]["response"]
analysis = tasks["analyze"]["response"]

print(f"Research: {research[:200]}...")
print(f"Analysis: {analysis[:200]}...")
```

**Parallel Pattern:**
```python
# Access branch outputs by ID
branches = result.execution_context["branches"]
for branch_id, branch_data in branches.items():
    print(f"{branch_id}: {branch_data['response'][:100]}...")

# Access reduce step output (if present)
if "reduce" in result.execution_context:
    reduce_output = result.execution_context["reduce"]["response"]
    print(f"Synthesis: {reduce_output}")
```

**Graph Pattern:**
```python
# Access node outputs by ID
nodes = result.execution_context["nodes"]
start_output = nodes["start"]["response"]
decision_output = nodes["evaluate"]["response"]
final_output = nodes["finish"]["response"]

# Check execution path
if "execution_path" in result.execution_context:
    path = result.execution_context["execution_path"]
    print(f"Executed nodes: {' → '.join(path)}")
```

#### Reading Generated Artifacts

```python
# Read all artifact files
for artifact_path in result.artifacts_written:
    with open(artifact_path, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"\n=== {artifact_path} ===")
        print(content)

# Find specific artifacts by pattern
reports = [p for p in result.artifacts_written if "report" in p]
if reports:
    with open(reports[0], 'r') as f:
        report_content = f.read()
        print(report_content)
```

#### Complete Example

```python
workflow = (
    FluentBuilder("analysis-workflow")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a researcher")
    .agent("analyst", "You are an analyst")
    .chain()
    .step("researcher", "Research {{topic}}")
    .step("analyst", "Analyze: {{ steps[0].response }}")
    .artifact("{{topic}}-analysis.md", "# Analysis\n\n{{ last_response }}")
    .build()
)

result = workflow.run_interactive(topic="quantum computing")

# Access everything
if result.success:
    # Intermediate results
    research = result.execution_context["steps"][0]["response"]
    analysis = result.execution_context["steps"][1]["response"]
    
    print(f"Research findings:\n{research[:300]}...\n")
    print(f"Analysis:\n{analysis[:300]}...\n")
    
    # Final output
    print(f"Final output:\n{result.last_response}\n")
    
    # Artifacts
    print(f"Generated files:")
    for path in result.artifacts_written:
        print(f"  ✓ {path}")
        with open(path, 'r') as f:
            content = f.read()
            print(f"    Size: {len(content)} bytes")
    
    # Performance metrics
    print(f"\nMetrics:")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    print(f"  Tokens: {sum(result.token_usage.values())}")
```

## Migration Guide: YAML → Builder API

### Single Agent Workflow

**YAML:**
```yaml
version: 0
name: simple-qa
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  assistant:
    prompt: You are a helpful assistant
pattern:
  type: single_agent
  config:
    agent: assistant
    input: "Answer: {{question}}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("simple-qa")
    .runtime("openai", model="gpt-4o-mini")
    .agent("assistant", "You are a helpful assistant")
    .single_agent()
    .prompt("assistant", "Answer: {{question}}")
    .build()
)
```

### Chain Pattern

**YAML:**
```yaml
version: 0
name: research-chain
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  researcher:
    prompt: You are a researcher
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
      - agent: researcher
        input: "Summarize: {{ steps[0].response }}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("research-chain")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a researcher")
    .chain()
    .step("researcher", "Research {{topic}}")
    .step("researcher", "Summarize: {{ steps[0].response }}")
    .build()
)
```

### Workflow Pattern (DAG)

**YAML:**
```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: gather_data
        agent: researcher
        input: "Gather data on {{topic}}"
      - id: analyze
        agent: analyst
        input: "Analyze: {{ tasks.gather_data.response }}"
        depends_on: [gather_data]
      - id: visualize
        agent: visualizer
        input: "Create charts for {{topic}}"
        depends_on: [gather_data]
      - id: report
        agent: writer
        input: |
          Analysis: {{ tasks.analyze.response }}
          Charts: {{ tasks.visualize.response }}
        depends_on: [analyze, visualize]
```

**Builder API:**
```python
workflow = (
    FluentBuilder("data-pipeline")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "...")
    .agent("analyst", "...")
    .agent("visualizer", "...")
    .agent("writer", "...")
    .workflow()
    .task("gather_data", "researcher", "Gather data on {{topic}}")
    .task("analyze", "analyst", 
          "Analyze: {{ tasks.gather_data.response }}",
          depends_on=["gather_data"])
    .task("visualize", "visualizer",
          "Create charts for {{topic}}",
          depends_on=["gather_data"])
    .task("report", "writer",
          "Analysis: {{ tasks.analyze.response }}\n"
          "Charts: {{ tasks.visualize.response }}",
          depends_on=["analyze", "visualize"])
    .build()
)
```

**Validation:**
- Circular dependencies detected at build time
- Missing task dependencies raise clear errors
- Topological sort validation ensures valid DAG

### Parallel Pattern

**YAML:**
```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: technical
        steps:
          - agent: tech_writer
            input: "Technical overview of {{topic}}"
      - id: business
        steps:
          - agent: biz_writer
            input: "Business case for {{topic}}"
    reduce:
      agent: synthesizer
      input: |
        Technical: {{ branches.technical.response }}
        Business: {{ branches.business.response }}
```

**Builder API:**
```python
workflow = (
    FluentBuilder("parallel-analysis")
    .runtime("openai", model="gpt-4o-mini")
    .agent("tech_writer", "...")
    .agent("biz_writer", "...")
    .agent("synthesizer", "...")
    .parallel()
    .branch("technical")
        .step("tech_writer", "Technical overview of {{topic}}")
        .done()
    .branch("business")
        .step("biz_writer", "Business case for {{topic}}")
        .done()
    .reduce("synthesizer",
            "Technical: {{ branches.technical.response }}\n"
            "Business: {{ branches.business.response }}")
    .build()
)
```

### Graph Pattern

**YAML:**
```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: draft
        agent: writer
        input: "Draft proposal for {{topic}}"
      - id: review
        agent: reviewer
        input: "Review: {{ nodes.draft.response }}"
      - id: revise
        agent: writer
        input: |
          Original: {{ nodes.draft.response }}
          Feedback: {{ nodes.review.response }}
    edges:
      - from: draft
        to: review
      - from: review
        to: revise
        condition: "{{ nodes.review.response | lower contains 'revise' }}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("review-loop")
    .runtime("openai", model="gpt-4o-mini")
    .agent("writer", "...")
    .agent("reviewer", "...")
    .graph()
    .node("draft", "writer", "Draft proposal for {{topic}}")
    .node("review", "reviewer", "Review: {{ nodes.draft.response }}")
    .node("revise", "writer",
          "Original: {{ nodes.draft.response }}\n"
          "Feedback: {{ nodes.review.response }}")
    .edge("draft", "review")
    .conditional_edge("review", "revise",
                      "{{ nodes.review.response | lower contains 'revise' }}")
    .build()
)
```

### Routing Pattern

**YAML:**
```yaml
pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: "Classify query: {{query}}"
    routes:
      - id: technical
        agent: tech_expert
        steps:
          - agent: tech_expert
            input: "Answer technical: {{query}}"
      - id: business
        agent: biz_expert
        steps:
          - agent: biz_expert
            input: "Answer business: {{query}}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("smart-routing")
    .runtime("openai", model="gpt-4o-mini")
    .agent("classifier", "...")
    .agent("tech_expert", "...")
    .agent("biz_expert", "...")
    .routing()
    .router("classifier", "Classify query: {{query}}")
    .route("technical")
        .step("tech_expert", "Answer technical: {{query}}")
        .done()
    .route("business")
        .step("biz_expert", "Answer business: {{query}}")
        .done()
    .build()
)
```

### Evaluator-Optimizer Pattern

**YAML:**
```yaml
pattern:
  type: evaluator_optimizer
  config:
    producer:
      agent: writer
      input: "Write article on {{topic}}"
    evaluator:
      agent: critic
      input: "Rate this (0-10): {{ iteration.response }}"
    accept:
      min_score: 8
      max_iterations: 3
    revise_prompt: |
      Original: {{ iteration.response }}
      Score: {{ iteration.score }}
      Feedback: {{ iteration.evaluation }}
```

**Builder API:**
```python
workflow = (
    FluentBuilder("iterative-writing")
    .runtime("openai", model="gpt-4o-mini")
    .agent("writer", "...")
    .agent("critic", "...")
    .evaluator_optimizer()
    .producer("writer", "Write article on {{topic}}")
    .evaluator("critic", "Rate this (0-10): {{ iteration.response }}")
    .accept(min_score=8, max_iterations=3)
    .revise_prompt(
        "Original: {{ iteration.response }}\n"
        "Score: {{ iteration.score }}\n"
        "Feedback: {{ iteration.evaluation }}"
    )
    .build()
)
```

### Orchestrator-Workers Pattern

**YAML:**
```yaml
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: coordinator
      input: "Break down: {{project}}"
    worker_template:
      agent: worker
      tools: [python, http_get]
    reduce:
      agent: synthesizer
      input: "Combine results: {{ workers | join('\n') }}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("task-swarm")
    .runtime("openai", model="gpt-4o-mini")
    .agent("coordinator", "...")
    .agent("worker", "...")
    .agent("synthesizer", "...")
    .orchestrator_workers()
    .orchestrator("coordinator", "Break down: {{project}}")
    .worker_template("worker", tools=["python", "http_get"])
    .reduce_step("synthesizer", "Combine results: {{ workers | join('\\n') }}")
    .build()
)
```

## Advanced Features

### Agent Tool Configuration

```python
.agent(
    "developer",
    "You are a Python developer",
    tools=["python", "http_get"],           # Tool list
    temperature=0.9,                         # Override runtime temp
    max_tokens=4000,                         # Override runtime max_tokens
)
```

### Artifact Output Templates

```python
.artifact(
    "{{topic}}-report.md",                  # Path with variables
    "# {{topic}}\n\n{{ last_response }}"   # Jinja2 template
)
.artifact(
    "summary.json",
    '{"result": "{{ last_response | tojson }}"}'
)
```

### Runtime Budgets

```python
.runtime(
    "openai",
    model="gpt-4o-mini",
    budgets={
        "token_budget": {
            "max_input_tokens": 100000,
            "max_output_tokens": 20000,
        }
    }
)
```

### HITL Integration (Pattern-Specific)

Different patterns have pattern-specific HITL methods:

**Chain:**
```python
.chain()
.step("researcher", "Research {{topic}}")
.hitl("Review research before continuing", show="steps[0].response")
.step("writer", "Write article based on: {{ steps[0].response }}")
```

**Workflow:**
```python
.workflow()
.task("draft", "writer", "Draft {{topic}}")
.hitl_task("approval", "Approve draft?", show="tasks.draft.response")
.task("publish", "publisher", "Publish approved draft",
      depends_on=["approval"])
```

**Graph:**
```python
.graph()
.node("draft", "writer", "Draft {{topic}}")
.hitl_node("approval", "Approve draft?", show="nodes.draft.response")
.node("publish", "publisher", "Publish")
.edge("draft", "approval")
.edge("approval", "publish")
```

**Evaluator-Optimizer:**
```python
.evaluator_optimizer()
.producer("writer", "Write {{topic}}")
.evaluator("critic", "Rate: {{ iteration.response }}")
.review_gate("Review iteration {{ iteration.number }}")  # Between iterations
.accept(min_score=8, max_iterations=3)
```

**Orchestrator-Workers:**
```python
.orchestrator_workers()
.orchestrator("planner", "Plan {{project}}")
.decomposition_review("Review task breakdown")  # After orchestration
.worker_template("worker", tools=["python"])
.reduce_step("synthesizer", "Combine: {{ workers | join('\\n') }}")
.reduce_review("Review final output")  # Before reduce
```

## Error Handling

### BuildError - Validation Failures

The builder API fails fast with actionable errors:

```python
from strands_cli.api.exceptions import BuildError

try:
    workflow = (
        FluentBuilder("test")
        .runtime("openai", model="gpt-4o-mini")
        .chain()
        .step("undefined_agent", "Do something")  # Agent doesn't exist
        .build()
    )
except BuildError as e:
    print(e)
    # Output: Agent 'undefined_agent' not found.
    #         Use .agent('undefined_agent', ...) to define it.
```

**Common BuildError scenarios:**

1. **Missing agent definition:**
```python
# Error: Agent 'researcher' not found
.step("researcher", "Research {{topic}}")

# Fix: Define agent first
.agent("researcher", "You are a researcher")
.chain()
.step("researcher", "Research {{topic}}")
```

2. **Invalid provider:**
```python
# Error: Invalid provider 'azure'. Must be one of: {'bedrock', 'ollama', 'openai'}
.runtime("azure", model="gpt-4")

# Fix: Use valid provider
.runtime("openai", model="gpt-4o-mini")
```

3. **Circular dependencies (Workflow pattern):**
```python
# Error: Circular dependency detected: task_a -> task_b -> task_a
.workflow()
.task("task_a", "agent", "...", depends_on=["task_b"])
.task("task_b", "agent", "...", depends_on=["task_a"])

# Fix: Remove circular dependency
.task("task_a", "agent", "...")
.task("task_b", "agent", "...", depends_on=["task_a"])
```

4. **Invalid template syntax:**
```python
# Error: Invalid template syntax at line 1: unexpected '}'
.step("agent", "Process {{ unclosed")

# Fix: Close template variables
.step("agent", "Process {{ variable }}")
```

5. **Duplicate agent ID:**
```python
# Error: Agent 'researcher' already defined
.agent("researcher", "Prompt 1")
.agent("researcher", "Prompt 2")

# Fix: Use unique IDs
.agent("researcher_1", "Prompt 1")
.agent("researcher_2", "Prompt 2")
```

## Best Practices

### 1. Define Agents First

```python
# Good: All agents defined upfront
workflow = (
    FluentBuilder("analysis")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "...")
    .agent("analyst", "...")
    .agent("writer", "...")
    .chain()
    .step("researcher", "...")
    .step("analyst", "...")
    .step("writer", "...")
    .build()
)

# Avoid: Agents scattered throughout
workflow = (
    FluentBuilder("analysis")
    .runtime("openai", model="gpt-4o-mini")
    .chain()
    .agent("researcher", "...")  # Harder to track
    .step("researcher", "...")
    .agent("analyst", "...")
    .step("analyst", "...")
    .build()
)
```

### 2. Extract to Variables for Reuse

```python
# Define reusable agent configs
RESEARCHER_AGENT = {
    "id": "researcher",
    "prompt": "You are a thorough research assistant..."
}

ANALYST_AGENT = {
    "id": "analyst",
    "prompt": "You are a data analyst..."
}

# Build multiple workflows with same agents
def build_research_workflow(name: str, pattern_type: str):
    builder = (
        FluentBuilder(name)
        .runtime("openai", model="gpt-4o-mini")
        .agent(**RESEARCHER_AGENT)
        .agent(**ANALYST_AGENT)
    )
    
    if pattern_type == "chain":
        return builder.chain().step(...).build()
    elif pattern_type == "workflow":
        return builder.workflow().task(...).build()
```

### 3. Use Type Hints

```python
from strands_cli.api import FluentBuilder, Workflow

def create_analysis_workflow(topic: str) -> Workflow:
    """Create a research workflow for the given topic.
    
    Args:
        topic: Research topic
        
    Returns:
        Configured workflow ready to execute
    """
    return (
        FluentBuilder("research")
        .runtime("openai", model="gpt-4o-mini")
        .agent("researcher", "You are a researcher")
        .single_agent()
        .prompt("researcher", f"Research {topic}")
        .build()
    )
```

### 4. Validate Early in Development

```python
# Add validation during development
try:
    workflow = builder.build()
    print("✓ Workflow built successfully")
except BuildError as e:
    print(f"✗ Build failed: {e}")
    # Fix errors before proceeding
```

### 5. Use Async for High Performance

```python
import asyncio
from strands_cli.api import FluentBuilder

async def run_multiple_workflows():
    """Run multiple workflows concurrently."""
    workflow1 = FluentBuilder("wf1")...build()
    workflow2 = FluentBuilder("wf2")...build()
    
    # Run concurrently
    results = await asyncio.gather(
        workflow1.run_interactive_async(topic="AI"),
        workflow2.run_interactive_async(topic="ML"),
    )
    
    return results

# Execute
asyncio.run(run_multiple_workflows())
```

## Testing Workflows

### Unit Testing Builder Construction

```python
import pytest
from strands_cli.api import FluentBuilder
from strands_cli.api.exceptions import BuildError

def test_chain_builder_validates_agents():
    """Test that chain builder validates agent existence."""
    with pytest.raises(BuildError, match="Agent 'missing' not found"):
        (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .chain()
            .step("missing", "Do something")  # Undefined agent
            .build()
        )

def test_workflow_builder_detects_cycles():
    """Test circular dependency detection."""
    with pytest.raises(BuildError, match="Circular dependency"):
        (
            FluentBuilder("test")
            .runtime("openai", model="gpt-4o-mini")
            .agent("agent", "...")
            .workflow()
            .task("a", "agent", "...", depends_on=["b"])
            .task("b", "agent", "...", depends_on=["a"])
            .build()
        )
```

### Integration Testing with Mocks

```python
import pytest
from unittest.mock import AsyncMock, patch
from strands_cli.api import FluentBuilder

@pytest.mark.asyncio
async def test_workflow_execution():
    """Test workflow execution with mocked LLM."""
    workflow = (
        FluentBuilder("test")
        .runtime("openai", model="gpt-4o-mini")
        .agent("researcher", "You are a researcher")
        .chain()
        .step("researcher", "Research {{topic}}")
        .build()
    )
    
    # Mock LLM response
    mock_response = "Mocked research results"
    with patch("strands_cli.runtime.providers.OpenAIModel") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.invoke.return_value = mock_response
        mock_model.return_value = mock_instance
        
        result = await workflow.run_interactive_async(topic="AI")
        
        assert result.success
        assert result.last_response == mock_response
```

## Performance Considerations

### Agent Caching

Strands automatically caches agents with identical configurations:

```python
# Only creates ONE agent instance (same ID + config)
workflow = (
    FluentBuilder("test")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a researcher")
    .chain()
    .step("researcher", "Step 1")
    .step("researcher", "Step 2")  # Reuses cached agent
    .step("researcher", "Step 3")  # Reuses cached agent
    .build()
)
```

### Model Client Pooling

Model clients are pooled automatically:

```python
# Only creates ONE OpenAI client (same provider + model + region)
workflow = (
    FluentBuilder("test")
    .runtime("openai", model="gpt-4o-mini")
    .agent("agent1", "...", model_id="gpt-4o-mini")  # Same client
    .agent("agent2", "...", model_id="gpt-4o-mini")  # Same client
    .agent("agent3", "...", model_id="gpt-4o")       # Different client
    ...
)
```

## Next Steps

Now that you understand the builder API basics:

1. **Explore pattern-specific documentation:**
   - [Chain Builder Guide](../howto/patterns/chain.md)
   - [Workflow Builder Guide](../howto/patterns/workflow.md)
   - [Parallel Builder Guide](../howto/patterns/parallel.md)
   - [Graph Builder Guide](../howto/patterns/graph.md)
   - [Routing Builder Guide](../howto/patterns/routing.md)
   - [Evaluator-Optimizer Builder Guide](../howto/patterns/evaluator-optimizer.md)
   - [Orchestrator-Workers Builder Guide](../howto/patterns/orchestrator-workers.md)

2. **Study complete examples:**
   - Check `examples/api/` directory for runnable code
   - Compare with YAML equivalents in `examples/`

3. **Read API reference:**
   - [Builder API Reference](../reference/api/builders.md) - Complete method signatures

4. **Learn advanced techniques:**
   - [HITL Integration](../howto/hitl.md)
   - [Tool Development](../howto/develop-tools.md)
   - [Context Management](../howto/context-management.md)

## Troubleshooting

### "No module named 'strands_cli.api'"

Install strands-cli in development mode:

```bash
uv pip install -e .
```

### "BuildError: Invalid provider"

Check provider spelling (must be `bedrock`, `ollama`, or `openai`):

```python
# Wrong
.runtime("aws", model="...")

# Correct
.runtime("bedrock", model="...")
```

### "BuildError: Agent 'X' not found"

Define all agents before referencing them:

```python
# Wrong - agent used before definition
.chain()
.step("researcher", "...")
.agent("researcher", "...")

# Correct - agent defined first
.agent("researcher", "...")
.chain()
.step("researcher", "...")
```

### IDE Not Showing Autocomplete

Ensure your IDE's Python language server is configured:

**VS Code:**
```json
{
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.autoImportCompletions": true
}
```

**PyCharm:**
- Enable "Type checking" in Settings → Python → Type Checking

## Summary

The builder API provides:

✅ **Type-safe** workflow construction  
✅ **Fail-fast** validation with actionable errors  
✅ **Fluent** interfaces for all 7 patterns  
✅ **IDE support** with autocomplete and type hints  
✅ **Testable** workflow logic  
✅ **Refactorable** code with confidence  

**Key Takeaways:**

1. Start with `FluentBuilder(name)`
2. Configure runtime explicitly (no defaults)
3. Define all agents upfront
4. Select pattern with pattern-specific builder
5. Build and validate with `.build()`
6. Execute with `.run_interactive()` or `.run_interactive_async()`

Happy building! 🚀

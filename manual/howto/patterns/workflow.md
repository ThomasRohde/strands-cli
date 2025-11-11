---
title: Workflow Pattern
description: DAG-based parallel task execution with dependencies
keywords: workflow, pattern, dag, directed acyclic graph, parallel, dependencies, tasks
---

# Workflow Pattern

The Workflow pattern executes tasks as a Directed Acyclic Graph (DAG), enabling parallel execution of independent tasks while respecting dependencies. This is ideal for complex workflows where multiple tasks can run concurrently but some tasks depend on others completing first.

## When to Use

Use the Workflow pattern when you need to:

- Execute independent tasks concurrently for faster completion
- Define explicit task dependencies (task B waits for task A)
- Build complex multi-stage pipelines with parallel branches
- Optimize execution time by parallelizing independent work
- Maintain clear task relationships in complex workflows

## Basic Example

=== "YAML"

    ```yaml
    version: 0
    name: simple-workflow
    description: DAG-based research workflow

    runtime:
      provider: bedrock
      model: anthropic.claude-3-sonnet-20240229-v1:0
      max_parallel: 2  # Run up to 2 tasks concurrently

    agents:
      - id: researcher
        system: "You are a research assistant providing factual information."

    pattern:
      type: workflow
      config:
        tasks:
          # Root task - no dependencies
          - id: overview
            agent: researcher
            description: "Get high-level overview"
            input: "Provide a brief overview of {{ topic }}"

          # Parallel tasks - both depend on overview
          - id: technical
            agent: researcher
            deps: [overview]
            description: "Research technical aspects"
            input: |
              Overview: {{ tasks.overview.response }}

              Research the technical details of {{ topic }}

          - id: business
            agent: researcher
            deps: [overview]
            description: "Research business aspects"
            input: |
              Overview: {{ tasks.overview.response }}

              Research the business implications of {{ topic }}

          # Final task - depends on both parallel tasks
          - id: synthesis
            agent: researcher
            deps: [technical, business]
            description: "Synthesize findings"
            input: |
              Technical: {{ tasks.technical.response }}
              Business: {{ tasks.business.response }}

              Write a comprehensive report.

    inputs:
      topic:
        type: string
        description: "Research topic"
        default: "artificial intelligence"
    ```

=== "Builder API"

    ```python
    from strands_cli.api import FluentBuilder

    workflow = (
        FluentBuilder("simple-workflow")
        .description("DAG-based research workflow")
        .runtime("bedrock",
                 model="anthropic.claude-3-sonnet-20240229-v1:0",
                 max_parallel=2)
        .agent("researcher",
               "You are a research assistant providing factual information.")
        .workflow()
        # Root task - no dependencies
        .task("overview", "researcher",
              "Provide a brief overview of {{ topic }}")
        # Parallel tasks - both depend on overview
        .task("technical", "researcher",
              """Overview: {{ tasks.overview.response }}
              
              Research the technical details of {{ topic }}""",
              depends_on=["overview"])
        .task("business", "researcher",
              """Overview: {{ tasks.overview.response }}
              
              Research the business implications of {{ topic }}""",
              depends_on=["overview"])
        # Final task - depends on both parallel tasks
        .task("synthesis", "researcher",
              """Technical: {{ tasks.technical.response }}
              Business: {{ tasks.business.response }}
              
              Write a comprehensive report.""",
              depends_on=["technical", "business"])
        .build()
    )

    # Execute with topic variable
    result = workflow.run_interactive(topic="artificial intelligence")
    print(result.last_response)
    ```

## Task Dependencies

### No Dependencies (Root Tasks)

Tasks with no `deps` field execute immediately:

```yaml
tasks:
  - id: task1
    agent: researcher
    input: "Independent task 1"

  - id: task2
    agent: researcher
    input: "Independent task 2"  # Runs concurrently with task1
```

### Single Dependency

Task waits for one parent to complete:

```yaml
tasks:
  - id: research
    agent: researcher
    input: "Gather information"

  - id: analyze
    agent: analyst
    deps: [research]  # Waits for research to complete
    input: "Analyze: {{ tasks.research.response }}"
```

### Multiple Dependencies

Task waits for all parents to complete:

```yaml
tasks:
  - id: source1
    agent: researcher
    input: "Research source 1"

  - id: source2
    agent: researcher
    input: "Research source 2"

  - id: synthesis
    agent: analyst
    deps: [source1, source2]  # Waits for BOTH to complete
    input: |
      Source 1: {{ tasks.source1.response }}
      Source 2: {{ tasks.source2.response }}

      Synthesize both sources.
```

## Accessing Task Results

### Specific Task Outputs

Access any completed task by its ID:

```yaml
# Single task reference
input: "Build on: {{ tasks.overview.response }}"

# Multiple task references
input: |
  Technical: {{ tasks.technical.response }}
  Business: {{ tasks.business.response }}

  Combine both perspectives.
```

### Task Metadata

Access task status and metadata:

```yaml
outputs:
  artifacts:
    - path: "report.md"
      content: |
        ## Technical Analysis
        Status: {{ tasks.technical.status }}
        {{ tasks.technical.response }}
```

### Iterating Over Tasks

Loop through completed tasks:

```yaml
input: |
  Review all completed tasks:
  {% for task_id, task in tasks.items() %}
  {{ task_id }}: {{ task.response | truncate(100) }}
  {% endfor %}
```

## Parallel Execution

### Controlling Concurrency

Limit concurrent task execution:

```yaml
runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  max_parallel: 3  # Maximum 3 tasks running simultaneously
```

Without `max_parallel`, all independent tasks run concurrently.

### Example: Fan-Out/Fan-In

```yaml
tasks:
  # Single source task
  - id: source
    agent: researcher
    input: "Research {{ topic }}"

  # Fan-out: Multiple parallel tasks
  - id: aspect1
    agent: analyst
    deps: [source]
    input: "Analyze aspect 1: {{ tasks.source.response }}"

  - id: aspect2
    agent: analyst
    deps: [source]
    input: "Analyze aspect 2: {{ tasks.source.response }}"

  - id: aspect3
    agent: analyst
    deps: [source]
    input: "Analyze aspect 3: {{ tasks.source.response }}"

  # Fan-in: Single synthesis task
  - id: synthesis
    agent: writer
    deps: [aspect1, aspect2, aspect3]
    input: |
      Aspect 1: {{ tasks.aspect1.response }}
      Aspect 2: {{ tasks.aspect2.response }}
      Aspect 3: {{ tasks.aspect3.response }}

      Synthesize all aspects.
```

## DAG Execution Order

The workflow executor:

1. Identifies root tasks (no dependencies)
2. Executes root tasks (up to `max_parallel` concurrently)
3. As tasks complete, checks which dependent tasks can now run
4. Continues until all tasks complete

### Example Execution Timeline

```yaml
tasks:
  - id: A          # Starts at t=0
  - id: B          # Starts at t=0 (parallel with A)
  - id: C
    deps: [A]      # Starts when A completes
  - id: D
    deps: [A, B]   # Starts when BOTH A and B complete
  - id: E
    deps: [C, D]   # Starts when BOTH C and D complete
```

Timeline:
```
t=0:  A and B start (parallel)
t=5:  A completes → C starts
t=7:  B completes → D starts (A already done)
t=10: C completes
t=12: D completes → E starts (C and D both done)
t=15: E completes
```

## Advanced Features

### Task Descriptions

Provide human-readable descriptions for logging:

```yaml
tasks:
  - id: research
    agent: researcher
    description: "Gather initial data about the topic"  # Shown in logs
    input: "Research {{ topic }}"
```

### Conditional Task Content

Use Jinja2 conditionals in task inputs:

```yaml
tasks:
  - id: synthesis
    agent: writer
    deps: [research, analysis]
    input: |
      {% if tasks.research.response | length > 500 %}
      Research (truncated): {{ tasks.research.response | truncate(200) }}
      {% else %}
      Research: {{ tasks.research.response }}
      {% endif %}

      Analysis: {{ tasks.analysis.response }}

      Write a summary.
```

### Different Agents Per Task

Assign specialized agents to different tasks:

```yaml
agents:
  - id: researcher
    system: "You research topics thoroughly."

  - id: analyst
    system: "You analyze data critically."

  - id: writer
    system: "You write clear reports."

tasks:
  - id: gather
    agent: researcher
    input: "Research {{ topic }}"

  - id: analyze
    agent: analyst
    deps: [gather]
    input: "Analyze: {{ tasks.gather.response }}"

  - id: report
    agent: writer
    deps: [analyze]
    input: "Write report: {{ tasks.analyze.response }}"
```

## Error Handling

### Task Failure Behavior

If a task fails:
- Tasks depending on it will not execute
- Independent tasks continue executing
- Workflow fails with partial results

### Retry Configuration

Configure retries at the runtime level:

```yaml
runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  failure_policy:
    retries: 3
    backoff: exponential
```

Each task gets up to 3 retry attempts before failing.

### Budget Limits

Prevent runaway workflows:

```yaml
runtime:
  budgets:
    max_tasks: 20           # Maximum total tasks
    max_tokens: 100000      # Maximum total tokens
    max_duration_s: 600     # Maximum 10 minutes
```

## Output Artifacts

### Accessing Task Results

Save workflow results to files:

```yaml
outputs:
  artifacts:
    - path: "research_report.md"
      content: |
        # {{ topic | title }} Report

        ## Overview
        {{ tasks.overview.response }}

        ## Technical Analysis
        {{ tasks.technical.response }}

        ## Business Analysis
        {{ tasks.business.response }}

        ## Synthesis
        {{ tasks.synthesis.response }}
```

### Using Last Response

The `last_response` variable contains the final task's output:

```yaml
outputs:
  artifacts:
    - path: "summary.txt"
      content: "{{ last_response }}"
```

## Best Practices

### 1. Design for Parallelism

Identify independent tasks that can run concurrently:

```yaml
# Good - parallel research branches
tasks:
  - id: source
    agent: researcher
    input: "Overview of {{ topic }}"

  - id: tech
    agent: researcher
    deps: [source]
    input: "Technical aspects"

  - id: business
    agent: researcher
    deps: [source]
    input: "Business aspects"  # Parallel with tech

# Avoid - unnecessary sequential execution
tasks:
  - id: step1
    agent: researcher
    input: "Research A"

  - id: step2
    agent: researcher
    deps: [step1]  # Only depends if actually needs step1 output
    input: "Research B"  # If independent, remove deps
```

### 2. Set Appropriate max_parallel

Balance speed and resource usage:

```yaml
# For I/O-bound tasks (API calls, web research)
runtime:
  max_parallel: 10  # Higher parallelism acceptable

# For compute-intensive tasks
runtime:
  max_parallel: 3   # Lower to avoid overload
```

### 3. Use Descriptive Task IDs

Make task IDs meaningful:

```yaml
# Good - clear purpose
tasks:
  - id: market_research
  - id: competitor_analysis
  - id: swot_synthesis

# Avoid - generic IDs
tasks:
  - id: task1
  - id: task2
  - id: task3
```

### 4. Validate DAG Structure

Ensure no circular dependencies:

```yaml
# Invalid - circular dependency
tasks:
  - id: A
    deps: [B]
  - id: B
    deps: [A]  # Error: cycle detected
```

Strands validates DAG structure at load time.

### 5. Manage Context Size

Truncate large task outputs when passing to dependent tasks:

```yaml
tasks:
  - id: large_research
    agent: researcher
    input: "Comprehensive research on {{ topic }}"

  - id: summary
    agent: writer
    deps: [large_research]
    input: |
      Research (truncated):
      {{ tasks.large_research.response | truncate(500) }}

      Summarize key points.
```

## Common Patterns

### Linear Pipeline (Sequential)

```yaml
tasks:
  - id: collect
    agent: researcher
    input: "Collect data"

  - id: analyze
    agent: analyst
    deps: [collect]
    input: "Analyze: {{ tasks.collect.response }}"

  - id: recommend
    agent: advisor
    deps: [analyze]
    input: "Recommend: {{ tasks.analyze.response }}"
```

### Diamond Pattern

```yaml
tasks:
  - id: source
    agent: researcher
    input: "Research {{ topic }}"

  - id: left
    agent: analyst
    deps: [source]
    input: "Left analysis"

  - id: right
    agent: analyst
    deps: [source]
    input: "Right analysis"

  - id: merge
    agent: writer
    deps: [left, right]
    input: "Merge both analyses"
```

### Multi-Stage Pipeline

```yaml
tasks:
  # Stage 1: Research
  - id: research1
    agent: researcher
    input: "Research aspect 1"

  - id: research2
    agent: researcher
    input: "Research aspect 2"

  # Stage 2: Analysis (depends on all research)
  - id: analysis1
    agent: analyst
    deps: [research1, research2]
    input: "Analyze technical"

  - id: analysis2
    agent: analyst
    deps: [research1, research2]
    input: "Analyze business"

  # Stage 3: Synthesis (depends on all analysis)
  - id: synthesis
    agent: writer
    deps: [analysis1, analysis2]
    input: "Synthesize all findings"
```

## Performance Considerations

### Task Scheduling Overhead

Workflow pattern has scheduling overhead for dependency resolution:

- Small workflows (< 5 tasks): Minimal overhead
- Large workflows (> 20 tasks): ~100-200ms scheduling overhead
- Consider using Chain pattern for simple sequential workflows

### Agent Caching

Strands automatically caches agents with identical configurations:

```yaml
agents:
  - id: researcher
    system: "You are a researcher"

tasks:
  - id: task1
    agent: researcher  # Agent built here
  - id: task2
    agent: researcher  # Cached - no rebuild
  - id: task3
    agent: researcher  # Cached - no rebuild
```

This provides ~90% overhead reduction for repeated agent use.

### Optimal Parallelism

The workflow executor efficiently schedules tasks:

```yaml
# Optimal: 3 parallel branches, max_parallel=3
runtime:
  max_parallel: 3

tasks:
  - id: source
    agent: researcher
    input: "Research"
  - id: branch1
    agent: analyst
    deps: [source]
    input: "Branch 1"
  - id: branch2
    agent: analyst
    deps: [source]
    input: "Branch 2"
  - id: branch3
    agent: analyst
    deps: [source]
    input: "Branch 3"
```

All three branches execute concurrently after source completes.

## Troubleshooting

### Workflow Not Completing

Check for circular dependencies:

```bash
strands validate workflow.yaml
```

Look for:
```
Validation Error: Circular dependency detected in workflow DAG
```

### Tasks Not Running in Parallel

Verify dependencies are correct:

```yaml
# Check that tasks don't have unnecessary deps
tasks:
  - id: task1
    agent: researcher
    input: "Independent task 1"

  - id: task2
    agent: researcher
    # No deps = can run parallel with task1
    input: "Independent task 2"
```

Enable debug logging:

```bash
strands run workflow.yaml --debug --verbose
```

### Budget Exceeded

Increase budget limits or reduce task count:

```yaml
runtime:
  budgets:
    max_tasks: 30        # Increase from default
    max_tokens: 200000   # Increase token budget
```

### Task Failures

Check task-level errors:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Task 'task_id' failed: <error message>
Dependent tasks ['dep1', 'dep2'] will not execute
```

## Workflow vs. Other Patterns

### Workflow vs. Chain

Use Workflow when tasks can run in parallel:

```yaml
# Chain: 30 seconds total (sequential)
pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research A"  # 10s
      - agent_id: researcher
        prompt: "Research B"  # 10s
      - agent_id: researcher
        prompt: "Research C"  # 10s

# Workflow: 10 seconds total (parallel)
pattern:
  type: workflow
  config:
    tasks:
      - id: research_a
        agent: researcher
        input: "Research A"  # 10s
      - id: research_b
        agent: researcher
        input: "Research B"  # 10s (concurrent)
      - id: research_c
        agent: researcher
        input: "Research C"  # 10s (concurrent)
```

### Workflow vs. Parallel

Workflow supports dependencies, Parallel does not:

```yaml
# Workflow: Tasks can depend on each other
pattern:
  type: workflow
  config:
    tasks:
      - id: source
        agent: researcher
        input: "Research"
      - id: analysis
        agent: analyst
        deps: [source]  # Waits for source
        input: "{{ tasks.source.response }}"

# Parallel: All branches independent
pattern:
  type: parallel
  config:
    branches:
      - id: branch1
        steps: [...]  # No dependencies between branches
      - id: branch2
        steps: [...]
```

Use Parallel for simpler scenarios with no inter-branch dependencies.

## Examples

Complete examples in the repository:

- `examples/workflow-parallel-research.yaml` - Fan-out/fan-in research
- `examples/workflow-linear-dag.yaml` - Sequential pipeline
- `examples/multi-task-workflow.yaml` - Complex multi-stage workflow

## See Also

- [Chain Pattern](chain.md) - For sequential execution
- [Parallel Pattern](parallel.md) - For simpler concurrent execution
- [Graph Pattern](graph.md) - For conditional control flow
- [Run Workflows](../run-workflows.md) - Execution guide
- [Context Management](../context-management.md) - Managing task context

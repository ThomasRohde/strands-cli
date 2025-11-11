# Orchestrator-Workers Pattern

The Orchestrator-Workers pattern implements dynamic task delegation where an orchestrator agent breaks down complex work into subtasks, delegates them to worker agents running in parallel, aggregates results, and optionally produces a final writeup. This is ideal for research swarms, data processing pipelines, and collaborative multi-agent workflows.

## When to Use

Use the Orchestrator-Workers pattern when you need to:

- Break down complex tasks into parallel subtasks dynamically
- Delegate work to specialized worker agents
- Process large datasets with distributed workers
- Aggregate results from multiple concurrent workers
- Implement research swarms or collaborative agent teams
- Scale work distribution based on task complexity

## Basic Example

=== "YAML"

    ```yaml
    version: 0
    name: simple-orchestrator
    description: Research swarm with dynamic task delegation

    runtime:
      provider: bedrock
      model: anthropic.claude-3-sonnet-20240229-v1:0

    agents:
      - id: orchestrator
        system: |
          You break down research topics into specific subtasks.
          Respond with JSON array: [{"task": "subtask 1"}, {"task": "subtask 2"}]

      - id: researcher
        system: "You are a research specialist. Conduct thorough research."

      - id: synthesizer
        system: "You aggregate research from multiple sources."

    pattern:
      type: orchestrator_workers
      config:
        orchestrator:
          agent: orchestrator
          limits:
            max_workers: 3
            max_rounds: 1

        worker_template:
          agent: researcher

        reduce:
          agent: synthesizer
          input: "Aggregate findings from all workers"

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
        FluentBuilder("simple-orchestrator")
        .description("Research swarm with dynamic task delegation")
        .runtime("bedrock",
                 model="anthropic.claude-3-sonnet-20240229-v1:0")
        .agent("orchestrator",
               """You break down research topics into specific subtasks.
               Respond with JSON array: [{"task": "subtask 1"}, {"task": "subtask 2"}]""")
        .agent("researcher",
               "You are a research specialist. Conduct thorough research.")
        .agent("synthesizer",
               "You aggregate research from multiple sources.")
        .orchestrator_workers()
        .orchestrator("orchestrator", "Break down research on {{ topic }}")
        .limits(max_workers=3, timeout_per_worker=300)
        .worker_template("researcher")
        .reduce_step("synthesizer",
                     """Aggregate findings from all workers:
                     {% for result in workers %}
                     - {{ result }}
                     {% endfor %}""")
        .build()
    )

    # Execute with topic variable
    result = workflow.run_interactive(topic="artificial intelligence")
    print(result.last_response)
    ```

## Pattern Components

### Orchestrator Configuration

The orchestrator creates tasks for workers:

```yaml
orchestrator:
  agent: orchestrator
  limits:
    max_workers: 3   # Maximum concurrent workers
    max_rounds: 1    # Maximum delegation rounds
```

**Critical**: Orchestrator must return JSON array of tasks:

```json
[
  {"task": "Research technical aspects"},
  {"task": "Research business implications"},
  {"task": "Research ethical considerations"}
]
```

### Worker Template

Defines how workers execute tasks:

```yaml
worker_template:
  agent: researcher
  tools: []  # Optional: Tools available to workers
```

Each task from the orchestrator spawns a worker using this template.

### Reduce Step

Aggregates worker results:

```yaml
reduce:
  agent: synthesizer
  input: |
    Synthesize findings from {{ workers | length }} workers:

    {% for worker in workers %}
    Worker {{ loop.index }}: {{ worker.response }}
    {% endfor %}
```

The reduce step executes after all workers complete.

### Writeup Step (Optional)

Creates final report from aggregated results:

```yaml
writeup:
  agent: writer
  input: |
    Synthesis: {{ reduce_response }}

    Create executive summary report.
```

## Orchestrator Output

### Task Array Format

Orchestrator must return JSON array:

```yaml
# Valid orchestrator output
[
  {"task": "Research aspect 1"},
  {"task": "Research aspect 2"},
  {"task": "Research aspect 3"}
]
```

Each object must have a `task` field. Additional fields are passed to workers.

### Dynamic Task Count

Orchestrator determines how many workers to spawn:

```yaml
# Orchestrator can create 1-10 tasks dynamically
[
  {"task": "Task 1"},
  {"task": "Task 2"}
  # ... up to max_workers tasks
]
```

The `max_workers` limit controls maximum concurrent workers.

### Task Metadata

Include additional metadata in tasks:

```yaml
# Orchestrator output with metadata
[
  {"task": "Research A", "priority": "high", "depth": "detailed"},
  {"task": "Research B", "priority": "medium", "depth": "brief"}
]
```

Workers can access metadata in their prompts.

## Worker Execution

### Worker Input Template

Workers receive orchestrator tasks:

```yaml
worker_template:
  agent: researcher
  # Implicit input: "{{ task }}"
```

Default worker input is the `task` field from orchestrator output.

### Custom Worker Input

Customize worker prompts:

```yaml
orchestrator:
  agent: orchestrator
  task_prompt_template: |
    Assigned task: {{ task }}
    Priority: {{ priority | default('normal') }}

    Execute this research task thoroughly.
```

Access task metadata in template.

### Worker Tools

Provide tools to workers:

```yaml
worker_template:
  agent: researcher
  tools:
    - http_executors  # Enable web research
```

## Accessing Results

### Workers Array

Access all worker results in reduce step:

```yaml
reduce:
  agent: synthesizer
  input: |
    Findings from {{ workers | length }} workers:

    {% for worker in workers %}
    Worker {{ loop.index }}:
    Task: {{ worker.task }}
    Result: {{ worker.response }}
    {% endfor %}
```

### Reduce Response

Access aggregated results in writeup:

```yaml
writeup:
  agent: writer
  input: |
    Aggregated findings:
    {{ reduce_response }}

    Create final report.
```

### Worker Metadata

Access worker task metadata:

```yaml
reduce:
  agent: synthesizer
  input: |
    {% for worker in workers %}
    Task: {{ worker.task }}
    Priority: {{ worker.priority }}
    Result: {{ worker.response }}
    {% endfor %}
```

## Multi-Round Delegation

### Multiple Rounds

Orchestrator can delegate multiple times:

```yaml
orchestrator:
  agent: orchestrator
  limits:
    max_workers: 3
    max_rounds: 2  # Two delegation rounds
```

Round 1 workers complete, then Round 2 workers execute.

### Round-Aware Orchestration

Orchestrator sees previous round results:

```yaml
agents:
  - id: orchestrator
    system: |
      Round 1: Break down topic into subtasks
      Round 2: Based on results, identify gaps and create follow-up tasks

      Respond with JSON array of tasks.
```

### Accessing Round Results

In reduce step, access all rounds:

```yaml
reduce:
  agent: synthesizer
  input: |
    Round 1 workers: {{ round_1_workers | length }}
    Round 2 workers: {{ round_2_workers | length }}

    All findings:
    {% for worker in workers %}
    {{ worker.response }}
    {% endfor %}
```

## Advanced Features

### Limiting Concurrency

Control parallel worker execution:

```yaml
orchestrator:
  agent: orchestrator
  limits:
    max_workers: 5  # Process max 5 tasks concurrently
```

If orchestrator creates 10 tasks and max_workers=5, workers execute in batches of 5.

### Dynamic Orchestration

Orchestrator adapts based on input:

```yaml
agents:
  - id: orchestrator
    system: |
      Analyze topic complexity: {{ topic }}

      For simple topics: Create 2-3 tasks
      For complex topics: Create 4-6 tasks

      Return JSON array of tasks.
```

### Specialized Workers

Use different worker types:

```yaml
agents:
  - id: technical_researcher
    system: "Technical research specialist"

  - id: business_researcher
    system: "Business analysis specialist"

worker_template:
  agent: "{{ worker_type | default('technical_researcher') }}"
```

## Error Handling

### Worker Failure

If a worker fails:
- Other workers continue executing
- Failed worker excluded from reduce step
- Workflow succeeds with partial results

### Orchestrator Failure

If orchestrator returns invalid JSON:

```bash
Error: Orchestrator response is not valid JSON
Expected: [{"task": "..."}, ...]
Received: "Create three research tasks"
```

Fix: Enforce JSON output in orchestrator system prompt.

### Budget Limits

Prevent runaway orchestration:

```yaml
runtime:
  budgets:
    max_steps: 50          # Maximum total steps
    max_tokens: 200000     # Maximum total tokens
    max_duration_s: 600    # Maximum 10 minutes
```

## Output Artifacts

### Using Writeup

Save final report:

```yaml
outputs:
  artifacts:
    - path: "final_report.md"
      content: "{{ last_response }}"  # From writeup step
```

### Using Reduce

Save aggregated results:

```yaml
outputs:
  artifacts:
    - path: "aggregated_findings.md"
      content: "{{ reduce_response }}"
```

### Using Worker Results

Access individual worker outputs:

```yaml
outputs:
  artifacts:
    - path: "all_findings.md"
      content: |
        # Research Findings

        {% for worker in workers %}
        ## Worker {{ loop.index }}
        Task: {{ worker.task }}

        {{ worker.response }}
        {% endfor %}

        ## Synthesis
        {{ reduce_response }}
```

## Best Practices

### 1. Clear Orchestrator Instructions

Provide explicit task breakdown guidance:

```yaml
agents:
  - id: orchestrator
    system: |
      You are a research orchestrator.

      Break down "{{ topic }}" into {{ num_perspectives }} distinct subtasks.
      Each subtask should focus on a different aspect or perspective.

      Respond with ONLY a JSON array:
      [{"task": "Research aspect 1"}, {"task": "Research aspect 2"}, ...]
```

### 2. Validate Orchestrator Output

Ensure orchestrator returns valid JSON array:

```yaml
# Good - valid JSON array
[
  {"task": "Research technical aspects"},
  {"task": "Research business aspects"}
]

# Bad - invalid format
"Create tasks for technical and business research"

# Bad - not an array
{"task": "Research everything"}
```

### 3. Set Appropriate Worker Limits

Balance speed and resource usage:

```yaml
# For I/O-bound tasks (research, web scraping)
limits:
  max_workers: 10  # Higher concurrency acceptable

# For compute-intensive tasks
limits:
  max_workers: 3   # Lower to avoid overload
```

### 4. Use Reduce for Aggregation

Always include reduce step for synthesis:

```yaml
# Good - synthesized output
config:
  orchestrator: {...}
  worker_template: {...}
  reduce:
    agent: synthesizer
    input: "Aggregate all findings"

# Avoid - no synthesis
config:
  orchestrator: {...}
  worker_template: {...}
  # Missing reduce step
```

### 5. Monitor Worker Distribution

Track task distribution:

```yaml
reduce:
  agent: synthesizer
  input: |
    Workers spawned: {{ workers | length }}
    Max workers: {{ max_workers }}
    Rounds: {{ round_count }}

    Findings: ...
```

## Common Patterns

### Research Swarm

```yaml
orchestrator:
  agent: research_planner
  limits:
    max_workers: 3
    max_rounds: 1

worker_template:
  agent: researcher
  tools:
    - http_executors

reduce:
  agent: synthesizer
  input: "Synthesize all research findings"

writeup:
  agent: report_writer
  input: "Create executive summary from synthesis"
```

### Data Processing Pipeline

```yaml
orchestrator:
  agent: task_planner
  limits:
    max_workers: 5
    max_rounds: 1

worker_template:
  agent: data_analyst

reduce:
  agent: aggregator
  input: "Aggregate analysis from all workers"
```

### Parallel Code Review

```yaml
orchestrator:
  agent: code_splitter
  limits:
    max_workers: 4
    max_rounds: 1

worker_template:
  agent: code_reviewer

reduce:
  agent: review_aggregator
  input: "Consolidate all code review findings"

writeup:
  agent: summary_writer
  input: "Create review summary with action items"
```

## Performance Considerations

### Orchestrator Overhead

The orchestrator adds one initial invocation:

```
Total time = Orchestrator time + Max(worker times) + Reduce time + Writeup time
           ≈ 2s + Worker execution + 2s + 2s
```

### Worker Parallelism

Workers execute in parallel up to max_workers:

```yaml
# 6 tasks, max_workers=3
Batch 1: Workers 1, 2, 3 (parallel) - 10s
Batch 2: Workers 4, 5, 6 (parallel) - 10s
Total: 20s

# 6 tasks, max_workers=6
All workers (parallel) - 10s
Total: 10s
```

### Agent Caching

Workers use cached agents:

```yaml
worker_template:
  agent: researcher  # Agent built once, reused for all workers
```

## Troubleshooting

### Orchestrator Not Returning JSON

Check orchestrator output:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Orchestrator response: "Break this into three tasks"
Error: Invalid JSON from orchestrator
```

Fix: Enforce JSON-only output in system prompt.

### Too Many Workers Created

If orchestrator creates more tasks than expected:

```yaml
orchestrator:
  limits:
    max_workers: 3  # Hard limit on concurrent workers
```

Workers beyond limit queue and execute in batches.

### Workers Not Completing

Enable debug logging:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Worker 1: Completed
Worker 2: Failed - <error>
Worker 3: Completed
```

Failed workers are excluded from reduce step.

### Reduce Step Failing

Ensure at least one worker succeeds:

```
Reduce step requires at least one successful worker
All workers failed - reduce step skipped
```

## Orchestrator-Workers vs. Other Patterns

### vs. Parallel

Orchestrator-Workers has dynamic task creation, Parallel has static branches:

```yaml
# Orchestrator-Workers: Dynamic tasks
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: planner  # AI creates tasks dynamically

# Parallel: Static branches
pattern:
  type: parallel
  config:
    branches:
      - id: branch1  # Predefined branches
      - id: branch2
```

### vs. Workflow

Orchestrator-Workers delegates dynamically, Workflow has fixed DAG:

```yaml
# Orchestrator-Workers: Dynamic delegation
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: planner  # Creates tasks at runtime

# Workflow: Fixed tasks
pattern:
  type: workflow
  config:
    tasks:
      - id: task1   # Predefined tasks
      - id: task2
```

## Examples

Complete examples in the repository:

- `examples/orchestrator-research-swarm-openai.yaml` - Research team collaboration
- `examples/orchestrator-data-processing-openai.yaml` - Data processing pipeline
- `examples/orchestrator-minimal-openai.yaml` - Basic orchestrator pattern

## See Also

- [Parallel Pattern](parallel.md) - For static concurrent branches
- [Workflow Pattern](workflow.md) - For DAG-based execution
- [Chain Pattern](chain.md) - For sequential execution
- [Run Workflows](../run-workflows.md) - Execution guide

---
title: Parallel Pattern
description: Concurrent branch execution with optional reduce step
keywords: parallel, pattern, concurrent, branches, reduce, fan-out, fan-in
---

# Parallel Pattern

The Parallel pattern executes multiple independent branches concurrently, with an optional reduce step to aggregate results. This is ideal for scenarios where you need to perform similar operations on different data or gather multiple perspectives simultaneously.

## When to Use

Use the Parallel pattern when you need to:

- Execute independent tasks concurrently for faster completion
- Gather multiple perspectives or analyses simultaneously
- Process different data sources in parallel
- Perform the same operation on multiple inputs
- Aggregate concurrent results into a single output

## Basic Example

=== "YAML"

    ```yaml
    version: 0
    name: simple-parallel
    description: Parallel research on two aspects

    runtime:
      provider: bedrock
      model: anthropic.claude-3-sonnet-20240229-v1:0

    agents:
      - id: researcher
        system: "You are a research assistant providing factual information."

    pattern:
      type: parallel
      config:
        branches:
          - id: technical
            steps:
              - agent: researcher
                input: "Research technical aspects of {{ topic }}"

          - id: business
            steps:
              - agent: researcher
                input: "Research business aspects of {{ topic }}"

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
        FluentBuilder("simple-parallel")
        .description("Parallel research on two aspects")
        .runtime("bedrock",
                 model="anthropic.claude-3-sonnet-20240229-v1:0")
        .agent("researcher",
               "You are a research assistant providing factual information.")
        .parallel()
        .branch("technical")
            .step("researcher", "Research technical aspects of {{ topic }}")
            .done()
        .branch("business")
            .step("researcher", "Research business aspects of {{ topic }}")
            .done()
        .build()
    )

    # Execute with topic variable
    result = workflow.run_interactive(topic="artificial intelligence")
    print(result.last_response)
    ```

## Branch Configuration

### Simple Branches

Each branch executes independently:

```yaml
branches:
  - id: branch1
    steps:
      - agent: researcher
        input: "Research aspect 1"

  - id: branch2
    steps:
      - agent: researcher
        input: "Research aspect 2"

  - id: branch3
    steps:
      - agent: researcher
        input: "Research aspect 3"
```

All branches start simultaneously.

### Multi-Step Branches

Branches can have multiple sequential steps:

```yaml
branches:
  - id: comprehensive_research
    steps:
      - agent: researcher
        input: "Gather data about {{ topic }}"

      - agent: analyst
        input: |
          Data: {{ last_response }}

          Analyze key points.

      - agent: writer
        input: |
          Analysis: {{ last_response }}

          Write summary.
```

Within a branch, steps execute sequentially. Across branches, execution is concurrent.

## Accessing Branch Results

### Specific Branch Outputs

Access any branch result by its ID:

```yaml
# In reduce step or artifacts
content: |
  Technical: {{ branches.technical.response }}
  Business: {{ branches.business.response }}
```

### Branch Metadata

Access branch status and metadata:

```yaml
content: |
  ## Technical Research
  Status: {{ branches.technical.status }}
  {{ branches.technical.response }}
```

### Iterating Over Branches

Loop through all branch results:

```yaml
content: |
  # All Research Findings

  {% for branch_id, branch in branches.items() %}
  ## {{ branch_id | title }}
  {{ branch.response }}
  {% endfor %}
```

## Reduce Step

### Basic Reduction

Aggregate all branch results:

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: aspect1
        steps: [...]

      - id: aspect2
        steps: [...]

      - id: aspect3
        steps: [...]

    reduce:
      agent: synthesizer
      input: |
        Synthesize these findings:

        Aspect 1: {{ branches.aspect1.response }}
        Aspect 2: {{ branches.aspect2.response }}
        Aspect 3: {{ branches.aspect3.response }}
```

The reduce step executes after all branches complete.

### Accessing All Branches in Reduce

Use template iteration:

```yaml
reduce:
  agent: synthesizer
  input: |
    Combine all research perspectives:

    {% for branch_id, branch in branches.items() %}
    {{ branch_id }}: {{ branch.response }}
    {% endfor %}

    Create unified analysis.
```

### Workers Array

Access branch results as an array:

```yaml
reduce:
  agent: synthesizer
  input: |
    Findings from {{ workers | length }} branches:

    {% for worker in workers %}
    Branch {{ loop.index }}: {{ worker.response }}
    {% endfor %}
```

## Advanced Features

### Different Agents Per Branch

Assign specialized agents to different branches:

```yaml
agents:
  - id: tech_expert
    system: "You are a technical expert."

  - id: business_analyst
    system: "You are a business analyst."

  - id: market_researcher
    system: "You are a market researcher."

  - id: synthesizer
    system: "You synthesize multiple perspectives."

branches:
  - id: technical
    steps:
      - agent: tech_expert
        input: "Technical analysis of {{ topic }}"

  - id: business
    steps:
      - agent: business_analyst
        input: "Business analysis of {{ topic }}"

  - id: market
    steps:
      - agent: market_researcher
        input: "Market analysis of {{ topic }}"

reduce:
  agent: synthesizer
  input: "Synthesize all analyses"
```

### Branch-Specific Variables

Pass different variables to different branches:

```yaml
branches:
  - id: detailed
    steps:
      - agent: researcher
        input: "Research {{ topic }}"
        vars:
          depth: "comprehensive"
          max_length: 1000

  - id: summary
    steps:
      - agent: researcher
        input: "Research {{ topic }}"
        vars:
          depth: "brief"
          max_length: 200
```

### Conditional Content in Branches

Use Jinja2 conditionals:

```yaml
branches:
  - id: analysis
    steps:
      - agent: analyst
        input: |
          {% if include_technical %}
          Include technical details for {{ topic }}
          {% else %}
          Provide high-level overview of {{ topic }}
          {% endif %}
```

## Without Reduce Step

### Parallel Execution Only

Omit the reduce step to run branches without aggregation:

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: branch1
        steps: [...]

      - id: branch2
        steps: [...]

    # No reduce step - just parallel execution
```

The `last_response` will be from the last branch to complete (non-deterministic).

### Accessing Results

Use branch-specific outputs in artifacts:

```yaml
outputs:
  artifacts:
    - path: "technical_report.md"
      content: "{{ branches.technical.response }}"

    - path: "business_report.md"
      content: "{{ branches.business.response }}"

    - path: "combined_report.md"
      content: |
        # Combined Report

        ## Technical
        {{ branches.technical.response }}

        ## Business
        {{ branches.business.response }}
```

## Error Handling

### Branch Failure Behavior

If a branch fails:
- Other branches continue executing
- Failed branch is excluded from reduce step
- Workflow succeeds with partial results (unless all branches fail)

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

Each step in each branch gets retry attempts.

### Budget Limits

Prevent runaway parallel workflows:

```yaml
runtime:
  budgets:
    max_steps: 20           # Maximum steps across all branches
    max_tokens: 100000      # Maximum total tokens
    max_duration_s: 600     # Maximum 10 minutes
```

## Output Artifacts

### Using Branch Results

Save individual branch outputs:

```yaml
outputs:
  artifacts:
    - path: "{{ topic }}_technical.md"
      content: "{{ branches.technical.response }}"

    - path: "{{ topic }}_business.md"
      content: "{{ branches.business.response }}"
```

### Using Reduced Result

Save the synthesized output:

```yaml
outputs:
  artifacts:
    - path: "{{ topic }}_synthesis.md"
      content: "{{ last_response }}"  # From reduce step
```

### Combined Artifacts

Include both individual and synthesized results:

```yaml
outputs:
  artifacts:
    - path: "complete_analysis.md"
      content: |
        # {{ topic | title }} Analysis

        ## Technical Perspective
        {{ branches.technical.response }}

        ## Business Perspective
        {{ branches.business.response }}

        ## Market Perspective
        {{ branches.market.response }}

        ## Synthesis
        {{ last_response }}
```

## Best Practices

### 1. Ensure Branch Independence

Branches should not depend on each other's results:

```yaml
# Good - independent branches
branches:
  - id: source1
    steps:
      - agent: researcher
        input: "Research source 1 about {{ topic }}"

  - id: source2
    steps:
      - agent: researcher
        input: "Research source 2 about {{ topic }}"

# Avoid - branch2 depends on branch1 (use Workflow pattern instead)
branches:
  - id: research
    steps:
      - agent: researcher
        input: "Research {{ topic }}"

  - id: analysis
    steps:
      - agent: analyst
        input: "Analyze {{ branches.research.response }}"  # Won't work!
```

If branches need to share results, use the Workflow pattern instead.

### 2. Use Descriptive Branch IDs

Make branch IDs meaningful:

```yaml
# Good - clear purpose
branches:
  - id: academic_perspective
  - id: industry_perspective
  - id: regulatory_perspective

# Avoid - generic IDs
branches:
  - id: branch1
  - id: branch2
  - id: branch3
```

### 3. Balance Branch Count

More branches = faster completion but higher resource usage:

```yaml
# Fast but resource-intensive (10 concurrent API calls)
branches:
  - id: perspective1
  - id: perspective2
  # ... 10 total branches

# Slower but more conservative (3 concurrent API calls)
branches:
  - id: perspective1
  - id: perspective2
  - id: perspective3
```

Consider your provider's rate limits and costs.

### 4. Use Reduce for Aggregation

Always use a reduce step when you need unified output:

```yaml
# Good - synthesized output
config:
  branches: [...]
  reduce:
    agent: synthesizer
    input: "Combine all findings"

# Avoid - no synthesis (just multiple independent outputs)
config:
  branches: [...]
  # Missing reduce step
```

### 5. Handle Variable Branch Counts

Use iteration to handle dynamic branch counts:

```yaml
reduce:
  agent: synthesizer
  input: |
    Synthesize findings from {{ branches | length }} branches:

    {% for branch_id, branch in branches.items() %}
    {{ branch_id }}: {{ branch.response }}
    {% endfor %}
```

## Common Patterns

### Multi-Perspective Analysis

```yaml
branches:
  - id: academic
    steps:
      - agent: academic_researcher
        input: "Academic perspective on {{ topic }}"

  - id: industry
    steps:
      - agent: industry_analyst
        input: "Industry perspective on {{ topic }}"

  - id: regulatory
    steps:
      - agent: regulatory_expert
        input: "Regulatory perspective on {{ topic }}"

reduce:
  agent: synthesizer
  input: "Synthesize all three perspectives"
```

### Data Source Aggregation

```yaml
branches:
  - id: database1
    steps:
      - agent: data_analyst
        input: "Analyze data from source 1"

  - id: database2
    steps:
      - agent: data_analyst
        input: "Analyze data from source 2"

  - id: api_data
    steps:
      - agent: data_analyst
        input: "Analyze data from API"

reduce:
  agent: aggregator
  input: "Aggregate all data sources"
```

### Competitive Analysis

```yaml
branches:
  - id: competitor_a
    steps:
      - agent: analyst
        input: "Analyze competitor A's strategy"

  - id: competitor_b
    steps:
      - agent: analyst
        input: "Analyze competitor B's strategy"

  - id: competitor_c
    steps:
      - agent: analyst
        input: "Analyze competitor C's strategy"

reduce:
  agent: strategist
  input: "Compare all competitors and recommend strategy"
```

## Performance Considerations

### Parallel Speedup

Parallel pattern provides linear speedup for independent tasks:

```yaml
# Sequential (Chain): 30 seconds total
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

# Parallel: 10 seconds total (3x speedup)
pattern:
  type: parallel
  config:
    branches:
      - id: a
        steps:
          - agent: researcher
            input: "Research A"  # 10s (concurrent)
      - id: b
        steps:
          - agent: researcher
            input: "Research B"  # 10s (concurrent)
      - id: c
        steps:
          - agent: researcher
            input: "Research C"  # 10s (concurrent)
```

### Agent Caching

Strands caches agents across branches:

```yaml
agents:
  - id: researcher
    system: "You are a researcher"

branches:
  - id: branch1
    steps:
      - agent: researcher  # Agent built here
  - id: branch2
    steps:
      - agent: researcher  # Cached - no rebuild
  - id: branch3
    steps:
      - agent: researcher  # Cached - no rebuild
```

### Reduce Step Overhead

The reduce step adds one additional agent invocation:

```
Total time = Max(branch execution times) + Reduce time
```

If you don't need synthesis, omit the reduce step.

## Troubleshooting

### Branches Not Running Concurrently

Verify you're using the Parallel pattern:

```bash
strands validate workflow.yaml
```

Check pattern type:
```yaml
pattern:
  type: parallel  # Not chain or workflow
```

### Some Branches Failing

Enable debug logging:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Branch 'technical' completed successfully
Branch 'business' failed: <error message>
Branch 'market' completed successfully
```

Failed branches are excluded from reduce step.

### Reduce Step Not Executing

Ensure at least one branch succeeds:

```
Reduce step requires at least one successful branch
All branches failed - reduce step skipped
```

### Variable Branch Results

Branch completion order is non-deterministic. Use branch IDs for consistent access:

```yaml
# Good - explicit branch access
content: |
  Technical: {{ branches.technical.response }}
  Business: {{ branches.business.response }}

# Avoid - order-dependent access
content: |
  First: {{ branches[0].response }}  # Which branch is first?
```

## Parallel vs. Other Patterns

### Parallel vs. Workflow

Use Parallel for independent branches, Workflow for dependencies:

```yaml
# Parallel: All branches independent
pattern:
  type: parallel
  config:
    branches:
      - id: branch1
        steps: [...]  # No dependencies
      - id: branch2
        steps: [...]  # No dependencies

# Workflow: Tasks can depend on each other
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: researcher
        input: "Research"
      - id: task2
        agent: analyst
        deps: [task1]  # Depends on task1
        input: "{{ tasks.task1.response }}"
```

### Parallel vs. Chain

Use Parallel for concurrent execution, Chain for sequential:

```yaml
# Parallel: 10 seconds total (concurrent)
pattern:
  type: parallel
  config:
    branches:
      - id: a
        steps: [...]  # Runs concurrently
      - id: b
        steps: [...]  # Runs concurrently

# Chain: 20 seconds total (sequential)
pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Step 1"  # 10s
      - agent_id: researcher
        prompt: "Step 2"  # 10s (after step 1)
```

## Examples

Complete examples in the repository:

- `examples/parallel-simple-2-branches.yaml` - Basic parallel research
- `examples/parallel-with-reduce.yaml` - Multi-perspective synthesis
- `examples/parallel-multi-step-branches.yaml` - Complex branch workflows

## See Also

- [Workflow Pattern](workflow.md) - For task dependencies
- [Chain Pattern](chain.md) - For sequential execution
- [Orchestrator-Workers Pattern](orchestrator-workers.md) - For dynamic parallel delegation
- [Run Workflows](../run-workflows.md) - Execution guide
- [Context Management](../context-management.md) - Managing branch context

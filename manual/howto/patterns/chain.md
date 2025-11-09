---
title: Chain Pattern
description: Sequential multi-step workflow execution with context threading
keywords: chain, pattern, sequential, multi-step, pipeline, context, last_response
---

# Chain Pattern

The Chain pattern executes a series of steps sequentially, where each step can access the results of previous steps. This is ideal for workflows that require ordered processing with context passing.

## When to Use

Use the Chain pattern when you need to:

- Execute steps in a specific order
- Pass results from one step to the next
- Build upon previous step outputs
- Implement multi-stage processing pipelines
- Maintain conversation context across steps

## Basic Example

```yaml
version: 0
name: simple-chain
description: Three-step research workflow

runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0

agents:
  - id: researcher
    system: "You are a research assistant providing factual information."

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research the topic: {{ topic }}. List 3-5 key points."

      - agent_id: researcher
        prompt: |
          Based on this research:
          {{ steps[0].response }}

          Analyze the most important point in detail.

      - agent_id: researcher
        prompt: |
          Previous research: {{ steps[0].response }}
          Analysis: {{ steps[1].response }}

          Write a 2-paragraph summary combining both insights.

inputs:
  topic:
    type: string
    description: "Research topic"
    default: "artificial intelligence"
```

## Accessing Step Results

### Last Response

Access the most recent step output:

```yaml
prompt: "Summarize this: {{ last_response }}"
```

### Specific Steps

Access any previous step by index (0-based):

```yaml
# First step
prompt: "Build on this: {{ steps[0].response }}"

# Second step
prompt: "Compare {{ steps[0].response }} with {{ steps[1].response }}"
```

### All Steps

Iterate over all previous steps:

```yaml
prompt: |
  Review all previous outputs:
  {% for step in steps %}
  Step {{ loop.index }}: {{ step.response }}
  {% endfor %}
```

## Context Threading

The Chain pattern automatically threads context through steps:

1. **Step 1** executes with initial input
2. **Step 2** has access to Step 1's response via `steps[0].response`
3. **Step 3** has access to both previous steps via `steps[0]` and `steps[1]`
4. And so on...

### Example: Research to Report

```yaml
pattern:
  type: chain
  config:
    steps:
      # Step 1: Gather information
      - agent_id: researcher
        prompt: "Find key facts about {{ topic }}"

      # Step 2: Analyze (uses Step 1)
      - agent_id: analyst
        prompt: |
          Given these facts:
          {{ steps[0].response }}

          Identify the 3 most important insights.

      # Step 3: Write report (uses Steps 1 and 2)
      - agent_id: writer
        prompt: |
          Facts: {{ steps[0].response }}
          Insights: {{ steps[1].response }}

          Write a comprehensive report for {{ audience }}.
```

## Using Multiple Agents

You can use different agents for different steps:

```yaml
agents:
  - id: researcher
    system: "You research topics thoroughly and cite sources."

  - id: analyst
    system: "You analyze data and identify patterns."

  - id: writer
    system: "You write clear, engaging content."

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research {{ topic }}"

      - agent_id: analyst
        prompt: "Analyze: {{ last_response }}"

      - agent_id: writer
        prompt: "Write a report based on: {{ last_response }}"
```

## Advanced Features

### Step-Level Variables

Define variables specific to each step:

```yaml
steps:
  - agent_id: researcher
    prompt: "Research {{ topic }} with focus on {{ focus }}"
    vars:
      focus: "technical details"

  - agent_id: researcher
    prompt: "Research {{ topic }} with focus on {{ focus }}"
    vars:
      focus: "business implications"
```

### Conditional Content

Use Jinja2 conditionals in prompts:

```yaml
steps:
  - agent_id: writer
    prompt: |
      {% if steps|length > 0 %}
      Previous context: {{ last_response }}
      {% endif %}

      Write about {{ topic }}.
```

### Truncating Long Responses

Use Jinja2 filters to manage context size:

```yaml
steps:
  - agent_id: summarizer
    prompt: |
      Summarize this (showing first 200 chars):
      {{ steps[0].response | truncate(200) }}
```

## Error Handling

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

If a step fails, it will retry up to 3 times with exponential backoff before failing the entire chain.

### Budget Limits

Prevent runaway chains:

```yaml
runtime:
  budgets:
    max_steps: 10          # Maximum chain steps
    max_tokens: 100000     # Maximum total tokens
    max_duration_s: 300    # Maximum 5 minutes
```

## Output Artifacts

Save chain results to files:

```yaml
outputs:
  artifacts:
    - path: "research_report.md"
      content: |
        # {{ topic }}

        ## Research
        {{ steps[0].response }}

        ## Analysis
        {{ steps[1].response }}

        ## Summary
        {{ steps[2].response }}
```

## Best Practices

### 1. Keep Steps Focused

Each step should have a clear, single purpose:

```yaml
# Good - clear purpose per step
steps:
  - agent_id: researcher
    prompt: "Find 5 sources about {{ topic }}"
  - agent_id: analyst
    prompt: "Analyze credibility of sources: {{ last_response }}"
  - agent_id: writer
    prompt: "Synthesize findings: {{ last_response }}"

# Avoid - too much in one step
steps:
  - agent_id: do_everything
    prompt: "Research, analyze, and write a complete report"
```

### 2. Manage Context Size

Long chains can accumulate large context. Use strategies to manage this:

```yaml
# Truncate earlier steps
prompt: |
  Early research (truncated): {{ steps[0].response | truncate(100) }}
  Recent analysis: {{ steps[-1].response }}

# Reference only what you need
prompt: |
  Key insight from step 2: {{ steps[1].response }}
  Write a conclusion.
```

### 3. Use Descriptive Prompts

Make step purposes clear:

```yaml
steps:
  - agent_id: researcher
    prompt: |
      # Research Phase
      Find authoritative sources about {{ topic }}.
      Focus on recent publications (last 2 years).

  - agent_id: analyst
    prompt: |
      # Analysis Phase
      Review these sources: {{ last_response }}
      Identify consensus and controversies.
```

### 4. Validate Inputs

Use input constraints:

```yaml
inputs:
  topic:
    type: string
    description: "Research topic"

  depth:
    type: string
    enum: ["shallow", "medium", "deep"]
    default: "medium"
```

### 5. Monitor Token Usage

Enable telemetry to track token consumption:

```yaml
telemetry:
  enabled: true
  console:
    enabled: true
```

Then run with trace:

```bash
strands run workflow.yaml --trace
```

## Common Patterns

### Research → Analyze → Report

```yaml
steps:
  - agent_id: researcher
    prompt: "Gather information about {{ topic }}"
  - agent_id: analyst
    prompt: "Analyze: {{ last_response }}"
  - agent_id: writer
    prompt: "Write report: {{ last_response }}"
```

### Iterative Refinement

```yaml
steps:
  - agent_id: writer
    prompt: "Write initial draft about {{ topic }}"
  - agent_id: editor
    prompt: "Improve this draft: {{ last_response }}"
  - agent_id: editor
    prompt: "Polish final version: {{ last_response }}"
```

### Multi-Format Output

```yaml
steps:
  - agent_id: writer
    prompt: "Write content about {{ topic }}"
  - agent_id: formatter
    prompt: "Convert to markdown: {{ last_response }}"
  - agent_id: formatter
    prompt: "Create HTML version: {{ steps[0].response }}"
```

## Performance Considerations

### Agent Caching

Strands automatically caches agents with identical configurations. If all steps use the same agent, only one agent is built:

```yaml
agents:
  - id: researcher
    system: "You are a researcher"

steps:
  - agent_id: researcher  # Agent built here
    prompt: "Step 1"
  - agent_id: researcher  # Cached - no rebuild
    prompt: "Step 2"
  - agent_id: researcher  # Cached - no rebuild
    prompt: "Step 3"
```

This provides ~90% overhead reduction.

### Parallel vs. Chain

If steps are independent, consider the [Parallel pattern](parallel.md) instead:

```yaml
# Chain (sequential) - 30 seconds total
steps:
  - agent_id: researcher
    prompt: "Research A"  # 10s
  - agent_id: researcher
    prompt: "Research B"  # 10s
  - agent_id: researcher
    prompt: "Research C"  # 10s

# Parallel (concurrent) - 10 seconds total
branches:
  - id: a
    agent_id: researcher
    prompt: "Research A"  # 10s
  - id: b
    agent_id: researcher
    prompt: "Research B"  # 10s (concurrent)
  - id: c
    agent_id: researcher
    prompt: "Research C"  # 10s (concurrent)
```

## Troubleshooting

### Chain Not Progressing

Check budget limits:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Budget exceeded: max_steps (5) reached
```

### Context Too Large

Reduce context accumulation:

```yaml
# Use truncate filter
prompt: "{{ steps[0].response | truncate(200) }}"

# Reference only recent steps
prompt: "{{ steps[-1].response }}"

# Adjust max_tokens per agent
agents:
  - id: researcher
    max_tokens: 500  # Limit response size
```

### Steps Failing

Enable retry logic:

```yaml
runtime:
  failure_policy:
    retries: 3
    backoff: exponential
```

## Examples

Complete examples in the repository:

- `examples/chain-3-step-research.yaml` - Basic three-step chain
- `examples/single-agent-chain-bedrock.yaml` - Bedrock provider
- `examples/single-agent-chain-ollama.yaml` - Ollama provider
- `examples/single-agent-chain-openai.yaml` - OpenAI provider

## See Also

- [Workflow Pattern](workflow.md) - For DAG-based parallel execution
- [Parallel Pattern](parallel.md) - For concurrent independent tasks
- [Graph Pattern](graph.md) - For conditional control flow
- [Run Workflows](../run-workflows.md) - Execution guide
- [Context Management](../context-management.md) - Managing chain context

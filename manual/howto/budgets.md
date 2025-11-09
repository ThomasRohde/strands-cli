# How to Manage Budgets

This guide shows you how to configure and use token budgets, time limits, and step limits in Strands workflows to prevent runaway costs and execution.

## Why Budgets Matter

Without budgets, workflows can:
- Consume excessive tokens and incur high costs
- Run indefinitely in loops or long chains
- Timeout unpredictably without clear limits

Budgets provide:
- **Cost control** - Hard limits on token usage
- **Time bounds** - Maximum execution duration
- **Safety** - Prevent infinite loops in graph/evaluator patterns

## Budget Types

Strands supports three types of budgets:

1. **Token Budget** (`max_tokens`) - Total tokens across all LLM calls
2. **Time Budget** (`max_duration_s`) - Maximum execution time in seconds
3. **Step Budget** (`max_steps`) - Maximum workflow steps/iterations

## Configuring Budgets

### Runtime-Level Budgets

Set global budgets for entire workflow:

```yaml
version: 0
name: budget-demo
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_tokens: 100000      # 100K token limit
    max_duration_s: 300     # 5 minute timeout
    max_steps: 50           # Max 50 steps/iterations

agents:
  assistant:
    prompt: "You are a helpful assistant"

pattern:
  type: chain
  config:
    steps:
      - agent_id: assistant
        prompt: "Hello!"
```

### Pattern-Level Budgets

Override budgets for specific patterns:

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_tokens: 200000  # Global budget

pattern:
  type: evaluator_optimizer
  config:
    producer: writer
    evaluator:
      agent: critic
      input: "Evaluate: {{ draft }}"
    accept:
      min_score: 85
      max_iters: 3  # Pattern-specific iteration limit
```

## Token Budgets

### Setting Token Limits

Token budgets are cumulative across all LLM calls:

```yaml
runtime:
  budgets:
    max_tokens: 50000  # Total tokens (input + output)
```

**What counts toward budget:**
- Input tokens (prompts, context, tool results)
- Output tokens (agent responses)
- All steps/iterations in the workflow

**What doesn't count:**
- Schema validation
- Template rendering
- Non-LLM tool execution

### Recommended Token Budgets

| Workflow Type | Recommended Budget | Reasoning |
|---------------|-------------------|-----------|
| Single-step | 10,000 | One agent call |
| Short chain (3-5 steps) | 50,000 | Multiple calls with context |
| Medium workflow (5-10 steps) | 100,000 | DAG with parallel branches |
| Long research (10+ steps) | 200,000 | Extended chains with tools |
| Evaluator-optimizer | 150,000 | Iterative refinement loops |
| Graph with loops | 300,000 | Conditional branches, iterations |

### Example: Research Workflow

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_tokens: 100000  # Sufficient for ~10 research steps

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research {{ topic }}"
      
      - agent_id: researcher
        prompt: "Analyze: {{ steps[0].response }}"
      
      - agent_id: writer
        prompt: "Write report on: {{ steps[1].response }}"
```

## Time Budgets

### Setting Time Limits

Time budgets enforce maximum execution duration:

```yaml
runtime:
  budgets:
    max_duration_s: 600  # 10 minute timeout
```

**What counts toward budget:**
- Total workflow execution time
- LLM API calls (including retries)
- Tool execution time
- Template rendering and processing

**Timeout behavior:**
- Workflow stops gracefully at budget exceeded
- Partial results returned if available
- Exit code indicates budget exceeded

### Recommended Time Budgets

| Workflow Type | Recommended Timeout | Reasoning |
|---------------|---------------------|-----------|
| Single-step | 30s | Quick single call |
| Short chain | 120s | Few sequential calls |
| Medium workflow | 300s | Parallel execution |
| Long research | 600s | Extended processing |
| Tool-heavy | 900s | External API calls |

### Example: API Integration

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_duration_s: 180  # 3 minutes for API calls

tools:
  http_executors:
    - id: github_api
      base_url: https://api.github.com
      endpoints:
        - path: /repos/{owner}/{repo}
          method: GET

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Fetch repo data for tensorflow/tensorflow"
```

## Step Budgets

### Setting Step Limits

Step budgets limit workflow iterations:

```yaml
runtime:
  budgets:
    max_steps: 100  # Maximum 100 steps/iterations
```

**What counts as a step:**
- Chain: Each step in `steps` array
- Workflow: Each task execution
- Parallel: Each branch step
- Routing: Classifier + all route steps
- Evaluator-Optimizer: Each iteration (producer + evaluator)
- Graph: Each node execution
- Orchestrator-Workers: Each worker task + orchestrator rounds

### Example: Graph with Loops

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_steps: 20  # Prevent infinite loops

pattern:
  type: graph
  config:
    max_iterations: 10  # Additional graph-specific limit
    nodes:
      analyze:
        agent: analyst
        input: "Analyze {{ input }}"
      
      decide:
        agent: decider
        input: "Continue? {{ nodes.analyze.response }}"
    
    edges:
      - from: START
        to: analyze
      
      - from: analyze
        to: decide
      
      - from: decide
        to: analyze
        condition: "nodes.decide.response contains 'continue'"
      
      - from: decide
        to: END
        condition: "nodes.decide.response contains 'done'"
```

## Budget Enforcement

### How Budgets Are Enforced

Budgets are checked:
- **Before each step**: Check if budget already exceeded
- **After each LLM call**: Update cumulative usage
- **At pattern boundaries**: Validate within pattern limits

### Budget Exceeded Behavior

When budget exceeded:
1. Workflow stops immediately
2. Partial results returned (if any)
3. Error message indicates which budget exceeded
4. Exit code: `EX_RUNTIME` (10)

### Example Error Messages

**Token budget:**
```
Error: Token budget exceeded
  Used: 105,432 tokens
  Limit: 100,000 tokens
  Overage: 5,432 tokens
```

**Time budget:**
```
Error: Time budget exceeded
  Duration: 325s
  Limit: 300s
  Overage: 25s
```

**Step budget:**
```
Error: Step budget exceeded
  Steps: 52
  Limit: 50
  Overage: 2 steps
```

## Pattern-Specific Considerations

### Chain Pattern

```yaml
runtime:
  budgets:
    max_steps: 10  # Limits total chain steps

pattern:
  type: chain
  config:
    steps:  # Each step counts toward budget
      - agent_id: step1
        prompt: "..."
      - agent_id: step2
        prompt: "..."
```

### Evaluator-Optimizer Pattern

```yaml
runtime:
  budgets:
    max_steps: 20  # Each iteration = 2 steps (producer + evaluator)

pattern:
  type: evaluator_optimizer
  config:
    accept:
      max_iters: 5  # Pattern-specific iteration limit
```

Budget = `max_iters * 2` (producer + evaluator per iteration)

### Graph Pattern

```yaml
runtime:
  budgets:
    max_steps: 50  # Each node execution counts

pattern:
  type: graph
  config:
    max_iterations: 20  # Additional graph limit
```

Effective limit = `min(max_steps, max_iterations)`

### Orchestrator-Workers Pattern

```yaml
runtime:
  budgets:
    max_steps: 100

pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      limits:
        max_workers: 5
        max_rounds: 3
```

Budget = orchestrator steps + (workers * rounds)

## Best Practices

### 1. Start Conservative

Begin with tight budgets during development:

```yaml
runtime:
  budgets:
    max_tokens: 10000
    max_duration_s: 60
    max_steps: 10
```

Increase as needed based on actual usage.

### 2. Monitor Usage

Enable debug mode to see budget consumption:

```bash
strands run workflow.yaml --debug
```

Debug logs show:
- Tokens per step
- Cumulative usage
- Time elapsed
- Steps executed

### 3. Use Multiple Budgets

Combine budgets for comprehensive control:

```yaml
runtime:
  budgets:
    max_tokens: 100000   # Cost control
    max_duration_s: 300  # Time limit
    max_steps: 50        # Loop prevention
```

All budgets enforced; first exceeded stops workflow.

### 4. Set Pattern-Specific Limits

```yaml
pattern:
  type: evaluator_optimizer
  config:
    accept:
      max_iters: 3  # Specific to pattern
```

Use pattern config for fine-grained control.

### 5. Production vs Development

**Development:**
```yaml
runtime:
  budgets:
    max_tokens: 50000
    max_duration_s: 120
```

**Production:**
```yaml
runtime:
  budgets:
    max_tokens: 200000
    max_duration_s: 600
    max_steps: 100
```

## Calculating Required Budgets

### Token Estimation

Estimate tokens needed:

1. **Count steps**: How many LLM calls?
2. **Estimate per-step**: ~2,000-5,000 tokens per call (input + output)
3. **Add buffer**: Multiply by 1.5-2x for safety
4. **Add context growth**: Later steps have more context

**Example:**
- 10-step chain
- ~3,000 tokens/step average
- Context growth: +500 tokens/step
- Total: `10 * 3000 + (10 * 500) = 35,000 tokens`
- With 2x buffer: `70,000 tokens`

### Time Estimation

Estimate duration needed:

1. **LLM latency**: ~2-5s per call
2. **Tool execution**: ~1-10s per tool call
3. **Network latency**: ~0.5-2s overhead
4. **Add buffer**: 2-3x for retries and variance

**Example:**
- 5 LLM calls * 3s = 15s
- 2 API calls * 5s = 10s
- Total: 25s
- With 3x buffer: 75s

## Troubleshooting

### Budget Exceeded Too Early

**Problem**: Workflow hits budget before completing

**Solutions:**
1. Increase budget: `max_tokens: 200000`
2. Reduce context: Use compaction
3. Simplify prompts: Shorter instructions
4. Use cheaper model: `gpt-4o-mini` instead of `gpt-4o`

### Budget Never Reached

**Problem**: Budget set too high, wasting potential

**Solutions:**
1. Review actual usage in debug logs
2. Reduce budget to 1.5x actual usage
3. Set appropriate limits per workflow type

### Infinite Loop Detection

**Problem**: Graph or evaluator pattern loops forever

**Solution**: Set strict step limit:

```yaml
runtime:
  budgets:
    max_steps: 20  # Force termination

pattern:
  type: graph
  config:
    max_iterations: 10
```

## Example: Complete Budget Configuration

```yaml
version: 0
name: production-workflow
description: Demonstrates complete budget management

runtime:
  provider: openai
  model_id: gpt-4o-mini
  
  # Comprehensive budget controls
  budgets:
    max_tokens: 150000      # ~15-20 agent calls
    max_duration_s: 600     # 10 minute timeout
    max_steps: 30           # Max 30 workflow steps
  
  # Retry strategy
  failure_policy:
    retries: 2
    backoff: exponential

agents:
  researcher:
    prompt: "You research topics thoroughly"
  
  writer:
    prompt: "You write clear reports"

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research {{ topic }}"
      
      - agent_id: researcher
        prompt: "Deep dive: {{ steps[0].response }}"
      
      - agent_id: writer
        prompt: "Write report: {{ steps[1].response }}"

inputs:
  topic:
    type: string
    default: "quantum computing"
```

Run with monitoring:

```bash
strands run production-workflow.yaml --debug --verbose
```

## See Also

- [Context Management](context-management.md) - Optimize token usage with compaction
- [Runtime Configuration](../reference/schema.md#runtime) - Complete runtime options
- [Telemetry](telemetry.md) - Monitor budget consumption

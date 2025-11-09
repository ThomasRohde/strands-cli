# Workflow Specification Reference

Comprehensive reference for the Strands workflow specification format.

!!! info "Complete Specification"
    For the full, detailed specification including all patterns and examples, see the [Workflow Manual](workflow-manual.md).

## Quick Reference

### Minimal Valid Spec

```yaml
version: 0
name: "my-workflow"
runtime:
  provider: ollama
  model_id: "llama3.2:3b"
  host: "http://localhost:11434"

agents:
  assistant:
    prompt: "You are a helpful assistant."

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Hello, world!"
```

### Top-Level Structure

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `version` | ✅ | integer/string | Spec version (use `0`) |
| `name` | ✅ | string | Workflow name |
| `description` | ❌ | string | Human-friendly description |
| `tags` | ❌ | array[string] | Classification tags |
| `runtime` | ✅ | object | Default model/provider/limits |
| `inputs` | ❌ | object | Parameter definitions |
| `env` | ❌ | object | Secrets and mounts |
| `telemetry` | ❌ | object | OTEL configuration |
| `context_policy` | ❌ | object | Compaction, notes, retrieval |
| `skills` | ❌ | array | Skill bundles |
| `tools` | ❌ | object | Python/MCP/HTTP tools |
| `agents` | ✅ | object | Agent definitions (min 1) |
| `pattern` | ✅ | object | Workflow pattern |
| `outputs` | ❌ | object | Artifact definitions |
| `security` | ❌ | object | Guardrails |

## Runtime Configuration

Provider-specific requirements and common settings.

### Bedrock

```yaml
runtime:
  provider: bedrock
  model_id: "us.anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"  # Required
  temperature: 0.7
  max_tokens: 2000
```

**Requirements**:
- AWS credentials configured
- `region` field required
- Model access enabled in Bedrock console

### OpenAI

```yaml
runtime:
  provider: openai
  model_id: "gpt-4o-mini"
  temperature: 0.7
  max_tokens: 2000
```

**Requirements**:
- `OPENAI_API_KEY` environment variable
- Optional: `host` for OpenAI-compatible servers

### Ollama

```yaml
runtime:
  provider: ollama
  model_id: "llama3.2:3b"
  host: "http://localhost:11434"  # Required
  temperature: 0.7
  max_tokens: 2000
```

**Requirements**:
- Ollama server running
- Model pulled: `ollama pull llama3.2:3b`

### Common Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | string | - | `bedrock`, `openai`, `ollama` |
| `model_id` | string | provider-specific | Model identifier |
| `region` | string | - | AWS region (Bedrock only) |
| `host` | string | - | Server URL (Ollama/OpenAI) |
| `temperature` | float (0.0-2.0) | 0.7 | Sampling temperature |
| `max_tokens` | integer (≥1) | 2000 | Max output tokens |
| `top_p` | float (0.0-1.0) | 0.95 | Nucleus sampling |
| `max_parallel` | integer (≥1) | 4 | Concurrent task limit |

### Budgets

```yaml
runtime:
  budgets:
    max_steps: 200        # Maximum workflow steps
    max_tokens: 800000    # Token limit (cumulative)
    max_duration_s: 900   # Time limit (seconds)
```

### Failure Policy

```yaml
runtime:
  failure_policy:
    retries: 2                # Retry count (0-10)
    backoff: exponential      # constant | exponential | jittered
```

## Agents

Agent definitions with prompts, tools, and overrides.

```yaml
agents:
  researcher:
    prompt: |
      You are a research specialist.
      Cite sources with links.
    tools: ["http_request"]
    model_id: "gpt-4o"  # Override runtime model
    inference:
      temperature: 0.2
      max_tokens: 4000
  
  writer:
    prompt: "Write concise reports for {{audience}}."
```

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `prompt` | ✅ | string | System prompt (supports `{{vars}}`) |
| `tools` | ❌ | array[string] | Tool references |
| `provider` | ❌ | string | Override runtime provider |
| `model_id` | ❌ | string | Override runtime model |
| `inference` | ❌ | object | Override temperature/tokens/top_p |

## Patterns

### Chain

Sequential steps with single agent.

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Find sources on {{topic}}"
      - agent: writer
        input: "Write a summary"
```

**See**: [Chain Pattern Guide](../howto/patterns/chain.md)

### Workflow (DAG)

Multi-task execution with dependencies.

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: extract
        agent: researcher
        description: "Fetch sources"
      - id: analyze
        agent: researcher
        deps: [extract]
        description: "Analyze trends"
      - id: report
        agent: writer
        deps: [analyze]
        description: "Write report"
```

**See**: [Workflow Pattern Guide](../howto/patterns/workflow.md)

### Routing

Dynamic agent selection based on classifier.

```yaml
pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: "Classify request"
    routes:
      faq:
        then:
          - agent: writer
            input: "Answer briefly"
      research:
        then:
          - agent: researcher
            input: "Deep dive"
```

**See**: [Routing Pattern Guide](../howto/patterns/routing.md)

### Parallel

Concurrent branches with optional reduce.

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: web
        steps:
          - agent: researcher
            input: "Search web"
      - id: docs
        steps:
          - agent: researcher
            input: "Search docs"
    reduce:
      agent: writer
      input: "Merge findings"
```

**See**: [Parallel Pattern Guide](../howto/patterns/parallel.md)

### Evaluator-Optimizer

Iterative refinement loop.

```yaml
pattern:
  type: evaluator_optimizer
  config:
    producer: writer
    evaluator:
      agent: critic
      input: "Score 0-100 and provide feedback"
    accept:
      min_score: 85
      max_iters: 3
    revise_prompt: "Improve based on feedback"
```

**See**: [Evaluator-Optimizer Pattern Guide](../howto/patterns/evaluator-optimizer.md)

### Orchestrator-Workers

Orchestrator decomposes tasks, workers execute.

```yaml
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: planner
      limits:
        max_workers: 6
        max_rounds: 3
    worker_template:
      agent: researcher
      tools: ["http_request"]
    reduce:
      agent: writer
      input: "Synthesize results"
```

**See**: [Orchestrator-Workers Pattern Guide](../howto/patterns/orchestrator-workers.md)

### Graph

State machine with conditional transitions.

```yaml
pattern:
  type: graph
  config:
    max_iterations: 5
    nodes:
      intake:
        agent: classifier
      handle_tech:
        agent: tech_support
      escalate:
        agent: manager
    edges:
      - from: intake
        choose:
          - when: "{{ 'technical' in nodes.intake.response }}"
            to: handle_tech
          - when: else
            to: escalate
      - from: handle_tech
        to: [escalate]
```

**See**: [Graph Pattern Guide](../howto/patterns/graph.md)

## Inputs and Variables

### Required Inputs

```yaml
inputs:
  required:
    topic: string
    audience: string
```

### Optional Inputs with Defaults

```yaml
inputs:
  optional:
    priority:
      type: string
      description: "Priority level"
      default: "medium"
      enum: ["low", "medium", "high"]
```

### Variable Interpolation

Use `{{variable}}` in any string field:

```yaml
agents:
  writer:
    prompt: "Write for {{audience}} about {{topic}}"

pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Priority: {{priority}}"

outputs:
  artifacts:
    - path: "{{topic}}_report.md"
      from: "{{ last_response }}"
```

### CLI Variable Overrides

```bash
strands run spec.yaml --var topic="AI Ethics" --var audience="executives"
```

## Tools

### Python Callables

```yaml
tools:
  python:
    - "strands_tools.http_request"
    - "strands_tools.file_read"
    - "./local_tools/custom.py:my_function"
```

**Allowlist** (v0.11):
- `strands_tools.http_request`
- `strands_tools.file_read`
- `strands_tools.file_write` (requires consent)
- `strands_tools.calculator`
- `strands_tools.current_time`

### MCP Servers

```yaml
tools:
  mcp:
    - id: "filesystem"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed"]
```

### HTTP Executors

```yaml
tools:
  http_executors:
    - id: "github"
      base_url: "https://api.github.com"
      headers:
        Authorization: "Bearer ${GITHUB_TOKEN}"
      timeout: 30
```

**Security**: See [Security Reference](security.md) for SSRF protection.

## Outputs

### Artifacts

```yaml
outputs:
  artifacts:
    - path: "./reports/{{name}}.md"
      from: "{{ last_response }}"
    - path: "./trace.json"
      from: "$TRACE"
```

**Template Variables**:
- `{{ last_response }}` - Final pattern output
- `{{ steps[0].response }}` - Chain step response
- `{{ tasks.task_id.response }}` - Workflow task response
- `{{ branches.branch_id.response }}` - Parallel branch response
- `{{ nodes.node_id.response }}` - Graph node response
- `$TRACE` - OTEL trace export

## Context Policy

### Compaction

```yaml
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 150000
```

### Notes

```yaml
context_policy:
  notes:
    file: "./artifacts/NOTES.md"
    include_last: 10
```

### JIT Retrieval

```yaml
context_policy:
  retrieval:
    jit_tools: ["grep", "head", "tail", "search"]
```

**See**: [Context Management Guide](../howto/context-management.md)

## Telemetry

```yaml
telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
    sample_ratio: 1.0
  redact:
    tool_inputs: true
    tool_outputs: false
```

**See**: [Telemetry Guide](../howto/telemetry.md)

## Security

```yaml
security:
  guardrails:
    deny_network: false
    pii_redaction: true
    allow_tools: ["http_request"]
```

**See**: [Security Model](../explanation/security-model.md) | [Security Reference](security.md)

## Further Reading

- **Complete Specification**: [Workflow Manual](workflow-manual.md)
- **JSON Schema**: `src/strands_cli/schema/strands-workflow.schema.json`
- **How-To Guides**: [Pattern Guides](../howto/patterns/chain.md), [Tools](../howto/tools.md)
- **Examples**: [Example Catalog](examples.md)

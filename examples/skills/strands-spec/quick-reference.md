# Quick Reference

One-page cheat sheet for strands-cli workflow specs.

## Minimal Spec Template

```yaml
version: 0
name: "workflow-name"

runtime:
  provider: bedrock|openai|ollama
  model_id: "model-identifier"
  region: "us-east-1"  # Bedrock only

agents:
  agent-name:
    prompt: "Instructions with {{ variables }}"

pattern:
  type: chain
  config:
    steps:
      - agent: agent-name
        input: "Task description"
```

## Top-Level Keys

| Key | Required | Description |
|-----|----------|-------------|
| `version` | ✅ | Spec version (always `0`) |
| `name` | ✅ | Workflow name |
| `description` | ❌ | Human-readable description |
| `runtime` | ✅ | Default model/provider/budgets |
| `inputs` | ❌ | Workflow parameters |
| `agents` | ✅ | Agent definitions (min: 1) |
| `pattern` | ✅ | Orchestration pattern |
| `outputs` | ❌ | Artifact outputs |
| `tools` | ❌ | Custom tool definitions |
| `skills` | ❌ | Skill bundles |
| `env` | ❌ | Secrets and mounts |
| `telemetry` | ❌ | OpenTelemetry config |
| `security` | ❌ | Guardrails |
| `context_policy` | ❌ | Context management |

## Runtime Quick Config

```yaml
runtime:
  # REQUIRED
  provider: bedrock|openai|ollama
  
  # Provider-specific
  model_id: "..."        # Model identifier
  region: "us-east-1"    # Bedrock only
  host: "http://..."     # Ollama only
  
  # Generation params
  temperature: 0.7       # 0.0-2.0
  max_tokens: 2000       # Per-message limit
  top_p: 0.95            # 0.0-1.0
  
  # Execution limits
  max_parallel: 4        # Concurrent invocations
  
  # Budgets
  budgets:
    max_tokens: 100000   # Total budget
    max_duration_s: 600  # Timeout
    max_steps: 50        # Max invocations
    
  # Retries
  failure_policy:
    retries: 2
    backoff: exponential
```

## Pattern Types

| Pattern | Use Case | Key Config |
|---------|----------|------------|
| `chain` | Sequential steps | `steps[]` |
| `routing` | Dynamic agent selection | `router`, `routes[]` |
| `parallel` | Concurrent branches | `branches[]` |
| `workflow` | DAG with dependencies | `tasks[]`, `depends_on` |
| `graph` | State machine | `nodes[]`, `edges[]` |
| `evaluator-optimizer` | Iterative refinement | `generator`, `evaluator`, `optimizer` |
| `orchestrator-workers` | Dynamic delegation | `orchestrator`, `workers[]` |

## Template Variables

| Variable | Scope | Description |
|----------|-------|-------------|
| `{{ variable }}` | All | Workflow input |
| `{{ last_response }}` | Chain | Most recent output |
| `{{ steps[N].response }}` | Chain | Step N output (0-indexed) |
| `{{ tasks.id.response }}` | Workflow | Task output by ID |
| `{{ branches.id.response }}` | Parallel | Branch output by ID |
| `{{ nodes.id.response }}` | Graph | Node output by ID |
| `{{ $TRACE }}` | All | Full execution trace |
| `{{ timestamp }}` | All | Current timestamp |

## Agent Definition

```yaml
agents:
  agent-name:
    # REQUIRED
    prompt: "Instructions"
    
    # OPTIONAL
    tools: ["python_exec", "http_request"]
    
    runtime:            # Override defaults
      temperature: 0.3
      max_tokens: 4000
```

## Native Tools

| Tool | Description | Config |
|------|-------------|--------|
| `python_exec` | Execute Python code | None |
| `http_request` | HTTP requests | `allowlist`, `timeout` |
| `grep` | Code search | None |
| `notes` | Context sharing | None |

## Common JMESPath Conditions

```yaml
# Equality
condition: "status == 'success'"

# Comparison (quote numbers with backticks)
condition: "score > `8`"

# String contains
condition: "contains(category, 'urgent')"

# Array membership
condition: "contains(tags, 'priority')"

# Multiple conditions
condition: "confidence > `0.8` && category == 'technical'"

# Boolean
condition: "is_valid"
```

## Input Types

```yaml
inputs:
  required:
    param_name: string         # Shorthand
    
  optional:
    param_with_details:
      type: string             # string|number|boolean|object|array
      description: "Help text"
      default: "value"
      enum: ["a", "b", "c"]    # Restrict values
```

## Output Artifacts

```yaml
outputs:
  artifacts:
    - path: "./output.txt"
      from: "{{ last_response }}"
      
    - path: "./trace-{{ timestamp }}.json"
      from: "{{ $TRACE }}"
      condition: "{{ debug_mode }}"  # Conditional output
```

## Provider Setup

### Bedrock
```yaml
runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"
```

Requires: AWS credentials (`aws configure`)

### OpenAI
```yaml
runtime:
  provider: openai
  model_id: "gpt-4o-mini"
```

Requires: `export OPENAI_API_KEY=sk-...`

### Ollama
```yaml
runtime:
  provider: ollama
  model_id: "llama3"
  host: "http://localhost:11434"
```

Requires: `ollama serve`

## CLI Commands

```bash
# Run workflow
uv run strands run workflow.yaml --var key=value

# Validate spec
uv run strands validate workflow.yaml

# Plan (dry-run)
uv run strands plan workflow.yaml

# Explain unsupported features
uv run strands explain workflow.yaml

# List supported features
uv run strands list-supported

# List native tools
uv run strands list-tools

# Resume failed workflow
uv run strands run --resume <session-id>

# Debug mode
uv run strands run workflow.yaml --debug --verbose

# Health check
uv run strands doctor

# Session management
uv run strands sessions list
uv run strands sessions show <session-id>
uv run strands sessions delete <session-id>
uv run strands sessions cleanup

# Version
uv run strands version
```

## Exit Codes

| Code | Name | Meaning |
|------|------|---------|
| 0 | `EX_OK` | Success |
| 2 | `EX_USAGE` | Invalid CLI usage |
| 3 | `EX_SCHEMA` | Schema validation failed |
| 10 | `EX_RUNTIME` | Provider/runtime error |
| 12 | `EX_IO` | File I/O error |
| 18 | `EX_UNSUPPORTED` | Unsupported feature |
| 70 | `EX_UNKNOWN` | Unexpected error |

## Common Patterns

### Chain with Context
```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: step-1
        input: "Do task 1"
      - agent: step-2
        input: "Do task 2 using: {{ steps[0].response }}"
```

### Parallel with Reduce
```yaml
pattern:
  type: parallel
  config:
    branches:
      - name: branch-a
        agent: agent-a
      - name: branch-b
        agent: agent-b
    reduce:
      enabled: true
      agent: aggregator
      input: "Combine: {{ branches.branch-a.response }} + {{ branches.branch-b.response }}"
```

### Routing with Default
```yaml
pattern:
  type: routing
  config:
    router: classifier
    router_input: "Classify: {{ input }}"
    routes:
      - name: route-a
        condition: "category == 'a'"
        agent: handler-a
    default: fallback-agent
```

### Workflow DAG
```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: fetch
        agent: fetcher
      - id: process
        agent: processor
        depends_on: [fetch]
```

### Graph with Loop
```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: draft
        agent: writer
      - id: review
        agent: reviewer
    edges:
      - from: draft
        to: review
      - from: review
        to: draft
        condition: "score < `8`"  # Loop back
    start_node: draft
    max_iterations: 5
```

## Debugging Checklist

- [ ] Validate spec: `uv run strands validate workflow.yaml`
- [ ] Check provider credentials
- [ ] Enable debug mode: `--debug --verbose`
- [ ] Export trace: Add `{{ $TRACE }}` artifact
- [ ] Test with simple inputs first
- [ ] Verify agent names match exactly
- [ ] Check budget limits
- [ ] Review error messages for JSONPointer path

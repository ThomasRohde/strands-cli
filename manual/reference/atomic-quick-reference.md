---
title: Atomic Agents Quick Reference
description: Quick reference card for atomic agent commands, structure, and patterns
keywords: atomic agents, quick reference, cheat sheet, commands
---

# Atomic Agents Quick Reference

Quick reference for working with atomic agents in Strands CLI.

## CLI Commands

### Discovery

```bash
# List all atomic agents
strands atomic list

# List with JSON output
strands atomic list --json

# Show all agents (including non-atomic)
strands atomic list --all

# Describe an agent
strands atomic describe <name>

# Describe with JSON output
strands atomic describe <name> --format json
```

### Validation

```bash
# Validate atomic agent invariants
strands atomic validate <name>

# Full schema validation
strands validate agents/atomic/<name>/<name>.yaml
```

### Execution

```bash
# Run with input file
strands atomic run <name> --input-file <path>

# Run and save output
strands atomic run <name> --input-file <path> --output-file <path>
```

### Testing

```bash
# Run all tests
strands atomic test <name>

# Run specific tests
strands atomic test <name> --filter "pattern*"

# Generate JSON report
strands atomic test <name> --json > results.json
```

### Scaffolding

```bash
# Create new atomic agent with defaults
strands atomic init <name>

# With metadata
strands atomic init <name> --domain <domain> --capability <capability>

# Force overwrite existing files
strands atomic init <name> --force
```

## Manifest Structure

### Minimal Atomic Agent

```yaml
version: 0
name: my_agent
description: Brief description

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  my_agent:
    prompt: |
      Clear, focused instructions.
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json

metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: domain_name
    strands.io/capability: capability_name
    strands.io/version: v1

pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: |
          {{ inputs.values.field }}
```

### Required Elements

- ✅ `version: 0` (workflow spec version)
- ✅ Exactly **one** agent in `agents` map
- ✅ `runtime` configuration
- ✅ `metadata.labels.strands.io/agent_type: atomic`
- ✅ Single-step `pattern` (chain or workflow)
- ✅ `input_schema` and `output_schema` (recommended)

## Schema Structure

### Input Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "field1": {
      "type": "string",
      "description": "Field description",
      "minLength": 1
    },
    "field2": {
      "type": "number",
      "minimum": 0
    }
  },
  "required": ["field1"],
  "additionalProperties": false
}
```

### Output Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "result": {
      "type": "string",
      "description": "Result description"
    },
    "items": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    }
  },
  "required": ["result"],
  "additionalProperties": false
}
```

## Test Suite Structure

```yaml
tests:
  - name: happy_path
    input: ./examples/sample.json
    expect:
      output_schema: ./schemas/output.json
      checks:
        - type: has_keys
          keys: ["field1", "field2"]
  
  - name: edge_case
    input: ./examples/sample.json
    expect:
      output_schema: ./schemas/output.json
      checks:
        - type: max_length
          field: summary
          value: 300
        - type: regex_match
          field: status
          pattern: "^(success|failure)$"
```

### Available Check Types

| Type | Description | Parameters |
|------|-------------|------------|
| `has_keys` | Keys exist in output | `keys: ["key1", "key2"]` |
| `max_length` | String max length | `field: "name"`, `value: 100` |
| `min_length` | String min length | `field: "name"`, `value: 10` |
| `regex_match` | String matches pattern | `field: "email"`, `pattern: "^.*@.*$"` |
| `contains` | String contains substring | `field: "text"`, `value: "keyword"` |
| `numeric_range` | Number in range | `field: "score"`, `min: 0`, `max: 100` |

## Directory Layout

```
project/
├── agents/
│   └── atomic/
│       ├── summarize_customer_email/
│       │   ├── summarize_customer_email.yaml
│       │   ├── schemas/
│       │   │   ├── input.json
│       │   │   └── output.json
│       │   ├── examples/
│       │   │   └── sample.json
│       │   └── tests.yaml
│       ├── classify_ticket_priority/
│       │   ├── classify_ticket_priority.yaml
│       │   ├── schemas/
│       │   │   ├── input.json
│       │   │   └── output.json
│       │   ├── examples/
│       │   │   └── sample.json
│       │   └── tests.yaml
│       └── extract_invoice_data/
│           ├── extract_invoice_data.yaml
│           ├── schemas/
│           │   ├── input.json
│           │   └── output.json
│           ├── examples/
│           │   └── sample.json
│           └── tests.yaml
└── workflows/
    └── customer_support_pipeline.yaml
```

## Metadata Labels

| Label | Required | Description | Example |
|-------|----------|-------------|---------|
| `strands.io/agent_type` | Yes | Always `"atomic"` | `atomic` |
| `strands.io/domain` | Recommended | Business domain | `customer_service` |
| `strands.io/capability` | Recommended | Core capability | `summarization` |
| `strands.io/version` | Recommended | Version identifier | `v1` |
| `strands.io/eval_profile` | Optional | Evaluation workflow | `summarization_v1` |

## Composition with $ref (v0.6.0+)

### Basic Reference

```yaml
# Reference atomic agent - inherits everything
agents:
  my_agent:
    $ref: ../agents/atomic/summarize_customer_email/summarize_customer_email.yaml
```

### Reference with Overrides

```yaml
# Reference but customize for this workflow
agents:
  my_agent:
    $ref: ../agents/atomic/summarize_customer_email/summarize_customer_email.yaml
    model_id: gpt-4o  # Use larger model
    tools: ["http_request"]  # Add tools
```

### In Chain Workflow

```yaml
agents:
  summarize:
    $ref: ./agents/atomic/summarize/summarize.yaml
  classify:
    $ref: ./agents/atomic/classify/classify.yaml

pattern:
  type: chain
  config:
    steps:
      - agent: summarize
        input: "{{ email }}"
      - agent: classify
        input: "{{ steps[0].response }}"
```

### In DAG Workflow

```yaml
agents:
  summarize:
    $ref: ./agents/atomic/summarize/summarize.yaml
  classify:
    $ref: ./agents/atomic/classify/classify.yaml

pattern:
  type: workflow
  config:
    tasks:
      - id: summarize
        agent: summarize
        input: "{{ email }}"
      - id: classify
        agent: classify
        deps: [summarize]
        input: "{{ tasks.summarize.response }}"
```

### In Orchestrator Pattern

```yaml
agents:
  orchestrator:
    prompt: "Break down tasks and assign to worker"
  worker:
    $ref: ./agents/atomic/summarize/summarize.yaml

pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: orchestrator
    worker_template:
      agent: worker  # Single atomic agent template for all tasks
```

### Mixed Inline and $ref

```yaml
# You can mix both patterns in the same workflow
agents:
  # Atomic agent via reference
  summarize:
    $ref: ./agents/atomic/summarize/summarize.yaml
  
  # Inline custom agent
  custom_agent:
    prompt: "Custom logic here..."
    tools: ["python"]
```

## Composition Patterns

### In Chain Workflow

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: summarize
        input: "{{ email }}"
      - agent: classify  
        input: "{{ steps[0].response }}"
```

### In DAG Workflow

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: summarize
        agent: summarize
        input: "{{ email }}"
      - id: classify
        depends_on: [summarize]
        agent: classify
        input: "{{ tasks.summarize.response }}"
```

### In Graph Pattern

```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: summarize
        agent: summarize
      - id: classify
        agent: classify
    edges:
      - from: start
        to: summarize
      - from: summarize
        to: classify
```

## Common Patterns

### Email Processing

```yaml
# agents/atomic/summarize_customer_email/summarize_customer_email.yaml
agents:
  summarize_customer_email:
    prompt: "Return summary and 3 bullet points."
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json
```

```json
// agents/atomic/summarize_customer_email/schemas/input.json
{
  "type": "object",
  "properties": {
    "subject": { "type": "string" },
    "body": { "type": "string" }
  },
  "required": ["subject", "body"]
}
```

```json
// agents/atomic/summarize_customer_email/schemas/output.json
{
  "type": "object",
  "properties": {
    "summary": { "type": "string", "maxLength": 300 },
    "bullets": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 3,
      "maxItems": 3
    }
  },
  "required": ["summary", "bullets"]
}
```

### Classification

```yaml
# agents/atomic/classify_ticket_priority/classify_ticket_priority.yaml
agents:
  classify_ticket_priority:
    prompt: "Output priority (low/medium/high/urgent) with rationale."
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json
```

```json
// agents/atomic/classify_ticket_priority/schemas/output.json
{
  "type": "object",
  "properties": {
    "priority": {
      "type": "string",
      "enum": ["low", "medium", "high", "urgent"]
    },
    "rationale": { "type": "string" }
  },
  "required": ["priority", "rationale"]
}
```

## Best Practices

### Design

1. **Single responsibility** — One focused capability per agent
2. **Explicit contracts** — Always define input/output schemas
3. **Minimal tools** — Use fewest tools necessary (ideally zero)
4. **Clear prompts** — Explicit about output format
5. **Descriptive names** — Use `verb_noun` pattern

### Testing

1. **Minimum 3 test cases** per agent (happy path + 2 edge cases)
2. **Test contracts, not content** — Validate structure, not exact text
3. **Add regression tests** when bugs are found
4. **Use JSON report** for CI/CD integration

### Schemas

1. **Be specific** — Use constraints (minLength, maxLength, pattern, enum)
2. **Reject extras** — Set `additionalProperties: false`
3. **Document everything** — Add descriptions to all properties
4. **Start simple** — Begin with required fields only

### Performance

1. **Use smaller models** — `gpt-4o-mini` for simple tasks
2. **Leverage caching** — Agents with identical configs are reused
3. **Parallelize** — Use parallel/workflow patterns for independent agents

## Troubleshooting

### Agent Not Found
```bash
Error: Atomic agent 'my_agent' not found
```
→ Check `agents/atomic/my_agent/my_agent.yaml` exists and has `strands.io/agent_type: atomic` label

### Input Validation Failure
```bash
Error: Input validation failed
  - 'field' is required but missing
```
→ Review `agents/atomic/my_agent/schemas/input.json` and ensure input JSON has all required fields

### Output Validation Warning
```bash
⚠ Output validation warning: 'field' does not match schema
```
→ Adjust prompt to be more explicit about output format or simplify output schema

### Schema Not Found
```bash
Error: Input schema not found: agents/atomic/my_agent/schemas/input.json
```
→ Verify schema file exists and path is correct (relative to manifest, should be `./schemas/input.json`)

### $ref Composition Errors

**Reference not found**:
```bash
Error: Agent reference not found: ../agents/atomic/missing.yaml
```
→ Verify path is correct relative to current workflow file

**Not an atomic agent**:
```bash
Error: Invalid agent reference: atomic agent must have exactly 1 agent, found 2
```
→ Referenced spec must contain exactly one agent (atomic agents are single-purpose)

**Nested references**:
```bash
Error: Nested agent references not allowed
```
→ Atomic agents cannot contain `$ref` to other agents (must be self-contained)

**Validation after reference resolution**:
```bash
Validation failed: Additional properties are not allowed ('prompt' was unexpected)
```
→ After `$ref` is resolved, agent has full definition. Check for conflicting inline fields.

## See Also

- [Tutorial: Getting Started with Atomic Agents](../tutorials/atomic-agents.md)
- [How-to: Work with Atomic Agents](../howto/atomic-agents.md)
- [Explanation: Atomic Agents Concept](../explanation/atomic-agents.md)
- [CLI Reference](../reference/cli.md#atomic-subcommands)

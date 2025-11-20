---
title: Working with Atomic Agents
description: Practical guide for creating, testing, validating, and composing atomic agents
keywords: atomic agents, how-to, testing, validation, composition, workflows
---

# Working with Atomic Agents

This guide covers common tasks and patterns for working with atomic agents in Strands CLI.

## Creating Atomic Agents

### Scaffold a New Atomic Agent

The fastest way to create a new atomic agent is with the `init` command:

```bash
strands atomic init <name> [--domain <domain>] [--capability <capability>]
```

**Example**:

```bash
strands atomic init extract_invoice_data \
  --domain finance \
  --capability extraction
```

This generates:

- `agents/atomic/extract_invoice_data/` — Self-contained agent directory
  - `extract_invoice_data.yaml` — Manifest with metadata labels
  - `schemas/input.json` — Input contract template
  - `schemas/output.json` — Output contract template
  - `tests.yaml` — Test suite skeleton
  - `examples/sample.json` — Sample input fixture

### Customize the Generated Files

After scaffolding, customize each file:

1. **Manifest** (`agents/atomic/<name>/<name>.yaml`):
   - Refine the `prompt` to be precise and focused
   - Adjust `runtime.model_id` for your provider/model
   - Add tools if needed (keep minimal for atomic agents)
   - Update template variables in `pattern.config.steps[0].input`

2. **Input Schema** (`agents/atomic/<name>/schemas/input.json`):
   - Define required and optional fields
   - Add constraints (minLength, maxLength, pattern, enum, etc.)
   - Provide clear descriptions for each property
   - Set `additionalProperties: false` to prevent unexpected fields

3. **Output Schema** (`agents/atomic/<name>/schemas/output.json`):
   - Define the expected response structure
   - Add validation rules (e.g., `maxItems` for arrays, `pattern` for strings)
   - Ensure required fields match what your prompt instructs the model to return

4. **Test Suite** (`agents/atomic/<name>/tests.yaml`):
   - Add multiple test cases covering happy path and edge cases
   - Define expectations for each case (schema validation + custom checks)

### Create Atomic Agents Manually

If you prefer manual creation, follow this structure:

```yaml
version: 0
name: my_atomic_agent
description: Brief description of what this agent does.

runtime:
  provider: openai  # or bedrock, ollama
  model_id: gpt-4o-mini

agents:
  my_atomic_agent:
    prompt: |
      Clear, focused instructions for the model.
      Specify output format expectations.
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json

metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: <domain>
    strands.io/capability: <capability>
    strands.io/version: v1

pattern:
  type: chain
  config:
    steps:
      - agent: my_atomic_agent
        input: |
          {{ inputs.values.field1 }}
          {{ inputs.values.field2 }}
```

**Requirements**:

- ✅ Exactly one agent definition
- ✅ Pattern is `chain` with one step OR `workflow` with one task
- ✅ `metadata.labels.strands.io/agent_type: atomic` present
- ✅ Both `input_schema` and `output_schema` defined (recommended)
- ✅ Runtime configuration present

## Validating Atomic Agents

### Check Atomic Invariants

Validate that your agent conforms to atomic agent rules:

```bash
strands atomic validate <name>
```

**What it checks**:

- ✅ Exactly one agent defined
- ✅ Single-step pattern (chain or workflow)
- ✅ No references to other agents/workflows
- ✅ Input and output schema files exist and are valid JSON Schema
- ✅ Runtime configuration is complete

**Example output**:

```
✓ Atomic agent validation passed: summarize_customer_email

Checks:
  ✓ Manifest structure valid
  ✓ Exactly one agent defined
  ✓ Single-step pattern (chain)
  ✓ Input schema exists: schemas/summarize_customer_email_input.json
  ✓ Output schema exists: schemas/summarize_customer_email_output.json
  ✓ Runtime configuration complete
```

### Validate Against Workflow Schema

For full schema validation:

```bash
strands validate agents/atomic/<name>.yaml
```

This uses the standard workflow schema validator and ensures your atomic agent is also a valid workflow spec.

## Running Atomic Agents

### Execute with Input File

```bash
strands atomic run <name> --input-file <path> [--output-file <path>]
```

**Example**:

```bash
strands atomic run summarize_customer_email \
  --input-file examples/atomic/email1.json \
  --output-file artifacts/summary1.json
```

**Execution flow**:

1. Load manifest and resolve schemas
2. Read and parse input JSON
3. **Validate input** against `input_schema` (fail fast if invalid)
4. Execute agent with validated input
5. **Validate output** against `output_schema` (warn if invalid but still write)
6. Write result to output file or stdout

### Handle Input Validation Errors

If input doesn't match the schema:

```bash
$ strands atomic run summarize_customer_email --input-file bad_input.json

✗ Input validation failed:
  - 'subject' is required but missing
  - 'extra_field' is not allowed (additionalProperties: false)

Schema: schemas/summarize_customer_email_input.json
```

### Handle Output Validation Errors

If the model's response doesn't match the output schema:

```bash
$ strands atomic run summarize_customer_email --input-file email.json

⚠ Output validation warning:
  - 'bullets' must have exactly 3 items (got 2)
  
Raw output written to: artifacts/output.json
Schema: schemas/summarize_customer_email_output.json
```

The CLI writes the raw output even on validation failure so you can inspect and debug.

### Run with Different Providers

Override the provider at runtime using environment variables:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
strands atomic run my_agent --input-file input.json

# Bedrock
export AWS_PROFILE=my-profile
# Edit manifest to set runtime.provider: bedrock
strands atomic run my_agent --input-file input.json

# Ollama
# Edit manifest to set runtime.provider: ollama
strands atomic run my_agent --input-file input.json
```

## Testing Atomic Agents

### Define Test Cases

Create `tests/<name>_tests.yaml`:

```yaml
tests:
  # Happy path test
  - name: standard_case
    input: ./examples/atomic/standard_input.json
    expect:
      output_schema: ./schemas/my_agent_output.json
      checks:
        - type: has_keys
          keys: ["field1", "field2"]
  
  # Edge case: minimal input
  - name: minimal_input
    input: ./examples/atomic/minimal_input.json
    expect:
      output_schema: ./schemas/my_agent_output.json
  
  # Edge case: maximum length input
  - name: long_input
    input: ./examples/atomic/long_input.json
    expect:
      output_schema: ./schemas/my_agent_output.json
      checks:
        - type: max_length
          field: summary
          value: 500
```

**Available check types**:

- `has_keys` — Ensure keys exist in output
- `max_length` — String field length constraint
- `min_length` — String field minimum length
- `regex_match` — Field matches pattern
- `contains` — Field contains substring
- `numeric_range` — Number field within min/max

### Run All Tests

```bash
strands atomic test <name>
```

**Example output**:

```
Test suite: summarize_customer_email
✓ [PASS] standard_case (1.2s)
✓ [PASS] minimal_input (0.9s)
✗ [FAIL] long_input (1.5s)
  - Output validation failed: 'summary' exceeds max length (512 > 500)

2/3 tests passed
```

### Run Specific Tests

Use `--filter` to run a subset of tests:

```bash
strands atomic test <name> --filter "standard*"
```

### Generate JSON Report for CI/CD

```bash
strands atomic test <name> --json > test-results.json
```

**Output format**:

```json
{
  "agent": "summarize_customer_email",
  "total": 3,
  "passed": 2,
  "failed": 1,
  "results": [
    {
      "name": "standard_case",
      "status": "passed",
      "duration_seconds": 1.2
    },
    {
      "name": "minimal_input",
      "status": "passed",
      "duration_seconds": 0.9
    },
    {
      "name": "long_input",
      "status": "failed",
      "duration_seconds": 1.5,
      "error": "Output validation failed: 'summary' exceeds max length"
    }
  ]
}
```

### Integrate with CI/CD

**GitHub Actions example**:

```yaml
name: Test Atomic Agents

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install Strands CLI
        run: uv pip install strands-cli
      
      - name: Test atomic agents
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          strands atomic test summarize_customer_email --json
          strands atomic test classify_ticket_priority --json
```

## Discovering Atomic Agents

### List All Atomic Agents

```bash
strands atomic list
```

**Example output**:

```
Atomic Agents:
- summarize_customer_email
  path: agents/atomic/summarize_customer_email.yaml
  domain: customer_service
  capability: summarization
  version: v1

- classify_ticket_priority
  path: agents/atomic/classify_ticket_priority.yaml
  domain: customer_service
  capability: classification
  version: v1

- extract_invoice_data
  path: agents/atomic/extract_invoice_data.yaml
  domain: finance
  capability: extraction
  version: v1
```

### List All Agents (Including Non-Atomic)

```bash
strands atomic list --all
```

This shows all agents with their `agent_type` labels, including orchestrators, routers, and evaluators.

### Get Structured Output

```bash
strands atomic list --json
```

**Output**:

```json
{
  "agents": [
    {
      "name": "summarize_customer_email",
      "path": "agents/atomic/summarize_customer_email.yaml",
      "type": "atomic",
      "domain": "customer_service",
      "capability": "summarization",
      "version": "v1",
      "input_schema": "schemas/summarize_customer_email_input.json",
      "output_schema": "schemas/summarize_customer_email_output.json"
    }
  ]
}
```

### Inspect Agent Details

```bash
strands atomic describe <name>
```

Or in JSON format:

```bash
strands atomic describe <name> --format json
```

## Composing Atomic Agents

### Use in Orchestrator Pattern

Atomic agents work as workers in orchestrator-workers patterns:

```yaml
version: 0
name: customer_support_orchestrator
runtime:
  provider: openai
  model_id: gpt-4o

agents:
  orchestrator:
    prompt: |
      You are a customer support orchestrator.
      Analyze the ticket and decide which workers to call.

pattern:
  type: orchestrator_workers
  config:
    orchestrator: orchestrator
    workers:
      - $ref: ./agents/atomic/summarize_customer_email.yaml#/agents/summarize_customer_email
      - $ref: ./agents/atomic/classify_ticket_priority.yaml#/agents/classify_ticket_priority
      - $ref: ./agents/atomic/extract_invoice_data.yaml#/agents/extract_invoice_data
    max_iterations: 3
```

### Use in Graph/DAG Workflows

Compose atomic agents as nodes in a graph:

```yaml
version: 0
name: multi_step_analysis
runtime:
  provider: openai
  model_id: gpt-4o-mini

pattern:
  type: graph
  config:
    nodes:
      - id: summarize
        agent:
          $ref: ./agents/atomic/summarize_customer_email.yaml#/agents/summarize_customer_email
        input: |
          Subject: {{ inputs.values.subject }}
          Body: {{ inputs.values.body }}
      
      - id: classify
        agent:
          $ref: ./agents/atomic/classify_ticket_priority.yaml#/agents/classify_ticket_priority
        input: |
          Summary: {{ nodes.summarize.response }}
      
      - id: route
        agent: router_agent
        input: |
          Priority: {{ nodes.classify.response }}
          Summary: {{ nodes.summarize.response }}
    
    edges:
      - from: start
        to: summarize
      
      - from: summarize
        to: classify
      
      - from: classify
        to: route
```

### Chain Multiple Atomic Agents

```yaml
version: 0
name: chained_analysis
runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  summarize:
    $ref: ./agents/atomic/summarize_customer_email.yaml#/agents/summarize_customer_email
  
  classify:
    $ref: ./agents/atomic/classify_ticket_priority.yaml#/agents/classify_ticket_priority

pattern:
  type: chain
  config:
    steps:
      - agent: summarize
        input: |
          Subject: {{ inputs.values.subject }}
          Body: {{ inputs.values.body }}
      
      - agent: classify
        input: |
          Email summary: {{ steps[0].response }}
```

## Managing Schemas

### Schema Organization

Recommended directory structure:

```
schemas/
  # Input schemas
  summarize_customer_email_input.json
  classify_ticket_priority_input.json
  
  # Output schemas
  summarize_customer_email_output.json
  classify_ticket_priority_output.json
  
  # Shared schemas (optional)
  _common/
    email.json
    customer.json
```

### Reuse Common Schemas

Use JSON Schema `$ref` to reuse definitions:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "email": {
      "$ref": "./_common/email.json"
    },
    "customer_id": {
      "type": "string",
      "pattern": "^CUST-[0-9]{6}$"
    }
  },
  "required": ["email"]
}
```

### Version Your Schemas

When making breaking changes to schemas:

1. Create a new version of the atomic agent (`v2`)
2. Create new schema files with version suffix:
   - `summarize_customer_email_input_v2.json`
   - `summarize_customer_email_output_v2.json`
3. Update `metadata.labels.strands.io/version: v2`
4. Maintain old version for backwards compatibility

## Best Practices

### Design Principles

1. **Single Responsibility** — Each atomic agent does one thing well
2. **Explicit Contracts** — Always define input/output schemas
3. **Minimal Tools** — Use the fewest tools necessary (ideally zero)
4. **Clear Prompts** — Be explicit about output format in the prompt
5. **Comprehensive Tests** — Cover happy path and edge cases

### Naming Conventions

- **Agents**: Use `verb_noun` pattern (e.g., `summarize_customer_email`, `classify_ticket_priority`)
- **Domains**: Use lowercase, underscored (e.g., `customer_service`, `finance`, `legal`)
- **Capabilities**: Use single word when possible (e.g., `summarization`, `classification`, `extraction`)

### Schema Design Tips

1. **Be specific**: Use constraints like `minLength`, `maxLength`, `pattern`, `enum`
2. **Reject extras**: Set `additionalProperties: false` to catch unexpected fields
3. **Validate semantics**: Use `pattern` for formats (emails, IDs, dates)
4. **Document everything**: Add `description` to all properties
5. **Start simple**: Begin with required fields only, add optional fields as needed

### Testing Strategy

1. **Minimum 3 test cases per agent**:
   - Happy path (standard input)
   - Edge case 1 (minimal/boundary input)
   - Edge case 2 (maximum/complex input)

2. **Add regression tests** when bugs are found

3. **Test contracts, not content**:
   - Validate structure and types (schema validation)
   - Check key presence and constraints (has_keys, max_length)
   - Avoid brittle exact-match assertions on generated text

### Performance Optimization

1. **Model selection**: Use smaller models (e.g., `gpt-4o-mini`) for simple atomic tasks
2. **Caching**: Strands CLI caches model clients automatically when reusing agents
3. **Parallel execution**: Use parallel or workflow patterns to run independent atomic agents concurrently

## Troubleshooting

### Agent Not Found

```bash
$ strands atomic run my_agent --input-file input.json
Error: Atomic agent 'my_agent' not found
```

**Solutions**:

- Check that `agents/atomic/my_agent.yaml` exists
- Verify `metadata.labels.strands.io/agent_type: atomic` is present
- Run `strands atomic list` to see all discovered agents

### Input Validation Failure

```bash
$ strands atomic run my_agent --input-file input.json
Error: Input validation failed
  - 'required_field' is required but missing
```

**Solutions**:

- Review `schemas/<name>_input.json` for required fields
- Ensure your input JSON includes all required properties
- Check that field types match (string vs number, etc.)

### Output Validation Warning

```bash
⚠ Output validation warning: 'field' does not match schema
```

**Solutions**:

- Review the model's output in the artifact file
- Adjust the prompt to be more explicit about output format
- Simplify the output schema if the model struggles with complex structures
- Use structured output features if your provider supports them

### Schema Not Found

```bash
Error: Input schema not found: schemas/my_agent_input.json
```

**Solutions**:

- Verify the schema file exists at the specified path
- Check that the path in the manifest is correct (relative to manifest location)
- Use `strands atomic validate <name>` to check schema file existence

## See Also

- [Tutorial: Getting Started with Atomic Agents](../tutorials/atomic-agents.md) — Step-by-step first agent
- [Explanation: Atomic Agents Concept](../explanation/atomic-agents.md) — Design philosophy
- [CLI Reference: atomic commands](../reference/cli.md#atomic-subcommands) — Complete command docs
- [Schema Reference](../reference/schema.md) — Workflow schema specification

---
title: Getting Started with Atomic Agents
description: Learn how to create, run, and test single-purpose reusable agents with input/output contracts
keywords: atomic agents, tutorial, quickstart, contracts, schemas, testing
---

# Getting Started with Atomic Agents

This tutorial walks you through creating your first atomic agent—a single-purpose, reusable agent with a well-defined contract that can be composed into larger workflows.

## What You'll Build

You'll create a simple email summarization agent that:

- Takes an email (subject and body) as structured input
- Validates the input against a JSON Schema
- Generates a concise summary with bullet points
- Validates the output against a JSON Schema
- Can be tested with automated test cases

## Prerequisites

- Strands CLI installed (`uv pip install strands-cli`)
- An OpenAI API key set in your environment (`OPENAI_API_KEY`)
- Basic familiarity with YAML and JSON

## Step 1: Scaffold Your Atomic Agent

Use the `atomic init` command to generate the boilerplate:

```bash
strands atomic init summarize_customer_email \
  --domain customer_service \
  --capability summarization
```

This creates a self-contained directory structure:

```
agents/atomic/summarize_customer_email/
  summarize_customer_email.yaml
  schemas/
    input.json
    output.json
  examples/
    sample.json
  tests.yaml
```

## Step 2: Understand the Generated Manifest

Open `agents/atomic/summarize_customer_email/summarize_customer_email.yaml`:

```yaml
version: 0
name: summarize_customer_email
description: Summarize a single customer email into a concise digest.

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  summarize_customer_email:
    prompt: |
      You are an expert customer support summarizer.
      Return a short summary and 3 bullet points of key details.
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json

metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: customer_service
    strands.io/capability: summarization
    strands.io/version: v1

pattern:
  type: chain
  config:
    steps:
      - agent: summarize_customer_email
        input: |
          Please summarize this email:

          Subject: {{ inputs.values.subject }}
          Body: {{ inputs.values.body }}
```

**Key elements**:

- **`metadata.labels.strands.io/agent_type: atomic`** — Marks this as an atomic agent for discovery
- **`input_schema` and `output_schema`** — Define the contract using relative paths within the agent directory
- **Single-step pattern** — Atomic agents execute one focused capability
- **Template variables** — `{{ inputs.values.* }}` pulls from validated input

## Step 3: Define Your Input Contract

Edit `agents/atomic/summarize_customer_email/schemas/input.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "subject": {
      "type": "string",
      "description": "Email subject line",
      "minLength": 1
    },
    "body": {
      "type": "string",
      "description": "Email body content",
      "minLength": 1
    }
  },
  "required": ["subject", "body"],
  "additionalProperties": false
}
```

This schema ensures callers provide exactly what the agent needs—no more, no less.

## Step 4: Define Your Output Contract

Edit `agents/atomic/summarize_customer_email/schemas/output.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "summary": {
      "type": "string",
      "description": "Concise summary (max 300 chars)",
      "maxLength": 300
    },
    "bullets": {
      "type": "array",
      "description": "3 key detail bullet points",
      "items": { "type": "string" },
      "minItems": 3,
      "maxItems": 3
    }
  },
  "required": ["summary", "bullets"],
  "additionalProperties": false
}
```

This ensures the agent's output has a predictable structure for downstream consumers.

## Step 5: Create Test Input

Create `agents/atomic/summarize_customer_email/examples/sample.json`:

```json
{
  "subject": "Shipping Delay for Order #12345",
  "body": "Hi, I ordered a laptop on Dec 1st (Order #12345) and was promised delivery by Dec 10th. It's now Dec 15th and the tracking still shows 'processing'. Can you please check on this? I need it for a client presentation on Dec 18th. Thanks, Sarah Chen"
}
```

## Step 6: Run Your Atomic Agent

Execute the agent with your test input:

```bash
strands atomic run summarize_customer_email \
  --input-file agents/atomic/summarize_customer_email/examples/sample.json \
  --output-file artifacts/summary_output.json
```

**What happens**:

1. CLI validates `summarize_email_input.json` against the input schema
2. Agent executes with the validated input
3. CLI validates the model's response against the output schema
4. Result is written to `artifacts/summary_output.json`

**Expected output**:

```json
{
  "summary": "Customer Sarah Chen reports Order #12345 (laptop) is delayed 5 days past promised delivery and needs it urgently for Dec 18th client presentation.",
  "bullets": [
    "Order placed Dec 1st, promised delivery Dec 10th",
    "Currently Dec 15th, tracking shows 'processing'",
    "Urgent: needed for client presentation Dec 18th"
  ]
}
```

## Step 7: Add Automated Tests

Edit `agents/atomic/summarize_customer_email/tests.yaml`:

```yaml
tests:
  - name: simple_email
    input: ./examples/sample.json
    expect:
      output_schema: ./schemas/output.json
      checks:
        - type: has_keys
          keys: ["summary", "bullets"]
        - type: max_length
          field: summary
          value: 300
```

Run the test suite:

```bash
strands atomic test summarize_customer_email
```

**Output**:

```
Test suite: summarize_customer_email
✓ [PASS] simple_email

1/1 tests passed
```

## Step 8: Discover Your Atomic Agent

List all atomic agents in your repository:

```bash
strands atomic list
```

**Output**:

```
Atomic Agents:
- summarize_customer_email
  path: agents/atomic/summarize_customer_email/summarize_customer_email.yaml
  domain: customer_service
  capability: summarization
  version: v1
```

Inspect the agent's details:

```bash
strands atomic describe summarize_customer_email
```

**Output**:

```
Name: summarize_customer_email
Description: Summarize a single customer email into a concise digest.
Type: atomic
Domain: customer_service
Capability: summarization
Version: v1

Runtime:
  Provider: openai
  Model: gpt-4o-mini

Contracts:
  Input Schema: agents/atomic/summarize_customer_email/schemas/input.json (valid)
  Output Schema: agents/atomic/summarize_customer_email/schemas/output.json (valid)

Tools: (none)
```

## Step 9: Compose into Workflows with $ref

The new `$ref` feature enables true composition—reference atomic agents instead of duplicating their definitions:

```yaml
# workflow.yaml
version: 0
name: customer_support_pipeline
runtime:
  provider: openai
  model_id: gpt-4o-mini

inputs:
  required:
    subject: string
    body: string

agents:
  # Reference atomic agent - inherits prompt, schemas, everything
  summarize_email:
    $ref: ./agents/atomic/summarize_customer_email/summarize_customer_email.yaml
  
  # Reference with override - use atomic agent but with different model
  generate_response:
    $ref: ./agents/atomic/draft_response/draft_response.yaml
    model_id: gpt-4o  # Override model for this workflow

pattern:
  type: chain
  config:
    steps:
      - agent: summarize_email
        input: |
          {
            "subject": {{ subject | tojson }},
            "body": {{ body | tojson }}
          }
      
      - agent: generate_response
        input: |
          {
            "summary": {{ steps[0].response | tojson }}
          }
```

**Benefits of $ref composition**:

- ✅ **Single source of truth**: Update atomic agent once, all workflows automatically use new version
- ✅ **No duplication**: No need to copy prompts, schemas, or configurations
- ✅ **Contract enforcement**: Schemas guaranteed to match atomic agent
- ✅ **Override support**: Can customize model, tools, inference params per usage
- ✅ **Backward compatible**: Inline agent definitions still fully supported
- ✅ **Portable**: Self-contained agent directories can be moved or extracted to centralized repos

Run the workflow:

```bash
strands run workflow.yaml \
  --var subject="Shipping Delay for Order #12345" \
  --var body="Hi, I ordered a laptop..."
```

### Allowed Overrides

When using `$ref`, you can override these fields:

```yaml
agents:
  my_agent:
    $ref: ./agents/atomic/my_agent.yaml
    model_id: gpt-4o          # Use different model
    provider: anthropic       # Use different provider  
    tools: ["http_request"]   # Override tools
    inference:                # Override inference params
      temperature: 0.7
      max_tokens: 1000
```

### Reference Resolution

- Paths are **relative to the current workflow file**
- Schemas in atomic agents are **resolved relative to the atomic agent file**
- This keeps atomic agents portable and self-contained

### Error Handling

Common errors when using `$ref`:

```bash
# Missing file
Error: Agent reference not found: ./agents/atomic/missing.yaml

# Not atomic (multiple agents)
Error: Invalid agent reference: atomic agent must have exactly 1 agent, found 2

# Nested references not allowed
Error: Nested agent references not allowed: atomic agents must be self-contained
```

## Next Steps

Now that you've created your first atomic agent:

- **Add more test cases** with edge cases (long emails, multi-topic emails, etc.)
- **Create related atomic agents** (e.g., `classify_ticket_priority`, `extract_invoice_lines`)
- **Build orchestrator patterns** that coordinate multiple atomic agents
- **Set up CI/CD** to run `strands atomic test` on every commit

## Key Takeaways

1. **Atomic agents are single-purpose** — One capability, one well-defined job
2. **Contracts enable composition** — Input/output schemas make agents predictable building blocks
3. **Testing is built-in** — Validate behavior with test fixtures before deploying
4. **Discovery is automatic** — `strands atomic list` finds agents by metadata labels
5. **Reusability is the goal** — Write once, compose into many workflows

## See Also

- [How-to: Work with Atomic Agents](../howto/atomic-agents.md) — Common tasks and patterns
- [Explanation: Atomic Agents Concept](../explanation/atomic-agents.md) — Design rationale and architecture
- [CLI Reference: atomic commands](../reference/cli.md#atomic-subcommands) — Complete command documentation
- [Tool Development Guide](../../docs/TOOL_DEVELOPMENT.md) — Building native tools for atomic agents

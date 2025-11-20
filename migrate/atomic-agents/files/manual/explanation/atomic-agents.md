---
title: Atomic Agents
description: Design philosophy, architecture, and rationale for single-purpose reusable agents with contracts
keywords: atomic agents, architecture, design, contracts, composition, governance
---

# Atomic Agents

This document explains the concept, design rationale, and architecture of atomic agents in Strands CLI.

## What Are Atomic Agents?

An **atomic agent** is a single-purpose, reusable agent specification with a well-defined input/output contract. The term "atomic" signifies:

- **Indivisible** — The smallest useful unit of agent capability
- **Self-contained** — Everything needed to execute is in one manifest
- **Composable** — Can be combined with other agents into larger workflows
- **Testable** — Behavior is predictable and verifiable
- **Governed** — Can be certified, versioned, and controlled independently

Atomic agents are the building blocks for complex multi-agent workflows, orchestrators, and graph-based agent systems.

## Why Atomic Agents?

### The Problem: Agent Sprawl and Duplication

Without a concept of atomic agents:

- **Duplication**: The same capability (e.g., "summarize an email") is re-implemented in multiple workflows
- **Inconsistency**: Each implementation has slightly different behavior, making debugging hard
- **No testing**: Inline agent definitions can't be tested in isolation
- **No discoverability**: Teams don't know what agents already exist
- **No governance**: Can't certify or version individual capabilities

### The Solution: Reusable Building Blocks

Atomic agents address these issues by:

1. **Defining a contract**: Input/output schemas make behavior predictable
2. **Enabling reuse**: One implementation, many consumers
3. **Supporting testing**: Each agent has its own test suite
4. **Enabling discovery**: `strands atomic list` shows what's available
5. **Facilitating governance**: Version, certify, and control individual agents

## Design Principles

### 1. Single Responsibility

Each atomic agent does **exactly one thing**. Examples:

- ✅ `summarize_customer_email` — Takes an email, returns a summary
- ✅ `classify_ticket_priority` — Takes a ticket, returns priority level
- ❌ `process_customer_ticket` — Too broad (summarize + classify + route)

**Why?** Single-purpose agents are:

- Easier to test
- More reusable across contexts
- Simpler to understand and maintain
- Cacheable at runtime (Strands CLI reuses agents with identical configs)

### 2. Explicit Contracts

Every atomic agent defines:

- **Input schema** — JSON Schema specifying required inputs
- **Output schema** — JSON Schema specifying expected outputs

**Why?** Contracts enable:

- **Validation** — Catch errors before execution
- **Composition** — Chain agents with confidence (output of A matches input of B)
- **Documentation** — Schemas are self-documenting
- **Type safety** — Downstream consumers know what to expect

### 3. Minimal Dependencies

Atomic agents:

- Should use **zero to few tools** (ideally zero)
- Should **not reference other agents** (no nested workflows)
- Should rely only on **model capabilities + simple tools**

**Why?** Minimizing dependencies:

- Reduces failure modes
- Simplifies testing
- Improves portability (easier to move between providers)
- Enhances performance (less overhead)

### 4. Testability First

Every atomic agent has:

- A test suite (`agents/atomic/<name>/tests.yaml`)
- Multiple test cases (happy path + edge cases)
- Automated validation of contracts

**Why?** Testing ensures:

- Agents behave correctly before deployment
- Regression detection when models change
- Confidence when composing into larger workflows
- Compliance with governance requirements

### 5. Discoverable by Convention

Atomic agents follow conventions:

- **Location**: `agents/atomic/<name>/<name>.yaml` (self-contained directory)
- **Metadata**: `strands.io/agent_type: atomic` label
- **Naming**: Descriptive verb-noun patterns
- **Organization**: Grouped by domain and capability

**Why?** Conventions enable:

- Automatic discovery via `strands atomic list`
- IDE autocomplete and tooling support
- Clear project organization
- Cross-team reuse
- Portability to centralized repositories

## Architecture

### Representation as Workflow Specs

Atomic agents are **standard workflow specs** (version 0) with specific constraints:

```yaml
version: 0                    # Standard workflow version
name: my_atomic_agent         # Agent identifier
description: "..."            # Human-readable description

runtime:                      # Required: agent must be runnable standalone
  provider: openai
  model_id: gpt-4o-mini

agents:                       # Exactly one agent definition
  my_atomic_agent:
    prompt: "..."
    input_schema: ./schemas/input.json
    output_schema: ../schemas/my_atomic_agent_output.json

metadata:                     # Atomic marker + labels
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: <domain>
    strands.io/capability: <capability>
    strands.io/version: v1

pattern:                      # Single-step execution
  type: chain                 # Or workflow with one task
  config:
    steps:
      - agent: my_atomic_agent
        input: "{{ inputs.values.field }}"
```

**Key architectural decisions**:

1. **Reuse existing schema**: No new file format; atomic agents are just constrained workflows
2. **Use existing runtime**: No special executor; atomic agents run via `run_single_agent`
3. **Validate at CLI time**: `strands atomic` commands enforce atomic invariants; `strands run` does not

### Atomic Invariants

A workflow spec is a valid atomic agent if and only if:

- ✅ Exactly **one agent** defined in `agents` map
- ✅ Pattern is **`chain` with one step** OR **`workflow` with one task** (no dependencies)
- ✅ **No references** to other agents or workflows
- ✅ **Runtime present** (agent must be runnable standalone)
- ✅ (Recommended) `input_schema` and `output_schema` defined

The `strands atomic validate` command checks these invariants.

### Metadata Schema

Atomic agents use standardized labels in `metadata.labels`:

| Label | Required | Description | Example |
|-------|----------|-------------|---------|
| `strands.io/agent_type` | Yes | Always `"atomic"` for atomic agents | `atomic` |
| `strands.io/domain` | Recommended | Business domain or category | `customer_service`, `finance`, `legal` |
| `strands.io/capability` | Recommended | Core capability provided | `summarization`, `classification`, `extraction` |
| `strands.io/version` | Recommended | Version identifier | `v1`, `v2` |
| `strands.io/eval_profile` | Optional | Evaluation workflow name | `summarization_v1` |

**Why labels?** Labels enable:

- Discovery via `strands atomic list --domain customer_service`
- Grouping and organization
- Governance workflows (e.g., "certify all v1 agents")
- Integration with external systems (CI/CD, catalogs, etc.)

### Contract Schema Format

Input and output schemas use **JSON Schema Draft 2020-12**:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "field1": {
      "type": "string",
      "description": "Field description",
      "minLength": 1
    }
  },
  "required": ["field1"],
  "additionalProperties": false
}
```

**Key features**:

- **Local file paths only** (no HTTP fetch in MVP)
- **Validated at runtime** by `strands atomic run` and `strands atomic test`
- **Not enforced by `strands run`** (general workflow executor doesn't validate contracts)

### Execution Model

When you run `strands atomic run <name> --input-file input.json`:

1. **Load manifest**: Parse YAML and validate against workflow schema
2. **Resolve schemas**: Load input/output schemas from file paths
3. **Validate input**: Check `input.json` against `input_schema`
4. **Merge input**: Populate `inputs.values` with validated data
5. **Execute agent**: Call `run_single_agent` (same as `strands run`)
6. **Validate output**: Check model response against `output_schema`
7. **Write result**: Save to `--output-file` or print to stdout

**Performance optimizations**:

- **Agent caching**: Agents with identical configs are reused within a workflow
- **Model client pooling**: `@lru_cache` ensures one HTTP client per (provider, model_id, region) tuple
- **Single event loop**: All async operations run in one `asyncio.run()` call

### Discovery Mechanism

`strands atomic list` discovers atomic agents via:

1. **Convention**: Scan `agents/atomic/**/*.yaml` recursively
2. **Metadata**: Check for `metadata.labels.strands.io/agent_type: atomic`

**Fallback**: If a manifest is in `agents/atomic/` but lacks the label, it's inferred as atomic.

**Future**: Support for cross-repo discovery via registry/catalog JSON files.

## Use Cases

### 1. Email Processing Pipeline

**Atomic agents**:

- `summarize_customer_email` — Condense email to summary + bullets
- `classify_ticket_priority` — Assign priority (low/medium/high/urgent)
- `extract_customer_info` — Parse name, email, account ID
- `detect_sentiment` — Classify sentiment (positive/negative/neutral)

**Composition** (orchestrator pattern):

```yaml
agents:
  summarize:
    $ref: ./agents/atomic/summarize_customer_email.yaml#/agents/summarize_customer_email
  classify:
    $ref: ./agents/atomic/classify_ticket_priority.yaml#/agents/classify_ticket_priority
  extract:
    $ref: ./agents/atomic/extract_customer_info.yaml#/agents/extract_customer_info
  sentiment:
    $ref: ./agents/atomic/detect_sentiment.yaml#/agents/detect_sentiment
  orchestrator:
    prompt: "Analyze email and delegate to appropriate worker"

pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: orchestrator
    worker_template:
      agent: summarize  # Single worker template (orchestrator assigns tasks dynamically)
```

**Note**: Orchestrator-workers uses a single `worker_template` that gets reused for all tasks. For multi-agent coordination where different agents handle different subtasks, use the **graph** or **workflow** pattern instead.

### 2. Document Analysis DAG

**Atomic agents**:

- `extract_text` — OCR or parse document to plain text
- `classify_document_type` — Identify document type (invoice, contract, receipt, etc.)
- `extract_invoice_lines` — Parse line items from invoice
- `extract_contract_terms` — Extract key terms from contract

**Composition** (graph pattern):

```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: extract
        agent: extract_text
      - id: classify
        agent: classify_document_type
      - id: invoice_parse
        agent: extract_invoice_lines
        condition: "{{ nodes.classify.response.type == 'invoice' }}"
      - id: contract_parse
        agent: extract_contract_terms
        condition: "{{ nodes.classify.response.type == 'contract' }}"
    edges:
      - from: start
        to: extract
      - from: extract
        to: classify
      - from: classify
        to: invoice_parse
      - from: classify
        to: contract_parse
```

Conditional branching based on document type.

### 3. Research Agent Swarm

**Atomic agents**:

- `search_web` — Query search engine and return top results
- `summarize_article` — Condense article to key points
- `fact_check` — Verify claims against sources
- `synthesize_findings` — Combine multiple summaries into coherent report

**Composition** (parallel pattern):

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: source1
        steps:
          - agent: search_web
            input: "{{ inputs.values.query }}"
          - agent: summarize_article
            input: "{{ branches.source1.steps[0].response }}"
      - id: source2
        steps:
          - agent: search_web
            input: "{{ inputs.values.query }}"
          - agent: summarize_article
            input: "{{ branches.source2.steps[0].response }}"
    reduce:
      agent: synthesize_findings
      input: |
        Source 1: {{ branches.source1.steps[1].response }}
        Source 2: {{ branches.source2.steps[1].response }}
```

Parallel execution of independent research paths.

## Governance and Evaluation

### Certification Workflow

Atomic agents can be certified before production use:

1. **Define evaluation profile**: Create `eval/<profile>.yaml` with quality metrics
2. **Label agents**: Add `strands.io/eval_profile: <profile>` to metadata
3. **Run evaluation**: External tool discovers agents by profile and runs eval workflow
4. **Store results**: Pass/fail status, scores, and regression checks
5. **Gate deployments**: CI/CD checks certification status before allowing production use

**Example**:

```yaml
# Agent metadata
metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/eval_profile: summarization_v1

# Evaluation workflow (eval/summarization_v1.yaml)
pattern:
  type: evaluator_optimizer
  config:
    evaluator: summarization_evaluator
    optimizer: null  # Eval-only mode
    max_iterations: 1
```

### Versioning Strategy

When atomic agents change:

- **Non-breaking changes** (prompt refinement, model upgrade):
  - Keep same version label (`v1`)
  - Use Git history for audit trail
  
- **Breaking changes** (schema change, behavior shift):
  - Create new version (`v2`)
  - Duplicate manifest and schemas with version suffix
  - Update `strands.io/version: v2`
  - Keep old version for backwards compatibility

**Example**:

```
agents/atomic/
  summarize_customer_email_v1.yaml
  summarize_customer_email_v2.yaml

schemas/
  summarize_customer_email_v1_input.json
  summarize_customer_email_v1_output.json
  summarize_customer_email_v2_input.json
  summarize_customer_email_v2_output.json
```

Workflows reference specific versions:

```yaml
agents:
  summarize:
    $ref: ./agents/atomic/summarize_customer_email_v1.yaml#/agents/summarize_customer_email
```

## Comparison to Other Approaches

### Atomic Agents vs. Inline Agent Definitions

| Aspect | Atomic Agents | Inline Definitions |
|--------|---------------|-------------------|
| **Reusability** | High (reference via `$ref`) | None (copy-paste) |
| **Testing** | Dedicated test suite | No isolation |
| **Discovery** | `strands atomic list` | Manual search |
| **Versioning** | Explicit labels | Git only |
| **Governance** | Certifiable | Difficult |

**When to use atomic agents**: Reusable capabilities used across multiple workflows.

**When to use inline**: One-off agents specific to a single workflow.

### Atomic Agents vs. Multi-Agent Systems

Atomic agents are **not** full multi-agent systems (like AutoGen, LangGraph, CrewAI). They are:

- **Simpler**: No agent-to-agent communication protocols
- **More predictable**: Explicit orchestration, not emergent behavior
- **Tool-focused**: Designed to be composed by workflows, not to compose themselves

**Atomic agents are building blocks. Workflows are the orchestration layer.**

### Atomic Agents vs. Tools

| Aspect | Atomic Agents | Tools |
|--------|---------------|-------|
| **Implementation** | Model-based (LLM) | Code-based (Python, HTTP) |
| **Complexity** | Handles nuanced tasks | Deterministic operations |
| **Examples** | Summarization, classification | HTTP requests, file I/O |
| **Schema** | Input + output schemas | Input schema only (tool spec) |

**Use atomic agents for**: Tasks requiring reasoning, language understanding, or synthesis.

**Use tools for**: Deterministic operations, API calls, file manipulation.

## Future Directions

### 1. Cross-Repo Discovery

Enable discovery of atomic agents across repositories via:

- **Catalog files**: `atomic-agents.json` index per repo
- **Registry service**: Centralized searchable registry
- **Namespacing**: `org/repo/agent` identifier format

### 2. Contract Evolution

Support for:

- **Semantic versioning**: `input_schema@v1.2.0`
- **Deprecation warnings**: Mark old schemas as deprecated
- **Migration guides**: Auto-generate migration docs for breaking changes

### 3. Advanced Evaluation

- **Regression testing**: Detect performance degradation across model versions
- **A/B testing**: Compare atomic agent variants
- **Cost tracking**: Monitor token usage per agent
- **Latency profiling**: Identify slow agents in workflows

### 4. Composition Patterns

- **Agent libraries**: Curated collections of domain-specific atomic agents
- **Template workflows**: Pre-built patterns (e.g., "email processing pipeline template")
- **Visual composition**: Drag-and-drop workflow builder for atomic agents

### 5. Runtime Optimizations

- **Batch execution**: Run same atomic agent on multiple inputs in parallel
- **Speculative execution**: Pre-warm likely downstream agents
- **Smart caching**: Cache agent responses for identical inputs

## Key Takeaways

1. **Atomic agents are single-purpose building blocks** with explicit contracts
2. **They're standard workflow specs** with additional constraints and metadata
3. **Contracts enable composition** and guarantee predictable behavior
4. **Discovery is automatic** via conventions and metadata labels
5. **Testing is first-class** with dedicated test suites and CLI support
6. **Governance is possible** through versioning, certification, and evaluation
7. **Reuse reduces duplication** and improves consistency across workflows

Atomic agents represent a **design philosophy**: build complex agent systems by composing simple, well-tested, contractually-bound units.

## See Also

- [Tutorial: Getting Started with Atomic Agents](../tutorials/atomic-agents.md) — Build your first atomic agent
- [How-to: Work with Atomic Agents](../howto/atomic-agents.md) — Common tasks and patterns
- [CLI Reference: atomic commands](../reference/cli.md#atomic-subcommands) — Command documentation
- [Schema Reference](../reference/schema.md) — Workflow schema specification
- [Explanation: Workflow Patterns](patterns.md) — How atomic agents fit into larger patterns

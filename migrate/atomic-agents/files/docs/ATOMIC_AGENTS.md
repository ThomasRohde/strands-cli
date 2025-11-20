# Atomic Agents for Strands CLI
**File:** `ATOMIC_AGENTS.md`  
**Status:** Draft – Developer Ready  
**Owner:** Strands CLI maintainers  
**Target Version:** v0.x

## 1. Overview

This document defines **Atomic Agents** as a first-class concept in `strands-cli`.
For the concrete implementation plan and CLI status, see `docs/ATOMIC_IMPLEMENTATION.md`.

In Strands, an **Atomic Agent** is:

- A single, self-contained `agent` spec (YAML)
- With a **narrow, well-defined capability**
- With a **stable input/output contract**, expressed via JSON Schema
- Designed to be **reused** across workflows and composed into higher-level patterns
- Small enough to be **governed, evaluated, and versioned** independently

Atomic Agents are the building blocks for more complex constructs such as orchestrators, routers, evaluators, and multi-step workflows.

This PRD introduces:
- Metadata and schema conventions to **mark and describe** atomic agents
- Directory conventions for **discovery and reuse**
- A **CLI surface** (`strands atomic ...`) for listing, inspecting, running, and testing atomic agents
- Hooks for **governance and evaluation**


## 2. Goals & Non‑Goals

### 2.1 Goals

1. **First-class concept:** Introduce “Atomic Agents” clearly in documentation, schema, and CLI, without breaking existing specs.
2. **Discoverability:** Provide conventions so tools (and humans) can quickly find and reuse atomic agents across projects.
3. **Contracts:** Encourage explicit, testable input/output contracts (JSON Schemas) for atomic agents.
4. **Composition:** Make it easy to compose atomic agents into orchestrators, graphs, and workflows.
5. **Testing & Governance:** Provide a minimal but clear path for validating atomic agents via fixtures and evaluation profiles.
6. **Developer Ergonomics:** Provide scaffolding to create new atomic agents with one command.

### 2.2 Non‑Goals

1. **New runtime engine:** We **do not** introduce a separate runtime for atomic agents; they use the existing Strands runtime.
2. **Hard type system / strict enforcement:** Atomic vs. non-atomic is a **convention + metadata**, not a hard runtime boundary (for now).
3. **Central registry service:** This PRD does not define a distributed registry of agents. Discovery is repo-local.
4. **Evaluation engine:** We do not define a new eval engine; we only specify how atomic agents hook into existing or future evaluation workflows.


## 3. Concept & Terminology

- **Atomic Agent**  
  A Strands agent spec (`kind: agent`) designed as a **single-purpose, reusable building block** with a stable contract. Marked with metadata `strands.io/agent_type: atomic`.

- **Composite Agent / Orchestrator / Router / Evaluator**  
  Agents and workflows that **coordinate** other agents. They may be specified with other `agent_type` labels (e.g., `orchestrator`, `router`, `evaluator`) and are not atomic.

- **Atomic Agent Library**  
  A repo-local collection of atomic agents (commonly under `./agents/atomic`) plus their schemas and tests.

- **Contract**  
  The combination of:
  - `input_schema` (JSON Schema)
  - `output_schema` (JSON Schema)
  - Any additional constraints defined in tests or evaluation profiles


## 4. User Stories

1. **As a developer**, I want to create a small, reusable agent (“summarize a single email”) that I can plug into multiple workflows without rewriting logic.
2. **As an architect**, I want to see a catalog of available atomic agents in a repo, including what they do and their contracts.
3. **As a workflow designer**, I want to compose existing atomic agents into orchestrator/worker patterns or graphs without having to modify the atomic agents.
4. **As a governance / risk owner**, I want a repeatable way to test and evaluate atomic agents, and certify specific versions for use in regulated workflows.
5. **As a CI/CD engineer**, I want to run automated tests for atomic agents and fail a build if they violate their declared schemas or expectations.


## 5. High-Level Design

### 5.1 Metadata Extension for Agent Specs

We extend `agent` specs with **optional** metadata and spec fields that characterize Atomic Agents.

**Example – Atomic Agent YAML:**

```yaml
kind: agent
version: 1
metadata:
  name: summarize_customer_email
  description: Summarize a single customer email into a short digest.
  labels:
    strands.io/agent_type: atomic             # <— NEW: agent type
    strands.io/domain: customer_service
    strands.io/capability: summarization
    strands.io/version: v1
    strands.io/eval_profile: summarization_v1 # <— OPTIONAL: eval profile name
spec:
  model:
    provider: openai
    name: gpt-4.1-mini
  instructions: |
    You are a specialized summarization micro-agent...
  input_schema:
    $ref: ./schemas/input.json
  output_schema:
    $ref: ./schemas/output.json
  tools: []
  inference:
    temperature: 0.2
```

Key decisions:

- **Atomic marker:**  
  Use `metadata.labels.strands.io/agent_type: atomic` to declare an atomic agent.
- **Contracts:**  
  - `spec.input_schema`: JSON Schema reference (local file path or JSON Pointer)
  - `spec.output_schema`: JSON Schema reference
- **Eval profile (optional):**  
  `metadata.labels.strands.io/eval_profile`: binds the agent to a named evaluation workflow (see §7).

These are **backwards-compatible** additions. Existing agents remain valid.

### 5.2 Types of Agents (Conventions)

We define a simple convention for `strands.io/agent_type`:

- `atomic` – Leaf, reusable capability; no internal orchestration assumptions.
- `orchestrator` – Coordinates multiple agents/tools; may call atomic agents.
- `router` – Routes tasks to agents/tools based on input.
- `evaluator` – Evaluates other agents’ outputs.
- `other` / omitted – Free-form; no strong semantics.

The runtime does not enforce behavior based on this label yet; the label is used by tooling, docs, and best practices.


## 6. Directory & Naming Conventions

To aid discovery and reuse, we define a recommended directory structure:

```text
./agents/
  atomic/
    summarize_customer_email/
      summarize_customer_email.yaml
      schemas/
        input.json
        output.json
      examples/
        sample.json
      tests.yaml
    
    classify_ticket_priority/
      classify_ticket_priority.yaml
      schemas/
        input.json
        output.json
      examples/
        sample.json
      tests.yaml
    
    extract_invoice_lines/
      extract_invoice_lines.yaml
      schemas/
        input.json
        output.json
      examples/
        sample.json
      tests.yaml

  orchestrators/
    customer_email_intake_orchestrator.yaml

  routers/
    email_intake_router.yaml

  evaluators/
    summarization_quality_evaluator.yaml
```

Conventions:

- **Atomic Agents are self-contained in `./agents/atomic/<name>/` subdirectories.**
- Each atomic agent directory contains:
  - `<name>.yaml` — The agent specification
  - `schemas/` — Input and output JSON schemas (named `input.json` and `output.json`)
  - `examples/` — Sample input files for testing (e.g., `sample.json`)
  - `tests.yaml` — Test suite definition
- Other agent types are grouped by role under `./agents/orchestrators/`, `./agents/routers/`, etc.
- This self-contained structure makes atomic agents **portable** and ready for extraction to centralized repositories.

Nothing in the runtime requires this layout, but the CLI and docs will **assume and encourage** it.


## 7. CLI Additions: `strands atomic ...`

We introduce a small CLI namespace for working with atomic agents.

### 7.1 Command Summary

```bash
strands atomic list [--all] [--json]
strands atomic describe <name> [--format yaml|json]
strands atomic run <name> --input-file <path> [--output-file <path>]
strands atomic test <name> [--filter <pattern>] [--json]
strands atomic init <name> [--domain <domain>] [--capability <capability>]
```

#### 7.1.1 `strands atomic list`

**Purpose:** List atomic agents in the current repo.

- Default behavior:
  - Scan `./agents/` recursively
  - Select specs with `kind: agent` and `metadata.labels.strands.io/agent_type == "atomic"`
- Flags:
  - `--all`: show all agents with their `agent_type` (atomic, orchestrator, etc.)
  - `--json`: machine-readable output (for tooling)

Example output (human-readable):

```text
$ strands atomic list

Atomic Agents:
- summarize_customer_email
  - path: agents/atomic/summarize_customer_email/summarize_customer_email.yaml
  - domain: customer_service
  - capability: summarization
  - version: v1

- classify_ticket_priority
  - path: agents/atomic/classify_ticket_priority/classify_ticket_priority.yaml
  - domain: customer_service
  - capability: classification
  - version: v1
```

#### 7.1.2 `strands atomic describe`

**Purpose:** Inspect an atomic agent’s metadata and contract.

- Input: `<name>` resolved to a spec path:
  - First search `./agents/atomic/<name>.yaml`
  - Fallback: global search in `./agents/**`

- Output includes:
  - Metadata: name, description, labels
  - Resolved paths for `input_schema` and `output_schema`
  - Model provider & name
  - Tools (if any)
  - Eval profile (if any)

Flags:
- `--format yaml|json` – raw spec or enriched view.

#### 7.1.3 `strands atomic run`

**Purpose:** Run an atomic agent in isolation for local testing and exploration.

- Input:
  - `<name>` – resolved as above
  - `--input-file <path>` – JSON input matching `input_schema`
- Behavior:
  - Validate input against `input_schema` (if defined). Fail fast on schema violations.
  - Run the agent via the standard runtime (Chat Completions / Responses, etc.).
  - Validate the resulting output against `output_schema` (if defined); on validation failure, surface a clear error and optionally still write raw output.
- Output:
  - Print result to stdout
  - If `--output-file` is set, write JSON result to file.

#### 7.1.4 `strands atomic test`

**Purpose:** Run a suite of tests for an atomic agent (fixtures + expectations).

- Input:
  - `<name>` – atomic agent name
- Behavior:
  - Locate test definition, e.g. `./tests/<name>_tests.yaml` (see §8).
  - For each test case:
    - Load `input` JSON
    - Call `strands atomic run`-equivalent internals
    - Check expectations (schema validation, key presence, optional evaluation hooks)
- Output:
  - Human-friendly summary (pass/fail per test)
  - `--json`: structured results for CI

Example:

```text
$ strands atomic test summarize_customer_email

Test suite: summarize_customer_email
- [PASS] simple_email
- [PASS] long_email_with_noise

2/2 tests passed
```

#### 7.1.5 `strands atomic init`

**Purpose:** Scaffold a new atomic agent with schemas and tests.

```bash
strands atomic init summarize_customer_email \
  --domain customer_service \
  --capability summarization
```

Generates (if not existing):

```text
agents/atomic/summarize_customer_email/
  summarize_customer_email.yaml
  schemas/
    input.json
    output.json
  examples/
    sample.json
  tests.yaml
```

With reasonable starter content:

- YAML skeleton with metadata labels set (agent_type, domain, capability)
- Input schema with a sensible template (e.g., `subject`, `body`, `customer_id`)
- Output schema with a template (e.g., `summary`, `bullets[]`, `sentiment`)
- Test YAML with one placeholder test referencing example input/output.
- Sample input JSON for testing


## 8. Testing Model for Atomic Agents

We define a simple, extensible test format for atomic agents.

### 8.1 Test File Location & Naming

- Location: `./agents/atomic/<agent_name>/tests.yaml`
- Naming convention: `tests.yaml` (within the agent's directory)

Example: `agents/atomic/summarize_customer_email/tests.yaml`


### 8.2 Test File Structure

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

  - name: long_email_with_noise
    input: ./examples/email_2.json
    expectations:
      output_schema: ./schemas/summarize_customer_email_output.json
```

Minimal expectation behavior:

- `output_schema`: validate result JSON against given schema.
- `checks` (extensible):
  - `has_keys`: ensure required keys exist.
  - `max_length`: basic length check for strings.
  - (Future) `regex_match`, `contains`, numeric ranges, etc.

`strands atomic test` is not meant to be a full testing framework, just a **lightweight quality gate** for atomic agents.


## 9. Governance & Evaluation Hooks

Atomic agents often need **evaluation profiles** and **governance behaviors** (e.g., certification of particular versions).

### 9.1 Eval Profile Label

Use `metadata.labels.strands.io/eval_profile` to associate the agent with a named evaluation workflow.

Example:

```yaml
metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/eval_profile: summarization_v1
```

### 9.2 Evaluation Workflows (Out of Scope, but Anticipated)

- Evaluation workflows can be defined as normal Strands workflows under `./eval/`:
  - e.g., `./eval/summarization_v1.yaml` (Evaluator/Optimizer pattern)
- External tooling or CI can consume this mapping:
  - Discover all agents with `eval_profile = X`
  - Run them against the associated eval workflow(s)
  - Store and surface results (pass/fail, scores, regression information)

This PRD only defines **how atomic agents expose their eval profile**, not the full eval implementation.


## 10. Integration with Existing Patterns

### 10.1 Orchestrator–Workers

Example orchestrator using atomic agent as worker template:

```yaml
kind: workflow
version: 1
metadata:
  name: customer_email_intake
spec:
  agents:
    orchestrator:
      prompt: "Break down customer email processing into tasks"
    worker:
      $ref: agents/atomic/summarize_customer_email/summarize_customer_email.yaml
  
  pattern: orchestrator_workers
  config:
    orchestrator:
      agent: orchestrator
    worker_template:
      agent: worker  # Atomic agent used as template for all tasks
```

- Atomic agents work well as the worker template.
- The orchestrator remains thin and focused on task decomposition and routing.
- For workflows requiring different agents for different tasks, use graph or workflow patterns instead.


### 10.2 Graph / DAG Workflows

Atomic agents as nodes:

```yaml
spec:
  pattern: graph
  nodes:
    - id: summarize
      agent: agents/atomic/summarize_customer_email/summarize_customer_email.yaml
    - id: classify
      agent: agents/atomic/classify_ticket_priority/classify_ticket_priority.yaml
  edges:
    - from: summarize
      to: classify
```

Atomic agents become the reusable node types in graphs.


## 11. Backwards Compatibility

- Existing agents and workflows **continue to work unchanged**.
- The `strands.io/agent_type` label is **optional**:
  - If absent, tools may treat the agent as `unknown` or infer its type based on usage or location.
- `input_schema` / `output_schema` are optional but **strongly recommended** for atomic agents.
- `strands atomic ...` commands operate only on agents explicitly or inferentially marked as atomic.


## 12. Implementation Plan

### Phase 1 – Metadata & Conventions

1. Update docs to introduce the concept of Atomic Agents.
2. Update agent schema definitions (if any validation is present) to allow:
   - `metadata.labels.strands.io/agent_type`
   - `spec.input_schema`
   - `spec.output_schema`
3. Add example atomic agents under `./agents/atomic/` in the repo.
4. Add example schemas under `./schemas/`.

### Phase 2 – CLI: List & Describe

1. Implement `strands atomic list`:
   - YAML parsing, label detection, directory traversal.
   - Pretty and JSON output.
2. Implement `strands atomic describe`:
   - Show metadata, contract paths, and basic validation of file existence.

### Phase 3 – CLI: Run

1. Implement `strands atomic run`:
   - Resolve agent by name.
   - Load and validate input JSON (if schema exists).
   - Invoke the standard runtime once.
   - Validate output against `output_schema` (if exists).
   - Surface schema or runtime errors clearly.

### Phase 4 – CLI: Test

1. Define a minimal test DSL (`_tests.yaml` format).
2. Implement `strands atomic test`:
   - Discover tests for a given agent.
   - Execute sequentially.
   - Aggregate and report results.
3. Integrate with CI (GitHub Actions example) in repo documentation.

### Phase 5 – CLI: Init / Scaffolding

1. Implement `strands atomic init`:
   - Generate YAML, schemas, and tests with opinionated defaults.
2. Add documentation and examples for developers.

### Phase 6 – Evaluation Integration (Optional / Future)

1. Define recommended folder structure for eval workflows (`./eval/`).
2. Document how to connect `strands.io/eval_profile` with eval workflows.
3. Provide example eval setup for one capability type (e.g., summarization).


## 13. Open Questions

1. **Strictness of “atomic”:**  
   Should we add optional validation to ensure atomic agents do *not* reference other agents (e.g., via nested workflows), or do we rely purely on convention?  
   _Initial proposal: convention-only; do not enforce._

2. **Schema resolution:**  
   Do we support remote schemas (HTTP) or just local file paths?  
   _Initial proposal: local file paths only for simplicity; remote support can come later._

3. **Tool usage in atomic agents:**  
   Are atomic agents allowed to use tools (e.g., HTTP, DB)?  
   _Initial proposal: yes, as long as the **observable behavior** is single-purpose._

4. **Versioning strategy:**  
   Do we standardize on `strands.io/version` or use semantic versioning in filenames as well?  
   _Initial proposal: support label only in first iteration; filename versioning is project-specific._

5. **Registry / catalog:**  
   Should we define a simple JSON index (`atomic-agents.json`) for discoverability across repos?  
   _Out of scope for this PRD; may be introduced later._


## 14. Acceptance Criteria

This feature is complete when:

- [ ] Documentation section “Atomic Agents” exists and explains concepts and conventions.
- [ ] At least **two** example atomic agents are implemented and used in an example workflow.
- [ ] `strands atomic list` and `strands atomic describe` work on the example agents.
- [ ] `strands atomic run` can execute an example atomic agent given an input JSON file.
- [ ] `strands atomic test` can run and pass a test suite for an example atomic agent.
- [ ] `strands atomic init` can scaffold a new atomic agent (YAML + schemas + tests).
- [ ] CI example is added to the repo, demonstrating `strands atomic test` usage.

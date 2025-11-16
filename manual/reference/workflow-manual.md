
# Strands Workflow Spec Manual (v0)
Date: 2025-11-03

This manual describes a declarative workflow specification for running agentic AI workflows with the **AWS Strands SDK** via a CLI. The spec is provided as a JSON Schema (Draft 2020‑12) and can be authored as **YAML or JSON**. It captures runtime, agents, tools, telemetry, security, and common agent **patterns** (chain, routing, parallel, orchestrator‑workers, evaluator‑optimizer, graph, workflow) inspired by industry guidance.

**Download the JSON Schema:** `strands-workflow.schema.json` (place alongside your workflow files).

---

## 1) Design Goals

- **Declarative, not imperative**: Keep orchestration in the spec; keep code minimal.
- **Portable**: Works as YAML or JSON; validated via the published JSON Schema.
- **Composable**: Patterns are re-usable abstractions tuned for agent work.
- **Safe-by-default**: Budgets, retries, and guardrails built in.
- **Observable**: OpenTelemetry tracing, artifact outputs, clear inputs/vars.
- **AWS-first**: Defaults assume Bedrock/regions, but providers are abstracted.

---

## 2) File Anatomy

A minimal file looks like this (YAML shown; JSON equivalent also valid):

```yaml
version: 0
name: "research-brief"
runtime:
  provider: bedrock
  model_id: "us.anthropic.claude-sonnet-4-20250514-v1:0"
  region: "eu-central-1"

agents:
  researcher:
    prompt: "Research {{topic}} and cite sources."
    tools: ["strands_tools.http_request"]
  writer:
    prompt: "Write a 600-word report for {{audience}}."

inputs:
  required:
    topic: string
  optional:
    audience: string

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Find 6 diverse sources."
      - agent: writer
        input: "Write the final report with citations."

outputs:
  artifacts:
    - path: "./artifacts/report.md"
      from: "{{ last_response }}"
```

**Top-level keys** (all defined by the schema):
- `version` (int/string): spec version. Use `0`. **[REQUIRED]**
- `name`: workflow name. **[REQUIRED]**
- `description`: human-friendly description. **[optional]**
- `tags`: array of tag strings. **[optional]**
- `runtime`: default model/provider/limits for all agents. **[REQUIRED]**
- `inputs`: parameters your CLI fills (`--var key=value`). **[optional]**
- `env`: secrets and filesystem mounts. **[optional]**
- `telemetry`: OTEL + redaction options. **[optional]**
- `context_policy`: compaction, notes, and JIT retrieval hints. **[optional]**
- `skills`: optional skill bundles (metadata + files). **[optional]**
- `tools`: Python callables, MCP servers, HTTP executors. **[optional]**
- `agents`: reusable agent templates. **[REQUIRED, must have at least 1]**
- `pattern`: **one** of the supported orchestration patterns. **[REQUIRED]**
- `outputs`: artifacts to write to disk. **[optional]**
- `security`: guardrails like network controls and PII redaction. **[optional]**

---

## 3) CLI Quick Start

Your CLI (`strands-cli`) should support:

```bash
# Run with variables
strands-cli run flow.yaml --var topic="L3 credit risk" --var audience=exec

# Validate against the JSON Schema
strands-cli validate flow.yaml --schema strands-workflow.schema.json

# Dry-run planner (renders resolved DAG/graph)
strands-cli plan flow.yaml

# Inspect / export OTEL trace
strands-cli trace <session-id>

# Resume a previous session (from artifacts/ state)
strands-cli resume <session-id>
```

**Variable precedence:** `--var` > environment > `inputs.optional.default` (if present).

---

## 4) Runtime

```yaml
runtime:
  provider: bedrock                 # REQUIRED: e.g., bedrock | openai | azure_openai | local
  model_id: "us.anthropic.claude-sonnet-4-20250514-v1:0"  # optional (default for agents)
  region: "eu-central-1"            # optional (required for bedrock)
  host: "http://localhost:11434"    # optional (required for ollama, optional for openai)
  temperature: 0.7                  # optional (0.0-2.0)
  max_tokens: 2000                  # optional (min: 1)
  top_p: 0.95                       # optional (0.0-1.0)
  max_parallel: 4                   # optional (min: 1)
  budgets:                          # optional
    max_steps: 200                  # optional (min: 1)
    max_tokens: 800000              # optional (min: 1)
    max_duration_s: 900             # optional (min: 1)
  failure_policy:                   # optional
    retries: 2                      # optional (min: 0)
    backoff: exponential            # optional: constant | exponential | jittered (default: exponential)
```

### Provider-Specific Requirements

**Bedrock**
- Requires: `region` (e.g., `us-east-1`, `eu-central-1`)
- Authentication: AWS credentials via environment, `~/.aws/credentials`, or IAM role
- Default model: `us.anthropic.claude-3-sonnet-20240229-v1:0`
- Example model IDs: `us.anthropic.claude-3-sonnet-20240229-v1:0`, `anthropic.claude-3-haiku-20240307-v1:0`

**OpenAI**
- Requires: `OPENAI_API_KEY` environment variable
- Optional: `host` for OpenAI-compatible servers (default: OpenAI API)
- Default model: `gpt-4o-mini`
- Example model IDs: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo`
- Get API key from: https://platform.openai.com/api-keys

**Ollama**
- Requires: `host` (e.g., `http://localhost:11434`)
- Authentication: None (local server)
- Default model: `gpt-oss`
- Example model IDs: `llama3`, `gpt-oss`, `mistral`
- Install from: https://ollama.ai/

**Best practices**
- Keep a **default model** in `runtime` and override per-agent only when needed.
- Use **budgets** to avoid runaway loops.
- Prefer **exponential** backoff with small retry counts; surface failures early.
- Store provider credentials securely (environment variables or AWS secrets, never in spec files)

---

## 5) Inputs and Interpolation

```yaml
inputs:
  required:
    topic: string                   # shorthand type name
  optional:
    audience:
      type: string
      description: "Target reader"
      default: "stakeholders"       # default value (can be any JSON type)
    priority:
      type: string
      enum: ["low", "medium", "high"]  # constrain to specific values
```

You can interpolate values inside strings using `{{var}}`. Defaults are specified in the `inputs.optional` section using the `default` property. The CLI performs variable substitution **before** execution.

---

## 6) Environment and Secrets

```yaml
env:
  secrets:
    - name: GITHUB_TOKEN
      source: env             # env | secrets_manager | ssm | file
  mounts:
    workdir: "./artifacts"
```

- Avoid embedding secrets in files; use `source: env` or AWS secrets.
- Mounts offer stable, named paths for tools and outputs.

---

## 7) Telemetry and Redaction

```yaml
telemetry:
  otel:
    endpoint: "http://localhost:4317"
    service_name: "strands-yaml-cli"
    sample_ratio: 1.0
  redact:
    tool_inputs: true
    tool_outputs: false
```

- Use a lower `sample_ratio` in production (e.g., `0.1`).
- Turn on redaction where required by policy.

---

## 8) Context Policy (Compaction, Notes, Retrieval)

```yaml
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 150000
  notes:
    file: "./artifacts/NOTES.md"
    include_last: 10
  retrieval:
    jit_tools: ["grep", "head", "tail", "search"]
```

- **Compaction**: trigger a summarization/compaction policy when token count passes a threshold.
- **Notes**: structured note-taking for continuity and memory.
- **JIT Retrieval**: Just-In-Time retrieval tools provide file system access during agent execution.

### 8.1 Compaction

Compaction reduces context size when token counts exceed limits. When `enabled: true` and conversation tokens surpass `when_tokens_over`, the system triggers a summarization policy.

### 8.2 Notes

Structured note-taking helps agents maintain continuity across runs. The `notes` configuration:
- `file`: Path to markdown file where notes are stored
- `include_last`: Number of most recent notes to include in agent context

### 8.3 JIT Retrieval Tools

**Phase 6.3 Feature**: Just-In-Time (JIT) retrieval tools are automatically injected into agents when `context_policy.retrieval.jit_tools` is configured. These tools provide safe, read-only file system access without pre-loading large files into context.

#### Configuration

```yaml
context_policy:
  retrieval:
    jit_tools:
      - "grep"    # Pattern search with context lines
      - "head"    # Read first N lines
      - "tail"    # Read last N lines
      - "search"  # Keyword/regex search with highlighting
```

#### Available JIT Tools

All JIT tools are **cross-platform** (Windows, macOS, Linux) and use **pure Python** implementations (no shell commands).

**1. grep** - Pattern search with context
- **Purpose**: Search files for regex/literal patterns with surrounding context
- **Parameters**:
  - `path` (required): Absolute file path
  - `pattern` (required): Search pattern (regex or literal string)
  - `context_lines` (optional, default=2): Lines before/after matches
  - `is_regex` (optional, default=true): Treat pattern as regex
  - `case_sensitive` (optional, default=false): Case-sensitive matching
  - `max_matches` (optional, default=100): Maximum matches to return
- **Returns**: Matched lines with line numbers and context
- **Example**: "Use grep to search for 'TODO' in src/main.py with 5 lines of context"

**2. head** - Read first N lines
- **Purpose**: Read beginning of file without loading entire contents
- **Parameters**:
  - `path` (required): Absolute file path
  - `lines` (optional, default=10): Number of lines to read
  - `encoding` (optional, default="utf-8"): File encoding
- **Returns**: First N lines with line numbers
- **Example**: "Use head to read the first 20 lines of README.md"

**3. tail** - Read last N lines
- **Purpose**: Read end of file (useful for logs, recent changes)
- **Parameters**:
  - `path` (required): Absolute file path
  - `lines` (optional, default=10): Number of lines to read
  - `encoding` (optional, default="utf-8"): File encoding
- **Returns**: Last N lines with line numbers
- **Example**: "Use tail to check the last 50 lines of error.log"

**4. search** - Keyword/regex search
- **Purpose**: Multi-keyword search with match highlighting
- **Parameters**:
  - `path` (required): Absolute file path
  - `keywords` (required): Search terms (string or array)
  - `is_regex` (optional, default=false): Treat keywords as regex
  - `case_sensitive` (optional, default=false): Case-sensitive matching
  - `context_lines` (optional, default=1): Lines around matches
  - `max_results` (optional, default=50): Maximum results
- **Returns**: Matches with highlighting (→ markers)
- **Example**: "Search config.yaml for 'database' or 'connection'"

#### Security & Path Validation

All JIT tools enforce strict path validation:
- **Absolute paths only**: Relative paths are rejected
- **Symlink prevention**: Symlinks are blocked to prevent directory traversal
- **Binary file detection**: Binary files are rejected (only text files allowed)
- **Encoding handling**: Graceful fallback to latin-1 for mixed-encoding files

#### Usage Patterns

**Pattern 1: Research & Analysis**
```yaml
agents:
  researcher:
    prompt: "Analyze repository structure and recent changes"
    tools: []  # No explicit tools - use JIT only

context_policy:
  retrieval:
    jit_tools: ["grep", "head", "tail", "search"]
```

The agent can now:
- `grep` for function definitions
- `head` to read file headers
- `tail` to check recent log entries
- `search` for configuration keys

**Pattern 2: Debugging Workflows**
```yaml
agents:
  debugger:
    prompt: "Find TODO comments and error messages"

context_policy:
  retrieval:
    jit_tools: ["grep", "search"]
```

**Pattern 3: Mixed Tools**
```yaml
agents:
  analyzer:
    prompt: "Analyze code and make API calls"
    tools: ["http_request"]  # Explicit tool

context_policy:
  retrieval:
    jit_tools: ["grep", "head"]  # Auto-injected

tools:
  python:
    - callable: "strands_tools.http_request"
```

The agent gets both `http_request` (from `tools.python`) and JIT retrieval tools (auto-injected).

#### Best Practices

1. **Explicit opt-in**: JIT tools are only available when `context_policy.retrieval.jit_tools` is configured
2. **Tool selection**: Only enable tools you need (e.g., just `["grep", "search"]` for code analysis)
3. **No duplicates**: If a tool is in both `agent.tools` and `jit_tools`, it's only loaded once
4. **Cross-platform**: All tools use pure Python - no shell command dependencies
5. **Read-only**: All JIT tools are read-only (no file modification capabilities)

#### Limitations (Phase 6 Scope)

- **Read-only**: No file writing, moving, or deletion
- **Text files only**: Binary files are rejected
- **No directory operations**: Can't list directories or create folders
- **No shell execution**: All operations use pure Python
- **MCP servers**: `mcp_servers` field is reserved for Phase 9 (not yet implemented)

#### Future: MCP Servers (Phase 9)

```yaml
context_policy:
  retrieval:
    jit_tools: ["grep", "head"]
    mcp_servers: ["filesystem", "github"]  # Phase 9 feature
```

Model Context Protocol (MCP) servers will provide extended retrieval capabilities in Phase 9, including directory operations, git integration, and custom data sources.

---

## 9) Skills (Optional)

Skills enable **progressive loading** of specialized capabilities, similar to Claude Code's skill system. Instead of front-loading all instructions, agents see only skill metadata initially and load full content on-demand when needed. This reduces initial prompt size, conserves tokens, and enables modular expertise.

### Basic Configuration

```yaml
skills:
  - id: xlsx
    path: ./skills/xlsx
    description: Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization
    preload_metadata: true

  - id: pdf
    path: ./skills/pdf
    description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms
```

### How Skills Work

**Discovery Phase** (at startup):
- CLI scans each skill directory and reads `SKILL.md` frontmatter
- Extracts `name` and `description` from YAML frontmatter
- Builds an "Available Skills" section in the agent's system prompt
- Agent sees skill names and descriptions but NOT full content

**Loading Phase** (on-demand):
- When the agent identifies a relevant task, it invokes: `Skill("skill_id")`
- CLI intercepts the invocation and loads the skill's full `SKILL.md` content
- Content is injected into the agent's context as a tool result
- Agent proceeds with the detailed instructions now available

### Skill Directory Structure

```
skills/
├── xlsx/
│   ├── SKILL.md              # Required: instructions with frontmatter
│   ├── LICENSE.txt           # Optional: licensing info
│   ├── recalc.py             # Optional: helper scripts
│   └── examples/             # Optional: reference files
└── pdf/
    ├── SKILL.md
    └── scripts/
        ├── extract.py
        └── merge.py
```

### Skill Properties

| Property | Required | Description |
|----------|----------|-------------|
| `id` | Yes | Unique identifier referenced in `Skill("id")` invocations |
| `path` | Yes | Filesystem path to skill directory (relative or absolute) |
| `description` | No | Brief summary of capabilities (auto-read from `SKILL.md` if omitted) |
| `preload_metadata` | No | If `true`, injects name/description into initial system prompt (default: `true`) |

### SKILL.md Format

Each skill directory must contain a `SKILL.md` file with YAML frontmatter:

````markdown
---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization"
license: Proprietary. LICENSE.txt has complete terms
---

# Requirements for Outputs

## All Excel files

### Zero Formula Errors
- Every Excel model MUST be delivered with ZERO formula errors...

### Color Coding Standards
- **Blue text**: Hardcoded inputs users will change
- **Black text**: ALL formulas and calculations
...

# XLSX Creation, Editing, and Analysis

## Overview
A user may ask you to create, edit, or analyze .xlsx files...

## Code Examples

```python
import pandas as pd
df = pd.read_excel("data.xlsx")
...
```
````

The frontmatter provides metadata; the body contains detailed instructions, code patterns, and best practices.

### Runtime Behavior

1. **System Prompt Injection**: At agent initialization, the CLI adds:
   - Instructions on when and how to invoke skills
   - List of available skills with IDs and descriptions
   - Directive: "To load a skill, call `Skill('skill_id')`"

2. **Autonomous Invocation**: Agent analyzes user request and decides if a skill is relevant (e.g., sees "create Excel file" → invokes `Skill("xlsx")`)

3. **Content Loading**: CLI reads `skills/xlsx/SKILL.md`, injects full markdown content as tool result

4. **Task Execution**: Agent follows loaded instructions to complete the task with specialized guidance

5. **Caching**: Loaded skills remain in context for the duration of the workflow step

### Example Usage

Full workflow demonstrating progressive skill loading:

```yaml
name: financial-analysis
version: 1.0.0

skills:
  - id: xlsx
    path: ./skills/xlsx
  - id: pdf
    path: ./skills/pdf

runtime:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0

agents:
  analyst:
    prompt: |
      You are a financial analyst with access to specialized skills.
      When encountering PDF or spreadsheet tasks, load the relevant
      skill to get detailed instructions and code patterns.
    tools:
      - python_exec

pattern:
  type: chain
  config:
    steps:
      - agent: analyst
        input: |
          Create a 3-year revenue projection model in Excel:
          - Starting MRR: $10,000
          - Monthly growth: 5%
          - Include formulas with proper color coding
          - Output: revenue_model.xlsx

outputs:
  artifacts:
    - path: ./revenue_model.py
      from: "{{ last_response }}"
```

When executed, the agent will:
1. See "Excel" in the request
2. Invoke `Skill("xlsx")` to load spreadsheet expertise
3. Follow loaded instructions for color coding, formulas, and formatting
4. Generate compliant Python code to create the file

### Best Practices

- **Keep descriptions concise**: 1-2 sentences explaining when to use the skill
- **Organize content clearly**: Use headings, bullet points, and code examples in `SKILL.md`
- **Avoid redundancy**: Don't duplicate common instructions across skills
- **Test skill isolation**: Each skill should work independently
- **Document dependencies**: Note required libraries or tools in the skill content
- **Version control skills**: Skills are versioned separately from workflow specs
- **Use official skills**: Anthropic provides curated skills for common tasks (PDF, XLSX, DOCX, PPTX)

> **See Also**: [Skills How-To Guide](../howto/skills.md) for step-by-step skill creation and testing.

---
## 10) Tools

```yaml
tools:
  python:
    - "strands_tools.http_request"
    - "./local_tools/confluence.py:search_pages"
  mcp:
    - id: "domains"
      command: "uvx"
      args: ["fastdomaincheck-mcp-server"]
  http_executors:
    - id: "gh"
      base_url: "https://api.github.com"
      headers:
        Authorization: "Bearer ${GITHUB_TOKEN}"
```

- **python**: fully qualified callables or module paths (importable by the CLI).
- **mcp**: external Model Context Protocol servers.
- **http_executors**: declarative HTTP configs for simple GET/POST tooling.

> Keep toolsets lean. Overlapping tools reduce determinism and increase cost.

---

## 11) Agents

```yaml
agents:
  researcher:
    prompt: |                       # REQUIRED: agent system prompt
      You are a research specialist. Cite sources with links.
    tools: ["strands_tools.http_request", "gh"]  # optional: tool references
    provider: bedrock               # optional: overrides runtime.provider
    model_id: "us.anthropic.claude-sonnet-4-20250514-v1:0"  # optional: overrides runtime.model_id
    inference:                      # optional
      temperature: 0.2              # 0.0-2.0
      top_p: 0.95                   # 0.0-1.0
      max_tokens: 4000              # min: 1

  writer:
    prompt: "Produce a crisp, sectioned report for {{audience}}."
```

- Each agent **requires** only a `prompt` field; all other fields are optional.
- Agents inherit from `runtime` unless overridden.
- Avoid setting wildly different temperatures across agents in the same flow.
- The `agents` object must contain at least one agent.

---

## 12) Patterns

The schema supports **7 pattern types**: `chain`, `routing`, `parallel`, `orchestrator_workers`, `evaluator_optimizer`, `graph`, and `workflow`. Each pattern has a specific `config` structure validated by the schema.

### 12.1 Chain

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}} and list top 6 sources."
      - agent: writer
        input: "Write a 600-word brief with citations."
```

**Use for**: straight-line handoffs and deterministic flows.

---

### 12.2 Routing

```yaml
pattern:
  type: routing
  config:
    router:
      agent: researcher
      input: "Classify the request into one route: faq, research, or coding."
    routes:
      faq:
        then:
          - agent: writer
            input: "Answer briefly with 3 bullets."
      research:
        then:
          - agent: researcher
            input: "Deep dive and gather evidence."
          - agent: writer
            input: "Summarize with links."
      coding:
        then:
          - agent: writer
            input: "Create a step-by-step plan."
```

**Router output**: your router agent should emit a small JSON dict (`{{route: 'faq'|'research'|'coding', rationale: '...'}}`), which the CLI interprets.

---

### 12.3 Parallel

```yaml
pattern:
  type: parallel
  config:
    branches:                       # REQUIRED: min 2 branches
      - id: web                     # REQUIRED: unique branch identifier
        steps:                      # REQUIRED: min 1 step per branch
          - agent: researcher
            input: "Collect web sources."
      - id: docs
        steps:
          - agent: researcher
            input: "Collect internal docs."
    reduce:                         # optional: aggregation step
      agent: writer
      input: "Merge findings and remove duplicates."
```

**Use for**: fanning out and reducing into a single result. CLI must join branch results deterministically.
**Requirements**: At least 2 branches required; each branch must have at least 1 step.

---

### 12.4 Orchestrator‑Workers

```yaml
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: researcher
      limits:
        max_workers: 6
        max_rounds: 3
    worker_template:
      agent: researcher
      tools: ["strands_tools.http_request", "gh"]
    reduce:
      agent: writer
      input: "Synthesize workers' findings; deduplicate and score sources."
    writeup:
      agent: writer
      input: "Final brief with executive summary and open questions."
```

**Use for**: multi-subtask research; maps to Strands Swarm/team behavior.

---

### 12.5 Evaluator‑Optimizer

```yaml
pattern:
  type: evaluator_optimizer
  config:
    producer: writer
    evaluator:
      agent: researcher
      input: |
        Critique for accuracy and structure.
        Return JSON: {{score: 0..100, issues: [], fixes: []}}.
    accept:
      min_score: 85
      max_iters: 3
    revise_prompt: "Revise the draft using evaluator fixes; do not invent citations."
```

**Use for**: iterative refinement with measurable gates.

---

### 12.6 Graph

**Pattern**: Explicit control flow with nodes, edges, and conditional transitions.

**Use for**: State machines, decision trees, iterative refinement loops, and complex workflows requiring dynamic routing based on previous agent responses.

#### Core Concepts

**Nodes**: Individual execution points, each running a specific agent.
- Entry node: First node in `nodes:` map (Python 3.7+ dict insertion order)
- Terminal nodes: Nodes with no outgoing edges (workflow stops when reached)
- Iterations: Nodes can be revisited multiple times (tracked automatically)

**Edges**: Define allowed transitions between nodes.
- **Static edges**: Always transition to target node(s)
  ```yaml
  - from: node_a
    to: [node_b]
  ```
- **Conditional edges**: Choose path based on runtime conditions
  ```yaml
  - from: node_a
    choose:
      - when: "{{ condition_1 }}"
        to: node_b
      - when: "{{ condition_2 }}"
        to: node_c
      - when: else
        to: node_d
  ```

**Conditions**: Jinja2 expressions evaluated against execution context.
- Access node responses: `{{ nodes.node_a.response }}`
- Access node iteration: `{{ nodes.node_a.iteration }}`
- Boolean operators: `and`, `or`, `not`
- Comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`
- String operations: `in`, `lower()`, `upper()`
- Special keyword: `else` always evaluates to `True` (catch-all)

**Cycle Protection**: Dual-limit enforcement prevents infinite loops.
- **Global limit**: `runtime.budgets.max_steps` (default 100) - total workflow steps
- **Per-node limit**: `pattern.config.max_iterations` (default 10) - max visits per node

#### Configuration

```yaml
pattern:
  type: graph
  config:
    max_iterations: 5  # Optional: per-node iteration limit (default: 10)
    
    nodes:
      # Entry node (first in map)
      intake:
        agent: classifier
        input: "{{ user_request }}"  # Optional: override agent prompt
      
      # Standard nodes
      handle_technical:
        agent: tech_support
      
      handle_billing:
        agent: billing_support
      
      # Terminal node (no outgoing edges)
      escalate:
        agent: senior_manager
    
    edges:
      # Entry: Route based on classification
      - from: intake
        choose:
          - when: "{{ 'technical' in nodes.intake.response.lower() }}"
            to: handle_technical
          - when: "{{ 'billing' in nodes.intake.response.lower() }}"
            to: handle_billing
          - when: else
            to: escalate
      
      # Technical path: Check priority
      - from: handle_technical
        choose:
          - when: "{{ 'high' in nodes.intake.response.lower() }}"
            to: escalate
          # Otherwise terminal (no else clause)
      
      # Billing path: Always escalate
      - from: handle_billing
        to: [escalate]
```

#### Condition Evaluation

Conditions are evaluated using Jinja2 with access to the execution context:

**Available Context**:
```python
{
  "nodes": {
    "node_id": {
      "response": "Agent response text",
      "agent": "agent_id",
      "status": "success|error",
      "iteration": 2  # How many times this node has executed
    }
  },
  "last_response": "Most recent node response",
  "total_steps": 5,
  # Plus any inputs.values variables
}
```

**Example Conditions**:
```yaml
# Simple string matching
when: "{{ 'approve' in nodes.reviewer.response.lower() }}"

# Numeric comparison
when: "{{ nodes.validator.iteration >= 3 }}"

# Boolean operators
when: "{{ 'valid' in nodes.check.response and nodes.check.iteration < 5 }}"

# Multiple conditions with else
choose:
  - when: "{{ nodes.score.response | int >= 85 }}"
    to: approve
  - when: "{{ nodes.score.response | int >= 60 }}"
    to: review
  - when: else
    to: reject
```

#### Loop Patterns

**Iterative Refinement** (with quality threshold):
```yaml
nodes:
  writer:
    agent: coder
    input: "{{ task }}"
  
  reviewer:
    agent: reviewer
  
  finalize:
    agent: finalizer

edges:
  - from: writer
    to: [reviewer]
  
  - from: reviewer
    choose:
      - when: "{{ 'approve' in nodes.reviewer.response.lower() }}"
        to: finalize
      - when: "{{ nodes.writer.iteration >= 3 }}"
        to: finalize  # Force exit after 3 attempts
      - when: else
        to: writer  # Loop back for revision
```

**Bounded Retry** (with iteration limit):
```yaml
edges:
  - from: processor
    choose:
      - when: "{{ 'success' in nodes.processor.response.lower() }}"
        to: complete
      - when: "{{ nodes.processor.iteration >= 5 }}"
        to: error_handler
      - when: else
        to: processor  # Retry
```

#### Execution Flow

1. **Entry**: Execute first node in `nodes:` map
2. **Edge Traversal**: For each node, find matching edges:
   - Evaluate `choose` conditions in order (first match wins)
   - Execute static `to` if no `choose` clause
   - Stop if no outgoing edges (terminal node)
3. **Iteration Tracking**: Increment node iteration counter on each visit
4. **Cycle Detection**: 
   - Check per-node iteration limit (raise error if exceeded)
   - Check global step limit (raise error if exceeded)
5. **Termination**: Stop when terminal node reached or limits hit

#### Output Templates

Access node data in output artifacts:

```yaml
outputs:
  artifacts:
    - path: ./result.md
      from: |
        # Workflow Result
        
        {% if nodes.approve %}
        ## Approved
        {{ nodes.approve.response }}
        {% endif %}
        
        {% if nodes.reject %}
        ## Rejected
        {{ nodes.reject.response }}
        Attempts: {{ nodes.processor.iteration }}
        {% endif %}
        
        Terminal Node: {{ terminal_node }}
        Total Steps: {{ total_steps }}
```

#### Visualization

Use `strands plan` to generate DOT visualization:

```bash
uv run strands plan examples/graph-state-machine-openai.yaml
```

Generates Graphviz DOT format showing:
- **Green nodes**: Entry points
- **Red nodes**: Terminal nodes
- **Blue nodes**: Standard nodes
- **Solid arrows**: Static edges
- **Dashed arrows**: Conditional edges (labeled with condition)

#### Examples

See full working examples:
- `examples/graph-state-machine-openai.yaml` - Customer support routing
- `examples/graph-decision-tree-bedrock.yaml` - Approval workflow
- `examples/graph-iterative-refinement-ollama.yaml` - Code review loop

---

### 12.7 Workflow (DAG)

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: extract
        agent: researcher
        description: "Fetch 3–5 sources on {{topic}}"
      - id: trend
        agent: researcher
        deps: [extract]
        description: "Extract trends with evidence"
      - id: report
        agent: writer
        deps: [trend]
        description: "Write the final report"
```

**Use for**: fixed DAGs; supports parallel execution where deps allow.

---

## 13) Outputs and Artifacts

```yaml
outputs:
  artifacts:
    - path: "./artifacts/{{name}}.md"
      from: "{{ last_response }}"
    - path: "./artifacts/trace.json"
      from: "$TRACE"
```

- `{{ last_response }}` is the final agent message from the pattern runner.
- `$TRACE` is a special symbol instructing the CLI to export an OTEL trace JSON snapshot.

---

## 14) Security & Guardrails

```yaml
security:
  guardrails:
    deny_network: false
    pii_redaction: true
    allow_tools: ["strands_tools.http_request", "gh"]
```

- Prefer **allow-lists** for tools in controlled environments.
- Toggle `deny_network` for fully offline runs with pre-provided corpora.

---

## 15) Validation

- Use the provided **JSON Schema** (`strands-workflow.schema.json`) to validate files.
- Any proper JSON Schema validator works:
  - Node: `ajv validate -s strands-workflow.schema.json -d flow.yaml`
  - Python: `jsonschema.validate(instance, schema)`
- The CLI should perform validation **before** attempting execution.

---

## 16) Execution Model (Informative)

- The CLI **compiles** `agents` to Strands agent instances (e.g., via a config-to-agent helper) and binds tools.
- A pattern **runner** translates `pattern` into the corresponding Strands primitive (Swarm/Graph/Workflow) or a small deterministic loop (chain/routing/evaluator).
- **Budgets** are enforced both at pattern and agent call sites.
- **Compaction** and **notes** apply between steps/rounds when thresholds are met.
- **Telemetry** spans are emitted per step/tool call; errors attach structured metadata.

---

## 17) Style Guide & Best Practices

- Keep prompts **short and task-specific**; use `input` to pass per-step instructions.
- Limit agent count to the minimum needed; over-segmentation hurts reliability.
- Prefer **routing** over giant “do-everything” prompts.
- In **parallel** and **orchestrator** patterns, set a clear **reduce** strategy.
- Always include **budgets** and **retries** with sane defaults.
- Keep **tools** minimal and well‑named; avoid overlapping responsibilities.
- Use **artifacts** to make outputs and traces easy to consume downstream.

---

## 18) Reference: JSON Example (Valid)

```json
{{
  "version": 0,
  "name": "research-brief",
  "runtime": {{
    "provider": "bedrock",
    "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "region": "eu-central-1",
    "budgets": {{"max_steps": 200, "max_tokens": 800000, "max_duration_s": 900}}
  }},
  "inputs": {{
    "required": {{"topic": "string"}},
    "optional": {{"audience": "string"}}
  }},
  "tools": {{
    "python": ["strands_tools.http_request"],
    "http_executors": [{{"id": "gh", "base_url": "https://api.github.com", "headers": {{"Authorization": "Bearer ${GITHUB_TOKEN}"}}}}]
  }},
  "agents": {{
    "researcher": {{"prompt": "Research {{{{topic}}}} and cite sources.", "tools": ["strands_tools.http_request", "gh"]}},
    "writer": {{"prompt": "Write a concise report for {{{{audience}}}}."}}
  }},
  "pattern": {{
    "type": "chain",
    "config": {{
      "steps": [
        {{"agent": "researcher", "input": "Find 6 diverse sources."}},
        {{"agent": "writer", "input": "Produce a 600-word brief with citations."}}
      ]
    }}
  }},
  "outputs": {{
    "artifacts": [
      {{"path": "./artifacts/research-brief.md", "from": "{{{{ last_response }}}}"}}
    ]
  }}
}}
```

> Note the doubled braces in this manual’s JSON block to avoid Markdown templating conflicts.

---

## 19) Troubleshooting

- **Schema validation fails**: run `strands-cli validate` with `--verbose` to see the exact path and expected type.
- **Tool import errors**: confirm your `PYTHONPATH` and the callable name (`module:func`).
- **Secrets missing**: verify environment variables or configure AWS Secrets Manager/SSM.
- **No artifacts produced**: ensure `outputs.artifacts` is configured and the chosen pattern emits `last_response`.
- **Infinite loops**: tighten `budgets.max_steps` and configure `failure_policy`.

---

## 20) Telemetry & Observability

Strands CLI integrates with OpenTelemetry (OTEL) to provide production-grade observability. Enable distributed tracing to monitor workflow execution, identify bottlenecks, and debug issues across multi-agent systems.

### Configuration

#### Basic Setup
```yaml
telemetry:
  otel:
    endpoint: http://localhost:4318/v1/traces  # OTLP/HTTP endpoint
    service_name: my-workflow-service          # Service identifier in traces
    sample_ratio: 1.0                          # Trace 100% of requests
```

#### Configuration Reference
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `endpoint` | string | `null` | OTLP endpoint URL (HTTP/gRPC). If null, tracing disabled. |
| `service_name` | string | `"strands-cli"` | Service name for trace identification |
| `sample_ratio` | float | `1.0` | Sampling rate (0.0-1.0). 0.0=disabled, 1.0=trace all |

### Span Hierarchy

Spans follow a consistent hierarchy across all workflow patterns:

```
execute.<pattern_type>              (root span)
├── execute.chain                   (for route execution in routing pattern)
│   ├── agent.invoke                (per step - from Strands SDK)
│   │   ├── tool.<tool_name>        (per tool call - from Strands SDK)
│   │   └── llm.completion          (from Strands SDK)
│   └── ...
├── ...
```

**Pattern-Specific Span Names**:
- Chain: `execute.chain`
- Workflow: `execute.workflow`
- Routing: `execute.routing` (contains nested `execute.chain` for route)
- Parallel: `execute.parallel`
- Evaluator-Optimizer: `execute.evaluator_optimizer`
- Orchestrator-Workers: `execute.orchestrator_workers`
- Graph: `execute.graph`

### Span Attributes Reference

#### Common Attributes (All Patterns)
| Attribute | Type | Example | Description |
|-----------|------|---------|-------------|
| `spec.name` | string | `"my-workflow"` | Workflow name from spec |
| `spec.version` | string | `"1.0.0"` | Workflow version |
| `pattern.type` | string | `"chain"` | Pattern type |
| `runtime.provider` | string | `"openai"` | LLM provider |
| `runtime.model_id` | string | `"gpt-4o"` | Model identifier |
| `runtime.region` | string | `"us-east-1"` | AWS region (Bedrock only) |

#### Pattern-Specific Attributes

**Chain**:
- `chain.step_count` (int) - Total steps in chain

**Workflow**:
- `workflow.task_count` (int) - Total tasks
- `workflow.layer_count` (int) - DAG execution layers

**Routing**:
- `routing.router_agent` (string) - Router agent ID
- `routing.route_count` (int) - Available routes
- `routing.max_retries` (int) - Max retries for router

**Parallel**:
- `parallel.branch_count` (int) - Number of branches
- `parallel.has_reduce` (bool) - Reduce step present
- `parallel.max_parallel` (int) - Concurrency limit

**Evaluator-Optimizer**:
- `evaluator_optimizer.max_iterations` (int) - Iteration limit
- `evaluator_optimizer.evaluator_agent` (string) - Evaluator ID
- `evaluator_optimizer.optimizer_agent` (string) - Optimizer ID

**Orchestrator-Workers**:
- `orchestrator_workers.orchestrator_agent` (string) - Orchestrator ID
- `orchestrator_workers.worker_count` (int) - Worker pool size

**Graph**:
- `graph.node_count` (int) - Total nodes
- `graph.edge_count` (int) - Total edges/transitions
- `graph.start_node` (string) - Entry point node

### Span Events Reference

Events mark key milestones during workflow execution.

#### Common Events (All Patterns)
| Event | Attributes | Description |
|-------|------------|-------------|
| `execution_start` | - | Workflow execution begins |
| `execution_complete` | `duration_seconds`, `cumulative_tokens` | Workflow finishes successfully |

#### Pattern-Specific Events

**Chain**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `step_start` | `step_index`, `agent_id` | Chain step begins |
| `step_complete` | `step_index`, `agent_id`, `response_length`, `cumulative_tokens` | Chain step finishes |

**Workflow**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `task_complete` | `task_id`, `agent_id`, `response_length`, `cumulative_tokens` | Task finishes |

**Routing**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `agent_selected` | `chosen_route`, `router_agent` | Router selects route |

**Parallel**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `branch_complete` | `branch_id`, `response_length`, `tokens` | Branch execution finishes |
| `reduce_start` | - | Reduce step begins (if configured) |

**Evaluator-Optimizer**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `iteration_start` | `iteration_number` | Iteration begins |
| `evaluation_complete` | `score`, `feedback` | Evaluator finishes |
| `optimization_complete` | `improved` | Optimizer finishes |
| `iteration_complete` | `iteration_number`, `converged` | Iteration finishes |

**Orchestrator-Workers**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `orchestrator_planning` | `task_count` | Orchestrator creates work plan |
| `worker_assigned` | `worker_id`, `task_id` | Task assigned to worker |
| `worker_complete` | `worker_id`, `task_id`, `success` | Worker finishes task |
| `orchestrator_synthesis` | `results_count` | Orchestrator aggregates results |

**Graph**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `node_entered` | `node_id`, `visit_count` | Node execution starts |
| `node_complete` | `node_id`, `next_transition` | Node execution finishes |
| `transition` | `from_node`, `to_node`, `condition` | Graph state transition |

**Utility Events (Cross-Pattern)**:
| Event | Attributes | Description |
|-------|------------|-------------|
| `retry_attempt` | `attempt`, `error`, `wait_seconds` | Retry triggered |
| `budget_warning` | `current_tokens`, `max_tokens`, `threshold`, `usage_percent` | Approaching budget limit |
| `budget_exceeded` | `current_tokens`, `max_tokens`, `overage` | Budget limit exceeded |

### Sampling Strategies

#### Development & Debugging
```yaml
telemetry:
  otel:
    sample_ratio: 1.0  # Trace all requests
```
**Use When**: Local development, debugging issues, performance profiling

#### Production (Low Traffic)
```yaml
telemetry:
  otel:
    sample_ratio: 0.5  # Trace 50% of requests
```
**Use When**: <1000 requests/day, cost-sensitive environments

#### Production (High Traffic)
```yaml
telemetry:
  otel:
    sample_ratio: 0.01  # Trace 1% of requests
```
**Use When**: >10,000 requests/day, high-scale deployments

#### Emergency Disable
```yaml
telemetry:
  otel:
    sample_ratio: 0.0  # Disable tracing
```
**Use When**: OTEL collector down, incident mitigation

### Backend Setup

#### Option 1: Jaeger (Recommended for Development)
```bash
# Start Jaeger all-in-one
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest

# Access UI: http://localhost:16686
```

#### Option 2: OTEL Collector + Backend
```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  jaeger:
    endpoint: jaeger:14250
  logging:
    loglevel: debug

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger, logging]
```

```bash
docker run -p 4318:4318 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otel/config.yaml \
  otel/opentelemetry-collector:latest \
  --config=/etc/otel/config.yaml
```

#### Option 3: Production (AWS X-Ray, DataDog, etc.)
Strands CLI uses standard OTLP protocol - compatible with all major APM vendors:
- **AWS X-Ray**: Use AWS Distro for OpenTelemetry
- **DataDog**: Configure DataDog agent with OTLP receiver
- **New Relic**: Use New Relic OTLP endpoint
- **Honeycomb**: Use Honeycomb OTLP endpoint

### Troubleshooting

#### No Traces Appearing
1. Check `sample_ratio` > 0.0
2. Verify OTEL endpoint is reachable: `curl http://localhost:4318/v1/traces`
3. Check logs for OTLP export errors: `strands run --verbose ...`

#### Trace Sampling Too Aggressive
- Increase `sample_ratio` for more traces
- TraceIdRatioBased sampler is deterministic (same trace ID = same sampling decision)

#### High Trace Volume Costs
- Decrease `sample_ratio` to reduce data volume
- Use head-based sampling (configured here) + tail-based sampling (at collector) for best results

### Best Practices

1. **Use Consistent Service Names**: Group related workflows with same `service_name`
2. **Set Appropriate Sampling**: Start with 1.0 in dev, tune down in production based on traffic
3. **Monitor Span Attributes**: Use `spec.name` and `pattern.type` for filtering in trace UI
4. **Track Events for Debugging**: Events like `retry_attempt` and `budget_warning` highlight issues
5. **Combine with Structured Logs**: Trace context (trace_id, span_id) automatically injected into logs via structlog

---

## 21) Migration & Extensibility

- Add new pattern types by extending the schema and the CLI’s runner registry.
- Keep `version` to gate breaking changes (introduce `1` when you add incompatible keys).
- Consider a `manual_gate` step type (human approval via Slack/Jira) in a future minor version.

---

## 22) Appendix: Schema Fields (At-a-Glance)

**Required top-level fields**: `version`, `name`, `runtime`, `agents` (min 1), `pattern`

- **runtime** [REQUIRED]: 
  - `provider` [REQUIRED]
  - `model_id`, `region`, `max_parallel`, `budgets`, `failure_policy` [all optional]
- **inputs** [optional]: required/optional var map with type, description, default, enum
- **env** [optional]: secrets (env/secrets_manager/ssm/file), mounts
- **telemetry** [optional]: otel (endpoint, service_name, sample_ratio), redact (tool_inputs, tool_outputs)
- **context_policy** [optional]: compaction, notes, retrieval
- **skills** [optional]: id, path, preload_metadata
- **tools** [optional]: python[], mcp[], http_executors[]
- **agents** [REQUIRED, min 1]: 
  - `prompt` [REQUIRED per agent]
  - `tools[]`, `provider`, `model_id`, `inference` [all optional]
- **pattern** [REQUIRED, exactly 1]:
  - chain: steps[] (min 1)
  - routing: router, routes.<name>.then[]
  - parallel: branches[] (min 2), reduce [optional]
  - orchestrator_workers: orchestrator, worker_template, reduce [optional], writeup [optional]
  - evaluator_optimizer: producer, evaluator, accept, revise_prompt [optional]
  - graph: nodes (min 1), edges (min 1) with conditional `choose`
  - workflow: tasks[] (min 1) with `deps`
- **outputs** [optional]: artifacts[] (`path`, `from`)
- **security** [optional]: guardrails (deny_network, pii_redaction, allow_tools)

---

## 23) Files

- **Schema**: `strands-workflow.schema.json`
- **Manual (this doc)**: `strands-workflow-manual.md`

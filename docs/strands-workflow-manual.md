
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

```yaml
skills:
  - id: "pdf-editing"
    path: "./skills/pdf"
    preload_metadata: true
```

- Each skill directory should include a `SKILL.md` with name/description/instructions and any referenced files.
- If `preload_metadata` is true, the CLI injects the skill name/description into the agent’s system prompt; content is still read on-demand via tools.

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

```yaml
pattern:
  type: graph
  config:
    nodes:
      research: {{ agent: researcher }}
      analyze:  {{ agent: researcher, input: "Extract 3–5 insights with evidence" }}
      write:    {{ agent: writer }}
      fix:      {{ agent: researcher, input: "Resolve: {{issues}}" }}
    edges:
      - from: research
        to: [analyze]
      - from: analyze
        choose:
          - when: "{{score}} >= 85"
            to: write
          - when: "else"
            to: fix
```

**Use for**: explicit control flow with conditions and loops.

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

## 20) Migration & Extensibility

- Add new pattern types by extending the schema and the CLI’s runner registry.
- Keep `version` to gate breaking changes (introduce `1` when you add incompatible keys).
- Consider a `manual_gate` step type (human approval via Slack/Jira) in a future minor version.

---

## 21) Appendix: Schema Fields (At-a-Glance)

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

## 22) Files

- **Schema**: `strands-workflow.schema.json`
- **Manual (this doc)**: `strands-workflow-manual.md`

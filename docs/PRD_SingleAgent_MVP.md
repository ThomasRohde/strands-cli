# PRD — Strands YAML CLI: Single‑Agent MVP (with Full‑Schema Support)

**Status:** Draft → Review → Build  
**Owner:** (you) Thomas Rohde  
**Date:** 2025-11-03  
**Target:** Ship a production‑ready MVP that executes **single‑agent** workflows while parsing the **full Strands Workflow Schema** and **gracefully stopping** on unsupported features. The design must scale cleanly to the full multi‑agent spec.

---

## 1) Context & Goals

AWS **Strands Agents SDK** provides a model‑driven way to build and run agents. We want a **declarative CLI** that reads YAML/JSON workflows (see schema), instantiates Strands agents, and executes them.  
Initial scope is **Single Agent MVP**; however, the CLI must:
- Parse and validate the **full schema** (Draft 2020‑12 JSON Schema).
- **Detect unsupported features** and **stop with a clear plan + remediation tips** (no silent partial behavior).
- Provide **stable internal interfaces** so we can later enable multi‑agent patterns (chain, routing, parallel, orchestrator‑workers, evaluator‑optimizer, graph, workflow) with minimal refactoring.

**Schema Ground Truth:** All validation, capability checks, and feature support are defined by [`strands-workflow.schema.json`](../src/strands_cli/schema/strands-workflow.schema.json) (JSON Schema Draft 2020-12). This schema is the canonical specification for the workflow format.

### Success criteria (MVP)
- ✅ CLI runs a valid **single‑agent** workflow end‑to‑end (Bedrock/Claude default).  
- ✅ Full JSON Schema validation + precise error messages.  
- ✅ Unsupported features → exit with **EX_UNSUPPORTED** and structured hints; no ambiguous runs.  
- ✅ **Artifact output** (last response).  
- ✅ Deterministic, testable runs (seedable; reproducible).

### Non‑goals (MVP)
- ❌ Multi‑agent orchestration (Swarm/Graph/Workflow).  
- ❌ Parallel execution / background workers.  
- ❌ External secret stores (ASM/SSM) beyond ENV.  
- ❌ Persistent memory & retrieval‑augmented context.  
- ❌ Interactive human‑in‑the‑loop gates.  
- ❌ **OTEL tracing** (scaffolding in place for future; see roadmap below).

---

## 2) User Stories

1. **As a developer**, I can `cli run flow.yaml --var topic="L3 risk"` and receive a generated artifact in `./artifacts/*.md` and an informative console summary.
2. **As a reviewer**, I can `cli plan flow.yaml` to see how the YAML maps to runtime (agents/tools/pattern), including **which parts are unsupported** and why.
3. **As a platform owner**, I can `cli validate flow.yaml` to get **schema errors** and **policy lint warnings** before running anything.
4. **As an architect**, I can see a **compatibility matrix** for the full schema vs MVP behavior and the roadmap to full production.

---

## 3) Scope (MVP)

### 3.1 Supported
- **Agents:** exactly **one** agent in `agents:` map (arbitrary key), with `prompt`, optional `tools`, and model overrides.  
- **Pattern:** one of:
  - `pattern.type="chain"` with **1 step only** (the step’s `agent` must reference the single agent).  
  - `pattern.type="workflow"` with **1 task only** (the task’s `agent` must reference the single agent).  
  (Both normalize to the same single‑agent execution path.)
- **Runtime:** `provider` in `{bedrock, ollama}` (default: `ollama`), `model_id`, `region` (required for Bedrock), `host` (required for Ollama), budgets (logged only), failure policy (retries for transport/5xx).  
- **Tools:** subset:  
  - `python`: allow whitelisted callables: `strands_tools.http_request`, `strands_tools.file_read`.  
  - `http_executors`: base_url + headers; simple GET/POST execution via internal wrapper.  
- **Inputs:** resolve `--var` overrides; provide to prompt templating.  
- **Outputs.artifacts:** write `{{ last_response }}` → file(s).  
- **Telemetry:** parsed but no-op (OTEL non-goal for MVP; scaffolding in place).  
- **Skills:** optional — inject `id`/`path` **metadata** into system prompt; do not auto‑execute code.  
- **Env.secrets:** source=`env` only.### 3.2 Not yet supported (graceful stop)
- Multiple agents; any reference to a second agent.  
- `pattern.type` in `{routing, orchestrator_workers, evaluator_optimizer, graph, parallel}`.  
- `chain.steps > 1` or `workflow.tasks > 1`.  
- `skills.preload_metadata=true` is **supported** (string injection only); any executable assets are not.  
- `security.guardrails` enforced policies (we **parse** but only log).  
- `context_policy` (compaction/notes/retrieval) parsed but not executed (log only).

**Behavior:** On detection, **exit EX_UNSUPPORTED (18)** with a **structured report** suggesting the smallest change to make it runnable in MVP.

---

## 4) CLI Design

### 4.1 Commands
```
strands-cli run <spec.(yaml|yml|json)> [--var k=v ...] [--out artifacts/]
strands-cli plan <spec> [--format md|json]
strands-cli validate <spec>
strands-cli explain <spec>   # show unsupported features & migration hints
strands-cli list-supported   # show exact MVP feature set
strands-cli version
```

### 4.2 Exit Codes
| Code | Name             | Meaning                                       |
|-----:|------------------|-----------------------------------------------|
| 0    | OK               | Success                                       |
| 2    | EX_USAGE         | Bad flags / file missing                      |
| 3    | EX_SCHEMA        | JSON Schema validation error                  |
| 10   | EX_RUNTIME       | Provider/model/tool runtime failure           |
| 12   | EX_IO            | Artifact write or IO error                    |
| 18   | EX_UNSUPPORTED   | Feature present but not supported in MVP      |
| 70   | EX_UNKNOWN       | Unexpected exception                          |

### 4.3 `plan` & `explain` outputs
- **plan:** resolved runtime, agent, tools, inputs, chosen pattern normalization, artifact plan, telemetry plan.  
- **explain:** per schema section, list unsupported items with **location pointers** (JSONPointer) and one‑line **remediation**.

---

## 5) Architecture

```
+-----------------------+
|        CLI (Typer)    |
+----------+------------+
           |
           v
+-----------------------+
|  Loader (YAML/JSON)   |  -> JSON Schema Validation
+----------+------------+
           |
           v
+-----------------------+
|  Capability Evaluator |  -> detects unsupported features (matrix)
+----------+------------+
           |
   supported? yes/no
     |                \
     v                 v
+----------------+   +---------------------+
| SingleAgentRun |   |  Graceful Stopper   |
|  (Executor)    |   | (report + EX_UNSUPPORTED) |
+----------------+   +---------------------+
           |
           v
+-----------------------+
|      Artifacts        |
| (OTEL scaffolding)    |
+-----------------------+
```

### 5.1 Modules
- `schema/`: embed [`strands-workflow.schema.json`](../src/strands_cli/schema/strands-workflow.schema.json) (compile with `fastjsonschema`).  
- `loader/`: read YAML/JSON, resolve `--var` into `inputs`, produce a typed `Spec`.  
- `capability/`: validate **MVP compatibility**; produce a `CapabilityReport` (used by `plan` and `explain`).  
- `runtime/strands_adapter.py`: map `Spec` → Strands `Agent` (+ tools).  
- `runtime/tools.py`: safe adapters for http_executors & whitelisted python tools.  
- `exec/single_agent.py`: render prompt (system+task), run agent, capture result, enforce retries.  
- `telemetry/otel.py`: **scaffolding only** (no-op TracerProvider for MVP; enables future tracing).  
- `artifacts/io.py`: ensure dirs, write files, guard against overwrite (or `--force`).

### 5.2 Data Flow (MVP)
1. Load spec → JSON Schema validation.  
2. Build `CapabilityReport`:
   - Count agents; inspect `pattern.type` and size; check tools and sections.  
3. If unsupported → **Graceful Stopper** renders a markdown/JSON report and exits **18**.  
4. Else, construct **single Strands Agent**:
   - System prompt = agent.prompt + injected **skills metadata** + runtime tags.  
   - Task prompt = resolved `pattern` input (single step/task) with `inputs` vars.  
   - Tools = safe adapters for allowed tool types.  
5. Execute; write artifacts; export spans; print compact run summary.

---

## 6) Detailed Behaviors

### 6.1 Schema Compatibility Matrix (v0)
*Based on [`strands-workflow.schema.json`](../src/strands_cli/schema/strands-workflow.schema.json)*

| Section                 | MVP Behavior                                                                           |
|-------------------------|-----------------------------------------------------------------------------------------|
| `version`               | accept `0` (int/str); warn otherwise                                                   |
| `name/description/tags` | pass‑through                                                                            |
| `runtime.provider`      | support `bedrock` and `ollama` (default: `ollama`); others → EX_UNSUPPORTED             |
| `runtime.model_id`      | pass‑through to Strands (e.g., `gpt-oss` for Ollama, `us.anthropic.claude-...` for Bedrock) |
| `runtime.region`        | required for Bedrock; ignored for Ollama                                                 |
| `runtime.host`          | required for Ollama (e.g., `http://localhost:11434`); ignored for Bedrock              |
| `runtime.budgets`       | parsed + logged (no enforcement beyond max_duration_s timeout)                          |
| `failure_policy`        | implement `retries` (HTTP/tool transient), `exponential` backoff                        |
| `inputs`                | merge with `--var`; make available to templates                                         |
| `env.secrets`           | `source=env` only; others → EX_UNSUPPORTED                                              |
| `env.mounts`            | logged only                                                                             |
| `telemetry.otel`        | parsed only; no-op in MVP (see roadmap)                                                  |
| `telemetry.redact`      | parsed only; no-op in MVP (see roadmap)                                                  |
| `context_policy`        | parsed; log “NYI”                                                                       |
| `skills`                | inject `id/path` names into system prompt; no code exec                                 |
| `tools.python`          | allowlist only (`strands_tools.http_request`, `strands_tools.file_read`)                |
| `tools.http_executors`  | supported via internal requester                                                        |
| `agents`                | exactly **one** agent; else EX_UNSUPPORTED                                              |
| `pattern.type=chain`    | **1 step only**; else EX_UNSUPPORTED                                                    |
| `pattern.type=workflow` | **1 task only**; else EX_UNSUPPORTED                                                    |
| other pattern types     | EX_UNSUPPORTED                                                                          |
| `outputs.artifacts`     | write `{{{{ last_response }}}}`; `$TRACE` reserved (roadmap)                            |
| `security.guardrails`   | parsed; warn “not enforced in MVP”                                                      |

### 6.2 Prompt Rendering
- **System** = agent.prompt + `skills` metadata + runtime banner (`name`, `tags`, `budgets` summary).  
- **Task** = `step.input` or `task.input`, Jinja‑style template with variables from `inputs` and `--var`.  
- **Safety**: Strip control chars; cap total token budget (configurable) to avoid provider errors.

### 6.3 Tooling
- `http_executors`: expose `http_request(exec_id, method, path, json/body, headers_override)` tool.  
- `python`: register allowlisted callables by string import path.  
- All tool calls are traced as child spans; request/response bodies redacted if `telemetry.redact.tool_inputs=true`.

### 6.4 Provider-Specific Configuration
- **Bedrock**: requires `runtime.region`; optional `runtime.model_id` (defaults to `us.anthropic.claude-3-sonnet-20240229-v1:0`).
- **Ollama**: requires `runtime.host` (e.g., `http://localhost:11434`); `runtime.model_id` must be installed in Ollama (e.g., `gpt-oss`, `llama3.1`, `mistral`); optional `temperature`, `top_p`, `max_tokens`, `keep_alive`, `stop_sequences`.

### 6.5 Graceful Stop Reports
- Output **Markdown** (and `--format json`) with:
  - Spec fingerprint (sha256), file path.  
  - Unsupported features list (JSONPointer to exact location).  
  - Minimal remediation (e.g., “Reduce chain.steps to 1”, “Remove extra agents”).  
  - Example minimal runnable spec snippet.  
- Exit **18** after writing report to `./artifacts/<name>-unsupported.md`.

---

## 7) Interfaces & Types (Python)

```python
# spec/types.py (pydantic)
class Spec(BaseModel): ...
class CapabilityReport(BaseModel):
    supported: bool
    reasons: list[str]
    pointers: list[str]  # JSONPointer locations
    normalized: dict     # values executor will use
```

```python
# runtime/strands_adapter.py
def build_agent(spec: Spec) -> "StrandsAgent":
    # provider/model/tools mapped here; skills injected into system prompt
    ...
```

```python
# exec/single_agent.py
def run_single_agent(spec: Spec, vars: dict) -> RunResult:
    # render prompts, call agent, capture last_response, write artifacts
    ...
```

---

## 8) Observability (Non-Goal for MVP)

- **OTEL scaffolding**: TracerProvider structure in place but **no-op** (no actual spans emitted in MVP).  
- **Future**: Enable TracerProvider at CLI start; emit spans: `validate`, `plan`, `build_agent`, `tool:<id>`, `llm:completion`.  
- **Future**: Attributes: `spec.name`, `spec.version`, `runtime.model_id`, `pattern.type`.  
- **Future**: Export to console JSON for local dev or remote OTEL collectors.  
- **Future**: Langfuse integration via OTEL bridge.

---

## 9) Security & Compliance

- Secrets from **env only** in MVP.  
- Network access allowed by default; **log** `security.guardrails` but do not enforce.  
- Optional offline mode later; policy engine to enforce denylist/allowlist.  
- PII redaction: redact tool inputs if configured; never log provider credentials.

---

## 10) Testing Strategy

- **Schema tests**: fixtures for valid/invalid specs; snapshot the error paths.  
- **Capability tests**: each unsupported feature returns EX_UNSUPPORTED + the right pointers.  
- **Runtime tests**: agent run with templated input; artifact produced; retries exercised (mock transport).  
- **E2E**: `plan → run` happy path; `explain` on unsupported path.  
- **Determinism**: seedable random; stable tool order; record‑replay stubs for HTTP tools.

---

## 11) Performance & Limits (MVP)

- One model call per run (single agent, single turn).  
- Timeouts: default 60s model call, 30s tool call; overall `max_duration_s` respected (best‑effort).  
- Memory: negligible; artifacts small (<1MB).

---

## 12) Deliverables

- `strands-cli/` Python package (Typer), `uv` project.  
- Modules as defined in §5.1.  
- Embedded [`strands-workflow.schema.json`](../src/strands_cli/schema/strands-workflow.schema.json) — **JSON Schema Draft 2020-12** — the single source of truth for workflow spec validation.  
- Example specs:
  - `examples/single-agent-chain.yaml` (1 step)  
  - `examples/single-agent-workflow.yaml` (1 task)
- CI: lint, test, build; release to internal index / PyPI (private).

---

## 13) Rollout Plan

1. **Dev Preview**: internal users (Thomas + team). Collect unsupported spec samples.  
2. **Beta**: expand tool allowlist; add `$TRACE` artifact; durability polish.  
3. **GA**: policy enforcement, multiple providers, Secrets Manager support.

---

## 14) Roadmap to Full Spec

- **OTEL tracing (V1)**: enable TracerProvider, emit spans for validate/plan/build_agent/tool calls, export to OTEL collectors.  
- **Multi‑agent orchestration**: enable `routing`, `parallel`, `evaluator_optimizer`; later `orchestrator_workers` with worker pools.  
- **Graph/Workflow**: native DAG engine + retries per node.  
- **Context policy**: compaction, notes, JIT retrieval tools (MCP).  
- **Security**: enforce `guardrails`, allowlist/denylist, offline runs.  
- **Human‑in‑the‑loop**: `manual_gate` via Slack/Jira connectors.  
- **Artifacts**: structured result bundles, `$TRACE` export, provenance/citation logs.

---

## 15) Sample Minimal MVP Specs (YAML)

### Ollama Example (Local)
```yaml
version: 0
name: "single-agent-brief-ollama"
runtime:
  provider: ollama
  model_id: "gpt-oss"
  host: "http://localhost:11434"

inputs:
  required:
    topic: string

agents:
  writer:
    prompt: |
      You are a concise analyst. Write 5 bullet insights on {{'{{'}}topic{{'}}'}} with one-line rationales.

pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Produce the insights now."

outputs:
  artifacts:
    - path: "./artifacts/brief-ollama.md"
      from: "{{'{{'}} last_response {{'}}'}}"
```

**Prerequisites:**
```bash
# Install Ollama model
ollama pull gpt-oss

# Start Ollama server
ollama serve
```

**Run:**
```
strands-cli run single-agent-brief-ollama.yaml --var topic="Payments L3 residual risk"
```

---

## 16) Open Questions

- Should MVP enforce `budgets.max_tokens` at the client by truncation or let the provider guard fail?  
- Do we need a pluggable renderer for prompts (Jinja vs runtime template)?  
- How strict should we be about network access in MVP (default allow vs explicit allowlist)?

---

## 17) References

- Strands Agents SDK — announcement & docs (2025): AWS Open Source Blog; GitHub repo; product page.  
- Anthropic — Agentic patterns (prompt chaining, routing, parallelization, orchestrator‑workers, evaluator‑optimizer).

---

## 18) Acceptance Checklist

- [ ] `validate` uses JSON Schema and returns **EX_SCHEMA** with line/column hints.  
- [ ] `plan` renders a normalized view for single‑agent execution.  
- [ ] `run` executes the spec and writes artifacts.  
- [ ] Unsupported features → **EX_UNSUPPORTED** + report.  
- [ ] OTEL scaffolding in place (no-op for MVP; ready for future enablement).  
- [ ] Unit/E2E tests green; CLI docs produced.

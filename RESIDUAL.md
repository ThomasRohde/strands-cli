# Residual Schema Features

**Document Purpose**: This file identifies functionality defined in `strands-workflow.schema.json` that is **parsed but not yet fully implemented or enforced** in the codebase.

**Generated**: 2025-11-13  
**Schema Version**: Draft 2020-12  
**CLI Version**: 0.4.0 (287 tests, 83% coverage)

**Status Legend**:
- ✅ **Fully Implemented** - Feature is coded, tested, and enforced
- ⚠️ **Parsed Only** - Schema validates it, Pydantic loads it, but no runtime enforcement
- ❌ **Not Implemented** - Schema defines it, but no code exists
- 🚧 **Partial Implementation** - Some aspects work, others don't

---

## Table of Contents

1. [Runtime Features](#1-runtime-features)
2. [Environment & Secrets](#2-environment--secrets)
3. [Context Policy](#3-context-policy)
4. [Security Features](#4-security-features)
5. [Telemetry & Observability](#5-telemetry--observability)
6. [Agent Configuration](#6-agent-configuration)
7. [Tools & MCP](#7-tools--mcp)
8. [Pattern-Specific Features](#8-pattern-specific-features)
9. [Skills](#9-skills)
10. [Input/Output Features](#10-inputoutput-features)
11. [Summary Tables](#11-summary-tables)

---

## 1. Runtime Features

### 1.1 Budgets (`runtime.budgets`)

**Schema Location**: `#/$defs/runtime` → `budgets`

| Feature | Type | Schema Default | Status | Notes |
|---------|------|----------------|--------|-------|
| `max_steps` | integer (min: 1) | - | ⚠️ **Parsed Only** | Logged in runtime banner; not enforced during execution |
| `max_tokens` | integer (min: 1) | - | ✅ **Implemented** | Enforced in `runtime/budget.py` via `BudgetMonitor` class; warning at 80%, abort at 100% |
| `max_duration_s` | integer (min: 1) | - | ⚠️ **Parsed Only** | Logged in runtime banner; no timer enforcement in executors |
| `warn_threshold` | number (0.0-1.0) | 0.8 | ✅ **Implemented** | Configurable warning threshold for token budget; default 80% |

**Implementation Details**:
- ✅ **Token budget enforcement**: `src/strands_cli/runtime/budget.py` lines 88-109
  - Tracks cumulative token usage across agent invocations
  - Logs warning at `warn_threshold` percentage
  - Raises `BudgetExceededError` at 100%, triggers exit code `EX_BUDGET_EXCEEDED (11)`
  - Runs AFTER compaction hook to allow token reduction before abort
- ❌ **Step budget**: No code found that counts steps or enforces `max_steps`
- ❌ **Duration budget**: No `asyncio.timeout()` or `time.time()` checks found in executors

**Capability Checker**: No validation for budgets (silently accepted)

**Remediation**:
```python
# Future implementation in executors
step_count = 0
start_time = time.time()

for step in steps:
    step_count += 1
    if spec.runtime.budgets.max_steps and step_count > spec.runtime.budgets.max_steps:
        raise BudgetExceededError("Max steps exceeded")
    
    if spec.runtime.budgets.max_duration_s:
        elapsed = time.time() - start_time
        if elapsed > spec.runtime.budgets.max_duration_s:
            raise BudgetExceededError("Max duration exceeded")
```

---

### 1.2 Failure Policy (`runtime.failure_policy`)

**Schema Location**: `#/$defs/runtime` → `failure_policy`

| Feature | Type | Schema Default | Status | Notes |
|---------|------|----------------|--------|-------|
| `retries` | integer (min: 0) | - | ✅ **Implemented** | Used in `exec/utils.py` `invoke_agent_with_retry()` via `tenacity` |
| `backoff` | enum | exponential | ✅ **Implemented** | Exponential backoff working; constant/jittered not tested |
| `wait_min` | integer (min: 0) | - | ⚠️ **Parsed Only** | Not passed to `tenacity` retry decorator |
| `wait_max` | integer (min: 0) | - | ⚠️ **Parsed Only** | Not passed to `tenacity` retry decorator |

**Implementation Details**:
- ✅ **Retries**: `src/strands_cli/exec/utils.py` lines 246-261
  - Uses `tenacity.retry()` with `stop_after_attempt(retries + 1)`
  - Hardcoded `wait=wait_exponential(multiplier=1, min=2, max=30)`
- ❌ **Custom wait times**: `failure_policy.wait_min` and `failure_policy.wait_max` are loaded into `Runtime` Pydantic model but **never referenced** in retry logic

**Capability Checker**: No validation (silently accepted)

**Remediation**:
```python
# In exec/utils.py, replace hardcoded wait with:
wait_min = runtime.failure_policy.wait_min or 2
wait_max = runtime.failure_policy.wait_max or 30
wait_strategy = wait_exponential(multiplier=1, min=wait_min, max=wait_max)
```

---

### 1.3 Inference Settings (Agent-Level Overrides)

**Schema Location**: `#/$defs/agentSpec` → `inference`

| Feature | Provider Support | Status | Notes |
|---------|------------------|--------|-------|
| `temperature` | OpenAI | ✅ **Implemented** | Bedrock/Ollama ignore it |
| `top_p` | OpenAI | ✅ **Implemented** | Bedrock/Ollama ignore it |
| `max_tokens` | OpenAI | ✅ **Implemented** | Bedrock/Ollama ignore it |

**Implementation Details**:
- ✅ **OpenAI**: `src/strands_cli/runtime/strands_adapter.py` lines 285-292
  - Agent-level `inference` overrides are passed to OpenAI model creation
- ❌ **Bedrock**: No support for inference overrides; model creation ignores agent config
- ❌ **Ollama**: No support for inference overrides

**Capability Checker**: No validation that inference settings are provider-specific

**Documentation Gap**: Schema doesn't indicate that `inference` only works for OpenAI

---

### 1.4 Provider/Model Agent-Level Overrides

**Schema Location**: `#/$defs/agentSpec` → `provider`, `model_id`

| Feature | Status | Notes |
|---------|--------|-------|
| `provider` | ⚠️ **Parsed Only** | Pydantic loads it, but runtime adapter **ignores it**; always uses `spec.runtime.provider` |
| `model_id` | ✅ **Implemented** | Agent-level override working; see `strands_adapter.py` line 277 |

**Implementation Details**:
- ✅ **Model override**: Agent can specify different model (e.g., `gpt-4o-mini` for summarization while main is `gpt-4o`)
- ❌ **Provider override**: No code found that allows per-agent provider switching (e.g., orchestrator on Bedrock, workers on Ollama)

**Capability Checker**: No validation; workflow with `agents.foo.provider: "bedrock"` when `runtime.provider: "openai"` would be silently ignored

---

## 2. Environment & Secrets

### 2.1 Secret Sources (`env.secrets[].source`)

**Schema Location**: `#/$defs/env` → `secrets[].source`

| Source | Schema Enum Value | Status | Capability Check |
|--------|-------------------|--------|------------------|
| `env` | ✅ | ✅ **Implemented** | ✅ Enforced (only allowed value) |
| `secrets_manager` | ✅ | ❌ **Not Implemented** | ✅ Flagged as unsupported |
| `ssm` | ✅ | ❌ **Not Implemented** | ✅ Flagged as unsupported |
| `file` | ✅ | ❌ **Not Implemented** | ✅ Flagged as unsupported |

**Implementation Details**:
- ✅ **env source**: `src/strands_cli/runtime/tools.py` line 67 reads from `os.environ`
- ❌ **AWS integrations**: No boto3 code for Secrets Manager or SSM Parameter Store
- ❌ **File secrets**: No file I/O for reading secret files

**Capability Checker**: `src/strands_cli/capability/checker.py` lines 543-560
```python
if secret.source != SecretSource.ENV:
    issues.append(
        CapabilityIssue(
            pointer=f"/env/secrets/{i}/source",
            reason=f"Secret source '{secret.source}' not supported in MVP",
            remediation="Use source: env",
        )
    )
```

**Exit Code**: Workflows with non-`env` sources will fail with `EX_UNSUPPORTED (18)` and structured remediation report.

---

### 2.2 Environment Mounts (`env.mounts`)

**Schema Location**: `#/$defs/env` → `mounts`

**Schema Definition**:
```json
"mounts": {
  "type": "object",
  "description": "Logical mount name to local path.",
  "additionalProperties": {
    "type": "string"
  }
}
```

**Status**: ❌ **Not Implemented**

**Evidence**:
- Schema allows: `env.mounts: { data: /mnt/data, logs: /var/logs }`
- No grep matches for "mounts" in `src/strands_cli/` except schema validation
- No file mounting, volume mapping, or path aliasing in runtime or executors

**Capability Checker**: No validation (silently accepted)

**Use Case**: Would enable portable path references in prompts/tools (e.g., `${data}/input.csv`)

---

## 3. Context Policy

### 3.1 Compaction Settings (`context_policy.compaction`)

**Schema Location**: `#/$defs/contextPolicy` → `compaction`

| Feature | Type | Schema Default | Status | Notes |
|---------|------|----------------|--------|-------|
| `enabled` | boolean | true | ✅ **Implemented** | Passed to Strands SDK `ConversationManager` |
| `when_tokens_over` | integer (min: 1000) | - | ✅ **Implemented** | Threshold enforced via `CompactionHook` |
| `summary_ratio` | number (0.0-1.0) | 0.35 | ✅ **Implemented** | Proportion of messages to summarize |
| `preserve_recent_messages` | integer (min: 1) | 12 | ✅ **Implemented** | Recent messages kept intact |
| `summarization_model` | string | - | ✅ **Implemented** | Creates pooled agent for cheaper model |

**Implementation Details**:
- ✅ **Full SDK integration**: `src/strands_cli/exec/utils.py` lines 44-71 creates `CompactionHook`
  - Hook is injected into agent via `build_agent()` parameter
  - Strands SDK auto-compacts conversation when token threshold exceeded
  - Uses cheaper model for summarization (e.g., `gpt-4o-mini` instead of `gpt-4o`)
- ✅ **Budget interaction**: Compaction runs BEFORE budget enforcement, allowing token reduction

**Capability Checker**: No validation (feature working, no check needed)

---

### 3.2 Notes (`context_policy.notes`)

**Schema Location**: `#/$defs/contextPolicy` → `notes`

| Feature | Type | Schema Default | Status | Notes |
|---------|------|----------------|--------|-------|
| `file` | string | - | ✅ **Implemented** | Markdown notes written to file path |
| `include_last` | integer (min: 1) | 12 | ✅ **Implemented** | Last N notes injected into agent context |
| `format` | enum (markdown, json) | markdown | ⚠️ **Parsed Only** | Only markdown implemented; JSON format ignored |

**Implementation Details**:
- ✅ **Markdown notes**: `src/strands_cli/exec/utils.py` lines 94-120
  - `NotesHook` tracks step/task execution and writes structured notes
  - Notes injected into system prompt via `build_agent()` parameter
  - Format: `## Step {n}: {agent_id}\n- **Input**: ...\n- **Output**: ...`
- ❌ **JSON format**: No code found that serializes notes as JSON when `format: json`

**Capability Checker**: No validation (silently accepts `format: json` but outputs markdown)

**Documentation Gap**: Manual describes notes but doesn't specify markdown-only limitation

---

### 3.3 JIT Retrieval Tools (`context_policy.retrieval.jit_tools`)

**Schema Location**: `#/$defs/contextPolicy` → `retrieval.jit_tools`

**Schema Definition**:
```json
"jit_tools": {
  "type": "array",
  "description": "List of JIT tool IDs to auto-inject into agents. Supported tools: grep, head, tail, search.",
  "items": {
    "type": "string",
    "pattern": "^[A-Za-z0-9_-]+$",
    "examples": ["grep", "head", "tail", "search"]
  }
}
```

**Status**: ✅ **Implemented** (Phase 6.3)

**Implementation Details**:
- ✅ **Auto-injection**: `src/strands_cli/runtime/strands_adapter.py` lines 297-312
  - If `context_policy.retrieval.jit_tools` present, tools from registry are added to agent
  - Tools: `grep`, `head`, `tail`, `search` (defined in `src/strands_cli/tools/`)
- ✅ **Validation**: Capability checker cross-references against registry allowlist
- ✅ **Limitations** (documented in manual):
  - Read-only (no file writing, moving, deletion)
  - Text files only (binary files rejected)
  - No directory operations
  - No shell execution

**Capability Checker**: No explicit check; relies on tool registry validation

---

### 3.4 MCP Servers (`context_policy.retrieval.mcp_servers`)

**Schema Location**: `#/$defs/contextPolicy` → `retrieval.mcp_servers`

**Schema Definition**:
```json
"mcp_servers": {
  "type": "array",
  "description": "List of Model Context Protocol (MCP) server IDs to enable (Phase 9 feature - placeholder).",
  "items": {
    "type": "string",
    "pattern": "^[A-Za-z0-9_-]+$"
  }
}
```

**Status**: ❌ **Not Implemented**

**Evidence**:
- Schema includes it with "Phase 9 feature - placeholder" comment
- MCP tools are implemented (`tools.mcp`), but `context_policy.retrieval.mcp_servers` is NOT
- No code found that auto-enables MCP servers based on this field
- **Workaround**: MCP servers must be declared in `tools.mcp` and explicitly added to `agents[].tools`

**Capability Checker**: No validation (silently accepted)

**Design Intent**: Would allow MCP servers to be auto-injected like JIT tools, without explicit agent tool declarations

---

## 4. Security Features

### 4.1 Guardrails (`security.guardrails`)

**Schema Location**: `#/$defs/security` → `guardrails`

| Feature | Type | Status | Notes |
|---------|------|--------|-------|
| `deny_network` | boolean | ❌ **Not Implemented** | Parsed but no network blocking in tool execution |
| `pii_redaction` | boolean | ❌ **Not Implemented** | Parsed but no runtime PII scrubbing (telemetry has separate redaction) |
| `allow_tools` | array[string] | ❌ **Not Implemented** | Parsed but not used for runtime allowlisting |

**Implementation Details**:
- ❌ **No enforcement code**: `src/strands_cli/types.py` line 1027 defines `Security` model with comment: `"Security configuration (parsed but not enforced in MVP)"`
- ✅ **Static allowlisting exists**: Python tools validated against hardcoded allowlist in capability checker, but NOT from `security.guardrails.allow_tools`
- ❌ **Network denial**: No `requests` monkey-patching or subprocess blocking found
- ⚠️ **Telemetry PII redaction**: Exists in `telemetry/otel.py` but separate from `security.guardrails.pii_redaction`

**Capability Checker**: No validation (silently accepted)

**Confusion Point**: Schema has TWO PII redaction fields:
1. `security.guardrails.pii_redaction` (not implemented)
2. `telemetry.redact.tool_inputs` / `tool_outputs` (implemented)

**Recommendation**: Clarify in schema which PII redaction controls runtime vs. telemetry

---

## 5. Telemetry & Observability

### 5.1 OTEL Configuration (`telemetry.otel`)

**Schema Location**: `#/$defs/telemetry` → `otel`

| Feature | Type | Status | Notes |
|---------|------|--------|-------|
| `endpoint` | string (URI) | ✅ **Implemented** | OTLP gRPC endpoint configured via TracerProvider |
| `service_name` | string | ✅ **Implemented** | Sets service.name resource attribute |
| `sample_ratio` | number (0.0-1.0) | ✅ **Implemented** | Sampling ratio enforced via TraceIdRatioBased sampler |

**Implementation Details**:
- ✅ **Full OTLP support**: `src/strands_cli/telemetry/otel.py` (Phase 10, v0.10.0)
  - TracerProvider with OTLP gRPC exporter
  - Console exporter for local dev
  - Auto-instrumentation for `httpx` and `asyncio`
  - Workflow-level spans: `workflow_execution`, `pattern_execution`, `step_execution`, etc.
  - Events: `execution_start`, `step_complete`, `budget_warning`, `error_occurred`
- ✅ **Trace artifacts**: `{{ $TRACE }}` template variable exports spans as JSON

**Capability Checker**: No validation (feature working)

**Contradiction**: Copilot instructions (`.github/copilot-instructions.md`) say "OTEL scaffolding in place (no-op for MVP)", but CHANGELOG v0.10.0 says "Full OTLP tracing activation"

---

### 5.2 Redaction Settings (`telemetry.redact`)

**Schema Location**: `#/$defs/telemetry` → `redact`

| Feature | Type | Schema Default | Status | Notes |
|---------|------|----------------|--------|-------|
| `tool_inputs` | boolean | true | ✅ **Implemented** | Redacts tool inputs in spans |
| `tool_outputs` | boolean | false | ✅ **Implemented** | Redacts tool outputs in spans |

**Implementation Details**:
- ✅ **PII scrubbing**: `src/strands_cli/telemetry/otel.py` lines 130-180
  - Built-in patterns: emails, credit cards, SSN, phone numbers, API keys
  - Configurable custom regex patterns
  - Applies to span attributes and events
- ✅ **Configurability**: Respects `telemetry.redact` settings from spec

**Capability Checker**: No validation (feature working)

---

## 6. Agent Configuration

### 6.1 Provider Override (`agents.<id>.provider`)

**Schema Location**: `#/$defs/agentSpec` → `provider`

**Schema Definition**:
```json
"provider": {
  "type": "string",
  "description": "Overrides runtime.provider"
}
```

**Status**: ⚠️ **Parsed Only**

**Evidence**:
- ✅ Schema allows: `agents.orchestrator.provider: "bedrock"` when `runtime.provider: "openai"`
- ❌ No code in `strands_adapter.py` that uses agent-level `provider`
- ✅ Agent-level `model_id` override works (line 277)
- ❌ Provider override silently ignored

**Capability Checker**: No validation (silently accepted)

**Use Case**: Mixed-provider workflows (e.g., orchestrator on Bedrock for cost, workers on OpenAI for speed)

---

## 7. Tools & MCP

### 7.1 Python Tool Formats

**Schema Location**: `#/$defs/tools` → `python`

**Schema Supports Two Formats**:

1. **Shorthand** (string): `"strands_tools.http_request"`
2. **Object** (with `callable` field): `{ "callable": "strands_tools.http_request" }`

**Status**: ✅ **Both Implemented**

**Implementation**: `src/strands_cli/runtime/tools.py` lines 143-165
- Handles both string and object formats via Pydantic discriminator
- Object format exists for "backward compatibility and future extensibility" per schema comment

**Future Extension Point**: Object format could support additional fields (e.g., `timeout`, `retries`, `config`)

---

### 7.2 MCP Transports

**Schema Location**: `#/$defs/tools` → `mcp`

| Transport | Schema Support | Status | Notes |
|-----------|----------------|--------|-------|
| **stdio** | `command` + `args` + `env` | ✅ **Implemented** | Phase 9; working with Strands SDK |
| **HTTPS** | `url` + `headers` | ✅ **Implemented** | Phase 9; SSE transport via Strands SDK |

**Implementation Details**:
- ✅ **stdio**: `src/strands_cli/runtime/tools.py` lines 210-225
  - Launches subprocess with `command` and `args`
  - Passes environment variables
  - Proper cleanup via `AgentCache.close()`
- ✅ **HTTPS**: Lines 226-239
  - HTTP SSE transport to remote MCP servers
  - Header support for auth
  - Async client pooling

**Capability Checker**: Lines 891-895 comment:
```python
# MCP tools are now supported (Phase 9) - no validation needed
```

**Timeout Configuration**: 
- ⚠️ `MCP_STARTUP_TIMEOUT_S` env var is logged but NOT enforced (requires async refactoring per Phase 9.1 notes)

---

### 7.3 HTTP Executor Metadata Fields

**Schema Location**: `#/$defs/tools` → `http_executors[]`

| Field | Status | Notes |
|-------|--------|-------|
| `id` | ✅ **Implemented** | Required |
| `base_url` | ✅ **Implemented** | Required |
| `headers` | ✅ **Implemented** | Secret resolution working |
| `timeout_ms` | ✅ **Implemented** | Converted to seconds for httpx |
| `description` | ⚠️ **Parsed Only** | Loaded but not injected into prompt |
| `examples` | ⚠️ **Parsed Only** | Loaded but not used for agent guidance |
| `common_endpoints` | ⚠️ **Parsed Only** | Loaded but not surfaced to agent |
| `response_format` | ⚠️ **Parsed Only** | Loaded but not documented to agent |
| `authentication_info` | ⚠️ **Parsed Only** | Loaded but not injected into prompt |

**Implementation Details**:
- ✅ **Core execution**: `src/strands_cli/runtime/tools.py` lines 70-108 create httpx clients
- ❌ **Metadata injection**: No code found that adds `description` or `examples` to agent system prompt
- **Use Case**: Rich metadata would help agents understand when/how to use each HTTP executor

**Capability Checker**: No validation for metadata fields

**Remediation**: Modify `strands_adapter.py` to inject HTTP executor metadata into agent system prompt alongside tool specs

---

## 8. Pattern-Specific Features

### 8.1 Multi-Round Orchestration (`orchestrator_workers.orchestrator.limits.max_rounds`)

**Schema Location**: `#/$defs/orchestratorWorkersConfig` → `orchestrator.limits.max_rounds`

**Status**: ❌ **Explicitly Blocked** (Phase 7 MVP limitation)

**Capability Checker**: Lines 334-342
```python
# Phase 7 MVP: Only single round supported
if limits.max_rounds is not None and limits.max_rounds > 1:
    issues.append(
        CapabilityIssue(
            pointer="/pattern/config/orchestrator/limits/max_rounds",
            reason="Multi-round orchestration not yet supported (Phase 7 MVP limitation)",
            remediation="Set max_rounds to 1 or omit for default single-round execution. "
            "Multi-round support planned for future release.",
        )
    )
```

**Exit Code**: Workflows with `max_rounds > 1` will fail with `EX_UNSUPPORTED (18)`

**Design Intent**: Iterative orchestration where orchestrator reviews worker results and spawns new rounds of workers

**Current Behavior**: Orchestrator decomposes once, workers execute in parallel, reduce aggregates, done.

---

### 8.2 Graph Multiple Static Targets (`graph.edges[].to` array)

**Schema Location**: `#/$defs/graphConfig` → `edges[].to`

**Schema Definition**:
```json
"to": {
  "type": "array",
  "items": { "$ref": "#/$defs/identifier" },
  "description": "Static target node IDs. Only the FIRST target is executed (sequential execution of multiple targets not yet supported). Use separate edges or conditional 'choose' for multi-target transitions."
}
```

**Status**: 🚧 **Partial Implementation**

**Implementation Details**:
- ✅ Schema allows: `edges: [{ from: "start", to: ["node1", "node2", "node3"] }]`
- ⚠️ **Only first target executes**: `src/strands_cli/exec/graph.py` uses `edge.to[0]` if present
- ❌ Sequential execution of all targets NOT implemented
- ✅ **Capability warning**: Lines 513-523 log warning if `len(edge.to) > 1`

```python
if edge.to and len(edge.to) > 1:
    warnings.append(
        f"Edge from '{edge.from_node}' has multiple static targets "
        f"{edge.to}. Only the FIRST target ('{edge.to[0]}') will be "
        "executed. Use separate edges or conditional 'choose' for "
        "multi-target transitions."
    )
```

**Exit Code**: `EX_OK (0)` (warning only, not error)

**Workaround**: Define separate edges for each target or use `choose` with conditions

---

### 8.3 HITL Validation and Timeout Enforcement

**Schema Location**: Multiple patterns support HITL with `timeout_seconds` and `validation.pattern`

**HITL Fields in Schema**:
```json
{
  "type": "hitl",
  "prompt": "Review and approve?",
  "context_display": "{{ context }}",
  "default": "approved",
  "timeout_seconds": 300,
  "validation": {
    "pattern": "^(approved|rejected)$"
  }
}
```

**Status**: 
- ✅ `type`, `prompt`, `context_display` - **Implemented**
- ⚠️ `default` - **Parsed but not enforced** (Phase 2 scope)
- ⚠️ `timeout_seconds` - **Parsed but not enforced** (Phase 2 scope)
- ❌ `validation.pattern` - **Not Implemented**

**Implementation Details**:
- ✅ **Core HITL**: `src/strands_cli/exec/utils.py` `prompt_user()` function handles terminal input
- ❌ **Timeout**: No `asyncio.timeout()` or `signal.alarm()` found; user can wait indefinitely
- ❌ **Default response**: No code applies `default` if timeout expires
- ❌ **Regex validation**: No regex matching for user input

**Capability Checker**: No validation (fields silently accepted)

**Phase 2 Note**: CHANGELOG says timeout/default are Phase 2 features but not yet enforced

---

## 9. Skills

### 9.1 Executable Skills (`skills[].preload_metadata` and code execution)

**Schema Location**: `#/$defs/skills`

**Schema Definition**:
```json
"skills": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "path"],
    "properties": {
      "id": { "$ref": "#/$defs/identifier" },
      "path": { "type": "string" },
      "preload_metadata": {
        "type": "boolean",
        "default": false,
        "description": "Whether to preload skill metadata into context"
      }
    }
  }
}
```

**Status**: 
- ✅ **Metadata injection** - Implemented
- ❌ **Code execution** - Not implemented
- ⚠️ `preload_metadata` flag - Parsed but unclear what it controls

**Implementation Details**:
- ✅ **Metadata in prompt**: `src/strands_cli/runtime/strands_adapter.py` line 15 docstring:
  > "Skills: metadata injection (no code execution)"
- ❌ **No skill execution**: No code found that loads Python/JS from `skills[].path` and executes it
- ❌ **No preload distinction**: `preload_metadata: true` vs `false` has no visible effect in code

**Capability Checker**: No validation; skills with executable assets are parsed but unused

**Design Intent**: Skills would allow injecting reusable code libraries (e.g., data processing functions) that agents can call

---

## 10. Input/Output Features

### 10.1 Input Variable Validation (`inputs.required` / `inputs.optional`)

**Schema Location**: `#/$defs/inputs`

**Schema Supports Rich Type Specs**:
```yaml
inputs:
  required:
    user_id: 
      type: integer
      description: "User ID to process"
    action:
      type: string
      enum: ["create", "update", "delete"]
  optional:
    batch_size:
      type: integer
      default: 100
```

**Status**: ⚠️ **Parsed but Not Validated**

**Implementation Details**:
- ✅ Schema validation: `inputs.required` keys must be present in `inputs.values` or CLI `--var`
- ❌ **Type validation**: No runtime check that `user_id` is actually an integer
- ❌ **Enum validation**: No check that `action` is one of the enum values
- ❌ **Default values**: `default` field parsed but not applied when variable missing

**Capability Checker**: No validation beyond schema presence

**Evidence**: `src/strands_cli/loader/yaml_loader.py` merges `--var` into spec but doesn't validate types

**Remediation**: Add Pydantic validation for input values based on type specs

---

### 10.2 Output Artifact Templates

**Schema Location**: `#/$defs/outputs` → `artifacts[].from`

**Schema Definition**:
```json
"from": {
  "type": "string",
  "description": "Source expression (e.g., '{{ last_response }}' or '$TRACE')."
}
```

**Supported Templates**:
- ✅ `{{ last_response }}` - Last agent response
- ✅ `{{ steps[n].response }}` - Chain step response
- ✅ `{{ tasks.<id>.response }}` - Workflow task response
- ✅ `{{ branches.<id>.response }}` - Parallel branch response
- ✅ `{{ nodes.<id>.response }}` - Graph node response
- ✅ `{{ $TRACE }}` - OTEL trace spans as JSON

**Status**: ✅ **Fully Implemented**

**Implementation**: `src/strands_cli/artifacts/io.py` + Jinja2 rendering in each executor

**Safety Note**: No validation that templates reference valid step/task IDs; invalid refs render as empty string

---

## 11. Summary Tables

### 11.1 Implementation Status by Category

| Category | Total Features | Fully Implemented | Partially Implemented | Not Implemented |
|----------|----------------|-------------------|----------------------|-----------------|
| **Runtime** | 10 | 5 (50%) | 4 (40%) | 1 (10%) |
| **Environment** | 4 | 1 (25%) | 0 | 3 (75%) |
| **Context Policy** | 10 | 7 (70%) | 2 (20%) | 1 (10%) |
| **Security** | 3 | 0 | 0 | 3 (100%) |
| **Telemetry** | 5 | 5 (100%) | 0 | 0 |
| **Agent Config** | 5 | 3 (60%) | 1 (20%) | 1 (20%) |
| **Tools** | 12 | 9 (75%) | 3 (25%) | 0 |
| **Patterns** | 8 | 6 (75%) | 1 (12.5%) | 1 (12.5%) |
| **Skills** | 2 | 1 (50%) | 1 (50%) | 0 |
| **I/O** | 4 | 3 (75%) | 1 (25%) | 0 |
| **TOTAL** | **63** | **40 (63%)** | **13 (21%)** | **10 (16%)** |

---

### 11.2 Critical Gaps for Production Use

| Gap | Impact | Priority | Remediation Effort |
|-----|--------|----------|-------------------|
| **Step/duration budgets** | Runaway workflows | 🔴 High | Medium (add counters + timers) |
| **Guardrails enforcement** | Security risk | 🔴 High | High (network sandboxing, allowlist enforcement) |
| **HITL timeout/validation** | UX inconsistency | 🟡 Medium | Low (asyncio.timeout + regex check) |
| **Multi-round orchestration** | Pattern limitation | 🟡 Medium | High (orchestrator loop + state management) |
| **Secrets Manager/SSM** | Production credential management | 🟡 Medium | Medium (boto3 integration) |
| **Input type validation** | Runtime type errors | 🟢 Low | Low (Pydantic validation) |
| **HTTP executor metadata** | Agent guidance | 🟢 Low | Low (prompt injection) |
| **Environment mounts** | Portability | 🟢 Low | Medium (path resolution + aliasing) |

---

### 11.3 Features That Will Silently Fail (No Capability Check)

These schema features are **parsed and accepted** but **not implemented**, with **no validation error**:

1. `runtime.budgets.max_steps` - Logged but not enforced
2. `runtime.budgets.max_duration_s` - Logged but not enforced
3. `runtime.failure_policy.wait_min` / `wait_max` - Ignored (hardcoded values used)
4. `agents.<id>.provider` - Ignored (runtime provider always used)
5. `env.mounts` - No file mounting implemented
6. `context_policy.notes.format: json` - Only markdown works
7. `context_policy.retrieval.mcp_servers` - Must use `tools.mcp` instead
8. `security.guardrails.*` - All fields ignored
9. `tools.http_executors[].description|examples|common_endpoints` - Not shown to agents
10. HITL `default`, `timeout_seconds`, `validation.pattern` - Not enforced

**Recommendation**: Add capability checks for these or document as "experimental/parse-only" in schema

---

## Appendix: Version History

- **2025-11-13**: Initial document generated from schema v0, codebase v0.4.0 (287 tests, 83% coverage)

---

## Contributing

When implementing features from this document:

1. **Update capability checker** - Add validation if feature becomes supported
2. **Add tests** - Maintain ≥85% coverage requirement
3. **Update this document** - Move feature from "Not Implemented" to "Implemented"
4. **Update CHANGELOG.md** - Document in version history
5. **Update manual** - Add usage examples to `docs/strands-workflow-manual.md`

---

## References

- **Schema**: `src/strands_cli/schema/strands-workflow.schema.json`
- **Capability Checker**: `src/strands_cli/capability/checker.py`
- **Runtime Adapter**: `src/strands_cli/runtime/strands_adapter.py`
- **Executors**: `src/strands_cli/exec/*.py`
- **Manual**: `docs/strands-workflow-manual.md`
- **Changelog**: `CHANGELOG.md`

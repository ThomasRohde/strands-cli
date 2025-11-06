# AWS Strands Agents SDK — Context Management Feature Research (Phase 6 v0.7.0)
_Date:_ 2025-11-06

**Goal:** Evaluate **native** support in the AWS **Strands Agents SDK** (open‑source) for Phase 6 context‑management requirements and outline pragmatic implementation patterns where features are only partially supported.

> TL;DR — Strands provides strong primitives for conversation compaction and observability (token usage), first‑class MCP integration, and a community tools package (journal, file ops, shell) that enables “structured notes” and JIT retrieval. Proactive budget enforcement and opinionated “notes” policy require light custom glue (hooks + state).

---

## Legend

- **Native** — supported out‑of‑the‑box by the SDK (documented feature)
- **Partial** — feasible with documented SDK primitives, but needs light glue code/config
- **Custom** — not present; implement with SDK hooks/state/tools

---

## Summary Matrix

| Requirement | Strands Support | Notes |
|---|---|---|
| **6.1 Context Compaction** — activate `context_policy.compaction`; trigger on token threshold; summarize; preserve critical context; configurable summarization agent | **Native/Partial** | Strands ships a **SummarizingConversationManager** that summarizes older messages, preserves recent messages, and allows a custom summarization agent / system prompt. Reduction triggers **reactively when context is exceeded**; a proactive “when_tokens_over” trigger can be added via **hooks** + token metrics. citeturn20view0 |
| **6.2 Structured Notes** — shared notes file; agents append between steps; include last N notes; Markdown w/ timestamps + attribution; continuity across sessions | **Partial** | Use **community `journal` tool** (structured logs/tasks) + **file ops** tools to write Markdown notes; add **Hooks** to append after each cycle with timestamps/agent attribution; use **Agent State/Session** to persist across runs and to slice “last N”. citeturn21view0turn22view0turn18search13 |
| **6.3 JIT Retrieval Tools** — `grep`, `head`, `tail`, `search`; MCP for external knowledge; smart, on‑demand selection | **Partial** | Use **File Operations** tools (read/search/edit) and **Shell** tool for grep/head/tail (with consent controls). For external knowledge, Strands provides **first‑class MCP integration** (`MCPAgentTool`, `MCPClient`). Selection logic is implemented in prompts or custom handlers. citeturn21view0turn24view0 |
| **6.4 Token Budget Management** — real‑time counting; enforce `budgets.max_tokens`; warn near limits; auto‑compact when budget exhausted | **Partial** | **Metrics** expose token usage (input/output/total) on `AgentResult` and telemetry (OpenTelemetry). Enforcement/warnings need a small **runtime guard** (handler/hook) that checks accumulated usage against config and triggers compaction or abort. Conversation managers already auto‑reduce on overflow. citeturn18search0turn18search11turn23view0 |

---

## 6.1 Context Compaction — What’s Native vs Needed

**Native:**  
Strands’ **Conversation Management** includes:

- `SlidingWindowConversationManager` — trims oldest messages when overflowing. citeturn20view0  
- `SummarizingConversationManager` — **summarizes older messages** instead of discarding; configurable `summary_ratio`, `preserve_recent_messages`, and **custom summarization agent / system prompt**; preserves tool‑result pairs. citeturn20view0

**Gaps & pattern:**  
- Trigger is **reactive** (called on overflow via `reduce_context`). To meet “**Trigger when token count > when_tokens_over**”, implement **proactive checks** in an `after_cycle` hook or event‑loop callback that (a) estimates tokens for next turn and (b) invokes the conversation manager’s reduction path early. citeturn23view0

**Reference snippet (proactive compaction guard):**
```python
from strands import Agent
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.hooks import AfterCycleHook

THRESHOLD_TOKENS = 60_000  # example: trigger compaction before context window overflow

class ProactiveCompaction(AfterCycleHook):
    def __call__(self, agent, result):
        # result.accumulated_usage: {'inputTokens': int, 'outputTokens': int, 'totalTokens': int}
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        if total >= THRESHOLD_TOKENS:
            # Re-run manager apply step to summarize before next LLM call
            agent.conversation_manager.apply_management(agent.messages)

agent = Agent(
    conversation_manager=SummarizingConversationManager(
        summary_ratio=0.35, preserve_recent_messages=12
    ),
    hooks=[ProactiveCompaction()],
)
```

---

## 6.2 Structured Notes — Design Using Community Tools + Hooks

**Building blocks:**  
- **`journal` tool**: “Create structured tasks and logs” — suitable for a centralized **notes ledger** per session/workflow. citeturn21view0  
- **File Ops tools** (`file_read`, `file_write`, `editor`): read/append Markdown with timestamps and headings; `editor` includes **search/undo** to manage note hygiene. citeturn21view0  
- **Hooks**: attach **after‑cycle** logic to append a standardized note entry. citeturn3view0  
- **State / Session**: store the notes path + maintain rolling index to include **last N** entries in context on demand. citeturn18search13

**Notes format (Markdown):**
```markdown
## [2025-11-06T09:41:00Z] — Agent: research-orchestrator
- Decision: switched to SummarizingConversationManager at 35% ratio
- Key refs: convo#182, tools: retrieve, file_read
```

**Reference snippet (append per step & inject last N into messages):**
```python
from datetime import datetime, timezone
from strands.hooks import AfterCycleHook

NOTES_PATH = "notes/shared.md"
NOTES_INCLUDE_LAST = 12

class AppendNotes(AfterCycleHook):
    def __call__(self, agent, result):
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = f"## [{ts}] — Agent: {agent.name}\n- Summary: {result.output}\n"
        agent.tool.file_write(path=NOTES_PATH, content=entry, append=True)  # community tool
        agent.state["notes_index"] = agent.state.get("notes_index", 0) + 1

def inject_last_n_notes(agent):
    md = agent.tool.file_read(path=NOTES_PATH)
    # naive split on '## ' headings; slice last N; then add as a system message:
    sections = [f"## {s}" for s in md.split("## ") if s.strip()]
    lastN = "\n".join(sections[-NOTES_INCLUDE_LAST:])
    agent.messages.insert(0, {"role": "system", "content": f"NOTES:\n{lastN}"})
```

**Continuity across sessions:** Persist the notes file in a durable location (e.g., workspace / S3 via a tool) and re‑inject on **session restore** before the next loop.

---

## 6.3 JIT Retrieval Tools — Grep/Head/Tail/Search + MCP

**Local & repo context:**  
- Use **`file_read`/`editor`** for **search** and partial reads (fast, no shell).  
- When necessary, **`shell`** enables `grep | head | tail` workflows; **consent** is controllable via `BYPASS_TOOL_CONSENT`. citeturn21view0

**External knowledge:**  
- Strands exposes **MCP** with `MCPAgentTool` and `MCPClient`; connect to external servers (e.g., in‑house Confluence/KB MCP) and the tools are **auto‑adapted** to the agent tool interface. citeturn24view0

**Smart selection:**  
- Implement selection policy in the system prompt (tool preference order) or add a **BeforeCycle/ToolSelection** hook to route questions to **JIT tools** only when a relevance check passes.

**Reference snippet (MCP + JIT search preference):**
```python
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

mcp = MCPClient(lambda: streamablehttp_client("http://kb.example/mcp/"))
with mcp:
    tools = mcp.list_tools_sync()
    agent = Agent(
        tools=[*tools, editor, file_read],  # community tools
        prompts={"system": "Prefer MCP KB tools over local file search when user asks about policy/confluence."}
    )
```

---

## 6.4 Token Budget Management — Counting, Warning, Enforcing

**What’s available:**  
- **Metrics**: `AgentResult.accumulated_usage` exposes **inputTokens/outputTokens/totalTokens**; telemetry uses **OpenTelemetry** for tracing and dashboards. citeturn18search0turn18search11  
- **Overflow handling**: conversation managers **reduce context** on overflow and retry. citeturn23view0

**What to add:**  
- Config: `budgets.max_tokens`, `budgets.warn_at`  
- Hook: compare **rolling usage** to budgets each cycle; **warn** via a user‑visible assistant message when nearing the limit; **trigger compaction** or **abort** when the limit is hit.

**Reference snippet (budget guard):**
```python
from strands.hooks import AfterCycleHook

BUDGET_MAX = 80_000
BUDGET_WARN = 60_000

class BudgetEnforcer(AfterCycleHook):
    def __call__(self, agent, result):
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        if total >= BUDGET_WARN and total < BUDGET_MAX:
            agent.messages.append({"role":"assistant","content": f"Warning: {total}/{BUDGET_MAX} tokens used. Compacting soon."})
        if total >= BUDGET_MAX:
            agent.conversation_manager.reduce_context(agent.messages)  # force compaction
            # or raise Interrupt / set a guardrail flag
```

---

## Implementation Checklist (Strands)

- [x] Switch to **`SummarizingConversationManager`**; set `preserve_recent_messages`; optionally a **cheaper summarization agent**. citeturn20view0  
- [x] Add **`ProactiveCompaction`** hook bound to a configurable `when_tokens_over`.  
- [x] Install **`strands-agents-tools`**; enable `file_read`, `file_write`, `editor`, `journal`, `shell` (if needed). citeturn21view0  
- [x] Implement **`AppendNotes`** hook; choose a durable notes path (local/S3); **inject last N** on each turn.  
- [x] Integrate **MCP** for external knowledge; prefer MCP tools in prompts. citeturn24view0  
- [x] Add **`BudgetEnforcer`**; output warnings; trigger compaction or stop.  
- [x] Wire **OpenTelemetry** exporter + dashboards for token usage and cycle metrics. citeturn18search6

---

## Risks & Mitigations

- **Lossy summaries** may hide specifics (IDs, numbers). Mitigate with **domain‑specific summary prompts** and **preserve_recent_messages** >= N. citeturn20view0  
- **Token estimates vs provider reality**: rely on **actual usage** from model responses; keep a safety margin in `when_tokens_over`. citeturn18search0  
- **Shell tool safety**: keep consent prompts on in production; whitelist paths/patterns. citeturn21view0

---

## Primary References

- Strands **Conversation Management** (Conversation managers; summarization; preservation) — citeturn20view0  
- Strands **Metrics / Token usage** (AgentResult + telemetry) — citeturn18search0turn18search11  
- Strands **Community Tools** (journal, file ops, shell) — citeturn21view0  
- Strands **MCP integration** (MCPAgentTool/MCPClient, example) — citeturn24view0  

---

### Appendix A — Optional: Cheaper Summarization Agent

Use a different provider/model for compaction to lower cost and latency:

```python
from strands import Agent
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.models import OpenAIModel

summarizer = Agent(model=OpenAIModel(model_id="gpt-4o-mini", params={"temperature":0.1}))
agent = Agent(conversation_manager=SummarizingConversationManager(
    preserve_recent_messages=10,
    summarization_agent=summarizer
))
```

### Appendix B — Example Notes Header Template

```text
## [{ISO8601_TIMESTAMP}] — Agent: {AGENT_NAME}
- Step: {CYCLE_INDEX}
- Decision: {BRIEF_DECISION}
- Tools: {TOOL_LIST}
- Outcome: {ONE_LINE_RESULT}
```

---

_Produced for Phase 6 (v0.7.0) planning._
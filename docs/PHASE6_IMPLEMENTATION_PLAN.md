# Phase 6: Context Management Implementation Plan

**Version:** v0.7.0  
**Created:** 2025-11-07  
**Status:** Planning  
**Complexity:** High  
**Duration:** 2-3 weeks  
**Dependencies:** Phase 1-5 (multi-step workflows, token tracking)

---

## Executive Summary

Implement intelligent context management for long-running workflows using **native Strands SDK primitives** (SummarizingConversationManager, community tools, hooks) with minimal custom glue code. Based on research in `docs/strands-phase6-context-research.md`, this phase leverages:

- **Native**: `SummarizingConversationManager` for context compaction
- **Partial**: Community tools (`journal`, `file_read`, `file_write`) + hooks for structured notes
- **Partial**: File ops + shell tools for JIT retrieval; MCP integration for external knowledge
- **Partial**: Metrics + runtime guards for token budget enforcement

---

## Architecture Overview

### Module Structure

```
src/strands_cli/
├── runtime/
│   ├── context_manager.py      # NEW: Wrapper for Strands ConversationManager
│   ├── token_counter.py        # NEW: tiktoken-based token counting
│   └── budget_enforcer.py      # NEW: Runtime token budget guard
├── tools/
│   ├── jit_retrieval.py        # NEW: grep/head/tail/search adapters
│   └── notes_manager.py        # NEW: Structured notes I/O
├── exec/
│   ├── hooks.py                # NEW: Context management hooks
│   └── [existing executors]    # MODIFY: Integrate context hooks
└── types.py                    # MODIFY: Expand ContextPolicy models

tests/
├── test_context_compaction.py  # NEW: Compaction trigger and summarization
├── test_structured_notes.py    # NEW: Notes I/O and templating
├── test_jit_retrieval.py       # NEW: JIT tools and MCP integration
├── test_token_budgets.py       # NEW: Budget enforcement and warnings
└── fixtures/
    └── phase6/
        ├── long-research-workflow.yaml
        ├── notes-continuation-workflow.yaml
        └── budget-constrained-workflow.yaml
```

### Data Flow

```
Workflow Start
 → Load spec with context_policy
 → Initialize ContextManager (wraps SummarizingConversationManager)
 → Initialize BudgetEnforcer (tracks cumulative tokens)
 → Attach ProactiveCompaction hook (triggers before overflow)
 → Attach NotesAppender hook (writes after each cycle)
 → Execute workflow steps/tasks/branches
   ├─ Before each LLM call:
   │   ├─ Check budget (warn at 80%, enforce at 100%)
   │   ├─ Inject last N notes into context
   │   └─ Check token count → trigger compaction if needed
   ├─ LLM invocation with conversation manager
   └─ After each cycle:
       ├─ Append to notes file (timestamp + agent + result)
       └─ Update budget tracker
 → Cleanup and finalize
```

---

## Feature 6.1: Context Compaction

### 6.1.1 Native Strands Integration

**Use Strands' `SummarizingConversationManager`:**

```python
from strands.agent.conversation_manager import SummarizingConversationManager
from strands import Agent

# Configuration from spec.context_policy.compaction
config = spec.context_policy.compaction
manager = SummarizingConversationManager(
    summary_ratio=0.35,  # Summarize 35% of older messages
    preserve_recent_messages=12,  # Keep last 12 messages intact
    summarization_agent=None  # Use main agent (or custom cheaper agent)
)
```

**Native capabilities (no code needed):**
- ✅ Summarizes older messages instead of discarding
- ✅ Preserves recent messages (configurable count)
- ✅ Preserves tool-result pairs (maintains tool continuity)
- ✅ Custom summarization agent support (e.g., GPT-4o-mini for cost savings)

**Gap: Proactive triggering**  
Strands' manager is **reactive** (triggers on overflow). Implement **proactive check** via hook:

```python
# In exec/hooks.py
from strands.hooks import AfterCycleHook

class ProactiveCompactionHook(AfterCycleHook):
    def __init__(self, threshold_tokens: int):
        self.threshold = threshold_tokens
    
    def __call__(self, agent, result):
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        
        if total >= self.threshold:
            # Force compaction before next turn
            agent.conversation_manager.apply_management(agent.messages)
```

### 6.1.2 Implementation Tasks

- [x] **Research complete** - Strands SDK conversation managers documented
- [ ] Create `runtime/context_manager.py`:
  - [ ] `ContextManager` wrapper class
  - [ ] Factory method: `create_from_policy(context_policy) -> SummarizingConversationManager`
  - [ ] Support custom summarization agent (cheaper model)
- [ ] Create `exec/hooks.py`:
  - [ ] `ProactiveCompactionHook` implementation
  - [ ] Configurable threshold from `context_policy.compaction.when_tokens_over`
- [ ] Expand `types.py` - `ContextPolicy.compaction`:
  ```python
  class Compaction(BaseModel):
      enabled: bool = True
      when_tokens_over: int | None = None  # Trigger threshold
      summary_ratio: float = 0.35
      preserve_recent_messages: int = 12
      summarization_model: str | None = None  # Optional cheaper model
  ```
- [ ] Modify executors to attach hook:
  - [ ] `exec/chain.py`: Add compaction hook to agent
  - [ ] `exec/workflow.py`: Add to all agents via AgentCache
  - [ ] `exec/parallel.py`: Add to all branch agents
  - [ ] `exec/routing.py`: Add to router and routed agents
  - [ ] `exec/evaluator_optimizer.py`: Add to producer and evaluator

### 6.1.3 Testing

- [ ] **Unit tests** (`test_context_compaction.py`):
  - [ ] Test `create_from_policy` with various configs
  - [ ] Test proactive trigger at exact threshold
  - [ ] Test preservation of recent messages
  - [ ] Test custom summarization agent
- [ ] **Integration tests**:
  - [ ] 3-step chain with 50K tokens → compaction at 40K
  - [ ] Verify ≥30% reduction in context size
  - [ ] Verify task-critical info preserved (initial prompt, recent tool results)
- [ ] **E2E test**:
  - [ ] Long research workflow (5+ steps, 150K tokens)
  - [ ] Validate final output quality with compaction

### 6.1.4 Configuration Example

```yaml
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 60000
    summary_ratio: 0.35
    preserve_recent_messages: 10
    summarization_model: "gpt-4o-mini"  # Optional: cheaper model for summaries
```

---

## Feature 6.2: Structured Notes

### 6.2.1 Design Using Community Tools + Hooks

**Building blocks:**
- **Community tools**: `journal`, `file_read`, `file_write`, `editor` from `strands-agents-tools`
- **Hooks**: `AfterCycleHook` to append notes after each step
- **State**: Track notes index and include last N in context
- **Format**: Markdown with ISO8601 timestamps and agent attribution

**Notes template:**
```markdown
## [2025-11-07T14:32:00Z] — Agent: research-agent (Step 1)
- **Input**: Analyze sentiment of customer reviews
- **Tools used**: http_request, file_read
- **Outcome**: Positive sentiment (0.82 score)
- **Key data**: 247 reviews analyzed, top keywords: "fast", "reliable"

## [2025-11-07T14:33:15Z] — Agent: summarizer-agent (Step 2)
- **Input**: Summarize findings from step 1
- **Tools used**: None
- **Outcome**: Generated executive summary
- **Decision**: Escalate to human review due to mixed signals
```

### 6.2.2 Implementation Tasks

- [ ] **Install community tools**:
  ```powershell
  uv add strands-agents-tools
  ```
- [ ] Create `tools/notes_manager.py`:
  - [ ] `NotesManager` class with:
    - [ ] `append_entry(timestamp, agent_name, step_index, input, tools, outcome)`
    - [ ] `read_last_n(n: int) -> str` (returns Markdown)
    - [ ] `format_entry()` - Markdown template
  - [ ] File locking for concurrent writes (use `fcntl` or `filelock`)
- [ ] Create `exec/hooks.py` (extend):
  - [ ] `NotesAppenderHook(AfterCycleHook)`:
    - [ ] Extract relevant data from `AgentResult`
    - [ ] Call `NotesManager.append_entry()`
    - [ ] Increment step counter in shared state
- [ ] Modify executors to inject notes:
  - [ ] Before each step: `inject_last_n_notes(agent, notes_manager, n)`
  - [ ] Insert as system message or user context
- [ ] Expand `types.py` - `ContextPolicy.notes`:
  ```python
  class Notes(BaseModel):
      file: str  # Path to notes file (e.g., "artifacts/notes.md")
      include_last: int = 12  # How many recent notes to inject
      format: str = "markdown"  # Future: JSON, plain text
  ```
- [ ] Add state persistence:
  - [ ] Store notes path in `AgentCache` or executor state
  - [ ] Enable cross-session continuity (read existing notes on startup)

### 6.2.3 Testing

- [ ] **Unit tests** (`test_structured_notes.py`):
  - [ ] Test `append_entry` creates correct Markdown format
  - [ ] Test `read_last_n` slices correctly
  - [ ] Test timestamp formatting (ISO8601)
  - [ ] Test concurrent writes (multiple processes)
- [ ] **Integration tests**:
  - [ ] 3-step chain → 3 note entries in correct order
  - [ ] Notes injection in step 2 includes step 1 note
  - [ ] Agent attribution matches actual agent_id
- [ ] **E2E test**:
  - [ ] Multi-session workflow (run, pause, resume)
  - [ ] Verify notes continuity across sessions

### 6.2.4 Configuration Example

```yaml
context_policy:
  notes:
    file: "artifacts/workflow-notes.md"
    include_last: 8
```

---

## Feature 6.3: JIT Retrieval Tools

### 6.3.1 Local Retrieval Tools

**Use community tools + shell for JIT operations:**

| Tool | Source | Purpose |
|------|--------|---------|
| `file_read` | strands-agents-tools | Read file (optionally with line range) |
| `editor` | strands-agents-tools | Search within file, partial reads |
| `shell` | strands-agents-tools | Execute `grep`, `head`, `tail`, `find` |

**Implementation pattern:**
```python
# In tools/jit_retrieval.py
from strands_agents_tools import file_read, editor, shell

def grep_tool(pattern: str, path: str, context_lines: int = 3) -> str:
    """Grep with context lines."""
    # Use shell tool with consent bypass for trusted operations
    result = shell(f"grep -C {context_lines} '{pattern}' {path}")
    return result

def search_in_file(query: str, path: str) -> str:
    """Search within a file using editor tool."""
    # Editor tool has built-in search
    return editor.search(path, query)
```

### 6.3.2 MCP Integration for External Knowledge

**Use Strands' native MCP support:**

```python
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

# Connect to external MCP server (e.g., Confluence, internal KB)
mcp = MCPClient(lambda: streamablehttp_client("http://kb.example/mcp/"))
with mcp:
    tools = mcp.list_tools_sync()
    # Tools are auto-adapted to Strands tool interface
    agent = Agent(tools=[*tools, file_read, editor])
```

### 6.3.3 Implementation Tasks

- [ ] Create `tools/jit_retrieval.py`:
  - [ ] Wrapper functions: `grep_tool`, `head_tool`, `tail_tool`, `search_tool`
  - [ ] Each wraps community tool or shell command
  - [ ] Add to native tool registry with `TOOL_SPEC` pattern
- [ ] Expand `types.py` - `ContextPolicy.retrieval`:
  ```python
  class Retrieval(BaseModel):
      jit_tools: list[str] | None = None  # e.g., ["grep", "search", "mcp:kb"]
      mcp_servers: list[str] | None = None  # MCP server IDs from tools.mcp
  ```
- [ ] Modify `runtime/strands_adapter.py`:
  - [ ] When `context_policy.retrieval.jit_tools` is set:
    - [ ] Load JIT tools from registry
    - [ ] Add to agent tool list
  - [ ] When `mcp_servers` is set:
    - [ ] Initialize MCP clients
    - [ ] Add MCP tools to agent
- [ ] Add smart selection logic:
  - [ ] System prompt hint: "Prefer MCP KB tools for policy questions; use local grep for code"
  - [ ] Optional: `BeforeCycle` hook to suggest tools based on query analysis

### 6.3.4 Testing

- [ ] **Unit tests** (`test_jit_retrieval.py`):
  - [ ] Test `grep_tool` wrapper with mock shell
  - [ ] Test `search_tool` with mock editor
  - [ ] Test MCP client initialization
- [ ] **Integration tests**:
  - [ ] Agent uses grep to find function definition
  - [ ] Agent uses search to find relevant docs
  - [ ] MCP tool invocation (mock MCP server)
- [ ] **E2E test**:
  - [ ] Workflow with JIT retrieval for large codebase
  - [ ] Verify only relevant context loaded (not entire repo)

### 6.3.5 Configuration Example

```yaml
context_policy:
  retrieval:
    jit_tools:
      - grep
      - search
      - head
      - tail
    mcp_servers:
      - kb_server  # References tools.mcp[id=kb_server]

tools:
  mcp:
    - id: kb_server
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-confluence"]
      env:
        CONFLUENCE_URL: "https://wiki.example.com"
```

---

## Feature 6.4: Token Budget Management

### 6.4.1 Real-Time Token Counting

**Use tiktoken for accurate counts:**

```python
# In runtime/token_counter.py
import tiktoken

class TokenCounter:
    def __init__(self, model_id: str):
        # Map provider model to tiktoken encoding
        self.encoding = self._get_encoding(model_id)
    
    def count_messages(self, messages: list[dict]) -> int:
        """Count tokens in message list (OpenAI format)."""
        num_tokens = 0
        for message in messages:
            # 4 tokens per message overhead
            num_tokens += 4
            for key, value in message.items():
                num_tokens += len(self.encoding.encode(str(value)))
        return num_tokens
    
    def _get_encoding(self, model_id: str) -> tiktoken.Encoding:
        # Map Bedrock/Ollama models to tiktoken encodings
        if "claude" in model_id:
            return tiktoken.get_encoding("cl100k_base")
        elif "gpt-4" in model_id or "gpt-3.5" in model_id:
            return tiktoken.encoding_for_model(model_id)
        else:
            # Fallback for unknown models
            return tiktoken.get_encoding("cl100k_base")
```

### 6.4.2 Budget Enforcement

**Runtime guard with warnings:**

```python
# In runtime/budget_enforcer.py
from strands.hooks import AfterCycleHook

class BudgetEnforcerHook(AfterCycleHook):
    def __init__(self, max_tokens: int, warn_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.warn_threshold = int(max_tokens * warn_threshold)
        self.warned = False
    
    def __call__(self, agent, result):
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        
        # Warning at 80%
        if total >= self.warn_threshold and not self.warned:
            agent.messages.append({
                "role": "assistant",
                "content": f"⚠️  Token budget warning: {total}/{self.max_tokens} tokens used ({total/self.max_tokens*100:.1f}%). Compacting context..."
            })
            self.warned = True
            # Trigger compaction
            agent.conversation_manager.apply_management(agent.messages)
        
        # Hard limit at 100%
        if total >= self.max_tokens:
            raise BudgetExceededError(
                f"Token budget exhausted: {total}/{self.max_tokens} tokens. Aborting workflow."
            )
```

### 6.4.3 Implementation Tasks

- [ ] Create `runtime/token_counter.py`:
  - [ ] `TokenCounter` class with tiktoken integration
  - [ ] Model mapping (Bedrock → tiktoken encoding)
  - [ ] Message token counting (compatible with Strands message format)
- [ ] Create `runtime/budget_enforcer.py`:
  - [ ] `BudgetEnforcerHook` implementation
  - [ ] Warning injection at 80% threshold
  - [ ] Auto-compaction on warning
  - [ ] Hard limit with `BudgetExceededError`
- [ ] Modify executors:
  - [ ] Initialize budget enforcer from `spec.budgets.max_tokens`
  - [ ] Attach to all agents via AgentCache
- [ ] Add exit code:
  - [ ] `EX_BUDGET_EXCEEDED = 19` in `exit_codes.py`
- [ ] Enhance telemetry:
  - [ ] Log budget warnings to structlog
  - [ ] Add OTEL attributes: `budget.max_tokens`, `budget.used_tokens`, `budget.percentage`

### 6.4.4 Testing

- [ ] **Unit tests** (`test_token_budgets.py`):
  - [ ] Test `TokenCounter.count_messages()` accuracy
  - [ ] Test budget warning at 80% threshold
  - [ ] Test hard limit abort at 100%
  - [ ] Test auto-compaction trigger
- [ ] **Integration tests**:
  - [ ] 3-step chain with tight budget → warning → compaction → completion
  - [ ] Workflow exceeding budget → abort with EX_BUDGET_EXCEEDED
- [ ] **E2E test**:
  - [ ] Long workflow with budget enforcement
  - [ ] Verify graceful degradation (compaction, then abort)

### 6.4.5 Configuration Example

```yaml
budgets:
  max_tokens: 80000
  warn_threshold: 0.75  # Warn at 75% instead of default 80%

context_policy:
  compaction:
    enabled: true
    when_tokens_over: 60000  # Proactive compaction before budget exhausted
```

---

## Integration Points

### With Existing Executors

All executors (`exec/*.py`) need updates:

```python
# Example: exec/chain.py
async def run_chain(spec: Spec, variables: dict[str, Any]) -> RunResult:
    cache = AgentCache()
    
    # NEW: Initialize context management
    context_manager = create_context_manager(spec.context_policy)
    notes_manager = NotesManager(spec.context_policy.notes) if spec.context_policy.notes else None
    
    # NEW: Create hooks
    hooks = []
    if spec.context_policy and spec.context_policy.compaction:
        hooks.append(ProactiveCompactionHook(
            threshold_tokens=spec.context_policy.compaction.when_tokens_over or 60000
        ))
    if notes_manager:
        hooks.append(NotesAppenderHook(notes_manager))
    if spec.budgets and spec.budgets.max_tokens:
        hooks.append(BudgetEnforcerHook(spec.budgets.max_tokens))
    
    try:
        for idx, step in enumerate(spec.pattern.config.steps):
            # NEW: Inject notes into context
            if notes_manager:
                inject_last_n_notes(agent, notes_manager, spec.context_policy.notes.include_last)
            
            # Get or build agent with hooks
            agent = await cache.get_or_build_agent(
                spec, step.agent_id, agent_config,
                conversation_manager=context_manager,
                hooks=hooks
            )
            
            result = await invoke_agent_with_retry(agent, prompt, ...)
            # Hook automatically appends to notes
        
        return RunResult(...)
    finally:
        await cache.close()
```

### With AgentCache

Modify `exec/utils.py` - `AgentCache`:

```python
class AgentCache:
    async def get_or_build_agent(
        self,
        spec: Spec,
        agent_id: str,
        agent_config: Agent,
        tool_overrides: list[str] | None = None,
        conversation_manager: ConversationManager | None = None,  # NEW
        hooks: list[Hook] | None = None,  # NEW
    ) -> Agent:
        # Build cache key including conversation manager type
        key = (agent_id, frozenset(tool_overrides or []), type(conversation_manager).__name__)
        
        if key not in self._cache:
            agent = build_agent(
                spec=spec,
                agent_config=agent_config,
                tools=tools,
                conversation_manager=conversation_manager,  # NEW
                hooks=hooks,  # NEW
            )
            self._cache[key] = agent
        
        return self._cache[key]
```

---

## Dependencies & Prerequisites

### Python Packages

```toml
# Add to pyproject.toml [project.dependencies]
tiktoken = "^0.8.0"              # Token counting
strands-agents-tools = "^0.1.0"   # Community tools (journal, file ops, shell)
filelock = "^3.16.0"              # Cross-process file locking for notes
```

### External Services (Optional)

- **MCP servers** for external knowledge retrieval (Phase 9 integration)
- **OTEL collector** for budget metrics visualization (Phase 10)

---

## Testing Strategy

### Test Coverage Goals

- **Unit tests**: ≥90% coverage of new modules
- **Integration tests**: All 4 features working together
- **E2E tests**: Long-running workflows (150K+ tokens)

### Test Fixtures

```
tests/fixtures/phase6/
├── long-research-workflow.yaml       # 5-step chain, 150K tokens
├── notes-continuation-workflow.yaml  # Multi-session with notes
├── budget-constrained-workflow.yaml  # 80K budget, compaction triggers
├── jit-retrieval-codebase.yaml      # Use grep/search on large repo
└── mcp-knowledge-base.yaml          # External KB via MCP
```

### Performance Benchmarks

- **Compaction overhead**: <500ms for 100K token summarization
- **Notes I/O**: <50ms per append (with file locking)
- **Token counting**: <100ms for 10K token message list
- **Budget check**: <10ms per step

---

## Acceptance Criteria

### 6.1 Context Compaction
- [x] Research complete - Strands SDK patterns documented
- [ ] Compaction triggers at configured threshold (e.g., 60K tokens)
- [ ] Context reduces by ≥30% after compaction
- [ ] Recent messages preserved (configurable count)
- [ ] Task-critical information retained (initial prompt, recent tool results)
- [ ] Optional custom summarization agent works (cheaper model)

### 6.2 Structured Notes
- [ ] Notes file created with correct Markdown format
- [ ] Each step appends entry with timestamp and agent attribution
- [ ] Last N notes injected into context before each step
- [ ] Concurrent writes safe (file locking)
- [ ] Cross-session continuity (existing notes loaded on startup)

### 6.3 JIT Retrieval Tools
- [ ] Grep, head, tail, search tools available and working
- [ ] Tools retrieve context without loading full files
- [ ] MCP integration connects to external servers
- [ ] MCP tools auto-adapted to Strands interface
- [ ] Smart tool selection via prompts or hooks

### 6.4 Token Budget Management
- [ ] Real-time token counting accurate (±5% of actual usage)
- [ ] Warning issued at 80% budget threshold
- [ ] Auto-compaction triggered on warning
- [ ] Hard limit enforced at 100% with `EX_BUDGET_EXCEEDED`
- [ ] Budget metrics exported to OTEL (when Phase 10 complete)

### Overall
- [ ] All existing tests pass (479 tests)
- [ ] New tests: ≥40 tests covering all 4 features
- [ ] Coverage remains ≥85%
- [ ] Type safety: mypy strict mode passing
- [ ] Linting: ruff check passing
- [ ] Documentation: Manual updated with context policy examples
- [ ] Examples: 3+ new workflows demonstrating features

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Strands SDK API changes | Low | High | Pin strands-agents-sdk version; monitor releases |
| Token counting inaccuracy (provider differences) | Medium | Medium | Use provider-reported usage as source of truth; tiktoken for estimates |
| Notes file corruption | Low | Medium | Atomic writes with temp file + rename; file locking |
| MCP server instability | Medium | Low | Timeout + retry; circuit breaker pattern |
| Compaction loses critical context | Medium | High | Preserve recent messages; allow custom prompts; extensive testing |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Community tools package instability | Medium | Medium | Fork and vendor if needed; fallback to direct SDK tools |
| Testing complexity for long workflows | High | Medium | Automated fixtures generation; mock LLM responses |
| Integration overhead across 5 executors | Medium | High | Shared hooks pattern; test each executor separately then together |

---

## Timeline & Milestones

### Week 1: Foundation (Nov 7-13)
- [ ] **Day 1-2**: Setup
  - [ ] Install dependencies (tiktoken, strands-agents-tools, filelock)
  - [ ] Expand `types.py` models (Compaction, Notes, Retrieval)
  - [ ] Create module structure (context_manager, token_counter, etc.)
- [ ] **Day 3-5**: Context Compaction (6.1)
  - [ ] Implement `ContextManager` wrapper
  - [ ] Implement `ProactiveCompactionHook`
  - [ ] Unit tests for compaction logic
  - [ ] Integration test: 3-step chain with compaction

### Week 2: Notes & Retrieval (Nov 14-20)
- [ ] **Day 1-3**: Structured Notes (6.2)
  - [ ] Implement `NotesManager` with Markdown formatting
  - [ ] Implement `NotesAppenderHook`
  - [ ] Notes injection in executors
  - [ ] Unit + integration tests
- [ ] **Day 4-5**: JIT Retrieval (6.3)
  - [ ] Implement JIT tool wrappers (grep, search, etc.)
  - [ ] MCP integration pattern
  - [ ] Unit + integration tests

### Week 3: Budgets & Integration (Nov 21-27)
- [ ] **Day 1-2**: Token Budgets (6.4)
  - [ ] Implement `TokenCounter` with tiktoken
  - [ ] Implement `BudgetEnforcerHook`
  - [ ] Unit + integration tests
- [ ] **Day 3-4**: Full Integration
  - [ ] Update all 5 executors (chain, workflow, parallel, routing, evaluator)
  - [ ] Update `AgentCache` to accept conversation manager and hooks
  - [ ] E2E tests with all features enabled
- [ ] **Day 5**: Polish & Documentation
  - [ ] Update manual with context policy examples
  - [ ] Create 3+ example workflows
  - [ ] Performance benchmarking
  - [ ] Final test run: `.\scripts\dev.ps1 ci`

---

## Documentation Updates

### Files to Update

1. **`docs/strands-workflow-manual.md`**
   - [ ] Section 8: Context Policy (expand with all 4 features)
   - [ ] Add configuration examples
   - [ ] Add best practices (when to use compaction, notes, JIT, budgets)

2. **`README.md`**
   - [ ] Add context management to feature list
   - [ ] Update examples section
   - [ ] Add token budget enforcement note

3. **`CHANGELOG.md`**
   - [ ] Document all changes under v0.7.0
   - [ ] Note Strands SDK dependency version

4. **New: `docs/CONTEXT_MANAGEMENT_GUIDE.md`**
   - [ ] Deep dive into each feature
   - [ ] Performance tuning guide
   - [ ] Troubleshooting common issues
   - [ ] Advanced patterns (multi-session workflows, MCP integration)

### Examples to Create

1. **`examples/context-long-research-openai.yaml`**
   - 5-step research workflow
   - Compaction at 60K tokens
   - Notes enabled
   - Budget: 100K tokens

2. **`examples/context-notes-continuation-ollama.yaml`**
   - Multi-session workflow
   - Notes persistence across runs
   - Demonstrates continuity

3. **`examples/context-jit-retrieval-bedrock.yaml`**
   - Large codebase analysis
   - Uses grep/search tools
   - Demonstrates JIT context loading

4. **`examples/context-budget-constrained-openai.yaml`**
   - Tight budget (50K tokens)
   - Auto-compaction + warnings
   - Demonstrates graceful degradation

---

## Success Metrics

### Functional Metrics
- ✅ All 4 context features working independently
- ✅ All 4 features working together in same workflow
- ✅ Context reduced by ≥30% with compaction
- ✅ Notes enable cross-step continuity
- ✅ JIT retrieval reduces memory footprint
- ✅ Budget enforcement prevents overruns

### Quality Metrics
- ✅ Test coverage ≥85% overall
- ✅ Context module coverage ≥90%
- ✅ Zero regressions in existing tests (479 tests passing)
- ✅ Mypy strict mode passing
- ✅ Ruff linting clean

### Performance Metrics
- ✅ Compaction: <500ms for 100K tokens
- ✅ Notes append: <50ms (with locking)
- ✅ Token counting: <100ms for 10K tokens
- ✅ Budget check: <10ms per step
- ✅ No >10% regression on simple workflows

---

## Open Questions

1. **Compaction strategy customization**: Should we allow users to specify custom summarization prompts?
   - **Recommendation**: Start with default, add customization in v0.7.1 if requested

2. **Notes format**: Should we support JSON in addition to Markdown?
   - **Recommendation**: Start with Markdown, add JSON in future if needed for programmatic access

3. **MCP server lifecycle**: Should we start/stop MCP servers per workflow or keep them running?
   - **Recommendation**: Per-workflow for now (simpler), optimize in Phase 9

4. **Token counting**: Use tiktoken estimates or provider-reported actual usage?
   - **Recommendation**: Use both - tiktoken for proactive checks, provider usage for tracking

5. **Budget warning message**: Should it go to logs only or also to agent context?
   - **Recommendation**: Both - logs for observability, context message for agent awareness

---

## Appendix A: Strands SDK Reference

### Key Strands Components Used

1. **`SummarizingConversationManager`**
   - Package: `strands.agent.conversation_manager`
   - Methods: `apply_management(messages)`, `reduce_context(messages)`
   - Config: `summary_ratio`, `preserve_recent_messages`, `summarization_agent`

2. **Hooks**
   - Package: `strands.hooks`
   - Types: `AfterCycleHook`, `BeforeCycleHook`
   - Usage: `agent = Agent(..., hooks=[MyHook()])`

3. **Community Tools**
   - Package: `strands-agents-tools`
   - Tools: `journal`, `file_read`, `file_write`, `editor`, `shell`
   - Consent: Controlled via `BYPASS_TOOL_CONSENT` env var

4. **MCP Integration**
   - Package: `strands.tools.mcp`
   - Classes: `MCPClient`, `MCPAgentTool`
   - Method: `list_tools_sync()` → auto-adapted tools

### Version Pinning

```toml
strands-agents-sdk = ">=0.2.0,<0.3.0"  # Ensure conversation manager stability
strands-agents-tools = ">=0.1.0,<0.2.0"  # Community tools
```

---

## Appendix B: Example Hook Implementation

```python
# Full example: exec/hooks.py
from datetime import datetime, timezone
from strands.hooks import AfterCycleHook
from strands_cli.tools.notes_manager import NotesManager

class NotesAppenderHook(AfterCycleHook):
    """Append structured note after each agent cycle."""
    
    def __init__(self, notes_manager: NotesManager):
        self.notes_manager = notes_manager
        self.step_counter = 0
    
    def __call__(self, agent, result):
        self.step_counter += 1
        
        # Extract data from result
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        agent_name = agent.name
        tools_used = [tool.name for tool in result.tool_results] if result.tool_results else []
        outcome = result.output[:200]  # Truncate long outputs
        
        # Append note
        self.notes_manager.append_entry(
            timestamp=timestamp,
            agent_name=agent_name,
            step_index=self.step_counter,
            input_summary=result.input_summary,  # From agent state
            tools_used=tools_used,
            outcome=outcome
        )

class ProactiveCompactionHook(AfterCycleHook):
    """Trigger compaction before token overflow."""
    
    def __init__(self, threshold_tokens: int):
        self.threshold = threshold_tokens
    
    def __call__(self, agent, result):
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        
        if total >= self.threshold:
            # Trigger compaction via conversation manager
            agent.conversation_manager.apply_management(agent.messages)

class BudgetEnforcerHook(AfterCycleHook):
    """Enforce token budget with warnings and hard limits."""
    
    def __init__(self, max_tokens: int, warn_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.warn_threshold = int(max_tokens * warn_threshold)
        self.warned = False
    
    def __call__(self, agent, result):
        usage = result.accumulated_usage or {}
        total = usage.get("totalTokens", 0)
        
        # Warning at threshold
        if total >= self.warn_threshold and not self.warned:
            warning_msg = (
                f"⚠️  Token budget warning: {total}/{self.max_tokens} tokens used "
                f"({total/self.max_tokens*100:.1f}%). Initiating compaction..."
            )
            agent.messages.append({"role": "assistant", "content": warning_msg})
            self.warned = True
            
            # Auto-trigger compaction
            if agent.conversation_manager:
                agent.conversation_manager.apply_management(agent.messages)
        
        # Hard limit
        if total >= self.max_tokens:
            from strands_cli.exit_codes import EX_BUDGET_EXCEEDED
            raise BudgetExceededError(
                f"Token budget exhausted: {total}/{self.max_tokens} tokens used. "
                "Workflow aborted to prevent cost overrun."
            )
```

---

**End of Implementation Plan**

# Plan: Human-in-the-Loop (Phase 12.1)

Implement manual approval gates using Strands SDK interrupts with configurable timeout behavior and fallback actions. Supports inline interactive CLI approval with integration hooks deferred to Phase 12.4.

## Steps

1. **Extend schema and types** in `src/strands_cli/schema/strands-workflow.schema.json` and `src/strands_cli/types.py` — Add `ManualGate` model with `enabled: bool`, `prompt: str | None`, `approval_tools: list[str] | None`, `timeout_s: int | None`, and `fallback: Literal["deny", "approve", "abort"]` (default: `"deny"`); extend `ChainStep`, `WorkflowTask`, and `GraphNode` with optional `manual_gate` property.

2. **Add approval hook infrastructure** in `src/strands_cli/runtime/hooks.py` (new file) — Implement `ApprovalHook` class using Strands `HookProvider` with `BeforeToolCallEvent` callback that calls `event.interrupt()` for designated tools, enforces timeout via `asyncio.wait_for()`, and applies fallback action (`deny`: cancel tool, `approve`: allow execution, `abort`: raise `ExecutionError`).

3. **Implement interrupt handling in executors** across `src/strands_cli/exec/` modules — Modify `run_chain()`, `run_workflow()`, `run_graph()` to detect `result.stop_reason == "interrupt"`, collect interrupt responses via Rich prompts in `--interactive` mode, handle timeout with fallback logic, and loop with `agent(responses)` to resume execution.

4. **Add state persistence layer** in `src/strands_cli/runtime/state.py` (new file) — Create `WorkflowCheckpoint` model with `session_id`, `spec_fingerprint`, `step_history`, `interrupt_data`, and `timestamp`; implement `save_checkpoint()` and `load_checkpoint()` functions using JSON serialization to `artifacts/<session-id>/checkpoint.json`.

5. **Create resume CLI command** in `src/strands_cli/__main__.py` — Add `@app.command() resume(session_id, approval, interactive)` that loads checkpoint, rebuilds agent cache, constructs interrupt responses, and dispatches to executor with `resume_from` parameter.

6. **Write comprehensive tests** in `tests/test_hitl.py`, `tests/test_approval_hooks.py`, `tests/test_state.py` — Test hook registration, interrupt detection with timeout enforcement, fallback action behavior (deny/approve/abort), checkpoint save/restore, resume command, and multi-session workflows; target ≥85% coverage with mocked `event.interrupt()` and user input.

## Further Considerations

1. **Fallback behavior validation** — Add schema enum constraint for `fallback: "deny" | "approve" | "abort"` with default `"deny"`; ensure `abort` fallback exits with `EX_RUNTIME` and descriptive error message.

2. **Integration hooks deferred** — Slack/Jira approval adapters postponed to Phase 12.4 (Advanced Analytics & Integrations); Phase 12.1 focuses on terminal-based approval with `--interactive` flag and spec-driven timeout/fallback configuration.

3. **Concurrent interrupt aggregation** — When parallel branches trigger multiple manual gates, prompt user sequentially (SDK limitation); consider adding `aggregate_approvals: bool` config in Phase 12.4 to batch approval requests across branches.

## Key Schema Changes

```yaml
# Example spec with manual gate
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Search for {{topic}}"
        tools: ["http_executors"]
        manual_gate:
          enabled: true
          prompt: "Approve HTTP request to external API?"
          approval_tools: ["http_executors"]  # Only gate these tools
          timeout_s: 300  # 5 minutes
          fallback: "deny"  # deny | approve | abort
```

## Exit Code Addition

```python
# src/strands_cli/exit_codes.py
EX_INTERRUPT = 19  # Workflow paused for approval (new)
EX_APPROVAL_TIMEOUT = 20  # Approval timeout with abort fallback (new)
```

## Strands SDK Integration Context

### Key API Methods & Patterns

1. **`event.interrupt(reason, value)`** - Raises an interrupt during `BeforeToolCallEvent` hook
   - `reason`: Unique identifier (namespace recommended, e.g., `"strands-cli-approval"`)
   - `value`: JSON-serializable context data (e.g., `{"tool": "http_executors", "input": {...}}`)

2. **`result.stop_reason`** - Check if agent stopped due to `"interrupt"`

3. **`result.interrupts`** - List of interrupt objects with `id`, `reason`, and `value`

4. **Resume Pattern:**
   ```python
   while True:
       if result.stop_reason != "interrupt":
           break
       
       responses = []
       for interrupt in result.interrupts:
           user_input = input(f"Approve {interrupt.reason}? (y/N): ")
           responses.append({
               "interruptResponse": {
                   "interruptId": interrupt.id,
                   "response": user_input
               }
           })
       
       result = agent(responses)  # Resume with interrupt responses
   ```

5. **State Management:**
   - `session_manager`: Auto-persists interrupt state between sessions
   - `session_manager.get()`: Store interrupt responses to avoid repeated prompts
   - `session_manager.has()`: Check if approval already granted

6. **Hook Integration:**
   - Interrupts raised in `BeforeToolCallEvent` hooks
   - `event.cancel_tool`: Cancel tool execution based on interrupt response
   - Multiple interrupts per hook supported (sequential, not parallel)

### Key Constraints
- Only `BeforeToolCallEvent` is interruptible (not AfterInvocationEvent)
- All concurrent tools are interruptible
- Tools running concurrently that aren't interrupted will execute
- Direct tool calls (non-agent) do NOT support interrupts

## Integration Points

### Files Requiring Modification

#### 1. Schema (`src/strands_cli/schema/strands-workflow.schema.json`)
- Add `ManualGate` definition under `$defs`
- Extend `ChainStep`, `WorkflowTask`, `GraphNode` with `manual_gate` property
- Add enum constraint for `fallback` field

#### 2. Types (`src/strands_cli/types.py`)
```python
class ManualGate(BaseModel):
    """Manual gate configuration for human approval."""
    enabled: bool = True
    prompt: str | None = None  # Custom prompt for user
    approval_tools: list[str] | None = None  # Tools requiring approval
    timeout_s: int | None = None  # Timeout for approval
    fallback: Literal["deny", "approve", "abort"] = "deny"

class ChainStep(BaseModel):
    # ... existing fields ...
    manual_gate: ManualGate | None = None

class WorkflowTask(BaseModel):
    # ... existing fields ...
    manual_gate: ManualGate | None = None

class GraphNode(BaseModel):
    # ... existing fields ...
    manual_gate: ManualGate | None = None
```

#### 3. Hooks (`src/strands_cli/runtime/hooks.py` - NEW)
```python
from strands_agents import HookProvider, HookRegistry, BeforeToolCallEvent

class ApprovalHook(HookProvider):
    """Request human approval before tool execution."""
    
    def __init__(
        self,
        app_name: str,
        approval_tools: list[str],
        timeout_s: int | None = None,
        fallback: Literal["deny", "approve", "abort"] = "deny",
        prompt: str | None = None
    ):
        self.app_name = app_name
        self.approval_tools = approval_tools
        self.timeout_s = timeout_s
        self.fallback = fallback
        self.custom_prompt = prompt
    
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.approve)
    
    def approve(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] not in self.approval_tools:
            return
        
        # Interrupt for approval
        approval = event.interrupt(
            f"{self.app_name}-approval",
            reason={
                "tool": event.tool_use["name"],
                "input": event.tool_use["input"],
                "prompt": self.custom_prompt
            }
        )
        
        # Apply fallback on timeout or denial
        if approval is None:  # Timeout
            if self.fallback == "deny":
                event.cancel_tool = "Approval timeout - access denied"
            elif self.fallback == "abort":
                raise ExecutionError("Approval timeout - workflow aborted")
            # fallback == "approve" -> allow execution
        elif approval.lower() != "y":  # Explicit denial
            if self.fallback == "abort":
                raise ExecutionError("User denied approval - workflow aborted")
            else:
                event.cancel_tool = "User denied approval"
```

#### 4. Executors (`src/strands_cli/exec/chain.py`, `workflow.py`, `graph.py`, etc.)
```python
async def run_chain(
    spec: Spec, 
    variables: dict[str, str] | None = None,
    resume_from: dict[str, Any] | None = None,  # NEW
    interactive: bool = False  # NEW
) -> RunResult:
    """Execute chain pattern with manual gate support."""
    
    cache = AgentCache()
    try:
        for i, step in enumerate(spec.pattern.config.steps):
            # Build agent with optional approval hook
            hooks = []
            if step.manual_gate and step.manual_gate.enabled:
                hooks.append(
                    ApprovalHook(
                        app_name="strands-cli",
                        approval_tools=step.manual_gate.approval_tools or [],
                        timeout_s=step.manual_gate.timeout_s,
                        fallback=step.manual_gate.fallback,
                        prompt=step.manual_gate.prompt
                    )
                )
            
            agent = await cache.get_or_build_agent(
                spec, step.agent_id, agent_config, tool_overrides, hooks=hooks
            )
            
            # Invoke with interrupt handling
            result = await invoke_with_interrupts(
                agent, prompt, interactive=interactive
            )
            
            # Save checkpoint after each step
            if step.manual_gate:
                checkpoint = WorkflowCheckpoint(
                    session_id=generate_session_id(),
                    spec_fingerprint=hash_spec(spec),
                    current_step=i,
                    step_history=step_results,
                    interrupt_data={}
                )
                save_checkpoint(checkpoint, spec.outputs.dir)
        
        return RunResult(...)
    finally:
        await cache.close()

async def invoke_with_interrupts(
    agent: Agent,
    prompt: str,
    interactive: bool = False
) -> InvokeResponse:
    """Invoke agent with interrupt loop handling."""
    
    result = await agent.ainvoke(prompt)
    
    while result.stop_reason == "interrupt":
        if not interactive:
            # Non-interactive: save checkpoint and exit
            raise InterruptError("Workflow paused for approval")
        
        # Interactive: prompt user
        responses = []
        for interrupt in result.interrupts:
            approval_prompt = interrupt.value.get("prompt") or f"Approve {interrupt.value['tool']}?"
            user_input = Confirm.ask(f"[yellow]{approval_prompt}[/yellow]")
            
            responses.append({
                "interruptResponse": {
                    "interruptId": interrupt.id,
                    "response": "y" if user_input else "n"
                }
            })
        
        # Resume with responses
        result = await agent.ainvoke(responses)
    
    return result
```

#### 5. State Management (`src/strands_cli/runtime/state.py` - NEW)
```python
from pydantic import BaseModel
from pathlib import Path
import json
import hashlib

class WorkflowCheckpoint(BaseModel):
    """Workflow execution checkpoint for resumption."""
    session_id: str
    spec_fingerprint: str
    current_step: int
    step_history: list[dict[str, Any]]
    interrupt_data: dict[str, Any]
    timestamp: str

def save_checkpoint(checkpoint: WorkflowCheckpoint, out_dir: str) -> Path:
    """Save checkpoint to artifacts/<session-id>/checkpoint.json"""
    checkpoint_dir = Path(out_dir) / checkpoint.session_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_file = checkpoint_dir / "checkpoint.json"
    checkpoint_file.write_text(checkpoint.model_dump_json(indent=2))
    
    return checkpoint_file

def load_checkpoint(session_id: str, out_dir: str) -> WorkflowCheckpoint:
    """Load checkpoint from artifacts/<session-id>/checkpoint.json"""
    checkpoint_file = Path(out_dir) / session_id / "checkpoint.json"
    
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_file}")
    
    data = json.loads(checkpoint_file.read_text())
    return WorkflowCheckpoint(**data)

def generate_session_id() -> str:
    """Generate unique session ID."""
    import uuid
    return str(uuid.uuid4())

def hash_spec(spec: Spec) -> str:
    """Generate fingerprint of spec for validation."""
    spec_json = spec.model_dump_json(sort_keys=True)
    return hashlib.sha256(spec_json.encode()).hexdigest()
```

#### 6. CLI Commands (`src/strands_cli/__main__.py`)
```python
@app.command()
def resume(
    session_id: Annotated[str, typer.Argument(help="Session ID to resume")],
    approval: Annotated[str | None, typer.Option("--approval", help="Approval response (y/n)")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="Interactive approval mode")] = False,
    out: Annotated[str, typer.Option("--out", help="Output directory")] = "./artifacts",
) -> None:
    """Resume interrupted workflow with approval."""
    try:
        # Load checkpoint
        checkpoint = load_checkpoint(session_id, out)
        
        # Load original spec (need to store spec path in checkpoint)
        # ... spec loading logic ...
        
        # Build interrupt responses
        if approval:
            responses = [{"interruptResponse": {"response": approval}}]
        else:
            responses = None
        
        # Resume from checkpoint
        result = asyncio.run(
            run_chain(spec, resume_from=checkpoint.model_dump(), interactive=interactive)
        )
        
        console.print(f"[green]✓ Workflow resumed and completed[/green]")
        sys.exit(EX_OK)
        
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_IO)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_RUNTIME)

# Update run command to support --interactive
@app.command()
def run(
    spec_file: Annotated[str, typer.Argument(...)],
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
    # ... existing options ...
) -> None:
    """Run workflow with optional interactive approval."""
    # ... existing logic ...
    
    try:
        result = asyncio.run(
            executor(spec, variables, interactive=interactive)
        )
        # ... rest of run logic ...
    except InterruptError:
        console.print("[yellow]⏸ Workflow paused for approval[/yellow]")
        console.print(f"Resume with: strands resume {session_id} --interactive")
        sys.exit(EX_INTERRUPT)
```

#### 7. Exit Codes (`src/strands_cli/exit_codes.py`)
```python
EX_INTERRUPT = 19  # Workflow paused for approval
EX_APPROVAL_TIMEOUT = 20  # Approval timeout with abort fallback
```

## Implementation Strategy

### Phase 1: SDK-Native Interrupts (3-4 days)
- Implement `ApprovalHook` in new `runtime/hooks.py`
- Add timeout enforcement via `asyncio.wait_for()`
- Modify executors to handle `stop_reason == "interrupt"` loop
- Add `--interactive` flag to `run` command for inline prompts
- Test with tool-level approvals (http_executors, file operations)

### Phase 2: Step-Level Gates (4-5 days)
- Extend schema with `ManualGate` definition and enum constraints
- Update `ChainStep`, `WorkflowTask`, `GraphNode` types
- Modify executors to check `step.manual_gate` and inject hooks
- Implement fallback logic (deny/approve/abort)
- Pause before step, prompt user, resume with approval

### Phase 3: State Persistence (5-7 days)
- Implement `WorkflowCheckpoint` model
- Add `save_checkpoint()` / `load_checkpoint()` functions
- Create `resume` CLI command
- Support multi-session workflows with checkpoint restoration
- Handle spec fingerprint validation on resume

## Testing Strategy

### Unit Tests (`tests/test_approval_hooks.py`)
- Test `ApprovalHook` registration and callback invocation
- Mock `BeforeToolCallEvent.interrupt()` calls
- Verify timeout enforcement with `asyncio.wait_for()`
- Test fallback behavior: deny → cancel_tool, approve → allow, abort → raise
- Test custom prompt override

### Integration Tests (`tests/test_hitl.py`)
- Test chain executor with manual gate enabled
- Mock user input for interactive approval
- Verify interrupt detection and response collection
- Test timeout with different fallback strategies
- Test resume from checkpoint

### E2E Tests (`tests/test_state.py`)
- Test checkpoint save/load roundtrip
- Verify spec fingerprint validation on resume
- Test session ID generation uniqueness
- Test multi-session workflow continuity
- Test concurrent approval gates in parallel branches

### Coverage Target
- Overall: ≥85%
- New modules: ≥90% (hooks.py, state.py)
- Modified executors: ≥80% (chain.py, workflow.py, graph.py)

## Acceptance Criteria

- [ ] `ManualGate` model with `fallback` enum in schema and types
- [ ] `ApprovalHook` raises interrupts for designated tools
- [ ] Timeout enforcement with configurable fallback action
- [ ] Interactive mode prompts user via Rich console
- [ ] Non-interactive mode saves checkpoint and exits with `EX_INTERRUPT`
- [ ] `resume` command loads checkpoint and continues execution
- [ ] Spec fingerprint validation prevents resume with modified spec
- [ ] All tests pass with ≥85% coverage
- [ ] Documentation updated with manual gate examples
- [ ] Example specs demonstrate deny/approve/abort fallbacks

## Example Workflow Specs

### Example 1: HTTP Request Approval with Deny Fallback
```yaml
version: 0
name: "web-research-with-approval"
runtime:
  provider: openai
  model_id: "gpt-4o"

agents:
  researcher:
    prompt: "Research {{topic}} using web search"
    tools: ["http_executors"]

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Find information about {{topic}}"
        manual_gate:
          enabled: true
          prompt: "Allow HTTP request to external API?"
          approval_tools: ["http_executors"]
          timeout_s: 300
          fallback: "deny"  # Cancel tool on timeout

outputs:
  artifacts:
    - path: "./artifacts/research.md"
      from: "{{ last_response }}"
```

### Example 2: File Operations with Abort Fallback
```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: file_manager
        input: "Organize files in {{directory}}"
        manual_gate:
          enabled: true
          prompt: "Approve file modifications?"
          approval_tools: ["strands_tools.file_write", "strands_tools.file_delete"]
          timeout_s: 600
          fallback: "abort"  # Stop workflow on timeout
```

### Example 3: Workflow Pattern with Selective Approval
```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: search
        agent: searcher
        input: "Search for {{query}}"
        # No manual gate - always execute
      
      - id: analyze
        agent: analyzer
        input: "Analyze {{ tasks.search.response }}"
        depends_on: [search]
        manual_gate:
          enabled: true
          prompt: "Approve analysis with external API?"
          approval_tools: ["http_executors"]
          timeout_s: 300
          fallback: "approve"  # Auto-approve on timeout
```

## Duration & Complexity

**Total Duration:** 2-3 weeks (12-16 days)  
**Complexity:** High  
**Dependencies:** None (can start immediately after Phase 10)

## Key Design Decisions

1. **Timeout handling**: Use `asyncio.wait_for()` wrapper around user input prompt; on timeout, apply configured fallback action
2. **Fallback semantics**: 
   - `deny`: Cancel tool execution (set `event.cancel_tool`)
   - `approve`: Allow tool execution (no-op)
   - `abort`: Raise `ExecutionError` to stop workflow
3. **Checkpoint granularity**: Save checkpoint after each step with manual gate (not every step)
4. **Session ID**: UUID v4 for uniqueness; stored in checkpoint for resume
5. **Spec fingerprint**: SHA-256 hash of spec JSON to prevent resume with modified spec
6. **Interactive mode**: `--interactive` flag required for inline prompts; non-interactive saves checkpoint and exits
7. **Integration hooks**: Deferred to Phase 12.4 (focus on terminal approval first)

# Phase 2 Implementation Plan: Chain Pattern Resume

**Created:** 2025-11-09  
**Status:** 📋 Ready for Implementation  
**Dependencies:** Phase 1 (Session Persistence Infrastructure) - MUST BE COMPLETE  
**Duration:** 2 weeks (10 working days)  
**Complexity:** Medium-High  
**Target Version:** v0.2.0 (Durable Execution)

---

## Executive Summary

This plan implements **resume from checkpoint** functionality for the chain pattern workflow, enabling:
- Crash recovery without re-executing completed steps
- Long-running workflows that can pause and resume across CLI sessions
- Cost optimization by avoiding re-running expensive LLM calls
- Integration with Strands SDK's native session management for agent conversation restoration

**Prerequisites:** Phase 1 must be completed with:
- ✅ `SessionState`, `SessionMetadata`, `TokenUsage` Pydantic models
- ✅ `FileSessionRepository` with save/load/list/delete operations
- ✅ Session ID generation and spec hash utilities
- ✅ ≥85% test coverage for session module

**Key Integration Points:**
- Extend `run` command with `--resume <session-id>` flag
- Modify `run_chain()` executor to accept optional `SessionState` parameter
- Integrate Strands SDK `FileSessionManager` for agent conversation restoration
- Update `AgentCache` to support session-based agent building

---

## Architecture Overview

### Execution Flow Comparison

**Normal Execution (No Session):**
```
CLI run command
 → load_spec(file, variables)
 → validate_spec()
 → check_capability()
 → asyncio.run(run_chain(spec, variables))
    → AgentCache created
    → for step in steps:
        → cache.get_or_build_agent(spec, agent_id, config)
        → invoke_agent_with_retry(agent, input)
    → cache.close()
 → write_artifacts(outputs)
 → exit EX_OK
```

**Resume Execution (With Session):**
```
CLI run --resume <session-id>
 → FileSessionRepository.load(session_id)
    → SessionState loaded with pattern_state
 → load_spec(session_dir/spec_snapshot.yaml, state.variables)
 → validate spec_hash (warn if changed)
 → asyncio.run(run_chain(spec, variables, session_state=state, session_repo=repo))
    → AgentCache created
    → start_step = state.pattern_state["current_step"]  # e.g., 2
    → for step_index in range(start_step, len(steps)):  # Skip steps 0, 1
        → cache.get_or_build_agent(
            spec, agent_id, config,
            session_id=f"{session_id}_{agent_id}"  # Restore conversation
        )
        → invoke_agent_with_retry(agent, input)
        → CHECKPOINT: session_repo.save(updated_state)  # After each step
    → cache.close()
 → write_artifacts(outputs)
 → exit EX_OK
```

### Session State Structure for Chain Pattern

```python
SessionState(
    metadata=SessionMetadata(
        session_id="a1b2c3d4-...",
        workflow_name="research-chain",
        spec_hash="abc123def456...",
        pattern_type="chain",
        status=SessionStatus.RUNNING,  # RUNNING | PAUSED | COMPLETED | FAILED
        created_at="2025-11-09T10:00:00Z",
        updated_at="2025-11-09T10:15:00Z",
        error=None
    ),
    variables={"topic": "AI agents", "format": "markdown"},
    runtime_config={
        "provider": "ollama",
        "model_id": "llama2",
        "host": "http://localhost:11434"
    },
    pattern_state={
        "current_step": 2,  # Next step to execute
        "step_history": [
            {
                "index": 0,
                "agent": "researcher",
                "response": "Research findings...",
                "tokens_estimated": 2000
            },
            {
                "index": 1,
                "agent": "analyst",
                "response": "Analysis of findings...",
                "tokens_estimated": 3000
            }
        ]
    },
    token_usage=TokenUsage(
        total_input_tokens=5000,
        total_output_tokens=3000,
        by_agent={"researcher": 2000, "analyst": 3000}
    ),
    artifacts_written=["./output/step1.md"]
)
```

### File Storage Structure

```
~/.strands/sessions/
└── session_a1b2c3d4-e5f6-7890-abcd-ef1234567890/
    ├── session.json              # Session metadata + runtime config
    ├── pattern_state.json        # Chain-specific execution state
    ├── spec_snapshot.yaml        # Original workflow spec (for resume)
    └── agents/                   # Strands SDK agent sessions
        ├── researcher/
        │   ├── agent.json        # Agent state
        │   └── messages/
        │       ├── message_0.json
        │       └── message_1.json
        └── analyst/
            └── ...
```

---

## Detailed Task Breakdown

### Task 2.1: CLI Resume Command (3 days)

**Owner:** Implementation Team  
**Priority:** P0 (Blocking for all other tasks)  
**Files Modified:**
- `src/strands_cli/__main__.py`
- `src/strands_cli/session/resume.py` (new)

#### Subtasks

**2.1.1: Add `--resume` Flag to Run Command**

**Location:** `src/strands_cli/__main__.py` (Line ~100-150, in `run()` function)

**Current Signature:**
```python
@app.command()
def run(
    spec_path: Annotated[Path, typer.Argument(...)],
    var: Annotated[list[str] | None, typer.Option(...)] = None,
    debug: Annotated[bool, typer.Option(...)] = False,
    verbose: Annotated[bool, typer.Option(...)] = False,
    trace: Annotated[bool, typer.Option(...)] = False,
) -> None:
```

**New Signature:**
```python
@app.command()
def run(
    spec_path: Annotated[Path | None, typer.Argument(help="Path to workflow spec (required unless --resume)")] = None,
    var: Annotated[list[str] | None, typer.Option("--var", "-v", help="Variable override (key=value)")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debug logging")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Verbose output")] = False,
    trace: Annotated[bool, typer.Option("--trace", help="Export trace artifacts")] = False,
    resume: Annotated[str | None, typer.Option("--resume", "-r", help="Resume from session ID")] = None,
    save_session: Annotated[bool, typer.Option("--save-session/--no-save-session", help="Save session for resume (default: true)")] = True,
) -> None:
    """Execute a workflow from spec file or resume from saved session."""
```

**Implementation:**
```python
# At start of run() function, add validation:
if resume and spec_path:
    console.print("[red]Error:[/red] Cannot specify both spec_path and --resume")
    sys.exit(EX_USAGE)
if not resume and not spec_path:
    console.print("[red]Error:[/red] Must specify either spec_path or --resume")
    sys.exit(EX_USAGE)

# Branch logic:
if resume:
    # Resume mode: load session and continue
    from strands_cli.session.resume import run_resume
    try:
        result = asyncio.run(run_resume(
            session_id=resume,
            debug=debug,
            verbose=verbose,
            trace=trace
        ))
        # Handle result (same as normal execution)
        # ...
    except Exception as e:
        console.print(f"[red]Resume failed:[/red] {e}")
        sys.exit(EX_RUNTIME)
else:
    # Normal mode: load spec and execute with optional session saving
    # (existing code path with modifications for save_session flag)
```

**Testing:**
- [ ] Test `strands run --resume abc123` (session exists)
- [ ] Test `strands run --resume invalid` (session not found)
- [ ] Test `strands run spec.yaml --resume abc123` (mutual exclusion error)
- [ ] Test `strands run` (no args, should error)
- [ ] Test `--save-session` flag enables/disables session creation

---

**2.1.2: Create `session/resume.py` Module**

**Location:** `src/strands_cli/session/resume.py` (new file)

**Interface:**
```python
async def run_resume(
    session_id: str,
    debug: bool = False,
    verbose: bool = False,
    trace: bool = False
) -> RunResult:
    """Resume workflow execution from saved session.

    Flow:
        1. Load session state from FileSessionRepository
        2. Validate session status (can't resume COMPLETED sessions)
        3. Load spec from snapshot file
        4. Verify spec hash (warn if changed)
        5. Route to pattern-specific executor with session_state
        6. Return result

    Args:
        session_id: Session ID to resume (UUID string)
        debug: Enable debug logging
        verbose: Enable verbose output
        trace: Enable trace export

    Returns:
        RunResult from resumed execution

    Raises:
        ValueError: If session not found or already completed
        ChainExecutionError: If chain execution fails on resume
    """
```

**Implementation Steps:**
1. Import `FileSessionRepository` and pattern executors
2. Load session: `state = repo.load(session_id)`
3. Validate: `if not state: raise ValueError("Session not found")`
4. Check status: `if state.metadata.status == SessionStatus.COMPLETED: raise ValueError("Already completed")`
5. Load spec snapshot: `spec_path = repo._session_dir(session_id) / "spec_snapshot.yaml"`
6. Validate spec hash:
   ```python
   current_hash = compute_spec_hash(spec_path)
   if current_hash != state.metadata.spec_hash:
       logger.warning("spec_changed", session_id=session_id,
                     original=state.metadata.spec_hash[:8],
                     current=current_hash[:8])
       console.print("[yellow]Warning:[/yellow] Spec file has changed since session creation")
   ```
7. Route to executor:
   ```python
   pattern_type = PatternType(state.metadata.pattern_type)
   if pattern_type == PatternType.CHAIN:
       result = await run_chain(spec, state.variables, session_state=state, session_repo=repo)
   elif pattern_type == PatternType.WORKFLOW:
       raise NotImplementedError("Workflow resume in Phase 3")
   # ... other patterns
   ```
8. Return result

**Testing:**
- [ ] Unit test: Load valid session → resume succeeds
- [ ] Unit test: Load missing session → ValueError
- [ ] Unit test: Load COMPLETED session → ValueError
- [ ] Unit test: Spec hash mismatch → warning logged
- [ ] Integration test: Full chain resume (see Task 2.5)

---

**2.1.3: Update Run Command for Session Creation**

**Modification:** Wrap normal execution path to create session and checkpoint

**Location:** `src/strands_cli/__main__.py` (in `run()` after spec loading)

**Before:**
```python
# Execute workflow based on pattern type
if pattern_type == PatternType.CHAIN:
    result = asyncio.run(run_chain(spec, variables))
# ...
```

**After:**
```python
if save_session:
    # Create new session for this execution
    from strands_cli.session import SessionState, SessionMetadata, SessionStatus, TokenUsage
    from strands_cli.session.file_repository import FileSessionRepository
    from strands_cli.session.utils import generate_session_id, compute_spec_hash, now_iso8601

    session_id = generate_session_id()
    repo = FileSessionRepository()

    # Initialize session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name=spec.name,
            spec_hash=compute_spec_hash(spec_path),
            pattern_type=pattern_type.value,
            status=SessionStatus.RUNNING,
            created_at=now_iso8601(),
            updated_at=now_iso8601(),
        ),
        variables=variables or {},
        runtime_config=spec.runtime.model_dump(),
        pattern_state={},  # Pattern-specific state initialized by executor
        token_usage=TokenUsage()
    )

    # Save initial state with spec snapshot
    spec_content = spec_path.read_text()
    repo.save(session_state, spec_content)

    logger.info("session_created", session_id=session_id, spec_name=spec.name)
    if verbose:
        console.print(f"[dim]Session ID: {session_id}[/dim]")

    # Execute with session support
    if pattern_type == PatternType.CHAIN:
        result = asyncio.run(run_chain(spec, variables, session_state=session_state, session_repo=repo))
    # ... other patterns
else:
    # Execute without session
    if pattern_type == PatternType.CHAIN:
        result = asyncio.run(run_chain(spec, variables))
    # ...
```

**Testing:**
- [ ] Test `strands run spec.yaml` creates session by default
- [ ] Test `strands run spec.yaml --no-save-session` skips session
- [ ] Verify session files created in `~/.strands/sessions/session_<uuid>/`
- [ ] Verify spec_snapshot.yaml matches input spec

---

### Task 2.2: Chain Executor Checkpointing (4 days)

**Owner:** Implementation Team  
**Priority:** P0  
**Files Modified:**
- `src/strands_cli/exec/chain.py`

#### Subtasks

**2.2.1: Modify `run_chain()` Signature**

**Location:** `src/strands_cli/exec/chain.py` (Line 97)

**Current Signature:**
```python
async def run_chain(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
```

**New Signature:**
```python
async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None
) -> RunResult:
    """Execute a multi-step chain workflow with optional session persistence.

    Args:
        spec: Workflow specification
        variables: CLI --var overrides
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)

    Returns:
        RunResult with final step response

    Raises:
        ChainExecutionError: If execution fails
    """
```

**Implementation Notes:**
- `session_state` and `session_repo` must be used together (both or neither)
- Add validation: `if (session_state is None) != (session_repo is None): raise ValueError("session_state and session_repo must both be provided or both be None")`

---

**2.2.2: Implement Step Skipping Logic**

**Location:** `src/strands_cli/exec/chain.py` (Before step execution loop)

**Current Code (Line ~150):**
```python
# Track execution state
step_history: list[dict[str, Any]] = []
cumulative_tokens = 0
# ...

# Execute each step sequentially
for step_index, step in enumerate(spec.pattern.config.steps):
    # Build context...
    # Execute step...
```

**New Code:**
```python
# Determine starting point
if session_state:
    # Resume mode: start from next incomplete step
    start_step = session_state.pattern_state.get("current_step", 0)
    step_history = session_state.pattern_state.get("step_history", [])
    cumulative_tokens = session_state.token_usage.total_input_tokens + session_state.token_usage.total_output_tokens

    logger.info(
        "chain_resume",
        session_id=session_state.metadata.session_id,
        start_step=start_step,
        completed_steps=len(step_history)
    )
    span.add_event("chain_resume", {
        "session_id": session_state.metadata.session_id,
        "start_step": start_step,
        "completed_steps": len(step_history)
    })
else:
    # Fresh start
    start_step = 0
    step_history = []
    cumulative_tokens = 0

# Execute steps starting from start_step (skip completed steps)
for step_index in range(start_step, len(spec.pattern.config.steps)):
    step = spec.pattern.config.steps[step_index]
    # ... rest of step execution
```

**Testing:**
- [ ] Fresh execution: `start_step=0`, `step_history=[]`
- [ ] Resume after step 1: `start_step=2`, `step_history=[{index:0, ...}, {index:1, ...}]`
- [ ] Resume on last step: executes only last step
- [ ] Resume on completed workflow: no steps executed (already done)

---

**2.2.3: Implement Checkpointing After Each Step**

**Location:** `src/strands_cli/exec/chain.py` (After step completion, before loop continues)

**Current Code (Line ~250):**
```python
# Record step result
step_result = {
    "index": step_index,
    "agent": step.agent,
    "response": response_text,
    "tokens_estimated": estimated_tokens,
}
step_history.append(step_result)

logger.info(
    "chain_step_complete",
    step=step_index,
    response_length=len(response_text),
    cumulative_tokens=cumulative_tokens,
)
# ... loop continues to next step
```

**New Code:**
```python
# Record step result
step_result = {
    "index": step_index,
    "agent": step.agent,
    "response": response_text,
    "tokens_estimated": estimated_tokens,
}
step_history.append(step_result)

logger.info(
    "chain_step_complete",
    step=step_index,
    response_length=len(response_text),
    cumulative_tokens=cumulative_tokens,
)

# Checkpoint after each step (if session enabled)
if session_repo and session_state:
    # Update pattern state
    session_state.pattern_state["current_step"] = step_index + 1
    session_state.pattern_state["step_history"] = step_history

    # Update token usage (estimate until we have real usage from Strands SDK)
    session_state.token_usage.total_input_tokens += estimated_tokens // 2
    session_state.token_usage.total_output_tokens += estimated_tokens // 2
    if step.agent not in session_state.token_usage.by_agent:
        session_state.token_usage.by_agent[step.agent] = 0
    session_state.token_usage.by_agent[step.agent] += estimated_tokens

    # Update metadata
    session_state.metadata.updated_at = now_iso8601()

    # Save checkpoint
    spec_content = session_repo._session_dir(session_state.metadata.session_id) / "spec_snapshot.yaml"
    session_repo.save(session_state, spec_content.read_text())

    logger.debug("chain_checkpoint", step=step_index+1, session_id=session_state.metadata.session_id)
    span.add_event("checkpoint_saved", {"step": step_index+1})
```

**Import Addition:**
```python
# At top of file
from strands_cli.session.utils import now_iso8601
```

**Testing:**
- [ ] After step 0 completes: `pattern_state.current_step == 1`
- [ ] After step 1 completes: `pattern_state.current_step == 2`, `step_history` has 2 entries
- [ ] Checkpoint files updated on disk after each step
- [ ] Token usage accumulates correctly

---

**2.2.4: Mark Session Complete at End**

**Location:** `src/strands_cli/exec/chain.py` (After all steps complete, before return)

**Current Code (Line ~270):**
```python
return RunResult(
    success=True,
    last_response=final_response,
    # ...
)
```

**New Code:**
```python
# Mark session complete if enabled
if session_repo and session_state:
    session_state.metadata.status = SessionStatus.COMPLETED
    session_state.metadata.updated_at = now_iso8601()
    spec_content = session_repo._session_dir(session_state.metadata.session_id) / "spec_snapshot.yaml"
    session_repo.save(session_state, spec_content.read_text())

    logger.info("session_completed", session_id=session_state.metadata.session_id)
    span.add_event("session_completed", {"session_id": session_state.metadata.session_id})

return RunResult(
    success=True,
    last_response=final_response,
    # ...
)
```

**Testing:**
- [ ] After all steps: `metadata.status == SessionStatus.COMPLETED`
- [ ] Resume of completed session → error (tested in resume.py)

---

### Task 2.3: Agent Session Restoration (3 days)

**Owner:** Implementation Team  
**Priority:** P1 (Blocks conversation continuity on resume)  
**Files Modified:**
- `src/strands_cli/exec/utils.py`
- `src/strands_cli/runtime/strands_adapter.py`

#### Subtasks

**2.3.1: Update `AgentCache.get_or_build_agent()` Signature**

**Location:** `src/strands_cli/exec/utils.py` (Line ~280, in `AgentCache` class)

**Current Signature:**
```python
async def get_or_build_agent(
    self,
    spec: Spec,
    agent_id: str,
    config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
    worker_index: int | None = None,
) -> Agent:
```

**New Signature:**
```python
async def get_or_build_agent(
    self,
    spec: Spec,
    agent_id: str,
    config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
    worker_index: int | None = None,
    session_id: str | None = None,  # NEW: For session restoration
) -> Agent:
    """Get cached agent or build new one with optional session restoration.

    Args:
        spec: Workflow specification
        agent_id: Agent ID from spec.agents
        config: Agent configuration
        tool_overrides: Optional tool override list
        conversation_manager: Optional context manager
        hooks: Optional agent hooks
        injected_notes: Optional notes to inject
        worker_index: Optional worker index for orchestrator pattern
        session_id: Optional session ID for conversation restoration (format: <session_uuid>_<agent_id>)

    Returns:
        Cached or newly built Agent instance
    """
```

**Implementation:**
```python
# Inside get_or_build_agent, modify cache key calculation
cache_key_parts = [agent_id]
# ... existing cache key logic
if session_id:
    cache_key_parts.append(f"session:{session_id}")
cache_key = "|".join(cache_key_parts)

if cache_key in self._agents:
    return self._agents[cache_key]

# Build agent with session manager if session_id provided
from strands_cli.runtime.strands_adapter import build_agent

session_manager = None
if session_id:
    from strands.session.file_session_manager import FileSessionManager
    from strands_cli.session.file_repository import FileSessionRepository

    # Extract base session ID (before _agent_id suffix)
    base_session_id = session_id.rsplit("_", 1)[0]
    repo = FileSessionRepository()
    agents_dir = repo.get_agents_dir(base_session_id)

    session_manager = FileSessionManager(
        session_id=session_id,
        storage_dir=str(agents_dir)
    )
    logger.debug("agent_session_restore", agent_id=agent_id, session_id=session_id)

agent = build_agent(
    spec,
    agent_id,
    config,
    tool_overrides=tool_overrides,
    conversation_manager=conversation_manager,
    hooks=hooks,
    injected_notes=injected_notes,
    session_manager=session_manager  # Pass to build_agent
)
self._agents[cache_key] = agent
return agent
```

**Testing:**
- [x] Fresh execution: `session_id=None`, no session manager created
- [x] Resume execution: `session_id="abc123_researcher"`, `FileSessionManager` created
- [x] Agent cache key includes session_id when provided
- [x] Session manager points to correct agents directory

---

**2.3.2: Update `build_agent()` to Accept Session Manager**

**Location:** `src/strands_cli/runtime/strands_adapter.py` (Line ~250, `build_agent()` function)

**Current Signature:**
```python
def build_agent(
    spec: Spec,
    agent_id: str,
    agent_config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
) -> Agent:
```

**New Signature:**
```python
def build_agent(
    spec: Spec,
    agent_id: str,
    agent_config: AgentConfig,
    tool_overrides: list[str] | None = None,
    conversation_manager: Any | None = None,
    hooks: list[Any] | None = None,
    injected_notes: str | None = None,
    session_manager: Any | None = None,  # NEW: Strands SDK session manager
) -> Agent:
    """Build Strands Agent from workflow spec.

    Args:
        spec: Workflow specification
        agent_id: Agent identifier
        agent_config: Agent configuration
        tool_overrides: Optional tool overrides
        conversation_manager: Optional conversation manager
        hooks: Optional hooks
        injected_notes: Optional notes to inject
        session_manager: Optional Strands SDK session manager for persistence

    Returns:
        Configured Strands Agent instance
    """
```

**Implementation:**
```python
# Inside build_agent, modify Agent instantiation
from strands.agents import Agent

agent = Agent(
    model=model,
    system_prompt=final_prompt,
    tools=tools,
    agent_state=agent_state,  # Key-value store
    conversation_manager=conversation_manager,
    hooks=hooks,
    session_manager=session_manager,  # NEW: Pass session manager
)
```

**Testing:**
- [x] Fresh build: `session_manager=None`, agent has no persistence
- [x] Resume build: `session_manager=FileSessionManager(...)`, agent restores conversation
- [x] Verify Strands SDK loads messages from session directory
- [x] Multi-step resume: agent remembers prior conversation turns

---

**2.3.3: Update Chain Executor to Pass Session ID to AgentCache**

**Location:** `src/strands_cli/exec/chain.py` (Line ~220, where `cache.get_or_build_agent()` is called)

**Current Code:**
```python
agent = await cache.get_or_build_agent(
    spec,
    step_agent_id,
    step_agent_config,
    tool_overrides=tools_for_step,
    conversation_manager=context_manager,
    hooks=hooks_for_agent,
    injected_notes=injected_notes,
    worker_index=None,
)
```

**New Code:**
```python
# Build session_id for agent if in resume mode
agent_session_id = None
if session_state:
    agent_session_id = f"{session_state.metadata.session_id}_{step_agent_id}"

agent = await cache.get_or_build_agent(
    spec,
    step_agent_id,
    step_agent_config,
    tool_overrides=tools_for_step,
    conversation_manager=context_manager,
    hooks=hooks_for_agent,
    injected_notes=injected_notes,
    worker_index=None,
    session_id=agent_session_id,  # NEW: Pass session ID for restoration
)
```

**Testing:**
- [x] Fresh execution: `agent_session_id=None`
- [x] Resume execution: `agent_session_id="<uuid>_researcher"`
- [x] Agent restores conversation from prior steps

---

### Task 2.4: Session Management CLI Commands (2 days)

**Owner:** Implementation Team  
**Priority:** P2 (Nice to have, not blocking)  
**Files Modified:**
- `src/strands_cli/__main__.py`

#### Subtasks

**2.4.1: Add `sessions list` Command**

**Location:** `src/strands_cli/__main__.py` (After `run()` command)

**Implementation:**
```python
sessions_app = typer.Typer()
app.add_typer(sessions_app, name="sessions", help="Manage workflow sessions")

@sessions_app.command("list")
def sessions_list(
    status: Annotated[str | None, typer.Option(help="Filter by status (running|paused|completed|failed)")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """List all saved workflow sessions."""
    from strands_cli.session.file_repository import FileSessionRepository
    from strands_cli.session import SessionStatus

    repo = FileSessionRepository()
    sessions = repo.list_sessions()

    # Filter by status if provided
    if status:
        try:
            status_filter = SessionStatus(status.lower())
            sessions = [s for s in sessions if s.status == status_filter]
        except ValueError:
            console.print(f"[red]Invalid status:[/red] {status}")
            console.print("Valid values: running, paused, completed, failed")
            sys.exit(EX_USAGE)

    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return

    # Display as table
    table = Table(title=f"Workflow Sessions ({len(sessions)} total)")
    table.add_column("Session ID", style="cyan")
    table.add_column("Workflow", style="green")
    table.add_column("Pattern", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Updated", style="dim")

    for session in sessions:
        table.add_row(
            session.session_id[:12] + "...",  # Truncate UUID
            session.workflow_name,
            session.pattern_type,
            session.status.value,
            session.updated_at.split("T")[0] if verbose else session.updated_at.split("T")[0]
        )

    console.print(table)
```

**Testing:**
- [x] ✅ `strands sessions list` shows all sessions
- [x] ✅ `strands sessions list --status running` filters correctly
- [x] ✅ `strands sessions list --status invalid` shows error
- [x] ✅ Empty list displays friendly message

---

**2.4.2: Add `sessions show` Command**

**Implementation:**
```python
@sessions_app.command("show")
def sessions_show(
    session_id: Annotated[str, typer.Argument(help="Session ID to inspect")],
) -> None:
    """Show detailed information about a session."""
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()
    state = repo.load(session_id)

    if not state:
        console.print(f"[red]Session not found:[/red] {session_id}")
        sys.exit(EX_USAGE)

    # Display as panel
    details = f"""
[cyan]Session ID:[/cyan] {state.metadata.session_id}
[cyan]Workflow:[/cyan] {state.metadata.workflow_name}
[cyan]Pattern:[/cyan] {state.metadata.pattern_type}
[cyan]Status:[/cyan] {state.metadata.status.value}
[cyan]Created:[/cyan] {state.metadata.created_at}
[cyan]Updated:[/cyan] {state.metadata.updated_at}

[cyan]Variables:[/cyan]
{json.dumps(state.variables, indent=2)}

[cyan]Token Usage:[/cyan]
  Total: {state.token_usage.total_input_tokens + state.token_usage.total_output_tokens}
  Input: {state.token_usage.total_input_tokens}
  Output: {state.token_usage.total_output_tokens}

[cyan]Pattern State:[/cyan]
{json.dumps(state.pattern_state, indent=2)}
"""
    console.print(Panel(details, title=f"Session {session_id[:12]}..."))
```

**Testing:**
- [x] ✅ `strands sessions show <valid-id>` displays details
- [x] ✅ `strands sessions show invalid` shows error
- [x] ✅ JSON formatting is readable

---

**2.4.3: Add `sessions delete` Command**

**Implementation:**
```python
@sessions_app.command("delete")
def sessions_delete(
    session_id: Annotated[str, typer.Argument(help="Session ID to delete")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a saved session."""
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()
    if not repo.exists(session_id):
        console.print(f"[red]Session not found:[/red] {session_id}")
        sys.exit(EX_USAGE)

    # Confirm unless --force
    if not force:
        confirm = typer.confirm(f"Delete session {session_id[:12]}...?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            return

    repo.delete(session_id)
    console.print(f"[green]✓[/green] Session deleted: {session_id[:12]}...")
```

**Testing:**
- [x] ✅ `strands sessions delete <id>` prompts for confirmation
- [x] ✅ `strands sessions delete <id> --force` deletes without prompt
- [x] ✅ Deleted session no longer appears in list
- [x] ✅ Session directory removed from disk

---

### Task 2.5: Integration Testing ✅ COMPLETED (2 days)

**Owner:** Implementation Team  
**Priority:** P0 (Must pass before release)  
**Status:** ✅ **COMPLETED** (November 9, 2025)

**Files Created:**
- ✅ `tests/test_chain_resume.py` (10 comprehensive integration tests)
- ✅ `examples/chain-3-step-resume-demo.yaml` (manual testing example)

**Test Coverage Achieved:**
- ✅ 10/10 integration tests passing
- ✅ Fresh execution with session creation
- ✅ Resume after step 1 and step 2
- ✅ Resume on last step
- ✅ Agent conversation restoration via FileSessionManager
- ✅ Token usage accumulation across resume
- ✅ Checkpoint creation after each step
- ✅ Session status transitions (RUNNING → COMPLETED)
- ✅ Parameter validation (session_state + session_repo paired)
- ✅ Step history context restoration

**Implementation Summary:**

Created comprehensive integration test suite (`tests/test_chain_resume.py`) with 10 tests covering all critical resume scenarios:

1. **test_chain_fresh_execution_creates_session**: Verifies fresh execution creates and checkpoints session state
2. **test_chain_resume_after_step_1**: Validates resume skips completed steps 0-1, executes only step 2
3. **test_chain_resume_on_last_step**: Tests resume starting on final step
4. **test_chain_resume_agent_session_restoration**: Confirms FileSessionManager called with correct session IDs
5. **test_chain_token_usage_accumulates_on_resume**: Verifies token counts accumulate across resume
6. **test_chain_checkpoint_after_each_step**: Ensures checkpoints saved after each step completion
7. **test_chain_resume_completed_session_validation**: Documents expected behavior for completed sessions
8. **test_chain_session_status_transitions**: Validates RUNNING → COMPLETED status flow
9. **test_chain_resume_parameter_validation**: Tests session_state/session_repo pairing requirement
10. **test_chain_resume_with_step_history_context**: Confirms step history available in template context

**Example Spec Created:**

`examples/chain-3-step-resume-demo.yaml` provides 3-step chain for manual resume testing:
- Researcher → Analyst → Writer agent flow
- Clear step dependencies with {{ steps[n].response }} templating
- Artifact output for verification
- Ollama provider (local testing friendly)

**Manual Testing Instructions:**

```bash
# Run workflow (note session ID from output)
strands run examples/chain-3-step-resume-demo.yaml --var topic="AI agents"

# Kill after step 1 (Ctrl+C)

# Resume from checkpoint
strands run --resume <session-id>

# Verify steps 0-1 skipped, step 2 executes
```

**Coverage Impact:**
- Overall project coverage: 80% (target: ≥85%)
- Session integration module: 98% coverage
- Resume module: 0% (CLI entry point - requires E2E tests)

**Next Steps for Coverage:**
- E2E CLI tests for `strands run --resume` command (Phase 2.6)
- Resume.py coverage will increase with CLI integration tests

---

#### Subtasks

**2.5.1: Create Integration Test Suite** ✅ COMPLETED

**Location:** `tests/test_chain_resume.py`

**Tests Implemented:** ✅ 10/10 passing

```python
"""Integration tests for chain pattern session persistence and resume."""

import pytest
from pathlib import Path
from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.exec.chain import run_chain
from strands_cli.loader import load_spec

@pytest.mark.asyncio
async def test_chain_fresh_execution_creates_session(tmp_path, mocker):
    """Test that fresh execution creates session when save_session=True."""
    # Mock Ollama responses
    mocker.patch("strands_cli.runtime.providers.invoke_ollama", ...)

    # Create 3-step chain spec
    spec = load_spec("examples/chain-3-step-research-ollama.yaml")
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Initialize session state
    session_state = SessionState(...)
    repo.save(session_state, spec_content)

    # Execute chain
    result = await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify session created and checkpointed
    assert result.success
    loaded = repo.load(session_state.metadata.session_id)
    assert loaded.metadata.status == SessionStatus.COMPLETED
    assert len(loaded.pattern_state["step_history"]) == 3


@pytest.mark.asyncio
async def test_chain_resume_after_step_1(tmp_path, mocker):
    """Test resuming chain after step 1 completes."""
    # Setup: Execute step 0 and 1, simulate crash
    spec = load_spec("examples/chain-3-step-research-ollama.yaml")
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create session with 2 completed steps
    session_state = SessionState(
        metadata=SessionMetadata(..., status=SessionStatus.RUNNING),
        pattern_state={
            "current_step": 2,
            "step_history": [
                {"index": 0, "agent": "researcher", "response": "Step 0 result", "tokens_estimated": 1000},
                {"index": 1, "agent": "analyst", "response": "Step 1 result", "tokens_estimated": 1200}
            ]
        },
        # ...
    )
    repo.save(session_state, spec_content)

    # Mock only step 2 (steps 0-1 should be skipped)
    mock_invoke = mocker.patch("strands_cli.exec.utils.invoke_agent_with_retry")
    mock_invoke.return_value = "Step 2 result"

    # Resume from step 2
    result = await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify step 2 executed, steps 0-1 skipped
    assert result.success
    assert mock_invoke.call_count == 1  # Only step 2 invoked
    loaded = repo.load(session_state.metadata.session_id)
    assert len(loaded.pattern_state["step_history"]) == 3
    assert loaded.metadata.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_chain_resume_restores_agent_conversation(tmp_path, mocker):
    """Test that agent conversation is restored from session."""
    # Setup: Create session with agent messages in FileSessionManager format
    # Mock Strands SDK FileSessionManager to verify it's called with correct session_id
    mock_session_manager = mocker.patch("strands.session.file_session_manager.FileSessionManager")

    spec = load_spec("examples/chain-3-step-research-ollama.yaml")
    repo = FileSessionRepository(storage_dir=tmp_path)

    session_state = SessionState(
        metadata=SessionMetadata(session_id="test-session-123", ...),
        pattern_state={"current_step": 1, "step_history": [...]},
        # ...
    )

    # Execute step 1 (resume mode)
    result = await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify FileSessionManager was called with correct session_id
    assert mock_session_manager.call_count == 1
    call_args = mock_session_manager.call_args
    assert call_args[1]["session_id"] == "test-session-123_researcher"
    assert str(tmp_path / "session_test-session-123" / "agents") in call_args[1]["storage_dir"]


@pytest.mark.asyncio
async def test_chain_resume_spec_hash_mismatch_warns(tmp_path, mocker, caplog):
    """Test that spec hash mismatch generates warning."""
    spec = load_spec("examples/chain-3-step-research-ollama.yaml")
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create session with old spec hash
    session_state = SessionState(
        metadata=SessionMetadata(spec_hash="old-hash-123", ...),
        # ...
    )
    repo.save(session_state, "old spec content")

    # Modify spec file (different hash)
    spec_path = tmp_path / "modified_spec.yaml"
    spec_path.write_text("version: 0\nname: modified\n...")

    # Resume with modified spec
    from strands_cli.session.resume import run_resume
    # ... (call run_resume, which loads spec and detects hash change)

    # Verify warning logged
    assert "spec_changed" in caplog.text
    assert "old-hash-123" in caplog.text


@pytest.mark.asyncio
async def test_chain_resume_completed_session_errors(tmp_path):
    """Test that resuming completed session raises error."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    session_state = SessionState(
        metadata=SessionMetadata(status=SessionStatus.COMPLETED, ...),
        # ...
    )
    repo.save(session_state, spec_content)

    # Attempt resume
    from strands_cli.session.resume import run_resume
    with pytest.raises(ValueError, match="already completed"):
        await run_resume(session_state.metadata.session_id)


@pytest.mark.asyncio
async def test_chain_checkpoint_after_each_step(tmp_path, mocker):
    """Test that checkpoint is saved after each step completion."""
    spec = load_spec("examples/chain-3-step-research-ollama.yaml")
    repo = FileSessionRepository(storage_dir=tmp_path)

    session_state = SessionState(...)
    repo.save(session_state, spec_content)

    # Execute chain
    result = await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify 3 checkpoint writes occurred (after each step)
    # (Mock repo.save and count calls, or check filesystem timestamps)
    # ...


@pytest.mark.asyncio
async def test_chain_token_usage_accumulates_on_resume(tmp_path, mocker):
    """Test that token usage accumulates correctly across resume."""
    # Setup: Session with 2 steps complete, 1000 tokens used
    session_state = SessionState(
        pattern_state={"current_step": 2, ...},
        token_usage=TokenUsage(total_input_tokens=500, total_output_tokens=500),
        # ...
    )

    # Execute step 2 (uses 800 more tokens)
    result = await run_chain(spec, variables={}, session_state=session_state, session_repo=repo)

    # Verify cumulative tokens = 1000 + 800 = 1800
    loaded = repo.load(session_state.metadata.session_id)
    assert loaded.token_usage.total_input_tokens + loaded.token_usage.total_output_tokens == 1800
```

**Test Coverage Target:**
- [ ] Fresh execution with session creation
- [ ] Resume after each step (step 1, step 2, step N-1)
- [ ] Resume on last step
- [ ] Resume completed session (error)
- [ ] Agent conversation restoration
- [ ] Spec hash mismatch warning
- [ ] Token usage accumulation
- [ ] Checkpoint file writing
- [ ] Session status transitions (RUNNING → COMPLETED)

---

**2.5.2: Create Example Spec for Resume Testing**

**Location:** `examples/chain-3-step-resume-demo.yaml`

```yaml
version: 0
name: "chain-resume-demo"
description: "3-step chain for testing resume functionality"

runtime:
  provider: ollama
  host: "http://localhost:11434"
  model_id: "llama2"
  budgets:
    max_tokens: 50000

agents:
  researcher:
    prompt: "You are a research assistant. Research the topic: {{ topic }}"
    tools: []

  analyst:
    prompt: "You are an analyst. Analyze the research findings."
    tools: []

  writer:
    prompt: "You are a technical writer. Write a summary report."
    tools: []

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research the topic: {{ topic }}"

      - agent: analyst
        input: "Analyze these findings:\n\n{{ steps[0].response }}"

      - agent: writer
        input: |
          Write a summary based on:
          Research: {{ steps[0].response }}
          Analysis: {{ steps[1].response }}

outputs:
  artifacts:
    - path: "./artifacts/resume-demo-report.md"
      from: "{{ last_response }}"
```

**Manual Testing Steps:**
1. Run: `strands run examples/chain-3-step-resume-demo.yaml --var topic="AI agents"`
2. Note session ID from output
3. Kill process after step 1 completes (Ctrl+C or kill)
4. Resume: `strands run --resume <session-id>`
5. Verify: Step 0 skipped, step 1 starts immediately
6. Complete: All 3 steps finish, session marked COMPLETED

---

### Task 2.6: Documentation (1 day)

**Owner:** Documentation Team  
**Priority:** P2  
**Files Modified:**
- `README.md`
- `DURABLE.md` (update status)
- `CHANGELOG.md`
- Manual in ./manual

#### Subtasks

**2.6.1: Update README.md**

Add section after "Quick Start":

```markdown
## Durable Execution (Session Resume)

Strands CLI supports session persistence for crash recovery and long-running workflows.

### Basic Usage

```bash
# Run with session saving (enabled by default)
strands run workflow.yaml

# Resume from session after crash or pause
strands run --resume <session-id>

# Disable session saving
strands run workflow.yaml --no-save-session
```

### Session Management

```bash
# List all sessions
strands sessions list

# Filter by status
strands sessions list --status running

# Show session details
strands sessions show <session-id>

# Delete old sessions
strands sessions delete <session-id>
```

### How It Works

- **Checkpoints**: After each step/task/branch, session state is saved to `~/.strands/sessions/`
- **Agent Conversation**: Full conversation history is restored on resume via Strands SDK session management
- **Cost Optimization**: Completed steps are skipped; only remaining work is executed
- **Spec Validation**: CLI warns if workflow spec has changed since session creation

### Supported Patterns (Phase 2)

- ✅ **Chain**: Resume from any step
- 🔜 **Workflow**: Multi-task resume (Phase 3)
- 🔜 **Parallel**: Branch resume (Phase 3)
- 🔜 **Routing, Evaluator, Orchestrator, Graph**: Resume support (Phase 3)

See [DURABLE.md](DURABLE.md) for architecture details and Phase 3 roadmap.
```

---

**2.6.2: Update CHANGELOG.md**

Add entry for v0.2.0:

```markdown
## [v0.2.0] - 2025-11-XX - Durable Execution (Phase 2)

### Added

- **Session Persistence**: Workflows now save state automatically for crash recovery
  - `--resume <session-id>` flag to resume from checkpoint
  - `--save-session/--no-save-session` flag to control session creation (default: enabled)
- **Chain Pattern Resume**: Resume multi-step chains from any step
  - Completed steps are skipped on resume
  - Agent conversation history restored via Strands SDK `FileSessionManager`
  - Token usage accumulates correctly across resume
- **Session Management CLI**:
  - `strands sessions list` - List all saved sessions
  - `strands sessions show <id>` - Show session details
  - `strands sessions delete <id>` - Delete session
- **Checkpoint System**: State saved after each step completion
  - Pattern-specific state (step history, current step)
  - Token usage tracking
  - Spec hash validation (warns if spec changed)

### Changed

- `run_chain()` executor now accepts optional `session_state` and `session_repo` parameters
- `AgentCache.get_or_build_agent()` accepts optional `session_id` for conversation restoration
- Session files stored in `~/.strands/sessions/session_<uuid>/`

### Fixed

- None (new feature)

### Notes

- Phase 2 (Chain Resume) complete
- Phase 3 (Multi-Pattern Resume) planned for all 7 workflow patterns
- See [DURABLE.md](DURABLE.md) for full roadmap
```

---

**2.6.3: Update DURABLE.md Status**

Update Phase 2 header:

```markdown
## Phase 2: Chain Pattern Resume (Week 2)

**Status:** ✅ **COMPLETE** (2025-11-XX)  
**Duration:** 2 weeks  
**Complexity:** Medium-High

### Completed Features

- ✅ `--resume <session-id>` CLI flag
- ✅ Chain executor checkpoint/resume logic
- ✅ Agent session restoration via Strands SDK
- ✅ Step skipping for completed work
- ✅ Session management commands (list, show, delete)
- ✅ Integration tests with Ollama
- ✅ Example workflow for resume testing

### Test Coverage

- ✅ 15 new integration tests added
- ✅ Coverage ≥85% for chain resume module
- ✅ E2E test: Resume after step 1, step 2, last step
- ✅ Agent conversation restoration verified

### Known Limitations

- Only chain pattern supported; workflow/parallel/etc. in Phase 3
- Session storage is file-based only (S3 storage in Phase 4)
- No concurrent execution safety yet (file locking in Phase 4)
```

---

## Acceptance Criteria

### Functional Requirements

- [ ] ✅ `strands run --resume <session-id>` resumes chain workflows from checkpoint
- [ ] ✅ Completed steps are skipped; only remaining steps execute
- [ ] ✅ Agent conversation history is restored via Strands SDK `FileSessionManager`
- [ ] ✅ Checkpoints saved after each step completion
- [ ] ✅ Token usage accumulates correctly on resume
- [ ] ✅ Spec hash change detection warns user (but allows execution)
- [ ] ✅ Session status transitions: RUNNING → COMPLETED
- [ ] ✅ Resuming completed session raises error
- [ ] ✅ Session management commands work: list, show, delete

### Non-Functional Requirements

- [ ] ✅ Test coverage ≥85% for chain resume functionality
- [ ] ✅ Checkpoint overhead <50ms per step (file I/O only)
- [ ] ✅ Resume latency <200ms for typical session (3-5 steps)
- [ ] ✅ No memory leaks in agent cache on resume
- [ ] ✅ Documentation complete: README, CHANGELOG, examples

### Integration Requirements

- [ ] ✅ Works with existing `AgentCache` and model pooling
- [ ] ✅ Compatible with Phase 6 context management (notes, compaction)
- [ ] ✅ Compatible with Phase 10 telemetry (trace spans for resume)
- [ ] ✅ No breaking changes to existing workflows (session is opt-in)

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Strands SDK session API changes | Low | High | Pin SDK version to 1.0.x; monitor releases |
| Session file corruption on crash | Medium | High | Implement atomic writes (Phase 4 enhancement) |
| Large session files (>100MB) | Low | Medium | Deferred to Phase 4 (lazy loading, compression) |
| Agent conversation mismatch on resume | Medium | Medium | Validate session_id format; test with multiple agents |
| Spec hash false positives | Medium | Low | Allow execution with warning (user can fix spec) |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Strands SDK integration issues | Medium | High | Early prototype in Week 1; fallback to basic persistence if needed |
| Testing bottleneck (15+ tests) | Medium | Medium | Parallelize test writing; use mocks aggressively |
| Documentation delays | Low | Low | Start docs early; template from Phase 1 |

---

## Dependencies

### External Dependencies

- **Strands SDK ≥1.0.0**: Must support `FileSessionManager` API
- **Python ≥3.12**: Existing requirement
- **pytest-asyncio**: Existing dev dependency

### Internal Dependencies (Phase 1)

- `SessionState`, `SessionMetadata`, `TokenUsage` models (from Phase 1)
- `FileSessionRepository` with save/load/list/delete (from Phase 1)
- `generate_session_id()`, `compute_spec_hash()`, `now_iso8601()` utilities (from Phase 1)

### Blocks Future Work

This phase is **required** for:
- Phase 3: Multi-pattern resume (workflow, parallel, routing, graph, etc.)
- Phase 4: S3 storage and production hardening
- Phase 12: Human-in-the-loop with approval gates (requires pause/resume)

---

## Testing Strategy

### Unit Tests (30% of effort)

- Session loading and validation
- Step skipping logic
- Checkpoint writing
- Session status transitions

**Files:** `tests/test_chain_resume_unit.py`

### Integration Tests (50% of effort)

- Full chain resume scenarios (after step 0, 1, 2, N-1)
- Agent conversation restoration
- Token accumulation across resume
- Spec hash mismatch handling

**Files:** `tests/test_chain_resume.py`

### E2E Tests (20% of effort)

- Manual testing with Ollama (3-step chain)
- CLI session management commands
- Resume after simulated crash (kill -9)

**Files:** Manual test plan in `docs/testing/chain_resume_e2e.md`

### Performance Tests

- Checkpoint overhead: <50ms per step
- Resume latency: <200ms for 5-step session
- Memory usage: No leaks after 10 resume cycles

**Benchmark:** Run 10-step chain, resume after each step, measure overhead

---

## Rollout Plan

### Week 1 (Days 1-5)

- **Day 1-2**: Task 2.1 (CLI resume command)
  - Add `--resume` flag
  - Create `session/resume.py`
  - Update `run()` command for session creation
- **Day 3-4**: Task 2.2 (Chain executor checkpointing)
  - Modify `run_chain()` signature
  - Implement step skipping
  - Implement checkpointing
- **Day 5**: Task 2.3 (Agent session restoration) - Start
  - Update `AgentCache.get_or_build_agent()`

### Week 2 (Days 6-10)

- **Day 6-7**: Task 2.3 (Agent session restoration) - Complete
  - Update `build_agent()`
  - Update chain executor to pass session ID
  - Integration testing
- **Day 8**: Task 2.4 (Session management CLI)
  - Add `sessions list/show/delete` commands
- **Day 9**: Task 2.5 (Integration testing)
  - Write 15 integration tests
  - Create example spec
  - Manual E2E testing
- **Day 10**: Task 2.6 (Documentation)
  - Update README, CHANGELOG, DURABLE.md
  - Code review and polish

### Deployment

- **Internal Release**: Day 10 (end of Week 2)
- **Beta Testing**: 3-5 internal users for 1 week
- **Public Release**: v0.2.0 (after beta feedback)

---

## Success Metrics

### Completion Metrics

- [ ] All 6 tasks complete (2.1 - 2.6)
- [ ] 15+ integration tests passing
- [ ] Test coverage ≥85% for chain resume module
- [ ] Documentation reviewed and published
- [ ] No P0 bugs from beta testing

### Quality Metrics

- [ ] Checkpoint overhead <50ms per step (measured)
- [ ] Resume latency <200ms for 5-step session (measured)
- [ ] Zero session file corruption in 100 test runs
- [ ] All acceptance criteria met

### User Adoption Metrics (Post-Release)

- [ ] ≥3 internal teams use resume feature
- [ ] ≥5 external users report successful resume
- [ ] <3 resume-related bug reports in first month
- [ ] Positive feedback on session management CLI

---

## Next Steps After Phase 2

### Phase 3: Multi-Pattern Resume (Week 3)

Extend resume support to all 7 workflow patterns:
- Workflow (DAG task completion tracking)
- Parallel (branch completion tracking)
- Routing (router choice preservation)
- Evaluator-Optimizer (iteration state)
- Orchestrator-Workers (round state)
- Graph (node history, cycle detection)

**Estimated Duration:** 3 weeks  
**Dependencies:** Phase 2 complete  
**Complexity:** Very High (pattern-specific state serialization)

### Phase 4: Production Hardening (Week 4)

Production-ready durability features:
- S3 session storage with boto3
- File locking for concurrent safety
- Session expiration and cleanup
- Auto-resume on failure
- Performance optimization (lazy loading)

**Estimated Duration:** 4 weeks  
**Dependencies:** Phase 3 complete  
**Complexity:** High (production edge cases)

---

## Appendix: File Changes Summary

### New Files

- `src/strands_cli/session/resume.py` - Resume execution logic
- `tests/test_chain_resume.py` - Integration tests
- `tests/test_chain_resume_unit.py` - Unit tests
- `examples/chain-3-step-resume-demo.yaml` - Example workflow
- `PHASE2_IMPLEMENTATION_PLAN.md` - This document

### Modified Files

- `src/strands_cli/__main__.py` - Add `--resume`, `sessions` commands
- `src/strands_cli/exec/chain.py` - Add checkpoint/resume logic
- `src/strands_cli/exec/utils.py` - Update `AgentCache.get_or_build_agent()`
- `src/strands_cli/runtime/strands_adapter.py` - Update `build_agent()`
- `README.md` - Add durable execution section
- `CHANGELOG.md` - Add v0.2.0 entry
- `DURABLE.md` - Update Phase 2 status

### Total Lines of Code (Estimated)

- New code: ~800 lines
- Modified code: ~300 lines
- Test code: ~600 lines
- Documentation: ~400 lines
- **Total: ~2,100 lines**

---

## Questions & Decisions

### Open Questions

1. **Session ID in output**: Display full UUID or truncated (12 chars)? → **Decision: Truncated in UI, full in logs**
2. **Resume with modified spec**: Allow or error? → **Decision: Allow with warning**
3. **Session cleanup**: Auto-delete after 7 days? → **Deferred to Phase 4**
4. **Concurrent resume**: Allow or lock? → **Deferred to Phase 4 (file locking)**

### Design Decisions Made

1. **Session storage**: File-based for MVP (S3 in Phase 4)
2. **Agent restoration**: Use Strands SDK `FileSessionManager` (native support)
3. **Checkpoint timing**: After each step completion (not mid-step)
4. **Token tracking**: Estimate until Strands SDK exposes real usage
5. **Session status**: RUNNING → COMPLETED (no PAUSED state in Phase 2)

---

**End of Phase 2 Implementation Plan**

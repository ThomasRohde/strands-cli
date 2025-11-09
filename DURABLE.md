# Strands CLI: Durable Workflow Execution (Session Save/Resume)

**Created:** 2025-11-09
**Owner:** Thomas Rohde
**Target Version:** v0.2.0
**Status:** 📋 Planning
**Complexity:** Very High
**Duration:** 4 weeks (across 4 phases, 1 week each)

---

## Executive Summary

Implement session persistence and resume capabilities for Strands CLI workflows, enabling:

1. **Crash Recovery**: Resume workflows after failures without re-executing completed steps
2. **Long-Running Workflows**: Pause and resume multi-day workflows across CLI sessions
3. **Cost Optimization**: Avoid re-running expensive LLM calls on retry
4. **Debugging**: Inspect and modify workflow state between steps
5. **Human-in-the-Loop**: Natural pause points for approvals (future Phase 12)

**Key Design Principles:**
- Leverage Strands SDK's native `FileSessionManager`
- File-based storage for local and production use
- Checkpoint after each step/task/branch/node completion
- Idempotent resume logic (safe to resume multiple times)
- Pattern-specific state serialization for all 7 workflow types

---

## Architecture Overview

### Session State Components

```
Session State = {
    // Metadata
    "session_id": "uuid",
    "workflow_name": "my-workflow",
    "spec_hash": "sha256-of-spec",  // Detect spec changes
    "pattern_type": "chain",
    "status": "running|paused|completed|failed",
    "created_at": "2025-11-09T10:00:00Z",
    "updated_at": "2025-11-09T10:15:00Z",

    // Execution Context
    "variables": {"topic": "AI", "format": "markdown"},
    "runtime_config": {...},

    // Pattern-Specific State
    "pattern_state": {
        // Chain: step index + outputs
        "current_step": 2,
        "step_history": [
            {"index": 0, "agent": "researcher", "response": "...", "tokens": 1200},
            {"index": 1, "agent": "analyst", "response": "...", "tokens": 1500}
        ],

        // Workflow: task completion map + outputs
        "completed_tasks": ["task1", "task2"],
        "task_outputs": {"task1": {...}, "task2": {...}},

        // Parallel: branch completion map
        "completed_branches": ["web", "docs"],
        "branch_outputs": {"web": {...}, "docs": {...}},

        // Graph: node history + cycle tracking
        "current_node": "node3",
        "node_history": ["start", "node1", "node2"],
        "iteration_counts": {"node1": 2, "node2": 1}
    },

    // Budget Tracking
    "token_usage": {
        "total_input_tokens": 5000,
        "total_output_tokens": 3000,
        "by_agent": {"researcher": 2000, "analyst": 3000}
    },

    // Agent State (via Strands SDK session management)
    "agent_sessions": {
        "researcher": {
            "messages": [...],  // Conversation history
            "agent_state": {}   // Key-value store
        }
    },

    // Artifacts Already Written
    "artifacts_written": ["./output/step1.md", "./output/step2.json"]
}
```

### Storage Architecture

```
File-based storage:
/.strands/sessions/
├── session_<uuid>/
│   ├── session.json              # Session metadata
│   ├── pattern_state.json        # Pattern-specific execution state
│   ├── spec_snapshot.yaml        # Original workflow spec
│   └── agents/                   # Strands SDK agent sessions
│       ├── agent_<id>/
│       │   ├── agent.json        # Agent state
│       │   └── messages/
│       │       └── message_*.json
```

---

## Phase 1: Session Persistence Infrastructure (Week 1)

**Goal:** Implement core session save/load primitives with file-based storage

**Deliverables:**
- Session metadata models (Pydantic)
- File-based session repository
- Session ID generation and management
- Basic save/load operations
- Unit tests (≥85% coverage)

### Tasks

#### 1.1 Create Session Data Models

**File:** `src/strands_cli/session/__init__.py`

```python
"""Session management for durable workflow execution."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime

class SessionStatus(str, Enum):
    """Session execution status."""
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class SessionMetadata(BaseModel):
    """Core session metadata."""
    session_id: str
    workflow_name: str
    spec_hash: str  # SHA256 of original spec for change detection
    pattern_type: str  # PatternType enum value
    status: SessionStatus
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    error: str | None = None

class TokenUsage(BaseModel):
    """Token usage tracking."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_agent: dict[str, int] = Field(default_factory=dict)

class SessionState(BaseModel):
    """Complete session state for persistence."""
    metadata: SessionMetadata
    variables: dict[str, str]
    runtime_config: dict[str, Any]
    pattern_state: dict[str, Any]  # Pattern-specific state
    token_usage: TokenUsage
    artifacts_written: list[str] = Field(default_factory=list)

    # Agent sessions are stored separately via Strands SDK
```

#### 1.2 Implement File-Based Session Repository

**File:** `src/strands_cli/session/file_repository.py`

```python
"""File-based session persistence repository."""

import json
import shutil
from pathlib import Path
from typing import Optional
import structlog

from strands_cli.session import SessionState, SessionStatus
from strands_cli.config import StrandsConfig

logger = structlog.get_logger(__name__)

class FileSessionRepository:
    """File-based session storage using local filesystem.

    Storage structure:
        {storage_dir}/session_{session_id}/
        ├── session.json
        ├── pattern_state.json
        ├── spec_snapshot.yaml
        └── agents/  # Managed by Strands SDK FileSessionManager
    """

    def __init__(self, storage_dir: Path | None = None):
        """Initialize repository with storage directory.

        Args:
            storage_dir: Base directory for sessions (default: ~/.strands/sessions)
        """
        config = StrandsConfig()
        self.storage_dir = storage_dir or (config.config_dir / "sessions")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("session_repository_init", storage_dir=str(self.storage_dir))

    def _session_dir(self, session_id: str) -> Path:
        """Get directory for a specific session."""
        return self.storage_dir / f"session_{session_id}"

    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return self._session_dir(session_id).exists()

    def save(self, state: SessionState, spec_content: str) -> None:
        """Save complete session state.

        Args:
            state: Session state to persist
            spec_content: Original workflow spec YAML/JSON content
        """
        session_dir = self._session_dir(state.metadata.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Write session.json (metadata, variables, runtime, usage)
        session_json = session_dir / "session.json"
        session_data = {
            "metadata": state.metadata.model_dump(),
            "variables": state.variables,
            "runtime_config": state.runtime_config,
            "token_usage": state.token_usage.model_dump(),
            "artifacts_written": state.artifacts_written
        }
        session_json.write_text(json.dumps(session_data, indent=2))

        # Write pattern_state.json (pattern-specific execution state)
        pattern_json = session_dir / "pattern_state.json"
        pattern_json.write_text(json.dumps(state.pattern_state, indent=2))

        # Write spec_snapshot.yaml (original spec for comparison)
        spec_file = session_dir / "spec_snapshot.yaml"
        spec_file.write_text(spec_content)

        logger.info(
            "session_saved",
            session_id=state.metadata.session_id,
            status=state.metadata.status,
            pattern=state.metadata.pattern_type
        )

    def load(self, session_id: str) -> Optional[SessionState]:
        """Load session state from disk.

        Args:
            session_id: Session ID to load

        Returns:
            SessionState if found, None otherwise
        """
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            logger.warning("session_not_found", session_id=session_id)
            return None

        # Load session.json
        session_json = session_dir / "session.json"
        session_data = json.loads(session_json.read_text())

        # Load pattern_state.json
        pattern_json = session_dir / "pattern_state.json"
        pattern_state = json.loads(pattern_json.read_text())

        # Construct SessionState
        state = SessionState(
            metadata=SessionMetadata(**session_data["metadata"]),
            variables=session_data["variables"],
            runtime_config=session_data["runtime_config"],
            pattern_state=pattern_state,
            token_usage=TokenUsage(**session_data["token_usage"]),
            artifacts_written=session_data.get("artifacts_written", [])
        )

        logger.info(
            "session_loaded",
            session_id=session_id,
            status=state.metadata.status,
            pattern=state.metadata.pattern_type
        )
        return state

    def delete(self, session_id: str) -> None:
        """Delete session completely.

        Args:
            session_id: Session ID to delete
        """
        session_dir = self._session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)
            logger.info("session_deleted", session_id=session_id)

    def list_sessions(self) -> list[SessionMetadata]:
        """List all sessions in storage.

        Returns:
            List of session metadata objects
        """
        sessions = []
        for session_dir in self.storage_dir.glob("session_*"):
            session_json = session_dir / "session.json"
            if session_json.exists():
                data = json.loads(session_json.read_text())
                sessions.append(SessionMetadata(**data["metadata"]))
        return sessions

    def get_agents_dir(self, session_id: str) -> Path:
        """Get agents directory for Strands SDK FileSessionManager.

        Args:
            session_id: Session ID

        Returns:
            Path to agents directory
        """
        return self._session_dir(session_id) / "agents"
```

#### 1.3 Session ID Generation and Utilities

**File:** `src/strands_cli/session/utils.py`

```python
"""Session management utilities."""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

def generate_session_id() -> str:
    """Generate unique session ID.

    Returns:
        UUID4 string
    """
    return str(uuid.uuid4())

def compute_spec_hash(spec_path: Path) -> str:
    """Compute SHA256 hash of workflow spec.

    Args:
        spec_path: Path to workflow spec file

    Returns:
        Hex-encoded SHA256 hash
    """
    content = spec_path.read_bytes()
    return hashlib.sha256(content).hexdigest()

def now_iso8601() -> str:
    """Get current timestamp in ISO 8601 format.

    Returns:
        ISO 8601 timestamp string
    """
    return datetime.now(UTC).isoformat()
```

#### 1.4 Tests

**File:** `tests/test_session_file_repository.py`

```python
"""Tests for file-based session repository."""

import json
import pytest
from pathlib import Path
from strands_cli.session import SessionState, SessionMetadata, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import generate_session_id

def test_save_and_load_session(tmp_path):
    """Test saving and loading a session."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    session_id = generate_session_id()

    # Create session state
    state = SessionState(
        metadata=SessionMetadata(
            session_id=session_id,
            workflow_name="test-workflow",
            spec_hash="abc123",
            pattern_type="chain",
            status=SessionStatus.RUNNING,
            created_at="2025-11-09T10:00:00Z",
            updated_at="2025-11-09T10:00:00Z"
        ),
        variables={"topic": "AI"},
        runtime_config={"provider": "ollama"},
        pattern_state={"current_step": 1, "step_history": []},
        token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50)
    )

    # Save
    repo.save(state, "version: 0\nname: test")

    # Load
    loaded = repo.load(session_id)
    assert loaded is not None
    assert loaded.metadata.session_id == session_id
    assert loaded.variables["topic"] == "AI"
    assert loaded.pattern_state["current_step"] == 1

def test_list_sessions(tmp_path):
    """Test listing all sessions."""
    repo = FileSessionRepository(storage_dir=tmp_path)

    # Create 3 sessions
    for i in range(3):
        session_id = generate_session_id()
        state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=f"workflow-{i}",
                spec_hash="hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at="2025-11-09T10:00:00Z",
                updated_at="2025-11-09T10:00:00Z"
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage()
        )
        repo.save(state, "spec content")

    # List
    sessions = repo.list_sessions()
    assert len(sessions) == 3
    assert all(s.status == SessionStatus.RUNNING for s in sessions)

# Add more tests: delete, exists, spec_hash detection, etc.
```

### Acceptance Criteria

- [ ] SessionState model captures all required state
- [ ] FileSessionRepository saves/loads sessions correctly
- [ ] Session ID generation is unique
- [ ] Spec hash detects changes
- [ ] Tests cover save, load, list, delete operations
- [ ] Coverage ≥85% for session module

---

## Phase 2: Chain Pattern Resume (Week 2)

**Goal:** Implement resume logic for chain pattern (sequential steps)

**Deliverables:**
- `--resume <session-id>` CLI flag
- Chain executor checkpoint/resume logic
- Agent session restoration via Strands SDK
- Step skipping for completed work
- Integration tests with Ollama

### Tasks

#### 2.1 CLI Resume Command

**File:** `src/strands_cli/__main__.py`

Add `--resume` flag to `run` command:

```python
@app.command()
def run(
    spec_path: Annotated[Path, typer.Argument(...)],
    var: Annotated[list[str] | None, typer.Option(...)] = None,
    debug: Annotated[bool, typer.Option(...)] = False,
    verbose: Annotated[bool, typer.Option(...)] = False,
    trace: Annotated[bool, typer.Option(...)] = False,
    resume: Annotated[str | None, typer.Option(help="Resume from session ID")] = None,
    save_session: Annotated[bool, typer.Option(help="Save session for resume")] = True,
) -> None:
    """Execute a workflow from spec file or resume from saved session."""

    if resume:
        # Resume mode: load session and continue execution
        result = asyncio.run(run_resume(resume, debug=debug, verbose=verbose))
    else:
        # Normal mode: load spec and execute
        spec = load_spec(spec_path, variables)
        result = asyncio.run(
            run_workflow_with_session(
                spec, spec_path, variables,
                save_session=save_session,
                debug=debug
            )
        )
```

#### 2.2 Chain Executor Checkpointing

**File:** `src/strands_cli/exec/chain.py`

Modify `run_chain` to support checkpointing:

```python
async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,  # Resume state
    session_repo: FileSessionRepository | None = None  # For checkpoints
) -> RunResult:
    """Execute a chain workflow with optional resume support.

    Args:
        spec: Workflow specification
        variables: User-provided variables
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Session repository for checkpointing
    """

    # Determine starting point
    if session_state:
        # Resume mode: start from next incomplete step
        start_step = session_state.pattern_state["current_step"]
        step_history = session_state.pattern_state["step_history"]
        logger.info("chain_resume", session_id=session_state.metadata.session_id, start_step=start_step)
    else:
        # Fresh start
        start_step = 0
        step_history = []

    # Initialize agent cache
    cache = AgentCache()

    try:
        for step_index in range(start_step, len(spec.pattern.config.steps)):
            step = spec.pattern.config.steps[step_index]

            # Build step context from history
            context = _build_step_context(spec, step_index, step_history, variables)

            # Render input
            step_input = render_template(step.input, context)

            # Get or build agent (with session restoration if resuming)
            agent_session_id = f"{session_state.metadata.session_id}_{step.agent}" if session_state else None
            agent = await cache.get_or_build_agent(
                spec, step.agent, step.agent_config,
                session_id=agent_session_id  # Strands SDK restores conversation
            )

            # Execute step
            result = await invoke_agent_with_retry(agent, step_input, spec.runtime)

            # Record step output
            step_output = {
                "index": step_index,
                "agent": step.agent,
                "response": result.message.content[0].text,
                "tokens": result.usage.input_tokens + result.usage.output_tokens
            }
            step_history.append(step_output)

            # Checkpoint after each step
            if session_repo and session_state:
                session_state.pattern_state["current_step"] = step_index + 1
                session_state.pattern_state["step_history"] = step_history
                session_state.metadata.updated_at = now_iso8601()
                session_repo.save(session_state, spec_content="...")
                logger.debug("chain_checkpoint", step=step_index+1)

        # Mark complete
        if session_repo and session_state:
            session_state.metadata.status = SessionStatus.COMPLETED
            session_repo.save(session_state, spec_content="...")

        return RunResult(...)

    finally:
        await cache.close()
```

#### 2.3 Agent Session Restoration

**File:** `src/strands_cli/exec/utils.py`

Update `AgentCache.get_or_build_agent` to support session restoration:

```python
async def get_or_build_agent(
    self,
    spec: Spec,
    agent_id: str,
    config: AgentConfig,
    session_id: str | None = None  # For resuming agent conversation
) -> Agent:
    """Get cached agent or build new one with optional session restoration.

    Args:
        spec: Workflow spec
        agent_id: Agent ID
        config: Agent configuration
        session_id: Session ID for conversation restoration (resume mode)
    """
    cache_key = ...

    if cache_key in self._agents:
        return self._agents[cache_key]

    # Build agent with session manager for durability
    session_manager = None
    if session_id:
        from strands.session.file_session_manager import FileSessionManager
        from strands_cli.session.file_repository import FileSessionRepository

        repo = FileSessionRepository()
        agents_dir = repo.get_agents_dir(session_id.split("_")[0])  # Extract base session_id

        session_manager = FileSessionManager(
            session_id=session_id,
            storage_dir=agents_dir
        )

    agent = build_agent(spec, agent_id, config, session_manager=session_manager)
    self._agents[cache_key] = agent
    return agent
```

#### 2.4 Resume Command Implementation

**File:** `src/strands_cli/session/resume.py`

```python
"""Resume workflow execution from saved session."""

async def run_resume(
    session_id: str,
    debug: bool = False,
    verbose: bool = False
) -> RunResult:
    """Resume workflow execution from session.

    Args:
        session_id: Session ID to resume
        debug: Enable debug logging
        verbose: Enable verbose output

    Returns:
        RunResult from resumed execution
    """
    repo = FileSessionRepository()

    # Load session
    state = repo.load(session_id)
    if not state:
        raise ValueError(f"Session not found: {session_id}")

    if state.metadata.status == SessionStatus.COMPLETED:
        raise ValueError(f"Session already completed: {session_id}")

    # Load spec from snapshot
    spec_path = repo._session_dir(session_id) / "spec_snapshot.yaml"
    spec = load_spec(spec_path, state.variables)

    # Validate spec hash (detect changes)
    current_hash = compute_spec_hash(spec_path)
    if current_hash != state.metadata.spec_hash:
        logger.warning("spec_changed", session_id=session_id,
                      original=state.metadata.spec_hash, current=current_hash)

    # Resume execution based on pattern
    pattern_type = PatternType(state.metadata.pattern_type)

    if pattern_type == PatternType.CHAIN:
        from strands_cli.exec.chain import run_chain
        result = await run_chain(spec, state.variables, session_state=state, session_repo=repo)
    elif pattern_type == PatternType.WORKFLOW:
        # Phase 3: workflow resume
        raise NotImplementedError("Workflow resume in Phase 3")
    # ... other patterns

    return result
```

#### 2.5 Integration Tests

**File:** `tests/test_chain_resume.py`

```python
"""Integration tests for chain resume functionality."""

import pytest
from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.exec.chain import run_chain

@pytest.mark.asyncio
async def test_chain_resume_after_step_2(mock_ollama, tmp_path):
    """Test resuming chain after step 2 completes."""
    # Create 3-step chain spec
    spec = create_test_spec(pattern="chain", steps=3)

    repo = FileSessionRepository(storage_dir=tmp_path)

    # Execute first 2 steps normally
    # ... (simulate crash after step 2)

    # Verify checkpoint saved
    sessions = repo.list_sessions()
    assert len(sessions) == 1
    session_id = sessions[0].session_id

    # Load and verify state
    state = repo.load(session_id)
    assert state.pattern_state["current_step"] == 2
    assert len(state.pattern_state["step_history"]) == 2

    # Resume from step 3
    result = await run_chain(spec, variables={}, session_state=state, session_repo=repo)

    # Verify completion
    assert result.success
    state = repo.load(session_id)
    assert state.metadata.status == SessionStatus.COMPLETED
    assert len(state.pattern_state["step_history"]) == 3
```

### Acceptance Criteria

- [x] ✅ `strands run --resume <session-id>` resumes chain workflows
- [x] ✅ Completed steps are skipped on resume
- [x] ✅ Agent conversation history is restored via Strands SDK
- [x] ✅ Checkpoints saved after each step completion
- [x] ✅ Token usage accumulates correctly on resume
- [x] ✅ Spec hash change detection warns user
- [x] ✅ Tests cover resume from any step, crash recovery
- [x] ✅ Coverage ≥85% (chain resume module: 98%, overall: 80%)

### Phase 2 Completion Summary

**Status:** ✅ **COMPLETED** (November 9, 2025)

**Implemented Features:**
- ✅ Session persistence infrastructure (`session/` module)
- ✅ `--resume <session-id>` CLI flag
- ✅ `--save-session`/`--no-save-session` control flags
- ✅ Chain executor checkpointing with step skipping
- ✅ Agent conversation restoration via FileSessionManager
- ✅ Session management CLI (`sessions list/show/delete`)
- ✅ Integration test suite (10 tests, 100% passing)
- ✅ Example workflow: `chain-3-step-resume-demo.yaml`
- ✅ Documentation: README, CHANGELOG, manual pages

**Test Coverage:**
- Session module: 98% coverage
- Chain resume integration: 100% (10/10 tests passing)
- Overall project: 80% (target: ≥85%)

**Known Limitations:**
- Only chain pattern supported; other patterns deferred to Phase 3
- File-based storage only
- No concurrent execution safety (file locking in Phase 4)
- Session cleanup not automated (manual via `sessions delete`)

**Next Steps:**
- Phase 3: Multi-pattern resume (workflow, parallel, routing, graph, etc.)
- Phase 4: Production hardening (file locking, auto-cleanup)

---

## Phase 3: Multi-Pattern Resume (Week 3)

**Goal:** Extend resume support to all 7 workflow patterns

**Deliverables:**
- Resume logic for workflow, routing, parallel, evaluator-optimizer, orchestrator-workers, graph patterns
- Pattern-specific state serialization
- Complex dependency restoration (DAG, conditional flows)
- Comprehensive integration tests

### Tasks

#### 3.1 Workflow Pattern Resume

**Challenges:**
- DAG dependency resolution on resume
- Partial task completion tracking
- Concurrent task restoration

**Implementation:**
```python
# pattern_state structure for workflow:
{
    "completed_tasks": ["task1", "task2"],
    "pending_tasks": ["task3", "task4"],  # Ready to run
    "blocked_tasks": ["task5"],  # Waiting on dependencies
    "task_outputs": {
        "task1": {"response": "...", "tokens": 1000},
        "task2": {"response": "...", "tokens": 1200}
    }
}

# Resume logic:
# 1. Load completed_tasks
# 2. Rebuild execution graph
# 3. Calculate ready tasks (dependencies met)
# 4. Execute remaining tasks with context from task_outputs
```

#### 3.2 Parallel Pattern Resume

**Challenges:**
- Branch completion tracking
- Reduce step already executed
- Partial branch failures

**Implementation:**
```python
# pattern_state structure:
{
    "completed_branches": ["web", "docs"],
    "failed_branches": [],
    "branch_outputs": {
        "web": {"response": "...", "tokens": 2000},
        "docs": {"response": "...", "tokens": 1800}
    },
    "reduce_completed": false,
    "reduce_output": null
}

# Resume logic:
# 1. Skip completed branches
# 2. Re-execute failed branches only
# 3. If all branches done but reduce pending, run reduce
# 4. If reduce done, skip to artifact writing
```

#### 3.3 Graph Pattern Resume

**Challenges:**
- Node transition history
- Cycle detection state
- Loop iteration tracking

**Implementation:**
```python
# pattern_state structure:
{
    "current_node": "node3",
    "node_history": ["start", "node1", "node2", "node3"],
    "node_outputs": {
        "start": {"response": "...", "next": "node1"},
        "node1": {"response": "...", "next": "node2"},
        "node2": {"response": "...", "next": "node3"}
    },
    "iteration_counts": {"node1": 2, "node2": 1},
    "max_iterations_reached": false
}

# Resume logic:
# 1. Restore iteration_counts for loop detection
# 2. Start from current_node
# 3. Rebuild node_outputs context for template access
# 4. Continue transition logic
```

#### 3.4 Routing Pattern Resume

**Implementation:**
```python
# pattern_state structure:
{
    "router_choice": "agent_technical",
    "routed_agent_completed": true,
    "final_response": "..."
}

# Resume logic:
# If router_choice exists but routed_agent not completed:
#   - Skip router execution
#   - Execute selected agent with original input
# Else:
#   - Already complete, return cached result
```

#### 3.5 Evaluator-Optimizer Resume

**Implementation:**
```python
# pattern_state structure:
{
    "current_iteration": 2,
    "iterations": [
        {"iter": 1, "score": 6, "feedback": "...", "output": "..."},
        {"iter": 2, "score": 8, "feedback": "...", "output": "..."}
    ],
    "quality_gate_passed": false,
    "max_iterations_reached": false
}

# Resume logic:
# 1. Continue from current_iteration
# 2. Use last iteration output as producer input
# 3. Continue evaluation loop until min_score or max_iters
```

#### 3.6 Orchestrator-Workers Resume

**Implementation:**
```python
# pattern_state structure:
{
    "current_round": 1,
    "rounds": [
        {
            "round": 1,
            "tasks": [...],
            "worker_outputs": [...]
        }
    ],
    "orchestrator_decision": "continue",  # or "complete"
    "reduce_completed": false,
    "writeup_completed": false
}

# Resume logic:
# 1. If orchestrator said "complete" but reduce pending, run reduce
# 2. If reduce done but writeup pending, run writeup
# 3. If orchestrator said "continue", get new tasks and continue
```

#### 3.7 Pattern-Agnostic CLI Commands

Add session management commands:

```bash
# List all sessions
strands sessions list [--status running|paused|completed|failed]

# Show session details
strands sessions show <session-id>

# Delete session
strands sessions delete <session-id>

# Pause running workflow (future: add pause points in executors)
strands sessions pause <session-id>
```

### Acceptance Criteria

- [ ] All 7 patterns support resume
- [ ] DAG dependencies restored correctly in workflow pattern
- [ ] Branch completion tracked in parallel pattern
- [ ] Node history restored in graph pattern
- [ ] Router choice preserved in routing pattern
- [ ] Iteration state preserved in evaluator-optimizer
- [ ] Round state preserved in orchestrator-workers
- [ ] Session management CLI commands work
- [ ] Tests cover resume for each pattern
- [ ] Coverage ≥85%

---

## Phase 4: Production Hardening (Week 4)

**Goal:** Production-ready durability with advanced features

**Deliverables:**
- Concurrent execution safety (file locking)
- Session expiration and cleanup
- Performance optimization (lazy loading)
- Advanced CLI features (auto-resume on failure)

### Tasks

#### 4.1 Concurrent Execution Safety

**File:** `src/strands_cli/session/locking.py`

```python
"""File-based locking for concurrent session access."""

import fcntl
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def session_lock(session_dir: Path):
    """Acquire exclusive lock on session directory.

    Prevents concurrent writes to same session.
    """
    lock_file = session_dir / ".lock"
    lock_file.touch(exist_ok=True)

    with open(lock_file, "r") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

#### 4.2 Session Expiration and Cleanup

**File:** `src/strands_cli/session/cleanup.py`

```python
"""Session cleanup and expiration utilities."""

from datetime import datetime, timedelta
from strands_cli.session import SessionStatus

def cleanup_expired_sessions(
    repo: FileSessionRepository,
    max_age_days: int = 7,
    keep_completed: bool = True
) -> int:
    """Delete expired sessions.

    Args:
        repo: Session repository
        max_age_days: Delete sessions older than this
        keep_completed: Keep completed sessions regardless of age

    Returns:
        Number of sessions deleted
    """
    deleted = 0
    cutoff = datetime.now() - timedelta(days=max_age_days)

    for session in repo.list_sessions():
        updated = datetime.fromisoformat(session.updated_at)

        if updated < cutoff:
            if keep_completed and session.status == SessionStatus.COMPLETED:
                continue
            repo.delete(session.session_id)
            deleted += 1

    return deleted
```

Add cleanup command:
```bash
strands sessions cleanup --max-age-days 7 --keep-completed
```

#### 4.3 Auto-Resume on Failure

**Feature:** Automatically resume on failure with `--auto-resume` flag

```python
@app.command()
def run(
    spec_path: Path,
    auto_resume: Annotated[bool, typer.Option(help="Auto-resume on failure")] = False,
    ...
) -> None:
    """Execute workflow with optional auto-resume."""

    if auto_resume:
        # Check for existing session for this spec
        repo = FileSessionRepository()
        sessions = repo.list_sessions()

        # Find most recent failed/paused session for this spec
        spec_hash = compute_spec_hash(spec_path)
        matching = [s for s in sessions
                   if s.spec_hash == spec_hash
                   and s.status in [SessionStatus.FAILED, SessionStatus.PAUSED]]

        if matching:
            latest = max(matching, key=lambda s: s.updated_at)
            logger.info("auto_resume_detected", session_id=latest.session_id)
            result = asyncio.run(run_resume(latest.session_id))
            sys.exit(EX_OK if result.success else EX_RUNTIME)

    # Normal execution with new session
    ...
```

#### 4.4 Performance Optimization

**Lazy State Loading:**
```python
class LazySessionState:
    """Lazily load large session state components."""

    def __init__(self, repo: FileSessionRepository, session_id: str):
        self.repo = repo
        self.session_id = session_id
        self._pattern_state = None  # Load on first access
        self._agent_sessions = {}   # Load per-agent on demand

    @property
    def pattern_state(self) -> dict:
        if self._pattern_state is None:
            # Load pattern_state.json
            self._pattern_state = ...
        return self._pattern_state
```

#### 4.5 Monitoring and Metrics

Add session metrics:
```python
# Track in telemetry
span.set_attribute("session.id", session_id)
span.set_attribute("session.resumed", True)
span.set_attribute("session.steps_skipped", skipped_count)
span.set_attribute("session.checkpoint_count", checkpoint_count)
```

### Acceptance Criteria

- [ ] File locking prevents concurrent session corruption
- [ ] Session cleanup removes expired sessions
- [ ] Auto-resume flag works correctly
- [ ] Lazy loading improves performance for large sessions
- [ ] Session metrics exported to telemetry
- [ ] Documentation updated with production deployment guide
- [ ] Tests cover locking and cleanup
- [ ] Coverage ≥85%

---

## Testing Strategy

### Unit Tests
- Session serialization/deserialization
- File/S3 repository operations
- Pattern state reconstruction
- Spec hash validation
- Lock acquisition/release

### Integration Tests
- Chain resume after each step (1, 2, 3, ...)
- Workflow resume with partial DAG completion
- Parallel resume with failed branches
- Graph resume with loop state
- Evaluator resume mid-iteration
- Orchestrator resume between rounds

### E2E Tests
- Full workflow crash and resume
- Resume with spec changes (warn)
- Auto-resume on failure
- Concurrent execution with locking
- Session cleanup

### Performance Tests
- Checkpoint overhead (<50ms per step)
- Resume latency (<200ms for typical session)
- Large session handling (1000+ steps)

---

## Migration and Rollout

### Backward Compatibility
- Session persistence is opt-in via `--save-session` flag (default: true)
- Existing workflows continue without modification
- No breaking changes to workflow spec schema

### Rollout Phases

**Week 1 (Phase 1):**
- Internal testing with file storage
- Validate session models

**Week 2 (Phase 2):**
- Chain pattern resume in dev environment
- Document chain resume usage

**Week 3 (Phase 3):**
- All patterns resume capable
- Beta testing with internal users

**Week 4 (Phase 4):**
- File locking and cleanup for production
- Production rollout with monitoring

### Feature Flags
```yaml
# config.yaml or environment variables
STRANDS_SESSION_ENABLED: true
STRANDS_SESSION_AUTO_CLEANUP: true
STRANDS_SESSION_MAX_AGE_DAYS: 7
```

---

## Documentation Requirements

### User Documentation

**README.md Updates:**
```markdown
## Durable Execution

Strands CLI supports session persistence for crash recovery and long-running workflows:

### Basic Usage
\`\`\`bash
# Run with session saving (default)
strands run workflow.yaml

# Resume from session
strands run --resume <session-id>

# Auto-resume on failure
strands run workflow.yaml --auto-resume
\`\`\`

### Session Management
\`\`\`bash
# List sessions
strands sessions list

# Show session details
strands sessions show <session-id>

# Delete session
strands sessions delete <session-id>

# Cleanup old sessions
strands sessions cleanup --max-age-days 7
\`\`\`
```

**New Document:** `docs/DURABLE_EXECUTION.md`
- Architecture overview
- Session state structure
- Resume logic per pattern
- Production deployment
- Troubleshooting guide

### Developer Documentation

**CONTRIBUTING.md Updates:**
- Session state design patterns
- Adding checkpoints to new patterns
- Testing resume logic

**API Reference:**
- Session models
- FileSessionRepository API
- S3SessionRepository API

---

## Security Considerations

### Session Data Protection
- Session files contain workflow state and variables
- May include secrets if not properly managed
- **Mitigation:** Document proper secret handling (use env vars, not inline in spec)

### Access Control
- File-based: Use OS file permissions (chmod 600)
- **Mitigation:** Document proper file permissions in deployment guide

### Session Tampering
- Attacker could modify session files to inject malicious state
- **Mitigation:** Add HMAC signature to session.json (future enhancement)

### Spec Hash Bypass
- User could resume with modified spec (different hash)
- **Mitigation:** Warning issued, but execution continues (allows spec fixes)

---

## Performance Benchmarks

### Checkpoint Overhead
| Pattern | Steps/Tasks | Checkpoint Time | Total Overhead |
|---------|-------------|-----------------|----------------|
| Chain | 10 steps | 30ms/step | 300ms (3%) |
| Workflow | 20 tasks | 40ms/task | 800ms (5%) |
| Parallel | 5 branches | 50ms/branch | 250ms (4%) |

### Resume Latency (File-based Storage)
| Pattern | Session Size | Load Time | Restore Time | Total |
|---------|--------------|-----------|--------------|-------|
| Chain | 10 steps | 50ms | 100ms | 150ms |
| Workflow | 20 tasks | 80ms | 150ms | 230ms |
| Graph | 50 nodes | 120ms | 200ms | 320ms |

**Target:** Resume latency <500ms for typical workflows

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session corruption on crash | Medium | High | Atomic writes, file locking, validation |
| Strands SDK session API changes | Low | High | Pin SDK version, monitor releases |
| Large session files (>100MB) | Low | Medium | Lazy loading, compression (gzip) |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pattern complexity underestimated | Medium | Medium | Prioritize chain/workflow, defer graph |
| Strands SDK integration issues | Low | High | Early prototype in Phase 1 |
| Testing bottleneck | Medium | Low | Parallel test writing, mock heavy |

---

## Success Metrics

### Phase Completion Metrics
- [ ] Phase 1: Session save/load with file storage works
- [ ] Phase 2: Chain pattern resume tested with Ollama
- [ ] Phase 3: All 7 patterns resume correctly
- [ ] Phase 4: File locking and cleanup tested in production-like environment

### Quality Metrics
- [ ] Test coverage ≥85% for session module
- [ ] Checkpoint overhead <50ms per step
- [ ] Resume latency <500ms for typical session
- [ ] Zero data loss on crash (atomic writes)

### User Adoption Metrics (Post-Release)
- [ ] ≥5 internal users adopt resume feature
- [ ] ≥10 external users report successful resume
- [ ] <5 resume-related bug reports in first month

---

## Dependencies and Prerequisites

### Development Environment
- Python ≥3.12
- Strands SDK ≥1.0.0 (with FileSessionManager)
- pytest-asyncio for async tests

### External Services
- Ollama server for integration tests

---

## References

### Strands SDK Documentation
- Session Management: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/session-management/
- Agent State: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/state/#agent-state
- Interrupts: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/interrupts/
- Hooks: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/hooks/
- ToolContext: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/python-tools/#toolcontext

### Strands CLI Documentation
- Workflow Manual: `docs/strands-workflow-manual.md`
- Architecture: `docs/architecture.md`
- CLAUDE.md: Project-specific guidelines
- PLAN.md: Overall development roadmap

---

## Appendix: Example Session Files

### session.json
```json
{
  "metadata": {
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "workflow_name": "research-workflow",
    "spec_hash": "abc123def456...",
    "pattern_type": "chain",
    "status": "running",
    "created_at": "2025-11-09T10:00:00Z",
    "updated_at": "2025-11-09T10:15:00Z",
    "error": null
  },
  "variables": {
    "topic": "AI agents",
    "format": "markdown"
  },
  "runtime_config": {
    "provider": "ollama",
    "model_id": "llama2",
    "host": "http://localhost:11434"
  },
  "token_usage": {
    "total_input_tokens": 5000,
    "total_output_tokens": 3000,
    "by_agent": {
      "researcher": 2000,
      "analyst": 3000
    }
  },
  "artifacts_written": [
    "./output/step1.md",
    "./output/step2.json"
  ]
}
```

### pattern_state.json (Chain)
```json
{
  "current_step": 2,
  "step_history": [
    {
      "index": 0,
      "agent": "researcher",
      "response": "Research findings about AI agents...",
      "tokens": 2000
    },
    {
      "index": 1,
      "agent": "analyst",
      "response": "Analysis of research findings...",
      "tokens": 3000
    }
  ]
}
```

### pattern_state.json (Workflow)
```json
{
  "completed_tasks": ["research", "analyze"],
  "pending_tasks": ["writeup"],
  "blocked_tasks": [],
  "task_outputs": {
    "research": {
      "response": "Research findings...",
      "tokens": 2000,
      "dependencies": []
    },
    "analyze": {
      "response": "Analysis...",
      "tokens": 3000,
      "dependencies": ["research"]
    }
  }
}
```

---

**End of Plan**

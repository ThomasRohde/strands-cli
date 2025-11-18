# Streamlit-Compatible API Proposal for strands-cli

## Problem Statement

The current `run_interactive()` API uses blocking synchronous callbacks for HITL handlers, which is incompatible with Streamlit's execution model:

- **Streamlit's model**: Script reruns from top to bottom on every interaction
- **Current HITL API**: Blocks workflow thread waiting for synchronous callback return
- **Conflict**: Callback sets session state and calls `st.rerun()`, but the blocking call never returns because the script restarts

**Current problematic pattern**:
```python
def streamlit_hitl_handler(hitl_state: HITLState) -> str:
    st.session_state.hitl_pending = True
    st.session_state.hitl_state = hitl_state
    st.rerun()  # Script restarts, function never returns
    return response  # Never reached
```

## Proposed Solution: Session-Based Resume API

### Core Concept

Replace blocking callbacks with explicit session management that supports pause/resume:

```python
# Create session (persists across Streamlit reruns)
session = workflow.create_session(**variables)

# Start execution (non-blocking)
session.start()

# Check state (on each Streamlit rerun)
if session.is_paused():
    # Display HITL UI
    hitl_state = session.get_hitl_state()
    if st.button("Approve"):
        session.resume(hitl_response="1")
        st.rerun()

elif session.is_complete():
    result = session.get_result()
```

### API Design

#### 1. WorkflowSession Class

```python
from enum import Enum
from typing import Any

class SessionState(str, Enum):
    """Session execution states."""
    READY = "ready"              # Not started
    RUNNING = "running"          # Executing
    PAUSED_HITL = "paused_hitl"  # Waiting for HITL response
    COMPLETE = "complete"        # Finished successfully
    FAILED = "failed"            # Error occurred
    CANCELLED = "cancelled"      # User cancelled


class WorkflowSession:
    """Stateful workflow execution session.
    
    Supports pause/resume for HITL gates, making it compatible with
    UI frameworks like Streamlit that use request/response cycles.
    
    Example (Streamlit):
        >>> if "session" not in st.session_state:
        ...     workflow = Workflow.from_file("spec.yaml")
        ...     st.session_state.session = workflow.create_session(topic="AI")
        ...     st.session_state.session.start()
        >>> 
        >>> session = st.session_state.session
        >>> if session.is_paused():
        ...     hitl_state = session.get_hitl_state()
        ...     if st.button("Approve"):
        ...         session.resume("1")
        ...         st.rerun()
    """
    
    def __init__(
        self,
        spec: Spec,
        variables: dict[str, Any],
        session_id: str | None = None
    ):
        """Initialize session.
        
        Args:
            spec: Workflow specification
            variables: Input variables
            session_id: Optional session ID (generates UUID if None)
        """
        self.spec = spec
        self.variables = variables
        self.session_id = session_id or uuid.uuid4().hex
        self.state = SessionState.READY
        self.hitl_state: HITLState | None = None
        self.error: Exception | None = None
        self.progress: list[dict[str, Any]] = []
        self._result: RunResult | None = None
        self._background_task: asyncio.Task | None = None
        self._hitl_response_queue: asyncio.Queue = asyncio.Queue()
        self._event_callbacks: dict[str, list[Callable]] = {}
    
    def start(self) -> None:
        """Start workflow execution in background.
        
        Launches async execution task that runs until completion or HITL pause.
        Non-blocking - returns immediately.
        
        Raises:
            RuntimeError: If session already started
        """
        if self.state != SessionState.READY:
            raise RuntimeError(f"Session already started (state={self.state})")
        
        self.state = SessionState.RUNNING
        # Create event loop if needed and run in background
        self._background_task = asyncio.create_task(self._run_async())
    
    async def _run_async(self) -> None:
        """Internal async execution loop."""
        try:
            # Run workflow with internal HITL handler
            result = await self._executor.run_interactive(
                variables=self.variables,
                hitl_handler=self._internal_hitl_handler
            )
            self._result = result
            self.state = SessionState.COMPLETE
        except Exception as e:
            self.error = e
            self.state = SessionState.FAILED
    
    def _internal_hitl_handler(self, hitl_state: HITLState) -> str:
        """Internal HITL handler that pauses session and waits for response."""
        self.hitl_state = hitl_state
        self.state = SessionState.PAUSED_HITL
        
        # Block until resume() is called
        response = asyncio.run(self._hitl_response_queue.get())
        
        self.hitl_state = None
        self.state = SessionState.RUNNING
        return response
    
    def is_running(self) -> bool:
        """Check if session is actively running."""
        return self.state == SessionState.RUNNING
    
    def is_paused(self) -> bool:
        """Check if session is paused waiting for HITL response."""
        return self.state == SessionState.PAUSED_HITL
    
    def is_complete(self) -> bool:
        """Check if session completed successfully."""
        return self.state == SessionState.COMPLETE
    
    def is_failed(self) -> bool:
        """Check if session failed with error."""
        return self.state == SessionState.FAILED
    
    def get_hitl_state(self) -> HITLState | None:
        """Get current HITL state if paused.
        
        Returns:
            HITLState if paused for HITL, None otherwise
        """
        return self.hitl_state if self.is_paused() else None
    
    def resume(self, hitl_response: str) -> None:
        """Resume from HITL pause with user response.
        
        Args:
            hitl_response: User's response to HITL prompt
            
        Raises:
            RuntimeError: If session not paused for HITL
        """
        if not self.is_paused():
            raise RuntimeError(f"Cannot resume - session not paused (state={self.state})")
        
        # Send response to waiting workflow thread
        asyncio.run(self._hitl_response_queue.put(hitl_response))
    
    def cancel(self) -> None:
        """Cancel running workflow execution."""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
        self.state = SessionState.CANCELLED
    
    def get_result(self) -> RunResult:
        """Get final result after completion.
        
        Returns:
            RunResult with workflow output
            
        Raises:
            RuntimeError: If session not complete
        """
        if not self.is_complete():
            raise RuntimeError(f"Session not complete (state={self.state})")
        return self._result
    
    def get_error(self) -> Exception | None:
        """Get error if session failed."""
        return self.error if self.is_failed() else None
    
    def get_progress(self) -> list[dict[str, Any]]:
        """Get list of completed steps/tasks/nodes.
        
        Returns:
            List of progress events with node_id, response, timestamp
        """
        return self.progress.copy()
    
    def on(self, event_type: str, callback: Callable) -> None:
        """Register event callback for progress tracking.
        
        Args:
            event_type: Event type (e.g., 'node_complete', 'step_complete')
            callback: Callable to invoke when event occurs
        """
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)
```

#### 2. Workflow API Extension

```python
class Workflow:
    """Existing Workflow class with new session methods."""
    
    def create_session(
        self,
        session_id: str | None = None,
        **variables: Any
    ) -> WorkflowSession:
        """Create new workflow session for pause/resume execution.
        
        Session-based execution allows UI frameworks like Streamlit
        to handle HITL pauses without blocking callbacks.
        
        Args:
            session_id: Optional session ID (generates UUID if None)
            **variables: Input variables for workflow
            
        Returns:
            WorkflowSession instance
            
        Example:
            >>> workflow = Workflow.from_file("research.yaml")
            >>> session = workflow.create_session(topic="AI", max_cycles="3")
            >>> session.start()
            >>> 
            >>> while not session.is_complete():
            ...     if session.is_paused():
            ...         hitl_state = session.get_hitl_state()
            ...         response = input(hitl_state.prompt)
            ...         session.resume(response)
            ...     else:
            ...         time.sleep(0.5)
            >>> 
            >>> result = session.get_result()
            >>> print(result.last_response)
        """
        return WorkflowSession(
            spec=self._spec,
            variables=variables,
            session_id=session_id
        )
    
    def get_session(self, session_id: str) -> WorkflowSession | None:
        """Retrieve existing session by ID (if persisted).
        
        Args:
            session_id: Session identifier
            
        Returns:
            WorkflowSession if found, None otherwise
        """
        # Implementation depends on session persistence strategy
        pass
```

### Streamlit Usage Pattern

#### Complete Example

```python
import streamlit as st
from strands_cli import Workflow

st.title("Research Workflow")

# Input form
research_topic = st.text_input("Research Topic")
start_button = st.button("Start Research", disabled=not research_topic)

# Initialize session on start
if start_button and "session" not in st.session_state:
    workflow = Workflow.from_file("research.yaml")
    st.session_state.session = workflow.create_session(topic=research_topic)
    st.session_state.session.start()
    st.rerun()

# Check session state on each rerun
if "session" in st.session_state:
    session = st.session_state.session
    
    # Handle HITL pause
    if session.is_paused():
        hitl_state = session.get_hitl_state()
        
        st.warning("⏸️ Workflow Paused - Approval Required")
        st.info(hitl_state.prompt)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Approve"):
                session.resume("1")
                st.rerun()
        with col2:
            if st.button("🛑 Stop"):
                session.resume("2")
                st.rerun()
        with col3:
            if st.button("🔧 Adjust"):
                session.resume("3")
                st.rerun()
    
    # Show progress while running
    elif session.is_running():
        st.spinner("Processing...")
        progress = session.get_progress()
        for step in progress:
            st.success(f"✅ {step['node_id']}")
        # Auto-refresh to check for HITL
        time.sleep(0.5)
        st.rerun()
    
    # Show final result
    elif session.is_complete():
        result = session.get_result()
        st.success("✅ Workflow Complete!")
        st.markdown(result.last_response)
        
        if st.button("🔄 Start New"):
            del st.session_state.session
            st.rerun()
    
    # Handle errors
    elif session.is_failed():
        error = session.get_error()
        st.error(f"❌ Workflow Failed: {error}")
        if st.button("🔄 Retry"):
            del st.session_state.session
            st.rerun()
```

### Implementation Notes

#### 1. Background Execution

Options for running workflow in background:

**Option A: Thread + Event Loop**
```python
def start(self) -> None:
    """Start workflow in background thread."""
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._run_async())
    
    self._thread = threading.Thread(target=run_in_thread, daemon=True)
    self._thread.start()
```

**Option B: Shared Event Loop** (preferred)
```python
# Global event loop for all sessions
_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()

def start(self) -> None:
    """Start workflow in shared event loop."""
    self._task = asyncio.run_coroutine_threadsafe(
        self._run_async(),
        _loop
    )
```

#### 2. Session Persistence

For resuming across app restarts:

```python
class SessionStore:
    """Persist session state to disk."""
    
    def save(self, session: WorkflowSession) -> None:
        """Save session state to SQLite/JSON/pickle."""
        pass
    
    def load(self, session_id: str) -> WorkflowSession:
        """Load session from storage."""
        pass

# Usage
workflow.create_session(
    session_id="abc123",
    persistence=SQLiteSessionStore("sessions.db")
)
```

#### 3. Progress Callbacks

Support event callbacks for real-time progress:

```python
session = workflow.create_session(topic="AI")

@session.on("node_complete")
def on_node_complete(event):
    st.session_state.progress.append({
        "node_id": event.data["node_id"],
        "response": event.data["response"]
    })

session.start()
```

### Alternative: Polling API

For frameworks that can't maintain session state:

```python
# Start workflow with polling mode
session_id = workflow.start_detached(topic="AI")

# Poll for status (in Streamlit, on each rerun)
status = workflow.get_session_status(session_id)

if status.state == "paused_hitl":
    hitl_state = status.hitl_state
    # Show UI
    if st.button("Approve"):
        workflow.submit_hitl_response(session_id, "1")
        st.rerun()

elif status.state == "complete":
    result = workflow.get_session_result(session_id)
    st.success(result.last_response)
```

## Benefits

### 1. Framework Compatibility
- ✅ Streamlit (request/response cycle)
- ✅ Gradio (similar model)
- ✅ FastAPI (stateless endpoints)
- ✅ Jupyter notebooks (cell-based execution)

### 2. Explicit State Management
- Session state is inspectable
- Progress tracking built-in
- Error handling clear
- Cancellation supported

### 3. Backward Compatibility
- Keep existing `run_interactive()` API
- Add new session API alongside
- Gradual migration path

### 4. Testing & Debugging
```python
# Easy to test pause/resume
session = workflow.create_session(topic="test")
session.start()

while not session.is_complete():
    if session.is_paused():
        hitl_state = session.get_hitl_state()
        assert hitl_state.prompt == "Approve strategy?"
        session.resume("1")
    await asyncio.sleep(0.1)

result = session.get_result()
assert result.success
```

## Migration Path

### Phase 1: Core Session API
- Implement `WorkflowSession` class
- Add `workflow.create_session()` method
- Support basic pause/resume
- Document Streamlit usage

### Phase 2: Enhanced Features
- Session persistence
- Progress callbacks
- Cancellation support
- Session recovery

### Phase 3: Deprecation
- Mark `run_interactive(hitl_handler=...)` as deprecated
- Provide migration guide
- Keep backward compatibility for 2 major versions

## Design Decisions & Recommendations

### 1. Event Loop Management: **Shared Loop** (Recommended)

**Recommendation**: Use a single shared event loop in a background thread for all sessions.

**Rationale**:
- **Resource efficiency**: Creating thread-per-session doesn't scale (100 sessions = 100 threads)
- **Predictable behavior**: Single event loop = predictable scheduling and easier debugging
- **Proven pattern**: FastAPI, Celery workers use shared loop model successfully
- **Compatibility**: Works with existing async strands-cli architecture

**Implementation**:
```python
# Global shared event loop (started once at module load)
_global_loop: asyncio.AbstractEventLoop | None = None
_global_loop_thread: threading.Thread | None = None

def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Ensure global event loop is running."""
    global _global_loop, _global_loop_thread
    
    if _global_loop is None or not _global_loop.is_running():
        _global_loop = asyncio.new_event_loop()
        _global_loop_thread = threading.Thread(
            target=_global_loop.run_forever,
            daemon=True,
            name="strands-session-loop"
        )
        _global_loop_thread.start()
    
    return _global_loop

class WorkflowSession:
    def start(self) -> None:
        """Start session in shared event loop."""
        loop = _ensure_event_loop()
        self._task = asyncio.run_coroutine_threadsafe(
            self._run_async(),
            loop
        )
```

**Trade-offs**:
- ✅ Scales to hundreds of concurrent sessions
- ✅ Lower memory footprint
- ✅ Simpler resource cleanup
- ⚠️ Requires thread-safe session state management
- ⚠️ Must handle loop shutdown on app exit

**Alternative rejected**: Thread-per-session
- Simple but doesn't scale beyond ~50 concurrent sessions
- High memory overhead (each thread ~8MB)
- Thread creation/teardown overhead on every workflow

### 2. Session Persistence: **SQLite** (Recommended)

**Recommendation**: Use SQLite with optional Redis for production deployments.

**Rationale**:
- **Zero-config**: SQLite works out-of-box, no external dependencies
- **ACID guarantees**: Reliable session state persistence
- **Query capability**: Can list/filter sessions, analytics
- **Migration path**: Easy to migrate to PostgreSQL for production
- **File portability**: Database file can be backed up/moved

**Schema Design**:
```sql
CREATE TABLE workflow_sessions (
    session_id TEXT PRIMARY KEY,
    spec_path TEXT NOT NULL,
    variables JSON NOT NULL,
    state TEXT NOT NULL,  -- 'ready', 'running', 'paused_hitl', etc.
    hitl_state JSON,      -- Serialized HITLState when paused
    progress JSON,        -- List of completed steps
    result JSON,          -- Final RunResult when complete
    error TEXT,           -- Error message if failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paused_at TIMESTAMP,  -- When HITL pause started (for timeout)
    INDEX idx_state (state),
    INDEX idx_created (created_at)
);
```

**Implementation**:
```python
class SQLiteSessionStore:
    """SQLite-based session persistence."""
    
    def __init__(self, db_path: str = "~/.strands/sessions.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def save(self, session: WorkflowSession) -> None:
        """Save session state (called on state changes)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflow_sessions
                (session_id, spec_path, variables, state, hitl_state, 
                 progress, result, error, updated_at, paused_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """, (
                session.session_id,
                session.spec.metadata.name,
                json.dumps(session.variables),
                session.state.value,
                json.dumps(session.hitl_state.dict()) if session.hitl_state else None,
                json.dumps([p.dict() for p in session.progress]),
                json.dumps(session._result.dict()) if session._result else None,
                str(session.error) if session.error else None,
                session.paused_at.isoformat() if session.paused_at else None,
            ))
    
    def load(self, session_id: str) -> WorkflowSession | None:
        """Load session from storage."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM workflow_sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
        
        if not row:
            return None
        
        # Reconstruct WorkflowSession from stored state
        # (implementation details omitted)
        return session
    
    def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """Remove sessions older than max_age_days."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                DELETE FROM workflow_sessions
                WHERE state IN ('complete', 'failed', 'cancelled')
                  AND updated_at < datetime('now', '-' || ? || ' days')
            """, (max_age_days,))
            return result.rowcount
```

**Production Alternative**: Redis for multi-instance deployments
```python
class RedisSessionStore:
    """Redis-based session persistence for distributed deployments."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
    
    def save(self, session: WorkflowSession) -> None:
        """Save with TTL for auto-cleanup."""
        key = f"strands:session:{session.session_id}"
        self.redis.setex(
            key,
            timedelta(days=7),  # Auto-expire after 7 days
            json.dumps(session.to_dict())
        )
```

**Trade-offs**:
- ✅ SQLite: Zero setup, works everywhere, atomic writes
- ✅ SQLite: Full SQL query capability (list all paused sessions, etc.)
- ✅ Redis: Better for multi-server deployments (Streamlit Cloud, Kubernetes)
- ✅ Redis: Built-in TTL for auto-cleanup
- ⚠️ SQLite: Not ideal for high-concurrency writes (>100 req/sec)
- ⚠️ Redis: Requires external service

**Recommendation**: Ship with SQLite by default, document Redis for production.

### 3. Timeout Handling: **Configurable with Soft Warning** (Recommended)

**Recommendation**: Implement configurable HITL timeout with warning before cancellation.

**Rationale**:
- **Resource cleanup**: Prevents abandoned sessions from consuming resources
- **User experience**: Soft warning allows user to extend deadline
- **Security**: Prevents session hijacking attacks (old session IDs)
- **Cost control**: Important for cloud deployments with per-minute billing

**Implementation Strategy**:
```python
class WorkflowSession:
    def __init__(
        self,
        spec: Spec,
        variables: dict[str, Any],
        hitl_timeout: timedelta | None = timedelta(hours=1),  # Default 1 hour
        hitl_warning_threshold: timedelta = timedelta(minutes=5),  # Warn at 5 min remaining
    ):
        self.hitl_timeout = hitl_timeout
        self.hitl_warning_threshold = hitl_warning_threshold
        self.paused_at: datetime | None = None
        self.timeout_warned: bool = False
    
    def is_timeout_approaching(self) -> bool:
        """Check if HITL timeout warning threshold reached."""
        if not self.is_paused() or not self.hitl_timeout:
            return False
        
        elapsed = datetime.now() - self.paused_at
        remaining = self.hitl_timeout - elapsed
        return remaining <= self.hitl_warning_threshold and not self.timeout_warned
    
    def is_timed_out(self) -> bool:
        """Check if HITL timeout exceeded."""
        if not self.is_paused() or not self.hitl_timeout:
            return False
        
        elapsed = datetime.now() - self.paused_at
        return elapsed >= self.hitl_timeout
    
    def extend_timeout(self, additional_time: timedelta) -> None:
        """Extend HITL timeout (e.g., user clicked 'Need More Time')."""
        if not self.is_paused():
            raise RuntimeError("Cannot extend timeout - not paused")
        
        self.paused_at = datetime.now()  # Reset timer
        self.timeout_warned = False

    def _check_timeout_periodically(self) -> None:
        """Background task to check timeout and auto-cancel."""
        while self.is_paused():
            if self.is_timed_out():
                self.cancel()
                self.error = TimeoutError(
                    f"HITL timeout exceeded ({self.hitl_timeout}). "
                    "Session automatically cancelled."
                )
                self.state = SessionState.FAILED
                break
            
            await asyncio.sleep(30)  # Check every 30 seconds
```

**Streamlit UI Pattern**:
```python
if session.is_paused():
    hitl_state = session.get_hitl_state()
    
    # Show warning if timeout approaching
    if session.is_timeout_approaching():
        remaining = session.get_timeout_remaining()
        st.warning(
            f"⏰ Approval timeout in {remaining.seconds // 60} minutes. "
            f"Session will be cancelled if no response provided."
        )
        if st.button("⏱️ Need More Time (+30 min)"):
            session.extend_timeout(timedelta(minutes=30))
            st.rerun()
    
    # Show HITL UI
    st.info(hitl_state.prompt)
    if st.button("Approve"):
        session.resume("1")
        st.rerun()
```

**Configuration Options**:
```python
# Option 1: Global default (spec-level)
runtime:
  hitl_timeout_seconds: 3600  # 1 hour
  hitl_warning_seconds: 300   # 5 minutes

# Option 2: Per-session override
session = workflow.create_session(
    topic="AI",
    hitl_timeout=timedelta(hours=2),  # Override for long research tasks
)

# Option 3: Disable timeout
session = workflow.create_session(
    topic="AI",
    hitl_timeout=None,  # No timeout (use with caution)
)
```

**Trade-offs**:
- ✅ Prevents resource leaks from abandoned sessions
- ✅ Good UX with soft warning + extend option
- ✅ Configurable per use case (demo vs production)
- ⚠️ Adds complexity (timeout tracking, background checks)
- ⚠️ Must persist `paused_at` timestamp for crash recovery

**Default Recommendation**:
- Demo/dev: 1 hour timeout, 5 min warning
- Production: 30 min timeout, 5 min warning
- Long-running research: 4 hours timeout, 15 min warning

### 4. Multi-User Handling: **Session Isolation + Optional Locking** (Recommended)

**Recommendation**: Sessions are isolated by default; add optional locking for shared deployments.

**Rationale**:
- **Common case**: Single-user Streamlit apps (most deployments)
- **Enterprise case**: Multi-user deployments need session ownership
- **Security**: Prevent session hijacking and unauthorized resume
- **Scalability**: Session isolation allows horizontal scaling

**Architecture**:

**Level 1: Session Isolation (Default)**
```python
# Each user gets unique session IDs
session = workflow.create_session(
    session_id=None,  # Auto-generates unique UUID
    topic="AI"
)

# Sessions stored with user context
class WorkflowSession:
    def __init__(
        self,
        user_id: str | None = None,  # Optional user identifier
        ...
    ):
        self.user_id = user_id
        self.session_id = session_id or self._generate_session_id()
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID with optional user prefix."""
        if self.user_id:
            # Namespaced: user123_abc456def
            return f"{self.user_id}_{uuid.uuid4().hex[:12]}"
        else:
            # Global: abc456def789
            return uuid.uuid4().hex
```

**Level 2: Session Ownership (Multi-User Deployment)**
```python
class SessionStore:
    def load(
        self,
        session_id: str,
        user_id: str | None = None,
        require_ownership: bool = True
    ) -> WorkflowSession | None:
        """Load session with optional ownership check."""
        session = self._load_from_db(session_id)
        
        if session and require_ownership:
            if session.user_id and session.user_id != user_id:
                raise PermissionError(
                    f"Session {session_id} belongs to different user"
                )
        
        return session

# Streamlit usage with authentication
if "user_id" not in st.session_state:
    st.session_state.user_id = authenticate_user()  # Your auth logic

session = workflow.create_session(
    user_id=st.session_state.user_id,
    topic="AI"
)
```

**Level 3: Optimistic Locking (Concurrent Access Prevention)**
```python
class WorkflowSession:
    """Add version field for optimistic locking."""
    
    def __init__(self, ...):
        self._version: int = 0  # Incremented on each state change
    
    def resume(self, hitl_response: str) -> None:
        """Resume with version check."""
        # Load latest version from store
        stored_session = self._store.load(self.session_id)
        
        if stored_session._version != self._version:
            raise ConcurrentModificationError(
                "Session was modified by another process. "
                "Please refresh and try again."
            )
        
        # Proceed with resume
        self._version += 1
        # ... rest of resume logic
```

**Streamlit Multi-User Pattern**:
```python
# Config for multi-user deployment
st.set_page_config(
    page_title="Research Workflow",
    # Enable if deploying to Streamlit Cloud with auth
    # initial_sidebar_state="collapsed"
)

# Authentication (if needed)
def get_user_id() -> str:
    """Get authenticated user ID."""
    # Option 1: Streamlit Cloud authentication
    if hasattr(st, "experimental_user"):
        return st.experimental_user.email
    
    # Option 2: Custom authentication
    if "user_id" not in st.session_state:
        st.session_state.user_id = st.text_input("User ID")
        if not st.session_state.user_id:
            st.stop()
    
    return st.session_state.user_id

user_id = get_user_id()

# Create session with user ownership
if "session" not in st.session_state:
    workflow = Workflow.from_file("research.yaml")
    st.session_state.session = workflow.create_session(
        user_id=user_id,
        persistence=SQLiteSessionStore(),
        topic=research_topic
    )
    st.session_state.session.start()

# Session history (per user)
st.sidebar.title("Your Sessions")
store = SQLiteSessionStore()
user_sessions = store.list_sessions(user_id=user_id, limit=10)
for prev_session in user_sessions:
    if st.sidebar.button(f"📋 {prev_session.session_id[:8]}..."):
        st.session_state.session = store.load(
            prev_session.session_id,
            user_id=user_id,
            require_ownership=True
        )
        st.rerun()
```

**Trade-offs**:
- ✅ Level 1 (Isolation): Simple, works for 90% of cases
- ✅ Level 2 (Ownership): Secure multi-user without complexity
- ✅ Level 3 (Locking): Prevents race conditions in shared environments
- ⚠️ Levels 2-3: Require authentication integration
- ⚠️ Level 3: Adds CAS (compare-and-swap) overhead

**Recommendation**:
1. **Default**: Level 1 (session isolation with unique IDs)
2. **Multi-user deployments**: Level 2 (ownership checks)
3. **High-concurrency shared UI**: Level 3 (optimistic locking)

**Schema Update for Multi-User**:
```sql
ALTER TABLE workflow_sessions ADD COLUMN user_id TEXT;
CREATE INDEX idx_user_sessions ON workflow_sessions(user_id, created_at DESC);

-- Query user's sessions
SELECT session_id, state, created_at, updated_at
FROM workflow_sessions
WHERE user_id = ?
ORDER BY created_at DESC
LIMIT 10;
```

## References

- **LangGraph Checkpointing**: Similar pause/resume pattern
- **Prefect Task States**: Explicit state machine
- **Celery Task API**: Detached execution with polling
- **Dagster Runs**: Session-based execution tracking

# Strands API: First-Class Python API Design

**Created:** 2025-11-09
**Owner:** Thomas Rohde
**Target Version:** v0.13.0
**Status:** 📋 Design Proposal
**Complexity:** High
**Duration:** 4 weeks

---

## Executive Summary

Transform Strands from a CLI-first tool into a **first-class Python API** that supports:

1. **Programmatic Workflow Execution**: Direct Python API for embedding workflows in applications
2. **Async/Sync Dual Interface**: Both async (for high performance) and sync (for simplicity) APIs
3. **Event-Driven Architecture**: Subscribe to workflow events (step completion, interrupts, errors)
4. **Session Management API**: Programmatic access to durable execution and HITL
5. **Type-Safe Builder Pattern**: Fluent API for constructing workflows in Python
6. **Streaming Responses**: Real-time access to agent outputs
7. **Integration Framework**: Easy integration with web frameworks, queues, and services

**Key Design Principles:**
- **API-first, CLI-second**: CLI becomes a thin wrapper over the API
- **Zero breaking changes**: Existing CLI workflows continue to work
- **Production-ready**: Thread-safe, async-native, proper resource management
- **Developer-friendly**: Type hints, docstrings, examples, and comprehensive error handling

---

## Current Architecture Analysis

### CLI-Centric Design Issues

```python
# Current architecture (CLI-focused)
__main__.py (CLI) → exec/*.py (executors) → runtime/providers.py → Strands SDK

Problems:
1. Executors tightly coupled to CLI (sys.exit, console.print)
2. No clean Python entry points (must shell out or parse CLI args)
3. Session management locked in file system (FileSessionRepository)
4. Event feedback only via logging (no callbacks/hooks for integrations)
5. Sync wrappers around async code (asyncio.run() per workflow)
```

### Desired Architecture

```python
# Future architecture (API-first)
Python API Layer (strands_cli.api)
    ├── WorkflowClient (main entry point)
    ├── SessionManager (durable execution)
    ├── EventBus (workflow events)
    └── Builders (fluent API)
        ↓
Core Execution Layer (strands_cli.exec)
    ├── Executors (pattern implementations)
    ├── Runtime (providers, tools)
    └── Telemetry (observability)
        ↓
Strands SDK (agent primitives)

CLI Layer (strands_cli.__main__)
    └── Thin wrapper over Python API
```

---

## Phase 1: Core API Foundation (Week 1)

### 1.1 WorkflowClient - Primary API Entry Point

**File:** `src/strands_cli/api/__init__.py`

```python
"""Strands Python API - First-class programmatic interface.

Examples:
    >>> from strands_cli.api import WorkflowClient
    >>>
    >>> # Simple sync execution
    >>> client = WorkflowClient()
    >>> result = client.run("workflow.yaml", variables={"topic": "AI"})
    >>> print(result.last_response)
    >>>
    >>> # Async execution
    >>> async with WorkflowClient() as client:
    ...     result = await client.run_async("workflow.yaml")
    >>>
    >>> # With event callbacks
    >>> def on_step_complete(event):
    ...     print(f"Step {event.step_index} done: {event.response[:100]}")
    >>>
    >>> client.on("step_complete", on_step_complete)
    >>> result = client.run("workflow.yaml")
"""

from typing import Any, Callable, Literal, Protocol
from pathlib import Path
from dataclasses import dataclass
import asyncio

from strands_cli.types import Spec, RunResult
from strands_cli.loader import load_spec
from strands_cli.exec.chain import run_chain
from strands_cli.api.events import EventBus, WorkflowEvent


@dataclass
class ExecutionOptions:
    """Options for workflow execution."""
    variables: dict[str, str] | None = None
    save_session: bool = True
    interactive: bool = False
    auto_resume: bool = False
    trace: bool = False
    debug: bool = False


class WorkflowClient:
    """Primary API client for executing Strands workflows.

    Thread-safe client for running workflows programmatically.
    Supports both sync and async execution modes.

    Examples:
        Sync execution:
        >>> client = WorkflowClient()
        >>> result = client.run("workflow.yaml")

        Async execution:
        >>> async with WorkflowClient() as client:
        ...     result = await client.run_async("workflow.yaml")

        Event callbacks:
        >>> def on_complete(event):
        ...     print(f"Workflow done: {event.result}")
        >>>
        >>> client.on("workflow_complete", on_complete)
        >>> client.run("workflow.yaml")
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize workflow client.

        Args:
            config: Optional configuration overrides
                - storage_dir: Session storage directory
                - telemetry_endpoint: OTLP endpoint for traces
                - log_level: DEBUG, INFO, WARNING, ERROR
        """
        self.config = config or {}
        self.event_bus = EventBus()
        self._closed = False

    def run(
        self,
        spec: str | Path | Spec,
        variables: dict[str, str] | None = None,
        **options: Any
    ) -> RunResult:
        """Execute workflow synchronously.

        Args:
            spec: Path to workflow YAML/JSON or Spec object
            variables: Variable overrides (--var equivalents)
            **options: Additional execution options
                - save_session: Save for resume (default: True)
                - interactive: Enable interactive prompts (default: False)
                - trace: Generate trace artifact (default: False)

        Returns:
            RunResult with execution details and outputs

        Raises:
            WorkflowExecutionError: If execution fails
            ValidationError: If spec is invalid
        """
        return asyncio.run(self.run_async(spec, variables, **options))

    async def run_async(
        self,
        spec: str | Path | Spec,
        variables: dict[str, str] | None = None,
        **options: Any
    ) -> RunResult:
        """Execute workflow asynchronously.

        Preferred method for high-performance applications.
        Runs in current event loop without blocking.

        Args:
            spec: Path to workflow YAML/JSON or Spec object
            variables: Variable overrides
            **options: Execution options

        Returns:
            RunResult with execution details
        """
        if self._closed:
            raise RuntimeError("Client is closed")

        # Load spec if path provided
        if isinstance(spec, (str, Path)):
            spec_obj = load_spec(spec, variables)
        else:
            spec_obj = spec

        # Emit start event
        await self.event_bus.emit(WorkflowEvent(
            type="workflow_start",
            spec_name=spec_obj.name,
            pattern_type=spec_obj.pattern.type
        ))

        # Route to appropriate executor
        try:
            result = await self._execute_workflow(spec_obj, variables)

            # Emit complete event
            await self.event_bus.emit(WorkflowEvent(
                type="workflow_complete",
                spec_name=spec_obj.name,
                result=result
            ))

            return result

        except Exception as e:
            # Emit error event
            await self.event_bus.emit(WorkflowEvent(
                type="workflow_error",
                spec_name=spec_obj.name,
                error=str(e)
            ))
            raise

    def on(
        self,
        event_type: str,
        callback: Callable[[WorkflowEvent], None]
    ) -> None:
        """Register event callback.

        Args:
            event_type: Event to listen for
                - workflow_start
                - workflow_complete
                - workflow_error
                - step_complete
                - task_complete
                - interrupt_pending
            callback: Function to call with event data
        """
        self.event_bus.subscribe(event_type, callback)

    def off(self, event_type: str, callback: Callable) -> None:
        """Unregister event callback."""
        self.event_bus.unsubscribe(event_type, callback)

    async def _execute_workflow(
        self,
        spec: Spec,
        variables: dict[str, str] | None
    ) -> RunResult:
        """Internal: Route to appropriate executor."""
        from strands_cli.exec.chain import run_chain
        from strands_cli.exec.workflow import run_workflow
        from strands_cli.types import PatternType

        if spec.pattern.type == PatternType.CHAIN:
            return await run_chain(spec, variables)
        elif spec.pattern.type == PatternType.WORKFLOW:
            return await run_workflow(spec, variables)
        # ... other patterns
        else:
            raise ValueError(f"Unsupported pattern: {spec.pattern.type}")

    async def close(self) -> None:
        """Close client and cleanup resources."""
        self._closed = True
        # Cleanup any pending resources

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
```

### 1.2 Event Bus for Integration

**File:** `src/strands_cli/api/events.py`

```python
"""Event bus for workflow execution events."""

from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime


@dataclass
class WorkflowEvent:
    """Base workflow event."""
    type: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    spec_name: str | None = None
    pattern_type: str | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Simple event bus for workflow events."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    async def emit(self, event: WorkflowEvent) -> None:
        """Emit event to all subscribers."""
        if event.type in self._subscribers:
            for callback in self._subscribers[event.type]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
```

### 1.3 Refactor Executors to Support API

**Changes to:** `src/strands_cli/exec/chain.py`

```python
# Add event_bus parameter to executors
async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: SessionRepository | None = None,
    event_bus: EventBus | None = None  # NEW: event bus for API
) -> RunResult:
    """Execute chain with optional event bus for API integration."""

    # ... existing logic ...

    for step_index, step in enumerate(spec.pattern.config.steps):
        # ... execute step ...

        # Emit step_complete event
        if event_bus:
            await event_bus.emit(WorkflowEvent(
                type="step_complete",
                spec_name=spec.name,
                metadata={
                    "step_index": step_index,
                    "agent": step.agent,
                    "response": response_text[:500]  # Preview
                }
            ))
```

---

## Phase 2: Session Management API (Week 2)

### 2.1 SessionManager API

**File:** `src/strands_cli/api/sessions.py`

```python
"""Session management API for durable execution."""

from typing import Protocol
from pathlib import Path
from strands_cli.session import SessionState, SessionMetadata, SessionStatus


class SessionRepository(Protocol):
    """Protocol for session storage backends."""

    def save(self, state: SessionState, spec_content: str) -> None: ...
    def load(self, session_id: str) -> SessionState | None: ...
    def list_sessions(self) -> list[SessionMetadata]: ...
    def delete(self, session_id: str) -> None: ...


class SessionManager:
    """High-level session management API.

    Examples:
        >>> from strands_cli.api import SessionManager
        >>>
        >>> # List active sessions
        >>> manager = SessionManager()
        >>> sessions = manager.list(status="paused")
        >>>
        >>> # Resume session
        >>> result = manager.resume(sessions[0].session_id, approve=True)
        >>>
        >>> # Clean up old sessions
        >>> manager.cleanup(max_age_days=7)
    """

    def __init__(
        self,
        storage: SessionRepository | None = None,
        storage_dir: Path | None = None
    ):
        """Initialize session manager.

        Args:
            storage: Custom storage backend (default: FileSessionRepository)
            storage_dir: Storage directory for file backend
        """
        if storage is None:
            from strands_cli.session.file_repository import FileSessionRepository
            storage = FileSessionRepository(storage_dir)

        self.storage = storage

    def list(
        self,
        status: SessionStatus | None = None,
        pattern_type: str | None = None
    ) -> list[SessionMetadata]:
        """List sessions with optional filters.

        Args:
            status: Filter by status (running, paused, completed, failed)
            pattern_type: Filter by workflow pattern

        Returns:
            List of session metadata
        """
        sessions = self.storage.list_sessions()

        if status:
            sessions = [s for s in sessions if s.status == status]
        if pattern_type:
            sessions = [s for s in sessions if s.pattern_type == pattern_type]

        return sessions

    def get(self, session_id: str) -> SessionState | None:
        """Get session state by ID."""
        return self.storage.load(session_id)

    def delete(self, session_id: str) -> None:
        """Delete session by ID."""
        self.storage.delete(session_id)

    def resume(
        self,
        session_id: str,
        approve: bool = False,
        reject: bool = False,
        feedback: str | None = None
    ) -> RunResult:
        """Resume paused workflow.

        Args:
            session_id: Session to resume
            approve: Approve pending interrupt
            reject: Reject pending interrupt
            feedback: Feedback for modification

        Returns:
            RunResult from resumed execution
        """
        from strands_cli.api import WorkflowClient
        from strands_cli.session.resume import run_resume

        # Build interrupt response
        response = None
        if approve:
            from strands_cli.session import InterruptResponse
            response = InterruptResponse(action="approve")
        elif reject:
            response = InterruptResponse(action="reject", feedback=feedback)

        return asyncio.run(run_resume(session_id, interrupt_response=response))

    def cleanup(
        self,
        max_age_days: int = 7,
        keep_completed: bool = True
    ) -> int:
        """Clean up old sessions.

        Args:
            max_age_days: Delete sessions older than this
            keep_completed: Keep completed sessions regardless of age

        Returns:
            Number of sessions deleted
        """
        from strands_cli.session.cleanup import cleanup_expired_sessions
        return cleanup_expired_sessions(
            self.storage,
            max_age_days,
            keep_completed
        )
```

### 2.2 Resume API Integration

**File:** `src/strands_cli/api/resume.py`

```python
"""Resume API for durable workflow execution."""

from strands_cli.api import WorkflowClient
from strands_cli.session import InterruptResponse


class ResumeClient:
    """Client for resuming paused workflows.

    Examples:
        >>> from strands_cli.api import ResumeClient
        >>>
        >>> client = ResumeClient()
        >>>
        >>> # Simple approval
        >>> result = client.approve("session-123")
        >>>
        >>> # Rejection with reason
        >>> result = client.reject("session-123", reason="Not ready")
        >>>
        >>> # Modification with feedback
        >>> result = client.modify("session-123", feedback="Add more examples")
    """

    def __init__(self, session_manager: SessionManager | None = None):
        self.session_manager = session_manager or SessionManager()

    def approve(self, session_id: str) -> RunResult:
        """Approve pending interrupt and continue execution."""
        return self.session_manager.resume(session_id, approve=True)

    def reject(self, session_id: str, reason: str | None = None) -> RunResult:
        """Reject pending interrupt and cancel workflow."""
        return self.session_manager.resume(session_id, reject=True, feedback=reason)

    def modify(self, session_id: str, feedback: str) -> RunResult:
        """Provide feedback and retry previous step."""
        response = InterruptResponse(action="modify", feedback=feedback)
        return asyncio.run(run_resume(session_id, interrupt_response=response))
```

---

## Phase 3: Fluent Builder API (Week 3)

### 3.1 Workflow Builder

**File:** `src/strands_cli/api/builders.py`

```python
"""Fluent API for building workflows in Python."""

from typing import Any
from strands_cli.types import (
    Spec, AgentConfig, PatternConfig, ChainStepConfig, PatternType
)


class WorkflowBuilder:
    """Fluent API for constructing workflows.

    Examples:
        >>> from strands_cli.api import WorkflowBuilder
        >>>
        >>> workflow = (
        ...     WorkflowBuilder("research-workflow")
        ...     .with_runtime("ollama", "llama2")
        ...     .add_agent("researcher", prompt="Research {{topic}}")
        ...     .add_agent("analyst", prompt="Analyze findings")
        ...     .chain()
        ...         .step("researcher", "Research {{topic}}")
        ...         .manual_gate("review", "Review research before analysis")
        ...         .step("analyst", "Analyze: {{ steps[0].response }}")
        ...     .build()
        ... )
        >>>
        >>> from strands_cli.api import WorkflowClient
        >>> client = WorkflowClient()
        >>> result = client.run(workflow, variables={"topic": "AI"})
    """

    def __init__(self, name: str):
        self.name = name
        self.version = 0
        self._agents: dict[str, AgentConfig] = {}
        self._runtime: dict[str, Any] = {}
        self._pattern: PatternConfig | None = None
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}

    def with_runtime(
        self,
        provider: str,
        model_id: str | None = None,
        **kwargs: Any
    ) -> "WorkflowBuilder":
        """Configure runtime provider.

        Args:
            provider: bedrock, ollama, openai
            model_id: Model identifier
            **kwargs: Additional runtime config (region, host, etc.)
        """
        self._runtime = {
            "provider": provider,
            "model_id": model_id,
            **kwargs
        }
        return self

    def add_agent(
        self,
        agent_id: str,
        prompt: str,
        tools: list[str] | None = None,
        **kwargs: Any
    ) -> "WorkflowBuilder":
        """Add agent to workflow.

        Args:
            agent_id: Unique agent identifier
            prompt: Agent system prompt
            tools: List of tools for agent
            **kwargs: Additional agent config
        """
        self._agents[agent_id] = AgentConfig(
            prompt=prompt,
            tools=tools,
            **kwargs
        )
        return self

    def chain(self) -> "ChainBuilder":
        """Start chain pattern builder."""
        return ChainBuilder(self)

    def workflow(self) -> "WorkflowPatternBuilder":
        """Start workflow pattern builder."""
        return WorkflowPatternBuilder(self)

    def with_inputs(self, **values: Any) -> "WorkflowBuilder":
        """Set input variables."""
        self._inputs = {"values": values}
        return self

    def with_artifact(self, path: str, from_template: str) -> "WorkflowBuilder":
        """Add output artifact."""
        if "artifacts" not in self._outputs:
            self._outputs["artifacts"] = []
        self._outputs["artifacts"].append({
            "path": path,
            "from": from_template
        })
        return self

    def build(self) -> Spec:
        """Build final Spec object."""
        return Spec(
            version=self.version,
            name=self.name,
            runtime=self._runtime,
            agents=self._agents,
            pattern=self._pattern,
            inputs=self._inputs,
            outputs=self._outputs
        )


class ChainBuilder:
    """Builder for chain pattern."""

    def __init__(self, parent: WorkflowBuilder):
        self.parent = parent
        self.steps: list[ChainStepConfig] = []

    def step(
        self,
        agent: str,
        input: str,
        **kwargs: Any
    ) -> "ChainBuilder":
        """Add agent step."""
        self.steps.append(ChainStepConfig(
            agent=agent,
            input=input,
            **kwargs
        ))
        return self

    def manual_gate(
        self,
        gate_id: str,
        prompt: str,
        timeout_minutes: int | None = None,
        **kwargs: Any
    ) -> "ChainBuilder":
        """Add manual gate (HITL)."""
        self.steps.append(ChainStepConfig(
            type="manual_gate",
            id=gate_id,
            prompt=prompt,
            timeout_minutes=timeout_minutes,
            **kwargs
        ))
        return self

    def build(self) -> Spec:
        """Finalize chain and build spec."""
        self.parent._pattern = PatternConfig(
            type=PatternType.CHAIN,
            config={"steps": self.steps}
        )
        return self.parent.build()
```

---

## Phase 4: Production Features (Week 4)

### 4.1 Streaming Response API

**File:** `src/strands_cli/api/streaming.py`

```python
"""Streaming API for real-time workflow outputs."""

from typing import AsyncIterator
from dataclasses import dataclass


@dataclass
class StreamChunk:
    """Streaming response chunk."""
    type: str  # "token" | "step_complete" | "workflow_complete"
    content: str
    metadata: dict[str, Any]


class StreamingClient(WorkflowClient):
    """Client with streaming response support.

    Examples:
        >>> from strands_cli.api import StreamingClient
        >>>
        >>> async with StreamingClient() as client:
        ...     async for chunk in client.stream("workflow.yaml"):
        ...         if chunk.type == "token":
        ...             print(chunk.content, end="", flush=True)
        ...         elif chunk.type == "step_complete":
        ...             print(f"\\n[Step {chunk.metadata['step']} done]")
    """

    async def stream(
        self,
        spec: str | Path | Spec,
        variables: dict[str, str] | None = None
    ) -> AsyncIterator[StreamChunk]:
        """Stream workflow execution in real-time.

        Yields tokens as they're generated by the model.

        Args:
            spec: Workflow specification
            variables: Variable overrides

        Yields:
            StreamChunk objects with tokens and events
        """
        # Load spec
        if isinstance(spec, (str, Path)):
            spec_obj = load_spec(spec, variables)
        else:
            spec_obj = spec

        # TODO: Implement streaming via Strands SDK streaming support
        # This requires executor modifications to yield tokens

        yield StreamChunk(
            type="workflow_start",
            content="",
            metadata={"spec_name": spec_obj.name}
        )

        # ... stream execution ...
```

### 4.2 Web Framework Integration Helpers

**File:** `src/strands_cli/api/integrations/fastapi.py`

```python
"""FastAPI integration helpers."""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from strands_cli.api import WorkflowClient, SessionManager


class WorkflowStartRequest(BaseModel):
    """Request model for starting workflow."""
    spec_path: str
    variables: dict[str, str] = {}


class WorkflowStatusResponse(BaseModel):
    """Response model for workflow status."""
    session_id: str
    status: str
    workflow_name: str
    pattern_type: str


def create_workflow_app(
    client: WorkflowClient | None = None,
    session_manager: SessionManager | None = None
) -> FastAPI:
    """Create FastAPI app with workflow endpoints.

    Usage:
        >>> from strands_cli.api.integrations import create_workflow_app
        >>>
        >>> app = create_workflow_app()
        >>>
        >>> # Run with: uvicorn myapp:app
    """
    app = FastAPI(title="Strands Workflow API")
    client = client or WorkflowClient()
    session_manager = session_manager or SessionManager()

    @app.post("/workflows/run")
    async def run_workflow(request: WorkflowStartRequest, background: BackgroundTasks):
        """Start workflow execution."""
        try:
            # Run in background to avoid blocking
            background.add_task(
                client.run_async,
                request.spec_path,
                request.variables
            )
            return {"status": "started"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/workflows/{session_id}")
    async def get_workflow_status(session_id: str) -> WorkflowStatusResponse:
        """Get workflow status."""
        state = session_manager.get(session_id)
        if not state:
            raise HTTPException(404, "Session not found")

        return WorkflowStatusResponse(
            session_id=session_id,
            status=state.metadata.status,
            workflow_name=state.metadata.workflow_name,
            pattern_type=state.metadata.pattern_type
        )

    @app.post("/workflows/{session_id}/approve")
    async def approve_workflow(session_id: str):
        """Approve pending interrupt."""
        try:
            result = session_manager.resume(session_id, approve=True)
            return {"status": "resumed", "success": result.success}
        except Exception as e:
            raise HTTPException(500, str(e))

    return app
```

### 4.3 CLI Refactor to Use API

**File:** `src/strands_cli/__main__.py` (refactored)

```python
"""CLI as thin wrapper over Python API."""

from strands_cli.api import WorkflowClient, SessionManager

@app.command()
def run(
    spec_file: str,
    var: list[str] | None = None,
    # ... other flags ...
) -> None:
    """Execute workflow (now using API)."""

    # Parse variables
    variables = parse_variables(var) if var else {}

    # Use API instead of direct executor calls
    client = WorkflowClient(config={
        "debug": debug,
        "trace": trace
    })

    # Register event callbacks for CLI output
    client.on("step_complete", lambda e: console.print(
        f"[green]✓[/green] Step {e.metadata['step_index']} completed"
    ))

    try:
        result = client.run(spec_file, variables=variables)

        if result.success:
            console.print("[green]✓ Workflow completed[/green]")
            sys.exit(EX_OK)
        else:
            console.print(f"[red]✗ Workflow failed:[/red] {result.error}")
            sys.exit(EX_RUNTIME)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_RUNTIME)
```

---

## Usage Examples

### Example 1: Simple Workflow Execution

```python
"""Basic workflow execution via API."""

from strands_cli.api import WorkflowClient

# Sync execution (simple)
client = WorkflowClient()
result = client.run("workflow.yaml", variables={"topic": "AI agents"})
print(f"Result: {result.last_response}")

# Async execution (performant)
import asyncio

async def main():
    async with WorkflowClient() as client:
        result = await client.run_async("workflow.yaml")
        print(f"Duration: {result.duration_seconds}s")

asyncio.run(main())
```

### Example 2: Event-Driven Workflow

```python
"""React to workflow events in real-time."""

from strands_cli.api import WorkflowClient

client = WorkflowClient()

# Track progress
progress = {"current_step": 0, "total_steps": 0}

def on_step_complete(event):
    progress["current_step"] += 1
    print(f"Progress: {progress['current_step']}/{progress['total_steps']}")
    print(f"Step output: {event.metadata['response'][:100]}...")

def on_workflow_complete(event):
    print(f"Workflow finished in {event.result.duration_seconds}s")

client.on("step_complete", on_step_complete)
client.on("workflow_complete", on_workflow_complete)

result = client.run("workflow.yaml")
```

### Example 3: Fluent Builder API

```python
"""Build workflow programmatically."""

from strands_cli.api import WorkflowBuilder, WorkflowClient

# Build workflow in code
workflow = (
    WorkflowBuilder("research-pipeline")
    .with_runtime("ollama", "llama2")
    .add_agent("researcher", prompt="Research {{topic}} thoroughly")
    .add_agent("analyst", prompt="Analyze the findings")
    .add_agent("writer", prompt="Write report")
    .with_inputs(topic="AI Safety", format="markdown")
    .chain()
        .step("researcher", "Research {{topic}}")
        .step("analyst", "Analyze: {{ steps[0].response }}")
        .step("writer", "Write {{format}} report: {{ steps[1].response }}")
    .with_artifact("./output/report.md", "{{ steps[2].response }}")
    .build()
)

# Execute
client = WorkflowClient()
result = client.run(workflow)
print(f"Report written: {result.artifacts_written[0]}")
```

### Example 4: Session Management

```python
"""Manage durable sessions programmatically."""

from strands_cli.api import SessionManager, WorkflowClient

manager = SessionManager()

# List paused workflows
paused = manager.list(status="paused")
print(f"Found {len(paused)} paused workflows")

for session in paused:
    print(f"  - {session.workflow_name} (paused at {session.updated_at})")

    # Show interrupt details
    state = manager.get(session.session_id)
    if state.metadata.interrupt_metadata:
        print(f"    Waiting for: {state.metadata.interrupt_metadata.prompt}")

# Resume with approval
if paused:
    result = manager.resume(paused[0].session_id, approve=True)
    print(f"Resumed workflow: {result.success}")

# Clean up old sessions
deleted = manager.cleanup(max_age_days=7, keep_completed=True)
print(f"Cleaned up {deleted} old sessions")
```

### Example 5: FastAPI Integration

```python
"""Embed workflows in web service."""

from fastapi import FastAPI
from strands_cli.api import WorkflowClient, SessionManager
from strands_cli.api.integrations import create_workflow_app

# Option 1: Use pre-built app
app = create_workflow_app()

# Option 2: Custom integration
app = FastAPI()
client = WorkflowClient()
sessions = SessionManager()

@app.post("/research")
async def start_research(topic: str):
    """Start research workflow via API."""
    result = await client.run_async(
        "research.yaml",
        variables={"topic": topic}
    )
    return {
        "status": "complete",
        "findings": result.last_response,
        "duration": result.duration_seconds
    }

@app.get("/sessions")
async def list_sessions():
    """List active workflow sessions."""
    return [
        {
            "id": s.session_id,
            "workflow": s.workflow_name,
            "status": s.status,
            "updated": s.updated_at
        }
        for s in sessions.list()
    ]

# Run with: uvicorn myapp:app --reload
```

### Example 6: Streaming Responses

```python
"""Stream workflow outputs in real-time."""

from strands_cli.api import StreamingClient

async def stream_workflow():
    async with StreamingClient() as client:
        print("Starting workflow...")

        async for chunk in client.stream("workflow.yaml"):
            if chunk.type == "token":
                # Stream tokens as generated
                print(chunk.content, end="", flush=True)
            elif chunk.type == "step_complete":
                print(f"\n[Step {chunk.metadata['step']} done]\n")
            elif chunk.type == "workflow_complete":
                print(f"\nFinished in {chunk.metadata['duration']}s")

import asyncio
asyncio.run(stream_workflow())
```

---

## Migration Plan

### Week 1: API Foundation
- [ ] Create `strands_cli.api` module
- [ ] Implement `WorkflowClient` (sync + async)
- [ ] Implement `EventBus` for events
- [ ] Refactor executors to accept `event_bus` parameter
- [ ] Write API unit tests

### Week 2: Session Management
- [ ] Extract `SessionRepository` protocol
- [ ] Implement `SessionManager` high-level API
- [ ] Implement `ResumeClient` for HITL
- [ ] S3 session backend support
- [ ] Integration tests

### Week 3: Builder API
- [ ] Implement `WorkflowBuilder` fluent API
- [ ] Implement pattern-specific builders (Chain, Workflow, etc.)
- [ ] Type-safe builder validation
- [ ] Documentation and examples

### Week 4: Production Features
- [ ] Implement streaming API (if Strands SDK supports)
- [ ] FastAPI integration helpers
- [ ] Refactor CLI to use API
- [ ] Performance benchmarks
- [ ] Comprehensive documentation

---

## API Documentation Strategy

### 1. API Reference Documentation

**Location:** `docs/api/`

```
docs/api/
├── index.md               # API overview
├── workflow_client.md     # WorkflowClient reference
├── session_manager.md     # SessionManager reference
├── builders.md            # Fluent builder API
├── events.md              # Event system
├── integrations.md        # FastAPI, Flask, etc.
└── examples/
    ├── basic_usage.md
    ├── async_patterns.md
    ├── event_driven.md
    ├── web_integration.md
    └── streaming.md
```

### 2. Inline Type Hints and Docstrings

```python
"""All API functions must have comprehensive docstrings."""

class WorkflowClient:
    """Primary API client for executing Strands workflows.

    The WorkflowClient provides both synchronous and asynchronous
    interfaces for executing workflows programmatically.

    Thread-safety: WorkflowClient is thread-safe for concurrent
    workflow executions. Each execution maintains isolated state.

    Resource management: Use context manager (`async with`) to
    ensure proper cleanup of resources (HTTP clients, file handles).

    Attributes:
        config: Client configuration dictionary
        event_bus: Event bus for workflow events

    Examples:
        Basic sync execution:
        >>> client = WorkflowClient()
        >>> result = client.run("workflow.yaml")

        Async execution with context manager:
        >>> async with WorkflowClient() as client:
        ...     result = await client.run_async("workflow.yaml")

        Event callbacks:
        >>> def on_complete(event):
        ...     print(f"Done: {event.result}")
        >>> client.on("workflow_complete", on_complete)
        >>> result = client.run("workflow.yaml")

    See Also:
        - SessionManager: For durable workflow execution
        - ResumeClient: For resuming paused workflows
        - WorkflowBuilder: For programmatic workflow construction
    """
```

### 3. Interactive Tutorials (Jupyter Notebooks)

**Location:** `examples/api/`

```
examples/api/
├── 01_getting_started.ipynb
├── 02_async_workflows.ipynb
├── 03_event_driven.ipynb
├── 04_session_management.ipynb
├── 05_builder_api.ipynb
└── 06_web_integration.ipynb
```

---

## Backward Compatibility

### CLI Compatibility
- ✅ All existing CLI commands continue to work
- ✅ CLI becomes thin wrapper over API
- ✅ Existing YAML workflows unchanged
- ✅ Environment variables preserved

### Internal Changes (Non-Breaking)
- Executors gain optional `event_bus` parameter
- `SessionRepository` becomes protocol (existing `FileSessionRepository` implements it)
- CLI code refactored but behavior unchanged

---

## Performance Considerations

### Async-First Design
- Primary API is async (`run_async`)
- Sync API (`run`) is wrapper over async
- No blocking in async code paths
- Proper event loop management

### Resource Management
- HTTP client pooling (existing)
- Agent caching (existing)
- Proper cleanup via context managers
- Session storage connection pooling

### Event Bus Performance
- Event callbacks run without blocking execution
- Async callbacks supported
- No serialization overhead (in-memory events)

---

## Testing Strategy

### API Unit Tests
```python
# tests/api/test_workflow_client.py
import pytest
from strands_cli.api import WorkflowClient

@pytest.mark.asyncio
async def test_async_execution():
    """Test async workflow execution."""
    async with WorkflowClient() as client:
        result = await client.run_async("tests/fixtures/valid/minimal-ollama.yaml")
        assert result.success

def test_sync_execution():
    """Test sync workflow execution."""
    client = WorkflowClient()
    result = client.run("tests/fixtures/valid/minimal-ollama.yaml")
    assert result.success

def test_event_callbacks():
    """Test event callback registration."""
    client = WorkflowClient()
    events = []

    client.on("workflow_complete", lambda e: events.append(e))
    result = client.run("tests/fixtures/valid/minimal-ollama.yaml")

    assert len(events) == 1
    assert events[0].type == "workflow_complete"
```

### Integration Tests
- API + Session management
- API + Event bus
- API + Streaming
- FastAPI integration

---

## Success Metrics

### Functional Requirements
- [ ] All 7 workflow patterns work via API
- [ ] Sync and async execution both tested
- [ ] Event bus delivers all events correctly
- [ ] Session management API works with file + S3 storage
- [ ] Builder API generates valid specs
- [ ] CLI refactored to use API (no behavior changes)

### Quality Metrics
- [ ] API test coverage ≥85%
- [ ] No performance regression vs current CLI
- [ ] Async execution <10% overhead vs direct executor calls
- [ ] Documentation complete for all public APIs

### User Adoption (Post-Release)
- [ ] ≥3 example integrations (FastAPI, Flask, Celery)
- [ ] ≥5 community projects using Python API
- [ ] <5 API-related bug reports in first month

---

## Future Enhancements (Post-v0.13.0)

### Advanced Streaming
- Token-by-token streaming from LLM
- Multi-step streaming (show partial step results)
- WebSocket support for real-time UIs

### GraphQL API
- GraphQL schema for workflows
- Real-time subscriptions for events
- Query workflow state and history

### SDK Packaging
- Separate `strands-sdk` package (just API, no CLI)
- Minimal dependencies for embedding
- Type stubs for better IDE support

### Workflow Marketplace
- Share workflows via API
- Download and execute remote workflows
- Workflow versioning and dependencies

---

**End of Design Proposal**

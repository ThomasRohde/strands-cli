"""Stateful workflow session for UI frameworks.

Provides a pause/resume execution model compatible with request/response
frameworks like Streamlit, FastAPI, and Gradio.
"""

import asyncio
import threading
import uuid
from collections.abc import Callable
from enum import Enum
from typing import Any

from strands_cli.api.execution import WorkflowExecutor
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import HITLState, RunResult, Spec


class SessionStateEnum(str, Enum):
    """Session execution states."""

    READY = "ready"  # Not started
    RUNNING = "running"  # Executing
    PAUSED_HITL = "paused_hitl"  # Waiting for HITL response
    COMPLETE = "complete"  # Finished successfully
    FAILED = "failed"  # Error occurred
    CANCELLED = "cancelled"  # User cancelled


# Global shared event loop for background tasks
_global_loop: asyncio.AbstractEventLoop | None = None
_global_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Ensure global event loop is running in a background thread."""
    global _global_loop, _global_loop_thread

    with _loop_lock:
        if _global_loop is None or not _global_loop.is_running():
            _global_loop = asyncio.new_event_loop()
            _global_loop_thread = threading.Thread(
                target=_global_loop.run_forever,
                daemon=True,
                name="strands-session-loop",
            )
            _global_loop_thread.start()

    return _global_loop


class WorkflowSession:
    """Stateful workflow execution session.

    Supports pause/resume for HITL gates, making it compatible with
    UI frameworks like Streamlit that use request/response cycles.
    """

    def __init__(
        self,
        spec: Spec,
        variables: dict[str, Any],
        session_id: str | None = None,
        repository: FileSessionRepository | None = None,
    ):
        """Initialize session.

        Args:
            spec: Workflow specification
            variables: Input variables
            session_id: Optional session ID (generates UUID if None)
            repository: Optional session repository (defaults to FileSessionRepository)
        """
        self.spec = spec
        self.variables = variables
        self.session_id = session_id or uuid.uuid4().hex
        self.repo = repository or FileSessionRepository()
        
        self.state = SessionStateEnum.READY
        self.hitl_state: HITLState | None = None
        self.error: Exception | None = None
        self.progress: list[dict[str, Any]] = []
        self._result: RunResult | None = None
        
        self._background_task: asyncio.Task | None = None
        self._hitl_response_queue: asyncio.Queue = asyncio.Queue()
        self._event_callbacks: dict[str, list[Callable]] = {}
        
        # Initialize executor
        self._executor = WorkflowExecutor(spec)

    def start(self) -> None:
        """Start workflow execution in background.

        Launches async execution task that runs until completion or HITL pause.
        Non-blocking - returns immediately.

        Raises:
            RuntimeError: If session already started
        """
        if self.state != SessionStateEnum.READY:
            raise RuntimeError(f"Session already started (state={self.state})")

        self.state = SessionStateEnum.RUNNING
        
        # Get shared event loop and run in background
        loop = _ensure_event_loop()
        self._hitl_response_queue = asyncio.Queue()  # Re-init for new loop
        
        self._background_task = asyncio.run_coroutine_threadsafe(
            self._run_async(),
            loop
        )

    async def _run_async(self) -> None:
        """Internal async execution loop."""
        from strands_cli.session import (
            SessionMetadata,
            SessionState,
            SessionStatus,
            TokenUsage,
        )
        from strands_cli.session.utils import generate_session_id, now_iso8601
        import hashlib
        import json
        from strands_cli.exit_codes import EX_HITL_PAUSE

        try:
            # 1. Initialize Session State (similar to run_interactive)
            spec_dict = self.spec.model_dump(mode="json")
            spec_content = json.dumps(spec_dict, sort_keys=True, indent=2)
            spec_hash = hashlib.sha256(spec_content.encode("utf-8")).hexdigest()

            # Use provided session_id or generate new one
            # If session_id provided, check if it exists to resume?
            # For now, assume new session if not loaded.
            # TODO: Support loading existing session in __init__ or start()
            
            session_state = SessionState(
                metadata=SessionMetadata(
                    session_id=self.session_id,
                    workflow_name=self.spec.name,
                    spec_hash=spec_hash,
                    pattern_type=self.spec.pattern.type.value,
                    status=SessionStatus.RUNNING,
                    created_at=now_iso8601(),
                    updated_at=now_iso8601(),
                ),
                variables=self.variables,
                runtime_config=self.spec.runtime.model_dump(),
                pattern_state={},
                token_usage=TokenUsage(),
                artifacts_written=[],
            )

            # Save initial session
            await self.repo.save(session_state, spec_content)

            # 2. Execution Loop
            hitl_response = None
            max_iterations = 100
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Execute workflow pattern
                # Accessing protected method _execute_pattern from WorkflowExecutor
                # This is necessary because run_interactive is not async-pause compatible
                result = await self._executor._execute_pattern(
                    self.variables,
                    session_state,
                    self.repo,
                    hitl_response,
                )
                result.session_id = self.session_id
                self._result = result

                # Check for HITL pause
                if result.agent_id == "hitl" and result.exit_code == EX_HITL_PAUSE:
                    # Extract HITL state
                    hitl_state_data = session_state.pattern_state.get("hitl_state", {})
                    if not hitl_state_data:
                        raise RuntimeError("HITL pause detected but no hitl_state in session")
                    
                    self.hitl_state = HITLState(**hitl_state_data)
                    self.state = SessionStateEnum.PAUSED_HITL
                    
                    # Wait for resume() to be called (async wait)
                    hitl_response = await self._hitl_response_queue.get()
                    
                    # Resume
                    self.state = SessionStateEnum.RUNNING
                    self.hitl_state = None
                    continue
                
                else:
                    # Completion
                    session_state.metadata.status = SessionStatus.COMPLETED
                    session_state.metadata.updated_at = now_iso8601()
                    await self.repo.save(session_state, spec_content)
                    self.state = SessionStateEnum.COMPLETE
                    return

            raise RuntimeError("HITL loop exceeded maximum iterations")

        except asyncio.CancelledError:
            self.state = SessionStateEnum.CANCELLED
            # Update session status on disk
            if 'session_state' in locals():
                session_state.metadata.status = SessionStatus.PAUSED # Mark as paused on cancel? Or FAILED?
                # Usually cancelled means user stopped it.
                await self.repo.save(session_state, spec_content)
            raise

        except Exception as e:
            self.error = e
            self.state = SessionStateEnum.FAILED
            if 'session_state' in locals():
                session_state.metadata.status = SessionStatus.FAILED
                session_state.metadata.error = str(e)
                await self.repo.save(session_state, spec_content)

    def _internal_hitl_handler(self, hitl_state: HITLState) -> str:
        """Not used in this implementation."""
        raise NotImplementedError("Should not be called")

    async def _run_loop_async(self) -> None:
        """Not used."""
        pass

    def is_running(self) -> bool:
        """Check if session is actively running."""
        return self.state == SessionStateEnum.RUNNING

    def is_paused(self) -> bool:
        """Check if session is paused waiting for HITL response."""
        return self.state == SessionStateEnum.PAUSED_HITL

    def is_complete(self) -> bool:
        """Check if session completed successfully."""
        return self.state == SessionStateEnum.COMPLETE

    def is_failed(self) -> bool:
        """Check if session failed with error."""
        return self.state == SessionStateEnum.FAILED

    def get_hitl_state(self) -> HITLState | None:
        """Get current HITL state if paused."""
        return self.hitl_state if self.is_paused() else None

    def resume(self, hitl_response: str) -> None:
        """Resume from HITL pause with user response."""
        if not self.is_paused():
            raise RuntimeError(f"Cannot resume - session not paused (state={self.state})")

        # Send response to waiting workflow thread
        # We use call_soon_threadsafe to put into queue which is thread safe?
        # Queue.put_nowait is not thread safe across loops?
        # Actually asyncio.Queue is not thread safe.
        # We need to use loop.call_soon_threadsafe(queue.put_nowait, item)
        
        loop = _ensure_event_loop()
        loop.call_soon_threadsafe(self._hitl_response_queue.put_nowait, hitl_response)

    def cancel(self) -> None:
        """Cancel running workflow execution."""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
        self.state = SessionStateEnum.CANCELLED

    def get_result(self) -> RunResult:
        """Get final result after completion."""
        if not self.is_complete():
            raise RuntimeError(f"Session not complete (state={self.state})")
        return self._result

    def get_error(self) -> Exception | None:
        """Get error if session failed."""
        return self.error if self.is_failed() else None

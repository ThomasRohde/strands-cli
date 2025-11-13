"""Workflow execution engine with HITL support."""

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import suppress
from typing import Any

from strands_cli.api.handlers import terminal_hitl_handler
from strands_cli.events import EventBus, WorkflowEvent
from strands_cli.exec.chain import run_chain
from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer
from strands_cli.exec.graph import run_graph
from strands_cli.exec.orchestrator_workers import run_orchestrator_workers
from strands_cli.exec.parallel import run_parallel
from strands_cli.exec.routing import run_routing
from strands_cli.exec.utils import AgentCache
from strands_cli.exec.workflow import run_workflow
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.session import (
    SessionMetadata,
    SessionState,
    SessionStatus,
    TokenUsage,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import generate_session_id, now_iso8601
from strands_cli.types import HITLState, PatternType, RunResult, Spec, StreamChunk, StreamChunkType


class WorkflowExecutor:
    """Executes workflows with optional interactive HITL.

    Supports async context manager protocol for automatic resource cleanup:
        async with workflow.async_executor() as executor:
            result = await executor.run(topic="AI safety")

    Resources are automatically cleaned up on exit.
    """

    def __init__(
        self,
        spec: Spec,
        output_dir: str | None = None,
        force_overwrite: bool = True,
    ):
        """Initialize executor with workflow spec.

        Args:
            spec: Validated workflow specification
            output_dir: Optional output directory for artifacts
            force_overwrite: Whether to overwrite existing artifact files (default: True)
        """
        self.spec = spec
        self.output_dir = output_dir
        self.force_overwrite = force_overwrite
        self.event_bus = EventBus()
        self._agent_cache: AgentCache | None = None

    async def __aenter__(self) -> "WorkflowExecutor":
        """Enter async context and initialize agent cache.

        Returns:
            Self for context manager usage
        """
        self._agent_cache = AgentCache()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Exit async context and cleanup resources.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)

        Returns:
            False to propagate exceptions
        """
        if self._agent_cache:
            await self._agent_cache.close()
            self._agent_cache = None  # Clear reference after cleanup
        return False

    def on(self, event_type: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to subscribe handlers to workflow events.

        Supports both sync and async handlers.

        Example:
            >>> workflow = WorkflowExecutor(spec)
            >>> @workflow.on("step_complete")
            >>> def on_step(event: WorkflowEvent):
            >>>     print(f"Step {event.data['step_index']} completed")
            >>>
            >>> @workflow.on("step_complete")
            >>> async def on_step_async(event: WorkflowEvent):
            >>>     await send_notification(event)

        Args:
            event_type: Event type to subscribe to

        Returns:
            Decorator function
        """
        from strands_cli.events import EventHandler

        def decorator(handler: EventHandler) -> EventHandler:
            self.event_bus.subscribe(event_type, handler)
            return handler

        return decorator

    async def run_interactive(
        self,
        variables: dict[str, Any],
        hitl_handler: Callable[[HITLState], str] | None = None,
    ) -> RunResult:
        """Run workflow with interactive HITL prompts.

        Creates session automatically and loops through HITL pauses,
        prompting user in terminal instead of exiting.

        Args:
            variables: Runtime variable overrides
            hitl_handler: Optional custom HITL handler (defaults to terminal_hitl_handler)

        Returns:
            RunResult with execution details
        """
        if hitl_handler is None:
            hitl_handler = terminal_hitl_handler

        # Serialize spec for session storage
        spec_dict = self.spec.model_dump(mode="json")
        spec_content = json.dumps(spec_dict, sort_keys=True, indent=2)
        spec_hash = hashlib.sha256(spec_content.encode("utf-8")).hexdigest()

        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=self.spec.name,
                spec_hash=spec_hash,
                pattern_type=self.spec.pattern.type.value,
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables=variables,
            runtime_config=self.spec.runtime.model_dump(),
            pattern_state={},
            token_usage=TokenUsage(),
            artifacts_written=[],
        )

        # Save initial session
        await session_repo.save(session_state, spec_content)

        try:
            # HITL loop: continue until workflow completes
            # Handles multiple HITL pauses by looping until workflow completes naturally
            hitl_response = None
            max_iterations = 100  # Safety limit to prevent infinite loops
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Execute workflow (may pause at HITL step)
                result = await self._execute_pattern(
                    variables,
                    session_state,
                    session_repo,
                    hitl_response,
                )
                result.session_id = session_state.metadata.session_id

                # Check if paused for HITL input
                if result.agent_id == "hitl" and result.exit_code == EX_HITL_PAUSE:
                    # Extract HITL state from session pattern_state
                    hitl_state_data = session_state.pattern_state.get("hitl_state", {})
                    if not hitl_state_data:
                        raise RuntimeError(
                            "HITL pause detected but no hitl_state in session. "
                            "This indicates an executor bug."
                        )

                    hitl_state = HITLState(**hitl_state_data)

                    # Validate HITL state is active
                    if not hitl_state.active:
                        raise RuntimeError(
                            "HITL pause detected but hitl_state.active is False. "
                            "This indicates an executor bug."
                        )

                    # Prompt user via handler (may raise on Ctrl+C)
                    hitl_response = hitl_handler(hitl_state)

                    # NOTE: Do NOT save session here - the executor will inject the HITL
                    # response and update completed_tasks/task_results, then save the session.
                    # Saving here would overwrite the executor's changes with stale state.

                    # Continue to next iteration (resume with response)
                    # The hitl_response will be passed to executor which will:
                    # 1. Inject response into task_results
                    # 2. Add task to completed_tasks
                    # 3. Save updated session state
                    continue
                else:
                    # Workflow completed successfully (no more HITL pauses)
                    # Mark session as completed
                    session_state.metadata.status = SessionStatus.COMPLETED
                    session_state.metadata.updated_at = now_iso8601()

                    # Write artifacts if configured
                    if self.output_dir and self.spec.outputs and self.spec.outputs.artifacts:
                        from strands_cli.artifacts.io import write_artifacts

                        # Merge variables for template rendering
                        merged_vars: dict[str, Any] = {**variables}
                        if result.variables:
                            merged_vars.update(result.variables)

                        written_files = write_artifacts(
                            self.spec.outputs.artifacts,
                            result.last_response or "",
                            self.output_dir,
                            self.force_overwrite,
                            variables=merged_vars,
                            execution_context=result.execution_context,
                            spec_name=self.spec.name,
                            pattern_type=self.spec.pattern.type.value,
                        )
                        result.artifacts_written = written_files

                    await session_repo.save(session_state, spec_content)
                    return result

            # Safety limit reached - possible infinite HITL loop in workflow
            raise RuntimeError(
                f"HITL loop exceeded maximum iterations ({max_iterations}). "
                "This may indicate an infinite loop in the workflow. "
                f"Check workflow '{self.spec.name}' for recursive HITL steps."
            )

        except KeyboardInterrupt:
            # User interrupted execution with Ctrl+C
            # Mark session as PAUSED so user can resume later with --resume
            session_state.metadata.status = SessionStatus.PAUSED
            session_state.metadata.updated_at = now_iso8601()
            await session_repo.save(session_state, spec_content)
            raise

        except Exception:
            # Any other exception - mark session as FAILED
            session_state.metadata.status = SessionStatus.FAILED
            session_state.metadata.updated_at = now_iso8601()
            await session_repo.save(session_state, spec_content)
            raise

    async def run_async(
        self,
        variables: dict[str, Any],
    ) -> RunResult:
        """Run workflow asynchronously without interactive mode.

        Async version of run() for use in async contexts.

        Args:
            variables: Runtime variable overrides

        Returns:
            RunResult with execution details (may indicate HITL pause)
        """
        return await self.run(variables)

    async def run(
        self,
        variables: dict[str, Any],
    ) -> RunResult:
        """Run workflow without interactive mode (session-based HITL).

        Standard execution mode that saves session and exits at HITL steps.

        Args:
            variables: Runtime variable overrides

        Returns:
            RunResult with execution details (may indicate HITL pause)
        """
        # Serialize spec for session storage
        spec_dict = self.spec.model_dump(mode="json")
        spec_content = json.dumps(spec_dict, sort_keys=True, indent=2)
        spec_hash = hashlib.sha256(spec_content.encode("utf-8")).hexdigest()

        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=self.spec.name,
                spec_hash=spec_hash,
                pattern_type=self.spec.pattern.type.value,
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables=variables,
            runtime_config=self.spec.runtime.model_dump(),
            pattern_state={},
            token_usage=TokenUsage(),
            artifacts_written=[],
        )

        # Save initial session
        await session_repo.save(session_state, spec_content)

        try:
            # Execute workflow (will exit at HITL)
            result = await self._execute_pattern(
                variables,
                session_state,
                session_repo,
                None,
            )
            result.session_id = session_state.metadata.session_id

            # Update session status
            session_state.metadata.updated_at = now_iso8601()
            if result.agent_id == "hitl":
                session_state.metadata.status = SessionStatus.PAUSED
            else:
                session_state.metadata.status = SessionStatus.COMPLETED

                # Write artifacts if configured and workflow completed successfully
                if self.output_dir and self.spec.outputs and self.spec.outputs.artifacts:
                    from strands_cli.artifacts.io import write_artifacts

                    # Merge variables for template rendering
                    merged_vars: dict[str, Any] = {**variables}
                    if result.variables:
                        merged_vars.update(result.variables)

                    written_files = write_artifacts(
                        self.spec.outputs.artifacts,
                        result.last_response or "",
                        self.output_dir,
                        self.force_overwrite,
                        variables=merged_vars,
                        execution_context=result.execution_context,
                        spec_name=self.spec.name,
                        pattern_type=self.spec.pattern.type.value,
                    )
                    result.artifacts_written = written_files

            await session_repo.save(session_state, spec_content)
            return result

        except Exception as exc:
            # Mark session as failed
            session_state.metadata.status = SessionStatus.FAILED
            session_state.metadata.updated_at = now_iso8601()
            session_state.metadata.error = f"{type(exc).__name__}: {exc}"
            await session_repo.save(session_state, spec_content)
            raise

    async def stream_async(
        self,
        variables: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream workflow execution events as they occur.

        Note: Token-by-token streaming not yet implemented in Phase 3.
        Returns complete responses as chunks for now.

        Args:
            variables: Runtime variable overrides as dict

        Yields:
            StreamChunk objects with execution progress

        Raises:
            Exception: Any exception from workflow execution is propagated
        """
        if variables is None:
            variables = {}

        # Create queue for streaming chunks
        chunks: asyncio.Queue[StreamChunk | None | Exception] = asyncio.Queue()

        def _map_event_to_chunk_type(event_type: str) -> StreamChunkType:
            """Map event types to chunk types."""
            if event_type == "workflow_start":
                return "workflow_start"
            elif event_type in ["step_start", "task_start", "branch_start", "node_start"]:
                return "step_start"
            elif event_type in [
                "step_complete",
                "task_complete",
                "branch_complete",
                "node_complete",
            ]:
                return "step_complete"
            elif event_type == "workflow_complete":
                return "complete"
            else:
                return "step_complete"  # Default

        def emit_chunk(event: WorkflowEvent) -> None:
            """Convert event to chunk and add to queue."""
            chunk = StreamChunk(
                chunk_type=_map_event_to_chunk_type(event.event_type),
                data=event.data,
                timestamp=event.timestamp,
            )
            chunks.put_nowait(chunk)

        # Subscribe to relevant events
        self.event_bus.subscribe("workflow_start", emit_chunk)
        self.event_bus.subscribe("step_start", emit_chunk)
        self.event_bus.subscribe("step_complete", emit_chunk)
        self.event_bus.subscribe("task_start", emit_chunk)
        self.event_bus.subscribe("task_complete", emit_chunk)
        self.event_bus.subscribe("branch_start", emit_chunk)
        self.event_bus.subscribe("branch_complete", emit_chunk)
        self.event_bus.subscribe("node_start", emit_chunk)
        self.event_bus.subscribe("node_complete", emit_chunk)
        self.event_bus.subscribe("workflow_complete", emit_chunk)

        # Execute workflow in background
        async def execute() -> None:
            try:
                await self.run_async(variables)
            except Exception as exc:
                await chunks.put(exc)
                return
            await chunks.put(None)  # Success sentinel

        task = asyncio.create_task(execute())

        # Yield chunks as they arrive
        try:
            while True:
                item = await chunks.get()
                if item is None:
                    # Success sentinel
                    break
                elif isinstance(item, Exception):
                    # Propagate exception to consumer
                    raise item
                else:
                    # Regular chunk
                    yield item
        finally:
            # Unsubscribe handlers to prevent duplicate callbacks
            self.event_bus.unsubscribe("workflow_start", emit_chunk)
            self.event_bus.unsubscribe("step_start", emit_chunk)
            self.event_bus.unsubscribe("step_complete", emit_chunk)
            self.event_bus.unsubscribe("task_start", emit_chunk)
            self.event_bus.unsubscribe("task_complete", emit_chunk)
            self.event_bus.unsubscribe("branch_start", emit_chunk)
            self.event_bus.unsubscribe("branch_complete", emit_chunk)
            self.event_bus.unsubscribe("node_start", emit_chunk)
            self.event_bus.unsubscribe("node_complete", emit_chunk)
            self.event_bus.unsubscribe("workflow_complete", emit_chunk)

            # Ensure task completes even if consumer stops early
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _execute_pattern(
        self,
        variables: dict[str, Any],
        session_state: SessionState,
        session_repo: FileSessionRepository,
        hitl_response: str | None = None,
    ) -> RunResult:
        """Route to appropriate executor based on pattern type.

        Args:
            variables: Runtime variable overrides
            session_state: Current session state
            session_repo: Session repository
            hitl_response: HITL response for resume (if any)

        Returns:
            RunResult from executor
        """
        pattern = self.spec.pattern.type

        if pattern == PatternType.CHAIN:
            return await run_chain(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.WORKFLOW:
            return await run_workflow(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.ROUTING:
            return await run_routing(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.PARALLEL:
            return await run_parallel(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.EVALUATOR_OPTIMIZER:
            return await run_evaluator_optimizer(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.ORCHESTRATOR_WORKERS:
            return await run_orchestrator_workers(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        elif pattern == PatternType.GRAPH:
            return await run_graph(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
                self.event_bus,
                self._agent_cache,
            )
        else:
            raise ValueError(f"Unsupported pattern type: {pattern}")


__all__ = ["WorkflowExecutor"]

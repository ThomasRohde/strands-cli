"""Workflow execution engine with HITL support."""

from collections.abc import Callable
from typing import Any

from strands_cli.api.handlers import terminal_hitl_handler
from strands_cli.exec.chain import run_chain
from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer
from strands_cli.exec.graph import run_graph
from strands_cli.exec.orchestrator_workers import run_orchestrator_workers
from strands_cli.exec.parallel import run_parallel
from strands_cli.exec.routing import run_routing
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
from strands_cli.types import HITLState, PatternType, RunResult, Spec


class WorkflowExecutor:
    """Executes workflows with optional interactive HITL."""

    def __init__(self, spec: Spec):
        """Initialize executor with workflow spec.

        Args:
            spec: Validated workflow specification
        """
        self.spec = spec

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
        spec_content = self.spec.model_dump_json(indent=2)

        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=self.spec.name,
                spec_hash="api-generated",  # API sessions don't have file hash
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

                    # Update session state with user response
                    # This is critical for resume - executor will use this on next iteration
                    hitl_state.active = False  # Mark as no longer waiting
                    hitl_state.user_response = hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()

                    # Update session metadata timestamp
                    session_state.metadata.updated_at = now_iso8601()

                    # Save updated session state with user response
                    await session_repo.save(session_state, spec_content)

                    # Continue to next iteration (resume with response)
                    # Clear hitl_response will be passed to executor which will resume from HITL step
                    continue
                else:
                    # Workflow completed successfully (no more HITL pauses)
                    # Mark session as completed and return result
                    session_state.metadata.status = SessionStatus.COMPLETED
                    session_state.metadata.updated_at = now_iso8601()
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
        spec_content = self.spec.model_dump_json(indent=2)

        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name=self.spec.name,
                spec_hash="api-generated",  # API sessions don't have file hash
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

            # Update session status
            if result.agent_id == "hitl":
                session_state.metadata.status = SessionStatus.PAUSED
            else:
                session_state.metadata.status = SessionStatus.COMPLETED

            await session_repo.save(session_state, spec_content)
            return result

        except Exception:
            # Mark session as failed
            session_state.metadata.status = SessionStatus.FAILED
            await session_repo.save(session_state, spec_content)
            raise

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
            )
        elif pattern == PatternType.WORKFLOW:
            return await run_workflow(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.ROUTING:
            return await run_routing(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.PARALLEL:
            return await run_parallel(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.EVALUATOR_OPTIMIZER:
            return await run_evaluator_optimizer(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.ORCHESTRATOR_WORKERS:
            return await run_orchestrator_workers(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.GRAPH:
            return await run_graph(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        else:
            raise ValueError(f"Unsupported pattern type: {pattern}")


__all__ = ["WorkflowExecutor"]

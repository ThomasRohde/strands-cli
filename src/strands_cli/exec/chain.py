"""Multi-step chain executor.

Executes sequential multi-step chains with context passing between steps.
Each step receives the outputs of previous steps via template variables.

Execution Flow:
    1. Validate chain configuration (at least 1 step)
    2. For each step in sequence:
        a. Build template context (prior step responses + user variables + step.vars)
        b. Render step input with Jinja2
        c. Build/reuse agent for step (with optional tool_overrides)
        d. Execute agent asynchronously with retry logic
        e. Track token budget and warn at 80% threshold
        f. Capture step response and timing
    3. Return RunResult with final step response and all step history

Context Threading:
    - Explicit step references: {{ steps[0].response }}, {{ steps[1].response }}
    - Each step receives all prior step outputs in template context
    - Optional per-step variable overrides via step.vars
    - Fail-fast: Stop on first step failure

Budget Enforcement:
    - Track cumulative tokens across all steps
    - Warn at 80% of budgets.max_tokens
    - Hard stop at 100% (if configured)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from rich.console import Console
from rich.panel import Panel

from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.checkpoint_utils import fail_session
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import now_iso8601
from strands_cli.telemetry import get_tracer
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import HITLState, PatternType, RunResult, Spec


class ChainExecutionError(Exception):
    """Raised when chain execution fails."""

    pass


logger = structlog.get_logger(__name__)
console = Console()


def _build_step_context(
    spec: Spec,
    step_index: int,
    step_history: list[dict[str, Any]],
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build template context for a step.

    Args:
        spec: Workflow spec
        step_index: Current step index (0-based)
        step_history: List of prior step results [{response: str, ...}, ...]
        variables: User-provided variables from --var flags

    Returns:
        Template context dictionary with steps[], user variables, and step.vars
    """
    context = {}

    # Add user-provided variables from spec.inputs.values
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])

    # Override with CLI --var variables
    if variables:
        context.update(variables)

    # Add step history as steps[] array
    # Each entry is {response: str, index: int} plus either {agent: str} for agent steps
    # or {type: 'hitl', prompt: str} for HITL steps
    context["steps"] = step_history

    # Add hitl_response convenience variable (most recent HITL step response)
    # Walk backwards through step_history to find the latest HITL step
    for step_record in reversed(step_history):
        if step_record.get("type") == "hitl":
            context["hitl_response"] = step_record.get("response", "")
            break

    # Add per-step variable overrides from step.vars
    if spec.pattern.config.steps is not None:
        step = spec.pattern.config.steps[step_index]
        if step.vars:
            context.update(step.vars)

    return context


async def run_chain(  # noqa: C901
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
) -> RunResult:
    """Execute a multi-step chain workflow with optional session persistence and HITL support.

    Executes steps sequentially with context passing. Each step receives
    all prior step responses via {{ steps[n].response }} template variables.

    Phase 1 HITL Support:
        - Detects HITL steps (type: hitl) and pauses execution
        - Saves session state before displaying HITL prompt
        - Exits with EX_HITL_PAUSE for user to provide response
        - Resumes with hitl_response and injects into step_history

    Phase 4 Performance Optimizations:
        - Agent caching: Reuses agents across steps with same (agent_id, tools)
        - Single event loop: No per-step asyncio.run() overhead
        - HTTP client cleanup: Proper resource management via AgentCache.close()

    Phase 2 Session Support:
        - Resume from checkpoint: Skip completed steps on resume
        - Incremental checkpointing: Save state after each step
        - Agent session restoration: Restore conversation history via Strands SDK

    Args:
        spec: Workflow spec with chain pattern
        variables: Optional CLI --var overrides
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)
        hitl_response: User response when resuming from HITL pause (None = not HITL resume)

    Returns:
        RunResult with final step response and execution metadata

    Raises:
        ChainExecutionError: If chain execution fails at any step
        ValueError: If session_state and session_repo not both provided or both None
    """
    # Validate session parameters (both or neither)
    if (session_state is None) != (session_repo is None):
        raise ValueError("session_state and session_repo must both be provided or both be None")
    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    # Phase 10: Create root span for chain execution with attributes
    with tracer.start_as_current_span("execute.chain") as span:
        # Set span attributes (queryable metadata)
        span.set_attribute("spec.name", spec.name)
        span.set_attribute("spec.version", spec.version or 0)
        span.set_attribute("pattern.type", "chain")
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id or "default")
        span.set_attribute("agent.count", len(spec.agents))
        if spec.pattern.config.steps:
            span.set_attribute("chain.step_count", len(spec.pattern.config.steps))

        logger.info("chain_execution_start", spec_name=spec.name)
        span.add_event("execution_start", {"spec_name": spec.name})

        if not spec.pattern.config.steps:
            raise ChainExecutionError("Chain pattern has no steps")

        # Get retry config
        max_attempts, wait_min, wait_max = get_retry_config(spec)

        # Determine starting point and restore state for resume
        if session_state:
            # Resume mode: start from next incomplete step
            start_step = session_state.pattern_state.get("current_step", 0)
            step_history = session_state.pattern_state.get("step_history", [])
            cumulative_tokens = (
                session_state.token_usage.total_input_tokens
                + session_state.token_usage.total_output_tokens
            )
            started_at = session_state.metadata.created_at
            logger.info(
                "chain_resume",
                session_id=session_state.metadata.session_id,
                start_step=start_step,
                completed_steps=len(step_history),
            )
            span.add_event(
                "chain_resume",
                {
                    "session_id": session_state.metadata.session_id,
                    "start_step": start_step,
                    "completed_steps": len(step_history),
                },
            )
        else:
            # Fresh start
            start_step = 0
            step_history = []
            cumulative_tokens = 0
            started_at = datetime.now(UTC).isoformat()

        # Phase 1 HITL: Handle resume from HITL pause
        if session_state:
            hitl_state_dict = session_state.pattern_state.get("hitl_state")
            if hitl_state_dict:
                hitl_state = HITLState(**hitl_state_dict)
                if hitl_state.active:
                    # Session is paused for HITL - validate response provided
                    if not hitl_response:
                        raise ChainExecutionError(
                            f"Session {session_state.metadata.session_id} is waiting for HITL response. "
                            f"Resume with: strands run --resume {session_state.metadata.session_id} "
                            f"--hitl-response 'your response'"
                        )

                    # Inject user response into step history (same pattern as agent steps)
                    # Structure: {index, type='hitl', prompt, response} - matches agent step pattern
                    # for template compatibility ({{ steps[n].response }} and {{ hitl_response }})
                    hitl_step_record = {
                        "index": hitl_state.step_index,
                        "type": "hitl",
                        "prompt": hitl_state.prompt,
                        "response": hitl_response,  # Store in 'response' field like agent steps
                        "tokens_estimated": 0,  # No tokens for HITL steps
                    }
                    step_history.append(hitl_step_record)

                    # Mark HITL as no longer active
                    hitl_state.active = False
                    hitl_state.user_response = hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()

                    # Checkpoint session after injecting HITL response (before continuing execution)
                    # This prevents data loss if workflow crashes mid-step after resume
                    if session_repo:
                        session_state.pattern_state["step_history"] = step_history
                        await session_repo.save(session_state, "")
                        logger.info(
                            "session.checkpoint_after_hitl",
                            session_id=session_state.metadata.session_id,
                            step=hitl_state.step_index,
                        )

                    # Continue from next step after HITL
                    start_step = hitl_state.step_index + 1

                    logger.info(
                        "hitl_response_received",
                        session_id=session_state.metadata.session_id,
                        step=hitl_state.step_index,
                        response_preview=hitl_response[:100]
                        if len(hitl_response) > 100
                        else hitl_response,
                    )
                    span.add_event(
                        "hitl_resume",
                        {
                            "step_index": hitl_state.step_index,
                            "response_length": len(hitl_response),
                        },
                    )

        # Track execution state
        max_tokens = None
        if spec.runtime.budgets:
            max_tokens = spec.runtime.budgets.get("max_tokens")

        # Phase 6.1: Create context manager and hooks for compaction
        context_manager = create_from_policy(spec.context_policy, spec)
        shared_hooks: list[Any] = []
        compaction_threshold: int | None = None
        if (
            spec.context_policy
            and spec.context_policy.compaction
            and spec.context_policy.compaction.enabled
        ):
            compaction_threshold = spec.context_policy.compaction.when_tokens_over or 60000
            logger.info("compaction_enabled", threshold_tokens=compaction_threshold)

        # Phase 6.4: Add budget enforcer hook (runs AFTER compaction to allow token reduction)
        if spec.runtime.budgets and spec.runtime.budgets.get("max_tokens"):
            from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

            max_tokens = spec.runtime.budgets["max_tokens"]
            warn_threshold = spec.runtime.budgets.get("warn_threshold", 0.8)
            shared_hooks.append(
                BudgetEnforcerHook(max_tokens=max_tokens, warn_threshold=warn_threshold)
            )
            logger.info(
                "budget_enforcer_enabled", max_tokens=max_tokens, warn_threshold=warn_threshold
            )

        # Phase 6.2: Initialize notes manager and hook for structured notes
        notes_manager = None
        # Phase 2: Seed step counter from existing history when resuming
        step_counter = [len(step_history)]  # Mutable container for hook to track step count
        if spec.context_policy and spec.context_policy.notes:
            notes_manager = NotesManager(spec.context_policy.notes.file)

            # Build agent_id → tools mapping for notes hook
            agent_tools: dict[str, list[str]] = {}
            for agent_id, agent_config in spec.agents.items():
                if agent_config.tools:
                    agent_tools[agent_id] = agent_config.tools

            shared_hooks.append(NotesAppenderHook(notes_manager, step_counter, agent_tools))
            logger.info("notes_enabled", notes_file=spec.context_policy.notes.file)

        # Phase 4: Create AgentCache for agent reuse across steps
        # Phase 2: Pass session_id for agent session restoration
        agent_session_id = session_state.metadata.session_id if session_state else None
        cache = AgentCache()
        try:
            # Execute steps starting from start_step (skip completed steps on resume)
            for step_index in range(start_step, len(spec.pattern.config.steps)):
                step = spec.pattern.config.steps[step_index]

                # Phase 1 HITL: Check if this is a HITL step
                if hasattr(step, "type") and step.type == "hitl":
                    # BLOCKER 2 FIX: Validate session persistence is available
                    if not session_repo or not session_state:
                        raise ChainExecutionError(
                            f"HITL step at index {step_index} requires session persistence, but session is disabled. "
                            "Session persistence is required to save pause state and enable resume. "
                            "Remove --no-save-session flag or remove HITL steps from workflow."
                        )
                    
                    # HITL pause point
                    logger.info(
                        "hitl_step_detected",
                        step=step_index,
                        total_steps=len(spec.pattern.config.steps),
                    )
                    span.add_event(
                        "hitl_pause",
                        {
                            "step_index": step_index,
                            "prompt_preview": step.prompt[:100]
                            if step.prompt and len(step.prompt) > 100
                            else (step.prompt or ""),
                        },
                    )

                    # Build context for displaying to user
                    template_context = _build_step_context(
                        spec, step_index, step_history, variables
                    )

                    # Render context_display template if provided
                    context_text = ""
                    if step.context_display:
                        context_text = render_template(step.context_display, template_context)

                    # Calculate timeout (Phase 2: not enforced yet)
                    timeout_at = None
                    if step.timeout_seconds and step.timeout_seconds > 0:
                        timeout_dt = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)
                        timeout_at = timeout_dt.isoformat()

                    # Create HITL state for session
                    new_hitl_state = HITLState(
                        active=True,
                        step_index=step_index,
                        prompt=step.prompt,
                        context_display=context_text,
                        default_response=step.default,
                        timeout_at=timeout_at,
                        user_response=None,
                    )

                    # Save session with HITL state BEFORE displaying to user
                    # (This ensures resume works even if CLI crashes during display)
                    if session_repo and session_state:
                        session_state.pattern_state["current_step"] = step_index
                        session_state.pattern_state["step_history"] = step_history
                        session_state.pattern_state["hitl_state"] = new_hitl_state.model_dump()
                        session_state.metadata.status = SessionStatus.PAUSED
                        session_state.metadata.updated_at = now_iso8601()

                        try:
                            spec_content = ""  # Spec snapshot already saved
                            await session_repo.save(session_state, spec_content)
                            logger.info(
                                "hitl_pause_saved",
                                session_id=session_state.metadata.session_id,
                                step=step_index,
                            )
                        except Exception as e:
                            logger.error(
                                "hitl_pause_save_failed",
                                session_id=session_state.metadata.session_id,
                                step=step_index,
                                error=str(e),
                            )
                            raise ChainExecutionError(
                                f"Failed to save HITL pause state: {e}"
                            ) from e

                    # Display HITL prompt to user
                    console.print()
                    console.print(
                        Panel(
                            f"[bold yellow]>>> HUMAN INPUT REQUIRED <<<[/bold yellow]\n\n{step.prompt}",
                            border_style="yellow",
                            padding=(1, 2),
                            title="HITL Pause",
                        )
                    )

                    if context_text:
                        console.print(
                            Panel(
                                f"[bold]Context for Review:[/bold]\n\n{context_text}",
                                border_style="dim",
                                padding=(1, 2),
                            )
                        )

                    if session_state:
                        console.print(
                            f"\n[dim]Session ID:[/dim] {session_state.metadata.session_id}"
                        )
                        console.print(
                            f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} "
                            f"--hitl-response 'your response'"
                        )
                    console.print()

                    # Exit with HITL pause code
                    hitl_pause_completed_at = datetime.now(UTC).isoformat()
                    hitl_pause_started_dt = datetime.fromisoformat(started_at)
                    hitl_pause_completed_dt = datetime.fromisoformat(hitl_pause_completed_at)
                    hitl_pause_duration = (
                        hitl_pause_completed_dt - hitl_pause_started_dt
                    ).total_seconds()

                    return RunResult(
                        success=True,
                        last_response=f"HITL pause at step {step_index}: {step.prompt}",
                        pattern_type=PatternType.CHAIN,
                        started_at=started_at,
                        completed_at=hitl_pause_completed_at,
                        duration_seconds=hitl_pause_duration,
                        agent_id="hitl",  # Special marker for HITL steps
                        execution_context={"steps": step_history},
                    )

                # Regular agent step execution
                logger.info(
                    "chain_step_start",
                    step=step_index,
                    total_steps=len(spec.pattern.config.steps),
                    agent=step.agent,
                )
                span.add_event(
                    "step_start",
                    {
                        "step_index": step_index,
                        "agent_id": step.agent or "",
                        "total_steps": len(spec.pattern.config.steps),
                    },
                )

                # Build context with prior step responses
                template_context = _build_step_context(spec, step_index, step_history, variables)

                # Render step input (default to empty if not provided)
                step_input_template = step.input or ""
                step_input = render_template(step_input_template, template_context)

                # Get the correct agent config for this step (Phase 2: support multi-agent chains)
                step_agent_id = step.agent
                if step_agent_id not in spec.agents:
                    raise ChainExecutionError(
                        f"Step {step_index} references unknown agent '{step_agent_id}'"
                    )
                step_agent_config = spec.agents[step_agent_id]

                # Phase 4: Use cached agent instead of rebuilding per step
                # Use step's tool_overrides if provided, else use agent's tools
                tools_for_step = step.tool_overrides if step.tool_overrides else None

                # Phase 6.2: Inject last N notes into agent context
                injected_notes = None
                if notes_manager and spec.context_policy and spec.context_policy.notes:
                    injected_notes = notes_manager.get_last_n_for_injection(
                        spec.context_policy.notes.include_last
                    )
                    if injected_notes:
                        logger.debug(
                            "notes_injected",
                            step=step_index,
                            notes_length=len(injected_notes),
                        )

                # Phase 6: Pass conversation manager, hooks, and notes for context management
                hooks_for_agent: list[Any] | None = None
                if compaction_threshold is not None or shared_hooks:
                    hooks_for_agent = []
                    if compaction_threshold is not None:
                        hooks_for_agent.append(
                            ProactiveCompactionHook(
                                threshold_tokens=compaction_threshold,
                                model_id=spec.runtime.model_id,
                            )
                        )
                    hooks_for_agent.extend(shared_hooks)

                # Phase 2: Create session manager for agent conversation restoration on resume
                agent_session_manager = None
                if agent_session_id and session_repo and session_state:
                    from strands.session.file_session_manager import FileSessionManager

                    # Get agents directory for this session
                    agents_dir = session_repo.get_agents_dir(session_state.metadata.session_id)

                    # Create session manager for this specific agent
                    # Format: {session_id}_{agent_id} to isolate per-agent conversations
                    formatted_agent_session_id = f"{agent_session_id}_{step_agent_id}"
                    agent_session_manager = FileSessionManager(
                        session_id=formatted_agent_session_id,
                        storage_dir=str(agents_dir),
                    )
                    logger.debug(
                        "agent_session_restore",
                        agent_id=step_agent_id,
                        session_id=formatted_agent_session_id,
                    )

                agent = await cache.get_or_build_agent(
                    spec,
                    step_agent_id,
                    step_agent_config,
                    tool_overrides=tools_for_step,
                    conversation_manager=context_manager,
                    hooks=hooks_for_agent,
                    injected_notes=injected_notes,
                    worker_index=None,
                    session_manager=agent_session_manager,
                )

                # Phase 4: Direct await instead of asyncio.run() per step
                step_response = await invoke_agent_with_retry(
                    agent, step_input, max_attempts, wait_min, wait_max
                )

                # Extract response text
                response_text = (
                    step_response if isinstance(step_response, str) else str(step_response)
                )

                # Track token usage using shared estimator
                estimated_tokens = estimate_tokens(step_input, response_text)
                cumulative_tokens += estimated_tokens

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
                span.add_event(
                    "step_complete",
                    {
                        "step_index": step_index,
                        "response_length": len(response_text),
                        "cumulative_tokens": cumulative_tokens,
                    },
                )

                # Phase 2: Checkpoint after each step if session persistence enabled
                if session_state and session_repo:
                    # Update session state with progress
                    session_state.pattern_state["current_step"] = step_index + 1
                    session_state.pattern_state["step_history"] = step_history
                    session_state.metadata.updated_at = now_iso8601()
                    session_state.metadata.status = SessionStatus.RUNNING
                    # Update token usage incrementally (preserve actual split, not floor-divided estimate)
                    input_tokens = estimated_tokens // 2
                    output_tokens = estimated_tokens - input_tokens  # Put remainder on output
                    session_state.token_usage.total_input_tokens += input_tokens
                    session_state.token_usage.total_output_tokens += output_tokens

                    # Persist checkpoint
                    try:
                        spec_content = ""  # Spec snapshot already saved at session creation
                        await session_repo.save(session_state, spec_content)
                        logger.debug(
                            "chain_checkpoint_saved",
                            session_id=session_state.metadata.session_id,
                            step=step_index,
                        )
                    except Exception as e:
                        logger.warning(
                            "chain_checkpoint_failed",
                            session_id=session_state.metadata.session_id,
                            step=step_index,
                            error=str(e),
                        )

        except Exception as e:
            # Mark session as failed before re-raising
            if session_state and session_repo:
                await fail_session(session_state, session_repo, e)

            # Re-wrap low-level errors in ChainExecutionError for consistent error handling
            if isinstance(e, ChainExecutionError):
                raise
            raise ChainExecutionError(f"Chain execution failed: {e}") from e
        finally:
            # Phase 4: Clean up cached agents and HTTP clients
            await cache.close()

        completed_at = datetime.now(UTC).isoformat()
        started_dt = datetime.fromisoformat(started_at)
        completed_dt = datetime.fromisoformat(completed_at)
        duration = (completed_dt - started_dt).total_seconds()

        # Final response is from last step
        final_response = step_history[-1]["response"]
        # Agent ID is from the last step that produced the final response
        final_agent_id = step_history[-1]["agent"]

        logger.info(
            "chain_execution_complete",
            spec_name=spec.name,
            steps_executed=len(step_history),
            duration_seconds=duration,
            cumulative_tokens=cumulative_tokens,
        )
        span.add_event(
            "execution_complete",
            {
                "duration_seconds": duration,
                "steps_executed": len(step_history),
                "cumulative_tokens": cumulative_tokens,
            },
        )

        # Phase 2: Mark session as completed if session persistence enabled
        if session_state and session_repo:
            session_state.metadata.status = SessionStatus.COMPLETED
            session_state.metadata.updated_at = now_iso8601()
            try:
                spec_content = ""  # Spec snapshot already saved
                await session_repo.save(session_state, spec_content)
                logger.info(
                    "chain_session_completed",
                    session_id=session_state.metadata.session_id,
                )
            except Exception as e:
                logger.warning(
                    "chain_session_completion_failed",
                    session_id=session_state.metadata.session_id,
                    error=str(e),
                )

        return RunResult(
            success=True,
            last_response=final_response,
            error=None,
            agent_id=final_agent_id,
            pattern_type=PatternType.CHAIN,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            artifacts_written=[],
            execution_context={"steps": step_history},
        )

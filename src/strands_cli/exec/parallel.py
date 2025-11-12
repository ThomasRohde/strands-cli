"""Parallel branch executor.

Executes parallel branches concurrently with optional reduce step for aggregation.
Each branch executes its steps sequentially while branches run in parallel.

Execution Flow:
    1. Validate parallel configuration (at least 2 branches)
    2. Execute all branches concurrently:
        a. Build branch context (user variables only - isolated from other branches)
        b. Execute branch steps sequentially (like chain)
        c. Track tokens per branch
        d. Respect max_parallel limit via semaphore
    3. Collect all branch results in alphabetical order by branch ID
    4. Optionally execute reduce step with {{ branches.<id>.response }} context
    5. Return RunResult with final response (reduced or aggregated)

Branch Execution:
    - Each branch is independent (no cross-branch context during execution)
    - Steps within a branch execute sequentially with {{ steps[n].response }} access
    - Fail-fast: First branch failure stops all branches (asyncio.gather with return_exceptions=False)

Budget Enforcement:
    - Track cumulative tokens across all branches and reduce step
    - Warn at 80% of budgets.max_tokens
    - Hard stop at 100% (if configured)

Reduce Step:
    - Aggregates all branch outputs via template context
    - Template access: {{ branches.web.response }}, {{ branches['docs'].status }}
    - Branch results ordered alphabetically by branch ID for determinism
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from rich.console import Console
from rich.panel import Panel

from strands_cli.events import EventBus, WorkflowEvent
from strands_cli.exec.hitl_utils import check_hitl_timeout, format_timeout_warning
from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.checkpoint_utils import fail_session
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import now_iso8601
from strands_cli.telemetry import get_tracer
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import HITLState, ParallelBranch, PatternType, RunResult, Spec

try:
    from strands_agents.agent import AgentResult  # type: ignore[import-not-found]
except ImportError:
    # Fallback type for type checking when SDK not installed
    AgentResult = Any


class ParallelExecutionError(Exception):
    """Raised when parallel execution fails."""

    pass


logger = structlog.get_logger(__name__)
console = Console()  # For HITL pause display


def _build_branch_step_context(
    spec: Spec,
    step_index: int,
    step_history: list[dict[str, Any]],
    user_variables: dict[str, Any],
    step_vars: dict[str, str | int | bool] | None = None,
) -> dict[str, Any]:
    """Build template context for a step within a branch.

    Args:
        spec: Workflow spec
        step_index: Current step index within this branch (0-based)
        step_history: List of prior step results in THIS branch
        user_variables: User-provided variables (spec.inputs.values + CLI --var)
        step_vars: Per-step variable overrides from step.vars

    Returns:
        Template context with steps[], user variables, and step.vars
    """
    context = {}

    # Start with user variables
    context.update(user_variables)

    # Add step history from THIS branch only
    context["steps"] = step_history

    # Add last_response for convenience (most recent step's response)
    if step_history:
        context["last_response"] = step_history[-1]["response"]

    # Add hitl_response convenience variable (most recent HITL step response)
    # Walk backwards through step_history to find the latest HITL step
    for step_record in reversed(step_history):
        if step_record.get("type") == "hitl":
            context["hitl_response"] = step_record.get("response", "")
            break

    # Add per-step variable overrides
    if step_vars:
        context.update(step_vars)

    return context


async def _execute_branch(  # noqa: C901 - Complexity acceptable for HITL support
    spec: Spec,
    branch: ParallelBranch,
    user_variables: dict[str, Any],
    cache: AgentCache,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
    start_step: int = 0,
    restored_step_history: list[dict[str, Any]] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
    event_bus: EventBus | None = None,
) -> tuple[str, int, list[dict[str, Any]]] | dict[str, Any]:
    """Execute all steps in a branch sequentially with optional resume and HITL support.

    Args:
        spec: Workflow spec
        branch: ParallelBranch configuration
        user_variables: User-provided variables (spec + CLI)
        cache: Shared AgentCache for agent reuse
        max_attempts: Maximum retry attempts per step
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)
        context_manager: Optional conversation manager
        hooks: Optional agent hooks
        notes_manager: Optional notes manager
        start_step: Step index to start from (for resume)
        restored_step_history: Previously completed steps (for resume)
        session_state: Session state for HITL pause/resume
        session_repo: Repository for saving session on HITL pause
        hitl_response: User's response when resuming from HITL pause

    Returns:
        Tuple of (final_response, cumulative_tokens, step_history) on completion,
        OR dict with HITL pause information if branch hits HITL step

    Raises:
        ParallelExecutionError: If any step fails after retries
    """
    # Restore or initialize step history
    if restored_step_history is not None:
        step_history = restored_step_history.copy()
        cumulative_tokens = sum(s["tokens_estimated"] for s in step_history)
    else:
        step_history = []
        cumulative_tokens = 0

    logger.info(
        "Executing branch",
        branch_id=branch.id,
        num_steps=len(branch.steps),
        start_step=start_step,
        restored_steps=len(step_history),
    )

    # Check if resuming from branch HITL pause
    # Two scenarios:
    # 1. Fresh resume with new hitl_response from user (hitl_response parameter provided)
    # 2. Crash recovery where response was already checkpointed (check session_state.hitl_state.user_response)
    if session_state:
        # Check for timeout BEFORE checking for hitl_response
        timed_out, timeout_default = check_hitl_timeout(session_state)

        if timed_out and hitl_response is None:
            # Auto-resume with default response
            hitl_state_dict = session_state.pattern_state.get("hitl_state")
            if (
                hitl_state_dict
                and hitl_state_dict.get("step_type") == "branch"
                and hitl_state_dict.get("branch_id") == branch.id
            ):
                console.print(
                    Panel(
                        format_timeout_warning(
                            hitl_state_dict.get("timeout_at"),
                            timeout_default,
                        ),
                        border_style="yellow",
                    )
                )
                hitl_response = timeout_default

                # Record timeout metadata in pattern_state and session metadata
                session_state.pattern_state["hitl_timeout_occurred"] = True
                session_state.pattern_state["hitl_timeout_at"] = hitl_state_dict.get("timeout_at")
                session_state.pattern_state["hitl_default_used"] = timeout_default

                session_state.metadata.metadata["hitl_timeout_occurred"] = True
                session_state.metadata.metadata["hitl_timeout_at"] = hitl_state_dict.get(
                    "timeout_at"
                )
                session_state.metadata.metadata["hitl_default_used"] = timeout_default
        # If user provided explicit response, that overrides timeout

        hitl_state_dict = session_state.pattern_state.get("hitl_state")
        if (
            hitl_state_dict
            and hitl_state_dict.get("step_type") == "branch"
            and hitl_state_dict.get("branch_id") == branch.id
        ):
            # Determine the effective HITL response:
            # - Use new response from parameter if provided
            # - Otherwise use persisted response from previous checkpoint
            effective_hitl_response = (
                hitl_response if hitl_response is not None else hitl_state_dict.get("user_response")
            )

            if effective_hitl_response is not None:
                # Restore pre-HITL step history from session state
                branch_states = session_state.pattern_state.get("branch_states", {})
                if branch.id in branch_states:
                    step_history = branch_states[branch.id]["step_history"].copy()
                    cumulative_tokens = branch_states[branch.id]["cumulative_tokens"]

                # Inject HITL response into step history
                hitl_step_record = {
                    "index": hitl_state_dict["step_index"],
                    "type": "hitl",
                    "prompt": hitl_state_dict["prompt"],
                    "response": effective_hitl_response,
                    "tokens_estimated": 0,
                }
                step_history.append(hitl_step_record)

                # Continue from next step after HITL
                start_step = hitl_state_dict["step_index"] + 1

                # Persist updated branch + HITL state before continuing
                # This prevents data loss if workflow crashes after resume but before next checkpoint
                if session_repo and session_state:
                    # Update branch state with injected HITL response
                    branch_states = session_state.pattern_state.setdefault("branch_states", {})
                    branch_state = branch_states.setdefault(branch.id, {})
                    branch_state["step_history"] = step_history.copy()
                    branch_state["current_step"] = hitl_state_dict["step_index"] + 1
                    branch_state["cumulative_tokens"] = cumulative_tokens

                    # Clear HITL state (no longer active)
                    hitl_state = HITLState(**hitl_state_dict)
                    hitl_state.active = False
                    hitl_state.user_response = effective_hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                    session_state.metadata.updated_at = now_iso8601()

                    # Checkpoint session
                    await session_repo.save(session_state, "")

                    logger.info(
                        "branch_hitl_resume_checkpointed",
                        session_id=session_state.metadata.session_id,
                        branch_id=branch.id,
                        step=hitl_state_dict["step_index"],
                        response_length=len(effective_hitl_response),
                        from_checkpoint=hitl_response is None,
                    )
                else:
                    # No session repo - just update in-memory state
                    if session_state:
                        hitl_state = HITLState(**hitl_state_dict)
                        hitl_state.active = False
                        hitl_state.user_response = effective_hitl_response
                        session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                    logger.warning(
                        "branch_hitl_resume_without_checkpoint",
                        branch_id=branch.id,
                        message="HITL response not persisted - crash will lose progress",
                    )

                logger.info(
                    "branch_hitl_response_received",
                    branch_id=branch.id,
                    step=hitl_state_dict["step_index"],
                    response_preview=effective_hitl_response[:100]
                    if len(effective_hitl_response) > 100
                    else effective_hitl_response,
                    from_checkpoint=hitl_response is None,
                )

    # Execute steps from start_step onward
    for step_index in range(start_step, len(branch.steps)):
        step = branch.steps[step_index]

        # Phase 2.2 HITL: Check if this is a HITL step
        if hasattr(step, "type") and step.type == "hitl":
            # BLOCKER: Validate session persistence is available
            if not session_repo or not session_state:
                raise ParallelExecutionError(
                    f"HITL step in branch '{branch.id}' at step {step_index} requires "
                    f"session persistence. Remove --no-save-session flag or remove HITL steps."
                )

            logger.info(
                "branch_hitl_pause",
                branch_id=branch.id,
                step=step_index,
            )

            # Build context for this branch (steps[] = this branch only)
            step_context = _build_branch_step_context(
                spec=spec,
                step_index=step_index,
                step_history=step_history,
                user_variables=user_variables,
                step_vars=None,
            )

            # Render context_display template
            context_text = ""
            if step.context_display:
                context_text = render_template(step.context_display, step_context)

            # Calculate timeout
            timeout_at = None
            if step.timeout_seconds and step.timeout_seconds > 0:
                timeout_dt = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)
                timeout_at = timeout_dt.isoformat()

            # Create HITL state
            hitl_state = HITLState(
                active=True,
                step_index=step_index,
                branch_id=branch.id,
                step_type="branch",
                prompt=step.prompt,
                context_display=context_text,
                default_response=step.default,
                timeout_at=timeout_at,
                user_response=None,
            )

            # Return HITL pause info to caller (run_parallel will save session and exit)
            return {
                "hitl_pause": True,
                "branch_id": branch.id,
                "step_index": step_index,
                "hitl_state": hitl_state,
                "step_history": step_history,
                "cumulative_tokens": cumulative_tokens,
            }

        # Regular agent step execution
        logger.info(
            "Executing branch step",
            branch_id=branch.id,
            step_index=step_index,
            agent=step.agent,
        )

        # Build context with prior steps in THIS branch
        step_context = _build_branch_step_context(
            spec=spec,
            step_index=step_index,
            step_history=step_history,
            user_variables=user_variables,
            step_vars=step.vars,
        )

        # Render input template
        step_input = render_template(step.input or "", step_context)

        # Build agent for step (using cache to avoid rebuilds)
        if step.agent not in spec.agents:
            raise ParallelExecutionError(
                f"Branch '{branch.id}' step {step_index} references unknown agent '{step.agent}'"
            )

        agent_config = spec.agents[step.agent]

        # Phase 6.2: Inject last N notes into agent context
        injected_notes = None
        if notes_manager and spec.context_policy and spec.context_policy.notes:
            injected_notes = notes_manager.get_last_n_for_injection(
                spec.context_policy.notes.include_last
            )

        agent = await cache.get_or_build_agent(
            spec=spec,
            agent_id=step.agent,
            agent_config=agent_config,
            tool_overrides=step.tool_overrides,
            conversation_manager=context_manager,
            hooks=hooks,
            injected_notes=injected_notes,
            worker_index=None,
        )

        # Phase 3: Emit branch_start event before agent invocation
        if event_bus:
            await event_bus.emit(
                WorkflowEvent(
                    event_type="branch_start",
                    timestamp=datetime.now(UTC),
                    session_id=session_state.metadata.session_id if session_state else None,
                    spec_name=spec.name,
                    pattern_type="parallel",
                    data={
                        "branch_id": branch.id,
                        "step_index": step_index,
                        "agent_id": step.agent,
                        "branch_count": len(spec.pattern.config.branches)
                        if spec.pattern.config.branches
                        else 0,
                        "input_preview": step_input[:200] if step_input else "",
                    },
                )
            )
            logger.debug(
                "branch_start_event_emitted",
                branch=branch.id,
                step=step_index,
                agent=step.agent,
            )

        # Execute with retry logic
        try:
            response = await invoke_agent_with_retry(
                agent, step_input, max_attempts, wait_min, wait_max
            )
            response_text = response if isinstance(response, str) else str(response)
        except Exception as e:
            logger.error(
                "Branch step failed",
                branch_id=branch.id,
                step_index=step_index,
                agent=step.agent,
                error=str(e),
            )
            raise ParallelExecutionError(
                f"Branch '{branch.id}' step {step_index} (agent '{step.agent}') failed: {e}"
            ) from e

        # Estimate tokens using shared estimator
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
            "Branch step completed",
            branch_id=branch.id,
            step_index=step_index,
            agent=step.agent,
            tokens_estimated=estimated_tokens,
        )

    # Return final response from last step
    final_response = step_history[-1]["response"]
    logger.info(
        "Branch completed",
        branch_id=branch.id,
        total_steps=len(step_history),
        cumulative_tokens=cumulative_tokens,
    )

    # Emit branch_complete event
    if event_bus:
        await event_bus.emit(
            WorkflowEvent(
                event_type="branch_complete",
                timestamp=datetime.now(UTC),
                session_id=session_state.metadata.session_id if session_state else None,
                spec_name=spec.name,
                pattern_type="parallel",
                data={
                    "branch_id": branch.id,
                    "response_length": len(final_response),
                    "cumulative_tokens": cumulative_tokens,
                },
            )
        )

    return final_response, cumulative_tokens, step_history


async def _execute_reduce_step(
    spec: Spec,
    reduce_config: Any,
    user_vars: dict[str, Any],
    branches_dict: dict[str, dict[str, Any]],
    cache: AgentCache,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> tuple[str, int]:
    """Execute reduce step to aggregate branch results.

    Args:
        spec: Workflow spec
        reduce_config: Reduce step configuration
        user_vars: User-provided variables
        branches_dict: Dictionary of branch results
        cache: Shared AgentCache for agent reuse
        max_attempts: Maximum retry attempts
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)

    Returns:
        Tuple of (reduce_response, tokens_estimated)

    Raises:
        ParallelExecutionError: If reduce step fails
    """
    logger.info("Executing reduce step", agent=reduce_config.agent)

    # Build reduce context with branches dictionary
    reduce_context = {
        **user_vars,
        "branches": branches_dict,
    }

    # Render reduce input
    reduce_input = render_template(reduce_config.input or "", reduce_context)

    # Build reduce agent (using cache to avoid rebuilds)
    if reduce_config.agent not in spec.agents:
        raise ParallelExecutionError(
            f"Reduce step references unknown agent '{reduce_config.agent}'"
        )

    reduce_agent_config = spec.agents[reduce_config.agent]

    # Phase 6.2: Inject last N notes into agent context
    injected_notes = None
    if notes_manager and spec.context_policy and spec.context_policy.notes:
        injected_notes = notes_manager.get_last_n_for_injection(
            spec.context_policy.notes.include_last
        )

    reduce_agent = await cache.get_or_build_agent(
        spec=spec,
        agent_id=reduce_config.agent,
        agent_config=reduce_agent_config,
        tool_overrides=reduce_config.tool_overrides,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=injected_notes,
        worker_index=None,
    )

    # Execute reduce with retry
    try:
        reduce_response = await invoke_agent_with_retry(
            reduce_agent, reduce_input, max_attempts, wait_min, wait_max
        )
        final_response = (
            reduce_response if isinstance(reduce_response, str) else str(reduce_response)
        )

        # Track reduce tokens using shared estimator
        reduce_tokens = estimate_tokens(reduce_input, final_response)

        logger.info(
            "Reduce step completed",
            agent=reduce_config.agent,
            tokens_estimated=reduce_tokens,
        )

        return final_response, reduce_tokens

    except Exception as e:
        logger.error("Reduce step failed", error=str(e))
        raise ParallelExecutionError(f"Reduce step failed: {e}") from e


async def _execute_all_branches_async(
    spec: Spec,
    branches: list[ParallelBranch],
    user_vars: dict[str, Any],
    cache: AgentCache,
    max_parallel: int | None,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
    completed_branches: set[str] | None = None,
    branch_results_dict: dict[str, dict[str, Any]] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
    event_bus: EventBus | None = None,
) -> list[tuple[str, tuple[str, int, list[dict[str, Any]]] | dict[str, Any]]]:
    """Execute all branches with semaphore control, resume support, and HITL support.

    Args:
        spec: Workflow spec
        branches: List of branches to execute
        user_vars: User-provided variables
        cache: Shared AgentCache for agent reuse
        max_parallel: Maximum concurrent branches (None for unlimited)
        max_attempts: Maximum retry attempts per step
        wait_min: Minimum wait time for exponential backoff (seconds)
        wait_max: Maximum wait time for exponential backoff (seconds)
        context_manager: Optional conversation manager
        hooks: Optional agent hooks
        notes_manager: Optional notes manager
        completed_branches: Set of already-completed branch IDs (for resume)
        branch_results_dict: Previously completed branch results (for resume)
        session_state: Session state for HITL pause/resume
        session_repo: Repository for saving session on HITL pause
        hitl_response: User's response when resuming from HITL pause

    Returns:
        List of (branch_id, (response, tokens, step_history) OR hitl_pause_dict) tuples

    Raises:
        ParallelExecutionError: If any branch fails (fail-fast)
    """
    completed_branches = completed_branches or set()
    branch_results_dict = branch_results_dict or {}

    semaphore = asyncio.Semaphore(max_parallel) if max_parallel else None

    async def _execute_with_semaphore(
        branch: ParallelBranch,
    ) -> tuple[str, tuple[str, int, list[dict[str, Any]]] | dict[str, Any]]:
        """Execute branch with semaphore limit or return cached result."""
        # Return cached result if branch already completed
        if branch.id in completed_branches:
            cached = branch_results_dict[branch.id]
            logger.info(
                "Branch restored from checkpoint",
                branch_id=branch.id,
                tokens=cached["tokens_estimated"],
            )
            return (
                branch.id,
                (
                    cached["response"],
                    cached["tokens_estimated"],
                    cached.get("step_history", []),
                ),
            )

        # Execute branch (with semaphore if configured)
        if semaphore:
            async with semaphore:
                result = await _execute_branch(
                    spec,
                    branch,
                    user_vars,
                    cache,
                    max_attempts,
                    wait_min,
                    wait_max,
                    context_manager,
                    hooks,
                    notes_manager,
                    start_step=0,
                    restored_step_history=None,
                    session_state=session_state,
                    session_repo=session_repo,
                    hitl_response=hitl_response,
                    event_bus=event_bus,
                )
        else:
            result = await _execute_branch(
                spec,
                branch,
                user_vars,
                cache,
                max_attempts,
                wait_min,
                wait_max,
                context_manager,
                hooks,
                notes_manager,
                start_step=0,
                restored_step_history=None,
                session_state=session_state,
                session_repo=session_repo,
                hitl_response=hitl_response,
                event_bus=event_bus,
            )
        return (branch.id, result)

    # Execute all branches in parallel (fail-fast with return_exceptions=False)
    results = await asyncio.gather(
        *[_execute_with_semaphore(branch) for branch in branches],
        return_exceptions=False,  # Fail-fast on first error
    )
    return results


async def run_parallel(  # noqa: C901 - Complexity acceptable for multi-branch orchestration
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
    event_bus: EventBus | None = None,
    agent_cache: AgentCache | None = None,
) -> RunResult:
    """Execute parallel pattern with concurrent branches, optional session persistence, and HITL support.

    Phase 6 Performance Optimization:
    - Async execution with shared AgentCache across all branches and reduce step
    - Single event loop eliminates per-branch loop churn
    - Agents reused when branches use same agent configuration

    Phase 3.2 Session Support:
    - Resume from checkpoint: Skip completed branches on resume
    - Branch-level checkpointing: Save state after all branches complete
    - Reduce gate: Execute reduce step once after all branches

    Phase 2.2 HITL Support:
    - Branch-level HITL: Pause individual branches for human review
    - Reduce-level HITL: Pause at aggregation step to review all branch outputs
    - Session persistence required for HITL steps

    Args:
        spec: Validated workflow spec with parallel pattern
        variables: CLI --var overrides
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)

    Returns:
        RunResult with final response (reduced or aggregated)

    Raises:
        ParallelExecutionError: If validation, execution, or reduce fails
        ValueError: If session_state and session_repo not both provided or both None
    """
    # Validate session parameters (both or neither)
    if (session_state is None) != (session_repo is None):
        raise ValueError("session_state and session_repo must both be provided or both be None")

    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("execute.parallel") as span:
        # Add span attributes
        span.set_attribute("spec.name", spec.name)
        span.set_attribute("spec.version", spec.version or 0)
        span.set_attribute("pattern.type", "parallel")
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id or "default")
        if spec.runtime.region:
            span.set_attribute("runtime.region", spec.runtime.region)

        # Add execution start event
        span.add_event("execution_start")

        # Determine starting point and restore state for resume
        if session_state:
            # Resume mode: restore branch results and reduce state
            completed_branches = set(session_state.pattern_state.get("completed_branches", []))
            branch_results_dict = session_state.pattern_state.get("branch_results", {})
            reduce_executed = session_state.pattern_state.get("reduce_executed", False)
            cumulative_tokens = (
                session_state.token_usage.total_input_tokens
                + session_state.token_usage.total_output_tokens
            )
            started_at = session_state.metadata.created_at
            logger.info(
                "parallel_resume",
                session_id=session_state.metadata.session_id,
                completed_branches=len(completed_branches),
                reduce_executed=reduce_executed,
            )
            span.add_event(
                "parallel_resume",
                {
                    "session_id": session_state.metadata.session_id,
                    "completed_branches": len(completed_branches),
                    "reduce_executed": reduce_executed,
                },
            )
        else:
            # Fresh start
            completed_branches = set()
            branch_results_dict = {}
            reduce_executed = False
            cumulative_tokens = 0
            started_at = datetime.now(UTC).isoformat()

        start_time = datetime.now(UTC)

        # Validate configuration
        if not spec.pattern.config.branches or len(spec.pattern.config.branches) < 2:
            raise ParallelExecutionError("Parallel pattern requires at least 2 branches")

        span.set_attribute("parallel.branch_count", len(spec.pattern.config.branches))
        span.set_attribute("parallel.has_reduce", spec.pattern.config.reduce is not None)

        # Get retry configuration
        max_attempts, wait_min, wait_max = get_retry_config(spec)

        # Build user variables (spec.inputs.values + CLI --var)
        user_vars: dict[str, Any] = {}
        if spec.inputs and spec.inputs.get("values"):
            user_vars.update(spec.inputs["values"])
        if variables:
            user_vars.update(variables)

        # Get max_parallel limit
        max_parallel = spec.runtime.max_parallel
        if max_parallel:
            span.set_attribute("parallel.max_parallel", max_parallel)

        # Get budget configuration
        max_tokens = None
        if spec.runtime.budgets:
            max_tokens = spec.runtime.budgets.get("max_tokens")

        logger.info(
            "Starting parallel execution",
            num_branches=len(spec.pattern.config.branches),
            max_parallel=max_parallel,
            max_tokens=max_tokens,
        )

        # Phase 6.1: Create context manager and hooks for compaction
        context_manager = create_from_policy(spec.context_policy, spec)
        hooks: list[Any] = []
        if (
            spec.context_policy
            and spec.context_policy.compaction
            and spec.context_policy.compaction.enabled
        ):
            threshold = spec.context_policy.compaction.when_tokens_over or 60000
            hooks.append(
                ProactiveCompactionHook(threshold_tokens=threshold, model_id=spec.runtime.model_id)
            )
            logger.info("compaction_enabled", threshold_tokens=threshold)

        # Phase 6.4: Add budget enforcer hook (runs AFTER compaction to allow token reduction)
        if spec.runtime.budgets and spec.runtime.budgets.get("max_tokens"):
            from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

            max_tokens = spec.runtime.budgets["max_tokens"]
            warn_threshold = spec.runtime.budgets.get("warn_threshold", 0.8)
            hooks.append(BudgetEnforcerHook(max_tokens=max_tokens, warn_threshold=warn_threshold))
            logger.info(
                "budget_enforcer_enabled", max_tokens=max_tokens, warn_threshold=warn_threshold
            )

        # Phase 6.2: Initialize notes manager and hook for structured notes
        notes_manager = None
        step_counter = [0]  # Mutable container for hook to track step count across all branches
        if spec.context_policy and spec.context_policy.notes:
            notes_manager = NotesManager(spec.context_policy.notes.file)

            # Build agent_id → tools mapping for notes hook
            agent_tools: dict[str, list[str]] = {}
            for agent_id, agent_config in spec.agents.items():
                if agent_config.tools:
                    agent_tools[agent_id] = agent_config.tools

            hooks.append(NotesAppenderHook(notes_manager, step_counter, agent_tools))
            logger.info("notes_enabled", notes_file=spec.context_policy.notes.file)

        # Create AgentCache for this execution
        cache = agent_cache or AgentCache()
        should_close = agent_cache is None

        try:
            # Execute all branches concurrently (skip already completed branches on resume)
            try:
                branch_exec_results = await _execute_all_branches_async(
                    spec,
                    spec.pattern.config.branches,
                    user_vars,
                    cache,
                    max_parallel,
                    max_attempts,
                    wait_min,
                    wait_max,
                    context_manager,
                    hooks,
                    notes_manager,
                    completed_branches,
                    branch_results_dict,
                    session_state,
                    session_repo,
                    hitl_response,
                    event_bus,
                )
            except Exception as e:
                end_time = datetime.now(UTC)
                duration = (end_time - start_time).total_seconds()

                logger.error(
                    "Parallel execution failed",
                    error=str(e),
                    duration_seconds=duration,
                )

                return RunResult(
                    success=False,
                    error=str(e),
                    agent_id="parallel",
                    pattern_type=PatternType.PARALLEL,
                    started_at=started_at,
                    completed_at=end_time.isoformat(),
                    duration_seconds=duration,
                )

            # Build branches dictionary (alphabetically ordered by branch ID)
            branches_dict: dict[str, dict[str, Any]] = {}

            # Phase 2.2 HITL: Check if any branch returned HITL pause
            for branch_id, result in branch_exec_results:
                if isinstance(result, dict) and result.get("hitl_pause"):
                    # Branch hit HITL step - save session and exit
                    hitl_info = result
                    hitl_state = hitl_info["hitl_state"]

                    # CRITICAL: Populate branches_dict with completed (non-HITL) branches BEFORE pausing
                    for other_branch_id, other_result in branch_exec_results:
                        if not (isinstance(other_result, dict) and other_result.get("hitl_pause")):
                            other_response, other_tokens, other_step_history = other_result
                            # Ensure tokens is an integer
                            other_tokens_int = other_tokens if isinstance(other_tokens, int) else 0
                            if other_branch_id not in completed_branches:
                                cumulative_tokens += other_tokens_int
                                completed_branches.add(other_branch_id)
                            branches_dict[other_branch_id] = {
                                "response": other_response,
                                "status": "success",
                                "tokens_estimated": other_tokens_int,
                                "step_history": other_step_history,
                            }

                    # Save session with branch HITL state
                    if session_state and session_repo:
                        session_state.pattern_state["current_step"] = hitl_info["step_index"]
                        session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                        session_state.pattern_state["completed_branches"] = list(completed_branches)
                        session_state.pattern_state["branch_results"] = branches_dict
                        session_state.pattern_state["reduce_executed"] = False
                        # Persist branch step_history so resume can restore pre-HITL context
                        if "branch_states" not in session_state.pattern_state:
                            session_state.pattern_state["branch_states"] = {}
                        session_state.pattern_state["branch_states"][branch_id] = {
                            "step_history": hitl_info["step_history"],
                            "current_step": hitl_info["step_index"],
                            "cumulative_tokens": hitl_info["cumulative_tokens"],
                        }
                        # CRITICAL: Persist token usage before pause to prevent budget bypass on resume
                        pause_tokens = cumulative_tokens + hitl_info["cumulative_tokens"]
                        session_state.token_usage.total_input_tokens = pause_tokens // 2
                        session_state.token_usage.total_output_tokens = (
                            pause_tokens - session_state.token_usage.total_input_tokens
                        )
                        session_state.metadata.status = SessionStatus.PAUSED
                        session_state.metadata.updated_at = now_iso8601()

                        try:
                            spec_content = ""  # Spec already saved
                            await session_repo.save(session_state, spec_content)
                            logger.info(
                                "branch_hitl_pause_saved",
                                session_id=session_state.metadata.session_id,
                                branch_id=branch_id,
                                step=hitl_info["step_index"],
                            )
                        except Exception as e:
                            logger.error(
                                "branch_hitl_pause_save_failed",
                                session_id=session_state.metadata.session_id,
                                error=str(e),
                            )
                            raise ParallelExecutionError(
                                f"Failed to save branch HITL pause state: {e}"
                            ) from e

                    # Display HITL prompt to user
                    console.print()
                    console.print(
                        Panel(
                            f"[bold yellow]>>> HUMAN INPUT REQUIRED <<<[/bold yellow]\n\n"
                            f"Branch: {branch_id}\n"
                            f"Step: {hitl_info['step_index']}\n\n"
                            f"{hitl_state.prompt}",
                            border_style="yellow",
                            padding=(1, 2),
                            title="HITL Pause (Branch)",
                        )
                    )

                    if hitl_state.context_display:
                        console.print(
                            Panel(
                                f"[bold]Context:[/bold]\n\n{hitl_state.context_display}",
                                border_style="dim",
                                padding=(1, 2),
                            )
                        )

                    console.print(
                        f"\n[dim]Resume with:[/dim] strands run --resume "
                        f"{session_state.metadata.session_id if session_state else 'SESSION_ID'} "
                        f'--hitl-response "your response"'
                    )

                    # Return HITL pause result
                    end_time = datetime.now(UTC)
                    duration = (end_time - start_time).total_seconds()

                    return RunResult(
                        success=True,
                        last_response=f"Branch HITL pause at {branch_id} step {hitl_info['step_index']}",
                        pattern_type=PatternType.PARALLEL,
                        agent_id="hitl",
                        started_at=started_at,
                        completed_at=end_time.isoformat(),
                        duration_seconds=duration,
                        exit_code=EX_HITL_PAUSE,
                        tokens_estimated=cumulative_tokens + hitl_info["cumulative_tokens"],
                        execution_context={
                            "session_id": session_state.metadata.session_id
                            if session_state
                            else None,
                            "branch_id": branch_id,
                            "step_index": hitl_info["step_index"],
                        },
                    )  # Clear hitl_state after successful branch resume
            if session_state and hitl_response and session_state.pattern_state.get("hitl_state"):
                hitl_state_dict = session_state.pattern_state["hitl_state"]
                if hitl_state_dict.get("step_type") == "branch":
                    session_state.pattern_state["hitl_state"] = None
                    logger.debug("branch_hitl_state_cleared")

            # Process results from branch execution (skip HITL pauses which were already handled)
            for branch_id, result in branch_exec_results:
                # Skip HITL pauses (already handled above)
                if isinstance(result, dict) and result.get("hitl_pause"):
                    continue

                # Unpack regular branch result
                # Result is guaranteed to be a tuple here (dict case filtered above)
                branch_response: str
                branch_tokens: int | str
                branch_step_history: list[dict[str, Any]]
                if isinstance(result, tuple):
                    branch_response, branch_tokens, branch_step_history = result
                else:
                    # Should never happen due to filter above, but satisfy type checker
                    continue

                # Ensure tokens is an integer
                branch_tokens_int = branch_tokens if isinstance(branch_tokens, int) else 0

                # Update cumulative tokens (only for newly executed branches)
                if branch_id not in completed_branches:
                    cumulative_tokens += branch_tokens_int
                    completed_branches.add(branch_id)

                branches_dict[branch_id] = {
                    "response": branch_response,
                    "status": "success",
                    "tokens_estimated": branch_tokens_int,
                    "step_history": branch_step_history,
                }
                # Add branch_complete event for each branch
                span.add_event(
                    "branch_complete",
                    {
                        "branch_id": branch_id,
                        "response_length": len(branch_response),
                        "tokens": branch_tokens_int,
                    },
                )

            logger.info(
                "All branches completed",
                num_branches=len(branches_dict),
                cumulative_tokens=cumulative_tokens,
            )

            # Checkpoint after all branches complete (before reduce)
            if session_state and session_repo and not reduce_executed:
                session_state.pattern_state["completed_branches"] = list(completed_branches)
                session_state.pattern_state["branch_results"] = branches_dict
                session_state.pattern_state["reduce_executed"] = False
                session_state.metadata.updated_at = now_iso8601()
                session_state.metadata.status = SessionStatus.RUNNING
                session_state.token_usage.total_input_tokens = cumulative_tokens // 2
                session_state.token_usage.total_output_tokens = cumulative_tokens // 2

                try:
                    spec_content = ""  # Spec snapshot already saved at session creation
                    await session_repo.save(session_state, spec_content)
                    logger.debug(
                        "parallel_branches_checkpointed",
                        session_id=session_state.metadata.session_id,
                        completed_branches=len(completed_branches),
                    )
                except Exception as e:
                    logger.warning(
                        "parallel_checkpoint_failed",
                        session_id=session_state.metadata.session_id,
                        error=str(e),
                    )

            # Execute reduce step if present or aggregate branches
            final_response: str
            final_agent_id: str

            if spec.pattern.config.reduce:
                # Check for timeout on reduce HITL when resuming from pause
                if session_state and not reduce_executed:
                    hitl_state_dict = session_state.pattern_state.get("hitl_state")
                    if hitl_state_dict and hitl_state_dict.get("step_type") == "reduce":
                        timed_out, timeout_default = check_hitl_timeout(session_state)
                        if timed_out and not hitl_response:
                            console.print(
                                Panel(
                                    format_timeout_warning(
                                        hitl_state_dict.get("timeout_at"),
                                        timeout_default,
                                    ),
                                    border_style="yellow",
                                )
                            )
                            hitl_response = timeout_default

                            # Record timeout metadata in pattern_state and session metadata
                            session_state.pattern_state["hitl_timeout_occurred"] = True
                            session_state.pattern_state["hitl_timeout_at"] = hitl_state_dict.get(
                                "timeout_at"
                            )
                            session_state.pattern_state["hitl_default_used"] = timeout_default

                            session_state.metadata.metadata["hitl_timeout_occurred"] = True
                            session_state.metadata.metadata["hitl_timeout_at"] = (
                                hitl_state_dict.get("timeout_at")
                            )
                            session_state.metadata.metadata["hitl_default_used"] = timeout_default

                # Phase 2.2 HITL: Check if reduce is HITL step
                if (
                    hasattr(spec.pattern.config.reduce, "type")
                    and spec.pattern.config.reduce.type == "hitl"
                ):
                    # Reduce HITL step
                    if not reduce_executed and not hitl_response:
                        # First time reaching reduce - pause for user input

                        # BLOCKER: Validate session persistence
                        if not session_repo or not session_state:
                            raise ParallelExecutionError(
                                "HITL reduce step requires session persistence. "
                                "Remove --no-save-session flag or remove HITL from reduce."
                            )

                        logger.info("reduce_hitl_pause")

                        # Build context with all branches
                        reduce_context = {
                            **user_vars,
                            "branches": branches_dict,
                        }

                        # Render context_display
                        context_text = ""
                        if spec.pattern.config.reduce.context_display:
                            context_text = render_template(
                                spec.pattern.config.reduce.context_display, reduce_context
                            )

                        # Calculate timeout
                        timeout_at = None
                        if (
                            spec.pattern.config.reduce.timeout_seconds
                            and spec.pattern.config.reduce.timeout_seconds > 0
                        ):
                            timeout_dt = datetime.now(UTC) + timedelta(
                                seconds=spec.pattern.config.reduce.timeout_seconds
                            )
                            timeout_at = timeout_dt.isoformat()

                        # Create HITL state
                        hitl_state = HITLState(
                            active=True,
                            step_type="reduce",
                            prompt=spec.pattern.config.reduce.prompt,
                            context_display=context_text,
                            default_response=spec.pattern.config.reduce.default,
                            timeout_at=timeout_at,
                            user_response=None,
                        )

                        # Save session with reduce HITL state
                        session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                        session_state.pattern_state["completed_branches"] = list(completed_branches)
                        session_state.pattern_state["branch_results"] = branches_dict
                        session_state.pattern_state["reduce_executed"] = False
                        # CRITICAL: Persist token usage before pause to prevent budget bypass on resume
                        session_state.token_usage.total_input_tokens = cumulative_tokens // 2
                        session_state.token_usage.total_output_tokens = (
                            cumulative_tokens - session_state.token_usage.total_input_tokens
                        )
                        session_state.metadata.status = SessionStatus.PAUSED
                        session_state.metadata.updated_at = now_iso8601()

                        try:
                            spec_content = ""
                            await session_repo.save(session_state, spec_content)
                            logger.info(
                                "reduce_hitl_pause_saved",
                                session_id=session_state.metadata.session_id,
                            )
                        except Exception as e:
                            logger.error(
                                "reduce_hitl_pause_save_failed",
                                session_id=session_state.metadata.session_id,
                                error=str(e),
                            )
                            raise ParallelExecutionError(
                                f"Failed to save reduce HITL pause state: {e}"
                            ) from e

                        # Display HITL prompt
                        console.print()
                        console.print(
                            Panel(
                                f"[bold yellow]>>> HUMAN INPUT REQUIRED <<<[/bold yellow]\n\n"
                                f"{spec.pattern.config.reduce.prompt}",
                                border_style="yellow",
                                padding=(1, 2),
                                title="HITL Pause (Reduce)",
                            )
                        )

                        if context_text:
                            console.print(
                                Panel(
                                    f"[bold]All Branch Results:[/bold]\n\n{context_text}",
                                    border_style="dim",
                                    padding=(1, 2),
                                )
                            )

                        console.print(
                            f"\n[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} "
                            f'--hitl-response "your response"'
                        )

                        # Return HITL pause result
                        end_time = datetime.now(UTC)
                        duration = (end_time - start_time).total_seconds()

                        return RunResult(
                            success=True,
                            last_response=f"Reduce HITL pause: {spec.pattern.config.reduce.prompt}",
                            pattern_type=PatternType.PARALLEL,
                            agent_id="hitl",
                            started_at=started_at,
                            completed_at=end_time.isoformat(),
                            duration_seconds=duration,
                            exit_code=EX_HITL_PAUSE,
                            tokens_estimated=cumulative_tokens,
                            execution_context={
                                "session_id": session_state.metadata.session_id,
                                "reduce_hitl": True,
                            },
                        )
                    else:
                        # Resumed from reduce HITL - use user response as final result
                        final_response = hitl_response or ""
                        final_agent_id = "parallel"  # NOT 'hitl' - prevents CLI infinite pause loop
                        reduce_executed = True

                        logger.info(
                            "reduce_hitl_resumed",
                            session_id=session_state.metadata.session_id if session_state else None,
                            response_preview=final_response[:100]
                            if len(final_response) > 100
                            else final_response,
                        )

                        # Clear HITL state and mark reduce as executed
                        if session_state:
                            session_state.pattern_state["hitl_state"] = None
                            session_state.pattern_state["reduce_executed"] = True
                            session_state.pattern_state["final_response"] = final_response
                            session_state.metadata.updated_at = now_iso8601()
                            logger.debug("reduce_hitl_state_cleared")

                        # Checkpoint session after reduce HITL resume
                        if session_repo and session_state:
                            session_state.metadata.updated_at = now_iso8601()
                            try:
                                spec_content = ""
                                await session_repo.save(session_state, spec_content)
                                logger.info(
                                    "reduce_hitl_resume_checkpointed",
                                    session_id=session_state.metadata.session_id,
                                )
                            except Exception as e:
                                logger.error(
                                    "reduce_hitl_resume_checkpoint_failed",
                                    session_id=session_state.metadata.session_id,
                                    error=str(e),
                                )
                                # Log warning but continue - checkpoint failure shouldn't block execution
                                logger.warning(
                                    "reduce_hitl_resume_without_checkpoint",
                                    message="HITL response not persisted - workflow crash will lose user input",
                                )

                elif not reduce_executed:
                    # Regular agent reduce step
                    span.add_event("reduce_start")
                    reduce_response, reduce_tokens = await _execute_reduce_step(
                        spec,
                        spec.pattern.config.reduce,
                        user_vars,
                        branches_dict,
                        cache,
                        max_attempts,
                        wait_min,
                        wait_max,
                        context_manager,
                        hooks,
                        notes_manager,
                    )
                    final_response = reduce_response
                    assert spec.pattern.config.reduce.agent is not None
                    final_agent_id = spec.pattern.config.reduce.agent
                    cumulative_tokens += reduce_tokens
                    reduce_executed = True

                    # Checkpoint after reduce
                    if session_state and session_repo:
                        session_state.pattern_state["reduce_executed"] = True
                        session_state.pattern_state["final_response"] = final_response
                        session_state.metadata.updated_at = now_iso8601()
                        session_state.token_usage.total_input_tokens = cumulative_tokens // 2
                        session_state.token_usage.total_output_tokens = cumulative_tokens // 2

                        try:
                            spec_content = ""
                            await session_repo.save(session_state, spec_content)
                            logger.debug(
                                "parallel_reduce_checkpointed",
                                session_id=session_state.metadata.session_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "parallel_reduce_checkpoint_failed",
                                session_id=session_state.metadata.session_id,
                                error=str(e),
                            )
                else:
                    # Reduce already executed on previous run - restore from checkpoint
                    assert (
                        session_state is not None
                    )  # For type checker (already validated reduce_executed implies session_state)
                    final_response = session_state.pattern_state.get("final_response", "")
                    assert spec.pattern.config.reduce.agent is not None
                    final_agent_id = spec.pattern.config.reduce.agent
                    logger.info(
                        "Reduce step restored from checkpoint",
                        session_id=session_state.metadata.session_id,
                    )
            else:
                # No reduce step - aggregate branch responses alphabetically
                logger.info("No reduce step - aggregating branch responses")

                aggregated_parts = [
                    f"Branch {bid}:\n{bdata['response']}"
                    for bid, bdata in sorted(branches_dict.items())
                ]
                final_response = "\n\n---\n\n".join(aggregated_parts)
                final_agent_id = "parallel"

            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            logger.info(
                "Parallel execution completed",
                duration_seconds=duration,
                cumulative_tokens=cumulative_tokens,
            )
            span.add_event(
                "execution_complete",
                {
                    "duration_seconds": duration,
                    "branch_count": len(branches_dict),
                    "cumulative_tokens": cumulative_tokens,
                },
            )

            # Mark session as completed if session persistence enabled
            if session_state and session_repo:
                session_state.metadata.status = SessionStatus.COMPLETED
                session_state.metadata.updated_at = now_iso8601()
                try:
                    spec_content = ""  # Spec snapshot already saved
                    await session_repo.save(session_state, spec_content)
                    logger.info(
                        "parallel_session_completed",
                        session_id=session_state.metadata.session_id,
                    )
                except Exception as e:
                    logger.warning(
                        "parallel_session_completion_failed",
                        session_id=session_state.metadata.session_id,
                        error=str(e),
                    )

            return RunResult(
                success=True,
                last_response=final_response,
                agent_id=final_agent_id,
                pattern_type=PatternType.PARALLEL,
                started_at=started_at,
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                exit_code=EX_OK,
                tokens_estimated=cumulative_tokens,
                execution_context={"branches": branches_dict},
            )
        except Exception as e:
            # Mark session as failed before re-raising
            if session_state and session_repo:
                await fail_session(session_state, session_repo, e)

            # Re-raise parallel execution errors
            if isinstance(e, ParallelExecutionError):
                raise
            raise ParallelExecutionError(f"Parallel execution failed: {e}") from e
        finally:
            # Clean up cached resources
            if should_close:
                await cache.close()

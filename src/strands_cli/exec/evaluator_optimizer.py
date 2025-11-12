"""Evaluator-optimizer pattern executor.

Executes iterative refinement pattern with producer-evaluator feedback loops.
Producer generates draft, evaluator scores and critiques, producer revises based on feedback.

Execution Flow:
    1. Validate evaluator-optimizer configuration
    2. Execute producer agent to generate initial draft
    3. Evaluation loop (up to max_iters):
        a. Execute evaluator agent with current draft
        b. Parse JSON response: {"score": int, "issues": [...], "fixes": [...]}
        c. Retry once on malformed JSON with clarification prompt
        d. If score >= min_score → SUCCESS, return draft
        e. If score < min_score → prepare revision context
        f. Execute producer agent with revision prompt + evaluator feedback
    4. If max_iters exhausted → FAILURE with detailed iteration history

Evaluator Output:
    - Expected JSON: {"score": 0-100, "issues": ["..."], "fixes": ["..."]}
    - Parsing strategies: direct JSON, extract JSON block, regex extraction
    - Retry once with clarification prompt on malformed responses

Template Context (Revision):
    - {{ draft }}: Current draft text
    - {{ evaluation.score }}: Current score (0-100)
    - {{ evaluation.issues }}: List of identified issues
    - {{ evaluation.fixes }}: List of suggested fixes
    - {{ iteration }}: Current iteration number (1-based)

Error Handling:
    - Malformed evaluator JSON → retry once with clarification
    - Max iterations exhausted → raise EvaluatorOptimizerExecutionError with history
    - No fallback behavior (explicit failures only)
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from strands_cli.events import EventBus, WorkflowEvent
from strands_cli.exec.hitl_utils import check_hitl_timeout, format_timeout_warning
from strands_cli.exec.hooks import ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.exit_codes import EX_OK
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.checkpoint_utils import (
    checkpoint_pattern_state,
    fail_session,
    finalize_session,
    get_cumulative_tokens,
    validate_session_params,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import now_iso8601
from strands_cli.telemetry import get_tracer
from strands_cli.types import EvaluatorDecision, HITLState, PatternType, RunResult, Spec


class EvaluatorOptimizerExecutionError(Exception):
    """Raised when evaluator-optimizer execution fails."""

    pass


logger = structlog.get_logger(__name__)
console = Console()


async def _run_initial_production(
    producer_agent: Any,
    initial_prompt: str,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[str, int]:
    """Execute initial production phase.

    Args:
        producer_agent: The producer agent
        initial_prompt: Initial prompt for production
        max_attempts: Max retry attempts
        wait_min: Min wait time for retries
        wait_max: Max wait time for retries

    Returns:
        Tuple of (draft, estimated_tokens)
    """
    logger.info("iteration_start", iteration=1, phase="production")
    producer_response = await invoke_agent_with_retry(
        producer_agent, initial_prompt, max_attempts, wait_min, wait_max
    )
    draft = producer_response if isinstance(producer_response, str) else str(producer_response)
    estimated_tokens = estimate_tokens(initial_prompt, draft)
    return draft, estimated_tokens


async def _run_evaluation_phase(
    evaluator_agent: Any,
    current_draft: str,
    config: Any,
    variables: dict[str, str] | None,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> tuple[str, int]:
    """Execute evaluation phase.

    Args:
        evaluator_agent: The evaluator agent
        current_draft: Current draft to evaluate
        config: Pattern configuration
        variables: User-provided variables
        max_attempts: Max retry attempts
        wait_min: Min wait time for retries
        wait_max: Max wait time for retries

    Returns:
        Tuple of (evaluator_response, estimated_tokens)
    """
    # Build evaluation prompt
    if config.evaluator.input:
        eval_context = {"draft": current_draft}
        if variables:
            eval_context.update(variables)
        eval_prompt = render_template(config.evaluator.input, eval_context)
    else:
        eval_prompt = f"Evaluate the following draft and return JSON with score (0-100), issues, and fixes:\n\n{current_draft}"

    # Execute evaluator with retry on malformed JSON
    evaluator_result = await invoke_agent_with_retry(
        evaluator_agent, eval_prompt, max_attempts, wait_min, wait_max
    )
    evaluator_response = (
        evaluator_result if isinstance(evaluator_result, str) else str(evaluator_result)
    )
    estimated_tokens = estimate_tokens(eval_prompt, evaluator_response)
    return evaluator_response, estimated_tokens


def _parse_evaluator_response(response: str, attempt: int) -> EvaluatorDecision:
    """Parse evaluator response to extract decision.

    Tries multiple parsing strategies:
    1. Direct JSON parsing
    2. Extract JSON block with ```json...``` markers
    3. Regex extraction of {...} object

    Args:
        response: Evaluator agent response text
        attempt: Current attempt number (for logging)

    Returns:
        EvaluatorDecision with score, issues, and fixes

    Raises:
        EvaluatorOptimizerExecutionError: If response cannot be parsed as valid JSON
    """
    logger.debug("parsing_evaluator_response", attempt=attempt, response_preview=response[:100])

    # Strategy 1: Direct JSON parse
    try:
        data = json.loads(response.strip())
        decision = EvaluatorDecision(**data)
        logger.info(
            "evaluator_decision_parsed",
            score=decision.score,
            issues_count=len(decision.issues) if decision.issues else 0,
            strategy="direct_json",
        )
        return decision
    except (json.JSONDecodeError, ValidationError):
        pass

    # Strategy 2: Extract JSON block from markdown code fence
    json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if json_block_match:
        try:
            data = json.loads(json_block_match.group(1))
            decision = EvaluatorDecision(**data)
            logger.info(
                "evaluator_decision_parsed",
                score=decision.score,
                issues_count=len(decision.issues) if decision.issues else 0,
                strategy="json_block",
            )
            return decision
        except (json.JSONDecodeError, ValidationError):
            pass

    # Strategy 3: Regex extraction of JSON object containing "score"
    json_object_match = re.search(r"\{[^}]*\"score\"[^}]*\}", response, re.DOTALL)
    if json_object_match:
        try:
            data = json.loads(json_object_match.group(0))
            decision = EvaluatorDecision(**data)
            logger.info(
                "evaluator_decision_parsed",
                score=decision.score,
                issues_count=len(decision.issues) if decision.issues else 0,
                strategy="regex_extract",
            )
            return decision
        except (json.JSONDecodeError, ValidationError):
            pass

    # All strategies failed
    raise EvaluatorOptimizerExecutionError(
        f"Failed to parse evaluator response as valid JSON on attempt {attempt}. "
        f'Expected format: {{"score": 0-100, "issues": [...], "fixes": [...]}}. '
        f"Received: {response[:200]}"
    )


def _build_revision_context(
    draft: str,
    evaluation: EvaluatorDecision,
    iteration: int,
    variables: dict[str, str] | None,
) -> dict[str, Any]:
    """Build template context for revision prompt.

    Args:
        draft: Current draft text
        evaluation: Evaluator decision with score, issues, fixes
        iteration: Current iteration number (1-based)
        variables: User-provided variables

    Returns:
        Template context dictionary with nested evaluation namespace
    """
    context: dict[str, Any] = {
        "draft": draft,
        "iteration": iteration,
        "evaluation": {
            "score": evaluation.score,
            "issues": evaluation.issues or [],
            "fixes": evaluation.fixes or [],
        },
    }

    # Merge user variables
    if variables:
        context.update(variables)

    return context


def _validate_evaluator_optimizer_config(spec: Spec) -> None:
    """Validate evaluator-optimizer configuration.

    Args:
        spec: Workflow spec

    Raises:
        EvaluatorOptimizerExecutionError: If configuration is invalid
    """
    if spec.pattern.type != PatternType.EVALUATOR_OPTIMIZER:
        raise EvaluatorOptimizerExecutionError(
            f"Expected evaluator_optimizer pattern, got {spec.pattern.type}"
        )

    config = spec.pattern.config

    # Runtime assertions for type safety (validates Pydantic schema loading)
    assert config.producer is not None, "Evaluator-optimizer pattern must have producer agent"
    assert config.evaluator is not None, "Evaluator-optimizer pattern must have evaluator config"
    assert config.accept is not None, "Evaluator-optimizer pattern must have accept criteria"

    if config.producer not in spec.agents:
        raise EvaluatorOptimizerExecutionError(
            f"Producer agent '{config.producer}' not found in agents map"
        )

    if config.evaluator.agent not in spec.agents:
        raise EvaluatorOptimizerExecutionError(
            f"Evaluator agent '{config.evaluator.agent}' not found in agents map"
        )


async def run_evaluator_optimizer(  # noqa: C901 - Complexity acceptable for iterative refinement logic
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
    event_bus: EventBus | None = None,
    agent_cache: AgentCache | None = None,
) -> RunResult:
    """Execute evaluator-optimizer pattern workflow with optional session persistence.

    Phase 4 Implementation:
    - Producer-evaluator feedback loops with iterative refinement
    - JSON parsing with single retry on malformed evaluator responses
    - Nested template context: {{ evaluation.score }}, {{ evaluation.issues }}, {{ evaluation.fixes }}
    - Fail on max_iters exhaustion with detailed iteration history
    - Agent caching for producer/evaluator reuse
    - Cumulative token budget tracking across all iterations

    Phase 3.3 Session Support:
    - Resume from checkpoint: Skip completed iterations on resume
    - Incremental checkpointing: Save state after each iteration
    - Iteration history restoration: Preserve draft and evaluation history
    - Acceptance check on resume: Exit early if already accepted

    Phase 1 HITL Support:
    - Optional review_gate between evaluation iterations
    - Pauses execution for human review/approval before continuing
    - Template context includes {{ iterations[n].evaluation }} and {{ iterations[n].draft }}
    - Supports timeout and default response configuration

    Args:
        spec: Validated workflow specification
        variables: User-provided template variables
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)
        hitl_response: User response when resuming from HITL pause (None = not HITL resume)

    Returns:
        RunResult with final draft and execution metadata

    Raises:
        EvaluatorOptimizerExecutionError: On configuration errors, max iterations, or unrecoverable failures
        ValueError: If session_state and session_repo not both provided or both None
    """
    # Validate session parameters
    validate_session_params(session_state, session_repo)
    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("execute.evaluator_optimizer") as span:
        logger.info("evaluator_optimizer_execution_start", spec_name=spec.name)

        # Validate configuration
        _validate_evaluator_optimizer_config(spec)

        # Set span attributes
        span.set_attribute("spec.name", spec.name)
        if spec.version:
            span.set_attribute("spec.version", spec.version)
        span.set_attribute("pattern.type", spec.pattern.type.value)
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id or "")
        span.set_attribute("runtime.region", spec.runtime.region or "")

        config = spec.pattern.config
        assert config.producer is not None
        assert config.evaluator is not None
        assert config.accept is not None

        span.set_attribute("evaluator_optimizer.max_iterations", config.accept.max_iters)
        span.set_attribute("evaluator_optimizer.evaluator_agent", config.evaluator.agent)
        span.set_attribute("evaluator_optimizer.optimizer_agent", config.producer)
        span.set_attribute("evaluator_optimizer.min_score", config.accept.min_score)

        # Add execution_start event
        span.add_event("execution_start")

        # Get retry configuration
        max_attempts, wait_min, wait_max = get_retry_config(spec)

        # Initialize state
        started_at = datetime.now(UTC).isoformat()
        cumulative_tokens = get_cumulative_tokens(session_state)
        max_tokens = spec.runtime.budgets.get("max_tokens") if spec.runtime.budgets else None

        producer_agent_id = config.producer
        evaluator_agent_id = config.evaluator.agent
        min_score = config.accept.min_score
        max_iters = config.accept.max_iters
        revise_prompt_template = config.revise_prompt or (
            "Revise the following draft based on evaluator feedback.\n\n"
            "Draft:\n{{ draft }}\n\n"
            "Evaluation (Score: {{ evaluation.score }}/100):\n"
            "{% if evaluation.issues %}Issues:\n"
            "{% for issue in evaluation.issues %}- {{ issue }}\n{% endfor %}"
            "{% endif %}"
            "{% if evaluation.fixes %}Suggested fixes:\n"
            "{% for fix in evaluation.fixes %}- {{ fix }}\n{% endfor %}"
            "{% endif %}\n"
            "Please provide an improved version."
        )

        # Get agent configurations
        producer_config = spec.agents[producer_agent_id]
        evaluator_config = spec.agents[evaluator_agent_id]

        # Build initial producer prompt
        initial_prompt = render_template(producer_config.prompt, variables or {})

        # Iteration tracking - restore from session state if resuming
        iteration_history: list[dict[str, Any]] = []
        current_draft = ""
        final_score = 0
        start_iteration = 1

        if session_state and session_repo:
            # Restore pattern state from checkpoint
            pattern_state = session_state.pattern_state
            current_draft = pattern_state.get("current_draft", "")
            iteration_history = pattern_state.get("iteration_history", [])
            final_score = pattern_state.get("final_score", 0)
            start_iteration = pattern_state.get("current_iteration", 1)
            accepted = pattern_state.get("accepted", False)

            # Check if already accepted on resume
            if accepted and final_score >= min_score:
                logger.info(
                    "resume_already_accepted",
                    session_id=session_state.metadata.session_id,
                    final_score=final_score,
                    min_score=min_score,
                    iterations=len(iteration_history),
                )

                # Mark session as complete
                await finalize_session(session_state, session_repo)

                # Return result from checkpoint
                end_time = datetime.now(UTC)
                duration = (end_time - datetime.fromisoformat(started_at)).total_seconds()

                execution_context = {
                    "iterations": len(iteration_history),
                    "final_score": final_score,
                    "min_score": min_score,
                    "max_iters": max_iters,
                    "history": iteration_history,
                    "cumulative_tokens": cumulative_tokens,
                    "resumed": True,
                }

                if iteration_history:
                    last_iteration = iteration_history[-1]
                    execution_context["last_evaluation"] = {
                        "score": last_iteration["score"],
                        "issues": last_iteration["issues"],
                        "fixes": last_iteration["fixes"],
                    }

                return RunResult(
                    success=True,
                    last_response=current_draft,
                    agent_id=producer_agent_id,
                    pattern_type=PatternType.EVALUATOR_OPTIMIZER,
                    started_at=started_at,
                    completed_at=end_time.isoformat(),
                    duration_seconds=duration,
                    execution_context=execution_context,
                )

            logger.info(
                "resuming_evaluator_optimizer",
                session_id=session_state.metadata.session_id,
                start_iteration=start_iteration,
                completed_iterations=len(iteration_history),
                current_draft_length=len(current_draft),
            )

            # Phase 1 HITL: Handle resume from HITL pause
            # Check for timeout BEFORE checking for hitl_response
            timed_out, timeout_default = check_hitl_timeout(session_state)

            if timed_out and hitl_response is None:
                # Auto-resume with default response
                hitl_state_dict = session_state.pattern_state.get("hitl_state")
                if hitl_state_dict:
                    hitl_state = HITLState(**hitl_state_dict)
                    console.print(
                        Panel(
                            format_timeout_warning(
                                hitl_state.timeout_at,
                                timeout_default,
                            ),
                            border_style="yellow",
                        )
                    )
                    hitl_response = timeout_default

                    # Record timeout metadata in pattern_state and session metadata
                    session_state.pattern_state["hitl_timeout_occurred"] = True
                    session_state.pattern_state["hitl_timeout_at"] = hitl_state.timeout_at
                    session_state.pattern_state["hitl_default_used"] = timeout_default

                    session_state.metadata.metadata["hitl_timeout_occurred"] = True
                    session_state.metadata.metadata["hitl_timeout_at"] = hitl_state.timeout_at
                    session_state.metadata.metadata["hitl_default_used"] = timeout_default
                # If user provided explicit response, that overrides timeout

            hitl_state_dict = session_state.pattern_state.get("hitl_state")
            if hitl_state_dict:
                hitl_state = HITLState(**hitl_state_dict)
                if hitl_state.active:
                    # Session is paused for HITL - validate response provided
                    if hitl_response is None:
                        raise EvaluatorOptimizerExecutionError(
                            f"Session {session_state.metadata.session_id} is waiting for HITL response. "
                            f"Resume with: strands run --resume {session_state.metadata.session_id} "
                            f"--hitl-response 'your response'"
                        )

                    # Mark HITL as inactive and store response
                    hitl_state.active = False
                    hitl_state.user_response = hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()

                    # Update session status to RUNNING
                    session_state.metadata.status = SessionStatus.RUNNING
                    session_state.metadata.updated_at = now_iso8601()

                    # Checkpoint session after injecting HITL response (before continuing execution)
                    if session_repo:
                        await session_repo.save(session_state, "")
                        logger.info(
                            "session.checkpoint_after_hitl",
                            session_id=session_state.metadata.session_id,
                            iteration=hitl_state.iteration_index,
                        )

                    logger.info(
                        "hitl_response_received",
                        session_id=session_state.metadata.session_id,
                        iteration=hitl_state.iteration_index,
                        response_preview=hitl_response[:100]
                        if len(hitl_response) > 100
                        else hitl_response,
                    )

                    # Check if user wants to stop early BEFORE continuing execution
                    if hitl_response and hitl_response.lower().strip() in ["stop", "abort", "end"]:
                        logger.info(
                            "early_termination_requested_at_resume",
                            iteration=hitl_state.iteration_index,
                            hitl_response=hitl_response,
                            final_score=final_score,
                        )

                        # Finalize session with current state
                        await finalize_session(session_state, session_repo)

                        # Return successful completion with early termination flag
                        completed_at = datetime.now(UTC).isoformat()
                        duration = (
                            datetime.fromisoformat(completed_at)
                            - datetime.fromisoformat(started_at)
                        ).total_seconds()

                        execution_context = {
                            "iterations": len(iteration_history),
                            "final_score": final_score,
                            "min_score": min_score,
                            "max_iters": max_iters,
                            "history": iteration_history,
                            "cumulative_tokens": cumulative_tokens,
                            "early_termination": True,
                            "termination_reason": "user_requested_at_resume",
                        }

                        if iteration_history:
                            last_iteration = iteration_history[-1]
                            execution_context["last_evaluation"] = {
                                "score": last_iteration["score"],
                                "issues": last_iteration["issues"],
                                "fixes": last_iteration["fixes"],
                            }

                        return RunResult(
                            success=True,
                            last_response=current_draft,
                            agent_id=producer_agent_id,
                            pattern_type=PatternType.EVALUATOR_OPTIMIZER,
                            started_at=started_at,
                            completed_at=completed_at,
                            duration_seconds=duration,
                            exit_code=EX_OK,
                            execution_context=execution_context,
                        )

                    # Continue from the iteration after HITL (already restored from start_iteration)
                    # The hitl_response is used in decision logic below (check for "stop" vs "continue")

        # Phase 6: Create context manager and hooks for compaction
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

        # Create AgentCache
        cache = agent_cache or AgentCache()
        should_close = agent_cache is None
        try:
            # Get or build agents (reuse cached agents)
            producer_agent = await cache.get_or_build_agent(
                spec,
                producer_agent_id,
                producer_config,
                conversation_manager=context_manager,
                hooks=hooks,
                worker_index=None,
            )
            evaluator_agent = await cache.get_or_build_agent(
                spec,
                evaluator_agent_id,
                evaluator_config,
                conversation_manager=context_manager,
                hooks=hooks,
                worker_index=None,
            )

            # Check if resuming after HITL with pending revision
            if session_state and session_state.pattern_state.get("pending_revision"):
                logger.info(
                    "executing_pending_revision",
                    session_id=session_state.metadata.session_id,
                    iteration=start_iteration,
                )

                # Get the last evaluation from iteration_history
                if iteration_history:
                    last_iter = iteration_history[-1]
                    last_evaluation = EvaluatorDecision(
                        score=last_iter["score"],
                        issues=last_iter["issues"],
                        fixes=last_iter["fixes"],
                    )

                    # Build revision context
                    revision_context = _build_revision_context(
                        current_draft, last_evaluation, start_iteration - 1, variables
                    )

                    # Render revision prompt
                    revision_prompt = render_template(revise_prompt_template, revision_context)

                    # Execute producer for revision
                    revision_response = await invoke_agent_with_retry(
                        producer_agent, revision_prompt, max_attempts, wait_min, wait_max
                    )
                    current_draft = (
                        revision_response
                        if isinstance(revision_response, str)
                        else str(revision_response)
                    )

                    # Estimate tokens for revision
                    estimated_tokens = estimate_tokens(revision_prompt, current_draft)
                    cumulative_tokens += estimated_tokens

                    # Clear pending_revision flag and checkpoint
                    if session_repo:
                        await checkpoint_pattern_state(
                            session_state,
                            session_repo,
                            pattern_state_updates={
                                "current_iteration": start_iteration,
                                "current_draft": current_draft,
                                "iteration_history": iteration_history,
                                "final_score": final_score,
                                "accepted": False,
                                "pending_revision": False,
                            },
                            token_increment=estimated_tokens,
                            status=SessionStatus.RUNNING,
                        )

                    logger.info(
                        "pending_revision_complete",
                        session_id=session_state.metadata.session_id if session_state else None,
                        iteration=start_iteration,
                        draft_length=len(current_draft),
                    )

            # Iteration 1: Initial production (skip if resuming)
            if start_iteration == 1:
                current_draft, estimated_tokens = await _run_initial_production(
                    producer_agent, initial_prompt, max_attempts, wait_min, wait_max
                )
                cumulative_tokens += estimated_tokens

                # Checkpoint after initial production (iteration 1)
                if session_state and session_repo:
                    await checkpoint_pattern_state(
                        session_state,
                        session_repo,
                        pattern_state_updates={
                            "current_iteration": 1,
                            "current_draft": current_draft,
                            "iteration_history": iteration_history,
                            "final_score": 0,
                            "accepted": False,
                        },
                        token_increment=estimated_tokens,
                        status=SessionStatus.RUNNING,
                    )

                # Update start iteration after initial production
                start_iteration = 2
            else:
                # Resuming - current_draft already loaded
                logger.info(
                    "skipping_initial_production",
                    reason="resuming_from_checkpoint",
                    start_iteration=start_iteration,
                )

            # Evaluation loop
            # Loop through evaluation-revision cycles up to max_iters
            # Iteration numbering: 1=initial_production, 2...(max_iters+1)=evaluate+revise
            # We do max_iters evaluation cycles starting from start_iteration
            for iteration in range(start_iteration, start_iteration + max_iters):
                logger.info("iteration_start", iteration=iteration, phase="evaluation")
                span.add_event("iteration_start", {"iteration_number": iteration})

                # Phase 3: Emit iteration_start event at loop start
                if event_bus:
                    await event_bus.emit(
                        WorkflowEvent(
                            event_type="iteration_start",
                            timestamp=datetime.now(UTC),
                            session_id=session_state.metadata.session_id if session_state else None,
                            spec_name=spec.name,
                            pattern_type="evaluator_optimizer",
                            data={
                                "iteration": iteration,
                                "evaluator_agent": evaluator_agent_id,
                                "optimizer_agent": producer_agent_id,
                                "max_iterations": start_iteration + max_iters - 1,
                            },
                        )
                    )
                    logger.debug(
                        "iteration_start_event_emitted",
                        iteration=iteration,
                        evaluator=evaluator_agent_id,
                        optimizer=producer_agent_id,
                    )

                # Execute evaluation phase
                evaluator_response, estimated_tokens = await _run_evaluation_phase(
                    evaluator_agent,
                    current_draft,
                    config,
                    variables,
                    max_attempts,
                    wait_min,
                    wait_max,
                )
                cumulative_tokens += estimated_tokens

                # Parse evaluator response (retry once on malformed JSON)
                evaluation: EvaluatorDecision | None = None
                for parse_attempt in range(1, 3):  # Try twice: initial + 1 retry
                    try:
                        evaluation = _parse_evaluator_response(evaluator_response, parse_attempt)
                        break
                    except EvaluatorOptimizerExecutionError as e:
                        if parse_attempt == 1:
                            # Retry with clarification
                            logger.warning(
                                "evaluator_response_malformed",
                                iteration=iteration,
                                attempt=parse_attempt,
                                error=str(e),
                            )
                            clarification_prompt = (
                                f"Your previous response was not valid JSON. "
                                f'Please return only valid JSON in this exact format: '
                                f'{{"score": <0-100>, "issues": ["issue1", ...], "fixes": ["fix1", ...]}}\n\n'
                                f"Evaluate this draft:\n\n{current_draft}"
                            )
                            clarification_result = await invoke_agent_with_retry(
                                evaluator_agent,
                                clarification_prompt,
                                max_attempts,
                                wait_min,
                                wait_max,
                            )
                            evaluator_response = (
                                clarification_result
                                if isinstance(clarification_result, str)
                                else str(clarification_result)
                            )

                            # Estimate tokens for retry
                            estimated_tokens = estimate_tokens(
                                clarification_prompt, evaluator_response
                            )
                            cumulative_tokens += estimated_tokens
                        else:
                            # Both attempts failed
                            raise EvaluatorOptimizerExecutionError(
                                f"Evaluator failed to return valid JSON after 2 attempts on iteration {iteration}. "
                                f"Last response: {evaluator_response[:200]}"
                            ) from e

                if not evaluation:
                    raise EvaluatorOptimizerExecutionError(
                        f"Failed to parse evaluator response on iteration {iteration}"
                    )

                final_score = evaluation.score

                # Record iteration history with full evaluator feedback
                iteration_history.append(
                    {
                        "iteration": iteration,
                        "score": evaluation.score,
                        "issues": evaluation.issues or [],
                        "fixes": evaluation.fixes or [],
                        "draft_preview": current_draft[:100],
                        "draft": current_draft,  # Full draft for template context
                        "evaluation": {  # Nested evaluation object for template access
                            "score": evaluation.score,
                            "issues": evaluation.issues or [],
                            "fixes": evaluation.fixes or [],
                            "feedback": "; ".join(evaluation.issues or [])
                            if evaluation.issues
                            else "",
                        },
                    }
                )

                logger.info(
                    "evaluation_complete",
                    iteration=iteration,
                    score=evaluation.score,
                    min_score=min_score,
                    accepted=evaluation.score >= min_score,
                )

                # Add evaluation_complete event
                event_attrs: dict[str, float | str] = {"score": evaluation.score}
                if evaluation.issues:
                    event_attrs["feedback"] = "; ".join(evaluation.issues[:3])  # First 3 issues
                span.add_event("evaluation_complete", event_attrs)

                # Check acceptance criteria
                if evaluation.score >= min_score:
                    logger.info("draft_accepted", iteration=iteration, score=evaluation.score)

                    # Checkpoint accepted state
                    if session_state and session_repo:
                        await checkpoint_pattern_state(
                            session_state,
                            session_repo,
                            pattern_state_updates={
                                "current_iteration": iteration,  # iteration is already int from range()
                                "current_draft": current_draft,
                                "iteration_history": iteration_history,
                                "final_score": final_score,
                                "accepted": True,
                            },
                            token_increment=0,
                            status=SessionStatus.RUNNING,
                        )

                    break

                # Check if we've exhausted max_iters (this is the last evaluation)
                # If so, we should NOT revise - just exit the loop and raise error
                if iteration >= start_iteration + max_iters - 1:
                    logger.info(
                        "max_iters_exhausted",
                        iteration=iteration,
                        max_iters=max_iters,
                        final_score=final_score,
                    )
                    break

                # Phase 1 HITL: Check for review_gate before continuing to revision
                if config.review_gate:
                    # BLOCKER: Validate session persistence is available
                    if not session_repo or not session_state:
                        raise EvaluatorOptimizerExecutionError(
                            f"Review gate at iteration {iteration} requires session persistence, "
                            "but session is disabled. Session persistence is required to save pause "
                            "state and enable resume. Remove --no-save-session flag or remove "
                            "review_gate from workflow."
                        )

                    # Build template context for HITL prompt
                    hitl_context = {
                        "iteration_index": len(iteration_history) - 1,  # 0-based index
                        "iterations": iteration_history,
                        "current_draft": current_draft,
                        "current_evaluation": {
                            "score": evaluation.score,
                            "issues": evaluation.issues or [],
                            "fixes": evaluation.fixes or [],
                        },
                    }
                    if variables:
                        hitl_context.update(variables)

                    # Render context_display template if provided
                    context_text = ""
                    if config.review_gate.context_display:
                        try:
                            context_text = render_template(
                                config.review_gate.context_display, hitl_context
                            )
                        except Exception as e:
                            logger.warning(
                                "context_display_render_failed",
                                iteration=iteration,
                                error=str(e),
                            )
                            context_text = f"(Failed to render context: {e})"

                    # Calculate timeout
                    timeout_at = None
                    if (
                        config.review_gate.timeout_seconds
                        and config.review_gate.timeout_seconds > 0
                    ):
                        timeout_dt = datetime.now(UTC) + timedelta(
                            seconds=config.review_gate.timeout_seconds
                        )
                        timeout_at = timeout_dt.isoformat()

                    # Create HITL state
                    new_hitl_state = HITLState(
                        active=True,
                        iteration_index=len(iteration_history) - 1,  # 0-based index
                        step_index=None,
                        task_id=None,
                        layer_index=None,
                        branch_id=None,
                        step_type=None,
                        node_id=None,
                        prompt=config.review_gate.prompt,
                        context_display=context_text,
                        default_response=config.review_gate.default,
                        timeout_at=timeout_at,
                        user_response=None,
                    )

                    # Save session with HITL state BEFORE displaying to user
                    session_state.pattern_state["current_iteration"] = iteration
                    session_state.pattern_state["current_draft"] = current_draft
                    session_state.pattern_state["iteration_history"] = iteration_history
                    session_state.pattern_state["final_score"] = final_score
                    session_state.pattern_state["accepted"] = False
                    session_state.pattern_state["pending_revision"] = (
                        True  # Flag that revision step is needed on resume
                    )
                    session_state.pattern_state["hitl_state"] = new_hitl_state.model_dump()
                    session_state.metadata.status = SessionStatus.PAUSED
                    session_state.metadata.updated_at = now_iso8601()

                    try:
                        await session_repo.save(session_state, "")
                        logger.info(
                            "hitl_pause_saved",
                            session_id=session_state.metadata.session_id,
                            iteration=len(iteration_history) - 1,
                        )
                    except Exception as e:
                        logger.error(
                            "hitl_pause_save_failed",
                            session_id=session_state.metadata.session_id,
                            iteration=len(iteration_history) - 1,
                            error=str(e),
                        )
                        raise EvaluatorOptimizerExecutionError(
                            f"Failed to save HITL pause state: {e}"
                        ) from e

                    # Display HITL prompt to user
                    console.print()
                    console.print(
                        Panel(
                            f"[bold yellow]>>> HUMAN REVIEW REQUIRED <<<[/bold yellow]\n\n{config.review_gate.prompt}",
                            border_style="yellow",
                            padding=(1, 2),
                            title=f"Review Gate - Iteration {len(iteration_history)}",
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

                    console.print(f"\n[dim]Session ID:[/dim] {session_state.metadata.session_id}")
                    console.print(
                        f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} "
                        f"--hitl-response 'continue' (or 'stop' to end early)"
                    )
                    console.print()

                    # Exit with HITL pause
                    from strands_cli.exit_codes import EX_HITL_PAUSE

                    hitl_pause_completed_at = datetime.now(UTC).isoformat()
                    hitl_pause_started_dt = datetime.fromisoformat(started_at)
                    hitl_pause_completed_dt = datetime.fromisoformat(hitl_pause_completed_at)
                    hitl_pause_duration = (
                        hitl_pause_completed_dt - hitl_pause_started_dt
                    ).total_seconds()

                    return RunResult(
                        success=True,
                        last_response=f"HITL review gate at iteration {len(iteration_history)}: {config.review_gate.prompt}",
                        pattern_type=PatternType.EVALUATOR_OPTIMIZER,
                        started_at=started_at,
                        completed_at=hitl_pause_completed_at,
                        duration_seconds=hitl_pause_duration,
                        agent_id="hitl",
                        exit_code=EX_HITL_PAUSE,
                        execution_context={
                            "iterations": len(iteration_history),
                            "current_score": final_score,
                            "history": iteration_history,
                        },
                    )

                # Prepare for revision
                logger.info("iteration_start", iteration=iteration + 1, phase="revision")

                # Build revision context
                revision_context = _build_revision_context(
                    current_draft, evaluation, iteration, variables
                )

                # Render revision prompt
                revision_prompt = render_template(revise_prompt_template, revision_context)

                # Execute producer for revision
                revision_response = await invoke_agent_with_retry(
                    producer_agent, revision_prompt, max_attempts, wait_min, wait_max
                )
                current_draft = (
                    revision_response
                    if isinstance(revision_response, str)
                    else str(revision_response)
                )

                # Estimate tokens for revision
                estimated_tokens = estimate_tokens(revision_prompt, current_draft)
                cumulative_tokens += estimated_tokens

                # Checkpoint after revision
                if session_state and session_repo:
                    await checkpoint_pattern_state(
                        session_state,
                        session_repo,
                        pattern_state_updates={
                            "current_iteration": int(iteration + 1),
                            "current_draft": current_draft,
                            "iteration_history": iteration_history,
                            "final_score": final_score,
                            "accepted": False,
                        },
                        token_increment=estimated_tokens,
                        status=SessionStatus.RUNNING,
                    )

                # Add optimization_complete event
                improved = (
                    len(iteration_history) > 1 and evaluation.score > iteration_history[-2]["score"]
                )
                span.add_event("optimization_complete", {"improved": improved})

                # Add iteration_complete event
                converged = evaluation.score >= min_score
                span.add_event(
                    "iteration_complete", {"iteration_number": iteration, "converged": converged}
                )

            # Check if loop completed without acceptance (max iterations exhausted)
            if final_score < min_score:
                raise EvaluatorOptimizerExecutionError(
                    f"Max iterations ({max_iters}) exhausted without reaching min_score ({min_score}). "
                    f"Final score: {final_score}. "
                    f"Iteration history: {iteration_history}"
                )

            # Build result
            completed_at = datetime.now(UTC).isoformat()
            duration = (
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
            ).total_seconds()

            logger.info(
                "evaluator_optimizer_execution_complete",
                spec_name=spec.name,
                iterations=len(iteration_history),
                final_score=final_score,
                duration_seconds=duration,
            )

            # Finalize session if using sessions
            if session_state and session_repo:
                await finalize_session(session_state, session_repo)

            # Add execution_complete event
            span.add_event(
                "execution_complete",
                {
                    "total_iterations": len(iteration_history),
                    "duration_seconds": duration,
                    "final_score": final_score,
                },
            )

            # Build execution context with full iteration history
            execution_context = {
                "iterations": len(iteration_history),
                "final_score": final_score,
                "min_score": min_score,
                "max_iters": max_iters,
                "history": iteration_history,
                "cumulative_tokens": cumulative_tokens,
            }

            # Add last evaluation details if we have iteration history
            if iteration_history:
                last_iteration = iteration_history[-1]
                execution_context["last_evaluation"] = {
                    "score": last_iteration["score"],
                    "issues": last_iteration["issues"],
                    "fixes": last_iteration["fixes"],
                }

            return RunResult(
                success=True,
                last_response=current_draft,
                agent_id=producer_agent_id,
                pattern_type=PatternType.EVALUATOR_OPTIMIZER,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                exit_code=EX_OK,
                execution_context=execution_context,
            )

        except Exception as e:
            # Mark session as failed before re-raising
            if session_state and session_repo:
                await fail_session(session_state, session_repo, e)

            # Re-raise evaluator-optimizer execution errors
            if isinstance(e, EvaluatorOptimizerExecutionError):
                raise
            raise EvaluatorOptimizerExecutionError(
                f"Evaluator-optimizer execution failed: {e}"
            ) from e
        finally:
            # Cleanup HTTP clients
            if should_close:
                await cache.close()

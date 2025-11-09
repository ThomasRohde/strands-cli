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
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError

from strands_cli.exec.hooks import ProactiveCompactionHook
from strands_cli.exec.utils import (
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
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
from strands_cli.telemetry import get_tracer
from strands_cli.types import EvaluatorDecision, PatternType, RunResult, Spec


class EvaluatorOptimizerExecutionError(Exception):
    """Raised when evaluator-optimizer execution fails."""

    pass


logger = structlog.get_logger(__name__)


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


async def run_evaluator_optimizer(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
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

    Args:
        spec: Validated workflow specification
        variables: User-provided template variables
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)

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
        span.set_attribute("runtime.model_id", spec.runtime.model_id)
        if spec.runtime.region:
            span.set_attribute("runtime.region", spec.runtime.region)

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
        cache = AgentCache()
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
            for iteration in range(start_iteration, max_iters + 1):
                logger.info("iteration_start", iteration=iteration, phase="evaluation")
                span.add_event("iteration_start", {"iteration_number": iteration})

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
                event_attrs = {"score": evaluation.score}
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
                                "current_iteration": iteration,
                                "current_draft": current_draft,
                                "iteration_history": iteration_history,
                                "final_score": final_score,
                                "accepted": True,
                            },
                            token_increment=0,
                            status=SessionStatus.RUNNING,
                        )

                    break

                # Check if max iterations exhausted
                if iteration >= max_iters:
                    raise EvaluatorOptimizerExecutionError(
                        f"Max iterations ({max_iters}) exhausted without reaching min_score ({min_score}). "
                        f"Final score: {evaluation.score}. "
                        f"Iteration history: {iteration_history}"
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
                            "current_iteration": iteration + 1,
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
            await cache.close()

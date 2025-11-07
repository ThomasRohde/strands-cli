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
    check_budget_threshold,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
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


async def run_evaluator_optimizer(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute evaluator-optimizer pattern workflow.

    Phase 4 Implementation:
    - Producer-evaluator feedback loops with iterative refinement
    - JSON parsing with single retry on malformed evaluator responses
    - Nested template context: {{ evaluation.score }}, {{ evaluation.issues }}, {{ evaluation.fixes }}
    - Fail on max_iters exhaustion with detailed iteration history
    - Agent caching for producer/evaluator reuse
    - Cumulative token budget tracking across all iterations

    Args:
        spec: Validated workflow specification
        variables: User-provided template variables

    Returns:
        RunResult with final draft and execution metadata

    Raises:
        EvaluatorOptimizerExecutionError: On configuration errors, max iterations, or unrecoverable failures
    """
    logger.info("evaluator_optimizer_execution_start", spec_name=spec.name)

    # Validate configuration
    _validate_evaluator_optimizer_config(spec)

    # Get retry configuration
    max_attempts, wait_min, wait_max = get_retry_config(spec)

    # Initialize state
    started_at = datetime.now(UTC).isoformat()
    cumulative_tokens = 0
    max_tokens = spec.runtime.budgets.get("max_tokens") if spec.runtime.budgets else None

    config = spec.pattern.config

    # Runtime assertions for type safety (already validated in _validate_evaluator_optimizer_config)
    assert config.producer is not None
    assert config.evaluator is not None
    assert config.accept is not None

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

    # Iteration tracking
    iteration_history: list[dict[str, Any]] = []
    current_draft = ""
    final_score = 0

    # Phase 6: Create context manager and hooks for compaction
    context_manager = create_from_policy(spec.context_policy, spec)
    hooks: list[Any] = []
    if spec.context_policy and spec.context_policy.compaction and spec.context_policy.compaction.enabled:
        threshold = spec.context_policy.compaction.when_tokens_over or 60000
        hooks.append(ProactiveCompactionHook(threshold_tokens=threshold))
        logger.info("compaction_enabled", threshold_tokens=threshold)

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
        )
        evaluator_agent = await cache.get_or_build_agent(
            spec,
            evaluator_agent_id,
            evaluator_config,
            conversation_manager=context_manager,
            hooks=hooks,
        )

        # Iteration 1: Initial production
        current_draft, estimated_tokens = await _run_initial_production(
            producer_agent, initial_prompt, max_attempts, wait_min, wait_max
        )
        cumulative_tokens += estimated_tokens
        check_budget_threshold(cumulative_tokens, max_tokens, "iteration_1_production")

        # Evaluation loop
        for iteration in range(1, max_iters + 1):
            logger.info("iteration_start", iteration=iteration, phase="evaluation")

            # Execute evaluation phase
            evaluator_response, estimated_tokens = await _run_evaluation_phase(
                evaluator_agent, current_draft, config, variables, max_attempts, wait_min, wait_max
            )
            cumulative_tokens += estimated_tokens
            check_budget_threshold(
                cumulative_tokens, max_tokens, f"iteration_{iteration}_evaluation"
            )

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
                            evaluator_agent, clarification_prompt, max_attempts, wait_min, wait_max
                        )
                        evaluator_response = (
                            clarification_result
                            if isinstance(clarification_result, str)
                            else str(clarification_result)
                        )

                        # Estimate tokens for retry
                        estimated_tokens = estimate_tokens(clarification_prompt, evaluator_response)
                        cumulative_tokens += estimated_tokens
                        check_budget_threshold(
                            cumulative_tokens, max_tokens, f"iteration_{iteration}_evaluation_retry"
                        )
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

            # Check acceptance criteria
            if evaluation.score >= min_score:
                logger.info("draft_accepted", iteration=iteration, score=evaluation.score)
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
                revision_response if isinstance(revision_response, str) else str(revision_response)
            )

            # Estimate tokens for revision
            estimated_tokens = estimate_tokens(revision_prompt, current_draft)
            cumulative_tokens += estimated_tokens
            check_budget_threshold(cumulative_tokens, max_tokens, f"iteration_{iteration}_revision")

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
            context={"execution": execution_context},  # Add for artifact template access
        )

    finally:
        # Cleanup HTTP clients
        await cache.close()

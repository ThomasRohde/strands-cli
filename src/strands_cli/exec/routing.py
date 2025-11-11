"""Routing pattern executor.

Executes routing pattern with router agent classification and conditional route execution.
Router agent analyzes input and returns JSON decision specifying which route to execute.

Execution Flow:
    1. Validate routing configuration (router + routes)
    2. Execute router agent with classification prompt
    3. Parse router response to extract JSON {"route": "<route_name>"}
    4. Retry on malformed JSON (up to max_retries, default 2)
    5. Validate selected route exists
    6. Execute selected route's steps as a chain
    7. Return RunResult with route execution outcome

Router Output:
    - Expected JSON: {"route": "<route_name>"}
    - Parsing strategies: direct JSON, extract JSON block, regex extraction
    - Retry with clarification prompt on malformed responses

Error Handling:
    - Malformed JSON → retry with clarification (up to max_retries)
    - Invalid route name → fail with ExecutionError listing valid routes
    - No fallback behavior (explicit failures only)
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

import structlog
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from strands_cli.exec.chain import run_chain
from strands_cli.exec.hitl_utils import check_hitl_timeout, format_timeout_warning
from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import AgentCache
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.checkpoint_utils import (
    checkpoint_pattern_state,
    fail_session,
    finalize_session,
    validate_session_params,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import now_iso8601
from strands_cli.telemetry import get_tracer
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import HITLState, PatternType, RouterDecision, RunResult, Spec


class RoutingExecutionError(Exception):
    """Raised when routing execution fails."""

    pass


class RouterReviewPauseError(Exception):
    """Raised to signal a router review HITL pause."""

    def __init__(self, result: RunResult) -> None:
        self.result = result
        super().__init__("Router review HITL pause")


logger = structlog.get_logger(__name__)


def _parse_router_response(response: str, attempt: int) -> RouterDecision:
    """Parse router response to extract route decision.

    Tries multiple parsing strategies:
    1. Direct JSON parsing
    2. Extract JSON block with ```json...``` markers
    3. Regex extraction of {...} object

    Args:
        response: Router agent response text
        attempt: Current attempt number (for logging)

    Returns:
        RouterDecision with route name

    Raises:
        RoutingExecutionError: If response cannot be parsed as valid JSON
    """
    logger.debug("parsing_router_response", attempt=attempt, response_preview=response[:100])

    # Strategy 1: Direct JSON parse
    try:
        data = json.loads(response.strip())
        decision = RouterDecision(**data)
        logger.info("router_decision_parsed", route=decision.route, strategy="direct_json")
        return decision
    except (json.JSONDecodeError, ValidationError):
        pass

    # Strategy 2: Extract JSON block from markdown code fence
    json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if json_block_match:
        try:
            data = json.loads(json_block_match.group(1))
            decision = RouterDecision(**data)
            logger.info("router_decision_parsed", route=decision.route, strategy="json_block")
            return decision
        except (json.JSONDecodeError, ValidationError):
            pass

    # Strategy 3: Regex extraction of JSON object
    json_object_match = re.search(r"\{[^}]*\"route\"[^}]*\}", response, re.DOTALL)
    if json_object_match:
        try:
            data = json.loads(json_object_match.group(0))
            decision = RouterDecision(**data)
            logger.info("router_decision_parsed", route=decision.route, strategy="regex_extract")
            return decision
        except (json.JSONDecodeError, ValidationError):
            pass

    # All strategies failed
    raise RoutingExecutionError(
        f"Failed to parse router response as valid JSON on attempt {attempt}. "
        f"Expected format: {{\"route\": \"<route_name>\"}}"
    )


def _validate_route_exists(route_name: str, routes: dict[str, Any]) -> None:
    """Validate that selected route exists in routes map.

    Args:
        route_name: Route name from router decision
        routes: Map of valid route names to route configs

    Raises:
        RoutingExecutionError: If route_name not in routes
    """
    if route_name not in routes:
        valid_routes = ", ".join(f"'{r}'" for r in routes)
        raise RoutingExecutionError(
            f"Invalid route '{route_name}' selected by router. Valid routes: {valid_routes}"
        )


async def _execute_router_with_retry(
    spec: Spec,
    router_agent_id: str,
    router_input: str,
    cache: AgentCache,
    max_retries: int,
    context_manager: Any = None,
    hooks: list[Any] | None = None,
    notes_manager: Any = None,
) -> tuple[str, str]:
    """Execute router agent with retry logic for malformed responses.

    Args:
        spec: Workflow spec
        router_agent_id: Router agent ID
        router_input: Rendered router input prompt
        cache: Shared AgentCache for agent reuse
        max_retries: Maximum retry attempts

    Returns:
        Tuple of (selected_route_name, router_response_text)

    Raises:
        RoutingExecutionError: If all retry attempts fail or route is invalid
    """
    router_agent_config = spec.agents[router_agent_id]

    # Phase 6.2: Inject last N notes into agent context
    injected_notes = None
    if notes_manager and spec.context_policy and spec.context_policy.notes:
        injected_notes = notes_manager.get_last_n_for_injection(
            spec.context_policy.notes.include_last
        )

    agent = await cache.get_or_build_agent(
        spec,
        router_agent_id,
        router_agent_config,
        conversation_manager=context_manager,
        hooks=hooks,
        injected_notes=injected_notes,
        worker_index=None,
    )

    # Construct router task with output format instructions
    router_task = router_input + "\n\nRespond with valid JSON: {\"route\": \"<route_name>\"}"

    for attempt in range(max_retries + 1):
        logger.info(
            "router_execution_attempt",
            attempt=attempt + 1,
            max_attempts=max_retries + 1,
            agent=router_agent_id,
        )

        try:
            # Execute router agent
            from strands_cli.utils import capture_and_display_stdout

            with capture_and_display_stdout():
                result = await agent.invoke_async(router_task)
            response = result if isinstance(result, str) else str(result)

            # Parse response
            decision = _parse_router_response(response, attempt + 1)

            # Validate route exists
            if spec.pattern.config.routes:
                _validate_route_exists(decision.route, spec.pattern.config.routes)

            logger.info(
                "router_decision_success",
                route=decision.route,
                attempt=attempt + 1,
            )
            return decision.route, response

        except RoutingExecutionError as e:
            # Check if this is a validation error (invalid route) vs parse error
            if "Invalid route" in str(e):
                # Invalid route is not retryable - fail immediately
                raise

            # Malformed JSON - retry if attempts remain
            if attempt < max_retries:
                logger.warning(
                    "router_parse_failed_retrying",
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                    error=str(e),
                )
                # Update task with clarification for next attempt
                router_task = (
                    f"{router_input}\n\n"
                    f"Previous response was malformed. "
                    f"Respond with ONLY valid JSON: {{\"route\": \"<route_name>\"}}"
                )
            else:
                logger.error(
                    "router_parse_failed_exhausted",
                    attempt=attempt + 1,
                    error=str(e),
                )
                raise RoutingExecutionError(
                    f"Router failed to produce valid JSON after {max_retries + 1} attempts"
                ) from e

    # Should never reach here
    raise RoutingExecutionError("Unexpected error in router execution")


def _validate_routing_config(spec: Spec) -> tuple[Any, str, int]:
    """Validate routing configuration and extract router info.

    Args:
        spec: Workflow spec with routing pattern

    Returns:
        Tuple of (router_config, router_agent_id, max_retries)

    Raises:
        RoutingExecutionError: If routing config is invalid
    """
    if not spec.pattern.config.router:
        raise RoutingExecutionError("Routing pattern requires router configuration")

    if not spec.pattern.config.routes:
        raise RoutingExecutionError("Routing pattern requires at least one route")

    router_config = spec.pattern.config.router
    router_agent_id = router_config.agent
    max_retries = router_config.max_retries

    return router_config, router_agent_id, max_retries


def _build_router_context(spec: Spec, variables: dict[str, str] | None) -> dict[str, Any]:
    """Build template context for router input.

    Args:
        spec: Workflow spec
        variables: Optional CLI --var overrides

    Returns:
        Template context dictionary
    """
    context = {}
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])
    if variables:
        context.update(variables)
    return context


async def _handle_router_review_hitl(
    spec: Spec,
    chosen_route: str,
    router_response: str,
    session_state: SessionState,
    session_repo: FileSessionRepository,
    variables: dict[str, str] | None,
    started_at: str,
) -> NoReturn:
    """Handle HITL review of router decision with approval/override capability.

    Four-phase execution:
    1. Validate session parameters (BLOCKER if session disabled)
    2. Build and save HITL state with router decision context
    3. Display prompt to user with router decision and context
    4. Exit with EX_HITL_PAUSE for user response

    Args:
        spec: Workflow spec
        chosen_route: Router's selected route
        router_response: Router agent's full response
        session_state: Session state for persistence
        session_repo: Session repository for checkpointing
        variables: Template variables
        started_at: Execution start timestamp

    Raises:
        RoutingExecutionError: If session not available or invalid override format
        RouterReviewPauseError: Always raised to signal HITL pause
    """
    console = Console()
    router_config = spec.pattern.config.router
    assert router_config is not None, "router config must be present"
    review_step = router_config.review_router
    assert review_step is not None, "review_router must be present"

    # Phase 1: Validate session persistence available (BLOCKER)
    if not session_repo or not session_state:
        raise RoutingExecutionError(
            "Router review HITL requires session persistence, but session is disabled. "
            "Session persistence is required to save pause state and enable resume. "
            "Remove --no-save-session flag or remove review_router from router config."
        )

    # Check if resuming from HITL pause
    hitl_state_dict = session_state.pattern_state.get("hitl_state")
    if hitl_state_dict:
        hitl_state = HITLState(**hitl_state_dict)
        if hitl_state.active and hitl_state.router_review:
            # Already paused - should not reach here (handled in main executor)
            raise RoutingExecutionError(
                f"Session {session_state.metadata.session_id} is waiting for HITL response. "
                f"Resume with: strands run --resume {session_state.metadata.session_id} "
                f"--hitl-response 'your response'"
            )

    # Phase 2: Build HITL state with router decision context
    # Build context including router decision for context_display
    template_context = _build_router_context(spec, variables)
    template_context["router"] = {
        "chosen_route": chosen_route,
        "response": router_response,
    }

    # Render context_display if provided
    context_text = ""
    if review_step.context_display:
        context_text = render_template(review_step.context_display, template_context)

    # Calculate timeout
    timeout_at = None
    if review_step.timeout_seconds and review_step.timeout_seconds > 0:
        timeout_dt = datetime.now(UTC) + timedelta(seconds=review_step.timeout_seconds)
        timeout_at = timeout_dt.isoformat()

    # Create HITL state for router review
    new_hitl_state = HITLState(
        active=True,
        router_review=True,
        prompt=review_step.prompt,
        context_display=context_text,
        default_response=review_step.default,
        timeout_at=timeout_at,
        user_response=None,
    )

    # Phase 3: Save HITL state to session BEFORE displaying to user
    session_state.pattern_state["hitl_state"] = new_hitl_state.model_dump()
    session_state.pattern_state["router_decision"] = {
        "chosen_route": chosen_route,
        "response": router_response,
    }
    session_state.metadata.status = SessionStatus.PAUSED
    session_state.metadata.updated_at = now_iso8601()

    try:
        spec_content = ""  # Spec snapshot already saved
        await session_repo.save(session_state, spec_content)
        logger.info(
            "router_review_hitl_pause_saved",
            session_id=session_state.metadata.session_id,
            chosen_route=chosen_route,
        )
    except Exception as e:
        logger.error(
            "router_review_hitl_pause_save_failed",
            session_id=session_state.metadata.session_id,
            error=str(e),
        )
        raise RoutingExecutionError(f"Failed to save router review HITL pause state: {e}") from e

    # Phase 4: Display HITL prompt to user
    console.print()
    console.print(
        Panel(
            f"[bold yellow]>>> ROUTER DECISION REVIEW REQUIRED <<<[/bold yellow]\n\n{review_step.prompt}",
            border_style="yellow",
            padding=(1, 2),
            title="Router Review HITL",
        )
    )

    if context_text:
        console.print(
            Panel(
                f"[bold]Router Decision Context:[/bold]\n\n{context_text}",
                border_style="dim",
                padding=(1, 2),
            )
        )

    console.print(f"\n[dim]Session ID:[/dim] {session_state.metadata.session_id}")
    console.print(
        f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} "
        f"--hitl-response 'approved' (or 'route:<name>' to override)"
    )
    console.print()

    logger.info(
        "router_review_hitl_pause",
        session_id=session_state.metadata.session_id,
        chosen_route=chosen_route,
    )

    pause_time = datetime.now(UTC)
    completed_at = pause_time.isoformat()
    try:
        started_dt = datetime.fromisoformat(started_at)
        duration = (pause_time - started_dt).total_seconds()
    except ValueError:
        duration = 0.0

    router_context = {
        "chosen_route": chosen_route,
        "response": router_response,
    }

    result = RunResult(
        success=True,
        last_response=f"Router review required for route '{chosen_route}'",
        error=None,
        agent_id="hitl",
        pattern_type=PatternType.ROUTING,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        artifacts_written=[],
        execution_context={
            "router": router_context,
            "status": "waiting_for_router_review",
        },
        exit_code=EX_HITL_PAUSE,
        session_id=session_state.metadata.session_id,
        variables={"router": router_context},
    )

    raise RouterReviewPauseError(result)


def _create_route_spec(spec: Spec, chosen_route: str) -> Spec:
    """Create a temporary spec for executing selected route as chain.

    Args:
        spec: Original routing spec
        chosen_route: Selected route name

    Returns:
        Modified spec with route steps as chain pattern

    Raises:
        RoutingExecutionError: If route has no steps
    """
    from strands_cli.types import PatternConfig

    routes = spec.pattern.config.routes
    assert routes is not None, "Routing pattern must have routes"
    route = routes[chosen_route]

    if not route.then:
        raise RoutingExecutionError(f"Route '{chosen_route}' has no steps to execute")

    # Create temporary spec for chain execution with selected route's steps
    route_spec = spec.model_copy(deep=True)
    route_spec.pattern.type = PatternType.CHAIN
    # Replace config with new PatternConfig containing only steps
    route_spec.pattern.config = PatternConfig(steps=route.then)

    return route_spec


async def run_routing(  # noqa: C901
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
) -> RunResult:
    """Execute a routing pattern workflow with optional session persistence.

    Phase 6 Performance Optimization:
    - Async execution with shared AgentCache for router and route execution
    - Single event loop eliminates per-route loop churn
    - Agents reused when router and route use same agent configuration

    Phase 3.1 Session Support:
    - Resume from checkpoint: Skip router if decision already made
    - Router decision checkpoint: Save route choice before execution
    - Route execution with resume: Delegate to chain resume logic

    Executes router agent to classify input, then runs the selected route's chain.
    Router decision is injected into route context as {{ router.chosen_route }}.

    Args:
        spec: Workflow spec with routing pattern
        variables: Optional CLI --var overrides
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)
        hitl_response: User response when resuming from HITL pause (None = not resuming from HITL)

    Returns:
        RunResult with selected route execution outcome

    Raises:
        RoutingExecutionError: If routing execution fails
        ValueError: If session_state and session_repo not both provided or both None
    """
    # Validate session parameters (both or neither)
    validate_session_params(session_state, session_repo)

    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("execute.routing") as span:
        # Add span attributes
        span.set_attribute("spec.name", spec.name)
        if spec.version:
            span.set_attribute("spec.version", spec.version)
        span.set_attribute("pattern.type", "routing")
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id or "")
        span.set_attribute("runtime.region", spec.runtime.region or "")
        if session_state:
            span.set_attribute("session.id", session_state.metadata.session_id)
            span.set_attribute("session.resume", True)

        # Add execution start event
        span.add_event("execution_start")

        logger.info(
            "routing_execution_start",
            spec_name=spec.name,
            resume=session_state is not None,
        )

        # Track execution start time
        started_at = datetime.now(UTC).isoformat()

        # Validate routing configuration
        router_config, router_agent_id, max_retries = _validate_routing_config(spec)
        span.set_attribute("routing.router_agent", router_agent_id)
        span.set_attribute("routing.route_count", len(spec.pattern.config.routes or {}))
        span.set_attribute("routing.max_retries", max_retries)

        # Validate router review HITL requires session persistence
        if router_config.review_router and (not session_state or not session_repo):
            raise RoutingExecutionError(
                "Router review HITL requires session persistence, but session is disabled. "
                "Session persistence is required to save pause state and enable resume. "
                "Remove --no-save-session flag or remove review_router from router config."
            )

        # Build router context and render input
        context = _build_router_context(spec, variables)
        router_input_template = router_config.input or ""
        try:
            router_input = render_template(router_input_template, context)
        except Exception as e:
            raise RoutingExecutionError(f"Failed to render router input: {e}") from e

        logger.info("router_input_rendered", preview=router_input[:100])

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
        step_counter = [0]  # Mutable container for hook to track step count
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
        cache = AgentCache()

        try:
            # Phase 1: Handle HITL resume if session is paused for router review
            # Note: hitl_response is passed as a function parameter from resume.py
            # Don't declare it as a local variable here - it comes as an argument
            chosen_route: str | None = None
            router_response: str = ""
            hitl_processed = False

            if session_state:
                # Check for timeout BEFORE checking for hitl_response
                timed_out, timeout_default = check_hitl_timeout(session_state)

                if timed_out and hitl_response is None:
                    # Auto-resume with default response
                    hitl_state_dict = session_state.pattern_state.get("hitl_state")
                    if hitl_state_dict:
                        from rich.console import Console

                        console = Console()
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
                        # Override hitl_response with timeout default
                        hitl_response = timeout_default

                        # Record timeout metadata
                        session_state.pattern_state["hitl_timeout_occurred"] = True
                        session_state.pattern_state["hitl_timeout_at"] = hitl_state.timeout_at
                        session_state.pattern_state["hitl_default_used"] = timeout_default

                        session_state.metadata.metadata["hitl_timeout_occurred"] = True
                        session_state.metadata.metadata["hitl_timeout_at"] = hitl_state.timeout_at
                        session_state.metadata.metadata["hitl_default_used"] = timeout_default

                # Check for active HITL state
                hitl_state_dict = session_state.pattern_state.get("hitl_state")
                if hitl_state_dict:
                    hitl_state = HITLState(**hitl_state_dict)
                    if hitl_state.active and hitl_state.router_review:
                        # Session is paused for router review - validate response provided
                        if hitl_response is None:
                            raise RoutingExecutionError(
                                f"Session {session_state.metadata.session_id} is waiting for router review HITL response. "
                                f"Resume with: strands run --resume {session_state.metadata.session_id} "
                                f"--hitl-response 'approved' (or 'route:<name>' to override)"
                            )

                        # Parse router review response: "approved" or "route:<name>"
                        router_decision = session_state.pattern_state.get("router_decision", {})
                        original_route = router_decision.get("chosen_route")
                        
                        # CRITICAL: Restore router_response from session state
                        # This ensures {{ router.response }} is available for artifact rendering
                        router_response = router_decision.get("response", "")

                        if hitl_response.strip().lower() == "approved":
                            # User approved router decision
                            chosen_route = original_route
                            logger.info(
                                "router_review_approved",
                                session_id=session_state.metadata.session_id,
                                route=chosen_route,
                            )
                        elif hitl_response.strip().lower().startswith("route:"):
                            # User override with specific route
                            override_route = hitl_response.strip().lower().replace("route:", "").strip()

                            # Validate override route exists
                            if spec.pattern.config.routes:
                                _validate_route_exists(override_route, spec.pattern.config.routes)

                            chosen_route = override_route
                            logger.info(
                                "router_review_override",
                                session_id=session_state.metadata.session_id,
                                original_route=original_route,
                                override_route=chosen_route,
                            )
                        else:
                            raise RoutingExecutionError(
                                f"Invalid router review response: '{hitl_response}'. "
                                "Expected 'approved' or 'route:<route_name>'"
                            )

                        # Mark HITL as no longer active
                        hitl_state.active = False
                        hitl_state.user_response = hitl_response
                        session_state.pattern_state["hitl_state"] = hitl_state.model_dump()

                        # Mark router as executed with final route
                        session_state.pattern_state["router_executed"] = True
                        session_state.pattern_state["chosen_route"] = chosen_route
                        session_state.pattern_state["route_state"] = {
                            "current_step": 0,
                            "step_history": [],
                        }

                        # Checkpoint session after processing HITL response
                        if session_repo:
                            await session_repo.save(session_state, "")
                            logger.info(
                                "session.checkpoint_after_router_review_hitl",
                                session_id=session_state.metadata.session_id,
                                route=chosen_route,
                            )

                        # Set flag to skip router execution below
                        hitl_processed = True

                        # Continue to route execution
                        span.add_event(
                            "router_review_hitl_resume",
                            {
                                "original_route": original_route or "",
                                "final_route": chosen_route,
                                "response": hitl_response,
                            },
                        )

            # Restore or execute router (if not already handled by HITL resume)
            if not hitl_processed:
                if session_state and session_state.pattern_state.get("router_executed"):
                    # Resume: router decision already made (non-HITL path)
                    chosen_route = session_state.pattern_state["chosen_route"]
                    
                    # CRITICAL: Restore router_response from session state
                    # This ensures {{ router.response }} is available for artifact rendering
                    router_decision_state = session_state.pattern_state.get("router_decision", {})
                    router_response = router_decision_state.get("response", "")
                    
                    logger.info(
                        "routing_router_restored",
                        route=chosen_route,
                        session_id=session_state.metadata.session_id,
                        has_router_response=bool(router_response),
                    )
                    span.add_event(
                        "router_restored",
                        {"chosen_route": chosen_route, "router_agent": router_agent_id},
                    )
                else:
                    # Fresh execution: run router with retry logic
                    try:
                        chosen_route, router_response = await _execute_router_with_retry(
                            spec,
                            router_agent_id,
                            router_input,
                            cache,
                            max_retries,
                            context_manager,
                            hooks,
                            notes_manager,
                        )
                    except RoutingExecutionError:
                        raise
                    except Exception as e:
                        raise RoutingExecutionError(f"Router execution failed: {e}") from e

                    # Check for router review HITL gate
                    if router_config.review_router and session_state and session_repo:
                        # Router review HITL pause - will exit with EX_HITL_PAUSE
                        await _handle_router_review_hitl(
                            spec,
                            chosen_route,
                            router_response,
                            session_state,
                            session_repo,
                            variables,
                            started_at,
                        )
                        # Execution will not reach here - function exits via sys.exit()

                    # No HITL or session disabled - checkpoint router decision and proceed
                    if session_state and session_repo:
                        await checkpoint_pattern_state(
                            session_state,
                            session_repo,
                            pattern_state_updates={
                                "router_executed": True,
                                "chosen_route": chosen_route,
                                "router_decision": {
                                    "chosen_route": chosen_route,
                                    "response": router_response,
                                },
                                "route_state": {"current_step": 0, "step_history": []},
                            },
                            token_increment=500,  # Estimated router tokens
                        )
                        logger.debug(
                            "routing_router_checkpointed",
                            route=chosen_route,
                            session_id=session_state.metadata.session_id,
                        )

            logger.info("route_selected", route=chosen_route)
            span.add_event(
                "route_selected", {"chosen_route": chosen_route, "router_agent": router_agent_id}
            )

            # Create spec for route execution
            route_spec = _create_route_spec(spec, chosen_route)

            # Inject router decision and response into context for route execution
            route_variables: dict[str, Any] = dict(variables) if variables else {}

            # CRITICAL: Ensure router_response is always available for artifact rendering
            # router_response is set in all execution paths:
            # 1. Fresh execution: Set at line 603-619 after _execute_router_with_retry
            # 2. HITL resume: Restored at line 667 from session_state.pattern_state["router_decision"]
            # 3. Non-HITL resume: Restored at line 596 from session_state.pattern_state["router_decision"]
            # This ensures {{ router.response }} always has the actual router reasoning

            route_variables["router"] = {
                "chosen_route": chosen_route,
                "response": router_response,  # Always available from above execution paths
            }

            # Build chain session state if resuming route
            route_session_state = None
            route_session_repo = None

            if session_state:
                # Create chain session state from routing state
                route_session_state = SessionState(
                    metadata=session_state.metadata,
                    variables=session_state.variables,
                    runtime_config=session_state.runtime_config,
                    pattern_state=session_state.pattern_state.get(
                        "route_state", {"current_step": 0, "step_history": []}
                    ),
                    token_usage=session_state.token_usage,
                    artifacts_written=session_state.artifacts_written,
                )
                route_session_repo = session_repo

            # Execute selected route as a chain
            steps = route_spec.pattern.config.steps
            assert steps is not None, "Route spec must have steps"
            logger.info("route_execution_start", route=chosen_route, steps=len(steps))

            try:
                # Execute route with resume support (delegates to chain resume logic)
                result = await run_chain(
                    route_spec, route_variables, route_session_state, route_session_repo
                )
            except Exception as e:
                raise RoutingExecutionError(f"Route '{chosen_route}' execution failed: {e}") from e

            # Update routing state with route results
            if session_state and session_repo and result.execution_context:
                # Preserve chain pattern state structure for resume (current_step + step_history)
                # The execution_context contains {"steps": [...]}, but we need the full pattern state
                session_state.pattern_state["route_state"] = {
                    "current_step": len(result.execution_context.get("steps", [])),
                    "step_history": result.execution_context.get("steps", []),
                }
                await finalize_session(session_state, session_repo)

            # Update result metadata to include routing info
            result.pattern_type = PatternType.ROUTING
            if not result.execution_context:
                result.execution_context = {}
            result.execution_context["chosen_route"] = chosen_route
            result.execution_context["router_agent"] = router_agent_id

            # Ensure router context is available for artifact rendering
            if result.variables is None:
                result.variables = {}
            
            # Use the router context that was already built for route execution
            # This includes router response from either fresh execution or session state
            result.variables["router"] = route_variables.get("router", {
                "chosen_route": chosen_route,
                "response": "",
            })
            
            logger.info(
                "routing_result_variables_set",
                variables_keys=list(result.variables.keys()) if result.variables else [],
                has_router=("router" in result.variables),
                router_chosen_route=result.variables.get("router", {}).get("chosen_route"),
            )

            logger.info(
                "routing_execution_complete",
                route=chosen_route,
                duration=result.duration_seconds,
            )
            span.add_event(
                "execution_complete",
                {
                    "chosen_route": chosen_route,
                    "duration_seconds": result.duration_seconds,
                },
            )

            return result
        except RouterReviewPauseError as pause:
            logger.info(
                "routing_paused_for_hitl",
                session_id=pause.result.session_id,
                exit_code=EX_HITL_PAUSE,
            )
            return pause.result
        except Exception as e:
            # Mark session as failed before re-raising
            if session_state and session_repo:
                await fail_session(session_state, session_repo, e)

            # Re-raise routing execution errors
            if isinstance(e, RoutingExecutionError):
                raise
            raise RoutingExecutionError(f"Routing execution failed: {e}") from e
        finally:
            # Clean up cached resources
            await cache.close()

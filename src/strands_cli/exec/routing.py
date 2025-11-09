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
from typing import Any

import structlog
from pydantic import ValidationError

from strands_cli.exec.chain import run_chain
from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.exec.utils import AgentCache
from strands_cli.loader import render_template
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.session import SessionState
from strands_cli.session.checkpoint_utils import (
    checkpoint_pattern_state,
    fail_session,
    finalize_session,
    validate_session_params,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.telemetry import get_tracer
from strands_cli.tools.notes_manager import NotesManager
from strands_cli.types import PatternType, RouterDecision, RunResult, Spec


class RoutingExecutionError(Exception):
    """Raised when routing execution fails."""

    pass


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
) -> str:
    """Execute router agent with retry logic for malformed responses.

    Args:
        spec: Workflow spec
        router_agent_id: Router agent ID
        router_input: Rendered router input prompt
        cache: Shared AgentCache for agent reuse
        max_retries: Maximum retry attempts

    Returns:
        Selected route name

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
            return decision.route

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
    routes = spec.pattern.config.routes
    assert routes is not None, "Routing pattern must have routes"
    route = routes[chosen_route]

    if not route.then:
        raise RoutingExecutionError(f"Route '{chosen_route}' has no steps to execute")

    # Create temporary spec for chain execution with selected route's steps
    route_spec = spec.model_copy(deep=True)
    route_spec.pattern.type = PatternType.CHAIN
    route_spec.pattern.config.steps = route.then
    route_spec.pattern.config.tasks = None  # Clear workflow tasks if any
    route_spec.pattern.config.router = None  # Clear router config
    route_spec.pattern.config.routes = None  # Clear routes

    return route_spec


async def run_routing(  # noqa: C901
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
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

        # Validate routing configuration
        router_config, router_agent_id, max_retries = _validate_routing_config(spec)
        span.set_attribute("routing.router_agent", router_agent_id)
        span.set_attribute("routing.route_count", len(spec.pattern.config.routes or {}))
        span.set_attribute("routing.max_retries", max_retries)

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
            # Restore or execute router
            if session_state and session_state.pattern_state.get("router_executed"):
                # Resume: router decision already made
                chosen_route = session_state.pattern_state["chosen_route"]
                logger.info(
                    "routing_router_restored",
                    route=chosen_route,
                    session_id=session_state.metadata.session_id,
                )
                span.add_event(
                    "router_restored",
                    {"chosen_route": chosen_route, "router_agent": router_agent_id},
                )
            else:
                # Fresh execution: run router with retry logic
                try:
                    chosen_route = await _execute_router_with_retry(
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

                # Checkpoint router decision
                if session_state and session_repo:
                    await checkpoint_pattern_state(
                        session_state,
                        session_repo,
                        pattern_state_updates={
                            "router_executed": True,
                            "chosen_route": chosen_route,
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

            # Inject router decision into context for route execution
            route_variables: dict[str, Any] = dict(variables) if variables else {}
            route_variables["router"] = {"chosen_route": chosen_route}

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

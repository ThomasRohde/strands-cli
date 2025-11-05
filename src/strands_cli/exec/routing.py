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

import asyncio
import json
import re
from typing import Any

import structlog
from pydantic import ValidationError

from strands_cli.exec.chain import run_chain
from strands_cli.loader import render_template
from strands_cli.runtime import build_agent
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
    max_retries: int,
) -> str:
    """Execute router agent with retry logic for malformed responses.

    Args:
        spec: Workflow spec
        router_agent_id: Router agent ID
        router_input: Rendered router input prompt
        max_retries: Maximum retry attempts

    Returns:
        Selected route name

    Raises:
        RoutingExecutionError: If all retry attempts fail or route is invalid
    """
    router_agent_config = spec.agents[router_agent_id]
    agent = build_agent(spec, router_agent_id, router_agent_config)

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
            from strands_cli.utils import suppress_stdout

            with suppress_stdout():
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


def run_routing(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a routing pattern workflow.

    Executes router agent to classify input, then runs the selected route's chain.
    Router decision is injected into route context as {{ router.chosen_route }}.

    Args:
        spec: Workflow spec with routing pattern
        variables: Optional CLI --var overrides

    Returns:
        RunResult with selected route execution outcome

    Raises:
        RoutingExecutionError: If routing execution fails
    """
    logger.info("routing_execution_start", spec_name=spec.name)

    if not spec.pattern.config.router:
        raise RoutingExecutionError("Routing pattern requires router configuration")

    if not spec.pattern.config.routes:
        raise RoutingExecutionError("Routing pattern requires at least one route")

    router_config = spec.pattern.config.router
    router_agent_id = router_config.agent
    max_retries = router_config.max_retries

    # Build template context for router input
    context = {}
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])
    if variables:
        context.update(variables)

    # Render router input
    router_input_template = router_config.input or ""
    try:
        router_input = render_template(router_input_template, context)
    except Exception as e:
        raise RoutingExecutionError(f"Failed to render router input: {e}") from e

    logger.info("router_input_rendered", preview=router_input[:100])

    # Execute router with retry logic
    try:
        chosen_route = asyncio.run(
            _execute_router_with_retry(spec, router_agent_id, router_input, max_retries)
        )
    except RoutingExecutionError:
        raise
    except Exception as e:
        raise RoutingExecutionError(f"Router execution failed: {e}") from e

    logger.info("route_selected", route=chosen_route)

    # Get selected route configuration
    route = spec.pattern.config.routes[chosen_route]

    if not route.then:
        raise RoutingExecutionError(f"Route '{chosen_route}' has no steps to execute")

    # Create temporary spec for chain execution with selected route's steps
    # We'll modify pattern config to use the route's steps
    route_spec = spec.model_copy(deep=True)
    route_spec.pattern.type = PatternType.CHAIN
    route_spec.pattern.config.steps = route.then
    route_spec.pattern.config.tasks = None  # Clear workflow tasks if any
    route_spec.pattern.config.router = None  # Clear router config
    route_spec.pattern.config.routes = None  # Clear routes

    # Inject router decision into context for route execution
    # Note: Need Any type here because we inject a nested dict for router context
    route_variables: dict[str, Any] = dict(variables) if variables else {}
    route_variables["router"] = {"chosen_route": chosen_route}

    # Execute selected route as a chain
    logger.info("route_execution_start", route=chosen_route, steps=len(route.then))

    try:
        result = run_chain(route_spec, route_variables)
    except Exception as e:
        raise RoutingExecutionError(f"Route '{chosen_route}' execution failed: {e}") from e

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

    return result

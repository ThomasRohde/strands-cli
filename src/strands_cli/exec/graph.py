"""Graph pattern executor.

Executes graph-based workflows with nodes, edges, and conditional transitions.
Supports state machines, decision trees, and iterative refinement with cycle protection.

Execution Flow:
    1. Validate graph configuration (nodes, edges)
    2. Start at entry node (first in YAML order)
    3. For each node execution:
        a. Check iteration limits (global max_steps + per-node max_iterations)
        b. Build template context with {{ nodes.<id>.response }} access
        c. Execute node agent with retry logic
        d. Find next node via edge traversal:
            - Evaluate static 'to' edges (sequential execution)
            - Evaluate conditional 'choose' edges (first match wins)
        e. Track token budget and warn at 80% threshold
    4. Terminate at terminal node (no outgoing edges)
    5. Return RunResult with terminal node response

Edge Traversal:
    - Static edges: Execute 'to' targets sequentially in array order
    - Conditional edges: Evaluate 'choose' conditions in order, transition to first match
    - Special 'else' keyword: Always matches (default fallback)
    - Terminal nodes: Nodes with no outgoing edges (workflow completion)

Cycle Protection:
    - Global limit: runtime.budgets.max_steps (default 100) total node executions
    - Per-node limit: pattern.config.max_iterations (default 10) visits per node
    - Prevents infinite loops with clear error messages

Template Context:
    - {{ nodes.<id>.response }}: Access node outputs
    - {{ nodes.<id>.agent }}: Agent used by node
    - {{ nodes.<id>.status }}: Execution status (success/error)
    - {{ nodes.<id>.iteration }}: Number of times node executed (for loops)
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from strands_cli.exec.conditions import ConditionEvaluationError, evaluate_condition
from strands_cli.exec.utils import (
    TOKEN_WARNING_THRESHOLD,
    AgentCache,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.loader import render_template
from strands_cli.telemetry import get_tracer
from strands_cli.types import GraphEdge, PatternType, RunResult, Spec

logger = structlog.get_logger(__name__)


class GraphExecutionError(Exception):
    """Raised when graph execution fails."""

    pass


def _build_node_context(
    spec: Spec,
    node_results: dict[str, dict[str, Any]],
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build template context for node execution.

    Args:
        spec: Workflow spec
        node_results: Dictionary of node_id -> {response, agent, status, iteration}
        variables: User-provided variables from --var flags

    Returns:
        Template context with nodes{}, user variables, and spec inputs
    """
    context = {}

    # Add user-provided variables from spec.inputs.values
    if spec.inputs and spec.inputs.get("values"):
        context.update(spec.inputs["values"])

    # Override with CLI --var variables
    if variables:
        context.update(variables)

    # Add node results as nodes{} dictionary
    context["nodes"] = node_results

    return context


def _get_next_node(
    current_node_id: str,
    edges: list[GraphEdge],
    node_results: dict[str, dict[str, Any]],
) -> str | None:
    """Find next node to execute based on edges and conditions.

    Evaluates edges from current node:
    1. If static 'to' edge: return first target (sequential execution)
    2. If conditional 'choose': evaluate conditions in order, return first match
    3. If no edges: return None (terminal node)

    Args:
        current_node_id: Node we're transitioning from
        edges: List of graph edges
        node_results: Current node execution results for condition evaluation

    Returns:
        Next node ID to execute, or None if terminal node

    Raises:
        GraphExecutionError: If edge has neither 'to' nor 'choose', or condition evaluation fails
    """
    # Find edge from current node
    current_edge = None
    for edge in edges:
        if edge.from_ == current_node_id:
            current_edge = edge
            break

    # No edge = terminal node
    if not current_edge:
        logger.debug("terminal_node_reached", node=current_node_id)
        return None

    # Static 'to' edge: return first target (sequential)
    if current_edge.to:
        next_node = current_edge.to[0]  # First target in array
        logger.debug(
            "static_transition",
            from_node=current_node_id,
            to_node=next_node,
            all_targets=current_edge.to,
        )
        return next_node

    # Conditional 'choose' edge: evaluate in order
    if current_edge.choose:
        context = {"nodes": node_results}
        for choice in current_edge.choose:
            try:
                if evaluate_condition(choice.when, context):
                    logger.debug(
                        "conditional_transition",
                        from_node=current_node_id,
                        to_node=choice.to,
                        condition=choice.when,
                        matched=True,
                    )
                    return choice.to
            except ConditionEvaluationError as e:
                logger.error(
                    "condition_evaluation_failed",
                    from_node=current_node_id,
                    condition=choice.when,
                    error=str(e),
                )
                raise GraphExecutionError(
                    f"Failed to evaluate condition '{choice.when}' in edge from '{current_node_id}': {e}"
                ) from e

        # No condition matched
        logger.warning(
            "no_condition_matched",
            from_node=current_node_id,
            conditions=[c.when for c in current_edge.choose],
        )
        return None  # Treat as terminal if no conditions match

    # Edge has neither 'to' nor 'choose' (should be caught by schema validation)
    raise GraphExecutionError(
        f"Edge from '{current_node_id}' has neither 'to' nor 'choose' targets"
    )


def _check_token_budget(
    cumulative_tokens: int,
    max_tokens: int | None,
    node_id: str,
) -> None:
    """Check token budget and raise error if hard limit exceeded.

    Args:
        cumulative_tokens: Total tokens used so far
        max_tokens: Maximum allowed tokens (None if no limit)
        node_id: Current node ID (for logging)

    Raises:
        GraphExecutionError: If cumulative tokens >= 100% of max_tokens
    """
    if not max_tokens:
        return

    # Warning threshold at 80%
    if cumulative_tokens >= max_tokens * TOKEN_WARNING_THRESHOLD:
        logger.warning(
            "token_budget_warning",
            node=node_id,
            cumulative=cumulative_tokens,
            max_tokens=max_tokens,
            percent=round(cumulative_tokens / max_tokens * 100, 1),
        )

    # Hard limit at 100%
    if cumulative_tokens >= max_tokens:
        logger.error(
            "token_budget_exceeded",
            node=node_id,
            cumulative=cumulative_tokens,
            max_tokens=max_tokens,
        )
        raise GraphExecutionError(
            f"Token budget exceeded at node '{node_id}' ({cumulative_tokens}/{max_tokens} tokens). "
            f"Consider increasing budgets.max_tokens or optimizing prompts."
        )


async def _execute_graph_node(
    node_id: str,
    spec: Spec,
    cache: AgentCache,
    node_results: dict[str, dict[str, Any]],
    variables: dict[str, str] | None,
    iteration_count: int,
) -> tuple[str, int]:
    """Execute a single graph node and return response and token count.

    Args:
        node_id: ID of node being executed
        spec: Workflow spec
        cache: Agent cache for reuse
        node_results: Dictionary of prior node execution results
        variables: User-provided variables from --var flags
        iteration_count: Number of times this node has executed

    Returns:
        Tuple of (response_text, estimated_token_count)

    Raises:
        GraphExecutionError: If node execution fails
    """
    # Type safety: nodes cannot be None if we got past capability checking
    nodes = spec.pattern.config.nodes
    if nodes is None:
        raise GraphExecutionError("Graph pattern has no nodes defined")

    node = nodes[node_id]

    logger.info(
        "node_execution_start",
        node=node_id,
        agent=node.agent,
        iteration=iteration_count,
    )

    # Build context with prior node results
    context = _build_node_context(spec, node_results, variables)

    # Render node input (or use default)
    if node.input:
        try:
            input_text = render_template(node.input, context)
        except Exception as e:
            raise GraphExecutionError(f"Failed to render input for node '{node_id}': {e}") from e
    else:
        # Default input references prior nodes
        input_text = f"Execute task for node '{node_id}'."
        if node_results:
            prior_nodes = ", ".join(node_results.keys())
            input_text += f" Prior nodes: {prior_nodes}."

    # Get agent config
    agent_config = spec.agents.get(node.agent)
    if not agent_config:
        raise GraphExecutionError(f"Node '{node_id}' references non-existent agent '{node.agent}'")

    # Build or reuse agent
    agent = await cache.get_or_build_agent(
        spec=spec,
        agent_id=node.agent,
        agent_config=agent_config,
        tool_overrides=None,  # Graph nodes don't support tool overrides
    )

    # Execute agent with retry
    max_attempts, wait_min, wait_max = get_retry_config(spec)
    try:
        result = await invoke_agent_with_retry(
            agent=agent,
            input_text=input_text,
            max_attempts=max_attempts,
            wait_min=wait_min,
            wait_max=wait_max,
        )
    except Exception as e:
        logger.error(
            "node_execution_failed",
            node=node_id,
            agent=node.agent,
            error=str(e),
        )
        # Store error result
        node_results[node_id] = {
            "response": f"ERROR: {e}",
            "agent": node.agent,
            "status": "error",
            "iteration": iteration_count,
        }
        raise GraphExecutionError(f"Node '{node_id}' execution failed: {e}") from e

    # Extract response text
    response_text = result if isinstance(result, str) else str(result)

    # Track tokens
    response_tokens = estimate_tokens(input_text, response_text)

    logger.info(
        "node_execution_complete",
        node=node_id,
        response_length=len(response_text),
        tokens=response_tokens,
    )

    return response_text, response_tokens


def _check_iteration_limit(
    node_id: str,
    iteration_counts: dict[str, int],
    max_iterations: int,
) -> None:
    """Check if node has exceeded per-node iteration limit.

    Args:
        node_id: Node being executed
        iteration_counts: Dictionary of node_id -> visit count
        max_iterations: Maximum visits per node

    Raises:
        GraphExecutionError: If node exceeds max_iterations
    """
    current_count = iteration_counts.get(node_id, 0) + 1
    iteration_counts[node_id] = current_count

    if current_count > max_iterations:
        logger.error(
            "node_iteration_limit_exceeded",
            node=node_id,
            iterations=current_count,
            max_iterations=max_iterations,
        )
        raise GraphExecutionError(
            f"Node '{node_id}' exceeded max iterations limit ({max_iterations}). "
            f"Possible infinite loop detected."
        )


async def run_graph(spec: Spec, variables: dict[str, str] | None = None) -> RunResult:
    """Execute a graph pattern workflow.

    Executes nodes via edge traversal with condition evaluation and cycle protection.

    Args:
        spec: Workflow spec with graph pattern configuration
        variables: User-provided variables from --var flags

    Returns:
        RunResult with terminal node response and execution metadata

    Raises:
        GraphExecutionError: If graph configuration invalid or execution fails
    """
    # Phase 10: Get tracer after configure_telemetry() has been called
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("execute.graph") as span:
        logger.info("graph_execution_start", spec_name=spec.name, spec_version=spec.version)
        start_time = datetime.now(UTC)

        # Validate configuration
        if not spec.pattern.config.nodes:
            raise GraphExecutionError("Graph pattern has no nodes")
        if not spec.pattern.config.edges:
            raise GraphExecutionError("Graph pattern has no edges")

        # Set span attributes
        span.set_attribute("spec.name", spec.name)
        if spec.version:
            span.set_attribute("spec.version", spec.version)
        span.set_attribute("pattern.type", spec.pattern.type.value)
        span.set_attribute("runtime.provider", spec.runtime.provider)
        span.set_attribute("runtime.model_id", spec.runtime.model_id)
        if spec.runtime.region:
            span.set_attribute("runtime.region", spec.runtime.region)

        span.set_attribute("graph.node_count", len(spec.pattern.config.nodes))
        span.set_attribute("graph.edge_count", len(spec.pattern.config.edges))

        # Entry node: first in YAML order
        start_node = next(iter(spec.pattern.config.nodes.keys()))
        span.set_attribute("graph.start_node", start_node)

        # Get limits
        max_iterations = spec.pattern.config.max_iterations
        max_steps = 100
        if spec.runtime.budgets and spec.runtime.budgets.get("max_steps"):
            max_steps = spec.runtime.budgets["max_steps"]
        span.set_attribute("graph.max_iterations", max_iterations)

        # Add execution_start event
        span.add_event("execution_start", {"start_node": start_node})

        # Initialize state
        node_results: dict[str, dict[str, Any]] = {}

        # Pre-populate all nodes with None to avoid template errors for unexecuted nodes
        for node_id in spec.pattern.config.nodes:
            node_results[node_id] = {
                "response": None,
                "agent": spec.pattern.config.nodes[node_id].agent,
                "status": "not_executed",
                "iteration": 0,
            }

        # Track the last successfully executed node (actual terminal node)
        last_executed_node: str | None = None

        iteration_counts: dict[str, int] = {}
        total_steps = 0
        cumulative_tokens = 0
        max_tokens = spec.runtime.budgets.get("max_tokens") if spec.runtime.budgets else None

        # Entry node: first in YAML order (dict insertion order in Python 3.12+)
        current_node_id = start_node
        logger.info("graph_entry_node", node=current_node_id)

        # Create AgentCache
        cache = AgentCache()

        try:
            # Execute nodes until terminal or limits reached
            while current_node_id and total_steps < max_steps:
                # Check per-node iteration limit
                _check_iteration_limit(current_node_id, iteration_counts, max_iterations)

                # Add node_entered event
                span.add_event(
                    "node_entered",
                    {
                        "node_id": current_node_id,
                        "visit_count": iteration_counts.get(current_node_id, 0) + 1,
                    },
                )

                # Execute node
                response_text, response_tokens = await _execute_graph_node(
                    node_id=current_node_id,
                    spec=spec,
                    cache=cache,
                    node_results=node_results,
                    variables=variables,
                    iteration_count=iteration_counts[current_node_id],
                )

                # Track budget
                cumulative_tokens += response_tokens
                _check_token_budget(cumulative_tokens, max_tokens, current_node_id)

                # Store node result
                node = spec.pattern.config.nodes[current_node_id]
                node_results[current_node_id] = {
                    "response": response_text,
                    "agent": node.agent,
                    "status": "success",
                    "iteration": iteration_counts[current_node_id],
                }

                # Track last successfully executed node
                last_executed_node = current_node_id

                # Find next node via edge traversal
                next_node_id = _get_next_node(
                    current_node_id, spec.pattern.config.edges, node_results
                )

                # Add node_complete event
                span.add_event(
                    "node_complete",
                    {
                        "node_id": current_node_id,
                        "next_transition": next_node_id if next_node_id else "terminal",
                    },
                )

                # Add transition event if not terminal
                if next_node_id:
                    span.add_event(
                        "transition",
                        {
                            "from_node": current_node_id,
                            "to_node": next_node_id,
                            "condition": "evaluated",
                        },
                    )

                # Increment step count for the node we just executed
                total_steps += 1

                # Update state - if None, we've reached a terminal node
                if next_node_id is None:
                    break

                current_node_id = next_node_id

            # Check if we hit max_steps limit - this is an error condition
            if total_steps >= max_steps:
                logger.error(
                    "graph_max_steps_exceeded",
                    total_steps=total_steps,
                    max_steps=max_steps,
                    last_node=last_executed_node,
                )
                raise GraphExecutionError(
                    f"Graph execution exceeded max_steps limit ({max_steps}). "
                    f"Possible infinite loop detected. Last executed node: '{last_executed_node}'"
                )

            # Find terminal node for final response - use actual last executed node
            if not last_executed_node:
                raise GraphExecutionError("No nodes were executed in graph")

            terminal_node = last_executed_node
            final_response = node_results[terminal_node]["response"]
            final_agent_id = spec.pattern.config.nodes[terminal_node].agent

            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            logger.info(
                "graph_execution_complete",
                nodes_executed=len(node_results),
                total_steps=total_steps,
                terminal_node=terminal_node,
                duration_seconds=duration,
                tokens=cumulative_tokens,
            )

            # Add execution_complete event
            span.add_event(
                "execution_complete", {"nodes_visited": total_steps, "duration_seconds": duration}
            )

            return RunResult(
                success=True,
                last_response=final_response,
                error=None,
                agent_id=final_agent_id,
                pattern_type=PatternType.GRAPH,
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                artifacts_written=[],
                execution_context={
                    "nodes": node_results,
                    "terminal_node": terminal_node,
                    "total_steps": total_steps,
                    "iteration_counts": iteration_counts,
                    "cumulative_tokens": cumulative_tokens,
                    "name": spec.name,
                    "timestamp": end_time.isoformat(),
                },
            )

        finally:
            await cache.close()

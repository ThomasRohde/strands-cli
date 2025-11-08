"""Tests for graph pattern executor.

Tests graph pattern execution including:
- Linear graph execution (no conditionals)
- Conditional edge evaluation
- Loop detection and iteration limits
- Terminal node detection
- Context access ({{ nodes.<id>.response }})
- Edge traversal (static and conditional)
- Error handling (missing nodes, infinite loops)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.conditions import (
    ConditionEvaluationError,
    evaluate_condition,
    validate_condition_syntax,
)
from strands_cli.exec.graph import (
    GraphExecutionError,
    _build_node_context,
    _check_iteration_limit,
    _get_next_node,
    run_graph,
)
from strands_cli.types import (
    Agent,
    ConditionalChoice,
    GraphEdge,
    GraphNode,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def linear_graph_spec() -> Spec:
    """Create a simple linear graph: A -> B -> C."""
    return Spec(
        version=0,
        name="test-linear-graph",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "agent_a": Agent(prompt="Agent A"),
            "agent_b": Agent(prompt="Agent B"),
            "agent_c": Agent(prompt="Agent C"),
        },
        pattern={
            "type": PatternType.GRAPH,
            "config": PatternConfig(
                nodes={
                    "node_a": GraphNode(agent="agent_a", input="Start"),
                    "node_b": GraphNode(agent="agent_b", input="{{ nodes.node_a.response }}"),
                    "node_c": GraphNode(agent="agent_c", input="{{ nodes.node_b.response }}"),
                },
                edges=[
                    GraphEdge(**{"from": "node_a", "to": ["node_b"]}),
                    GraphEdge(**{"from": "node_b", "to": ["node_c"]}),
                    # node_c has no outgoing edges (terminal)
                ],
            ),
        },
    )


@pytest.fixture
def conditional_graph_spec() -> Spec:
    """Create a graph with conditional edges."""
    return Spec(
        version=0,
        name="test-conditional-graph",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "checker": Agent(prompt="Check condition"),
            "path_a": Agent(prompt="Path A"),
            "path_b": Agent(prompt="Path B"),
        },
        pattern={
            "type": PatternType.GRAPH,
            "config": PatternConfig(
                nodes={
                    "check": GraphNode(agent="checker"),
                    "handle_a": GraphNode(agent="path_a"),
                    "handle_b": GraphNode(agent="path_b"),
                },
                edges=[
                    GraphEdge(**{
                        "from": "check",
                        "choose": [
                            ConditionalChoice(when="{{ score >= 85 }}", to="handle_a"),
                            ConditionalChoice(when="else", to="handle_b"),
                        ],
                    }),
                    # Both paths are terminal
                ],
            ),
        },
    )


@pytest.fixture
def loop_graph_spec() -> Spec:
    """Create a graph with a loop."""
    return Spec(
        version=0,
        name="test-loop-graph",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "processor": Agent(prompt="Process"),
            "checker": Agent(prompt="Check"),
            "finalizer": Agent(prompt="Finalize"),
        },
        pattern={
            "type": PatternType.GRAPH,
            "config": PatternConfig(
                max_iterations=3,
                nodes={
                    "process": GraphNode(agent="processor"),
                    "check": GraphNode(agent="checker"),
                    "finalize": GraphNode(agent="finalizer"),
                },
                edges=[
                    GraphEdge(**{"from": "process", "to": ["check"]}),
                    GraphEdge(**{
                        "from": "check",
                        "choose": [
                            ConditionalChoice(when="{{ nodes.process.iteration >= 3 }}", to="finalize"),
                            ConditionalChoice(when="else", to="process"),
                        ],
                    }),
                    # finalize is terminal
                ],
            ),
        },
    )


# ============================================================================
# Condition Evaluation Tests
# ============================================================================


def test_evaluate_condition_else_keyword():
    """Test that 'else' keyword always evaluates to True."""
    assert evaluate_condition("else", {}) is True
    assert evaluate_condition("  ELSE  ", {}) is True


def test_evaluate_condition_simple_comparison():
    """Test simple numeric comparison."""
    context = {"score": 90}
    assert evaluate_condition("{{ score >= 85 }}", context) is True
    assert evaluate_condition("{{ score < 85 }}", context) is False


def test_evaluate_condition_nested_access():
    """Test nested dictionary access."""
    context = {"nodes": {"analyze": {"score": 75}}}
    assert evaluate_condition("{{ nodes.analyze.score >= 85 }}", context) is False
    assert evaluate_condition("{{ nodes.analyze.score >= 70 }}", context) is True


def test_evaluate_condition_boolean_operators():
    """Test boolean AND/OR/NOT operators."""
    context = {"a": 10, "b": 20}
    assert evaluate_condition("{{ a > 5 and b > 15 }}", context) is True
    assert evaluate_condition("{{ a > 5 or b < 10 }}", context) is True
    assert evaluate_condition("{{ not (a > 15) }}", context) is True


def test_evaluate_condition_malformed_syntax():
    """Test that malformed expressions raise ConditionEvaluationError."""
    with pytest.raises(ConditionEvaluationError, match="Malformed condition"):
        evaluate_condition("{{ invalid syntax }", {})


def test_evaluate_condition_undefined_variable():
    """Test that undefined variables raise ConditionEvaluationError."""
    with pytest.raises(ConditionEvaluationError, match="Undefined variable"):
        evaluate_condition("{{ undefined_var > 0 }}", {})


def test_validate_condition_syntax_valid():
    """Test syntax validation for valid expressions."""
    valid, error = validate_condition_syntax("{{ score >= 85 }}")
    assert valid is True
    assert error is None


def test_validate_condition_syntax_invalid():
    """Test syntax validation for invalid expressions."""
    valid, error = validate_condition_syntax("{{ invalid syntax }")
    assert valid is False
    assert "Syntax error" in error


def test_validate_condition_syntax_else():
    """Test that 'else' keyword is always valid."""
    valid, error = validate_condition_syntax("else")
    assert valid is True
    assert error is None


# ============================================================================
# Helper Function Tests
# ============================================================================


def test_build_node_context_with_node_results():
    """Test building template context with node results."""
    spec = Spec(
        version=0,
        name="test",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test")},
        pattern={"type": PatternType.GRAPH, "config": PatternConfig(nodes={}, edges=[])},
        inputs={"values": {"user_var": "user_value"}},
    )

    node_results = {
        "node_a": {"response": "Response A", "agent": "agent1", "status": "success", "iteration": 1},
        "node_b": {"response": "Response B", "agent": "agent1", "status": "success", "iteration": 1},
    }

    variables = {"cli_var": "cli_value"}

    context = _build_node_context(spec, node_results, variables)

    # Check all variables present
    assert context["user_var"] == "user_value"
    assert context["cli_var"] == "cli_value"  # CLI vars override spec inputs
    assert context["nodes"] == node_results


def test_get_next_node_static_edge():
    """Test static edge transition (first target in 'to' array)."""
    edges = [GraphEdge(**{"from": "node_a", "to": ["node_b", "node_c"]})]
    next_node = _get_next_node("node_a", edges, {})

    # Should return first target (sequential execution)
    assert next_node == "node_b"


def test_get_next_node_conditional_first_match():
    """Test conditional edge - first matching condition wins."""
    edges = [
        GraphEdge(**{
            "from": "node_a",
            "choose": [
                ConditionalChoice(when="{{ nodes.node_a.score >= 90 }}", to="excellent"),
                ConditionalChoice(when="{{ nodes.node_a.score >= 70 }}", to="good"),
                ConditionalChoice(when="else", to="poor"),
            ],
        })
    ]

    # node_results with varying scores
    node_results_high = {"node_a": {"response": "...", "score": 92}}
    node_results_mid = {"node_a": {"response": "...", "score": 75}}
    node_results_low = {"node_a": {"response": "...", "score": 50}}

    assert _get_next_node("node_a", edges, node_results_high) == "excellent"
    assert _get_next_node("node_a", edges, node_results_mid) == "good"
    assert _get_next_node("node_a", edges, node_results_low) == "poor"


def test_get_next_node_terminal_no_edge():
    """Test terminal node (no outgoing edges) returns None."""
    edges = [GraphEdge(**{"from": "node_a", "to": ["node_b"]})]
    next_node = _get_next_node("node_b", edges, {})  # node_b has no edge

    assert next_node is None


def test_get_next_node_no_condition_matched():
    """Test conditional edge with no matches returns None."""
    edges = [
        GraphEdge(**{
            "from": "node_a",
            "choose": [
                ConditionalChoice(when="{{ nodes.node_a.score >= 90 }}", to="high"),
                ConditionalChoice(when="{{ nodes.node_a.score < 50 }}", to="low"),
                # No 'else' clause
            ],
        })
    ]

    node_results = {"node_a": {"response": "...", "score": 60}}  # Doesn't match any condition

    next_node = _get_next_node("node_a", edges, node_results)
    assert next_node is None  # Treat as terminal


def test_check_iteration_limit_within_limit():
    """Test iteration tracking within limit."""
    iteration_counts = {}
    _check_iteration_limit("node_a", iteration_counts, max_iterations=3)

    assert iteration_counts["node_a"] == 1


def test_check_iteration_limit_exceeds_limit():
    """Test that exceeding iteration limit raises error."""
    iteration_counts = {"node_a": 3}

    with pytest.raises(GraphExecutionError, match="exceeded max iterations limit"):
        _check_iteration_limit("node_a", iteration_counts, max_iterations=3)


# ============================================================================
# Graph Executor Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_run_graph_linear_execution(linear_graph_spec: Spec, mocker):
    """Test linear graph execution (A -> B -> C)."""
    # Mock agent building and execution
    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    # Mock invoke_agent_with_retry to return string responses
    mock_invoke = mocker.patch("strands_cli.exec.graph.invoke_agent_with_retry")
    mock_invoke.side_effect = [
        "Response A",
        "Response B",
        "Response C",
    ]

    # Execute graph
    result = await run_graph(linear_graph_spec)

    # Verify execution
    assert result.success is True
    assert result.pattern_type == PatternType.GRAPH
    assert result.last_response == "Response C"  # Terminal node response
    assert result.execution_context["nodes"] == {
        "node_a": {"response": "Response A", "agent": "agent_a", "status": "success", "iteration": 1},
        "node_b": {"response": "Response B", "agent": "agent_b", "status": "success", "iteration": 1},
        "node_c": {"response": "Response C", "agent": "agent_c", "status": "success", "iteration": 1},
    }
    assert result.execution_context["terminal_node"] == "node_c"
    assert result.execution_context["total_steps"] == 3

    # Verify invoke_agent_with_retry called 3 times
    assert mock_invoke.call_count == 3
    mock_cache_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_graph_conditional_path_selection(conditional_graph_spec: Spec, mocker):
    """Test conditional edge path selection based on score."""
    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    # Mock invoke_agent_with_retry
    mock_invoke = mocker.patch("strands_cli.exec.graph.invoke_agent_with_retry")
    mock_invoke.side_effect = [
        "Analysis result",
        "Path A response",
    ]

    # Mock condition evaluation to choose path A
    mocker.patch("strands_cli.exec.graph.evaluate_condition", return_value=True)

    result = await run_graph(conditional_graph_spec)

    # Should execute check -> handle_a (not handle_b)
    # Note: All nodes get initialized, but only check and handle_a should be executed
    executed_nodes = [
        k for k, v in result.execution_context["nodes"].items()
        if v["status"] == "success"
    ]
    assert executed_nodes == ["check", "handle_a"]
    assert mock_invoke.call_count == 2
    mock_cache_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_graph_loop_with_iteration_limit(loop_graph_spec: Spec, mocker):
    """Test loop execution with iteration limit enforcement."""
    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()

    # Mock responses for process -> check cycle (3 iterations) -> finalize
    mock_agent.invoke_async = AsyncMock(side_effect=[
        MagicMock(text="Process 1"),
        MagicMock(text="Continue"),
        MagicMock(text="Process 2"),
        MagicMock(text="Continue"),
        MagicMock(text="Process 3"),
        MagicMock(text="Done"),
        MagicMock(text="Final result"),
    ])

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    # Mock condition evaluation: loop 3 times, then exit
    def mock_eval(expr, context):
        if "iteration >= 3" in expr:
            # Extract actual iteration from context
            process_iter = context.get("nodes", {}).get("process", {}).get("iteration", 0)
            return process_iter >= 3
        # Else clause: always true
        return True

    mocker.patch("strands_cli.exec.graph.evaluate_condition", side_effect=mock_eval)

    result = await run_graph(loop_graph_spec)

    # Should loop through process 3 times, then finalize
    assert result.execution_context["terminal_node"] == "finalize"
    assert result.execution_context["iteration_counts"]["process"] == 3


@pytest.mark.asyncio
async def test_run_graph_exceeds_global_max_steps(linear_graph_spec: Spec, mocker):
    """Test that global max_steps limit prevents runaway execution."""
    # Set low max_steps
    linear_graph_spec.runtime.budgets = {"max_steps": 2}

    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    # Mock invoke_agent_with_retry
    mock_invoke = mocker.patch("strands_cli.exec.graph.invoke_agent_with_retry")
    mock_invoke.side_effect = [
        "Response A",
        "Response B",
    ]

    result = await run_graph(linear_graph_spec)

    # Should stop after 2 steps (max_steps limit)
    assert result.execution_context["total_steps"] == 2
    # Should only execute node_a and node_b (node_c gets initialized but not executed)
    executed_nodes = [
        k for k, v in result.execution_context["nodes"].items()
        if v["status"] == "success"
    ]
    assert len(executed_nodes) == 2
    assert "node_a" in executed_nodes
    assert "node_b" in executed_nodes


@pytest.mark.asyncio
async def test_run_graph_no_nodes_raises_error():
    """Test that graph with no nodes raises error."""
    spec = Spec(
        version=0,
        name="invalid",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test")},
        pattern={"type": PatternType.GRAPH, "config": PatternConfig(nodes={}, edges=[])},
    )

    with pytest.raises(GraphExecutionError, match="has no nodes"):
        await run_graph(spec)


@pytest.mark.asyncio
async def test_run_graph_no_edges_raises_error():
    """Test that graph with no edges raises error."""
    spec = Spec(
        version=0,
        name="invalid",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test")},
        pattern={
            "type": PatternType.GRAPH,
            "config": PatternConfig(
                nodes={"node1": GraphNode(agent="agent1")},
                edges=[],
            ),
        },
    )

    with pytest.raises(GraphExecutionError, match="has no edges"):
        await run_graph(spec)


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_run_graph_agent_execution_failure(linear_graph_spec: Spec, mocker):
    """Test that agent execution failure is properly handled."""
    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=Exception("Agent failed"))

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    with pytest.raises(GraphExecutionError, match="execution failed"):
        await run_graph(linear_graph_spec)

    # Ensure cleanup happened
    mock_cache_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_graph_template_rendering_failure(linear_graph_spec: Spec, mocker):
    """Test that template rendering errors are caught."""
    # Make node input template invalid
    linear_graph_spec.pattern.config.nodes["node_b"].input = "{{ invalid | unknown_filter }}"

    mock_cache = mocker.patch("strands_cli.exec.graph.AgentCache")
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value=MagicMock(text="Response A"))

    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)
    mock_cache_instance.close = AsyncMock()

    with pytest.raises(GraphExecutionError, match="Failed to render input"):
        await run_graph(linear_graph_spec)

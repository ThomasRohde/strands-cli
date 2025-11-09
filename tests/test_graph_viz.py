"""Tests for graph visualization utilities.

Tests DOT format generation and text-based visualization for graph patterns.
"""

import pytest

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
from strands_cli.visualization.graph_viz import generate_dot, generate_text_visualization

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def minimal_graph_spec() -> Spec:
    """Create minimal valid graph for testing."""
    return Spec(
        version=0,
        name="test-graph",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test agent")},
        pattern={
            "type": PatternType.GRAPH,
            "config": PatternConfig(
                nodes={"node1": GraphNode(agent="agent1")},
                edges=[],  # Will cause invalid graph
            ),
        },
    )


@pytest.fixture
def linear_graph_spec() -> Spec:
    """Create simple linear graph: A -> B -> C."""
    return Spec(
        version=0,
        name="linear-graph",
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
                    "node_a": GraphNode(agent="agent_a"),
                    "node_b": GraphNode(agent="agent_b"),
                    "node_c": GraphNode(agent="agent_c"),
                },
                edges=[
                    GraphEdge(**{"from": "node_a", "to": ["node_b"]}),
                    GraphEdge(**{"from": "node_b", "to": ["node_c"]}),
                    # node_c is terminal
                ],
            ),
        },
    )


@pytest.fixture
def conditional_graph_spec() -> Spec:
    """Create graph with conditional edges."""
    return Spec(
        version=0,
        name="conditional-graph",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "checker": Agent(prompt="Check"),
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
                    GraphEdge(
                        **{
                            "from": "check",
                            "choose": [
                                ConditionalChoice(
                                    when="{{ nodes.check.score >= 85 }}", to="handle_a"
                                ),
                                ConditionalChoice(when="else", to="handle_b"),
                            ],
                        }
                    ),
                ],
            ),
        },
    )


# ============================================================================
# DOT Format Generation Tests
# ============================================================================


class TestDOTGeneration:
    """Tests for Graphviz DOT format generation."""

    def test_generate_dot_invalid_empty_graph(self, minimal_graph_spec):
        """Test DOT generation for invalid empty graph."""
        minimal_graph_spec.pattern.config.edges = []
        dot = generate_dot(minimal_graph_spec)
        assert "Invalid graph" in dot

    def test_generate_dot_invalid_no_nodes(self, minimal_graph_spec):
        """Test DOT generation when no nodes defined."""
        minimal_graph_spec.pattern.config.nodes = {}
        dot = generate_dot(minimal_graph_spec)
        assert "Invalid graph" in dot

    def test_generate_dot_basic_structure(self, linear_graph_spec):
        """Test basic DOT structure with nodes and edges."""
        dot = generate_dot(linear_graph_spec)

        # Check header
        assert "digraph workflow {" in dot
        assert "rankdir=TB" in dot  # Top to bottom layout

        # Check nodes are defined
        assert '"node_a"' in dot
        assert '"node_b"' in dot
        assert '"node_c"' in dot

        # Check edges
        assert '"node_a" -> "node_b"' in dot
        assert '"node_b" -> "node_c"' in dot

    def test_generate_dot_highlights_entry_node(self, linear_graph_spec):
        """Test entry node has green background."""
        dot = generate_dot(linear_graph_spec)
        assert "lightgreen" in dot
        assert "[ENTRY]" in dot

    def test_generate_dot_highlights_terminal_nodes(self, linear_graph_spec):
        """Test terminal nodes have red background."""
        dot = generate_dot(linear_graph_spec)
        assert "lightcoral" in dot
        assert "[TERMINAL]" in dot

    def test_generate_dot_conditional_edges_dashed(self, conditional_graph_spec):
        """Test conditional edges rendered with dashed style."""
        dot = generate_dot(conditional_graph_spec)
        assert "style=dashed" in dot

    def test_generate_dot_conditional_edge_labels(self, conditional_graph_spec):
        """Test conditional edges have condition labels."""
        dot = generate_dot(conditional_graph_spec)
        # Should have condition text (truncated if >30 chars)
        assert 'label=' in dot
        # Should have 'else' label
        assert 'else' in dot.lower()

    def test_generate_dot_escapes_quotes_in_conditions(self):
        """Test that condition labels properly escape quotes."""
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"node1": GraphNode(agent="agent1"), "node2": GraphNode(agent="agent1")},
                    edges=[
                        GraphEdge(
                            **{
                                "from": "node1",
                                "choose": [
                                    ConditionalChoice(when='{{ status == "done" }}', to="node2"),
                                ],
                            }
                        )
                    ],
                ),
            },
        )
        dot = generate_dot(spec)
        # Quotes should be escaped in DOT format
        assert '\\"' in dot

    def test_generate_dot_truncates_long_conditions(self):
        """Test long conditions are truncated with ellipsis."""
        long_condition = "{{ nodes.analyze.score >= 85 and nodes.analyze.quality > 90 and nodes.analyze.status == 'complete' }}"
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"node1": GraphNode(agent="agent1"), "node2": GraphNode(agent="agent1")},
                    edges=[
                        GraphEdge(
                            **{
                                "from": "node1",
                                "choose": [ConditionalChoice(when=long_condition, to="node2")],
                            }
                        )
                    ],
                ),
            },
        )
        dot = generate_dot(spec)
        # Should be truncated to ~30 chars
        assert "..." in dot

    def test_generate_dot_multiple_static_edges(self):
        """Test graph with multiple static edges from same node."""
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={
                        "node1": GraphNode(agent="agent1"),
                        "node2": GraphNode(agent="agent1"),
                        "node3": GraphNode(agent="agent1"),
                    },
                    edges=[
                        GraphEdge(**{"from": "node1", "to": ["node2", "node3"]}),
                    ],
                ),
            },
        )
        dot = generate_dot(spec)
        # Should show both edges
        assert '"node1" -> "node2"' in dot
        assert '"node1" -> "node3"' in dot


# ============================================================================
# Text Visualization Tests
# ============================================================================


class TestTextVisualization:
    """Tests for text-based graph visualization."""

    def test_text_viz_invalid_graph(self, minimal_graph_spec):
        """Test text visualization for invalid graph."""
        minimal_graph_spec.pattern.config.edges = []
        text = generate_text_visualization(minimal_graph_spec)
        assert "Invalid graph" in text

    def test_text_viz_basic_structure(self, linear_graph_spec):
        """Test basic text visualization structure."""
        text = generate_text_visualization(linear_graph_spec)

        # Check header
        assert "Graph Structure" in text
        assert "=" * 50 in text

        # Check sections
        assert "Entry Node:" in text
        assert "Terminal Nodes:" in text
        assert "Nodes:" in text
        assert "Edges:" in text

    def test_text_viz_shows_entry_node(self, linear_graph_spec):
        """Test entry node is marked."""
        text = generate_text_visualization(linear_graph_spec)
        assert "Entry Node: node_a" in text
        assert "[ENTRY]" in text

    def test_text_viz_shows_terminal_nodes(self, linear_graph_spec):
        """Test terminal nodes are listed."""
        text = generate_text_visualization(linear_graph_spec)
        assert "Terminal Nodes:" in text
        assert "node_c" in text
        assert "[TERMINAL]" in text

    def test_text_viz_warns_no_terminals(self):
        """Test warning when graph has no terminal nodes."""
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"node1": GraphNode(agent="agent1"), "node2": GraphNode(agent="agent1")},
                    edges=[
                        GraphEdge(**{"from": "node1", "to": ["node2"]}),
                        GraphEdge(**{"from": "node2", "to": ["node1"]}),  # Cycle
                    ],
                ),
            },
        )
        text = generate_text_visualization(spec)
        assert "infinite loop" in text.lower()

    def test_text_viz_displays_static_edges(self, linear_graph_spec):
        """Test static edges are displayed."""
        text = generate_text_visualization(linear_graph_spec)
        assert "node_a → node_b" in text
        assert "node_b → node_c" in text

    def test_text_viz_displays_conditional_edges(self, conditional_graph_spec):
        """Test conditional edges show with tree structure."""
        text = generate_text_visualization(conditional_graph_spec)
        # Check for tree-style display
        assert "→" in text
        assert "├─" in text or "if" in text

    def test_text_viz_truncates_long_conditions(self):
        """Test long conditions are truncated in text format."""
        long_condition = "{{ " + "x" * 100 + " }}"
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"node1": GraphNode(agent="agent1"), "node2": GraphNode(agent="agent1")},
                    edges=[
                        GraphEdge(
                            **{
                                "from": "node1",
                                "choose": [ConditionalChoice(when=long_condition, to="node2")],
                            }
                        )
                    ],
                ),
            },
        )
        text = generate_text_visualization(spec)
        # Should be truncated
        assert "..." in text

    def test_text_viz_handles_multiple_terminals(self):
        """Test multiple terminal nodes are listed."""
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={
                        "node1": GraphNode(agent="agent1"),
                        "node2": GraphNode(agent="agent1"),
                        "node3": GraphNode(agent="agent1"),
                    },
                    edges=[
                        GraphEdge(
                            **{
                                "from": "node1",
                                "choose": [
                                    ConditionalChoice(when="{{ a }}", to="node2"),
                                    ConditionalChoice(when="else", to="node3"),
                                ],
                            }
                        ),
                    ],
                ),
            },
        )
        text = generate_text_visualization(spec)
        # Both node2 and node3 are terminals
        assert "node2" in text
        assert "node3" in text

    def test_dot_single_node_graph(self):
        """Test DOT generation for single-node terminal graph."""
        # Single-node graph needs at least one edge (can be from node to itself)
        # Or test that validation rejects edgeless graphs
        spec = Spec(
            version=0,
            name="single-node",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"only_node": GraphNode(agent="agent1")},
                    edges=[],  # No edges - triggers invalid graph handling
                ),
            },
        )
        dot = generate_dot(spec)

        # Should indicate invalid graph (no edges)
        assert "Invalid graph" in dot

    def test_text_viz_single_node_graph(self):
        """Test text visualization for single-node terminal graph."""
        # Single-node graph needs at least one edge
        spec = Spec(
            version=0,
            name="single-node",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test")},
            pattern={
                "type": PatternType.GRAPH,
                "config": PatternConfig(
                    nodes={"only_node": GraphNode(agent="agent1")},
                    edges=[],
                ),
            },
        )
        text = generate_text_visualization(spec)

        # Should indicate invalid graph (no edges)
        assert "Invalid graph" in text

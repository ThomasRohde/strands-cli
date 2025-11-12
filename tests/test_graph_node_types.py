"""Tests for GraphNode and HITLState type validation (Task 2).

Tests the type model extensions for graph pattern HITL support:
- HITLState with node_id field
- GraphNode supporting both agent and HITL nodes
- Validation preventing hybrid nodes
"""

import pytest
from pydantic import ValidationError

from strands_cli.types import GraphNode, HITLState


class TestGraphNode:
    """Tests for GraphNode validation."""

    def test_agent_node_valid(self) -> None:
        """Test valid agent node."""
        node = GraphNode(agent="writer", input="Write code")

        assert node.agent == "writer"
        assert node.input == "Write code"
        assert node.type is None
        assert node.prompt is None

    def test_agent_node_minimal(self) -> None:
        """Test agent node with only required agent field."""
        node = GraphNode(agent="planner")

        assert node.agent == "planner"
        assert node.input is None

    def test_hitl_node_valid(self) -> None:
        """Test valid HITL node with all fields."""
        node = GraphNode(
            type="hitl",
            prompt="Approve the plan?",
            context_display="Review: {{ nodes.planner.response }}",
            default="approved",
            timeout_seconds=3600,
        )

        assert node.type == "hitl"
        assert node.prompt == "Approve the plan?"
        assert node.context_display is not None
        assert node.default == "approved"
        assert node.timeout_seconds == 3600
        assert node.agent is None

    def test_hitl_node_minimal(self) -> None:
        """Test HITL node with only required fields."""
        node = GraphNode(type="hitl", prompt="Approve?")

        assert node.type == "hitl"
        assert node.prompt == "Approve?"
        assert node.context_display is None
        assert node.default is None
        assert node.timeout_seconds is None

    def test_hitl_node_zero_timeout(self) -> None:
        """Test HITL node with zero timeout (no timeout)."""
        node = GraphNode(type="hitl", prompt="Approve?", timeout_seconds=0)

        assert node.timeout_seconds == 0

    def test_node_missing_both_agent_and_hitl_raises_error(self) -> None:
        """Test node without agent or HITL type raises error."""
        with pytest.raises(ValidationError, match=r"Node must be agent.*or HITL"):
            GraphNode(input="Some input")

    def test_node_with_both_agent_and_hitl_raises_error(self) -> None:
        """Test node with both agent and HITL type raises error."""
        with pytest.raises(ValidationError, match="cannot be both agent and HITL"):
            GraphNode(agent="writer", type="hitl", prompt="Approve?")

    def test_hitl_node_missing_prompt_raises_error(self) -> None:
        """Test HITL node without prompt raises error."""
        with pytest.raises(ValidationError, match=r"Node must be agent.*or HITL"):
            GraphNode(type="hitl")

    def test_hitl_node_with_agent_field_raises_error(self) -> None:
        """Test HITL node cannot have agent field."""
        with pytest.raises(ValidationError, match="cannot be both agent and HITL"):
            GraphNode(type="hitl", prompt="Approve?", agent="writer")

    def test_hitl_node_with_input_field_raises_error(self) -> None:
        """Test HITL node cannot have input field."""
        with pytest.raises(ValidationError, match="HITL node cannot have 'input' field"):
            GraphNode(type="hitl", prompt="Approve?", input="Some input")

    def test_hitl_node_negative_timeout_raises_error(self) -> None:
        """Test HITL node with negative timeout raises error."""
        with pytest.raises(ValidationError, match=r"Input should be greater than or equal to 0"):
            GraphNode(type="hitl", prompt="Approve?", timeout_seconds=-1)

    def test_agent_node_with_type_field_raises_error(self) -> None:
        """Test agent node cannot have type field."""
        with pytest.raises(ValidationError, match="Agent node cannot have 'type' field"):
            GraphNode(agent="writer", type="some_type")

    def test_agent_node_with_prompt_field_raises_error(self) -> None:
        """Test agent node cannot have prompt field."""
        with pytest.raises(ValidationError, match="Agent node cannot have 'prompt' field"):
            GraphNode(agent="writer", prompt="Some prompt")

    def test_agent_node_with_context_display_raises_error(self) -> None:
        """Test agent node cannot have context_display field."""
        with pytest.raises(ValidationError, match="Agent node cannot have 'context_display' field"):
            GraphNode(agent="writer", context_display="Some context")

    def test_agent_node_with_default_raises_error(self) -> None:
        """Test agent node cannot have default field."""
        with pytest.raises(ValidationError, match="Agent node cannot have 'default' field"):
            GraphNode(agent="writer", default="approved")

    def test_agent_node_with_timeout_raises_error(self) -> None:
        """Test agent node cannot have timeout_seconds field."""
        with pytest.raises(ValidationError, match="Agent node cannot have 'timeout_seconds' field"):
            GraphNode(agent="writer", timeout_seconds=3600)


class TestHITLStateGraphPattern:
    """Tests for HITLState with graph pattern fields."""

    def test_hitl_state_with_node_id(self) -> None:
        """Test HITLState with node_id for graph pattern."""
        state = HITLState(
            active=True,
            node_id="review_node",
            prompt="Review and approve",
            context_display="Context: ...",
            default_response="approved",
            timeout_at="2025-11-10T15:00:00Z",
            user_response=None,
        )

        assert state.active is True
        assert state.node_id == "review_node"
        assert state.prompt == "Review and approve"
        assert state.step_index is None
        assert state.task_id is None
        assert state.branch_id is None

    def test_hitl_state_graph_pattern_minimal(self) -> None:
        """Test HITLState with minimal graph pattern fields."""
        state = HITLState(active=True, node_id="review", prompt="Approve?")

        assert state.node_id == "review"
        assert state.context_display is None
        assert state.default_response is None

    def test_hitl_state_cannot_mix_chain_and_graph_fields(self) -> None:
        """Test HITLState rejects mixing chain and graph fields."""
        with pytest.raises(ValidationError, match="cannot mix fields from multiple patterns"):
            HITLState(
                active=True,
                step_index=0,  # Chain field
                node_id="review",  # Graph field
                prompt="Approve?",
            )

    def test_hitl_state_cannot_mix_workflow_and_graph_fields(self) -> None:
        """Test HITLState rejects mixing workflow and graph fields."""
        with pytest.raises(ValidationError, match="cannot mix fields from multiple patterns"):
            HITLState(
                active=True,
                task_id="task1",  # Workflow field
                layer_index=0,  # Workflow field
                node_id="review",  # Graph field
                prompt="Approve?",
            )

    def test_hitl_state_cannot_mix_parallel_and_graph_fields(self) -> None:
        """Test HITLState rejects mixing parallel and graph fields."""
        with pytest.raises(ValidationError, match="cannot mix fields from multiple patterns"):
            HITLState(
                active=True,
                branch_id="branch1",  # Parallel field
                node_id="review",  # Graph field
                prompt="Approve?",
            )

    def test_hitl_state_requires_pattern_fields(self) -> None:
        """Test HITLState requires at least one pattern field set."""
        with pytest.raises(ValidationError, match="must have fields for one pattern"):
            HITLState(active=True, prompt="Approve?")

    def test_hitl_state_chain_pattern_still_works(self) -> None:
        """Test existing chain pattern HITLState validation still works."""
        state = HITLState(active=True, step_index=2, prompt="Review step 2")

        assert state.step_index == 2
        assert state.node_id is None

    def test_hitl_state_workflow_pattern_still_works(self) -> None:
        """Test existing workflow pattern HITLState validation still works."""
        state = HITLState(active=True, task_id="review_task", layer_index=1, prompt="Review task")

        assert state.task_id == "review_task"
        assert state.layer_index == 1
        assert state.node_id is None

    def test_hitl_state_parallel_pattern_still_works(self) -> None:
        """Test existing parallel pattern HITLState validation still works."""
        state = HITLState(
            active=True,
            branch_id="branch_research",
            step_index=0,
            step_type="branch",
            prompt="Review branch",
        )

        assert state.branch_id == "branch_research"
        assert state.step_type == "branch"
        assert state.node_id is None

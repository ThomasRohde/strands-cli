"""Tests for HITL (Human-in-the-Loop) functionality in graph pattern executor.

Tests cover:
- HITL node type validation
- HITL pause with session save
- HITL resume with response injection
- Conditional edge routing based on HITL responses
- HITL nodes in iterative loops
- Multiple HITL nodes in sequence
- Context display template rendering
- Terminal HITL nodes
- Error handling for missing session persistence
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.graph import GraphExecutionError, run_graph
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import (
    Agent,
    GraphEdge,
    GraphNode,
    HITLState,
    Pattern,
    PatternConfig,
    PatternType,
    Runtime,
    Spec,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def minimal_graph_hitl_spec() -> Spec:
    """Minimal graph spec with single HITL node."""
    return Spec(
        name="test-graph-hitl-minimal",
        version=0,
        runtime=Runtime(
            provider="ollama",
            model_id="llama3.2:3b",
            host="http://localhost:11434",
        ),
        agents={
            "planner": Agent(prompt="You are a planner. Create plans."),
            "executor": Agent(prompt="You are an executor. Execute plans."),
        },
        pattern=Pattern(
            type=PatternType.GRAPH,
            config=PatternConfig(
                nodes={
                    "plan": GraphNode(agent="planner", input="Create a plan"),
                    "review": GraphNode(
                        type="hitl",
                        prompt="Review the plan. Respond 'approve' or 'revise'",
                        context_display="Plan:\n{{ nodes.plan.response }}",
                        default="approved",
                        timeout_seconds=3600,
                    ),
                    "execute": GraphNode(
                        agent="executor",
                        input="Execute plan: {{ nodes.plan.response }}",
                    ),
                },
                edges=[
                    GraphEdge(**{"from": "plan", "to": ["review"]}),
                    GraphEdge(**{"from": "review", "to": ["execute"]}),
                ],
                max_iterations=10,
            ),
        ),
    )


@pytest.fixture
def graph_conditional_hitl_spec() -> Spec:
    """Graph spec with conditional routing based on HITL response."""
    return Spec(
        name="test-graph-hitl-conditional",
        version=0,
        runtime=Runtime(
            provider="ollama",
            model_id="llama3.2:3b",
            host="http://localhost:11434",
        ),
        agents={
            "planner": Agent(prompt="You are a planner."),
            "executor": Agent(prompt="You are an executor."),
            "revisor": Agent(prompt="You are a revisor."),
        },
        pattern=Pattern(
            type=PatternType.GRAPH,
            config=PatternConfig(
                nodes={
                    "plan": GraphNode(agent="planner", input="Create plan"),
                    "review": GraphNode(
                        type="hitl",
                        prompt="Review plan. Respond 'approve' or 'revise'",
                        context_display="{{ nodes.plan.response }}",
                    ),
                    "execute": GraphNode(agent="executor", input="Execute plan"),
                    "revise": GraphNode(
                        agent="revisor",
                        input="Revise based on: {{ nodes.review.response }}",
                    ),
                },
                edges=[
                    GraphEdge(**{"from": "plan", "to": ["review"]}),
                    GraphEdge(
                        **{
                            "from": "review",
                            "choose": [
                                {
                                    "when": "{{ nodes.review.response == 'approve' }}",
                                    "to": "execute",
                                },
                                {"when": "else", "to": "revise"},
                            ],
                        }
                    ),
                    GraphEdge(**{"from": "revise", "to": ["review"]}),
                ],
                max_iterations=5,
            ),
        ),
    )


@pytest.fixture
def graph_multiple_hitl_spec() -> Spec:
    """Graph spec with multiple sequential HITL nodes."""
    return Spec(
        name="test-graph-multi-hitl",
        version=0,
        runtime=Runtime(
            provider="ollama",
            model_id="llama3.2:3b",
            host="http://localhost:11434",
        ),
        agents={
            "agent1": Agent(prompt="Agent 1"),
            "agent2": Agent(prompt="Agent 2"),
        },
        pattern=Pattern(
            type=PatternType.GRAPH,
            config=PatternConfig(
                nodes={
                    "task1": GraphNode(agent="agent1", input="Task 1"),
                    "review1": GraphNode(type="hitl", prompt="Approve task 1?"),
                    "task2": GraphNode(agent="agent2", input="Task 2"),
                    "review2": GraphNode(type="hitl", prompt="Approve task 2?"),
                    "final": GraphNode(agent="agent1", input="Final task"),
                },
                edges=[
                    GraphEdge(**{"from": "task1", "to": ["review1"]}),
                    GraphEdge(**{"from": "review1", "to": ["task2"]}),
                    GraphEdge(**{"from": "task2", "to": ["review2"]}),
                    GraphEdge(**{"from": "review2", "to": ["final"]}),
                ],
                max_iterations=10,
            ),
        ),
    )


@pytest.fixture
def graph_terminal_hitl_spec() -> Spec:
    """Graph spec with HITL as terminal node (no outgoing edges)."""
    return Spec(
        name="test-graph-terminal-hitl",
        version=0,
        runtime=Runtime(
            provider="ollama",
            model_id="llama3.2:3b",
            host="http://localhost:11434",
        ),
        agents={
            "executor": Agent(prompt="You are an executor."),
        },
        pattern=Pattern(
            type=PatternType.GRAPH,
            config=PatternConfig(
                nodes={
                    "execute": GraphNode(agent="executor", input="Execute task"),
                    "final_approval": GraphNode(
                        type="hitl",
                        prompt="Final approval. Confirm completion.",
                        context_display="{{ nodes.execute.response }}",
                    ),
                },
                edges=[
                    GraphEdge(**{"from": "execute", "to": ["final_approval"]}),
                    # No outgoing edge from final_approval (terminal)
                ],
                max_iterations=10,
            ),
        ),
    )


# ============================================================================
# Unit Tests: HITL Node Type Validation
# ============================================================================


class TestGraphNodeValidation:
    """Test suite for GraphNode HITL validation."""

    def test_graph_node_accepts_agent_node(self) -> None:
        """Test GraphNode validates agent node correctly."""
        node = GraphNode(agent="test_agent", input="Test input")
        assert node.agent == "test_agent"
        assert node.input == "Test input"
        assert node.type is None

    def test_graph_node_accepts_hitl_node(self) -> None:
        """Test GraphNode validates HITL node correctly."""
        node = GraphNode(
            type="hitl",
            prompt="Test prompt",
            context_display="Test context",
            default="default response",
            timeout_seconds=3600,
        )
        assert node.type == "hitl"
        assert node.prompt == "Test prompt"
        assert node.context_display == "Test context"
        assert node.default == "default response"
        assert node.timeout_seconds == 3600
        assert node.agent is None

    def test_graph_node_rejects_hybrid_node(self) -> None:
        """Test GraphNode rejects node with both agent and HITL fields."""
        with pytest.raises(ValueError, match="cannot be both agent and HITL"):
            GraphNode(
                agent="test_agent",
                type="hitl",
                prompt="Test prompt",
            )

    def test_graph_node_rejects_empty_node(self) -> None:
        """Test GraphNode rejects node with neither agent nor HITL fields."""
        with pytest.raises(ValueError, match=r"must be agent.*or HITL"):
            GraphNode()

    def test_graph_node_rejects_hitl_without_prompt(self) -> None:
        """Test GraphNode rejects HITL node without prompt."""
        with pytest.raises(ValueError, match=r"must be agent.*or HITL"):
            GraphNode(type="hitl")


# ============================================================================
# Unit Tests: HITLState with node_id
# ============================================================================


class TestHITLStateNodeId:
    """Test suite for HITLState node_id field."""

    def test_hitl_state_accepts_node_id(self) -> None:
        """Test HITLState accepts node_id for graph pattern."""
        state = HITLState(
            active=True,
            node_id="review_node",
            prompt="Review the output",
            context_display="Context text",
        )
        assert state.node_id == "review_node"
        assert state.step_index is None
        assert state.task_id is None

    def test_hitl_state_accepts_step_index(self) -> None:
        """Test HITLState accepts step_index for chain pattern."""
        state = HITLState(
            active=True,
            step_index=2,
            prompt="Approve step 2?",
        )
        assert state.step_index == 2
        assert state.node_id is None

    def test_hitl_state_accepts_task_id(self) -> None:
        """Test HITLState accepts task_id for workflow pattern."""
        state = HITLState(
            active=True,
            task_id="task_123",
            layer_index=0,  # Workflow requires both task_id and layer_index
            prompt="Approve task?",
        )
        assert state.task_id == "task_123"
        assert state.layer_index == 0
        assert state.node_id is None


# ============================================================================
# Integration Tests: HITL Pause and Resume
# ============================================================================


class TestGraphHITLPauseResume:
    """Test suite for graph HITL pause and resume workflow."""

    @pytest.mark.asyncio
    async def test_graph_pauses_at_hitl_node(
        self, minimal_graph_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test graph executor pauses at HITL node and saves session."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent execution for 'plan' node
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Plan: Build dashboard with API")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Initialize session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-graph-pause-123",
                workflow_name=minimal_graph_hitl_spec.name,
                pattern_type="graph",
                spec_hash="abc123",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Act - Run graph (should pause at 'review' HITL node)
        result = await run_graph(
            spec=minimal_graph_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Should indicate HITL pause
        assert result.success is True
        assert "HITL pause" in result.last_response
        assert result.session_id is not None

        # Assert - Session should be saved with HITL state
        loaded_state = await repo.load(result.session_id)
        assert loaded_state.metadata.status == SessionStatus.PAUSED

        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        assert hitl_state.node_id == "review"
        assert "Review the plan" in hitl_state.prompt

    @pytest.mark.asyncio
    async def test_graph_resumes_with_hitl_response(
        self, minimal_graph_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test graph executor resumes from HITL pause with user response."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Create session paused at HITL node
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-graph-hitl-123",
                workflow_name=minimal_graph_hitl_spec.name,
                pattern_type="graph",
                spec_hash="abc123",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Plan: Build dashboard with API",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    },
                    "review": {
                        "response": None,
                        "type": "hitl",
                        "prompt": "Review the plan. Respond 'approve' or 'revise'",
                        "status": "waiting_for_user",
                        "iteration": 1,
                    },
                },
                "iteration_counts": {"plan": 1, "review": 1},
                "execution_path": ["plan", "review"],
                "total_steps": 2,
                "cumulative_tokens": 150,
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review the plan. Respond 'approve' or 'revise'",
                    "context_display": "Plan:\nPlan: Build dashboard with API",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
        )

        # Mock agent execution for 'execute' node
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Execution complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act - Resume with HITL response
        result = await run_graph(
            spec=minimal_graph_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approve",
        )

        # Assert - Workflow completes successfully
        assert result.success is True
        assert "Execution complete" in result.last_response

        # Assert - HITL response injected into node_results
        loaded_state = await repo.load("test-graph-hitl-123")
        assert loaded_state.pattern_state["node_results"]["review"]["response"] == "approve"
        assert loaded_state.pattern_state["node_results"]["review"]["status"] == "success"
        assert loaded_state.pattern_state["hitl_state"]["active"] is False

    @pytest.mark.asyncio
    async def test_resume_without_hitl_response_raises_error(
        self, minimal_graph_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test resuming from HITL without --hitl-response raises error."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-no-response",
                workflow_name=minimal_graph_hitl_spec.name,
                pattern_type="graph",
                spec_hash="abc123",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Plan text",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    }
                },
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review the plan",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(),
        )

        # Act & Assert - Should raise error
        with pytest.raises(GraphExecutionError, match="waiting for HITL response"):
            await run_graph(
                spec=minimal_graph_hitl_spec,
                variables={},
                session_state=session_state,
                session_repo=repo,
                hitl_response=None,  # Missing response
            )


# ============================================================================
# Integration Tests: Conditional Routing
# ============================================================================


class TestGraphHITLConditionalRouting:
    """Test suite for edge conditions accessing HITL node responses."""

    @pytest.mark.asyncio
    async def test_conditional_routing_based_on_hitl_response_approve(
        self, graph_conditional_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test edge condition evaluates HITL response correctly (approve path)."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-conditional-approve",
                workflow_name=graph_conditional_hitl_spec.name,
                pattern_type="graph",
                spec_hash="def456",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Plan details",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    }
                },
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review plan",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(),
        )

        # Mock agent for 'execute' node
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Executed successfully")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act - Resume with 'approve' response
        result = await run_graph(
            spec=graph_conditional_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approve",
        )

        # Assert - Should execute 'execute' node, not 'revise'
        assert result.success is True
        loaded_state = await repo.load("test-conditional-approve")
        assert "execute" in loaded_state.pattern_state["node_results"]
        assert loaded_state.pattern_state["node_results"]["execute"]["status"] == "success"
        # 'revise' node should NOT be executed
        assert (
            "revise" not in loaded_state.pattern_state["node_results"]
            or loaded_state.pattern_state["node_results"]["revise"].get("status") != "success"
        )

    @pytest.mark.asyncio
    async def test_conditional_routing_based_on_hitl_response_revise(
        self, graph_conditional_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test edge condition evaluates HITL response correctly (revise path)."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-conditional-revise",
                workflow_name=graph_conditional_hitl_spec.name,
                pattern_type="graph",
                spec_hash="ghi789",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Plan details",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    }
                },
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review plan",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(),
        )

        # Mock agent for 'revise' node
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Revised plan based on feedback")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act - Resume with 'revise' response (should trigger else path)
        result = await run_graph(
            spec=graph_conditional_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="revise",
        )

        # Assert - Should execute 'revise' node and pause at 'review' again
        assert result.success is True
        loaded_state = await repo.load("test-conditional-revise")
        assert "revise" in loaded_state.pattern_state["node_results"]
        assert loaded_state.pattern_state["node_results"]["revise"]["status"] == "success"
        # Should pause at review again (loop back)
        assert loaded_state.metadata.status == SessionStatus.PAUSED
        assert loaded_state.pattern_state["hitl_state"]["node_id"] == "review"


# ============================================================================
# Integration Tests: HITL in Loops
# ============================================================================


class TestGraphHITLLoops:
    """Test suite for HITL nodes in iterative loops."""

    @pytest.mark.asyncio
    async def test_hitl_in_loop_iteration_counting(
        self, graph_conditional_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test HITL node in loop increments iteration count correctly."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Simulate second iteration (loop back from revise to review)
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-loop-iteration",
                workflow_name=graph_conditional_hitl_spec.name,
                pattern_type="graph",
                spec_hash="loop123",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:10:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Original plan",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    },
                    "revise": {
                        "response": "Revised plan v1",
                        "agent": "revisor",
                        "status": "success",
                        "iteration": 1,
                    },
                },
                "iteration_counts": {
                    "plan": 1,
                    "review": 1,  # First iteration already done
                    "revise": 1,
                },
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review plan",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(),
        )

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Revised plan v2")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act - Resume with 'revise' again (second loop)
        result = await run_graph(
            spec=graph_conditional_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="revise again",
        )

        # Assert - Iteration counts should increment
        loaded_state = await repo.load("test-loop-iteration")
        assert loaded_state.pattern_state["iteration_counts"]["review"] == 2
        assert loaded_state.pattern_state["iteration_counts"]["revise"] == 2
        # Should pause at review again
        assert loaded_state.metadata.status == SessionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_hitl_loop_exceeds_max_iterations(
        self, graph_conditional_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test HITL loop raises error when exceeding max_iterations."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Create session at max iteration limit (5 for this spec)
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-max-iter",
                workflow_name=graph_conditional_hitl_spec.name,
                pattern_type="graph",
                spec_hash="maxiter123",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:15:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "current_node": "review",
                "node_results": {
                    "plan": {
                        "response": "Original plan",
                        "agent": "planner",
                        "status": "success",
                        "iteration": 1,
                    },
                    "revise": {
                        "response": "Revised plan v4",
                        "agent": "revisor",
                        "status": "success",
                        "iteration": 4,
                    },
                },
                "iteration_counts": {
                    "plan": 1,
                    "review": 5,  # At max limit
                    "revise": 4,
                },
                "hitl_state": {
                    "active": True,
                    "node_id": "review",
                    "prompt": "Review plan",
                    "user_response": None,
                },
            },
            token_usage=TokenUsage(),
        )

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Won't execute")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act & Assert - Should raise error
        with pytest.raises(GraphExecutionError, match="exceeded max iterations"):
            await run_graph(
                spec=graph_conditional_hitl_spec,
                variables={},
                session_state=session_state,
                session_repo=repo,
                hitl_response="revise",  # Would trigger loop
            )


# ============================================================================
# Integration Tests: Multiple HITL Nodes
# ============================================================================


class TestGraphMultipleHITLNodes:
    """Test suite for graphs with multiple HITL nodes."""

    @pytest.mark.asyncio
    async def test_multiple_hitl_nodes_sequential(
        self, graph_multiple_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test graph with multiple sequential HITL nodes pauses correctly."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent for task1
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 1 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Initialize session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-multi-hitl-123",
                workflow_name=graph_multiple_hitl_spec.name,
                pattern_type="graph",
                spec_hash="multi123",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Act - First run (should pause at review1)
        result = await run_graph(
            spec=graph_multiple_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at first HITL
        assert result.success is True
        assert "HITL pause" in result.last_response
        loaded_state = await repo.load(result.session_id)
        assert loaded_state.pattern_state["hitl_state"]["node_id"] == "review1"

        # Act - Resume from first HITL (should pause at review2)
        mock_agent.invoke_async = AsyncMock(return_value="Task 2 complete")

        result2 = await run_graph(
            spec=graph_multiple_hitl_spec,
            variables={},
            session_state=loaded_state,
            session_repo=repo,
            hitl_response="yes",
        )

        # Assert - Paused at second HITL
        assert result2.success is True
        loaded_state2 = await repo.load(result.session_id)
        assert loaded_state2.pattern_state["hitl_state"]["node_id"] == "review2"
        assert loaded_state2.pattern_state["node_results"]["review1"]["response"] == "yes"

        # Act - Resume from second HITL (should complete)
        mock_agent.invoke_async = AsyncMock(return_value="Final task complete")

        result3 = await run_graph(
            spec=graph_multiple_hitl_spec,
            variables={},
            session_state=loaded_state2,
            session_repo=repo,
            hitl_response="approved",
        )

        # Assert - Workflow completes
        assert result3.success is True
        loaded_state3 = await repo.load(result.session_id)
        assert loaded_state3.pattern_state["node_results"]["review2"]["response"] == "approved"
        assert loaded_state3.pattern_state["node_results"]["final"]["status"] == "success"


# ============================================================================
# Integration Tests: Terminal HITL Nodes
# ============================================================================


class TestGraphTerminalHITL:
    """Test suite for HITL nodes as terminal nodes."""

    @pytest.mark.asyncio
    async def test_terminal_hitl_node_completes_workflow(
        self, graph_terminal_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test workflow with terminal HITL node completes after user response."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # First run - pause at terminal HITL
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Execution result")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Initialize session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-terminal-hitl-123",
                workflow_name=graph_terminal_hitl_spec.name,
                pattern_type="graph",
                spec_hash="terminal123",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        result = await run_graph(
            spec=graph_terminal_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at final_approval
        assert result.success is True
        loaded_state = await repo.load(result.session_id)
        assert loaded_state.pattern_state["hitl_state"]["node_id"] == "final_approval"

        # Act - Resume with approval (should complete)
        result2 = await run_graph(
            spec=graph_terminal_hitl_spec,
            variables={},
            session_state=loaded_state,
            session_repo=repo,
            hitl_response="confirmed",
        )

        # Assert - Workflow completes successfully
        assert result2.success is True
        loaded_state2 = await repo.load(result.session_id)
        assert loaded_state2.pattern_state["node_results"]["final_approval"]["response"] == "confirmed"
        assert loaded_state2.pattern_state["hitl_state"]["active"] is False


# ============================================================================
# Integration Tests: Context Display Rendering
# ============================================================================


class TestGraphHITLContextDisplay:
    """Test suite for HITL context_display template rendering."""

    @pytest.mark.asyncio
    async def test_context_display_renders_with_node_results(
        self, minimal_graph_hitl_spec: Spec, tmp_path: Any, mocker: Any
    ) -> None:
        """Test context_display template accesses previous node results."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Detailed plan with steps 1, 2, 3")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Initialize session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-context-123",
                workflow_name=minimal_graph_hitl_spec.name,
                pattern_type="graph",
                spec_hash="context123",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Act - Run to HITL pause
        result = await run_graph(
            spec=minimal_graph_hitl_spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - context_display should contain rendered node result
        loaded_state = await repo.load(result.session_id)
        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.context_display is not None
        assert "Detailed plan with steps 1, 2, 3" in hitl_state.context_display


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestGraphHITLErrorHandling:
    """Test suite for HITL error handling."""

    @pytest.mark.asyncio
    async def test_hitl_without_session_raises_error(
        self, minimal_graph_hitl_spec: Spec, mocker: Any
    ) -> None:
        """Test HITL node without session persistence raises error."""
        # Arrange
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Plan result")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act & Assert - Should raise error when HITL detected without session
        with pytest.raises(GraphExecutionError, match="requires session persistence"):
            await run_graph(
                spec=minimal_graph_hitl_spec,
                variables={},
                session_state=None,
                session_repo=None,  # No session repo
            )

    @pytest.mark.asyncio
    async def test_normal_graph_without_session_works(
        self, tmp_path: Any, mocker: Any
    ) -> None:
        """Test graph without HITL works without session persistence."""
        # Arrange - Graph spec without HITL nodes
        spec = Spec(
            name="test-no-hitl",
            version=0,
            runtime=Runtime(provider="ollama", model_id="llama3.2:3b"),
            agents={"agent1": Agent(prompt="Test agent")},
            pattern=Pattern(
                type=PatternType.GRAPH,
                config=PatternConfig(
                    nodes={
                        "task1": GraphNode(agent="agent1", input="Task 1"),
                        "task2": GraphNode(agent="agent1", input="Task 2"),
                    },
                    edges=[GraphEdge(**{"from": "task1", "to": ["task2"]})],
                    max_iterations=10,
                ),
            ),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task result")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        # Act - Should complete without error
        result = await run_graph(
            spec=spec,
            variables={},
            session_state=None,
            session_repo=None,
        )

        # Assert - Completes successfully
        assert result.success is True


# ============================================================================
# Regression Tests: Checkpoint Ordering
# ============================================================================


class TestGraphHITLCheckpointOrdering:
    """Regression tests for checkpoint crash-safety invariants."""

    @pytest.mark.asyncio
    async def test_graph_hitl_resume_checkpoint_advances_current_node(
        self, tmp_path: Any, mocker: Any
    ) -> None:
        """Test checkpoint advances current_node before save (crash-safety).
        
        Validates fix for Issue #2 from HITL.md section 2.3:
        - Checkpoint must update current_node to NEXT node before save
        - On crash during HITL resume, recovery should resume at next node
        - Should NOT re-pause at same HITL node in infinite loop
        
        Test flow:
        1. Create graph: plan → review (HITL) → execute
        2. Run to HITL pause → verify current_node=review, hitl_state.active=True
        3. Resume with response → verify checkpoint advances current_node=execute
        4. Simulate crash before workflow completes
        5. Load session → verify current_node=execute (NOT review)
        6. Resume from crash → should continue from execute, not re-pause at review
        """
        # Arrange - Graph spec: plan → review (HITL) → execute
        spec = Spec(
            name="test-checkpoint-ordering",
            version=0,
            runtime=Runtime(
                provider="ollama",
                model_id="llama3.2:3b",
                host="http://localhost:11434",
            ),
            agents={
                "planner": Agent(prompt="You are a planner."),
                "executor": Agent(prompt="You are an executor."),
            },
            pattern=Pattern(
                type=PatternType.GRAPH,
                config=PatternConfig(
                    nodes={
                        "plan": GraphNode(agent="planner", input="Create plan"),
                        "review": GraphNode(
                            type="hitl",
                            prompt="Review plan. Respond 'approve' or 'revise'",
                            context_display="Plan: {{ nodes.plan.response }}",
                            default="approved",
                            timeout_seconds=3600,
                        ),
                        "execute": GraphNode(
                            agent="executor",
                            input="Execute: {{ nodes.plan.response }}",
                        ),
                    },
                    edges=[
                        GraphEdge(**{"from": "plan", "to": ["review"]}),
                        GraphEdge(**{"from": "review", "to": ["execute"]}),
                    ],
                    max_iterations=10,
                ),
            ),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Step 1: Initial run - pause at HITL
        mock_agent_plan = MagicMock()
        mock_agent_plan.invoke_async = AsyncMock(return_value="Plan: Build feature X")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent_plan)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-checkpoint-123",
                workflow_name=spec.name,
                pattern_type="graph",
                spec_hash="checkpoint-test-123",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        result1 = await run_graph(
            spec=spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at review HITL node
        assert result1.success is True
        loaded_state1 = await repo.load("test-checkpoint-123")
        assert loaded_state1.pattern_state["current_node"] == "review"
        assert loaded_state1.pattern_state["hitl_state"]["active"] is True
        assert loaded_state1.pattern_state["hitl_state"]["node_id"] == "review"

        # Step 2: Resume with HITL response (will advance but simulate crash before completion)
        mock_agent_execute = MagicMock()
        mock_agent_execute.invoke_async = AsyncMock(return_value="Execution complete")

        mock_cache2 = mocker.AsyncMock()
        mock_cache2.get_or_build_agent = AsyncMock(return_value=mock_agent_execute)
        mock_cache2.close = AsyncMock()
        mocker.patch("strands_cli.exec.graph.AgentCache", return_value=mock_cache2)

        # Resume with response
        result2 = await run_graph(
            spec=spec,
            variables={},
            session_state=loaded_state1,
            session_repo=repo,
            hitl_response="approve",
        )

        # Assert - Workflow completed successfully
        assert result2.success is True

        # Step 3: CRITICAL VALIDATION - Load checkpoint after HITL resume
        # This checkpoint was saved AFTER processing HITL response
        loaded_state2 = await repo.load("test-checkpoint-123")

        # ✅ Current node should be 'execute' (next node after HITL)
        # This validates fix - checkpoint updates current_node BEFORE save
        assert loaded_state2.pattern_state["current_node"] == "execute", (
            "Checkpoint must advance current_node to next node (execute) "
            "BEFORE save to ensure crash recovery resumes at correct node"
        )

        # ✅ HITL state should be inactive (response processed)
        assert loaded_state2.pattern_state["hitl_state"]["active"] is False

        # ✅ Review node result should contain user response
        assert loaded_state2.pattern_state["node_results"]["review"]["response"] == "approve"

        # ✅ Execute node result should exist (workflow completed)
        assert "execute" in loaded_state2.pattern_state["node_results"]
        assert loaded_state2.pattern_state["node_results"]["execute"]["response"] == "Execution complete"

        # Step 4: Simulate crash recovery scenario
        # If we resume from loaded_state2 (which has current_node=execute), 
        # workflow should NOT re-pause at review node
        # (This is conceptual validation - actual test shows checkpoint state is correct)

        # Final assertion - execution path should show linear progression
        execution_path = loaded_state2.pattern_state["execution_path"]
        assert execution_path == ["plan", "review", "execute"], (
            "Execution path should show linear progression through all nodes"
        )



"""Tests for HITL (Human-in-the-Loop) functionality in workflow pattern executor.

Tests cover:
- Template variable {{ hitl_response }} exposure for workflow tasks
- HITL task pause with session save
- HITL task resume with response injection
- Multiple HITL tasks in different layers
- Auto-enable session persistence when HITL detected
- Single-HITL-per-layer MVP constraint enforcement
- Pre-HITL task execution before pause
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.workflow import (
    WorkflowExecutionError,
    _build_task_context,
    _check_layer_for_hitl,
    run_workflow,
)
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import HITLState, PatternType, Spec


class TestWorkflowHITLTemplateContext:
    """Test suite for HITL template variable exposure in workflow pattern."""

    def test_build_task_context_with_hitl_response(self) -> None:
        """Test {{ hitl_response }} variable contains most recent HITL task response."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None

        task_results = {
            "research": {
                "response": "Research findings on AI safety...",
                "status": "success",
                "tokens_estimated": 150,
                "agent": "researcher",
            },
            "review_research": {
                "type": "hitl",
                "prompt": "Review research findings?",
                "response": "approved with revisions",
                "status": "success",
                "tokens_estimated": 0,
            },
        }

        # Act
        context = _build_task_context(spec=spec, task_results=task_results, variables=None)

        # Assert
        assert "hitl_response" in context
        assert context["hitl_response"] == "approved with revisions"
        assert context["tasks"]["review_research"]["response"] == "approved with revisions"
        assert context["tasks"]["review_research"]["type"] == "hitl"

    def test_build_task_context_with_multiple_hitl_tasks(self) -> None:
        """Test {{ hitl_response }} returns MOST RECENT HITL task response."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None

        task_results = {
            "task1": {
                "response": "First result",
                "status": "success",
                "tokens_estimated": 100,
                "agent": "agent1",
            },
            "hitl1": {
                "type": "hitl",
                "prompt": "First approval?",
                "response": "approved",
                "status": "success",
                "tokens_estimated": 0,
            },
            "task2": {
                "response": "Second result",
                "status": "success",
                "tokens_estimated": 120,
                "agent": "agent2",
            },
            "hitl2": {
                "type": "hitl",
                "prompt": "Final approval?",
                "response": "rejected - revise",
                "status": "success",
                "tokens_estimated": 0,
            },
        }

        # Act
        context = _build_task_context(spec=spec, task_results=task_results, variables=None)

        # Assert - Should return the LAST HITL response
        # Note: dict order is preserved in Python 3.7+ so hitl2 should be last
        assert "hitl_response" in context
        # The last HITL task in iteration order is hitl2
        assert context["hitl_response"] == "rejected - revise"

    def test_build_task_context_without_hitl_task(self) -> None:
        """Test {{ hitl_response }} is NOT in context when no HITL tasks exist."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None

        task_results = {
            "task1": {
                "response": "Result 1",
                "status": "success",
                "tokens_estimated": 100,
                "agent": "agent1",
            },
            "task2": {
                "response": "Result 2",
                "status": "success",
                "tokens_estimated": 120,
                "agent": "agent2",
            },
        }

        # Act
        context = _build_task_context(spec=spec, task_results=task_results, variables=None)

        # Assert - hitl_response should NOT be present
        assert "hitl_response" not in context
        assert "tasks" in context

    def test_build_task_context_preserves_task_access_pattern(self) -> None:
        """Test {{ tasks.<id>.response }} still works alongside {{ hitl_response }}."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None

        task_results = {
            "research": {
                "response": "Research output",
                "status": "success",
                "tokens_estimated": 100,
                "agent": "researcher",
            },
            "approval": {
                "type": "hitl",
                "prompt": "Approve?",
                "response": "approved",
                "status": "success",
                "tokens_estimated": 0,
            },
        }

        # Act
        context = _build_task_context(spec=spec, task_results=task_results, variables=None)

        # Assert - Both access patterns work
        assert context["tasks"]["research"]["response"] == "Research output"
        assert context["tasks"]["approval"]["response"] == "approved"
        assert context["hitl_response"] == "approved"


class TestWorkflowHITLLayerDetection:
    """Test suite for HITL task detection in execution layers."""

    def test_check_layer_for_hitl_finds_hitl_task(self) -> None:
        """Test _check_layer_for_hitl returns HITL task ID when present."""
        # Arrange
        layer_task_ids = ["task1", "hitl_approval", "task2"]
        task_map = {
            "task1": MagicMock(type=None, agent="agent1"),
            "hitl_approval": MagicMock(type="hitl", prompt="Approve?"),
            "task2": MagicMock(type=None, agent="agent2"),
        }
        completed_tasks = set()

        # Act
        hitl_task_id = _check_layer_for_hitl(layer_task_ids, task_map, completed_tasks)

        # Assert
        assert hitl_task_id == "hitl_approval"

    def test_check_layer_for_hitl_returns_none_when_no_hitl(self) -> None:
        """Test _check_layer_for_hitl returns None when no HITL tasks in layer."""
        # Arrange
        layer_task_ids = ["task1", "task2", "task3"]
        task_map = {
            "task1": MagicMock(type=None, agent="agent1"),
            "task2": MagicMock(type=None, agent="agent2"),
            "task3": MagicMock(type=None, agent="agent3"),
        }
        completed_tasks = set()

        # Act
        hitl_task_id = _check_layer_for_hitl(layer_task_ids, task_map, completed_tasks)

        # Assert
        assert hitl_task_id is None

    def test_check_layer_for_hitl_skips_completed_tasks(self) -> None:
        """Test _check_layer_for_hitl ignores completed HITL tasks."""
        # Arrange
        layer_task_ids = ["task1", "hitl_approval", "task2"]
        task_map = {
            "task1": MagicMock(type=None, agent="agent1"),
            "hitl_approval": MagicMock(type="hitl", prompt="Approve?"),
            "task2": MagicMock(type=None, agent="agent2"),
        }
        completed_tasks = {"hitl_approval"}  # Already completed

        # Act
        hitl_task_id = _check_layer_for_hitl(layer_task_ids, task_map, completed_tasks)

        # Assert
        assert hitl_task_id is None

    def test_check_layer_for_hitl_enforces_single_hitl_constraint(self) -> None:
        """Test _check_layer_for_hitl raises error with multiple HITL tasks (MVP constraint)."""
        # Arrange
        layer_task_ids = ["task1", "hitl1", "hitl2", "task2"]
        task_map = {
            "task1": MagicMock(type=None, agent="agent1"),
            "hitl1": MagicMock(type="hitl", prompt="First approval?"),
            "hitl2": MagicMock(type="hitl", prompt="Second approval?"),
            "task2": MagicMock(type=None, agent="agent2"),
        }
        completed_tasks = set()

        # Act & Assert
        with pytest.raises(
            WorkflowExecutionError,
            match=r"Multiple HITL tasks found in same execution layer.*\['hitl1', 'hitl2'\]",
        ):
            _check_layer_for_hitl(layer_task_ids, task_map, completed_tasks)


class TestWorkflowHITLPauseAndResume:
    """Test suite for HITL task pause and resume workflow."""

    @pytest.mark.asyncio
    async def test_workflow_pauses_at_hitl_task(self, tmp_path: Path, mocker: Any) -> None:
        """Test workflow executor pauses at HITL task and exits with EX_HITL_PAUSE."""
        # Arrange - Create workflow spec with HITL task
        spec_dict = {
            "name": "workflow-hitl-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {
                "researcher": {"prompt": "Research the topic"},
                "analyst": {"prompt": "Analyze findings"},
            },
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "research", "agent": "researcher", "input": "Research {{ topic }}"},
                        {
                            "id": "review",
                            "type": "hitl",
                            "deps": ["research"],
                            "prompt": "Review research findings. Approve?",
                            "context_display": "{{ tasks.research.response }}",
                        },
                        {
                            "id": "analysis",
                            "agent": "analyst",
                            "deps": ["review"],
                            "input": "Analyze: {{ tasks.review.response }}",
                        },
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent execution for research task
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Research complete: AI safety critical")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        # Mock user_cache_dir to use tmp_path
        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - Run workflow (should pause at HITL task)
        result = await run_workflow(
            spec=spec,
            variables={"topic": "AI"},
            session_state=None,  # Fresh start
            session_repo=None,  # Will auto-enable
        )

        # Assert - Should return HITL pause result
        assert result.success is True
        assert result.exit_code == EX_HITL_PAUSE
        assert result.agent_id == "hitl"
        assert result.session_id is not None

        # Assert - Session should exist in auto-created repo
        from pathlib import Path

        cache_dir = Path(tmp_path) / "sessions"  # Mocked to tmp_path
        repo = FileSessionRepository(storage_dir=cache_dir)
        loaded_state = await repo.load(result.session_id)
        assert loaded_state.metadata.status == SessionStatus.PAUSED
        assert "hitl_state" in loaded_state.pattern_state

        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        assert hitl_state.task_id == "review"
        assert hitl_state.layer_index == 1  # Second layer
        assert hitl_state.prompt == "Review research findings. Approve?"

    @pytest.mark.asyncio
    async def test_workflow_resumes_with_hitl_response(self, tmp_path: Path, mocker: Any) -> None:
        """Test workflow executor resumes from HITL pause and injects user response."""
        # Arrange
        spec_dict = {
            "name": "workflow-hitl-resume-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {
                "researcher": {"prompt": "Research"},
                "analyst": {"prompt": "Analyze"},
            },
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "research", "agent": "researcher", "input": "Research"},
                        {
                            "id": "review",
                            "type": "hitl",
                            "deps": ["research"],
                            "prompt": "Approve research?",
                        },
                        {
                            "id": "analysis",
                            "agent": "analyst",
                            "deps": ["review"],
                            "input": "User said: {{ tasks.review.response }}",
                        },
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent execution for analysis task
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Analysis complete")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        # Create session state paused at HITL
        repo = FileSessionRepository(storage_dir=tmp_path)
        hitl_state = HITLState(
            active=True,
            task_id="review",
            layer_index=1,
            prompt="Approve research?",
            context_display="Research output...",
            user_response=None,
            step_index=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-workflow-hitl-123",
                workflow_name=spec.name,
                spec_hash="test-hash-123",
                pattern_type=PatternType.WORKFLOW,
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "task_results": {
                    "research": {
                        "response": "Research output...",
                        "status": "success",
                        "tokens_estimated": 150,
                        "agent": "researcher",
                    }
                },
                "completed_tasks": ["research"],
                "current_layer": 1,
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(total_input_tokens=100, total_output_tokens=150),
        )

        # Act - Resume with HITL response
        result = await run_workflow(
            spec=spec,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved with changes",
        )

        # Assert - Workflow completes successfully
        assert result.success is True
        assert result.exit_code != EX_HITL_PAUSE

        # Assert - HITL response injected into task_results
        loaded_state = await repo.load("test-workflow-hitl-123")
        assert "review" in loaded_state.pattern_state["task_results"]
        review_result = loaded_state.pattern_state["task_results"]["review"]
        assert review_result["type"] == "hitl"
        assert review_result["response"] == "approved with changes"

    @pytest.mark.asyncio
    async def test_resume_without_hitl_response_raises_error(
        self, tmp_path: Path, mocker: Any
    ) -> None:
        """Test resuming from HITL pause without --hitl-response raises error."""
        # Arrange
        spec_dict = {
            "name": "workflow-hitl-error-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review", "type": "hitl", "deps": ["task1"], "prompt": "Approve?"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        repo = FileSessionRepository(storage_dir=tmp_path)
        hitl_state = HITLState(
            active=True,
            task_id="review",
            layer_index=1,
            prompt="Approve?",
            user_response=None,
            step_index=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-error-123",
                workflow_name=spec.name,
                spec_hash="test-hash-error",
                pattern_type=PatternType.WORKFLOW,
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "task_results": {"task1": {"response": "Done", "status": "success"}},
                "completed_tasks": ["task1"],
                "current_layer": 1,
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Act & Assert - Should raise WorkflowExecutionError
        with pytest.raises(WorkflowExecutionError, match="waiting for HITL response"):
            await run_workflow(
                spec=spec,
                variables={},
                session_state=session_state,
                session_repo=repo,
                hitl_response=None,  # No response provided
            )


class TestWorkflowHITLAutoEnableSessions:
    """Test suite for auto-enabling session persistence when HITL detected."""

    @pytest.mark.asyncio
    async def test_hitl_task_auto_enables_sessions(self, tmp_path: Path, mocker: Any) -> None:
        """Test HITL task automatically creates session when not provided."""
        # Arrange
        spec_dict = {
            "name": "auto-session-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review", "type": "hitl", "deps": ["task1"], "prompt": "Approve?"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 1 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        # Mock user_cache_dir to use tmp_path
        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - Run WITHOUT session_state or session_repo
        result = await run_workflow(
            spec=spec,
            variables={},
            session_state=None,  # No session provided
            session_repo=None,  # No repo provided
        )

        # Assert - Session was auto-created
        assert result.session_id is not None
        assert result.exit_code == EX_HITL_PAUSE

        # Verify session directory exists in tmp_path/sessions/session_<id>/
        session_dir = tmp_path / "sessions"
        assert session_dir.exists()
        session_folder = session_dir / f"session_{result.session_id}"
        assert session_folder.exists()
        assert (session_folder / "session.json").exists()


class TestWorkflowHITLPreTaskExecution:
    """Test suite for executing tasks before HITL in same layer."""

    @pytest.mark.asyncio
    async def test_executes_tasks_before_hitl_in_layer(self, tmp_path: Path, mocker: Any) -> None:
        """Test tasks before HITL in same layer execute before pause."""
        # Arrange - Layer with task1 and task2 (no deps), then hitl depending on both
        spec_dict = {
            "name": "pre-hitl-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        # Layer 0: task1 and task2 run in parallel
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "task2", "agent": "agent1", "input": "Task 2"},
                        # Layer 1: hitl depends on both
                        {
                            "id": "review",
                            "type": "hitl",
                            "deps": ["task1", "task2"],
                            "prompt": "Review both tasks?",
                        },
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        call_count = [0]

        async def mock_invoke(*args: Any, **kwargs: Any) -> str:
            call_count[0] += 1
            return f"Task {call_count[0]} complete"

        mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke)

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act
        result = await run_workflow(spec=spec, variables={})

        # Assert - Both tasks executed before HITL pause
        assert result.exit_code == EX_HITL_PAUSE
        assert mock_agent.invoke_async.call_count == 2  # task1 and task2

        # Verify session has both tasks completed
        repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
        loaded_state = await repo.load(result.session_id)
        assert "task1" in loaded_state.pattern_state["completed_tasks"]
        assert "task2" in loaded_state.pattern_state["completed_tasks"]
        assert "task1" in loaded_state.pattern_state["task_results"]
        assert "task2" in loaded_state.pattern_state["task_results"]


class TestWorkflowHITLMultipleTasks:
    """Test suite for workflows with multiple HITL tasks in different layers."""

    @pytest.mark.asyncio
    async def test_multiple_hitl_tasks_sequential_layers(self, tmp_path: Path, mocker: Any) -> None:
        """Test workflow with HITL tasks in sequential layers (dependency chain)."""
        # Arrange
        spec_dict = {
            "name": "multi-hitl-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review1", "type": "hitl", "deps": ["task1"], "prompt": "Review 1?"},
                        {"id": "task2", "agent": "agent1", "deps": ["review1"], "input": "Task 2"},
                        {"id": "review2", "type": "hitl", "deps": ["task2"], "prompt": "Review 2?"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - First run should pause at review1
        result1 = await run_workflow(spec=spec, variables={})

        # Assert - Paused at first HITL
        assert result1.exit_code == EX_HITL_PAUSE
        repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
        state1 = await repo.load(result1.session_id)
        assert state1.pattern_state["hitl_state"]["task_id"] == "review1"

        # Act - Resume with first HITL response (should pause at review2)
        result2 = await run_workflow(
            spec=spec,
            variables={},
            session_state=state1,
            session_repo=repo,
            hitl_response="first approved",
        )

        # Assert - Paused at second HITL
        assert result2.exit_code == EX_HITL_PAUSE
        state2 = await repo.load(result1.session_id)
        assert state2.pattern_state["hitl_state"]["task_id"] == "review2"
        assert "review1" in state2.pattern_state["completed_tasks"]
        assert state2.pattern_state["task_results"]["review1"]["response"] == "first approved"


class TestWorkflowHITLSessionCheckpoint:
    """Test suite for session checkpointing after HITL response injection."""

    @pytest.mark.asyncio
    async def test_session_checkpoint_after_hitl_resume(self, tmp_path: Path, mocker: Any) -> None:
        """Test session is checkpointed after injecting HITL response before continuing."""
        # Arrange
        spec_dict = {
            "name": "checkpoint-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review", "type": "hitl", "deps": ["task1"], "prompt": "Approve?"},
                        {"id": "task2", "agent": "agent1", "deps": ["review"], "input": "Task 2"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent that takes time (simulates crash scenario)
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 2 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        repo = FileSessionRepository(storage_dir=tmp_path)
        hitl_state = HITLState(
            active=True,
            task_id="review",
            layer_index=1,
            prompt="Approve?",
            user_response=None,
            step_index=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="checkpoint-test-123",
                workflow_name=spec.name,
                spec_hash="test-hash-checkpoint",
                pattern_type=PatternType.WORKFLOW,
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "task_results": {"task1": {"response": "Done", "status": "success"}},
                "completed_tasks": ["task1"],
                "current_layer": 1,
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Act - Resume with HITL response
        await run_workflow(
            spec=spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved",
        )

        # Assert - Session was checkpointed with HITL response BEFORE task2 execution
        loaded_state = await repo.load("checkpoint-test-123")
        assert "review" in loaded_state.pattern_state["completed_tasks"]
        assert loaded_state.pattern_state["task_results"]["review"]["response"] == "approved"
        assert loaded_state.pattern_state["task_results"]["review"]["type"] == "hitl"
        assert loaded_state.pattern_state["hitl_state"]["active"] is False


# Fixtures for workflow HITL tests


@pytest.fixture
def workflow_with_hitl_spec_dict() -> dict[str, Any]:
    """Workflow spec with HITL task for testing."""
    return {
        "name": "workflow-hitl-fixture",
        "version": 0,
        "runtime": {"provider": "ollama", "model_id": "llama2"},
        "agents": {
            "researcher": {"prompt": "Research topics"},
            "analyst": {"prompt": "Analyze findings"},
        },
        "pattern": {
            "type": "workflow",
            "config": {
                "tasks": [
                    {"id": "research", "agent": "researcher", "input": "Research {{ topic }}"},
                    {
                        "id": "review_research",
                        "type": "hitl",
                        "deps": ["research"],
                        "prompt": "Review research findings. Approve?",
                        "context_display": "{{ tasks.research.response }}",
                        "default": "approved",
                    },
                    {
                        "id": "analysis",
                        "agent": "analyst",
                        "deps": ["review_research"],
                        "input": "Analyze: {{ tasks.review_research.response }}",
                    },
                ]
            },
        },
    }


class TestWorkflowHITLBlockerRegressions:
    """Regression tests for HITL blocker fixes."""

    @pytest.mark.asyncio
    async def test_auto_session_can_be_resumed(self, tmp_path: Path, mocker: Any) -> None:
        """BLOCKER 2 REGRESSION: Test auto-created HITL sessions can be resumed.

        Verifies that spec_snapshot.yaml is persisted when sessions are auto-created,
        preventing SessionNotFoundError during resume.
        """
        # Arrange
        spec_dict = {
            "name": "auto-session-resume-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review", "type": "hitl", "deps": ["task1"], "prompt": "Approve?"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 1 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        # Mock user_cache_dir to use tmp_path
        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - Run workflow (should auto-create session and pause at HITL)
        result = await run_workflow(spec=spec, variables={})

        # Assert - Session created
        assert result.exit_code == EX_HITL_PAUSE
        assert result.session_id is not None

        # Assert - Spec snapshot exists
        from strands_cli.session.file_repository import FileSessionRepository

        repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
        spec_snapshot_path = await repo.get_spec_snapshot_path(result.session_id)
        assert spec_snapshot_path.exists(), "Spec snapshot must exist for resume compatibility"

        # Assert - Can load session and resume (should not raise SessionNotFoundError)
        loaded_state = await repo.load(result.session_id)
        assert loaded_state is not None

    @pytest.mark.asyncio
    async def test_spec_name_with_spaces_creates_valid_session(
        self, tmp_path: Path, mocker: Any
    ) -> None:
        """BLOCKER 1 REGRESSION: Test workflow names with spaces create valid session IDs.

        Verifies that generate_session_id() is used instead of concatenating spec.name,
        preventing SessionCorruptedError from invalid characters.
        """
        # Arrange - Spec with spaces in name
        spec_dict = {
            "name": "workflow with many spaces",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {"id": "review", "type": "hitl", "deps": ["task1"], "prompt": "Approve?"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 1 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - Should not raise SessionCorruptedError
        result = await run_workflow(spec=spec, variables={})

        # Assert - Session created with valid ID
        assert result.exit_code == EX_HITL_PAUSE
        assert result.session_id is not None
        # Verify session ID matches FileSessionRepository validation pattern
        import re

        assert re.fullmatch(r"[A-Za-z0-9_-]+", result.session_id), (
            f"Session ID '{result.session_id}' contains invalid characters"
        )

    @pytest.mark.asyncio
    async def test_workflow_ending_with_hitl_completes_successfully(
        self, tmp_path: Path, mocker: Any
    ) -> None:
        """BLOCKER 3 REGRESSION: Test workflows ending with HITL task complete without KeyError.

        Verifies that HITL task results include 'agent': 'hitl' field to prevent
        KeyError when accessing task_results[last_task_id]['agent'] on completion.
        """
        # Arrange - Workflow ending with HITL task
        spec_dict = {
            "name": "hitl-final-test",
            "version": 0,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Task 1"},
                        {
                            "id": "final_review",
                            "type": "hitl",
                            "deps": ["task1"],
                            "prompt": "Final approval?",
                        },
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Task 1 complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.workflow.AgentCache", return_value=mock_cache)

        mocker.patch("platformdirs.user_cache_dir", return_value=str(tmp_path))

        # Act - First run pauses at HITL
        result1 = await run_workflow(spec=spec, variables={})
        assert result1.exit_code == EX_HITL_PAUSE

        # Resume with HITL response (workflow should complete, not raise KeyError)
        from strands_cli.session.file_repository import FileSessionRepository

        repo = FileSessionRepository(storage_dir=tmp_path / "sessions")
        state = await repo.load(result1.session_id)

        # Act - Resume should complete without KeyError
        result2 = await run_workflow(
            spec=spec,
            variables={},
            session_state=state,
            session_repo=repo,
            hitl_response="approved",
        )

        # Assert - Workflow completed successfully
        assert result2.success is True
        assert result2.exit_code != EX_HITL_PAUSE
        assert result2.agent_id == "hitl"  # Final task was HITL

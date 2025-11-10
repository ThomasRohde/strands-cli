"""Tests for HITL (Human-in-the-Loop) functionality in chain pattern executor.

Tests cover:
- Template variable {{ hitl_response }} exposure
- HITL pause with session save
- HITL resume with response injection
- Multiple HITL steps in workflow
- Artifact template access to HITL responses
- Error handling for missing hitl_response variable
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.chain import ChainExecutionError, _build_step_context, run_chain
from strands_cli.session import SessionMetadata, SessionState, TokenUsage
from strands_cli.types import HITLState, Spec


class TestHITLTemplateContext:
    """Test suite for HITL template variable exposure."""

    def test_build_context_with_hitl_response_single_step(
        self, mock_hitl_step_history: list[dict[str, Any]]
    ) -> None:
        """Test {{ hitl_response }} variable contains most recent HITL response."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        # Act
        context = _build_step_context(
            spec=spec,
            step_index=2,
            step_history=mock_hitl_step_history,
            variables=None,
        )

        # Assert
        assert "hitl_response" in context
        assert context["hitl_response"] == "approved with minor revisions"
        assert context["steps"] == mock_hitl_step_history

    def test_build_context_with_multiple_hitl_steps(self) -> None:
        """Test {{ hitl_response }} returns MOST RECENT HITL step (walk backwards)."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        step_history = [
            {"index": 0, "agent": "agent1", "response": "First result", "tokens_estimated": 100},
            {"index": 1, "type": "hitl", "prompt": "First approval?", "response": "approved", "tokens_estimated": 0},
            {"index": 2, "agent": "agent2", "response": "Second result", "tokens_estimated": 120},
            {"index": 3, "type": "hitl", "prompt": "Final approval?", "response": "rejected - revise", "tokens_estimated": 0},
        ]

        # Act
        context = _build_step_context(
            spec=spec, step_index=4, step_history=step_history, variables=None
        )

        # Assert - Should return the LAST HITL response (step 3)
        assert context["hitl_response"] == "rejected - revise"
        assert context["steps"][3]["response"] == "rejected - revise"

    def test_build_context_without_hitl_step(self) -> None:
        """Test {{ hitl_response }} is NOT in context when no HITL steps exist."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        step_history = [
            {"index": 0, "agent": "agent1", "response": "Result 1", "tokens_estimated": 100},
            {"index": 1, "agent": "agent2", "response": "Result 2", "tokens_estimated": 120},
        ]

        # Act
        context = _build_step_context(
            spec=spec, step_index=2, step_history=step_history, variables=None
        )

        # Assert - hitl_response should NOT be present
        assert "hitl_response" not in context
        assert "steps" in context

    def test_build_context_with_empty_hitl_response(self) -> None:
        """Test {{ hitl_response }} handles empty string response gracefully."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        step_history = [
            {"index": 0, "agent": "agent1", "response": "Result", "tokens_estimated": 100},
            {"index": 1, "type": "hitl", "prompt": "Approval?", "response": "", "tokens_estimated": 0},
        ]

        # Act
        context = _build_step_context(
            spec=spec, step_index=2, step_history=step_history, variables=None
        )

        # Assert
        assert "hitl_response" in context
        assert context["hitl_response"] == ""

    def test_build_context_preserves_steps_array_structure(
        self, mock_hitl_step_history: list[dict[str, Any]]
    ) -> None:
        """Test {{ steps[n].response }} still works alongside {{ hitl_response }}."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        # Act
        context = _build_step_context(
            spec=spec, step_index=2, step_history=mock_hitl_step_history, variables=None
        )

        # Assert - Both access patterns work
        assert context["steps"][0]["response"] == "Research findings: AI safety is critical..."
        assert context["steps"][1]["response"] == "approved with minor revisions"
        assert context["hitl_response"] == "approved with minor revisions"


class TestHITLPauseAndResume:
    """Test suite for HITL pause and resume workflow."""

    @pytest.mark.asyncio
    async def test_chain_pauses_at_hitl_step(
        self, chain_with_hitl_spec_dict: dict[str, Any], tmp_path: Any, mocker: Any
    ) -> None:
        """Test chain executor pauses at HITL step and exits with EX_HITL_PAUSE."""
        from pathlib import Path
        from strands_cli.session.file_repository import FileSessionRepository

        # Arrange
        spec = Spec(**chain_with_hitl_spec_dict)

        # Mock agent execution for step 0
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Research findings: AI safety is critical...")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Use real FileSessionRepository with tmp_path
        repo = FileSessionRepository(storage_dir=Path(tmp_path))

        # Mock session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-123",
                workflow_name=spec.name,
                pattern_type="chain",
                spec_hash="abc123",
                status="running",
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={"topic": "AI safety"},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Act - Run chain (should pause at step 1)
        result = await run_chain(
            spec=spec,
            variables={"topic": "AI safety"},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Should return HITL pause result
        assert result.success is True
        assert result.agent_id == "hitl"  # Marker for HITL pause
        assert "HITL pause at step 1" in result.last_response

        # Assert - Session should be saved with HITL state
        loaded_state = await repo.load("test-123")
        assert loaded_state.metadata.status == "paused"
        assert "hitl_state" in loaded_state.pattern_state

        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        assert hitl_state.step_index == 1
        assert hitl_state.prompt == "Review the research findings. Approve to proceed?"

    @pytest.mark.asyncio
    async def test_chain_resumes_with_hitl_response(
        self, chain_with_hitl_spec_dict: dict[str, Any], tmp_path: Any, mocker: Any
    ) -> None:
        """Test chain executor resumes from HITL pause and injects user response."""
        from pathlib import Path
        from strands_cli.session.file_repository import FileSessionRepository

        # Arrange
        spec = Spec(**chain_with_hitl_spec_dict)

        # Mock agent execution for step 2 (after HITL)
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Analysis complete based on approval.")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Use real FileSessionRepository with tmp_path
        repo = FileSessionRepository(storage_dir=Path(tmp_path))

        # Mock session state with HITL paused state
        hitl_state = HITLState(
            active=True,
            step_index=1,
            prompt="Review the research findings. Approve to proceed?",
            context_display="Research findings: AI safety is critical...",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-123",
                workflow_name=spec.name,
                pattern_type="chain",
                spec_hash="abc123",
                status="paused",
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI safety"},
            runtime_config={},
            pattern_state={
                "step_history": [
                    {
                        "index": 0,
                        "agent": "researcher",
                        "response": "Research findings: AI safety is critical...",
                        "tokens_estimated": 150,
                    }
                ],
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(
                total_input_tokens=100,
                total_output_tokens=150,
            ),
        )

        # Act - Resume with HITL response
        result = await run_chain(
            spec=spec,
            variables={"topic": "AI safety"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved with minor revisions",
        )

        # Assert - Workflow completes successfully
        assert result.success is True
        assert len(result.execution_context["steps"]) == 3

        # Assert - HITL response injected into step_history
        hitl_step = result.execution_context["steps"][1]
        assert hitl_step["type"] == "hitl"
        assert hitl_step["response"] == "approved with minor revisions"

        # Assert - Final step received HITL response in context
        # (Verified by checking agent.invoke_async was called - implicit test)
        assert mock_agent.invoke_async.called

    @pytest.mark.asyncio
    async def test_resume_without_hitl_response_raises_error(
        self, chain_with_hitl_spec_dict: dict[str, Any], tmp_path: Any, mocker: Any
    ) -> None:
        """Test resuming from HITL pause without --hitl-response raises error."""
        from pathlib import Path
        from strands_cli.session.file_repository import FileSessionRepository

        # Arrange
        spec = Spec(**chain_with_hitl_spec_dict)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Use real FileSessionRepository with tmp_path
        repo = FileSessionRepository(storage_dir=Path(tmp_path))

        hitl_state = HITLState(
            active=True,
            step_index=1,
            prompt="Review the research findings. Approve to proceed?",
            context_display="Research findings: AI safety is critical...",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-123",
                workflow_name=spec.name,
                pattern_type="chain",
                spec_hash="abc123",
                status="paused",
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI safety"},
            runtime_config={},
            pattern_state={
                "step_history": [
                    {
                        "index": 0,
                        "agent": "researcher",
                        "response": "Research findings: AI safety is critical...",
                        "tokens_estimated": 150,
                    }
                ],
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Act & Assert - Should raise ChainExecutionError

        with pytest.raises(ChainExecutionError, match="waiting for HITL response"):
            await run_chain(
                spec=spec,
                variables={"topic": "AI safety"},
                session_state=session_state,
                session_repo=repo,
                hitl_response=None,  # No response provided
            )

    @pytest.mark.asyncio
    async def test_session_checkpoint_after_hitl_resume(
        self, chain_with_hitl_spec_dict: dict[str, Any], tmp_path: Any, mocker: Any
    ) -> None:
        """Test session is checkpointed after injecting HITL response before continuing."""
        from pathlib import Path
        from strands_cli.session.file_repository import FileSessionRepository

        # Arrange
        spec = Spec(**chain_with_hitl_spec_dict)

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Analysis complete.")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Use real FileSessionRepository with tmp_path
        repo = FileSessionRepository(storage_dir=Path(tmp_path))

        hitl_state = HITLState(
            active=True,
            step_index=1,
            prompt="Review the research findings. Approve to proceed?",
            context_display="Research findings: AI safety is critical...",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-123",
                workflow_name=spec.name,
                pattern_type="chain",
                spec_hash="abc123",
                status="paused",
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI safety"},
            runtime_config={},
            pattern_state={
                "step_history": [
                    {
                        "index": 0,
                        "agent": "researcher",
                        "response": "Research findings: AI safety is critical...",
                        "tokens_estimated": 150,
                    }
                ],
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Act
        await run_chain(
            spec=spec,
            variables={"topic": "AI safety"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved",
        )

        # Assert - Session saved with HITL response in step_history
        loaded_state = await repo.load("test-123")
        assert len(loaded_state.pattern_state["step_history"]) >= 2
        assert loaded_state.pattern_state["step_history"][1]["type"] == "hitl"
        assert loaded_state.pattern_state["step_history"][1]["response"] == "approved"


class TestHITLMultipleSteps:
    """Test suite for workflows with multiple HITL steps."""

    @pytest.mark.asyncio
    async def test_multiple_hitl_steps_sequential(self, tmp_path: Any, mocker: Any) -> None:
        """Test workflow with multiple sequential HITL steps."""
        from pathlib import Path
        from strands_cli.session.file_repository import FileSessionRepository

        # Arrange - Spec with 2 HITL steps
        spec_dict = {
            "name": "multi-hitl-test",
            "version": 1,
            "runtime": {"provider": "ollama", "model_id": "llama2"},
            "agents": {"agent1": {"prompt": "Test agent"}},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "agent1", "input": "Step 1"},
                        {"type": "hitl", "prompt": "First approval?"},
                        {"agent": "agent1", "input": "Step 2: {{ hitl_response }}"},
                        {"type": "hitl", "prompt": "Second approval?"},
                        {"agent": "agent1", "input": "Final: {{ hitl_response }}"},
                    ]
                },
            },
        }
        spec = Spec(**spec_dict)

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Agent result")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Use real FileSessionRepository with tmp_path
        repo = FileSessionRepository(storage_dir=Path(tmp_path))

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-multi-hitl",
                workflow_name=spec.name,
                pattern_type="chain",
                spec_hash="def456",
                status="running",
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Act - Run should pause at first HITL (step 1)
        result = await run_chain(
            spec=spec,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at step 1
        assert result.success is True
        assert result.agent_id == "hitl"  # Marker for HITL pause
        loaded_state = await repo.load("test-multi-hitl")
        assert loaded_state.pattern_state["hitl_state"]["step_index"] == 1


class TestHITLArtifactTemplates:
    """Test suite for artifact templates referencing HITL steps."""

    def test_artifact_context_includes_hitl_steps(
        self, mock_hitl_step_history: list[dict[str, Any]]
    ) -> None:
        """Test artifacts can reference HITL responses via {{ steps[n].response }}."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        # Act
        context = _build_step_context(
            spec=spec,
            step_index=2,
            step_history=mock_hitl_step_history,
            variables=None,
        )

        # Assert - Artifact templates can use both patterns
        # Pattern 1: {{ steps[1].response }}
        assert context["steps"][1]["response"] == "approved with minor revisions"
        assert context["steps"][1]["type"] == "hitl"

        # Pattern 2: {{ hitl_response }}
        assert context["hitl_response"] == "approved with minor revisions"

    def test_artifact_missing_hitl_response_when_no_hitl_step(self) -> None:
        """Test {{ hitl_response }} is absent when no HITL steps (causes template error)."""
        # Arrange
        spec = MagicMock()
        spec.inputs = None
        spec.pattern.config.steps = None

        step_history = [
            {"index": 0, "agent": "agent1", "response": "Result", "tokens_estimated": 100}
        ]

        # Act
        context = _build_step_context(
            spec=spec, step_index=1, step_history=step_history, variables=None
        )

        # Assert - hitl_response NOT in context (template using it will fail)
        assert "hitl_response" not in context

        # Note: This is desired behavior per user decision (Option B: raise template error)
        # Jinja2 will raise UndefinedError if template uses {{ hitl_response }}

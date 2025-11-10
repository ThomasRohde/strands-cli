"""Tests for Phase 2: Chain executor checkpointing and session restoration.

Tests cover:
- Fresh execution with session persistence
- Resume from checkpoint (skip completed steps)
- Agent conversation restoration via Strands SDK
- Session state updates and checkpointing
- Error scenarios (invalid session parameters, corrupted state)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.chain import run_chain
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository

if TYPE_CHECKING:
    from strands_cli.types import Spec


class TestChainSessionValidation:
    """Test session parameter validation."""

    @pytest.fixture
    def chain_spec_3_steps(self, tmp_path: Path) -> Spec:
        """Chain with 3 steps for testing."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "test-agent", "input": "Step 1 prompt"},
                        {"agent": "test-agent", "input": "Step 2: {{ steps[0].response }}"},
                        {"agent": "test-agent", "input": "Step 3: {{ steps[1].response }}"},
                    ]
                },
            },
            "agents": {
                "test-agent": {
                    "prompt": "You are a test agent",
                    "tools": [],
                }
            },
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        return load_spec(str(spec_file))

    @pytest.mark.asyncio
    async def test_session_state_without_repo_raises_error(
        self, chain_spec_3_steps: Spec, mocker: Any
    ) -> None:
        """Test that providing session_state without session_repo raises ValueError."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        # Create minimal session state
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=generate_session_id(),
                workflow_name="test",
                spec_hash="abc123",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Mock agent cache to prevent actual execution
        mock_cache = mocker.AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Attempt to run with session_state but no session_repo
        with pytest.raises(ValueError, match="session_state and session_repo must both"):
            await run_chain(chain_spec_3_steps, variables=None, session_state=session_state)

    @pytest.mark.asyncio
    async def test_session_repo_without_state_raises_error(
        self, chain_spec_3_steps: Spec, mocker: Any, tmp_path: Path
    ) -> None:
        """Test that providing session_repo without session_state raises ValueError."""
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent cache to prevent actual execution
        mock_cache = mocker.AsyncMock()
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Attempt to run with session_repo but no session_state
        with pytest.raises(ValueError, match="session_state and session_repo must both"):
            await run_chain(chain_spec_3_steps, variables=None, session_repo=repo)


class TestChainFreshExecutionWithSession:
    """Test fresh execution with session persistence enabled."""

    @pytest.fixture
    def chain_spec_3_steps(self, tmp_path: Path) -> Spec:
        """Chain with 3 steps for testing."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "test-agent", "input": "Step 1 prompt"},
                        {"agent": "test-agent", "input": "Step 2: {{ steps[0].response }}"},
                        {"agent": "test-agent", "input": "Step 3: {{ steps[1].response }}"},
                    ]
                },
            },
            "agents": {
                "test-agent": {
                    "prompt": "You are a test agent",
                    "tools": [],
                }
            },
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        return load_spec(str(spec_file))

    @pytest.mark.asyncio
    async def test_fresh_execution_creates_checkpoints(
        self, chain_spec_3_steps: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that fresh execution with session creates checkpoints after each step."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        # Create session state for fresh execution
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={},  # Empty for fresh start
            token_usage=TokenUsage(),
        )

        # Create repository
        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Response 1", "Response 2", "Response 3"])

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Run chain with session
        result = await run_chain(
            chain_spec_3_steps, variables=None, session_state=session_state, session_repo=repo
        )

        assert result.success is True
        assert result.last_response == "Response 3"

        # Verify session was checkpointed
        loaded_state = await repo.load(session_id)
        assert loaded_state is not None
        assert loaded_state.metadata.status == SessionStatus.COMPLETED
        assert loaded_state.pattern_state["current_step"] == 3  # All steps completed
        assert len(loaded_state.pattern_state["step_history"]) == 3

    @pytest.mark.asyncio
    async def test_fresh_execution_updates_token_usage(
        self, chain_spec_3_steps: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that token usage is tracked in session state."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Short", "Medium response", "Long"])

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Run chain
        await run_chain(
            chain_spec_3_steps, variables=None, session_state=session_state, session_repo=repo
        )

        # Load session and verify token tracking
        loaded_state = await repo.load(session_id)
        assert loaded_state is not None
        assert loaded_state.token_usage.total_input_tokens > 0
        assert loaded_state.token_usage.total_output_tokens > 0


class TestChainResumeFromCheckpoint:
    """Test resume from checkpoint functionality."""

    @pytest.fixture
    def chain_spec_3_steps(self, tmp_path: Path) -> Spec:
        """Chain with 3 steps for testing."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "test-agent", "input": "Step 1 prompt"},
                        {"agent": "test-agent", "input": "Step 2: {{ steps[0].response }}"},
                        {"agent": "test-agent", "input": "Step 3: {{ steps[1].response }}"},
                    ]
                },
            },
            "agents": {
                "test-agent": {
                    "prompt": "You are a test agent",
                    "tools": [],
                }
            },
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        return load_spec(str(spec_file))

    @pytest.mark.asyncio
    async def test_resume_skips_completed_steps(
        self, chain_spec_3_steps: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that resume skips already-completed steps."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        # Create session state with 2 steps already completed
        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={
                "current_step": 2,  # Next step to execute is index 2
                "step_history": [
                    {"index": 0, "agent": "test-agent", "response": "Response 1"},
                    {"index": 1, "agent": "test-agent", "response": "Response 2"},
                ],
            },
            token_usage=TokenUsage(total_input_tokens=10, total_output_tokens=10),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent - should only be invoked once for step 2
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response 3")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Resume chain
        result = await run_chain(
            chain_spec_3_steps, variables=None, session_state=session_state, session_repo=repo
        )

        assert result.success is True
        assert result.last_response == "Response 3"

        # Verify agent was only invoked once (for step 2)
        assert mock_agent.invoke_async.call_count == 1

        # Verify session was updated
        loaded_state = await repo.load(session_id)
        assert loaded_state is not None
        assert loaded_state.metadata.status == SessionStatus.COMPLETED
        assert loaded_state.pattern_state["current_step"] == 3
        assert len(loaded_state.pattern_state["step_history"]) == 3

    @pytest.mark.asyncio
    async def test_resume_preserves_step_history(
        self, chain_spec_3_steps: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that resume preserves existing step history."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={
                "current_step": 1,
                "step_history": [
                    {
                        "index": 0,
                        "agent": "test-agent",
                        "response": "Original Response 1",
                        "tokens_estimated": 5,
                    }
                ],
            },
            token_usage=TokenUsage(total_input_tokens=5, total_output_tokens=5),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock agent for remaining steps
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Response 2", "Response 3"])

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Resume chain
        result = await run_chain(
            chain_spec_3_steps, variables=None, session_state=session_state, session_repo=repo
        )

        assert result.success is True

        # Verify original step history was preserved
        loaded_state = await repo.load(session_id)
        assert loaded_state is not None
        step_history = loaded_state.pattern_state["step_history"]
        assert len(step_history) == 3
        assert step_history[0]["response"] == "Original Response 1"
        assert step_history[1]["response"] == "Response 2"
        assert step_history[2]["response"] == "Response 3"

    @pytest.mark.asyncio
    async def test_resume_incremental_checkpointing(
        self, chain_spec_3_steps: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that resume creates checkpoints after each step."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={
                "current_step": 1,
                "step_history": [{"index": 0, "agent": "test-agent", "response": "Response 1"}],
            },
            token_usage=TokenUsage(total_input_tokens=5, total_output_tokens=5),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Track save calls
        save_count = [0]
        original_save = repo.save

        async def tracked_save(state: SessionState, spec_content: str) -> None:
            save_count[0] += 1
            await original_save(state, spec_content)

        repo.save = tracked_save  # type: ignore[method-assign]

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Response 2", "Response 3"])

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Resume chain
        await run_chain(
            chain_spec_3_steps, variables=None, session_state=session_state, session_repo=repo
        )

        # Verify save was called after each step + final completion
        # 2 steps executed + 1 final completion = 3 saves
        assert save_count[0] == 3


class TestChainAgentSessionRestoration:
    """Test agent conversation restoration via Strands SDK."""

    @pytest.fixture
    def chain_spec_with_agent(self, tmp_path: Path) -> Spec:
        """Simple chain for agent restoration testing."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {"steps": [{"agent": "test-agent", "input": "Test prompt"}]},
            },
            "agents": {"test-agent": {"prompt": "You are a test agent"}},
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        return load_spec(str(spec_file))

    @pytest.mark.asyncio
    async def test_resume_creates_session_manager(
        self, chain_spec_with_agent: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that resume creates FileSessionManager for agent restoration."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={"current_step": 0, "step_history": []},
            token_usage=TokenUsage(),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Mock FileSessionManager (it's imported inside chain.py)
        mock_session_manager = MagicMock()
        mock_file_session_manager_class = mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response")

        # Mock AgentCache.get_or_build_agent to capture session_manager parameter
        captured_session_manager = None

        async def capture_get_or_build_agent(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal captured_session_manager
            captured_session_manager = kwargs.get("session_manager")
            return mock_agent

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.side_effect = capture_get_or_build_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Resume chain
        await run_chain(
            chain_spec_with_agent,
            variables=None,
            session_state=session_state,
            session_repo=repo,
        )

        # Verify FileSessionManager was created
        assert mock_file_session_manager_class.called
        # Verify it was passed to agent
        assert captured_session_manager is mock_session_manager

    @pytest.mark.asyncio
    async def test_fresh_execution_no_session_manager(
        self, chain_spec_with_agent: Spec, mocker: Any
    ) -> None:
        """Test that fresh execution without session doesn't create session manager."""
        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response")

        # Mock AgentCache.get_or_build_agent to capture session_manager parameter
        captured_session_manager = None

        async def capture_get_or_build_agent(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal captured_session_manager
            captured_session_manager = kwargs.get("session_manager")
            return mock_agent

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.side_effect = capture_get_or_build_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Run chain without session
        await run_chain(chain_spec_with_agent, variables=None)

        # Verify no session manager was created
        assert captured_session_manager is None

    @pytest.mark.asyncio
    async def test_agent_session_id_format(
        self, chain_spec_with_agent: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that agent session ID is formatted as {session_id}_{agent_id}."""
        from strands_cli.session.utils import generate_session_id, now_iso8601

        session_id = generate_session_id()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=session_id,
                workflow_name="Test Chain",
                spec_hash="test-hash",
                pattern_type="chain",
                status=SessionStatus.RUNNING,
                created_at=now_iso8601(),
                updated_at=now_iso8601(),
            ),
            variables={},
            runtime_config={"provider": "bedrock", "model_id": "test-model"},
            pattern_state={"current_step": 0, "step_history": []},
            token_usage=TokenUsage(),
        )

        repo = FileSessionRepository(storage_dir=tmp_path)

        # Capture FileSessionManager call to verify session_id format
        captured_session_id = None

        def mock_file_session_manager_init(self: Any, *, session_id: str, storage_dir: str) -> None:
            nonlocal captured_session_id
            captured_session_id = session_id
            # Don't actually initialize (avoid file I/O)

        # Mock FileSessionManager
        mock_session_manager = MagicMock()
        mock_file_session_manager_class = mocker.patch(
            "strands.session.file_session_manager.FileSessionManager",
            return_value=mock_session_manager,
        )

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response")

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

        # Resume chain
        await run_chain(
            chain_spec_with_agent,
            variables=None,
            session_state=session_state,
            session_repo=repo,
        )

        # Verify FileSessionManager was called with properly formatted session_id
        assert mock_file_session_manager_class.called
        call_kwargs = mock_file_session_manager_class.call_args[1]
        agent_session_id = call_kwargs["session_id"]

        # Session ID should be formatted as {base_session_id}_{agent_id}
        expected_format = f"{session_id}_test-agent"
        assert agent_session_id == expected_format

"""Unit tests for WorkflowSession."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from strands_cli.api.workflow_session import WorkflowSession, SessionStateEnum
from strands_cli.types import Spec, Pattern, PatternType, PatternConfig, Runtime, ProviderType, HITLState, RunResult
from strands_cli.session import SessionState, SessionMetadata, SessionStatus, TokenUsage
from strands_cli.exit_codes import EX_HITL_PAUSE

@pytest.fixture
def mock_spec():
    return Spec(
        name="test_workflow",
        pattern=Pattern(type=PatternType.WORKFLOW, config=PatternConfig(tasks=[])),
        runtime=Runtime(provider=ProviderType.OLLAMA),
        agents={},
    )

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.load = AsyncMock()
    return repo

@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor._execute_pattern = AsyncMock()
    return executor

@pytest.mark.asyncio
async def test_workflow_session_start(mock_spec, mock_repo, mock_executor):
    """Test starting a workflow session."""
    with patch("strands_cli.api.workflow_session.WorkflowExecutor", return_value=mock_executor):
        session = WorkflowSession(mock_spec, {}, repository=mock_repo)
        
        # Mock executor to return success immediately
        mock_executor._execute_pattern.return_value = RunResult(
            success=True,
            exit_code=0,
            pattern_type=PatternType.WORKFLOW,
            session_id=session.session_id,
            agent_id="system",
            last_response="done",
            error=None,
            tokens_estimated=0,
            started_at="now",
            completed_at="now",
            duration_seconds=1.0,
        )
        
        session.start()
        
        # Wait for background task
        await asyncio.sleep(0.1)
        
        assert session.state == SessionStateEnum.COMPLETE
        assert session.is_complete()
        assert session.get_result().last_response == "done"

@pytest.mark.asyncio
async def test_workflow_session_hitl_pause(mock_spec, mock_repo, mock_executor):
    """Test workflow session pausing at HITL."""
    with patch("strands_cli.api.workflow_session.WorkflowExecutor", return_value=mock_executor):
        session = WorkflowSession(mock_spec, {}, repository=mock_repo)
        
        # Mock executor to return HITL pause first
        hitl_result = RunResult(
            success=True,
            exit_code=EX_HITL_PAUSE,
            pattern_type=PatternType.WORKFLOW,
            session_id=session.session_id,
            agent_id="hitl",
            last_response="",
            error=None,
            tokens_estimated=0,
            started_at="now",
            completed_at="now",
            duration_seconds=1.0,
        )
        
        mock_executor._execute_pattern.return_value = hitl_result
        
        # Mock session state with HITL data
        mock_session_state = MagicMock()
        mock_session_state.pattern_state = {
            "hitl_state": {
                "active": True,
                "task_id": "task1",
                "prompt": "Approve?",
                "layer_index": 0,
            }
        }
        # Mock repo.save to capture the session state being saved
        # But here we need repo.load? No, session keeps state in memory?
        # No, _run_async creates session_state.
        # But when PAUSED_HITL happens, it reads from session_state variable in local scope.
        # Wait, my implementation of _run_async reads from local `session_state`.
        # But `session_state.pattern_state` is updated by `_execute_pattern` (passed by ref).
        # So we need `_execute_pattern` to update the `session_state` object passed to it.
        
        async def side_effect_execute(variables, session_state, repo, hitl_response):
            if hitl_response is None:
                # First run: Simulate HITL pause
                session_state.pattern_state["hitl_state"] = {
                    "active": True,
                    "task_id": "task1",
                    "prompt": "Approve?",
                    "layer_index": 0,
                }
                return hitl_result
            else:
                # Resume run: Success
                return RunResult(
                    success=True,
                    exit_code=0,
                    pattern_type=PatternType.WORKFLOW,
                    session_id=session.session_id,
                    agent_id="system",
                    last_response="approved",
                    error=None,
                    tokens_estimated=0,
                    started_at="now",
                    completed_at="now",
                    duration_seconds=1.0,
                )
                
        mock_executor._execute_pattern.side_effect = side_effect_execute
        
        session.start()
        
        # Wait for pause
        await asyncio.sleep(0.1)
        
        assert session.state == SessionStateEnum.PAUSED_HITL
        assert session.is_paused()
        hitl_state = session.get_hitl_state()
        assert hitl_state is not None
        assert hitl_state.prompt == "Approve?"
        
        # Resume
        session.resume("yes")
        
        # Wait for completion
        await asyncio.sleep(0.1)
        
        assert session.state == SessionStateEnum.COMPLETE
        assert session.get_result().last_response == "approved"

"""Tests for evaluator-optimizer pattern resume functionality.

Phase 3.3: Test coverage for iteration state restoration, draft preservation,
and checkpoint-based resume for the evaluator-optimizer pattern.
"""

from pathlib import Path

import pytest

from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer
from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.file_repository import FileSessionRepository


@pytest.fixture
def evaluator_optimizer_spec(evaluator_optimizer_spec_fixture):
    """Evaluator-optimizer spec from conftest."""
    return evaluator_optimizer_spec_fixture


@pytest.fixture
def partial_evaluator_session(tmp_path: Path) -> tuple[SessionState, FileSessionRepository]:
    """Create evaluator-optimizer session with 2 iterations complete."""
    session_id = "test-eval-partial"
    repo = FileSessionRepository()

    # Create session state with partial completion
    state = SessionState(
        metadata={
            "session_id": session_id,
            "workflow_name": "test-evaluator-workflow",
            "pattern_type": "evaluator_optimizer",
            "status": SessionStatus.RUNNING,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:01:00Z",
            "spec_hash": "abc123",
        },
        variables={"task": "Write a short essay"},
        pattern_state={
            "current_iteration": 3,
            "current_draft": "This is the revised draft after iteration 2...",
            "iteration_history": [
                {
                    "iteration": 1,
                    "score": 60,
                    "issues": ["Too brief", "Missing examples"],
                    "fixes": ["Add more detail", "Include concrete examples"],
                    "draft_preview": "This is the initial draft...",
                },
                {
                    "iteration": 2,
                    "score": 75,
                    "issues": ["Could use better structure"],
                    "fixes": ["Add section headings"],
                    "draft_preview": "This is the revised draft...",
                },
            ],
            "final_score": 75,
            "accepted": False,
        },
        token_usage={
            "total_input_tokens": 500,
            "total_output_tokens": 800,
        },
    )

    return state, repo


@pytest.mark.asyncio
async def test_session_params_validation(evaluator_optimizer_spec):
    """Test that session_state and session_repo must both be provided or both None."""
    from unittest.mock import MagicMock

    mock_state = MagicMock()

    # Only state provided
    with pytest.raises(ValueError, match="must both be provided or both be None"):
        await run_evaluator_optimizer(
            evaluator_optimizer_spec,
            session_state=mock_state,
            session_repo=None,
        )

    # Only repo provided
    with pytest.raises(ValueError, match="must both be provided or both be None"):
        await run_evaluator_optimizer(
            evaluator_optimizer_spec,
            session_state=None,
            session_repo=MagicMock(),
        )

"""Tests for HITL functionality in evaluator-optimizer pattern."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import (
    AcceptConfig,
    Agent,
    EvaluatorConfig,
    HITLState,
    HITLStep,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
)


@pytest.fixture
def evaluator_spec_with_review_gate(tmp_path):
    """Create evaluator-optimizer spec with review gate."""
    return Spec(
        version=0,
        name="evaluator-review-gate-test",
        description="Test evaluator-optimizer with review gate",
        runtime=Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        ),
        agents={
            "writer": Agent(prompt="You write drafts"),
            "critic": Agent(prompt="You evaluate and return JSON with score, issues, fixes"),
        },
        pattern=Pattern(
            type=PatternType.EVALUATOR_OPTIMIZER,
            config=PatternConfig(
                producer="writer",
                evaluator=EvaluatorConfig(
                    agent="critic",
                    input="Evaluate: {{ draft }}",
                ),
                accept=AcceptConfig(
                    min_score=80,
                    max_iters=3,
                ),
                review_gate=HITLStep(
                    type="hitl",
                    prompt="Review draft iteration {{ iteration_index }}. Approve or provide feedback?",
                    context_display=(
                        "### Draft (Iteration {{ iteration_index }})\n"
                        "{{ iterations[-1].draft }}\n\n"
                        "### Evaluation\n"
                        "Score: {{ iterations[-1].evaluation.score }}\n"
                        "Feedback: {{ iterations[-1].evaluation.feedback }}\n"
                    ),
                    default="continue",
                    timeout_seconds=1800,
                ),
            ),
        ),
    )


@pytest.fixture
def evaluator_spec_no_review_gate(tmp_path):
    """Create evaluator-optimizer spec WITHOUT review gate for comparison."""
    return Spec(
        version=0,
        name="evaluator-no-review-test",
        description="Test evaluator-optimizer without review gate",
        runtime=Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        ),
        agents={
            "writer": Agent(prompt="You write drafts"),
            "critic": Agent(prompt="You evaluate and return JSON"),
        },
        pattern=Pattern(
            type=PatternType.EVALUATOR_OPTIMIZER,
            config=PatternConfig(
                producer="writer",
                evaluator=EvaluatorConfig(
                    agent="critic",
                    input="Evaluate: {{ draft }}",
                ),
                accept=AcceptConfig(
                    min_score=80,
                    max_iters=3,
                ),
                # NO review_gate
            ),
        ),
    )


@pytest.mark.asyncio
async def test_evaluator_optimizer_review_gate_pause(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test evaluator-optimizer pauses at review gate after first evaluation."""
    # Mock producer and evaluator responses
    mock_producer_response = "Draft version 1 content"
    mock_evaluator_response = (
        '{"score": 65, "issues": ["Needs more detail"], "fixes": ["Add examples"]}'
    )

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            # Producer initial draft
            return mock_producer_response
        else:
            # Evaluator response
            return mock_evaluator_response

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute until HITL pause
    result = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )

    # Verify HITL pause
    assert result.exit_code == EX_HITL_PAUSE
    assert result.agent_id == "hitl"
    assert "review draft iteration" in result.last_response.lower()

    # Verify session state
    loaded_state = await repo.load("test-session")
    assert loaded_state.metadata.status == SessionStatus.PAUSED

    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
    assert hitl_state.active is True
    assert hitl_state.iteration_index == 0
    assert hitl_state.timeout_at is not None
    assert hitl_state.default_response == "continue"


@pytest.mark.asyncio
async def test_evaluator_optimizer_resume_with_continue(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test resuming evaluator-optimizer with 'continue' proceeds to next iteration."""
    # Mock responses
    mock_draft_v1 = "Draft version 1"
    mock_eval_v1 = '{"score": 65, "issues": ["Issue1"], "fixes": ["Fix1"]}'
    mock_draft_v2 = "Draft version 2 improved"
    mock_eval_v2 = '{"score": 85, "issues": [], "fixes": []}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        responses = [
            mock_draft_v1,  # Producer iteration 0
            mock_eval_v1,  # Evaluator iteration 0
            # HITL pause here
            mock_draft_v2,  # Producer iteration 1 (after resume)
            mock_eval_v2,  # Evaluator iteration 1 (accept)
        ]
        return responses[call_count[0] - 1]

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-continue",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to HITL pause
    result1 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE

    # Load session and resume with 'continue'
    loaded_state = await repo.load("test-session-continue")
    result2 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="continue",
    )

    # Verify successful completion
    assert result2.success is True
    assert result2.exit_code == EX_OK
    assert result2.last_response == mock_draft_v2
    assert result2.execution_context["iterations"] == 2
    assert result2.execution_context["final_score"] == 85


@pytest.mark.asyncio
async def test_evaluator_optimizer_resume_with_stop(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test resuming evaluator-optimizer with 'stop' ends optimization early."""
    # Mock responses
    mock_draft_v1 = "Draft version 1"
    mock_eval_v1 = '{"score": 65, "issues": ["Issue1"], "fixes": ["Fix1"]}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_draft_v1
        else:
            return mock_eval_v1

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-stop",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to HITL pause
    result1 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE

    # Load session and resume with 'stop' (user rejects continuation)
    loaded_state = await repo.load("test-session-stop")
    result2 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="stop",
    )

    # Verify early termination
    assert result2.success is True  # Successfully stopped
    assert result2.exit_code == EX_OK
    assert result2.last_response == mock_draft_v1  # Returns last draft
    assert result2.execution_context["iterations"] == 1
    assert result2.execution_context["final_score"] == 65
    assert result2.execution_context.get("early_termination") is True


@pytest.mark.asyncio
async def test_evaluator_optimizer_multiple_review_gates(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test evaluator-optimizer pauses at review gate for each iteration below min_score."""
    # Mock responses for 3 iterations with 2 HITL pauses
    mock_responses = [
        "Draft v1",
        '{"score": 60, "issues": ["I1"], "fixes": ["F1"]}',
        # HITL pause 1
        "Draft v2",
        '{"score": 70, "issues": ["I2"], "fixes": ["F2"]}',
        # HITL pause 2
        "Draft v3",
        '{"score": 85, "issues": [], "fixes": []}',  # Accept
    ]

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        return mock_responses[call_count[0] - 1]

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-multi-review",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to first HITL pause
    result1 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE
    loaded_state1 = await repo.load("test-multi-review")
    hitl_state1 = HITLState(**loaded_state1.pattern_state["hitl_state"])
    assert hitl_state1.iteration_index == 0

    # Resume to second HITL pause
    result2 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=loaded_state1,
        session_repo=repo,
        hitl_response="continue",
    )
    assert result2.exit_code == EX_HITL_PAUSE
    loaded_state2 = await repo.load("test-multi-review")
    hitl_state2 = HITLState(**loaded_state2.pattern_state["hitl_state"])
    assert hitl_state2.iteration_index == 1

    # Resume to completion
    result3 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=loaded_state2,
        session_repo=repo,
        hitl_response="continue",
    )

    # Verify successful completion
    assert result3.success is True
    assert result3.exit_code == EX_OK
    assert result3.last_response == "Draft v3"
    assert result3.execution_context["iterations"] == 3
    assert result3.execution_context["final_score"] == 85


@pytest.mark.asyncio
async def test_evaluator_optimizer_no_review_gate_no_pause(
    evaluator_spec_no_review_gate, tmp_path, mocker
):
    """Test evaluator-optimizer without review gate runs to completion without HITL pause."""
    # Mock responses
    mock_draft_v1 = "Draft v1"
    mock_eval_v1 = '{"score": 60, "issues": ["I1"], "fixes": ["F1"]}'
    mock_draft_v2 = "Draft v2"
    mock_eval_v2 = '{"score": 85, "issues": [], "fixes": []}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        responses = [mock_draft_v1, mock_eval_v1, mock_draft_v2, mock_eval_v2]
        return responses[call_count[0] - 1]

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-no-review",
            workflow_name=evaluator_spec_no_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to completion (should NOT pause)
    result = await run_evaluator_optimizer(
        evaluator_spec_no_review_gate,
        session_state=session_state,
        session_repo=repo,
    )

    # Verify completion without HITL pause
    assert result.success is True
    assert result.exit_code == EX_OK
    assert result.agent_id != "hitl"
    assert result.last_response == "Draft v2"
    assert result.execution_context["iterations"] == 2
    assert result.execution_context["final_score"] == 85


@pytest.mark.asyncio
async def test_evaluator_optimizer_hitl_requires_session(evaluator_spec_with_review_gate, mocker):
    """Test that review gate requires session persistence enabled."""
    # Mock responses to get to HITL pause point
    mock_draft = "Draft v1"
    mock_eval = '{"score": 65, "issues": [], "fixes": []}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        return mock_draft if call_count[0] == 1 else mock_eval

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Execute without session persistence (should raise error)
    from strands_cli.exec.evaluator_optimizer import EvaluatorOptimizerExecutionError

    with pytest.raises(EvaluatorOptimizerExecutionError, match="requires session persistence"):
        await run_evaluator_optimizer(
            evaluator_spec_with_review_gate,
            session_state=None,
            session_repo=None,
        )


@pytest.mark.asyncio
async def test_evaluator_optimizer_hitl_timeout_metadata(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test that HITL timeout metadata is correctly set."""
    # Mock responses
    mock_draft = "Draft v1"
    mock_eval = '{"score": 65, "issues": [], "fixes": []}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        return mock_draft if call_count[0] == 1 else mock_eval

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-timeout",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to HITL pause
    result = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result.exit_code == EX_HITL_PAUSE

    # Verify timeout metadata
    loaded_state = await repo.load("test-timeout")
    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])

    assert hitl_state.timeout_at is not None
    timeout_dt = datetime.fromisoformat(hitl_state.timeout_at)
    now = datetime.now(UTC)

    # Timeout should be ~1800 seconds in the future
    time_diff = (timeout_dt - now).total_seconds()
    assert 1700 < time_diff < 1900  # Allow 100s margin for test execution time


@pytest.mark.asyncio
async def test_evaluator_optimizer_context_display_template(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test that context_display template is correctly rendered with iteration data."""
    # Mock responses
    mock_draft = "Draft about AI safety and ethics"
    mock_eval = '{"score": 65, "issues": ["Needs citations"], "fixes": ["Add references"]}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        return mock_draft if call_count[0] == 1 else mock_eval

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-context",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to HITL pause
    result = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result.exit_code == EX_HITL_PAUSE

    # Verify HITL state context_display contains rendered template
    loaded_state = await repo.load("test-context")
    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])

    context_display = hitl_state.context_display or ""

    # Should contain draft text
    assert mock_draft in context_display

    # Should contain score
    assert "65" in context_display

    # Should contain iteration index (0 for first iteration)
    assert "0" in context_display


@pytest.mark.asyncio
async def test_evaluator_optimizer_resume_integration(
    evaluator_spec_with_review_gate, tmp_path, mocker
):
    """Test resuming evaluator-optimizer with hitl_response via dispatcher pattern.

    Regression test for hitl-phase2 blocker where --hitl-response parameter
    must be forwarded from resume dispatcher to executor. Tests the integration
    path that mirrors the CLI flow: pause → load state → resume with response.
    """
    # Mock responses for 2 complete iterations
    mock_draft_v1 = "Draft version 1"
    mock_eval_v1 = '{"score": 65, "issues": ["I1"], "fixes": ["F1"]}'
    mock_draft_v2 = "Draft version 2 improved"
    mock_eval_v2 = '{"score": 85, "issues": [], "fixes": []}'

    call_count = [0]

    async def mock_invoke_side_effect(prompt):
        call_count[0] += 1
        responses = [mock_draft_v1, mock_eval_v1, mock_draft_v2, mock_eval_v2]
        return responses[call_count[0] - 1]

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.evaluator_optimizer.AgentCache")
    mock_cache_instance = MagicMock()
    mock_cache.return_value = mock_cache_instance
    mock_cache_instance.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(side_effect=mock_invoke_side_effect)
    mock_cache_instance.get_or_build_agent = AsyncMock(return_value=mock_agent)

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Phase 1: Execute to HITL pause
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-resume-integration",
            workflow_name=evaluator_spec_with_review_gate.name,
            spec_hash="test-hash",
            pattern_type="evaluator_optimizer",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    result1 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE
    assert call_count[0] == 2  # Producer + evaluator for iteration 0

    # Phase 2: Load paused state and resume with hitl_response
    # This simulates the dispatcher flow in resume.py::_dispatch_pattern_executor()
    loaded_state = await repo.load("test-resume-integration")
    assert loaded_state is not None
    assert loaded_state.metadata.status == SessionStatus.PAUSED

    # Verify HITL state was saved
    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
    assert hitl_state.active is True
    assert hitl_state.iteration_index == 0

    # Phase 3: Resume with hitl_response (THIS TESTS THE FIX)
    # Before fix: hitl_response parameter was missing in dispatcher
    # After fix: parameter is forwarded to executor
    result2 = await run_evaluator_optimizer(
        evaluator_spec_with_review_gate,
        variables={},
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="continue",  # CRITICAL: This parameter must be forwarded
    )

    # Verify successful completion (proves hitl_response was used)
    assert result2.success is True
    assert result2.exit_code == EX_OK
    assert result2.last_response == mock_draft_v2
    assert result2.execution_context["iterations"] == 2
    assert result2.execution_context["final_score"] == 85
    assert call_count[0] == 4  # All 4 responses consumed

    # Verify HITL state was cleared
    final_state = await repo.load("test-resume-integration")
    final_hitl_state = HITLState(**final_state.pattern_state["hitl_state"])
    assert final_hitl_state.active is False
    assert final_hitl_state.user_response == "continue"

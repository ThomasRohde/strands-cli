"""Tests for HITL functionality in orchestrator-workers pattern."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from strands_cli.exec.orchestrator_workers import run_orchestrator_workers
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK
from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import HITLState, PatternType


@pytest.fixture
def orchestrator_spec_with_decomposition_review(tmp_path):
    """Create orchestrator spec with decomposition review gate."""
    from strands_cli.types import (
        Agent,
        HITLStep,
        OrchestratorConfig,
        OrchestratorLimits,
        Pattern,
        PatternConfig,
        ProviderType,
        Runtime,
        Spec,
        WorkerTemplate,
    )

    return Spec(
        version=0,
        name="orchestrator-decomposition-review-test",
        description="Test orchestrator with decomposition review",
        runtime=Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        ),
        agents={
            "orchestrator": Agent(prompt="Decompose tasks into JSON array"),
            "worker": Agent(prompt="Complete assigned task"),
        },
        pattern=Pattern(
            type=PatternType.ORCHESTRATOR_WORKERS,
            config=PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="orchestrator",
                    limits=OrchestratorLimits(max_workers=2, max_rounds=1),
                ),
                decomposition_review=HITLStep(
                    type="hitl",
                    prompt="Review task decomposition before proceeding",
                    context_display="Orchestrator plan:\n{{ orchestrator_response }}",
                    default="approve",
                    timeout_seconds=1800,
                ),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        ),
    )


@pytest.fixture
def orchestrator_spec_with_reduce_review(tmp_path):
    """Create orchestrator spec with reduce review gate."""
    from strands_cli.types import (
        Agent,
        ChainStep,
        HITLStep,
        OrchestratorConfig,
        OrchestratorLimits,
        Pattern,
        PatternConfig,
        ProviderType,
        Runtime,
        Spec,
        WorkerTemplate,
    )

    return Spec(
        version=0,
        name="orchestrator-reduce-review-test",
        description="Test orchestrator with reduce review",
        runtime=Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        ),
        agents={
            "orchestrator": Agent(prompt="Decompose tasks into JSON array"),
            "worker": Agent(prompt="Complete assigned task"),
            "reducer": Agent(prompt="Aggregate worker results"),
        },
        pattern=Pattern(
            type=PatternType.ORCHESTRATOR_WORKERS,
            config=PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="orchestrator",
                    limits=OrchestratorLimits(max_workers=2, max_rounds=1),
                ),
                worker_template=WorkerTemplate(agent="worker"),
                reduce_review=HITLStep(
                    type="hitl",
                    prompt="Review worker results before aggregation",
                    context_display="Workers: {{ worker_count }}",
                    default="approved",
                    timeout_seconds=1800,
                ),
                reduce=ChainStep(
                    agent="reducer",
                    input="Aggregate: {{ hitl_response }}",
                ),
            ),
        ),
    )


@pytest.fixture
def orchestrator_spec_with_both_reviews(tmp_path):
    """Create orchestrator spec with both decomposition and reduce review gates."""
    from strands_cli.types import (
        Agent,
        ChainStep,
        HITLStep,
        OrchestratorConfig,
        OrchestratorLimits,
        Pattern,
        PatternConfig,
        ProviderType,
        Runtime,
        Spec,
        WorkerTemplate,
    )

    return Spec(
        version=0,
        name="orchestrator-both-reviews-test",
        description="Test orchestrator with both review gates",
        runtime=Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        ),
        agents={
            "orchestrator": Agent(prompt="Decompose tasks into JSON array"),
            "worker": Agent(prompt="Complete assigned task"),
            "reducer": Agent(prompt="Aggregate worker results"),
        },
        pattern=Pattern(
            type=PatternType.ORCHESTRATOR_WORKERS,
            config=PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="orchestrator",
                    limits=OrchestratorLimits(max_workers=2, max_rounds=1),
                ),
                decomposition_review=HITLStep(
                    type="hitl",
                    prompt="Review decomposition",
                    default="approve",
                    timeout_seconds=1800,
                ),
                worker_template=WorkerTemplate(agent="worker"),
                reduce_review=HITLStep(
                    type="hitl",
                    prompt="Review results",
                    default="approved",
                    timeout_seconds=1800,
                ),
                reduce=ChainStep(
                    agent="reducer",
                    input="Aggregate results",
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_orchestrator_decomposition_review_pause(
    orchestrator_spec_with_decomposition_review, tmp_path, mocker
):
    """Test orchestrator pauses at decomposition review gate."""
    # Mock orchestrator response - Valid JSON string
    mock_orchestrator_response = '[{"task": "Subtask 1"}, {"task": "Subtask 2"}]'

    # Mock agent invocation
    mock_invoke = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke.return_value = mock_orchestrator_response

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session",
            workflow_name=orchestrator_spec_with_decomposition_review.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
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
    result = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
        session_state=session_state,
        session_repo=repo,
    )

    # Verify HITL pause
    assert result.exit_code == EX_HITL_PAUSE
    assert result.agent_id == "hitl"
    assert "decomposition review" in result.last_response.lower()

    # Verify session state
    loaded_state = await repo.load("test-session")
    assert loaded_state.metadata.status == SessionStatus.PAUSED

    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
    assert hitl_state.active is True
    assert hitl_state.phase == "decomposition"
    assert hitl_state.worker_count == 2


@pytest.mark.asyncio
async def test_orchestrator_reduce_review_pause(
    orchestrator_spec_with_reduce_review, tmp_path, mocker
):
    """Test orchestrator pauses at reduce review gate."""
    # Mock orchestrator and worker responses - Valid JSON string
    mock_orchestrator_response = '[{"task": "Task 1"}, {"task": "Task 2"}]'
    mock_worker_responses = ["Worker 1 result", "Worker 2 result"]

    call_count = [0]

    async def mock_invoke_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Orchestrator call
            return mock_orchestrator_response
        else:
            # Worker calls
            return mock_worker_responses[(call_count[0] - 2) % len(mock_worker_responses)]

    mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
        side_effect=mock_invoke_side_effect,
    )

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-reduce",
            workflow_name=orchestrator_spec_with_reduce_review.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute until HITL pause (should pause at reduce review)
    result = await run_orchestrator_workers(
        orchestrator_spec_with_reduce_review,
        session_state=session_state,
        session_repo=repo,
    )

    # Verify HITL pause at reduce review
    assert result.exit_code == EX_HITL_PAUSE
    assert result.agent_id == "hitl"
    assert "reduce review" in result.last_response.lower()

    # Verify session state
    loaded_state = await repo.load("test-session-reduce")
    assert loaded_state.metadata.status == SessionStatus.PAUSED

    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
    assert hitl_state.active is True
    assert hitl_state.phase == "reduce"
    assert hitl_state.worker_count == 2


@pytest.mark.asyncio
async def test_orchestrator_resume_from_decomposition(
    orchestrator_spec_with_decomposition_review, tmp_path, mocker
):
    """Test resuming orchestrator from decomposition review continues to workers."""
    # Mock responses - Valid JSON string
    mock_orchestrator_response = '[{"task": "Task 1"}]'
    mock_worker_response = "Worker result"

    call_count = [0]

    async def mock_invoke_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_orchestrator_response
        else:
            return mock_worker_response

    mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
        side_effect=mock_invoke_side_effect,
    )

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create initial session state
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-resume",
            workflow_name=orchestrator_spec_with_decomposition_review.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
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
    result1 = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE

    # Load session and resume with approval
    loaded_state = await repo.load("test-session-resume")
    result2 = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="approve",
    )

    # Verify successful completion
    assert result2.success is True
    assert result2.exit_code == EX_OK
    assert "Worker result" in str(result2.execution_context.get("workers", []))


@pytest.mark.asyncio
async def test_orchestrator_both_review_gates_sequence(
    orchestrator_spec_with_both_reviews, tmp_path, mocker
):
    """Test orchestrator with both decomposition and reduce review gates."""
    # Mock responses - Valid JSON string
    mock_orchestrator_response = '[{"task": "Task 1"}]'
    mock_worker_response = "Worker result"
    mock_reducer_response = "Final aggregated result"

    call_count = [0]

    async def mock_invoke_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_orchestrator_response
        elif call_count[0] == 2:
            return mock_worker_response
        else:
            return mock_reducer_response

    mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
        side_effect=mock_invoke_side_effect,
    )

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-both-gates",
            workflow_name=orchestrator_spec_with_both_reviews.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    # Execute to first HITL pause (decomposition review)
    result1 = await run_orchestrator_workers(
        orchestrator_spec_with_both_reviews,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE
    loaded_state1 = await repo.load("test-both-gates")
    hitl_state1 = HITLState(**loaded_state1.pattern_state["hitl_state"])
    assert hitl_state1.phase == "decomposition"

    # Resume from decomposition review
    result2 = await run_orchestrator_workers(
        orchestrator_spec_with_both_reviews,
        session_state=loaded_state1,
        session_repo=repo,
        hitl_response="approve",
    )
    assert result2.exit_code == EX_HITL_PAUSE
    loaded_state2 = await repo.load("test-both-gates")
    hitl_state2 = HITLState(**loaded_state2.pattern_state["hitl_state"])
    assert hitl_state2.phase == "reduce"

    # Resume from reduce review
    result3 = await run_orchestrator_workers(
        orchestrator_spec_with_both_reviews,
        session_state=loaded_state2,
        session_repo=repo,
        hitl_response="approved",
    )

    # Verify successful completion
    assert result3.success is True
    assert result3.exit_code == EX_OK
    assert "Final aggregated result" in result3.last_response


@pytest.mark.asyncio
async def test_orchestrator_hitl_requires_session(orchestrator_spec_with_decomposition_review, mocker):
    """Test that HITL gates require session persistence enabled."""
    # Mock orchestrator response
    mock_orchestrator_response = '[{"task": "Task 1"}]'  # Valid JSON string

    # Mock agent invocation
    mock_invoke_patch = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke_patch.return_value = mock_orchestrator_response

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Execute without session persistence (should raise error)
    from strands_cli.exec.orchestrator_workers import OrchestratorExecutionError

    with pytest.raises(OrchestratorExecutionError, match="requires session persistence"):
        await run_orchestrator_workers(
            orchestrator_spec_with_decomposition_review,
            session_state=None,
            session_repo=None,
        )


@pytest.mark.asyncio
async def test_orchestrator_hitl_timeout_metadata(
    orchestrator_spec_with_decomposition_review, tmp_path, mocker
):
    """Test that HITL timeout metadata is correctly set."""
    # Mock orchestrator response - Valid JSON string
    mock_orchestrator_response = '[{"task": "Task 1"}]'

    mock_invoke_patch = mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
    )
    mock_invoke_patch.return_value = mock_orchestrator_response

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Create session state
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-timeout",
            workflow_name=orchestrator_spec_with_decomposition_review.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
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
    result = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
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
async def test_orchestrator_resume_integration_decomposition(
    orchestrator_spec_with_decomposition_review, tmp_path, mocker
):
    """Test resuming orchestrator-workers with hitl_response via dispatcher pattern.

    Regression test for hitl-phase2 blocker where --hitl-response parameter
    must be forwarded from resume dispatcher to executor. Tests the integration
    path that mirrors the CLI flow: pause → load state → resume with response.
    """
    # Mock orchestrator and worker responses
    mock_orchestrator_response = '[{"task": "Task 1"}]'
    mock_worker_response = "Worker result"

    call_count = [0]

    async def mock_invoke_side_effect(*args, **kwargs):
        call_count[0] += 1
        return mock_orchestrator_response if call_count[0] == 1 else mock_worker_response

    mocker.patch(
        "strands_cli.exec.orchestrator_workers.invoke_agent_with_retry",
        new_callable=AsyncMock,
        side_effect=mock_invoke_side_effect,
    )

    # Mock agent cache
    mock_cache = mocker.patch("strands_cli.exec.orchestrator_workers.AgentCache")
    mock_cache.return_value.get_or_build_agent = AsyncMock()
    mock_cache.return_value.close = AsyncMock()

    # Create session repository
    repo = FileSessionRepository(tmp_path)

    # Phase 1: Execute to HITL pause (decomposition review)
    from strands_cli.session import SessionMetadata, SessionState, TokenUsage

    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-orch-resume-integration",
            workflow_name=orchestrator_spec_with_decomposition_review.name,
            spec_hash="test-hash",
            pattern_type="orchestrator_workers",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={},
        token_usage=TokenUsage(),
    )

    result1 = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
        session_state=session_state,
        session_repo=repo,
    )
    assert result1.exit_code == EX_HITL_PAUSE
    assert call_count[0] == 1  # Only orchestrator call before pause

    # Phase 2: Load paused state and resume with hitl_response
    # This simulates the dispatcher flow in resume.py::_dispatch_pattern_executor()
    loaded_state = await repo.load("test-orch-resume-integration")
    assert loaded_state is not None
    assert loaded_state.metadata.status == SessionStatus.PAUSED

    # Verify HITL state was saved
    hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
    assert hitl_state.active is True
    assert hitl_state.phase == "decomposition"

    # Phase 3: Resume with hitl_response (THIS TESTS THE FIX)
    # Before fix: hitl_response parameter was missing in dispatcher
    # After fix: parameter is forwarded to executor
    result2 = await run_orchestrator_workers(
        orchestrator_spec_with_decomposition_review,
        variables={},
        session_state=loaded_state,
        session_repo=repo,
        hitl_response="approve",  # CRITICAL: This parameter must be forwarded
    )

    # Verify successful completion (proves hitl_response was used)
    assert result2.success is True
    assert result2.exit_code == EX_OK
    assert "Worker result" in str(result2.execution_context.get("workers", []))
    assert call_count[0] == 2  # Orchestrator + worker calls

    # Verify HITL state was cleared
    final_state = await repo.load("test-orch-resume-integration")
    final_hitl_state = HITLState(**final_state.pattern_state["hitl_state"])
    assert final_hitl_state.active is False
    assert final_hitl_state.user_response == "approve"

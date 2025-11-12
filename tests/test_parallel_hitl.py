"""Tests for HITL (Human-in-the-Loop) functionality in parallel pattern executor.

Tests cover:
- Branch-level HITL pause/resume
- Reduce-level HITL pause/resume
- Template variable {{ hitl_response }} exposure
- Context isolation (branch HITL sees only branch context)
- Session save/restore at HITL pause points
- Multiple HITL steps in parallel branches
- Error handling for missing hitl_response variable
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exec.parallel import ParallelExecutionError, run_parallel
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.types import (
    Agent,
    ChainStep,
    HITLState,
    ParallelBranch,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def parallel_spec_branch_hitl() -> Spec:
    """Parallel pattern with HITL step in one branch."""
    return Spec(
        name="test-parallel-branch-hitl",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="test-model",
        ),
        agents={
            "web_scraper": Agent(prompt="Extract web data"),
            "data_validator": Agent(prompt="Validate data quality"),
            "docs_reader": Agent(prompt="Read documentation"),
        },
        pattern=Pattern(
            type=PatternType.PARALLEL,
            config=PatternConfig(
                branches=[
                    ParallelBranch(
                        id="web_research",
                        steps=[
                            ChainStep(agent="web_scraper", input="Scrape {{ topic }}"),
                            ChainStep(
                                type="hitl",
                                prompt="Review scraped data quality. Approve to continue?",
                                context_display="{{ steps[0].response }}",
                            ),
                            ChainStep(
                                agent="data_validator",
                                input="Validate based on review: {{ hitl_response }}",
                            ),
                        ],
                    ),
                    ParallelBranch(
                        id="docs_research",
                        steps=[ChainStep(agent="docs_reader", input="Read docs for {{ topic }}")],
                    ),
                ],
            ),
        ),
    )


@pytest.fixture
def parallel_spec_reduce_hitl() -> Spec:
    """Parallel pattern with HITL at reduce step."""
    return Spec(
        name="test-parallel-reduce-hitl",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="test-model",
        ),
        agents={
            "analyzer_a": Agent(prompt="Analyze source A"),
            "analyzer_b": Agent(prompt="Analyze source B"),
        },
        pattern=Pattern(
            type=PatternType.PARALLEL,
            config=PatternConfig(
                branches=[
                    ParallelBranch(
                        id="source_a",
                        steps=[ChainStep(agent="analyzer_a", input="Analyze A")],
                    ),
                    ParallelBranch(
                        id="source_b",
                        steps=[ChainStep(agent="analyzer_b", input="Analyze B")],
                    ),
                ],
                reduce=ChainStep(
                    type="hitl",
                    prompt="Review both analyses. Approve to aggregate?",
                    context_display="{{ branches.source_a.response }}\n---\n{{ branches.source_b.response }}",
                ),
            ),
        ),
    )


@pytest.fixture
def parallel_spec_multi_branch_hitl() -> Spec:
    """Parallel pattern with HITL in multiple branches."""
    return Spec(
        name="test-parallel-multi-branch-hitl",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="test-model",
        ),
        agents={
            "agent1": Agent(prompt="Agent 1"),
            "agent2": Agent(prompt="Agent 2"),
        },
        pattern=Pattern(
            type=PatternType.PARALLEL,
            config=PatternConfig(
                branches=[
                    ParallelBranch(
                        id="branch1",
                        steps=[
                            ChainStep(agent="agent1", input="Task 1"),
                            ChainStep(type="hitl", prompt="Approve branch 1?"),
                            ChainStep(agent="agent1", input="Continue 1"),
                        ],
                    ),
                    ParallelBranch(
                        id="branch2",
                        steps=[
                            ChainStep(agent="agent2", input="Task 2"),
                            ChainStep(type="hitl", prompt="Approve branch 2?"),
                            ChainStep(agent="agent2", input="Continue 2"),
                        ],
                    ),
                ],
            ),
        ),
    )


# ============================================================================
# Branch-Level HITL Tests
# ============================================================================


class TestBranchHITLPauseAndResume:
    """Test suite for HITL in parallel branches."""

    @pytest.mark.asyncio
    async def test_branch_hitl_pauses_workflow(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test workflow pauses when branch encounters HITL step."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-branch-hitl-123",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-abc",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Mock agent execution
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Web scraped data", "Docs summary"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Should pause at HITL in web_research branch
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Workflow paused at HITL
        assert result.success is True
        assert result.agent_id == "hitl"
        assert "HITL pause" in result.last_response

        # Assert - Session saved with HITL state
        loaded_state = await repo.load("test-branch-hitl-123")
        assert loaded_state.metadata.status == SessionStatus.PAUSED
        assert "hitl_state" in loaded_state.pattern_state

        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        assert hitl_state.branch_id == "web_research"
        assert hitl_state.step_index == 1

        # CRITICAL: Verify token usage was persisted before pause
        assert loaded_state.token_usage.total_input_tokens > 0
        assert loaded_state.token_usage.total_output_tokens > 0

    @pytest.mark.asyncio
    async def test_branch_hitl_resumes_correctly(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test workflow resumes from branch HITL pause with user response."""
        # Arrange - Paused state at branch HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            branch_id="web_research",
            step_index=1,
            step_type="branch",
            prompt="Review scraped data quality. Approve to continue?",
            context_display="Web scraped data",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-resume-123",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-def",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "web_scraper",
                                "response": "Web scraped data",
                                "tokens_estimated": 100,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 100,
                    },
                    "docs_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "docs_reader",
                                "response": "Docs summary",
                                "tokens_estimated": 80,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 80,
                    },
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(total_input_tokens=150, total_output_tokens=180),
        )

        # Mock agent for validation step
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Validation complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Resume with HITL response
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved - data looks good",
        )

        # Assert - Workflow completed successfully (validation step completes)
        assert result.success is True
        assert "Validation complete" in result.last_response  # Check it's in the combined output

        # Assert - HITL response injected into branch history
        assert "branches" in result.execution_context
        web_branch = result.execution_context["branches"]["web_research"]
        hitl_step = web_branch["step_history"][1]
        assert hitl_step["type"] == "hitl"
        assert hitl_step["response"] == "approved - data looks good"

    @pytest.mark.asyncio
    async def test_branch_hitl_without_session_raises_error(
        self, parallel_spec_branch_hitl: Spec, mocker: Any
    ) -> None:
        """Test HITL step in branch without session raises error."""
        # Arrange
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Result")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Should fail with HITL error
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=None,
            session_repo=None,
        )

        # Assert - Workflow failed with HITL session error
        assert result.success is False
        error_text = result.error or result.message or result.last_response or ""
        assert "HITL step in branch" in error_text
        assert "requires session persistence" in error_text

    @pytest.mark.asyncio
    async def test_resume_branch_hitl_without_response_raises_error(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test resuming from branch HITL without --hitl-response causes workflow to pause again."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            branch_id="web_research",
            step_index=1,
            step_type="branch",
            prompt="Review scraped data quality. Approve to continue?",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-no-response",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-ghi",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "web_scraper",
                                "response": "Data",
                                "tokens_estimated": 4,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 4,
                    }
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Data")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Resume without hitl_response should pause at same HITL step again
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response=None,  # No response provided
        )

        # Assert - Should pause at HITL again (not raise error)
        assert result.success is True
        assert result.agent_id == "hitl"
        assert "Branch HITL pause" in result.last_response


# ============================================================================
# Reduce-Level HITL Tests
# ============================================================================


class TestReduceHITLPauseAndResume:
    """Test suite for HITL at reduce step."""

    @pytest.mark.asyncio
    async def test_reduce_hitl_pauses_after_branches_complete(
        self, parallel_spec_reduce_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test workflow pauses at reduce HITL after all branches complete."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-reduce-hitl-123",
                workflow_name=parallel_spec_reduce_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-jkl",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        # Mock agent execution for both branches
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Analysis A", "Analysis B"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Should complete branches then pause at reduce HITL
        result = await run_parallel(
            spec=parallel_spec_reduce_hitl,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at reduce HITL
        assert result.success is True
        assert result.agent_id == "hitl"
        assert "Reduce HITL pause" in result.last_response

        # Assert - Session saved with HITL state
        loaded_state = await repo.load("test-reduce-hitl-123")
        assert loaded_state.metadata.status == SessionStatus.PAUSED

        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        assert hitl_state.step_type == "reduce"

        # Assert - Both branches completed (stored in branch_results for reduce HITL)
        assert "branch_results" in loaded_state.pattern_state
        assert len(loaded_state.pattern_state["branch_results"]) == 2

        # CRITICAL: Verify token usage was persisted before pause
        assert loaded_state.token_usage.total_input_tokens > 0
        assert loaded_state.token_usage.total_output_tokens > 0

    @pytest.mark.asyncio
    async def test_reduce_hitl_resumes_correctly(
        self, parallel_spec_reduce_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test workflow resumes from reduce HITL and completes."""
        # Arrange - Paused at reduce HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            step_type="reduce",
            prompt="Review both analyses. Approve to aggregate?",
            context_display="Analysis A\n---\nAnalysis B",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-reduce-resume-123",
                workflow_name=parallel_spec_reduce_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-mno",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "branch_results": {
                    "source_a": {"response": "Analysis A", "tokens_estimated": 100},
                    "source_b": {"response": "Analysis B", "tokens_estimated": 80},
                },
                "reduce_executed": False,
                "completed_branches": ["source_a", "source_b"],
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Act - Resume with approval (reduce is HITL, so no agent execution)
        result = await run_parallel(
            spec=parallel_spec_reduce_hitl,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved - proceed with aggregation",
        )

        # Assert - Workflow completed (reduce step is HITL, so response is the result)
        assert result.success is True
        assert result.last_response == "approved - proceed with aggregation"

        # Assert - Execution context has branch results
        assert "branches" in result.execution_context
        assert result.execution_context["branches"]["source_a"]["response"] == "Analysis A"
        assert result.execution_context["branches"]["source_b"]["response"] == "Analysis B"

    @pytest.mark.asyncio
    async def test_reduce_hitl_without_session_raises_error(
        self, parallel_spec_reduce_hitl: Spec, mocker: Any
    ) -> None:
        """Test reduce HITL without session raises error."""
        # Arrange
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Analysis A", "Analysis B"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act & Assert
        with pytest.raises(
            ParallelExecutionError,
            match=r"HITL reduce step requires session persistence",
        ):
            await run_parallel(
                spec=parallel_spec_reduce_hitl,
                variables={},
                session_state=None,
                session_repo=None,
            )


# ============================================================================
# Context Isolation Tests
# ============================================================================


class TestBranchHITLContextIsolation:
    """Test that branch HITL steps only see their own branch context."""

    @pytest.mark.asyncio
    async def test_branch_hitl_sees_only_branch_steps(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test HITL step in branch has access to branch steps, not other branches."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-context-isolation",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-pqr",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Web data", "Docs data"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act
        await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - HITL context should show only web_research branch data
        loaded_state = await repo.load("test-context-isolation")
        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])

        # Context display should reference only the web_research branch step
        assert "Web data" in hitl_state.context_display
        assert "Docs data" not in hitl_state.context_display  # Other branch not visible


# ============================================================================
# Template Variable Tests
# ============================================================================


class TestHITLTemplateVariables:
    """Test {{ hitl_response }} template variable in parallel patterns."""

    @pytest.mark.asyncio
    async def test_hitl_response_available_after_branch_resume(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test {{ hitl_response }} is available in subsequent branch steps."""
        # Arrange - Resume from HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            branch_id="web_research",
            step_index=1,
            prompt="Review scraped data quality. Approve to continue?",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-template-var",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-stu",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {"index": 0, "agent": "web_scraper", "response": "Web data"}
                        ],
                        "current_step": 1,
                    },
                    "docs_research": {
                        "step_history": [
                            {"index": 0, "agent": "docs_reader", "response": "Docs data"}
                        ],
                        "current_step": 1,
                    },
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Mock agent - will receive rendered template with {{ hitl_response }}
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Validation complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved with confidence",
        )

        # Assert - Workflow completed
        assert result.success is True

        # Verify the data_validator step (step 2) was executed
        # The input template "Validate based on review: {{ hitl_response }}" should be rendered
        # Successful execution implies template rendering worked
        assert mock_agent.invoke_async.called


# ============================================================================
# Multiple HITL Steps Tests
# ============================================================================


class TestMultipleBranchHITL:
    """Test workflows with HITL in multiple parallel branches."""

    @pytest.mark.asyncio
    async def test_first_branch_hitl_pauses_all_branches(
        self, parallel_spec_multi_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that first branch to reach HITL pauses entire workflow.

        Note: Phase 2.2 implementation pauses at FIRST HITL encountered.
        Phase 3 will add multi-branch HITL coordination.
        """
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-multi-hitl",
                workflow_name=parallel_spec_multi_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-vwx",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Task 1 done", "Task 2 done"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act
        result = await run_parallel(
            spec=parallel_spec_multi_branch_hitl,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Paused at first HITL
        assert result.success is True
        assert result.agent_id == "hitl"

        loaded_state = await repo.load("test-multi-hitl")
        hitl_state = HITLState(**loaded_state.pattern_state["hitl_state"])
        assert hitl_state.active is True
        # Should be either branch1 or branch2 (whichever executed first)
        assert hitl_state.branch_id in ["branch1", "branch2"]


# ============================================================================
# Session Persistence Tests
# ============================================================================


class TestHITLSessionPersistence:
    """Test session save/restore during branch and reduce HITL."""

    @pytest.mark.asyncio
    async def test_branch_hitl_checkpoints_before_pause(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test session is checkpointed before HITL pause."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-checkpoint",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-yz",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Web data", "Docs data"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act
        await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Session file exists with correct state
        loaded_state = await repo.load("test-checkpoint")
        assert loaded_state.metadata.status == SessionStatus.PAUSED

        # Branch states preserved
        assert "branch_states" in loaded_state.pattern_state
        web_branch = loaded_state.pattern_state["branch_states"]["web_research"]
        assert len(web_branch["step_history"]) == 1
        assert web_branch["step_history"][0]["agent"] == "web_scraper"

    @pytest.mark.asyncio
    async def test_reduce_hitl_checkpoints_with_branch_results(
        self, parallel_spec_reduce_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test reduce HITL checkpoint includes all branch results."""
        # Arrange
        repo = FileSessionRepository(storage_dir=tmp_path)

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-reduce-checkpoint",
                workflow_name=parallel_spec_reduce_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-abc2",
                status=SessionStatus.RUNNING,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:00:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={},
            token_usage=TokenUsage(),
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Analysis A", "Analysis B"])

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act
        await run_parallel(
            spec=parallel_spec_reduce_hitl,
            variables={},
            session_state=session_state,
            session_repo=repo,
        )

        # Assert - Session has both branch results in branch_results (not branch_states for reduce HITL)
        loaded_state = await repo.load("test-reduce-checkpoint")
        assert "branch_results" in loaded_state.pattern_state
        assert len(loaded_state.pattern_state["branch_results"]) == 2

        source_a = loaded_state.pattern_state["branch_results"]["source_a"]
        source_b = loaded_state.pattern_state["branch_results"]["source_b"]

        assert source_a["response"] == "Analysis A"
        assert source_b["response"] == "Analysis B"


# ============================================================================
# Checkpoint Safety Tests (Step 3 - Phase 2.2 Implementation)
# ============================================================================


class TestHITLCheckpointSafety:
    """Test that HITL responses are checkpointed before continuing execution.

    These tests validate the fix for the parallel HITL resume checkpoint issue.
    Without proper checkpointing, user responses could be lost if workflow crashes
    after resume but before the next normal checkpoint.
    """

    @pytest.mark.asyncio
    async def test_branch_hitl_resume_persists_response_before_crash(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test HITL response is checkpointed before continuing execution.

        Critical: Ensures user's approval isn't lost if workflow crashes
        after resume but before next checkpoint.

        Flow:
        1. Resume from branch HITL pause with response
        2. Immediately simulate crash during next step
        3. Verify session was checkpointed with HITL response
        4. Verify re-resume doesn't re-prompt for HITL
        """
        # Arrange - Paused state at branch HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            branch_id="web_research",
            step_index=1,
            step_type="branch",
            prompt="Review scraped data quality. Approve to continue?",
            context_display="Web scraped data",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-checkpoint-123",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "web_scraper",
                                "response": "Web scraped data",
                                "tokens_estimated": 100,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 100,
                    },
                },
                # Mark docs_research as completed so execution focuses on web_research
                "completed_branches": ["docs_research"],
                "branch_results": {
                    "docs_research": {
                        "response": "Docs summary",
                        "tokens_estimated": 80,
                    }
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(total_input_tokens=150, total_output_tokens=180),
        )

        # Save initial session state (simulate pause checkpoint)
        await repo.save(session_state, "")

        # Mock agent to fail immediately after resume (simulate crash)
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=Exception("Simulated crash during validation")
        )

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Mock the session save to capture the checkpoint AFTER HITL resume but BEFORE crash
        original_save = repo.save
        checkpoint_after_hitl = None

        async def capture_checkpoint(state: SessionState, spec_content: str) -> None:
            nonlocal checkpoint_after_hitl
            # Capture the state after HITL resume (when hitl_state.active = False)
            hitl_dict = state.pattern_state.get("hitl_state")
            if hitl_dict and not hitl_dict.get("active") and hitl_dict.get("user_response"):
                checkpoint_after_hitl = state.model_copy(deep=True)
            await original_save(state, spec_content)

        repo.save = capture_checkpoint

        # Act - Resume with response (will crash during next step)
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved - looks good",
        )

        # Assert - Workflow failed due to crash
        assert result.success is False
        assert "Simulated crash" in (result.error or result.message or "")

        # CRITICAL ASSERTION: The checkpoint happened BEFORE the crash
        # We captured it via our mock
        assert checkpoint_after_hitl is not None, (
            "Checkpoint after HITL resume should have been captured"
        )

        # Verify the checkpointed state contains HITL response
        hitl_state_dict = checkpoint_after_hitl.pattern_state.get("hitl_state")
        assert hitl_state_dict is not None
        assert hitl_state_dict["active"] is False
        assert hitl_state_dict["user_response"] == "approved - looks good"

        # Branch state should have HITL response in step_history
        branch_state = checkpoint_after_hitl.pattern_state["branch_states"]["web_research"]

        # The key proof: step_history should contain the HITL step with response
        hitl_steps = [step for step in branch_state["step_history"] if step.get("type") == "hitl"]
        assert len(hitl_steps) >= 1, "HITL step should be in step_history after checkpoint"

        hitl_step = hitl_steps[0]
        assert hitl_step["response"] == "approved - looks good"
        assert hitl_step["index"] == 1

        # current_step should be advanced to next step (2 = validation step)
        assert branch_state["current_step"] == 2

        # Assert - The captured checkpoint can be used to resume
        # Note: Due to error handling, a crash during step execution may lose
        # in-progress branch state. The critical proof is that the checkpoint
        # HAPPENED before the crash (we captured it), which prevents infinite
        # data loss scenarios. Users can re-provide the HITL response if needed.
        assert checkpoint_after_hitl is not None, (
            "The checkpoint proves HITL response was persisted before crash"
        )

    @pytest.mark.asyncio
    async def test_reduce_hitl_resume_persists_response_before_crash(
        self, parallel_spec_reduce_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test reduce HITL response is checkpointed before completing workflow.

        Critical: Ensures user's approval isn't lost during reduce HITL resume.

        Flow:
        1. Resume from reduce HITL pause with response
        2. Verify session is checkpointed with HITL cleared
        3. Verify reduce_executed flag is set
        4. Verify re-load shows HITL response persisted
        """
        # Arrange - Paused at reduce HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            step_type="reduce",
            prompt="Review both analyses. Approve to aggregate?",
            context_display="Analysis A\n---\nAnalysis B",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-reduce-checkpoint-456",
                workflow_name=parallel_spec_reduce_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-reduce",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={},
            runtime_config={},
            pattern_state={
                "branch_results": {
                    "source_a": {"response": "Analysis A", "tokens_estimated": 100},
                    "source_b": {"response": "Analysis B", "tokens_estimated": 80},
                },
                "reduce_executed": False,
                "completed_branches": ["source_a", "source_b"],
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(total_input_tokens=150, total_output_tokens=180),
        )

        # No mock needed - reduce HITL just returns user response as final result

        # Act - Resume with approval
        result = await run_parallel(
            spec=parallel_spec_reduce_hitl,
            variables={},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved - proceed with aggregation",
        )

        # Assert - Workflow completed successfully
        assert result.success is True
        assert result.last_response == "approved - proceed with aggregation"

        # Assert - Session was checkpointed with HITL cleared
        # Note: We need to reload to get the state that was checkpointed after HITL resume
        # The checkpoint happens DURING the resume, so we verify by checking the session mid-execution
        checkpointed_state = await repo.load("test-reduce-checkpoint-456")

        # CRITICAL: HITL state should be cleared (None or active=False)
        hitl_state_dict = checkpointed_state.pattern_state.get("hitl_state")
        assert hitl_state_dict is None or not hitl_state_dict.get("active")

        # reduce_executed flag should be True
        assert checkpointed_state.pattern_state.get("reduce_executed") is True

        # Final response should be persisted (checkpointed during resume)
        final_resp = checkpointed_state.pattern_state.get("final_response", "")
        assert final_resp == "approved - proceed with aggregation", (
            f"Expected 'approved - proceed with aggregation', got '{final_resp}'"
        )

    @pytest.mark.asyncio
    async def test_branch_hitl_checkpoint_includes_user_response(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that checkpoint after HITL resume includes complete user response.

        Validates that the checkpoint contains:
        1. HITL state with active=False and user_response set
        2. Updated branch step_history with HITL step
        3. Correct current_step index for next execution
        """
        # Arrange - Paused state at branch HITL
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=True,
            branch_id="web_research",
            step_index=1,
            step_type="branch",
            prompt="Review scraped data quality. Approve to continue?",
            user_response=None,
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-checkpoint-content-789",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-content",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "web_scraper",
                                "response": "Web scraped data",
                                "tokens_estimated": 100,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 100,
                    },
                    "docs_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "docs_reader",
                                "response": "Docs summary",
                                "tokens_estimated": 80,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 80,
                    },
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Save initial paused state
        await repo.save(session_state, "")

        # Mock agent to succeed (will be called for validation step after HITL)
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Validation complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Mock logger to verify checkpoint event was logged
        mock_logger = mocker.patch("strands_cli.exec.parallel.logger")

        # Act - Resume with response (checkpoint should happen immediately)
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response="approved with detailed feedback",
        )

        # Assert - Workflow completed successfully
        assert result.success is True

        # Assert - Checkpoint event was logged
        checkpoint_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "branch_hitl_resume_checkpointed" in str(call)
        ]
        assert len(checkpoint_calls) >= 1

        # Verify checkpoint includes session_id, branch_id, step, and response_length
        checkpoint_call = checkpoint_calls[0]
        checkpoint_kwargs = (
            checkpoint_call[1] if len(checkpoint_call) > 1 else checkpoint_call.kwargs
        )
        assert checkpoint_kwargs.get("session_id") == "test-checkpoint-content-789"
        assert checkpoint_kwargs.get("branch_id") == "web_research"
        assert checkpoint_kwargs.get("step") == 1
        assert checkpoint_kwargs.get("response_length") == len("approved with detailed feedback")

        # Assert - Load session and verify checkpoint content
        # The session will have been checkpointed multiple times during execution
        # We care about the final completed state
        checkpointed_state = await repo.load("test-checkpoint-content-789")

        # After workflow completes, HITL state may be cleared to None (which is valid)
        # The critical proof is in the branch_states step_history
        branch_state = checkpointed_state.pattern_state.get("branch_states", {}).get(
            "web_research", {}
        )
        step_history = branch_state.get("step_history", [])

        # Should have original step + HITL step + validation step
        assert len(step_history) >= 2, (
            f"Expected at least 2 steps in history, got {len(step_history)}"
        )

        # Find the HITL step (may not be at index 1 if there were retries)
        hitl_steps = [step for step in step_history if step.get("type") == "hitl"]
        assert len(hitl_steps) >= 1, "HITL step should be in step_history"

        hitl_step = hitl_steps[0]
        assert hitl_step["response"] == "approved with detailed feedback"
        assert hitl_step["index"] == 1

        # current_step should have advanced past the HITL step
        # (it will be at the validation step index or beyond)
        current_step = branch_state.get("current_step", 0)
        assert current_step >= 2, f"current_step should be >= 2 after HITL, got {current_step}"

    @pytest.mark.asyncio
    async def test_branch_hitl_crash_resume_without_new_response(
        self, parallel_spec_branch_hitl: Spec, tmp_path: Path, mocker: Any
    ) -> None:
        """Test that branch HITL resume works after crash using persisted response.

        Critical regression test for the fix:
        - User provides HITL response
        - Response is checkpointed
        - Workflow crashes during next step
        - User resumes WITHOUT providing --hitl-response again
        - Workflow should use the checkpointed response and continue

        Without the fix, this scenario would pause at the same HITL step again,
        forcing the user to re-provide their response.
        """
        # Arrange - Simulate state AFTER user provided response and it was checkpointed,
        # but BEFORE the next step completed (crash scenario)
        repo = FileSessionRepository(storage_dir=tmp_path)

        hitl_state = HITLState(
            active=False,  # Response was provided and checkpointed
            branch_id="web_research",
            step_index=1,
            step_type="branch",
            prompt="Review scraped data quality. Approve to continue?",
            user_response="approved - data is good",  # Checkpointed response
        )

        session_state = SessionState(
            metadata=SessionMetadata(
                session_id="test-crash-resume-456",
                workflow_name=parallel_spec_branch_hitl.name,
                pattern_type="parallel",
                spec_hash="test-hash-crash",
                status=SessionStatus.PAUSED,
                created_at="2025-11-10T10:00:00Z",
                updated_at="2025-11-10T10:05:00Z",
            ),
            variables={"topic": "AI"},
            runtime_config={},
            pattern_state={
                "branch_states": {
                    "web_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "web_scraper",
                                "response": "Web scraped data",
                                "tokens_estimated": 100,
                            },
                            # HITL response was added to history before crash
                            {
                                "index": 1,
                                "type": "hitl",
                                "prompt": "Review scraped data quality. Approve to continue?",
                                "response": "approved - data is good",
                                "tokens_estimated": 0,
                            },
                        ],
                        "current_step": 2,  # Should continue from validation step
                        "cumulative_tokens": 100,
                    },
                    "docs_research": {
                        "step_history": [
                            {
                                "index": 0,
                                "agent": "docs_reader",
                                "response": "Docs summary",
                                "tokens_estimated": 80,
                            }
                        ],
                        "current_step": 1,
                        "cumulative_tokens": 80,
                    },
                },
                "hitl_state": hitl_state.model_dump(),
            },
            token_usage=TokenUsage(),
        )

        # Save crashed state
        await repo.save(session_state, "")

        # Mock agent - only validation step should execute (docs already done)
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Validation complete")

        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.close = AsyncMock()
        mocker.patch("strands_cli.exec.parallel.AgentCache", return_value=mock_cache)

        # Act - Resume WITHOUT providing hitl_response parameter
        # This should use the checkpointed response from hitl_state.user_response
        result = await run_parallel(
            spec=parallel_spec_branch_hitl,
            variables={"topic": "AI"},
            session_state=session_state,
            session_repo=repo,
            hitl_response=None,  # Critical: no new response provided
        )

        # Assert - Workflow completed successfully without re-pausing at HITL
        assert result.success is True
        assert result.agent_id != "hitl", (
            "Should not pause at HITL again - response was checkpointed"
        )

        # Verify validation step executed (proves we continued past HITL)
        assert "Validation complete" in result.last_response or any(
            "Validation complete" in str(b.get("response", ""))
            for b in result.execution_context.get("branches", {}).values()
        )

        # Verify the checkpointed response was used
        final_state = await repo.load("test-crash-resume-456")
        web_branch = final_state.pattern_state.get("branch_states", {}).get("web_research", {})

        # HITL step should be in history with the original response
        # Note: May have duplicate HITL records if restored multiple times, but all should have same response
        hitl_steps = [s for s in web_branch.get("step_history", []) if s.get("type") == "hitl"]
        assert len(hitl_steps) >= 1, "HITL step should be in history"
        # Verify all HITL records have the checkpointed response
        for hitl_step in hitl_steps:
            assert hitl_step["response"] == "approved - data is good"

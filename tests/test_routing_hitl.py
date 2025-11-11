"""Tests for HITL (Human-in-the-Loop) functionality in routing pattern executor.

Tests cover:
- Router review HITL pause with session save
- Router review HITL resume with approval
- Router review HITL resume with override
- Router context injection ({{ router.chosen_route }}, {{ router.response }})
- Timeout handling for router review
- Error handling for missing session persistence
- Error handling for invalid override format
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.routing import RoutingExecutionError, run_routing
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
from strands_cli.types import HITLState, PatternType, Spec


@pytest.fixture
def mock_session_repo() -> Any:
    """Create mock session repository for testing."""
    repo = AsyncMock()
    repo.save = AsyncMock()
    repo.load = AsyncMock()
    return repo


@pytest.fixture
def routing_hitl_spec(sample_openai_spec: Spec) -> Spec:
    """Create routing spec with router review HITL gate."""
    spec = sample_openai_spec.model_copy(deep=True)
    spec.pattern.type = PatternType.ROUTING

    # Configure routing pattern with review_router
    from strands_cli.types import ChainStep, Route, RouterConfig, RoutingConfig

    router_config = RouterConfig(
        agent="classifier",
        input="Classify: {{ inquiry }}",
        max_retries=2,
        review_router=ChainStep(
            type="hitl",
            prompt="Review router decision. Respond with 'approved' or 'route:<name>' to override",
            context_display="Router chose: {{ router.chosen_route }}\\nReasoning: {{ router.response }}",
            timeout_seconds=0,
        ),
    )

    routes = {
        "technical": Route(
            then=[ChainStep(agent="test_agent", input="Handle technical: {{ inquiry }}")]
        ),
        "billing": Route(then=[ChainStep(agent="test_agent", input="Handle billing: {{ inquiry }}")]),
    }

    spec.pattern.config = RoutingConfig(router=router_config, routes=routes)
    spec.agents["classifier"] = spec.agents["test_agent"]

    return spec


@pytest.fixture
def routing_session_state() -> SessionState:
    """Create session state for routing HITL tests."""
    return SessionState(
        metadata=SessionMetadata(
            session_id="test-routing-hitl-session",
            workflow_name="routing-hitl-test",
            pattern_type="routing",
            spec_hash="test123",
            status=SessionStatus.RUNNING,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        ),
        variables={"inquiry": "My account shows double charges"},
        runtime_config={},
        pattern_state={
            "router_executed": False,
            "current_step": 0,
            "step_history": [],
        },
        token_usage=TokenUsage(total_tokens=0),
        artifacts_written=[],
    )


class TestRouterReviewHITLPause:
    """Test suite for router review HITL pause functionality."""

    @pytest.mark.asyncio
    async def test_router_review_hitl_pause_saves_session(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test that router review HITL pauses execution and saves session."""
        # Arrange
        variables = {"inquiry": "My account shows double charges"}

        # Mock router execution to return classification
        mock_agent = AsyncMock()
        mock_agent.invoke_async = AsyncMock(
            return_value='{"route": "billing", "reasoning": "Payment issue detected"}'
        )

        # Patch AgentCache to return mock agent
        with patch("strands_cli.exec.routing.AgentCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act & Assert - Should exit with EX_HITL_PAUSE
            with pytest.raises(SystemExit) as exc_info:
                await run_routing(
                    routing_hitl_spec,
                    variables,
                    routing_session_state,
                    mock_session_repo,
                )

            assert exc_info.value.code == EX_HITL_PAUSE

            # Verify session was saved with HITL state
            assert mock_session_repo.save.called
            saved_state = mock_session_repo.save.call_args[0][0]

            assert "hitl_state" in saved_state.pattern_state
            hitl_state = HITLState(**saved_state.pattern_state["hitl_state"])
            assert hitl_state.active is True
            assert hitl_state.router_review is True
            assert "Review router decision" in hitl_state.prompt

            # Verify router decision was saved
            assert "router_decision" in saved_state.pattern_state
            router_decision = saved_state.pattern_state["router_decision"]
            assert router_decision["chosen_route"] == "billing"
            assert "Payment issue detected" in router_decision["response"]


class TestRouterReviewHITLResume:
    """Test suite for router review HITL resume functionality."""

    @pytest.mark.asyncio
    async def test_router_review_hitl_resume_with_approval(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test resuming with 'approved' continues with router's choice."""
        # Arrange - Set up paused session state
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review router decision",
            context_display="Router chose: billing",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": '{"route": "billing", "reasoning": "Payment issue"}',
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test inquiry"}

        # Mock route execution
        mock_chain_result = MagicMock()
        mock_chain_result.success = True
        mock_chain_result.last_response = "Billing support response"
        mock_chain_result.execution_context = {"steps": []}
        mock_chain_result.duration_seconds = 1.5
        mock_chain_result.variables = {}

        with (
            patch("strands_cli.exec.routing.run_chain", return_value=mock_chain_result),
            patch("strands_cli.exec.routing.AgentCache") as mock_cache_class,
        ):
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act
            result = await run_routing(
                routing_hitl_spec,
                variables,
                routing_session_state,
                mock_session_repo,
                hitl_response="approved",
            )

            # Assert
            assert result.success is True
            assert result.execution_context["chosen_route"] == "billing"

            # Verify HITL state was deactivated
            assert routing_session_state.pattern_state["hitl_state"]["active"] is False
            assert (
                routing_session_state.pattern_state["hitl_state"]["user_response"] == "approved"
            )

    @pytest.mark.asyncio
    async def test_router_review_hitl_resume_with_override(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test resuming with 'route:technical' overrides router's choice."""
        # Arrange - Router chose 'billing', human overrides to 'technical'
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review router decision",
            context_display="Router chose: billing",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": '{"route": "billing"}',
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test inquiry"}

        # Mock route execution
        mock_chain_result = MagicMock()
        mock_chain_result.success = True
        mock_chain_result.last_response = "Technical support response"
        mock_chain_result.execution_context = {"steps": []}
        mock_chain_result.duration_seconds = 1.5
        mock_chain_result.variables = {}

        with (
            patch("strands_cli.exec.routing.run_chain", return_value=mock_chain_result),
            patch("strands_cli.exec.routing.AgentCache") as mock_cache_class,
        ):
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act
            result = await run_routing(
                routing_hitl_spec,
                variables,
                routing_session_state,
                mock_session_repo,
                hitl_response="route:technical",
            )

            # Assert - Route should be overridden to 'technical'
            assert result.success is True
            assert result.execution_context["chosen_route"] == "technical"

            # Verify override was recorded
            assert routing_session_state.pattern_state["chosen_route"] == "technical"

    @pytest.mark.asyncio
    async def test_router_review_hitl_invalid_override_format(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test invalid override format raises error."""
        # Arrange
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review router decision",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": "{}",
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test"}

        with patch("strands_cli.exec.routing.AgentCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act & Assert
            with pytest.raises(RoutingExecutionError) as exc_info:
                await run_routing(
                    routing_hitl_spec,
                    variables,
                    routing_session_state,
                    mock_session_repo,
                    hitl_response="invalid format",
                )

            assert "Invalid router review response" in str(exc_info.value)
            assert "Expected 'approved' or 'route:<route_name>'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_router_review_hitl_invalid_route_override(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test override to nonexistent route raises error."""
        # Arrange
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review router decision",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": "{}",
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test"}

        with patch("strands_cli.exec.routing.AgentCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act & Assert
            with pytest.raises(RoutingExecutionError) as exc_info:
                await run_routing(
                    routing_hitl_spec,
                    variables,
                    routing_session_state,
                    mock_session_repo,
                    hitl_response="route:nonexistent",
                )

            assert "Invalid route" in str(exc_info.value)
            assert "nonexistent" in str(exc_info.value)


class TestRouterReviewHITLErrors:
    """Test suite for router review HITL error handling."""

    @pytest.mark.asyncio
    async def test_router_review_hitl_without_session_fails(
        self,
        routing_hitl_spec: Spec,
    ) -> None:
        """Test router review HITL without session persistence raises BLOCKER error."""
        # Arrange
        variables = {"inquiry": "Test inquiry"}

        # Mock router execution
        mock_agent = AsyncMock()
        mock_agent.invoke_async = AsyncMock(return_value='{"route": "billing"}')

        with patch("strands_cli.exec.routing.AgentCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act & Assert - Should raise BLOCKER error
            with pytest.raises(RoutingExecutionError) as exc_info:
                await run_routing(
                    routing_hitl_spec,
                    variables,
                    session_state=None,  # No session
                    session_repo=None,
                )

            assert "requires session persistence" in str(exc_info.value)
            assert "Remove --no-save-session flag" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_router_review_hitl_missing_response_on_resume(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test resuming paused session without hitl_response raises error."""
        # Arrange - Session paused for router review
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review router decision",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": "{}",
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test"}  # No hitl_response

        with patch("strands_cli.exec.routing.AgentCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act & Assert
            with pytest.raises(RoutingExecutionError) as exc_info:
                await run_routing(
                    routing_hitl_spec,
                    variables,
                    routing_session_state,
                    mock_session_repo,
                )

            assert "waiting for router review HITL response" in str(exc_info.value)
            assert "--hitl-response" in str(exc_info.value)


class TestRouterContextInjection:
    """Test suite for router context injection in route templates."""

    @pytest.mark.asyncio
    async def test_router_context_available_in_routes(
        self,
        routing_hitl_spec: Spec,
        routing_session_state: SessionState,
        mock_session_repo: Any,
    ) -> None:
        """Test {{ router.chosen_route }} and {{ router.response }} available in routes."""
        # Arrange - Resume from HITL with approval
        routing_session_state.pattern_state["hitl_state"] = HITLState(
            active=True,
            router_review=True,
            prompt="Review",
        ).model_dump()
        routing_session_state.pattern_state["router_decision"] = {
            "chosen_route": "billing",
            "response": '{"route": "billing", "reasoning": "Payment issue"}',
        }
        routing_session_state.metadata.status = SessionStatus.PAUSED

        variables = {"inquiry": "Test"}

        # Mock route execution to capture variables passed
        captured_variables = {}

        async def mock_run_chain(spec, variables, *args, **kwargs):
            captured_variables.update(variables)
            result = MagicMock()
            result.success = True
            result.last_response = "Response"
            result.execution_context = {"steps": []}
            result.duration_seconds = 1.0
            result.variables = {}
            return result

        with (
            patch("strands_cli.exec.routing.run_chain", side_effect=mock_run_chain),
            patch("strands_cli.exec.routing.AgentCache") as mock_cache_class,
        ):
            mock_cache = AsyncMock()
            mock_cache.close = AsyncMock()
            mock_cache_class.return_value = mock_cache

            # Act
            await run_routing(
                routing_hitl_spec,
                variables,
                routing_session_state,
                mock_session_repo,
                hitl_response="approved",
            )

            # Assert - Router context should be in variables passed to route
            assert "router" in captured_variables
            assert captured_variables["router"]["chosen_route"] == "billing"
            assert "Payment issue" in captured_variables["router"]["response"]


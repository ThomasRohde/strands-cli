"""Tests for routing pattern executor.

Tests routing pattern execution including:
- Valid routing with route selection
- Invalid route name error handling
- Malformed JSON retry logic
- Multi-agent configuration
- Template context injection (router.chosen_route)
- Budget tracking across router + route execution
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from strands_cli.exec.routing import (
    RoutingExecutionError,
    _parse_router_response,
    _validate_route_exists,
    run_routing,
)
from strands_cli.types import (
    Agent,
    ChainStep,
    PatternConfig,
    PatternType,
    ProviderType,
    Route,
    RouterConfig,
    RouterDecision,
    Runtime,
    Spec,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def minimal_routing_spec() -> Spec:
    """Create a minimal valid routing spec with 3 routes."""
    return Spec(
        version=0,
        name="test-routing",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "router": Agent(prompt="You are a classifier"),
            "faq_handler": Agent(prompt="You answer FAQs"),
            "researcher": Agent(prompt="You research topics"),
            "escalator": Agent(prompt="You escalate to human"),
        },
        pattern={
            "type": PatternType.ROUTING,
            "config": PatternConfig(
                router=RouterConfig(agent="router", input="Classify: {{ query }}"),
                routes={
                    "faq": Route(then=[ChainStep(agent="faq_handler", input="Answer briefly")]),
                    "research": Route(
                        then=[
                            ChainStep(agent="researcher", input="Research topic"),
                            ChainStep(agent="faq_handler", input="Summarize findings"),
                        ]
                    ),
                    "escalate": Route(then=[ChainStep(agent="escalator", input="Escalate")]),
                },
            ),
        },
    )


@pytest.fixture
def mock_agent():
    """Create a mock agent with invoke_async method."""
    agent = MagicMock()
    agent.invoke_async = AsyncMock()
    return agent


# ============================================================================
# Router Response Parsing Tests
# ============================================================================


def test_parse_router_response_valid_json():
    """Test parsing valid JSON router response."""
    response = '{"route": "faq"}'
    decision = _parse_router_response(response, attempt=1)

    assert isinstance(decision, RouterDecision)
    assert decision.route == "faq"


def test_parse_router_response_json_block():
    """Test parsing JSON from markdown code block."""
    response = """Here's my decision:

```json
{"route": "research"}
```

I chose research because..."""
    decision = _parse_router_response(response, attempt=1)

    assert decision.route == "research"


def test_parse_router_response_regex_extraction():
    """Test parsing JSON via regex extraction."""
    response = 'I think the best route is {"route": "escalate"} for this case.'
    decision = _parse_router_response(response, attempt=1)

    assert decision.route == "escalate"


def test_parse_router_response_malformed():
    """Test that malformed responses raise error."""
    response = "This is not JSON at all"

    with pytest.raises(RoutingExecutionError) as exc_info:
        _parse_router_response(response, attempt=1)

    assert "Failed to parse router response" in str(exc_info.value)


def test_parse_router_response_missing_route_key():
    """Test that JSON without 'route' key raises error."""
    response = '{"decision": "faq"}'  # Wrong key

    with pytest.raises(RoutingExecutionError):
        _parse_router_response(response, attempt=1)


# ============================================================================
# Route Validation Tests
# ============================================================================


def test_validate_route_exists_valid():
    """Test validation passes for valid route."""
    routes = {"faq": Route(then=[]), "research": Route(then=[])}
    _validate_route_exists("faq", routes)  # Should not raise


def test_validate_route_exists_invalid():
    """Test validation fails for invalid route."""
    routes = {"faq": Route(then=[]), "research": Route(then=[])}

    with pytest.raises(RoutingExecutionError) as exc_info:
        _validate_route_exists("unknown", routes)

    error_msg = str(exc_info.value)
    assert "Invalid route 'unknown'" in error_msg
    assert "faq" in error_msg
    assert "research" in error_msg


# ============================================================================
# Full Routing Execution Tests
# ============================================================================


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_success(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test successful routing execution with valid route selection."""
    # Mock router agent response - invoke_async returns string directly
    mock_agent.invoke_async = AsyncMock(return_value='{"route": "faq"}')
    mock_get_agent.return_value = mock_agent

    # Mock chain execution result
    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "FAQ answered"
    chain_result.duration = 1.5
    chain_result.duration_seconds = 1.5
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    # Execute routing
    result = await run_routing(minimal_routing_spec, variables={"query": "test"})

    # Verify router was called
    assert mock_get_agent.called
    assert mock_agent.invoke_async.called

    # Verify chain was called with correct spec
    assert mock_run_chain.called
    chain_spec = mock_run_chain.call_args[0][0]
    assert chain_spec.pattern.type == PatternType.CHAIN
    assert chain_spec.pattern.config.steps == minimal_routing_spec.pattern.config.routes["faq"].then

    # Verify result metadata
    assert result.pattern_type == PatternType.ROUTING
    assert result.execution_context["chosen_route"] == "faq"
    assert result.execution_context["router_agent"] == "router"


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@pytest.mark.asyncio
async def test_run_routing_invalid_route(mock_get_agent, minimal_routing_spec, mock_agent):
    """Test routing fails with clear error for invalid route name."""
    # Mock router returns invalid route - invoke_async returns string directly
    mock_agent.invoke_async = AsyncMock(return_value='{"route": "unknown_route"}')
    mock_get_agent.return_value = mock_agent

    with pytest.raises(RoutingExecutionError) as exc_info:
        await run_routing(minimal_routing_spec, variables={"query": "test"})

    error_msg = str(exc_info.value)
    assert "Invalid route 'unknown_route'" in error_msg
    assert "faq" in error_msg
    assert "research" in error_msg
    assert "escalate" in error_msg


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_retry_on_malformed_json(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test routing retries on malformed JSON and succeeds on 2nd attempt."""
    # First attempt returns malformed JSON, second returns valid JSON - invoke_async returns strings directly
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "This is not JSON",
            '{"route": "research"}',
        ]
    )
    mock_get_agent.return_value = mock_agent

    # Mock chain execution
    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "Research complete"
    chain_result.duration = 2.0
    chain_result.duration_seconds = 2.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    # Execute routing
    result = await run_routing(minimal_routing_spec, variables={"query": "test"})

    # Verify router was called twice
    assert mock_agent.invoke_async.call_count == 2

    # Verify result uses correct route
    assert result.execution_context["chosen_route"] == "research"


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@pytest.mark.asyncio
async def test_run_routing_exhausts_retries(mock_get_agent, minimal_routing_spec, mock_agent):
    """Test routing fails after exhausting retry attempts."""
    # All attempts return malformed JSON
    mock_agent.invoke_async.return_value = Mock(response="Not JSON at all")
    mock_get_agent.return_value = mock_agent

    with pytest.raises(RoutingExecutionError) as exc_info:
        await run_routing(minimal_routing_spec, variables={"query": "test"})

    assert "failed to produce valid JSON" in str(exc_info.value)
    # Default max_retries is 2, so 3 total attempts (initial + 2 retries)
    assert mock_agent.invoke_async.call_count == 3


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_multi_step_route(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test routing executes multi-step route correctly."""
    # Router selects 'research' route which has 2 steps - invoke_async returns string directly
    mock_agent.invoke_async = AsyncMock(return_value='{"route": "research"}')
    mock_get_agent.return_value = mock_agent

    # Mock chain execution
    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "Research and summary complete"
    chain_result.duration = 3.0
    chain_result.duration_seconds = 3.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    result = await run_routing(minimal_routing_spec, variables={"query": "test"})

    # Verify chain was called with 2-step route
    chain_spec = mock_run_chain.call_args[0][0]
    assert len(chain_spec.pattern.config.steps) == 2
    assert chain_spec.pattern.config.steps[0].agent == "researcher"
    assert chain_spec.pattern.config.steps[1].agent == "faq_handler"

    assert result.execution_context["chosen_route"] == "research"


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_template_context(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test router.chosen_route is available in route step templates."""
    # Mock router response - invoke_async returns string directly
    mock_agent.invoke_async = AsyncMock(return_value='{"route": "faq"}')
    mock_get_agent.return_value = mock_agent

    # Mock chain execution
    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "Done"
    chain_result.duration = 1.0
    chain_result.duration_seconds = 1.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    # Execute routing
    await run_routing(minimal_routing_spec, variables={"query": "test"})

    # Verify run_chain was called with router context
    route_variables = mock_run_chain.call_args[0][1]
    assert "router" in route_variables
    assert route_variables["router"]["chosen_route"] == "faq"
    assert route_variables["query"] == "test"


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_custom_max_retries(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test custom max_retries configuration is respected."""
    # Set custom max_retries
    minimal_routing_spec.pattern.config.router.max_retries = 1

    # All attempts return malformed JSON
    mock_agent.invoke_async.return_value = Mock(response="Not JSON")
    mock_get_agent.return_value = mock_agent

    with pytest.raises(RoutingExecutionError):
        await run_routing(minimal_routing_spec, variables={"query": "test"})

    # Should only try 2 times (initial + 1 retry)
    assert mock_agent.invoke_async.call_count == 2


@pytest.mark.asyncio
async def test_run_routing_no_router_config(minimal_routing_spec):
    """Test routing fails gracefully when router config is missing."""
    minimal_routing_spec.pattern.config.router = None

    with pytest.raises(RoutingExecutionError) as exc_info:
        await run_routing(minimal_routing_spec)

    assert "requires router configuration" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_routing_no_routes(minimal_routing_spec):
    """Test routing fails gracefully when routes are missing."""
    minimal_routing_spec.pattern.config.routes = None

    with pytest.raises(RoutingExecutionError) as exc_info:
        await run_routing(minimal_routing_spec)

    assert "requires at least one route" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_routing_empty_route(minimal_routing_spec):
    """Test routing fails when selected route has no steps."""
    # Create route with no steps
    minimal_routing_spec.pattern.config.routes["empty"] = Route(then=[])

    # Router selects empty route
    with patch("strands_cli.exec.utils.AgentCache.get_or_build_agent") as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value='{"route": "empty"}')
        mock_get_agent.return_value = mock_agent

        with pytest.raises(RoutingExecutionError) as exc_info:
            await run_routing(minimal_routing_spec, variables={"query": "test"})

        assert "has no steps to execute" in str(exc_info.value)


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_preserves_user_variables(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test user variables are passed through to route execution."""
    mock_agent.invoke_async = AsyncMock(return_value='{"route": "faq"}')
    mock_get_agent.return_value = mock_agent

    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "Done"
    chain_result.duration = 1.0
    chain_result.duration_seconds = 1.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    # Execute with custom variables
    await run_routing(minimal_routing_spec, variables={"query": "test", "user_id": "123"})

    # Verify variables passed to chain
    route_variables = mock_run_chain.call_args[0][1]
    assert route_variables["query"] == "test"
    assert route_variables["user_id"] == "123"
    assert route_variables["router"]["chosen_route"] == "faq"


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_router_response_in_artifacts(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test router.response is available for artifact rendering."""
    # Router returns decision with reasoning
    router_reasoning = "I chose the FAQ route because the query is straightforward and doesn't require deep research."
    mock_agent.invoke_async = AsyncMock(return_value=f'{{"route": "faq"}}\n\n{router_reasoning}')
    mock_get_agent.return_value = mock_agent

    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "FAQ answered"
    chain_result.duration = 1.0
    chain_result.duration_seconds = 1.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    # Execute routing
    result = await run_routing(minimal_routing_spec, variables={"query": "test"})
    result = await run_routing(
        minimal_routing_spec, variables={"query": "test", "user_id": "user123"}
    )

    # Verify router context includes response text for artifacts
    assert "router" in result.variables
    assert result.variables["router"]["chosen_route"] == "faq"
    assert result.variables["router"]["response"] != ""
    assert "faq" in result.variables["router"]["response"]

    # Also verify route_variables passed to chain included response
    route_variables = mock_run_chain.call_args[0][1]
    assert "router" in route_variables
    assert route_variables["router"]["response"] != ""


@patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
@patch("strands_cli.exec.routing.run_chain")
@pytest.mark.asyncio
async def test_run_routing_router_response_restored_from_session(
    mock_run_chain, mock_get_agent, minimal_routing_spec, mock_agent
):
    """Test router.response is correctly restored from session state on resume."""
    from datetime import UTC, datetime

    from strands_cli.session import SessionMetadata, SessionState, SessionStatus
    from strands_cli.session.file_repository import FileSessionRepository

    # Mock session state with router decision already saved
    router_reasoning = "Selected FAQ route based on simple query pattern."
    session_state = SessionState(
        metadata=SessionMetadata(
            session_id="test-session-123",
            workflow_name="test-routing",
            spec_hash="abc123",
            pattern_type="routing",
            status=SessionStatus.RUNNING,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        ),
        variables={},
        runtime_config={},
        pattern_state={
            "router_executed": True,
            "chosen_route": "faq",
            "router_decision": {
                "chosen_route": "faq",
                "response": router_reasoning,  # Router response saved in session
            },
            "route_state": {"current_step": 0, "step_history": []},
        },
        token_usage={},
        artifacts_written=[],
    )

    # Mock session repository
    session_repo = Mock(spec=FileSessionRepository)
    session_repo.save = AsyncMock()

    # Mock chain execution
    chain_result = Mock()
    chain_result.success = True
    chain_result.last_response = "FAQ answered"
    chain_result.duration = 1.0
    chain_result.duration_seconds = 1.0
    chain_result.pattern_type = PatternType.CHAIN
    chain_result.execution_context = {"steps": []}
    chain_result.variables = {}
    mock_run_chain.return_value = chain_result

    mock_agent.invoke_async = AsyncMock()  # Router should NOT be called on resume
    mock_get_agent.return_value = mock_agent

    # Execute routing with resume
    result = await run_routing(
        minimal_routing_spec,
        variables={"query": "test"},
        session_state=session_state,
        session_repo=session_repo,
    )

    # Verify router was NOT called (resumed from checkpoint)
    assert not mock_agent.invoke_async.called

    # Verify router context includes restored response
    assert "router" in result.variables
    assert result.variables["router"]["chosen_route"] == "faq"
    assert result.variables["router"]["response"] == router_reasoning

    # Verify route_variables passed to chain included restored response
    route_variables = mock_run_chain.call_args[0][1]
    assert "router" in route_variables
    assert route_variables["router"]["response"] == router_reasoning

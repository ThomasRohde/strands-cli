"""Tests for execution utilities module.

Tests shared utilities used across all executors including:
- Retry configuration extraction and validation
- Budget threshold checking and warnings
- Retry decorator creation
- Agent invocation with retry logic
- Token estimation
- AgentCache with worker_index isolation
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.utils import (
    TRANSIENT_ERRORS,
    AgentCache,
    ExecutionUtilsError,
    create_retry_decorator,
    estimate_tokens,
    get_retry_config,
    invoke_agent_with_retry,
)
from strands_cli.loader import load_spec
from strands_cli.types import Agent as AgentConfig
from strands_cli.types import ProviderType, Runtime, Spec

# --- Fixtures ---


@pytest.fixture
def minimal_spec(minimal_ollama_spec: Any) -> Spec:
    """Minimal spec with no failure_policy."""
    return load_spec(minimal_ollama_spec)


@pytest.fixture
def spec_with_retry_policy(minimal_ollama_spec: Any) -> Spec:
    """Spec with custom retry policy."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.failure_policy = {
        "retries": 5,
        "backoff": "exponential",
        "wait_min": 2,
        "wait_max": 120,
    }
    return spec


@pytest.fixture
def spec_with_invalid_retry_count(minimal_ollama_spec: Any) -> Spec:
    """Spec with invalid negative retry count."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.failure_policy = {
        "retries": -1,
    }
    return spec


@pytest.fixture
def spec_with_invalid_wait_times(minimal_ollama_spec: Any) -> Spec:
    """Spec with wait_min > wait_max."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.failure_policy = {
        "retries": 3,
        "backoff": "exponential",
        "wait_min": 100,
        "wait_max": 10,
    }
    return spec


@pytest.fixture
def spec_with_budget(minimal_ollama_spec: Any) -> Spec:
    """Spec with token budget configured."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.budgets = {"max_tokens": 1000}
    return spec


# --- Tests for get_retry_config ---


def test_get_retry_config_with_defaults(minimal_spec: Spec) -> None:
    """Test that defaults are used when no failure_policy is set."""
    max_attempts, wait_min, wait_max = get_retry_config(minimal_spec)

    assert max_attempts == 3
    assert wait_min == 1
    assert wait_max == 60


def test_get_retry_config_with_custom_policy(spec_with_retry_policy: Spec) -> None:
    """Test that custom retry policy values are extracted correctly."""
    max_attempts, wait_min, wait_max = get_retry_config(spec_with_retry_policy)

    assert max_attempts == 6  # retries + 1
    assert wait_min == 2
    assert wait_max == 120


def test_get_retry_config_with_zero_retries(minimal_ollama_spec: Any) -> None:
    """Test that zero retries is valid (1 attempt total)."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.failure_policy = {"retries": 0}

    max_attempts, wait_min, wait_max = get_retry_config(spec)

    assert max_attempts == 1
    assert wait_min == 1
    assert wait_max == 60


def test_get_retry_config_raises_on_negative_retries(spec_with_invalid_retry_count: Spec) -> None:
    """Test that negative retry count raises ExecutionUtilsError."""
    with pytest.raises(ExecutionUtilsError, match="retries must be >= 0"):
        get_retry_config(spec_with_invalid_retry_count)


def test_get_retry_config_raises_on_invalid_wait_times(
    spec_with_invalid_wait_times: Spec,
) -> None:
    """Test that wait_min > wait_max raises ExecutionUtilsError."""
    with pytest.raises(ExecutionUtilsError, match=r"wait_min.*must be <= wait_max"):
        get_retry_config(spec_with_invalid_wait_times)


def test_get_retry_config_with_partial_policy(minimal_ollama_spec: Any) -> None:
    """Test that defaults are used for missing policy fields."""
    spec = load_spec(minimal_ollama_spec)
    spec.runtime.failure_policy = {"retries": 2}  # No backoff or wait times

    max_attempts, wait_min, wait_max = get_retry_config(spec)

    assert max_attempts == 3
    assert wait_min == 1  # Default
    assert wait_max == 60  # Default


# Note: check_budget_threshold function removed in Phase 6.4 - replaced by BudgetEnforcerHook
# See tests/test_token_budgets.py for budget enforcement tests


# --- Tests for create_retry_decorator ---


def test_create_retry_decorator_returns_decorator() -> None:
    """Test that create_retry_decorator returns a retry decorator."""
    decorator = create_retry_decorator(max_attempts=3, wait_min=1, wait_max=60)

    # Decorator should be callable
    assert callable(decorator)


@pytest.mark.asyncio
async def test_create_retry_decorator_retries_transient_errors() -> None:
    """Test that retry decorator retries on transient errors."""
    decorator = create_retry_decorator(max_attempts=3, wait_min=0, wait_max=1)

    call_count = 0

    @decorator
    async def flaky_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("Transient timeout")
        return "success"

    result = await flaky_function()

    assert result == "success"
    assert call_count == 3  # Should retry twice, succeed on 3rd attempt


@pytest.mark.asyncio
async def test_create_retry_decorator_fails_after_max_attempts() -> None:
    """Test that retry decorator gives up after max_attempts."""
    decorator = create_retry_decorator(max_attempts=2, wait_min=0, wait_max=1)

    call_count = 0

    @decorator
    async def always_fails() -> str:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Always fails")

    with pytest.raises(ConnectionError, match="Always fails"):
        await always_fails()

    assert call_count == 2  # Should try twice and give up


@pytest.mark.asyncio
async def test_create_retry_decorator_does_not_retry_non_transient_errors() -> None:
    """Test that non-transient errors are not retried."""
    decorator = create_retry_decorator(max_attempts=3, wait_min=0, wait_max=1)

    call_count = 0

    @decorator
    async def raises_value_error() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("Not a transient error")

    with pytest.raises(ValueError, match="Not a transient error"):
        await raises_value_error()

    assert call_count == 1  # Should fail immediately, no retries


# --- Tests for invoke_agent_with_retry ---


@pytest.mark.asyncio
async def test_invoke_agent_with_retry_success(mocker: Any) -> None:
    """Test successful agent invocation without retries."""
    mock_agent = AsyncMock()
    mock_agent.invoke_async.return_value = "Agent response"

    # Mock capture_and_display_stdout
    mocker.patch("strands_cli.utils.capture_and_display_stdout", mocker.MagicMock())

    result = await invoke_agent_with_retry(
        agent=mock_agent,
        input_text="Test input",
        max_attempts=3,
        wait_min=0,
        wait_max=1,
    )

    assert result == "Agent response"
    mock_agent.invoke_async.assert_called_once_with("Test input")


@pytest.mark.asyncio
async def test_invoke_agent_with_retry_retries_on_timeout(mocker: Any) -> None:
    """Test that agent invocation retries on TimeoutError."""
    mock_agent = AsyncMock()
    call_count = 0

    async def flaky_invoke(input_text: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutError("Timeout")
        return "Success after retry"

    mock_agent.invoke_async = flaky_invoke

    # Mock capture_and_display_stdout
    mocker.patch("strands_cli.utils.capture_and_display_stdout", mocker.MagicMock())

    result = await invoke_agent_with_retry(
        agent=mock_agent,
        input_text="Test input",
        max_attempts=3,
        wait_min=0,
        wait_max=1,
    )

    assert result == "Success after retry"
    assert call_count == 2  # Should retry once


@pytest.mark.asyncio
async def test_invoke_agent_with_retry_fails_after_max_attempts(mocker: Any) -> None:
    """Test that agent invocation fails after max retry attempts."""
    mock_agent = AsyncMock()
    mock_agent.invoke_async.side_effect = ConnectionError("Persistent connection error")

    # Mock capture_and_display_stdout
    mocker.patch("strands_cli.utils.capture_and_display_stdout", mocker.MagicMock())

    with pytest.raises(ConnectionError, match="Persistent connection error"):
        await invoke_agent_with_retry(
            agent=mock_agent,
            input_text="Test input",
            max_attempts=2,
            wait_min=0,
            wait_max=1,
        )

    assert mock_agent.invoke_async.call_count == 2


@pytest.mark.asyncio
async def test_invoke_agent_with_retry_does_not_retry_non_transient(mocker: Any) -> None:
    """Test that non-transient errors fail immediately without retries."""
    mock_agent = AsyncMock()
    mock_agent.invoke_async.side_effect = ValueError("Invalid input")

    # Mock capture_and_display_stdout
    mocker.patch("strands_cli.utils.capture_and_display_stdout", mocker.MagicMock())

    with pytest.raises(ValueError, match="Invalid input"):
        await invoke_agent_with_retry(
            agent=mock_agent,
            input_text="Test input",
            max_attempts=3,
            wait_min=0,
            wait_max=1,
        )

    assert mock_agent.invoke_async.call_count == 1  # No retries


# --- Tests for estimate_tokens ---


def test_estimate_tokens_simple() -> None:
    """Test token estimation with simple text."""
    input_text = "Hello world"
    output_text = "Hi there friend"

    tokens = estimate_tokens(input_text, output_text)

    assert tokens == 5  # 2 (input) + 3 (output)


def test_estimate_tokens_empty_strings() -> None:
    """Test token estimation with empty strings."""
    tokens = estimate_tokens("", "")

    assert tokens == 0


def test_estimate_tokens_with_punctuation() -> None:
    """Test token estimation treats punctuation as separate words."""
    input_text = "What's your name?"
    output_text = "I am Claude."

    # Note: split() may not perfectly tokenize punctuation, but this is
    # just a heuristic estimation
    tokens = estimate_tokens(input_text, output_text)

    assert tokens > 0  # Should count some tokens


def test_estimate_tokens_multiline() -> None:
    """Test token estimation with multiline text."""
    input_text = "Line one\nLine two\nLine three"
    output_text = "Response line one\nResponse line two"

    tokens = estimate_tokens(input_text, output_text)

    assert tokens == 12  # 6 + newlines (input) + 4 + newlines (output)


# --- Integration Tests ---


def test_transient_errors_constant() -> None:
    """Test that TRANSIENT_ERRORS constant is properly defined."""
    assert TimeoutError in TRANSIENT_ERRORS
    assert ConnectionError in TRANSIENT_ERRORS
    assert isinstance(TRANSIENT_ERRORS, tuple)


def test_execution_utils_error_inheritance() -> None:
    """Test that ExecutionUtilsError is an Exception."""
    error = ExecutionUtilsError("Test error")

    assert isinstance(error, Exception)
    assert str(error) == "Test error"


# --- Tests for AgentCache ---


@pytest.mark.asyncio
async def test_agent_cache_basic_caching() -> None:
    """Test that AgentCache caches agents correctly."""
    spec = Spec(
        version=0,
        name="test-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent1": AgentConfig(prompt="Test prompt")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        cache = AgentCache()

        # First call should build agent
        agent1 = await cache.get_or_build_agent(
            spec,
            "agent1",
            spec.agents["agent1"],
            worker_index=None,
        )

        # Second call with same parameters should return cached agent
        agent2 = await cache.get_or_build_agent(
            spec,
            "agent1",
            spec.agents["agent1"],
            worker_index=None,
        )

        assert agent1 is agent2
        assert mock_build.call_count == 1  # Only built once

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_worker_index_creates_unique_cache_keys() -> None:
    """Test that different worker_index values create different cache keys."""
    spec = Spec(
        version=0,
        name="test-worker-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"worker": AgentConfig(prompt="Worker prompt")},
        pattern={"type": "orchestrator_workers", "config": {}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        # Create different mock agents for each worker
        mock_agent_0 = MagicMock()
        mock_agent_1 = MagicMock()
        mock_agent_2 = MagicMock()
        mock_build.side_effect = [mock_agent_0, mock_agent_1, mock_agent_2]

        cache = AgentCache()

        # Build agent for worker 0
        agent_0 = await cache.get_or_build_agent(
            spec,
            "worker",
            spec.agents["worker"],
            worker_index=0,
        )

        # Build agent for worker 1
        agent_1 = await cache.get_or_build_agent(
            spec,
            "worker",
            spec.agents["worker"],
            worker_index=1,
        )

        # Build agent for worker 2
        agent_2 = await cache.get_or_build_agent(
            spec,
            "worker",
            spec.agents["worker"],
            worker_index=2,
        )

        # All agents should be different
        assert agent_0 is not agent_1
        assert agent_1 is not agent_2
        assert agent_0 is not agent_2

        # build_agent should be called 3 times (no cache hits)
        assert mock_build.call_count == 3

        # Verify each agent is the correct mock
        assert agent_0 is mock_agent_0
        assert agent_1 is mock_agent_1
        assert agent_2 is mock_agent_2

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_same_worker_index_returns_cached_agent() -> None:
    """Test that same worker_index reuses cached agent."""
    spec = Spec(
        version=0,
        name="test-worker-cache-hit",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"worker": AgentConfig(prompt="Worker prompt")},
        pattern={"type": "orchestrator_workers", "config": {}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        cache = AgentCache()

        # Build agent for worker 0
        agent_first = await cache.get_or_build_agent(
            spec,
            "worker",
            spec.agents["worker"],
            worker_index=0,
        )

        # Request same worker_index again
        agent_second = await cache.get_or_build_agent(
            spec,
            "worker",
            spec.agents["worker"],
            worker_index=0,
        )

        # Should return same cached instance
        assert agent_first is agent_second
        assert mock_build.call_count == 1  # Only built once

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_none_worker_index_separate_from_indexed() -> None:
    """Test that worker_index=None creates separate cache key from indexed workers."""
    spec = Spec(
        version=0,
        name="test-none-vs-indexed",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Agent prompt")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent_none = MagicMock()
        mock_agent_0 = MagicMock()
        mock_build.side_effect = [mock_agent_none, mock_agent_0]

        cache = AgentCache()

        # Build agent with worker_index=None
        agent_none = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
        )

        # Build agent with worker_index=0
        agent_0 = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=0,
        )

        # Should be different agents (different cache keys)
        assert agent_none is not agent_0
        assert mock_build.call_count == 2

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_close_cleanup() -> None:
    """Test that cache.close() cleans up resources."""
    spec = Spec(
        version=0,
        name="test-cleanup",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Test")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        cache = AgentCache()

        # Build some agents
        await cache.get_or_build_agent(spec, "agent", spec.agents["agent"], worker_index=None)
        await cache.get_or_build_agent(spec, "agent", spec.agents["agent"], worker_index=0)

        # Verify cache has entries
        assert len(cache._agents) == 2

        # Close cache
        await cache.close()

        # Verify cache is cleared
        assert len(cache._agents) == 0


@pytest.mark.asyncio
async def test_agent_cache_notes_not_in_key() -> None:
    """Test that agents with different notes are cached together (notes injected at invocation time)."""
    spec = Spec(
        version=0,
        name="test-notes-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Test")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        cache = AgentCache()

        # Build agent with notes "Step 1 notes"
        agent1 = await cache.get_or_build_agent(
            spec, "agent", spec.agents["agent"], injected_notes="Step 1 notes", worker_index=None
        )
        assert mock_build.call_count == 1

        # Build agent with different notes "Step 2 notes"
        # Should reuse cached agent (notes don't affect cache key)
        agent2 = await cache.get_or_build_agent(
            spec, "agent", spec.agents["agent"], injected_notes="Step 2 notes", worker_index=None
        )
        assert mock_build.call_count == 1  # Still 1 - agent reused
        assert agent1 is agent2  # Same agent instance

        # Build agent with no notes
        # Should still reuse cached agent
        agent3 = await cache.get_or_build_agent(
            spec, "agent", spec.agents["agent"], injected_notes=None, worker_index=None
        )
        assert mock_build.call_count == 1  # Still 1 - agent reused
        assert agent1 is agent3  # Same agent instance

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_session_manager_creates_unique_cache_keys() -> None:
    """Test that agents with different session managers have separate cache entries (Phase 2)."""
    spec = Spec(
        version=0,
        name="test-session-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Test")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    # Mock session managers with different session_ids
    session_manager_1 = MagicMock()
    session_manager_1.session_id = "session-123_agent"

    session_manager_2 = MagicMock()
    session_manager_2.session_id = "session-456_agent"

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent_1 = MagicMock()
        mock_agent_2 = MagicMock()
        mock_build.side_effect = [mock_agent_1, mock_agent_2]

        cache = AgentCache()

        # Build agent with session_manager_1
        agent1 = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=session_manager_1,
        )
        assert mock_build.call_count == 1
        assert agent1 is mock_agent_1

        # Build agent with session_manager_2 (different session_id)
        # Should create a NEW cache entry
        agent2 = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=session_manager_2,
        )
        assert mock_build.call_count == 2  # Two separate builds
        assert agent2 is mock_agent_2
        assert agent1 is not agent2  # Different agent instances

        # Verify both are cached (2 entries)
        assert len(cache._agents) == 2

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_same_session_manager_returns_cached_agent() -> None:
    """Test that agents with the same session manager are cached together (Phase 2)."""
    spec = Spec(
        version=0,
        name="test-session-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Test")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    # Mock session manager
    session_manager = MagicMock()
    session_manager.session_id = "session-123_agent"

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        cache = AgentCache()

        # Build agent with session_manager
        agent1 = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=session_manager,
        )
        assert mock_build.call_count == 1
        assert agent1 is mock_agent

        # Build agent with same session_manager
        # Should reuse cached agent
        agent2 = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=session_manager,
        )
        assert mock_build.call_count == 1  # Still 1 - agent reused
        assert agent1 is agent2  # Same agent instance

        # Verify only one cache entry
        assert len(cache._agents) == 1

        await cache.close()


@pytest.mark.asyncio
async def test_agent_cache_none_session_manager_separate_from_session() -> None:
    """Test that agents with session_manager=None are separate from those with session (Phase 2)."""
    spec = Spec(
        version=0,
        name="test-session-cache",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"agent": AgentConfig(prompt="Test")},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    # Mock session manager
    session_manager = MagicMock()
    session_manager.session_id = "session-123_agent"

    with patch("strands_cli.exec.utils.build_agent") as mock_build:
        mock_agent_fresh = MagicMock()
        mock_agent_session = MagicMock()
        mock_build.side_effect = [mock_agent_fresh, mock_agent_session]

        cache = AgentCache()

        # Build agent without session (fresh execution)
        agent_fresh = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=None,
        )
        assert mock_build.call_count == 1
        assert agent_fresh is mock_agent_fresh

        # Build agent with session manager (resume execution)
        # Should create a NEW cache entry
        agent_session = await cache.get_or_build_agent(
            spec,
            "agent",
            spec.agents["agent"],
            worker_index=None,
            session_manager=session_manager,
        )
        assert mock_build.call_count == 2  # Two separate builds
        assert agent_session is mock_agent_session
        assert agent_fresh is not agent_session  # Different instances

        # Verify both are cached (2 entries: one for None, one for session_id)
        assert len(cache._agents) == 2

        await cache.close()

"""Tests for AgentCache (Phase 2 performance optimization).

Verifies agent caching behavior:
- Cache hits/misses for repeated agent configurations
- Tool deduplication across agents
- Resource cleanup on cache.close()
- Cache key correctness (agent_id, frozenset(tool_ids))
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from strands_cli.exec.utils import AgentCache
from strands_cli.loader import load_spec
from strands_cli.types import Spec


@pytest.fixture
def minimal_spec(minimal_ollama_spec: Any) -> Spec:
    """Create minimal spec for agent building."""
    return load_spec(minimal_ollama_spec)


@pytest.fixture
def mock_agent() -> Mock:
    """Create mock Strands Agent."""
    agent = Mock()
    agent.tools = []
    return agent


@pytest.mark.asyncio
async def test_agent_cache_initialization() -> None:
    """Test AgentCache initializes with empty caches."""
    cache = AgentCache()

    assert len(cache._agents) == 0
    assert len(cache._http_executors) == 0


@pytest.mark.asyncio
async def test_agent_cache_miss_builds_new_agent(minimal_spec: Spec, mock_agent: Mock) -> None:
    """Test cache miss builds new agent and caches it."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent) as mock_build:
        agent = await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Verify build_agent was called (with agent_cache in Phase 9, session_manager in Phase 2)
        mock_build.assert_called_once_with(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=None,
            conversation_manager=None,
            hooks=None,
            injected_notes=None,
            agent_cache=cache,  # Phase 9: added for MCP client tracking
            session_manager=None,  # Phase 2: added for session restoration
        )

        # Verify returned agent
        assert agent is mock_agent

        # Verify agent was cached (agent has no tools, so empty frozenset, no CM, no worker_index)
        cache_key = (agent_id, frozenset(), None, None)
        assert cache_key in cache._agents
        assert cache._agents[cache_key] is mock_agent


@pytest.mark.asyncio
async def test_agent_cache_hit_returns_cached_agent(minimal_spec: Spec, mock_agent: Mock) -> None:
    """Test cache hit returns cached agent without rebuilding."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent) as mock_build:
        # First call - cache miss
        agent1 = await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Second call - cache hit
        agent2 = await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Verify build_agent called only once (first time)
        assert mock_build.call_count == 1

        # Verify both calls returned same agent instance
        assert agent1 is agent2
        assert agent1 is mock_agent


@pytest.mark.asyncio
async def test_agent_cache_different_tools_creates_separate_entry(
    minimal_spec: Spec,
) -> None:
    """Test different tool configurations create separate cache entries."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    mock_agent1 = Mock()
    mock_agent1.tools = []
    mock_agent2 = Mock()
    mock_agent2.tools = []

    with patch(
        "strands_cli.exec.utils.build_agent", side_effect=[mock_agent1, mock_agent2]
    ) as mock_build:
        # Request agent with no tool overrides (default)
        agent1 = await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Request agent with overridden tools
        agent2 = await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["tool-c"],
        )

        # Verify build_agent called twice (different cache keys)
        assert mock_build.call_count == 2

        # Verify different agents returned
        assert agent1 is mock_agent1
        assert agent2 is mock_agent2

        # Verify two cache entries
        assert len(cache._agents) == 2


@pytest.mark.asyncio
async def test_agent_cache_no_tools_uses_empty_frozenset(
    minimal_spec: Spec, mock_agent: Mock
) -> None:
    """Test agent with no tools uses empty frozenset as cache key."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent):
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Verify cache key uses empty frozenset for no tools, None for CM, None for worker_index
        cache_key = (agent_id, frozenset(), None, None)
        assert cache_key in cache._agents


@pytest.mark.asyncio
async def test_agent_cache_tracks_http_executors(minimal_spec: Spec) -> None:
    """Test cache tracks HTTP executors from agent tools for cleanup."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    # Create mock agent with HTTP executor tool (module-based)
    mock_http_executor = Mock()  # Generic mock for HTTP executor
    mock_http_executor.TOOL_SPEC = {"name": "http-exec-1"}
    mock_http_executor._http_client = Mock()
    mock_http_executor._http_config = Mock()
    mock_http_executor._http_config.id = "http-exec-1"

    mock_agent = Mock()
    mock_agent.tools = [mock_http_executor]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent):
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Verify HTTP executor was tracked
        assert "http-exec-1" in cache._http_executors
        assert cache._http_executors["http-exec-1"] is mock_http_executor


@pytest.mark.asyncio
async def test_agent_cache_deduplicates_http_executors(minimal_spec: Spec) -> None:
    """Test cache deduplicates HTTP executors across multiple agents."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    # Create shared HTTP executor (module-based)
    mock_http_executor = Mock()  # Generic mock for HTTP executor
    mock_http_executor.TOOL_SPEC = {"name": "http-exec-shared"}
    mock_http_executor._http_client = Mock()
    mock_http_executor._http_config = Mock()
    mock_http_executor._http_config.id = "http-exec-shared"

    mock_agent1 = Mock()
    mock_agent1.tools = [mock_http_executor]

    mock_agent2 = Mock()
    mock_agent2.tools = [mock_http_executor]

    with patch("strands_cli.exec.utils.build_agent", side_effect=[mock_agent1, mock_agent2]):
        # Build same agent twice with different tool overrides
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["some-tool"],
        )

        # Verify only one HTTP executor tracked (deduplicated by ID)
        assert len(cache._http_executors) == 1
        assert "http-exec-shared" in cache._http_executors


@pytest.mark.asyncio
async def test_agent_cache_close_cleans_up_http_executors(minimal_spec: Spec) -> None:
    """Test cache.close() calls close() on all HTTP executors."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    # Create mock HTTP executors (module-based)
    mock_exec1 = Mock()  # Generic mock for HTTP executor 1
    mock_exec1.TOOL_SPEC = {"name": "http-1"}
    mock_exec1._http_client = Mock()
    mock_exec1._http_client.close = Mock()
    mock_exec1._http_config = Mock()
    mock_exec1._http_config.id = "http-1"

    mock_exec2 = Mock()  # Generic mock for HTTP executor 2
    mock_exec2.TOOL_SPEC = {"name": "http-2"}
    mock_exec2._http_client = Mock()
    mock_exec2._http_client.close = Mock()
    mock_exec2._http_config = Mock()
    mock_exec2._http_config.id = "http-2"

    mock_agent1 = Mock()
    mock_agent1.tools = [mock_exec1]

    mock_agent2 = Mock()
    mock_agent2.tools = [mock_exec2]

    with patch("strands_cli.exec.utils.build_agent", side_effect=[mock_agent1, mock_agent2]):
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["tool-a"],
        )

        # Close the cache
        await cache.close()

        # Verify close() called on both executors' _http_client
        mock_exec1._http_client.close.assert_called_once()
        mock_exec2._http_client.close.assert_called_once()

        # Verify caches cleared
        assert len(cache._agents) == 0
        assert len(cache._http_executors) == 0


@pytest.mark.asyncio
async def test_agent_cache_close_handles_cleanup_errors(minimal_spec: Spec) -> None:
    """Test cache.close() handles errors during executor cleanup gracefully."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    # Create mock HTTP executor that raises on close (module-based)
    mock_exec = Mock()  # Generic mock for HTTP executor
    mock_exec.TOOL_SPEC = {"name": "http-failing"}
    mock_exec._http_client = Mock()
    mock_exec._http_client.close = Mock(side_effect=RuntimeError("Cleanup failed"))
    mock_exec._http_config = Mock()
    mock_exec._http_config.id = "http-failing"

    mock_agent = Mock()
    mock_agent.tools = [mock_exec]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent):
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
        )

        # Close should not raise even if executor cleanup fails
        await cache.close()

        # Verify caches still cleared
        assert len(cache._agents) == 0
        assert len(cache._http_executors) == 0


@pytest.mark.asyncio
async def test_agent_cache_tool_override_changes_cache_key(
    minimal_spec: Spec,
) -> None:
    """Test tool_overrides parameter affects cache key."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    mock_agent1 = Mock()
    mock_agent1.tools = []
    mock_agent2 = Mock()
    mock_agent2.tools = []

    with patch(
        "strands_cli.exec.utils.build_agent", side_effect=[mock_agent1, mock_agent2]
    ) as mock_build:
        # Request with no overrides (uses agent_config.tools which is None)
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=None,
        )

        # Request with actual tools (different from None)
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["tool-a"],
        )

        # Verify build_agent called twice (different cache keys)
        assert mock_build.call_count == 2

        # Verify two cache entries
        assert len(cache._agents) == 2


@pytest.mark.asyncio
async def test_agent_cache_same_tools_different_order_same_key(
    minimal_spec: Spec, mock_agent: Mock
) -> None:
    """Test that tool lists with same items but different order produce cache hit."""
    cache = AgentCache()

    agent_id = "simple"
    agent_config = minimal_spec.agents[agent_id]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent) as mock_build:
        # Request with tools in one order
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["tool-b", "tool-a"],
        )

        # Request with tools in different order
        await cache.get_or_build_agent(
            minimal_spec,
            agent_id,
            agent_config,
            tool_overrides=["tool-a", "tool-b"],
        )

        # Verify build_agent called only once (frozenset makes order irrelevant)
        assert mock_build.call_count == 1

        # Verify only one cache entry
        assert len(cache._agents) == 1

"""Tests for execution hooks (Phase 6).

Verifies hook behavior:
- ProactiveCompactionHook token monitoring and compaction triggering
- NotesAppenderHook note writing and extraction
- Hook integration with agent lifecycle
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from strands_cli.exec.hooks import NotesAppenderHook, ProactiveCompactionHook
from strands_cli.tools.notes_manager import NotesManager


@pytest.mark.asyncio
async def test_proactive_compaction_hook_triggers_at_threshold(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook triggers compaction when threshold exceeded."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold)

    # Create mock agent with conversation manager and usage
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.messages = [{"role": "user", "content": "test"}]
    mock_agent.accumulated_usage = {"totalTokens": 1500}  # Exceeds threshold

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify compaction was triggered
    mock_agent.conversation_manager.apply_management.assert_called_once()
    assert hook.compacted is True


@pytest.mark.asyncio
async def test_proactive_compaction_hook_skips_below_threshold(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook does not trigger when below threshold."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold)

    # Create mock agent with usage below threshold
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.messages = [{"role": "user", "content": "test"}]
    mock_agent.accumulated_usage = {"totalTokens": 500}  # Below threshold

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify compaction was NOT triggered
    mock_agent.conversation_manager.apply_management.assert_not_called()
    assert hook.compacted is False


@pytest.mark.asyncio
async def test_proactive_compaction_hook_only_fires_once(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook only triggers once (single-fire behavior)."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold)

    # Create mock agent
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.messages = [{"role": "user", "content": "test"}]
    mock_agent.accumulated_usage = {"totalTokens": 1500}

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook twice
    hook._check_and_compact(mock_event)
    hook._check_and_compact(mock_event)

    # Verify compaction only called once
    assert mock_agent.conversation_manager.apply_management.call_count == 1
    assert hook.compacted is True


@pytest.mark.asyncio
async def test_proactive_compaction_hook_handles_missing_usage(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook handles agents without usage metrics gracefully."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold)

    # Create mock agent without accumulated_usage
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    del mock_agent.accumulated_usage  # No usage metrics

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Should not raise exception
    hook._check_and_compact(mock_event)

    # Verify no compaction triggered
    assert hook.compacted is False


@pytest.mark.asyncio
async def test_proactive_compaction_hook_uses_token_counter_fallback(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook falls back to TokenCounter when provider metrics missing."""
    threshold = 1000
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id=model_id)

    # Create mock agent without accumulated_usage (triggers fallback)
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.accumulated_usage = None  # No provider metrics

    # Create messages that would exceed threshold when counted
    # Each message has ~4 token overhead + content
    # "Hello world" ≈ 2-3 tokens, so ~200 messages should exceed 1000 tokens
    mock_agent.messages = [{"role": "user", "content": "Hello world " * 50} for _ in range(20)]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify compaction was triggered via TokenCounter fallback
    mock_agent.conversation_manager.apply_management.assert_called_once()
    assert hook.compacted is True


@pytest.mark.asyncio
async def test_proactive_compaction_hook_token_counter_below_threshold(tmp_path: Any) -> None:
    """Test TokenCounter fallback does not trigger when below threshold."""
    threshold = 10000  # High threshold
    model_id = "gpt-4o-mini"
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id=model_id)

    # Create mock agent with minimal messages
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.accumulated_usage = {"totalTokens": 0}  # Stale metrics
    mock_agent.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify compaction was NOT triggered
    mock_agent.conversation_manager.apply_management.assert_not_called()
    assert hook.compacted is False


@pytest.mark.asyncio
async def test_proactive_compaction_hook_prefers_provider_metrics(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook prefers provider metrics over TokenCounter."""
    threshold = 1000
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id=model_id)

    # Create mock agent with both provider metrics and messages
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()

    # Provider metrics show below threshold
    mock_agent.accumulated_usage = {"totalTokens": 500}

    # Messages would show above threshold if counted (but should not be used)
    mock_agent.messages = [{"role": "user", "content": "Hello world " * 50} for _ in range(20)]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify compaction was NOT triggered (using provider metrics, not TokenCounter)
    mock_agent.conversation_manager.apply_management.assert_not_called()
    assert hook.compacted is False


@pytest.mark.asyncio
async def test_proactive_compaction_hook_without_token_counter_or_metrics(tmp_path: Any) -> None:
    """Test ProactiveCompactionHook skips when no TokenCounter and no provider metrics."""
    threshold = 1000
    # No model_id provided, so no TokenCounter created
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id=None)

    # Create mock agent without accumulated_usage
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.accumulated_usage = None
    mock_agent.messages = [{"role": "user", "content": "Hello world " * 50} for _ in range(20)]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook callback
    hook._check_and_compact(mock_event)

    # Verify no compaction triggered (no metrics and no counter)
    mock_agent.conversation_manager.apply_management.assert_not_called()
    assert hook.compacted is False


@pytest.mark.asyncio
async def test_notes_appender_hook_writes_note(tmp_path: Any) -> None:
    """Test NotesAppenderHook writes note after invocation."""
    notes_file = tmp_path / "test-notes.md"
    notes_manager = NotesManager(str(notes_file))
    step_counter = [0]
    agent_tools = {"test-agent": ["tool-a", "tool-b"]}

    hook = NotesAppenderHook(notes_manager, step_counter, agent_tools)

    # Create mock agent with messages
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.messages = [
        {"role": "user", "content": "What is the weather?"},
        {"role": "assistant", "content": "It's sunny!"},
    ]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook
    hook._append_note(mock_event)

    # Verify step counter incremented
    assert step_counter[0] == 1

    # Verify note file exists
    assert notes_file.exists()

    # Verify note content
    content = notes_file.read_text()
    assert "test-agent" in content
    assert "Step 1" in content
    assert "tool-a, tool-b" in content


@pytest.mark.asyncio
async def test_notes_appender_hook_handles_write_errors(tmp_path: Any) -> None:
    """Test NotesAppenderHook handles write errors gracefully (no raise)."""
    # Create notes manager with invalid path
    notes_manager = NotesManager("/invalid/path/notes.md")
    step_counter = [0]
    agent_tools = {}

    hook = NotesAppenderHook(notes_manager, step_counter, agent_tools)

    # Create mock agent
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.messages = []

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Should not raise exception (error policy: log and continue)
    hook._append_note(mock_event)

    # Step counter should still increment
    assert step_counter[0] == 1


@pytest.mark.asyncio
async def test_notes_appender_hook_extracts_input_from_messages(tmp_path: Any) -> None:
    """Test NotesAppenderHook correctly extracts input from agent messages."""
    notes_file = tmp_path / "test-notes.md"
    notes_manager = NotesManager(str(notes_file))
    step_counter = [0]

    hook = NotesAppenderHook(notes_manager, step_counter, {})

    # Create mock agent with complex message history
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.messages = [
        {"role": "user", "content": [{"text": "Analyze this data"}]},
        {"role": "assistant", "content": [{"text": "Processing..."}]},
        {"role": "tool", "content": [{"toolResult": {}}]},
        {"role": "user", "content": [{"text": "What is the result?"}]},
    ]

    # Create mock event
    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger hook
    hook._append_note(mock_event)

    # Verify note content includes latest user input
    content = notes_file.read_text()
    assert "What is the result?" in content


@pytest.mark.asyncio
async def test_notes_manager_get_last_n_for_injection_alias(tmp_path: Any) -> None:
    """Test get_last_n_for_injection is an alias for read_last_n."""
    notes_file = tmp_path / "test-notes.md"
    manager = NotesManager(str(notes_file))

    # Write some notes
    manager.append_entry(
        timestamp="2025-11-08T00:00:00Z",
        agent_name="agent-1",
        step_index=1,
        input_summary="Input 1",
        tools_used=["tool-a"],
        outcome="Outcome 1",
    )
    manager.append_entry(
        timestamp="2025-11-08T00:01:00Z",
        agent_name="agent-2",
        step_index=2,
        input_summary="Input 2",
        tools_used=None,
        outcome="Outcome 2",
    )

    # Test both methods return same result
    result_read = manager.read_last_n(1)
    result_inject = manager.get_last_n_for_injection(1)

    assert result_read == result_inject
    assert "agent-2" in result_inject
    assert "Step 2" in result_inject


@pytest.mark.asyncio
async def test_agent_cache_with_notes_hash(tmp_path: Any) -> None:
    """Test AgentCache uses notes hash in cache key."""
    from strands_cli.exec.utils import AgentCache
    from strands_cli.loader import load_spec

    # Load minimal spec
    spec_path = tmp_path / "minimal.yaml"
    spec_path.write_text(
        """
version: 0
name: test-spec
runtime:
  provider: ollama
  model_id: test-model
agents:
  test-agent:
    prompt: Test prompt
pattern:
  type: chain
  config:
    steps:
      - agent: test-agent
        input: Test input
"""
    )

    spec = load_spec(str(spec_path))
    cache = AgentCache()

    mock_agent = Mock()
    mock_agent.tools = []

    agent_config = spec.agents["test-agent"]

    with patch("strands_cli.exec.utils.build_agent", return_value=mock_agent) as mock_build:
        # Build agent with notes
        agent1 = await cache.get_or_build_agent(
            spec, "test-agent", agent_config, injected_notes="Note 1"
        )

        # Build agent with same notes (should be cache hit)
        agent2 = await cache.get_or_build_agent(
            spec, "test-agent", agent_config, injected_notes="Note 1"
        )

        # Build agent with different notes (should ALSO be cache hit - notes don't affect cache key)
        agent3 = await cache.get_or_build_agent(
            spec, "test-agent", agent_config, injected_notes="Note 2"
        )

        # Verify build_agent called only once (notes don't affect cache key)
        assert mock_build.call_count == 1

        # Verify cache behavior - all agents are the same instance
        assert agent1 is agent2
        assert agent1 is agent3  # Different notes but same cached agent
        assert agent1 is mock_agent

        # Verify cache has 1 entry (notes don't create separate cache entries)
        assert len(cache._agents) == 1

    await cache.close()

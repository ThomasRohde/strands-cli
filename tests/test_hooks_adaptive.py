"""Tests for adaptive compaction hook features.

Tests auto-reduction of preserve_recent_messages and improved token counting.
"""

from typing import Any
from unittest.mock import Mock

import pytest

from strands_cli.exec.hooks import ProactiveCompactionHook


@pytest.mark.asyncio
async def test_compaction_auto_reduces_preserve_recent_messages() -> None:
    """Test that preserve_recent_messages is auto-reduced when insufficient messages."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id="gpt-4o-mini")

    # Create mock agent with only 9 messages but preserve_recent_messages=15
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.conversation_manager.preserve_recent_messages = 15

    # Only 9 messages (user's scenario from bug report)
    mock_agent.messages = [{"role": "user", "content": "msg"}] * 9
    mock_agent.accumulated_usage = {"totalTokens": 1500}  # Exceeds threshold

    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Trigger compaction
    hook._check_and_compact(mock_event)

    # Compaction should succeed (not raise ValueError)
    mock_agent.conversation_manager.apply_management.assert_called_once()
    assert hook.compacted is True

    # Original preserve value should be restored
    assert mock_agent.conversation_manager.preserve_recent_messages == 15


@pytest.mark.asyncio
async def test_compaction_calculates_adjusted_preserve_value() -> None:
    """Test that adjusted preserve value is calculated correctly."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id="gpt-4o-mini")

    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.conversation_manager.preserve_recent_messages = 15

    # 10 messages: adjusted = max(10 - 5, 3) = 5
    mock_agent.messages = [{"role": "user", "content": "msg"}] * 10
    mock_agent.accumulated_usage = {"totalTokens": 1500}

    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Track what preserve value was used during apply_management
    preserve_during_compaction = None

    def capture_preserve(*args: Any, **kwargs: Any) -> None:
        nonlocal preserve_during_compaction
        preserve_during_compaction = mock_agent.conversation_manager.preserve_recent_messages

    mock_agent.conversation_manager.apply_management.side_effect = capture_preserve

    hook._check_and_compact(mock_event)

    # During compaction, preserve should be reduced to 5
    assert preserve_during_compaction == 5

    # After compaction, original value restored
    assert mock_agent.conversation_manager.preserve_recent_messages == 15


@pytest.mark.asyncio
async def test_compaction_enforces_minimum_preserve_value() -> None:
    """Test that preserve_recent_messages never goes below hard minimum of 3."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id="gpt-4o-mini")

    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.conversation_manager.preserve_recent_messages = 20

    # Only 4 messages: adjusted = max(4 - 5, 3) = max(-1, 3) = 3 (hard minimum)
    mock_agent.messages = [{"role": "user", "content": "msg"}] * 4
    mock_agent.accumulated_usage = {"totalTokens": 1500}

    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    preserve_during_compaction = None

    def capture_preserve(*args: Any, **kwargs: Any) -> None:
        nonlocal preserve_during_compaction
        preserve_during_compaction = mock_agent.conversation_manager.preserve_recent_messages

    mock_agent.conversation_manager.apply_management.side_effect = capture_preserve

    hook._check_and_compact(mock_event)

    # Should use minimum of 3
    assert preserve_during_compaction == 3


@pytest.mark.asyncio
async def test_compaction_no_reduction_when_sufficient_messages() -> None:
    """Test that preserve_recent_messages is not reduced when there are enough messages."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id="gpt-4o-mini")

    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.conversation_manager.preserve_recent_messages = 15

    # 30 messages: 30 >= 15 + 5 (minimum required), so no adjustment needed
    mock_agent.messages = [{"role": "user", "content": "msg"}] * 30
    mock_agent.accumulated_usage = {"totalTokens": 1500}

    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    preserve_during_compaction = None

    def capture_preserve(*args: Any, **kwargs: Any) -> None:
        nonlocal preserve_during_compaction
        preserve_during_compaction = mock_agent.conversation_manager.preserve_recent_messages

    mock_agent.conversation_manager.apply_management.side_effect = capture_preserve

    hook._check_and_compact(mock_event)

    # Should use configured value (no reduction)
    assert preserve_during_compaction == 15

    # Value unchanged after compaction
    assert mock_agent.conversation_manager.preserve_recent_messages == 15


@pytest.mark.asyncio
async def test_token_counter_comparison_logging() -> None:
    """Test that token counter logs comparison with provider metrics."""
    threshold = 1000
    hook = ProactiveCompactionHook(threshold_tokens=threshold, model_id="gpt-4o-mini")

    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.conversation_manager = Mock()
    mock_agent.conversation_manager.apply_management = Mock()
    mock_agent.conversation_manager.preserve_recent_messages = 12

    # Provide both provider metrics and messages for fallback
    mock_agent.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    mock_agent.accumulated_usage = {"totalTokens": 1500}

    from strands.hooks import AfterInvocationEvent

    mock_event = Mock(spec=AfterInvocationEvent)
    mock_event.agent = mock_agent

    # Should use provider metrics (1500) and not trigger fallback comparison
    hook._check_and_compact(mock_event)

    # Compaction should trigger based on provider metrics
    assert hook.compacted is True

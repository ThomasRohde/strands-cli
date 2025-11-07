"""Tests for context compaction (Feature 6.1).

Tests for intelligent context management using SummarizingConversationManager
with proactive triggering via custom hooks.

Coverage:
- Runtime/context_manager.py: Factory function and summarization agent creation
- Exec/hooks.py: ProactiveCompactionHook trigger logic and hook registration
- Integration: AgentCache with different conversation managers, hook event flow
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.hooks import AfterInvocationEvent, HookRegistry

from strands_cli.exec.hooks import ProactiveCompactionHook
from strands_cli.runtime.context_manager import create_from_policy
from strands_cli.types import Compaction, ContextPolicy, Runtime


class TestCreateFromPolicy:
    """Tests for create_from_policy() factory function."""

    def test_returns_none_when_compaction_disabled(self) -> None:
        """Test that None is returned when compaction is disabled."""
        from strands_cli.types import Spec, Agent, PatternType

        policy = ContextPolicy(compaction=Compaction(enabled=False))
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider="ollama", host="http://localhost:11434"),
            agents={"a": Agent(prompt="test")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )
        result = create_from_policy(policy, spec)

        assert result is None

    def test_returns_none_when_no_compaction_config(self) -> None:
        """Test that None is returned when compaction config is missing."""
        from strands_cli.types import Spec, Agent, PatternType

        policy = ContextPolicy()  # No compaction field
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider="ollama", host="http://localhost:11434"),
            agents={"a": Agent(prompt="test")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )
        result = create_from_policy(policy, spec)

        assert result is None

    @patch("strands_cli.runtime.context_manager._create_summarization_agent")
    def test_creates_summarizing_manager_with_default_model(
        self, mock_create_agent: MagicMock
    ) -> None:
        """Test SummarizingConversationManager created with default settings."""
        from strands_cli.types import Spec, Agent, PatternType

        # Don't need to mock since no custom model specified
        policy = ContextPolicy(
            compaction=Compaction(
                enabled=True,
                when_tokens_over=2000,
                summary_ratio=0.3,
                preserve_recent_messages=5,
            )
        )
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(
                provider="bedrock",
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                region="us-east-1",
            ),
            agents={"a": Agent(prompt="test")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )

        result = create_from_policy(policy, spec)

        assert isinstance(result, SummarizingConversationManager)
        # With no custom model, _create_summarization_agent should NOT be called
        mock_create_agent.assert_not_called()

    @patch("strands_cli.runtime.context_manager._create_summarization_agent")
    def test_creates_summarizing_manager_with_custom_model(
        self, mock_create_agent: MagicMock
    ) -> None:
        """Test SummarizingConversationManager created with custom summarization model."""
        from strands_cli.types import Spec, Agent, PatternType

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        policy = ContextPolicy(
            compaction=Compaction(
                enabled=True,
                when_tokens_over=1500,
                summary_ratio=0.2,
                preserve_recent_messages=3,
                summarization_model="anthropic.claude-3-haiku-20240307-v1:0",
            )
        )
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(
                provider="bedrock",
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                region="us-east-1",
            ),
            agents={"a": Agent(prompt="test")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )

        result = create_from_policy(policy, spec)

        assert isinstance(result, SummarizingConversationManager)
        # Verify summarization agent was created with custom model (model_id first, spec second)
        mock_create_agent.assert_called_once_with("anthropic.claude-3-haiku-20240307-v1:0", spec)

    @patch("strands_cli.runtime.context_manager.create_model")
    def test_summarization_agent_uses_model_pooling(self, mock_create_model: MagicMock) -> None:
        """Test that summarization agent creation uses model pooling."""
        from strands_cli.types import Spec, Agent, PatternType

        # Note: Without custom summarization_model, create_model won't be called for summarization
        # This test would need a custom model to trigger the pooling path
        policy = ContextPolicy(
            compaction=Compaction(
                enabled=True,
                summarization_model="gpt-4o-mini",  # Custom model triggers pooling
            )
        )
        spec = Spec(
            version=0,
            name="test",
            runtime=Runtime(provider="ollama", host="http://localhost:11434", model_id="llama2"),
            agents={"a": Agent(prompt="test")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )

        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        result = create_from_policy(policy, spec)

        assert isinstance(result, SummarizingConversationManager)
        # Verify create_model was called for custom summarization model (model pooling)
        assert mock_create_model.call_count >= 1


class TestProactiveCompactionHook:
    """Tests for ProactiveCompactionHook trigger logic."""

    @pytest.fixture
    def mock_conversation_manager(self) -> MagicMock:
        """Mock SummarizingConversationManager."""
        manager = MagicMock(spec=SummarizingConversationManager)
        manager.summarize_async = AsyncMock()
        manager.history = [{"role": "user", "content": "msg"}] * 10  # 10 messages
        return manager

    @pytest.fixture
    def mock_config(self) -> Compaction:
        """Default compaction config."""
        return Compaction(
            enabled=True,
            when_tokens_over=1000,
            summary_ratio=0.3,
            preserve_recent_messages=5,
        )

    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """Mock AfterInvocationEvent with usage data."""
        event = MagicMock(spec=AfterInvocationEvent)
        event.response = MagicMock()
        event.response.usage = MagicMock()
        event.response.usage.input_tokens = 800  # Default below threshold
        event.response.usage.output_tokens = 200
        return event

    @pytest.mark.asyncio
    async def test_hook_registration_adds_callback(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction
    ) -> None:
        """Test that register_hooks() adds callback to HookRegistry."""
        hook = ProactiveCompactionHook(threshold_tokens=mock_config.when_tokens_over)

        mock_registry = MagicMock(spec=HookRegistry)
        hook.register_hooks(mock_registry)

        # Verify add_callback was called with AfterInvocationEvent
        assert mock_registry.add_callback.call_count == 1
        call_args = mock_registry.add_callback.call_args
        assert call_args[0][0] == AfterInvocationEvent
        # Verify callback is callable
        assert callable(call_args[0][1])

    @pytest.mark.asyncio
    async def test_no_compaction_when_below_threshold(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction, mock_event: MagicMock
    ) -> None:
        """Test that compaction is NOT triggered when input_tokens < threshold."""
        # Setup agent with conversation_manager and accumulated_usage
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        # accumulated_usage should be a dict, not MagicMock with attributes
        mock_agent.accumulated_usage = {"totalTokens": 800}  # Below threshold
        mock_event.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)
        hook._check_and_compact(mock_event)

        # apply_management should NOT be called
        mock_conversation_manager.apply_management.assert_not_called()

    @pytest.mark.asyncio
    async def test_compaction_triggered_when_at_threshold(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction, mock_event: MagicMock
    ) -> None:
        """Test that compaction IS triggered when input_tokens >= threshold."""
        # Setup agent with conversation_manager and accumulated_usage
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        mock_agent.accumulated_usage = {"totalTokens": 1000}  # At threshold
        mock_event.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)
        hook._check_and_compact(mock_event)

        # apply_management SHOULD be called once
        mock_conversation_manager.apply_management.assert_called_once()

    @pytest.mark.asyncio
    async def test_compaction_triggered_when_above_threshold(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction, mock_event: MagicMock
    ) -> None:
        """Test that compaction IS triggered when input_tokens > threshold."""
        # Setup agent with conversation_manager and accumulated_usage
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        mock_agent.accumulated_usage = {"totalTokens": 1500}  # Above threshold
        mock_event.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)
        hook._check_and_compact(mock_event)

        # apply_management SHOULD be called once
        mock_conversation_manager.apply_management.assert_called_once()

    @pytest.mark.asyncio
    async def test_compaction_only_triggers_once(
        self, mock_conversation_manager: MagicMock, mock_event: MagicMock
    ) -> None:
        """Test that compaction only triggers once (compacted flag prevents re-trigger)."""
        # Setup agent
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        mock_agent.accumulated_usage = {"totalTokens": 2000}
        mock_event.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)

        # First call should trigger
        hook._check_and_compact(mock_event)
        assert mock_conversation_manager.apply_management.call_count == 1

        # Second call should NOT trigger (already compacted)
        hook._check_and_compact(mock_event)
        assert mock_conversation_manager.apply_management.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_no_compaction_when_usage_missing(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction
    ) -> None:
        """Test that compaction is NOT triggered when event has no usage data."""
        event_no_usage = MagicMock(spec=AfterInvocationEvent)
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        mock_agent.accumulated_usage = None  # No usage data
        event_no_usage.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)
        hook._check_and_compact(event_no_usage)

        # Should not crash, and should not call apply_management
        mock_conversation_manager.apply_management.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_invocations_only_compact_once(
        self, mock_conversation_manager: MagicMock, mock_config: Compaction, mock_event: MagicMock
    ) -> None:
        """Test that compaction only happens once due to compacted flag."""
        # Setup agent
        mock_agent = MagicMock()
        mock_agent.conversation_manager = mock_conversation_manager
        mock_agent.accumulated_usage = {"totalTokens": 1200}
        mock_event.agent = mock_agent

        hook = ProactiveCompactionHook(threshold_tokens=1000)

        # Simulate 3 invocations - only first should trigger
        hook._check_and_compact(mock_event)
        hook._check_and_compact(mock_event)
        hook._check_and_compact(mock_event)

        # apply_management should only be called once (compacted flag prevents re-trigger)
        assert mock_conversation_manager.apply_management.call_count == 1


class TestAgentCacheWithCompaction:
    """Tests for AgentCache behavior with different conversation managers."""

    @pytest.mark.asyncio
    async def test_cache_key_differentiates_conversation_managers(self) -> None:
        """Test that agents with different conversation managers are cached separately."""
        from strands_cli.exec.utils import AgentCache
        from strands_cli.types import Agent, PatternType, ProviderType, Runtime, Spec

        spec = Spec(
            version=0,
            name="test-cache-cm",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test agent")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )

        cache = AgentCache()

        with patch("strands_cli.exec.utils.build_agent") as mock_build:
            mock_agent1 = MagicMock()
            mock_agent2 = MagicMock()
            mock_build.side_effect = [mock_agent1, mock_agent2]

            # Build agent with no conversation manager
            agent_no_cm = await cache.get_or_build_agent(spec, "agent1", Agent(prompt="Test"))

            # Build agent WITH conversation manager (different cache key)
            mock_cm = MagicMock(spec=SummarizingConversationManager)
            agent_with_cm = await cache.get_or_build_agent(
                spec, "agent1", Agent(prompt="Test"), conversation_manager=mock_cm
            )

            # Should have built 2 different agents (cache miss due to different cm)
            assert mock_build.call_count == 2
            assert agent_no_cm is not agent_with_cm

        await cache.close()

    @pytest.mark.asyncio
    async def test_cache_reuses_agent_with_same_conversation_manager_type(self) -> None:
        """Test that agents with same conversation manager type are reused."""
        from strands_cli.exec.utils import AgentCache
        from strands_cli.types import Agent, PatternType, ProviderType, Runtime, Spec

        spec = Spec(
            version=0,
            name="test-cache-reuse",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": Agent(prompt="Test agent")},
            pattern={"type": PatternType.CHAIN, "config": {}},
        )

        cache = AgentCache()

        with patch("strands_cli.exec.utils.build_agent") as mock_build:
            mock_agent = MagicMock()
            mock_build.return_value = mock_agent

            # Build agent with conversation manager
            mock_cm1 = MagicMock(spec=SummarizingConversationManager)
            agent1 = await cache.get_or_build_agent(
                spec, "agent1", Agent(prompt="Test"), conversation_manager=mock_cm1
            )

            # Build again with DIFFERENT instance but SAME type
            mock_cm2 = MagicMock(spec=SummarizingConversationManager)
            agent2 = await cache.get_or_build_agent(
                spec, "agent1", Agent(prompt="Test"), conversation_manager=mock_cm2
            )

            # Should reuse cached agent (same cache key)
            assert mock_build.call_count == 1
            assert agent1 is agent2

        await cache.close()


class TestEndToEndIntegration:
    """End-to-end integration tests for context compaction in executors."""

    @pytest.mark.asyncio
    async def test_chain_executor_with_compaction_enabled(self) -> None:
        """Test that chain executor creates and uses compaction hooks."""
        from strands_cli.exec.chain import run_chain
        from strands_cli.types import (
            Agent,
            ChainStep,
            PatternConfig,
            PatternType,
            ProviderType,
            Runtime,
            Spec,
        )

        spec = Spec(
            version=0,
            name="test-chain-compaction",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            context_policy=ContextPolicy(
                compaction=Compaction(enabled=True, when_tokens_over=1000)
            ),
            agents={"agent1": Agent(prompt="Test agent")},
            pattern={
                "type": PatternType.CHAIN,
                "config": PatternConfig(
                    steps=[
                        ChainStep(agent="agent1", prompt="Step 1"),
                        ChainStep(agent="agent1", prompt="Step 2"),
                    ]
                ),
            },
        )

        with patch("strands_cli.exec.chain.AgentCache") as mock_cache_class:
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            mock_cache.close = AsyncMock()

            mock_agent = MagicMock()
            mock_agent.invoke_async = AsyncMock(return_value="Response")
            mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

            await run_chain(spec, {})

            # Verify get_or_build_agent was called with hooks parameter
            calls = mock_cache.get_or_build_agent.call_args_list
            assert len(calls) == 2  # Called once per step (2 steps)

            # Verify hooks parameter was provided (list with ProactiveCompactionHook)
            call_kwargs = calls[0].kwargs
            assert "hooks" in call_kwargs
            assert isinstance(call_kwargs["hooks"], list)
            assert len(call_kwargs["hooks"]) == 1
            assert isinstance(call_kwargs["hooks"][0], ProactiveCompactionHook)

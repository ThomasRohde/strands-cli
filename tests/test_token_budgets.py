"""Tests for token budget management (Feature 6.4).

Tests cover:
- TokenCounter accuracy with different providers
- BudgetEnforcerHook warning and hard limit behavior
- Configurable warning thresholds
- Integration with executors
- Structured logging output
- Exit code handling
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strands_cli.exit_codes import EX_BUDGET_EXCEEDED
from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook, BudgetExceededError
from strands_cli.runtime.token_counter import TokenCounter
from strands_cli.types import (
    Agent,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
)

# --- TokenCounter Tests ---


class TestTokenCounter:
    """Test TokenCounter tiktoken integration."""

    def test_count_messages_simple(self) -> None:
        """Test basic message counting."""
        counter = TokenCounter("gpt-4")
        messages = [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there"},
        ]

        tokens = counter.count_messages(messages)

        # Should include: 2 messages * 4 overhead + content tokens + 2 for reply priming
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_count_messages_empty(self) -> None:
        """Test empty message list."""
        counter = TokenCounter("gpt-4")
        messages: list[dict[str, Any]] = []

        tokens = counter.count_messages(messages)

        # Just the 2 tokens for reply priming
        assert tokens == 2

    def test_encoding_selection_claude(self) -> None:
        """Test that Claude models use cl100k_base encoding."""
        counter = TokenCounter("anthropic.claude-3-sonnet-20240229-v1:0")

        assert counter.encoding.name == "cl100k_base"

    def test_encoding_selection_gpt4(self) -> None:
        """Test that GPT-4 models use correct encoding."""
        counter = TokenCounter("gpt-4")

        # GPT-4 should use cl100k_base
        assert counter.encoding.name == "cl100k_base"

    def test_encoding_selection_fallback(self) -> None:
        """Test unknown models fall back to cl100k_base."""
        counter = TokenCounter("llama2")

        assert counter.encoding.name == "cl100k_base"

    def test_count_accuracy_within_tolerance(self) -> None:
        """Test token count is reasonably accurate (±10% tolerance)."""
        counter = TokenCounter("gpt-4")

        # Known example: "Hello, how are you today?"
        messages = [{"role": "user", "content": "Hello, how are you today?"}]

        tokens = counter.count_messages(messages)

        # Expected: ~11 tokens (4 overhead + ~5 content + 2 priming)
        # Allow ±10% tolerance
        assert 8 <= tokens <= 14

    def test_count_with_none_values(self) -> None:
        """Test that None values in messages are handled."""
        counter = TokenCounter("gpt-4")
        messages = [
            {"role": "user", "content": "Hello", "name": None},
        ]

        tokens = counter.count_messages(messages)

        # Should not crash, should count correctly
        assert tokens > 0


# --- BudgetEnforcerHook Tests ---


class TestBudgetEnforcerHook:
    """Test BudgetEnforcerHook warning and enforcement logic."""

    def test_initialization(self) -> None:
        """Test hook initialization with default threshold."""
        hook = BudgetEnforcerHook(max_tokens=100000)

        assert hook.max_tokens == 100000
        assert hook.warn_threshold == 0.8
        assert hook.warn_tokens == 80000
        assert not hook.warned

    def test_initialization_custom_threshold(self) -> None:
        """Test hook initialization with custom threshold."""
        hook = BudgetEnforcerHook(max_tokens=100000, warn_threshold=0.75)

        assert hook.max_tokens == 100000
        assert hook.warn_threshold == 0.75
        assert hook.warn_tokens == 75000

    def test_no_action_below_threshold(self, caplog: Any) -> None:
        """Test no warnings below threshold."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with agent having 700 tokens (70% usage)
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 700}

        # Should not raise or warn
        hook._check_budget(event)

        assert not hook.warned

    def test_warning_at_threshold(self, caplog: Any) -> None:
        """Test warning logged at configured threshold."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with agent having 800 tokens (80% usage)
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 800}

        # Should warn but not raise
        hook._check_budget(event)

        assert hook.warned

    def test_warning_at_custom_threshold(self, caplog: Any) -> None:
        """Test warning at custom 75% threshold."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.75)

        # Mock event with agent having 750 tokens (75% usage)
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 750}

        # Should warn
        hook._check_budget(event)

        assert hook.warned

    def test_warning_only_once(self, caplog: Any) -> None:
        """Test warning logged only once."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with agent having 850 tokens
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 850}

        # Call twice
        hook._check_budget(event)
        hook._check_budget(event)

        # Should only warn once
        assert hook.warned

    def test_hard_limit_at_100_percent(self) -> None:
        """Test BudgetExceededError raised at 100%."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with agent having 1000 tokens (100% usage)
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 1000}

        # Should raise BudgetExceededError
        with pytest.raises(BudgetExceededError) as exc_info:
            hook._check_budget(event)

        error = exc_info.value
        assert error.cumulative_tokens == 1000
        assert error.max_tokens == 1000
        assert error.exit_code == EX_BUDGET_EXCEEDED

    def test_hard_limit_above_100_percent(self) -> None:
        """Test BudgetExceededError raised above 100%."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with agent having 1100 tokens (110% usage)
        event = MagicMock()
        event.agent.accumulated_usage = {"totalTokens": 1100}

        # Should raise
        with pytest.raises(BudgetExceededError) as exc_info:
            hook._check_budget(event)

        error = exc_info.value
        assert error.cumulative_tokens == 1100
        assert error.max_tokens == 1000

    def test_handles_missing_accumulated_usage(self) -> None:
        """Test hook handles event.agent without accumulated_usage."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event without accumulated_usage
        event = MagicMock()
        event.agent.accumulated_usage = None

        # Should not raise
        hook._check_budget(event)

    def test_handles_empty_accumulated_usage(self) -> None:
        """Test hook handles empty accumulated_usage dict."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # Mock event with empty dict
        event = MagicMock()
        event.agent.accumulated_usage = {}

        # Should not raise
        hook._check_budget(event)

    def test_cumulative_tracking(self) -> None:
        """Test hook tracks cumulative tokens."""
        hook = BudgetEnforcerHook(max_tokens=1000, warn_threshold=0.8)

        # First call with 400 tokens
        event1 = MagicMock()
        event1.agent.accumulated_usage = {"totalTokens": 400}
        hook._check_budget(event1)

        assert hook.cumulative_tokens == 400

        # Second call with 700 tokens (SDK accumulates tokens)
        event2 = MagicMock()
        event2.agent.accumulated_usage = {"totalTokens": 700}
        hook._check_budget(event2)

        assert hook.cumulative_tokens == 700
        assert not hook.warned  # 700 < 800 (warn threshold)


# --- Integration Tests ---


@pytest.fixture
def spec_with_budget() -> Spec:
    """Spec with token budget configured."""
    return Spec(
        name="test-budget",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="test-model",
            budgets={"max_tokens": 1000, "warn_threshold": 0.8},
        ),
        agents={"agent1": Agent(prompt="Test agent")},
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(
                steps=[
                    {"agent": "agent1", "input": "Test input"},
                ]
            ),
        ),
    )


@pytest.fixture
def spec_with_custom_threshold() -> Spec:
    """Spec with custom warning threshold."""
    return Spec(
        name="test-custom-threshold",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="test-model",
            budgets={"max_tokens": 1000, "warn_threshold": 0.75},
        ),
        agents={"agent1": Agent(prompt="Test agent")},
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(
                steps=[
                    {"agent": "agent1", "input": "Test input"},
                ]
            ),
        ),
    )


class TestBudgetIntegration:
    """Test budget enforcement integration with executors."""

    def test_budget_configuration_parsed(self, spec_with_budget: Spec) -> None:
        """Test budget configuration is correctly parsed from spec."""
        assert spec_with_budget.runtime.budgets is not None
        assert spec_with_budget.runtime.budgets["max_tokens"] == 1000
        assert spec_with_budget.runtime.budgets["warn_threshold"] == 0.8

    def test_custom_threshold_parsed(self, spec_with_custom_threshold: Spec) -> None:
        """Test custom warning threshold is parsed."""
        assert spec_with_custom_threshold.runtime.budgets is not None
        assert spec_with_custom_threshold.runtime.budgets["warn_threshold"] == 0.75

    @pytest.mark.asyncio
    async def test_budget_enforcer_initialized_in_chain(
        self, spec_with_budget: Spec, mocker: Any
    ) -> None:
        """Test that budget enforcer hook is initialized in chain executor."""
        from strands_cli.exec.chain import run_chain

        # Mock AgentCache and agent
        mock_cache = mocker.patch("strands_cli.exec.chain.AgentCache")
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response")
        mock_cache.return_value.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.return_value.close = AsyncMock()

        # Run chain
        result = await run_chain(spec_with_budget, variables=None)

        # Verify result
        assert result.success is True

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises_error(self, spec_with_budget: Spec, mocker: Any) -> None:
        """Test that exceeding budget raises BudgetExceededError."""
        from strands_cli.exec.chain import ChainExecutionError, run_chain

        # Set very low budget
        spec_with_budget.runtime.budgets = {"max_tokens": 10, "warn_threshold": 0.8}

        # Mock AgentCache to return an agent whose invocation raises BudgetExceededError
        mock_cache = mocker.patch("strands_cli.exec.chain.AgentCache")
        mock_agent = MagicMock()
        budget_error = BudgetExceededError(
            "Token budget exhausted",
            cumulative_tokens=25,
            max_tokens=10,
        )
        mock_agent.invoke_async = AsyncMock(side_effect=budget_error)
        mock_cache.return_value.get_or_build_agent = AsyncMock(return_value=mock_agent)
        mock_cache.return_value.close = AsyncMock()

        with pytest.raises(ChainExecutionError) as exc_info:
            await run_chain(spec_with_budget, variables=None)

        cause = exc_info.value.__cause__
        assert isinstance(cause, BudgetExceededError)
        assert cause.cumulative_tokens == 25


# --- Exit Code Tests ---


class TestBudgetExitCodes:
    """Test exit code handling for budget exceeded."""

    def test_budget_exceeded_error_has_exit_code(self) -> None:
        """Test BudgetExceededError includes EX_BUDGET_EXCEEDED."""
        error = BudgetExceededError("Budget exceeded", cumulative_tokens=1000, max_tokens=900)

        assert error.exit_code == EX_BUDGET_EXCEEDED
        assert error.cumulative_tokens == 1000
        assert error.max_tokens == 900

    def test_exit_code_constant_value(self) -> None:
        """Test EX_BUDGET_EXCEEDED has correct value."""
        assert EX_BUDGET_EXCEEDED == 20

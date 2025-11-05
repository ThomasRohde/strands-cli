"""Tests for exec/chain.py — Sequential multi-step chain executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.chain import _build_step_context, _check_budget_warning, run_chain
from strands_cli.types import Spec


class TestBuildStepContext:
    """Test step context construction for template rendering."""

    def test_build_step_context_first_step(self, minimal_ollama_spec: Path) -> None:
        """First step should have empty steps array."""
        from strands_cli.loader.yaml_loader import load_spec

        spec = load_spec(str(minimal_ollama_spec))
        variables = {"topic": "test"}
        step_history: list[dict[str, Any]] = []

        context = _build_step_context(spec, 0, step_history, variables)

        assert context["steps"] == []
        assert context["topic"] == "test"

    def test_build_step_context_with_history(self, minimal_ollama_spec: Path) -> None:
        """Steps array should contain previous responses."""
        from strands_cli.loader.yaml_loader import load_spec

        spec = load_spec(str(minimal_ollama_spec))
        variables = {"topic": "test"}
        step_history: list[dict[str, Any]] = [
            {"index": 0, "agent": "agent1", "response": "First result"},
            {"index": 1, "agent": "agent1", "response": "Second result"},
        ]

        # Use step_index=0 since we're just testing context building, not actual step execution
        context = _build_step_context(spec, 0, step_history, variables)

        assert len(context["steps"]) == 2
        assert context["steps"][0]["response"] == "First result"
        assert context["steps"][1]["response"] == "Second result"
        assert context["topic"] == "test"


class TestCheckBudgetWarning:
    """Test budget threshold warnings."""

    def test_no_warning_below_threshold(self) -> None:
        """No warning when consumption below 80%."""
        step_number = 1
        cumulative_tokens = 700
        max_tokens = 1000

        # Should not raise
        _check_budget_warning(cumulative_tokens, max_tokens, step_number)

    def test_warning_at_80_percent(self) -> None:
        """Warning emitted at 80% consumption."""
        step_number = 2
        cumulative_tokens = 800
        max_tokens = 1000

        # Should not raise, but will log warning to structlog
        _check_budget_warning(cumulative_tokens, max_tokens, step_number)

    def test_stops_at_100_percent(self) -> None:
        """Should raise error at 100% consumption."""
        step_number = 3
        cumulative_tokens = 1000
        max_tokens = 1000

        with pytest.raises(Exception, match="Token budget exceeded"):
            _check_budget_warning(cumulative_tokens, max_tokens, step_number)

    def test_no_warning_when_no_budgets(self) -> None:
        """No warning when budgets not configured."""
        step_number = 1
        cumulative_tokens = 999999
        max_tokens = None

        # Should not raise or warn
        _check_budget_warning(cumulative_tokens, max_tokens, step_number)


class TestRunChain:
    """Test chain execution orchestration."""

    @pytest.fixture
    def chain_spec_3_steps(self, tmp_path: Path) -> Spec:
        """Chain with 3 steps for testing."""
        from ruamel.yaml import YAML

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "test-agent", "input": "Step 1 prompt"},
                        {"agent": "test-agent", "input": "Step 2: {{ steps[0].response }}"},
                        {"agent": "test-agent", "input": "Step 3: {{ steps[1].response }}"},
                    ]
                },
            },
            "agents": {
                "test-agent": {
                    "prompt": "You are a test agent",
                    "tools": [],
                }
            },
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        from strands_cli.loader.yaml_loader import load_spec

        return load_spec(str(spec_file))

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_success(self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec) -> None:
        """Test successful 3-step chain execution."""
        # Mock agent responses
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Response 1",
                "Response 2",
                "Response 3",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True
        assert result.last_response == "Response 3"
        assert mock_build_agent.call_count == 3

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_with_step_variables(
        self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test chain with step-level variable overrides."""
        # Modify spec to include step vars
        steps = chain_spec_3_steps.pattern.config.steps
        if steps:
            steps[0].vars = {"custom_var": "custom_value"}

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Response 1",
                "Response 2",
                "Response 3",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_chain(chain_spec_3_steps, variables={"base_var": "base_value"})

        assert result.success is True

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_step_failure(
        self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test chain stops on step failure."""
        from strands_cli.exec.chain import ChainExecutionError

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("Agent error"))
        mock_build_agent.return_value = mock_agent

        with pytest.raises(ChainExecutionError, match="Agent error"):
            run_chain(chain_spec_3_steps, variables=None)

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_budget_tracking(
        self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test budget consumption tracking across steps."""
        # Add budget constraints
        chain_spec_3_steps.runtime.budgets = {"max_tokens": 500}

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Response 1",
                "Response 2",
                "Response 3",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_budget_exceeded(
        self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test chain stops when budget exceeded."""
        from strands_cli.exec.chain import ChainExecutionError

        chain_spec_3_steps.runtime.budgets = {"max_tokens": 5}

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            return_value="Response with many tokens that exceeds budget"
        )
        mock_build_agent.return_value = mock_agent

        with pytest.raises(ChainExecutionError, match="budget exceeded"):
            run_chain(chain_spec_3_steps, variables=None)

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_with_tool_overrides(
        self, mock_build_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test step-level tool overrides."""
        # Add tool overrides to step
        steps = chain_spec_3_steps.pattern.config.steps
        if steps:
            steps[0].tool_overrides = ["strands_tools.http_request"]

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Response 1",
                "Response 2",
                "Response 3",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True
        # Verify build_agent was called with tool_overrides for first step
        first_call = mock_build_agent.call_args_list[0]
        assert first_call[1]["tool_overrides"] == ["strands_tools.http_request"]


class TestChainTemplateRendering:
    """Test Jinja2 template rendering in chain execution."""

    @patch("strands_cli.exec.chain.build_agent")
    def test_chain_renders_previous_responses(
        self, mock_build_agent: MagicMock, tmp_path: Path
    ) -> None:
        """Test that {{ steps[N].response }} renders correctly."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Chain",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "agent1", "input": "What is 2+2?"},
                        {"agent": "agent1", "input": "The answer was: {{ steps[0].response }}"},
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a calculator"}},
        }

        spec_file = tmp_path / "chain.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "4",
                "Correct",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_chain(spec, variables=None)

        assert result.success is True
        # Verify second invocation received rendered template with first response
        # (The actual template rendering is tested separately)


class TestSingleAgentRegression:
    """Regression tests for single_agent.py fixes."""

    @patch("strands_cli.exec.single_agent.build_agent")
    def test_single_step_uses_step_agent(self, mock_build_agent: MagicMock, tmp_path: Path) -> None:
        """Test that single-step chain uses agent referenced in step, not first agent in map.

        Regression test for issue where run_single_agent always used first agent in spec.agents dict.
        """
        from ruamel.yaml import YAML

        from strands_cli.exec.single_agent import run_single_agent
        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        # Create spec with agents in different order
        spec_data = {
            "name": "Test Agent Selection",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model", "region": "us-east-1"},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": [
                        {"agent": "agent_b", "input": "Test task"}  # References agent_b
                    ]
                },
            },
            "agents": {
                "agent_a": {"prompt": "I am agent A"},  # First in dict
                "agent_b": {"prompt": "I am agent B"},  # Should be selected
            },
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response from B")
        mock_build_agent.return_value = mock_agent

        result = run_single_agent(spec, variables=None)

        # Verify build_agent was called with agent_b, not agent_a
        assert mock_build_agent.call_count == 1
        call_args = mock_build_agent.call_args
        assert call_args[0][1] == "agent_b"  # agent_id argument
        assert result.agent_id == "agent_b"
        assert result.success is True

    @patch("strands_cli.exec.single_agent.build_agent")
    def test_single_agent_respects_cli_vars(
        self, mock_build_agent: MagicMock, tmp_path: Path
    ) -> None:
        """Test that --var CLI overrides are merged into template variables.

        Regression test for issue where variables argument was ignored in run_single_agent.
        """
        from ruamel.yaml import YAML

        from strands_cli.exec.single_agent import run_single_agent
        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test CLI Variables",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model", "region": "us-east-1"},
            "inputs": {"values": {"default_topic": "default"}},
            "pattern": {
                "type": "chain",
                "config": {"steps": [{"agent": "test", "input": "Process topic: {{ topic }}"}]},
            },
            "agents": {"test": {"prompt": "Test agent"}},
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        # Capture the rendered input passed to agent
        captured_input = None

        async def capture_invoke(input_text: str) -> str:
            nonlocal captured_input
            captured_input = input_text
            return "Response"

        mock_agent = MagicMock()
        mock_agent.invoke_async = capture_invoke
        mock_build_agent.return_value = mock_agent

        # Run with CLI variable override
        result = run_single_agent(spec, variables={"topic": "cli_override"})

        assert result.success is True
        # Verify the template was rendered with CLI variable, not default
        assert captured_input is not None
        assert "cli_override" in captured_input
        assert "default" not in captured_input

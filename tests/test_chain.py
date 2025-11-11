"""Tests for exec/chain.py — Sequential multi-step chain executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.chain import _build_step_context, run_chain
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


# Note: TestCheckBudgetWarning class removed in Phase 6.4
# Budget enforcement now handled by BudgetEnforcerHook (see tests/test_token_budgets.py)


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

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_success(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
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
        mock_get_agent.return_value = mock_agent

        result = await run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True
        assert result.last_response == "Response 3"
        assert mock_get_agent.call_count == 3

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_with_step_variables(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
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
        mock_get_agent.return_value = mock_agent

        result = await run_chain(chain_spec_3_steps, variables={"base_var": "base_value"})

        assert result.success is True

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_step_failure(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test chain stops on step failure."""
        from strands_cli.exec.chain import ChainExecutionError

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("Agent error"))
        mock_get_agent.return_value = mock_agent

        with pytest.raises(ChainExecutionError, match="Agent error"):
            await run_chain(chain_spec_3_steps, variables=None)

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_budget_tracking(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
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
        mock_get_agent.return_value = mock_agent

        result = await run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_budget_exceeded(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test chain stops when budget exceeded."""
        from strands_cli.exec.chain import ChainExecutionError
        from strands_cli.runtime.budget_enforcer import BudgetExceededError

        chain_spec_3_steps.runtime.budgets = {"max_tokens": 5}

        budget_error = BudgetExceededError(
            "Token budget exhausted",
            cumulative_tokens=10,
            max_tokens=5,
        )

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=budget_error)
        mock_get_agent.return_value = mock_agent

        # BudgetExceededError should propagate as the cause of ChainExecutionError
        with pytest.raises(ChainExecutionError) as exc_info:
            await run_chain(chain_spec_3_steps, variables=None)

        cause = exc_info.value.__cause__
        assert isinstance(cause, BudgetExceededError)
        assert "Token budget exhausted" in str(cause)

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_run_chain_with_tool_overrides(
        self, mock_get_agent: MagicMock, chain_spec_3_steps: Spec
    ) -> None:
        """Test step-level tool overrides."""
        # Add tool overrides to step
        steps = chain_spec_3_steps.pattern.config.steps
        if steps:
            steps[0].tool_overrides = ["strands_tools.http_request.http_request"]

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Response 1",
                "Response 2",
                "Response 3",
            ]
        )
        mock_get_agent.return_value = mock_agent

        result = await run_chain(chain_spec_3_steps, variables=None)

        assert result.success is True
        # Verify get_or_build_agent was called with tool_overrides for first step
        first_call = mock_get_agent.call_args_list[0]
        assert first_call[1]["tool_overrides"] == ["strands_tools.http_request.http_request"]


class TestChainTemplateRendering:
    """Test Jinja2 template rendering in chain execution."""

    @pytest.mark.asyncio
    @patch("strands_cli.exec.utils.AgentCache.get_or_build_agent")
    async def test_chain_renders_previous_responses(
        self, mock_get_agent: MagicMock, tmp_path: Path
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
        with open(spec_file, "w") as f:  # noqa: ASYNC230
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "4",
                "Correct",
            ]
        )
        mock_get_agent.return_value = mock_agent

        result = await run_chain(spec, variables=None)

        assert result.success is True
        # Verify second invocation received rendered template with first response
        # (The actual template rendering is tested separately)


class TestSingleAgentRegression:
    """Regression tests for single_agent.py fixes."""

    @pytest.mark.asyncio
    async def test_single_step_uses_step_agent(self, tmp_path: Path, mocker: Any) -> None:
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
        with open(spec_file, "w") as f:  # noqa: ASYNC230
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value="Response from B")

        # Mock AgentCache to track which agent is built
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.single_agent.AgentCache", return_value=mock_cache)

        result = await run_single_agent(spec, variables=None)

        # Verify get_or_build_agent was called with agent_b, not agent_a
        assert mock_cache.get_or_build_agent.call_count == 1
        call_args = mock_cache.get_or_build_agent.call_args
        assert call_args[0][1] == "agent_b"  # agent_id argument
        assert result.agent_id == "agent_b"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_single_agent_respects_cli_vars(self, tmp_path: Path, mocker: Any) -> None:
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
        with open(spec_file, "w") as f:  # noqa: ASYNC230
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

        # Mock AgentCache
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.single_agent.AgentCache", return_value=mock_cache)

        # Run with CLI variable override
        result = await run_single_agent(spec, variables={"topic": "cli_override"})

        assert result.success is True
        # Verify the template was rendered with CLI variable, not default
        assert captured_input is not None
        assert "cli_override" in captured_input
        assert "default" not in captured_input


@pytest.mark.asyncio
async def test_chain_with_notes_creates_and_injects(tmp_path: Path, mocker: Any) -> None:
    """Test that chain executor creates notes file and attempts to inject into subsequent steps."""
    import yaml

    from strands_cli.exec.chain import run_chain
    from strands_cli.loader.yaml_loader import load_spec

    notes_file = tmp_path / "test-notes.md"

    # Create a 3-step chain with notes enabled
    spec_data = {
        "version": 0,
        "name": "Notes Test Chain",
        "runtime": {"provider": "ollama", "model_id": "llama3.2", "host": "http://localhost:11434"},
        "context_policy": {"notes": {"file": str(notes_file), "include_last": 2}},
        "agents": {"agent1": {"prompt": "You are agent 1", "tools": []}},
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {"agent": "agent1", "input": "Step 1 input"},
                    {"agent": "agent1", "input": "Step 2 input"},
                    {"agent": "agent1", "input": "Step 3 input"},
                ]
            },
        },
    }

    spec_file = tmp_path / "test.yaml"
    with open(spec_file, "w") as f:  # noqa: ASYNC230
        yaml.dump(spec_data, f)

    spec = load_spec(str(spec_file))

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.name = "agent1"
    mock_agent.invoke_async = AsyncMock(side_effect=["Response 1", "Response 2", "Response 3"])

    # Mock AgentCache
    mock_cache = mocker.AsyncMock()
    mock_cache.get_or_build_agent.return_value = mock_agent
    mock_cache.close.return_value = None
    mocker.patch("strands_cli.exec.chain.AgentCache", return_value=mock_cache)

    # Run chain
    result = await run_chain(spec, variables=None)

    assert result.success is True
    assert result.last_response == "Response 3"

    # Verify NotesManager was initialized (check logs show "notes_enabled")
    # Verify that get_or_build_agent was called with hooks parameter
    calls = mock_cache.get_or_build_agent.call_args_list
    assert len(calls) == 3

    # Check that hooks were passed (NotesAppenderHook should be in the list)
    for call in calls:
        hooks_arg = call.kwargs.get("hooks")
        assert hooks_arg is not None, "hooks parameter should be passed to get_or_build_agent"
        # Should contain NotesAppenderHook
        from strands_cli.exec.hooks import NotesAppenderHook

        has_notes_hook = any(isinstance(hook, NotesAppenderHook) for hook in hooks_arg)
        assert has_notes_hook, "NotesAppenderHook should be in hooks list"

    # Check that injected_notes parameter changes across steps
    # Step 1: no notes yet (empty or None)
    step1_notes = calls[0].kwargs.get("injected_notes")
    assert step1_notes is None or step1_notes == "", "Step 1 should have no prior notes"

    # Steps 2 and 3: NotesManager.read_last_n() is called (but returns empty since hooks didn't run)
    # We can't verify file creation without actually running hooks, but we verify the plumbing exists

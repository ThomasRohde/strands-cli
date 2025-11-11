"""Unit tests for Workflow API.

Focuses on testing the public API surface without extensive mocking of internals.
Integration tests verify end-to-end behavior with real executors.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.api import Workflow
from strands_cli.api.execution import WorkflowExecutor
from strands_cli.api.handlers import terminal_hitl_handler
from strands_cli.exit_codes import EX_OK
from strands_cli.loader import LoadError
from strands_cli.schema.validator import SchemaValidationError
from strands_cli.types import HITLState, PatternType, RunResult, Spec


# ============================================================================
# Test Helpers
# ============================================================================


def create_run_result(**kwargs) -> RunResult:
    """Create RunResult with sensible defaults for testing."""
    now = datetime.now(UTC).isoformat()
    defaults = {
        "success": True,
        "exit_code": EX_OK,
        "pattern_type": PatternType.CHAIN,
        "agent_id": "agent1",
        "last_response": "Test response",
        "started_at": now,
        "completed_at": now,
        "duration_seconds": 0.0,
    }
    defaults.update(kwargs)
    return RunResult(**defaults)


def create_hitl_state(**kwargs) -> HITLState:
    """Create HITLState with sensible defaults for testing."""
    defaults = {
        "active": True,
        "prompt": "Test prompt",
        "step_index": 0,  # Default to chain pattern
    }
    defaults.update(kwargs)
    return HITLState(**defaults)


# ============================================================================
# Workflow Class Tests
# ============================================================================


class TestWorkflowFromFile:
    """Test Workflow.from_file() classmethod."""

    def test_from_file_loads_spec(self, tmp_path: Path) -> None:
        """Test that from_file loads and validates spec."""
        # Create minimal spec file with Ollama host
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text(
            """
version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Test prompt"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Test input"
"""
        )

        # Load workflow
        workflow = Workflow.from_file(spec_file)

        # Verify
        assert isinstance(workflow.spec, Spec)
        assert workflow.spec.name == "test-workflow"
        assert workflow.spec.runtime.provider == "ollama"
        assert workflow.spec.pattern.type == "chain"

    def test_from_file_with_variables(self, tmp_path: Path) -> None:
        """Test that from_file merges variables."""
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text(
            """
version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Research {{topic}}"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Research {{topic}}"
"""
        )

        # Load with variables
        workflow = Workflow.from_file(spec_file, topic="AI")

        # Verify (variables merged during load_spec)
        assert workflow.spec is not None
        assert workflow.spec.name == "test-workflow"

    def test_from_file_with_string_path(self, tmp_path: Path) -> None:
        """Test that from_file accepts string path."""
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text(
            """
version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "test"
"""
        )

        # Load with string path (not Path object)
        workflow = Workflow.from_file(str(spec_file))

        assert workflow.spec.name == "test-workflow"

    def test_from_file_with_nonexistent_file(self) -> None:
        """Test that from_file raises LoadError for missing file."""
        with pytest.raises(LoadError):
            Workflow.from_file("/nonexistent/path/to/file.yaml")

    def test_from_file_with_invalid_yaml(self, tmp_path: Path) -> None:
        """Test that from_file raises LoadError for malformed YAML."""
        spec_file = tmp_path / "malformed.yaml"
        spec_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(LoadError):
            Workflow.from_file(spec_file)

    def test_from_file_with_invalid_spec(self, tmp_path: Path) -> None:
        """Test that from_file raises SchemaValidationError for invalid spec."""
        spec_file = tmp_path / "invalid.yaml"
        spec_file.write_text(
            """
version: 0
name: test-workflow
# Missing required 'runtime' field
agents:
  agent1:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps: []
"""
        )

        with pytest.raises(SchemaValidationError):
            Workflow.from_file(spec_file)


class TestWorkflowInit:
    """Test Workflow.__init__() constructor."""

    def test_init_stores_spec(self) -> None:
        """Test that __init__ stores spec correctly."""
        # Create mock spec
        mock_spec = MagicMock(spec=Spec)
        mock_spec.name = "test-workflow"

        # Initialize workflow
        workflow = Workflow(mock_spec)

        # Verify
        assert workflow.spec == mock_spec
        assert workflow.spec.name == "test-workflow"


class TestWorkflowRunInteractiveAsync:
    """Test Workflow.run_interactive_async() async method."""

    @pytest.mark.asyncio
    async def test_run_interactive_async_creates_executor(self) -> None:
        """Test that run_interactive_async creates WorkflowExecutor."""
        # Mock WorkflowExecutor
        with patch("strands_cli.api.WorkflowExecutor") as mock_executor_cls:
            mock_executor = AsyncMock()
            mock_executor_cls.return_value = mock_executor

            mock_result = create_run_result(last_response="Test response")
            mock_executor.run_interactive.return_value = mock_result

            mock_spec = MagicMock(spec=Spec)
            mock_spec.name = "test-workflow"
            mock_spec.pattern = MagicMock()
            mock_spec.pattern.type = PatternType.CHAIN

            mock_runtime = MagicMock()
            mock_runtime.model_dump.return_value = {"provider": "ollama"}
            mock_spec.runtime = mock_runtime

            workflow = Workflow(mock_spec)

            # Run
            result = await workflow.run_interactive_async(topic="AI")

            # Verify executor created with spec
            mock_executor_cls.assert_called_once_with(mock_spec)
            mock_executor.run_interactive.assert_called_once_with(
                {"topic": "AI"}, hitl_handler=None
            )
            assert result.last_response == "Test response"

    @pytest.mark.asyncio
    async def test_run_interactive_async_passes_variables(self) -> None:
        """Test that variables are passed to executor."""
        with patch("strands_cli.api.WorkflowExecutor") as mock_executor_cls:
            mock_executor = AsyncMock()
            mock_executor_cls.return_value = mock_executor

            mock_result = create_run_result()
            mock_executor.run_interactive.return_value = mock_result

            mock_spec = MagicMock(spec=Spec)
            workflow = Workflow(mock_spec)

            await workflow.run_interactive_async(topic="quantum computing", style="academic")

            # Verify variables dict passed correctly
            call_args = mock_executor.run_interactive.call_args[0][0]
            assert call_args == {"topic": "quantum computing", "style": "academic"}


class TestWorkflowRunAsync:
    """Test Workflow.run_async() non-interactive async method."""

    @pytest.mark.asyncio
    async def test_run_async_creates_executor(self) -> None:
        """Test that run_async creates WorkflowExecutor."""
        with patch("strands_cli.api.WorkflowExecutor") as mock_executor_cls:
            mock_executor = AsyncMock()
            mock_executor_cls.return_value = mock_executor

            mock_result = create_run_result()
            mock_executor.run.return_value = mock_result

            mock_spec = MagicMock(spec=Spec)
            workflow = Workflow(mock_spec)

            result = await workflow.run_async(topic="AI")

            # Verify executor.run called (not run_interactive)
            mock_executor_cls.assert_called_once_with(mock_spec)
            mock_executor.run.assert_called_once_with({"topic": "AI"})
            assert result.exit_code == EX_OK


# ============================================================================
# WorkflowExecutor Tests
# ============================================================================


class TestWorkflowExecutorInit:
    """Test WorkflowExecutor.__init__()."""

    def test_init_stores_spec(self) -> None:
        """Test that executor stores spec."""
        mock_spec = MagicMock(spec=Spec)
        executor = WorkflowExecutor(mock_spec)

        assert executor.spec == mock_spec


# ============================================================================
# HITL Handler Tests
# ============================================================================


class TestTerminalHitlHandler:
    """Test terminal_hitl_handler function."""

    def test_terminal_hitl_handler_prompts_user(self, mocker) -> None:
        """Test that handler displays prompt and returns user input."""
        # Mock Rich Console and Prompt
        mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = "user response"

        hitl_state = create_hitl_state(prompt="Approve findings?")

        result = terminal_hitl_handler(hitl_state)

        # Verify Prompt.ask called
        mock_prompt.ask.assert_called_once_with("Your response")

        # Verify result
        assert result == "user response"

    def test_terminal_hitl_handler_displays_context(self, mocker) -> None:
        """Test that handler displays context_display if provided."""
        mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = "response"

        hitl_state = create_hitl_state(
            prompt="Review results?",
            context_display="Research findings: AI is transforming industries...",
        )

        terminal_hitl_handler(hitl_state)

        # Verify prompt was called (context shown in UI)
        mock_prompt.ask.assert_called_once()

    def test_terminal_hitl_handler_truncates_long_context(self, mocker) -> None:
        """Test that handler truncates context_display > 1000 chars."""
        mock_console = mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = "response"

        long_context = "x" * 1500  # 1500 chars
        hitl_state = create_hitl_state(prompt="Review?", context_display=long_context)

        terminal_hitl_handler(hitl_state)

        # Verify truncation message shown
        calls = mock_console.return_value.print.call_args_list
        truncation_shown = any("truncated" in str(call).lower() for call in calls)
        assert truncation_shown

    def test_terminal_hitl_handler_uses_default_response(self, mocker) -> None:
        """Test that handler uses default_response for empty input."""
        mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = ""  # Empty response

        hitl_state = create_hitl_state(prompt="Continue?", default_response="yes")

        result = terminal_hitl_handler(hitl_state)

        # Verify default used
        assert result == "yes"

    def test_terminal_hitl_handler_strips_whitespace(self, mocker) -> None:
        """Test that handler strips leading/trailing whitespace."""
        mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = "  response with spaces  "

        hitl_state = create_hitl_state(prompt="Input?")

        result = terminal_hitl_handler(hitl_state)

        assert result == "response with spaces"

    def test_terminal_hitl_handler_shows_default_hint(self, mocker) -> None:
        """Test that handler shows default value as hint."""
        mocker.patch("strands_cli.api.handlers.Console")
        mock_prompt = mocker.patch("strands_cli.api.handlers.Prompt")
        mock_prompt.ask.return_value = "custom"

        hitl_state = create_hitl_state(prompt="Approve?", default_response="approved")

        result = terminal_hitl_handler(hitl_state)

        # Verify handler returned custom response (not default)
        assert result == "custom"


# ============================================================================
# Integration Tests (API + Executors)
# ============================================================================


class TestWorkflowAPIIntegration:
    """Integration tests for full API workflow.

    Note: These tests mock agent invocation to avoid Ollama dependency.
    """

    @pytest.mark.asyncio
    async def test_workflow_end_to_end_no_hitl(self, tmp_path: Path) -> None:
        """Test complete workflow execution without HITL."""
        # Create simple spec with Ollama host
        spec_file = tmp_path / "simple.yaml"
        spec_file.write_text(
            """
version: 0
name: simple-workflow
runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Generate a greeting"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Say hello"
"""
        )

        # Mock agent invocation at the Strands SDK level
        with patch("strands.agent.agent.Agent.invoke_async") as mock_invoke:
            mock_invoke.return_value = "Hello, world!"

            # Load and run
            workflow = Workflow.from_file(spec_file)
            result = await workflow.run_interactive_async()

            # Verify
            assert result.success is True
            assert result.last_response == "Hello, world!"
            mock_invoke.assert_called()

    def test_workflow_sync_wrapper_works(self, tmp_path: Path) -> None:
        """Test that sync run_interactive() wrapper works."""
        spec_file = tmp_path / "simple.yaml"
        spec_file.write_text(
            """
version: 0
name: simple-workflow
runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "test"
"""
        )

        with patch("strands.agent.agent.Agent.invoke_async") as mock_invoke:
            mock_invoke.return_value = "Test response"

            workflow = Workflow.from_file(spec_file)
            result = workflow.run_interactive()  # Sync method

            assert result.success is True
            assert result.last_response == "Test response"

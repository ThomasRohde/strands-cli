"""Integration tests for CLI commands with multi-step workflows."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from strands_cli.__main__ import app


@pytest.fixture
def cli_runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def multi_step_chain_yaml(tmp_path: Path) -> Path:
    """Create a multi-step chain spec for CLI testing."""
    spec_content = """
version: 0
name: cli-test-chain
runtime:
  provider: ollama
  model_id: gpt-oss
  host: http://localhost:11434
  budgets:
    max_tokens: 1000
agents:
  test-agent:
    prompt: "You are a test agent"
pattern:
  type: chain
  config:
    steps:
      - agent: test-agent
        input: "Step 1: {{ topic }}"
      - agent: test-agent
        input: "Step 2: Based on {{ steps[0].response }}"
      - agent: test-agent
        input: "Step 3: Final summary"
outputs:
  artifacts:
    - path: "./cli-test-output.txt"
      from: "{{ last_response }}"
"""
    spec_file = tmp_path / "chain-test.yaml"
    spec_file.write_text(spec_content, encoding="utf-8")
    return spec_file


@pytest.fixture
def multi_task_workflow_yaml(tmp_path: Path) -> Path:
    """Create a multi-task workflow spec for CLI testing."""
    spec_content = """
version: 0
name: cli-test-workflow
runtime:
  provider: ollama
  model_id: gpt-oss
  host: http://localhost:11434
  max_parallel: 2
  budgets:
    max_tokens: 1000
agents:
  worker:
    prompt: "You are a worker agent"
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: worker
        input: "Task 1: {{ topic }}"
      - id: task2
        agent: worker
        deps: [task1]
        input: "Task 2: {{ tasks.task1.response }}"
      - id: task3
        agent: worker
        deps: [task1]
        input: "Task 3: {{ tasks.task1.response }}"
      - id: task4
        agent: worker
        deps: [task2, task3]
        input: "Task 4: Merge {{ tasks.task2.response }} and {{ tasks.task3.response }}"
outputs:
  artifacts:
    - path: "./workflow-output.txt"
      from: |
        Task 1: {{ tasks.task1.response }}
        Task 2: {{ tasks.task2.response }}
        Task 3: {{ tasks.task3.response }}
        Task 4: {{ tasks.task4.response }}
"""
    spec_file = tmp_path / "workflow-test.yaml"
    spec_file.write_text(spec_content, encoding="utf-8")
    return spec_file


class TestCLIRunCommand:
    """Test the 'run' command with multi-step workflows."""

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_multi_step_chain(
        self,
        mock_build_agent: MagicMock,
        cli_runner: CliRunner,
        multi_step_chain_yaml: Path,
        tmp_path: Path,
    ):
        """Test running a multi-step chain via CLI."""
        # Mock agent responses
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=["Response 1", "Response 2", "Response 3"])
        mock_build_agent.return_value = mock_agent

        output_dir = tmp_path / "output"
        result = cli_runner.invoke(
            app,
            [
                "run",
                str(multi_step_chain_yaml),
                "--var",
                "topic=testing",
                "--out",
                str(output_dir),
                "--force",
            ],
        )

        assert result.exit_code == 0
        assert "Workflow completed successfully" in result.stdout
        assert mock_build_agent.call_count == 3

        # Verify artifact was written
        artifact_file = output_dir / "cli-test-output.txt"
        assert artifact_file.exists()
        assert "Response 3" in artifact_file.read_text()

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_multi_task_workflow(
        self,
        mock_build_agent: MagicMock,
        cli_runner: CliRunner,
        multi_task_workflow_yaml: Path,
        tmp_path: Path,
    ):
        """Test running a multi-task workflow via CLI."""
        # Mock agent responses
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=["Response 1", "Response 2", "Response 3", "Response 4"]
        )
        mock_build_agent.return_value = mock_agent

        output_dir = tmp_path / "output"
        result = cli_runner.invoke(
            app,
            [
                "run",
                str(multi_task_workflow_yaml),
                "--var",
                "topic=testing",
                "--out",
                str(output_dir),
                "--force",
            ],
        )

        assert result.exit_code == 0
        assert "Workflow completed successfully" in result.stdout
        assert mock_build_agent.call_count == 4

        # Verify artifact was written with task context
        artifact_file = output_dir / "workflow-output.txt"
        assert artifact_file.exists()
        content = artifact_file.read_text()
        assert "Task 1: Response 1" in content
        assert "Task 4: Response 4" in content

    @patch("strands_cli.exec.chain.build_agent")
    def test_run_chain_with_failure(
        self, mock_build_agent: MagicMock, cli_runner: CliRunner, multi_step_chain_yaml: Path
    ):
        """Test chain execution failure via CLI."""
        # Mock agent to fail on second step
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=["Response 1", RuntimeError("Step 2 failed")]
        )
        mock_build_agent.return_value = mock_agent

        result = cli_runner.invoke(
            app, ["run", str(multi_step_chain_yaml), "--var", "topic=testing"]
        )

        assert result.exit_code == 10  # EX_RUNTIME
        assert "Execution failed" in result.stdout


class TestCLIPlanCommand:
    """Test the 'plan' command."""

    def test_plan_multi_step_chain(self, cli_runner: CliRunner, multi_step_chain_yaml: Path):
        """Test plan command shows multi-step chain details."""
        result = cli_runner.invoke(app, ["plan", str(multi_step_chain_yaml)])

        assert result.exit_code == 0
        assert "cli-test-chain" in result.stdout
        assert "ollama" in result.stdout
        assert "chain" in result.stdout.lower()
        assert "MVP Compatible" in result.stdout

    def test_plan_multi_task_workflow(self, cli_runner: CliRunner, multi_task_workflow_yaml: Path):
        """Test plan command shows multi-task workflow details."""
        result = cli_runner.invoke(app, ["plan", str(multi_task_workflow_yaml)])

        assert result.exit_code == 0
        assert "cli-test-workflow" in result.stdout
        assert "workflow" in result.stdout.lower()
        assert "MVP Compatible" in result.stdout

    def test_plan_json_format(self, cli_runner: CliRunner, multi_step_chain_yaml: Path):
        """Test plan command with JSON output."""
        import json
        import re

        result = cli_runner.invoke(app, ["plan", str(multi_step_chain_yaml), "--format", "json"])

        assert result.exit_code == 0

        # Strip ANSI color codes from output
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_output = ansi_escape.sub('', result.stdout)

        # Verify JSON structure
        plan_data = json.loads(clean_output)
        assert plan_data["name"] == "cli-test-chain"
        assert plan_data["pattern"] == "chain"
        assert plan_data["supported"] is True


class TestCLIValidateCommand:
    """Test the 'validate' command."""

    def test_validate_multi_step_chain(self, cli_runner: CliRunner, multi_step_chain_yaml: Path):
        """Test validate command accepts multi-step chain."""
        result = cli_runner.invoke(app, ["validate", str(multi_step_chain_yaml)])

        assert result.exit_code == 0
        assert "Spec is valid" in result.stdout
        assert "cli-test-chain" in result.stdout

    def test_validate_multi_task_workflow(
        self, cli_runner: CliRunner, multi_task_workflow_yaml: Path
    ):
        """Test validate command accepts multi-task workflow."""
        result = cli_runner.invoke(app, ["validate", str(multi_task_workflow_yaml)])

        assert result.exit_code == 0
        assert "Spec is valid" in result.stdout
        assert "cli-test-workflow" in result.stdout

    def test_validate_invalid_spec(self, cli_runner: CliRunner, tmp_path: Path):
        """Test validate command rejects invalid spec."""
        invalid_spec = tmp_path / "invalid.yaml"
        invalid_spec.write_text(
            """
version: 0
name: invalid
runtime:
  provider: invalid_provider
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps: []
""",
            encoding="utf-8",
        )

        result = cli_runner.invoke(app, ["validate", str(invalid_spec)])

        assert result.exit_code == 3  # EX_SCHEMA
        assert "Validation failed" in result.stdout


class TestCLIExplainCommand:
    """Test the 'explain' command."""

    def test_explain_unsupported_features(self, cli_runner: CliRunner, tmp_path: Path):
        """Test explain command for unsupported features."""
        # Use a spec with multiple agents (valid schema, unsupported by MVP)
        unsupported_spec = tmp_path / "unsupported.yaml"
        unsupported_spec.write_text(
            """
version: 0
name: unsupported-multi-agent
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
agents:
  agent1:
    prompt: "Agent 1"
  agent2:
    prompt: "Agent 2"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Step 1"
outputs:
  artifacts:
    - path: "./out.txt"
      from: "{{ last_response }}"
""",
            encoding="utf-8",
        )

        result = cli_runner.invoke(app, ["explain", str(unsupported_spec)])

        assert result.exit_code == 0  # explain shows issues but doesn't fail
        # Check that output mentions unsupported features
        assert "Unsupported" in result.stdout or "unsupported" in result.stdout.lower()
        assert "agents" in result.stdout.lower()

    def test_explain_supported_spec(self, cli_runner: CliRunner, multi_step_chain_yaml: Path):
        """Test explain command for supported spec."""
        result = cli_runner.invoke(app, ["explain", str(multi_step_chain_yaml)])

        assert result.exit_code == 0
        assert "MVP Compatible" in result.stdout or "supported" in result.stdout.lower()

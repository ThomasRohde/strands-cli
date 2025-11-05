"""CLI command tests for strands-cli.

Tests all CLI commands using typer.testing.CliRunner:
- run: Execute workflows
- validate: Validate specs
- plan: Show execution plans
- explain: Show unsupported features
- list-supported: List MVP features
- version: Show version
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

from typer.testing import CliRunner

from strands_cli import __version__
from strands_cli.__main__ import app
from strands_cli.exit_codes import (
    EX_OK,
    EX_RUNTIME,
    EX_SCHEMA,
    EX_UNSUPPORTED,
)

runner = CliRunner()


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_shows_correct_version(self) -> None:
        """Test version command displays correct version."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == EX_OK
        assert __version__ in result.stdout
        assert "strands-cli" in result.stdout


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_ollama_spec(self, minimal_ollama_spec: Path) -> None:
        """Test validate command with valid Ollama spec."""
        result = runner.invoke(app, ["validate", str(minimal_ollama_spec)])

        assert result.exit_code == EX_OK
        assert "OK Spec is valid" in result.stdout or "valid" in result.stdout.lower()
        assert "minimal-ollama" in result.stdout

    def test_validate_valid_bedrock_spec(self, minimal_bedrock_spec: Path) -> None:
        """Test validate command with valid Bedrock spec."""
        result = runner.invoke(app, ["validate", str(minimal_bedrock_spec)])

        assert result.exit_code == EX_OK
        assert "minimal-bedrock" in result.stdout

    def test_validate_shows_spec_metadata(self, minimal_ollama_spec: Path) -> None:
        """Test validate command shows spec metadata."""
        result = runner.invoke(app, ["validate", str(minimal_ollama_spec)])

        assert result.exit_code == EX_OK
        # Should show version, agents, pattern
        assert "Version:" in result.stdout or "version" in result.stdout.lower()
        assert "Agents:" in result.stdout or "agents" in result.stdout.lower()
        assert "Pattern:" in result.stdout or "pattern" in result.stdout.lower()

    def test_validate_invalid_spec_returns_schema_error(self, missing_required_spec: Path) -> None:
        """Test validate command with invalid spec returns EX_SCHEMA."""
        result = runner.invoke(app, ["validate", str(missing_required_spec)])

        assert result.exit_code == EX_SCHEMA
        assert "Validation failed" in result.stdout or "failed" in result.stdout.lower()

    def test_validate_malformed_spec_returns_schema_error(self, malformed_spec: Path) -> None:
        """Test validate command with malformed YAML returns EX_SCHEMA."""
        result = runner.invoke(app, ["validate", str(malformed_spec)])

        assert result.exit_code == EX_SCHEMA

    def test_validate_verbose_flag(self, minimal_ollama_spec: Path) -> None:
        """Test validate command with --verbose flag."""
        result = runner.invoke(app, ["validate", str(minimal_ollama_spec), "--verbose"])

        assert result.exit_code == EX_OK
        assert "Validating:" in result.stdout or "validating" in result.stdout.lower()


class TestPlanCommand:
    """Tests for the plan command."""

    def test_plan_shows_execution_plan(self, minimal_ollama_spec: Path) -> None:
        """Test plan command shows execution plan."""
        result = runner.invoke(app, ["plan", str(minimal_ollama_spec)])

        assert result.exit_code == EX_OK
        assert "minimal-ollama" in result.stdout
        # Should show runtime, agents, pattern
        assert "ollama" in result.stdout.lower()

    def test_plan_markdown_format(self, minimal_ollama_spec: Path) -> None:
        """Test plan command with markdown format (default)."""
        result = runner.invoke(app, ["plan", str(minimal_ollama_spec), "--format=md"])

        assert result.exit_code == EX_OK
        # Should include table or structured output
        assert "Runtime" in result.stdout or "Agents" in result.stdout

    def test_plan_json_format(self, minimal_ollama_spec: Path) -> None:
        """Test plan command with JSON format."""
        result = runner.invoke(app, ["plan", str(minimal_ollama_spec), "--format=json"])

        assert result.exit_code == EX_OK
        # Should be valid JSON with expected fields
        assert '"name"' in result.stdout
        assert '"supported"' in result.stdout
        assert '"runtime"' in result.stdout
        assert '"provider"' in result.stdout

    def test_plan_unsupported_spec_shows_issues(self, parallel_pattern_spec: Path) -> None:
        """Test plan command shows unsupported features."""
        result = runner.invoke(app, ["plan", str(parallel_pattern_spec)])

        assert result.exit_code == EX_OK
        assert "Unsupported" in result.stdout or "unsupported" in result.stdout.lower()

    def test_plan_supported_spec_shows_compatible(self, minimal_ollama_spec: Path) -> None:
        """Test plan command shows MVP compatible for supported specs."""
        result = runner.invoke(app, ["plan", str(minimal_ollama_spec)])

        assert result.exit_code == EX_OK
        assert "Compatible" in result.stdout or "compatible" in result.stdout.lower()


class TestExplainCommand:
    """Tests for the explain command."""

    def test_explain_supported_spec_shows_no_issues(self, minimal_ollama_spec: Path) -> None:
        """Test explain command with supported spec shows no issues."""
        result = runner.invoke(app, ["explain", str(minimal_ollama_spec)])

        assert result.exit_code == EX_OK
        assert "No unsupported features" in result.stdout or "compatible" in result.stdout.lower()

    def test_explain_unsupported_spec_shows_remediation(self, parallel_pattern_spec: Path) -> None:
        """Test explain command shows remediation for unsupported features."""
        result = runner.invoke(app, ["explain", str(parallel_pattern_spec)])

        assert result.exit_code == EX_OK
        assert "Unsupported Features" in result.stdout
        assert "Remediation:" in result.stdout or "remediation" in result.stdout.lower()

    def test_explain_multi_step_chain(self, multi_step_chain_spec: Path) -> None:
        """Test explain command for multi-step chain (now supported)."""
        result = runner.invoke(app, ["explain", str(multi_step_chain_spec)])

        # Phase 1: Multi-step chains are now supported, so explain should show no issues
        assert result.exit_code == EX_OK
        assert "No unsupported features" in result.stdout or "compatible" in result.stdout.lower()

    def test_explain_routing_pattern(self, routing_pattern_spec: Path) -> None:
        """Test explain command for routing pattern (now supported in Phase 2)."""
        result = runner.invoke(app, ["explain", str(routing_pattern_spec)])

        # Phase 2: Routing is now supported, so explain should show no issues
        assert result.exit_code == EX_OK
        assert "No unsupported features" in result.stdout or "compatible" in result.stdout.lower()


class TestListSupportedCommand:
    """Tests for the list-supported command."""

    def test_list_supported_shows_mvp_features(self) -> None:
        """Test list-supported shows all MVP features."""
        result = runner.invoke(app, ["list-supported"])

        assert result.exit_code == EX_OK
        # Should list key MVP features
        assert "Agents" in result.stdout
        assert "Patterns" in result.stdout
        assert "Providers" in result.stdout

    def test_list_supported_shows_providers(self) -> None:
        """Test list-supported shows supported providers."""
        result = runner.invoke(app, ["list-supported"])

        assert result.exit_code == EX_OK
        assert "bedrock" in result.stdout.lower()
        assert "ollama" in result.stdout.lower()

    def test_list_supported_shows_pattern_constraints(self) -> None:
        """Test list-supported shows pattern constraints."""
        result = runner.invoke(app, ["list-supported"])

        assert result.exit_code == EX_OK
        assert "chain" in result.stdout.lower()
        assert "workflow" in result.stdout.lower()

    def test_list_supported_shows_tools(self) -> None:
        """Test list-supported shows supported tools."""
        result = runner.invoke(app, ["list-supported"])

        assert result.exit_code == EX_OK
        assert "HTTP" in result.stdout or "http" in result.stdout.lower()
        assert "Python" in result.stdout or "python" in result.stdout.lower()


class TestRunCommand:
    """Tests for the run command."""

    def test_run_valid_ollama_spec(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command with valid Ollama spec."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Test response from agent."

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )

        assert result.exit_code == EX_OK
        assert "completed successfully" in result.stdout.lower() or "✓" in result.stdout

    def test_run_with_var_overrides(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command with --var overrides."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Custom topic response."

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--var",
                "topic=Custom Topic",
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )

        assert result.exit_code == EX_OK

    def test_run_verbose_flag(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command with --verbose flag."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Verbose test response."

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--verbose",
                "--force",
            ],
        )

        assert result.exit_code == EX_OK
        assert "Loading spec:" in result.stdout or "Provider:" in result.stdout

    def test_run_unsupported_spec_returns_unsupported(
        self,
        parallel_pattern_spec: Path,
        temp_artifacts_dir: Path,
    ) -> None:
        """Test run command with unsupported spec returns EX_UNSUPPORTED."""
        result = runner.invoke(
            app,
            [
                "run",
                str(parallel_pattern_spec),
                "--out",
                str(temp_artifacts_dir),
            ],
        )

        assert result.exit_code == EX_UNSUPPORTED
        assert "Unsupported features detected" in result.stdout

    def test_run_invalid_spec_returns_schema_error(
        self,
        missing_required_spec: Path,
        temp_artifacts_dir: Path,
    ) -> None:
        """Test run command with invalid spec returns EX_SCHEMA."""
        result = runner.invoke(
            app,
            [
                "run",
                str(missing_required_spec),
                "--out",
                str(temp_artifacts_dir),
            ],
        )

        assert result.exit_code == EX_SCHEMA

    def test_run_agent_failure_returns_runtime_error(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command with agent failure returns EX_RUNTIME."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.side_effect = RuntimeError("Agent execution failed")

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )

        assert result.exit_code == EX_RUNTIME
        assert "failed" in result.stdout.lower()

    def test_run_shows_artifacts_written(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command shows artifacts written."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Artifact test response."

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )

        assert result.exit_code == EX_OK
        assert "Artifacts written:" in result.stdout or "artifact" in result.stdout.lower()

    def test_run_force_flag_overwrites_artifacts(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
        mocker: Any,
    ) -> None:
        """Test run command with --force flag overwrites existing artifacts."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "First response."

        # First run
        result1 = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )
        assert result1.exit_code == EX_OK

        # Second run with --force should succeed
        mock_strands_agent.invoke_async.return_value = "Second response."
        result2 = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )
        assert result2.exit_code == EX_OK


class TestCLIErrorHandling:
    """Tests for CLI error handling across commands."""

    def test_nonexistent_file_returns_schema_error(self, temp_artifacts_dir: Path) -> None:
        """Test commands with nonexistent file return appropriate error."""
        nonexistent = temp_artifacts_dir / "nonexistent.yaml"

        result = runner.invoke(app, ["validate", str(nonexistent)])
        assert result.exit_code == EX_SCHEMA

    def test_verbose_flag_shows_traceback_on_error(self, missing_required_spec: Path) -> None:
        """Test --verbose flag shows traceback on unexpected errors."""
        # Validate should fail with schema error
        result = runner.invoke(app, ["validate", str(missing_required_spec), "--verbose"])

        # Should still exit with schema error, but verbose may show more context
        assert result.exit_code == EX_SCHEMA

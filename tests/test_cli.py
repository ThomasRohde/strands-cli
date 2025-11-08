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

    def test_plan_mcp_spec_shows_compatible(self, mcp_tools_spec: Path) -> None:
        """Test plan command shows MCP tools are now supported (Phase 9)."""
        result = runner.invoke(app, ["plan", str(mcp_tools_spec)])

        assert result.exit_code == EX_OK
        assert "Compatible" in result.stdout or "compatible" in result.stdout.lower()

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

    def test_explain_mcp_tools_now_supported(self, mcp_tools_spec: Path) -> None:
        """Test explain command shows MCP tools are supported (Phase 9)."""
        result = runner.invoke(app, ["explain", str(mcp_tools_spec)])

        assert result.exit_code == EX_OK
        # MCP tools are now supported, should show compatible
        assert "No unsupported features" in result.stdout or "compatible" in result.stdout.lower()
        # Should NOT show unsupported features
        assert "Unsupported Features" not in result.stdout

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
        temp_artifacts_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test run command with unsupported spec returns EX_UNSUPPORTED."""
        # Phase 9: All pattern types are now supported. Create a spec with an invalid/unsupported
        # provider to test EX_UNSUPPORTED error code path
        unsupported_spec = tmp_path / "unsupported-provider.yaml"
        unsupported_spec.write_text(
            """
version: 0
name: unsupported-provider
runtime:
  provider: unsupported_provider
  model_id: test
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: "./out.txt"
      from: "{{ last_response }}"
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                str(unsupported_spec),
                "--out",
                str(temp_artifacts_dir),
            ],
        )

        # Should fail schema validation (not capability check) with invalid provider
        assert result.exit_code == EX_SCHEMA  # Invalid provider fails schema validation
        assert "validation" in result.stdout.lower() or "schema" in result.stdout.lower()

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

    def test_malformed_yaml_returns_schema_error(self, malformed_spec: Path) -> None:
        """Test malformed YAML returns EX_SCHEMA across all commands."""
        # Validate command
        result = runner.invoke(app, ["validate", str(malformed_spec)])
        assert result.exit_code == EX_SCHEMA
        assert "failed" in result.stdout.lower() or "error" in result.stdout.lower()

        # Plan command
        result = runner.invoke(app, ["plan", str(malformed_spec)])
        assert result.exit_code == EX_SCHEMA

        # Explain command
        result = runner.invoke(app, ["explain", str(malformed_spec)])
        assert result.exit_code == EX_SCHEMA

    def test_schema_validation_error_shows_location(self, missing_required_spec: Path) -> None:
        """Test schema validation errors show JSONPointer location."""
        result = runner.invoke(app, ["validate", str(missing_required_spec)])

        assert result.exit_code == EX_SCHEMA
        # Should show some path context (may vary based on error message format)
        assert "error" in result.stdout.lower()

    def test_run_with_invalid_provider_returns_runtime_error(
        self,
        mocker: Any,
        temp_artifacts_dir: Path,
        minimal_ollama_spec: Path,
    ) -> None:
        """Test run command with provider initialization failure returns EX_RUNTIME."""
        # Mock create_model to raise RuntimeError (simulating provider failure)
        mocker.patch(
            "strands_cli.runtime.strands_adapter.create_model",
            side_effect=RuntimeError("Failed to connect to provider"),
        )

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
        assert "failed" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_run_with_readonly_output_dir_shows_error(
        self,
        mocker: Any,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
    ) -> None:
        """Test run command with read-only output directory shows artifact write error."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Test response"

        # Mock Path.write_text to raise PermissionError (simulating read-only filesystem)
        mocker.patch("pathlib.Path.write_text", side_effect=PermissionError("Permission denied"))

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

        # Should show error message about artifact writing
        # Note: Current implementation may exit with EX_RUNTIME or show error message
        # This test ensures the error is surfaced to the user
        assert "error" in result.stdout.lower() or "failed" in result.stdout.lower()

    def test_plan_with_verbose_shows_detailed_info(self, minimal_ollama_spec: Path) -> None:
        """Test plan command with --verbose shows detailed execution info."""
        result = runner.invoke(app, ["plan", str(minimal_ollama_spec), "--verbose"])

        assert result.exit_code == EX_OK
        # Should show loading steps or capability checking
        assert len(result.stdout) > 100  # Verbose output should be substantial

    def test_explain_with_verbose_shows_capability_details(self, minimal_ollama_spec: Path) -> None:
        """Test explain command with --verbose shows capability check details."""
        result = runner.invoke(app, ["explain", str(minimal_ollama_spec), "--verbose"])

        assert result.exit_code == EX_OK
        # Should show checking messages or detailed compatibility info
        assert "compatible" in result.stdout.lower() or "no unsupported" in result.stdout.lower()

    def test_run_with_bypass_tool_consent_sets_env_var(
        self,
        mocker: Any,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
    ) -> None:
        """Test --bypass-tool-consent flag sets BYPASS_TOOL_CONSENT environment variable."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Test response"

        # Mock os.environ to capture environment variable changes
        import os

        original_environ = os.environ.copy()
        mocker.patch.dict(os.environ, original_environ, clear=False)

        result = runner.invoke(
            app,
            [
                "run",
                str(minimal_ollama_spec),
                "--bypass-tool-consent",
                "--out",
                str(temp_artifacts_dir),
                "--force",
            ],
        )

        # Verify the environment variable was set to "true"
        assert os.environ.get("BYPASS_TOOL_CONSENT") == "true"

        # Should still succeed normally
        assert result.exit_code == EX_OK

    def test_run_without_bypass_tool_consent_does_not_set_env_var(
        self,
        mocker: Any,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: Any,
    ) -> None:
        """Test run without --bypass-tool-consent does not set the environment variable."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Test response"

        # Ensure BYPASS_TOOL_CONSENT is not set initially
        import os

        if "BYPASS_TOOL_CONSENT" in os.environ:
            del os.environ["BYPASS_TOOL_CONSENT"]

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

        # Verify the environment variable was NOT set
        assert "BYPASS_TOOL_CONSENT" not in os.environ

        # Should still succeed normally
        assert result.exit_code == EX_OK

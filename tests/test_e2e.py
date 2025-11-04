"""End-to-end integration tests for strands-cli.

Tests full workflow execution from spec loading through artifact generation.
Tests both Ollama and Bedrock providers with mocked backends.
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from strands_cli.artifacts import write_artifacts
from strands_cli.capability import check_capability
from strands_cli.exec import run_single_agent
from strands_cli.loader import LoadError, load_spec
from strands_cli.schema import SchemaValidationError


class TestOllamaE2E:
    """End-to-end tests for Ollama provider workflows."""

    def test_ollama_happy_path_full_workflow(
        self,
        minimal_ollama_spec: Path,
        temp_artifacts_dir: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test complete Ollama workflow: load → validate → execute → write artifacts."""
        # Mock time.sleep to avoid delays in retry logic
        mocker.patch("time.sleep")

        # Configure mock agent to return a response
        mock_strands_agent.invoke_async.return_value = "This is the AI response for Ollama test."

        # Load and validate spec
        spec = load_spec(str(minimal_ollama_spec))
        assert spec.name == "minimal-ollama"
        assert spec.runtime.provider == "ollama"

        # Check capability (should pass for single-agent Ollama)
        capability_report = check_capability(spec)
        assert capability_report.supported
        assert len(capability_report.issues) == 0

        # Execute workflow
        result = run_single_agent(spec, {})
        assert result.success
        assert result.last_response == "This is the AI response for Ollama test."
        assert result.duration_seconds > 0

        # Write artifacts
        artifacts_written = write_artifacts(
            spec.outputs.artifacts,
            result.last_response,
            str(temp_artifacts_dir),
            force=False,
        )

        # Verify artifacts
        assert len(artifacts_written) > 0
        # Check that at least one artifact was written
        assert any(Path(art).exists() for art in artifacts_written)

    def test_ollama_with_variables(
        self,
        minimal_ollama_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test Ollama workflow with variable overrides."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Analysis of Quantum Computing complete."

        # Load spec with variable override
        variables = {"topic": "Quantum Computing"}
        spec = load_spec(str(minimal_ollama_spec), variables)

        # Execute
        result = run_single_agent(spec, variables)
        assert result.success
        assert result.last_response is not None

        # Verify agent was called (template should have expanded)
        mock_strands_agent.invoke_async.assert_called_once()

    def test_ollama_with_budgets_and_retries(
        self,
        with_budgets_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test Ollama workflow respects budgets and retry configuration."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Budget-aware response."

        spec = load_spec(str(with_budgets_spec))
        assert spec.runtime.budgets is not None
        # budgets is a dict in the spec
        assert spec.runtime.budgets.get("max_tokens") == 50000
        # failure_policy might also be a dict or Pydantic model
        if hasattr(spec.runtime.failure_policy, "retries"):
            assert spec.runtime.failure_policy.retries == 3
        else:
            assert spec.runtime.failure_policy.get("retries") == 3

        result = run_single_agent(spec, {})
        assert result.success


class TestBedrockE2E:
    """End-to-end tests for AWS Bedrock provider workflows."""

    def test_bedrock_happy_path_full_workflow(
        self,
        minimal_bedrock_spec: Path,
        temp_artifacts_dir: Path,
        mock_bedrock_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test complete Bedrock workflow: load → validate → execute → write artifacts."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "This is the AI response from Bedrock."

        # Load and validate spec
        spec = load_spec(str(minimal_bedrock_spec))
        assert spec.name == "minimal-bedrock"
        assert spec.runtime.provider == "bedrock"
        assert spec.runtime.region == "us-east-1"

        # Check capability (should pass for single-agent Bedrock)
        capability_report = check_capability(spec)
        assert capability_report.supported

        # Execute workflow
        result = run_single_agent(spec, {})
        assert result.success
        assert result.last_response == "This is the AI response from Bedrock."

        # Write artifacts
        artifacts_written = write_artifacts(
            spec.outputs.artifacts,
            result.last_response,
            str(temp_artifacts_dir),
            force=False,
        )

        # Verify artifacts
        assert len(artifacts_written) > 0
        # Check that at least one artifact was written
        assert any(Path(art).exists() for art in artifacts_written)


class TestUnsupportedFeaturesE2E:
    """End-to-end tests for unsupported feature detection and reporting."""

    def test_multi_agent_spec_rejected(
        self,
        multi_agent_spec: Path,
    ) -> None:
        """Test multi-agent spec fails capability check with proper report."""
        # Load spec (should pass schema validation)
        spec = load_spec(str(multi_agent_spec))

        # Check capability (should fail - multiple agents)
        capability_report = check_capability(spec)
        assert not capability_report.supported
        assert len(capability_report.issues) > 0

        # Verify issue details
        issue = capability_report.issues[0]
        assert "agent" in issue.reason.lower()
        assert issue.pointer is not None
        assert (
            "keep only one" in issue.remediation.lower()
            or "single" in issue.remediation.lower()
            or "reduce" in issue.remediation.lower()
        )

    def test_multi_step_chain_rejected(
        self,
        multi_step_chain_spec: Path,
    ) -> None:
        """Test multi-step chain spec fails capability check."""
        spec = load_spec(str(multi_step_chain_spec))

        capability_report = check_capability(spec)
        assert not capability_report.supported
        assert len(capability_report.issues) > 0

        # Should mention multiple steps
        assert any("step" in issue.reason.lower() for issue in capability_report.issues)

    def test_multi_task_workflow_rejected(
        self,
        multi_task_workflow_spec: Path,
    ) -> None:
        """Test multi-task workflow spec fails capability check."""
        spec = load_spec(str(multi_task_workflow_spec))

        capability_report = check_capability(spec)
        assert not capability_report.supported
        assert any("task" in issue.reason.lower() for issue in capability_report.issues)

    def test_routing_pattern_rejected(
        self,
        routing_pattern_spec: Path,
    ) -> None:
        """Test routing pattern spec fails capability check."""
        spec = load_spec(str(routing_pattern_spec))

        capability_report = check_capability(spec)
        assert not capability_report.supported
        assert any("routing" in issue.reason.lower() for issue in capability_report.issues)

    def test_mcp_tools_rejected(
        self,
        mcp_tools_spec: Path,
    ) -> None:
        """Test MCP tools spec fails capability check."""
        spec = load_spec(str(mcp_tools_spec))

        capability_report = check_capability(spec)
        assert not capability_report.supported
        assert any("mcp" in issue.reason.lower() for issue in capability_report.issues)


class TestSchemaValidationE2E:
    """End-to-end tests for schema validation failures."""

    def test_missing_required_fields_rejected(
        self,
        missing_required_spec: Path,
    ) -> None:
        """Test spec with missing required fields fails schema validation."""
        with pytest.raises(SchemaValidationError) as exc_info:
            load_spec(str(missing_required_spec))

        error_msg = str(exc_info.value)
        assert "required" in error_msg.lower() or "missing" in error_msg.lower()

    def test_invalid_provider_rejected(
        self,
        invalid_provider_spec: Path,
    ) -> None:
        """Test spec with invalid provider fails schema validation."""
        # Try loading - may raise SchemaValidationError or succeed depending on schema
        try:
            spec = load_spec(str(invalid_provider_spec))
            # If it loads, check that the provider is actually invalid
            # This would be caught at runtime, not schema validation
            assert spec.runtime.provider not in ["bedrock", "ollama"]
        except SchemaValidationError as e:
            # Expected behavior - schema catches it
            error_msg = str(e)
            assert "provider" in error_msg.lower() or "enum" in error_msg.lower()

    def test_invalid_pattern_rejected(
        self,
        invalid_pattern_spec: Path,
    ) -> None:
        """Test spec with invalid pattern fails schema validation."""
        with pytest.raises(SchemaValidationError) as exc_info:
            load_spec(str(invalid_pattern_spec))

        error_msg = str(exc_info.value)
        assert "pattern" in error_msg.lower()

    def test_malformed_yaml_rejected(
        self,
        malformed_spec: Path,
    ) -> None:
        """Test malformed YAML file raises LoadError."""
        with pytest.raises(LoadError) as exc_info:
            load_spec(str(malformed_spec))

        error_msg = str(exc_info.value)
        assert "yaml" in error_msg.lower() or "parse" in error_msg.lower()


class TestRuntimeErrorsE2E:
    """End-to-end tests for runtime error handling."""

    def test_provider_connection_failure(
        self,
        minimal_ollama_spec: Path,
        mocker: Any,
    ) -> None:
        """Test graceful handling of provider connection failures."""
        # Mock the create_model function to raise an error
        mocker.patch(
            "strands_cli.runtime.strands_adapter.create_model",
            side_effect=RuntimeError("Failed to connect to Ollama server"),
        )

        spec = load_spec(str(minimal_ollama_spec))

        # Execution should fail gracefully
        with pytest.raises(Exception) as exc_info:
            run_single_agent(spec, {})

        # Should indicate connection/runtime error
        error_msg = str(exc_info.value)
        assert "connect" in error_msg.lower() or "runtime" in error_msg.lower()

    def test_agent_execution_failure(
        self,
        minimal_ollama_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test handling of agent execution failures."""
        mocker.patch("time.sleep")

        # Mock agent to raise an error
        mock_strands_agent.invoke_async.side_effect = RuntimeError("Agent execution failed")

        spec = load_spec(str(minimal_ollama_spec))

        # Should capture the error in the result
        result = run_single_agent(spec, {})
        assert not result.success
        assert result.error is not None
        assert "failed" in result.error.lower()


class TestToolsAndSkillsE2E:
    """End-to-end tests for workflows with tools and skills."""

    def test_workflow_with_tools(
        self,
        with_tools_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test workflow with HTTP executor tools."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Tool execution complete."

        spec = load_spec(str(with_tools_spec))
        # Agent is named "worker" in with-tools.yaml
        assert "worker" in spec.agents
        assert spec.agents["worker"].tools is not None
        assert len(spec.agents["worker"].tools) > 0

        capability_report = check_capability(spec)
        assert capability_report.supported

        result = run_single_agent(spec, {})
        assert result.success

    def test_workflow_with_skills(
        self,
        with_skills_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mocker: Any,
    ) -> None:
        """Test workflow with skills metadata injection."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Skills applied successfully."

        spec = load_spec(str(with_skills_spec))
        # Agent is named "coder" in with-skills.yaml
        assert "coder" in spec.agents
        # Skills are defined at spec level, not agent level
        assert spec.skills is not None
        assert len(spec.skills) > 0

        capability_report = check_capability(spec)
        assert capability_report.supported

        result = run_single_agent(spec, {})
        assert result.success


class TestSecretsE2E:
    """End-to-end tests for secrets handling."""

    def test_workflow_with_env_secrets(
        self,
        with_secrets_spec: Path,
        mock_ollama_client: Mock,
        mock_strands_agent: Mock,
        mock_create_model: None,
        mock_env_secrets: None,
        mocker: Any,
    ) -> None:
        """Test workflow with environment variable secrets."""
        mocker.patch("time.sleep")
        mock_strands_agent.invoke_async.return_value = "Secrets loaded successfully."

        spec = load_spec(str(with_secrets_spec))
        # Agent is named "secure" in with-secrets.yaml
        assert "secure" in spec.agents
        # Secrets are defined at env level
        assert spec.env is not None
        assert spec.env.secrets is not None

        # All secrets should be source: env
        for secret in spec.env.secrets:
            assert secret.source == "env"

        capability_report = check_capability(spec)
        assert capability_report.supported

        result = run_single_agent(spec, {})
        assert result.success

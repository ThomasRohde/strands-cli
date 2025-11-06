"""Unit tests for capability checking module."""

from pathlib import Path

import pytest

from strands_cli.capability.checker import ALLOWED_PYTHON_CALLABLES, check_capability
from strands_cli.loader.yaml_loader import LoadError, load_spec
from strands_cli.types import PatternType, ProviderType


@pytest.mark.unit
class TestCapabilityChecker:
    """Test capability checking for MVP compatibility."""

    def test_minimal_ollama_supported(self, minimal_ollama_spec: Path) -> None:
        """Test that minimal Ollama spec is supported."""
        spec = load_spec(minimal_ollama_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert len(report.issues) == 0
        assert report.normalized is not None
        assert report.normalized["provider"] == ProviderType.OLLAMA
        assert report.normalized["agent_id"] == "simple"

    def test_minimal_bedrock_supported(self, minimal_bedrock_spec: Path) -> None:
        """Test that minimal Bedrock spec is supported."""
        spec = load_spec(minimal_bedrock_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert len(report.issues) == 0
        assert report.normalized is not None
        assert report.normalized["provider"] == ProviderType.BEDROCK
        assert report.normalized["region"] == "us-east-1"

    def test_with_tools_supported(self, with_tools_spec: Path) -> None:
        """Test that spec with HTTP executors is supported."""
        spec = load_spec(with_tools_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert len(report.issues) == 0

    def test_multi_agent_chain_supported(self, multi_agent_chain_spec: Path) -> None:
        """Test that multi-agent chain spec is now supported in Phase 2."""
        spec = load_spec(multi_agent_chain_spec)
        report = check_capability(spec)

        # Phase 2: Multi-agent specs are now supported
        assert report.supported is True
        assert len(report.issues) == 0

    def test_multi_step_chain_supported(self, multi_step_chain_spec: Path) -> None:
        """Test that multi-step chain is now supported in Phase 1."""
        spec = load_spec(multi_step_chain_spec)
        report = check_capability(spec)

        # Phase 1: Multi-step chains are now supported
        assert report.supported is True
        assert len(report.issues) == 0

    def test_multi_task_workflow_supported(self, multi_task_workflow_spec: Path) -> None:
        """Test that multi-task workflow is now supported in Phase 1."""
        spec = load_spec(multi_task_workflow_spec)
        report = check_capability(spec)

        # Phase 1: Multi-task workflows are now supported
        assert report.supported is True
        assert len(report.issues) == 0

    def test_routing_pattern_supported(self, routing_pattern_spec: Path) -> None:
        """Test that routing pattern is now supported in Phase 2."""
        spec = load_spec(routing_pattern_spec)
        report = check_capability(spec)

        # Phase 2: Routing pattern is now supported
        assert report.supported is True
        assert len(report.issues) == 0

    def test_parallel_pattern_supported(self, parallel_pattern_spec: Path) -> None:
        """Test that parallel pattern is now supported (Phase 3)."""
        spec = load_spec(parallel_pattern_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert len(report.issues) == 0

    def test_mcp_tools_unsupported(self, mcp_tools_spec: Path) -> None:
        """Test that MCP tools are rejected."""
        spec = load_spec(mcp_tools_spec)
        report = check_capability(spec)

        assert report.supported is False

        # Find the MCP tools issue
        mcp_issue = next((issue for issue in report.issues if "/tools/mcp" in issue.pointer), None)
        assert mcp_issue is not None
        assert "MCP" in mcp_issue.reason
        assert "not supported" in mcp_issue.reason

    def test_bedrock_requires_region(self, temp_output_dir: Path) -> None:
        """Test that Bedrock without region is rejected."""
        spec_file = temp_output_dir / "bedrock-no-region.yaml"
        spec_content = """
version: 0
name: bedrock-no-region
runtime:
  provider: bedrock
  model_id: claude-3
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is False

        # Find the region issue
        region_issue = next(
            (issue for issue in report.issues if "/runtime/region" in issue.pointer), None
        )
        assert region_issue is not None
        assert "requires 'region'" in region_issue.reason

    def test_ollama_requires_host(self, temp_output_dir: Path) -> None:
        """Test that Ollama without host is rejected."""
        spec_file = temp_output_dir / "ollama-no-host.yaml"
        spec_content = """
version: 0
name: ollama-no-host
runtime:
  provider: ollama
  model_id: gpt-oss
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is False

        # Find the host issue
        host_issue = next(
            (issue for issue in report.issues if "/runtime/host" in issue.pointer), None
        )
        assert host_issue is not None
        assert "requires 'host'" in host_issue.reason

    def test_openai_supported_with_api_key(self, temp_output_dir: Path, monkeypatch) -> None:
        """Test that OpenAI spec passes when API key is set."""
        # Set API key in environment
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")

        spec_file = temp_output_dir / "openai-provider.yaml"
        spec_content = """
version: 0
name: openai-test
runtime:
  provider: openai
  model_id: gpt-4o-mini
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is True
        assert len(report.issues) == 0
        assert report.normalized is not None
        assert report.normalized["provider"] == ProviderType.OPENAI

    def test_openai_requires_api_key(self, temp_output_dir: Path, monkeypatch) -> None:
        """Test that OpenAI without API key is rejected."""
        # Ensure API key is not set
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        spec_file = temp_output_dir / "openai-no-key.yaml"
        spec_content = """
version: 0
name: openai-no-key
runtime:
  provider: openai
  model_id: gpt-4
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is False

        # Find the API key issue
        api_key_issue = next(
            (
                issue
                for issue in report.issues
                if "OPENAI_API_KEY" in issue.reason or "/runtime/provider" in issue.pointer
            ),
            None,
        )
        assert api_key_issue is not None
        assert "OPENAI_API_KEY" in api_key_issue.reason

    def test_unsupported_provider(self, temp_output_dir: Path) -> None:
        """Test that invalid provider raises LoadError during schema validation."""
        spec_file = temp_output_dir / "invalid-provider.yaml"
        spec_content = """
version: 0
name: invalid-provider-test
runtime:
  provider: fake_provider
  model_id: test-model
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        # Should raise LoadError because Pydantic enum validation rejects invalid provider
        with pytest.raises(LoadError, match="Failed to create typed Spec"):
            load_spec(spec_file)

    def test_secrets_source_env_only(self, with_secrets_spec: Path) -> None:
        """Test that env-sourced secrets are supported."""
        spec = load_spec(with_secrets_spec)
        report = check_capability(spec)

        # Should be supported since secrets use source: env
        assert report.supported is True
        assert len(report.issues) == 0

    def test_secrets_source_non_env_rejected(self, temp_output_dir: Path) -> None:
        """Test that non-env secret sources are rejected."""
        spec_file = temp_output_dir / "secrets-asm.yaml"
        spec_content = """
version: 0
name: secrets-asm
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
env:
  secrets:
    - source: secrets_manager
      key: API_KEY
      path: /my/secret
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
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is False

        # Find the secret source issue
        secret_issue = next(
            (issue for issue in report.issues if "/env/secrets/0/source" in issue.pointer), None
        )
        assert secret_issue is not None
        assert "not supported" in secret_issue.reason
        assert "env" in secret_issue.remediation

    def test_normalized_values_chain(self, minimal_ollama_spec: Path) -> None:
        """Test that normalized values are extracted for chain pattern."""
        spec = load_spec(minimal_ollama_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert report.normalized is not None
        assert report.normalized["agent_id"] == "simple"
        assert report.normalized["pattern_type"] == PatternType.CHAIN
        # Phase 1: task_input removed from normalized since executors handle it directly
        assert "provider" in report.normalized
        assert "model_id" in report.normalized
        assert report.normalized["provider"] == ProviderType.OLLAMA
        assert report.normalized["model_id"] == "gpt-oss"
        assert report.normalized["host"] == "http://localhost:11434"

    def test_normalized_values_workflow(self, temp_output_dir: Path) -> None:
        """Test that normalized values are extracted for workflow pattern."""
        spec_file = temp_output_dir / "workflow-test.yaml"
        spec_content = """
version: 0
name: workflow-test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
agents:
  worker:
    prompt: "Do work"
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: worker
        input: "Do the task"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is True
        assert report.normalized is not None
        assert report.normalized["agent_id"] == "worker"
        assert report.normalized["pattern_type"] == PatternType.WORKFLOW
        # Phase 1: task_input removed from normalized since executors handle it directly
        assert "provider" in report.normalized
        assert "model_id" in report.normalized

    def test_no_normalized_values_when_unsupported(self, parallel_pattern_spec: Path) -> None:
        """Test that normalized values are None when spec is unsupported."""
        spec = load_spec(parallel_pattern_spec)
        report = check_capability(spec)

        assert report.supported is True
        assert report.normalized is not None

    def test_jsonpointer_accuracy(self, mcp_tools_spec: Path) -> None:
        """Test that JSONPointer paths are accurate."""
        # Use MCP tools spec since it's unsupported
        spec = load_spec(mcp_tools_spec)
        report = check_capability(spec)

        # All issues should have valid JSONPointer format
        for issue in report.issues:
            assert issue.pointer.startswith("/")
            assert "pointer" in issue.model_dump()

    def test_remediation_provided(self, mcp_tools_spec: Path) -> None:
        """Test that all issues include remediation guidance."""
        spec = load_spec(mcp_tools_spec)
        report = check_capability(spec)

        for issue in report.issues:
            assert issue.remediation
            assert len(issue.remediation) > 0

    def test_allowed_python_callables_list(self) -> None:
        """Test that allowed Python callables are defined."""
        assert "strands_tools.http_request.http_request" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.file_read.file_read" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.file_write.file_write" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.calculator.calculator" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.current_time.current_time" in ALLOWED_PYTHON_CALLABLES
        # Also check old format (backward compatibility)
        assert "strands_tools.http_request" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.file_read" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.file_write" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.calculator" in ALLOWED_PYTHON_CALLABLES
        assert "strands_tools.current_time" in ALLOWED_PYTHON_CALLABLES
        assert len(ALLOWED_PYTHON_CALLABLES) == 10  # 5 new format + 5 old format

    def test_empty_chain_steps_rejected(self, temp_output_dir: Path) -> None:
        """Test that chain with empty steps is rejected at schema validation."""
        from strands_cli.schema.validator import SchemaValidationError

        spec_file = temp_output_dir / "chain-empty.yaml"
        spec_content = """
version: 0
name: chain-empty
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps: []
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        # Should fail at schema validation (minItems=1)
        with pytest.raises(SchemaValidationError) as exc_info:
            load_spec(spec_file)

        error_text = str(exc_info.value)
        assert "pattern/config" in error_text or "steps" in error_text

    def test_empty_workflow_tasks_rejected(self, temp_output_dir: Path) -> None:
        """Test that workflow with empty tasks is rejected at schema validation."""
        from strands_cli.schema.validator import SchemaValidationError

        spec_file = temp_output_dir / "workflow-empty.yaml"
        spec_content = """
version: 0
name: workflow-empty
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
agents:
  test:
    prompt: "Test"
pattern:
  type: workflow
  config:
    tasks: []
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        # Should fail at schema validation (minItems=1)
        with pytest.raises(SchemaValidationError) as exc_info:
            load_spec(spec_file)

        error_text = str(exc_info.value)
        assert "pattern/config" in error_text or "tasks" in error_text

    def test_tool_overrides_validation(self, temp_output_dir: Path) -> None:
        """Test that tool_overrides are validated against available tools."""
        spec_file = temp_output_dir / "invalid-tool-override.yaml"
        spec_content = """
version: 0
name: invalid-tool-override
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
tools:
  http_executors:
    - id: my_api
      base_url: http://example.com
agents:
  test:
    prompt: "Test"
    tools: [my_api]
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Step 1"
      - agent: test
        input: "Step 2"
        tool_overrides: [nonexistent_tool]
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)
        report = check_capability(spec)

        assert report.supported is False

        # Find the tool override issue
        tool_issue = next(
            (issue for issue in report.issues if "tool_overrides" in issue.pointer), None
        )
        assert tool_issue is not None
        assert "nonexistent_tool" in tool_issue.reason
        assert "undefined tool" in tool_issue.reason

    def test_max_parallel_field_preserved(self, temp_output_dir: Path) -> None:
        """Test that max_parallel from runtime is properly preserved."""
        spec_file = temp_output_dir / "max-parallel.yaml"
        spec_content = """
version: 0
name: max-parallel
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
  max_parallel: 3
agents:
  test:
    prompt: "Test"
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: test
        input: "Task 1"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")
        spec = load_spec(spec_file)

        # Verify max_parallel is preserved in the Runtime model
        assert spec.runtime.max_parallel == 3

"""Integration tests for python_exec tool in real workflows.

Tests end-to-end execution of workflows using the python_exec native tool.
"""

from pathlib import Path

import pytest

from strands_cli.loader import load_spec
from strands_cli.types import PatternType


class TestPythonExecIntegration:
    """Integration tests for python_exec in workflows."""

    @pytest.mark.asyncio
    async def test_python_exec_in_single_agent_workflow(
        self, tmp_path: Path, mock_create_model: None
    ) -> None:
        """Test python_exec tool in a single-agent workflow."""
        # Create a minimal spec with python_exec tool
        spec_content = """
version: 0
name: python-exec-test
description: Test python_exec tool integration

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  calculator:
    prompt: |
      You are a calculator assistant. Use the python_exec tool to perform
      calculations. Just execute the code and return the result.

pattern:
  type: chain
  config:
    steps:
      - agent: calculator
        input: "Calculate 2 + 2"

tools:
  python:
    - python_exec

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "python_exec_test.yaml"
        spec_file.write_text(spec_content)

        # Load and run the spec
        spec = load_spec(str(spec_file))
        assert spec.pattern.type == PatternType.CHAIN

        # Verify tool is in spec
        assert spec.tools is not None
        assert spec.tools.python is not None
        assert len(spec.tools.python) == 1
        assert spec.tools.python[0].callable == "python_exec"

        # Run the workflow (mock will return success)
        from strands_cli.exec.chain import run_chain
        result = await run_chain(spec, {})

        assert result is not None
        assert result.last_response is not None

    @pytest.mark.asyncio
    async def test_python_exec_with_full_path(
        self, tmp_path: Path, mock_create_model: None
    ) -> None:
        """Test python_exec using full path instead of short ID."""
        spec_content = """
version: 0
name: python-exec-fullpath
description: Test python_exec with full module path

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  calculator:
    prompt: "Calculate something"

pattern:
  type: chain
  config:
    steps:
      - agent: calculator
        input: "Test"

tools:
  python:
    - strands_cli.tools.python_exec

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "python_exec_fullpath.yaml"
        spec_file.write_text(spec_content)

        spec = load_spec(str(spec_file))

        # Verify tool path
        assert spec.tools.python[0].callable == "strands_cli.tools.python_exec"

        # Run should succeed
        from strands_cli.exec.chain import run_chain
        result = await run_chain(spec, {})
        assert result is not None

    def test_python_exec_in_spec_validation(self, tmp_path: Path) -> None:
        """Test that python_exec passes capability validation."""
        from strands_cli.capability import check_capability

        spec_content = """
version: 0
name: python-exec-validation
description: Test validation

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  test_agent:
    prompt: "Test"

pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "Test"

tools:
  python:
    - python_exec

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "validate_test.yaml"
        spec_file.write_text(spec_content)

        spec = load_spec(str(spec_file))
        report = check_capability(spec)

        # Should be supported (no issues)
        assert report.supported is True
        assert len(report.issues) == 0

    def test_invalid_tool_rejected(self, tmp_path: Path) -> None:
        """Test that invalid/unknown tools are rejected."""
        from strands_cli.capability import check_capability

        spec_content = """
version: 0
name: invalid-tool
description: Test invalid tool rejection

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  test_agent:
    prompt: "Test"

pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "Test"

tools:
  python:
    - nonexistent_tool

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "invalid_tool.yaml"
        spec_file.write_text(spec_content)

        spec = load_spec(str(spec_file))
        report = check_capability(spec)

        # Should be unsupported
        assert report.supported is False
        assert len(report.issues) > 0
        # Check that error mentions the tool is not in allowlist
        assert any("allowlist" in issue.reason.lower() for issue in report.issues)

    def test_python_exec_with_legacy_format(self, tmp_path: Path) -> None:
        """Test that legacy strands_tools.python_exec format works via registry."""
        from strands_cli.capability import check_capability

        spec_content = """
version: 0
name: python-exec-legacy
description: Test legacy format support

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  test_agent:
    prompt: "Test"

pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "Test"

tools:
  python:
    - strands_tools.python_exec

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "legacy_format.yaml"
        spec_file.write_text(spec_content)

        spec = load_spec(str(spec_file))
        report = check_capability(spec)

        # Should be supported (registry provides backward compat)
        assert report.supported is True
        assert len(report.issues) == 0

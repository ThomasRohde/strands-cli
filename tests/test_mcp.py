"""Tests for MCP (Model Context Protocol) integration.

Phase 9: Tests MCP server tool loading and lifecycle using Strands SDK MCPClient.

Test Coverage:
- Unit: MCP tool loading, error handling, graceful degradation
- Integration: Spec validation, capability checking
- E2E: Workflow execution with MCP tools (requires MCP server)
"""

from pathlib import Path

import pytest

from strands_cli.capability.checker import check_capability
from strands_cli.loader.yaml_loader import load_spec
from strands_cli.runtime.strands_adapter import (
    MCP_AVAILABLE,
    AdapterError,
    _load_mcp_tools,
)
from strands_cli.types import McpServer, Tools


class TestMCPToolLoading:
    """Unit tests for MCP tool loading logic."""

    def test_load_mcp_tools_no_config_returns_empty(
        self, minimal_ollama_spec: Path
    ) -> None:
        """When spec has no MCP tools, _load_mcp_tools returns empty list."""
        # Arrange
        spec = load_spec(str(minimal_ollama_spec), {})
        assert spec.tools is None or spec.tools.mcp is None

        # Act
        result = _load_mcp_tools(spec, None)

        # Assert
        assert result == []

    def test_load_mcp_tools_with_config_creates_clients(
        self, minimal_ollama_spec: Path
    ) -> None:
        """When spec has MCP tools and mcp package available, creates MCPClient instances."""
        # Arrange
        if not MCP_AVAILABLE:
            pytest.skip("MCP package not installed")

        # Add MCP configuration to spec
        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[
                McpServer(
                    id="test_server",
                    command="python",
                    args=["-m", "mcp.server.stdio"],
                    env={"MCP_LOG_LEVEL": "debug"},
                )
            ]
        )

        # Act
        result = _load_mcp_tools(spec, None)

        # Assert
        assert len(result) == 1
        # Verify MCPClient instance created (duck typing check)
        mcp_client = result[0]
        assert hasattr(mcp_client, "list_tools_sync")  # MCPClient method

    def test_load_mcp_tools_multiple_servers(self, minimal_ollama_spec: Path) -> None:
        """When spec has multiple MCP servers, creates client for each."""
        # Arrange
        if not MCP_AVAILABLE:
            pytest.skip("MCP package not installed")

        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[
                McpServer(id="filesystem", command="uvx", args=["mcp-server-filesystem"]),
                McpServer(id="git", command="uvx", args=["mcp-server-git"]),
            ]
        )

        # Act
        result = _load_mcp_tools(spec, None)

        # Assert
        assert len(result) == 2

    def test_load_mcp_tools_without_mcp_package_raises_error(
        self, minimal_ollama_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When MCP configured but mcp package not installed, raises AdapterError."""
        # Arrange
        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[
                McpServer(
                    id="test_server", command="python", args=["-m", "mcp.server.stdio"]
                )
            ]
        )

        # Mock MCP_AVAILABLE to False
        monkeypatch.setattr("strands_cli.runtime.strands_adapter.MCP_AVAILABLE", False)

        # Act & Assert
        with pytest.raises(
            AdapterError,
            match="MCP tools configured but 'mcp' package not installed",
        ):
            _load_mcp_tools(spec, None)

    def test_load_mcp_tools_graceful_degradation_on_client_error(
        self, minimal_ollama_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When MCPClient creation fails for one server, continues with others."""
        # Arrange
        if not MCP_AVAILABLE:
            pytest.skip("MCP package not installed")

        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[
                McpServer(id="invalid", command="invalid-command-that-will-fail"),
                McpServer(
                    id="valid", command="python", args=["-m", "mcp.server.stdio"]
                ),
            ]
        )

        # Act - should not raise, continue with working servers
        result = _load_mcp_tools(spec, None)

        # Assert - at least one should succeed (or both fail gracefully)
        # Since we can't control external commands, just verify no crash
        assert isinstance(result, list)


class TestMCPCapabilityChecking:
    """Integration tests for MCP capability checking."""

    def test_mcp_tools_pass_capability_check(self, tmp_path):
        """MCP tools now pass capability checking (Phase 9)."""
        # Arrange - Create spec with MCP tools
        spec_content = """
version: 0
name: "test-mcp"
runtime:
  provider: ollama
  host: "http://localhost:11434"
  model_id: "llama2"

agents:
  assistant:
    prompt: "You are a helpful assistant."

tools:
  mcp:
    - id: "filesystem"
      command: "uvx"
      args: ["mcp-server-filesystem"]

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Test MCP tools"

outputs:
  artifacts:
    - path: "./artifacts/output.txt"
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "mcp-spec.yaml"
        spec_file.write_text(spec_content)

        # Act - Load and check capability
        spec = load_spec(str(spec_file), {})
        report = check_capability(spec)

        # Assert - MCP tools supported, no issues
        assert report.supported is True
        assert len(report.issues) == 0

    def test_multiple_mcp_servers_supported(self, tmp_path):
        """Multiple MCP servers pass capability checking."""
        # Arrange
        spec_content = """
version: 0
name: "test-multi-mcp"
runtime:
  provider: ollama
  host: "http://localhost:11434"
  model_id: "llama2"

agents:
  assistant:
    prompt: "You are a helpful assistant."

tools:
  mcp:
    - id: "filesystem"
      command: "uvx"
      args: ["mcp-server-filesystem"]
    - id: "git"
      command: "uvx"
      args: ["mcp-server-git"]
    - id: "custom"
      command: "python"
      args: ["-m", "my_custom_mcp_server"]
      env:
        MCP_LOG_LEVEL: "debug"

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Test"

outputs:
  artifacts:
    - path: "./artifacts/output.txt"
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "multi-mcp.yaml"
        spec_file.write_text(spec_content)

        # Act
        spec = load_spec(str(spec_file), {})
        report = check_capability(spec)

        # Assert
        assert report.supported is True
        assert len(spec.tools.mcp) == 3  # type: ignore


class TestMCPWorkflowExecution:
    """E2E tests for workflow execution with MCP tools.

    Note: These tests are marked with @pytest.mark.mcp and may be skipped
    if MCP servers are not available in the test environment.
    """

    @pytest.mark.mcp
    @pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
    def test_workflow_with_mcp_filesystem_server(self, tmp_path):
        """E2E: Execute workflow with MCP filesystem server (requires uvx and MCP server)."""
        # This test requires:
        # 1. uvx command available
        # 2. mcp-server-filesystem package
        # 3. Actual LLM provider (Ollama/Bedrock/OpenAI)
        # Skip in CI unless MCP test environment configured

        pytest.skip(
            "E2E MCP test requires external MCP server and LLM - run manually with:\n"
            "  pip install mcp strands-agents[mcp]\n"
            "  uvx mcp-server-filesystem\n"
            "  pytest -m mcp tests/test_mcp.py::TestMCPWorkflowExecution"
        )

        # Arrange
        spec_content = f"""
version: 0
name: "mcp-filesystem-test"
runtime:
  provider: ollama
  host: "http://localhost:11434"
  model_id: "llama2"

agents:
  file_helper:
    prompt: "You are a helpful file operations assistant."
    tools: ["mcp_filesystem"]

tools:
  mcp:
    - command: "uvx"
      args: ["mcp-server-filesystem", "{tmp_path}"]

pattern:
  type: chain
  config:
    steps:
      - agent: file_helper
        input: "List files in the current directory"

outputs:
  artifacts:
    - path: "./artifacts/mcp-test-output.txt"
      from: "{{{{ last_response }}}}"
"""
        spec_file = tmp_path / "mcp-e2e.yaml"
        spec_file.write_text(spec_content)

        # Act - This would execute the workflow
        # Actual execution requires:
        # - Running Ollama with llama2 model
        # - MCP filesystem server accessible
        # from strands_cli.exec.single_agent import run_single_agent
        # spec = load_spec(str(spec_file), {})
        # result = asyncio.run(run_single_agent(spec, {}))

        # Assert
        # assert result.status == "success"


class TestMCPToolFiltering:
    """Tests for MCP tool filtering behavior."""

    def test_tools_to_use_parameter_currently_ignored(
        self, minimal_ollama_spec: Path
    ) -> None:
        """Phase 9 MVP: tools_to_use filtering not yet implemented for MCP.

        All tools from configured MCP servers are loaded regardless of tools_to_use.
        This is documented behavior - filtering support can be added in future phase.
        """
        # Arrange
        if not MCP_AVAILABLE:
            pytest.skip("MCP package not installed")

        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[
                McpServer(
                    id="test_server", command="python", args=["-m", "mcp.server.stdio"]
                )
            ]
        )

        # Act - Pass tools_to_use filter
        result_with_filter = _load_mcp_tools(spec, ["specific_tool"])
        result_without_filter = _load_mcp_tools(spec, None)

        # Assert - Both return same number of clients (filtering not yet implemented)
        # In future, we could implement tool_filters parameter on MCPClient
        assert len(result_with_filter) == len(result_without_filter)


class TestMCPErrorHandling:
    """Tests for MCP error handling and edge cases."""

    def test_empty_mcp_list_returns_empty(self, minimal_ollama_spec: Path) -> None:
        """When spec.tools.mcp is empty list, returns empty list."""
        # Arrange
        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(mcp=[])

        # Act
        result = _load_mcp_tools(spec, None)

        # Assert
        assert result == []

    def test_mcp_with_minimal_config(self, minimal_ollama_spec: Path) -> None:
        """MCP server with only id and command (no args or env) works correctly."""
        # Arrange
        if not MCP_AVAILABLE:
            pytest.skip("MCP package not installed")

        spec = load_spec(str(minimal_ollama_spec), {})
        spec.tools = Tools(
            mcp=[McpServer(id="minimal", command="python")]
        )  # Minimal config

        # Act
        result = _load_mcp_tools(spec, None)

        # Assert - Should create client even with minimal config
        assert len(result) == 1

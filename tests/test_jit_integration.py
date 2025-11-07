"""Integration tests for JIT retrieval tools in workflows.

Tests that JIT tools are properly auto-injected via context_policy.retrieval
and work correctly in actual workflow execution.
"""

import pytest
from pydantic import ValidationError

from strands_cli.types import (
    Agent as AgentConfig,
)
from strands_cli.types import (
    ChainStep,
    ContextPolicy,
    Pattern,
    PatternConfig,
    PatternType,
    ProviderType,
    PythonTool,
    Retrieval,
    Runtime,
    Spec,
    Tools,
)


class TestJITToolsAutoInjection:
    """Test auto-injection of JIT tools via context_policy.retrieval."""

    def test_jit_tools_added_to_agent(self, mocker):
        """JIT tools should be loaded and added to agent's tool list."""
        from strands_cli.runtime.strands_adapter import build_agent

        # Mock the model and Agent constructor
        mock_model = mocker.MagicMock()
        mocker.patch("strands_cli.runtime.strands_adapter.create_model", return_value=mock_model)
        mock_agent_class = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        # Create spec with JIT tools in context_policy
        spec = Spec(
            version=0,
            name="test-jit",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": AgentConfig(prompt="Test prompt")},
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="agent1")]),
            ),
            context_policy=ContextPolicy(
                retrieval=Retrieval(jit_tools=["grep", "head", "tail", "search"])
            ),
        )

        agent_config = AgentConfig(prompt="Test prompt")

        # Build the agent
        build_agent(spec, "agent1", agent_config)

        # Verify Agent was constructed with tools
        assert mock_agent_class.called
        call_kwargs = mock_agent_class.call_args[1]
        tools = call_kwargs.get("tools")
        assert tools is not None
        assert len(tools) == 4  # All 4 JIT tools should be loaded

        # Verify tools have TOOL_SPEC (characteristic of native tools)
        for tool in tools:
            assert hasattr(tool, "TOOL_SPEC")

    def test_jit_tools_merged_with_existing_tools(self, mocker):
        """JIT tools should be merged with agent's existing tools."""
        from strands_cli.runtime.strands_adapter import build_agent

        mock_model = mocker.MagicMock()
        mocker.patch("strands_cli.runtime.strands_adapter.create_model", return_value=mock_model)
        mock_agent_class = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        # Mock load_python_callable to return a mock tool
        mock_python_tool = mocker.MagicMock()
        mock_python_tool.__name__ = "python_exec"
        mocker.patch(
            "strands_cli.runtime.strands_adapter.load_python_callable",
            return_value=mock_python_tool,
        )

        spec = Spec(
            version=0,
            name="test-jit-merge",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": AgentConfig(prompt="Test", tools=["python_exec"])},
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="agent1")]),
            ),
            tools=Tools(python=[PythonTool(callable="python_exec")]),
            context_policy=ContextPolicy(retrieval=Retrieval(jit_tools=["grep", "head"])),
        )

        build_agent(spec, "agent1", spec.agents["agent1"])

        # Should have python_exec (1) + JIT tools (2) = 3 total
        assert mock_agent_class.called
        call_kwargs = mock_agent_class.call_args[1]
        tools = call_kwargs.get("tools")
        assert tools is not None
        assert len(tools) == 3

    def test_jit_tools_no_duplicates(self, mocker):
        """Should not add duplicate tools if already in agent's tool list."""
        from strands_cli.runtime.strands_adapter import build_agent

        mock_model = mocker.MagicMock()
        mocker.patch("strands_cli.runtime.strands_adapter.create_model", return_value=mock_model)
        mock_agent_class = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        spec = Spec(
            version=0,
            name="test-no-dupes",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": AgentConfig(prompt="Test", tools=["grep", "head"])},
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="agent1")]),
            ),
            context_policy=ContextPolicy(retrieval=Retrieval(jit_tools=["grep", "head"])),
        )

        build_agent(spec, "agent1", spec.agents["agent1"])

        # Should only load each tool once (deduplication)
        assert mock_agent_class.called
        call_kwargs = mock_agent_class.call_args[1]
        tools = call_kwargs.get("tools")
        assert tools is not None
        assert len(tools) == 2  # Only grep and head, no duplicates

    def test_no_jit_tools_without_context_policy(self, mocker):
        """Should not add JIT tools if context_policy is not set."""
        from strands_cli.runtime.strands_adapter import build_agent

        mock_model = mocker.MagicMock()
        mocker.patch("strands_cli.runtime.strands_adapter.create_model", return_value=mock_model)
        mock_agent_class = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        spec = Spec(
            version=0,
            name="test-no-context",
            runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
            agents={"agent1": AgentConfig(prompt="Test")},
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="agent1")]),
            ),
            # No context_policy
        )

        build_agent(spec, "agent1", spec.agents["agent1"])

        # Should not load any JIT tools
        assert mock_agent_class.called
        call_kwargs = mock_agent_class.call_args[1]
        tools = call_kwargs.get("tools")
        # Tools should be None or empty list
        assert tools is None or len(tools) == 0


class TestJITToolsRegistry:
    """Test that JIT tools are properly registered and discoverable."""

    def test_jit_tools_in_registry(self):
        """All 4 JIT tools should be in the registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "grep" in allowlist
        assert "head" in allowlist
        assert "tail" in allowlist
        assert "search" in allowlist

    def test_jit_tool_modules_loadable(self):
        """All JIT tools should be loadable from registry."""
        import importlib

        from strands_cli.tools import get_registry

        registry = get_registry()

        # Test grep tool
        grep_info = registry.get("grep")
        assert grep_info is not None
        grep_module = importlib.import_module(grep_info.module_path)
        assert hasattr(grep_module, "TOOL_SPEC")
        assert grep_module.TOOL_SPEC["name"] == "grep"

        # Test head tool
        head_info = registry.get("head")
        assert head_info is not None
        head_module = importlib.import_module(head_info.module_path)
        assert hasattr(head_module, "TOOL_SPEC")
        assert head_module.TOOL_SPEC["name"] == "head"

        # Test tail tool
        tail_info = registry.get("tail")
        assert tail_info is not None
        tail_module = importlib.import_module(tail_info.module_path)
        assert hasattr(tail_module, "TOOL_SPEC")
        assert tail_module.TOOL_SPEC["name"] == "tail"

        # Test search tool
        search_info = registry.get("search")
        assert search_info is not None
        search_module = importlib.import_module(search_info.module_path)
        assert hasattr(search_module, "TOOL_SPEC")
        assert search_module.TOOL_SPEC["name"] == "search"


class TestRetrievalModelValidation:
    """Test Retrieval model field validation."""

    def test_valid_jit_tool_names(self):
        """Should accept valid tool names."""
        retrieval = Retrieval(jit_tools=["grep", "head", "tail", "search", "my-tool", "my_tool"])
        assert len(retrieval.jit_tools) == 6

    def test_invalid_jit_tool_names(self):
        """Should reject invalid tool names with special characters."""
        with pytest.raises(ValidationError, match="Invalid JIT tool ID"):
            Retrieval(jit_tools=["grep", "bad;tool"])

        with pytest.raises(ValidationError):
            Retrieval(jit_tools=["grep", "bad$tool"])

        with pytest.raises(ValidationError):
            Retrieval(jit_tools=["grep", "bad tool"])  # space

    def test_empty_jit_tools_list(self):
        """Should accept empty jit_tools list."""
        retrieval = Retrieval(jit_tools=[])
        assert retrieval.jit_tools == []

    def test_none_jit_tools(self):
        """Should accept None for jit_tools."""
        retrieval = Retrieval(jit_tools=None)
        assert retrieval.jit_tools is None

    def test_mcp_servers_field_present(self):
        """Should have mcp_servers field for Phase 9."""
        retrieval = Retrieval(mcp_servers=["server1", "server2"])
        assert retrieval.mcp_servers == ["server1", "server2"]

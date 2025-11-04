"""Unit tests for runtime providers, strands adapter, and tools."""

from unittest.mock import Mock

import pytest

from strands_cli.runtime.providers import (
    ProviderError,
    create_bedrock_model,
    create_model,
    create_ollama_model,
)
from strands_cli.runtime.strands_adapter import (
    AdapterError,
    build_agent,
    build_system_prompt,
)
from strands_cli.runtime.tools import (
    HttpExecutorAdapter,
    ToolError,
    load_python_callable,
)
from strands_cli.types import (
    Agent as AgentConfig,
)
from strands_cli.types import (
    HttpExecutor,
    ProviderType,
    PythonTool,
    Runtime,
    Skill,
    Tools,
)

# ============================================================================
# Providers Tests
# ============================================================================


class TestBedrockModelCreation:
    """Tests for create_bedrock_model."""

    def test_creates_bedrock_model_with_region(self, mocker):
        """Should create BedrockModel with valid region."""
        # Mock BedrockModel (it creates boto3 client internally)
        mock_bedrock_model_cls = mocker.patch("strands_cli.runtime.providers.BedrockModel")
        mock_model = Mock()
        mock_bedrock_model_cls.return_value = mock_model

        runtime = Runtime(
            provider=ProviderType.BEDROCK,
            region="us-east-1",
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        )

        result = create_bedrock_model(runtime)

        # Verify BedrockModel created with correct model_id
        mock_bedrock_model_cls.assert_called_once_with(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        )

        assert result == mock_model

    def test_uses_default_model_id_if_not_specified(self, mocker):
        """Should use default model ID when not provided."""
        mock_bedrock_model_cls = mocker.patch("strands_cli.runtime.providers.BedrockModel")

        runtime = Runtime(
            provider=ProviderType.BEDROCK,
            region="us-west-2",
        )

        create_bedrock_model(runtime)

        # Check that default model ID was used
        call_kwargs = mock_bedrock_model_cls.call_args[1]
        assert call_kwargs["model_id"] == "us.anthropic.claude-3-sonnet-20240229-v1:0"

    def test_raises_error_when_region_missing(self):
        """Should raise ProviderError when region is None."""
        runtime = Runtime(provider=ProviderType.BEDROCK)

        with pytest.raises(ProviderError, match=r"Bedrock provider requires runtime\.region"):
            create_bedrock_model(runtime)

    def test_raises_error_on_bedrock_model_failure(self, mocker):
        """Should raise ProviderError when BedrockModel init fails."""
        mocker.patch(
            "strands_cli.runtime.providers.BedrockModel",
            side_effect=Exception("Invalid model ID"),
        )

        runtime = Runtime(provider=ProviderType.BEDROCK, region="us-east-1")

        with pytest.raises(ProviderError, match="Failed to create BedrockModel"):
            create_bedrock_model(runtime)


class TestOllamaModelCreation:
    """Tests for create_ollama_model."""

    def test_creates_ollama_model_with_host(self, mocker):
        """Should create OllamaModel with valid host."""
        mock_ollama_model_cls = mocker.patch("strands_cli.runtime.providers.OllamaModel")
        mock_model = Mock()
        mock_ollama_model_cls.return_value = mock_model

        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="llama3",
        )

        result = create_ollama_model(runtime)

        # Verify OllamaModel created
        mock_ollama_model_cls.assert_called_once_with(
            host="http://localhost:11434",
            model_id="llama3",
        )

        assert result == mock_model

    def test_uses_default_model_id_if_not_specified(self, mocker):
        """Should use default model ID when not provided."""
        mock_ollama_model_cls = mocker.patch("strands_cli.runtime.providers.OllamaModel")

        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
        )

        create_ollama_model(runtime)

        # Check that default model ID was used
        call_kwargs = mock_ollama_model_cls.call_args[1]
        assert call_kwargs["model_id"] == "gpt-oss"

    def test_raises_error_when_host_missing(self):
        """Should raise ProviderError when host is None."""
        runtime = Runtime(provider=ProviderType.OLLAMA)

        with pytest.raises(ProviderError, match=r"Ollama provider requires runtime\.host"):
            create_ollama_model(runtime)

    def test_raises_error_on_ollama_model_failure(self, mocker):
        """Should raise ProviderError when OllamaModel init fails."""
        mocker.patch(
            "strands_cli.runtime.providers.OllamaModel",
            side_effect=Exception("Connection refused"),
        )

        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://invalid:11434",
        )

        with pytest.raises(ProviderError, match="Failed to create OllamaModel"):
            create_ollama_model(runtime)


class TestCreateModel:
    """Tests for create_model factory function."""

    def test_creates_bedrock_model_when_provider_is_bedrock(self, mocker):
        """Should delegate to create_bedrock_model."""
        mock_bedrock = mocker.patch("strands_cli.runtime.providers.create_bedrock_model")
        mock_model = Mock()
        mock_bedrock.return_value = mock_model

        runtime = Runtime(provider=ProviderType.BEDROCK, region="us-east-1")

        result = create_model(runtime)

        mock_bedrock.assert_called_once_with(runtime)
        assert result == mock_model

    def test_creates_ollama_model_when_provider_is_ollama(self, mocker):
        """Should delegate to create_ollama_model."""
        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        mock_model = Mock()
        mock_ollama.return_value = mock_model

        runtime = Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434")

        result = create_model(runtime)

        mock_ollama.assert_called_once_with(runtime)
        assert result == mock_model

    def test_raises_error_for_unsupported_provider(self):
        """Should raise ProviderError for unknown provider."""
        # Create a runtime with an invalid provider (bypassing enum validation)
        runtime = Runtime(provider=ProviderType.BEDROCK, region="us-east-1")
        runtime.provider = "unknown"  # type: ignore

        with pytest.raises(ProviderError, match="Unsupported provider"):
            create_model(runtime)


# ============================================================================
# Strands Adapter Tests
# ============================================================================


class TestBuildSystemPrompt:
    """Tests for build_system_prompt."""

    def test_builds_prompt_with_agent_prompt_only(self, sample_ollama_spec):
        """Should return agent prompt when no skills or special config."""
        agent_config = AgentConfig(prompt="You are a helpful assistant.")

        result = build_system_prompt(
            agent_config=agent_config,
            spec=sample_ollama_spec,
            agent_id="test-agent",
        )

        # Should contain agent prompt
        assert "You are a helpful assistant." in result

        # Should contain runtime banner
        assert "# Runtime Context" in result
        assert "**Workflow:**" in result
        assert "**Agent ID:** test-agent" in result

    def test_includes_skills_metadata_when_present(self, sample_ollama_spec):
        """Should inject skills section when spec has skills."""
        agent_config = AgentConfig(prompt="Base prompt")

        # Add skills to spec
        sample_ollama_spec.skills = [
            Skill(
                id="web-search",
                path="/opt/skills/web_search.py",
                description="Search the web",
            ),
            Skill(
                id="calculator",
                description="Perform calculations",
            ),
        ]

        result = build_system_prompt(
            agent_config=agent_config,
            spec=sample_ollama_spec,
            agent_id="agent1",
        )

        # Should have skills section
        assert "# Available Skills" in result
        assert "**web-search**" in result
        assert "path: `/opt/skills/web_search.py`" in result
        assert "Search the web" in result
        assert "**calculator**" in result
        assert "Perform calculations" in result

    def test_includes_budgets_summary_when_present(self, sample_ollama_spec):
        """Should include budgets in runtime banner."""
        agent_config = AgentConfig(prompt="Base prompt")

        # Add budgets to spec
        sample_ollama_spec.runtime.budgets = {
            "max_iterations": 10,
            "max_cost_usd": 5.0,
        }

        result = build_system_prompt(
            agent_config=agent_config,
            spec=sample_ollama_spec,
            agent_id="agent1",
        )

        # Should have budgets in banner
        assert "**Budgets:**" in result
        assert "max_iterations: 10" in result
        assert "max_cost_usd: 5.0" in result

    def test_includes_tags_when_present(self, sample_ollama_spec):
        """Should include tags in runtime banner."""
        agent_config = AgentConfig(prompt="Base prompt")

        # Add tags to spec
        sample_ollama_spec.tags = ["test", "development"]

        result = build_system_prompt(
            agent_config=agent_config,
            spec=sample_ollama_spec,
            agent_id="agent1",
        )

        # Should have tags in banner
        assert "**Tags:** test, development" in result


class TestBuildAgent:
    """Tests for build_agent."""

    def test_builds_agent_with_minimal_config(self, sample_ollama_spec, mocker):
        """Should create agent with just model and instructions."""
        # Mock create_model
        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mock_model = Mock()
        mock_create_model.return_value = mock_model

        # Mock Agent
        mock_agent_cls = mocker.patch("strands_cli.runtime.strands_adapter.Agent")
        mock_agent = Mock()
        mock_agent_cls.return_value = mock_agent

        agent_config = AgentConfig(prompt="You are helpful.")
        agent_id = "assistant"

        result = build_agent(sample_ollama_spec, agent_id, agent_config)

        # Verify model created
        mock_create_model.assert_called_once_with(sample_ollama_spec.runtime)

        # Verify Agent created with correct params
        call_args = mock_agent_cls.call_args[1]
        assert call_args["name"] == "assistant"
        assert call_args["model"] == mock_model
        assert "You are helpful." in call_args["system_prompt"]
        assert call_args["tools"] is None

        assert result == mock_agent

    def test_builds_agent_with_http_executors(self, sample_ollama_spec, mocker):
        """Should register HTTP executor tools."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mock_agent_cls = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        # Add HTTP executor to spec
        sample_ollama_spec.tools = Tools(
            http_executors=[
                HttpExecutor(
                    id="api-call",
                    base_url="https://api.example.com",
                    timeout=30,
                )
            ]
        )

        agent_config = AgentConfig(prompt="Base prompt")

        build_agent(sample_ollama_spec, "agent1", agent_config)

        # Verify tools list passed to Agent
        call_args = mock_agent_cls.call_args[1]
        tools = call_args["tools"]

        assert tools is not None
        assert len(tools) == 1
        assert isinstance(tools[0], HttpExecutorAdapter)

    def test_builds_agent_with_python_tools(self, sample_ollama_spec, mocker):
        """Should register Python callable tools."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mock_agent_cls = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        # Mock load_python_callable
        mock_load = mocker.patch("strands_cli.runtime.strands_adapter.load_python_callable")
        mock_callable = Mock()
        mock_load.return_value = mock_callable

        # Add Python tool to spec
        sample_ollama_spec.tools = Tools(python=[PythonTool(callable="strands_tools.http_request")])

        agent_config = AgentConfig(prompt="Base prompt")

        build_agent(sample_ollama_spec, "agent1", agent_config)

        # Verify load_python_callable called
        mock_load.assert_called_once_with("strands_tools.http_request")

        # Verify tools list passed to Agent
        call_args = mock_agent_cls.call_args[1]
        tools = call_args["tools"]

        assert tools is not None
        assert len(tools) == 1
        assert tools[0] == mock_callable

    def test_raises_adapter_error_on_model_creation_failure(self, sample_ollama_spec, mocker):
        """Should raise AdapterError if model creation fails."""
        mocker.patch(
            "strands_cli.runtime.strands_adapter.create_model",
            side_effect=Exception("Connection error"),
        )

        agent_config = AgentConfig(prompt="Base prompt")

        with pytest.raises(AdapterError, match="Failed to create model"):
            build_agent(sample_ollama_spec, "agent1", agent_config)

    def test_raises_adapter_error_on_python_tool_load_failure(self, sample_ollama_spec, mocker):
        """Should raise AdapterError if Python tool loading fails."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mocker.patch(
            "strands_cli.runtime.strands_adapter.load_python_callable",
            side_effect=ToolError("Not in allowlist"),
        )

        sample_ollama_spec.tools = Tools(python=[PythonTool(callable="bad_tool.func")])

        agent_config = AgentConfig(prompt="Base prompt")

        with pytest.raises(AdapterError, match="Failed to load Python tool"):
            build_agent(sample_ollama_spec, "agent1", agent_config)

    def test_raises_adapter_error_on_agent_creation_failure(self, sample_ollama_spec, mocker):
        """Should raise AdapterError if Agent init fails."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mocker.patch(
            "strands_cli.runtime.strands_adapter.Agent",
            side_effect=Exception("Invalid config"),
        )

        agent_config = AgentConfig(prompt="Base prompt")

        with pytest.raises(AdapterError, match="Failed to create Strands Agent"):
            build_agent(sample_ollama_spec, "agent1", agent_config)


# ============================================================================
# Tools Tests
# ============================================================================


class TestLoadPythonCallable:
    """Tests for load_python_callable."""

    def test_loads_allowed_callable(self, mocker):
        """Should load callable if in allowlist."""
        # Mock the import
        mock_module = Mock()
        mock_http_request = Mock()  # Simulated callable
        mock_module.http_request = mock_http_request

        mocker.patch(
            "strands_cli.runtime.tools.importlib.import_module",
            return_value=mock_module,
        )

        # strands_tools.http_request is in ALLOWED_PYTHON_CALLABLES
        result = load_python_callable("strands_tools.http_request")

        assert result == mock_http_request
        assert callable(result)

    def test_raises_error_for_disallowed_callable(self):
        """Should raise ToolError if callable not in allowlist."""
        with pytest.raises(ToolError, match="not in allowlist"):
            load_python_callable("os.system")

    def test_raises_error_for_invalid_import_path(self, mocker):
        """Should raise ToolError if module import fails."""
        # Mock failed import
        mocker.patch(
            "strands_cli.runtime.tools.importlib.import_module",
            side_effect=ImportError("No module named strands_tools"),
        )

        with pytest.raises(ToolError, match="Failed to load callable"):
            load_python_callable("strands_tools.http_request")

    def test_raises_error_if_not_callable(self, mocker):
        """Should raise ToolError if loaded object is not callable."""
        # Mock importlib to return a non-callable
        mock_module = Mock()
        mock_module.http_request = "not_a_function"

        mocker.patch(
            "strands_cli.runtime.tools.importlib.import_module",
            return_value=mock_module,
        )

        with pytest.raises(ToolError, match="is not callable"):
            load_python_callable("strands_tools.http_request")


class TestHttpExecutorAdapter:
    """Tests for HttpExecutorAdapter."""

    def test_creates_adapter_with_config(self):
        """Should initialize adapter with HTTP executor config."""
        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=30,
            headers={"Authorization": "Bearer token"},
        )

        adapter = HttpExecutorAdapter(config)

        assert adapter.config == config
        assert adapter.client.base_url == "https://api.example.com"

    def test_executes_http_request_successfully(self, mocker):
        """Should make HTTP request and return response dict."""
        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=30,
        )

        adapter = HttpExecutorAdapter(config)

        # Mock httpx.Client.request
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'

        mocker.patch.object(adapter.client, "request", return_value=mock_response)

        result = adapter(
            method="POST",
            path="/api/endpoint",
            json_data={"key": "value"},
        )

        # Verify response format
        assert result["status"] == 200
        assert result["headers"]["content-type"] == "application/json"
        assert result["body"] == '{"result": "success"}'

        # Verify request was made correctly
        adapter.client.request.assert_called_once_with(
            method="POST",
            url="/api/endpoint",
            json={"key": "value"},
            headers=None,
        )

    def test_merges_headers_override(self, mocker):
        """Should merge headers_override with config headers."""
        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=30,
            headers={"Authorization": "Bearer token"},
        )

        adapter = HttpExecutorAdapter(config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = ""

        mocker.patch.object(adapter.client, "request", return_value=mock_response)

        adapter(
            method="GET",
            path="/test",
            headers_override={"X-Custom": "value"},
        )

        # Verify merged headers
        call_kwargs = adapter.client.request.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer token"
        assert call_kwargs["headers"]["X-Custom"] == "value"

    def test_raises_tool_error_on_timeout(self, mocker):
        """Should raise ToolError on timeout."""
        import httpx

        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=1,
        )

        adapter = HttpExecutorAdapter(config)

        mocker.patch.object(
            adapter.client,
            "request",
            side_effect=httpx.TimeoutException("Timeout"),
        )

        with pytest.raises(ToolError, match="HTTP request timed out"):
            adapter(method="GET", path="/slow")

    def test_raises_tool_error_on_http_error(self, mocker):
        """Should raise ToolError on HTTP errors."""
        import httpx

        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=30,
        )

        adapter = HttpExecutorAdapter(config)

        mocker.patch.object(
            adapter.client,
            "request",
            side_effect=httpx.HTTPError("Connection failed"),
        )

        with pytest.raises(ToolError, match="HTTP request failed"):
            adapter(method="GET", path="/error")

    def test_context_manager_closes_client(self):
        """Should close client on context manager exit."""
        config = HttpExecutor(
            id="test-api",
            base_url="https://api.example.com",
            timeout=30,
        )

        with HttpExecutorAdapter(config) as adapter:
            assert adapter.client is not None

        # Client should be closed after exit
        assert adapter.client.is_closed

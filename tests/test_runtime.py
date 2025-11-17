"""Unit tests for runtime providers, strands adapter, and tools."""

from unittest.mock import Mock

import pytest

from strands_cli.runtime.providers import (
    ProviderError,
    RuntimeConfig,
    _create_model_cached,
    create_bedrock_model,
    create_model,
    create_ollama_model,
    create_openai_model,
)
from strands_cli.runtime.strands_adapter import (
    AdapterError,
    build_agent,
    build_system_prompt,
)
from strands_cli.runtime.tools import (
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


class TestOpenAIModelCreation:
    """Tests for create_openai_model."""

    def test_creates_openai_model_with_api_key(self, mocker, monkeypatch):
        """Should create OpenAIModel with valid API key from environment."""
        # Set API key in environment
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")

        mock_openai_model_cls = mocker.patch("strands_cli.runtime.providers.OpenAIModel")
        mock_model = Mock()
        mock_openai_model_cls.return_value = mock_model

        runtime = Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4o-mini",
        )

        result = create_openai_model(runtime)

        # Verify OpenAIModel created with correct params (no params passed when empty)
        mock_openai_model_cls.assert_called_once_with(
            client_args={"api_key": "sk-test-key-12345"},
            model_id="gpt-4o-mini",
        )

        assert result == mock_model

    def test_uses_default_model_id_if_not_specified(self, mocker, monkeypatch):
        """Should use gpt-4o-mini as default model ID when not provided."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        mock_openai_model_cls = mocker.patch("strands_cli.runtime.providers.OpenAIModel")

        runtime = Runtime(provider=ProviderType.OPENAI)

        create_openai_model(runtime)

        # Check that default model ID was used
        call_kwargs = mock_openai_model_cls.call_args[1]
        assert call_kwargs["model_id"] == "gpt-4o-mini"

    def test_raises_error_when_api_key_missing(self, monkeypatch):
        """Should raise ProviderError when OPENAI_API_KEY is not set."""
        # Ensure API key is not in environment
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        runtime = Runtime(provider=ProviderType.OPENAI)

        with pytest.raises(
            ProviderError, match=r"OpenAI provider requires OPENAI_API_KEY environment variable"
        ):
            create_openai_model(runtime)

    def test_supports_base_url_for_compatible_servers(self, mocker, monkeypatch):
        """Should support runtime.host as base_url for OpenAI-compatible servers."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        mock_openai_model_cls = mocker.patch("strands_cli.runtime.providers.OpenAIModel")

        runtime = Runtime(
            provider=ProviderType.OPENAI,
            model_id="custom-model",
            host="https://api.custom-openai.com/v1",
        )

        create_openai_model(runtime)

        # Verify base_url was passed in client_args
        call_kwargs = mock_openai_model_cls.call_args[1]
        assert call_kwargs["client_args"]["base_url"] == "https://api.custom-openai.com/v1"

    def test_passes_inference_params_to_model(self, mocker, monkeypatch):
        """Should pass temperature, max_tokens, and top_p to params dict."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        mock_openai_model_cls = mocker.patch("strands_cli.runtime.providers.OpenAIModel")

        runtime = Runtime(
            provider=ProviderType.OPENAI,
            model_id="gpt-4",
            temperature=0.8,
            max_tokens=1500,
            top_p=0.95,
        )

        create_openai_model(runtime)

        # Verify params dict was constructed correctly
        call_kwargs = mock_openai_model_cls.call_args[1]
        assert call_kwargs["params"] == {
            "temperature": 0.8,
            "max_tokens": 1500,
            "top_p": 0.95,
        }

    def test_omits_params_when_not_specified(self, mocker, monkeypatch):
        """Should pass None for params when no inference params specified."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        mock_openai_model_cls = mocker.patch("strands_cli.runtime.providers.OpenAIModel")

        runtime = Runtime(provider=ProviderType.OPENAI)

        create_openai_model(runtime)

        # Verify params is not passed when empty
        call_kwargs = mock_openai_model_cls.call_args[1]
        assert "params" not in call_kwargs

    def test_raises_error_on_openai_model_failure(self, mocker, monkeypatch):
        """Should raise ProviderError when OpenAIModel init fails."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        mocker.patch(
            "strands_cli.runtime.providers.OpenAIModel",
            side_effect=Exception("Invalid API key"),
        )

        runtime = Runtime(provider=ProviderType.OPENAI)

        with pytest.raises(ProviderError, match="Failed to create OpenAIModel"):
            create_openai_model(runtime)


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

    def test_creates_openai_model_when_provider_is_openai(self, mocker):
        """Should delegate to create_openai_model."""
        mock_openai = mocker.patch("strands_cli.runtime.providers.create_openai_model")
        mock_model = Mock()
        mock_openai.return_value = mock_model

        runtime = Runtime(provider=ProviderType.OPENAI)

        result = create_model(runtime)

        mock_openai.assert_called_once_with(runtime)
        assert result == mock_model

    def test_raises_error_for_unsupported_provider(self):
        """Should raise ProviderError for unknown provider in cached function."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        # Create a RuntimeConfig with invalid provider string (bypassing enum in create_model)
        config = RuntimeConfig(
            provider="invalid_provider",
            model_id=None,
            region=None,
            host=None,
            temperature=None,
            top_p=None,
            max_tokens=None,
        )

        with pytest.raises(ProviderError, match="Unsupported provider"):
            _create_model_cached(config)

    def test_caches_model_clients_for_identical_configs(self, mocker):
        """Should return cached model client for repeated identical runtime configs."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        # Mock the actual model creation functions
        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        mock_model1 = Mock()
        mock_model2 = Mock()
        mock_ollama.side_effect = [mock_model1, mock_model2]

        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="llama3",
        )

        # First call should create new model
        result1 = create_model(runtime)
        assert result1 == mock_model1
        assert _create_model_cached.cache_info().misses == 1
        assert _create_model_cached.cache_info().hits == 0

        # Second call with same config should return cached model
        result2 = create_model(runtime)
        assert result2 == mock_model1  # Same instance (cached)
        assert _create_model_cached.cache_info().hits == 1
        assert _create_model_cached.cache_info().misses == 1

        # Verify create_ollama_model was called only once
        assert mock_ollama.call_count == 1

    def test_cache_differentiates_by_model_id(self, mocker):
        """Should create separate cache entries for different model IDs."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        mock_model1 = Mock()
        mock_model2 = Mock()
        mock_ollama.side_effect = [mock_model1, mock_model2]

        # Create two different runtimes with different model IDs
        runtime1 = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="llama3",
        )

        runtime2 = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            model_id="gpt-oss",
        )

        # Both should trigger model creation (different model_id)
        result1 = create_model(runtime1)
        result2 = create_model(runtime2)

        assert result1 == mock_model1
        assert result2 == mock_model2
        assert mock_ollama.call_count == 2
        assert _create_model_cached.cache_info().misses == 2
        assert _create_model_cached.cache_info().hits == 0

    def test_cache_differentiates_by_provider(self, mocker):
        """Should create separate cache entries for different providers."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        mock_bedrock = mocker.patch("strands_cli.runtime.providers.create_bedrock_model")
        mock_model_ollama = Mock()
        mock_model_bedrock = Mock()
        mock_ollama.return_value = mock_model_ollama
        mock_bedrock.return_value = mock_model_bedrock

        runtime1 = Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434")
        runtime2 = Runtime(provider=ProviderType.BEDROCK, region="us-east-1")

        # Both should trigger model creation (different provider)
        result1 = create_model(runtime1)
        result2 = create_model(runtime2)

        assert result1 == mock_model_ollama
        assert result2 == mock_model_bedrock
        assert _create_model_cached.cache_info().misses == 2
        assert _create_model_cached.cache_info().hits == 0

    def test_cache_respects_maxsize_limit(self, mocker):
        """Should evict least recently used entries when cache exceeds maxsize."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        # Create enough unique mocks
        mock_models = [Mock() for _ in range(20)]
        mock_ollama.side_effect = mock_models

        # Create more than maxsize (16) different configurations
        for i in range(20):
            runtime = Runtime(
                provider=ProviderType.OLLAMA,
                host="http://localhost:11434",
                model_id=f"model-{i}",
            )
            create_model(runtime)

        # Cache size should not exceed maxsize
        cache_info = _create_model_cached.cache_info()
        assert cache_info.currsize <= cache_info.maxsize
        assert cache_info.maxsize == 16

    def test_logs_cache_stats_periodically(self, mocker):
        """Should log cache statistics every 10 calls."""
        # Clear cache before test
        _create_model_cached.cache_clear()

        mock_ollama = mocker.patch("strands_cli.runtime.providers.create_ollama_model")
        mock_model = Mock()
        mock_ollama.return_value = mock_model

        # Mock logger to capture log calls
        mock_logger = Mock()
        mocker.patch("strands_cli.runtime.providers.structlog.get_logger", return_value=mock_logger)

        runtime = Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434")

        # Make 10 calls (all cache hits after first miss)
        for _ in range(10):
            create_model(runtime)

        # Should have logged cache stats after the 10th call
        # Check if info was called with cache stats
        info_calls = [
            call for call in mock_logger.info.call_args_list if call[0][0] == "model_cache_stats"
        ]
        assert len(info_calls) >= 1

        # Verify the logged stats
        last_call = info_calls[-1]
        call_kwargs = last_call[1]
        assert call_kwargs["hits"] == 9  # 9 hits after first miss
        assert call_kwargs["misses"] == 1
        assert "hit_rate" in call_kwargs
        assert call_kwargs["maxsize"] == 16


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

    def test_injects_http_executor_metadata(self, sample_ollama_spec):
        """Should inject a formatted block of HTTP tool metadata into the prompt."""
        agent_config = AgentConfig(prompt="Base prompt")
        sample_ollama_spec.tools = Tools(
            http_executors=[
                HttpExecutor(
                    id="weather-api",
                    base_url="https://api.weather.com",
                    description="API for getting weather forecasts.",
                    common_endpoints=[
                        {"path": "/current?city={city}", "description": "Get current weather"},
                        {
                            "path": "/forecast?city={city}&days=5",
                            "description": "Get 5-day forecast",
                        },
                    ],
                    authentication_info="API key required in X-API-Key header.",
                )
            ]
        )

        result = build_system_prompt(
            agent_config=agent_config,
            spec=sample_ollama_spec,
            agent_id="agent1",
        )

        assert "# HTTP Tools Reference" in result
        assert "## Tool: `weather-api`" in result
        assert "**Description**: API for getting weather forecasts." in result
        assert "**Base URL**: `https://api.weather.com`" in result
        assert "**Common Endpoints**:" in result
        assert "- `/current?city={city}`" in result
        assert "- `/forecast?city={city}&days=5`" in result
        assert "**Authentication**: API key required in X-API-Key header." in result


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
        # HTTP executors are now modules with TOOL_SPEC (not HttpExecutorAdapter class)
        assert hasattr(tools[0], "TOOL_SPEC")
        assert tools[0].TOOL_SPEC["name"] == "api-call"

    def test_builds_agent_with_python_tools(self, sample_ollama_spec, mocker):
        """Should register Python callable tools."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mock_agent_cls = mocker.patch("strands_cli.runtime.strands_adapter.Agent")

        # Mock load_python_callable
        mock_load = mocker.patch("strands_cli.runtime.strands_adapter.load_python_callable")
        mock_callable = Mock()
        mock_load.return_value = mock_callable

        # Add Python tool to spec
        sample_ollama_spec.tools = Tools(
            python=[PythonTool(callable="http_request")]
        )

        agent_config = AgentConfig(prompt="Base prompt")

        build_agent(sample_ollama_spec, "agent1", agent_config)

        # Verify load_python_callable called
        mock_load.assert_called_once_with("http_request")

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


    def test_raises_error_for_disallowed_callable(self):
        """Should raise ToolError if callable not in allowlist."""
        with pytest.raises(ToolError, match="not in allowlist"):
            load_python_callable("os.system")

    def test_raises_error_for_invalid_import_path(self, mocker):
        """Should raise ToolError if module import fails."""
        # Mock registry to include the tool in allowlist
        mock_registry = Mock()
        mock_registry.get_allowlist.return_value = {"http_request", "strands_cli.tools.http_request"}
        mock_registry.resolve.return_value = "strands_cli.tools.http_request"
        mocker.patch("strands_cli.tools.get_registry", return_value=mock_registry)

        # Mock failed import
        mocker.patch(
            "strands_cli.runtime.tools.importlib.import_module",
            side_effect=ImportError("No module named strands_cli.tools.http_request"),
        )

        with pytest.raises(ToolError, match="Failed to load tool"):
            load_python_callable("http_request")


    def test_loads_module_based_tool_with_tool_spec(self, mocker):
        """Should return module itself if it has TOOL_SPEC attribute (module-based tool)."""
        # Mock the import
        mock_module = Mock()
        mock_module.TOOL_SPEC = {
            "name": "file_write",
            "description": "Write content to a file",
        }  # Module-based tool
        mock_file_write_func = Mock()  # Function exists but should not be returned
        mock_module.file_write = mock_file_write_func

        # Mock registry to include the tool in allowlist
        mock_registry = Mock()
        mock_registry.get_allowlist.return_value = {"file_write", "strands_cli.tools.file_write"}
        mock_registry.resolve.return_value = "strands_cli.tools.file_write"
        mocker.patch("strands_cli.tools.get_registry", return_value=mock_registry)

        mocker.patch(
            "strands_cli.runtime.tools.importlib.import_module",
            return_value=mock_module,
        )

        result = load_python_callable("file_write")

        # Should return the module itself, not the function
        assert result == mock_module
        assert hasattr(result, "TOOL_SPEC")
        assert result.TOOL_SPEC["name"] == "file_write"


# ============================================================================
# HTTP Executor Security Tests (SSRF Prevention)
# ============================================================================


class TestHttpExecutorSecurity:
    """Test that HttpExecutor blocks SSRF attack vectors."""

    def test_blocks_localhost_ipv4(self):
        """Test that localhost IPv4 (127.0.0.1) is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://127.0.0.1:8080",
            )

    def test_blocks_localhost_hostname(self):
        """Test that localhost hostname is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://localhost:8080",
            )

    def test_blocks_localhost_ipv6(self):
        """Test that localhost IPv6 (::1) is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://[::1]:8080",
            )

    def test_blocks_aws_metadata_endpoint(self):
        """Test that AWS metadata endpoint is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://169.254.169.254/latest/meta-data/",
            )

    def test_blocks_rfc1918_10_network(self):
        """Test that RFC1918 10.0.0.0/8 network is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://10.0.0.1:8080",
            )

        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://10.255.255.255:8080",
            )

    def test_blocks_rfc1918_172_network(self):
        """Test that RFC1918 172.16.0.0/12 network is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://172.16.0.1:8080",
            )

        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://172.31.255.255:8080",
            )

    def test_blocks_rfc1918_192_network(self):
        """Test that RFC1918 192.168.0.0/16 network is blocked."""
        with pytest.raises(ValueError, match=r"blocked pattern.*SSRF"):
            HttpExecutor(
                id="malicious",
                base_url="http://192.168.1.1:8080",
            )

    def test_blocks_file_protocol(self):
        """Test that file:// protocol is blocked."""
        with pytest.raises(ValueError, match="must use http or https"):
            HttpExecutor(
                id="malicious",
                base_url="file:///etc/passwd",
            )

    def test_blocks_ftp_protocol(self):
        """Test that ftp:// protocol is blocked."""
        with pytest.raises(ValueError, match="must use http or https"):
            HttpExecutor(
                id="malicious",
                base_url="ftp://internal-server/data",
            )

    def test_blocks_gopher_protocol(self):
        """Test that gopher:// protocol is blocked."""
        with pytest.raises(ValueError, match="must use http or https"):
            HttpExecutor(
                id="malicious",
                base_url="gopher://internal-server:70",
            )

    def test_blocks_unspecified_ip(self):
        """Test that 0.0.0.0 is blocked even without explicit pattern."""
        with pytest.raises(ValueError, match=r"blocked host '0\.0\.0\.0'"):
            HttpExecutor(
                id="malicious",
                base_url="http://0.0.0.0:8080",
            )

    def test_blocks_urls_with_credentials(self):
        """Test that URLs containing credentials are rejected."""
        with pytest.raises(ValueError, match="must not include credentials"):
            HttpExecutor(
                id="malicious",
                base_url="https://user:pass@api.example.com",
            )

    def test_blocks_obfuscated_loopback_with_userinfo(self):
        """Test that loopback disguised via userinfo is detected."""
        with pytest.raises(ValueError, match="must not include credentials"):
            HttpExecutor(
                id="malicious",
                base_url="https://example.com@127.0.0.1:8080",
            )

    def test_allows_public_https_urls(self):
        """Test that public HTTPS URLs are allowed."""
        # These should NOT raise ValueError
        executor1 = HttpExecutor(
            id="safe",
            base_url="https://api.openai.com",
        )
        assert executor1.base_url == "https://api.openai.com"

        executor2 = HttpExecutor(
            id="safe",
            base_url="https://api.example.com",
        )
        assert executor2.base_url == "https://api.example.com"

    def test_allows_public_http_urls(self):
        """Test that public HTTP URLs are allowed (blocklist, not allowlist by default)."""
        executor = HttpExecutor(
            id="safe",
            base_url="http://api.example.com",
        )
        assert executor.base_url == "http://api.example.com"

    def test_env_var_custom_blocked_patterns(self, monkeypatch):
        """Test that STRANDS_HTTP_BLOCKED_PATTERNS env var adds custom blocks."""
        # Add custom blocked pattern via env var (use simple pattern without regex escapes)
        monkeypatch.setenv("STRANDS_HTTP_BLOCKED_PATTERNS", '["^https://evil.com"]')

        # Need to reload config to pick up env var
        from strands_cli.config import StrandsConfig

        config = StrandsConfig()

        # Verify custom pattern is loaded
        assert "^https://evil.com" in config.http_blocked_patterns

        # Test that it blocks the custom pattern
        with pytest.raises(ValueError, match="blocked pattern"):
            HttpExecutor(
                id="test",
                base_url="https://evil.com/api",
            )

    def test_env_var_allowed_domains_enforces_allowlist(self, monkeypatch):
        """Test that STRANDS_HTTP_ALLOWED_DOMAINS env var enforces allowlist."""
        # Set allowed domains (use simple pattern)
        monkeypatch.setenv("STRANDS_HTTP_ALLOWED_DOMAINS", '["^https://api.trusted.com"]')

        # Should allow URLs matching the pattern
        executor = HttpExecutor(
            id="safe",
            base_url="https://api.trusted.com/v1",
        )
        assert executor.base_url == "https://api.trusted.com/v1"

        # Should block URLs not matching the pattern
        with pytest.raises(ValueError, match="not in allowed domains"):
            HttpExecutor(
                id="blocked",
                base_url="https://untrusted.com",
            )

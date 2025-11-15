"""Tests for inference parameter support across providers.

Tests cover:
- Inference Pydantic model validation
- Agent-level inference override merging
- Provider-specific warnings (Bedrock/Ollama)
- Capability checker validation
"""

import pytest
from pytest_mock import MockerFixture

from strands_cli.capability.checker import check_capability
from strands_cli.runtime.providers import create_bedrock_model, create_ollama_model
from strands_cli.runtime.strands_adapter import build_agent
from strands_cli.types import Agent, Inference, ProviderType, Runtime, Spec


class TestInferenceModel:
    """Test Inference Pydantic model validation."""

    def test_accepts_valid_temperature(self) -> None:
        """Should accept temperature values between 0.0 and 2.0."""
        inf = Inference(temperature=0.7)
        assert inf.temperature == 0.7

        inf = Inference(temperature=0.0)
        assert inf.temperature == 0.0

        inf = Inference(temperature=2.0)
        assert inf.temperature == 2.0

    def test_rejects_invalid_temperature(self) -> None:
        """Should reject temperature values outside 0.0-2.0 range."""
        with pytest.raises(ValueError):
            Inference(temperature=-0.1)

        with pytest.raises(ValueError):
            Inference(temperature=2.1)

    def test_accepts_valid_top_p(self) -> None:
        """Should accept top_p values between 0.0 and 1.0."""
        inf = Inference(top_p=0.95)
        assert inf.top_p == 0.95

        inf = Inference(top_p=0.0)
        assert inf.top_p == 0.0

        inf = Inference(top_p=1.0)
        assert inf.top_p == 1.0

    def test_rejects_invalid_top_p(self) -> None:
        """Should reject top_p values outside 0.0-1.0 range."""
        with pytest.raises(ValueError):
            Inference(top_p=-0.1)

        with pytest.raises(ValueError):
            Inference(top_p=1.5)

    def test_accepts_valid_max_tokens(self) -> None:
        """Should accept max_tokens values >= 1."""
        inf = Inference(max_tokens=100)
        assert inf.max_tokens == 100

        inf = Inference(max_tokens=1)
        assert inf.max_tokens == 1

    def test_rejects_invalid_max_tokens(self) -> None:
        """Should reject max_tokens values < 1."""
        with pytest.raises(ValueError):
            Inference(max_tokens=0)

        with pytest.raises(ValueError):
            Inference(max_tokens=-10)

    def test_all_fields_optional(self) -> None:
        """Should allow creating Inference with no fields set."""
        inf = Inference()
        assert inf.temperature is None
        assert inf.top_p is None
        assert inf.max_tokens is None

    def test_agent_has_inference_field(self) -> None:
        """Should allow Agent model to have inference field."""
        agent = Agent(
            prompt="Test prompt",
            inference=Inference(temperature=0.7, max_tokens=500),
        )
        assert agent.inference is not None
        assert agent.inference.temperature == 0.7
        assert agent.inference.max_tokens == 500


class TestAgentInferenceMerging:
    """Test agent-level inference override merging in build_agent."""

    @pytest.fixture
    def minimal_spec(self) -> Spec:
        """Minimal spec for testing."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        return Spec(
            name="test-spec",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.OPENAI,
                model_id="gpt-4o-mini",
                temperature=0.5,
                top_p=0.9,
                max_tokens=1000,
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(
                    steps=[
                        ChainStep(agent="test_agent", input="Hello"),
                    ],
                ),
            ),
            agents={
                "test_agent": Agent(prompt="Test agent"),
            },
        )

    def test_merges_agent_temperature_override(
        self, minimal_spec: Spec, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should merge agent-level temperature with runtime defaults."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        # Mock create_model to capture what runtime config is passed
        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Add agent-level inference override
        agent_config = Agent(
            prompt="Test",
            inference=Inference(temperature=1.2),
        )

        build_agent(minimal_spec, "test_agent", agent_config)

        # Verify create_model was called with merged runtime
        call_args = mock_create_model.call_args[0][0]
        assert call_args.temperature == 1.2  # Agent override
        assert call_args.top_p == 0.9  # Runtime default
        assert call_args.max_tokens == 1000  # Runtime default

    def test_merges_all_inference_params(
        self, minimal_spec: Spec, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should merge all inference parameters independently."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Override all three params
        agent_config = Agent(
            prompt="Test",
            inference=Inference(temperature=0.2, top_p=0.95, max_tokens=500),
        )

        build_agent(minimal_spec, "test_agent", agent_config)

        call_args = mock_create_model.call_args[0][0]
        assert call_args.temperature == 0.2
        assert call_args.top_p == 0.95
        assert call_args.max_tokens == 500

    def test_agent_override_takes_precedence_over_runtime(
        self, minimal_spec: Spec, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use agent inference values when both runtime and agent specify them."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Both runtime and agent set temperature - agent should win
        agent_config = Agent(
            prompt="Test",
            inference=Inference(temperature=1.5),  # Different from runtime's 0.5
        )

        build_agent(minimal_spec, "test_agent", agent_config)

        call_args = mock_create_model.call_args[0][0]
        assert call_args.temperature == 1.5  # Agent value, not runtime's 0.5

    def test_no_inference_uses_runtime_defaults(
        self, minimal_spec: Spec, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use runtime defaults when agent has no inference overrides."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Agent without inference field
        agent_config = Agent(prompt="Test")

        build_agent(minimal_spec, "test_agent", agent_config)

        call_args = mock_create_model.call_args[0][0]
        assert call_args.temperature == 0.5  # Runtime default
        assert call_args.top_p == 0.9
        assert call_args.max_tokens == 1000

    def test_partial_inference_override(
        self, minimal_spec: Spec, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should merge partial inference overrides with runtime defaults."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_create_model = mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Only override temperature, leave top_p and max_tokens as runtime defaults
        agent_config = Agent(
            prompt="Test",
            inference=Inference(temperature=0.1),  # Only this field set
        )

        build_agent(minimal_spec, "test_agent", agent_config)

        call_args = mock_create_model.call_args[0][0]
        assert call_args.temperature == 0.1  # Agent override
        assert call_args.top_p == 0.9  # Runtime default (not overridden)
        assert call_args.max_tokens == 1000  # Runtime default (not overridden)


class TestBedrockInferenceWarnings:
    """Test Bedrock provider warns about unsupported inference params."""

    def test_warns_when_temperature_set(self) -> None:
        """Should log warning when temperature is set for Bedrock (via structlog)."""
        runtime = Runtime(
            provider=ProviderType.BEDROCK,
            region="us-east-1",
            temperature=0.7,
        )

        # Should not raise error, but logs warning internally via structlog
        model = create_bedrock_model(runtime)
        assert model is not None

    def test_warns_when_all_params_set(self) -> None:
        """Should log warning for all inference params when set."""
        runtime = Runtime(
            provider=ProviderType.BEDROCK,
            region="us-east-1",
            temperature=0.5,
            top_p=0.9,
            max_tokens=1000,
        )

        # Should not raise error, but logs warnings internally
        model = create_bedrock_model(runtime)
        assert model is not None

    def test_no_warning_when_no_params_set(self) -> None:
        """Should not log warning when no inference params set."""
        runtime = Runtime(
            provider=ProviderType.BEDROCK,
            region="us-east-1",
        )

        # Should create model without any warnings
        model = create_bedrock_model(runtime)
        assert model is not None


class TestOllamaInferenceWarnings:
    """Test Ollama provider warns about unsupported inference params."""

    def test_warns_when_temperature_set(self) -> None:
        """Should log warning when temperature is set for Ollama (via structlog)."""
        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            temperature=1.2,
        )

        # Should not raise error, but logs warning internally
        model = create_ollama_model(runtime)
        assert model is not None

    def test_warns_when_all_params_set(self) -> None:
        """Should log warning for all inference params when set."""
        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            temperature=0.8,
            top_p=0.95,
            max_tokens=2000,
        )

        # Should not raise error, but logs warnings internally
        model = create_ollama_model(runtime)
        assert model is not None

    def test_no_warning_when_no_params_set(self) -> None:
        """Should not log warning when no inference params set."""
        runtime = Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
        )

        # Should create model without warnings
        model = create_ollama_model(runtime)
        assert model is not None


class TestCapabilityInferenceValidation:
    """Test capability checker warns about provider-specific inference support."""

    def test_warns_runtime_inference_with_bedrock(self) -> None:
        """Should warn when runtime-level inference params used with Bedrock."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        spec = Spec(
            name="test",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.BEDROCK,
                region="us-east-1",
                temperature=0.7,
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="test", input="Hello")]),
            ),
            agents={"test": Agent(prompt="Test")},
        )

        report = check_capability(spec)

        # Should have warning issue
        assert len(report.issues) == 1
        assert "/runtime/temperature" in report.issues[0].pointer
        assert "Warning" in report.issues[0].reason
        assert "limited by SDK" in report.issues[0].reason

    def test_warns_runtime_inference_with_ollama(self) -> None:
        """Should warn when runtime-level inference params used with Ollama."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        spec = Spec(
            name="test",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.OLLAMA,
                host="http://localhost:11434",
                temperature=0.5,
                top_p=0.9,
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="test", input="Hello")]),
            ),
            agents={"test": Agent(prompt="Test")},
        )

        report = check_capability(spec)

        # Should have warning issues for both params
        assert len(report.issues) == 2
        pointers = [issue.pointer for issue in report.issues]
        assert "/runtime/temperature" in pointers
        assert "/runtime/top_p" in pointers
        assert all("not supported" in issue.reason for issue in report.issues)

    def test_warns_agent_inference_with_bedrock(self) -> None:
        """Should warn when agent-level inference params used with Bedrock."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        spec = Spec(
            name="test",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.BEDROCK,
                region="us-east-1",
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="test_agent", input="Hello")]),
            ),
            agents={
                "test_agent": Agent(
                    prompt="Test",
                    inference=Inference(temperature=0.8, max_tokens=500),
                ),
            },
        )

        report = check_capability(spec)

        # Should have warning issues
        assert len(report.issues) == 2
        pointers = [issue.pointer for issue in report.issues]
        assert "/agents/test_agent/inference/temperature" in pointers
        assert "/agents/test_agent/inference/max_tokens" in pointers

    def test_no_warning_for_openai(self) -> None:
        """Should not warn when OpenAI provider uses inference params."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        spec = Spec(
            name="test",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.OPENAI,
                temperature=0.7,
                top_p=0.95,
                max_tokens=1000,
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="test_agent", input="Hello")]),
            ),
            agents={
                "test_agent": Agent(
                    prompt="Test",
                    inference=Inference(temperature=0.2),
                ),
            },
        )

        report = check_capability(spec)

        # Should have NO issues (OpenAI fully supports inference params)
        assert len(report.issues) == 0
        assert report.supported is True

    def test_warns_with_multiple_agents_having_inference(self) -> None:
        """Should warn for each agent with inference overrides on non-OpenAI provider."""
        from strands_cli.types import ChainStep, Pattern, PatternConfig, PatternType

        spec = Spec(
            name="test",
            version="1.0",
            runtime=Runtime(
                provider=ProviderType.OLLAMA,
                host="http://localhost:11434",
            ),
            pattern=Pattern(
                type=PatternType.CHAIN,
                config=PatternConfig(steps=[ChainStep(agent="agent1", input="Hello")]),
            ),
            agents={
                "agent1": Agent(
                    prompt="Agent 1",
                    inference=Inference(temperature=0.7),
                ),
                "agent2": Agent(
                    prompt="Agent 2",
                    inference=Inference(top_p=0.9),
                ),
            },
        )

        report = check_capability(spec)

        # Should have warnings for both agents
        assert len(report.issues) == 2
        pointers = [issue.pointer for issue in report.issues]
        assert "/agents/agent1/inference/temperature" in pointers
        assert "/agents/agent2/inference/top_p" in pointers

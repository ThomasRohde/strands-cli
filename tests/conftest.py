"""Pytest configuration and shared fixtures for strands-cli tests.

Provides fixtures for:
- Test fixtures (valid/invalid/unsupported specs)
- Mocked providers (Bedrock, Ollama)
- Mocked Strands Agents
- Temporary directories and file cleanup
- Sample spec data
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

# ============================================================================
# Fixture Paths
# ============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to valid test fixtures."""
    return fixtures_dir / "valid"


@pytest.fixture
def invalid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to invalid test fixtures."""
    return fixtures_dir / "invalid"


@pytest.fixture
def unsupported_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to unsupported test fixtures."""
    return fixtures_dir / "unsupported"


# ============================================================================
# Fixture File Paths
# ============================================================================


@pytest.fixture
def minimal_ollama_spec(valid_fixtures_dir: Path) -> Path:
    """Path to minimal Ollama spec fixture."""
    return valid_fixtures_dir / "minimal-ollama.yaml"


@pytest.fixture
def minimal_bedrock_spec(valid_fixtures_dir: Path) -> Path:
    """Path to minimal Bedrock spec fixture."""
    return valid_fixtures_dir / "minimal-bedrock.yaml"


@pytest.fixture
def with_tools_spec(valid_fixtures_dir: Path) -> Path:
    """Path to spec with tools."""
    return valid_fixtures_dir / "with-tools.yaml"


@pytest.fixture
def with_skills_spec(valid_fixtures_dir: Path) -> Path:
    """Path to spec with skills."""
    return valid_fixtures_dir / "with-skills.yaml"


@pytest.fixture
def with_budgets_spec(valid_fixtures_dir: Path) -> Path:
    """Path to spec with budgets."""
    return valid_fixtures_dir / "with-budgets.yaml"


@pytest.fixture
def with_secrets_spec(valid_fixtures_dir: Path) -> Path:
    """Path to spec with secrets."""
    return valid_fixtures_dir / "with-secrets.yaml"


@pytest.fixture
def missing_required_spec(invalid_fixtures_dir: Path) -> Path:
    """Path to spec missing required fields."""
    return invalid_fixtures_dir / "missing-required.yaml"


@pytest.fixture
def invalid_provider_spec(invalid_fixtures_dir: Path) -> Path:
    """Path to spec with invalid provider."""
    return invalid_fixtures_dir / "invalid-provider.yaml"


@pytest.fixture
def invalid_pattern_spec(invalid_fixtures_dir: Path) -> Path:
    """Path to spec with invalid pattern."""
    return invalid_fixtures_dir / "invalid-pattern.yaml"


@pytest.fixture
def malformed_spec(invalid_fixtures_dir: Path) -> Path:
    """Path to malformed YAML spec."""
    return invalid_fixtures_dir / "malformed.yaml"


@pytest.fixture
def parallel_pattern_spec(valid_fixtures_dir: Path) -> Path:
    """Path to parallel pattern spec (now supported - Phase 3)."""
    return valid_fixtures_dir / "parallel-pattern.yaml"


@pytest.fixture
def multi_agent_chain_spec(valid_fixtures_dir: Path) -> Path:
    """Path to multi-agent chain spec (supported in Phase 2)."""
    return valid_fixtures_dir / "multi-agent-chain.yaml"


@pytest.fixture
def multi_step_chain_spec(valid_fixtures_dir: Path) -> Path:
    """Path to multi-step chain spec (now supported in Phase 1)."""
    return valid_fixtures_dir / "multi-step-chain.yaml"


@pytest.fixture
def multi_task_workflow_spec(valid_fixtures_dir: Path) -> Path:
    """Path to multi-task workflow spec (now supported in Phase 1)."""
    return valid_fixtures_dir / "multi-task-workflow.yaml"


@pytest.fixture
def routing_pattern_spec(valid_fixtures_dir: Path) -> Path:
    """Path to routing pattern spec (supported in Phase 2)."""
    return valid_fixtures_dir / "routing-pattern.yaml"


@pytest.fixture
def mcp_tools_spec(unsupported_fixtures_dir: Path) -> Path:
    """Path to MCP tools spec (unsupported)."""
    return unsupported_fixtures_dir / "mcp-tools.yaml"


@pytest.fixture
def multi_agent_spec(unsupported_fixtures_dir: Path) -> Path:
    """Path to parallel pattern spec (unsupported - Phase 3).

    Alias for parallel_pattern_spec to maintain backward compatibility with tests
    that expect an unsupported multi-feature spec.
    """
    return unsupported_fixtures_dir / "parallel-pattern.yaml"


# ============================================================================
# Temporary Directories
# ============================================================================


@pytest.fixture
def temp_output_dir() -> Any:
    """Create a temporary directory for test outputs, clean up after test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_artifacts_dir(temp_output_dir: Path) -> Path:
    """Create a temporary artifacts directory."""
    artifacts_dir = temp_output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


# ============================================================================
# Mock Providers
# ============================================================================


@pytest.fixture
def mock_bedrock_client(mocker: Any) -> Mock:
    """Mock boto3 Bedrock client."""
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Mocked Bedrock response"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 20},
    }

    # Mock boto3.client() to return our mock client
    mocker.patch("boto3.client", return_value=mock_client)

    return mock_client


@pytest.fixture
def mock_ollama_client(mocker: Any) -> Mock:
    """Mock Ollama client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.message.content = "Mocked Ollama response"
    mock_client.chat.return_value = mock_response

    # Mock ollama.Client
    mocker.patch("ollama.Client", return_value=mock_client)

    return mock_client


@pytest.fixture
def mock_openai_client(mocker: Any) -> Mock:
    """Mock OpenAI client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "Mocked OpenAI response"
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_client.chat.completions.create.return_value = mock_response

    # Mock OpenAI client
    mocker.patch("openai.OpenAI", return_value=mock_client)

    return mock_client


# ============================================================================
# Mock Strands Agent
# ============================================================================


@pytest.fixture
def mock_strands_agent(mocker: Any) -> Mock:
    """Mock Strands Agent for execution tests."""
    from unittest.mock import AsyncMock

    mock_agent = MagicMock()

    # Use AsyncMock for invoke_async to handle awaitable properly
    mock_agent.invoke_async = AsyncMock(return_value="Mocked agent execution result")

    # Mock Agent class constructor
    mocker.patch("strands_cli.runtime.strands_adapter.Agent", return_value=mock_agent)

    return mock_agent


@pytest.fixture
def mock_agent_result_with_usage() -> MagicMock:
    """Mock Strands Agent result with realistic usage metrics.
    
    Returns a mock result object that simulates Strands SDK's AfterInvocationEvent
    with accumulated usage data for context compaction testing.
    """
    mock_result = MagicMock()
    mock_result.output = "Mocked agent response"
    mock_result.accumulated_usage = {
        "totalTokens": 1500,
        "inputTokens": 1000,
        "outputTokens": 500,
    }
    mock_result.tool_results = []
    mock_result.input_summary = "Test input"
    return mock_result


@pytest.fixture
def mock_create_model(mocker: Any) -> Mock:
    """Mock the create_model function to avoid actual provider connections."""
    # Mock create_model to return a mock model object
    mock_model = mocker.MagicMock()
    mocker.patch(
        "strands_cli.runtime.strands_adapter.create_model",
        return_value=mock_model,
    )
    return mock_model


# ============================================================================
# Sample Spec Data
# ============================================================================


@pytest.fixture
def sample_minimal_spec_dict() -> dict[str, Any]:
    """Return a minimal valid spec as a dictionary."""
    return {
        "version": 0,
        "name": "test-spec",
        "runtime": {
            "provider": "ollama",
            "model_id": "gpt-oss",
            "host": "http://localhost:11434",
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "test_agent",
                        "input": "Test input",
                    }
                ]
            },
        },
        "outputs": {
            "artifacts": [
                {
                    "path": "./artifacts/test-output.txt",
                    "from": "{{ last_response }}",
                }
            ]
        },
    }


@pytest.fixture
def sample_bedrock_spec_dict() -> dict[str, Any]:
    """Return a Bedrock spec as a dictionary."""
    return {
        "version": 0,
        "name": "bedrock-test",
        "runtime": {
            "provider": "bedrock",
            "model_id": "us.anthropic.claude-3-sonnet-20240229-v1:0",
            "region": "us-east-1",
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "test_agent",
                        "input": "Test input",
                    }
                ]
            },
        },
        "outputs": {
            "artifacts": [
                {
                    "path": "./artifacts/test-output.txt",
                    "from": "{{ last_response }}",
                }
            ]
        },
    }


@pytest.fixture
def sample_ollama_spec(sample_minimal_spec_dict: dict[str, Any]) -> Any:
    """Return a minimal Ollama spec as a Spec object (mutable for tests)."""
    from strands_cli.types import Spec

    return Spec.model_validate(sample_minimal_spec_dict)


@pytest.fixture
def sample_bedrock_spec(sample_bedrock_spec_dict: dict[str, Any]) -> Any:
    """Return a minimal Bedrock spec as a Spec object (mutable for tests)."""
    from strands_cli.types import Spec

    return Spec.model_validate(sample_bedrock_spec_dict)


@pytest.fixture
def sample_openai_spec_dict() -> dict[str, Any]:
    """Return an OpenAI spec as a dictionary."""
    return {
        "version": 0,
        "name": "openai-test",
        "runtime": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        "agents": {
            "test_agent": {
                "prompt": "You are a test agent.",
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "test_agent",
                        "input": "Test input",
                    }
                ]
            },
        },
        "outputs": {
            "artifacts": [
                {
                    "path": "./artifacts/test-output.txt",
                    "from": "{{ last_response }}",
                }
            ]
        },
    }


@pytest.fixture
def sample_openai_spec(sample_openai_spec_dict: dict[str, Any]) -> Any:
    """Return a minimal OpenAI spec as a Spec object (mutable for tests)."""
    from strands_cli.types import Spec

    return Spec.model_validate(sample_openai_spec_dict)


# ============================================================================
# Environment Variables
# ============================================================================


@pytest.fixture
def clean_env(monkeypatch: Any) -> None:
    """Clean up environment variables for isolated tests."""
    # Remove any STRANDS_ env vars
    env_vars_to_remove = [
        "STRANDS_AWS_REGION",
        "STRANDS_BEDROCK_MODEL_ID",
        "STRANDS_VERBOSE",
        "STRANDS_CONFIG_DIR",
    ]
    for var in env_vars_to_remove:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_env_secrets(monkeypatch: Any) -> None:
    """Set up mock environment secrets for testing."""
    monkeypatch.setenv("API_KEY", "test-api-key-12345")
    monkeypatch.setenv("DB_PASSWORD", "test-db-password")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow-running tests")

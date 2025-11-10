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
def evaluator_optimizer_spec_fixture() -> Any:
    """Evaluator-optimizer spec for testing (Phase 3.3)."""
    from strands_cli.types import Spec

    spec_dict = {
        "version": 0,
        "name": "test-evaluator-optimizer",
        "runtime": {
            "provider": "ollama",
            "model_id": "llama3.2:3b",
            "budgets": {
                "max_tokens": 10000,
            },
        },
        "agents": {
            "producer": {
                "prompt": "You are a content producer. {{ task }}",
            },
            "evaluator": {
                "prompt": "You are an evaluator.",
            },
        },
        "pattern": {
            "type": "evaluator_optimizer",
            "config": {
                "producer": "producer",
                "evaluator": {
                    "agent": "evaluator",
                    "input": "Evaluate: {{ draft }}",
                },
                "accept": {
                    "min_score": 80,
                    "max_iters": 5,
                },
            },
        },
    }

    return Spec.model_validate(spec_dict)


@pytest.fixture
def graph_spec_fixture() -> Any:
    """Graph pattern spec for testing (Phase 3.3)."""
    from strands_cli.types import Spec

    spec_dict = {
        "version": 0,
        "name": "test-graph",
        "runtime": {
            "provider": "ollama",
            "model_id": "llama3.2:3b",
            "budgets": {
                "max_tokens": 5000,
                "max_steps": 10,
            },
        },
        "agents": {
            "loader": {
                "prompt": "Load data",
            },
            "analyzer": {
                "prompt": "Analyze data",
            },
            "reporter": {
                "prompt": "Generate report",
            },
        },
        "pattern": {
            "type": "graph",
            "config": {
                "nodes": {
                    "load": {
                        "agent": "loader",
                        "input": "Load initial data",
                    },
                    "analyze": {
                        "agent": "analyzer",
                        "input": "Analyze {{ nodes.load.response }}",
                    },
                    "report": {
                        "agent": "reporter",
                        "input": "Report on {{ nodes.analyze.response }}",
                    },
                },
                "edges": [
                    {"from": "load", "to": ["analyze"]},
                    {"from": "analyze", "to": ["report"]},
                ],
                "max_iterations": 10,
            },
        },
    }

    return Spec.model_validate(spec_dict)


@pytest.fixture
def mcp_tools_spec(valid_fixtures_dir: Path) -> Path:
    """Path to MCP tools spec (Phase 9 - now supported)."""
    return valid_fixtures_dir / "mcp-tools.yaml"


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


@pytest.fixture
def sample_spec_with_compaction_dict() -> dict[str, Any]:
    """Return a spec with compaction configuration as a dictionary."""
    return {
        "version": 0,
        "name": "compaction-test",
        "runtime": {
            "provider": "ollama",
            "model_id": "gpt-oss",
            "host": "http://localhost:11434",
        },
        "context_policy": {
            "compaction": {
                "enabled": True,
                "when_tokens_over": 5000,
                "summary_ratio": 0.4,
                "preserve_recent_messages": 10,
                "summarization_model": "gpt-4o-mini",
            }
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
    }


@pytest.fixture
def sample_spec_with_notes_dict() -> dict[str, Any]:
    """Return a spec with notes configuration as a dictionary."""
    return {
        "version": 0,
        "name": "notes-test",
        "runtime": {
            "provider": "ollama",
            "model_id": "gpt-oss",
            "host": "http://localhost:11434",
        },
        "context_policy": {
            "notes": {
                "file": "artifacts/test-notes.md",
                "include_last": 8,
                "format": "markdown",
            }
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
    }


@pytest.fixture
def sample_spec_with_full_context_policy_dict() -> dict[str, Any]:
    """Return a spec with complete context policy as a dictionary."""
    return {
        "version": 0,
        "name": "full-context-policy-test",
        "runtime": {
            "provider": "ollama",
            "model_id": "gpt-oss",
            "host": "http://localhost:11434",
        },
        "context_policy": {
            "compaction": {
                "enabled": True,
                "when_tokens_over": 4000,
                "summary_ratio": 0.35,
                "preserve_recent_messages": 12,
            },
            "notes": {
                "file": "artifacts/workflow-notes.md",
                "include_last": 12,
                "format": "markdown",
            },
            "retrieval": {
                "jit_tools": ["grep", "head", "tail", "search"],
            },
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
    }


@pytest.fixture
def chain_with_hitl_spec_dict() -> dict[str, Any]:
    """Complete 3-step chain spec with HITL approval gate (dict format)."""
    return {
        "name": "chain-hitl-test",
        "version": 1,
        "description": "Test workflow with HITL approval step",
        "runtime": {
            "provider": "ollama",
            "model_id": "llama2",
        },
        "agents": {
            "researcher": {
                "prompt": "You are a research assistant. Provide concise summaries.",
            },
            "analyst": {
                "prompt": "You are an analyst. Review and analyze information.",
            },
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    # Step 0: Initial research
                    {
                        "agent": "researcher",
                        "input": "Research {{ topic }}",
                    },
                    # Step 1: HITL approval gate
                    {
                        "type": "hitl",
                        "prompt": "Review the research findings. Approve to proceed?",
                        "context_display": "{{ steps[0].response }}",
                        "default": "approved",
                        "timeout_seconds": 3600,
                    },
                    # Step 2: Analysis with HITL response
                    {
                        "agent": "analyst",
                        "input": "User decision: {{ hitl_response }}\nAnalyze: {{ steps[0].response }}",
                    },
                ]
            },
        },
        "inputs": {
            "values": {
                "topic": "AI safety",
            }
        },
    }


@pytest.fixture
def mock_hitl_step_history() -> list[dict[str, Any]]:
    """Mock step history with HITL step for testing template context."""
    return [
        # Step 0: Agent step
        {
            "index": 0,
            "agent": "researcher",
            "response": "Research findings: AI safety is critical...",
            "tokens_estimated": 150,
        },
        # Step 1: HITL step
        {
            "index": 1,
            "type": "hitl",
            "prompt": "Review the research. Approve?",
            "response": "approved with minor revisions",
            "tokens_estimated": 0,
        },
    ]


@pytest.fixture
def hitl_session_state(chain_with_hitl_spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Mock SessionState for HITL pause/resume testing."""
    from strands_cli.types import HITLState

    hitl_state = HITLState(
        active=True,
        step_index=1,
        prompt="Review the research findings. Approve to proceed?",
        context_display="Research findings: AI safety is critical...",
        user_response=None,
    )

    return {
        "metadata": {
            "session_id": "test-hitl-session-123",
            "workflow_name": "chain-hitl-test",
            "pattern_type": "chain",
            "status": "paused",
            "created_at": "2025-11-10T10:00:00Z",
            "updated_at": "2025-11-10T10:05:00Z",
        },
        "variables": {"topic": "AI safety"},
        "pattern_state": {
            "step_history": [
                {
                    "index": 0,
                    "agent": "researcher",
                    "response": "Research findings: AI safety is critical...",
                    "tokens_estimated": 150,
                }
            ],
            "hitl_state": hitl_state.model_dump(),
        },
        "token_usage": {
            "total_input_tokens": 100,
            "total_output_tokens": 150,
        },
    }


@pytest.fixture
def double_hitl_spec() -> Any:
    """Workflow with 2 HITL steps for testing resume re-pause (BLOCKER 1)."""
    from strands_cli.types import (
        Agent,
        ChainStep,
        Pattern,
        PatternConfig,
        PatternType,
        Runtime,
        Spec,
    )

    return Spec(
        name="test-double-hitl",
        runtime=Runtime(provider="ollama", model_id="llama3.2:3b", host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test agent for multi-HITL workflow")},
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(
                steps=[
                    ChainStep(agent="agent1", input="Execute step 0"),
                    ChainStep(type="hitl", prompt="First approval - review step 0?"),
                    ChainStep(agent="agent1", input="Execute step 2"),
                    ChainStep(type="hitl", prompt="Second approval - review step 2?"),
                    ChainStep(agent="agent1", input="Execute final step"),
                ]
            ),
        ),
    )


@pytest.fixture
def minimal_chain_spec() -> Any:
    """Minimal chain spec without HITL steps for testing normal execution."""
    from strands_cli.types import (
        Agent,
        ChainStep,
        Pattern,
        PatternConfig,
        PatternType,
        Runtime,
        Spec,
    )

    return Spec(
        name="test-minimal-chain",
        runtime=Runtime(provider="ollama", model_id="llama3.2:3b", host="http://localhost:11434"),
        agents={"agent1": Agent(prompt="Test agent")},
        pattern=Pattern(
            type=PatternType.CHAIN,
            config=PatternConfig(
                steps=[
                    ChainStep(agent="agent1", input="Step 1"),
                    ChainStep(agent="agent1", input="Step 2"),
                ]
            ),
        ),
    )


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

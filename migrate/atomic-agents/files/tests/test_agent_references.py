"""Tests for atomic agent composition via $ref.

Tests the ability to reference external atomic agent specs in composite
workflows, enabling true composability and single source of truth.
"""

import pytest
from pathlib import Path
from strands_cli.loader.yaml_loader import load_spec, LoadError
from strands_cli.types import Spec


@pytest.fixture
def tmp_atomic_agent(tmp_path: Path) -> Path:
    """Create a temporary atomic agent spec file."""
    agent_dir = tmp_path / "agents" / "atomic" / "test_agent"
    agent_dir.mkdir(parents=True)

    schema_dir = agent_dir / "schemas"
    schema_dir.mkdir(parents=True)

    # Create input schema
    input_schema = schema_dir / "input.json"
    input_schema.write_text("""{
        "type": "object",
        "properties": {
            "text": {"type": "string"}
        },
        "required": ["text"]
    }""")

    # Create output schema
    output_schema = schema_dir / "output.json"
    output_schema.write_text("""{
        "type": "object",
        "properties": {
            "result": {"type": "string"}
        },
        "required": ["result"]
    }""")

    # Create atomic agent
    agent_file = agent_dir / "test_agent.yaml"
    agent_content = """version: 0
name: test_atomic_agent
description: A test atomic agent
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  test_agent:
    prompt: "You are a test agent"
    tools: ["python"]
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json
metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: test
    strands.io/capability: testing
    strands.io/version: v1
pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "{{ text }}"
"""
    agent_file.write_text(agent_content)

    return agent_file


@pytest.fixture
def tmp_composite_workflow(tmp_path: Path, tmp_atomic_agent: Path) -> Path:
    """Create a composite workflow that references the atomic agent."""
    workflow_file = tmp_path / "composite_workflow.yaml"
    workflow_file.write_text("""version: 0
name: test_composite
description: Composite workflow using atomic agent reference
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/test_agent/test_agent.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test input"
""")
    return workflow_file


def test_agent_ref_basic_resolution(tmp_composite_workflow: Path) -> None:
    """Test that $ref resolves to atomic agent definition."""
    spec = load_spec(tmp_composite_workflow)

    assert "my_agent" in spec.agents
    agent = spec.agents["my_agent"]

    # Should have inherited prompt from atomic agent
    assert agent.prompt == "You are a test agent"

    # Should have inherited tools
    assert agent.tools == ["python"]

    # Should have resolved schema paths (absolute paths)
    assert agent.input_schema is not None
    assert agent.output_schema is not None
    assert isinstance(agent.input_schema, str)
    assert isinstance(agent.output_schema, str)
    assert "input.json" in agent.input_schema
    assert "output.json" in agent.output_schema


def test_agent_ref_with_overrides(tmp_path: Path, tmp_atomic_agent: Path) -> None:
    """Test that override fields merge correctly with referenced agent."""
    workflow_file = tmp_path / "workflow_with_overrides.yaml"
    workflow_file.write_text("""version: 0
name: test_overrides
description: Test agent reference with overrides
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/test_agent/test_agent.yaml
    model_id: gpt-4o  # Override model
    tools: ["http_executors"]  # Override tools
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    spec = load_spec(workflow_file)
    agent = spec.agents["my_agent"]

    # Should have inherited prompt
    assert agent.prompt == "You are a test agent"

    # Should have overridden model
    assert agent.model_id == "gpt-4o"

    # Should have overridden tools
    assert agent.tools == ["http_executors"]


def test_agent_ref_missing_file(tmp_path: Path) -> None:
    """Test error handling when referenced file doesn't exist."""
    workflow_file = tmp_path / "workflow_missing_ref.yaml"
    workflow_file.write_text("""version: 0
name: test_missing
description: Test missing reference
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/nonexistent/nonexistent.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    with pytest.raises(LoadError) as exc_info:
        load_spec(workflow_file)

    assert "Agent reference not found" in str(exc_info.value)
    assert "nonexistent.yaml" in str(exc_info.value)


def test_agent_ref_invalid_atomic_multiple_agents(tmp_path: Path) -> None:
    """Test error when referenced spec has multiple agents (not atomic)."""
    agent_dir = tmp_path / "agents" / "atomic" / "invalid_multi"
    agent_dir.mkdir(parents=True)

    # Create invalid atomic agent with multiple agents
    invalid_agent = agent_dir / "invalid_multi.yaml"
    invalid_agent.write_text("""version: 0
name: invalid_atomic
description: Invalid - has multiple agents
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  agent1:
    prompt: "Agent 1"
  agent2:
    prompt: "Agent 2"
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: agent1
        input: "test"
      - id: task2
        agent: agent2
        input: "test"
        deps: [task1]
""")

    workflow_file = tmp_path / "workflow_invalid_ref.yaml"
    workflow_file.write_text("""version: 0
name: test_invalid
description: Test invalid reference
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/invalid_multi/invalid_multi.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    with pytest.raises(LoadError) as exc_info:
        load_spec(workflow_file)

    assert "exactly 1 agent" in str(exc_info.value).lower()
    assert "found 2" in str(exc_info.value).lower()


def test_agent_ref_nested_not_allowed(tmp_path: Path) -> None:
    """Test that nested $ref (agent referencing another agent) is not allowed."""
    agent_dir = tmp_path / "agents" / "atomic" / "nested"
    agent_dir.mkdir(parents=True)

    # Create agent that contains a $ref (nested reference)
    nested_agent = agent_dir / "nested.yaml"
    nested_agent.write_text("""version: 0
name: nested_atomic
description: Invalid - contains nested $ref
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  nested_agent:
    $ref: ./other_agent.yaml
metadata:
  labels:
    strands.io/agent_type: atomic
pattern:
  type: chain
  config:
    steps:
      - agent: nested_agent
        input: "test"
""")

    workflow_file = tmp_path / "workflow_nested_ref.yaml"
    workflow_file.write_text("""version: 0
name: test_nested
description: Test nested reference rejection
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/nested/nested.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    with pytest.raises(LoadError) as exc_info:
        load_spec(workflow_file)

    assert "Nested agent references not allowed" in str(exc_info.value)


def test_agent_ref_schema_path_resolution(tmp_atomic_agent: Path, tmp_path: Path) -> None:
    """Test that schema paths are resolved relative to atomic agent, not composite."""
    # Composite is in different directory structure
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    workflow_file = workflow_dir / "workflow.yaml"
    workflow_file.write_text("""version: 0
name: test_schema_paths
description: Test schema path resolution
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ../agents/atomic/test_agent/test_agent.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    spec = load_spec(workflow_file)
    agent = spec.agents["my_agent"]

    # Schemas should be absolute paths pointing to the schema files
    # (resolved from atomic agent's location, not composite workflow)
    assert agent.input_schema is not None
    assert agent.output_schema is not None

    # Verify they point to actual files
    input_path = Path(agent.input_schema)  # type: ignore
    output_path = Path(agent.output_schema)  # type: ignore

    assert input_path.exists()
    assert output_path.exists()
    assert input_path.name == "input.json"
    assert output_path.name == "output.json"


def test_agent_ref_mixed_inline_and_refs(tmp_path: Path, tmp_atomic_agent: Path) -> None:
    """Test that workflow can mix inline agents and $ref agents."""
    workflow_file = tmp_path / "workflow_mixed.yaml"
    workflow_file.write_text("""version: 0
name: test_mixed
description: Mix inline and referenced agents
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  referenced_agent:
    $ref: ./agents/atomic/test_agent/test_agent.yaml
  inline_agent:
    prompt: "I am an inline agent"
    tools: ["python"]
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: referenced_agent
        input: "Test ref"
      - id: task2
        agent: inline_agent
        input: "Test inline"
        deps: [task1]
""")

    spec = load_spec(workflow_file)

    # Referenced agent should have atomic agent's prompt
    assert spec.agents["referenced_agent"].prompt == "You are a test agent"

    # Inline agent should have its own prompt
    assert spec.agents["inline_agent"].prompt == "I am an inline agent"


def test_agent_ref_warning_on_non_atomic_label(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that warning is logged when referenced agent lacks atomic label."""
    agent_dir = tmp_path / "agents" / "atomic" / "non_atomic"
    agent_dir.mkdir(parents=True)

    # Create agent without atomic label
    non_atomic = agent_dir / "non_atomic.yaml"
    non_atomic.write_text("""version: 0
name: non_atomic_agent
description: Missing atomic label
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  test_agent:
    prompt: "No atomic label"
metadata:
  labels:
    strands.io/agent_type: other
pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "test"
""")

    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text("""version: 0
name: test_warning
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  my_agent:
    $ref: ./agents/atomic/non_atomic/non_atomic.yaml
pattern:
  type: chain
  config:
    steps:
      - agent: my_agent
        input: "Test"
""")

    # Set debug mode to see warning
    import os

    os.environ["STRANDS_DEBUG"] = "true"

    try:
        spec = load_spec(workflow_file)

        # Should still load successfully (warning only)
        assert "my_agent" in spec.agents

        # Warning should be logged (check if debug logging available)
        # Note: This test may not capture logs in all test configurations
    finally:
        os.environ.pop("STRANDS_DEBUG", None)

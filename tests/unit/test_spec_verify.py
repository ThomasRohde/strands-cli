"""Unit tests for spec_verify native tool.

Tests the spec verification tool which validates workflow specs
and returns structured JSON validation reports.
"""

import json


class TestSpecVerifyToolSpec:
    """Test TOOL_SPEC definition for spec_verify."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in spec_verify module."""
        from strands_cli.tools import spec_verify

        assert hasattr(spec_verify, "TOOL_SPEC")
        assert isinstance(spec_verify.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.spec_verify import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "spec_verify"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.spec_verify import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "spec_content" in input_schema["properties"]
        assert "check_capability" in input_schema["properties"]
        assert "spec_content" in input_schema["required"]
        assert input_schema["properties"]["check_capability"]["default"] is True


class TestSpecVerifyFunction:
    """Test spec_verify function behavior."""

    def test_spec_verify_callable_exists(self) -> None:
        """Test that spec_verify function is defined and callable."""
        from strands_cli.tools.spec_verify import spec_verify

        assert callable(spec_verify)

    def test_valid_yaml_spec_success(self) -> None:
        """Test validation of a valid YAML workflow spec."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: test-workflow
description: Test workflow

runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434

agents:
  test_agent:
    prompt: "Test prompt"

pattern:
  type: chain
  config:
    steps:
      - agent: test_agent
        input: "Test input"
"""

        tool_input = {
            "toolUseId": "verify-001",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["toolUseId"] == "verify-001"
        assert result["status"] == "success"
        assert len(result["content"]) == 1
        assert "json" in result["content"][0]

        report = result["content"][0]["json"]
        assert report["schema_valid"] is True
        assert report["pydantic_valid"] is True
        assert report["capability_supported"] is True
        assert len(report["errors"]) == 0
        assert len(report["issues"]) == 0
        assert report["spec_info"]["name"] == "test-workflow"
        assert report["spec_info"]["pattern_type"] == "chain"

    def test_valid_json_spec_success(self) -> None:
        """Test validation of a valid JSON workflow spec."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = json.dumps(
            {
                "version": 0,
                "name": "json-workflow",
                "runtime": {
                    "provider": "ollama",
                    "model_id": "test-model",
                    "host": "http://localhost:11434",
                },
                "agents": {"test": {"prompt": "test"}},
                "pattern": {
                    "type": "chain",
                    "config": {"steps": [{"agent": "test", "input": "test"}]},
                },
            }
        )

        tool_input = {
            "toolUseId": "verify-json",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is True
        assert report["spec_info"]["name"] == "json-workflow"

    def test_empty_spec_content_error(self) -> None:
        """Test that empty spec content returns appropriate error."""
        from strands_cli.tools.spec_verify import spec_verify

        tool_input = {
            "toolUseId": "verify-empty",
            "input": {"spec_content": ""},
        }

        result = spec_verify(tool_input)

        assert result["toolUseId"] == "verify-empty"
        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        assert len(report["errors"]) == 1
        assert report["errors"][0]["phase"] == "input"
        assert "No spec_content provided" in report["errors"][0]["message"]

    def test_invalid_yaml_syntax_error(self) -> None:
        """Test that invalid YAML syntax is caught."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: broken
invalid yaml: [unclosed bracket
"""

        tool_input = {
            "toolUseId": "verify-bad-yaml",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        assert len(report["errors"]) == 1
        assert report["errors"][0]["phase"] == "parse"
        assert report["errors"][0]["type"] == "LoadError"

    def test_invalid_json_syntax_error(self) -> None:
        """Test that invalid JSON syntax is caught."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = '{"version": 0, "name": "broken", invalid}'

        tool_input = {
            "toolUseId": "verify-bad-json",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        # Invalid JSON gets parsed as YAML (with schema errors)
        assert report["errors"][0]["phase"] == "schema"

    def test_schema_validation_error(self) -> None:
        """Test that schema validation errors are reported."""
        from strands_cli.tools.spec_verify import spec_verify

        # Missing required 'version' field
        spec_content = """
name: missing-version
runtime:
  provider: ollama
  host: http://localhost:11434
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-schema",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        assert report["pydantic_valid"] is False
        assert len(report["errors"]) == 1
        assert report["errors"][0]["phase"] == "schema"
        assert report["errors"][0]["type"] == "SchemaValidationError"
        assert "validation_errors" in report["errors"][0]

    def test_missing_required_runtime_field(self) -> None:
        """Test schema validation for missing runtime field."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: missing-runtime
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-no-runtime",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False

    def test_unsupported_pattern_type(self) -> None:
        """Test capability check for unsupported feature."""
        from strands_cli.tools.spec_verify import spec_verify

        # MCP tools are not supported and also fail schema validation
        spec_content = """
version: 0
name: test-capability
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  test: {prompt: "test"}
tools:
  mcp:
    - server: unsupported
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-unsupported",
            "input": {"spec_content": spec_content, "check_capability": True},
        }

        result = spec_verify(tool_input)

        # MCP tools fail schema validation
        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False

    def test_unsupported_provider(self) -> None:
        """Test capability check for unsupported provider."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: unsupported-provider
runtime:
  provider: unknown_provider
  model_id: test-model
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-provider",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        # Pydantic validation should fail on invalid provider enum
        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is True
        assert report["pydantic_valid"] is False
        assert report["errors"][0]["phase"] == "pydantic"

    def test_check_capability_false_skips_capability_check(self) -> None:
        """Test that check_capability=false skips capability validation."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: test-skip-capability
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-no-cap",
            "input": {"spec_content": spec_content, "check_capability": False},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is True
        assert report["pydantic_valid"] is True
        assert report["capability_supported"] is None
        assert len(report["issues"]) == 0

    def test_workflow_pattern_with_valid_dag(self) -> None:
        """Test validation of workflow pattern with valid DAG."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: workflow-dag
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  agent1: {prompt: "test1"}
  agent2: {prompt: "test2"}
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: agent1
        input: "First task"
      - id: task2
        agent: agent2
        input: "Second task"
        deps: [task1]
"""

        tool_input = {
            "toolUseId": "verify-workflow",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is True
        assert len(report["issues"]) == 0

    def test_workflow_pattern_with_cycle_detection(self) -> None:
        """Test capability check detects cycles in workflow DAG."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: workflow-cycle
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  agent1: {prompt: "test1"}
  agent2: {prompt: "test2"}
pattern:
  type: workflow
  config:
    tasks:
      - id: task1
        agent: agent1
        input: "First"
        deps: [task2]
      - id: task2
        agent: agent2
        input: "Second"
        deps: [task1]
"""

        tool_input = {
            "toolUseId": "verify-cycle",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is False
        assert any("cycle" in issue["reason"].lower() for issue in report["issues"])

    def test_parallel_pattern_validation(self) -> None:
        """Test validation of parallel pattern."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: parallel-test
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  agent1: {prompt: "test1"}
  agent2: {prompt: "test2"}
pattern:
  type: parallel
  config:
    branches:
      - id: branch1
        steps:
          - agent: agent1
            input: "Branch 1"
      - id: branch2
        steps:
          - agent: agent2
            input: "Branch 2"
"""

        tool_input = {
            "toolUseId": "verify-parallel",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is True
        assert report["spec_info"]["pattern_type"] == "parallel"

    def test_routing_pattern_validation(self) -> None:
        """Test validation of routing pattern."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: routing-test
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  router: {prompt: "route"}
  handler1: {prompt: "handle1"}
  handler2: {prompt: "handle2"}
pattern:
  type: routing
  config:
    router:
      agent: router
      input: "Route this"
    routes:
      route1:
        then:
          - agent: handler1
            input: "Handle 1"
      route2:
        then:
          - agent: handler2
            input: "Handle 2"
"""

        tool_input = {
            "toolUseId": "verify-routing",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is True
        assert report["spec_info"]["pattern_type"] == "routing"

    def test_evaluator_optimizer_pattern_validation(self) -> None:
        """Test validation of evaluator-optimizer pattern."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: eval-opt-test
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  producer: {prompt: "produce"}
  evaluator: {prompt: "evaluate"}
pattern:
  type: evaluator_optimizer
  config:
    producer: producer
    evaluator:
      agent: evaluator
      input: "evaluate: {{ draft }}"
    accept:
      min_score: 85
      max_iters: 3
"""

        tool_input = {
            "toolUseId": "verify-eval-opt",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is True
        assert report["spec_info"]["pattern_type"] == "evaluator_optimizer"

    def test_spec_too_large_error(self) -> None:
        """Test that oversized specs are rejected."""
        from strands_cli.tools.spec_verify import spec_verify

        # Create a spec larger than 10MB
        large_content = "x" * (11 * 1024 * 1024)

        tool_input = {
            "toolUseId": "verify-large",
            "input": {"spec_content": large_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        assert "too large" in report["errors"][0]["message"].lower()

    def test_spec_not_dict_error(self) -> None:
        """Test that non-dictionary specs are rejected."""
        from strands_cli.tools.spec_verify import spec_verify

        # YAML list instead of dict
        spec_content = """
- item1
- item2
- item3
"""

        tool_input = {
            "toolUseId": "verify-list",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "error"
        report = result["content"][0]["json"]
        assert report["schema_valid"] is False
        assert "dictionary" in report["errors"][0]["message"].lower()

    def test_disallowed_python_tool(self) -> None:
        """Test capability check for disallowed Python tool."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: disallowed-tool
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  test:
    prompt: "test"
tools:
  python:
    - dangerous.eval
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-tool",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is False
        assert any("not in allowlist" in issue["reason"] for issue in report["issues"])

    def test_missing_tooluseid_handled(self) -> None:
        """Test that missing toolUseId is handled gracefully."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: test
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            # No toolUseId
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["toolUseId"] == ""
        assert result["status"] == "success"

    def test_spec_info_includes_agent_count(self) -> None:
        """Test that spec_info includes agent count."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: multi-agent
runtime:
  provider: ollama
  model_id: test-model
  host: http://localhost:11434
agents:
  agent1: {prompt: "test1"}
  agent2: {prompt: "test2"}
  agent3: {prompt: "test3"}
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-agents",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["spec_info"]["agent_count"] == 3

    def test_bedrock_missing_region(self) -> None:
        """Test capability check for Bedrock without region."""
        from strands_cli.tools.spec_verify import spec_verify

        spec_content = """
version: 0
name: bedrock-no-region
runtime:
  provider: bedrock
  model_id: test-model
agents:
  test: {prompt: "test"}
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "test"
"""

        tool_input = {
            "toolUseId": "verify-bedrock",
            "input": {"spec_content": spec_content},
        }

        result = spec_verify(tool_input)

        assert result["status"] == "success"
        report = result["content"][0]["json"]
        assert report["capability_supported"] is False
        assert any(
            "region" in issue["pointer"] and "bedrock" in issue["reason"].lower()
            for issue in report["issues"]
        )

"""Unit tests for YAML/JSON loader module."""

import json
from pathlib import Path

import pytest

from strands_cli.loader.yaml_loader import LoadError, load_spec, parse_variables
from strands_cli.schema.validator import SchemaValidationError


@pytest.mark.unit
class TestLoadSpec:
    """Test spec loading and parsing functionality."""

    def test_load_yaml_minimal_ollama(self, minimal_ollama_spec: Path) -> None:
        """Test loading minimal Ollama YAML spec."""
        spec = load_spec(minimal_ollama_spec)

        assert spec.name == "minimal-ollama"
        assert spec.version == 0
        assert spec.runtime.provider == "ollama"
        assert spec.runtime.model_id == "gpt-oss"
        assert spec.runtime.host == "http://localhost:11434"
        assert len(spec.agents) == 1
        assert "simple" in spec.agents

    def test_load_yaml_minimal_bedrock(self, minimal_bedrock_spec: Path) -> None:
        """Test loading minimal Bedrock YAML spec."""
        spec = load_spec(minimal_bedrock_spec)

        assert spec.name == "minimal-bedrock"
        assert spec.runtime.provider == "bedrock"
        assert spec.runtime.region == "us-east-1"
        assert "simple" in spec.agents

    def test_load_yaml_with_tools(self, with_tools_spec: Path) -> None:
        """Test loading spec with tools."""
        spec = load_spec(with_tools_spec)

        assert spec.tools is not None
        # Python tools are structured objects in Pydantic, but strings in YAML/schema
        # The loader should handle this automatically via Pydantic validation
        assert spec.tools.http_executors is not None
        assert len(spec.tools.http_executors) == 1
        assert spec.tools.http_executors[0].id == "api"

    def test_load_python_tools_string_format(self, temp_output_dir: Path) -> None:
        """Test that Python tools in string format are converted to PythonTool objects."""
        spec_file = temp_output_dir / "python-tools.yaml"
        spec_content = """
version: 0
name: python-tools-test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
tools:
  python:
    - http_request
    - calculator
agents:
  test:
    prompt: "Test agent"
    tools:
      - http_request
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        spec = load_spec(spec_file)

        # Verify that string format was converted to PythonTool objects
        assert spec.tools is not None
        assert spec.tools.python is not None
        assert len(spec.tools.python) == 2
        assert spec.tools.python[0].callable == "http_request"
        assert spec.tools.python[1].callable == "calculator"

    def test_load_yaml_with_skills(self, with_skills_spec: Path) -> None:
        """Test loading spec with skills."""
        spec = load_spec(with_skills_spec)

        assert spec.skills is not None
        assert len(spec.skills) == 2
        assert spec.skills[0].id == "python-basics"
        assert spec.skills[1].id == "testing"

    def test_load_yaml_with_budgets(self, with_budgets_spec: Path) -> None:
        """Test loading spec with budgets and failure policy."""
        spec = load_spec(with_budgets_spec)

        # budgets and failure_policy are dict[str, Any] in the Pydantic model
        assert spec.runtime.budgets is not None
        assert spec.runtime.budgets["max_steps"] == 100
        assert spec.runtime.budgets["max_tokens"] == 50000
        assert spec.runtime.budgets["max_duration_s"] == 300

        assert spec.runtime.failure_policy is not None
        assert spec.runtime.failure_policy["retries"] == 3
        assert spec.runtime.failure_policy["backoff"] == "exponential"

    def test_load_yaml_with_secrets(self, with_secrets_spec: Path) -> None:
        """Test loading spec with environment secrets."""
        spec = load_spec(with_secrets_spec)

        assert spec.env is not None
        assert spec.env.secrets is not None
        assert len(spec.env.secrets) == 2
        assert spec.env.secrets[0].key == "API_KEY"
        assert spec.env.secrets[0].source == "env"

    def test_load_json_format(self, temp_output_dir: Path) -> None:
        """Test loading JSON format spec."""
        json_spec = temp_output_dir / "test-spec.json"
        spec_data = {
            "version": 0,
            "name": "json-test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
            "outputs": {"artifacts": [{"path": "./out.txt", "from": "{{ last_response }}"}]},
        }
        json_spec.write_text(json.dumps(spec_data), encoding="utf-8")

        spec = load_spec(json_spec)
        assert spec.name == "json-test"
        assert spec.runtime.provider == "ollama"

    def test_file_not_found(self) -> None:
        """Test error handling for non-existent file."""
        with pytest.raises(LoadError) as exc_info:
            load_spec("nonexistent.yaml")

        assert "not found" in str(exc_info.value).lower()

    def test_unsupported_extension(self, temp_output_dir: Path) -> None:
        """Test error for unsupported file extension."""
        bad_file = temp_output_dir / "spec.txt"
        bad_file.write_text("version: 0", encoding="utf-8")

        with pytest.raises(LoadError) as exc_info:
            load_spec(bad_file)

        assert "unsupported file extension" in str(exc_info.value).lower()
        assert ".txt" in str(exc_info.value)

    def test_malformed_yaml(self, malformed_spec: Path) -> None:
        """Test error handling for malformed YAML."""
        with pytest.raises(LoadError) as exc_info:
            load_spec(malformed_spec)

        assert "failed to parse" in str(exc_info.value).lower()

    def test_invalid_spec_schema(self, invalid_pattern_spec: Path) -> None:
        """Test that schema validation errors are raised."""
        with pytest.raises(SchemaValidationError):
            load_spec(invalid_pattern_spec)

    def test_spec_not_dict(self, temp_output_dir: Path) -> None:
        """Test error when spec is not a dictionary."""
        bad_spec = temp_output_dir / "list.yaml"
        bad_spec.write_text("- item1\n- item2", encoding="utf-8")

        with pytest.raises(LoadError) as exc_info:
            load_spec(bad_spec)

        assert "must be a dictionary" in str(exc_info.value).lower()

    def test_variable_resolution_basic(self, minimal_ollama_spec: Path) -> None:
        """Test that CLI variables are merged into inputs.values."""
        variables = {"topic": "AI Safety", "audience": "engineers"}
        spec = load_spec(minimal_ollama_spec, variables=variables)

        assert spec.inputs is not None
        assert "values" in spec.inputs
        assert spec.inputs["values"]["topic"] == "AI Safety"
        assert spec.inputs["values"]["audience"] == "engineers"

    def test_variable_resolution_override_existing(self, temp_output_dir: Path) -> None:
        """Test that CLI variables override existing inputs.values."""
        spec_file = temp_output_dir / "spec-with-inputs.yaml"
        spec_content = """
version: 0
name: test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
inputs:
  values:
    topic: "Original Topic"
    other: "Keep This"
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        variables = {"topic": "New Topic"}
        spec = load_spec(spec_file, variables=variables)

        assert spec.inputs["values"]["topic"] == "New Topic"  # Overridden
        assert spec.inputs["values"]["other"] == "Keep This"  # Preserved

    def test_variable_resolution_create_inputs_section(self, temp_output_dir: Path) -> None:
        """Test that inputs section is created if missing."""
        spec_file = temp_output_dir / "spec-no-inputs.yaml"
        spec_content = """
version: 0
name: test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        variables = {"key": "value"}
        spec = load_spec(spec_file, variables=variables)

        assert spec.inputs is not None
        assert "values" in spec.inputs
        assert spec.inputs["values"]["key"] == "value"

    def test_variable_resolution_invalid_inputs_structure_raises(
        self, temp_output_dir: Path
    ) -> None:
        """Test that malformed inputs structures trigger LoadError when merging variables."""
        spec_file = temp_output_dir / "spec-invalid-inputs.yaml"
        spec_content = """
version: 0
name: test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
inputs: []
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        with pytest.raises(LoadError) as exc_info:
            load_spec(spec_file, variables={"topic": "value"})

        assert "inputs" in str(exc_info.value)

    def test_variable_resolution_invalid_values_structure_raises(
        self, temp_output_dir: Path
    ) -> None:
        """Test that malformed inputs.values structures trigger LoadError when merging variables."""
        spec_file = temp_output_dir / "spec-invalid-values.yaml"
        spec_content = """
version: 0
name: test
runtime:
  provider: ollama
  model_id: gpt
  host: http://localhost:11434
inputs:
  values: []
agents:
  test:
    prompt: "Test"
pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"
outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file.write_text(spec_content, encoding="utf-8")

        with pytest.raises(LoadError) as exc_info:
            load_spec(spec_file, variables={"topic": "value"})

        assert "inputs.values" in str(exc_info.value)


@pytest.mark.unit
class TestParseVariables:
    """Test variable parsing from CLI arguments."""

    def test_parse_single_variable(self) -> None:
        """Test parsing a single key=value variable."""
        vars_dict = parse_variables(["topic=AI"])
        assert vars_dict == {"topic": "AI"}

    def test_parse_multiple_variables(self) -> None:
        """Test parsing multiple variables."""
        vars_dict = parse_variables(["topic=AI", "audience=engineers", "region=us-east-1"])
        assert vars_dict == {"topic": "AI", "audience": "engineers", "region": "us-east-1"}

    def test_parse_value_with_equals(self) -> None:
        """Test parsing value containing equals sign."""
        vars_dict = parse_variables(["url=https://example.com?key=value"])
        assert vars_dict == {"url": "https://example.com?key=value"}

    def test_parse_value_with_spaces(self) -> None:
        """Test that spaces are stripped from key and value."""
        vars_dict = parse_variables(["  topic  =  AI Safety  "])
        assert vars_dict == {"topic": "AI Safety"}

    def test_parse_empty_value(self) -> None:
        """Test parsing variable with empty value."""
        vars_dict = parse_variables(["key="])
        assert vars_dict == {"key": ""}

    def test_parse_no_equals_raises_error(self) -> None:
        """Test error when variable lacks equals sign."""
        with pytest.raises(LoadError) as exc_info:
            parse_variables(["invalid_variable"])

        assert "invalid variable format" in str(exc_info.value).lower()
        assert "key=value" in str(exc_info.value).lower()

    def test_parse_empty_key_raises_error(self) -> None:
        """Test error when variable has empty key."""
        with pytest.raises(LoadError) as exc_info:
            parse_variables(["=value"])

        assert "empty variable key" in str(exc_info.value).lower()

    def test_parse_empty_list(self) -> None:
        """Test parsing empty variable list."""
        vars_dict = parse_variables([])
        assert vars_dict == {}

    def test_parse_variable_override(self) -> None:
        """Test that later variables override earlier ones."""
        vars_dict = parse_variables(["topic=First", "topic=Second"])
        assert vars_dict == {"topic": "Second"}


@pytest.mark.unit
class TestPythonToolFormats:
    """Test that both Python tool formats are accepted by schema and loader."""

    def test_python_tools_object_format_validates(self, tmp_path: Path) -> None:
        """Test that Python tools with 'callable' object format pass schema validation."""
        spec_content = """
version: 0
name: "python-object-format"
runtime:
  provider: ollama
  host: http://localhost:11434
  model_id: gpt-oss

tools:
  python:
    - callable: "file_read"

agents:
  test:
    prompt: "Test agent"

pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"

outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "python-object.yaml"
        spec_file.write_text(spec_content)

        # Should NOT raise SchemaValidationError
        spec = load_spec(str(spec_file), {})
        assert spec.tools is not None
        assert spec.tools.python is not None
        assert len(spec.tools.python) == 1
        assert spec.tools.python[0].callable == "file_read"

    def test_python_tools_mixed_formats_validates(self, tmp_path: Path) -> None:
        """Test that mixing string and object formats works correctly."""
        spec_content = """
version: 0
name: "python-mixed-format"
runtime:
  provider: ollama
  host: http://localhost:11434
  model_id: gpt-oss

tools:
  python:
    - callable: "file_read"
    - file_write

agents:
  test:
    prompt: "Test agent"

pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"

outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "python-mixed.yaml"
        spec_file.write_text(spec_content)

        # Should NOT raise SchemaValidationError
        spec = load_spec(str(spec_file), {})
        assert spec.tools is not None
        assert spec.tools.python is not None
        assert len(spec.tools.python) == 2
        assert spec.tools.python[0].callable == "file_read"
        assert spec.tools.python[1].callable == "file_write"

    def test_optional_inputs_with_defaults_applied_to_values(self, tmp_path: Path) -> None:
        """Test that optional input defaults are applied to inputs.values."""
        spec_content = """
version: 0
name: "optional-defaults-test"
runtime:
  provider: ollama
  host: http://localhost:11434
  model_id: gpt-oss

inputs:
  required:
    use_case: string
  optional:
    requirements:
      type: string
      default: ""
    provider:
      type: string
      default: "openai"
    pattern_preference:
      type: string
      default: ""

agents:
  test:
    prompt: "Test: {{ use_case }}, {{ requirements }}, {{ provider }}, {{ pattern_preference }}"

pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test with defaults"

outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "optional-defaults.yaml"
        spec_file.write_text(spec_content)

        # Load spec with only required variable
        spec = load_spec(str(spec_file), {"use_case": "test case"})
        
        # Verify that defaults were applied to inputs.values
        assert spec.inputs is not None
        assert "values" in spec.inputs
        values = spec.inputs["values"]
        
        assert values["use_case"] == "test case"  # From CLI
        assert values["requirements"] == ""  # Default applied
        assert values["provider"] == "openai"  # Default applied
        assert values["pattern_preference"] == ""  # Default applied

    def test_required_inputs_with_defaults_applied_to_values(self, tmp_path: Path) -> None:
        """Test that required input defaults are applied to inputs.values."""
        spec_content = """
version: 0
name: "required-defaults-test"
runtime:
  provider: ollama
  host: http://localhost:11434
  model_id: gpt-oss

inputs:
  required:
    topic:
      type: string
      default: "general"
    format:
      type: string
      default: "markdown"

agents:
  test:
    prompt: "Test: {{ topic }}, {{ format }}"

pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"

outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "required-defaults.yaml"
        spec_file.write_text(spec_content)

        # Load spec without providing any variables (defaults should be applied)
        spec = load_spec(str(spec_file), {})
        
        # Verify that defaults were applied to inputs.values
        assert spec.inputs is not None
        assert "values" in spec.inputs
        values = spec.inputs["values"]
        
        assert values["topic"] == "general"  # Default applied
        assert values["format"] == "markdown"  # Default applied

    def test_cli_variables_override_defaults(self, tmp_path: Path) -> None:
        """Test that CLI variables override default values."""
        spec_content = """
version: 0
name: "override-defaults-test"
runtime:
  provider: ollama
  host: http://localhost:11434
  model_id: gpt-oss

inputs:
  optional:
    setting:
      type: string
      default: "default-value"

agents:
  test:
    prompt: "Test: {{ setting }}"

pattern:
  type: chain
  config:
    steps:
      - agent: test
        input: "Test"

outputs:
  artifacts:
    - path: ./out.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "override-defaults.yaml"
        spec_file.write_text(spec_content)

        # Load spec with CLI override
        spec = load_spec(str(spec_file), {"setting": "cli-override"})
        
        # Verify that CLI value overrode the default
        assert spec.inputs is not None
        assert "values" in spec.inputs
        values = spec.inputs["values"]
        
        assert values["setting"] == "cli-override"  # CLI override wins

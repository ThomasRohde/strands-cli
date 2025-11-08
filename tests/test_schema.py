"""Unit tests for schema validation module."""

from pathlib import Path

import pytest

from strands_cli.schema.validator import (
    SchemaValidationError,
    get_schema,
    validate_spec,
)


@pytest.mark.unit
class TestSchemaValidation:
    """Test schema validation functionality."""

    def test_valid_minimal_ollama_spec(self, minimal_ollama_spec: Path) -> None:
        """Test that minimal Ollama spec passes validation."""
        import yaml

        with minimal_ollama_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        # Should not raise
        validate_spec(spec_data)

    def test_valid_minimal_bedrock_spec(self, minimal_bedrock_spec: Path) -> None:
        """Test that minimal Bedrock spec passes validation."""
        import yaml

        with minimal_bedrock_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        # Should not raise
        validate_spec(spec_data)

    def test_valid_spec_with_tools(self, with_tools_spec: Path) -> None:
        """Test that spec with tools passes validation."""
        import yaml

        with with_tools_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        validate_spec(spec_data)

    def test_valid_spec_with_skills(self, with_skills_spec: Path) -> None:
        """Test that spec with skills passes validation."""
        import yaml

        with with_skills_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        validate_spec(spec_data)

    def test_valid_spec_with_budgets(self, with_budgets_spec: Path) -> None:
        """Test that spec with budgets passes validation."""
        import yaml

        with with_budgets_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        validate_spec(spec_data)

    def test_valid_spec_with_secrets(self, with_secrets_spec: Path) -> None:
        """Test that spec with secrets passes validation."""
        import yaml

        with with_secrets_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        validate_spec(spec_data)

    def test_missing_required_fields(self) -> None:
        """Test validation fails for missing required fields."""
        spec_data = {"description": "Incomplete spec"}

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        assert len(error.errors) > 0
        assert "validation failed" in str(error).lower()

        # Should report missing required fields
        error_messages = " ".join(err["message"] for err in error.errors)
        assert "version" in error_messages or "required" in error_messages.lower()

    def test_invalid_pattern_type(self, invalid_pattern_spec: Path) -> None:
        """Test validation fails for invalid pattern type."""
        import yaml

        with invalid_pattern_spec.open("r") as f:
            spec_data = yaml.safe_load(f)

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        assert len(error.errors) > 0

        # Should have JSONPointer to pattern type
        pointers = [err["pointer"] for err in error.errors]
        assert any("pattern" in ptr.lower() for ptr in pointers)

    def test_additional_properties_not_allowed(self) -> None:
        """Test validation fails for unexpected properties."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
            "outputs": {"artifacts": [{"path": "./out.txt", "from": "{{ last_response }}"}]},
            "unexpected_field": "This should fail",
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        assert len(error.errors) > 0
        error_text = str(error)
        assert "additional properties" in error_text.lower() or "unexpected" in error_text.lower()

    def test_jsonpointer_accuracy(self) -> None:
        """Test that JSONPointer paths correctly identify error locations."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {
                "provider": "ollama",
                "model_id": "gpt",
                "host": "http://localhost:11434",
                "budgets": {"max_tokens": -100},  # Invalid: negative value
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
            "outputs": {"artifacts": [{"path": "./out.txt", "from": "{{ last_response }}"}]},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        assert len(error.errors) > 0

        # Should point to /runtime/budgets/max_tokens
        pointers = [err["pointer"] for err in error.errors]
        assert any("runtime" in ptr and "budgets" in ptr for ptr in pointers)

    def test_error_message_human_readable(self) -> None:
        """Test that error messages are human-readable."""
        spec_data = {"version": "invalid_version_string"}

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        # Should contain counts and descriptions
        assert "validation failed" in error_text.lower()
        assert "error" in error_text.lower()

    def test_multiple_errors_reported(self) -> None:
        """Test that multiple validation errors are collected and reported."""
        spec_data = {
            # Missing version, name
            "runtime": {"invalid_provider": "bad"},  # Missing provider field
            # Missing agents, pattern
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        # Should have multiple errors (missing version, name, agents, pattern, etc.)
        assert len(error.errors) >= 2

    def test_get_schema_returns_copy(self) -> None:
        """Test that get_schema returns a copy of the schema."""
        schema1 = get_schema()
        schema2 = get_schema()

        # Should be equal but not the same object
        assert schema1 == schema2
        assert schema1 is not schema2

        # Modifying one shouldn't affect the other
        schema1["modified"] = True
        assert "modified" not in schema2

    def test_schema_has_required_sections(self) -> None:
        """Test that the schema contains all required top-level sections."""
        schema = get_schema()

        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "title" in schema
        assert "properties" in schema
        assert "required" in schema

        # Check that key properties are defined
        properties = schema["properties"]
        assert "version" in properties
        assert "name" in properties
        assert "runtime" in properties
        assert "agents" in properties
        assert "pattern" in properties
        assert "outputs" in properties

    def test_schema_coverage_runtime_properties(self) -> None:
        """Test that runtime schema includes all expected properties."""
        schema = get_schema()
        runtime_def = schema["$defs"]["runtime"]
        runtime_props = runtime_def["properties"]

        # Check MVP-required properties
        assert "provider" in runtime_props
        assert "model_id" in runtime_props
        assert "region" in runtime_props
        assert "host" in runtime_props  # Added for Ollama
        assert "budgets" in runtime_props
        assert "failure_policy" in runtime_props

    def test_schema_coverage_inputs_properties(self) -> None:
        """Test that inputs schema includes values property."""
        schema = get_schema()
        inputs_def = schema["$defs"]["inputs"]
        inputs_props = inputs_def["properties"]

        assert "required" in inputs_props
        assert "optional" in inputs_props
        assert "values" in inputs_props  # Added for runtime variable resolution

    def test_schema_coverage_pattern_types(self) -> None:
        """Test that all 7 pattern types are defined in schema."""
        schema = get_schema()
        pattern_def = schema["$defs"]["pattern"]

        # Pattern type enum should include all 7 types
        pattern_type_def = pattern_def["properties"]["type"]
        expected_types = {
            "chain",
            "routing",
            "parallel",
            "orchestrator_workers",
            "evaluator_optimizer",
            "graph",
            "workflow",
        }
        assert set(pattern_type_def["enum"]) == expected_types

        # All config types should be defined in $defs
        defs = schema["$defs"]
        assert "chainConfig" in defs
        assert "routingConfig" in defs
        assert "parallelConfig" in defs
        assert "orchestratorWorkersConfig" in defs
        assert "evaluatorOptimizerConfig" in defs
        assert "graphConfig" in defs
        assert "workflowConfig" in defs

    def test_schema_validation_error_structure(self) -> None:
        """Test SchemaValidationError has correct structure."""
        errors = [
            {
                "pointer": "/version",
                "message": "Field required",
                "validator": "required",
                "path": ["version"],
            },
            {
                "pointer": "/name",
                "message": "Field required",
                "validator": "required",
                "path": ["name"],
            },
        ]

        exc = SchemaValidationError("Test error", errors)

        assert str(exc) == "Test error"
        assert exc.errors == errors
        assert len(exc.errors) == 2
        assert exc.errors[0]["pointer"] == "/version"

    def test_workflow_task_requires_id(self) -> None:
        """Test that workflow pattern tasks require an id field."""
        spec_data = {
            "version": 0,
            "name": "test-workflow",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "agents": {"worker": {"prompt": "Do work"}},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {
                            # Missing "id" field - should fail
                            "agent": "worker",
                            "input": "Do task",
                        }
                    ]
                },
            },
            "outputs": {"artifacts": [{"path": "./out.txt", "from": "{{ last_response }}"}]},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        error_text = str(error)
        # Should mention the missing "id" field
        assert "id" in error_text.lower() or "required" in error_text.lower()

    def test_chain_steps_minimum(self) -> None:
        """Test that chain pattern requires at least 1 step."""
        spec_data = {
            "version": 0,
            "name": "test-chain",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "agents": {"worker": {"prompt": "Do work"}},
            "pattern": {
                "type": "chain",
                "config": {
                    "steps": []  # Empty steps - should fail
                },
            },
            "outputs": {"artifacts": [{"path": "./out.txt", "from": "{{ last_response }}"}]},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error = exc_info.value
        error_text = str(error)
        assert "minitems" in error_text.lower() or "steps" in error_text.lower()

    def test_context_policy_compaction_all_fields(
        self, sample_spec_with_compaction_dict: dict
    ) -> None:
        """Test that compaction with all fields passes validation."""
        # Should not raise
        validate_spec(sample_spec_with_compaction_dict)

    def test_context_policy_notes_all_fields(
        self, sample_spec_with_notes_dict: dict
    ) -> None:
        """Test that notes with all fields passes validation."""
        # Should not raise
        validate_spec(sample_spec_with_notes_dict)

    def test_context_policy_full_config(
        self, sample_spec_with_full_context_policy_dict: dict
    ) -> None:
        """Test that full context policy configuration passes validation."""
        # Should not raise
        validate_spec(sample_spec_with_full_context_policy_dict)

    def test_compaction_summary_ratio_range(self) -> None:
        """Test that summary_ratio must be between 0.0 and 1.0."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "compaction": {
                    "enabled": True,
                    "summary_ratio": 1.5,  # Invalid: > 1.0
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "summary_ratio" in error_text.lower() or "maximum" in error_text.lower()

    def test_compaction_when_tokens_over_minimum(self) -> None:
        """Test that when_tokens_over must be at least 1000."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "compaction": {
                    "enabled": True,
                    "when_tokens_over": 500,  # Invalid: < 1000
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "when_tokens_over" in error_text.lower() or "minimum" in error_text.lower()

    def test_compaction_preserve_recent_messages_minimum(self) -> None:
        """Test that preserve_recent_messages must be at least 1."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "compaction": {
                    "enabled": True,
                    "preserve_recent_messages": 0,  # Invalid: < 1
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "preserve_recent_messages" in error_text.lower() or "minimum" in error_text.lower()

    def test_notes_include_last_minimum(self) -> None:
        """Test that include_last must be at least 1."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "notes": {
                    "file": "artifacts/notes.md",
                    "include_last": 0,  # Invalid: < 1
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "include_last" in error_text.lower() or "minimum" in error_text.lower()

    def test_notes_format_enum(self) -> None:
        """Test that notes format must be 'markdown' or 'json'."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "notes": {
                    "file": "artifacts/notes.md",
                    "format": "xml",  # Invalid: not in enum
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "format" in error_text.lower() or "enum" in error_text.lower()

    def test_notes_file_required(self) -> None:
        """Test that notes.file is required when notes config is present."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama", "model_id": "gpt", "host": "http://localhost:11434"},
            "context_policy": {
                "notes": {
                    # Missing "file" field - should fail
                    "include_last": 10,
                }
            },
            "agents": {"test": {"prompt": "Hello"}},
            "pattern": {"type": "chain", "config": {"steps": [{"agent": "test", "input": "Hi"}]}},
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_spec(spec_data)

        error_text = str(exc_info.value)
        assert "file" in error_text.lower() or "required" in error_text.lower()


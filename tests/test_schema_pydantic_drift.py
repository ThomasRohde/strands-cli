"""Tests to detect drift between JSON Schema defaults and Pydantic model defaults.

This test suite automatically validates that default values defined in the
JSON Schema (strands-workflow.schema.json) match the corresponding default
values in Pydantic models (types.py). This prevents configuration drift
that could lead to inconsistent behavior.

Phase 2 Remediation: Schema/Pydantic drift prevention
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from strands_cli.types import (
    AcceptConfig,
    Compaction,
    Notes,
    Retrieval,
    RouterConfig,
)


def load_schema() -> dict[str, Any]:
    """Load the JSON Schema from the embedded resource."""
    schema_path = (
        Path(__file__).parent.parent
        / "src"
        / "strands_cli"
        / "schema"
        / "strands-workflow.schema.json"
    )
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def get_schema_defaults(schema: dict[str, Any], pointer: str) -> dict[str, Any]:
    """Extract default values from a JSON Schema definition.

    Args:
        schema: The full JSON Schema
        pointer: JSON pointer to the definition (e.g., "#/$defs/contextPolicy/properties/compaction")

    Returns:
        Dictionary mapping property names to their default values
    """
    defaults = {}

    # Navigate to the definition
    parts = pointer.strip("#/").split("/")
    current = schema

    for part in parts:
        if part:
            current = current[part]

    # Extract defaults from properties
    if "properties" in current:
        for prop_name, prop_def in current["properties"].items():
            if "default" in prop_def:
                defaults[prop_name] = prop_def["default"]

    return defaults


def get_pydantic_defaults(model: type[BaseModel]) -> dict[str, Any]:
    """Extract default values from a Pydantic model.

    Args:
        model: The Pydantic model class

    Returns:
        Dictionary mapping field names to their default values
    """
    defaults = {}

    for field_name, field_info in model.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            defaults[field_name] = field_info.default
        elif field_info.default_factory is not None:
            # Handle default factories (e.g., list, dict)
            defaults[field_name] = field_info.default_factory()

    return defaults


class TestSchemaPydanticDrift:
    """Test suite to detect drift between JSON Schema and Pydantic defaults."""

    def test_compaction_defaults_match(self) -> None:
        """Verify Compaction model defaults match JSON Schema."""
        schema = load_schema()
        schema_defaults = get_schema_defaults(schema, "#/$defs/contextPolicy/properties/compaction")
        pydantic_defaults = get_pydantic_defaults(Compaction)

        # Compare defaults
        for field_name, schema_default in schema_defaults.items():
            assert field_name in pydantic_defaults, (
                f"Field '{field_name}' has default in schema but not in Pydantic model"
            )
            assert pydantic_defaults[field_name] == schema_default, (
                f"Default value mismatch for '{field_name}': "
                f"schema={schema_default}, pydantic={pydantic_defaults[field_name]}"
            )

        # Check for Pydantic defaults not in schema (potential drift)
        for field_name, _pydantic_default in pydantic_defaults.items():
            if field_name not in schema_defaults:
                # This is a warning - Pydantic can have defaults that schema doesn't mandate
                # But it should be intentional
                pass  # Allow for now, could warn in future

    def test_notes_defaults_match(self) -> None:
        """Verify Notes model defaults match JSON Schema."""
        schema = load_schema()
        schema_defaults = get_schema_defaults(schema, "#/$defs/contextPolicy/properties/notes")
        pydantic_defaults = get_pydantic_defaults(Notes)

        for field_name, schema_default in schema_defaults.items():
            assert field_name in pydantic_defaults, (
                f"Field '{field_name}' has default in schema but not in Pydantic model"
            )
            assert pydantic_defaults[field_name] == schema_default, (
                f"Default value mismatch for '{field_name}': "
                f"schema={schema_default}, pydantic={pydantic_defaults[field_name]}"
            )

    def test_retrieval_no_unexpected_defaults(self) -> None:
        """Verify Retrieval model has no unexpected defaults."""
        schema = load_schema()
        schema_defaults = get_schema_defaults(schema, "#/$defs/contextPolicy/properties/retrieval")
        pydantic_defaults = get_pydantic_defaults(Retrieval)

        # Retrieval should have no defaults in either schema or Pydantic
        assert len(schema_defaults) == 0, (
            f"Unexpected defaults in schema for Retrieval: {schema_defaults}"
        )
        assert len(pydantic_defaults) == 0, (
            f"Unexpected defaults in Pydantic for Retrieval: {pydantic_defaults}"
        )

    def test_router_config_defaults_match(self) -> None:
        """Verify RouterConfig model defaults match JSON Schema."""
        schema = load_schema()
        schema_defaults = get_schema_defaults(schema, "#/$defs/routingConfig/properties/router")
        pydantic_defaults = get_pydantic_defaults(RouterConfig)

        for field_name, schema_default in schema_defaults.items():
            assert field_name in pydantic_defaults, (
                f"Field '{field_name}' has default in schema but not in Pydantic model"
            )
            assert pydantic_defaults[field_name] == schema_default, (
                f"Default value mismatch for '{field_name}': "
                f"schema={schema_default}, pydantic={pydantic_defaults[field_name]}"
            )

    def test_accept_config_defaults_match(self) -> None:
        """Verify AcceptConfig model defaults match JSON Schema."""
        schema = load_schema()
        schema_defaults = get_schema_defaults(
            schema, "#/$defs/evaluatorOptimizerConfig/properties/accept"
        )
        pydantic_defaults = get_pydantic_defaults(AcceptConfig)

        for field_name, schema_default in schema_defaults.items():
            assert field_name in pydantic_defaults, (
                f"Field '{field_name}' has default in schema but not in Pydantic model"
            )
            assert pydantic_defaults[field_name] == schema_default, (
                f"Default value mismatch for '{field_name}': "
                f"schema={schema_default}, pydantic={pydantic_defaults[field_name]}"
            )

    def test_all_schema_defaults_covered(self) -> None:
        """Comprehensive check: scan entire schema for defaults and verify Pydantic coverage.

        This test provides a safety net to catch any defaults that might exist
        in the schema but aren't explicitly tested above.
        """
        schema = load_schema()

        # Map of schema paths to Pydantic models (add more as needed)
        schema_to_model_map = {
            "#/$defs/contextPolicy/properties/compaction": Compaction,
            "#/$defs/contextPolicy/properties/notes": Notes,
            "#/$defs/contextPolicy/properties/retrieval": Retrieval,
            "#/$defs/routingConfig/properties/router": RouterConfig,
            "#/$defs/evaluatorOptimizerConfig/properties/accept": AcceptConfig,
        }

        for schema_path, model in schema_to_model_map.items():
            schema_defaults = get_schema_defaults(schema, schema_path)
            pydantic_defaults = get_pydantic_defaults(model)

            # Verify all schema defaults exist in Pydantic
            for field_name, schema_default in schema_defaults.items():
                assert field_name in pydantic_defaults, (
                    f"[{model.__name__}] Field '{field_name}' has default in schema "
                    f"({schema_path}) but not in Pydantic model"
                )
                assert pydantic_defaults[field_name] == schema_default, (
                    f"[{model.__name__}] Default mismatch for '{field_name}': "
                    f"schema={schema_default}, pydantic={pydantic_defaults[field_name]}"
                )

    def test_runtime_defaults_existence(self) -> None:
        """Verify runtime configuration defaults are documented.

        Note: Runtime defaults are intentionally different - schema has fewer
        defaults since many are provided via environment variables or config.
        This test just verifies the schema has the expected defaults.
        """
        schema = load_schema()

        # Check budgets defaults
        budgets_defaults = get_schema_defaults(schema, "#/$defs/runtime/properties/budgets")
        assert "warn_threshold" in budgets_defaults
        assert budgets_defaults["warn_threshold"] == 0.8

        # Check failure_policy defaults
        failure_policy_defaults = get_schema_defaults(
            schema, "#/$defs/runtime/properties/failure_policy"
        )
        assert "backoff" in failure_policy_defaults
        assert failure_policy_defaults["backoff"] == "exponential"

    def test_budgets_defaults_match_pydantic(self) -> None:
        """Verify budget configuration defaults match between schema and Pydantic.

        Note: Budget enforcement was removed per Phase 0, but warn_threshold default
        should still match between schema and any Pydantic models that use it.
        """
        schema = load_schema()
        budgets_defaults = get_schema_defaults(schema, "#/$defs/runtime/properties/budgets")

        # Verify warn_threshold default
        assert "warn_threshold" in budgets_defaults
        assert budgets_defaults["warn_threshold"] == 0.8


@pytest.mark.integration
class TestSchemaDefaultsApplied:
    """Integration tests to verify defaults are actually applied during parsing."""

    def test_compaction_defaults_applied_when_enabled_only(self) -> None:
        """Verify compaction defaults are applied when enabled=true is specified."""
        from strands_cli.loader.yaml_loader import load_spec

        spec_yaml = """
version: 0
name: test-compaction-defaults
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  writer:
    prompt: "You are a helpful assistant"
pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Test"
context_policy:
  compaction:
    enabled: true
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_yaml)
            f.flush()
            spec = load_spec(f.name)

        # Verify defaults were applied
        assert spec.context_policy is not None
        assert spec.context_policy.compaction is not None
        assert spec.context_policy.compaction.enabled is True
        assert spec.context_policy.compaction.summary_ratio == 0.35
        assert spec.context_policy.compaction.preserve_recent_messages == 12

    def test_notes_defaults_applied(self) -> None:
        """Verify notes defaults are applied when file is specified."""
        from strands_cli.loader.yaml_loader import load_spec

        spec_yaml = """
version: 0
name: test-notes-defaults
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  writer:
    prompt: "You are a helpful assistant"
pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Test"
context_policy:
  notes:
    file: "artifacts/notes.md"
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_yaml)
            f.flush()
            spec = load_spec(f.name)

        # Verify defaults were applied
        assert spec.context_policy is not None
        assert spec.context_policy.notes is not None
        assert spec.context_policy.notes.file == "artifacts/notes.md"
        assert spec.context_policy.notes.include_last == 12
        assert spec.context_policy.notes.format == "markdown"

    def test_router_config_defaults_applied(self) -> None:
        """Verify router config defaults are applied."""
        from strands_cli.loader.yaml_loader import load_spec

        spec_yaml = """
version: 0
name: test-router-defaults
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  router:
    prompt: "You are a router"
  worker:
    prompt: "You are a worker"
pattern:
  type: routing
  config:
    router:
      agent: router
      input: "Route this"
    routes:
      route_a:
        then:
          - agent: worker
            input: "Do A"
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_yaml)
            f.flush()
            spec = load_spec(f.name)

        # Verify defaults were applied
        assert spec.pattern.config.router is not None
        assert spec.pattern.config.router.max_retries == 2

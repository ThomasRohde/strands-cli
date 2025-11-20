"""Schema and model acceptance tests for metadata and contract fields."""

from strands_cli.schema.validator import validate_spec
from strands_cli.types import Spec


def _example_spec() -> dict:
    """Build a minimal spec that exercises metadata and agent contract fields."""

    return {
        "version": 0,
        "name": "atomic-test",
        "metadata": {
            "name": "atomic-test-friendly",
            "description": "Example manifest with metadata and schemas",
            "labels": {
                "strands.io/agent_type": "atomic",
                "strands.io/domain": "demo",
            },
        },
        "runtime": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
        },
        "agents": {
            "worker": {
                "prompt": "Do a thing",
                "input_schema": "./schemas/input.json",
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
            }
        },
        "pattern": {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "worker",
                        "input": "Hello {{topic}}",
                    }
                ]
            },
        },
    }


def test_validate_accepts_metadata_and_contract_fields() -> None:
    """JSON Schema validation allows metadata and agent contract extensions."""

    spec_dict = _example_spec()

    # Should not raise
    validate_spec(spec_dict)


def test_pydantic_parses_metadata_and_contract_fields() -> None:
    """Pydantic model accepts and preserves metadata and schema contract fields."""

    spec_dict = _example_spec()

    spec = Spec.model_validate(spec_dict)

    assert spec.metadata is not None
    assert spec.metadata.labels["strands.io/agent_type"] == "atomic"
    agent = spec.agents["worker"]
    assert agent.input_schema == "./schemas/input.json"
    assert isinstance(agent.output_schema, dict)

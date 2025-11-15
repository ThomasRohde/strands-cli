"""Tests for variable detection functionality."""

from __future__ import annotations

import pytest

from strands_cli.loader.variable_detector import (
    detect_missing_variables,
    extract_param_info,
    get_variable_metadata,
)
from strands_cli.types import Spec


def test_detect_missing_variables_no_inputs() -> None:
    """Test detection when spec has no inputs."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
    )

    missing = detect_missing_variables(spec)
    assert missing == []


def test_detect_missing_variables_no_required() -> None:
    """Test detection when spec has inputs but no required params."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"values": {"topic": "AI"}},
    )

    missing = detect_missing_variables(spec)
    assert missing == []


def test_detect_missing_variables_all_satisfied() -> None:
    """Test detection when all required variables have values."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={
            "required": {"topic": "string", "format": "string"},
            "values": {"topic": "AI", "format": "markdown"},
        },
    )

    missing = detect_missing_variables(spec)
    assert missing == []


def test_detect_missing_variables_one_missing() -> None:
    """Test detection when one required variable is missing."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={
            "required": {"topic": "string", "format": "string"},
            "values": {"format": "markdown"},
        },
    )

    missing = detect_missing_variables(spec)
    assert missing == ["topic"]


def test_detect_missing_variables_multiple_missing() -> None:
    """Test detection when multiple required variables are missing."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={
            "required": {
                "topic": "string",
                "format": "string",
                "user_id": "integer",
            },
            "values": {"format": "markdown"},
        },
    )

    missing = detect_missing_variables(spec)
    assert set(missing) == {"topic", "user_id"}


def test_detect_missing_variables_with_default_in_spec() -> None:
    """Test detection when required param has default in schema."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={
            "required": {
                "topic": {"type": "string", "default": "AI"},
                "format": "string",
            },
            "values": {},
        },
    )

    missing = detect_missing_variables(spec)
    assert missing == ["format"]  # Only format is missing (topic has default)


def test_get_variable_metadata_required() -> None:
    """Test getting metadata for required variable."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": "string"}},
    )

    param_spec, location = get_variable_metadata(spec, "topic")
    assert param_spec == "string"
    assert location == "required"


def test_get_variable_metadata_optional() -> None:
    """Test getting metadata for optional variable."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"optional": {"format": "string"}},
    )

    param_spec, location = get_variable_metadata(spec, "format")
    assert param_spec == "string"
    assert location == "optional"


def test_get_variable_metadata_not_found() -> None:
    """Test getting metadata for nonexistent variable."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": "string"}},
    )

    with pytest.raises(KeyError, match="Variable 'nonexistent' not found"):
        get_variable_metadata(spec, "nonexistent")


def test_extract_param_info_shorthand() -> None:
    """Test extracting info from shorthand param spec."""
    info = extract_param_info("string")

    assert info["type"] == "string"
    assert info["description"] == ""
    assert info["default"] is None
    assert info["enum"] is None


def test_extract_param_info_detailed() -> None:
    """Test extracting info from detailed param spec."""
    param_spec = {
        "type": "integer",
        "description": "User ID",
        "default": 42,
        "enum": [1, 2, 3],
    }

    info = extract_param_info(param_spec)

    assert info["type"] == "integer"
    assert info["description"] == "User ID"
    assert info["default"] == 42
    assert info["enum"] == [1, 2, 3]


def test_extract_param_info_partial() -> None:
    """Test extracting info from partially specified param."""
    param_spec = {"type": "number", "description": "Score"}

    info = extract_param_info(param_spec)

    assert info["type"] == "number"
    assert info["description"] == "Score"
    assert info["default"] is None
    assert info["enum"] is None

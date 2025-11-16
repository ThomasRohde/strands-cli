"""Tests for interactive variable prompting functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from strands_cli.loader.variable_prompter import (
    coerce_value,
    is_interactive,
    prompt_for_missing_variables,
    prompt_for_variable,
)
from strands_cli.types import Spec


def test_coerce_value_string() -> None:
    """Test coercing to string type."""
    result = coerce_value("hello world", "string")
    assert result == "hello world"
    assert isinstance(result, str)


def test_coerce_value_integer() -> None:
    """Test coercing to integer type."""
    result = coerce_value("42", "integer")
    assert result == 42
    assert isinstance(result, int)


def test_coerce_value_integer_invalid() -> None:
    """Test coercing invalid integer raises ValueError."""
    with pytest.raises(ValueError, match="Cannot convert 'hello' to integer"):
        coerce_value("hello", "integer")


def test_coerce_value_number() -> None:
    """Test coercing to number (float) type."""
    result = coerce_value("3.14", "number")
    assert result == 3.14
    assert isinstance(result, float)


def test_coerce_value_number_from_int() -> None:
    """Test coercing integer string to number."""
    result = coerce_value("42", "number")
    assert result == 42.0
    assert isinstance(result, float)


def test_coerce_value_number_invalid() -> None:
    """Test coercing invalid number raises ValueError."""
    with pytest.raises(ValueError, match="Cannot convert 'hello' to number"):
        coerce_value("hello", "number")


def test_coerce_value_boolean_true_variants() -> None:
    """Test coercing various true representations."""
    for value in ["true", "True", "TRUE", "yes", "Yes", "y", "Y", "1"]:
        result = coerce_value(value, "boolean")
        assert result is True
        assert isinstance(result, bool)


def test_coerce_value_boolean_false_variants() -> None:
    """Test coercing various false representations."""
    for value in ["false", "False", "FALSE", "no", "No", "n", "N", "0"]:
        result = coerce_value(value, "boolean")
        assert result is False
        assert isinstance(result, bool)


def test_coerce_value_boolean_invalid() -> None:
    """Test coercing invalid boolean raises ValueError."""
    with pytest.raises(ValueError, match="Cannot convert 'maybe' to boolean"):
        coerce_value("maybe", "boolean")


def test_coerce_value_unknown_type() -> None:
    """Test coercing unknown type falls back to string."""
    result = coerce_value("hello", "custom_type")
    assert result == "hello"
    assert isinstance(result, str)


@patch("sys.stdin.isatty")
def test_is_interactive_tty(mock_isatty: MagicMock) -> None:
    """Test is_interactive returns True when stdin is TTY."""
    mock_isatty.return_value = True
    assert is_interactive() is True


@patch("sys.stdin.isatty")
def test_is_interactive_non_tty(mock_isatty: MagicMock) -> None:
    """Test is_interactive returns False when stdin is not TTY."""
    mock_isatty.return_value = False
    assert is_interactive() is False


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_variable_string(mock_ask: MagicMock) -> None:
    """Test prompting for string variable."""
    mock_ask.return_value = "AI safety"

    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": "string"}},
    )

    result = prompt_for_variable(spec, "topic")
    assert result == "AI safety"
    assert isinstance(result, str)


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_variable_integer(mock_ask: MagicMock) -> None:
    """Test prompting for integer variable with coercion."""
    mock_ask.return_value = "42"

    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"user_id": "integer"}},
    )

    result = prompt_for_variable(spec, "user_id")
    assert result == 42
    assert isinstance(result, int)


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_variable_with_description(mock_ask: MagicMock) -> None:
    """Test prompting for variable with description."""
    mock_ask.return_value = "test value"

    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": {"type": "string", "description": "Topic to research"}}},
    )

    result = prompt_for_variable(spec, "topic")
    assert result == "test value"


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_variable_retry_on_invalid_type(
    mock_ask: MagicMock,
) -> None:
    """Test prompting retries when type coercion fails."""
    # First call returns invalid integer, second call returns valid
    mock_ask.side_effect = ["not a number", "42"]

    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"user_id": "integer"}},
    )

    result = prompt_for_variable(spec, "user_id")
    assert result == 42
    assert mock_ask.call_count == 2


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_missing_variables_multiple(mock_ask: MagicMock) -> None:
    """Test prompting for multiple missing variables."""
    mock_ask.side_effect = ["AI safety", "42"]

    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={
            "required": {"topic": "string", "user_id": "integer"},
            "values": {},
        },
    )

    result = prompt_for_missing_variables(spec, ["topic", "user_id"])

    assert result == {"topic": "AI safety", "user_id": 42}
    assert mock_ask.call_count == 2


@patch("strands_cli.loader.variable_prompter.Prompt.ask")
def test_prompt_for_missing_variables_empty_list(
    mock_ask: MagicMock,
) -> None:
    """Test prompting with empty missing list returns empty dict."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": "string"}, "values": {"topic": "AI"}},
    )

    result = prompt_for_missing_variables(spec, [])

    assert result == {}
    assert mock_ask.call_count == 0


def test_prompt_for_variable_not_in_spec() -> None:
    """Test prompting for variable not in spec raises KeyError."""
    spec = Spec(
        name="test",
        version=1,
        runtime={"provider": "ollama", "model_id": "llama2"},
        agents={"agent1": {"prompt": "test"}},
        pattern={"type": "chain", "config": {"steps": []}},
        inputs={"required": {"topic": "string"}},
    )

    with pytest.raises(KeyError, match="Variable 'nonexistent' not found"):
        prompt_for_variable(spec, "nonexistent")

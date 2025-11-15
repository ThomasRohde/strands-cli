"""Variable detection for identifying missing required variables.

This module provides functionality to detect which required variables are missing
from a workflow specification (i.e., they lack both CLI-provided values and defaults).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands_cli.types import Spec


def detect_missing_variables(spec: Spec) -> list[str]:
    """Detect required variables that lack both values and defaults.

    Examines the spec's inputs configuration to identify required parameters
    that don't have values (from CLI or spec defaults) and don't have default
    values specified in their parameter schema.

    Args:
        spec: The validated workflow specification

    Returns:
        List of variable names that are missing (empty if all required vars are satisfied)

    Examples:
        >>> spec = Spec(...)  # Has required "topic" without value or default
        >>> detect_missing_variables(spec)
        ['topic']

        >>> spec = Spec(...)  # All required vars have values
        >>> detect_missing_variables(spec)
        []
    """
    if not spec.inputs:
        return []

    # Get dictionaries (handle None and dict types)
    required_params = spec.inputs.get("required", {}) if isinstance(spec.inputs, dict) else {}
    values = spec.inputs.get("values", {}) if isinstance(spec.inputs, dict) else {}

    if not required_params:
        return []

    missing = []

    for param_name, param_spec in required_params.items():
        # Check if value already exists (from CLI --var or spec defaults)
        if param_name in values:
            continue

        # Check if parameter spec has a default value
        # Param spec can be:
        # 1. Shorthand string: "string", "integer", etc.
        # 2. Detailed dict: {"type": "string", "default": "value", ...}
        if isinstance(param_spec, dict) and "default" in param_spec:
            # Has default in schema, not missing
            continue

        # No value and no default = missing
        missing.append(param_name)

    return missing


def get_variable_metadata(
    spec: Spec, var_name: str
) -> tuple[str | dict[str, Any], str]:
    """Get metadata for a variable from the spec's input schema.

    Args:
        spec: The validated workflow specification
        var_name: Name of the variable to get metadata for

    Returns:
        Tuple of (param_spec, location) where:
        - param_spec: The parameter specification (string or dict)
        - location: "required" or "optional" indicating where the var was found

    Raises:
        KeyError: If variable not found in either required or optional params
    """
    if not spec.inputs or not isinstance(spec.inputs, dict):
        raise KeyError(f"Variable '{var_name}' not found in spec inputs")

    # Check required params first
    required_params = spec.inputs.get("required", {})
    if var_name in required_params:
        return required_params[var_name], "required"

    # Check optional params
    optional_params = spec.inputs.get("optional", {})
    if var_name in optional_params:
        return optional_params[var_name], "optional"

    raise KeyError(f"Variable '{var_name}' not found in spec inputs")


def extract_param_info(param_spec: str | dict[str, Any]) -> dict[str, Any]:
    """Extract structured information from a parameter specification.

    Args:
        param_spec: Parameter spec (shorthand string or detailed dict)

    Returns:
        Dictionary with keys:
        - type: Parameter type ("string", "integer", "number", "boolean")
        - description: Human-readable description (empty if not provided)
        - default: Default value (None if not provided)
        - enum: List of allowed values (None if not constrained)

    Examples:
        >>> extract_param_info("string")
        {'type': 'string', 'description': '', 'default': None, 'enum': None}

        >>> extract_param_info({"type": "integer", "description": "User ID"})
        {'type': 'integer', 'description': 'User ID', 'default': None, 'enum': None}
    """
    if isinstance(param_spec, str):
        # Shorthand: "string", "integer", etc.
        return {
            "type": param_spec,
            "description": "",
            "default": None,
            "enum": None,
        }

    # Detailed dict
    return {
        "type": param_spec.get("type", "string"),
        "description": param_spec.get("description", ""),
        "default": param_spec.get("default"),
        "enum": param_spec.get("enum"),
    }


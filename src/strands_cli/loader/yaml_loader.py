"""YAML/JSON loader for workflow specifications.

Handles loading, parsing, and validating workflow specs from YAML or JSON files.
Supports CLI variable overrides (--var) which are merged into inputs.values.

Validation Flow:
    1. Read and parse YAML/JSON file
    2. Merge CLI variables into inputs.values
    3. Validate against JSON Schema Draft 2020-12
    4. Convert to typed Pydantic Spec model

Supported Formats:
    - .yaml, .yml: Parsed with ruamel.yaml (safe mode)
    - .json: Parsed with standard json module
"""

import json
import os
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError as PydanticValidationError
from ruamel.yaml import YAML

from strands_cli.schema.validator import validate_spec
from strands_cli.types import Spec

logger = structlog.get_logger(__name__)

# Security: Maximum spec file size to prevent memory exhaustion
# 10MB should be more than sufficient for any reasonable workflow spec
MAX_SPEC_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


class LoadError(Exception):
    """Raised when a spec file cannot be loaded or parsed."""

    pass


def _validate_file_path(file_path: Path) -> None:
    """Validate file exists and is not too large.

    Args:
        file_path: Path to validate

    Raises:
        LoadError: If file doesn't exist or is too large
    """
    if not file_path.exists():
        raise LoadError(f"Spec file not found: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > MAX_SPEC_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        max_mb = MAX_SPEC_SIZE_BYTES / (1024 * 1024)
        raise LoadError(f"Spec file too large: {size_mb:.1f}MB exceeds maximum of {max_mb:.0f}MB")


def _parse_file_content(file_path: Path, content: str) -> dict[str, Any]:
    """Parse file content based on extension.

    Args:
        file_path: Path to file (used for extension detection)
        content: File content to parse

    Returns:
        Parsed data as dictionary

    Raises:
        LoadError: If parsing fails or format unsupported
    """
    suffix = file_path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            yaml = YAML(typ="safe", pure=True)
            spec_data = yaml.load(content)
        elif suffix == ".json":
            spec_data = json.loads(content)
        else:
            raise LoadError(f"Unsupported file extension: {suffix}. Use .yaml, .yml, or .json")
    except Exception as e:
        raise LoadError(f"Failed to parse {file_path}: {e}") from e

    if not isinstance(spec_data, dict):
        raise LoadError(f"Spec must be a dictionary/object, got {type(spec_data)}")

    return spec_data


def _merge_variables(spec_data: dict[str, Any], variables: dict[str, str]) -> None:
    """Merge CLI variables into spec_data.inputs.values.

    Args:
        spec_data: Spec dictionary to modify in-place
        variables: Variables to merge
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    if debug:
        logger.debug(
            "variable_merge_start",
            cli_variables=variables,
            has_spec_inputs="inputs" in spec_data,
        )

    if "inputs" not in spec_data:
        spec_data["inputs"] = {}
    elif not isinstance(spec_data["inputs"], dict):
        raise LoadError(
            "Spec 'inputs' section must be an object/dict to merge CLI variables"
        )

    if "values" not in spec_data["inputs"]:
        spec_data["inputs"]["values"] = {}
    elif not isinstance(spec_data["inputs"]["values"], dict):
        raise LoadError(
            "Spec 'inputs.values' section must be an object/dict to merge CLI variables"
        )

    # Store original values for debug logging
    original_values = spec_data["inputs"]["values"].copy() if debug else {}

    spec_data["inputs"]["values"].update(variables)

    if debug:
        logger.debug(
            "variable_merge_complete",
            original_values=original_values,
            cli_overrides=variables,
            final_values=spec_data["inputs"]["values"],
        )


def load_spec(file_path: str | Path, variables: dict[str, str] | None = None) -> Spec:
    """Load and validate a workflow spec from YAML or JSON.

    This is the primary entry point for loading workflow specifications.
    Performs multi-stage validation: file parsing, schema validation, and
    Pydantic model conversion for type safety.

    Args:
        file_path: Path to the spec file (.yaml, .yml, or .json)
        variables: Optional CLI variables (--var k=v) to merge into inputs.values.
                   These override values in the spec file.

    Returns:
        Validated Spec object with full type information

    Raises:
        LoadError: If file cannot be read, parsed, or format is unsupported
        SchemaValidationError: If spec doesn't conform to JSON Schema
        PydanticValidationError: If spec cannot be converted to typed Spec
                                 (should be rare if schema validation passed)
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"
    file_path = Path(file_path)

    if debug:
        logger.debug(
            "load_spec_start",
            file_path=str(file_path),
            has_variables=bool(variables),
        )

    _validate_file_path(file_path)

    # Read file content
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise LoadError(f"Failed to read {file_path}: {e}") from e

    spec_data = _parse_file_content(file_path, content)

    if debug:
        logger.debug(
            "spec_parsed",
            spec_name=spec_data.get("name", "<unnamed>"),
            has_inputs="inputs" in spec_data,
        )

    # Merge CLI variables into inputs.values
    if variables:
        _merge_variables(spec_data, variables)

    # Validate against JSON Schema
    validate_spec(spec_data)

    if debug:
        logger.debug("schema_validation_passed")

    # Convert to typed Pydantic model
    try:
        spec = Spec.model_validate(spec_data)
        if debug:
            logger.debug(
                "spec_loaded",
                spec_name=spec.name,
                spec_version=spec.version,
                agents=list(spec.agents.keys()),
                pattern=spec.pattern.type if spec.pattern else None,
            )
        return spec
    except PydanticValidationError as e:
        raise LoadError(f"Failed to create typed Spec: {e}") from e


def parse_variables(var_args: list[str]) -> dict[str, str]:
    """Parse --var arguments into a dictionary.

    Args:
        var_args: List of "key=value" strings from CLI

    Returns:
        Dictionary of variables

    Raises:
        LoadError: If a variable is malformed
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"
    variables = {}

    if debug:
        logger.debug("parse_variables_start", var_count=len(var_args))

    for var in var_args:
        if "=" not in var:
            raise LoadError(f"Invalid variable format: {var}. Expected key=value")

        key, value = var.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise LoadError(f"Empty variable key in: {var}")

        variables[key] = value

        if debug:
            logger.debug(
                "variable_parsed",
                key=key,
                value=value,
                source="cli_flag",
            )

    if debug:
        logger.debug("parse_variables_complete", variables=variables)

    return variables

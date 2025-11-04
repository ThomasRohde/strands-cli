"""Schema validation for Strands workflow specifications.

Validates workflow specs against the JSON Schema Draft 2020-12 schema.
Provides precise error reporting using JSONPointer to locate validation failures.

Validation Architecture:
    - Schema loaded once at module import time (cached)
    - Draft202012Validator used for JSON Schema 2020-12 compliance
    - Errors include JSONPointer paths for exact location reporting
    - Validation is required before Pydantic model conversion

Schema Location:
    docs/strands-workflow.schema.json (relative to project root)
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class SchemaValidationError(Exception):
    """Raised when a spec fails JSON Schema validation."""

    def __init__(self, message: str, errors: list[dict[str, Any]]):
        """Initialize with message and structured error details.

        Args:
            message: Human-readable error summary
            errors: List of error details with JSONPointer paths
        """
        super().__init__(message)
        self.errors = errors


def _load_embedded_schema() -> dict[str, Any]:
    """Load the embedded strands-workflow.schema.json.

    Loads the schema from the docs/ directory relative to the project root.
    This function is called once at module import time and the result is cached.

    Returns:
        Parsed schema as a dictionary

    Raises:
        FileNotFoundError: If schema file is missing
        json.JSONDecodeError: If schema JSON is malformed
    """
    schema_path = (
        Path(__file__).parent.parent.parent.parent / "docs" / "strands-workflow.schema.json"
    )
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# Cache the schema and validator at module load time
_SCHEMA = _load_embedded_schema()
_VALIDATOR = Draft202012Validator(_SCHEMA)


def validate_spec(spec_data: dict[str, Any]) -> None:
    """Validate a workflow spec against the JSON Schema.

    Uses JSON Schema Draft 2020-12 validation to ensure the spec conforms
    to the strands-workflow.schema.json. Validation errors include JSONPointer
    paths for precise error location reporting (e.g., /runtime/provider).

    This is the first validation gate; Pydantic model conversion follows.

    Args:
        spec_data: Parsed YAML/JSON spec as a dictionary

    Raises:
        SchemaValidationError: If validation fails, with detailed error information
                              including JSONPointer locations, messages, and validator types
    """
    errors = list(_VALIDATOR.iter_errors(spec_data))

    if not errors:
        return

    # Format errors with JSONPointer paths for precise location reporting
    # JSONPointer uses slash-separated paths like /runtime/provider or /agents/main/tools/0
    formatted_errors = []
    for error in errors:
        pointer = "/" + "/".join(str(p) for p in error.absolute_path)
        if not pointer or pointer == "/":
            pointer = "(root)"

        formatted_errors.append(
            {
                "pointer": pointer,
                "message": error.message,
                "validator": error.validator,
                "path": list(error.absolute_path),
            }
        )

    # Create human-readable summary
    summary_lines = [f"Spec validation failed with {len(formatted_errors)} error(s):"]
    for i, err in enumerate(formatted_errors[:5], 1):  # Show first 5
        summary_lines.append(f"  {i}. {err['pointer']}: {err['message']}")

    if len(formatted_errors) > 5:
        summary_lines.append(f"  ... and {len(formatted_errors) - 5} more error(s)")

    raise SchemaValidationError("\n".join(summary_lines), formatted_errors)


def get_schema() -> dict[str, Any]:
    """Get the loaded schema dictionary.

    Returns a copy of the cached schema for inspection or documentation purposes.

    Returns:
        The strands-workflow.schema.json as a dict (copied to prevent mutation)
    """
    return _SCHEMA.copy()

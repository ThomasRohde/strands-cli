"""Spec verification tool (Strands SDK module-based pattern).

Validate workflow specifications and return structured validation reports.
Enables agentic workflows to programmatically verify and refine specs.
"""

import json
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from strands_cli.capability.checker import check_capability
from strands_cli.loader.yaml_loader import MAX_SPEC_SIZE_BYTES, LoadError
from strands_cli.schema.validator import SchemaValidationError, validate_spec
from strands_cli.types import Spec

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "spec_verify",
    "description": "Validate a workflow spec and return structured validation report",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "spec_content": {
                    "type": "string",
                    "description": "YAML or JSON workflow spec content to validate",
                },
                "check_capability": {
                    "type": "boolean",
                    "default": True,
                    "description": "Also check MVP capability compatibility (default: true)",
                },
            },
            "required": ["spec_content"],
        }
    },
}


def _parse_spec_content(spec_content: str) -> dict[str, Any]:
    """Parse YAML or JSON spec content.

    Args:
        spec_content: YAML or JSON string content

    Returns:
        Parsed spec data as dictionary

    Raises:
        LoadError: If parsing fails or content is invalid
    """
    # Check size limit
    content_bytes = len(spec_content.encode("utf-8"))
    if content_bytes > MAX_SPEC_SIZE_BYTES:
        size_mb = content_bytes / (1024 * 1024)
        max_mb = MAX_SPEC_SIZE_BYTES / (1024 * 1024)
        raise LoadError(
            f"Spec content too large: {size_mb:.1f}MB exceeds maximum of {max_mb:.0f}MB"
        )

    # Try JSON first (simpler), then YAML
    try:
        spec_data = json.loads(spec_content)
    except json.JSONDecodeError:
        # Not JSON, try YAML
        from ruamel.yaml import YAML

        yaml = YAML(typ="safe", pure=True)
        try:
            spec_data = yaml.load(spec_content)
        except Exception as e:
            raise LoadError(f"Failed to parse spec content as YAML or JSON: {e}") from e

    if not isinstance(spec_data, dict):
        raise LoadError(f"Spec must be a dictionary/object, got {type(spec_data).__name__}")

    return spec_data


def _build_success_report(
    spec: Spec,
    check_capability_flag: bool,
) -> dict[str, Any]:
    """Build success validation report.

    Args:
        spec: Validated Spec object
        check_capability_flag: Whether to check capability compatibility

    Returns:
        JSON validation report
    """
    report: dict[str, Any] = {
        "schema_valid": True,
        "pydantic_valid": True,
        "capability_supported": None,
        "errors": [],
        "issues": [],
        "spec_info": {
            "name": spec.name,
            "version": spec.version,
            "pattern_type": spec.pattern.type,
            "provider": spec.runtime.provider,
            "agent_count": len(spec.agents),
        },
    }

    # Check capability if requested
    if check_capability_flag:
        capability_report = check_capability(spec)
        report["capability_supported"] = capability_report.supported

        if capability_report.issues:
            report["issues"] = [
                {
                    "pointer": issue.pointer,
                    "reason": issue.reason,
                    "remediation": issue.remediation,
                }
                for issue in capability_report.issues
            ]

    return report


def _build_error_report(
    error: Exception,
    phase: str,
) -> dict[str, Any]:
    """Build error validation report.

    Args:
        error: Exception that occurred
        phase: Validation phase where error occurred

    Returns:
        JSON error report
    """
    report: dict[str, Any] = {
        "schema_valid": phase not in ["parse", "schema"],
        "pydantic_valid": phase not in ["parse", "schema", "pydantic"],
        "capability_supported": None,
        "errors": [],
        "issues": [],
    }

    # Build error details
    if isinstance(error, LoadError):
        report["errors"].append(
            {
                "phase": "parse",
                "type": "LoadError",
                "message": str(error),
            }
        )
    elif isinstance(error, SchemaValidationError):
        report["errors"].append(
            {
                "phase": "schema",
                "type": "SchemaValidationError",
                "message": str(error),
                "validation_errors": error.errors,
            }
        )
    elif isinstance(error, PydanticValidationError):
        report["errors"].append(
            {
                "phase": "pydantic",
                "type": "PydanticValidationError",
                "message": str(error),
                "validation_errors": [
                    {
                        "loc": list(err["loc"]),
                        "msg": err["msg"],
                        "type": err["type"],
                    }
                    for err in error.errors()
                ],
            }
        )
    else:
        report["errors"].append(
            {
                "phase": phase,
                "type": type(error).__name__,
                "message": str(error),
            }
        )

    return report


def spec_verify(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Validate a workflow spec and return structured validation report.

    Performs three-layer validation:
    1. Parse YAML/JSON content
    2. Validate against JSON Schema Draft 2020-12
    3. Convert to Pydantic Spec model
    4. Optionally check MVP capability compatibility

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and JSON validation report in content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    spec_content = tool_input.get("spec_content", "")
    check_capability_flag = tool_input.get("check_capability", True)

    if not spec_content:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {
                    "json": {
                        "schema_valid": False,
                        "pydantic_valid": False,
                        "capability_supported": None,
                        "errors": [
                            {
                                "phase": "input",
                                "type": "ValueError",
                                "message": "No spec_content provided",
                            }
                        ],
                        "issues": [],
                    }
                }
            ],
        }

    try:
        # Phase 1: Parse YAML/JSON
        spec_data = _parse_spec_content(spec_content)

        # Phase 2: Validate JSON Schema
        validate_spec(spec_data)

        # Phase 3: Convert to Pydantic Spec
        spec = Spec.model_validate(spec_data)

        # Build success report with optional capability check
        report = _build_success_report(spec, check_capability_flag)

        # Return success (even if capability unsupported - that's in the report)
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"json": report}],
        }

    except LoadError as e:
        report = _build_error_report(e, "parse")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"json": report}],
        }

    except SchemaValidationError as e:
        report = _build_error_report(e, "schema")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"json": report}],
        }

    except PydanticValidationError as e:
        report = _build_error_report(e, "pydantic")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"json": report}],
        }

    except Exception as e:
        report = _build_error_report(e, "unknown")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"json": report}],
        }

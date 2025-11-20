"""YAML/JSON loader for workflow specifications.

Handles loading, parsing, and validating workflow specs from YAML or JSON files.
Supports CLI variable overrides (--var) which are merged into inputs.values.
Supports atomic agent composition via $ref in agent definitions.

Validation Flow:
    1. Read and parse YAML/JSON file
    2. Resolve any $ref agent references to external atomic agent specs
    3. Merge CLI variables into inputs.values
    4. Validate against JSON Schema Draft 2020-12
    5. Convert to typed Pydantic Spec model

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


def _apply_input_defaults(spec_data: dict[str, Any]) -> None:
    """Apply default values from input parameter schemas to inputs.values.

    This ensures that optional parameters with defaults are available to
    template rendering even if not explicitly provided via CLI.

    Args:
        spec_data: Spec dictionary to modify in-place
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    if "inputs" not in spec_data or not isinstance(spec_data["inputs"], dict):
        return

    if "values" not in spec_data["inputs"]:
        spec_data["inputs"]["values"] = {}
    elif not isinstance(spec_data["inputs"]["values"], dict):
        return

    values = spec_data["inputs"]["values"]
    defaults_applied = []

    # Process required parameters with defaults
    required_params = spec_data["inputs"].get("required", {})
    if isinstance(required_params, dict):
        for param_name, param_spec in required_params.items():
            # Skip if value already exists
            if param_name in values:
                continue

            # Extract default if present
            if isinstance(param_spec, dict) and "default" in param_spec:
                values[param_name] = param_spec["default"]
                defaults_applied.append(param_name)

    # Process optional parameters with defaults
    optional_params = spec_data["inputs"].get("optional", {})
    if isinstance(optional_params, dict):
        for param_name, param_spec in optional_params.items():
            # Skip if value already exists
            if param_name in values:
                continue

            # Extract default if present
            if isinstance(param_spec, dict) and "default" in param_spec:
                values[param_name] = param_spec["default"]
                defaults_applied.append(param_name)

    if debug and defaults_applied:
        logger.debug(
            "input_defaults_applied",
            defaults_applied=defaults_applied,
            final_values=values,
        )


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
        raise LoadError("Spec 'inputs' section must be an object/dict to merge CLI variables")

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

    # Resolve $ref in agent definitions BEFORE validation
    # This allows atomic agent composition while maintaining single source of truth
    _resolve_agent_references(spec_data, file_path)

    # Apply default values from parameter schemas to inputs.values
    # This must happen BEFORE merging CLI variables so CLI can override defaults
    _apply_input_defaults(spec_data)

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

        # Attach spec directory for skills path resolution
        # This is not part of the Pydantic model but needed for runtime context
        spec._spec_dir = str(file_path.parent)  # type: ignore[attr-defined]

        if debug:
            logger.debug(
                "spec_loaded",
                spec_name=spec.name,
                spec_version=spec.version,
                agents=list(spec.agents.keys()),
                pattern=spec.pattern.type if spec.pattern else None,
                spec_dir=str(file_path.parent),
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


def _resolve_agent_reference(  # noqa: C901  # Complexity justified for robust reference resolution
    ref_path: str,
    current_spec_path: Path,
    override_fields: dict[str, Any],
    visited_refs: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve $ref in agent definition to external atomic agent spec.

    Args:
        ref_path: Path to external atomic agent spec (relative to current spec)
        current_spec_path: Path to the spec file containing the $ref
        override_fields: Fields specified alongside $ref to override referenced agent
        visited_refs: Set of already-visited reference paths (for circular detection)

    Returns:
        Merged agent definition from referenced spec and overrides

    Raises:
        LoadError: If reference file not found, invalid, circular, or not atomic
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    # Initialize visited set for circular reference detection
    if visited_refs is None:
        visited_refs = set()

    # Resolve reference path relative to current spec
    ref_file = (current_spec_path.parent / ref_path).resolve()
    ref_file_str = str(ref_file)

    if debug:
        logger.debug(
            "resolving_agent_ref",
            ref_path=ref_path,
            resolved_path=ref_file_str,
            current_spec=str(current_spec_path),
        )

    # Check for circular references
    if ref_file_str in visited_refs:
        raise LoadError(f"Circular agent reference detected: {ref_path} (already visited)")

    # Validate referenced file exists
    if not ref_file.exists():
        raise LoadError(
            f"Agent reference not found: {ref_path}\n"
            f"  Resolved to: {ref_file_str}\n"
            f"  Referenced from: {current_spec_path}"
        )

    # Load the referenced spec
    visited_refs.add(ref_file_str)
    try:
        content = ref_file.read_text(encoding="utf-8")
        referenced_spec = _parse_file_content(ref_file, content)
    except Exception as e:
        raise LoadError(f"Failed to load agent reference {ref_path}: {e}") from e

    # Validate it's an atomic agent (single agent definition)
    if "agents" not in referenced_spec or not isinstance(referenced_spec["agents"], dict):
        raise LoadError(f"Invalid agent reference {ref_path}: missing or invalid 'agents' section")

    agents = referenced_spec["agents"]
    if len(agents) != 1:
        raise LoadError(
            f"Invalid agent reference {ref_path}: "
            f"atomic agent must have exactly 1 agent, found {len(agents)}"
        )

    # Validate it has atomic label (best practice check, not strict requirement)
    metadata = referenced_spec.get("metadata", {})
    labels = metadata.get("labels", {})
    agent_type = labels.get("strands.io/agent_type")

    if debug and agent_type != "atomic":
        logger.warning(
            "agent_ref_not_atomic",
            ref_path=ref_path,
            agent_type=agent_type,
            message="Referenced agent does not have strands.io/agent_type=atomic label",
        )

    # Extract the single agent definition
    agent_id, agent_def = next(iter(agents.items()))

    if debug:
        logger.debug(
            "agent_ref_loaded",
            ref_path=ref_path,
            agent_id=agent_id,
            has_prompt="prompt" in agent_def,
            has_tools="tools" in agent_def,
            has_schemas="input_schema" in agent_def or "output_schema" in agent_def,
        )

    # Resolve schema paths relative to the atomic agent's directory
    # (not relative to the composite workflow)
    if "input_schema" in agent_def and isinstance(agent_def["input_schema"], str):
        schema_path = (ref_file.parent / agent_def["input_schema"]).resolve()
        agent_def["input_schema"] = str(schema_path)

    if "output_schema" in agent_def and isinstance(agent_def["output_schema"], str):
        schema_path = (ref_file.parent / agent_def["output_schema"]).resolve()
        agent_def["output_schema"] = str(schema_path)

    # Check for nested $ref (not allowed to prevent complex composition chains)
    if "$ref" in agent_def or "ref" in agent_def:
        raise LoadError(
            f"Nested agent references not allowed: {ref_path} contains another $ref.\n"
            f"  Atomic agents must be self-contained and cannot reference other agents."
        )

    # Merge override fields (override takes precedence)
    # Only allow override of specific safe fields
    allowed_overrides = {
        "model_id",
        "provider",
        "temperature",
        "tools",
        "inference",
        "top_p",
        "max_tokens",
    }

    for key, value in override_fields.items():
        if key not in allowed_overrides and key not in {"$ref", "ref"} and debug:
            logger.warning(
                "unexpected_override_field",
                field=key,
                ref_path=ref_path,
                message=f"Field '{key}' is not a typical override; proceeding anyway",
            )
        agent_def[key] = value

    if debug and override_fields:
        logger.debug(
            "agent_ref_merged",
            ref_path=ref_path,
            overrides=list(override_fields.keys()),
        )

    return agent_def  # type: ignore[return-value]  # Schema paths converted to absolute strings


def _resolve_agent_references(spec_data: dict[str, Any], spec_path: Path) -> None:
    """Resolve all $ref entries in agents section.

    Args:
        spec_data: Spec dictionary to modify in-place
        spec_path: Path to the spec file (for relative path resolution)

    Raises:
        LoadError: If any reference resolution fails
    """
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    if "agents" not in spec_data or not isinstance(spec_data["agents"], dict):
        return

    agents = spec_data["agents"]
    refs_resolved = []

    for agent_id, agent_def in agents.items():
        if not isinstance(agent_def, dict):
            continue

        # Check for $ref field
        ref_path = agent_def.get("$ref") or agent_def.get("ref")
        if not ref_path:
            continue

        if debug:
            logger.debug("found_agent_ref", agent_id=agent_id, ref=ref_path)

        # Extract override fields (everything except $ref)
        override_fields = {k: v for k, v in agent_def.items() if k not in {"$ref", "ref"}}

        # Resolve the reference
        resolved_agent = _resolve_agent_reference(ref_path, spec_path, override_fields)

        # Replace agent definition with resolved + merged version
        agents[agent_id] = resolved_agent
        refs_resolved.append(agent_id)

    if debug and refs_resolved:
        logger.debug("agent_refs_resolved", count=len(refs_resolved), agent_ids=refs_resolved)

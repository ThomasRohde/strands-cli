#!/usr/bin/env python3
"""Generate comprehensive schema documentation from JSON Schema."""

import json
from pathlib import Path
from typing import Any


def resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a $ref pointer to its definition."""
    if ref.startswith("#/$defs/"):
        def_name = ref.split("/")[-1]
        return defs.get(def_name)
    return None


def get_type_string(prop_schema: dict[str, Any]) -> str:
    """Extract and format type information from schema."""
    prop_type = prop_schema.get("type", "any")
    if isinstance(prop_type, list):
        return " | ".join(f"`{t}`" for t in prop_type)

    # Handle oneOf type unions
    if "oneOf" in prop_schema:
        types = []
        for option in prop_schema["oneOf"]:
            if "type" in option:
                types.append(option["type"])
            elif "$ref" in option:
                types.append(option["$ref"].split("/")[-1])
        if types:
            return " | ".join(f"`{t}`" for t in types)

    return f"`{prop_type}`"


def format_constraints(prop_schema: dict[str, Any]) -> list[str]:
    """Extract validation constraints from schema."""
    constraints = []

    if "minimum" in prop_schema:
        constraints.append(f"Minimum: `{prop_schema['minimum']}`")
    if "maximum" in prop_schema:
        constraints.append(f"Maximum: `{prop_schema['maximum']}`")
    if "minLength" in prop_schema:
        constraints.append(f"Min length: `{prop_schema['minLength']}`")
    if "maxLength" in prop_schema:
        constraints.append(f"Max length: `{prop_schema['maxLength']}`")
    if "pattern" in prop_schema:
        constraints.append(f"Pattern: `{prop_schema['pattern']}`")
    if "format" in prop_schema:
        constraints.append(f"Format: `{prop_schema['format']}`")
    if prop_schema.get("uniqueItems"):
        constraints.append("Items must be unique")
    if "default" in prop_schema:
        constraints.append(f"Default: `{prop_schema['default']}`")

    return constraints


def generate_nested_properties(
    prop_schema: dict[str, Any],
    defs: dict[str, Any],
    level: int = 4,
    max_depth: int = 2,
    current_depth: int = 0
) -> str:
    """Generate documentation for nested object properties."""
    if current_depth >= max_depth:
        return ""

    lines = []
    properties = prop_schema.get("properties", {})
    required = prop_schema.get("required", [])

    if not properties:
        return ""

    lines.append("")
    lines.append(f"{'#' * level} Properties")
    lines.append("")

    for prop_name, nested_schema in properties.items():
        # Resolve $ref if present
        if "$ref" in nested_schema:
            resolved = resolve_ref(nested_schema["$ref"], defs)
            if resolved:
                nested_schema = {**resolved, **{k: v for k, v in nested_schema.items() if k != "$ref"}}

        is_required = prop_name in required
        req_badge = "**required**" if is_required else "*optional*"

        lines.append(f"**`{prop_name}`** ({req_badge})")
        lines.append("")

        # Type
        type_str = get_type_string(nested_schema)
        lines.append(f"- Type: {type_str}")

        # Description
        if "description" in nested_schema:
            lines.append(f"- {nested_schema['description']}")

        # Constraints
        constraints = format_constraints(nested_schema)
        for constraint in constraints:
            lines.append(f"- {constraint}")

        # Enum values
        if "enum" in nested_schema:
            enum_vals = ", ".join(f"`{v}`" for v in nested_schema["enum"])
            lines.append(f"- Allowed values: {enum_vals}")

        lines.append("")

    return "\n".join(lines)


def generate_property_docs(schema: dict[str, Any], level: int = 3, max_depth: int = 2) -> str:
    """Generate markdown documentation for schema properties."""
    lines = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    defs = schema.get("$defs", {})

    for prop_name, prop_schema in properties.items():
        # Resolve $ref if present
        original_ref = None
        if "$ref" in prop_schema:
            original_ref = prop_schema["$ref"].split("/")[-1]
            resolved = resolve_ref(prop_schema["$ref"], defs)
            if resolved:
                # Merge resolved schema with any overrides
                prop_schema = {**resolved, **{k: v for k, v in prop_schema.items() if k != "$ref"}}

        # Property header
        is_required = prop_name in required
        req_badge = "**Required**" if is_required else "*Optional*"
        lines.append(f"{'#' * level} `{prop_name}` {req_badge}")
        lines.append("")

        # Type with ref link
        type_str = get_type_string(prop_schema)
        if original_ref:
            lines.append(f"**Type**: {type_str} (see [`{original_ref}`](#{original_ref.lower()}))")
        else:
            lines.append(f"**Type**: {type_str}")
        lines.append("")

        # Description
        description = prop_schema.get("description", "No description available.")
        lines.append(description)
        lines.append("")

        # Constraints
        constraints = format_constraints(prop_schema)
        if constraints:
            lines.append("**Constraints**:")
            lines.append("")
            for constraint in constraints:
                lines.append(f"- {constraint}")
            lines.append("")

        # Enum values
        if "enum" in prop_schema:
            lines.append("**Allowed values**:")
            lines.append("")
            for value in prop_schema["enum"]:
                lines.append(f"- `{value}`")
            lines.append("")

        # Examples
        if "examples" in prop_schema:
            lines.append("**Examples**:")
            lines.append("")
            examples = prop_schema["examples"]
            if isinstance(examples, list):
                for example in examples:
                    if isinstance(example, (dict, list)):
                        lines.append("```yaml")
                        lines.append(json.dumps(example, indent=2))
                        lines.append("```")
                    else:
                        lines.append(f"```\n{example}\n```")
            lines.append("")

        # Nested properties for objects
        if prop_schema.get("type") == "object" and "properties" in prop_schema:
            nested_docs = generate_nested_properties(prop_schema, defs, level + 1, max_depth)
            if nested_docs:
                lines.append(nested_docs)

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _format_definition_property(
    prop_name: str, prop_schema: dict[str, Any], defs: dict[str, Any], required: list[str]
) -> list[str]:
    """Format a single definition property."""
    lines = []

    # Resolve $ref
    if "$ref" in prop_schema:
        resolved = resolve_ref(prop_schema["$ref"], defs)
        if resolved:
            prop_schema = {**resolved, **{k: v for k, v in prop_schema.items() if k != "$ref"}}

    is_required = prop_name in required
    req_badge = "**required**" if is_required else "*optional*"

    lines.append(f"**`{prop_name}`** ({req_badge})")
    lines.append("")

    # Type
    type_str = get_type_string(prop_schema)
    lines.append(f"- Type: {type_str}")

    # Description
    if "description" in prop_schema:
        lines.append(f"- {prop_schema['description']}")

    # Constraints
    constraints = format_constraints(prop_schema)
    for constraint in constraints:
        lines.append(f"- {constraint}")

    # Enum
    if "enum" in prop_schema:
        enum_vals = ", ".join(f"`{v}`" for v in prop_schema["enum"])
        lines.append(f"- Allowed values: {enum_vals}")

    lines.append("")

    return lines


def generate_definition_docs(def_name: str, def_schema: dict[str, Any], defs: dict[str, Any], level: int = 3) -> str:
    """Generate documentation for a schema definition."""
    lines = []

    lines.append(f"{'#' * level} `{def_name}`")
    lines.append("")

    # Description
    description = def_schema.get("description", "No description available.")
    lines.append(description)
    lines.append("")

    # Type
    type_str = get_type_string(def_schema)
    lines.append(f"**Type**: {type_str}")
    lines.append("")

    # Constraints
    constraints = format_constraints(def_schema)
    if constraints:
        lines.append("**Constraints**:")
        lines.append("")
        for constraint in constraints:
            lines.append(f"- {constraint}")
        lines.append("")

    # Enum values
    if "enum" in def_schema:
        lines.append("**Allowed values**:")
        lines.append("")
        for value in def_schema["enum"]:
            lines.append(f"- `{value}`")
        lines.append("")

    # Examples
    if "examples" in def_schema:
        lines.append("**Examples**:")
        lines.append("")
        examples = def_schema["examples"]
        if isinstance(examples, list):
            for example in examples:
                if isinstance(example, (dict, list)):
                    lines.append("```yaml")
                    lines.append(json.dumps(example, indent=2))
                    lines.append("```")
                else:
                    lines.append(f"```\n{example}\n```")
        lines.append("")

    # Properties for object types
    if def_schema.get("type") == "object" and "properties" in def_schema:
        properties = def_schema.get("properties", {})
        required = def_schema.get("required", [])

        lines.append(f"{'#' * (level + 1)} Properties")
        lines.append("")

        for prop_name, prop_schema in properties.items():
            lines.extend(_format_definition_property(prop_name, prop_schema, defs, required))

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Generate schema documentation."""
    # Load schema
    schema_path = (
        Path(__file__).parent.parent / "src/strands_cli/schema/strands-workflow.schema.json"
    )
    with open(schema_path) as f:
        schema = json.load(f)

    # Generate documentation
    docs = [
        "# Schema Reference",
        "",
        "Complete JSON Schema reference for Strands workflow specifications.",
        "",
        "> **Note**: This documentation is auto-generated from `strands-workflow.schema.json`.",
        "> For a more narrative guide, see the [Workflow Manual](workflow-manual.md).",
        "",
        "## Overview",
        "",
        f"**Schema Title**: {schema.get('title', 'N/A')}",
        "",
        f"**Description**: {schema.get('description', 'N/A')}",
        "",
        f"**Schema Version**: {schema.get('$schema', 'N/A')}",
        "",
        "## Quick Links",
        "",
        "- [Top-Level Properties](#top-level-properties)",
        "- [Schema Definitions](#schema-definitions)",
        "- [Workflow Patterns](#workflow-patterns)",
        "- [See Also](#see-also)",
        "",
        "## Top-Level Properties",
        "",
        "These are the root properties of a workflow specification file:",
        "",
        generate_property_docs(schema, level=3, max_depth=1),
        "",
        "## Schema Definitions",
        "",
        "The following types are referenced throughout the schema using `$ref`.",
        "Click each definition to see detailed property documentation.",
        "",
    ]

    # Generate documentation for key definitions
    defs = schema.get("$defs", {})

    # Group definitions by category
    pattern_defs = [
        "chainConfig",
        "workflowConfig",
        "routingConfig",
        "parallelConfig",
        "evaluatorOptimizerConfig",
        "orchestratorWorkersConfig",
        "graphConfig",
    ]

    core_defs = [
        "runtime",
        "agents",
        "agentSpec",
        "tools",
        "inputs",
        "outputs",
        "env",
    ]

    advanced_defs = [
        "telemetry",
        "contextPolicy",
        "security",
        "skills",
    ]

    # Pattern configurations
    docs.append("### Workflow Patterns")
    docs.append("")
    docs.append(
        "These definitions configure the seven supported workflow patterns. "
        "See [Pattern Explanations](../explanation/patterns.md) for usage guidance."
    )
    docs.append("")

    for def_name in pattern_defs:
        if def_name in defs:
            docs.append(generate_definition_docs(def_name, defs[def_name], defs, level=4))

    # Core definitions
    docs.append("### Core Configuration")
    docs.append("")
    docs.append(
        "Essential configuration types used in most workflows."
    )
    docs.append("")

    for def_name in core_defs:
        if def_name in defs:
            docs.append(generate_definition_docs(def_name, defs[def_name], defs, level=4))

    # Advanced definitions
    docs.append("### Advanced Features")
    docs.append("")
    docs.append(
        "Optional advanced configuration for observability, security, and optimization."
    )
    docs.append("")

    for def_name in advanced_defs:
        if def_name in defs:
            docs.append(generate_definition_docs(def_name, defs[def_name], defs, level=4))

    # Utility definitions
    docs.append("### Utility Types")
    docs.append("")
    docs.append(
        "Basic types and validators used throughout the schema."
    )
    docs.append("")

    utility_defs = [
        name for name in sorted(defs.keys())
        if name not in pattern_defs + core_defs + advanced_defs
    ]

    for def_name in utility_defs:
        docs.append(generate_definition_docs(def_name, defs[def_name], defs, level=4))

    # Footer
    docs.append("## See Also")
    docs.append("")
    docs.append("- [Workflow Manual](workflow-manual.md) - Comprehensive guide with examples")
    docs.append("- [Pattern Explanations](../explanation/patterns.md) - When to use each pattern")
    docs.append("- [CLI Reference](cli.md) - Command-line interface")
    docs.append("- [Examples](examples.md) - Example workflows for each pattern")
    docs.append("- [Tutorials](../tutorials/quickstart-ollama.md) - Getting started guide")

    # Write to file
    output_path = Path(__file__).parent.parent / "manual/reference/schema.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(docs))
    print(f"Generated schema documentation: {output_path}")
    print(f"  - {len(defs)} definitions documented")
    print(f"  - {len(schema.get('properties', {}))} top-level properties")


if __name__ == "__main__":
    main()

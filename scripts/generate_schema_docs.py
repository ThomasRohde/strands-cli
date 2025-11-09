#!/usr/bin/env python3
"""Generate schema documentation from JSON Schema."""
import json
from pathlib import Path


def generate_property_docs(schema: dict, level: int = 3) -> str:
    """Generate markdown documentation for schema properties."""
    lines = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    defs = schema.get("$defs", {})

    for prop_name, prop_schema in properties.items():
        # Resolve $ref if present
        if "$ref" in prop_schema:
            ref_path = prop_schema["$ref"].split("/")[-1]
            if ref_path in defs:
                prop_schema = defs[ref_path]

        # Property header
        is_required = prop_name in required
        req_badge = "**Required**" if is_required else "*Optional*"
        lines.append(f"{'#' * level} `{prop_name}` {req_badge}")
        lines.append("")

        # Type
        prop_type = prop_schema.get("type", "any")
        if isinstance(prop_type, list):
            prop_type = " | ".join(prop_type)
        lines.append(f"**Type**: `{prop_type}`")
        lines.append("")

        # Description
        description = prop_schema.get("description", "No description available.")
        lines.append(description)
        lines.append("")

        # Examples
        if "examples" in prop_schema:
            lines.append("**Examples**:")
            lines.append("")
            lines.append("```")
            for example in prop_schema["examples"]:
                lines.append(str(example))
            lines.append("```")
            lines.append("")

        # Enum values
        if "enum" in prop_schema:
            lines.append("**Allowed values**:")
            lines.append("")
            for value in prop_schema["enum"]:
                lines.append(f"- `{value}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    """Generate schema documentation."""
    # Load schema
    schema_path = Path(__file__).parent.parent / "src/strands_cli/schema/strands-workflow.schema.json"
    with open(schema_path) as f:
        schema = json.load(f)

    # Generate documentation
    docs = [
        "# Schema Reference",
        "",
        "Complete JSON Schema reference for Strands workflow specifications.",
        "",
        "## Overview",
        "",
        f"**Schema Title**: {schema.get('title', 'N/A')}",
        "",
        f"**Description**: {schema.get('description', 'N/A')}",
        "",
        f"**Schema Version**: {schema.get('$schema', 'N/A')}",
        "",
        "## Top-Level Properties",
        "",
        generate_property_docs(schema, level=3),
        "",
        "## Schema Definitions",
        "",
        "The schema includes the following reusable definitions in `$defs`:",
        "",
    ]

    # List all definitions
    defs = schema.get("$defs", {})
    for def_name in sorted(defs.keys()):
        docs.append(f"- `{def_name}`")

    docs.append("")
    docs.append("## See Also")
    docs.append("")
    docs.append("- [CLI Reference](cli.md) - Command-line interface")
    docs.append("- [Examples](examples.md) - Example workflows")
    docs.append("- [Tutorials](../tutorials/quickstart-ollama.md) - Getting started")

    # Write to file
    output_path = Path(__file__).parent.parent / "manual/reference/schema.md"
    output_path.write_text("\n".join(docs))
    print(f"Generated schema documentation: {output_path}")


if __name__ == "__main__":
    main()

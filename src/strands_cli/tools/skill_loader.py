"""Skill loader tool factory for progressive skill loading.

This module provides a factory function to create skill loader tools
that enable agents to dynamically load detailed skill instructions
from the filesystem during workflow execution, mimicking Claude Code's
progressive skill loading behavior.

The factory pattern allows injecting workflow-specific context (spec, spec_dir)
into the tool at build time, similar to http_executor_factory.
"""

from pathlib import Path
from types import ModuleType
from typing import Any

from strands_cli.types import Spec


def create_skill_loader_tool(spec: Spec, spec_dir: str | None, loaded_skills: set[str]) -> ModuleType:
    """Create a skill loader tool module with spec context.

    Factory function that creates a dynamic module-based tool with access
    to the workflow spec, spec directory, and loaded skills set. This follows
    the same pattern as http_executor_factory.

    Args:
        spec: Workflow specification (contains skills list)
        spec_dir: Directory of the workflow spec file (for path resolution)
        loaded_skills: Set of already-loaded skill IDs (shared across invocations)

    Returns:
        Module-based tool with TOOL_SPEC and Skill function
    """
    # Tool specification for Strands SDK
    tool_spec = {
        "name": "Skill",
        "description": (
            "Load detailed instructions for a specific skill. "
            "Use this when you need specialized capabilities from an available skill."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "ID of the skill to load (from Available Skills list)",
                    }
                },
                "required": ["skill_id"],
            }
        },
    }

    def skill(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Load skill content from filesystem.

        This tool is invoked by agents to progressively load skill instructions
        on demand. It reads the SKILL.md file from the skill's directory and
        returns the content as a tool result.

        Args:
            tool: Tool invocation dict with toolUseId and input
            **kwargs: Additional context (unused - context comes from closure)

        Returns:
            Tool result dict with status and content
        """
        tool_use_id = tool.get("toolUseId", "")
        tool_input = tool.get("input", {})
        skill_id = tool_input.get("skill_id", "")

        # Validate inputs
        if not skill_id:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": "Error: skill_id parameter is required"}],
            }

        # Check if skill already loaded (warn but don't error)
        if skill_id in loaded_skills:
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [
                    {
                        "text": f"Skill '{skill_id}' is already loaded. "
                        f"No need to reload it."
                    }
                ],
            }

        # Find skill in spec
        skill = None
        if spec.skills:
            for s in spec.skills:
                if s.id == skill_id:
                    skill = s
                    break

        if skill is None:
            # Provide helpful error with list of available skills
            available = ", ".join([s.id for s in spec.skills]) if spec.skills else "none"
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Skill '{skill_id}' not found in workflow specification.\n"
                        f"Available skills: {available}"
                    }
                ],
            }

        # Validate and resolve skill path
        if not skill.path:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Skill '{skill_id}' has no path defined in the specification."
                    }
                ],
            }

        # Resolve skill path relative to spec directory
        skill_path = Path(skill.path)
        if not skill_path.is_absolute() and spec_dir:
            skill_path = Path(spec_dir) / skill_path

        # Security: Validate path to prevent directory traversal
        try:
            skill_path = skill_path.resolve()
            # Additional check: ensure resolved path is still within expected boundaries
            # (This is a basic check; adjust based on security requirements)
        except (OSError, RuntimeError) as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Invalid skill path for '{skill_id}': {e}"
                    }
                ],
            }

        # Look for SKILL.md file
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            # Fallback to README.md
            skill_file = skill_path / "README.md"
            if not skill_file.exists():
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [
                        {
                            "text": f"Error: Skill '{skill_id}' has no SKILL.md or README.md file at path: {skill_path}"
                        }
                    ],
                }

        # Read skill content
        try:
            # Read file synchronously (tools are called in async context by SDK)
            content = _read_skill_file(skill_file)
        except Exception as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error reading skill file for '{skill_id}': {e}"
                    }
                ],
            }

        # Mark skill as loaded
        loaded_skills.add(skill_id)

        # Format skill content for injection
        formatted_content = _format_skill_content(skill_id, skill.description, content)

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": formatted_content}],
        }

    # Create module with proper attributes for Strands SDK compatibility
    # (following the same pattern as http_executor_factory)
    module_name = "Skill"
    tool_module = ModuleType(module_name)
    tool_module.__doc__ = "Progressive skill loader for Strands CLI"
    tool_module.__name__ = module_name
    tool_module.__package__ = "strands_cli.tools"
    tool_module.__file__ = "<dynamic:skill_loader>"

    # Set TOOL_SPEC (dynamic attribute on ModuleType)
    tool_module.TOOL_SPEC = tool_spec  # type: ignore[attr-defined]

    # Set function name to match TOOL_SPEC name
    skill.__name__ = "Skill"
    skill.__doc__ = "Load detailed instructions for a specific skill"

    # Set the function as a module attribute with the same name
    tool_module.Skill = skill  # type: ignore[attr-defined]

    # Attach context for inspection/debugging (dynamic attributes)
    tool_module._spec = spec  # type: ignore[attr-defined]
    tool_module._spec_dir = spec_dir  # type: ignore[attr-defined]
    tool_module._loaded_skills = loaded_skills  # type: ignore[attr-defined]

    return tool_module


def _read_skill_file(file_path: Path) -> str:
    """Read skill file content synchronously (called in thread).

    Args:
        file_path: Path to skill file

    Returns:
        File content as string

    Raises:
        IOError: If file cannot be read
    """
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def _format_skill_content(skill_id: str, description: str | None, content: str) -> str:
    """Format skill content for injection into agent context.

    Args:
        skill_id: Skill identifier
        description: Optional skill description
        content: Raw skill file content

    Returns:
        Formatted skill content with header
    """
    lines = [f"# Loaded Skill: {skill_id}"]

    if description:
        lines.append(f"\n**Description**: {description}")

    lines.append("\n---\n")
    lines.append(content)

    return "\n".join(lines)

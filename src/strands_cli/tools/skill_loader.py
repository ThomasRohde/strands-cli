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

import structlog

from strands_cli.types import Spec


def create_skill_loader_tool(
    spec: Spec, spec_dir: str | None, loaded_skills: set[str]
) -> ModuleType:
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
    logger = structlog.get_logger(__name__)

    # Tool specification for Strands SDK
    tool_spec = {
        "name": "Skill",
        "description": (
            "Load detailed instructions for a specific skill or skill module. "
            "Use this when you need specialized capabilities from an available skill. "
            "Supports nested module loading via paths like 'skill-id/module' "
            "(e.g., 'strands-spec/patterns' loads patterns.md from the strands-spec skill)."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": (
                            "ID of the skill to load (from Available Skills list), "
                            "or skill-id/module to load a specific module "
                            "(e.g., 'strands-spec/patterns' loads patterns.md)"
                        ),
                    }
                },
                "required": ["skill_id"],
            }
        },
    }

    logger.info(
        "skill_loader_tool_created",
        spec_name=getattr(spec, "name", None),
        spec_dir=spec_dir,
        skills_count=len(spec.skills) if spec.skills else 0,
    )

    def skill(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Load skill content from filesystem.

        This tool is invoked by agents to progressively load skill instructions
        on demand. It reads the SKILL.md file from the skill's directory and
        returns the content as a tool result.

        Supports nested module loading via paths like "skill-id/module" which
        will load module.md from the skill directory (e.g., "strands-spec/patterns"
        loads patterns.md from the strands-spec skill directory).

        Args:
            tool: Tool invocation dict with toolUseId and input
            **kwargs: Additional context (unused - context comes from closure)

        Returns:
            Tool result dict with status and content
        """
        tool_use_id = tool.get("toolUseId", "")
        tool_input = tool.get("input", {})
        skill_id_input = tool_input.get("skill_id", "")

        logger.info(
            "skill_load_requested",
            skill_id=skill_id_input or None,
            spec_name=getattr(spec, "name", None),
        )

        # Validate inputs
        if not skill_id_input:
            logger.warning("skill_load_missing_param", missing="skill_id")
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": "Error: skill_id parameter is required"}],
            }

        # Parse skill_id to support nested modules (e.g., "strands-spec/patterns")
        # Split on "/" to separate base skill ID from optional module path
        parts = skill_id_input.split("/", 1)
        base_skill_id = parts[0]
        module_path = parts[1] if len(parts) > 1 else None

        logger.debug(
            "skill_path_parsed",
            skill_id_input=skill_id_input,
            base_skill_id=base_skill_id,
            module_path=module_path,
        )

        # Check if skill already loaded (warn but don't error)
        if skill_id_input in loaded_skills:
            logger.info(
                "skill_already_loaded",
                skill_id=skill_id_input,
                loaded_count=len(loaded_skills),
            )
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [
                    {"text": f"Skill '{skill_id_input}' is already loaded. No need to reload it."}
                ],
            }

        # Find base skill in spec
        skill = None
        if spec.skills:
            for s in spec.skills:
                if s.id == base_skill_id:
                    skill = s
                    break

        if skill is None:
            # Provide helpful error with list of available skills
            available = ", ".join([s.id for s in spec.skills]) if spec.skills else "none"
            logger.warning(
                "skill_not_found",
                skill_id=skill_id_input,
                base_skill_id=base_skill_id,
                available=available.split(", ") if available != "none" else [],
            )
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Skill '{base_skill_id}' not found in workflow specification.\n"
                        f"Available skills: {available}"
                    }
                ],
            }

        # Validate and resolve skill path
        if not skill.path:
            logger.warning("skill_no_path", skill_id=base_skill_id)
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Skill '{base_skill_id}' has no path defined in the specification."
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
            logger.error(
                "skill_path_invalid", skill_id=base_skill_id, path=str(skill_path), error=str(e)
            )
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: Invalid skill path for '{base_skill_id}': {e}"}],
            }

        logger.info("skill_path_resolved", skill_id=skill_id_input, path=str(skill_path))

        # Determine which file to load
        if module_path:
            # Loading a nested module (e.g., "patterns" -> patterns.md)
            skill_file = skill_path / f"{module_path}.md"
            if not skill_file.exists():
                # List available modules for helpful error message
                available_modules = []
                if skill_path.exists() and skill_path.is_dir():
                    available_modules = [
                        f.stem
                        for f in skill_path.glob("*.md")
                        if f.name not in ["SKILL.md", "README.md"]
                    ]

                logger.warning(
                    "skill_module_missing",
                    skill_id=skill_id_input,
                    base_skill_id=base_skill_id,
                    module_path=module_path,
                    tried=str(skill_file),
                    available_modules=available_modules,
                )

                available_str = ", ".join(available_modules) if available_modules else "none"
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [
                        {
                            "text": f"Error: Module '{module_path}' not found in skill '{base_skill_id}'.\n"
                            f"Expected file: {skill_file}\n"
                            f"Available modules: {available_str}"
                        }
                    ],
                }
            logger.info(
                "skill_module_selected",
                skill_id=skill_id_input,
                module_path=module_path,
                file=str(skill_file),
            )
        else:
            # Look for SKILL.md file
            skill_file = skill_path / "SKILL.md"
            if not skill_file.exists():
                # Fallback to README.md
                skill_file = skill_path / "README.md"
                if not skill_file.exists():
                    logger.warning(
                        "skill_file_missing",
                        skill_id=base_skill_id,
                        tried=[str(skill_path / "SKILL.md"), str(skill_path / "README.md")],
                    )
                    return {
                        "toolUseId": tool_use_id,
                        "status": "error",
                        "content": [
                            {
                                "text": f"Error: Skill '{base_skill_id}' has no SKILL.md or README.md file at path: {skill_path}"
                            }
                        ],
                    }
                else:
                    logger.info(
                        "skill_file_selected",
                        skill_id=skill_id_input,
                        file=str(skill_file),
                        fallback=True,
                    )
            else:
                logger.info(
                    "skill_file_selected",
                    skill_id=skill_id_input,
                    file=str(skill_file),
                    fallback=False,
                )

        # Read skill content
        try:
            # Read file synchronously (tools are called in async context by SDK)
            content = _read_skill_file(skill_file)
        except Exception as e:
            logger.error(
                "skill_file_read_error", skill_id=skill_id_input, file=str(skill_file), error=str(e)
            )
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error reading skill file for '{skill_id_input}': {e}"}],
            }

        logger.info(
            "skill_file_read",
            skill_id=skill_id_input,
            file=str(skill_file),
            content_len=len(content),
        )

        # Mark skill as loaded (use full skill_id_input to track modules separately)
        loaded_skills.add(skill_id_input)

        logger.info(
            "skill_loaded",
            skill_id=skill_id_input,
            loaded_count=len(loaded_skills),
        )

        # Format skill content for injection
        # For modules, use a simpler format without the description
        if module_path:
            formatted_content = _format_module_content(base_skill_id, module_path, content)
        else:
            formatted_content = _format_skill_content(skill_id_input, skill.description, content)

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


def _format_module_content(base_skill_id: str, module_path: str, content: str) -> str:
    """Format skill module content for injection into agent context.

    Args:
        base_skill_id: Base skill identifier
        module_path: Module path (e.g., "patterns", "tools")
        content: Raw module file content

    Returns:
        Formatted module content with header
    """
    lines = [f"# Loaded Skill Module: {base_skill_id}/{module_path}"]
    lines.append("\n---\n")
    lines.append(content)

    return "\n".join(lines)

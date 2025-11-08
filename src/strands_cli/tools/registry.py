"""Minimal tool registry for native tools.

This module provides auto-discovery and registration of native tools that follow
the Strands SDK module-based pattern with TOOL_SPEC exports.
"""

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ToolInfo:
    """Minimal tool metadata for discovery.

    Attributes:
        id: Tool identifier (e.g., "http_request")
        module_path: Full import path (e.g., "strands_cli.tools.http_request")
        description: Tool description from TOOL_SPEC
    """

    id: str
    module_path: str
    description: str

    @property
    def import_path(self) -> str:
        """Full import path for loading.

        Returns:
            The module_path (e.g., "strands_cli.tools.http_request")
        """
        return self.module_path

    @property
    def legacy_path(self) -> str:
        """Backward-compatible 'strands_tools.*' path.

        Returns:
            Legacy format path (e.g., "strands_tools.http_request.http_request")
        """
        return f"strands_tools.{self.id}.{self.id}"

    @property
    def legacy_short(self) -> str:
        """Old short format.

        Returns:
            Legacy short format (e.g., "strands_tools.http_request")
        """
        return f"strands_tools.{self.id}"


class ToolRegistry:
    """Simple singleton registry for native tools.

    Auto-discovers tools from the strands_cli.tools module on first instantiation.
    Tools must export a TOOL_SPEC dictionary following the Strands SDK pattern.
    """

    _instance: "ToolRegistry | None" = None
    _tools: dict[str, ToolInfo]

    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern - ensures only one registry instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._discover_tools()
        return cls._instance

    def _discover_tools(self) -> None:
        """Auto-discover tools from strands_cli.tools module.

        Scans for Python files in tools/ directory, imports them,
        and checks for TOOL_SPEC export. Logs warnings for malformed
        modules but continues discovery.
        """
        tools_dir = Path(__file__).parent

        # Modules to skip (not tools themselves)
        skip_modules = {
            "registry",  # This registry module
            "http_executor_factory",  # Creates HTTP executor tools dynamically
            "notes_manager",  # Utility for notes management
        }

        # Scan all .py files (skip __init__, registry, etc.)
        for _importer, module_name, _is_pkg in pkgutil.iter_modules([str(tools_dir)]):
            # Skip special files, packages, and utility modules
            if module_name.startswith("_") or module_name in skip_modules:
                continue

            try:
                module = importlib.import_module(f"strands_cli.tools.{module_name}")

                # Check for TOOL_SPEC (Strands SDK pattern)
                if not hasattr(module, "TOOL_SPEC"):
                    logger.warning(
                        "Tool module missing TOOL_SPEC, skipping",
                        module_name=module_name,
                        module_path=f"strands_cli.tools.{module_name}",
                    )
                    continue

                spec = module.TOOL_SPEC

                # Validate TOOL_SPEC has required fields
                if not isinstance(spec, dict) or "name" not in spec:
                    logger.warning(
                        "Tool module has invalid TOOL_SPEC (missing 'name'), skipping",
                        module_name=module_name,
                        module_path=f"strands_cli.tools.{module_name}",
                    )
                    continue

                tool_id = spec["name"]

                # Check for duplicate tool IDs
                if tool_id in self._tools:
                    logger.warning(
                        "Duplicate tool ID detected, using last discovered",
                        tool_id=tool_id,
                        existing_module=self._tools[tool_id].module_path,
                        new_module=f"strands_cli.tools.{module_name}",
                    )

                tool_info = ToolInfo(
                    id=tool_id,
                    module_path=f"strands_cli.tools.{module_name}",
                    description=spec.get("description", ""),
                )
                self._tools[tool_id] = tool_info

                logger.debug("Discovered tool", tool_id=tool_id, module_path=tool_info.module_path)

            except Exception as e:
                logger.warning(
                    "Failed to import tool module, skipping",
                    module_name=module_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    def get(self, tool_id: str) -> ToolInfo | None:
        """Get tool by ID.

        Args:
            tool_id: Tool identifier (e.g., "http_request")

        Returns:
            ToolInfo if found, None otherwise
        """
        return self._tools.get(tool_id)

    def list_all(self) -> list[ToolInfo]:
        """List all registered tools.

        Returns:
            List of all ToolInfo objects in the registry
        """
        return list(self._tools.values())

    def resolve(self, user_input: str) -> str | None:
        """Resolve user input to canonical import path.

        Supports multiple formats for backward compatibility:
        - Direct ID: "http_request" → "strands_cli.tools.http_request"
        - Legacy short: "strands_tools.http_request" → "strands_cli.tools.http_request"
        - Legacy full: "strands_tools.http_request.http_request" → "strands_cli.tools.http_request"

        Args:
            user_input: Tool reference from workflow spec

        Returns:
            Canonical import path or None if not found
        """
        # Direct ID lookup
        if user_input in self._tools:
            return self._tools[user_input].import_path

        # Legacy format: "strands_tools.X" or "strands_tools.X.X"
        if user_input.startswith("strands_tools."):
            parts = user_input.split(".")
            tool_id = parts[1] if len(parts) >= 2 else None
            if tool_id and tool_id in self._tools:
                return self._tools[tool_id].import_path

        return None

    def get_allowlist(self) -> set[str]:
        """Generate complete allowlist for capability checker.

        Returns all valid import formats for all discovered tools:
        - Short ID: "python_exec"
        - New format: "strands_cli.tools.python_exec"
        - Legacy full: "strands_tools.python_exec.python_exec"
        - Legacy short: "strands_tools.python_exec"

        Returns:
            Set of all valid import path formats
        """
        allowlist = set()
        for tool in self._tools.values():
            allowlist.add(tool.id)  # Short ID: "python_exec"
            allowlist.add(tool.import_path)  # New: "strands_cli.tools.python_exec"
            allowlist.add(tool.legacy_path)  # Legacy: "strands_tools.python_exec.python_exec"
            allowlist.add(tool.legacy_short)  # Legacy: "strands_tools.python_exec"
        return allowlist

    def _reset(self) -> None:
        """Reset registry to clean state.

        WARNING: This method is for testing only. It clears all discovered
        tools and re-runs discovery. Not intended for production use.
        """
        self._tools.clear()
        self._discover_tools()


def get_registry() -> ToolRegistry:
    """Get the global tool registry singleton.

    Returns:
        The singleton ToolRegistry instance
    """
    return ToolRegistry()

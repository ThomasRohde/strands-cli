"""Safe tool adapters for Python tools.

Provides controlled tool execution with security boundaries:

Python Tools:
    - Allowlist enforcement (only approved imports)
    - Dynamic import validation
    - Callable verification

HTTP Executors:
    - Now handled by tools/http_executor_factory.py
    - Creates proper native tool modules with TOOL_SPEC

All tools raise ToolError on failures for consistent error handling.
"""

import importlib
from typing import Any


class ToolError(Exception):
    """Raised when tool initialization or execution fails."""

    pass


def load_python_callable(import_path: str) -> Any:
    """Load a Python tool from an import path.

    Handles two types of tools based on Strands patterns:
    1. @tool decorated functions: Returns the decorated function object
    2. Module-based tools: Returns the module itself (has TOOL_SPEC)

    Security: Only loads from native tools registry to prevent arbitrary code
    execution. All tools must be auto-discovered with TOOL_SPEC pattern.

    Supports native tool path formats:
    - Short ID: "python_exec" (resolved via registry)
    - Full path: "strands_cli.tools.python_exec"

    Args:
        import_path: Native tool short ID or full dotted import path

    Returns:
        Either a decorated function tool or a module-based tool object

    Raises:
        ToolError: If tool is not in allowlist, cannot be loaded, or is invalid
    """
    # Import registry here to avoid circular imports
    from strands_cli.tools import get_registry

    registry = get_registry()
    allowed = registry.get_allowlist()

    if import_path not in allowed:
        raise ToolError(
            f"Python callable '{import_path}' not in allowlist. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )

    try:
        # Try native-first resolution for short IDs (e.g., "python_exec")
        resolved_path = registry.resolve(import_path)
        if resolved_path:
            # Native tool found - load the module directly
            module = importlib.import_module(resolved_path)
            # Native tools always have TOOL_SPEC, return module
            if hasattr(module, "TOOL_SPEC"):
                return module

        # Check if this is already a full native path (e.g., "strands_cli.tools.python_exec")
        if import_path.startswith("strands_cli.tools."):
            module = importlib.import_module(import_path)
            if hasattr(module, "TOOL_SPEC"):
                return module

        # Should not reach here if registry resolution and native path checks didn't match
        raise ToolError(
            f"Tool '{import_path}' not found. Use short ID or full path for native tools."
        )

    except Exception as e:
        raise ToolError(f"Failed to load tool '{import_path}': {e}") from e

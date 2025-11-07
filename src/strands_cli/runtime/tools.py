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

from strands_cli.capability import ALLOWED_PYTHON_CALLABLES


class ToolError(Exception):
    """Raised when tool initialization or execution fails."""

    pass


def load_python_callable(import_path: str) -> Any:
    """Load a Python tool from an import path.

    Handles two types of tools based on Strands patterns:
    1. @tool decorated functions: Returns the decorated function object
    2. Module-based tools: Returns the module itself (has TOOL_SPEC)

    Security: Only loads from the ALLOWED_PYTHON_CALLABLES allowlist and native
    tools registry to prevent arbitrary code execution.

    Supports multiple path formats:
    - Native short ID: "python_exec" (resolved via registry)
    - Native full path: "strands_cli.tools.python_exec"
    - Old format: "strands_tools.http_request" (infers function name)
    - New format: "strands_tools.http_request.http_request" (explicit)

    Args:
        import_path: Dotted import path, short ID, or legacy format

    Returns:
        Either a decorated function tool or a module-based tool object

    Raises:
        ToolError: If tool is not in allowlist, cannot be loaded, or is invalid
    """
    # Import registry here to avoid circular imports
    from strands_cli.tools import get_registry

    registry = get_registry()
    # Combine hardcoded allowlist (strands_tools.*) with native tools from registry
    allowed = ALLOWED_PYTHON_CALLABLES | registry.get_allowlist()

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

        # Handle legacy strands_tools.* paths
        # Normalize old format to new format for consistent handling
        # Old: "strands_tools.http_request" -> New: "strands_tools.http_request.http_request"
        if import_path.count(".") == 1:  # Old format (module.submodule)
            # Extract the function name from the last part of the path
            func_name = import_path.split(".")[-1]
            module_path = import_path
        else:  # New format (module.submodule.function)
            module_path, func_name = import_path.rsplit(".", 1)

        module = importlib.import_module(module_path)

        # Check if this is a module-based tool (has TOOL_SPEC)
        # According to Strands docs, module-based tools should pass the module itself
        if hasattr(module, "TOOL_SPEC"):
            # Module-based tool: return the module, not the function
            # This fixes the "unrecognized tool specification" warning
            return module

        # Otherwise, get the callable (should be @tool decorated)
        callable_obj = getattr(module, func_name)
        if not callable(callable_obj):
            raise ToolError(f"'{import_path}' is not callable")

        return callable_obj

    except Exception as e:
        raise ToolError(f"Failed to load tool '{import_path}': {e}") from e

"""Python code execution tool (Strands SDK module-based pattern).

Execute Python code safely with restricted builtins and stdout capture.
MVP implementation - production version should add proper sandboxing.
"""

import io
from contextlib import redirect_stdout
from typing import Any

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "python_exec",
    "description": "Execute Python code and return results (MVP - simple version with restricted builtins)",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {
                    "type": "integer",
                    "default": 5,
                    "description": "Timeout in seconds (not enforced in MVP)",
                },
            },
            "required": ["code"],
        }
    },
}


def python_exec(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Execute Python code with restricted builtins and stdout capture.

    MVP Implementation:
    - Uses exec() with restricted globals
    - Captures stdout via StringIO
    - Returns result or error

    Security Limitations (MVP):
    - No proper sandboxing (subprocess/docker)
    - No resource limits (memory, CPU)
    - No timeout enforcement
    - Limited builtin allowlist
    - No AST parsing for dangerous operations

    Production version should address all security limitations.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    code = tool_input.get("code", "")

    if not code:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No code provided"}],
        }

    try:
        # Capture stdout
        output = io.StringIO()

        with redirect_stdout(output):
            # Restricted globals - only safe builtins
            # Production: expand this list carefully or use AST validation
            restricted_globals = {
                "__builtins__": {
                    # Type constructors
                    "int": int,
                    "float": float,
                    "str": str,
                    "bool": bool,
                    "list": list,
                    "dict": dict,
                    "tuple": tuple,
                    "set": set,
                    # Utilities
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "abs": abs,
                    "round": round,
                    "sorted": sorted,
                    "reversed": reversed,
                    # Output
                    "print": print,
                    # Type checking
                    "isinstance": isinstance,
                    "type": type,
                }
            }

            # Execute code with restricted environment
            exec(code, restricted_globals)

        # Get captured output
        result = output.getvalue()

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result if result else "Code executed successfully (no output)"}],
        }

    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Execution failed: {type(e).__name__}: {e!s}"}],
        }

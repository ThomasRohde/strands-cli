"""File read tool (Strands SDK module-based pattern).

Read file contents from the filesystem with proper error handling.
"""

from pathlib import Path
from typing import Any

TOOL_SPEC = {
    "name": "file_read",
    "description": "Read the contents of a file from the filesystem",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (relative or absolute)",
                },
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                    "description": "File encoding (default: utf-8)",
                },
            },
            "required": ["path"],
        }
    },
}


def file_read(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Read file contents from filesystem.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional context (ignored)

    Returns:
        Tool result with file contents or error message
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    file_path = tool_input.get("path", "")
    encoding = tool_input.get("encoding", "utf-8")

    if not file_path:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: 'path' parameter is required"}],
        }

    try:
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: File not found: {file_path}"}],
            }

        if not path.is_file():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: Path is not a file: {file_path}"}],
            }

        contents = path.read_text(encoding=encoding)

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": contents}],
        }

    except UnicodeDecodeError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {"text": f"Error: Failed to decode file with encoding '{encoding}': {e}"}
            ],
        }
    except PermissionError:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Permission denied reading file: {file_path}"}],
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error reading file: {e}"}],
        }

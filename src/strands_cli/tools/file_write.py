"""File write tool (Strands SDK module-based pattern).

Write contents to a file on the filesystem with proper error handling.
"""

from pathlib import Path
from typing import Any

TOOL_SPEC = {
    "name": "file_write",
    "description": "Write contents to a file on the filesystem",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (relative or absolute)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                    "description": "File encoding (default: utf-8)",
                },
                "create_dirs": {
                    "type": "boolean",
                    "default": False,
                    "description": "Create parent directories if they don't exist (default: false)",
                },
            },
            "required": ["path", "content"],
        }
    },
}


def file_write(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Write content to a file on the filesystem.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional context (ignored)

    Returns:
        Tool result with success message or error message
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    file_path = tool_input.get("path", "")
    content = tool_input.get("content")
    encoding = tool_input.get("encoding", "utf-8")
    create_dirs = tool_input.get("create_dirs", False)

    if not file_path:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: 'path' parameter is required"}],
        }

    if content is None:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: 'content' parameter is required"}],
        }

    try:
        path = Path(file_path).expanduser().resolve()

        if path.is_dir():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: Path is a directory, not a file: {file_path}"}],
            }

        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.parent.exists():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Parent directory does not exist: {path.parent}. "
                        "Set 'create_dirs' to true to create it automatically."
                    }
                ],
            }

        path.write_text(content, encoding=encoding)

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": f"Successfully wrote {len(content)} characters to {file_path}"}],
        }

    except PermissionError:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Permission denied writing to file: {file_path}"}],
        }
    except UnicodeEncodeError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {"text": f"Error: Failed to encode content with encoding '{encoding}': {e}"}
            ],
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error writing file: {e}"}],
        }

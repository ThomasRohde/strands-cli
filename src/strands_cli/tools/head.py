"""JIT head tool - read first N lines from file.

Pure Python implementation using pathlib for cross-platform support.
Useful for reading file headers, metadata, or previewing file contents.
"""

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "head",
    "description": "Read the first N lines from a file. "
    "Useful for previewing file contents or reading headers without loading entire files. "
    "Cross-platform pure Python implementation.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file to read (relative or absolute)",
                },
                "lines": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of lines to read from start (default: 10)",
                },
                "bytes_limit": {
                    "type": "integer",
                    "default": 1048576,
                    "description": "Maximum bytes to read (default: 1MB, prevents loading huge files)",
                },
            },
            "required": ["path"],
        }
    },
}


def head(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Read first N lines from a file.

    Cross-platform implementation using pure Python (no subprocess/shell).
    Validates paths and handles encoding errors gracefully.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    path_str = tool_input.get("path", "")
    num_lines = tool_input.get("lines", 10)
    bytes_limit = tool_input.get("bytes_limit", 1048576)  # 1MB default

    # Validate inputs
    if not path_str:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No file path provided"}],
        }

    if num_lines < 1:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Number of lines must be at least 1"}],
        }

    try:
        # Validate and resolve path (prevents directory traversal)
        path = Path(path_str).resolve()

        # Check if file exists and is readable
        if not path.exists():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"File not found: {path}"}],
            }

        if not path.is_file():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Path is not a file: {path}"}],
            }

        # Check for binary file (first 8KB)
        with open(path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": f"Binary file detected (cannot read as text): {path}"}],
                }

        # Read first N lines with byte limit
        lines_read = []
        bytes_read = 0

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= num_lines:
                        break

                    line_bytes = len(line.encode("utf-8"))
                    if bytes_read + line_bytes > bytes_limit:
                        lines_read.append(
                            f"\n[Truncated: byte limit ({bytes_limit} bytes) reached]"
                        )
                        break

                    lines_read.append(line.rstrip())
                    bytes_read += line_bytes

        except Exception as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Failed to read file: {e}"}],
            }

        if not lines_read:
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"text": f"File is empty: {path}"}],
            }

        # Build output with line numbers
        output_lines = [f"First {len(lines_read)} line(s) from {path}:\n"]

        for i, line in enumerate(lines_read, start=1):
            if line.startswith("\n[Truncated:"):
                output_lines.append(line)
            else:
                output_lines.append(f"{i:4d} | {line}")

        result_text = "\n".join(output_lines)

        logger.info(
            "head_read_completed",
            file=str(path),
            lines_requested=num_lines,
            lines_read=len(lines_read),
            bytes_read=bytes_read,
        )

        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": result_text}]}

    except Exception as e:
        logger.error("head_read_failed", error=str(e), path=path_str)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Read failed: {type(e).__name__}: {e}"}],
        }

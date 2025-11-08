"""JIT tail tool - read last N lines from file.

Pure Python implementation using deque for efficient tail reading.
Useful for reading log file endings or recent entries without loading entire files.
"""

from collections import deque
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "tail",
    "description": "Read the last N lines from a file. "
                   "Useful for reading recent log entries or file endings without loading entire files. "
                   "Cross-platform pure Python implementation.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file to read (relative or absolute)"
                },
                "lines": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of lines to read from end (default: 10)"
                },
                "bytes_limit": {
                    "type": "integer",
                    "default": 10485760,
                    "description": "Maximum bytes to read (default: 10MB, for efficient tail on large files)"
                }
            },
            "required": ["path"]
        }
    }
}


def tail(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:  # noqa: C901
    """Read last N lines from a file.

    Cross-platform implementation using deque for efficiency.
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
    bytes_limit = tool_input.get("bytes_limit", 10485760)  # 10MB default

    # Validate inputs
    if not path_str:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No file path provided"}]
        }

    if num_lines < 1:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Number of lines must be at least 1"}]
        }

    try:
        # Validate and resolve path (prevents directory traversal)
        path = Path(path_str).resolve()

        # Check if file exists and is readable
        if not path.exists():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"File not found: {path}"}]
            }

        if not path.is_file():
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Path is not a file: {path}"}]
            }

        # Check for binary file (first 8KB)
        with open(path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": f"Binary file detected (cannot read as text): {path}"}]
                }

        # Read last N lines efficiently using deque
        # Deque automatically limits size, keeping only last N items
        last_lines: deque[str] = deque(maxlen=num_lines)
        bytes_read = 0
        truncated = False

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_bytes = len(line.encode("utf-8"))

                    # Check byte limit
                    if bytes_read + line_bytes > bytes_limit:
                        truncated = True
                        break

                    last_lines.append(line.rstrip())
                    bytes_read += line_bytes

        except Exception as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Failed to read file: {e}"}]
            }

        if not last_lines:
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"text": f"File is empty: {path}"}]
            }

        # Build output with line numbers (relative to end)
        output_lines = [f"Last {len(last_lines)} line(s) from {path}:\n"]

        if truncated:
            output_lines.append(f"[Note: File truncated at {bytes_limit} bytes limit]\n")

        # Calculate starting line number (approximate if truncated)
        start_num = 1 if truncated else max(1, len(last_lines))

        for i, line in enumerate(last_lines, start=start_num):
            output_lines.append(f"{i:4d} | {line}")

        result_text = "\n".join(output_lines)

        logger.info(
            "tail_read_completed",
            file=str(path),
            lines_requested=num_lines,
            lines_read=len(last_lines),
            bytes_read=bytes_read,
            truncated=truncated
        )

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result_text}]
        }

    except Exception as e:
        logger.error("tail_read_failed", error=str(e), path=path_str)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Read failed: {type(e).__name__}: {e}"}]
        }

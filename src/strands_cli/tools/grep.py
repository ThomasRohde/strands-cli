"""JIT grep tool - cross-platform pattern search with context lines.

Pure Python implementation using regex and pathlib for portability.
No shell dependencies - works on Windows, macOS, and Linux.
"""

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "grep",
    "description": "Search for regex pattern in a file and return matching lines with context. "
    "Useful for finding specific content without loading entire files. "
    "Cross-platform pure Python implementation.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Path to file to search (relative or absolute)",
                },
                "context_lines": {
                    "type": "integer",
                    "default": 3,
                    "description": "Number of context lines before and after each match (default: 3)",
                },
                "ignore_case": {
                    "type": "boolean",
                    "default": False,
                    "description": "Perform case-insensitive search (default: false)",
                },
                "max_matches": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum number of matches to return (default: 100)",
                },
            },
            "required": ["pattern", "path"],
        }
    },
}


def _validate_inputs(tool_use_id: str, pattern_str: str, path_str: str) -> dict[str, Any] | None:
    """Validate tool inputs and return error dict if invalid."""
    if not pattern_str:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No search pattern provided"}],
        }

    if not path_str:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No file path provided"}],
        }

    return None


def _validate_file_path(tool_use_id: str, path: Path) -> dict[str, Any] | None:
    """Validate file path and return error dict if invalid."""
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

    return None


def _check_binary_file(tool_use_id: str, path: Path) -> dict[str, Any] | None:
    """Check if file is binary and return error dict if true."""
    with open(path, "rb") as f:
        chunk = f.read(8192)
        if b"\x00" in chunk:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Binary file detected (cannot search): {path}"}],
            }
    return None


def _build_output(
    matches: list[int],
    lines: list[str],
    path: Path,
    pattern_str: str,
    context_lines: int,
    max_matches: int,
) -> str:
    """Build formatted output with context lines."""
    if not matches:
        return f"No matches found for pattern '{pattern_str}' in {path}"

    output_lines = [f"Found {len(matches)} match(es) in {path}:\n"]

    for match_line in matches:
        # Calculate context window
        start_line = max(1, match_line - context_lines)
        end_line = min(len(lines), match_line + context_lines)

        output_lines.append(f"\n--- Match at line {match_line} ---")

        for i in range(start_line - 1, end_line):
            line_number = i + 1
            prefix = ">" if line_number == match_line else " "
            output_lines.append(f"{prefix} {line_number:4d} | {lines[i].rstrip()}")

    if len(matches) >= max_matches:
        output_lines.append(f"\n(Showing first {max_matches} matches only)")

    return "\n".join(output_lines)


def grep(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:  # noqa: C901
    """Search for pattern in file with context lines.

    Cross-platform implementation using pure Python (no subprocess/shell).
    Validates paths to prevent directory traversal and handles encoding errors.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    pattern_str = tool_input.get("pattern", "")
    path_str = tool_input.get("path", "")
    context_lines = tool_input.get("context_lines", 3)
    ignore_case = tool_input.get("ignore_case", False)
    max_matches = tool_input.get("max_matches", 100)

    # Validate inputs
    error = _validate_inputs(tool_use_id, pattern_str, path_str)
    if error:
        return error

    try:
        # Validate and resolve path (prevents directory traversal)
        path = Path(path_str).resolve()

        # Validate file exists and is a file
        error = _validate_file_path(tool_use_id, path)
        if error:
            return error

        # Check for binary file
        error = _check_binary_file(tool_use_id, path)
        if error:
            return error

        # Compile regex pattern
        flags = re.IGNORECASE if ignore_case else 0
        try:
            pattern = re.compile(pattern_str, flags)
        except re.error as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Invalid regex pattern: {e}"}],
            }

        # Read file and search
        # NOTE: Currently loads entire file into memory. For very large files (>100MB),
        # consider streaming implementation. See docs/STREAMING_DESIGN.md for design.
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Failed to read file: {e}"}],
            }

        # Find matching lines
        matches = []
        for line_num, line in enumerate(lines, start=1):
            if pattern.search(line):
                matches.append(line_num)
                if len(matches) >= max_matches:
                    break

        # Build output
        result_text = _build_output(matches, lines, path, pattern_str, context_lines, max_matches)

        if matches:
            logger.info(
                "grep_search_completed",
                pattern=pattern_str,
                file=str(path),
                matches=len(matches),
                context_lines=context_lines,
            )

        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": result_text}]}

    except Exception as e:
        logger.error("grep_search_failed", error=str(e), pattern=pattern_str, path=path_str)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Search failed: {type(e).__name__}: {e}"}],
        }

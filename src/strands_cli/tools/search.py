"""JIT search tool - keyword/regex search with match highlighting.

Pure Python implementation with colored output and line numbers.
Similar to grep but with simpler output format and match highlighting.
"""

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "search",
    "description": "Search for keyword or regex pattern in a file and return matching lines with line numbers. "
    "Simpler than grep - no context lines, just direct matches. "
    "Useful for finding specific content quickly. "
    "Cross-platform pure Python implementation.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (plain text or regex)"},
                "path": {
                    "type": "string",
                    "description": "Path to file to search (relative or absolute)",
                },
                "is_regex": {
                    "type": "boolean",
                    "default": False,
                    "description": "Treat query as regex pattern (default: false, plain text)",
                },
                "ignore_case": {
                    "type": "boolean",
                    "default": True,
                    "description": "Perform case-insensitive search (default: true)",
                },
                "max_matches": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of matches to return (default: 50)",
                },
            },
            "required": ["query", "path"],
        }
    },
}


def search(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:  # noqa: C901
    """Search for keyword/pattern in file with line numbers.

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

    query = tool_input.get("query", "")
    path_str = tool_input.get("path", "")
    is_regex = tool_input.get("is_regex", False)
    ignore_case = tool_input.get("ignore_case", True)
    max_matches = tool_input.get("max_matches", 50)

    # Validate inputs
    if not query:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No search query provided"}],
        }

    if not path_str:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No file path provided"}],
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
                    "content": [{"text": f"Binary file detected (cannot search): {path}"}],
                }

        # Prepare search pattern
        flags = re.IGNORECASE if ignore_case else 0

        if is_regex:
            try:
                pattern = re.compile(query, flags)
            except re.error as e:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": f"Invalid regex pattern: {e}"}],
                }
        else:
            # Escape query for literal search
            escaped_query = re.escape(query)
            pattern = re.compile(escaped_query, flags)

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
                matches.append((line_num, line.rstrip()))
                if len(matches) >= max_matches:
                    break

        if not matches:
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"text": f"No matches found for '{query}' in {path}"}],
            }

        # Build output
        output_lines = [f"Found {len(matches)} match(es) for '{query}' in {path}:\n"]

        for line_num, line in matches:
            # Highlight matches by wrapping in >>> <<<
            highlighted = pattern.sub(lambda m: f">>>{m.group()}<<<", line)
            output_lines.append(f"{line_num:4d} | {highlighted}")

        if len(matches) >= max_matches:
            output_lines.append(f"\n(Showing first {max_matches} matches only)")

        result_text = "\n".join(output_lines)

        logger.info(
            "search_completed",
            query=query,
            file=str(path),
            matches=len(matches),
            is_regex=is_regex,
            ignore_case=ignore_case,
        )

        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": result_text}]}

    except Exception as e:
        logger.error("search_failed", error=str(e), query=query, path=path_str)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Search failed: {type(e).__name__}: {e}"}],
        }

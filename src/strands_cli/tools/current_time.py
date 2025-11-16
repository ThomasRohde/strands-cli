"""Current time tool (Strands SDK module-based pattern).

Get the current time in various formats and timezones.
"""

from datetime import UTC, datetime
from typing import Any

TOOL_SPEC = {
    "name": "current_time",
    "description": "Get the current date and time in various formats and timezones",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["iso", "unix", "human"],
                    "default": "iso",
                    "description": "Output format: 'iso' (ISO 8601), 'unix' (timestamp), 'human' (readable)",
                },
                "timezone": {
                    "type": "string",
                    "enum": ["utc", "local"],
                    "default": "utc",
                    "description": "Timezone: 'utc' or 'local' (default: utc)",
                },
            },
            "required": [],
        }
    },
}


def current_time(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Get the current time in the specified format and timezone.

    Supported formats:
    - iso: ISO 8601 format (e.g., 2024-01-15T10:30:45Z)
    - unix: Unix timestamp (e.g., 1705318245)
    - human: Human-readable format (e.g., January 15, 2024 at 10:30:45 AM)

    Supported timezones:
    - utc: Coordinated Universal Time
    - local: System local time

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional context (ignored)

    Returns:
        Tool result with formatted time or error message
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    format_type = tool_input.get("format", "iso")
    tz_type = tool_input.get("timezone", "utc")

    try:
        if tz_type == "utc":
            now = datetime.now(UTC)
        elif tz_type == "local":
            now = datetime.now()
        else:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: Invalid timezone '{tz_type}'. Use 'utc' or 'local'."}],
            }

        if format_type == "iso":
            time_str = now.isoformat()
        elif format_type == "unix":
            time_str = str(int(now.timestamp()))
        elif format_type == "human":
            time_str = now.strftime("%B %d, %Y at %I:%M:%S %p")
            if tz_type == "utc":
                time_str += " UTC"
        else:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Invalid format '{format_type}'. Use 'iso', 'unix', or 'human'."
                    }
                ],
            }

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": time_str}],
        }

    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error getting current time: {e}"}],
        }

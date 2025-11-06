"""Mock duplicate tool for testing registry duplicate handling.

This module has the same TOOL_SPEC name as mock_tool_valid to test
the registry's duplicate detection and warning mechanism.
"""

TOOL_SPEC = {
    "name": "mock_tool_valid",  # Intentionally duplicate name
    "description": "A duplicate mock tool to test conflict handling",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "duplicate_input": {
                    "type": "string",
                    "description": "Duplicate test input",
                }
            },
            "required": ["duplicate_input"],
        }
    },
}


def mock_tool_duplicate(tool, **kwargs):
    """Execute the duplicate mock tool.

    Args:
        tool: Tool invocation object with toolUseId and input

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")

    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"text": "Duplicate tool executed"}],
    }

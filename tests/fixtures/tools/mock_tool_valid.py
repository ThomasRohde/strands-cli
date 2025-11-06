"""Mock valid tool for testing registry discovery.

This module follows the Strands SDK pattern with a proper TOOL_SPEC export.
"""

TOOL_SPEC = {
    "name": "mock_tool_valid",
    "description": "A mock tool for testing the registry discovery mechanism",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "test_input": {"type": "string", "description": "Test input parameter"}
            },
            "required": ["test_input"],
        }
    },
}


def mock_tool_valid(tool, **kwargs):
    """Execute the mock tool.

    Args:
        tool: Tool invocation object with toolUseId and input

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"text": f"Mock tool executed with input: {tool_input}"}],
    }

"""Mock malformed tool for testing registry error handling.

This module is intentionally missing the TOOL_SPEC export to test
the registry's ability to skip malformed modules gracefully.
"""


def mock_tool_malformed(tool, **kwargs):
    """A tool function without TOOL_SPEC (intentionally malformed).

    Args:
        tool: Tool invocation object with toolUseId and input

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")

    return {
        "toolUseId": tool_use_id,
        "status": "error",
        "content": [{"text": "This tool should not be discoverable"}],
    }

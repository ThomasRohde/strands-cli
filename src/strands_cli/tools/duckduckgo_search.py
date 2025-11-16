"""DuckDuckGo search tool (Strands SDK module-based pattern).

Search DuckDuckGo for text results and news with automatic backend fallback.
Uses ddgs library with support for multiple search backends (auto, google, brave, bing).
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Import DDGS at module level for easier testing
try:
    from ddgs import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    DDGS = None  # type: ignore

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "duckduckgo_search",
    "description": "Search DuckDuckGo for text results or news. Supports automatic backend fallback for resilience.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["text", "news"],
                    "default": "text",
                    "description": "Type of search to perform (text or news)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results to return (1-50)",
                    "minimum": 1,
                    "maximum": 50,
                },
                "region": {
                    "type": "string",
                    "default": "us-en",
                    "description": "Region/language code (e.g., us-en, uk-en, cn-zh)",
                },
                "safesearch": {
                    "type": "string",
                    "enum": ["on", "moderate", "off"],
                    "default": "moderate",
                    "description": "SafeSearch filter level",
                },
                "timelimit": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Time limit for results (d=day, w=week, m=month, y=year)",
                },
            },
            "required": ["query"],
        }
    },
}


def duckduckgo_search(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Execute DuckDuckGo search and return structured JSON results.

    Supports text and news searches with automatic backend fallback for resilience.
    Uses ddgs library which rotates through multiple backends (Google, Brave, Bing, DuckDuckGo)
    when rate limited.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and JSON content containing search results
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    # Extract and validate parameters
    query = tool_input.get("query", "").strip()
    if not query:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No search query provided"}],
        }

    search_type = tool_input.get("search_type", "text")
    max_results = tool_input.get("max_results", 10)
    region = tool_input.get("region", "us-en")
    safesearch = tool_input.get("safesearch", "moderate")
    timelimit = tool_input.get("timelimit")

    # Validate max_results range
    if not isinstance(max_results, int) or max_results < 1 or max_results > 50:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"max_results must be between 1 and 50, got: {max_results}"}],
        }

    # Check if DDGS is available
    if not DDGS_AVAILABLE:
        logger.error("ddgs library not available")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "ddgs library not installed. Install with: pip install ddgs"}],
        }

    try:
        logger.info(
            "DuckDuckGo search request",
            query=query,
            search_type=search_type,
            max_results=max_results,
            region=region,
        )

        # Initialize DDGS with automatic backend fallback
        with DDGS() as ddgs:
            # Prepare common parameters (query is positional, rest are kwargs)
            search_params = {
                "region": region,
                "safesearch": safesearch,
                "max_results": max_results,
                "backend": "auto",  # Automatic backend rotation for resilience
            }

            # Add timelimit if specified
            if timelimit:
                search_params["timelimit"] = timelimit

            # Execute search based on type (query is first positional argument)
            if search_type == "text":
                results = list(ddgs.text(query, **search_params))
            elif search_type == "news":
                results = list(ddgs.news(query, **search_params))
            else:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": f"Invalid search_type: {search_type}"}],
                }

        logger.info(
            "DuckDuckGo search completed",
            query=query,
            search_type=search_type,
            result_count=len(results),
        )

        # Return structured JSON results
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [
                {
                    "json": {
                        "query": query,
                        "search_type": search_type,
                        "result_count": len(results),
                        "results": results,
                    }
                }
            ],
        }

    except Exception as e:
        # Catch all exceptions including RatelimitException, TimeoutException, etc.
        error_type = type(e).__name__
        logger.error(
            "DuckDuckGo search failed",
            error_type=error_type,
            error=str(e),
            query=query,
            search_type=search_type,
        )

        # Provide helpful error messages
        if "ratelimit" in str(e).lower():
            error_msg = f"Rate limit exceeded: {e}. The search will automatically retry with different backends."
        elif "timeout" in str(e).lower():
            error_msg = f"Search timed out: {e}. Try reducing max_results or simplifying the query."
        else:
            error_msg = f"Search failed ({error_type}): {e}"

        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_msg}],
        }

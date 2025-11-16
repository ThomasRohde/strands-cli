"""Tavily AI-powered search tool (Strands SDK module-based pattern).

Search the web using Tavily's AI-optimized search with relevance scoring.
Requires TAVILY_API_KEY environment variable. Get API key at https://app.tavily.com
(1000 free API credits monthly, no credit card required).
"""

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Import TavilyClient at module level for easier testing
try:
    from tavily import TavilyClient  # type: ignore[import-untyped]

    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    TavilyClient = None

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "tavily_search",
    "description": "Search the web using Tavily AI-powered search. Returns optimized results with relevance scores and optional AI-generated answers. Requires TAVILY_API_KEY environment variable.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of results to return (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                },
                "include_answer": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include AI-generated answer based on search results",
                },
            },
            "required": ["query"],
        }
    },
}


def tavily_search(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Execute Tavily search and return structured JSON results.

    Supports AI-optimized web search with relevance scoring and optional answer generation.
    Requires TAVILY_API_KEY environment variable. Get API key at https://app.tavily.com
    (1000 free API credits monthly, no credit card required).

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

    max_results = tool_input.get("max_results", 5)
    include_answer = tool_input.get("include_answer", False)

    # Validate max_results range
    if not isinstance(max_results, int) or max_results < 1 or max_results > 20:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {"text": f"max_results must be between 1 and 20, got: {max_results}"}
            ],
        }

    # Check if TavilyClient is available
    if not TAVILY_AVAILABLE:
        logger.error("tavily-python library not available")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {"text": "tavily-python library not installed. Install with: pip install tavily-python"}
            ],
        }

    # Check for API key
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logger.error("TAVILY_API_KEY environment variable not set")
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [
                {
                    "text": "TAVILY_API_KEY environment variable not set. Get your free API key at https://app.tavily.com (1000 free API credits monthly)."
                }
            ],
        }

    try:
        logger.info(
            "Tavily search request",
            query=query,
            max_results=max_results,
            include_answer=include_answer,
        )

        # Initialize Tavily client
        client = TavilyClient(api_key=api_key)

        # Execute search
        response = client.search(
            query=query,
            max_results=max_results,
            include_answer=include_answer,
        )

        logger.info(
            "Tavily search completed",
            query=query,
            result_count=len(response.get("results", [])),
            has_answer=include_answer and "answer" in response,
        )

        # Return raw Tavily response in JSON format
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"json": response}],
        }

    except Exception as e:
        # Catch all exceptions including API errors, rate limits, etc.
        error_type = type(e).__name__
        logger.error(
            "Tavily search failed",
            error_type=error_type,
            error=str(e),
            query=query,
        )

        # Provide helpful error messages
        error_msg = str(e).lower()
        if "api key" in error_msg or "auth" in error_msg:
            error_text = f"Authentication failed: {e}. Verify your TAVILY_API_KEY is valid."
        elif "rate limit" in error_msg or "quota" in error_msg:
            error_text = f"Rate limit or quota exceeded: {e}. Check your usage at https://app.tavily.com"
        elif "timeout" in error_msg:
            error_text = f"Search timed out: {e}. Try reducing max_results or simplifying the query."
        else:
            error_text = f"Search failed ({error_type}): {e}"

        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_text}],
        }

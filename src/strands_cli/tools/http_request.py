"""HTTP request tool (Strands SDK module-based pattern).

Make HTTP requests with support for GET, POST, PUT, DELETE methods.
MVP implementation with basic functionality.
"""

import json
from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

TOOL_SPEC = {
    "name": "http_request",
    "description": "Make HTTP requests (GET, POST, PUT, DELETE) with optional headers and body",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to make the request to",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                    "description": "HTTP method (default: GET)",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs",
                },
                "body": {
                    "type": "string",
                    "description": "Request body (for POST/PUT)",
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Request timeout in seconds (default: 30)",
                },
            },
            "required": ["url"],
        }
    },
}


def http_request(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Make an HTTP request.

    MVP Implementation:
    - Uses httpx library for HTTP requests
    - Supports GET, POST, PUT, DELETE methods
    - Basic header support
    - Simple timeout handling

    Security Limitations (MVP):
    - No SSRF protection
    - No URL validation/allowlisting
    - No rate limiting
    - No certificate validation controls

    Production version should add comprehensive security controls.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional context (ignored)

    Returns:
        Tool result with response or error message
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    if httpx is None:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: httpx library not installed. Install with: pip install httpx"}],
        }

    url = tool_input.get("url", "")
    method = tool_input.get("method", "GET").upper()
    headers = tool_input.get("headers", {})
    body = tool_input.get("body")
    timeout = tool_input.get("timeout", 30)

    if not url:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: 'url' parameter is required"}],
        }

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Error: Invalid URL format: {url}"}],
            }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Failed to parse URL: {e}"}],
        }

    if method not in ["GET", "POST", "PUT", "DELETE"]:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Unsupported HTTP method: {method}"}],
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, headers=headers, content=body)
            elif method == "PUT":
                response = client.put(url, headers=headers, content=body)
            elif method == "DELETE":
                response = client.delete(url, headers=headers)

        result_text = f"Status: {response.status_code}\n\n"
        result_text += f"Headers:\n{json.dumps(dict(response.headers), indent=2)}\n\n"
        result_text += f"Body:\n{response.text}"

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result_text}],
        }

    except httpx.TimeoutException:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Request timed out after {timeout} seconds"}],
        }
    except httpx.ConnectError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: Connection failed: {e}"}],
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error making HTTP request: {e}"}],
        }

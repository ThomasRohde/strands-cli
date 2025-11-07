"""HTTP executor factory for creating native tool modules.

Dynamically creates Strands SDK-compatible module-based tools from
HttpExecutor configurations. Each HTTP executor becomes a proper native
tool with TOOL_SPEC and matching callable function.

This integrates HTTP executors into the native tools framework rather
than treating them as a separate tool type.
"""

import os
import re
from types import ModuleType
from typing import Any

import httpx
import structlog

from strands_cli.types import HttpExecutor, Spec

logger = structlog.get_logger(__name__)


class HttpExecutorToolError(Exception):
    """Raised when HTTP executor tool execution fails."""

    pass


def _resolve_secret_placeholders(text: str, spec: Spec | None) -> str:
    """Resolve ${VARIABLE} placeholders with environment variable values.

    Resolves secret references in the format ${VARIABLE_NAME} by:
    1. Looking up the variable in spec.env.secrets to get the env var key
    2. Reading the environment variable value
    3. Replacing the placeholder with the value

    Args:
        text: String that may contain ${VAR} placeholders
        spec: Workflow spec containing env.secrets configuration (optional)

    Returns:
        String with all placeholders resolved to environment variable values

    Example:
        >>> spec.env.secrets = [Secret(name="GITHUB_TOKEN", source="env", key="MY_GITHUB_PAT")]
        >>> os.environ["MY_GITHUB_PAT"] = "ghp_secret123"
        >>> _resolve_secret_placeholders("Bearer ${GITHUB_TOKEN}", spec)
        'Bearer ghp_secret123'
    """
    if not spec or not spec.env or not spec.env.secrets:
        return text

    # Build mapping from secret name to environment variable key
    secret_map: dict[str, str] = {}
    for secret in spec.env.secrets:
        secret_map[secret.name or secret.key] = secret.key

    # Replace all ${VAR} placeholders
    def replace_placeholder(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in secret_map:
            env_key = secret_map[var_name]
            return os.environ.get(env_key, "")
        # If not in secrets, try direct env lookup as fallback
        return os.environ.get(var_name, "")

    return re.sub(r"\$\{([^}]+)\}", replace_placeholder, text)


def create_http_executor_tool(config: HttpExecutor, spec: Spec | None = None) -> ModuleType:
    """Create a native tool module for an HTTP executor configuration.

    Generates a proper Strands SDK module-based tool with:
    - Module-level TOOL_SPEC dictionary
    - Function matching TOOL_SPEC["name"]
    - Proper tool invocation signature: tool(dict, **kwargs) -> dict

    The created tool maintains an httpx.Client for efficient connection pooling
    and follows the same error handling patterns as other native tools.

    Args:
        config: HTTP executor configuration (id, base_url, headers, timeout)
        spec: Optional workflow spec for resolving secret placeholders in headers

    Returns:
        Module object compatible with Strands SDK and native tools registry

    Example:
        >>> from strands_cli.types import HttpExecutor
        >>> config = HttpExecutor(
        ...     id="github_api",
        ...     base_url="https://api.github.com",
        ...     headers={"Authorization": "Bearer ${GITHUB_TOKEN}"},
        ... )
        >>> tool_module = create_http_executor_tool(config, spec)
        >>> # Headers will have ${GITHUB_TOKEN} resolved from environment
    """
    # Resolve secret placeholders in headers
    resolved_headers = {}
    if config.headers:
        for key, value in config.headers.items():
            resolved_headers[key] = _resolve_secret_placeholders(value, spec)

    # Create HTTP client for this executor
    client = httpx.Client(
        base_url=config.base_url,
        timeout=config.timeout,
        headers=resolved_headers,
    )

    # Define TOOL_SPEC for this HTTP executor
    tool_spec = {
        "name": config.id,
        "description": f"HTTP executor for {config.base_url}",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                        "default": "GET",
                    },
                    "path": {
                        "type": "string",
                        "description": "Request path (relative to base URL)",
                    },
                    "json_data": {
                        "type": "object",
                        "description": "Optional JSON body for POST/PUT requests",
                    },
                    "headers_override": {
                        "type": "object",
                        "description": "Optional headers to merge with base headers",
                    },
                },
                "required": ["path"],
            }
        },
    }

    # Define tool function (matches TOOL_SPEC name)
    def tool_function(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Execute HTTP request via configured client.

        Args:
            tool: Tool invocation with toolUseId and input
            **kwargs: Additional arguments (unused)

        Returns:
            ToolResult dict with status and content
        """
        tool_use_id = tool.get("toolUseId", "")
        tool_input = tool.get("input", {})

        try:
            # Extract parameters
            method = tool_input.get("method", "GET")
            path = tool_input.get("path", "")
            json_data = tool_input.get("json_data")
            headers_override = tool_input.get("headers_override")

            if not path:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": "Missing required 'path' parameter"}],
                }

            # Merge headers (use resolved headers, not config.headers)
            # Note: The httpx.Client already has resolved_headers as defaults,
            # but we need to support headers_override functionality
            request_headers = None
            if headers_override:
                # Merge default resolved headers with overrides
                request_headers = {**resolved_headers, **headers_override}

            # Execute request (client will use default headers if request_headers is None)
            response = client.request(
                method=method.upper(),
                url=path,
                json=json_data,
                headers=request_headers,
            )

            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [
                    {
                        "json": {
                            "status": response.status_code,
                            "headers": dict(response.headers),
                            "body": response.text,
                        }
                    }
                ],
            }

        except httpx.TimeoutException as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"HTTP request timed out: {e}"}],
            }
        except httpx.HTTPError as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"HTTP request failed: {e}"}],
            }
        except Exception as e:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Unexpected error: {e}"}],
            }

    # Create module with proper attributes for Strands SDK compatibility
    module_name = config.id  # Use config.id as module name (e.g., "gh")
    module = ModuleType(module_name)
    module.__doc__ = f"HTTP executor tool for {config.base_url}"
    module.__name__ = module_name
    module.__package__ = "strands_cli.tools"
    # Set __file__ to indicate this is a dynamically generated tool module
    module.__file__ = f"<dynamic:http_executor_{config.id}>"

    # Set TOOL_SPEC
    module.TOOL_SPEC = tool_spec

    # Set function name to match TOOL_SPEC name and module name
    tool_function.__name__ = config.id
    tool_function.__doc__ = f"HTTP executor for {config.base_url}"

    # Set the function as a module attribute with the same name
    setattr(module, config.id, tool_function)

    # Store client and config for cleanup
    module._http_client = client
    module._http_config = config

    return module


def close_http_executor_tool(module: ModuleType) -> None:
    """Close HTTP client for an HTTP executor tool module.

    Should be called during cleanup to release sockets and connections.

    Args:
        module: HTTP executor tool module created by create_http_executor_tool
    """
    from contextlib import suppress

    if hasattr(module, "_http_client"):
        with suppress(Exception):
            module._http_client.close()

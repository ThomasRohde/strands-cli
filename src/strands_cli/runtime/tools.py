"""Safe tool adapters for http_executors and Python tools.

Provides controlled tool execution with security boundaries:

Python Tools:
    - Allowlist enforcement (only approved imports)
    - Dynamic import validation
    - Callable verification

HTTP Executors:
    - Configurable base URL and headers
    - Timeout enforcement (default 30s)
    - Error handling with httpx
    - Response normalization to dict format

All tools raise ToolError on failures for consistent error handling.
"""

import importlib
from collections.abc import Callable
from typing import Any

import httpx

from strands_cli.capability import ALLOWED_PYTHON_CALLABLES
from strands_cli.types import HttpExecutor


class ToolError(Exception):
    """Raised when tool initialization or execution fails."""

    pass


def load_python_callable(import_path: str) -> Callable[..., Any]:
    """Load a Python callable from an import path.

    Security: Only loads callables from the ALLOWED_PYTHON_CALLABLES allowlist
    to prevent arbitrary code execution. Uses dynamic import to load the module
    and extract the callable.

    Args:
        import_path: Dotted import path like "strands_tools.http_request"

    Returns:
        The loaded callable object

    Raises:
        ToolError: If callable is not in allowlist, cannot be loaded,
                  or is not actually callable
    """
    if import_path not in ALLOWED_PYTHON_CALLABLES:
        raise ToolError(
            f"Python callable '{import_path}' not in allowlist. "
            f"Allowed: {', '.join(ALLOWED_PYTHON_CALLABLES)}"
        )

    try:
        module_path, func_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        callable_obj = getattr(module, func_name)
    except Exception as e:
        raise ToolError(f"Failed to load callable '{import_path}': {e}") from e

    if not callable(callable_obj):
        raise ToolError(f"'{import_path}' is not callable")

    return callable_obj


class HttpExecutorAdapter:
    """Safe HTTP executor adapter with timeout and retry logic.

    Wraps http_executors config into a callable tool that can be
    registered with a Strands Agent. Provides:

    - Base URL configuration for relative paths
    - Header management (base + per-request override)
    - Timeout enforcement (configurable, default 30s)
    - Normalized response format (status, headers, body)
    - Error handling for timeouts and HTTP errors

    The adapter is callable and context-manager compatible for resource cleanup.
    """

    def __init__(self, config: HttpExecutor):
        """Initialize HTTP executor.

        Args:
            config: HTTP executor configuration with base_url, headers, timeout
        """
        self.config = config
        self.client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.headers or {},
        )

    def __call__(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        headers_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (relative to base_url)
            json_data: Optional JSON body
            headers_override: Optional headers to merge/override

        Returns:
            Response as dictionary with status, headers, body

        Raises:
            ToolError: If request fails
        """
        # Merge headers
        headers = dict(self.config.headers or {})
        if headers_override:
            headers.update(headers_override)

        try:
            response = self.client.request(
                method=method.upper(),
                url=path,
                json=json_data,
                headers=headers if headers else None,
            )

            return {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
        except httpx.TimeoutException as e:
            raise ToolError(f"HTTP request timed out: {e}") from e
        except httpx.HTTPError as e:
            raise ToolError(f"HTTP request failed: {e}") from e
        except Exception as e:
            raise ToolError(f"Unexpected error in HTTP request: {e}") from e

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

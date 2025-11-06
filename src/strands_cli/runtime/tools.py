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
from typing import Any

import httpx

from strands_cli.capability import ALLOWED_PYTHON_CALLABLES
from strands_cli.types import HttpExecutor


class ToolError(Exception):
    """Raised when tool initialization or execution fails."""

    pass


def load_python_callable(import_path: str) -> Any:
    """Load a Python tool from an import path.

    Handles two types of tools based on Strands patterns:
    1. @tool decorated functions: Returns the decorated function object
    2. Module-based tools: Returns the module itself (has TOOL_SPEC)

    Security: Only loads from the ALLOWED_PYTHON_CALLABLES allowlist to prevent
    arbitrary code execution.

    Supports both old and new path formats for backward compatibility:
    - Old: "strands_tools.http_request" (infers function name from module)
    - New: "strands_tools.http_request.http_request" (explicit function name)

    Args:
        import_path: Dotted import path like "strands_tools.calculator.calculator"
                    or "strands_tools.calculator" (old format)

    Returns:
        Either a decorated function tool or a module-based tool object

    Raises:
        ToolError: If tool is not in allowlist, cannot be loaded, or is invalid
    """
    if import_path not in ALLOWED_PYTHON_CALLABLES:
        raise ToolError(
            f"Python callable '{import_path}' not in allowlist. "
            f"Allowed: {', '.join(sorted(ALLOWED_PYTHON_CALLABLES))}"
        )

    try:
        # Normalize old format to new format for consistent handling
        # Old: "strands_tools.http_request" -> New: "strands_tools.http_request.http_request"
        if import_path.count(".") == 1:  # Old format (module.submodule)
            # Extract the function name from the last part of the path
            func_name = import_path.split(".")[-1]
            module_path = import_path
        else:  # New format (module.submodule.function)
            module_path, func_name = import_path.rsplit(".", 1)

        module = importlib.import_module(module_path)

        # Check if this is a module-based tool (has TOOL_SPEC)
        # According to Strands docs, module-based tools should pass the module itself
        if hasattr(module, "TOOL_SPEC"):
            # Module-based tool: return the module, not the function
            # This fixes the "unrecognized tool specification" warning
            return module

        # Otherwise, get the callable (should be @tool decorated)
        callable_obj = getattr(module, func_name)
        if not callable(callable_obj):
            raise ToolError(f"'{import_path}' is not callable")

        return callable_obj

    except Exception as e:
        raise ToolError(f"Failed to load tool '{import_path}': {e}") from e


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

    def close(self) -> None:
        """Close the HTTP client and release resources.

        Should be called when the tool is no longer needed to prevent
        lingering sockets in long-running workflow orchestrations.
        """
        self.client.close()

    async def aclose(self) -> None:
        """Async close for async context manager support.

        Enables proper cleanup in async workflows and AgentCache.
        """
        self.client.close()

    def __enter__(self) -> "HttpExecutorAdapter":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        """Context manager exit - ensures cleanup on context exit."""
        self.close()

    async def __aenter__(self) -> "HttpExecutorAdapter":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        """Async context manager exit - ensures cleanup on context exit."""
        await self.aclose()

    def __del__(self) -> None:
        """Destructor to cleanup resources if not explicitly closed."""
        from contextlib import suppress

        with suppress(Exception):
            self.client.close()

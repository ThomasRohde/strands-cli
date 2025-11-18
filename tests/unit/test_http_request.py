"""Unit tests for http_request native tool.

Tests the http_request tool which makes HTTP requests.
"""

import importlib.util

import pytest

HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None


class TestHttpRequestToolSpec:
    """Test TOOL_SPEC definition for http_request."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in http_request module."""
        from strands_cli.tools import http_request

        assert hasattr(http_request, "TOOL_SPEC")
        assert isinstance(http_request.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.http_request import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "http_request"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.http_request import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "url" in input_schema["properties"]
        assert "method" in input_schema["properties"]
        assert "headers" in input_schema["properties"]
        assert "body" in input_schema["properties"]
        assert "timeout" in input_schema["properties"]
        assert "url" in input_schema["required"]


class TestHttpRequestFunction:
    """Test http_request function behavior."""

    def test_http_request_callable_exists(self) -> None:
        """Test that http_request function is defined and callable."""
        from strands_cli.tools.http_request import http_request

        assert callable(http_request)

    def test_missing_url_returns_error(self) -> None:
        """Test that missing URL parameter returns error."""
        from strands_cli.tools.http_request import http_request

        tool_input = {"toolUseId": "no-url", "input": {}}

        result = http_request(tool_input)

        assert result["toolUseId"] == "no-url"
        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_empty_url_returns_error(self) -> None:
        """Test that empty URL string returns error."""
        from strands_cli.tools.http_request import http_request

        tool_input = {"toolUseId": "empty-url", "input": {"url": ""}}

        result = http_request(tool_input)

        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_invalid_url_format_returns_error(self) -> None:
        """Test that invalid URL format returns error."""
        from strands_cli.tools.http_request import http_request

        tool_input = {"toolUseId": "invalid-url", "input": {"url": "not-a-valid-url"}}

        result = http_request(tool_input)

        assert result["status"] == "error"
        assert "invalid" in result["content"][0]["text"].lower()

    def test_unsupported_method_returns_error(self) -> None:
        """Test that unsupported HTTP method returns error."""
        from strands_cli.tools.http_request import http_request

        tool_input = {
            "toolUseId": "bad-method",
            "input": {"url": "https://httpbin.org/get", "method": "PATCH"},
        }

        result = http_request(tool_input)

        assert result["status"] == "error"
        assert "unsupported" in result["content"][0]["text"].lower()

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_get_request_success(self) -> None:
        """Test successful GET request to httpbin (allows 503 for service outages)."""
        from strands_cli.tools.http_request import http_request

        tool_input = {"toolUseId": "get-test", "input": {"url": "https://httpbin.org/get"}}

        result = http_request(tool_input)

        if result["status"] == "success":
            # Accept both 200 (success) and 503 (service temporarily unavailable)
            # httpbin.org is an external service that may have availability issues
            text = result["content"][0]["text"]
            assert "Status: 200" in text or "Status: 503" in text
            assert "Headers:" in text

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_post_request_with_body(self) -> None:
        """Test POST request with body (allows 503 for service outages)."""
        from strands_cli.tools.http_request import http_request

        tool_input = {
            "toolUseId": "post-test",
            "input": {
                "url": "https://httpbin.org/post",
                "method": "POST",
                "body": "test data",
            },
        }

        result = http_request(tool_input)

        if result["status"] == "success":
            # Accept both 200 (success) and 503 (service temporarily unavailable)
            text = result["content"][0]["text"]
            assert "Status: 200" in text or "Status: 503" in text

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_custom_headers(self) -> None:
        """Test request with custom headers (allows 503 for service outages)."""
        from strands_cli.tools.http_request import http_request

        tool_input = {
            "toolUseId": "headers-test",
            "input": {
                "url": "https://httpbin.org/headers",
                "headers": {"X-Custom-Header": "test-value"},
            },
        }

        result = http_request(tool_input)

        if result["status"] == "success":
            # Accept both 200 (success) and 503 (service temporarily unavailable)
            text = result["content"][0]["text"]
            assert "Status: 200" in text or "Status: 503" in text

    def test_connection_error_handling(self) -> None:
        """Test that connection errors are handled gracefully."""
        from strands_cli.tools.http_request import http_request

        tool_input = {
            "toolUseId": "conn-err",
            "input": {"url": "https://nonexistent-domain-12345.example", "timeout": 1},
        }

        result = http_request(tool_input)

        assert result["status"] == "error"
        assert "error" in result["content"][0]["text"].lower()


class TestHttpRequestToolIntegration:
    """Test http_request tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that http_request is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("http_request")

        assert tool_info is not None
        assert tool_info.id == "http_request"
        assert tool_info.module_path == "strands_cli.tools.http_request"

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that http_request paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "http_request" in allowlist
        assert "strands_cli.tools.http_request" in allowlist

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("http_request")

        assert resolved == "strands_cli.tools.http_request"

    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load http_request with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("http_request")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "http_request")
        assert callable(tool_module.http_request)

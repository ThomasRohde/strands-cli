"""Unit tests for the web_fetch native tool."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from pytest_mock import MockerFixture


class TestWebFetchTool:
    """Tests covering the web_fetch tool behavior."""

    def test_tool_spec_schema(self) -> None:
        """Ensure TOOL_SPEC defines the expected schema."""
        from strands_cli.tools.web_fetch import DEFAULT_TIMEOUT, TOOL_SPEC

        assert TOOL_SPEC["name"] == "web_fetch"
        assert "description" in TOOL_SPEC

        schema = TOOL_SPEC["inputSchema"]["json"]
        assert schema["required"] == ["url"]
        properties = schema["properties"]
        assert properties["mode"]["enum"] == ["html", "markdown"]
        assert properties["mode"]["default"] == "html"
        assert properties["timeout"]["default"] == DEFAULT_TIMEOUT
        assert properties["timeout"]["minimum"] == 1
        assert properties["include_raw_html"]["type"] == "boolean"
        assert properties["headers"]["type"] == "object"

    def test_html_mode_success(self, mocker: MockerFixture) -> None:
        """Return HTML response without extra processing."""
        from strands_cli.tools import web_fetch

        response = httpx.Response(
            200,
            text="<html><body>Hello</body></html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("GET", "https://example.com"),
        )
        mock_fetch = mocker.patch("strands_cli.tools.web_fetch._fetch_with_retry", return_value=response)

        tool = {"toolUseId": "wf-1", "input": {"url": "https://example.com"}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "success"
        payload = result["content"][0]["json"]
        assert payload["status"] == 200
        assert payload["url"] == "https://example.com"
        assert payload["body"].strip().startswith("<html>")
        assert "headers" in payload
        headers = {k.lower(): v for k, v in payload["headers"].items()}
        assert headers["content-type"] == "text/html"
        mock_fetch.assert_called_once()
        called_headers = mock_fetch.call_args[0][1]
        assert "User-Agent" in called_headers

    def test_custom_headers_overwrite_defaults(self, mocker: MockerFixture) -> None:
        """Custom headers should override defaults in fetch call."""
        from strands_cli.tools import web_fetch

        response = httpx.Response(
            200,
            text="<html/>",
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        mock_fetch = mocker.patch("strands_cli.tools.web_fetch._fetch_with_retry", return_value=response)

        tool = {
            "toolUseId": "wf-headers",
            "input": {
                "url": "https://example.com",
                "headers": {"User-Agent": "custom-agent", "X-Test": "1"},
            },
        }

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "success"
        headers_used = mock_fetch.call_args[0][1]
        assert headers_used["User-Agent"] == "custom-agent"
        assert headers_used["X-Test"] == "1"

    def test_markdown_mode_with_raw_html(self, mocker: MockerFixture) -> None:
        """Return markdown payload and optional raw HTML."""
        from strands_cli.tools import web_fetch

        response = httpx.Response(
            200,
            text="<html><body><article>Example</article></body></html>",
            headers={},
            request=httpx.Request("GET", "https://example.com/article"),
        )
        mocker.patch("strands_cli.tools.web_fetch._fetch_with_retry", return_value=response)
        mocker.patch(
            "strands_cli.tools.web_fetch._extract_main_content",
            return_value="<article>Example</article>",
        )
        mocker.patch(
            "strands_cli.tools.web_fetch._convert_to_markdown",
            return_value="# Example",
        )

        tool = {
            "toolUseId": "wf-md",
            "input": {
                "url": "https://example.com/article",
                "mode": "markdown",
                "include_raw_html": True,
            },
        }

        result = web_fetch.web_fetch(tool)

        payload = result["content"][0]["json"]
        assert payload["markdown"] == "# Example"
        assert payload["raw_html"] == response.text
        assert payload["status"] == 200

    def test_markdown_mode_requires_bool_raw_flag(self) -> None:
        """include_raw_html must be boolean when provided."""
        from strands_cli.tools import web_fetch

        tool = {
            "toolUseId": "wf-md-raw-invalid",
            "input": {"url": "https://example.com", "mode": "markdown", "include_raw_html": "yes"},
        }

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "include_raw_html must be a boolean" in result["content"][0]["text"]

    def test_markdown_mode_requires_markdownify(self, mocker: MockerFixture) -> None:
        """If markdownify is unavailable, markdown mode errors."""
        from strands_cli.tools import web_fetch

        mocker.patch("strands_cli.tools.web_fetch.MARKDOWNIFY_AVAILABLE", False)
        mocker.patch("strands_cli.tools.web_fetch.html_to_markdown", None)

        tool = {"toolUseId": "wf-md-missing", "input": {"url": "https://example.com", "mode": "markdown"}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "markdownify dependency is not available" in result["content"][0]["text"]

    def test_invalid_url_error(self) -> None:
        """Only http/https URLS are allowed."""
        from strands_cli.tools import web_fetch

        tool = {"toolUseId": "wf-invalid", "input": {"url": "ftp://example.com"}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "Invalid URL" in result["content"][0]["text"]

    def test_timeout_validation(self) -> None:
        """timeout must be an integer > 0."""
        from strands_cli.tools import web_fetch

        tool = {"toolUseId": "wf-timeout", "input": {"url": "https://example.com", "timeout": "10"}}
        result = web_fetch.web_fetch(tool)
        assert result["status"] == "error"

        tool["input"]["timeout"] = 0
        result = web_fetch.web_fetch(tool)
        assert result["status"] == "error"
        assert "greater than zero" in result["content"][0]["text"]

    def test_headers_validation(self) -> None:
        """headers must be an object."""
        from strands_cli.tools import web_fetch

        tool = {"toolUseId": "wf-headers-invalid", "input": {"url": "https://example.com", "headers": []}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "headers must be an object" in result["content"][0]["text"]

    def test_invalid_mode(self) -> None:
        """Unsupported modes should error."""
        from strands_cli.tools import web_fetch

        tool = {"toolUseId": "wf-mode", "input": {"url": "https://example.com", "mode": "text"}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "Unsupported mode" in result["content"][0]["text"]

    def test_network_error_surface(self, mocker: MockerFixture) -> None:
        """Network errors from httpx should be returned as tool errors."""
        from strands_cli.tools import web_fetch

        request = httpx.Request("GET", "https://example.com")
        mocker.patch(
            "strands_cli.tools.web_fetch._fetch_with_retry",
            side_effect=httpx.ConnectError("boom", request=request),
        )

        tool = {"toolUseId": "wf-error", "input": {"url": "https://example.com"}}

        result = web_fetch.web_fetch(tool)

        assert result["status"] == "error"
        assert "Network error" in result["content"][0]["text"]

    def test_non_200_status_preserved(self, mocker: MockerFixture) -> None:
        """Non-200 responses should still return body content."""
        from strands_cli.tools import web_fetch

        response = httpx.Response(
            404,
            text="<html><body>Not Found</body></html>",
            request=httpx.Request("GET", "https://example.com/missing"),
        )
        mocker.patch("strands_cli.tools.web_fetch._fetch_with_retry", return_value=response)

        tool = {"toolUseId": "wf-404", "input": {"url": "https://example.com/missing"}}

        result = web_fetch.web_fetch(tool)

        payload = result["content"][0]["json"]
        assert payload["status"] == 404
        assert "Not Found" in payload["body"]

    def test_retry_logic_recovers_after_timeout(self, mocker: MockerFixture) -> None:
        """_fetch_with_retry should retry once on timeout errors."""
        from strands_cli.tools.web_fetch import _fetch_with_retry

        url = "https://example.com"
        responses = [
            httpx.ReadTimeout("timeout", request=httpx.Request("GET", url)),
            httpx.Response(200, text="ok", request=httpx.Request("GET", url)),
        ]

        def client_side_effect(*_: object, **__: object) -> MagicMock:
            result = responses.pop(0)
            instance = MagicMock()
            instance.__enter__.return_value = instance
            instance.__exit__.return_value = False
            if isinstance(result, Exception):
                instance.get.side_effect = result
            else:
                instance.get.return_value = result
            return instance

        mock_client = mocker.patch("strands_cli.tools.web_fetch.httpx.Client", side_effect=client_side_effect)

        resp = _fetch_with_retry(url, headers={}, timeout=5)

        assert resp.status_code == 200
        assert mock_client.call_count == 2

    def test_retry_logic_raises_after_failures(self, mocker: MockerFixture) -> None:
        """_fetch_with_retry should raise after exhausting retries."""

        from strands_cli.tools.web_fetch import _fetch_with_retry

        url = "https://example.com"
        request = httpx.Request("GET", url)
        error = httpx.ConnectError("boom", request=request)
        responses = [error, error]

        def client_side_effect(*_: object, **__: object) -> MagicMock:
            instance = MagicMock()
            instance.__enter__.return_value = instance
            instance.__exit__.return_value = False
            instance.get.side_effect = responses.pop(0)
            return instance

        mocker.patch("strands_cli.tools.web_fetch.httpx.Client", side_effect=client_side_effect)

        with pytest.raises(httpx.ConnectError):
            _fetch_with_retry(url, headers={}, timeout=5)

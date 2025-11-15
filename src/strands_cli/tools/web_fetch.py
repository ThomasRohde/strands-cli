"""Web fetch tool for retrieving static HTML or markdown content."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata as importlib_metadata
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

try:
    import trafilatura

    TRAFILATURA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via dependency injection in tests
    trafilatura = None  # type: ignore[assignment]
    TRAFILATURA_AVAILABLE = False

try:
    from markdownify import markdownify as html_to_markdown  # type: ignore[import-untyped]

    MARKDOWNIFY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via dependency injection in tests
    html_to_markdown = None
    MARKDOWNIFY_AVAILABLE = False

DEFAULT_TIMEOUT = 10
MAX_RETRIES = 2

try:
    PACKAGE_VERSION = importlib_metadata.version("strands-cli")
except importlib_metadata.PackageNotFoundError:  # pragma: no cover - dev installs only
    PACKAGE_VERSION = "dev"

DEFAULT_USER_AGENT = f"strands-cli-web-fetch/{PACKAGE_VERSION}"

TOOL_SPEC = {
    "name": "web_fetch",
    "description": "Fetch static web pages over HTTP/HTTPS and optionally convert the main content to markdown.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "HTTP or HTTPS URL to fetch.",
                },
                "timeout": {
                    "type": "integer",
                    "default": DEFAULT_TIMEOUT,
                    "minimum": 1,
                    "description": "Request timeout in seconds.",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers to include with the request.",
                    "additionalProperties": {"type": "string"},
                },
                "mode": {
                    "type": "string",
                    "enum": ["html", "markdown"],
                    "default": "html",
                    "description": "Response processing mode.",
                },
                "include_raw_html": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include the raw HTML when returning markdown output.",
                },
            },
            "required": ["url"],
        }
    },
}


def web_fetch(tool: dict[str, Any], **_: Any) -> dict[str, Any]:
    """Fetch a web page and return HTML or markdown content."""

    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input") or {}

    url = str(tool_input.get("url", "")).strip()
    if not url:
        return _error_result(tool_use_id, "No URL provided.")

    if not _is_valid_url(url):
        return _error_result(tool_use_id, f"Invalid URL: {url}. Only http and https are allowed.")

    mode = str(tool_input.get("mode", "html")).lower()
    if mode not in {"html", "markdown"}:
        return _error_result(tool_use_id, f"Unsupported mode '{mode}'. Use 'html' or 'markdown'.")

    timeout_input = tool_input.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout_input, int):
        return _error_result(tool_use_id, "timeout must be an integer value in seconds.")
    if timeout_input <= 0:
        return _error_result(tool_use_id, "timeout must be greater than zero.")

    headers_input = tool_input.get("headers")
    if headers_input is not None and not isinstance(headers_input, dict):
        return _error_result(tool_use_id, "headers must be an object/dictionary of string values.")

    try:
        custom_headers = _normalize_header_values(headers_input)
    except ValueError as exc:
        return _error_result(tool_use_id, str(exc))
    request_headers = _build_request_headers(custom_headers)

    include_raw_html = False
    if mode == "markdown":
        include_raw_input = tool_input.get("include_raw_html", False)
        if not isinstance(include_raw_input, bool):
            return _error_result(tool_use_id, "include_raw_html must be a boolean value.")
        include_raw_html = include_raw_input
        if not MARKDOWNIFY_AVAILABLE or html_to_markdown is None:
            return _error_result(tool_use_id, "markdownify dependency is not available.")

    try:
        response = _fetch_with_retry(url, request_headers, timeout_input)
    except httpx.TimeoutException as exc:
        logger.warning("Web fetch timed out", url=url, timeout=timeout_input, error=str(exc))
        return _error_result(tool_use_id, f"Request to {url} timed out after {timeout_input} seconds.")
    except httpx.RequestError as exc:
        logger.warning("Web fetch request error", url=url, error=str(exc))
        return _error_result(tool_use_id, f"Network error while fetching {url}: {exc}")

    logger.info(
        "Web fetch completed",
        url=url,
        status_code=response.status_code,
        final_url=str(response.url),
        mode=mode,
    )

    body_text = response.text

    if mode == "html":
        payload = {
            "status": response.status_code,
            "url": str(response.url),
            "headers": dict(response.headers),
            "body": body_text,
        }
        return _success_result(tool_use_id, payload)

    extracted_html = _extract_main_content(body_text, str(response.url))
    markdown_output = _convert_to_markdown(extracted_html)

    payload = {
        "status": response.status_code,
        "url": str(response.url),
        "markdown": markdown_output,
    }

    if include_raw_html:
        payload["raw_html"] = body_text

    return _success_result(tool_use_id, payload)


def _fetch_with_retry(
    url: str,
    headers: Mapping[str, str],
    timeout: int,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
                response = client.get(url)
            return response
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning("Web fetch timeout", url=url, timeout=timeout, attempt=attempt)
            if attempt == MAX_RETRIES:
                raise
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning("Web fetch transient error", url=url, attempt=attempt, error=str(exc))
            if attempt == MAX_RETRIES:
                raise

    assert last_error is not None
    raise last_error


def _extract_main_content(html: str, url: str | None) -> str:
    if not TRAFILATURA_AVAILABLE or trafilatura is None:
        return html

    extracted: str | None = None
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_images=False,
            favor_precision=True,
            output_format="html",
        )
    except Exception as exc:  # pragma: no cover - library level errors
        logger.warning("Trafilatura extraction failed", url=url, error=str(exc))
        extracted = None

    if not extracted:
        try:
            extracted = trafilatura.extract(html, url=url)
        except Exception as exc:  # pragma: no cover - library level errors
            logger.warning("Trafilatura fallback extraction failed", url=url, error=str(exc))
            extracted = None

    return extracted or html


def _convert_to_markdown(html: str) -> str:
    if not MARKDOWNIFY_AVAILABLE or html_to_markdown is None:
        raise RuntimeError("markdownify dependency missing")

    markdown: str = html_to_markdown(
        html,
        heading_style="ATX",
        default_title=True,
        strip=["script", "style"],
    )
    return markdown.strip()


def _is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_header_values(headers: dict[str, Any] | None) -> dict[str, str]:
    if not headers:
        return {}
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str):
            raise ValueError("Header keys must be strings.")
        normalized[key] = str(value)
    return normalized


def _build_request_headers(custom_headers: Mapping[str, str] | None) -> dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if custom_headers:
        headers.update(custom_headers)
    return headers


def _success_result(tool_use_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"json": payload}],
    }


def _error_result(tool_use_id: str, message: str) -> dict[str, Any]:
    return {
        "toolUseId": tool_use_id,
        "status": "error",
        "content": [{"text": message}],
    }

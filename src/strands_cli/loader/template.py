"""Template rendering with Jinja2 and safety controls.

Provides secure template rendering for prompts and artifacts using Jinja2.
Safety controls prevent common issues:

1. StrictUndefined: Raises error on undefined variables (no silent failures)
2. Control character stripping: Removes potentially harmful control chars
3. Unicode normalization: Ensures consistent text representation
4. Token budget enforcement: Optional output length limiting
5. No file system access: Templates are strings only (no file loader)

Custom Filters (Phase 1):
    - truncate(n): Truncate text to n characters with ellipsis
    - tojson: Serialize Python object to JSON string

Used for:
    - Rendering agent prompts with input variables
    - Generating output artifacts with {{ last_response }}
    - Injecting runtime context into system prompts
    - Multi-step context: {{ steps[0].response }}, {{ tasks.<id>.response }}
"""

import json
import os
import re
import unicodedata
from typing import Any

import structlog
from jinja2 import BaseLoader, StrictUndefined, TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

try:
    from jinja2.sandbox import SecurityError  # type: ignore[attr-defined]
except ImportError:
    # Fallback for older jinja2 versions
    SecurityError = Exception  # type: ignore[misc,assignment]

logger = structlog.get_logger(__name__)


class TemplateError(Exception):
    """Raised when template rendering fails."""

    pass


class TemplateSecurityError(TemplateError):
    """Raised when template attempts unsafe operations."""

    pass


# Control characters to strip (except newline, tab, carriage return)
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]")


def _strip_control_chars(text: str) -> str:
    """Remove control characters from text for safety.

    Removes potentially harmful control characters while preserving
    essential whitespace (newline, tab, carriage return). Also normalizes
    unicode to NFC form for consistent text representation.

    Args:
        text: Input text that may contain control characters

    Returns:
        Sanitized text with control characters removed and unicode normalized
    """
    # Remove control characters
    text = _CONTROL_CHARS_PATTERN.sub("", text)

    # Normalize unicode (NFC form)
    text = unicodedata.normalize("NFC", text)

    return text


def _filter_truncate(text: str, length: int = 100) -> str:
    """Truncate text to specified length with ellipsis.

    Custom Jinja2 filter for token budget control in templates.

    Args:
        text: Text to truncate
        length: Maximum length (default 100)

    Returns:
        Truncated text with "..." appended if truncated
    """
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def _filter_tojson(obj: Any) -> str:
    """Serialize object to JSON string.

    Custom Jinja2 filter for structured data in templates.

    Args:
        obj: Python object to serialize

    Returns:
        JSON string representation
    """
    return json.dumps(obj, ensure_ascii=False)


def _filter_title(text: str) -> str:
    """Convert text to title case.

    Custom Jinja2 filter for formatting text.

    Args:
        text: Text to convert

    Returns:
        Text with title case formatting
    """
    return text.title()


def _filter_regex_search(text: str, pattern: str) -> str:
    """Search for a regex pattern in text and return the first match.

    Custom Jinja2 filter for extracting data from text with regex.

    Args:
        text: Text to search in
        pattern: Regex pattern to search for (should include capture group)

    Returns:
        First captured group match, or empty string if no match
    """
    match = re.search(pattern, text, re.IGNORECASE)
    if match and match.groups():
        return match.group(1)
    return ""


def _create_sandboxed_environment() -> SandboxedEnvironment:
    """Create a sandboxed Jinja2 environment with approved filters."""
    env = SandboxedEnvironment(
        loader=BaseLoader(),
        autoescape=False,
        undefined=StrictUndefined,
    )
    env.filters.clear()
    env.filters["truncate"] = _filter_truncate
    env.filters["tojson"] = _filter_tojson
    env.filters["title"] = _filter_title
    env.filters["regex_search"] = _filter_regex_search
    env.globals.clear()
    return env


def _render_with_environment(
    env: SandboxedEnvironment,
    template_str: str,
    variables: dict[str, Any],
    max_output_chars: int | None = None,
) -> str:
    """Render using a provided sandboxed environment with safety controls."""
    debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"

    if debug:
        template_preview = template_str[:200] if len(template_str) > 200 else template_str
        logger.debug(
            "template_render_start",
            template_preview=template_preview,
            template_length=len(template_str),
            variable_keys=list(variables.keys()),
            variable_count=len(variables),
        )

    try:
        template = env.from_string(template_str)
    except TemplateSyntaxError as e:
        logger.warning(
            "template_syntax_error",
            violation_type="invalid_syntax",
            error=str(e),
            template_preview=template_str[:100],
        )
        raise TemplateError(f"Invalid template syntax: {e}") from e

    try:
        rendered = template.render(**variables)

        if debug:
            rendered_preview = rendered[:200] if len(rendered) > 200 else rendered
            logger.debug(
                "template_rendered",
                rendered_preview=rendered_preview,
                rendered_length=len(rendered),
                was_truncated=max_output_chars is not None and len(rendered) > max_output_chars,
            )
    except UndefinedError as e:
        raise TemplateError(f"Undefined variable in template: {e}") from e
    except SecurityError as e:
        logger.warning(
            "template_security_violation",
            violation_type="unsafe_operation",
            error=str(e),
            template_preview=template_str[:100],
        )
        raise TemplateSecurityError(f"Template attempted unsafe operation: {e}") from e
    except Exception as e:
        raise TemplateError(f"Template rendering failed: {e}") from e

    rendered = _strip_control_chars(rendered)

    if max_output_chars is not None and len(rendered) > max_output_chars:
        rendered = rendered[:max_output_chars]

    return rendered


def render_template(
    template_str: str,
    variables: dict[str, Any],
    max_output_chars: int | None = None,
) -> str:
    """Render a Jinja2 template with safety controls."""
    env = _create_sandboxed_environment()
    return _render_with_environment(env, template_str, variables, max_output_chars)


class TemplateRenderer:
    """Reusable template renderer with consistent configuration.

    This is a lightweight wrapper for consistency and future extensibility
    (e.g., adding custom filters, caching compiled templates, etc.).
    """

    def __init__(self, max_output_chars: int | None = None):
        """Initialize renderer.

        Args:
            max_output_chars: Optional max output length for all renders
        """
        self.max_output_chars = max_output_chars
        self.env = _create_sandboxed_environment()

    def render(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a template.

        Args:
            template_str: Template string
            variables: Variables to inject

        Returns:
            Rendered string

        Raises:
            TemplateError: If rendering fails
        """
        return _render_with_environment(self.env, template_str, variables, self.max_output_chars)

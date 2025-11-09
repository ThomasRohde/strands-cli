"""PII redaction engine for OpenTelemetry spans.

Provides pattern-based redaction of sensitive data in span attributes,
including emails, credit cards, SSNs, phone numbers, and API keys.
"""

import json
import re
from re import Pattern
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RedactionEngine:
    """Engine for detecting and redacting PII in span attributes."""

    # PII detection patterns
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.IGNORECASE
    )
    CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    PHONE_PATTERN = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
    # API keys: 20+ alphanumeric/dash/underscore chars (heuristic)
    API_KEY_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{20,}\b")

    # Redaction placeholder
    REDACTED_PLACEHOLDER = "***REDACTED***"

    def __init__(self, custom_patterns: list[str] | None = None) -> None:
        """Initialize redaction engine.

        Args:
            custom_patterns: Optional list of regex patterns for additional PII types.
        """
        self.patterns: list[Pattern[str]] = [
            self.EMAIL_PATTERN,
            self.CREDIT_CARD_PATTERN,
            self.SSN_PATTERN,
            self.PHONE_PATTERN,
            self.API_KEY_PATTERN,
        ]

        # Add custom patterns if provided
        if custom_patterns:
            for pattern_str in custom_patterns:
                try:
                    self.patterns.append(re.compile(pattern_str))
                    logger.debug("redaction.custom_pattern_added", pattern=pattern_str)
                except re.error as e:
                    logger.warning(
                        "redaction.invalid_custom_pattern",
                        pattern=pattern_str,
                        error=str(e),
                    )

        self.redaction_count = 0

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if attribute key suggests sensitive data.

        Args:
            key: Attribute key name.

        Returns:
            True if key name suggests sensitive data (API keys, tokens, secrets, etc.).
        """
        key_lower = key.lower()
        sensitive_terms = ["key", "token", "secret", "password", "credential"]
        return any(term in key_lower for term in sensitive_terms)

    def redact_value(self, value: Any, is_sensitive_context: bool = True) -> Any:
        """Redact PII from a value of any type.

        Args:
            value: Value to redact (str, dict, list, or primitive).
            is_sensitive_context: If True (default), apply all patterns including API key.
                                  If False, skip API key pattern (for non-sensitive attributes).

        Returns:
            Redacted value with same structure.
        """
        if isinstance(value, str):
            return self._redact_string(value, is_sensitive_context)
        elif isinstance(value, dict):
            return self._redact_dict(value, is_sensitive_context)
        elif isinstance(value, list):
            return [self.redact_value(item, is_sensitive_context) for item in value]
        else:
            # Primitives (int, float, bool, None) pass through
            return value

    def _redact_string(self, text: str, is_sensitive_context: bool = True) -> str:
        """Apply PII patterns to a string with context awareness.

        Args:
            text: String to redact.
            is_sensitive_context: If True (default), apply all patterns including API key.
                                  If False, skip API key pattern for non-sensitive attributes.

        Returns:
            Redacted string with PII replaced.
        """
        original = text

        # Apply patterns based on context
        if is_sensitive_context:
            # Sensitive context: apply ALL patterns including API key
            for pattern in self.patterns:
                text = pattern.sub(self.REDACTED_PLACEHOLDER, text)
        else:
            # Non-sensitive context: apply all patterns EXCEPT API key
            for pattern in self.patterns:
                if pattern is not self.API_KEY_PATTERN:
                    text = pattern.sub(self.REDACTED_PLACEHOLDER, text)

        # Track if redaction occurred
        if text != original:
            self.redaction_count += 1

        return text

    def _redact_dict(self, data: dict[str, Any], is_sensitive_context: bool = True) -> dict[str, Any]:
        """Recursively redact all values in a dictionary.

        Args:
            data: Dictionary to redact.
            is_sensitive_context: If True (default), apply all patterns including API key.
                                  If False, skip API key pattern for non-sensitive attributes.

        Returns:
            New dictionary with redacted values.
        """
        result = {}
        for key, value in data.items():
            # Check if this specific nested key is sensitive
            nested_is_sensitive = is_sensitive_context or self._is_sensitive_key(key)
            result[key] = self.redact_value(value, nested_is_sensitive)
        return result

    def redact_span_attributes(
        self,
        attributes: dict[str, Any],
        redact_tool_inputs: bool = False,
        redact_tool_outputs: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Redact PII from span attributes based on configuration.

        Args:
            attributes: Span attributes dictionary.
            redact_tool_inputs: Whether to redact tool.input.* attributes.
            redact_tool_outputs: Whether to redact tool.output.* attributes.

        Returns:
            Tuple of (redacted_attributes, was_redacted).
        """
        redacted_attrs = {}
        initial_count = self.redaction_count

        for key, value in attributes.items():
            # Check if key suggests sensitive data
            is_sensitive_context = self._is_sensitive_key(key)

            # Check if this attribute should be redacted based on config
            should_redact = False

            if (
                (redact_tool_inputs and key.startswith("tool.input."))
                or (redact_tool_outputs and key.startswith("tool.output."))
                or isinstance(value, str)
            ):
                should_redact = True

            if should_redact:
                redacted_attrs[key] = self.redact_value(value, is_sensitive_context)
            else:
                redacted_attrs[key] = value

        # Check if any redactions occurred
        was_redacted = self.redaction_count > initial_count

        # Add redaction metadata if PII was found
        if was_redacted:
            redacted_attrs["redacted"] = True

        return redacted_attrs, was_redacted

    def get_redaction_count(self) -> int:
        """Get total number of redactions performed.

        Returns:
            Count of redacted values.
        """
        return self.redaction_count

    def reset_count(self) -> None:
        """Reset redaction counter."""
        self.redaction_count = 0


def redact_json_string(json_str: str, engine: RedactionEngine | None = None) -> str:
    """Redact PII from a JSON string.

    Parses JSON, redacts values, and re-serializes.

    Args:
        json_str: JSON string to redact.
        engine: Optional RedactionEngine instance (creates new if None).

    Returns:
        Redacted JSON string.

    Raises:
        ValueError: If json_str is not valid JSON.
    """
    if engine is None:
        engine = RedactionEngine()

    try:
        data = json.loads(json_str)
        redacted = engine.redact_value(data)
        return json.dumps(redacted)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

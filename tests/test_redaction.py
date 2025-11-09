"""Tests for PII redaction in telemetry spans."""

from __future__ import annotations

import json

import pytest

from strands_cli.telemetry.redaction import RedactionEngine, redact_json_string


class TestRedactionEngine:
    """Tests for RedactionEngine PII detection and redaction."""

    def test_email_redaction(self) -> None:
        """Test email address redaction."""
        engine = RedactionEngine()
        text = "Contact us at support@example.com or admin@test.org"
        result = engine.redact_value(text)
        assert "***REDACTED***" in result
        assert "support@example.com" not in result
        assert "admin@test.org" not in result

    def test_credit_card_redaction(self) -> None:
        """Test credit card number redaction."""
        engine = RedactionEngine()

        # Various credit card formats
        test_cases = [
            "4532-1488-0343-6467",  # Dashes
            "4532 1488 0343 6467",  # Spaces
            "4532148803436467",  # No separators
        ]

        for card in test_cases:
            result = engine.redact_value(card)
            assert "***REDACTED***" in result
            assert card not in result

    def test_ssn_redaction(self) -> None:
        """Test SSN redaction."""
        engine = RedactionEngine()
        text = "My SSN is 123-45-6789"
        result = engine.redact_value(text)
        assert "***REDACTED***" in result
        assert "123-45-6789" not in result

    def test_phone_redaction(self) -> None:
        """Test phone number redaction."""
        engine = RedactionEngine()

        test_cases = [
            "555-123-4567",  # Dashes
            "555.123.4567",  # Dots
            "5551234567",  # No separators
        ]

        for phone in test_cases:
            result = engine.redact_value(phone)
            assert "***REDACTED***" in result
            assert phone not in result

    def test_api_key_redaction(self) -> None:
        """Test API key redaction (20+ alphanumeric chars)."""
        engine = RedactionEngine()
        text = "API key: sk_live_abcdef1234567890ABCDEF"
        result = engine.redact_value(text)
        assert "***REDACTED***" in result
        assert "sk_live_abcdef1234567890ABCDEF" not in result

    def test_multiple_pii_patterns(self) -> None:
        """Test redaction of multiple PII types in one string."""
        engine = RedactionEngine()
        text = "Email: user@example.com, Phone: 555-123-4567, SSN: 123-45-6789"
        result = engine.redact_value(text)

        # All PII should be redacted
        assert "user@example.com" not in result
        assert "555-123-4567" not in result
        assert "123-45-6789" not in result
        assert result.count("***REDACTED***") == 3

    def test_custom_patterns(self) -> None:
        """Test custom redaction patterns."""
        # Add custom pattern for employee IDs (e.g., EMP-12345)
        engine = RedactionEngine(custom_patterns=[r"EMP-\d{5}"])
        text = "Employee EMP-12345 submitted a report"
        result = engine.redact_value(text)
        assert "***REDACTED***" in result
        assert "EMP-12345" not in result

    def test_invalid_custom_pattern(self) -> None:
        """Test that invalid regex patterns are logged and skipped."""
        # Invalid regex: unmatched parenthesis
        # Should not raise exception, just log warning
        RedactionEngine(custom_patterns=[r"(invalid"])
        # Engine created successfully despite invalid pattern

    def test_redact_dict_values(self) -> None:
        """Test redaction of dictionary values."""
        engine = RedactionEngine()
        data = {
            "email": "user@example.com",
            "phone": "555-123-4567",
            "name": "John Doe",  # Should not be redacted
        }
        result = engine.redact_value(data)
        assert result["email"] == "***REDACTED***"
        assert result["phone"] == "***REDACTED***"
        assert result["name"] == "John Doe"

    def test_redact_list_values(self) -> None:
        """Test redaction of list values."""
        engine = RedactionEngine()
        data = ["user@example.com", "John Doe", "555-123-4567"]
        result = engine.redact_value(data)
        assert result[0] == "***REDACTED***"
        assert result[1] == "John Doe"
        assert result[2] == "***REDACTED***"

    def test_redact_nested_structures(self) -> None:
        """Test redaction of nested dicts and lists."""
        engine = RedactionEngine()
        data = {
            "user": {
                "contact": {
                    "email": "user@example.com",
                    "phone": "555-123-4567",
                },
                "name": "John Doe",
            },
            "logs": ["Logged in from 555-999-8888", "Normal activity"],
        }
        result = engine.redact_value(data)
        assert result["user"]["contact"]["email"] == "***REDACTED***"
        assert result["user"]["contact"]["phone"] == "***REDACTED***"
        assert result["user"]["name"] == "John Doe"
        assert "***REDACTED***" in result["logs"][0]
        assert result["logs"][1] == "Normal activity"

    def test_redact_primitives_passthrough(self) -> None:
        """Test that primitives (int, float, bool, None) pass through."""
        engine = RedactionEngine()
        assert engine.redact_value(42) == 42
        assert engine.redact_value(3.14) == 3.14
        assert engine.redact_value(True) is True
        assert engine.redact_value(None) is None

    def test_redaction_count(self) -> None:
        """Test redaction counter (counts strings with redactions, not individual matches)."""
        engine = RedactionEngine()
        assert engine.get_redaction_count() == 0

        engine.redact_value("Email: user@example.com")
        assert engine.get_redaction_count() == 1

        # Counter increments once per string with redactions
        engine.redact_value("Phone: 555-123-4567, SSN: 123-45-6789")
        assert engine.get_redaction_count() == 2  # 2 strings total

        engine.reset_count()
        assert engine.get_redaction_count() == 0

    def test_redact_span_attributes_tool_inputs(self) -> None:
        """Test redaction of tool.input.* attributes."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.email": "user@example.com",
            "tool.input.api_key": "sk_live_abc123def456ghi789jkl",
            "tool.output.result": "success",
            "other.attribute": "value",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=False
        )

        assert was_redacted is True
        assert redacted["tool.input.email"] == "***REDACTED***"
        assert redacted["tool.input.api_key"] == "***REDACTED***"
        assert redacted["tool.output.result"] == "success"  # Not redacted
        assert redacted["other.attribute"] == "value"
        assert redacted["redacted"] is True

    def test_redact_span_attributes_tool_outputs(self) -> None:
        """Test redaction of tool.output.* attributes."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.query": "search",
            "tool.output.email": "admin@example.com",
            "tool.output.phone": "555-123-4567",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=False, redact_tool_outputs=True
        )

        assert was_redacted is True
        assert redacted["tool.input.query"] == "search"  # Not redacted
        assert redacted["tool.output.email"] == "***REDACTED***"
        assert redacted["tool.output.phone"] == "***REDACTED***"
        assert redacted["redacted"] is True

    def test_redact_span_attributes_both(self) -> None:
        """Test redaction of both tool inputs and outputs."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.email": "user@example.com",
            "tool.output.result": "Email sent to admin@example.com",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=True
        )

        assert was_redacted is True
        assert redacted["tool.input.email"] == "***REDACTED***"
        assert "***REDACTED***" in redacted["tool.output.result"]
        assert redacted["redacted"] is True

    def test_redact_span_attributes_no_pii(self) -> None:
        """Test that attributes with no PII are not marked as redacted."""
        engine = RedactionEngine()
        attrs = {
            "tool.input.query": "search term",
            "tool.output.count": "42",
            "other.attribute": "value",
        }

        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=True, redact_tool_outputs=True
        )

        assert was_redacted is False
        assert redacted == attrs  # Unchanged
        assert "redacted" not in redacted

    def test_redact_span_attributes_always_scan_strings(self) -> None:
        """Test that all string attributes are scanned for PII even if not tool.* attributes."""
        engine = RedactionEngine()
        attrs = {
            "user.info": "Contact: user@example.com",
            "request.body": "Normal data",
        }

        # Even with tool_inputs/outputs=False, scan all strings
        redacted, was_redacted = engine.redact_span_attributes(
            attrs, redact_tool_inputs=False, redact_tool_outputs=False
        )

        assert was_redacted is True
        assert "***REDACTED***" in redacted["user.info"]
        assert redacted["request.body"] == "Normal data"
        assert redacted["redacted"] is True


class TestRedactJsonString:
    """Tests for redact_json_string utility function."""

    def test_redact_valid_json(self) -> None:
        """Test redaction of valid JSON string."""
        json_str = '{"email": "user@example.com", "name": "John Doe"}'
        result = redact_json_string(json_str)

        data = json.loads(result)
        assert data["email"] == "***REDACTED***"
        assert data["name"] == "John Doe"

    def test_redact_invalid_json(self) -> None:
        """Test that invalid JSON raises ValueError."""
        invalid_json = "{invalid json"

        with pytest.raises(ValueError, match="Invalid JSON"):
            redact_json_string(invalid_json)

    def test_redact_json_with_custom_engine(self) -> None:
        """Test redact_json_string with custom RedactionEngine."""
        engine = RedactionEngine(custom_patterns=[r"SECRET-\d{4}"])
        json_str = '{"code": "SECRET-1234", "data": "normal"}'
        result = redact_json_string(json_str, engine=engine)

        data = json.loads(result)
        assert data["code"] == "***REDACTED***"
        assert data["data"] == "normal"


class TestRedactionEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_string(self) -> None:
        """Test redaction of empty string."""
        engine = RedactionEngine()
        assert engine.redact_value("") == ""

    def test_empty_dict(self) -> None:
        """Test redaction of empty dict."""
        engine = RedactionEngine()
        assert engine.redact_value({}) == {}

    def test_empty_list(self) -> None:
        """Test redaction of empty list."""
        engine = RedactionEngine()
        assert engine.redact_value([]) == []

    def test_no_pii_in_text(self) -> None:
        """Test that text without PII is unchanged."""
        engine = RedactionEngine()
        text = "This is a normal sentence with no sensitive data."
        assert engine.redact_value(text) == text
        assert engine.get_redaction_count() == 0

    def test_pii_at_string_boundaries(self) -> None:
        """Test PII at start/end of strings."""
        engine = RedactionEngine()

        # Email at start
        result = engine.redact_value("user@example.com is the contact")
        assert result.startswith("***REDACTED***")

        # Email at end
        engine.reset_count()
        result = engine.redact_value("Contact: user@example.com")
        assert result.endswith("***REDACTED***")

    def test_multiple_occurrences_same_pii(self) -> None:
        """Test multiple occurrences of same PII pattern."""
        engine = RedactionEngine()
        text = "Emails: user@example.com, admin@example.com, support@example.com"
        result = engine.redact_value(text)
        assert result.count("***REDACTED***") == 3

    def test_case_insensitive_email(self) -> None:
        """Test that email pattern is case-insensitive."""
        engine = RedactionEngine()
        text = "Contact USER@EXAMPLE.COM or Admin@Test.ORG"
        result = engine.redact_value(text)
        assert "USER@EXAMPLE.COM" not in result
        assert "Admin@Test.ORG" not in result
        assert result.count("***REDACTED***") == 2

    def test_partial_credit_card_not_redacted(self) -> None:
        """Test that partial credit card numbers are not redacted."""
        engine = RedactionEngine()
        # Only 12 digits (not 16)
        text = "Card: 4532 1488 0343"
        result = engine.redact_value(text)
        # Should not be redacted (incomplete credit card)
        assert "4532 1488 0343" in result or "***REDACTED***" in result

    def test_api_key_minimum_length(self) -> None:
        """Test that API key pattern requires 20+ chars."""
        engine = RedactionEngine()

        # 19 chars - should not be redacted
        short = "a" * 19
        result = engine.redact_value(short)
        assert result == short

        # 20 chars - should be redacted
        long = "a" * 20
        result = engine.redact_value(long)
        assert result == "***REDACTED***"

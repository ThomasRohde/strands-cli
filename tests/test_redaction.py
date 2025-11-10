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


class TestContextAwareRedaction:
    """Tests for context-aware API key redaction (Phase 2.1)."""

    def test_redaction_preserves_trace_ids(self) -> None:
        """Verify trace_id/span_id not redacted despite 32+ chars."""
        engine = RedactionEngine()

        attrs = {
            "trace_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",  # 32 chars
            "span_id": "1234567890abcdef",  # 16 chars
            "agent.id": "research_specialist_agent_v2",  # 30+ chars
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs)

        # Should NOT redact (no sensitive key context)
        assert redacted["trace_id"] == attrs["trace_id"]
        assert redacted["span_id"] == attrs["span_id"]
        assert redacted["agent.id"] == attrs["agent.id"]
        assert not was_redacted

    def test_redaction_catches_api_keys_with_context(self) -> None:
        """Verify API keys redacted when key name suggests sensitive data."""
        engine = RedactionEngine()

        attrs = {
            "openai_api_key": "sk-proj-1234567890abcdefghij",  # Sensitive key name
            "api_token": "ghp_abcdefghijklmnopqrstuvwxyz",  # GitHub token
            "workflow_id": "1234567890abcdefghij",  # NOT sensitive (no key context)
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs)

        assert "***REDACTED***" in redacted["openai_api_key"]
        assert "***REDACTED***" in redacted["api_token"]
        assert redacted["workflow_id"] == attrs["workflow_id"]  # Preserved
        assert was_redacted

    def test_redaction_sensitive_key_patterns(self) -> None:
        """Test various sensitive key name patterns."""
        engine = RedactionEngine()

        # All these should trigger API key redaction
        sensitive_keys = [
            "api_key",
            "apiKey",
            "API_KEY",
            "bearer_token",
            "oauth_token",
            "secret_key",
            "db_password",
            "credential_value",
        ]

        for key_name in sensitive_keys:
            attrs = {key_name: "a" * 25}  # 25 chars to trigger API key pattern
            redacted, was_redacted = engine.redact_span_attributes(attrs)

            assert redacted[key_name] == "***REDACTED***", f"Failed for key: {key_name}"
            assert was_redacted

    def test_redaction_non_sensitive_long_strings(self) -> None:
        """Test that long strings in non-sensitive keys are preserved."""
        engine = RedactionEngine()

        # Non-sensitive keys with 20+ char values
        attrs = {
            "workflow.name": "advanced_research_workflow_2025",  # 30 chars
            "agent.description": "specialized_code_analyzer",  # 25 chars
            "task.id": "abcdefghijklmnopqrst",  # 20 chars exactly
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs)

        # All should be preserved (no sensitive key context)
        assert redacted["workflow.name"] == attrs["workflow.name"]
        assert redacted["agent.description"] == attrs["agent.description"]
        assert redacted["task.id"] == attrs["task.id"]
        assert not was_redacted

    def test_redaction_mixed_sensitive_and_non_sensitive(self) -> None:
        """Test mixed attributes with both sensitive and non-sensitive keys."""
        engine = RedactionEngine()

        attrs = {
            "trace_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",  # Long, non-sensitive
            "openai_api_key": "sk-1234567890abcdefghij",  # Long, sensitive
            "agent.id": "research_agent_with_long_name",  # Long, non-sensitive
            "github_token": "ghp_abcdefghijklmnopqrstuvwxyz",  # Long, sensitive
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs)

        # Non-sensitive preserved
        assert redacted["trace_id"] == attrs["trace_id"]
        assert redacted["agent.id"] == attrs["agent.id"]

        # Sensitive redacted
        assert "***REDACTED***" in redacted["openai_api_key"]
        assert "***REDACTED***" in redacted["github_token"]

        assert was_redacted


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

        # 20 chars - should be redacted (when in sensitive context)
        long = "a" * 20
        result = engine.redact_value(long)
        assert result == "***REDACTED***"


class TestNestedRedaction:
    """Tests for nested attribute redaction (Phase 2.3)."""

    def test_redaction_nested_tool_inputs(self) -> None:
        """Verify nested tool.input structures are redacted."""
        engine = RedactionEngine()

        attrs = {
            "tool.input.api_config": {
                "api_key": "sk-1234567890abcdefghij",
                "user_email": "test@example.com",
            },
            "tool.input.user_data": {
                "name": "John Doe",
                "phone": "555-123-4567",
            },
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs, redact_tool_inputs=True)

        # Check nested redaction occurred
        assert was_redacted

        # API key should be redacted (sensitive key name)
        api_config = redacted["tool.input.api_config"]
        assert "***REDACTED***" in str(api_config["api_key"])

        # Email should be redacted
        assert "***REDACTED***" in str(api_config["user_email"])

        # Phone should be redacted
        user_data = redacted["tool.input.user_data"]
        assert "***REDACTED***" in str(user_data["phone"])

        # Name should be preserved
        assert user_data["name"] == "John Doe"

    def test_redaction_nested_tool_outputs(self) -> None:
        """Verify nested tool.output structures are redacted."""
        engine = RedactionEngine()

        attrs = {
            "tool.output.results": {
                "count": 42,
                "emails_found": ["admin@example.com", "user@test.org"],
                "api_response": {
                    "token": "sk-abcdefghijklmnopqrst",
                    "status": "success",
                },
            }
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs, redact_tool_outputs=True)

        assert was_redacted

        results = redacted["tool.output.results"]

        # Emails should be redacted
        assert "***REDACTED***" in str(results["emails_found"])

        # API token should be redacted (sensitive key name + long value)
        api_response = results["api_response"]
        assert "***REDACTED***" in str(api_response["token"])

        # Count and status should be preserved
        assert results["count"] == 42
        assert api_response["status"] == "success"

    def test_redaction_deeply_nested_structures(self) -> None:
        """Test redaction of deeply nested (3+ levels) structures."""
        engine = RedactionEngine()

        # Use tool.input prefix to ensure redaction is applied
        attrs = {
            "tool.input.config": {
                "level2": {
                    "level3": {
                        "email": "deep@example.com",
                        "credit_card": "4532-1488-0343-6467",
                        "normal": "data",
                    }
                }
            }
        }

        redacted, was_redacted = engine.redact_span_attributes(attrs, redact_tool_inputs=True)

        assert was_redacted

        level3 = redacted["tool.input.config"]["level2"]["level3"]
        assert "***REDACTED***" in level3["email"]
        assert "***REDACTED***" in level3["credit_card"]
        assert level3["normal"] == "data"

"""Security tests for condition evaluation.

Tests that condition evaluation properly sandboxes Jinja2 templates
and blocks dangerous patterns that could lead to code execution (RCE).
"""

import pytest

from strands_cli.exec.conditions import (
    ConditionEvaluationError,
    evaluate_condition,
    validate_condition_syntax,
)


class TestConditionSecurityPatternBlocking:
    """Test that dangerous patterns are blocked before evaluation."""

    @pytest.mark.parametrize(
        "malicious_expr",
        [
            "{{ ''.__class__ }}",
            "{{ [].__class__.__mro__ }}",
            "{{ {}.__class__.__mro__[1].__subclasses__() }}",
            "{{ ().__class__.__bases__[0].__subclasses__() }}",
            "{{ ''.__class__.__mro__[1].__subclasses__()[104].__init__.__globals__ }}",
            "{{ eval('1+1') }}",
            "{{ exec('import os') }}",
            "{{ compile('x=1', '', 'exec') }}",
            "{{ __import__('os') }}",
            "{{ __builtins__ }}",
            "{{ open('/etc/passwd') }}",
            "{{ file('/etc/passwd') }}",
        ],
    )
    def test_blocks_malicious_patterns(self, malicious_expr: str):
        """Verify dangerous patterns are rejected with security error."""
        with pytest.raises(ConditionEvaluationError, match=r"Security violation|Forbidden pattern"):
            evaluate_condition(malicious_expr, {})

    @pytest.mark.parametrize(
        "malicious_expr",
        [
            "{{ x.__class__ }}",
            "{{ obj.__mro__ }}",
            "{{ thing.__subclasses__() }}",
            "{{ data.__globals__ }}",
            "{{ item.__init__ }}",
            "{{ eval(x) }}",
            "{{ exec(code) }}",
        ],
    )
    def test_blocks_patterns_in_variable_access(self, malicious_expr: str):
        """Verify patterns blocked even when used with variables."""
        context = {"x": "test", "obj": object, "thing": list, "data": {}, "item": {}}
        with pytest.raises(ConditionEvaluationError, match=r"Security violation|Forbidden pattern"):
            evaluate_condition(malicious_expr, context)

    def test_blocks_case_insensitive_patterns(self):
        """Verify pattern blocking is case-insensitive."""
        malicious_variants = [
            "{{ __CLASS__ }}",
            "{{ __Class__ }}",
            "{{ EVAL('x') }}",
            "{{ Exec('x') }}",
        ]
        for expr in malicious_variants:
            with pytest.raises(ConditionEvaluationError, match="Security violation"):
                evaluate_condition(expr, {})


class TestConditionSandboxEnforcement:
    """Test that SandboxedEnvironment blocks dangerous operations."""

    def test_safe_comparison_operations_work(self):
        """Verify safe comparison operations still function."""
        context = {"score": 85, "threshold": 80}

        assert evaluate_condition("{{ score >= threshold }}", context) is True
        assert evaluate_condition("{{ score < 100 }}", context) is True
        assert evaluate_condition("{{ score == 85 }}", context) is True
        assert evaluate_condition("{{ score != 90 }}", context) is True

    def test_safe_boolean_operators_work(self):
        """Verify boolean operators still work in sandbox."""
        context = {"a": 10, "b": 20}

        assert evaluate_condition("{{ a > 5 and b > 15 }}", context) is True
        assert evaluate_condition("{{ a > 5 or b < 10 }}", context) is True
        assert evaluate_condition("{{ not (a > 15) }}", context) is True

    def test_safe_filters_available(self):
        """Verify whitelisted filters are available."""
        context = {"name": "TEST", "value": None, "items": [1, 2, 3]}

        # lower filter
        assert evaluate_condition("{{ name.lower() == 'test' }}", context) is True

        # upper filter
        assert evaluate_condition("{{ 'test'.upper() == 'TEST' }}", context) is True

        # default filter
        assert (
            evaluate_condition("{{ value | default('fallback') == 'fallback' }}", context) is True
        )

        # length filter (via len built-in)
        assert evaluate_condition("{{ items | length == 3 }}", context) is True

    def test_search_filter_available(self):
        """Verify search filter works for pattern matching."""
        context = {"response": "Score: 85", "text": "Hello World"}

        # search filter for regex matching (use | filter syntax, not 'is' test)
        assert evaluate_condition("{{ response | search('Score: \\\\d+') }}", context) is True
        assert evaluate_condition("{{ text | search('World') }}", context) is True
        assert evaluate_condition("{{ text | search('Missing') }}", context) is False

    def test_nested_dictionary_access_works(self):
        """Verify safe nested dictionary access still works."""
        context = {
            "nodes": {
                "analyze": {"score": 90, "status": "complete"},
                "review": {"score": 75, "status": "pending"},
            }
        }

        assert evaluate_condition("{{ nodes.analyze.score >= 85 }}", context) is True
        assert evaluate_condition("{{ nodes.review.status == 'pending' }}", context) is True

    def test_string_operations_work(self):
        """Verify safe string operations function in sandbox."""
        context = {"category": "Technical", "priority": "high"}

        assert evaluate_condition("{{ 'technical' in category.lower() }}", context) is True
        assert evaluate_condition("{{ category.startswith('Tech') }}", context) is True


class TestConditionValidationSecurity:
    """Test validation function also enforces security."""

    @pytest.mark.parametrize(
        "malicious_expr",
        [
            "{{ __class__ }}",
            "{{ eval('x') }}",
            "{{ exec('code') }}",
            "{{ __import__('os') }}",
        ],
    )
    def test_validate_rejects_dangerous_patterns(self, malicious_expr: str):
        """Verify validate_condition_syntax also blocks dangerous patterns."""
        valid, error = validate_condition_syntax(malicious_expr)
        assert valid is False
        assert "Security violation" in error or "Forbidden pattern" in error

    def test_validate_allows_safe_expressions(self):
        """Verify validation allows safe expressions."""
        safe_exprs = [
            "{{ score >= 85 }}",
            "{{ nodes.analyze.status == 'complete' }}",
            "{{ a > 5 and b < 10 }}",
            "else",
        ]
        for expr in safe_exprs:
            valid, error = validate_condition_syntax(expr)
            assert valid is True
            assert error is None


class TestElseKeywordSecurity:
    """Test that 'else' keyword handling is secure."""

    def test_else_keyword_always_true(self):
        """Verify 'else' keyword works without security issues."""
        assert evaluate_condition("else", {}) is True
        assert evaluate_condition("  ELSE  ", {}) is True
        assert evaluate_condition("Else", {}) is True

    def test_else_validation(self):
        """Verify 'else' passes validation."""
        valid, error = validate_condition_syntax("else")
        assert valid is True
        assert error is None


class TestSecurityWithContextData:
    """Test security with various context data types."""

    def test_context_with_objects_safe(self):
        """Verify context objects can't be exploited."""

        class CustomObject:
            def __init__(self):
                self.value = 42

        context = {"obj": CustomObject(), "data": {"key": "value"}}

        # Access to public attributes should work
        assert evaluate_condition("{{ obj.value == 42 }}", context) is True

        # But __class__ access should be blocked by pattern filter
        with pytest.raises(ConditionEvaluationError, match="Security violation"):
            evaluate_condition("{{ obj.__class__ }}", context)

    def test_context_with_none_safe(self):
        """Verify None values handled safely."""
        context = {"value": None, "data": None}

        # None comparisons should work
        assert evaluate_condition("{{ value == None }}", context) is True
        assert evaluate_condition("{{ data is none }}", context) is True

    def test_context_with_empty_dict_safe(self):
        """Verify empty context is safe."""
        # Should not raise errors with empty context
        assert evaluate_condition("else", {}) is True

        # Accessing undefined variables returns False (Jinja2 default behavior in if-context)
        # This is actually SAFE - undefined vars in conditions evaluate to False
        result = evaluate_condition("{{ undefined_var }}", {})
        assert result is False  # Undefined variables are falsy


class TestSecurityEdgeCases:
    """Test edge cases in security validation."""

    def test_pattern_in_string_literal_blocks_safely(self):
        """Verify patterns in string literals are blocked for conservative security."""
        # Even in string literals, we block dangerous patterns to prevent
        # clever attacks that might exploit template parsing edge cases
        context = {"response": "The __class__ attribute is forbidden"}

        # Conservative: block __class__ even in string literals
        with pytest.raises(
            ConditionEvaluationError, match=r"Security violation.*Forbidden pattern"
        ):
            evaluate_condition("{{ '__class__' in response }}", context)

    def test_whitespace_variations_in_patterns(self):
        """Verify pattern detection handles whitespace."""
        malicious_exprs = [
            "{{ __class__ }}",
            "{{__class__}}",
            "{{  __class__  }}",
            "{{ __class__}}",
        ]
        for expr in malicious_exprs:
            with pytest.raises(ConditionEvaluationError, match="Security violation"):
                evaluate_condition(expr, {})

    def test_comment_syntax_safe(self):
        """Verify Jinja2 comments don't bypass security."""
        # Jinja2 comments: {# comment #}
        # Should still check full expression for patterns
        malicious = "{{ __class__ {# comment #} }}"
        with pytest.raises(ConditionEvaluationError, match="Security violation"):
            evaluate_condition(malicious, {})

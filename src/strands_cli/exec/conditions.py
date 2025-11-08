"""Condition evaluation for graph pattern.

Provides safe evaluation of conditional expressions in graph edges.
Uses Jinja2 template engine for expression evaluation with restricted environment.
"""

from typing import Any

import structlog
from jinja2 import Environment, TemplateSyntaxError, UndefinedError

logger = structlog.get_logger(__name__)


class ConditionEvaluationError(Exception):
    """Raised when condition evaluation fails."""

    pass


def evaluate_condition(when_expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a conditional expression using Jinja2.

    Supports:
    - Comparisons: ==, !=, <, <=, >, >=
    - Boolean operators: and, or, not
    - Template variables: {{ nodes.analyze.score }}
    - Special keyword: "else" (always true)

    Args:
        when_expr: Condition expression or "else"
        context: Template context with variables (nodes, steps, etc.)

    Returns:
        True if condition evaluates to true, False otherwise

    Raises:
        ConditionEvaluationError: If expression is malformed or evaluation fails

    Examples:
        >>> evaluate_condition("else", {})
        True
        >>> evaluate_condition("score >= 85", {"score": 90})
        True
        >>> evaluate_condition("nodes.analyze.score >= 85", {"nodes": {"analyze": {"score": 90}}})
        True
    """
    # Handle special "else" keyword
    if when_expr.strip().lower() == "else":
        logger.debug("condition_else", result=True)
        return True

    # Create Jinja2 environment with minimal features for safety
    env = Environment(autoescape=False)

    try:
        # Strip {{ }} if present (conditions can be written with or without them)
        expr = when_expr.strip()
        if expr.startswith("{{") and expr.endswith("}}"):
            expr = expr[2:-2].strip()

        # Wrap expression in {% if %} block for evaluation
        # This allows us to evaluate the expression and get a boolean result
        template_str = f"{{% if {expr} %}}true{{% else %}}false{{% endif %}}"
        template = env.from_string(template_str)

        # Render with context
        result = template.render(**context)
        is_true = result.strip() == "true"

        logger.debug(
            "condition_evaluated",
            expression=when_expr,
            result=is_true,
            context_keys=list(context.keys()),
        )
        return is_true

    except TemplateSyntaxError as e:
        logger.error(
            "condition_syntax_error",
            expression=when_expr,
            error=str(e),
            line=e.lineno,
        )
        raise ConditionEvaluationError(
            f"Malformed condition expression '{when_expr}': {e.message} (line {e.lineno})"
        ) from e

    except UndefinedError as e:
        logger.error(
            "condition_undefined_variable",
            expression=when_expr,
            error=str(e),
        )
        raise ConditionEvaluationError(
            f"Undefined variable in condition '{when_expr}': {e.message}"
        ) from e

    except Exception as e:
        logger.error(
            "condition_evaluation_failed",
            expression=when_expr,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise ConditionEvaluationError(
            f"Failed to evaluate condition '{when_expr}': {e}"
        ) from e


def validate_condition_syntax(when_expr: str) -> tuple[bool, str | None]:
    """Validate condition syntax without evaluating.

    Useful for early validation without requiring full context.

    Args:
        when_expr: Condition expression to validate

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_condition_syntax("score >= 85")
        (True, None)
        >>> validate_condition_syntax("invalid syntax }")
        (False, "...")
    """
    # Special "else" is always valid
    if when_expr.strip().lower() == "else":
        return True, None

    env = Environment(autoescape=False)

    try:
        # Strip {{ }} if present
        expr = when_expr.strip()
        if expr.startswith("{{") and expr.endswith("}}"):
            expr = expr[2:-2].strip()

        template_str = f"{{% if {expr} %}}true{{% else %}}false{{% endif %}}"
        env.from_string(template_str)
        return True, None

    except TemplateSyntaxError as e:
        return False, f"Syntax error: {e.message} (line {e.lineno})"

    except Exception as e:
        return False, f"Validation error: {e}"

"""Condition evaluation for graph pattern.

Provides safe evaluation of conditional expressions in graph edges.
Uses Jinja2 template engine for expression evaluation with restricted environment.
"""

import re
from typing import Any

import structlog
from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

logger = structlog.get_logger(__name__)

# Dangerous patterns that could lead to code execution
DANGEROUS_PATTERNS = [
    r"__\w+__",  # Any double-underscore attribute (catches __class__, __mro__, __globals__, etc.)
    r"\beval\b",
    r"\bexec\b",
    r"\bcompile\b",
    r"\bopen\b",
    r"\bfile\b",
    r"\bimport\b",
]


# Safe builtins whitelist for Jinja2 sandbox
SAFE_BUILTINS: dict[str, object] = {
    "True": True,
    "False": False,
    "None": None,
    "range": range,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
}


class ConditionEvaluationError(Exception):
    """Raised when condition evaluation fails."""

    pass


def evaluate_condition(when_expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a conditional expression using Jinja2.

    Security: Uses SandboxedEnvironment to prevent code execution.
    Blocks dangerous patterns like __class__, eval, exec, etc.

    Supports:
    - Comparisons: ==, !=, <, <=, >, >=
    - Boolean operators: and, or, not
    - Template variables: {{ nodes.analyze.score }}
    - Special keyword: "else" (always true)
    - Safe filters: default, length, lower, upper, search

    Args:
        when_expr: Condition expression or "else"
        context: Template context with variables (nodes, steps, etc.)

    Returns:
        True if condition evaluates to true, False otherwise

    Raises:
        ConditionEvaluationError: If expression is malformed, contains dangerous
            patterns, or evaluation fails

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

    # Security check: reject dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, when_expr, re.IGNORECASE):
            logger.error(
                "condition_security_violation",
                expression=when_expr,
                forbidden_pattern=pattern,
            )
            raise ConditionEvaluationError(
                f"Security violation: Forbidden pattern '{pattern}' detected in condition expression"
            )

    # Create sandboxed Jinja2 environment with restricted namespace
    env = SandboxedEnvironment(autoescape=False)

    # Whitelist-based namespace with only safe builtins
    env.globals = SAFE_BUILTINS.copy()

    # Only safe filters
    env.filters = {
        "default": lambda v, d: v if v is not None else d,
        "length": len,
        "lower": str.lower,
        "upper": str.upper,
        "search": lambda s, p: re.search(p, str(s)) is not None,
    }

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
        raise ConditionEvaluationError(f"Failed to evaluate condition '{when_expr}': {e}") from e


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

    # Security check: reject dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, when_expr, re.IGNORECASE):
            return False, f"Security violation: Forbidden pattern '{pattern}' detected"

    env = SandboxedEnvironment(autoescape=False)
    env.globals = SAFE_BUILTINS.copy()
    env.filters = {
        "default": lambda v, d: v if v is not None else d,
        "length": len,
        "lower": str.lower,
        "upper": str.upper,
        "search": lambda s, p: re.search(p, str(s)) is not None,
    }

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

"""Calculator tool (Strands SDK module-based pattern).

Perform basic mathematical calculations safely.
"""

import ast
import operator
from typing import Any

TOOL_SPEC = {
    "name": "calculator",
    "description": "Perform basic mathematical calculations (addition, subtraction, multiplication, division, exponentiation)",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', '10 * 5 - 3')",
                }
            },
            "required": ["expression"],
        }
    },
}


SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_expr(node: ast.AST) -> float | int | complex:
    """Safely evaluate a mathematical expression AST node.

    Args:
        node: AST node to evaluate

    Returns:
        Numeric result of the expression

    Raises:
        ValueError: If expression contains unsupported operations
        ZeroDivisionError: If division by zero is attempted
    """
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported operation: {type(node.op).__name__}")
        left = _eval_expr(node.left)
        right = _eval_expr(node.right)
        op_func = SAFE_OPERATORS[type(node.op)]
        result: float | int | complex = op_func(left, right)  # type: ignore[assignment]
        return result
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operation: {type(node.op).__name__}")
        operand = _eval_expr(node.operand)
        op_func = SAFE_OPERATORS[type(node.op)]
        result: float | int | complex = op_func(operand)  # type: ignore[assignment]
        return result
    elif isinstance(node, ast.Expression):
        return _eval_expr(node.body)
    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def calculator(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Safely evaluate a mathematical expression.

    Security:
    - Uses AST parsing to validate expressions
    - Only allows basic arithmetic operations
    - Prevents code execution via eval()
    - No function calls or variable access

    Supported operations:
    - Addition: +
    - Subtraction: -
    - Multiplication: *
    - Division: /
    - Floor Division: //
    - Modulo: %
    - Exponentiation: **
    - Unary operations: +x, -x

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional context (ignored)

    Returns:
        Tool result with calculation result or error message
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    expression = tool_input.get("expression", "").strip()

    if not expression:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: 'expression' parameter is required"}],
        }

    try:
        parsed = ast.parse(expression, mode="eval")
        result = _eval_expr(parsed)

        if isinstance(result, float) and result.is_integer():
            result = int(result)

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": f"{expression} = {result}"}],
        }

    except SyntaxError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Syntax error in expression: {e}"}],
        }
    except ZeroDivisionError:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Error: Division by zero"}],
        }
    except ValueError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: {e}"}],
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error evaluating expression: {e}"}],
        }

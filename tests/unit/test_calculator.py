"""Unit tests for calculator native tool.

Tests the calculator tool which safely evaluates mathematical expressions.
"""


class TestCalculatorToolSpec:
    """Test TOOL_SPEC definition for calculator."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in calculator module."""
        from strands_cli.tools import calculator

        assert hasattr(calculator, "TOOL_SPEC")
        assert isinstance(calculator.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.calculator import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "calculator"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.calculator import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "expression" in input_schema["properties"]
        assert "expression" in input_schema["required"]


class TestCalculatorFunction:
    """Test calculator function behavior."""

    def test_calculator_callable_exists(self) -> None:
        """Test that calculator function is defined and callable."""
        from strands_cli.tools.calculator import calculator

        assert callable(calculator)

    def test_simple_addition(self) -> None:
        """Test simple addition calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "add-test", "input": {"expression": "2 + 2"}}

        result = calculator(tool_input)

        assert result["toolUseId"] == "add-test"
        assert result["status"] == "success"
        assert "4" in result["content"][0]["text"]

    def test_simple_subtraction(self) -> None:
        """Test simple subtraction calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "sub-test", "input": {"expression": "10 - 3"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "7" in result["content"][0]["text"]

    def test_simple_multiplication(self) -> None:
        """Test simple multiplication calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "mul-test", "input": {"expression": "5 * 6"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "30" in result["content"][0]["text"]

    def test_simple_division(self) -> None:
        """Test simple division calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "div-test", "input": {"expression": "20 / 4"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "5" in result["content"][0]["text"]

    def test_floor_division(self) -> None:
        """Test floor division calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "floor-div", "input": {"expression": "7 // 2"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "3" in result["content"][0]["text"]

    def test_modulo(self) -> None:
        """Test modulo calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "mod-test", "input": {"expression": "10 % 3"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "1" in result["content"][0]["text"]

    def test_exponentiation(self) -> None:
        """Test exponentiation calculation."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "pow-test", "input": {"expression": "2 ** 3"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "8" in result["content"][0]["text"]

    def test_complex_expression(self) -> None:
        """Test complex expression with multiple operations."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "complex", "input": {"expression": "(10 + 5) * 2 - 3"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "27" in result["content"][0]["text"]

    def test_negative_numbers(self) -> None:
        """Test calculation with negative numbers."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "negative", "input": {"expression": "-5 + 10"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "5" in result["content"][0]["text"]

    def test_decimal_numbers(self) -> None:
        """Test calculation with decimal numbers."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "decimal", "input": {"expression": "3.5 * 2"}}

        result = calculator(tool_input)

        assert result["status"] == "success"
        assert "7" in result["content"][0]["text"]

    def test_missing_expression_returns_error(self) -> None:
        """Test that missing expression parameter returns error."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "no-expr", "input": {}}

        result = calculator(tool_input)

        assert result["toolUseId"] == "no-expr"
        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_empty_expression_returns_error(self) -> None:
        """Test that empty expression string returns error."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "empty-expr", "input": {"expression": ""}}

        result = calculator(tool_input)

        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_division_by_zero_returns_error(self) -> None:
        """Test that division by zero returns error."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "div-zero", "input": {"expression": "5 / 0"}}

        result = calculator(tool_input)

        assert result["status"] == "error"
        assert "zero" in result["content"][0]["text"].lower()

    def test_syntax_error_returns_error(self) -> None:
        """Test that syntax errors are caught."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "syntax-err", "input": {"expression": "2 +"}}

        result = calculator(tool_input)

        assert result["status"] == "error"
        assert "syntax" in result["content"][0]["text"].lower()

    def test_invalid_characters_returns_error(self) -> None:
        """Test that invalid characters return error."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "invalid-char", "input": {"expression": "2 + abc"}}

        result = calculator(tool_input)

        assert result["status"] == "error"

    def test_function_call_not_allowed(self) -> None:
        """Test that function calls are not allowed (security)."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "func-call", "input": {"expression": "print(5)"}}

        result = calculator(tool_input)

        assert result["status"] == "error"

    def test_variable_access_not_allowed(self) -> None:
        """Test that variable access is not allowed (security)."""
        from strands_cli.tools.calculator import calculator

        tool_input = {"toolUseId": "var-access", "input": {"expression": "x + 5"}}

        result = calculator(tool_input)

        assert result["status"] == "error"


class TestCalculatorToolIntegration:
    """Test calculator tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that calculator is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("calculator")

        assert tool_info is not None
        assert tool_info.id == "calculator"
        assert tool_info.module_path == "strands_cli.tools.calculator"

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that calculator paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "calculator" in allowlist
        assert "strands_cli.tools.calculator" in allowlist

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("calculator")

        assert resolved == "strands_cli.tools.calculator"

    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load calculator with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("calculator")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "calculator")
        assert callable(tool_module.calculator)

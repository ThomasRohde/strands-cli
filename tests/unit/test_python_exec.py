"""Unit tests for python_exec native tool.

Tests the MVP implementation of the python_exec tool which executes
Python code with restricted builtins and stdout capture.
"""


class TestPythonExecToolSpec:
    """Test TOOL_SPEC definition for python_exec."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in python_exec module."""
        from strands_cli.tools import python_exec

        assert hasattr(python_exec, "TOOL_SPEC")
        assert isinstance(python_exec.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.python_exec import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "python_exec"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.python_exec import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "code" in input_schema["properties"]
        assert "timeout" in input_schema["properties"]
        assert "code" in input_schema["required"]


class TestPythonExecFunction:
    """Test python_exec function behavior."""

    def test_python_exec_callable_exists(self) -> None:
        """Test that python_exec function is defined and callable."""
        from strands_cli.tools.python_exec import python_exec

        assert callable(python_exec)

    def test_simple_code_execution_success(self) -> None:
        """Test execution of simple Python code that prints output."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "test-123", "input": {"code": "print('Hello, World!')"}}

        result = python_exec(tool_input)

        assert result["toolUseId"] == "test-123"
        assert result["status"] == "success"
        assert len(result["content"]) == 1
        assert "Hello, World!" in result["content"][0]["text"]

    def test_code_execution_with_calculation(self) -> None:
        """Test execution of code that performs calculations."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "calc-456",
            "input": {"code": "result = 2 + 2\nprint(f'Result: {result}')"},
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        assert "Result: 4" in result["content"][0]["text"]

    def test_code_execution_with_multiple_prints(self) -> None:
        """Test that multiple print statements are captured."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "multi-print",
            "input": {"code": "print('Line 1')\nprint('Line 2')\nprint('Line 3')"},
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        output = result["content"][0]["text"]
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output

    def test_no_output_returns_success_message(self) -> None:
        """Test that code with no output returns success message."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "no-output",
            "input": {
                "code": "x = 5 + 5"  # No print, just assignment
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        assert "successfully" in result["content"][0]["text"].lower()

    def test_empty_code_returns_error(self) -> None:
        """Test that empty code returns error status."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "empty-code", "input": {"code": ""}}

        result = python_exec(tool_input)

        assert result["toolUseId"] == "empty-code"
        assert result["status"] == "error"
        assert "No code provided" in result["content"][0]["text"]

    def test_missing_code_field_returns_error(self) -> None:
        """Test that missing code field returns error."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "no-code-field", "input": {}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        assert "No code provided" in result["content"][0]["text"]

    def test_syntax_error_returns_error_status(self) -> None:
        """Test that syntax errors are caught and returned as errors."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "syntax-err", "input": {"code": "print('missing closing quote"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        assert "Execution failed" in result["content"][0]["text"]
        assert "SyntaxError" in result["content"][0]["text"]

    def test_runtime_error_returns_error_status(self) -> None:
        """Test that runtime errors are caught and returned."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "runtime-err",
            "input": {
                "code": "x = 1 / 0"  # Division by zero
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "error"
        assert "Execution failed" in result["content"][0]["text"]
        assert "ZeroDivisionError" in result["content"][0]["text"]

    def test_name_error_for_undefined_variable(self) -> None:
        """Test that undefined variables raise NameError."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "name-err", "input": {"code": "print(undefined_variable)"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        assert "NameError" in result["content"][0]["text"]


class TestPythonExecRestrictedBuiltins:
    """Test restricted builtins security."""

    def test_allowed_builtins_work(self) -> None:
        """Test that allowed builtins are accessible."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "allowed-builtins",
            "input": {
                "code": """
x = int('42')
y = float('3.14')
z = str(123)
items = list([1, 2, 3])
result = len(items) + sum(items)
print(f'Result: {result}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        assert "Result: 9" in result["content"][0]["text"]  # len([1,2,3]) + sum([1,2,3]) = 3 + 6

    def test_range_and_enumerate_work(self) -> None:
        """Test that range and enumerate are available."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "range-enum",
            "input": {
                "code": """
for i in range(3):
    print(f'Number: {i}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        output = result["content"][0]["text"]
        assert "Number: 0" in output
        assert "Number: 1" in output
        assert "Number: 2" in output

    def test_list_dict_set_constructors_work(self) -> None:
        """Test that collection constructors are available."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "collections",
            "input": {
                "code": """
my_list = list([1, 2, 3])
my_dict = dict(a=1, b=2)
my_set = set([1, 2, 2, 3])
my_tuple = tuple([4, 5])
print(f'List: {len(my_list)}, Dict: {len(my_dict)}, Set: {len(my_set)}, Tuple: {len(my_tuple)}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        assert "List: 3, Dict: 2, Set: 3, Tuple: 2" in result["content"][0]["text"]

    def test_math_builtins_available(self) -> None:
        """Test that math-related builtins (abs, min, max, etc.) work."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "math-builtins",
            "input": {
                "code": """
numbers = [1, -5, 10, 3]
print(f'Min: {min(numbers)}')
print(f'Max: {max(numbers)}')
print(f'Sum: {sum(numbers)}')
print(f'Abs: {abs(-42)}')
print(f'Round: {round(3.7)}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        output = result["content"][0]["text"]
        assert "Min: -5" in output
        assert "Max: 10" in output
        assert "Sum: 9" in output
        assert "Abs: 42" in output
        assert "Round: 4" in output

    def test_sorted_and_reversed_work(self) -> None:
        """Test that sorted and reversed are available."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "sorted-reversed",
            "input": {
                "code": """
items = [3, 1, 4, 1, 5]
print(f'Sorted: {sorted(items)}')
print(f'Reversed: {list(reversed(items))}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        output = result["content"][0]["text"]
        assert "[1, 1, 3, 4, 5]" in output
        assert "[5, 1, 4, 1, 3]" in output

    def test_isinstance_and_type_work(self) -> None:
        """Test that type checking functions are available."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {
            "toolUseId": "type-check",
            "input": {
                "code": """
x = 42
print(f'Is int: {isinstance(x, int)}')
print(f'Type: {type(x).__name__}')
"""
            },
        }

        result = python_exec(tool_input)

        assert result["status"] == "success"
        output = result["content"][0]["text"]
        assert "Is int: True" in output
        assert "Type: int" in output

    def test_restricted_builtins_blocks_import(self) -> None:
        """Test that import is not available (security)."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "blocked-import", "input": {"code": "import os"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        # Should get NameError because 'import' is not in restricted builtins
        assert "Error" in result["content"][0]["text"]

    def test_restricted_builtins_blocks_open(self) -> None:
        """Test that file operations are not available (security)."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "blocked-open", "input": {"code": "open('test.txt', 'w')"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        # Should get NameError because 'open' is not in restricted builtins
        assert "Error" in result["content"][0]["text"]

    def test_restricted_builtins_blocks_eval(self) -> None:
        """Test that eval is not available (security)."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "blocked-eval", "input": {"code": "eval('1 + 1')"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        # Should get NameError because 'eval' is not in restricted builtins
        assert "Error" in result["content"][0]["text"]

    def test_restricted_builtins_blocks_exec_function(self) -> None:
        """Test that exec function is not available (security)."""
        from strands_cli.tools.python_exec import python_exec

        tool_input = {"toolUseId": "blocked-exec-fn", "input": {"code": "exec('print(\"test\")')"}}

        result = python_exec(tool_input)

        assert result["status"] == "error"
        # Should get NameError because 'exec' is not in restricted builtins
        assert "Error" in result["content"][0]["text"]


class TestPythonExecToolIntegration:
    """Test python_exec tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that python_exec is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("python_exec")

        assert tool_info is not None
        assert tool_info.id == "python_exec"
        assert tool_info.module_path == "strands_cli.tools.python_exec"
        assert "python code" in tool_info.description.lower()

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that python_exec paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        # Should have both formats
        assert "python_exec" in allowlist  # Short ID
        assert "strands_cli.tools.python_exec" in allowlist  # Full path

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("python_exec")

        assert resolved == "strands_cli.tools.python_exec"


    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load python_exec with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("python_exec")

        # Should return the module (has TOOL_SPEC)
        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "python_exec")
        assert callable(tool_module.python_exec)

    def test_load_python_callable_with_full_path(self) -> None:
        """Test that load_python_callable can load with full native path."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("strands_cli.tools.python_exec")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "python_exec")


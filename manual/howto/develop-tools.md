# Native Tools Development Guide

This guide explains how to develop native tools for the Strands CLI using the registry-based auto-discovery system.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Your First Tool: Echo](#your-first-tool-echo)
3. [TOOL_SPEC Format](#tool_spec-format)
4. [ToolResult Contract](#toolresult-contract)
5. [Advanced Example: python_exec](#advanced-example-python_exec)
6. [Testing Your Tool](#testing-your-tool)
7. [Using Tools in Workflows](#using-tools-in-workflows)
8. [Registry Mechanics](#registry-mechanics)

## Architecture Overview

The Strands CLI uses a **registry-based auto-discovery system** for native tools. Tools are automatically discovered and registered at runtime without manual configuration.

### Key Components

- **Tool Modules**: Python files in `src/strands_cli/tools/` that export `TOOL_SPEC`
- **Registry**: `src/strands_cli/tools/registry.py` - scans and registers tools on first import
- **Capability Checker**: `src/strands_cli/capability/checker.py` - validates tool usage against allowlist
- **Tool Adapter**: `src/strands_cli/runtime/tools.py` - loads and executes tools during workflow runs

### Auto-Discovery Flow

```
1. CLI starts → imports strands_cli.tools
2. ToolRegistry.__new__() → singleton instantiation
3. _discover_tools() → scans src/strands_cli/tools/*.py
4. For each .py file:
   - Import module
   - Check for TOOL_SPEC export
   - Validate TOOL_SPEC.name exists
   - Register ToolInfo(id, module_path, description)
5. Tools available via get_registry().list_all()
```

### Directory Structure

```
src/strands_cli/tools/
├── __init__.py           # Exports get_registry()
├── registry.py           # Auto-discovery logic
└── python_exec.py        # Example native tool
```

## Your First Tool: Echo

Let's build a simple `echo` tool that returns the input message unchanged.

### Step 1: Create the Tool Module

Create `src/strands_cli/tools/echo.py`:

```python
"""Echo tool - returns input message unchanged.

Simple example demonstrating the minimal native tool pattern.
"""

from typing import Any


# Tool Specification (required for auto-discovery)
TOOL_SPEC = {
    "name": "echo",
    "description": "Returns the input message unchanged",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo back"
                }
            },
            "required": ["message"]
        }
    }
}


def echo(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Echo tool implementation.
    
    Args:
        tool: Tool invocation object with:
            - toolUseId: Unique identifier for this invocation
            - input: Dict containing the input parameters
        **kwargs: Additional arguments (unused but required for signature)
    
    Returns:
        ToolResult dict with:
            - toolUseId: Echo back the invocation ID
            - status: "success" or "error"
            - content: List of content blocks (text or other formats)
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    message = tool_input.get("message", "")
    
    if not message:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No message provided"}]
        }
    
    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"text": message}]
    }
```

### Step 2: Verify Auto-Discovery

The tool is automatically discovered when the registry initializes. Verify it works:

```powershell
uv run python -c "from strands_cli.tools import get_registry; print([t.id for t in get_registry().list_all()])"
# Should output: ['python_exec', 'echo']
```

### Step 3: Use in a Workflow

Create `examples/echo-demo.yaml`:

```yaml
version: 0
name: echo-demo
description: Test the echo native tool

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  assistant:
    prompt: |
      You are a helpful assistant. When asked to echo a message,
      use the echo tool to return it unchanged.

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Echo this message: Hello, World!"

tools:
  python:
    - echo  # Short ID format (auto-resolved by registry)

outputs:
  artifacts:
    - path: ./echo-result.txt
      from: "{{ last_response }}"
```

Run it:

```powershell
uv run strands run examples/echo-demo.yaml --force
```

## TOOL_SPEC Format

The `TOOL_SPEC` dictionary follows the Strands SDK module-based pattern and must contain:

### Required Fields

```python
TOOL_SPEC = {
    "name": str,           # Tool identifier (must match function name)
    "description": str,    # Human-readable description
    "inputSchema": dict    # JSON Schema defining input parameters
}
```

### Input Schema Structure

The `inputSchema` must follow this format:

```python
"inputSchema": {
    "json": {
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string|number|integer|boolean|array|object",
                "description": "Parameter description",
                # Optional:
                "default": value,
                "enum": [allowed_values],
                "minimum": number,
                "maximum": number,
                "items": {...}  # For array types
            }
        },
        "required": ["param1", "param2"]  # List of required parameter names
    }
}
```

### Complete Example

```python
TOOL_SPEC = {
    "name": "calculator",
    "description": "Perform arithmetic calculations",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Arithmetic operation to perform",
                    "enum": ["add", "subtract", "multiply", "divide"]
                },
                "a": {
                    "type": "number",
                    "description": "First operand"
                },
                "b": {
                    "type": "number",
                    "description": "Second operand"
                },
                "precision": {
                    "type": "integer",
                    "description": "Number of decimal places",
                    "default": 2,
                    "minimum": 0,
                    "maximum": 10
                }
            },
            "required": ["operation", "a", "b"]
        }
    }
}
```

## ToolResult Contract

All tool functions must return a dictionary following this standard format:

### Success Response

```python
{
    "toolUseId": str,      # Echo back the invocation ID
    "status": "success",   # Indicates successful execution
    "content": [           # List of content blocks
        {"text": str},     # Text content (most common)
        # or:
        {"json": dict},    # JSON content
        {"image": bytes},  # Binary content
    ]
}
```

### Error Response

```python
{
    "toolUseId": str,      # Echo back the invocation ID
    "status": "error",     # Indicates failure
    "content": [
        {"text": str}      # Error message
    ]
}
```

### Guidelines

1. **Always include `toolUseId`**: Extract from `tool.get("toolUseId", "")` and echo it back
2. **Use descriptive error messages**: Help users understand what went wrong
3. **Return text content by default**: Most tools return `{"text": result}`
4. **Handle missing inputs gracefully**: Validate inputs and return errors, don't raise exceptions
5. **Catch all exceptions**: Wrap execution logic in try/except and return error responses

### Example with Error Handling

```python
def my_tool(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    
    # Validate required parameters
    required_param = tool_input.get("required_param")
    if not required_param:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Missing required parameter: required_param"}]
        }
    
    try:
        # Execute tool logic
        result = perform_operation(required_param)
        
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": str(result)}]
        }
    
    except ValueError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Invalid input: {e}"}]
        }
    
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Execution failed: {type(e).__name__}: {e}"}]
        }
```

## Advanced Example: python_exec

The `python_exec` tool demonstrates advanced patterns including security restrictions, output capture, and comprehensive error handling.

### Full Implementation

```python
"""Python code execution tool (Strands SDK module-based pattern).

Execute Python code safely with restricted builtins and stdout capture.
MVP implementation - production version should add proper sandboxing.
"""

import io
from contextlib import redirect_stdout
from typing import Any

# Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "python_exec",
    "description": "Execute Python code and return results (MVP - simple version with restricted builtins)",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {
                    "type": "integer",
                    "default": 5,
                    "description": "Timeout in seconds (not enforced in MVP)",
                },
            },
            "required": ["code"],
        }
    },
}


def python_exec(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Execute Python code with restricted builtins and stdout capture.

    MVP Implementation:
    - Uses exec() with restricted globals
    - Captures stdout via StringIO
    - Returns result or error

    Security Limitations (MVP):
    - No proper sandboxing (subprocess/docker)
    - No resource limits (memory, CPU)
    - No timeout enforcement
    - Limited builtin allowlist
    - No AST parsing for dangerous operations

    Production version should address all security limitations.

    Args:
        tool: Tool invocation object with toolUseId and input
        **kwargs: Additional arguments (unused)

    Returns:
        ToolResult dict with status and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    code = tool_input.get("code", "")

    if not code:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "No code provided"}],
        }

    try:
        # Capture stdout
        output = io.StringIO()

        with redirect_stdout(output):
            # Restricted globals - only safe builtins
            restricted_globals = {
                "__builtins__": {
                    # Type constructors
                    "int": int,
                    "float": float,
                    "str": str,
                    "bool": bool,
                    "list": list,
                    "dict": dict,
                    "tuple": tuple,
                    "set": set,
                    # Utilities
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "abs": abs,
                    "round": round,
                    "sorted": sorted,
                    "reversed": reversed,
                    # Output
                    "print": print,
                    # Type checking
                    "isinstance": isinstance,
                    "type": type,
                }
            }

            # Execute code with restricted environment
            exec(code, restricted_globals)

        # Get captured output
        result = output.getvalue()

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result if result else "Code executed successfully (no output)"}],
        }

    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Execution failed: {type(e).__name__}: {e!s}"}],
        }
```

### Key Patterns Demonstrated

1. **Output Capture**: Using `io.StringIO()` and `redirect_stdout()` to capture printed output
2. **Security Restrictions**: Custom `__builtins__` dict to limit available functions
3. **Comprehensive Error Handling**: Catching all exceptions and returning structured errors
4. **Documentation**: Clear docstrings explaining security limitations
5. **Type Hints**: Full type annotations for better IDE support and type checking

## Testing Your Tool

Every native tool should have comprehensive tests. Here's the pattern used for `python_exec`.

### Test File Structure

Create `tests/test_echo.py`:

```python
"""Unit tests for echo native tool."""

import pytest


class TestEchoTool:
    """Tests for the echo tool."""

    def test_echo_success(self) -> None:
        """Test successful echo operation."""
        from strands_cli.tools.echo import echo
        
        tool = {
            "toolUseId": "test-123",
            "input": {"message": "Hello, World!"}
        }
        
        result = echo(tool)
        
        assert result["toolUseId"] == "test-123"
        assert result["status"] == "success"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Hello, World!"
    
    def test_echo_empty_message(self) -> None:
        """Test echo with empty message returns error."""
        from strands_cli.tools.echo import echo
        
        tool = {
            "toolUseId": "test-456",
            "input": {"message": ""}
        }
        
        result = echo(tool)
        
        assert result["toolUseId"] == "test-456"
        assert result["status"] == "error"
        assert "No message provided" in result["content"][0]["text"]
    
    def test_echo_missing_input(self) -> None:
        """Test echo with missing input dict."""
        from strands_cli.tools.echo import echo
        
        tool = {
            "toolUseId": "test-789",
            "input": {}
        }
        
        result = echo(tool)
        
        assert result["status"] == "error"
    
    def test_echo_tool_spec_format(self) -> None:
        """Test that TOOL_SPEC has required fields."""
        from strands_cli.tools.echo import TOOL_SPEC
        
        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "echo"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC
        assert "json" in TOOL_SPEC["inputSchema"]
        
        schema = TOOL_SPEC["inputSchema"]["json"]
        assert "properties" in schema
        assert "message" in schema["properties"]
        assert schema["required"] == ["message"]
```

### Integration Test Pattern

Create `tests/test_echo_integration.py`:

```python
"""Integration tests for echo tool in workflows."""

from pathlib import Path

import pytest

from strands_cli.loader import load_spec


class TestEchoIntegration:
    """Integration tests for echo tool."""

    def test_echo_in_spec_validation(self, tmp_path: Path) -> None:
        """Test that echo tool passes capability validation."""
        from strands_cli.capability import check_capability
        
        spec_content = """
version: 0
name: echo-validation-test
description: Test echo tool validation

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  assistant:
    prompt: "Test assistant"

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Test"

tools:
  python:
    - echo

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "echo_test.yaml"
        spec_file.write_text(spec_content)
        
        spec = load_spec(str(spec_file))
        report = check_capability(spec)
        
        # Should be supported (no issues)
        assert report.supported is True
        assert len(report.issues) == 0
    
    @pytest.mark.asyncio
    async def test_echo_in_chain_workflow(
        self, tmp_path: Path, mock_create_model: None
    ) -> None:
        """Test echo tool in a chain workflow."""
        spec_content = """
version: 0
name: echo-chain-test
description: Test echo in chain pattern

runtime:
  provider: ollama
  model_id: llama3.2:3b
  host: http://localhost:11434

agents:
  assistant:
    prompt: "Use the echo tool"

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: "Echo: Test message"

tools:
  python:
    - echo

outputs:
  artifacts:
    - path: result.txt
      from: "{{ last_response }}"
"""
        spec_file = tmp_path / "echo_chain.yaml"
        spec_file.write_text(spec_content)
        
        spec = load_spec(str(spec_file))
        
        from strands_cli.exec.chain import run_chain
        result = await run_chain(spec, {})
        
        assert result is not None
        assert result.last_response is not None
```

### Run Tests

```powershell
# Run all tests for echo tool
uv run pytest tests/test_echo.py -v

# Run with coverage
uv run pytest tests/test_echo.py --cov=src/strands_cli/tools/echo --cov-report=term-missing

# Run integration tests
uv run pytest tests/test_echo_integration.py -v
```

## Using Tools in Workflows

### Short ID Format (Recommended)

The simplest way to use a native tool:

```yaml
tools:
  python:
    - echo          # Auto-resolved to strands_cli.tools.echo
    - python_exec   # Auto-resolved to strands_cli.tools.python_exec
```

### Full Path Format

For explicit imports:

```yaml
tools:
  python:
    - strands_cli.tools.echo
    - strands_cli.tools.python_exec
```

 

### Complete Workflow Example

```yaml
version: 0
name: multi-tool-demo
description: Demonstrate multiple native tools

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  assistant:
    prompt: |
      You are a helpful assistant with access to multiple tools.
      Use the echo tool to repeat messages, and python_exec to perform calculations.

pattern:
  type: chain
  config:
    steps:
      - agent: assistant
        input: |
          First, echo this message: "Starting workflow"
          Then calculate the factorial of 5 using Python.

tools:
  python:
    - echo        # Native echo tool
    - python_exec # Native Python execution tool

outputs:
  artifacts:
    - path: ./workflow-result.txt
      from: "{{ last_response }}"
```

Run it:

```powershell
uv run strands run examples/multi-tool-demo.yaml --force
```

## Registry Mechanics

### How Auto-Discovery Works

The `ToolRegistry` class uses a singleton pattern and discovers tools on first instantiation:

```python
# From src/strands_cli/tools/registry.py

class ToolRegistry:
    """Simple singleton registry for native tools."""
    
    _instance: "ToolRegistry | None" = None
    _tools: dict[str, ToolInfo]
    
    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern - ensures only one registry instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._discover_tools()  # Auto-discovery happens here
        return cls._instance
```

### Discovery Process

```python
def _discover_tools(self) -> None:
    """Auto-discover tools from strands_cli.tools module."""
    tools_dir = Path(__file__).parent
    
    # Scan all .py files (skip __init__, registry, etc.)
    for _importer, module_name, _is_pkg in pkgutil.iter_modules([str(tools_dir)]):
        if module_name.startswith("_") or module_name == "registry":
            continue
        
        try:
            module = importlib.import_module(f"strands_cli.tools.{module_name}")
            
            # Check for TOOL_SPEC (Strands SDK pattern)
            if not hasattr(module, "TOOL_SPEC"):
                logger.warning("Tool module missing TOOL_SPEC, skipping", module_name=module_name)
                continue
            
            spec = module.TOOL_SPEC
            
            # Validate TOOL_SPEC has required fields
            if not isinstance(spec, dict) or "name" not in spec:
                logger.warning("Tool module has invalid TOOL_SPEC (missing 'name'), skipping")
                continue
            
            tool_id = spec["name"]
            
            # Register tool
            tool_info = ToolInfo(
                id=tool_id,
                module_path=f"strands_cli.tools.{module_name}",
                description=spec.get("description", "")
            )
            self._tools[tool_id] = tool_info
            
        except Exception as e:
            logger.warning("Failed to import tool module, skipping", error=str(e))
```

### ToolInfo Structure

```python
@dataclass
class ToolInfo:
    """Minimal tool metadata for discovery."""
    
    id: str                # Tool identifier (e.g., "echo")
    module_path: str       # Full import path (e.g., "strands_cli.tools.echo")
    description: str       # Tool description from TOOL_SPEC
    
    @property
    def import_path(self) -> str:
        """Full import path for loading."""
        return self.module_path
    
    
```

### Resolution Strategy

The registry resolves short IDs to full import paths:

```python
def resolve(self, user_input: str) -> str | None:
    """Resolve user input to canonical import path.
    
    Supports direct ID: "echo" → "strands_cli.tools.echo"
    """
    # Direct ID lookup
    if user_input in self._tools:
        return self._tools[user_input].import_path
    
    return None
```

### Allowlist Generation

The registry provides an allowlist for capability checking:

```python
def get_allowlist(self) -> set[str]:
    """Generate complete allowlist for capability checker.
    
    Returns all valid import formats for all discovered tools:
    - Short ID: "echo"
    - Full path: "strands_cli.tools.echo"
    """
    allowlist = set()
    for tool in self._tools.values():
        allowlist.add(tool.id)
        allowlist.add(tool.import_path)
    return allowlist
```

### Allowlist in Capability Checker

The capability checker uses the registry allowlist to validate Python tools:

```python
# From src/strands_cli/capability/checker.py

from strands_cli.tools import get_registry

registry = get_registry()
allowed = registry.get_allowlist()

if tool.callable not in allowed:
    issues.append(
        CapabilityIssue(
            pointer=f"/tools/python/{i}/callable",
            reason=f"Python callable '{tool.callable}' not in allowlist",
            remediation="Use an existing native tool or add one under strands_cli.tools"
        )
    )
```

### Accessing the Registry

```python
from strands_cli.tools import get_registry

# Get registry instance
registry = get_registry()

# List all discovered tools
all_tools = registry.list_all()
for tool in all_tools:
    print(f"{tool.id}: {tool.description}")

# Get specific tool
tool_info = registry.get("echo")
if tool_info:
    print(f"Import path: {tool_info.import_path}")

# Resolve user input
canonical_path = registry.resolve("echo")
# Returns: "strands_cli.tools.echo"

# Get allowlist for validation
allowlist = registry.get_allowlist()
# Returns: {"echo", "strands_cli.tools.echo", ...}
```

---

## Summary

Native tools in Strands CLI follow a simple pattern:

1. **Create** a Python module in `src/strands_cli/tools/`
2. **Export** a `TOOL_SPEC` dictionary with `name`, `description`, and `inputSchema`
3. **Implement** a function matching `TOOL_SPEC["name"]` that returns a ToolResult dict
4. **Test** with unit tests and integration tests
5. **Use** in workflows via short ID, full path, or legacy format

The registry handles auto-discovery, resolution, and backward compatibility automatically. No manual registration required!

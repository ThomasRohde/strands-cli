# Contributing to strands-cli

Thank you for your interest in contributing to strands-cli! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Exit Codes Convention](#exit-codes-convention)
- [Architecture Guidelines](#architecture-guidelines)

## Getting Started

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended)
- Git
- AWS credentials (for Bedrock provider testing)
- Ollama (for Ollama provider testing)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR-USERNAME/strands-cli.git
cd strands-cli
```

3. Add the upstream repository:

```bash
git remote add upstream https://github.com/original-org/strands-cli.git
```

### Install Development Dependencies

```bash
uv sync --dev
```

This installs all dependencies including development tools:
- pytest, pytest-mock, pytest-cov
- ruff (linting and formatting)
- mypy (type checking)
- pre-commit hooks

### Verify Installation

```bash
uv run strands --version
uv run pytest --version
```

## Development Setup

### Development Workflow

```powershell
# On Windows (recommended)
.\scripts\dev.ps1 test       # Run all tests
.\scripts\dev.ps1 test-cov   # Run with coverage
.\scripts\dev.ps1 lint       # Lint code
.\scripts\dev.ps1 format     # Auto-format code
.\scripts\dev.ps1 typecheck  # Type check
.\scripts\dev.ps1 ci         # Full CI pipeline
```

```bash
# On Linux/macOS
uv run pytest                          # Run all tests
uv run pytest --cov=src/strands_cli   # With coverage
uv run ruff check .                    # Lint
uv run ruff format .                   # Format
uv run mypy src                        # Type check
```

### Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_schema.py -v

# Specific test class
uv run pytest tests/test_e2e.py::TestOllamaE2E -v

# Specific test method
uv run pytest tests/test_cli.py::TestRunCommand::test_run_valid_ollama_spec -v

# With coverage
uv run pytest --cov=src/strands_cli --cov-report=html
# Open htmlcov/index.html
```

## Code Style

### Python Version

- **Minimum**: Python 3.12
- **Type hints**: Use modern syntax (`str | None`, not `Optional[str]`)
- **Match statements**: Preferred over long if/elif chains
- **Walrus operator**: Use `:=` when it improves readability

### Code Formatting

We use **Ruff** for both linting and formatting:

```bash
# Check code style
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

**Key rules**:
- Line length: 100 characters (not 88)
- Indentation: 4 spaces
- Quote style: Double quotes
- Trailing commas: Required in multi-line structures
- Import order: stdlib → third-party → first-party

### Type Checking

We use **Mypy** in strict mode:

```bash
uv run mypy src
```

**Requirements**:
- All functions must have type annotations
- No `Any` types without explanation
- Use `# type: ignore` sparingly and always with a comment explaining why
- Prefer Protocol/TypeAlias over complex Union types

**Example**:

```python
from typing import Protocol

class AgentConfig(Protocol):
    """Protocol for agent configuration."""
    prompt: str
    tools: list[str] | None

def build_agent(config: AgentConfig) -> Agent:
    """Build agent from config. Returns configured Agent."""
    ...
```

### Pydantic Models

All configuration and spec models must use **Pydantic v2**:

```python
from pydantic import BaseModel, Field

class Runtime(BaseModel):
    """Runtime configuration."""
    provider: str = Field(..., description="Provider type")
    model_id: str | None = Field(None, description="Model ID")
    
    model_config = {
        "strict": True,
        "extra": "forbid",  # Reject unknown fields
    }
```

### Code Comments

- **Docstrings**: Use Google style for all public functions/classes
- **Inline comments**: Explain *why*, not *what*
- **TODOs**: Include issue reference: `# TODO(#123): Fix edge case`

**Example**:

```python
def check_capability(spec: Spec) -> CapabilityReport:
    """Check if spec is compatible with MVP constraints.
    
    Args:
        spec: Validated workflow specification
        
    Returns:
        Report with supported status and issues
        
    Note:
        This performs static analysis only. Runtime capabilities
        are checked during execution.
    """
    # Check agent count first - most common unsupported feature
    if len(spec.agents) != 1:
        ...
```

## Testing Requirements

### Test Coverage

- **Minimum**: 85% code coverage (currently 88%)
- **Target**: 90%+
- **Check coverage**: `uv run pytest --cov=src/strands_cli --cov-report=term-missing`

### Test Structure

Follow existing patterns in `tests/`:

```python
class TestFeatureName:
    """Tests for feature description."""
    
    def test_happy_path(self, fixture1: Type1, fixture2: Type2) -> None:
        """Test successful case with valid inputs."""
        result = function_under_test(fixture1, fixture2)
        assert result.success
        assert result.value == expected
        
    def test_error_case_descriptive_name(self, invalid_fixture: Type) -> None:
        """Test error handling for specific condition."""
        with pytest.raises(SpecificError) as exc_info:
            function_under_test(invalid_fixture)
        assert "expected message" in str(exc_info.value).lower()
```

### Fixture Usage

Use fixtures from `tests/conftest.py`:

- **Valid specs**: `minimal_ollama_spec`, `minimal_bedrock_spec`, `with_tools_spec`
- **Invalid specs**: `missing_required_spec`, `invalid_provider_spec`
- **Unsupported specs**: `multi_agent_spec`, `routing_pattern_spec`
- **Mocks**: `mock_ollama_client`, `mock_bedrock_client`, `mock_strands_agent`, `mock_create_model`
- **Temp dirs**: `temp_output_dir`, `temp_artifacts_dir`

### Mocking Strategy

Use `pytest-mock` and `mocker` fixture:

```python
def test_with_mocking(mocker: Any, mock_strands_agent: Mock) -> None:
    """Test with mocked dependencies."""
    # Mock time.sleep to avoid delays
    mocker.patch("time.sleep")
    
    # Configure mock return value
    mock_strands_agent.run.return_value = "Expected response"
    
    # Call function
    result = run_single_agent(spec, {})
    
    # Verify mock was called
    mock_strands_agent.run.assert_called_once()
```

### Test File Naming

- `test_<module>.py` for unit tests (e.g., `test_schema.py`)
- `test_e2e.py` for end-to-end integration tests
- `test_cli.py` for CLI command tests

### Writing New Tests

1. **Identify test category**: Unit, integration, or E2E?
2. **Create fixtures**: Add to `conftest.py` if reusable
3. **Use descriptive names**: `test_<what>_<when>_<expected>`
4. **Test one thing**: Each test should verify one behavior
5. **Arrange-Act-Assert**: Structure tests clearly

### Schema/Pydantic Drift Prevention

**Critical**: When adding or modifying configuration fields, ensure defaults are synchronized:

1. **Update JSON Schema** (`src/strands_cli/schema/strands-workflow.schema.json`)
   - Add `"default": value` to property definition
   
2. **Update Pydantic Model** (`src/strands_cli/types.py`)
   - Add `Field(default=value)` to model field

3. **Update Drift Test** (`tests/test_schema_pydantic_drift.py`)
   - Add new model to `schema_to_model_map` if needed
   - Run tests to verify: `uv run pytest tests/test_schema_pydantic_drift.py -v`

**Example - Adding a new field:**

```python
# 1. Update JSON Schema
{
  "properties": {
    "new_field": {
      "type": "integer",
      "default": 42,
      "description": "New configuration field"
    }
  }
}

# 2. Update Pydantic Model
class MyConfig(BaseModel):
    new_field: int = Field(42, description="New configuration field")

# 3. Verify drift test passes
# The test automatically validates defaults match
```

**Why this matters**: Mismatched defaults between JSON Schema and Pydantic models can cause:
- Silent configuration drift
- Unexpected behavior when users omit fields
- Validation failures when specs are loaded

The drift tests in `test_schema_pydantic_drift.py` automatically catch these issues.

```python
def test_load_spec_with_invalid_yaml_raises_load_error(
    malformed_spec: Path
) -> None:
    """Test that malformed YAML raises LoadError with helpful message."""
    # Arrange: invalid YAML file (via fixture)
    
    # Act & Assert: should raise LoadError
    with pytest.raises(LoadError) as exc_info:
        load_spec(str(malformed_spec))
    
    # Verify error message is helpful
    assert "yaml" in str(exc_info.value).lower()
    assert "parse" in str(exc_info.value).lower()
```

## Developing Native Tools

Native tools extend the Strands CLI with custom functionality that can be invoked by agents during workflow execution. The CLI uses a registry-based auto-discovery system that makes adding new tools straightforward.

### Quick Start

1. **Create tool file** in `src/strands_cli/tools/<tool_name>.py`
2. **Export `TOOL_SPEC`** dictionary with `name`, `description`, and `inputSchema`
3. **Implement function** matching `TOOL_SPEC["name"]` that returns ToolResult dict
4. **Add tests** in `tests/test_<tool_name>.py` with unit and integration tests
5. **Verify auto-discovery** by running registry check
6. **Submit PR** following the standard process below

### Tool Structure

```
src/strands_cli/tools/
├── __init__.py           # Exports get_registry()
├── registry.py           # Auto-discovery logic (don't modify)
└── your_tool.py          # Your new tool (follows pattern below)
```

### Example Tool

```python
"""Your tool description."""

from typing import Any

# Required: Export TOOL_SPEC for auto-discovery
TOOL_SPEC = {
    "name": "your_tool",  # Must match function name
    "description": "What your tool does",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Parameter description"}
            },
            "required": ["param"]
        }
    }
}

def your_tool(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Tool implementation.
    
    Args:
        tool: Contains toolUseId and input dict
        **kwargs: Additional arguments (unused)
    
    Returns:
        ToolResult dict with toolUseId, status, and content
    """
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    param = tool_input.get("param", "")
    
    try:
        result = f"Processed: {param}"
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result}]
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: {e}"}]
        }
```

### Testing Requirements

Create `tests/test_your_tool.py`:

```python
"""Tests for your_tool."""

import pytest

class TestYourTool:
    def test_your_tool_success(self) -> None:
        """Test successful execution."""
        from strands_cli.tools.your_tool import your_tool
        
        tool = {
            "toolUseId": "test-123",
            "input": {"param": "test value"}
        }
        
        result = your_tool(tool)
        
        assert result["toolUseId"] == "test-123"
        assert result["status"] == "success"
        assert "Processed" in result["content"][0]["text"]
    
    def test_your_tool_spec_format(self) -> None:
        """Test TOOL_SPEC has required fields."""
        from strands_cli.tools.your_tool import TOOL_SPEC
        
        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "your_tool"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC
```

### Verify Auto-Discovery

```powershell
# Check that your tool is discovered
uv run python -c "from strands_cli.tools import get_registry; print([t.id for t in get_registry().list_all()])"
# Should include: [..., 'your_tool']

# Run tests
uv run pytest tests/test_your_tool.py -v

# Validate in a workflow spec
uv run strands validate examples/your-tool-demo.yaml
```

### Using Your Tool in Workflows

```yaml
tools:
  python:
    - your_tool  # Short ID format (recommended)
    # or:
    - strands_cli.tools.your_tool  # Full path format
```

### Detailed Guide

For comprehensive documentation including:
- Architecture overview
- Complete tutorial with "echo" tool example
- `TOOL_SPEC` format specification
- ToolResult contract details
- Advanced patterns (see `python_exec` implementation)
- Integration testing strategies
- Registry mechanics

**See: [`docs/TOOL_DEVELOPMENT.md`](docs/TOOL_DEVELOPMENT.md)**

## Pull Request Process

### Before Submitting

1. **Run full CI pipeline**:

```powershell
.\scripts\dev.ps1 ci
```

This ensures:
- No linting violations
- No type errors
- All tests pass
- Coverage ≥85%

2. **Update documentation**:
   - Add/update docstrings
   - Update README.md if behavior changes
   - Update CHANGELOG.md (see below)

3. **Write clear commit messages**:

```
feat(loader): add support for JSON input files

- Implement JSON parser alongside YAML
- Add validation for JSON schema
- Update loader tests with JSON fixtures

Closes #123
```

Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `test:` Adding tests
- `refactor:` Code restructuring without behavior change
- `chore:` Maintenance tasks

### Creating Pull Request

1. **Create feature branch**:

```bash
git checkout -b feat/your-feature-name
```

2. **Make changes and commit**:

```bash
git add .
git commit -m "feat(module): description"
```

3. **Push to your fork**:

```bash
git push origin feat/your-feature-name
```

4. **Open Pull Request** on GitHub with:
   - Clear title and description
   - Link to related issues
   - Screenshots/examples if UI changes
   - Checklist completion (see template)

### PR Checklist

- [ ] Code follows style guidelines (ruff, mypy pass)
- [ ] All tests pass (`pytest`)
- [ ] Coverage ≥85% maintained
- [ ] New features have tests
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts with main

### Code Review

- Be responsive to feedback
- Keep PRs focused and small when possible
- Explain design decisions in comments
- Reference relevant docs/issues

## Exit Codes Convention

All exit codes are defined in `src/strands_cli/exit_codes.py`:

| Code | Name | Use For |
|------|------|---------|
| 0 | EX_OK | Successful execution |
| 2 | EX_USAGE | Invalid CLI usage (bad flags, missing file) |
| 3 | EX_SCHEMA | JSON Schema validation failure |
| 10 | EX_RUNTIME | Provider/model/tool runtime error |
| 12 | EX_IO | File I/O error (artifacts) |
| 18 | EX_UNSUPPORTED | Feature present but not supported in MVP |
| 70 | EX_UNKNOWN | Unexpected exception |

**Rules**:
1. Always use the correct exit code for error type
2. Test exit codes in CLI tests
3. Document any new exit codes
4. Never use generic `sys.exit(1)` - use named constants

**Example**:

```python
from strands_cli.exit_codes import EX_SCHEMA, EX_OK

try:
    spec = load_spec(path)
except SchemaValidationError as e:
    console.print(f"[red]Validation failed:[/red] {e}")
    sys.exit(EX_SCHEMA)

sys.exit(EX_OK)
```

## Architecture Guidelines

### Module Design

- **Single responsibility**: Each module has one clear purpose
- **File size limit**: Keep files under ~300 lines; split into submodules if exceeded
- **One class/concern per file**: Prefer `loader/yaml.py` + `loader/json.py` over monolithic `loader.py`
- **Clear boundaries**: Respect module separation (schema → loader → capability → runtime → exec)

### Dependency Injection

Prefer passing dependencies explicitly:

```python
# Good: Explicit dependencies
def build_agent(spec: Spec, model: Model) -> Agent:
    return Agent(model=model, prompt=spec.agents["id"].prompt)

# Avoid: Hidden global state
def build_agent(spec: Spec) -> Agent:
    model = get_global_model()  # Bad: implicit dependency
    ...
```

### Error Handling

1. **Use specific exceptions**: Don't catch `Exception` without re-raising
2. **Wrap external errors**: Translate library exceptions to domain exceptions
3. **Provide context**: Include helpful error messages with JSONPointer for schema errors
4. **Log before raising**: Use `structlog` for structured logging

```python
try:
    spec_dict = yaml.safe_load(content)
except yaml.YAMLError as e:
    raise LoadError(
        f"Failed to parse YAML from {path}: {e}"
    ) from e
```

### Performance Considerations

- **Lazy loading**: Don't load all fixtures at startup
- **Caching**: Use `@functools.cache` for expensive operations
- **Async where appropriate**: Future work (not in MVP)

### Security

- **Secrets**: Never log secrets; redact in telemetry
- **Path traversal**: Validate file paths in artifact output
- **Command injection**: Sanitize inputs to shell commands
- **Dependency updates**: Run `uv sync --upgrade` regularly

## CHANGELOG.md

Update `CHANGELOG.md` for all user-facing changes:

```markdown
## [Unreleased]

### Added
- New feature X (#123)

### Changed
- Updated behavior Y (#124)

### Fixed
- Bug Z in module M (#125)

### Deprecated
- Old API endpoint (use new_api instead)
```

Follow [Keep a Changelog](https://keepachangelog.com/) format.

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue with use case description
- **Security**: Email security@example.com (do not open public issue)

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 License.

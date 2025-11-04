# Strands CLI — AI Agent Instructions

## Project Overview

**strands-cli** is a Python 3.12+ CLI that executes declarative agentic workflows (YAML/JSON) on AWS Bedrock/Ollama with schema validation, observability scaffolding, and safe orchestration. The MVP (v0.1.0, 177 tests, 88% coverage) focuses on **single-agent execution** while parsing and validating the full multi-agent workflow schema.

**Key Design Principle**: Parse the full schema, but gracefully stop with actionable errors (exit code 18) on unsupported features rather than silently ignoring them.

**Tech Stack**: Typer (CLI), Pydantic v2 (validation), ruamel.yaml (YAML), jsonschema (Draft 2020-12), Strands Agents SDK, Rich (output), tenacity (retries), structlog (logging). Development: ruff (lint/format), mypy (strict typing), pytest, uv (package manager).

## Architecture & Big Picture

### Three-Phase Execution Model
1. **Load & Validate**: YAML/JSON → JSON Schema validation (Draft 2020-12) → typed `Spec` (Pydantic v2)
2. **Capability Check**: Evaluate MVP compatibility; if unsupported features detected → exit with `EX_UNSUPPORTED (18)` + structured remediation report
3. **Execute**: For single-agent flows → build Strands Agent → run → write artifacts (OTEL scaffolding in place for future)

### Module Structure
```
src/strands_cli/
├── __main__.py           # Typer CLI app with 6 commands
├── types.py              # Pydantic models (Spec, Runtime, Agent, etc.)
├── exit_codes.py         # Exit code constants (EX_OK, EX_SCHEMA, EX_UNSUPPORTED, etc.)
├── config.py             # Pydantic Settings (env vars)
├── schema/
│   └── validator.py      # JSON Schema validation using fastjsonschema
├── loader/
│   ├── yaml_loader.py    # Load YAML/JSON, merge --var variables
│   └── template.py       # Jinja2 template rendering
├── capability/
│   ├── checker.py        # Check MVP compatibility, return CapabilityReport
│   └── reporter.py       # Generate Markdown remediation reports
├── runtime/
│   ├── providers.py      # Bedrock/Ollama client adapters
│   ├── strands_adapter.py # Map Spec → Strands Agent
│   └── tools.py          # Safe tool adapters (allowlisted python, http_executors)
├── exec/
│   └── single_agent.py   # Render prompts, run agent, capture result
├── artifacts/
│   └── io.py             # Write output files with overwrite guards
└── telemetry/
    └── otel.py           # OTEL scaffolding (no-op in MVP; ready for future)
```

### Data Flow (Critical Path)
```
CLI run command
 → parse_variables(--var)
 → load_spec(file, variables) → validate_spec(JSON Schema) → Spec (Pydantic)
 → check_capability(spec) → CapabilityReport
   ├─ unsupported → generate_markdown_report() → exit EX_UNSUPPORTED (18)
   └─ supported → run_single_agent(spec, vars)
       → build_agent(spec.agents[id], tools) → Strands Agent
       → await agent.invoke_async(task_prompt) → result
       → write_artifacts(spec.outputs, result) → files
       → exit EX_OK (0)
```

## Supported Workflow Features (MVP Scope)

**MUST support**:
- Exactly **one agent** in `agents:` map
- Pattern types: `chain` (1 step only) OR `workflow` (1 task only)
- Tools: `python` (allowlist: `strands_tools.http_request`, `strands_tools.file_read`), `http_executors`
- Runtime: `provider=bedrock`, `model_id`, `region`, budgets (logged), retries (exponential backoff)
- Inputs: `--var` overrides with Jinja2 templating
- Outputs: `artifacts` with `{{ last_response }}`
- Skills: inject `id/path` metadata into system prompt (no code exec)
- Secrets: `source=env` only

**MUST reject with EX_UNSUPPORTED (18)**:
- Multiple agents
- `pattern.type` in `{routing, parallel, orchestrator_workers, evaluator_optimizer, graph}` OR `chain.steps > 1` OR `workflow.tasks > 1`
- Skills with executable assets
- `security.guardrails` enforcement (parse but only log)
- `context_policy` execution (parse but only log)
- OTEL tracing activation (parse config but no-op for MVP)

## Development Workflow (Critical Commands)

### PowerShell Automation (Primary on Windows)
```powershell
.\scripts\dev.ps1 test          # Run all 177 tests
.\scripts\dev.ps1 test-cov      # Tests + coverage report → htmlcov/
.\scripts\dev.ps1 lint          # Ruff check
.\scripts\dev.ps1 format        # Ruff format
.\scripts\dev.ps1 typecheck     # Mypy strict mode
.\scripts\dev.ps1 ci            # Full pipeline: lint → typecheck → test-cov
.\scripts\dev.ps1 validate-examples  # Validate all examples/ specs
```

### Direct Commands (Cross-platform)
```bash
uv sync --dev                   # Install all dependencies
uv run pytest                   # Run tests
uv run pytest --cov=src/strands_cli --cov-report=term-missing  # With coverage
uv run ruff check . && uv run ruff format .  # Lint + format
uv run mypy src                 # Type check
uv run strands --help           # Test CLI locally
uv run strands validate examples/single-agent-chain-ollama.yaml
uv run strands run examples/single-agent-chain-ollama.yaml --var topic="test"
```

### Before Every Commit
```powershell
.\scripts\dev.ps1 ci  # MUST pass: lint, typecheck, tests (≥85% coverage)
```

### Exit Codes (CRITICAL — Never use generic exit(1))
| Code | Name | When to Use |
|------|------|-------------|
| 0 | `EX_OK` | Success |
| 2 | `EX_USAGE` | Bad CLI flags/missing file |
| 3 | `EX_SCHEMA` | JSON Schema validation error |
| 10 | `EX_RUNTIME` | Provider/model/tool runtime failure |
| 12 | `EX_IO` | Artifact write/IO error |
| 18 | `EX_UNSUPPORTED` | Feature present but not supported in MVP |
| 70 | `EX_UNKNOWN` | Unexpected exception |

**Pattern**: Always import from `exit_codes.py` and use named constants:
```python
from strands_cli.exit_codes import EX_SCHEMA, EX_OK
sys.exit(EX_SCHEMA)  # NOT sys.exit(3)
```

## Code Conventions & Patterns

### Module Design & File Organization
- **Separation of concerns**: Each module has a single, well-defined responsibility
- **File size limits**: Keep files under ~300 lines; split into submodules if exceeded
- **One class/concern per file**: Prefer `loader/yaml.py` + `loader/json.py` over monolithic `loader.py`
- **Clear boundaries**: `schema/` (validation), `loader/` (parsing), `capability/` (checks), `runtime/` (execution), `telemetry/` (observability), `artifacts/` (I/O)
- **No circular imports**: Use dependency injection and protocol/interface patterns when needed

### Typing & Validation
- **Python 3.12+ only**: Use modern type hints (`str | None`, not `Optional[str]`)
- **Pydantic v2**: All config and spec models must be Pydantic `BaseModel` with strict validation
- **Mypy strict mode**: Enabled in `pyproject.toml`; no `# type: ignore` without comments explaining why
- **Example**:
```python
from pydantic import BaseModel, Field

class Agent(BaseModel):
    """Agent configuration."""
    prompt: str
    tools: list[str] | None = None
    model_id: str | None = Field(None, description="Override runtime model")
```

### Error Handling Patterns
- **Schema validation**: Use `SchemaValidationError` with JSONPointer to exact location
- **Unsupported features**: Generate structured `CapabilityReport` → Markdown/JSON remediation
- **Runtime errors**: Wrap in `ExecutionError`; use `tenacity` for retries
- **Example from `loader/yaml_loader.py`**:
```python
try:
    spec_data = yaml.load(content)
except Exception as e:
    raise LoadError(f"Failed to parse {file_path}: {e}") from e
```

### Rich Console Output (NO print() statements)
```python
from rich.console import Console
console = Console()

console.print("[green]✓ Success[/green]")
console.print(f"[red]Error:[/red] {message}")
console.print(f"[dim]Debug info[/dim]")  # Use with --verbose
```

### Testing Strategy
- **Coverage requirement**: ≥85% (current: 88%); run `.\scripts\dev.ps1 test-cov`
- **Fixture organization**: All shared fixtures in `tests/conftest.py`
  - Valid specs: `minimal_ollama_spec`, `minimal_bedrock_spec`, `with_tools_spec`
  - Invalid: `missing_required_spec`, `invalid_provider_spec`, `malformed_spec`
  - Unsupported: `multi_agent_spec`, `routing_pattern_spec`, `multi_step_chain_spec`
- **Mocking pattern**: Use `mocker` fixture from pytest-mock; see `tests/test_runtime.py`
- **Test naming**: `test_<what>_<when>_<expected>` (e.g., `test_load_spec_with_invalid_yaml_raises_load_error`)
- **Example**:
```python
def test_capability_check_rejects_multiple_agents(multi_agent_spec: Spec) -> None:
    """Test that specs with >1 agent are flagged as unsupported."""
    report = check_capability(multi_agent_spec)
    
    assert not report.supported
    assert len(report.issues) > 0
    assert any("agents" in issue.pointer for issue in report.issues)
```

## Key Files & References

- **Schema**: `strands-workflow.schema.json` (JSON Schema Draft 2020-12) — the source of truth
- **Manual**: `strands-workflow-manual.md` — comprehensive workflow spec docs with examples for all 7 patterns
- **PRD**: `PRD_SingleAgent_MVP.md` — full MVP requirements, scope, and acceptance criteria
- **Stack**: `stack.md` — dependency choices and rationale
- **Config**: `pyproject.toml` — all tool configs (ruff, mypy, pytest, coverage)

## Common Tasks

### Adding a New Command
1. Add command function to `src/strands_cli/__main__.py` using `@app.command()` decorator
2. Use `typer.Argument()` and `typer.Option()` for parameters
3. Use `console.print()` from Rich for output (support `--verbose` flag)
4. Follow exit code conventions (import from `exit_codes.py`)
5. Example pattern:
```python
@app.command()
def mycommand(
    spec_file: Annotated[str, typer.Argument(help="Path to spec")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Command description for --help."""
    try:
        # Load spec
        spec = load_spec(spec_file)
        
        # Process
        result = process_spec(spec)
        
        # Output
        console.print(f"[green]✓ Success[/green]: {result}")
        sys.exit(EX_OK)
        
    except (LoadError, SchemaValidationError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_SCHEMA)
```

### Adding Tool Support
- **Python tools**: Add to `ALLOWED_PYTHON_CALLABLES` in `capability/checker.py`
- **HTTP executors**: Already supported; just add config in spec
- **Example adding Python callable**:
```python
# In capability/checker.py
ALLOWED_PYTHON_CALLABLES = {
    "strands_tools.http_request",
    "strands_tools.file_read",
    "my_new_module.my_tool",  # Add here
}
```

### Writing Tests
1. Create fixture in `tests/conftest.py` if reusable
2. Follow test naming: `test_<feature>_<condition>_<expected>`
3. Use Arrange-Act-Assert pattern
4. Mock external dependencies (Bedrock, Ollama, file I/O)
5. Run with `.\scripts\dev.ps1 test` before committing

## AWS & Secrets

- **Default region**: `us-east-1` (configurable via `STRANDS_AWS_REGION` env or `runtime.region` in spec)
- **Secrets**: MVP only supports `source: env`; production will add Secrets Manager/SSM
- **Bedrock models**: Default to `anthropic.claude-3-sonnet-20240229-v1:0` (override via `runtime.model_id` or `STRANDS_BEDROCK_MODEL_ID`)

## Observability

- **OTEL**: Scaffolding in place (no-op for MVP). Parse config but don't emit spans in MVP.
- **Spans (future)**: `validate`, `plan`, `build_agent`, `tool:<id>`, `llm:completion`
- **Attributes (future)**: `spec.name`, `spec.version`, `runtime.model_id`, `pattern.type`
- **Logs**: Use `structlog` with JSON formatter; wire to OTEL context (future)

## Documentation Style

- **User-facing docs**: Write in Markdown; reference actual file paths in backticks
- **Code comments**: Explain *why*, not *what*; especially for capability checks and error codes
- **Examples**: Always provide runnable examples in `examples/` directory

## Anti-Patterns to Avoid

- ❌ Don't silently ignore unsupported features — always exit with `EX_UNSUPPORTED` and helpful report
- ❌ Don't use `print()` — use Rich `console.print()` for consistent formatting
- ❌ Don't hardcode file paths — use `platformdirs` for cache/config; allow `--out` override
- ❌ Don't catch all exceptions without re-raising — use specific error codes
- ❌ Don't implement multi-agent logic yet — focus on single-agent MVP correctness

## Questions to Clarify

When encountering ambiguity:
1. Check `strands-workflow.schema.json` for validation rules
2. Reference `PRD_SingleAgent_MVP.md` for scope boundaries
3. Consult `strands-workflow-manual.md` for intended behavior
4. If still unclear: Ask user to specify scope (MVP vs future) and update this file

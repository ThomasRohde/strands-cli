# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Strands CLI** is a Python 3.12+ command-line tool for executing declarative agentic workflows defined in YAML/JSON. It provides enterprise-grade orchestration for AI agent workflows with comprehensive observability, strict schema validation, and multi-provider support (AWS Bedrock, Ollama, OpenAI).

**Current Version**: 0.11.0
**Test Coverage**: 82% (795+ tests)
**Language**: Python 3.12+ (strict typing with Mypy)
**Package Manager**: uv

## Essential Development Commands

### Testing & Quality
```bash
# PowerShell (Windows - Primary)
.\scripts\dev.ps1 ci                  # Full CI: lint + typecheck + test-cov
.\scripts\dev.ps1 test                # Run all tests
.\scripts\dev.ps1 test-cov            # Tests with coverage report → htmlcov/
.\scripts\dev.ps1 lint                # Ruff linting
.\scripts\dev.ps1 format              # Auto-format code
.\scripts\dev.ps1 typecheck           # Mypy strict type checking
.\scripts\dev.ps1 validate-examples   # Validate all example specs

# Direct Commands (Cross-platform)
uv sync --dev                         # Install dependencies
uv run pytest                         # Run tests
uv run pytest --cov=src/strands_cli --cov-report=html  # Coverage
uv run ruff check .                   # Lint
uv run ruff format .                  # Format
uv run mypy src                       # Type check
```

### Running Workflows
```bash
# Basic execution
uv run strands run examples/single-agent-chain-ollama.yaml

# With variable overrides
uv run strands run workflow.yaml --var topic="AI" --var format="markdown"

# Debugging
uv run strands run workflow.yaml --debug --verbose

# Validation and planning
uv run strands validate workflow.yaml
uv run strands plan workflow.yaml

# Health check
uv run strands doctor
```

## Architecture & Execution Model

### Three-Phase Execution
1. **Load & Validate**: YAML/JSON → JSON Schema validation → Pydantic `Spec` models
2. **Capability Check**: Evaluate feature compatibility; exit with `EX_UNSUPPORTED` (18) if unsupported features detected
3. **Execute**: Build agents → run workflow pattern → write artifacts

### Async Execution Model (Critical)
All executors run within a **single `asyncio.run()` call** from the CLI:

```python
# In CLI (__main__.py)
result = asyncio.run(run_chain(spec, variables))  # Single event loop

# In executor (exec/chain.py)
async def run_chain(spec: Spec, variables: dict[str, Any]) -> RunResult:
    cache = AgentCache()  # Create once
    try:
        for step in spec.pattern.config.steps:
            agent = await cache.get_or_build_agent(...)  # Reuse cached agents
            result = await invoke_agent_with_retry(agent, ...)  # Direct await
        return RunResult(...)
    finally:
        await cache.close()  # Cleanup HTTP clients
```

**Rules**:
- ✅ Use `async def` for all executor functions
- ✅ Create `AgentCache` at executor start, use throughout, close in finally
- ✅ Use `await` for agent invocations (NOT `asyncio.run()`)
- ❌ Never call `asyncio.run()` inside an executor (only in CLI)
- ❌ Never create agents with `build_agent()` directly (use `AgentCache.get_or_build_agent()`)

### Performance Optimizations
- **Agent Caching**: `AgentCache` provides 90% reduction in multi-step workflow overhead
- **Model Client Pooling**: `@lru_cache` on `create_model()` for Bedrock/Ollama/OpenAI clients
- **Single Event Loop**: One async event loop per workflow execution
- **Resource Cleanup**: HTTP clients properly closed via `cache.close()`

## Module Structure

```
src/strands_cli/
├── __main__.py               # Typer CLI entry point (8 commands)
├── types.py                  # Pydantic v2 models (Spec, Runtime, Agent, etc.)
├── config.py                 # Pydantic Settings (env vars)
├── exit_codes.py             # Exit code constants (0, 2, 3, 10, 12, 18, 70)
├── schema/
│   ├── strands-workflow.schema.json  # JSON Schema Draft 2020-12
│   └── validator.py          # Schema validation logic
├── loader/
│   ├── yaml_loader.py        # YAML/JSON parsing, --var merging
│   └── template.py           # Jinja2 template rendering
├── capability/
│   ├── checker.py            # Feature compatibility checks
│   └── reporter.py           # Markdown remediation reports
├── runtime/
│   ├── providers.py          # Bedrock/Ollama/OpenAI client adapters
│   ├── strands_adapter.py    # Map Spec → Strands Agent
│   ├── context_manager.py    # Context management and notes
│   ├── budget_enforcer.py    # Token/time budget tracking
│   └── tools.py              # Tool adapters (Python, HTTP executors)
├── exec/                     # Async workflow executors
│   ├── single_agent.py       # Single-agent pattern
│   ├── chain.py              # Chain pattern (sequential steps)
│   ├── workflow.py           # Workflow pattern (DAG)
│   ├── routing.py            # Routing pattern (conditional)
│   ├── parallel.py           # Parallel pattern (concurrent branches)
│   ├── evaluator_optimizer.py # Evaluator-optimizer pattern
│   ├── orchestrator_workers.py # Orchestrator-workers pattern
│   ├── graph.py              # Graph pattern (state machines)
│   ├── conditions.py         # JMESPath condition evaluation
│   ├── hooks.py              # Lifecycle hooks
│   └── utils.py              # AgentCache, shared utilities
├── artifacts/
│   └── io.py                 # Artifact writing with path validation
├── telemetry/
│   ├── otel.py               # OpenTelemetry tracing
│   └── redaction.py          # PII redaction engine
├── tools/                    # Native tool registry
│   ├── __init__.py           # Exports get_registry()
│   ├── registry.py           # Auto-discovery from TOOL_SPEC
│   ├── python_exec.py        # Python code execution tool
│   ├── grep.py               # Code search tool
│   ├── notes_manager.py      # Workflow notes tool
│   └── http_executor_factory.py # HTTP request tool factory
└── visualization/
    └── graph_viz.py          # Graph pattern visualization
```

## Supported Workflow Patterns (7 Total)

1. **Chain**: Sequential multi-step execution with context threading
2. **Workflow**: DAG-based parallel task execution with dependency resolution
3. **Routing**: Dynamic agent selection based on input classification
4. **Parallel**: Concurrent branch execution with optional reduce/aggregation
5. **Evaluator-Optimizer**: Iterative refinement with quality gates
6. **Orchestrator-Workers**: Dynamic task delegation to worker pools
7. **Graph**: Explicit control flow with conditionals, loops, cycle protection

All patterns are fully implemented and tested with examples in `examples/`.

## Exit Codes (CRITICAL — Always use named constants)

Import from `exit_codes.py`:

| Code | Name | Use For |
|------|------|---------|
| 0 | `EX_OK` | Success |
| 2 | `EX_USAGE` | Invalid CLI usage (bad flags, missing file) |
| 3 | `EX_SCHEMA` | JSON Schema validation failure |
| 10 | `EX_RUNTIME` | Provider/model/tool runtime error |
| 12 | `EX_IO` | File I/O error (artifacts) |
| 18 | `EX_UNSUPPORTED` | Feature present but not supported |
| 70 | `EX_UNKNOWN` | Unexpected exception |

```python
from strands_cli.exit_codes import EX_SCHEMA, EX_OK
sys.exit(EX_SCHEMA)  # NOT sys.exit(3)
```

## Code Quality Standards

### Type Checking
- **Strict Mypy**: All functions must have type annotations
- **Modern syntax**: Use `str | None`, not `Optional[str]`
- **No `Any`** without explanation
- **Pydantic v2**: All config/spec models must be `BaseModel`

### Testing Requirements
- **Minimum coverage**: 82% (current)
- **Fixtures**: Defined in `tests/conftest.py`
- **Naming**: `test_<what>_<when>_<expected>`
- **Async tests**: Use `@pytest.mark.asyncio`
- **Before committing**: Run `.\scripts\dev.ps1 ci` (must pass)

### Linting & Formatting
- **Tool**: Ruff (both linting and formatting)
- **Line length**: 100 characters
- **Quote style**: Preserve (double quotes preferred)
- **Import order**: stdlib → third-party → first-party

## Key Design Patterns

### Model Client Pooling
```python
from functools import lru_cache
from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeConfig:
    """Hashable runtime configuration for LRU cache."""
    provider: str
    model_id: str
    region: str | None = None

@lru_cache(maxsize=16)
def _create_model_cached(config: RuntimeConfig) -> Model:
    """Create and cache model clients."""
    # Reuses model clients across steps/tasks/branches
```

### Agent Caching
```python
class AgentCache:
    """Cache agents to avoid rebuilding with same config."""
    async def get_or_build_agent(
        self, spec: Spec, agent_id: str, config: AgentConfig
    ) -> Agent:
        # Returns cached agent if exists, builds new one if not
        # 10-step chain with same agent → 1 build (not 10)
```

### Error Handling
- **Use specific exceptions**: Don't catch `Exception` without re-raising
- **Wrap external errors**: Translate library exceptions to domain exceptions
- **Provide context**: Include helpful error messages with JSONPointer for schema errors
- **Rich output**: Use `console.print()` from Rich (NOT `print()`)

## Skills System (Progressive Loading)

Strands CLI supports **skills** - modular prompt extensions that are loaded on-demand, mimicking Claude Code's progressive skill loading behavior. Skills allow agents to dynamically access specialized knowledge without bloating the initial system prompt.

### How Skills Work

1. **Skill Definition**: Define skills in the workflow spec with `id`, `path`, and `description`
2. **Metadata Injection**: Skill metadata is injected into the system prompt with usage instructions
3. **Progressive Loading**: Agent invokes `Skill("skill_id")` to load full skill content on demand
4. **Auto-Injection**: Skill loader tool is automatically injected when skills are present

### Defining Skills in Workflow Spec

```yaml
skills:
  - id: pdf
    path: ./skills/pdf
    description: PDF manipulation toolkit for extracting text, tables, and metadata

  - id: xlsx
    path: ./skills/xlsx
    description: Spreadsheet toolkit with formulas, charts, and data analysis

agents:
  data-processor:
    prompt: |
      You are a data processing assistant.
      When tasks require specialized expertise, load the relevant skill.
```

### Creating a Skill

Skills are directories with a `SKILL.md` (or `README.md`) file:

```
skills/pdf/
├── SKILL.md          # Detailed instructions, code patterns, best practices
└── examples/         # Optional: Example files and usage
```

**SKILL.md Structure**:
```markdown
# PDF Processing Skill

Comprehensive toolkit for PDF document manipulation.

## Capabilities
- Text extraction
- Table extraction
- Metadata reading

## When to Use This Skill
Invoke when you need to extract or manipulate PDF content.

## Code Patterns

\`\`\`python
import PyPDF2

def extract_text_from_pdf(pdf_path):
    # Pattern code here...
\`\`\`

## Best Practices
1. Use context managers for file handling
2. Handle encoding issues
```

### System Prompt Integration

When skills are defined, the system prompt automatically includes:

1. **Usage Instructions**:
   ```
   # How to Use Skills

   When a user's request might be solved by a specialized skill,
   call the Skill tool to load it.

   To use a skill, call: Skill("skill_id")

   Only use skills from the Available Skills list below.
   Do not invoke a skill that's already been loaded.
   ```

2. **Skills List**:
   ```
   # Available Skills

   - **pdf** (path: `./skills/pdf`): PDF manipulation toolkit...
   - **xlsx** (path: `./skills/xlsx`): Spreadsheet toolkit...
   ```

### Implementation Details

- **Tool Factory**: `src/strands_cli/tools/skill_loader.py` creates skill loader tools
- **Auto-Injection**: `strands_adapter.py` automatically injects skill loader when `spec.skills` exists
- **State Tracking**: `AgentCache._loaded_skills` prevents re-loading
- **Path Resolution**: Skill paths resolved relative to spec file directory
- **Security**: Path validation prevents directory traversal attacks

### Examples

See `examples/skills-demo.yaml` for a complete demonstration with PDF and XLSX skills.

## Native Tool Development

Create tools in `src/strands_cli/tools/` with auto-discovery:

```python
"""My tool description."""
from typing import Any

# Required: Export TOOL_SPEC for auto-discovery
TOOL_SPEC = {
    "name": "my_tool",  # Must match function name
    "description": "What my tool does",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"]
        }
    }
}

def my_tool(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Tool implementation."""
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})

    try:
        result = f"Processed: {tool_input.get('param')}"
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result}]
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": str(e)}]
        }
```

See `docs/TOOL_DEVELOPMENT.md` for comprehensive guide.

## Schema/Pydantic Drift Prevention

When adding/modifying configuration fields, ensure defaults are synchronized:

1. **Update JSON Schema** (`src/strands_cli/schema/strands-workflow.schema.json`)
2. **Update Pydantic Model** (`src/strands_cli/types.py`)
3. **Verify drift test** (`tests/test_schema_pydantic_drift.py`)

The drift tests automatically catch mismatched defaults.

## Template Variables in Workflows

Access execution context in prompts and artifacts:

| Variable | Description |
|----------|-------------|
| `{{ last_response }}` | Most recent agent response |
| `{{ steps[0].response }}` | Specific step output (0-indexed) |
| `{{ tasks.task_id.response }}` | Task output by ID (workflow pattern) |
| `{{ branches.branch_id.response }}` | Branch output by ID (parallel pattern) |
| `{{ nodes.node_id.response }}` | Node output by ID (graph pattern) |
| `{{ $TRACE }}` | Complete execution trace (telemetry) |

## Telemetry & Observability

- **OpenTelemetry**: Full OTLP tracing with span instrumentation
- **PII Redaction**: Automatic scrubbing of sensitive data (emails, credit cards, SSN, etc.)
- **Trace Artifacts**: Export execution traces with `--trace` flag or `{{ $TRACE }}` template
- **Debug Logging**: Structured logging with `--debug --verbose`

## Security Features

- **JSON Schema Validation**: Draft 2020-12 with JSONPointer error reporting
- **Sandboxed Templates**: Jinja2 templates block code execution
- **HTTP URL Validation**: SSRF prevention with allowlist/blocklist
- **Path Traversal Protection**: Validated artifact write paths
- **Environment Secrets**: Secrets management via env vars (future: Secrets Manager/SSM)

## Anti-Patterns to Avoid

- ❌ Don't silently ignore unsupported features — exit with `EX_UNSUPPORTED` and helpful report
- ❌ Don't use `print()` — use Rich `console.print()` for consistent formatting
- ❌ Don't call `asyncio.run()` inside executors — maintain single event loop from CLI
- ❌ Don't create agents directly with `build_agent()` — use `AgentCache.get_or_build_agent()`
- ❌ Don't create new model clients repeatedly — rely on `@lru_cache` pooling
- ❌ Don't use generic `sys.exit(1)` — use named constants from `exit_codes.py`

## Important Documentation

- **Schema Reference**: `src/strands_cli/schema/strands-workflow.schema.json` — source of truth
- **Workflow Manual**: `docs/strands-workflow-manual.md` — comprehensive spec docs for all 7 patterns
- **Tool Development**: `docs/TOOL_DEVELOPMENT.md` — native tool creation guide
- **Security Guide**: `docs/security.md` — threat model, attack examples, configuration
- **Contributing**: `CONTRIBUTING.md` — development workflow and code conventions
- **Copilot Instructions**: `.github/copilot-instructions.md` — AI coding assistant guidelines

## Provider Configuration

### AWS Bedrock
- **Default region**: `us-east-1` (override via `STRANDS_AWS_REGION` or `runtime.region`)
- **Default model**: `anthropic.claude-3-sonnet-20240229-v1:0`
- **Credentials**: AWS CLI credentials (`aws configure`)

### Ollama
- **Default host**: `http://localhost:11434`
- **Setup**: Install Ollama, run `ollama serve`, pull model with `ollama pull llama2`

### OpenAI
- **API Key**: Set `OPENAI_API_KEY` environment variable
- **Supported models**: All OpenAI models including GPT-4o, o1-preview, o1-mini

## Common Workflows

### Adding a New Workflow Pattern
1. Update JSON Schema (`src/strands_cli/schema/strands-workflow.schema.json`)
2. Add Pydantic models (`src/strands_cli/types.py`)
3. Create executor (`src/strands_cli/exec/<pattern>.py`)
4. Add executor to CLI (`__main__.py` run command dispatcher)
5. Write tests (`tests/test_<pattern>.py`)
6. Add examples (`examples/<pattern>-*.yaml`)
7. Update documentation (README.md, CHANGELOG.md)

### Running Single Test
```bash
# Specific test file
uv run pytest tests/test_chain.py -v

# Specific test method
uv run pytest tests/test_chain.py::TestChainExecution::test_basic_chain -v
```

### Debugging Failed Tests
```bash
# Show detailed output
uv run pytest tests/test_chain.py -vvs

# Run with coverage
uv run pytest tests/test_chain.py --cov=src/strands_cli/exec/chain --cov-report=term-missing
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `STRANDS_AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `STRANDS_BEDROCK_MODEL_ID` | Default Bedrock model | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `STRANDS_DEBUG` | Enable debug logging | `false` |
| `STRANDS_VERBOSE` | Enable verbose output | `false` |
| `STRANDS_CONFIG_DIR` | Config directory path | OS-specific |
| `STRANDS_MAX_TRACE_SPANS` | Max spans in trace | `1000` |
| `OPENAI_API_KEY` | OpenAI API key | (required for OpenAI) |

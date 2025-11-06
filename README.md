# strands-cli

Execute agentic workflows (YAML/JSON) on AWS Bedrock/Ollama with strong observability, schema validation, and safe orchestration.

**Current Version**: v0.4.0 | 287 tests passing | 83% coverage

## Features

### Core Capabilities (v0.4.0)
- ✅ **Parallel execution pattern** - Concurrent branch execution with optional reduce step for aggregation
- ✅ **Multi-agent workflows** - Support for multiple agents in chain, workflow, routing, and parallel patterns
- ✅ **Routing pattern** - Dynamic agent selection based on input classification with JSON-based routing
- ✅ **Multi-step chain workflows** - Sequential execution with context threading across steps
- ✅ **Multi-task DAG workflows** - Parallel execution with dependency resolution
- ✅ **Template-based context** - Access prior step/task/branch outputs via `{{ steps[n].response }}`, `{{ tasks.<id>.response }}`, `{{ branches.<id>.response }}`
- ✅ **AWS Bedrock, Ollama, and OpenAI** provider support with comprehensive authentication
- ✅ **Schema validation** using JSON Schema Draft 2020-12 with JSONPointer error reporting
- ✅ **Capability checking** with graceful degradation (exit code 18)
- ✅ **Variable substitution** via `--var` flags and Jinja2 templates
- ✅ **HTTP executor tools** with timeout/retry
- ✅ **Python tool allowlist** (`strands_tools.http_request`, `strands_tools.file_read`)
- ✅ **Artifact output** with overwrite protection (`--force` to override)
- ✅ **Skills metadata** injection (no code execution)
- ✅ **Environment secrets** (`source: env`)
- ✅ **Budget enforcement** - Token and time limits with cumulative tracking
- ✅ **Concurrency control** - Semaphore-based limits via `runtime.max_parallel`
- ✅ **Exponential backoff** retry logic per step/task/branch
- ✅ **Rich CLI interface** with progress indicators
- ✅ **OpenTelemetry scaffolding** (no-op in current version, ready for future)

### Performance Optimizations
- ⚡ **Agent Caching** - Agents are reused across steps/tasks/branches with identical configurations, reducing initialization overhead by ~90% in multi-step workflows
- ⚡ **Model Client Pooling** - LRU cache shares model clients (Bedrock/Ollama/OpenAI) across agents, eliminating redundant connection setup
- ⚡ **Single Event Loop** - One async event loop per workflow execution eliminates per-step loop creation/teardown overhead
- ⚡ **Resource Cleanup** - HTTP clients and tool adapters properly closed after execution to prevent resource leaks

### Future Roadmap
- 🚧 Orchestrator-workers pattern
- 🚧 Evaluator-optimizer pattern
- 🚧 Graph pattern with conditional logic
- 🚧 MCP tools integration
- 🚧 Guardrails enforcement
- 🚧 Context policy execution
- 🚧 Full OTEL tracing

## Quick Start

### Prerequisites

Before using strands-cli, ensure you have:

- **Python 3.12+**: Check with `python --version`
- **uv package manager** (recommended): Install from [uv docs](https://github.com/astral-sh/uv)
- **For Ollama workflows**:
  - [Install Ollama](https://ollama.ai/)
  - Start the server: `ollama serve` (runs on http://localhost:11434)
  - Pull a model: `ollama pull gpt-oss` (or your preferred model)
- **For AWS Bedrock workflows**:
  - AWS credentials configured: `aws configure` or environment variables
  - Appropriate Bedrock model access in your AWS region
- **For OpenAI workflows**:
  - OpenAI API key: Set `OPENAI_API_KEY` environment variable
  - Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)

**Verify your setup** with the health check:
```bash
uv run strands doctor
```

### Installation

**From Source** (MVP - not published to PyPI yet):

```bash
git clone https://github.com/ThomasRohde/strands-cli.git
cd strands-cli
uv sync
```

### Basic Usage

#### Validate a workflow spec

```bash
uv run strands validate examples/single-agent-chain-ollama.yaml
```

Output:
```
✓ Spec is valid: single-agent-chain-ollama
  Version: 0
  Agents: 1
  Pattern: chain
```

#### Run a workflow (Ollama)

```bash
# Make sure Ollama is running locally
uv run strands run examples/single-agent-chain-ollama.yaml --var topic="AI ethics"
```

Output:
```
Running workflow: single-agent-chain-ollama

✓ Workflow completed successfully
Duration: 3.45s

Artifacts written:
  • ./artifacts/analysis-ollama.md
```

#### Run a workflow (AWS Bedrock)

```bash
# Requires AWS credentials configured
export AWS_REGION=us-east-1
uv run strands run examples/single-agent-chain-bedrock.yaml --out ./output --force
```

#### Run a workflow (OpenAI)

```bash
# Requires OPENAI_API_KEY environment variable
export OPENAI_API_KEY=your-api-key
uv run strands run examples/single-agent-chain-openai.yaml --var topic="quantum computing"
```

#### Show execution plan

```bash
uv run strands plan examples/single-agent-chain-ollama.yaml
```

Output shows runtime configuration, agents, pattern, and MVP compatibility.

#### Explain unsupported features

```bash
uv run strands explain examples/multi-agent-unsupported.yaml
```

Shows detailed remediation for specs with unsupported features.

#### List MVP-supported features

```bash
uv run strands list-supported
```

Shows all MVP capabilities: providers, patterns, tools, constraints.

#### Check installation health

```bash
uv run strands doctor
```

Verifies Python version, schema file, Ollama connectivity, and dependencies.

### Common Workflows

#### Override variables

```bash
uv run strands run workflow.yaml \
  --var topic="Climate Change" \
  --var output_format="markdown" \
  --out ./results
```

#### Force overwrite artifacts

```bash
uv run strands run workflow.yaml --force
```

#### Verbose output

```bash
uv run strands run workflow.yaml --verbose
```

## Security Considerations

Strands CLI implements defense-in-depth security for user-editable workflow specs. All user-controlled inputs (YAML specs, templates, variables) are treated as potentially malicious.

### Key Security Features

**🔒 Template Sandboxing** - Jinja2 templates use `SandboxedEnvironment` to prevent code execution
```yaml
# ❌ BLOCKED: Python introspection attacks
outputs:
  artifacts:
    - path: "{{ ''.__class__.__mro__ }}"  # Sandbox blocks this
```

**🔒 SSRF Prevention** - HTTP executors validate URLs against blocklist
```yaml
# ❌ BLOCKED: Internal network access
tools:
  http_executors:
    - base_url: "http://169.254.169.254"  # AWS metadata endpoint blocked
```

**🔒 Path Traversal Protection** - Artifact paths validated and sanitized
```bash
# ❌ BLOCKED: Directory escape attempts
strands run spec.yaml --var path="../../etc/passwd"
```

### Security Controls

1. **Sandboxed Jinja2 Templates**: Blocks `__class__`, `__mro__`, `eval`, `__import__`, etc.
2. **HTTP URL Validation**: Blocks localhost, private IPs (RFC1918), cloud metadata endpoints, file:// protocol
3. **Artifact Path Validation**: Rejects absolute paths, blocks `..` traversal, sanitizes components, prevents symlink following
4. **Audit Logging**: All security violations logged at WARNING level with structured fields

### Configuration

**Block additional HTTP endpoints** (production):
```bash
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://internal\\.company\\.com"]'
```

**Enforce HTTP allowlist** (CI/CD):
```bash
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.openai\\.com", "^https://api\\.anthropic\\.com"]'
```

**📖 Full Documentation**: See [`docs/security.md`](docs/security.md) for comprehensive threat model, attack examples, and configuration details.

## Development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- AWS credentials (for Bedrock provider)
- Ollama (for Ollama provider)

### Setup

```bash
# Clone repository
git clone https://github.com/ThomasRohde/strands-cli.git
cd strands-cli

# Install dependencies (including dev tools)
uv sync --dev

# Verify installation
uv run strands --version
uv run strands doctor
```

### Development Commands

**Using PowerShell automation** (recommended on Windows):

```powershell
# Run all tests
.\scripts\dev.ps1 test

# Run tests with coverage
.\scripts\dev.ps1 test-cov

# Run specific test file
.\scripts\dev.ps1 test tests/test_schema.py -v

# Lint code
.\scripts\dev.ps1 lint

# Auto-format code
.\scripts\dev.ps1 format

# Type check
.\scripts\dev.ps1 typecheck

# Full CI pipeline (lint + typecheck + test + coverage)
.\scripts\dev.ps1 ci

# Validate all example specs
.\scripts\dev.ps1 validate-examples
```

**Using uv directly**:

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/strands_cli --cov-report=term-missing

# Lint code
uv run ruff check .

# Auto-format code
uv run ruff format .

# Type check
uv run mypy src

# Run CLI locally
uv run strands --help
uv run strands validate examples/single-agent-chain-ollama.yaml
```

### Project Structure

```
strands-cli/
├── src/strands_cli/          # Main package
│   ├── __main__.py           # CLI entry point (Typer app)
│   ├── config.py             # Pydantic Settings
│   ├── exit_codes.py         # Exit code constants
│   ├── types.py              # Pydantic models for specs
│   ├── schema/               # JSON Schema validation
│   │   └── validator.py      # Compile & validate with fastjsonschema
│   ├── loader/               # YAML/JSON parsing & templating
│   │   ├── yaml_loader.py    # Load & merge variables
│   │   └── template.py       # Jinja2 rendering
│   ├── capability/           # MVP constraint checking
│   │   ├── checker.py        # Validate MVP compatibility
│   │   └── reporter.py       # Generate remediation reports
│   ├── runtime/              # Provider adapters
│   │   ├── providers.py      # Bedrock & Ollama clients
│   │   ├── strands_adapter.py # Map Spec → Strands Agent
│   │   └── tools.py          # Safe tool adapters
│   ├── exec/                 # Workflow execution
│   │   └── single_agent.py   # Single-agent orchestration
│   ├── artifacts/            # Output handling
│   │   └── io.py             # Write artifacts with overwrite guards
│   └── telemetry/            # Observability (scaffolding)
│       └── otel.py           # OTEL no-op (ready for future)
├── tests/                    # Test suite (177 tests, 88% coverage)
│   ├── conftest.py           # Shared fixtures
│   ├── test_schema.py        # Schema validation tests
│   ├── test_loader.py        # YAML/template tests
│   ├── test_capability.py    # Capability checker tests
│   ├── test_runtime.py       # Provider adapter tests
│   ├── test_executor.py      # Execution & artifacts tests
│   ├── test_e2e.py           # End-to-end workflow tests
│   ├── test_cli.py           # CLI command tests
│   └── fixtures/             # Test data
│       ├── valid/            # Valid specs
│       ├── invalid/          # Schema-invalid specs
│       └── unsupported/      # MVP-unsupported specs
├── docs/                     # Documentation
│   ├── strands-workflow-manual.md    # Comprehensive spec manual
│   ├── PRD_SingleAgent_MVP.md        # MVP requirements
│   └── stack.md              # Dependency rationale
├── src/strands_cli/schema/   # Schema validation (source of truth)
│   ├── strands-workflow.schema.json  # Statically bundled with package
│   └── validator.py          # JSON Schema validation
├── examples/                 # Sample workflows
│   ├── single-agent-chain-ollama.yaml
│   ├── single-agent-chain-bedrock.yaml
│   └── multi-agent-unsupported.yaml (for testing)
├── scripts/                  # Automation
│   └── dev.ps1               # PowerShell dev workflow
├── pyproject.toml            # Project config & dependencies
└── README.md                 # This file
```

### Running Tests

```bash
# All tests
uv run pytest

# Specific test class
uv run pytest tests/test_e2e.py::TestOllamaE2E -v

# With coverage report
uv run pytest --cov=src/strands_cli --cov-report=html
# Open htmlcov/index.html

# Watch mode (with pytest-watch)
uv run ptw -- tests/
```

### Code Quality

**Before committing**, ensure all checks pass:

```powershell
.\scripts\dev.ps1 ci
```

This runs:
1. Ruff linting (zero violations)
2. Mypy type checking (strict mode)
3. Pytest with coverage (≥85% required)
4. Example spec validation

**Exit Codes**: See `src/strands_cli/exit_codes.py` for all exit codes (0, 2, 3, 10, 12, 18, 70).

### Adding New Features

1. **Update schema**: Edit `src/strands_cli/schema/strands-workflow.schema.json` (source of truth)
2. **Update types**: Add Pydantic models in `src/strands_cli/types.py`
4. **Write tests first**: Add fixtures and tests
5. **Implement**: Follow existing patterns (see `CONTRIBUTING.md`)
6. **Run CI**: `.\scripts\dev.ps1 ci`
7. **Update docs**: Update `README.md`, `CHANGELOG.md`

## Configuration

Environment variables (prefix: `STRANDS_`):

- `STRANDS_AWS_REGION`: AWS region for Bedrock (default: `us-east-1`)
- `STRANDS_BEDROCK_MODEL_ID`: Default Bedrock model
- `STRANDS_VERBOSE`: Enable verbose logging
- `STRANDS_CONFIG_DIR`: Config directory (uses `platformdirs` by default)

## Supported Workflow Features

| Feature | Support | Notes |
|---------|---------|-------|
| **Agents** | Multiple agents | Single or multi-agent workflows |
| **Patterns** | `chain`, `workflow`, `routing`, `parallel` | Multi-step/task/branch supported |
| **Providers** | `bedrock`, `ollama`, `openai` | Full authentication support |
| **Python Tools** | Allowlist only | `strands_tools.http_request`, `strands_tools.file_read` |
| **HTTP Executors** | ✅ Full support | Timeout, retries, headers |
| **Secrets** | `source: env` only | Secrets Manager/SSM → future |
| **Skills** | Metadata injection | Code execution → future |
| **Budgets** | ✅ Enforced | Cumulative token tracking with warnings/hard limits |
| **Concurrency** | ✅ Semaphore control | Via `runtime.max_parallel` |
| **Retries** | ✅ Exponential backoff | Configurable via `failure_policy` |
| **Artifacts** | Template support | `{{ last_response }}`, `{{ steps[n].response }}`, `{{ tasks.<id>.response }}`, `{{ branches.<id>.response }}` |
| **OTEL** | Parsed (scaffolding) | Full tracing activation → future |

### Unsupported Patterns (exit code 18)
- Orchestrator-workers pattern
- Evaluator-optimizer pattern  
- Graph pattern with conditional logic
- MCP tools (`tools.mcp`)
- Guardrails enforcement
- Context policy execution

For unsupported features, the CLI exits with code 18 and generates a detailed remediation report.

## Troubleshooting

### Schema validation errors (exit code 3)

```bash
uv run strands validate workflow.yaml --verbose
```

Check the error message for JSONPointer to exact location.

### Unsupported features (exit code 18)

```bash
uv run strands explain workflow.yaml
```

Shows detailed remediation (e.g., "Reduce chain.steps to 1").

### Runtime errors (exit code 10)

- **Bedrock**: Verify AWS credentials: `aws sts get-caller-identity`
- **Ollama**: Ensure Ollama is running: `ollama list`

### Provider connection issues

```bash
# Test Bedrock connectivity
aws bedrock-runtime invoke-model --model-id <model-id> --body '{"prompt":"test"}' /tmp/out

# Test Ollama
curl http://localhost:11434/api/tags
```

## License

Apache-2.0

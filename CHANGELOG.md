# Changelog

All notable changes to strands-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Strands SDK API compatibility** - Updated to use correct Strands SDK API:
  - Changed `OllamaModel` initialization from `base_url`/`model` to `host`/`model_id`
  - Changed `Agent` initialization from `instructions` to `system_prompt`
  - Changed agent execution from `.run()` to `await .invoke_async()` with async support
  - Updated all tests to use `invoke_async` instead of `run`
  - Fixed mock fixtures to use `AsyncMock` for async methods
- **Documentation updates** - Updated all documentation to reflect correct API usage:
  - Updated `.github/copilot-instructions.md` to show `invoke_async` in data flow
  - Updated code comments to reference `invoke_async()` return values

## [0.1.0] - 2025-11-04

### Added - MVP Release

#### Core Functionality
- Single-agent workflow execution (chain with 1 step, workflow with 1 task)
- JSON Schema validation with detailed JSONPointer error reporting
- Capability checking with graceful degradation (exit code 18)
- Variable resolution via `--var` flags with Jinja2 template expansion
- Artifact output with `{{ last_response }}` template support
- Overwrite protection for artifacts (use `--force` to override)
- Exponential backoff retry logic for transient errors

#### Provider Support
- AWS Bedrock integration (boto3)
  - Configurable region (default: us-east-1)
  - Model ID override support
  - Bedrock conversation API
- Ollama integration
  - Local Ollama server support
  - Configurable host URL
  - Model selection

#### Tools & Skills
- HTTP executor tools
  - Base URL configuration
  - Custom headers support
  - Timeout and retry configuration
- Python tool allowlist
  - `strands_tools.http_request`
  - `strands_tools.file_read`
- Skills metadata injection
  - Skill ID and path injection into system prompts
  - No code execution (metadata only)

#### Security
- Environment variable secrets (`source: env`)
- Secret key validation
- Safe secret handling in prompts

#### CLI Commands
- `strands run` - Execute workflows with variable overrides
- `strands validate` - Validate specs against JSON Schema
- `strands plan` - Show execution plan (supports `--format=md` and `--format=json`)
- `strands explain` - Show unsupported features with remediation
- `strands list-supported` - List all MVP-supported features
- `strands version` - Show CLI version

#### Developer Tools
- PowerShell automation script (`scripts/dev.ps1`) for Windows
  - `.\scripts\dev.ps1 test` - Run all tests
  - `.\scripts\dev.ps1 test-cov` - Run with coverage
  - `.\scripts\dev.ps1 lint` - Lint code
  - `.\scripts\dev.ps1 format` - Auto-format code
  - `.\scripts\dev.ps1 typecheck` - Type check
  - `.\scripts\dev.ps1 ci` - Full CI pipeline
  - `.\scripts\dev.ps1 validate-examples` - Validate all example specs
- Comprehensive test suite
  - 177 tests passing
  - 88% code coverage (exceeds 85% target)
  - Unit, integration, E2E, and CLI tests
  - 15 test fixtures (valid/invalid/unsupported)
- Modern Python stack
  - uv for dependency management
  - pytest with pytest-mock for testing
  - ruff for linting and formatting (line length 100)
  - mypy for strict type checking
  - Pydantic v2 for configuration and validation

#### Configuration
- Environment variable support with `STRANDS_` prefix
  - `STRANDS_AWS_REGION` - AWS region for Bedrock
  - `STRANDS_BEDROCK_MODEL_ID` - Default Bedrock model
  - `STRANDS_VERBOSE` - Enable verbose logging
  - `STRANDS_CONFIG_DIR` - Config directory path
- Budgets configuration (logged, not enforced)
  - `max_steps`, `max_tokens`, `max_duration_s`
- Failure policy configuration
  - Retry count
  - Exponential backoff (wait_min, wait_max)

#### Observability
- OpenTelemetry scaffolding (no-op in MVP, ready for future activation)
  - Span structure defined
  - Configuration parsing
  - No actual trace emission in MVP
- Rich console output with progress indicators
- Structured error messages with JSONPointer
- Verbose mode for debugging

#### Exit Codes
- `0` (EX_OK) - Successful execution
- `2` (EX_USAGE) - Invalid CLI usage
- `3` (EX_SCHEMA) - JSON Schema validation failure
- `10` (EX_RUNTIME) - Provider/model/tool runtime error
- `12` (EX_IO) - File I/O error
- `18` (EX_UNSUPPORTED) - Feature present but not supported in MVP
- `70` (EX_UNKNOWN) - Unexpected exception

#### Documentation
- JSON Schema: `docs/strands-workflow.schema.json` (Draft 2020-12)
- Manual: `docs/strands-workflow-manual.md` (comprehensive spec guide)
- PRD: `docs/PRD_SingleAgent_MVP.md` (MVP requirements)
- Stack: `docs/stack.md` (dependency rationale)
- README: Quick Start and Development sections
- CONTRIBUTING: Contribution guidelines
- Examples: 5 workflow specs in `examples/`
  - `single-agent-chain-ollama.yaml`
  - `single-agent-chain-bedrock.yaml`
  - `single-agent-workflow-ollama.yaml`
  - `multi-agent-unsupported.yaml` (for testing)
  - `multi-step-unsupported.yaml` (for testing)

### Supported Features (MVP Scope)

#### Patterns
- ✅ `chain` with exactly 1 step
- ✅ `workflow` with exactly 1 task

#### Providers
- ✅ `bedrock` (AWS Bedrock with Anthropic Claude)
- ✅ `ollama` (local Ollama server)

#### Tools
- ✅ `http_executors` (HTTP requests with timeout/retry)
- ✅ `python` tools (allowlist only):
  - `strands_tools.http_request`
  - `strands_tools.file_read`

#### Secrets
- ✅ `source: env` (environment variables)

#### Skills
- ✅ Metadata injection (ID and path)
- ❌ Code execution (future)

#### Budgets
- ✅ Parsing and logging
- ❌ Enforcement (future)

#### Retries
- ✅ Exponential backoff
- ✅ Configurable retry count
- ✅ Configurable wait times (min/max)

#### Guardrails
- ✅ Parsing
- ❌ Enforcement (future)

#### Context Policy
- ✅ Parsing
- ❌ Execution (future)

#### Telemetry
- ✅ Configuration parsing
- ❌ OTEL trace emission (future)

### Not Supported (Exit Code 18)

The following features are parsed by the schema but trigger exit code 18 with remediation reports:

#### Multi-Agent
- ❌ Multiple agents in `agents:` map
- **Remediation**: Keep only one agent

#### Multi-Step/Task Patterns
- ❌ `chain` with more than 1 step
- ❌ `workflow` with more than 1 task
- **Remediation**: Reduce to single step/task

#### Advanced Patterns
- ❌ `routing` - Route to different agents based on conditions
- ❌ `parallel` - Execute agents concurrently
- ❌ `orchestrator_workers` - Orchestrator delegates to workers
- ❌ `evaluator_optimizer` - Evaluate and optimize responses
- ❌ `graph` - DAG-based execution
- **Remediation**: Use `chain` or `workflow` with 1 step/task

#### MCP Tools
- ❌ Model Context Protocol (MCP) tools
- **Remediation**: Use `http_executors` or allowlisted Python tools

#### Skills with Executables
- ❌ Skills with `executable: true` or `assets` containing code
- **Remediation**: Use metadata-only skills

#### Secret Sources
- ❌ `source: aws_secrets_manager`
- ❌ `source: aws_ssm`
- **Remediation**: Use `source: env`

### Breaking Changes

None (initial release)

### Known Issues

None

### Migration Guide

Not applicable (initial release)

### Security

- Secrets are never logged or included in error messages
- All file paths are validated to prevent path traversal
- Tool execution is sandboxed (allowlist only)
- HTTP requests respect timeout/retry limits

### Performance

- Schema validation: <10ms for typical specs
- Workflow execution: Depends on provider latency
- Artifact writing: <5ms for small files

### Dependencies

**Core**:
- Python ≥3.12
- typer ≥0.15.1 (CLI framework)
- pydantic ≥2.10.5 (validation)
- ruamel.yaml ≥0.18.9 (YAML parsing)
- jinja2 ≥3.1.5 (templating)
- fastjsonschema ≥2.21.1 (schema validation)
- strands-agents-sdk ≥0.2.4 (Strands API)
- boto3 ≥1.36.1 (AWS Bedrock)
- ollama ≥0.4.5 (Ollama integration)
- tenacity ≥9.0.0 (retry logic)
- rich ≥13.9.4 (console output)

**Development**:
- pytest ≥8.3.4
- pytest-mock ≥3.15.1
- pytest-cov ≥6.3.0
- ruff ≥0.8.4
- mypy ≥1.14.1

See `pyproject.toml` for complete dependency list.

### Contributors

- Initial MVP implementation

---

## Future Releases

### [0.2.0] - Planned

- Multi-agent workflow support
- Routing pattern implementation
- Full OTEL tracing
- Guardrails enforcement

### [0.3.0] - Planned

- Parallel pattern support
- MCP tools integration
- Context policy execution
- AWS Secrets Manager integration

### [1.0.0] - Planned

- Production-ready release
- All 7 patterns supported
- Complete observability
- Enterprise features

---

[Unreleased]: https://github.com/your-org/strands-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/strands-cli/releases/tag/v0.1.0

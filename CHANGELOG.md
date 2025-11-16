# Changelog

All notable changes to strands-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

TBD

## [0.4.2] - 2025-11-16

### Added
- **Interactive Variable Prompting (`--ask`)** - Prompt for missing required variables interactively
  - `--ask` / `-a` flag for `strands run` command
  - Beautiful Rich UI with panels and color-coded prompts
  - Type validation with visual feedback: `string`, `integer`, `number`, `boolean`
  - Shows parameter descriptions and examples from workflow spec
  - Example workflows: `examples/chain-interactive-prompts-openai.yaml`
  - Variable detection and prompting modules with comprehensive test coverage

- **Web Fetch native tool** - Retrieve web pages as HTML or markdown
  - `strands_cli.tools.web_fetch` with full Strands tool spec
  - Markdown conversion via `markdownify` library
  - Unit tests covering validation, markdown mode, and error handling

- **Configuration Presets** - Simplified workflow configuration
  - Four predefined presets: `minimal`, `balanced`, `long_run`, `interactive`
  - Presets merge with existing config (user values take precedence)
  - Reduces boilerplate for common workflow patterns

- **Context Management** - Fine-grained control over message history
  - Message compaction for long-running workflows
  - Note-taking capability for context preservation
  - JIT tool loading with dynamic tool retrieval
  - Retrieval-augmented generation support

- **Python API & Fluent Builders** - Programmatic workflow construction
  - `Workflow` class for loading and executing workflows from Python
  - `Workflow.from_file()` - Load YAML/JSON workflows
  - `workflow.run()` and `workflow.run_async()` - Execute with variables
  - Fluent builder API for all 7 patterns (ChainBuilder, WorkflowBuilder, ParallelBuilder, etc.)
  - Type-safe builders with IDE autocomplete support

- **Session Management** - Durable execution with crash recovery
  - `--save-session` / `--no-save-session` flags for controlling persistence
  - `--resume <session-id>` to resume chain workflows from checkpoint
  - `strands sessions` command group (list, show, delete)
  - Automatic checkpoint after each step with step skipping on resume

- **Interactive HITL** - Human-in-the-loop workflow execution
  - `terminal_hitl_handler()` for Rich terminal UI
  - Custom handler support for integration with external systems
  - Session-based state management across HITL prompts

- **OpenTelemetry Integration** - Production-ready observability
  - Full OTLP tracing activation (was scaffolding in MVP)
  - Console exporter for local development
  - Auto-instrumentation for httpx and logging
  - Configurable service name, endpoint, sample ratio
  - `--trace` CLI flag for automatic trace artifact generation
  - `{{ $TRACE }}` template variable for trace exports

- **PII Redaction** - Privacy-safe trace exports
  - Automatic redaction of email, credit cards, SSN, phone numbers, API keys
  - Configurable via `telemetry.redact` config
  - Custom redaction patterns for domain-specific secrets

- **Enhanced Debugging** - `--debug` flag with structured logging
  - Structured JSON logging output
  - Variable resolution tracing
  - Template rendering diagnostics
  - Agent cache hit/miss statistics
  - LLM request/response metadata

- **All 7 Workflow Patterns** - Complete pattern support
  - `chain` - Sequential multi-step execution
  - `workflow` - DAG-based task execution with dependencies
  - `routing` - Dynamic agent routing based on classification
  - `parallel` - Concurrent branch execution with optional reduce
  - `evaluator_optimizer` - Iterative refinement with feedback loop
  - `orchestrator_workers` - Task delegation with worker pools
  - `graph` - State machine with conditional transitions

- **Multi-Agent Workflows** - Multiple agents in single workflow
  - Agent map with agent ID references
  - Agent caching and reuse across steps/tasks
  - Per-agent tool overrides
  - Provider-level agent configuration

- **Enhanced Tooling** - Expanded Python tool ecosystem
  - `strands_tools.http_request` - HTTP requests
  - `strands_tools.file_read` - Read file contents
  - `strands_tools.file_write` - Write content to files
  - `strands_tools.calculator` - Mathematical calculations
  - `strands_tools.current_time` - Get current date/time
  - Tool allowlist enforcement with capability checking
  - MCP (Model Context Protocol) tool support

### Changed
- **Version** - v0.4.2 (from v0.1.0)
- **Test Suite** - 795+ tests with 83%+ code coverage
- **Stability** - Production-hardened with concurrency fixes
- **Documentation** - Complete manual with all 7 patterns

### Fixed
- **Thread-safe telemetry** - Proper locking for concurrent workflows
- **Bounded span collection** - FIFO eviction prevents OOM
- **Schema/Pydantic drift** - Automated consistency tests

### Breaking Changes
None - Full backward compatibility with v0.1.0

---

## [0.1.0] - 2025-11-04

### Added - MVP Release

#### Core Functionality
- Single-agent workflow execution
- JSON Schema validation with JSONPointer error reporting
- Capability checking with graceful degradation (exit code 18)
- Variable resolution via `--var` flags with Jinja2 templating
- Artifact output with `{{ last_response }}` template support
- Exponential backoff retry logic

#### Provider Support
- AWS Bedrock integration
- Ollama local server support
- OpenAI integration

#### Tools & Skills
- HTTP executor tools
- Python tool allowlist (http_request, file_read)
- Skills metadata injection

#### CLI Commands
- `strands run` - Execute workflows
- `strands validate` - Validate specs
- `strands plan` - Show execution plan
- `strands explain` - Show unsupported features
- `strands list-supported` - List MVP features
- `strands version` - Show CLI version

#### Documentation
- JSON Schema (Draft 2020-12)
- Comprehensive manual
- 5 example workflows

#### Exit Codes
- `0` (EX_OK), `2` (EX_USAGE), `3` (EX_SCHEMA), `10` (EX_RUNTIME), `12` (EX_IO), `18` (EX_UNSUPPORTED), `70` (EX_UNKNOWN)

---

[Unreleased]: https://github.com/your-org/strands-cli/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/your-org/strands-cli/compare/v0.1.0...v0.4.2
[0.1.0]: https://github.com/your-org/strands-cli/releases/tag/v0.1.0

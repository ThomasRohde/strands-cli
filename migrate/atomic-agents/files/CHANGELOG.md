# Changelog

All notable changes to strands-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Atomic Agent Composition with $ref** - True composability for atomic agents
  - `$ref` field in agent definitions to reference external atomic agent specs
  - Single source of truth: update atomic agent once, all workflows automatically update
  - Override support for `model_id`, `provider`, `tools`, and `inference` parameters
  - Schema path resolution relative to atomic agent file (not composite workflow)
  - Circular reference detection and nested reference prevention
  - Comprehensive validation and error messages
  - Example workflows: `examples/customer-support-intake-composite-openai.yaml`, `examples/atomic-ref-demo-openai.yaml`
  - Updated documentation in `manual/tutorials/atomic-agents.md` and `manual/reference/atomic-quick-reference.md`
  - Test suite: `tests/test_agent_references.py` (8 comprehensive tests)

### Changed
- Extended `Agent` Pydantic model with optional `ref` field (aliased as `$ref`)
- Updated JSON Schema to support `oneOf` pattern for inline vs reference agent definitions
- Agent loader now resolves `$ref` before schema validation

## [0.5.0] - 2025-01-16

### Added
- **Progressive Skills Loading** - Claude Code-like dynamic skill loading system
  - `Skill("skill_id")` tool for on-demand loading of detailed skill instructions
  - Reduces initial prompt size by only including skill metadata
  - Auto-injection of skill loader tool when `skills` are defined in workflow spec
  - State tracking in `AgentCache` to prevent duplicate skill loading
  - Path resolution support for relative skill paths
  - Fallback to README.md if SKILL.md not found
  - Schema support for skills with `id`, `path`, and `description` fields
  - Example workflow: `examples/skills-demo.yaml`
  - Official Anthropic skills included: `pdf`, `xlsx`, `docx`, `pptx`
  - Comprehensive unit tests for skill loader functionality

### Changed
- Enhanced system prompt builder to inject skills metadata and usage instructions
- Updated `AgentCache` to track loaded skills across workflow execution
- Modified YAML loader to attach `_spec_dir` for skill path resolution
- Updated JSON Schema to support skills configuration

### Documentation
- Added Skills System section to CLAUDE.md
- Created README in examples/skills with proper attribution to Anthropic
- Updated workflow examples to demonstrate progressive skill loading

## [0.4.3] - 2025-11-16

### Added
- **Tavily AI-powered search tool** - Advanced web search and research capability
  - `strands_cli.tools.tavily_search` with full Strands tool spec
  - Deep research mode for comprehensive information gathering
  - Related example: `examples/tavily-deep-research-demo.yaml`

- **Enhanced context compaction** - Improved adaptive message preservation
  - Smarter message history management for long-running workflows
  - Better context retention during compaction

### Changed
- **DuckDuckGo search tool** improvements
  - Updated to utilize shared research notes for enhanced collaboration
  - Better context retention across search operations

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

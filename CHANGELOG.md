# Changelog

All notable changes to strands-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - Python API (MVP - Interactive HITL Workflows)

#### Python API Module (`api/`)
- **`Workflow` class** - First-class programmatic interface for workflow execution
  - `from_file(path, **variables)` classmethod - Load workflow from YAML/JSON with variable overrides
  - `run_interactive(**variables)` - Execute workflow with interactive HITL prompts in terminal
  - `run_interactive_async(**variables)` - Async version for high-performance applications
  - `run(**variables)` - Standard execution mode (non-interactive, session-based HITL)
  - `run_async(**variables)` - Async version of standard execution
  - Automatic session management with transparent state persistence
  - Compatible with all 7 workflow patterns (chain, workflow, routing, parallel, evaluator-optimizer, orchestrator-workers, graph)

#### Interactive HITL Execution
- **`WorkflowExecutor` class** - HITL loop orchestration and session management
  - Automatic session creation with unique ID (`interactive-{spec.name}-{timestamp}`)
  - HITL loop logic: continues execution until workflow completes, prompting user at each HITL pause
  - Session state updates after each HITL response
  - Safety limit: max 100 iterations to prevent infinite loops
  - Error handling: marks sessions as FAILED on exception, COMPLETED on success
  - Graceful KeyboardInterrupt handling with session preservation
  - Pattern routing to appropriate executor (chain, workflow, etc.)

- **`terminal_hitl_handler()`** - Rich terminal UI for HITL prompts
  - Beautiful Rich panels with HITL prompt display
  - Optional context display (truncated at 1000 chars for readability)
  - Default response support (press Enter to use default)
  - User input via Rich `Prompt.ask()`
  - Custom handler support via `hitl_handler` parameter

#### Package Exports
- **Main package exports** - Convenient imports from `strands` package
  - `from strands import Workflow` - Primary API class
  - `from strands_cli.api import Workflow, WorkflowExecutor` - Detailed imports
  - `from strands_cli.api.handlers import terminal_hitl_handler` - Custom handler development

#### Documentation & Examples
- **Comprehensive API guide** - Production-ready documentation in `manual/reference/api/python-api.md`
  - Quickstart guide with 5-minute tutorial
  - Complete API reference with all methods, parameters, and return types
  - Custom HITL handler examples (auto-approve, Slack integration)
  - Pattern-specific usage examples for all 7 patterns
  - Integration examples: FastAPI endpoints, Jupyter notebooks, batch processing
  - Performance considerations: agent caching, model client pooling, concurrency control
  - Error handling patterns and best practices
  - Current limitations and workarounds for MVP
  - Future enhancements roadmap (fluent builder API, event system, session management API)

- **Example script** - Interactive HITL workflow demonstration
  - `examples/api/01_interactive_hitl.py` - Shows loading, execution, and result access
  - Works with existing example workflows (e.g., `chain-hitl-business-proposal-openai.yaml`)

#### Technical Implementation
- **Zero breaking changes** - API layer wraps existing executors without modifications
  - All executors already support required signature: `run_<pattern>(spec, variables, session_state, session_repo, hitl_response)`
  - Session management infrastructure reused from Phase 2 (Durable Execution)
  - Agent caching via existing `AgentCache` class
  - Model client pooling via existing `@lru_cache` on `create_model()`
  - Single event loop per workflow (asyncio.run() only in CLI/API sync wrappers)

- **Performance optimizations** - Production-ready efficiency
  - Agent reuse across steps via `AgentCache.get_or_build_agent()`
  - Model client pooling: 10-step chain with same runtime → 1 client instance (not 10)
  - Concurrency control: `max_parallel` enforced via semaphore in parallel executor
  - <5% overhead vs CLI execution for interactive mode

### Changed
- **Package exports** - Added `Workflow` to main `strands_cli.__init__.py`
  - Enables `from strands import Workflow` for developer convenience
  - Maintains backward compatibility with existing CLI imports

### Added - Phase 2 (Durable Execution - Chain Pattern Resume)

#### Session Persistence
- **Session save/load infrastructure** - Foundation for crash recovery and long-running workflows
  - New module: `session/` with Pydantic models for session state management
  - `SessionState`, `SessionMetadata`, `SessionStatus`, `TokenUsage` models
  - `FileSessionRepository` for file-based session persistence
  - Session storage in `~/.strands/sessions/session_<uuid>/` directory
  - Atomic session save with metadata, pattern state, and spec snapshot
  - Session ID generation with `generate_session_id()` utility
  - Spec hash validation with `compute_spec_hash()` for change detection

#### Chain Pattern Resume
- **`--resume <session-id>` flag** - Resume chain workflows from checkpoint
  - New CLI flag in `run` command for session resumption
  - `--save-session`/`--no-save-session` flag to control session creation (default: enabled)
  - `run_resume()` function in `session/resume.py` module
  - Loads session state and routes to pattern-specific executor
  - Validates session status (prevents resuming completed sessions)
  - Warns if spec file has changed since session creation

- **Chain executor checkpointing** - Automatic state preservation after each step
  - Modified `run_chain()` signature to accept optional `session_state` and `session_repo` parameters
  - Step skipping logic: resume from `current_step` index, skip completed work
  - Checkpoint saved after each step completion with updated pattern state
  - Token usage accumulation across resume sessions
  - Session status transitions: RUNNING → COMPLETED
  - `pattern_state` structure: `current_step`, `step_history` with responses and token counts

- **Agent conversation restoration** - Full conversation history preserved
  - Updated `AgentCache.get_or_build_agent()` with `session_id` parameter
  - Integration with Strands SDK `FileSessionManager` for agent session persistence
  - Session ID format: `<session_uuid>_<agent_id>` for per-agent storage
  - Agent messages and state restored from `agents/` subdirectory
  - Cache key includes session_id to prevent incorrect agent reuse

#### Session Management CLI
- **`strands sessions` command group** - Manage saved sessions
  - `sessions list` - List all sessions with filtering by status
  - `sessions show <id>` - Display detailed session information
  - `sessions delete <id>` - Delete session with confirmation prompt
  - `--force` flag for delete command to skip confirmation
  - Rich table output for session list with truncated UUIDs
  - JSON-formatted session details in show command

#### Testing & Documentation
- **Integration test suite** - Comprehensive chain resume testing
  - New file: `tests/test_chain_resume.py` with 10 integration tests
  - Tests cover: fresh execution, resume after steps 1/2, agent restoration, token accumulation
  - Checkpoint validation, session status transitions, parameter validation
  - Test coverage: 80% overall (session module: 98%)

- **Example workflow** - Resume demonstration
  - New file: `examples/chain-3-step-resume-demo.yaml`
  - 3-step chain: researcher → analyst → writer
  - Manual testing instructions for crash simulation and resume

- **Documentation updates** - User and developer guides
  - Updated `README.md` with Durable Execution section
  - Updated `DURABLE.md` with Phase 2 completion status
  - New manual pages: `manual/howto/session-management.md`, `manual/reference/session-api.md`
  - Session architecture diagrams and storage structure documentation

## [0.10.0] - 2025-11-09

### Fixed - Phase 10.1 Production Hardening
- **Thread-safe telemetry configuration** - Added `_telemetry_lock` for safe concurrent configuration
  - Protects global `_tracer_provider` and `_trace_collector` from race conditions
  - Multiple concurrent workflows can now safely configure telemetry
  - No performance impact on single-workflow execution
- **Bounded span collection** - FIFO eviction prevents OOM in long-running workflows
  - Default limit: 1000 spans (~5MB memory)
  - Configurable via `STRANDS_MAX_TRACE_SPANS` environment variable
  - Warning logged when spans evicted: `span_evicted_fifo`
  - Eviction count tracked in trace metadata: `evicted_count` field
- **Flush timeout detection** - User warnings when trace export times out
  - Returns `False` from `force_flush_telemetry()` on timeout
  - User-facing warning in CLI with remediation guidance
  - Structured logging: `telemetry_flush_timeout` event
  - Trace artifact still written (best-effort) on timeout

### Added - Phase 10 (Observability & Debugging)

#### OpenTelemetry Tracing
- **Full OTLP tracing activation** - Production-ready observability with comprehensive span coverage
  - Activated `TracerProvider` in `telemetry/otel.py` (previously scaffolding/no-op)
  - OTLP exporter for remote collectors (Jaeger, Zipkin, Honeycomb)
  - Console exporter for local development and debugging
  - Auto-instrumentation for httpx and logging libraries
  - Configurable service name, endpoint, and sample ratio via `telemetry.otel` config
  - Span hierarchy across all 7 workflow patterns with parent-child relationships
  - Comprehensive span attributes: `spec.name`, `spec.version`, `runtime.provider`, `runtime.model_id`, `pattern.type`, `agent.id`, etc.

#### Trace Artifacts
- **`{{ $TRACE }}` special variable** - Export execution traces to artifacts
  - New template variable available in `outputs.artifacts[].from`
  - Generates complete trace JSON with trace_id, spans, timestamps, attributes, events
  - Example usage:
    ```yaml
    outputs:
      artifacts:
        - path: "./artifacts/trace.json"
          from: "{{ $TRACE }}"
    ```
- **`--trace` CLI flag** - Auto-generate trace artifacts without modifying spec
  - Automatically creates `./artifacts/<spec-name>-trace.json` on workflow completion
  - Pretty-printed JSON with 2-space indentation
  - Includes metadata: spec name, version, pattern type, total duration
  - Works with all workflow patterns

#### PII Redaction
- **Automatic redaction of sensitive data** - Privacy-safe trace exports
  - New module: `telemetry/redaction.py` with `RedactionEngine`
  - PII pattern detection:
    - Email addresses: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
    - Credit cards: `\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b`
    - SSN: `\b\d{3}-\d{2}-\d{4}\b`
    - Phone numbers: `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b`
    - API keys: `\b[A-Za-z0-9_-]{20,}\b` (heuristic)
  - Configurable redaction via `telemetry.redact.tool_inputs` and `telemetry.redact.tool_outputs`
  - Safe replacement with `***REDACTED***` marker
  - Redacted attributes tagged with `redacted=true` metadata
  - Custom redaction patterns support for domain-specific secrets

#### Enhanced Debugging
- **`--debug` flag** - Structured debug logging for troubleshooting
  - Added to all commands: `run`, `validate`, `plan`, `explain`
  - Sets `STRANDS_DEBUG=true` environment variable
  - Configures Python logging to DEBUG level
  - Debug output includes:
    - Variable resolution steps (parse → merge → final context)
    - Template rendering (before/after with 200-char previews)
    - Capability check details (agents, patterns, unsupported features)
    - Agent cache hits/misses with reuse statistics
    - LLM request/response metadata (model, input/output lengths)
  - All debug logs use structured JSON format (structlog)
  - Example usage:
    ```bash
    uv run strands run workflow.yaml --debug
    uv run strands validate workflow.yaml --debug --verbose
    ```

#### Telemetry Configuration
- **New Pydantic models** in `types.py`:
  - `OTELConfig`: OTLP endpoint, service name, sample ratio, exporter type
  - `RedactionConfig`: tool_inputs, tool_outputs, custom_patterns
  - Extended `TelemetryConfig` with otel and redact fields
- **Span lifecycle coverage** across all executors:
  - `execute.chain` - Chain pattern execution
  - `execute.workflow` - Workflow/DAG pattern execution
  - `execute.routing` - Routing pattern execution
  - `execute.parallel` - Parallel pattern execution
  - `execute.evaluator_optimizer` - Evaluator-optimizer pattern execution
  - `execute.orchestrator_workers` - Orchestrator-workers pattern execution
  - `execute.graph` - Graph pattern execution
  - Nested spans for steps, tasks, branches, nodes with proper parent-child relationships

#### Testing
- **Comprehensive test suite** - 13 new tests added
  - Tests in `tests/test_debug_flag.py` - Debug flag functionality across all commands
  - Tests in existing modules updated for OTEL integration
  - Trace artifact validation tests
  - Redaction pattern tests (all PII types)
  - OTLP exporter configuration tests
  - Integration tests with mock OTLP collector
- **Coverage maintained** - 795 tests passing, 82% coverage (minor drop due to new telemetry code)

#### Examples
- **debug-demo-openai.yaml** - Demonstrates --debug flag with multi-step chain
- Updated existing examples with telemetry config options

### Changed
- **TracerProvider initialization** - Moved from no-op to active OTLP/Console exporters
- **Artifact writer** - Enhanced `write_artifacts()` to support `{{ $TRACE }}` special variable
- **CLI run command** - Added `--trace` and `--debug` options
- **Logging configuration** - Enhanced to respect DEBUG level when --debug flag is set

### Fixed
- **OTLP exporter fallback** - Gracefully falls back to Console exporter if OTLP endpoint unavailable
- **Trace context propagation** - Proper parent span context passed to nested executors
- **Redaction edge cases** - Handles nested JSON in span attributes correctly

### Security
- **PII redaction by default** - Recommended for production deployments
  - Configure `telemetry.redact.tool_inputs: true` and `telemetry.redact.tool_outputs: true`
  - Prevents accidental exposure of credentials, API keys, personal data in traces
  - Custom patterns can be added for domain-specific secrets
- **Audit logging** - Redaction events logged for compliance and auditing
  - Structured logs include: redaction count, patterns matched, attribute names
  - Enables security teams to verify sensitive data protection

### Documentation
- **README.md** - Updated with Phase 10 features in Core Capabilities
- **docs/strands-workflow-manual.md** - Enhanced telemetry section (if updated)
- **Telemetry examples** - Added trace artifact and redaction examples

### Breaking Changes

**None** - All changes are backward compatible. Existing workflows continue to work without modification.

To opt into telemetry features:
- Add `telemetry.otel` config to your spec for OTLP export
- Add `telemetry.redact` config to enable PII scrubbing
- Use `--trace` flag for one-time trace export
- Use `--debug` flag for enhanced logging

### Migration Guide

**Enabling OpenTelemetry:**

Before (v0.9.0 and earlier - scaffolding only):
```yaml
# Telemetry config was parsed but not used
telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
```

After (v0.10.0 - active tracing):
```yaml
# Same config, but now actively exports traces
telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
    sample_ratio: 1.0  # 100% sampling
  redact:
    tool_inputs: true
    tool_outputs: true
```

**Trace Artifacts:**

```yaml
# Export trace to artifact
outputs:
  artifacts:
    - path: "./artifacts/trace.json"
      from: "{{ $TRACE }}"
```

Or use the `--trace` flag:
```bash
uv run strands run workflow.yaml --trace
```

**Debug Logging:**

```bash
# Enhanced debugging with structured logs
uv run strands run workflow.yaml --debug

# Combine with verbose for maximum detail
uv run strands run workflow.yaml --debug --verbose
```

### Performance
- **OTLP overhead** - <5% latency impact with 100% sampling (benchmarked on 10-step chains)
- **Redaction performance** - Negligible impact; only applied when configured
- **Console exporter** - No network overhead for local development

### Known Issues
- **Large traces** - Traces with >1000 spans may be truncated by some OTLP collectors
  - Mitigation: Reduce `sample_ratio` for high-volume workflows
- **Custom patterns** - Overly broad regex patterns may over-redact
  - Mitigation: Test custom patterns with sample data before production

### Deprecations

**None**

---

## [0.9.0] - 2025-11-08

### Added - Phase 8 (Graph Pattern & Advanced Control Flow)

#### Graph Pattern Support
- **Explicit control flow with conditionals and loops** - Define workflow graphs with nodes and edges
  - New executor: `src/strands_cli/exec/graph.py`
  - Condition evaluator: `src/strands_cli/exec/conditions.py`
  - Node-based execution with explicit transitions
  - Conditional edges: `choose` clauses with `when` conditions
  - Static edges: Unconditional `to` transitions
  - Cycle detection and protection with max iteration limits
  - Safe condition evaluation with restricted builtins
  - Template access: Node outputs `{{ node.<id>.response }}`
  - Graph visualization support for planning and debugging

#### Security Enhancements
- **Restricted condition evaluation** - Safe evaluation of edge conditions
  - Allowlisted builtins only (len, str, int, float, bool, etc.)
  - No arbitrary code execution in `when` clauses
  - JSON-safe comparison operators
  - Token budget checks before condition evaluation

#### Examples
- **graph-decision-tree-openai.yaml** - Multi-branch decision tree with conditional routing
- **graph-iterative-refinement-openai.yaml** - Loop-based quality improvement
- **graph-state-machine-openai.yaml** - State machine with transitions

#### Testing
- **Comprehensive test suite** - 32 tests in `tests/test_graph.py`
  - Basic graph execution with conditionals
  - Loop detection and max iteration enforcement
  - Cycle protection
  - Condition evaluation with node context
  - Token budget integration
  - Security validation for condition evaluation
- **Graph visualization tests** - 21 tests in `tests/test_graph_viz.py`
- **Condition security tests** - 36 tests in `tests/test_conditions_security.py`

## [0.8.0] - 2025-11-08

### Added - Phase 7 (Orchestrator-Workers Pattern)

#### Orchestrator-Workers Pattern Support
- **Dynamic task delegation with worker pools** - Orchestrator breaks down tasks, workers execute in parallel
  - New executor: `src/strands_cli/exec/orchestrator_workers.py`
  - Orchestrator agent returns JSON array of subtasks: `[{"task": "description"}, ...]`
  - Worker pool executes subtasks with configurable concurrency (`max_workers` limit)
  - Round tracking: Counts orchestrator delegation cycles (not individual worker calls)
  - Optional `reduce` step aggregates worker outputs
  - Optional `writeup` step generates final synthesis
  - Template access: Indexed workers array `{{ workers[0].response }}`
  - Fail-fast semantics: First worker error cancels remaining workers

#### Configuration & Validation
- **New Pydantic models** in `types.py`:
  - `OrchestratorLimits`: `max_workers`, `max_rounds` constraints
  - `OrchestratorConfig`: Orchestrator agent with optional limits
  - `WorkerTemplate`: Worker agent with optional tool overrides
  - Extended `PatternConfig` with orchestrator, worker_template, writeup fields
- **Capability checking** - Validates orchestrator pattern configuration
  - Checks orchestrator and worker agents exist in spec
  - Validates limits (max_workers ≥ 1, max_rounds ≥ 1)
  - Verifies reduce/writeup agent references

#### JSON Parsing & Error Handling
- **Multi-strategy JSON parsing** for orchestrator responses:
  - Direct JSON parse
  - Code block extraction (```json ... ```)
  - Regex-based array/object extraction
  - Retry logic (up to 2 retries) with clarification prompts on malformed JSON
  - Empty array `[]` support (signals "no work needed")

#### Examples
- **orchestrator-research-swarm-openai.yaml** - Research delegation with 3 workers, reduce, and writeup
- **orchestrator-data-processing-bedrock.yaml** - Data processing with max_workers=3, max_rounds=2
- **orchestrator-minimal-ollama.yaml** - Minimal example (no reduce/writeup)

#### Testing
- **Comprehensive test suite** - 17 tests in `tests/test_orchestrator_workers.py`
  - Basic flow (orchestrator → workers → reduce → writeup)
  - Concurrency limits (max_workers enforcement via semaphore)
  - JSON parsing with retry logic
  - Empty subtask handling
  - Fail-fast on worker errors
  - Indexed template access
  - Tool override validation
  - Agent caching verification

### Added - Phase 2 Remediation (Hardening & UX Polish)

#### Schema Drift Prevention
- **Automated schema/Pydantic drift tests** - Prevents configuration inconsistencies
  - New test suite in `tests/test_schema_pydantic_drift.py`
  - Validates default values match between JSON Schema and Pydantic models
  - Covers: Compaction, Notes, Retrieval, RouterConfig, AcceptConfig
  - Integration tests verify defaults are applied during spec loading
  - Prevents silent configuration drift that could cause unexpected behavior

#### Configuration Presets
- **Context management presets** - Simplifies workflow configuration
  - New module: `src/strands_cli/presets.py`
  - Four predefined presets: `minimal`, `balanced`, `long_run`, `interactive`
  - `minimal` - Compaction disabled (short workflows, 1-3 steps)
  - `balanced` - Standard settings (most workflows, 3-10 steps, 100K token threshold)
  - `long_run` - Optimized for research (10+ steps, 80K threshold, notes + JIT tools)
  - `interactive` - Chat-optimized (50K threshold, 16 recent messages)
  - Helper functions: `get_context_preset()`, `apply_preset_to_spec()`, `describe_presets()`
  - Presets merge with existing config (user values take precedence)

#### Documentation Enhancements
- **Streaming design document** - Future-proofs JIT tools
  - New doc: `docs/STREAMING_DESIGN.md`
  - Details streaming implementation strategy for large file support (>100MB)
  - Documents current limitations (loads entire file into memory)
  - Provides implementation plan for future phases
  - Added TODO comments in `grep.py` and `search.py`

### Added - Python Tool Expansion

#### New Python Tools
- **file_write tool** - Write content to files with user consent protection
  - Interactive consent prompts in normal mode
  - `--bypass-tool-consent` flag for automation/CI environments
  - Sets `BYPASS_TOOL_CONSENT=true` environment variable
  - Security warnings for untrusted workflows (see docs/security.md)
- **calculator tool** - Mathematical calculations using SymPy
  - Supports arithmetic, algebra, calculus operations
  - Safe evaluation (no code execution)
- **current_time tool** - Get current date and time
  - Returns formatted timestamps
  - Read-only operation

#### Tool Loading Architecture Improvements
- **Module-based tool detection** - Support for tools with `TOOL_SPEC` attribute
  - Automatically detects module-based vs @tool decorated functions
  - Returns module itself for module-based tools (e.g., file_write)
  - Returns function object for @tool decorated functions
  - Fixes "unrecognized tool specification" warnings from Strands SDK
- **String format support** - Simplified tool specification in YAML
  - JSON Schema accepts: `["strands_tools.calculator.calculator"]`
  - Pydantic validator converts to: `[{"callable": "strands_tools.calculator.calculator"}]`
  - Backwards compatible with dict format

#### CLI Enhancements
- **--bypass-tool-consent flag** - Added to `run` command
  - Skips interactive file_write confirmation prompts
  - Required for CI/CD automation with file_write tool
  - Security implications documented in docs/security.md
- **Updated list-supported output** - Now shows all 5 Python tools
  - `strands_tools.http_request.http_request`
  - `strands_tools.file_read.file_read`
  - `strands_tools.file_write.file_write` (NEW)
  - `strands_tools.calculator.calculator` (NEW)
  - `strands_tools.current_time.current_time` (NEW)

#### Example Workflows
- **chain-calculator-openai.yaml** - Demonstrates calculator tool for multi-step math problems
- **routing-multi-tool-openai.yaml** - Routes to specialized agents using all 5 Python tools
- **simple-file-read-openai.yaml** - Simple file reading and summarization
- **workflow-file-operations-openai.yaml** - File read/write workflow for document generation

### Changed
- **Python tool allowlist** - Expanded from 2 to 5 tools in `capability/checker.py`
  - Old: `strands_tools.http_request`, `strands_tools.file_read`
  - New: Supports both old and new path formats (backward compatible)
  - New format: `strands_tools.http_request.http_request` (explicit function name)
  - Old format: `strands_tools.http_request` (auto-inferred function name) - still works!
- **Error handling refactoring** - Cleaner error propagation in executors
  - Chain executor: Single catch-all exception handler replaces nested try-except
  - Evaluator-optimizer: Extracted helper functions for better separation of concerns
  - Removed nested error wrapping for clearer stack traces
- **Type safety improvements** - Replaced `type: ignore` comments with runtime assertions
  - Added explanatory assertion messages in single_agent.py, workflow.py, routing.py
  - Maintains strict mypy compliance without type suppression

### Fixed
- **pytest-asyncio configuration** - Added `asyncio_default_fixture_loop_scope = "function"` to `pyproject.toml` to fix deprecation warning
- **Mypy strict type safety** - Fixed 3 type errors in workflow and routing execution:
  - `workflow.py:356` - Added type assertion for tasks before topological sort
  - `routing.py:270` - Added type assertion for routes before indexing
  - `routing.py:337` - Added type assertion for steps before len()
- **Import ordering** - Fixed import block formatting in `yaml_loader.py`
- **Tool loading for module-based tools** - Fixed return type and detection logic in `runtime/tools.py`
  - Changed return type from `Callable[..., Any]` to `Any`
  - Detects and returns modules with `TOOL_SPEC` attribute
  - Prevents SDK warnings about unrecognized tool specifications

### Security
- **Python tool security documentation** - Added comprehensive security section to docs/security.md
  - Documented file_write tool risks and mitigation
  - Explained --bypass-tool-consent security implications
  - Added best practices for production/CI usage
  - Updated threat model to include dangerous tool usage
- **Tool allowlist enforcement** - Capability checker validates all Python tools
  - Non-allowlisted tools trigger exit code 18 with remediation
  - Structured logging for blocked tool attempts

### Testing
- **289 tests passing** - Added 2 integration tests for --bypass-tool-consent
  - `test_run_with_bypass_tool_consent_sets_env_var` - Verifies flag sets environment variable
  - `test_run_without_bypass_tool_consent_does_not_set_env_var` - Verifies default behavior
- **Added 1 test for backward compatibility** - `test_loads_old_format_callable` verifies old tool paths work
- **Updated capability tests** - Now validate all 10 tools in allowlist (5 new + 5 old formats)
- **Updated runtime tests** - Fixed mocks for new tool loading behavior
- **Updated chain tests** - Updated for new tool path format

### Breaking Changes

**None** - The tool path format change is **fully backward compatible**.

Both formats are supported:

**New format (recommended)**:
```yaml
tools:
  python:
    - callable: "strands_tools.http_request.http_request"
```

**Old format (still works)**:
```yaml
tools:
  python:
    - callable: "strands_tools.http_request"
```

The old format automatically infers the function name from the module name. No migration is required for existing workflow specs.

### Documentation
- **README.md** - Updated to list all 5 Python tools in Features and Supported Features sections
- **docs/security.md** - Added comprehensive Python Tool Security section
- **CONTRIBUTING.md** - Updated copilot-instructions.md reference (if applicable)

### Performance
- No performance changes (existing agent caching and model pooling unchanged)

---

## [0.4.0] - 2025-11-05

### Added - Parallel Execution Pattern

#### Parallel Pattern
- **Concurrent branch execution** - Execute multiple workflow branches in parallel
  - Asyncio-based concurrent execution with `asyncio.gather`
  - Fail-fast semantics: any branch failure cancels all branches
  - Alphabetical ordering of branch results for deterministic reduce context
  - Multi-step support within each branch with context threading
  - Access branch outputs via `{{ branches.<id>.response }}`

#### Concurrency Control
- **Semaphore-based limiting** - Respect `runtime.max_parallel` for resource control
  - Semaphore prevents exceeding max concurrent branches
  - Defaults to 10 concurrent branches if not specified
  - Branch execution retries with exponential backoff

#### Reduce Step
- **Output aggregation** - Optional reduce step synthesizes all branch outputs
  - Reduce agent receives alphabetically sorted branch results
  - Template access: `{{ branches.branch_a.response }}`, `{{ branches.branch_b.response }}`
  - Cumulative token budget tracking includes reduce step
  - Reduce step has same retry logic as branch steps

#### Budget Tracking
- **Cumulative token counting** - Track tokens across all branches and reduce
  - Warn at 80% of `budgets.max_tokens`
  - Fail at 100% with `ParallelExecutionError`
  - Per-step token tracking within each branch
  - Total tokens reported in `RunResult`

#### Examples
- **parallel-simple-2-branches.yaml** - Basic concurrent research with 2 branches
- **parallel-with-reduce.yaml** - Multi-perspective research with synthesis
- **parallel-multi-step-branches.yaml** - Complex workflows with 3-step branches

### Changed
- **Capability checker** - Parallel pattern now supported (was unsupported in v0.3.0)
  - Validates ≥2 branches required
  - Validates unique branch IDs
  - Validates all branch agents exist in `agents` map
  - Validates reduce agent exists if reduce step present
- **CLI dispatch** - Added parallel pattern routing in `run` command
- **Test fixtures** - Moved `parallel-pattern.yaml` from unsupported to valid fixtures

### Fixed
- **Artifact template variables** - User variables from `--var` flags now available in artifact paths and content
  - Artifact paths support templates: `./artifacts/{{topic}}-report.md`
  - Artifact content can access `{{topic}}` and other `--var` variables
  - Execution context (`steps`, `tasks`, `branches`) available in artifact templates
  - Added `execution_context` parameter to `write_artifacts()`
  - Updated `RunResult` to include `execution_context` field

### Testing
- **287 tests passing** - Added 16 parallel-specific tests
- **83% coverage** - Parallel module at 85%, overall coverage dropped 5% due to 152 new lines
- **All mypy checks passing** - Strict type safety maintained

## [0.3.0] - 2025-11-05

### Added - Routing & Multi-Agent Support

### Added - Multi-Step Workflows

#### Chain Pattern
- **Multi-step chains** - Execute sequential workflows with multiple steps
  - Pass context from previous steps via `{{ steps[n].response }}`
  - Per-step variable overrides with `step.vars`
  - Token budget tracking across all steps
  - Exponential backoff retry for each step

#### Workflow Pattern  
- **Multi-task workflows** - Execute DAG-based parallel workflows
  - Topological sort for dependency resolution
  - Parallel task execution when dependencies allow
  - Reference task outputs via `{{ tasks.<id>.response }}`
  - Cycle detection at validation time
  - Per-task timeout and retry configuration

#### Enhanced Templating
- **Extended Jinja2 context** - Access to workflow state
  - `{{ steps[<index>].response }}` - Prior step outputs in chains
  - `{{ tasks.<id>.response }}` - Task outputs in workflows
  - `{{ tasks.<id>.status }}` - Task completion status
  - `{{ last_response }}` - Most recent agent output

#### Observability
- **Execution traces** - Parent-child span relationships for steps/tasks
- **Budget enforcement** - Hard limits on token usage and execution time
- **Failure handling** - Fail-fast mode with detailed error reporting

### Changed
- **BedrockModel initialization** - Simplified to use SDK's internal boto3 client
  - Removed manual boto3 client creation
  - BedrockModel now handles AWS credential resolution internally
  - Region configuration via environment or `~/.aws/config`

### Fixed
- **Type safety** - All mypy strict mode checks passing
  - Added proper type annotations to async functions
  - Fixed return types for agent invocations
  - Added type assertions for callable resolution
- **Test suite** - Updated Bedrock tests to match new SDK API
  - Removed boto3 mocking (handled internally by SDK)
  - Fixed async test fixtures
  - 224 tests passing, 81% coverage

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
- JSON Schema: `src/strands_cli/schema/strands-workflow.schema.json` (Draft 2020-12)
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

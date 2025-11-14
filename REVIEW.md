# Code Review Plan for Strands CLI

**Version**: 1.0  
**Last Updated**: November 14, 2025  
**Purpose**: Systematic, reusable approach to comprehensive code review organized by architectural concerns and layers

---

## Overview

This review plan divides the strands-cli codebase into **8 primary review layers** based on architectural boundaries, separation of concerns, and dependency flow. Each layer is further broken into focused review units with specific checklists.

### Review Principles

1. **Bottom-Up Dependency Review** - Review foundation layers before dependent layers
2. **Concern Separation** - Each review unit focuses on a single architectural concern
3. **Test Coverage Integration** - Review implementation alongside corresponding tests
4. **Cross-Cutting Verification** - Security, performance, and error handling reviewed at each layer
5. **Incremental Progress** - Each unit can be completed independently (30-90 min each)

---

## Layer 1: Foundation & Core Types (Estimated: 3-4 hours)

**Purpose**: Review foundational types, schemas, and configuration that all other layers depend on.

### 1.1 Type System & Models (`types.py`)
**Files**: `src/strands_cli/types.py`  
**Tests**: `tests/test_types.py`, `tests/test_schema_pydantic_drift.py`

**Review Focus**:
- [ ] Pydantic v2 model correctness (validators, field constraints, defaults)
- [ ] Type annotations complete and accurate (mypy strict compliance)
- [ ] Model hierarchy and composition (inheritance, composition patterns)
- [ ] JSON Schema alignment (check drift tests pass)
- [ ] Enum definitions are exhaustive and match schema
- [ ] Optional vs required field logic matches business rules
- [ ] Default value consistency across Pydantic and JSON Schema

**Red Flags**:
- Type annotations with `Any` without justification
- Missing validators for business-critical constraints
- Mutable default values (lists, dicts)
- Inconsistent field naming conventions

---

### 1.2 JSON Schema Validation (`schema/`)
**Files**: `src/strands_cli/schema/validator.py`, `src/strands_cli/schema/strands-workflow.schema.json`  
**Tests**: `tests/test_schema.py`

**Review Focus**:
- [ ] Schema completeness (all patterns, all fields documented)
- [ ] Draft 2020-12 compliance (proper use of modern JSON Schema features)
- [ ] Error message clarity (JSONPointer precision, actionable messages)
- [ ] Schema loading mechanism (importlib.resources usage)
- [ ] Validation error handling and reporting
- [ ] Performance of validation (caching, precompilation)

**Red Flags**:
- Schema drift from types.py (should be caught by drift tests)
- Vague error messages that don't help users fix issues
- Missing required field validations
- Over-permissive schema allowing invalid configs

---

### 1.3 Configuration & Settings (`config.py`, `exit_codes.py`)
**Files**: `src/strands_cli/config.py`, `src/strands_cli/exit_codes.py`  
**Tests**: `tests/test_config.py`

**Review Focus**:
- [ ] Environment variable naming conventions (`STRANDS_` prefix)
- [ ] Pydantic Settings configuration correctness
- [ ] Default values match documentation
- [ ] Exit code constants are comprehensive and documented
- [ ] Platform compatibility (Windows/Linux/macOS paths)
- [ ] Security: No secrets logged or exposed

**Red Flags**:
- Hardcoded paths that don't use platformdirs
- Exit codes used inconsistently across codebase
- Missing env var documentation in README
- Secrets in config objects without proper handling

---

## Layer 2: Data Loading & Templating (Estimated: 2-3 hours)

**Purpose**: Review YAML/JSON loading, variable resolution, and Jinja2 templating.

### 2.1 YAML/JSON Loading (`loader/`)
**Files**: `src/strands_cli/loader/yaml_loader.py`, `src/strands_cli/loader/template.py`  
**Tests**: `tests/test_loader.py`

**Review Focus**:
- [ ] YAML parsing security (safe_load vs load)
- [ ] Variable merging logic (CLI --var overrides)
- [ ] Template rendering safety (Jinja2 sandboxing)
- [ ] Error handling for malformed files
- [ ] Support for both YAML and JSON input
- [ ] File path validation and sanitization
- [ ] Character encoding handling (UTF-8)

**Red Flags**:
- Use of `yaml.load()` instead of `yaml.safe_load()`
- Unvalidated user input in templates
- Path traversal vulnerabilities in file loading
- Poor error messages for template syntax errors

---

## Layer 3: Capability Checking & Validation (Estimated: 2-3 hours)

**Purpose**: Review feature detection, compatibility checking, and user-facing remediation.

### 3.1 Capability Checker (`capability/`)
**Files**: `src/strands_cli/capability/checker.py`, `src/strands_cli/capability/reporter.py`  
**Tests**: `tests/test_capability.py`, `tests/test_capability_reporter.py`

**Review Focus**:
- [ ] Complete coverage of all 7 workflow patterns
- [ ] Allowlist enforcement for tools (Python, HTTP, MCP)
- [ ] Accurate detection of unsupported features
- [ ] Remediation report quality (Markdown, JSON formats)
- [ ] Exit code 18 usage consistency
- [ ] Clear guidance on how to fix issues
- [ ] Tool registry integration (native tool allowlist)

**Red Flags**:
- Features marked unsupported that are actually implemented
- Vague remediation advice ("not supported")
- Missing checks for new features added in recent releases
- Hardcoded tool lists not synced with tool registry

**Coverage Gap Analysis**:
- Current: 63% coverage on capability checker
- Review: Are critical paths (pattern validation, tool allowlisting) covered?
- Action: Identify missing test cases for unsupported feature detection

---

## Layer 4: Runtime & Agent Management (Estimated: 4-5 hours)

**Purpose**: Review provider integration, agent lifecycle, and tool execution.

### 4.1 Provider Adapters (`runtime/providers.py`)
**Files**: `src/strands_cli/runtime/providers.py`  
**Tests**: `tests/test_runtime.py`

**Review Focus**:
- [ ] Bedrock client configuration (boto3 session, region handling)
- [ ] Ollama client configuration (host URL, model selection)
- [ ] OpenAI client configuration (API key, model selection)
- [ ] Error handling for provider failures (network, auth, rate limits)
- [ ] Retry logic integration (exponential backoff via tenacity)
- [ ] Provider-specific quirks documented (model ID formats, etc.)

**Red Flags**:
- Unhandled provider-specific exceptions
- Missing retry logic for transient failures
- Secrets (API keys) logged or exposed in error messages
- Boto3 session creation without proper credential fallback

---

### 4.2 Strands Agent Adapter (`runtime/strands_adapter.py`)
**Files**: `src/strands_cli/runtime/strands_adapter.py`  
**Tests**: `tests/test_runtime.py`, `tests/test_agent_cache.py`

**Review Focus**:
- [ ] Agent building logic (system prompt construction)
- [ ] Tool integration (Python, HTTP, native registry)
- [ ] Model client pooling (@lru_cache on create_model)
- [ ] Agent caching (AgentCache correctness)
- [ ] Session management integration (FileSessionManager)
- [ ] Memory/resource cleanup (async context managers)
- [ ] Skills injection (metadata-only in MVP)

**Red Flags**:
- Agent instances not reused (performance issue)
- Model clients created redundantly (cache miss)
- Skills with executable=true not blocked
- Circular dependencies in agent references

**Performance Review**:
- [ ] Verify 10-step chain with same runtime → 1 model client
- [ ] Verify agent cache hit rate in multi-step workflows
- [ ] Check for memory leaks in long-running workflows

---

### 4.3 Tool Execution (`runtime/tools.py`, `tools/`)
**Files**: `src/strands_cli/runtime/tools.py`, `src/strands_cli/tools/*.py`  
**Tests**: `tests/test_python_exec_integration.py`, `tests/test_http_executor_factory.py`

**Review Focus**:
- [ ] Python tool allowlist enforcement (security-critical)
- [ ] HTTP executor factory (timeout, retry, headers)
- [ ] Native tool registry (auto-discovery via TOOL_SPEC)
- [ ] Tool result formatting (ToolResult structure)
- [ ] Error handling in tool execution
- [ ] User consent for dangerous tools (file_write)
- [ ] Tool loading mechanism (module vs @tool decorated)

**Red Flags**:
- Non-allowlisted Python callables executed
- Missing input validation on tool parameters
- Unhandled exceptions in tool execution
- HTTP requests without timeout limits

**Security Review**:
- [ ] file_write tool consent mechanism (--bypass-tool-consent flag)
- [ ] Path traversal protection in file operations
- [ ] Code injection risks in Python tool execution
- [ ] Secrets leakage in HTTP headers/logs

---

## Layer 5: Execution Patterns (Estimated: 8-10 hours)

**Purpose**: Review all 7 workflow pattern executors for correctness, performance, and consistency.

### 5.1 Single-Agent Executor (`exec/single_agent.py`)
**Files**: `src/strands_cli/exec/single_agent.py`  
**Tests**: `tests/test_executor.py`

**Review Focus**:
- [ ] Simplest execution path (baseline for other patterns)
- [ ] Error handling and retry logic
- [ ] Budget enforcement (tokens, duration)
- [ ] Artifact template variable resolution
- [ ] Session state integration (if applicable)

---

### 5.2 Chain Pattern (`exec/chain.py`)
**Files**: `src/strands_cli/exec/chain.py`  
**Tests**: `tests/test_chain.py`, `tests/test_chain_resume.py`, `tests/test_chain_hitl.py`, `tests/test_chain_checkpointing.py`

**Review Focus**:
- [ ] Sequential step execution (context threading)
- [ ] Step output access via `{{ steps[n].response }}`
- [ ] Per-step variable overrides
- [ ] Checkpoint saving after each step (session persistence)
- [ ] Resume logic (skip completed steps)
- [ ] Token budget accumulation across steps
- [ ] Agent cache usage (reuse same agent across steps)
- [ ] HITL integration (human-in-the-loop pauses)

**Red Flags**:
- Steps executed out of order
- Context from previous steps not passed correctly
- Agent instances recreated unnecessarily
- Checkpoint corruption or race conditions

---

### 5.3 Workflow/DAG Pattern (`exec/workflow.py`)
**Files**: `src/strands_cli/exec/workflow.py`  
**Tests**: `tests/test_workflow.py`, `tests/test_workflow_resume.py`, `tests/test_workflow_hitl.py`

**Review Focus**:
- [ ] Topological sort correctness (dependency resolution)
- [ ] Parallel task execution (asyncio.gather)
- [ ] Task output access via `{{ tasks.<id>.response }}`
- [ ] Cycle detection and prevention
- [ ] Dependency validation at capability check
- [ ] Task failure propagation
- [ ] Resume from checkpoint (task state restoration)

**Red Flags**:
- Deadlock in circular dependencies (should be caught by cycle detection)
- Race conditions in parallel task execution
- Task outputs not available to dependent tasks
- Incorrect topological sort (tasks run before dependencies)

---

### 5.4 Routing Pattern (`exec/routing.py`)
**Files**: `src/strands_cli/exec/routing.py`  
**Tests**: `tests/test_routing.py`, `tests/test_routing_resume.py`, `tests/test_routing_hitl.py`

**Review Focus**:
- [ ] Router agent execution (classification logic)
- [ ] Route selection based on router output
- [ ] Fallback to default route when no match
- [ ] Multi-step execution within selected route
- [ ] Context passing to route steps
- [ ] Agent caching across router and route agents
- [ ] Resume logic (router decision preserved)

**Red Flags**:
- Router output not parsed correctly
- Route selection logic doesn't match spec
- Default route not executed when expected
- Agent cache misses for route agents

---

### 5.5 Parallel Pattern (`exec/parallel.py`)
**Files**: `src/strands_cli/exec/parallel.py`  
**Tests**: `tests/test_parallel.py`, `tests/test_parallel_resume.py`, `tests/test_parallel_hitl.py`

**Review Focus**:
- [ ] Concurrent branch execution (asyncio.gather)
- [ ] Semaphore-based concurrency control (max_parallel)
- [ ] Fail-fast semantics (any branch failure cancels all)
- [ ] Branch output alphabetical ordering (deterministic reduce)
- [ ] Reduce step execution (aggregation logic)
- [ ] Multi-step branches (context threading within branch)
- [ ] Token budget tracking across all branches + reduce

**Red Flags**:
- Branch execution not truly concurrent (sequential execution)
- max_parallel not enforced (resource exhaustion)
- Non-deterministic reduce context (branch order changes)
- Branch failures not canceling other branches

**Performance Review**:
- [ ] Verify semaphore limits concurrent branches
- [ ] Check for proper async context cleanup on cancellation

---

### 5.6 Evaluator-Optimizer Pattern (`exec/evaluator_optimizer.py`)
**Files**: `src/strands_cli/exec/evaluator_optimizer.py`  
**Tests**: `tests/test_evaluator_optimizer.py`, `tests/test_evaluator_optimizer_resume.py`, `tests/test_evaluator_optimizer_hitl.py`

**Review Focus**:
- [ ] Producer → Evaluator → Optimizer feedback loop
- [ ] Iteration limit enforcement (max_iterations)
- [ ] Accept criteria evaluation (quality threshold)
- [ ] Optimization prompt construction (include evaluation feedback)
- [ ] Token budget tracking across all iterations
- [ ] Resume from checkpoint (iteration state preserved)
- [ ] Agent caching (producer, evaluator, optimizer reuse)

**Red Flags**:
- Infinite loop if accept criteria never met
- Evaluation feedback not passed to optimizer
- Iteration count off by one
- Agent instances recreated each iteration

---

### 5.7 Orchestrator-Workers Pattern (`exec/orchestrator_workers.py`)
**Files**: `src/strands_cli/exec/orchestrator_workers.py`  
**Tests**: `tests/test_orchestrator_workers.py`, `tests/test_orchestrator_resume.py`, `tests/test_orchestrator_hitl.py`

**Review Focus**:
- [ ] Orchestrator subtask decomposition (JSON array parsing)
- [ ] Worker pool execution (max_workers limit)
- [ ] Round tracking (orchestrator delegation cycles)
- [ ] Reduce step (aggregate worker outputs)
- [ ] Writeup step (final synthesis)
- [ ] JSON parsing retry logic (malformed orchestrator responses)
- [ ] Empty subtask array handling (`[]` = no work)
- [ ] Indexed worker output access `{{ workers[0].response }}`

**Red Flags**:
- JSON parsing failures not retried
- max_workers not enforced (resource exhaustion)
- Worker failures not canceling other workers (fail-fast)
- Round count incorrect (counts worker calls instead of delegation cycles)

**JSON Parsing Review**:
- [ ] Multi-strategy parsing (direct, code block, regex)
- [ ] Retry logic with clarification prompts
- [ ] Error handling for non-JSON responses

---

### 5.8 Graph Pattern (`exec/graph.py`, `exec/conditions.py`)
**Files**: `src/strands_cli/exec/graph.py`, `src/strands_cli/exec/conditions.py`  
**Tests**: `tests/test_graph.py`, `tests/test_graph_hitl.py`, `tests/test_graph_node_types.py`, `tests/test_conditions_security.py`, `tests/test_graph_viz.py`

**Review Focus**:
- [ ] Node execution (state machine semantics)
- [ ] Edge transitions (static `to` vs conditional `choose`)
- [ ] Condition evaluation safety (restricted builtins)
- [ ] Cycle detection and max iteration limit
- [ ] Node output access `{{ nodes.<id>.response }}`
- [ ] Graph visualization generation (planning/debugging)
- [ ] Token budget tracking across nodes

**Red Flags**:
- Arbitrary code execution in `when` conditions (security critical)
- Infinite loops (cycle detection failure)
- Incorrect node output access in conditions
- Graph cycles not detected at validation time

**Security Review**:
- [ ] Condition evaluator allowlisted builtins only
- [ ] No `eval()` or `exec()` usage
- [ ] Safe comparison operators only
- [ ] Template access restricted to node outputs

**Coverage Analysis**:
- Current: graph.py 94%, conditions.py 91%
- Review: Are edge cases in condition evaluation covered?

---

### 5.9 Cross-Pattern Utilities (`exec/utils.py`, `exec/hitl_utils.py`, `exec/hooks.py`)
**Files**: `src/strands_cli/exec/utils.py`, `src/strands_cli/exec/hitl_utils.py`, `src/strands_cli/exec/hooks.py`  
**Tests**: `tests/test_exec_utils.py`, `tests/test_hooks.py`

**Review Focus**:
- [ ] AgentCache implementation (cache key correctness)
- [ ] Agent reuse logic (same config → same agent instance)
- [ ] HTTP client cleanup (async context managers)
- [ ] HITL utility functions (prompt formatting, response handling)
- [ ] Hook execution (pre/post execution callbacks)
- [ ] Shared template rendering logic

**Red Flags**:
- Agent cache key doesn't include all relevant config
- Memory leaks in cache (agents never evicted)
- HTTP clients not closed properly
- Race conditions in concurrent cache access

---

## Layer 6: Session & State Management (Estimated: 3-4 hours)

**Purpose**: Review session persistence, checkpointing, and resume logic.

### 6.1 Session Models & Storage (`session/`)
**Files**: `src/strands_cli/session/*.py`  
**Tests**: `tests/test_session_*.py`

**Review Focus**:
- [ ] SessionState model completeness (all pattern states supported)
- [ ] FileSessionRepository correctness (atomic writes, locking)
- [ ] Session directory structure (~/.strands/sessions/)
- [ ] Session ID generation (uniqueness, collision avoidance)
- [ ] Spec hash validation (detect spec changes)
- [ ] Token usage accumulation across resume
- [ ] Session status transitions (RUNNING → COMPLETED → FAILED)
- [ ] Concurrent session access (file locking)

**Red Flags**:
- Non-atomic session writes (corruption on crash)
- Race conditions in concurrent session access
- Session files not cleaned up (disk space growth)
- Spec hash mismatches not detected

**Test Coverage Review**:
- [ ] Tests cover: create, load, update, delete sessions
- [ ] Tests cover: concurrent access, locking, corruption recovery
- [ ] Tests cover: all pattern state types (chain, workflow, graph, etc.)

---

### 6.2 Resume Logic (`session/resume.py`)
**Files**: `src/strands_cli/session/resume.py`  
**Tests**: `tests/test_resume_module.py`, pattern-specific resume tests

**Review Focus**:
- [ ] Session validation (status, spec hash)
- [ ] Pattern-specific routing (chain, workflow, etc.)
- [ ] Error handling (session not found, corrupted)
- [ ] CLI integration (--resume flag)
- [ ] User warnings (spec changed since session creation)

**Red Flags**:
- Resuming completed sessions (should error)
- Spec changes not detected/warned
- Pattern state not passed to executor correctly

---

## Layer 7: Observability & Debugging (Estimated: 3-4 hours)

**Purpose**: Review telemetry, logging, and debugging infrastructure.

### 7.1 OpenTelemetry Integration (`telemetry/otel.py`, `telemetry/redaction.py`)
**Files**: `src/strands_cli/telemetry/otel.py`, `src/strands_cli/telemetry/redaction.py`  
**Tests**: `tests/test_telemetry*.py`, `tests/test_redaction*.py`

**Review Focus**:
- [ ] OTLP exporter configuration (endpoint, service name)
- [ ] Console exporter for local development
- [ ] Span hierarchy correctness (parent-child relationships)
- [ ] Span attributes completeness (spec.name, runtime.model_id, etc.)
- [ ] PII redaction patterns (email, SSN, credit cards, API keys)
- [ ] Trace artifact generation (`{{ $TRACE }}` variable)
- [ ] Thread-safety (telemetry lock)
- [ ] Bounded span collection (FIFO eviction, memory limits)
- [ ] Flush timeout detection and user warnings

**Red Flags**:
- Sensitive data in span attributes (PII leakage)
- Missing span hierarchy (orphaned spans)
- Memory leaks in trace collector (unbounded growth)
- Race conditions in telemetry configuration (concurrent workflows)

**Security Review**:
- [ ] Redaction engine coverage (all PII patterns)
- [ ] Custom pattern support (domain-specific secrets)
- [ ] Redaction audit logging (compliance)

**Performance Review**:
- [ ] OTLP overhead <5% (benchmarked)
- [ ] Span collection FIFO eviction (1000 span limit)
- [ ] Flush timeout handling (no blocking)

---

### 7.2 Structured Logging
**Files**: Cross-cutting (all modules use structlog)  
**Tests**: Integration tests with log assertions

**Review Focus**:
- [ ] Consistent use of structlog across all modules
- [ ] Log levels appropriate (DEBUG, INFO, WARNING, ERROR)
- [ ] Structured log fields (JSON-serializable)
- [ ] No secrets logged (API keys, credentials)
- [ ] Debug flag integration (--debug sets DEBUG level)
- [ ] Performance: Avoid expensive log formatting in hot paths

**Red Flags**:
- Print statements instead of structured logging
- Secrets in log messages
- Exception stack traces missing context
- Log spam (excessive DEBUG logs in production)

---

## Layer 8: CLI & User Interface (Estimated: 3-4 hours)

**Purpose**: Review command-line interface, user experience, and error reporting.

### 8.1 CLI Commands (`__main__.py`)
**Files**: `src/strands_cli/__main__.py`  
**Tests**: `tests/test_cli.py`, `tests/test_cli_integration.py`

**Review Focus**:
- [ ] Command structure (run, validate, plan, explain, sessions, list-supported)
- [ ] Argument parsing (Typer usage, --var flags, --resume, --debug, etc.)
- [ ] Exit code consistency (use constants from exit_codes.py)
- [ ] Error message quality (actionable, user-friendly)
- [ ] Rich console output (progress, formatting)
- [ ] Help text completeness (--help for all commands)
- [ ] Flag validation (conflicting flags, required combinations)

**Red Flags**:
- Hardcoded exit codes (not using constants)
- Generic error messages ("something went wrong")
- Missing --help documentation
- Inconsistent flag naming conventions

**Coverage Gap Analysis**:
- Current: __main__.py at 58% coverage
- Review: Which CLI commands lack tests?
- Action: Add integration tests for under-tested commands

---

### 8.2 Artifact Output (`artifacts/io.py`)
**Files**: `src/strands_cli/artifacts/io.py`  
**Tests**: Integration tests in executor tests

**Review Focus**:
- [ ] Overwrite protection (--force flag required)
- [ ] Template variable resolution (last_response, steps, tasks, etc.)
- [ ] File path validation (no path traversal)
- [ ] Directory creation (parents created automatically)
- [ ] Error handling (permission denied, disk full)
- [ ] `{{ $TRACE }}` special variable support

**Red Flags**:
- Path traversal vulnerabilities
- Files overwritten without user consent
- Missing error handling for I/O failures
- Template rendering errors not caught

---

### 8.3 Presets & User Experience (`presets.py`)
**Files**: `src/strands_cli/presets.py`  
**Tests**: `tests/test_presets.py`

**Review Focus**:
- [ ] Preset definitions (minimal, balanced, long_run, interactive)
- [ ] Preset application logic (merging with user config)
- [ ] Documentation accuracy (preset descriptions match behavior)
- [ ] User value precedence (presets don't override user settings)

---

## Layer 9: Python API (Estimated: 3-4 hours)

**Purpose**: Review programmatic interface for workflow execution and builder API.

### 9.1 Workflow Execution API (`api/workflow.py`, `api/executor.py`)
**Files**: `src/strands_cli/api/workflow.py`, `src/strands_cli/api/executor.py`  
**Tests**: `tests/test_api_workflow.py`, `tests/test_api_executor_integration.py`

**Review Focus**:
- [ ] Workflow.from_file() loading logic
- [ ] run_interactive() HITL loop orchestration
- [ ] run_async() performance (agent caching, model pooling)
- [ ] Session management (automatic session creation)
- [ ] Error handling (same exit codes as CLI)
- [ ] HITL handler interface (terminal_hitl_handler, custom handlers)
- [ ] Safety limits (max 100 HITL iterations)
- [ ] Graceful KeyboardInterrupt handling

**Red Flags**:
- Infinite HITL loops (safety limit not enforced)
- Session state corruption on exception
- Agent cache misses in interactive mode
- Memory leaks in long-running interactive sessions

---

### 9.2 Builder API (`api/builders.py`)
**Files**: `src/strands_cli/api/builders.py`  
**Tests**: `tests/test_api_builders.py`, `tests/test_api_builder_integration.py`

**Review Focus**:
- [ ] FluentBuilder interface (chainable methods)
- [ ] Pattern-specific builders (Chain, Workflow, Parallel, Graph, etc.)
- [ ] Type safety (IDE autocomplete support)
- [ ] Validation at build time (actionable errors)
- [ ] Spec equivalence (built specs == YAML specs)
- [ ] All 7 patterns supported
- [ ] Documentation completeness (docstrings, examples)

**Red Flags**:
- Builder methods return wrong type (breaks chaining)
- Validation delayed until execution (should fail at build())
- Built specs don't match YAML equivalents
- Missing builder methods for critical features

---

## Cross-Cutting Concerns (Throughout All Layers)

### Code Comments & Documentation Review Checklist
Apply to every layer:

- [ ] **Docstrings**: All public classes, functions, methods have docstrings
  - [ ] Format: Google/NumPy style with parameters, returns, raises
  - [ ] Accuracy: Docstrings match current implementation (no stale docs)
  - [ ] Completeness: All parameters documented, edge cases explained
- [ ] **Inline Comments**: Strategic comments for "why", not "what"
  - [ ] Complex algorithms explained (e.g., topological sort in workflow.py)
  - [ ] Non-obvious design decisions justified (e.g., why @lru_cache on create_model)
  - [ ] Security considerations noted (e.g., "Restricted builtins to prevent code injection")
  - [ ] Performance optimizations explained (e.g., "Agent caching prevents redundant builds")
- [ ] **TODO/FIXME Comments**: Actionable and tracked
  - [ ] Every TODO has context (why deferred, what's needed)
  - [ ] FIXMEs have issue numbers or remediation plan
  - [ ] No stale TODOs from completed work
- [ ] **Type Annotations**: All functions fully annotated (mypy strict compliance)
  - [ ] Return types specified (not just parameters)
  - [ ] Complex types documented (e.g., `dict[str, Any]` with comment explaining structure)
- [ ] **Module-level Docstrings**: Every module has purpose statement
  - [ ] Explains module's role in architecture
  - [ ] Lists key classes/functions exported
  - [ ] Notes dependencies or integration points
- [ ] **Comment Quality Anti-patterns**:
  - ❌ Commented-out code (delete or explain why kept)
  - ❌ Obvious comments: `# increment counter` for `counter += 1`
  - ❌ Misleading comments (out of sync with code)
  - ❌ Excessive comments (self-documenting code is better)

**Review Questions**:
- Can a new developer understand the code without asking questions?
- Do comments explain *why* decisions were made, not just *what* the code does?
- Are edge cases and error conditions documented?
- Would you understand this code 6 months from now?

---

### Security Review Checklist
Apply to every layer:

- [ ] **Input Validation**: All user inputs validated (schemas, allowlists)
- [ ] **Path Traversal**: File paths sanitized (no `../` attacks)
- [ ] **Code Injection**: No `eval()`, `exec()`, or unsafe deserialization
- [ ] **Secrets Handling**: No secrets in logs, error messages, or traces
- [ ] **PII Protection**: Redaction enabled for sensitive data
- [ ] **Tool Execution**: Allowlisted tools only, user consent for dangerous operations
- [ ] **Condition Evaluation**: Restricted builtins in graph conditions

---

### Performance Review Checklist
Apply to every layer:

- [ ] **Agent Caching**: Agents reused across steps/tasks (AgentCache)
- [ ] **Model Pooling**: Model clients cached (@lru_cache on create_model)
- [ ] **Concurrency Control**: max_parallel enforced (semaphores)
- [ ] **Memory Management**: No unbounded growth (trace spans, session storage)
- [ ] **Async Patterns**: Single event loop per workflow (no asyncio.run in executors)
- [ ] **Hot Path Optimization**: Expensive operations avoided in loops

---

### Error Handling Review Checklist
Apply to every layer:

- [ ] **Exit Codes**: Correct exit code constants used (not generic `exit(1)`)
- [ ] **Error Messages**: Actionable, user-friendly, include remediation
- [ ] **Exception Wrapping**: Domain-specific exceptions (LoadError, ExecutionError, etc.)
- [ ] **Stack Traces**: Full context preserved for debugging
- [ ] **Retry Logic**: Exponential backoff for transient failures (tenacity)
- [ ] **Failure Modes**: Fail-fast where appropriate, graceful degradation elsewhere

---

### Testing Review Checklist
Apply to every layer:

- [ ] **Unit Tests**: Core logic tested in isolation
- [ ] **Integration Tests**: End-to-end workflows tested
- [ ] **Mocking Strategy**: External dependencies mocked (Bedrock, Ollama, file I/O)
- [ ] **Test Fixtures**: Reusable fixtures in conftest.py
- [ ] **Coverage**: ≥85% overall, critical paths at 100%
- [ ] **Async Tests**: Proper pytest-asyncio usage
- [ ] **Error Cases**: Negative tests for expected failures

---

## Review Execution Strategy

### Phase 1: Foundation (Layers 1-2)
**Duration**: 5-7 hours  
**Order**: Types → Schema → Config → Loading → Templating

**Goal**: Verify foundation is solid before reviewing dependent layers.

---

### Phase 2: Validation & Runtime (Layers 3-4)
**Duration**: 6-8 hours  
**Order**: Capability → Providers → Agent Adapter → Tools

**Goal**: Ensure validation and runtime infrastructure is correct.

---

### Phase 3: Execution Patterns (Layer 5)
**Duration**: 8-10 hours  
**Order**: Single-Agent → Chain → Workflow → Routing → Parallel → Evaluator-Optimizer → Orchestrator → Graph

**Goal**: Review all 7 patterns systematically, comparing for consistency.

---

### Phase 4: Advanced Features (Layers 6-7)
**Duration**: 6-8 hours  
**Order**: Session Management → Telemetry → Logging

**Goal**: Verify advanced features work correctly and safely.

---

### Phase 5: User Interface (Layers 8-9)
**Duration**: 6-8 hours  
**Order**: CLI → Artifacts → Presets → Python API → Builders

**Goal**: Ensure user-facing interfaces are polished and ergonomic.

---

### Phase 6: Cross-Cutting Review
**Duration**: 3-4 hours  
**Order**: Security → Performance → Error Handling → Testing

**Goal**: Verify cross-cutting concerns are handled consistently.

---

## Review Output Template

For each review unit, create a review note:

```markdown
## Review: [Layer X.Y - Component Name]

**Date**: YYYY-MM-DD  
**Reviewer**: [Name]  
**Files**: [List of files reviewed]  
**Tests**: [List of test files reviewed]

### Summary
[Brief overview of component purpose and review findings]

### Checklist Results
- [✓] Item passed
- [✗] Item failed (see issues below)
- [⚠] Item needs attention (minor issue)

### Issues Found
1. **[Severity: Critical/High/Medium/Low]** [Issue description]
   - **Location**: `file.py:line`
   - **Impact**: [What breaks or is at risk]
   - **Recommendation**: [How to fix]

### Positive Observations
- [Things done well]
- [Good patterns to replicate]

### Recommendations
1. [Specific actionable recommendation]
2. [Priority ranking: P0/P1/P2]

### Test Coverage Gaps
- [Missing test scenarios]
- [Recommended new tests]

### Next Steps
- [ ] Create GitHub issues for critical/high severity items
- [ ] Schedule fix implementation
- [ ] Re-review after fixes
```

---

## Metrics to Track

### Code Quality Metrics
- [ ] Test coverage: Current 83%, Target ≥85%
- [ ] Mypy strict mode: 100% passing (current: ✓)
- [ ] Ruff linting: 0 violations (current: ✓)
- [ ] Complexity: Max cyclomatic complexity ≤15 (current: ✓)

### Review Progress Metrics
- [ ] Layers completed: X / 9
- [ ] Review units completed: X / 35
- [ ] Issues found: X (breakdown by severity)
- [ ] Test coverage gaps identified: X

---

## Tools & Automation

### Recommended Review Tools
- **Coverage Report**: `.\scripts\dev.ps1 test-cov` → `htmlcov/index.html`
- **Type Checking**: `uv run mypy src` (strict mode)
- **Linting**: `uv run ruff check .`
- **Complexity**: Use ruff's cyclomatic complexity checks
- **Dependency Graph**: Use `pydeps` to visualize module dependencies
- **Code Search**: `grep_search` for patterns across codebase

### Automation Scripts
```powershell
# Full review prep (generate coverage, type check, lint)
.\scripts\dev.ps1 ci

# Coverage report for specific module
uv run pytest --cov=src/strands_cli/exec --cov-report=html tests/test_chain.py

# Find TODOs and FIXMEs
rg "TODO|FIXME|XXX|HACK" src/

# Find missing docstrings
rg "^(class|def|async def) " src/ | rg -v '"""'

# Find commented-out code blocks
rg "^\s*#\s*(def|class|import|from)" src/

# Complexity analysis (functions with high complexity)
rg "def |async def " src/ | head -20  # Manual review needed
```

---

## Review Antipatterns to Avoid

❌ **Don't**: Review files in random order (hard to track dependencies)  
✅ **Do**: Follow layer order (bottom-up dependency review)

❌ **Don't**: Focus only on code (tests are equally important)  
✅ **Do**: Review implementation + tests together

❌ **Don't**: Create massive review sessions (cognitive overload)  
✅ **Do**: Break into 30-90 min focused units

❌ **Don't**: Ignore cross-cutting concerns (security, performance)  
✅ **Do**: Apply cross-cutting checklists to every layer

❌ **Don't**: Review without running tests (miss runtime issues)  
✅ **Do**: Run tests and check coverage before/during review

❌ **Don't**: Skip documentation review (outdated docs mislead)  
✅ **Do**: Verify README, manual, and docstrings match implementation

---

## Appendix: Quick Reference

### File Count by Layer
- Layer 1 (Foundation): 3 files
- Layer 2 (Loading): 2 files
- Layer 3 (Capability): 2 files
- Layer 4 (Runtime): 3 files + tools/
- Layer 5 (Execution): 12 files (8 patterns + 4 utils)
- Layer 6 (Session): 6 files in session/
- Layer 7 (Observability): 2 files in telemetry/
- Layer 8 (CLI): 3 files
- Layer 9 (API): 4 files in api/

**Total**: ~40 core files + ~70 test files

### Test File Mapping
- `test_types.py` → `types.py`
- `test_schema.py` → `schema/validator.py`
- `test_chain.py` → `exec/chain.py`
- (See tests/ directory for full mapping)

### Coverage Targets by Layer
- Foundation: 90%+ (core types are critical)
- Loading: 85%+
- Capability: 80%+ (current gap: 63% → needs improvement)
- Runtime: 85%+
- Execution: 85%+ (most patterns 90%+)
- Session: 90%+ (current: 98% ✓)
- Telemetry: 80%+
- CLI: 70%+ (current gap: 58% → needs improvement)
- API: 85%+

---

**End of Review Plan**

*This plan should be updated as the codebase evolves. Track completion progress and findings in a separate `REVIEW_PROGRESS.md` file.*

# Strands CLI Evolution Plan

**Created:** 2025-11-04  
**Owner:** Thomas Rohde  
**Current Version:** v0.4.0 (Parallel Execution Pattern)  
**Target:** Full multi-agent workflow orchestration with observability, security, and enterprise features

---

## Completed Phases Summary (v0.1.0 → v0.4.0)

**Completion Date**: November 7, 2025  
**Current Version**: v0.5.0  
**Status**: ✅ Phases 1-4 Complete  
**Tests**: 479 passing | Coverage maintained  
**Type Safety**: Mypy strict mode passing

### Major Achievements

**Multi-Pattern Workflow Support:**
- ✅ **Chain Pattern**: Sequential multi-step execution with context threading (`{{ steps[n].response }}`)
- ✅ **Workflow Pattern**: DAG-based parallel task execution with dependency resolution (`{{ tasks.<id>.response }}`)
- ✅ **Routing Pattern**: Dynamic agent selection with router retry logic and malformed JSON handling
- ✅ **Parallel Pattern**: Concurrent branch execution with optional reduce aggregation (`{{ branches.<id>.response }}`)
- ✅ **Evaluator-Optimizer Pattern**: Iterative refinement with producer-evaluator feedback loops and quality gates

**Multi-Agent Architecture:**
- ✅ Agent reuse and caching via `AgentCache` singleton
- ✅ Model client pooling with `@lru_cache` (10x+ efficiency for multi-step workflows)
- ✅ Single asyncio event loop per workflow with proper resource cleanup
- ✅ Support for multiple agents across all pattern types

**Provider Ecosystem:**
- ✅ AWS Bedrock integration (Anthropic Claude models)
- ✅ Ollama local model support
- ✅ OpenAI API integration with key-based authentication
- ✅ Provider-agnostic model client pooling

**Execution Features:**
- ✅ Asyncio-based concurrency with semaphore control (`max_parallel`)
- ✅ Token budget tracking with warnings (80%) and hard limits (100%)
- ✅ Fail-fast error handling with proper cleanup
- ✅ Context threading across steps/tasks/branches
- ✅ Jinja2 templating with workflow history access

**Tool System:**
- ✅ HTTP executors with metadata support
- ✅ Python callable allowlisting (`strands_tools.*`)
- ✅ Tool override validation in capability checker
- ✅ Auto-discovery registry pattern with `TOOL_SPEC` exports

**Quality & Testing:**
- ✅ 479 comprehensive tests (unit, integration, E2E)
- ✅ Code coverage maintained at target levels
- ✅ Type-safe with mypy strict mode
- ✅ Ruff linting and formatting compliance

### Key Design Decisions

1. **Agent Caching**: `AgentCache` singleton reuses agents across workflow execution (10x efficiency gain)
2. **Model Pooling**: `@lru_cache` on `create_model()` prevents redundant client instantiation
3. **Single Event Loop**: One `asyncio.run()` per workflow from CLI; executors use `await` (no nested event loops)
4. **Fail-Fast Semantics**: `asyncio.gather(return_exceptions=False)` cancels all branches on first failure
5. **Router Retry**: Up to 2 retries (configurable `max_retries`) for malformed JSON with clarification prompts
6. **Alphabetical Ordering**: Branch results sorted by ID for deterministic reduce step context
7. **Cumulative Budgets**: Token counts accumulate across all steps/tasks/branches in a workflow
8. **Template Hygiene**: Explicit references (`steps[n]`, `tasks.<id>`, `branches.<id>`) prevent ambiguity
9. **Evaluator JSON Parsing**: Multi-strategy parsing (direct JSON, block extraction, regex) with retry on malformed responses
10. **Iteration Limits**: Quality gate enforcement with `min_score` threshold and `max_iters` protection against infinite loops

### Technical Debt & Future Work

- **Coverage Gap**: Need CLI edge case tests (`doctor`, error paths) to reach 85% overall
- **Complexity Warnings**: 7 functions exceed C901 threshold (cosmetic, non-blocking)
- **OTEL Activation**: Scaffolding in place but no-op (Phase 10 target)
- **Branch Timeouts**: Deferred to Phase 5 (need per-branch cancellation)
- **Graph Visualization**: Plan command needs execution path rendering

### Breaking Changes

None - all changes backward compatible with v0.1.0 specs.

**Next Phase**: Phase 5 (Security & Guardrails), Phase 6 (Context Management), or Phase 7 (Orchestrator-Workers) - multiple parallel tracks available

---

## Overview

This phased plan extends the strands-cli from its current state (multi-step workflows) to a full-featured agentic workflow orchestration platform. Each phase builds incrementally on the previous, delivering testable, production-ready capabilities.

**Design Principles:**
- **Incremental delivery**: Each phase adds 1-3 major features
- **Test-first**: Maintain ≥85% coverage at each phase completion
- **Backward compatible**: Earlier phases never break; new features gate cleanly
- **Schema-driven**: All features validated by `strands-workflow.schema.json`
- **Exit code discipline**: Continue using EX_UNSUPPORTED (18) until feature is complete

**Key Reference Documents:**
- **`src/strands_cli/schema/strands-workflow.schema.json`** - JSON Schema Draft 2020-12 (source of truth for validation)
- **`docs/strands-workflow-manual.md`** - Comprehensive manual with examples for all 7 patterns
- **`docs/PRD_SingleAgent_MVP.md`** - MVP requirements and scope boundaries
- **`docs/stack.md`** - Technology stack and dependency rationale

**Development Resources:**
- **MCP Context7** - Use `mcp_context7_resolve-library-id` and `mcp_context7_get-library-docs` to fetch up-to-date documentation for libraries (boto3, pydantic, strands-agents-sdk, etc.)
- **MCP Ref Tools** - Use `mcp_ref_tools_ref_search_documentation` to search web/GitHub docs and `mcp_ref_tools_ref_read_url` to read documentation content
- Always consult the schema and manual before implementing new pattern types or workflow features to ensure compliance with the spec**Current State (v0.1.0):**
- ✅ Single agent execution (chain/workflow with 1 step/task)
- ✅ JSON Schema validation with JSONPointer errors
- ✅ Capability checking with remediation reports
- ✅ Bedrock & Ollama provider support
- ✅ Basic tools (HTTP executors, allowlisted Python callables)
- ✅ Secrets from environment variables
- ✅ Artifact output with templating
- ✅ 177 tests, 88% coverage

---

## Phase 1: Multi-Step Workflows (v0.2.0)

**Status:** ✅ **COMPLETE** (2025-11-04)  
**Duration:** 2 weeks  
**Complexity:** Low-Medium

Implemented multi-step chain and workflow execution with DAG-based dependency resolution, context threading, and enhanced Jinja2 templating for accessing prior step/task outputs.

---

## Phase 2: Routing & Conditional Logic (v0.3.0)

**Status:** ✅ **COMPLETE** (2025-11-05)  
**Duration:** 2 weeks  
**Complexity:** Medium

Implemented routing pattern with dynamic agent selection, router retry logic for malformed JSON, multi-agent support, and OpenAI provider integration.

---

## Phase 3: Parallel Execution (v0.4.0)

**Status:** ✅ **COMPLETE** (2025-11-05)  
**Duration:** 2-3 weeks  
**Complexity:** High

Implemented parallel pattern with asyncio-based concurrent branch execution, optional reduce aggregation, semaphore-based concurrency control, and cumulative token budget tracking.

---

## Phase 4: Evaluator-Optimizer Pattern (v0.5.0)

**Status:** ✅ **COMPLETE** (2025-11-07)  
**Duration:** 2 weeks  
**Complexity:** Medium

Implemented iterative refinement pattern with producer-evaluator feedback loops, quality score evaluation with retry logic, and convergence detection with configurable acceptance criteria.

---

## Phase 5: Security & Guardrails (v0.6.0)

**Goal:** Enterprise-grade security controls and policy enforcement

**Duration:** 3 weeks  
**Complexity:** High  
**Dependencies:** None (can run in parallel with pattern work)

### Features

#### 5.1 Guardrails Enforcement
- Activate `security.guardrails` (currently parsed but not enforced)
- **Network controls**:
  - `deny_network: true` → block all HTTP tools and external API calls
  - Tool allowlist: only execute tools in `security.guardrails.allow_tools`
- **PII redaction**:
  - `pii_redaction: true` → scan inputs/outputs for PII patterns
  - Redact: emails, SSNs, credit cards, phone numbers, addresses
  - Log redaction events for compliance audit

#### 5.2 Secrets Management
- Add `source: secrets_manager` (AWS Secrets Manager)
- Add `source: ssm` (AWS Systems Manager Parameter Store)
- Implement secret caching with TTL
- Validate secret permissions at runtime
- Never log or trace secret values

#### 5.3 Tool Sandboxing
- Extend Python tool allowlist configuration
- Add tool permission levels (read-only, network, filesystem)
- Validate tool inputs against schemas
- Timeout enforcement per tool call
- Resource limits (memory, CPU)

#### 5.4 Audit Logging
- Log all security-relevant events:
  - Secret access
  - Guardrail violations
  - Tool executions
  - Network requests
  - PII redactions
- Export audit logs to CloudWatch/S3
- Structured JSON format for SIEM integration

### Acceptance Criteria

- [ ] `deny_network: true` blocks HTTP executor calls
- [ ] Tool allowlist rejects non-allowlisted tools at runtime
- [ ] PII redaction removes sensitive data from outputs
- [ ] Secrets Manager/SSM secrets load correctly
- [ ] Secret values never appear in logs or traces
- [ ] Audit log contains all required security events
- [ ] Coverage ≥85%
- [ ] New tests: `test_security.py` (guardrails, redaction, secrets)

### Implementation Checklist

- [ ] **Use context7** to get boto3 Secrets Manager and SSM documentation
- [ ] **Review schema** `security.guardrails` and `env.secrets` definitions
- [ ] Use **ref.tools** to research PII detection patterns and OWASP guidelines
- [ ] Implement guardrail enforcement in `runtime/tools.py`
- [ ] Add PII detection patterns and redaction logic
- [ ] Create `runtime/secrets.py` for ASM/SSM integration
- [ ] Add audit logger in `telemetry/audit.py`
- [ ] Update tool adapters with permission checks
- [ ] Add security examples and documentation
- [ ] Compliance guide for enterprise deployments
- [ ] Security testing with malicious inputs

---

## Phase 6: Context Management (v0.7.0)

**Goal:** Intelligent context handling for long-running workflows

**Status:** 📋 **PLANNED** (Implementation plan complete)  
**Duration:** 2-3 weeks  
**Complexity:** High  
**Dependencies:** Phase 1-5 (multi-step workflows, token tracking)  
**Detailed Plan:** See `docs/PHASE6_IMPLEMENTATION_PLAN.md`

### Overview

Implement intelligent context management using **native Strands SDK primitives** with minimal custom glue:
- **Native**: `SummarizingConversationManager` for context compaction
- **Partial**: Community tools (`journal`, `file_ops`) + hooks for structured notes
- **Partial**: JIT retrieval tools + MCP integration for external knowledge
- **Partial**: Metrics + runtime guards for token budget enforcement

Based on research in `docs/strands-phase6-context-research.md`.

### Features

#### 6.1 Context Compaction
- **Native Strands support**: Use `SummarizingConversationManager` with configurable `summary_ratio` and `preserve_recent_messages`
- **Proactive trigger**: Custom hook monitors token count and triggers compaction before overflow
- **Configurable summarization agent**: Optional cheaper model (e.g., GPT-4o-mini) for cost savings
- **Preservation**: Maintains recent messages and tool-result pairs

#### 6.2 Structured Notes
- **Community tools integration**: Use `strands-agents-tools` for file I/O (`journal`, `file_read`, `file_write`)
- **Hook-based appending**: `NotesAppenderHook` writes Markdown entries after each step
- **Context injection**: Include last N notes in agent context before each step
- **Format**: Markdown with ISO8601 timestamps, agent attribution, tools used, and outcomes
- **Cross-session continuity**: Persist notes file and reload on workflow resume

#### 6.3 JIT Retrieval Tools
- **Local tools**: `grep`, `head`, `tail`, `search` wrappers using community `shell` and `editor` tools
- **MCP integration**: First-class support for external knowledge bases (Confluence, internal KB)
- **Smart selection**: System prompt hints or hooks for relevance-based tool selection
- **On-demand loading**: Retrieve context only when needed, not preloaded

#### 6.4 Token Budget Management
- **Real-time counting**: tiktoken-based token estimation for all providers
- **Warning system**: Alert at 80% threshold with context message
- **Auto-compaction**: Trigger compaction on warning to extend runway
- **Hard limit**: Abort with `EX_BUDGET_EXCEEDED (19)` at 100%
- **Metrics**: Export budget usage to OTEL (Phase 10 integration)

### Architecture

```
New Modules:
- runtime/context_manager.py      # Strands ConversationManager wrapper
- runtime/token_counter.py        # tiktoken-based counting
- runtime/budget_enforcer.py      # Budget guard hook
- tools/jit_retrieval.py          # grep/search/head/tail adapters
- tools/notes_manager.py          # Markdown notes I/O
- exec/hooks.py                   # Context hooks (compaction, notes, budget)

Modified:
- exec/*.py (all executors)       # Integrate context hooks
- exec/utils.py (AgentCache)      # Accept conversation_manager + hooks
- types.py                        # Expand ContextPolicy models
```

### Acceptance Criteria

- [ ] Compaction triggers at configured threshold and reduces context by ≥30%
- [ ] Notes file persists across steps with correct Markdown format
- [ ] JIT retrieval tools fetch context without loading full files
- [ ] Token budget enforcement prevents over-limit calls with warnings at 80%
- [ ] Compaction preserves task-critical information (recent messages, tool results)
- [ ] MCP integration connects to external knowledge bases
- [ ] All existing tests pass (479 tests)
- [ ] New tests: ≥40 tests for context features
- [ ] Coverage ≥85%
- [ ] Documentation: Manual updated, 3+ example workflows

### Implementation Checklist

**Week 1: Foundation & Compaction**
- [ ] Install dependencies: `tiktoken`, `strands-agents-tools`, `filelock`
- [ ] Expand `types.py` - detailed `ContextPolicy` models (Compaction, Notes, Retrieval)
- [ ] Create `runtime/context_manager.py` - wrapper for `SummarizingConversationManager`
- [ ] Create `exec/hooks.py` - `ProactiveCompactionHook` implementation
- [ ] Unit + integration tests for compaction (3-step chain with summarization)

**Week 2: Notes & Retrieval**
- [ ] Create `tools/notes_manager.py` - Markdown I/O with file locking
- [ ] Create `NotesAppenderHook` - append after each cycle
- [ ] Implement notes injection in executors (before each step)
- [ ] Create `tools/jit_retrieval.py` - grep/search/head/tail wrappers
- [ ] Add MCP integration pattern for external KB
- [ ] Unit + integration tests for notes and JIT tools

**Week 3: Budgets & Integration**
- [ ] Create `runtime/token_counter.py` - tiktoken integration
- [ ] Create `runtime/budget_enforcer.py` - `BudgetEnforcerHook`
- [ ] Add `EX_BUDGET_EXCEEDED = 19` to `exit_codes.py`
- [ ] Update all 5 executors to integrate hooks
- [ ] Update `AgentCache` to accept conversation manager and hooks
- [ ] E2E tests with all features enabled
- [ ] Update manual with context policy examples
- [ ] Create 4+ example workflows
- [ ] Performance benchmarking (compaction <500ms, notes <50ms)
- [ ] Final CI run: `.\scripts\dev.ps1 ci`

### Key Design Decisions

1. **Strands-native approach**: Leverage SDK's `SummarizingConversationManager` instead of custom implementation
2. **Proactive compaction**: Hook-based monitoring triggers compaction before overflow (reactive is too late)
3. **Community tools**: Use `strands-agents-tools` for file ops and shell commands (don't reinvent)
4. **Markdown notes**: Human-readable format with clear structure (JSON later if needed)
5. **Budget warning flow**: Warn (80%) → auto-compact → warn again → hard limit (100%)
6. **Token counting**: tiktoken for estimates, provider usage for ground truth
7. **Hook pattern**: All context features implemented as composable hooks attached to agents

### Dependencies

```toml
# New dependencies
tiktoken = "^0.8.0"              # Token counting
strands-agents-tools = "^0.1.0"   # Community tools (journal, file ops, shell)
filelock = "^3.16.0"              # Cross-process file locking
```

### Examples to Create

1. `examples/context-long-research-openai.yaml` - 5-step, 150K tokens, compaction demo
2. `examples/context-notes-continuation-ollama.yaml` - Multi-session with notes persistence
3. `examples/context-jit-retrieval-bedrock.yaml` - Large codebase with grep/search
4. `examples/context-budget-constrained-openai.yaml` - Tight budget with auto-compaction

### Documentation Updates

- [ ] `docs/strands-workflow-manual.md` - Expand section 8 (Context Policy) with all features
- [ ] `docs/CONTEXT_MANAGEMENT_GUIDE.md` - NEW: Deep dive guide with best practices
- [ ] `README.md` - Add context management to features list
- [ ] `CHANGELOG.md` - Document v0.7.0 changes

---

## Phase 7: Orchestrator-Workers Pattern (v0.8.0)

**Goal:** Dynamic task delegation with worker pools

**Duration:** 3 weeks  
**Complexity:** Very High  
**Dependencies:** Phase 3 (parallel execution), Phase 6 (context management)

### Features

#### 7.1 Orchestrator Agent
- Implement `pattern.type = orchestrator_workers` in `exec/orchestrator.py`
- **Orchestrator responsibilities**:
  - Break down task into subtasks
  - Assign subtasks to workers (dynamic allocation)
  - Monitor worker progress
  - Synthesize worker results
- **Limits**:
  - `max_workers` - Maximum concurrent workers
  - `max_rounds` - Maximum orchestration iterations

#### 7.2 Worker Pool Management
- Dynamic worker instantiation from `worker_template`
- Worker state tracking (idle, working, complete, failed)
- Load balancing across workers
- Worker timeout and retry
- Graceful worker failure handling

#### 7.3 Work Queue
- Task queue for subtask distribution
- Priority-based scheduling
- Duplicate detection
- Progress tracking and reporting

#### 7.4 Reduce & Writeup
- Optional `reduce` step to aggregate worker outputs
- Optional `writeup` step for final report generation
- Template access to all worker results

### Acceptance Criteria

- [ ] Orchestrator delegates 5 subtasks to 3 workers
- [ ] Workers execute in parallel respecting max_workers limit
- [ ] Failed worker retries with different worker instance
- [ ] Reduce step receives all worker outputs
- [ ] Writeup step generates final report
- [ ] Worker progress tracked in real-time
- [ ] Coverage ≥85%
- [ ] New tests: `test_orchestrator.py` (delegation, pooling, aggregation)

### Implementation Checklist

- [ ] **Consult `strands-workflow-manual.md`** section 12.4 (Orchestrator-Workers) for delegation semantics
- [ ] **Review schema** `orchestratorWorkersConfig` for orchestrator, worker_template, reduce, writeup
- [ ] **Use ref.tools** to research worker pool patterns and task queue implementations
- [ ] Create `exec/orchestrator.py` with delegation logic
- [ ] Implement worker pool manager
- [ ] Add task queue with priority scheduling
- [ ] Create worker state machine
- [ ] Extend template context with worker outputs
- [ ] Update capability checker for orchestrator pattern
- [ ] Add orchestrator examples (research swarm, data processing)
- [ ] Document orchestration patterns and best practices

---

## Phase 8: Graph Pattern & Advanced Control Flow (v0.9.0)

**Goal:** Explicit control flow with conditionals and loops

**Duration:** 3 weeks  
**Complexity:** Very High  
**Dependencies:** Phase 1 (DAG execution), Phase 2 (conditional logic)

### Features

#### 8.1 Graph Pattern
- Implement `pattern.type = graph` in `exec/graph.py`
- **Nodes**: Map of node_id → agent + input
- **Edges**: Explicit transitions between nodes
  - Static: `to: [node_ids]` - Unconditional transitions
  - Conditional: `choose: [{when, to}]` - Evaluated conditions
- **Execution**:
  - Start at first node (or explicit entry node)
  - Execute node agent
  - Evaluate edge conditions
  - Transition to next node(s)
  - Detect cycles and apply max iterations limit

#### 8.2 Condition Evaluation
- Simple expression language for `when` clauses
- Access to node outputs: `{{ node.<id>.score >= 85 }}`
- Boolean operators: AND, OR, NOT
- Comparison operators: ==, !=, <, <=, >, >=
- Special `else` clause for default transitions

#### 8.3 Loop Detection & Control
- Detect cycles in graph
- Max iterations per cycle (configurable)
- Break conditions to exit loops early
- Prevent infinite loops

#### 8.4 Graph Visualization
- Generate graph visualization in `plan` command
- Export DOT format for Graphviz rendering
- Highlight execution path in trace output

### Acceptance Criteria

- [ ] Graph with 5 nodes and conditional edges executes correctly
- [ ] Loop executes 3 times before break condition
- [ ] Condition evaluation works for numeric and string comparisons
- [ ] Infinite loop protection triggers after max iterations
- [ ] Graph visualization shows all nodes and edges
- [ ] Coverage ≥85%
- [ ] New tests: `test_graph.py` (conditionals, loops, cycles)

### Implementation Checklist

- [ ] **Consult `strands-workflow-manual.md`** section 12.6 (Graph) for nodes, edges, and choose conditions
- [ ] **Review schema** `graphConfig` definition for conditional edges and cycle detection
- [ ] **Use ref.tools** to research graph execution engines and topological traversal
- [ ] Create `exec/graph.py` with graph executor
- [ ] Implement condition parser and evaluator
- [ ] Add cycle detection and loop limiting
- [ ] Create graph visualizer (consider Graphviz/DOT format)
- [ ] Update capability checker for graph pattern
- [ ] Add graph examples (state machines, decision trees)
- [ ] Document graph pattern and condition syntax
- [ ] Add graph execution trace visualization

---

## Phase 9: MCP Tools Integration (v0.10.0)

**Goal:** Model Context Protocol server integration

**Duration:** 2-3 weeks  
**Complexity:** High  
**Dependencies:** Phase 5 (tool sandboxing)

### Features

#### 9.1 MCP Server Support
- Remove MCP restriction in `capability/checker.py`
- Implement MCP client in `runtime/mcp.py`
- **Server lifecycle**:
  - Start MCP server process (`command` + `args`)
  - Initialize protocol handshake
  - Register available tools
  - Maintain server connection
  - Shutdown on workflow completion
- **Environment isolation**:
  - Pass `env` variables to MCP server
  - Sandbox server execution
  - Resource limits (CPU, memory, network)

#### 9.2 MCP Tool Adapter
- Adapt MCP tool schema to Strands tool format
- Handle streaming responses
- Timeout and cancellation
- Error translation and retry

#### 9.3 Popular MCP Servers
- Pre-configure common MCP servers:
  - Filesystem operations
  - Git operations
  - Database queries
  - Web scraping
  - Custom tools

### Acceptance Criteria

- [ ] MCP server starts and registers tools successfully
- [ ] Agent can invoke MCP tools during execution
- [ ] MCP server shuts down cleanly on completion
- [ ] Timeout kills unresponsive MCP server
- [ ] MCP tool errors handled gracefully
- [ ] Coverage ≥85%
- [ ] New tests: `test_mcp.py` (lifecycle, invocation, errors)

### Implementation Checklist

- [ ] **Consult `strands-workflow-manual.md`** section 10 (Tools) for MCP configuration
- [ ] **Review schema** `tools.mcp` definition for command, args, env
- [ ] **Use ref.tools** to search Model Context Protocol specification and best practices
- [ ] **Use context7** to get MCP SDK documentation if available
- [ ] Create `runtime/mcp.py` with MCP client
- [ ] Implement MCP protocol handshake
- [ ] Add MCP tool adapter
- [ ] Create MCP server process manager
- [ ] Update capability checker to allow MCP tools
- [ ] Add MCP examples (filesystem, git, database)
- [ ] Document MCP integration and server setup
- [ ] Test with popular MCP servers

---

## Phase 10: Observability & Debugging (v0.11.0)

**Goal:** Enable production observability and debugging with full OpenTelemetry tracing

**Duration:** 2-3 weeks  
**Complexity:** Medium  
**Dependencies:** Phases 1-9 (benefits from all patterns being implemented for comprehensive tracing)

### Features

#### 10.1 OpenTelemetry Tracing
- **Activate TracerProvider** in `telemetry/otel.py` (currently no-op)
- Emit spans for workflow lifecycle:
  - `validate` - Schema validation duration and errors
  - `plan` - Capability checking and normalization
  - `build_agent` - Agent construction with tool binding
  - `execute` - Full workflow execution
  - `tool:<tool_id>` - Individual tool invocations
  - `llm:completion` - Model API calls with token counts
- **Attributes per span**:
  - `spec.name`, `spec.version`, `spec.tags`
  - `runtime.provider`, `runtime.model_id`, `runtime.region`
  - `pattern.type`, `agent.id`, `tool.id`
  - `error.type`, `error.message` (on failures)
- **Export targets**:
  - Console JSON (local dev)
  - OTLP HTTP/gRPC (remote collectors)
  - Configurable via `telemetry.otel.endpoint`

#### 10.2 Trace Artifacts
- Implement `$TRACE` special artifact source
- Export complete trace to JSON file: `./artifacts/<name>-trace.json`
- Include timing, spans, attributes, and errors
- Enable `--trace` flag for ad-hoc trace emission

#### 10.3 Redaction & Privacy
- Activate `telemetry.redact.tool_inputs` / `tool_outputs`
- Scrub sensitive data from spans before export:
  - API keys, tokens, credentials
  - PII patterns (email, SSN, credit cards)
  - User-defined redaction patterns
- Log redaction events for audit

#### 10.4 Verbose Debugging
- Enhance `--verbose` mode with structured logging
- Add `--debug` flag for trace-level logs
- Include:
  - Variable resolution steps
  - Template rendering output
  - Tool binding details
  - Provider API request/response (redacted)

### Acceptance Criteria

- [ ] All spans emitted with correct parent-child relationships
- [ ] Trace JSON includes all lifecycle events with <1ms timestamp precision
- [ ] Redaction removes secrets from tool spans (validated with test fixtures)
- [ ] `--trace` flag produces `<name>-trace.json` artifact
- [ ] OTLP export works with Jaeger/Zipkin/Honeycomb
- [ ] Coverage remains ≥85%
- [ ] New tests: `test_telemetry.py` (trace activation, span structure, redaction)

### Implementation Checklist

- [ ] **Consult `strands-workflow-manual.md`** section 7 (Telemetry) for OTEL and redaction config
- [ ] **Review schema** `telemetry` definition for otel endpoint, sample_ratio, redact options
- [ ] **Use context7** to get OpenTelemetry Python SDK documentation
- [ ] **Use ref.tools** to search OTLP protocol specs and span attribute conventions
- [ ] Implement `OTELTracerProvider` in `telemetry/otel.py`
- [ ] Add span decorators to key functions (`@tracer.start_as_current_span`)
- [ ] Create trace export logic in `artifacts/io.py`
- [ ] Add redaction patterns and PII scrubbing
- [ ] Update `run` command to initialize tracer
- [ ] Add integration tests with mock OTLP collector
- [ ] Document OTEL configuration in README
- [ ] Add example trace JSON to `examples/traces/`

---

## Phase 11: Production Hardening (v1.0.0-rc)

**Goal:** Enterprise readiness and reliability

**Duration:** 3-4 weeks  
**Complexity:** Medium  
**Dependencies:** All previous phases

### Features

#### 11.1 Durability & Resume
- Implement workflow state persistence
- Checkpoint after each step/task completion
- **Resume command**: `strands resume <session-id>`
- Crash recovery with state restoration
- Idempotent step execution

#### 11.2 Rate Limiting & Throttling
- Provider-specific rate limits (Bedrock, OpenAI)
- Exponential backoff with jitter
- Circuit breaker pattern for failing services
- Request queue with priority

#### 11.3 Cost Management
- Token usage tracking per workflow
- Cost estimation before execution
- Budget alerts and hard limits
- Cost attribution by agent/step

#### 11.4 Performance Optimization
- Agent caching (reuse agents across steps)
- Tool result caching
- Parallel template rendering
- Lazy loading of large artifacts

#### 11.5 Monitoring & Alerting
- Prometheus metrics exporter
- Health check endpoint
- Error rate and latency tracking
- Custom alert rules

### Acceptance Criteria

- [ ] Workflow resumes from checkpoint after crash
- [ ] Rate limit backoff prevents provider throttling
- [ ] Cost tracking accurate within 5%
- [ ] Budget alert fires before limit exceeded
- [ ] Metrics export to Prometheus
- [ ] Health check returns status
- [ ] Coverage ≥85%
- [ ] New tests: `test_durability.py`, `test_performance.py`

### Implementation Checklist

- [ ] **Use context7** to get tenacity documentation for advanced retry patterns
- [ ] **Use ref.tools** to research circuit breaker patterns and rate limiting algorithms
- [ ] **Use context7** to get Prometheus Python client documentation
- [ ] Create `runtime/state.py` for checkpoint management
- [ ] Implement resume command and state restoration
- [ ] Add rate limiter and circuit breaker
- [ ] Create cost calculator for all providers
- [ ] Add Prometheus metrics exporter
- [ ] Implement caching layers
- [ ] Add health check endpoint
- [ ] Performance benchmarking suite
- [ ] Load testing with large workflows

---

## Phase 12: Enterprise Features (v1.0.0)

**Goal:** Production release with enterprise capabilities

**Duration:** 4 weeks  
**Complexity:** High  
**Dependencies:** Phase 11 (production hardening)

### Features

#### 12.1 Human-in-the-Loop
- Implement `manual_gate` step type
- Integration with Slack for approvals
- Integration with Jira for task assignment
- Configurable timeout for human response
- Fallback automation on timeout

#### 12.2 Multi-Provider Support
- Add OpenAI provider
- Add Azure OpenAI provider
- Add Anthropic API provider (direct, not via Bedrock)
- Provider fallback on failures
- Cost optimization across providers

#### 12.3 Workflow Catalog
- Built-in workflow templates
- Import/export workflows
- Version control integration
- Workflow sharing and discovery

#### 12.4 Advanced Analytics
- Langfuse integration for LLM observability
- Token usage analytics and optimization
- Agent performance comparison
- Cost breakdown by pattern/agent/tool

#### 12.5 CLI Enhancements
- Interactive mode for workflow building
- Workflow validation with suggestions
- Auto-fix for common issues
- Rich TUI for workflow monitoring

### Acceptance Criteria

- [ ] Slack approval gate pauses workflow until approval
- [ ] OpenAI and Azure OpenAI providers work correctly
- [ ] Provider fallback switches on error
- [ ] Workflow catalog loads and executes templates
- [ ] Langfuse trace export includes all LLM calls
- [ ] Interactive mode creates valid workflows
- [ ] Coverage ≥85%
- [ ] Production deployment guide complete

### Implementation Checklist

- [ ] **Use context7** to get Slack SDK and Jira Python SDK documentation
- [ ] **Use context7** to get OpenAI Python SDK and Azure OpenAI documentation
- [ ] **Use ref.tools** to search Langfuse integration patterns
- [ ] Create `integrations/slack.py` for approval gates
- [ ] Create `integrations/jira.py` for task assignment
- [ ] Add OpenAI and Azure provider adapters
- [ ] Implement provider fallback logic
- [ ] Build workflow catalog system
- [ ] Add Langfuse exporter
- [ ] Create interactive CLI mode
- [ ] Write deployment and operations guide
- [ ] Security audit and penetration testing
- [ ] Performance tuning for production scale

---

## Testing Strategy

### Per-Phase Testing Requirements

Each phase must include:

1. **Unit tests** - Core logic with mocked dependencies (≥80% coverage)
2. **Integration tests** - Component interactions with test fixtures (≥70% coverage)
3. **E2E tests** - Full workflow execution with real/mock providers (≥60% coverage)
4. **Regression tests** - Previous phases continue working

### Test Fixtures Organization

```
tests/
├── fixtures/
│   ├── valid/
│   │   ├── phase1-otel.yaml
│   │   ├── phase2-chain-3step.yaml
│   │   ├── phase3-routing.yaml
│   │   ├── phase4-parallel.yaml
│   │   └── ...
│   ├── invalid/
│   │   └── (schema violations per phase)
│   └── unsupported/
│       └── (features not yet implemented)
├── test_phase1_otel.py
├── test_phase2_multiStep.py
├── test_phase3_routing.py
└── ...
```

### Continuous Integration

- All tests run on every commit
- Coverage must be ≥85% before merge
- Lint, typecheck, and format checks required
- E2E tests run against real Ollama (local) and mocked Bedrock
- Performance regression tests for critical paths

---

## Documentation Updates Per Phase

### Required Documentation

Each phase must update:

1. **README.md** - Add new features to feature list and examples
2. **CHANGELOG.md** - Document changes following Keep a Changelog format
3. **User Guide** - Add pattern/feature documentation with examples
4. **API Reference** - Update if new public interfaces added
5. **Migration Guide** - If breaking changes (minimize in minor versions)

### Examples

Each phase must add 2-3 example specs to `examples/` demonstrating new capabilities.

---

## Version Numbering

- **v0.x.0** - Minor versions during feature development
- **v1.0.0-rc.x** - Release candidates with all features, hardening in progress
- **v1.0.0** - Production release
- **v1.x.0** - Post-release minor features
- **v2.0.0** - Breaking changes (avoid if possible)

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Strands SDK API changes | Medium | High | Pin SDK version; monitor releases |
| Provider rate limits | High | Medium | Implement backoff and caching early (Phase 11) |
| State corruption on crash | Low | High | Write-ahead logging; atomic commits (Phase 11) |
| Token budget overruns | Medium | Medium | Strict enforcement in Phase 7 |
| MCP server instability | Medium | Low | Timeout, isolation, circuit breaker (Phase 10) |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Complexity underestimation | Medium | High | Add 20% buffer; descope if needed |
| Testing bottleneck | Medium | Medium | Test-first approach; parallel test writing |
| Dependency delays | Low | Medium | Phases designed to be independent where possible |

---

## Success Metrics

### Per-Phase Metrics

- **Test coverage**: ≥85% (measured by `pytest --cov`)
- **Performance**: No >20% regression on single-agent workflows
- **Documentation**: All new features documented with examples
- **Exit codes**: All failures use correct exit codes (no generic exit 1)

### Overall Success (v1.0.0)

- **All 7 patterns implemented** and tested
- **Production deployments**: ≥3 internal teams using strands-cli
- **Community adoption**: ≥10 external users/organizations
- **Reliability**: ≥99.5% success rate on valid workflows
- **Performance**: <500ms overhead vs direct SDK usage
- **Security**: Pass enterprise security audit

---

## Dependencies & Prerequisites

### Development Environment

- Python ≥3.12
- uv package manager
- AWS credentials (for Bedrock)
- Ollama server (for Ollama)
- Docker (for MCP server testing)
- Git (for version control)

### External Services

- **Phase 1**: OTLP collector (Jaeger/Zipkin) for trace testing
- **Phase 6**: AWS Secrets Manager/SSM access
- **Phase 10**: MCP server implementations
- **Phase 12**: Slack workspace, Jira instance (for integration testing)

---

## Questions & Decisions Needed

1. **Provider priority**: Which additional providers after OpenAI/Azure? (Cohere, AI21, local llama.cpp?)
2. **MCP servers**: Bundle common MCP servers or require separate installation?
3. **State storage**: Local filesystem, S3, or database for workflow state?
4. **UI**: Build web UI for workflow monitoring or keep CLI-only?
5. **Pricing model**: Open source, commercial license, or dual-license?

---

## Appendix: Phase Dependencies Graph

```
Phase 1 (Multi-step) ───┬─> Phase 2 (Routing) ───┐
                        │                         │
Phase 5 (Security) ─────┤                         ├─> Phase 4 (Evaluator)
                        │                         │
                        └─> Phase 3 (Parallel) ───┼─> Phase 7 (Orchestrator) ──┐
                                                  │                             │
Phase 6 (Context) ────────────────────────────> │                             │
                                                  │                             │
                                                  └─> Phase 8 (Graph) ──────────┤
                                                                                │
Phase 9 (MCP) ──────────────────────────────────────────────────────────────> │
                                                                                │
                                                                                ├─> Phase 10 (OTEL)
                                                                                │
                                                                                └─> Phase 11 (Hardening) ─> Phase 12 (Enterprise) ─> v1.0.0
```

---

## Appendix: Example Workflow Evolution

### MVP (v0.1.0) - Current
```yaml
version: 0
name: "simple-analysis"
runtime:
  provider: ollama
  host: "http://localhost:11434"
  model_id: "gpt-oss"

agents:
  analyst:
    prompt: "Analyze {{topic}} and provide insights."

pattern:
  type: chain
  config:
    steps:
      - agent: analyst
        input: "Analyze the topic."

outputs:
  artifacts:
    - path: "./artifacts/analysis.md"
      from: "{{ last_response }}"
```

### Phase 1 (v0.2.0) - Multi-step
```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
      - agent: analyst
        input: "Analyze findings from {{ steps[0].response }}"
      - agent: writer
        input: "Write report based on {{ steps[1].response }}"
```

### Phase 3 (v0.4.0) - Parallel
```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: web
        steps: [...]
      - id: docs
        steps: [...]
    reduce:
      agent: synthesizer
      input: "Merge {{ branches.web.response }} and {{ branches.docs.response }}"
```

### Phase 7 (v0.8.0) - Orchestrator
```yaml
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent: planner
      limits:
        max_workers: 5
        max_rounds: 3
    worker_template:
      agent: researcher
      tools: ["http_executors", "strands_tools.http_request"]
    reduce:
      agent: synthesizer
    writeup:
      agent: writer
```

---

**End of Plan**

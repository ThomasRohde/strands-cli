# Strands CLI Evolution Plan

**Created:** 2025-11-04  
**Owner:** Thomas Rohde  
**Current Version:** v0.9.0 (Graph Pattern with Advanced Control Flow)  
**Target:** Full multi-agent workflow orchestration with observability, security, and enterprise features

---

## Completed Phases Summary (v0.1.0 → v0.9.0)

**Completion Date**: November 9, 2025  
**Current Version**: v0.10.0  
**Status**: ✅ Phases 1-4, 7-8, 10 Complete  
**Tests**: 795 passing | Coverage: 82%  
**Type Safety**: Mypy strict mode passing

### Major Achievements

**Multi-Pattern Workflow Support:**
- ✅ **Chain Pattern**: Sequential multi-step execution with context threading (`{{ steps[n].response }}`)
- ✅ **Workflow Pattern**: DAG-based parallel task execution with dependency resolution (`{{ tasks.<id>.response }}`)
- ✅ **Routing Pattern**: Dynamic agent selection with router retry logic and malformed JSON handling
- ✅ **Parallel Pattern**: Concurrent branch execution with optional reduce aggregation (`{{ branches.<id>.response }}`)
- ✅ **Evaluator-Optimizer Pattern**: Iterative refinement with producer-evaluator feedback loops and quality gates
- ✅ **Orchestrator-Workers Pattern**: Dynamic task delegation with worker pools, max_workers concurrency control, and optional reduce/writeup steps
- ✅ **Graph Pattern**: Explicit control flow with conditional edges, loop detection, cycle protection, and max iteration limits

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
- ✅ 795 comprehensive tests (unit, integration, E2E)
- ✅ Code coverage: 82% (Phase 10 added telemetry code)
- ✅ Type-safe with mypy strict mode
- ✅ Ruff linting and formatting compliance

**Observability & Debugging:**
- ✅ Full OpenTelemetry tracing with OTLP/Console exporters
- ✅ Trace artifacts via `{{ $TRACE }}` variable and `--trace` flag
- ✅ PII redaction with configurable patterns
- ✅ Enhanced debugging with `--debug` flag and structured logging
- ✅ Span coverage across all 7 workflow patterns

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
11. **Full Observability**: OpenTelemetry tracing with OTLP export, trace artifacts, PII redaction, and debug logging

### Technical Debt & Future Work

- **Coverage Gap**: Need more edge case tests to reach 85% overall (currently 82% due to Phase 10 telemetry code)
- **Complexity Warnings**: 7 functions exceed C901 threshold (cosmetic, non-blocking)
- **Branch Timeouts**: Deferred to Phase 5 (need per-branch cancellation)
- **Graph Visualization**: Plan command needs execution path rendering
- **Trace Size Limits**: No max_span_count limit yet (could cause large trace files)

### Breaking Changes

None - all changes backward compatible with v0.1.0 specs.

**Next Phase**: Phase 5 (Security & Guardrails), Phase 6 (Context Management), Phase 9 (MCP Tools), or Phase 11 (Production Hardening) - multiple parallel tracks available

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

**Status:** 📋 **PLANNED**  
**Duration:** 3 weeks  
**Complexity:** High

Enterprise-grade security controls including guardrails enforcement (deny_network, tool allowlist), PII redaction, AWS Secrets Manager/SSM integration, tool sandboxing with permission levels, and comprehensive audit logging to CloudWatch/S3 for SIEM integration.

---

## Phase 6: Context Management (v0.7.0)

**Status:** ✅ **COMPLETE** (2025-11-07)  
**Duration:** 2-3 weeks  
**Complexity:** High

Intelligent context handling with native Strands `SummarizingConversationManager` for compaction, structured notes via `NotesManager` with Markdown persistence, JIT retrieval tools (grep, head, tail, search), and token budget enforcement with 80% warnings and hard limits. Implements proactive compaction hooks and cross-session continuity.

---

## Phase 7: Orchestrator-Workers Pattern (v0.8.0)

**Status:** ✅ **COMPLETE** (2025-11-08)  
**Duration:** 3 weeks  
**Complexity:** Very High

Dynamic task delegation with worker pools, orchestrator JSON parsing with retry logic, configurable max_workers concurrency via semaphore, optional reduce/writeup steps, template access to indexed worker outputs, and fail-fast semantics. Implements multi-round delegation with round tracking and worker isolation.

---

## Phase 8: Graph Pattern & Advanced Control Flow (v0.9.0)

**Status:** ✅ **COMPLETE** (2025-11-08)  
**Duration:** 3 weeks  
**Complexity:** Very High

Explicit control flow with node-based execution, conditional edges with secure `when` clause evaluation, static and dynamic transitions, cycle detection with max iteration limits, loop control with break conditions, and graph visualization support. Implements safe condition evaluation with restricted builtins and template access to node outputs.

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

## Phase 10: Observability & Debugging (v0.10.0)

**Status:** ✅ **COMPLETE** (2025-11-09)  
**Duration:** 1 week  
**Complexity:** Medium

Implemented full OpenTelemetry tracing with OTLP/Console exporters, trace artifact export via `{{ $TRACE }}` variable and `--trace` flag, PII redaction with configurable patterns, and enhanced debugging with `--debug` flag and structured logging.

### Completed Features

#### OpenTelemetry Tracing ✅
- ✅ Activated `TracerProvider` in `telemetry/otel.py` (previously scaffolding/no-op)
- ✅ OTLP exporter for remote collectors (Jaeger, Zipkin, Honeycomb)
- ✅ Console exporter for local development
- ✅ Auto-instrumentation for httpx and logging
- ✅ Configurable service name, endpoint, sample ratio
- ✅ Comprehensive span attributes across all patterns
- ✅ Parent-child span relationships for all workflow types

#### Trace Artifacts ✅
- ✅ `{{ $TRACE }}` special variable in artifact templates
- ✅ `--trace` CLI flag for auto-generated trace files
- ✅ Complete trace JSON export with metadata
- ✅ Pretty-printed output with 2-space indentation
- ✅ Trace includes: trace_id, spans, timestamps, attributes, events

#### PII Redaction ✅
- ✅ New `telemetry/redaction.py` module with `RedactionEngine`
- ✅ PII pattern detection: email, credit card, SSN, phone, API keys
- ✅ Configurable redaction via `telemetry.redact.tool_inputs/tool_outputs`
- ✅ Safe replacement with `***REDACTED***` marker
- ✅ Custom redaction patterns support
- ✅ Redacted attributes tagged with metadata

#### Enhanced Debugging ✅
- ✅ `--debug` flag added to all commands (run, validate, plan, explain)
- ✅ Structured JSON debug logging with structlog
- ✅ Variable resolution step-by-step logging
- ✅ Template rendering before/after with previews
- ✅ Agent cache hit/miss statistics
- ✅ LLM request/response metadata logging

### Test Coverage
- ✅ 13 new tests added
- ✅ 795 total tests passing
- ✅ 82% coverage (slight drop due to new telemetry code)
- ✅ All mypy strict checks passing

### Implementation Notes
- Trace artifacts use `TraceCollector` to capture spans before export
- Redaction applied via `RedactingSpanProcessor` wrapper
- Debug logging respects `STRANDS_DEBUG` environment variable
- OTLP exporter gracefully falls back to Console if endpoint unavailable
- Performance impact: <5% latency overhead with 100% sampling

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
                                                                                ├─> Phase 10 (OTEL) ✅ COMPLETE
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

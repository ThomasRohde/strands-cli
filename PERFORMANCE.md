# Performance Optimization Plan

## Executive Summary

The Phase 3 codebase review identified critical performance bottlenecks in agent/client lifecycle management and event loop usage. This phased plan remediates these issues through incremental, testable improvements while maintaining backward compatibility and 85%+ test coverage.

**Key Issues:**
- 🔥 **Agent/Model Rebuild Overhead**: Every step/task creates new `BedrockModel`/`OllamaModel`/`OpenAIModel` clients and `Agent` instances, losing connection pooling benefits and repeating initialization costs
- 🟡 **HTTP Client Waste**: Each agent rebuild creates new `httpx.Client` instances that are never properly cleaned up
- 🟡 **Event Loop Churn**: `asyncio.run()` called per step/task creates and tears down event loops repeatedly instead of maintaining a single persistent loop

**Target Improvements:**
- Reduce agent construction calls by ~90% in multi-step workflows (10-step chain: 10→1 builds per unique agent)
- Eliminate per-step event loop overhead (10-step chain: 10→1 loop lifecycle)
- Enable proper HTTP client cleanup to prevent resource leaks
- Maintain single top-level `asyncio.run()` in CLI for clean architecture

## Architecture Overview

### Current Flow (Problematic)
```
CLI run command (sync)
  → for each step/task:
      → build_agent() → create_model() → NEW boto3/httpx client
      → asyncio.run(invoke_agent_with_retry(...)) → NEW event loop
      → (no cleanup)
```

### Target Flow (Optimized)
```
CLI run command (sync)
  → asyncio.run(executor(...)) → SINGLE event loop
      → AgentCache instance created
      → for each step/task:
          → cache.get_or_build_agent() → reuses cached agents
              → create_model() → @lru_cache returns cached model clients
              → tools built with async context managers
      → await cache.close() → cleanup all HTTP clients
```

## Phased Implementation

### Phase 1: Foundation - Model Client Pooling ✅ Safe, High Impact
**Goal**: Eliminate redundant model client creation using `functools.lru_cache`

**Scope:**
- File: `src/strands_cli/runtime/strands_adapter.py`
- Create hashable runtime config dataclass
- Wrap model creation logic with `@lru_cache(maxsize=16)`
- Add cache info logging for observability

**Success Criteria:**
- ✅ All 287 tests pass
- ✅ Mypy strict mode passes
- ✅ `lru_cache_info()` shows hits for repeated model configs in integration tests
- ✅ No behavioral changes—agents still function identically

**Estimated Effort**: 2-4 hours

**Implementation Steps:**
1. Create `RuntimeConfig` frozen dataclass with `(provider, model_id, region, host)` fields
2. Add `_create_model_cached()` helper with `@lru_cache(maxsize=16)` decorator
3. Refactor `create_model()` to convert `Runtime` → `RuntimeConfig` → call cached helper
4. Add `structlog` logging for cache hits/misses
5. Update `tests/test_runtime.py` to verify caching behavior

**Rollback**: Simple—remove `@lru_cache` decorator if issues arise

---

### Phase 2: Agent Caching Infrastructure ✅ Safe, Medium Impact
**Goal**: Add executor-scoped agent cache without changing executor signatures yet

**Scope:**
- File: `src/strands_cli/exec/utils.py`
- Create `AgentCache` class with `get_or_build_agent()` method
- Implement resource cleanup via `async def close()`
- Key agents by `(agent_id, frozenset(tool_ids))`

**Success Criteria:**
- ✅ `AgentCache` unit tests pass (mock `build_agent` to verify call counts)
- ✅ `close()` properly cleans up HTTP clients (verify `httpx.Client.close()` calls)
- ✅ No integration changes yet—cache is built but not used by executors

**Estimated Effort**: 3-5 hours

**Implementation Steps:**
1. Add `AgentCache` class to `exec/utils.py`:
   ```python
   class AgentCache:
       def __init__(self):
           self._agents: dict[tuple[str, frozenset[str]], Any] = {}
           self._tools: dict[str, HttpExecutorAdapter] = {}
       
       async def get_or_build_agent(
           self, spec, agent_id, agent_config, tool_overrides=None
       ):
           # Build cache key from agent_id + tool names
           # Check cache, return if hit
           # Build agent + store tools if miss
       
       async def close(self):
           # Close all HTTP executor clients
   ```
2. Add `tests/test_agent_cache.py` with coverage for:
   - Cache hits/misses
   - Tool deduplication
   - Cleanup verification
3. Add async context manager support to `HttpExecutorAdapter` if missing

**Rollback**: No executor changes—cache class can be removed without affecting runtime

---

### Phase 3: Single Executor Conversion (Pilot) ✅ Safe, Validates Approach
**Goal**: Convert `single_agent.py` executor to async and integrate `AgentCache`

**Scope:**
- File: `src/strands_cli/exec/single_agent.py`
- Convert `run_single_agent()` from sync to `async def`
- Add `AgentCache` usage (creates, uses, closes)
- Remove `asyncio.run()` call—now returns awaitable result

**Success Criteria:**
- ✅ All single-agent tests pass (`test_single_agent.py`, `test_cli.py` single-agent cases)
- ✅ Mypy passes with async signatures
- ✅ Agent is built once per run (verify via mock call count)
- ✅ CLI integration still works (proves `asyncio.run()` wrapper approach)

**Estimated Effort**: 2-3 hours

**Implementation Steps:**
1. Change signature: `def run_single_agent(...)` → `async def run_single_agent(...)`
2. Add at function start:
   ```python
   cache = AgentCache()
   try:
       agent = await cache.get_or_build_agent(spec, agent_id, agent_config)
       result = await invoke_agent_with_retry(agent, ...)
       return result
   finally:
       await cache.close()
   ```
3. Update CLI `__main__.py` to wrap single-agent dispatch:
   ```python
   if normalized.pattern_type == PatternType.SINGLE_AGENT:
       result = asyncio.run(run_single_agent(spec, variables))
   ```
4. Update tests to handle async executor

**Rollback**: Keep both sync and async versions during transition; feature flag if needed

---

### Phase 4: Chain Executor Conversion ✅ Medium Risk, High Impact
**Goal**: Convert `chain.py` to async with agent caching—validates multi-step optimization

**Scope:**
- File: `src/strands_cli/exec/chain.py`
- Convert `run_chain()` to async
- Replace per-step `build_agent()` + `asyncio.run()` with cached agents + `await`
- Add cache cleanup in finally block

**Success Criteria:**
- ✅ All chain tests pass (`test_chain.py`, `test_cli_integration.py` chain cases)
- ✅ Agent built once per unique `(agent_id, tools)` in multi-step chains
- ✅ Single event loop across all steps (verify via `asyncio.get_running_loop()` ID)
- ✅ HTTP clients properly closed after execution

**Estimated Effort**: 3-4 hours

**Implementation Steps:**
1. Convert signature: `async def run_chain(spec, variables) -> RunResult`
2. Refactor step loop (currently around line 155):
   ```python
   cache = AgentCache()
   try:
       for step_index, step in enumerate(spec.pattern.config.steps):
           # Build tools_for_step (existing logic)
           
           # CHANGED: Use cache instead of build_agent
           agent = await cache.get_or_build_agent(
               spec, step_agent_id, step_agent_config, tool_overrides=tools_for_step
           )
           
           # CHANGED: Direct await instead of asyncio.run
           step_response = await invoke_agent_with_retry(
               agent, step_input, max_attempts, wait_min, wait_max
           )
   finally:
       await cache.close()
   ```
3. Update CLI dispatch: `result = asyncio.run(run_chain(spec, variables))`
4. Add performance regression test verifying agent reuse

**Rollback**: Phase 3 single-agent conversion proves async approach works

---

### Phase 5: Workflow Executor Conversion ✅ Medium Risk, High Impact
**Goal**: Convert `workflow.py` to async with agent caching—handles DAG parallelism

**Scope:**
- File: `src/strands_cli/exec/workflow.py`
- Convert `run_workflow()` to async
- Share `AgentCache` across all tasks in all layers
- Remove `asyncio.run()` from layer execution

**Success Criteria:**
- ✅ All workflow tests pass (`test_workflow.py`)
- ✅ Agent reused across tasks with same `(agent_id, tools)` configuration
- ✅ Parallel task execution still respects `max_parallel` semaphore
- ✅ Single event loop manages entire DAG execution

**Estimated Effort**: 4-5 hours

**Implementation Steps:**
1. Convert signature: `async def run_workflow(spec, variables) -> RunResult`
2. Create `AgentCache` once at start, pass to `_execute_workflow_layer()`
3. Update `_execute_workflow_layer()` signature to accept `cache: AgentCache`
4. Refactor task execution (currently around line 180):
   ```python
   async def _execute_task(task, context, cache, semaphore, ...):
       async with semaphore:
           agent = await cache.get_or_build_agent(
               spec, task.agent_id, agent_config, tool_overrides=task_tools
           )
           result = await invoke_agent_with_retry(agent, prompt, ...)
   ```
5. Update CLI dispatch: `result = asyncio.run(run_workflow(spec, variables))`
6. Add cleanup in finally block

**Rollback**: Phase 4 chain conversion validates multi-step caching pattern

---

### Phase 6: Parallel & Routing Executors ✅ Low Risk, Completes Migration
**Goal**: Convert remaining executors (`parallel.py`, `routing.py`) to async

**Scope:**
- Files: `src/strands_cli/exec/parallel.py`, `src/strands_cli/exec/routing.py`
- Apply same pattern as chain/workflow
- Ensure reduce step in parallel executor shares cache with branches

**Success Criteria:**
- ✅ All parallel tests pass (`test_parallel.py`)
- ✅ All routing tests pass (`test_routing.py`)
- ✅ Full test suite passes (287 tests)
- ✅ All executors now async with agent caching

**Estimated Effort**: 3-4 hours (parallel), 2-3 hours (routing)

**Implementation Steps:**
1. **Parallel Executor**:
   - Convert `run_parallel()` to async
   - Share `AgentCache` between `_execute_all_branches_async()` and `_execute_reduce_step()`
   - Remove `asyncio.run()` calls (lines 388, 445)
   - Update CLI dispatch

2. **Routing Executor**:
   - Convert `run_routing()` to async
   - Use cache for router agent and routed agents
   - Remove `asyncio.run()` call
   - Update CLI dispatch

3. Verify all CLI integration tests pass

**Rollback**: Isolated changes—previous phases prove architecture works

---

### Phase 7: Testing & Validation ✅ Essential, No Code Changes
**Goal**: Comprehensive performance and regression testing

**Scope:**
- File: `tests/test_performance.py` (new)
- Add benchmarks and validation tests

**Success Criteria:**
- ✅ Performance tests verify optimization claims
- ✅ No regression in functionality
- ✅ Coverage remains ≥85%
- ✅ All 287+ tests pass

**Estimated Effort**: 3-4 hours

**Implementation Steps:**
1. Create `tests/test_performance.py` with test cases:
   ```python
   @pytest.mark.asyncio
   async def test_agent_caching_reduces_build_calls(mocker):
       """Verify 10-step chain builds agent once per unique config."""
       mock_build = mocker.patch("strands_cli.runtime.strands_adapter.build_agent")
       # Run 10-step chain with same agent
       # Assert build_agent called 1 time (not 10)
   
   @pytest.mark.asyncio
   async def test_single_event_loop_across_workflow(mocker):
       """Verify single event loop ID throughout execution."""
       loop_ids = []
       async def track_loop(*args, **kwargs):
           loop_ids.append(id(asyncio.get_running_loop()))
           return Mock()
       mocker.patch("...", side_effect=track_loop)
       # Run multi-step workflow
       # Assert len(set(loop_ids)) == 1
   
   @pytest.mark.asyncio
   async def test_http_clients_cleaned_up(mocker):
       """Verify httpx.Client.close() called for all cached clients."""
       mock_close = mocker.patch("httpx.Client.close")
       # Run workflow with HTTP tools
       # Assert mock_close.call_count == expected_client_count
   
   def test_model_client_lru_cache_hits(mocker):
       """Verify repeated model configs return cached instances."""
       # Create 3 agents with same runtime config
       # Assert lru_cache_info().hits >= 2
   ```

2. Run full test suite: `.\scripts\dev.ps1 test-cov`
3. Verify coverage ≥85%: `uv run pytest --cov=src/strands_cli --cov-report=term-missing`
4. Validate all examples: `.\scripts\dev.ps1 validate-examples`

**Rollback**: Tests are non-invasive—can be adjusted without affecting implementation

---

### Phase 8: Documentation & Cleanup ✅ Essential, User-Facing
**Goal**: Update documentation and remove deprecated code

**Scope:**
- Update `README.md` with performance improvements
- Update `.github/copilot-instructions.md` to reflect async executor pattern
- Remove any sync executor fallback code
- Update coverage badge

**Success Criteria:**
- ✅ README documents performance benefits
- ✅ Copilot instructions reflect async architecture
- ✅ No dead code remains
- ✅ Coverage badge updated

**Estimated Effort**: 2-3 hours

**Implementation Steps:**
1. Add to `README.md` Performance section:
   ```markdown
   ## Performance Optimizations
   
   - **Agent Caching**: Agents are reused across steps/tasks with identical configurations, reducing initialization overhead by ~90% in multi-step workflows
   - **Model Client Pooling**: LRU cache shares model clients (Bedrock/Ollama/OpenAI) across agents, eliminating redundant connection setup
   - **Single Event Loop**: One async event loop per workflow execution eliminates per-step loop creation/teardown overhead
   - **Resource Cleanup**: HTTP clients and tool adapters properly closed after execution
   ```

2. Update `.github/copilot-instructions.md`:
   - Change "Executors are synchronous functions" → "Executors are async functions"
   - Add `AgentCache` usage pattern to conventions
   - Document `@lru_cache` model pooling

3. Remove any `# TODO: async conversion` comments

4. Update coverage badge in README if changed

**Rollback**: Documentation-only—no functional impact

---

## Risk Assessment & Mitigation

### High Risk Items
| Risk | Mitigation | Phase |
|------|-----------|-------|
| Breaking async/await chains | Comprehensive async tests per phase; mypy catches signature mismatches | 3-6 |
| Cache key collisions | Use `(agent_id, frozenset(tool_ids))` for uniqueness; unit tests verify | 2 |
| Resource leaks if cleanup fails | Use try/finally blocks; tests verify `close()` called | 2-6 |

### Medium Risk Items
| Risk | Mitigation | Phase |
|------|-----------|-------|
| LRU cache excessive memory | `maxsize=16` limits growth; monitor in production | 1 |
| Event loop lifecycle issues | Single top-level `asyncio.run()` in CLI maintains clear boundary | 3 |

### Low Risk Items
| Risk | Mitigation | Phase |
|------|-----------|-------|
| Performance regression | Benchmark tests catch slowdowns; caching is additive | 7 |
| Test suite instability | Run full suite after each phase; >85% coverage maintained | All |

## Success Metrics

### Quantitative Goals
- ✅ **Build Call Reduction**: 10-step chain with single agent → 1 `build_agent()` call (down from 10)
- ✅ **Event Loop Efficiency**: 1 `asyncio.run()` call per workflow (down from steps × tasks)
- ✅ **Model Cache Hit Rate**: ≥80% in multi-step workflows with repeated configs
- ✅ **Test Coverage**: Maintain ≥85% coverage throughout
- ✅ **Test Pass Rate**: 100% (287+ tests)

### Qualitative Goals
- ✅ **Maintainability**: Async pattern consistent across all executors
- ✅ **Observability**: Cache hit/miss logging for debugging
- ✅ **Resource Safety**: All HTTP clients properly cleaned up
- ✅ **Type Safety**: Mypy strict mode passes

## Timeline Estimate

| Phase | Effort | Dependencies | Can Start After |
|-------|--------|--------------|-----------------|
| 1. Model Pooling | 2-4h | None | Immediate |
| 2. Agent Cache | 3-5h | None (parallel with 1) | Immediate |
| 3. Single Agent | 2-3h | Phases 1, 2 | Phase 1+2 complete |
| 4. Chain | 3-4h | Phase 3 | Phase 3 complete |
| 5. Workflow | 4-5h | Phase 4 | Phase 4 complete |
| 6. Parallel/Routing | 5-7h | Phase 5 | Phase 5 complete |
| 7. Testing | 3-4h | Phases 1-6 | Phase 6 complete |
| 8. Documentation | 2-3h | Phase 7 | Phase 7 complete |

**Total Estimated Effort**: 24-35 hours (3-5 days of focused work)

**Parallel Opportunities**: Phases 1 and 2 can run concurrently (different files, no conflicts)

## Rollback Strategy

Each phase is designed for safe rollback:

1. **Git branching**: Create `feature/performance-phase-N` branches per phase
2. **Feature flags** (if needed): Use environment variable to toggle caching: `STRANDS_ENABLE_AGENT_CACHE=false`
3. **Incremental merge**: Merge phases to `master` only after full test suite passes
4. **Revert commits**: Each phase is atomic—git revert possible without cascading failures

## Open Questions & Decisions

### Resolved (per user input)
- ✅ **Cache scope**: Per-executor-run (create/destroy with each workflow execution)
- ✅ **Model pooling**: `functools.lru_cache` (simple, bounded, Python stdlib)
- ✅ **Conversion strategy**: All executors at once (Phases 3-6 sequential but all converted)

### To Be Determined
- ⏳ **LRU cache size**: Start with `maxsize=16`; monitor and adjust based on real-world usage
- ⏳ **Cache metrics**: Expose via `--verbose` flag or structured logs only?
- ⏳ **Production monitoring**: Add OTEL spans for cache hit/miss rates in future?

## Next Steps

1. **Review & Approve Plan**: Stakeholder sign-off on phased approach
2. **Create Tracking Issues**: One GitHub issue per phase with acceptance criteria
3. **Start Phase 1**: Model client pooling (safe, high-impact, no dependencies)
4. **Checkpoint After Phase 3**: Validate async conversion approach before scaling
5. **Full Suite Validation**: Run `.\scripts\dev.ps1 ci` after each phase completion

---

*Plan created: November 5, 2025*  
*Based on: PHASE3.md codebase review*  
*Target: strands-cli v0.2.0 performance improvements*

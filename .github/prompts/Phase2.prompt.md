# Plan: Complete Programmatic Workflow Builders (Phase 2)

Phase 2 transforms **strands-cli** from YAML-only to a code-first library by implementing fluent builder APIs for all 7 workflow patterns. Developers can construct complete workflows in Python without touching YAML, while maintaining full type safety and validation.

**Design Decisions Applied:**
1. ✅ **Fail fast**: Builders validate on `.build()` using Pydantic (catch errors early with clear messages)
2. ✅ **Explicit agent calls**: Require `.agent()` definition before use (no implicit agent creation)
3. ✅ **Explicit runtime**: Require `.runtime()` call (no environment variable fallback in builders)
4. ✅ **Pattern-specific HITL**: Use pattern-specific methods (`.review_gate()`, `.decomposition_review()`) instead of generic `.hitl()`

## Steps

### 1. Implement core `FluentBuilder` with strict validation and `ChainBuilder`

**Objective:** Create foundation for all pattern builders with fail-fast validation.

**Implementation:**
- Create `src/strands_cli/api/builders.py` with `FluentBuilder` base class
- Add `.runtime(provider, model, **kwargs)` → validates provider in `{"bedrock", "ollama", "openai"}`
- Add `.agent(id, prompt, tools=None, **kwargs)` → stores in `_agents` dict, validates no duplicates
- Add `.artifact(path, template)` → validates template syntax on add
- Implement `.build()` → constructs `Spec`, validates via Pydantic, raises `BuildError` with actionable message on failure
- Implement `ChainBuilder` with `.step(agent, input)` → validates agent exists in parent's `_agents`
- Add `ChainBuilder.hitl(prompt, show=None, default=None)` → pattern-specific HITL for chain steps
- Wire `FluentBuilder.chain()` to return `ChainBuilder(self)`

**Testing:**
- Unit tests: invalid provider → `BuildError`, missing agent → `BuildError`, valid build → `Spec` passes schema
- Test agent validation: referencing undefined agent raises clear error with suggestion

**Acceptance Criteria:**
- ✅ `FluentBuilder` validates runtime provider immediately
- ✅ `.agent()` prevents duplicate IDs
- ✅ `.build()` fails fast with actionable `BuildError` messages
- ✅ `ChainBuilder.step()` validates agent exists before adding step
- ✅ Built `Spec` passes Pydantic validation

---

### 2. Implement `WorkflowBuilder` (DAG) and `ParallelBuilder` with dependency validation

**Objective:** Enable DAG-based workflows and parallel execution patterns with cycle detection.

**Implementation:**
- Add `WorkflowBuilder.task(id, agent, input, depends_on=None)` → validates agent exists, checks no cycles in DAG
- Add `WorkflowBuilder.hitl_task(id, prompt, show=None, depends_on=None)` → HITL task variant
- Implement topological sort validation in `WorkflowBuilder.build()` → fail fast on circular dependencies
- Add `ParallelBuilder.branch(id)` → returns context manager/builder for branch steps
- Add `ParallelBuilder.reduce(agent, input)` → optional reduce step
- Add `ParallelBuilder.hitl_in_branch()` and `.hitl_in_reduce()` → pattern-specific HITL placements
- Wire to `FluentBuilder.workflow()` and `.parallel()`

**Testing:**
- Unit tests: circular dependency detection raises `BuildError`
- Unit tests: missing dependency task ID raises clear error
- Integration tests: compare built specs to `examples/workflow-*.yaml` and `examples/parallel-*.yaml` golden files

**Acceptance Criteria:**
- ✅ `WorkflowBuilder` detects circular dependencies at build time
- ✅ Task dependencies validated (all referenced tasks exist)
- ✅ `ParallelBuilder.branch()` creates isolated branch contexts
- ✅ Built specs match YAML equivalents (golden tests pass)

---

### 3. Implement advanced pattern builders with pattern-specific HITL methods

**Objective:** Support all remaining patterns (graph, routing, evaluator-optimizer, orchestrator-workers) with specialized HITL gates.

**Implementation:**

**GraphBuilder:**
- Add `GraphBuilder.node(id, agent, input)` and `.hitl_node(id, prompt, show=None)` → validates unique node IDs
- Add `GraphBuilder.edge(from_node, to_node)` and `.conditional_edge(from_node, when, to_node)` → validates nodes exist

**RoutingBuilder:**
- Add `RoutingBuilder.router(agent, input)` and `.review_router(prompt, show)` → router with optional HITL review
- Add `RoutingBuilder.route(id, agent, steps)` → route definition

**EvaluatorOptimizerBuilder:**
- Add `EvaluatorOptimizerBuilder.producer(agent)`, `.evaluator(agent, input)`, `.accept(min_score, max_iters)`, `.revise_prompt(template)`
- Add `EvaluatorOptimizerBuilder.review_gate(prompt, show)` → HITL between iterations (pattern-specific)

**OrchestratorWorkersBuilder:**
- Add `OrchestratorWorkersBuilder.orchestrator(agent, input)`, `.worker_template(agent, tools)`, `.reduce_step(agent, input)`
- Add `OrchestratorWorkersBuilder.decomposition_review(prompt)` and `.reduce_review(prompt)` → pattern-specific HITL gates

**Wiring:**
- Wire all to `FluentBuilder` via `.graph()`, `.routing()`, `.evaluator_optimizer()`, `.orchestrator_workers()`

**Testing:**
- Unit tests: each builder method validates inputs (agent exists, no duplicate IDs, valid templates)
- Golden tests: compare built specs to example YAMLs for each pattern

**Acceptance Criteria:**
- ✅ All 7 patterns have dedicated builder classes
- ✅ Pattern-specific HITL methods (not generic `.hitl()`)
- ✅ Edge/route/node validation at build time
- ✅ Built specs structurally identical to YAML examples

---

### 4. Create comprehensive test suite with golden file comparisons

**Objective:** Ensure 85%+ coverage and validate builder output matches YAML specs exactly.

**Implementation:**
- **Unit tests:** Each builder method validates inputs (agent exists, no duplicate IDs, valid templates)
- **Unit tests:** `.build()` fails fast with clear `BuildError` messages for invalid configs
- **Golden tests:** For each pattern, load YAML from `examples/`, build equivalent via API, compare `Spec` objects (must be identical)
- **Integration tests:** Build workflow → `.run_interactive()` → mock LLM responses → validate execution path
- **Test fixtures:** Add `invalid_agent_reference`, `circular_dependency`, `missing_runtime` fixtures to `tests/conftest.py`
- **Coverage validation:** `.\scripts\dev.ps1 test-cov` → ≥85% for `builders.py`

**Test Files:**
- `tests/test_api_builders.py` → unit tests for all builders
- `tests/test_api_golden.py` → golden file comparisons (YAML vs builder output)
- `tests/test_api_integration.py` → end-to-end builder → execution tests

**Acceptance Criteria:**
- ✅ ≥85% test coverage for `src/strands_cli/api/builders.py`
- ✅ All 7 patterns have golden tests (builder output == YAML spec)
- ✅ Clear error messages tested (e.g., missing agent suggests similar names)
- ✅ All tests pass: `.\scripts\dev.ps1 ci`

---

### 5. Document builder API with examples and migration guide

**Objective:** Provide complete documentation for developers to adopt builder API.

**Implementation:**

**API Reference (`docs/API_REFERENCE.md`):**
- Complete method signatures, parameters, return types, and examples for all 7 builders
- For each pattern, add "YAML → Python" comparison showing equivalent code
- Document error handling (what exceptions to expect, how to handle `BuildError`)
- Type hint examples for IDE autocomplete

**Examples (`examples/api/`):**
- Create `02_chain_builder.py` through `08_orchestrator_builder.py` (one runnable example per pattern)
- Each example demonstrates: runtime config, explicit agent definitions, pattern-specific HITL methods, artifact output
- Add `README.md` in `examples/api/` explaining each example

**README Updates:**
- Update `README.md` quickstart with builder API example (3-5 line snippet)
- Link to full API reference documentation

**Docstrings:**
- Add comprehensive docstrings to all public builder methods (IDE hover documentation)
- Include `Example:` sections in docstrings with runnable code snippets

**Acceptance Criteria:**
- ✅ `docs/API_REFERENCE.md` documents all 7 builders completely
- ✅ 7 runnable example scripts (one per pattern) in `examples/api/`
- ✅ YAML → Python migration examples for each pattern
- ✅ Docstrings on all public methods with examples
- ✅ README.md includes builder API quickstart

---

## Further Considerations

### 1. Error message quality for fail-fast validation

**Question:** Since we're failing fast on `.build()`, should error messages include suggestions (e.g., "Agent 'analyst' not found. Did you mean 'analyzer'? Use .agent('analyst', ...) to define it")?

**Recommendation:** Yes, use `difflib.get_close_matches()` for suggestions on missing agents.

**Implementation:**
```python
# In ChainBuilder.step()
if agent not in self.parent._agents:
    suggestions = difflib.get_close_matches(agent, self.parent._agents.keys(), n=3, cutoff=0.6)
    msg = f"Agent '{agent}' not found."
    if suggestions:
        msg += f" Did you mean: {', '.join(repr(s) for s in suggestions)}?"
    msg += f" Use .agent('{agent}', ...) to define it."
    raise BuildError(msg)
```

---

### 2. Builder method return types for better chaining

**Question:** Should pattern builders return `self` for chaining or `Workflow` on `.build()`? Current PRD shows `ChainBuilder.build()` → `Workflow`.

**Recommendation:** Keep as designed - intermediate methods return builder, only `.build()` returns `Workflow`.

**Rationale:** 
- Clear termination point (`.build()`)
- Pydantic validation happens at `.build()`, so returning `Workflow` makes sense
- Fluent chaining still works: `.step().step().hitl().build()`

---

### 3. Runtime validation timing

**Question:** Should `.runtime()` validate provider immediately or defer to `.build()`?

**Recommendation:** Validate provider enum immediately in `.runtime()` for fail-fast, but defer connectivity checks to execution time.

**Implementation:**
```python
def runtime(self, provider: str, model: str | None = None, **kwargs) -> "FluentBuilder":
    # Immediate validation
    valid_providers = {"bedrock", "ollama", "openai"}
    if provider not in valid_providers:
        raise BuildError(f"Invalid provider '{provider}'. Must be one of: {valid_providers}")
    
    # Store config (connectivity checked at execution)
    self._runtime = {"provider": provider, "model_id": model, **kwargs}
    return self
```

---

### 4. Template validation depth

**Question:** Should builders validate Jinja2 template syntax and variable references at build time?

**Recommendation:** Yes for syntax, no for variable existence (variables may come from runtime context like `{{steps[0].response}}`).

**Implementation:**
```python
from jinja2 import Environment, TemplateSyntaxError

def _validate_template_syntax(template: str) -> None:
    """Validate Jinja2 template syntax (but not variable references)."""
    try:
        env = Environment()
        env.parse(template)
    except TemplateSyntaxError as e:
        raise BuildError(f"Invalid template syntax: {e}")

# In ChainBuilder.step()
def step(self, agent: str, input: str) -> "ChainBuilder":
    self._validate_agent_exists(agent)
    _validate_template_syntax(input)  # Check syntax only
    self.steps.append({"agent": agent, "input": input})
    return self
```

---

## Success Criteria (Phase 2)

✅ All 7 patterns constructible via fluent API  
✅ Builder API is type-safe (Pylance/mypy clean)  
✅ Built workflows validate same as YAML specs  
✅ Example scripts demonstrate each pattern  
✅ Documentation covers all builders with examples  
✅ No YAML required for any workflow pattern  
✅ ≥85% test coverage for builders  
✅ Fail-fast validation with actionable error messages  
✅ Pattern-specific HITL methods (not generic)  
✅ Explicit agent and runtime definitions required

---

## Timeline (Week 2)

**Day 1-2: Builder Foundation**
- [ ] Implement `FluentBuilder` base class
- [ ] Implement `ChainBuilder` with `.step()` and `.hitl()`
- [ ] Implement `WorkflowBuilder` with `.task()`
- [ ] Validate built specs match YAML equivalents

**Day 3-4: Remaining Patterns**
- [ ] Implement `ParallelBuilder`
- [ ] Implement `GraphBuilder`
- [ ] Implement `RoutingBuilder`
- [ ] Implement `EvaluatorOptimizerBuilder`, `OrchestratorWorkersBuilder`

**Day 5: Testing & Examples**
- [ ] Unit tests for all builders
- [ ] Integration tests: built == YAML
- [ ] Examples: One script per pattern
- [ ] Documentation: Builder API reference

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Builder API too complex | Keep minimal - only essential methods, sensible defaults |
| Validation too strict | Allow escape hatch: `build(validate=False)` for advanced users |
| Template validation false positives | Only validate syntax, not variable references |
| Circular dependency detection bugs | Use well-tested topological sort from `graphlib` |
| Golden test brittleness | Use structural comparison, not string equality |

---

## Dependencies

**Required for Phase 2:**
- ✅ Phase 1 complete (MVP: Interactive HITL workflows)
- ✅ All 7 pattern executors working
- ✅ Pydantic models stable (`Spec`, `PatternConfig`, etc.)
- ✅ Schema validation working

**Blocks:**
- Phase 3 (events, async, integrations) depends on Phase 2 builders

---

## Deliverables Checklist

- [ ] `src/strands_cli/api/builders.py` with all 7 builder classes
- [ ] `src/strands_cli/api/exceptions.py` with `BuildError` exception
- [ ] `tests/test_api_builders.py` - unit tests
- [ ] `tests/test_api_golden.py` - golden file comparisons
- [ ] `tests/test_api_integration.py` - end-to-end tests
- [ ] `examples/api/02_chain_builder.py` through `08_orchestrator_builder.py`
- [ ] `examples/api/README.md` - example documentation
- [ ] `docs/API_REFERENCE.md` - complete builder API reference
- [ ] `README.md` updated with builder quickstart
- [ ] All tests passing: `.\scripts\dev.ps1 ci`
- [ ] Coverage ≥85% for `builders.py`

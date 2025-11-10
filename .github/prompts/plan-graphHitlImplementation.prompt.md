# Graph Pattern HITL Implementation Plan

## Context
Implementing fixes for 3 MAJOR issues identified in Graph Pattern HITL implementation review (HITL.md section 2.3, line 773).

## User Constraints
1. Skip atomicity considerations (transaction-level consistency not required)
2. Ignore caching considerations (no optimization focus)
3. UX Decision: Terminal HITL nodes should complete workflow (based on test expectations in `test_terminal_hitl_node_completes_workflow`)

## Issues to Fix

### Issue 1: CLI Exception Handling Gap
**Location**: `src/strands_cli/__main__.py:169`
**Problem**: `GraphExecutionError` not in `ExecutionError` tuple, causes graph failures to surface as "Unexpected error" with `EX_UNKNOWN (70)` instead of structured error with `EX_RUNTIME (10)`
**Impact**: Poor error messages, wrong exit codes for graph execution failures

### Issue 2: Checkpoint Ordering Bug
**Location**: `src/strands_cli/exec/graph.py:688-700`
**Problem**: Session checkpoint saves BEFORE updating `current_node` to next node
- Current flow: `execution_path.append(hitl_node_id)` → `session_repo.save()` → `_get_next_node()` → `current_node = next_node_id`
- On crash/resume: Re-pauses at same HITL node because `current_node` still points to HITL node
**Impact**: Workflow stuck in loop on crash recovery, re-executes HITL node unnecessarily

### Issue 3: CLI Validation Gap
**Location**: `src/strands_cli/__main__.py:93` (`_spec_has_hitl_steps()`)
**Problem**: Function checks chain/workflow/parallel patterns but not graph pattern
**Impact**: `--no-save-session` flag allowed with graph HITL workflows, breaks at runtime with confusing error instead of early validation failure

## Implementation Steps

### Step 1: Fix CLI Exception Handling (No Dependencies)
**File**: `src/strands_cli/__main__.py`
**Line**: 169
**Change**: Add `GraphExecutionError` to `ExecutionError` tuple

```python
# Current (line 169):
ExecutionError = (
    SingleAgentExecutionError,
    ChainExecutionError,
    WorkflowExecutionError,
    ParallelExecutionError,
    EvaluatorOptimizerExecutionError,
    OrchestratorExecutionError,
)

# After fix:
ExecutionError = (
    SingleAgentExecutionError,
    ChainExecutionError,
    WorkflowExecutionError,
    ParallelExecutionError,
    EvaluatorOptimizerExecutionError,
    OrchestratorExecutionError,
    GraphExecutionError,
)
```

**Validation**: Graph execution errors will be caught by exception handler at line 173, display structured error message, exit with `EX_RUNTIME (10)` instead of `EX_UNKNOWN (70)`

---

### Step 2: Fix Checkpoint Ordering (Depends on Step 1 for Clean Error Messaging)
**File**: `src/strands_cli/exec/graph.py`
**Lines**: 688-700 (HITL resume logic in `run_graph()`)

**Current Code**:
```python
# Lines 688-700 (approximate)
if resume_session and hitl_state and hitl_state.active:
    hitl_node_id = hitl_state.node_id
    hitl_response = hitl_state.user_response
    
    node_results[hitl_node_id] = {"response": hitl_response}
    hitl_state.active = False
    execution_path.append(hitl_node_id)
    
    # BUG: Save happens BEFORE current_node update
    await session_repo.save(session_state, spec_content="")
    
    next_node_id = _get_next_node(...)
    current_node = next_node_id  # Too late - already saved with old current_node
```

**Fixed Code**:
```python
if resume_session and hitl_state and hitl_state.active:
    hitl_node_id = hitl_state.node_id
    hitl_response = hitl_state.user_response
    
    # Process HITL response
    node_results[hitl_node_id] = {"response": hitl_response}
    hitl_state.active = False
    execution_path.append(hitl_node_id)
    
    # Determine next node BEFORE saving
    next_node_id = _get_next_node(...)
    
    # Update current_node and status BEFORE save
    if next_node_id is None:
        # Terminal HITL node - mark workflow complete
        current_node = hitl_node_id  # Keep terminal node for final response extraction
        session_state.status = SessionStatus.COMPLETED
    else:
        # Non-terminal HITL - advance to next node
        current_node = next_node_id
    
    # Save checkpoint with correct current_node
    await session_repo.save(session_state, spec_content="")
    
    # If terminal HITL, exit workflow loop
    if next_node_id is None:
        # Workflow completed at terminal HITL node
        break  # or continue to final result assembly
```

**Key Changes**:
1. Move `_get_next_node()` call BEFORE `session_repo.save()`
2. Update `current_node` BEFORE `session_repo.save()`
3. Add special handling for terminal HITL nodes (`next_node_id is None`):
   - Keep `current_node = hitl_node_id` for final response extraction
   - Set `session_state.status = SessionStatus.COMPLETED` to prevent re-pause
   - Exit workflow loop after checkpoint

**Validation**: 
- Crash during HITL resume → resumes at NEXT node (not re-paused at HITL node)
- Terminal HITL node → workflow completes, final response extracted from `node_results[hitl_node_id]`
- Existing test `test_terminal_hitl_node_completes_workflow` should pass

---

### Step 3: Fix CLI Validation Gap (No Dependencies)
**File**: `src/strands_cli/__main__.py`
**Line**: 93 (`_spec_has_hitl_steps()`)

**Current Code**:
```python
def _spec_has_hitl_steps(spec: Spec) -> bool:
    """Check if spec has HITL steps requiring session persistence."""
    if spec.pattern.type == "chain":
        return any(step.hitl for step in spec.pattern.config.steps)
    elif spec.pattern.type == "workflow":
        return any(task.hitl for task in spec.pattern.config.tasks)
    elif spec.pattern.type == "parallel":
        for branch in spec.pattern.config.branches:
            if any(step.hitl for step in branch.steps):
                return True
    return False
```

**Fixed Code**:
```python
def _spec_has_hitl_steps(spec: Spec) -> bool:
    """Check if spec has HITL steps requiring session persistence."""
    if spec.pattern.type == "chain":
        return any(step.hitl for step in spec.pattern.config.steps)
    elif spec.pattern.type == "workflow":
        return any(task.hitl for task in spec.pattern.config.tasks)
    elif spec.pattern.type == "parallel":
        for branch in spec.pattern.config.branches:
            if any(step.hitl for step in branch.steps):
                return True
    elif spec.pattern.type == "graph":
        return any(node.hitl for node in spec.pattern.config.nodes)
    return False
```

**Validation**: 
- Graph workflow with HITL + `--no-save-session` → early exit with `EX_USAGE (2)` and helpful error message
- Prevents confusing runtime errors when session persistence disabled but HITL nodes present

---

### Step 4: Add Checkpoint Regression Test (Depends on Step 2)
**File**: `tests/test_graph_hitl.py`
**Test Name**: `test_graph_hitl_resume_checkpoint_advances_current_node`

**Purpose**: Validate crash-safety invariant - checkpoint must advance `current_node` before save

**Test Flow**:
1. Create graph spec with HITL node → next node
2. Run workflow → pause at HITL
3. Load session → verify `current_node = hitl_node_id`, `hitl_state.active = True`
4. **Resume with response** → workflow should advance
5. **Simulate crash before completion** (mock exception after checkpoint save)
6. **Load session again** → verify `current_node = next_node_id` (NOT hitl_node_id)
7. Resume from crash → should continue from next_node_id, not re-pause at HITL

**Expected Result**: Session checkpoint reflects post-HITL state, crash recovery resumes at next node

---

### Step 5: Add CLI Validation Test (Depends on Step 3)
**File**: `tests/test_cli.py` (or new `tests/test_cli_validation.py`)
**Test Name**: `test_graph_hitl_with_no_save_session_fails_validation`

**Purpose**: Ensure `--no-save-session` + graph HITL → early validation error

**Test Flow**:
1. Create graph spec with HITL node
2. Run CLI with `--no-save-session` flag
3. Assert exit code = `EX_USAGE (2)`
4. Assert error message mentions session persistence requirement for HITL

---

### Step 6: Add CLI Error Handling Test (Depends on Step 1)
**File**: `tests/test_cli.py`
**Test Name**: `test_graph_execution_error_returns_ex_runtime`

**Purpose**: Ensure `GraphExecutionError` surfaces with correct exit code and structured error

**Test Flow**:
1. Create graph spec (any valid config)
2. Mock graph executor to raise `GraphExecutionError("test error")`
3. Run CLI
4. Assert exit code = `EX_RUNTIME (10)`
5. Assert error output contains structured message (not "Unexpected error")

---

## Execution Order

### Phase 1: Core Fixes (Parallel - No Dependencies Between Steps)
1. **Step 1**: Add `GraphExecutionError` to CLI exception tuple
2. **Step 3**: Extend `_spec_has_hitl_steps()` for graph pattern

### Phase 2: Checkpoint Fix (Sequential - Depends on Phase 1)
3. **Step 2**: Fix checkpoint ordering in graph executor
   - Requires Step 1 complete for clean error messaging during testing
   - Implements terminal HITL UX decision (workflow completion)

### Phase 3: Validation Tests (Parallel - After Phase 2)
4. **Step 4**: Checkpoint regression test (validates Step 2)
5. **Step 5**: CLI validation test (validates Step 3)
6. **Step 6**: CLI error handling test (validates Step 1)

## Success Criteria

### Code Quality
- [ ] All changes follow existing code patterns (async/await, error handling, Pydantic models)
- [ ] Type hints maintained (mypy strict mode passes)
- [ ] No ruff lint warnings introduced
- [ ] Comments explain WHY for non-obvious logic (especially terminal HITL handling)

### Test Coverage
- [ ] All existing tests pass (287 tests, ≥85% coverage)
- [ ] 3 new tests added (Steps 4-6)
- [ ] Coverage maintained or improved (especially `src/strands_cli/__main__.py` and `src/strands_cli/exec/graph.py`)

### Functional Validation
- [ ] Graph HITL pause/resume works after crash (Step 4 test validates)
- [ ] Terminal HITL nodes complete workflow (existing `test_terminal_hitl_node_completes_workflow` validates)
- [ ] `--no-save-session` rejected for graph HITL (Step 5 test validates)
- [ ] Graph execution errors display properly (Step 6 test validates)
- [ ] Manual test: Run `examples/graph-hitl-approval-demo-openai.yaml` → pause → resume → complete

### Documentation
- [ ] HITL.md section 2.3 marked as verified (add "✅ Implementation verified" note)
- [ ] CHANGELOG.md updated with bug fixes (exit code fix, checkpoint fix, validation fix)
- [ ] No new user-facing docs needed (fixes don't change intended API)

## Risks & Mitigation

### Risk 1: Breaking Existing HITL Tests
**Mitigation**: Run full test suite after each step; Step 2 changes only checkpoint ordering (not HITL API)

### Risk 2: Terminal HITL Edge Cases
**Mitigation**: Existing test `test_terminal_hitl_node_completes_workflow` validates expected behavior; Step 4 adds crash-safety validation

### Risk 3: Session State Migration
**Mitigation**: No schema changes to `SessionState` or `HITLState` - only logic changes in executor

## Implementation Notes

### Code Locations (Quick Reference)
- **CLI Entry**: `src/strands_cli/__main__.py` (lines 93, 169)
- **Graph Executor**: `src/strands_cli/exec/graph.py` (lines 688-700)
- **Session Persistence**: `src/strands_cli/session/file_repository.py` (atomic save logic - no changes needed)
- **HITL State Model**: `src/strands_cli/types.py` (lines 180-200, no changes needed)
- **Existing Tests**: `tests/test_graph_hitl.py` (1034 lines, comprehensive coverage)

### Terminal HITL UX Decision (User Constraint #3)
Based on test analysis (`test_terminal_hitl_node_completes_workflow` lines 996-1034):
- **Expected Behavior**: Terminal HITL node receives response → workflow marks as COMPLETED → final response extracted from terminal node result
- **Implementation**: When `next_node_id is None`, set `session_state.status = SessionStatus.COMPLETED` and exit workflow loop
- **Rationale**: Prevents infinite re-pause loop while preserving terminal node as current_node for result assembly

### Testing Strategy
- **Unit Tests**: Steps 4-6 focus on regression prevention and validation coverage
- **Integration Test**: Manual execution of `examples/graph-hitl-approval-demo-openai.yaml` with pause/crash/resume scenarios
- **Coverage Target**: Maintain ≥85% (current 83%); Step 2 changes should improve graph.py coverage

## Next Actions
1. Implement Steps 1 & 3 in parallel (independent CLI fixes)
2. Implement Step 2 (checkpoint ordering fix with terminal HITL handling)
3. Run test suite to validate no regressions
4. Implement Steps 4-6 in parallel (validation tests)
5. Manual integration test with graph-hitl-approval-demo-openai.yaml
6. Update CHANGELOG.md and HITL.md with verification notes

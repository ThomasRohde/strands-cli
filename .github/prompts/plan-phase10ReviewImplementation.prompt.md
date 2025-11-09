# Phase 10 Review — Implementation Plan

## Overview

This plan addresses the code review findings with a focus on **production readiness** and **incremental safety**. Work is organized into 3 implementation phases: Critical Fixes (merge-blocking), Quality Improvements (pre-release), and Future Enhancements (post-release).

---

## **Phase 1: Critical Fixes (Merge-Blocking)**
**Goal**: Eliminate production risks before merging to `main`  
**Timeline**: 2-4 hours  
**Branch**: `phase10-critical-fixes`

### Step 1.1: Thread-Safe Global State (MAJOR #1)
**Priority**: P0 — Race conditions in production environments  
**Files**: `src/strands_cli/telemetry/otel.py`

**Implementation**:
```python
# Add module-level lock
_telemetry_lock = Lock()

# Wrap configure_telemetry with lock acquisition
def configure_telemetry(spec_telemetry: dict[str, Any] | None = None) -> None:
    with _telemetry_lock:
        _configure_telemetry_locked(spec_telemetry)

def _configure_telemetry_locked(spec_telemetry: dict[str, Any] | None = None) -> None:
    """Internal implementation (assumes lock held)."""
    global _tracer_provider, _trace_collector
    # ... existing implementation ...
```

**Test Coverage**:
```python
# tests/test_telemetry_concurrency.py (NEW FILE)
@pytest.mark.asyncio
async def test_concurrent_configure_telemetry():
    """Verify thread-safety with 20 parallel config calls."""
    configs = [
        {"otel": {"service_name": f"service-{i}", "sample_ratio": 1.0}}
        for i in range(20)
    ]
    
    async def configure(cfg):
        configure_telemetry(cfg)
        return get_trace_collector() is not None
    
    results = await asyncio.gather(*[configure(c) for c in configs])
    assert all(results), "All config calls should succeed"
    
    # Verify consistent final state
    final_collector = get_trace_collector()
    assert final_collector is not None
```

**Acceptance Criteria**:
- ✅ No race conditions with 20+ concurrent calls
- ✅ Consistent global state after parallel configuration
- ✅ No span loss or provider mismatches
- ✅ Test passes 100 times in a row (flakiness check)

---

### Step 1.2: Bounded Span Collection (MAJOR #3)
**Priority**: P0 — Prevents OOM in long-running workflows  
**Files**: `src/strands_cli/telemetry/otel.py`

**Implementation**:
```python
class TraceCollector:
    DEFAULT_MAX_SPANS = 1000  # ~5MB max memory
    
    def __init__(self, max_spans: int | None = None) -> None:
        self._spans: list[dict[str, Any]] = []
        self._lock = Lock()
        self._max_spans = max_spans or int(
            os.getenv("STRANDS_MAX_TRACE_SPANS", str(self.DEFAULT_MAX_SPANS))
        )
        self._trace_id: str | None = None
        self._evicted_count = 0  # Track total evictions
    
    def add_span(self, span: ReadableSpan, redacted_attrs: dict[str, Any] | None = None) -> None:
        with self._lock:
            # ... build span_dict ...
            
            # FIFO eviction if limit exceeded
            if len(self._spans) >= self._max_spans:
                evicted = self._spans.pop(0)
                self._evicted_count += 1
                logger.warning(
                    "span_evicted_fifo",
                    limit=self._max_spans,
                    evicted_name=evicted.get("name"),
                    evicted_total=self._evicted_count,
                )
            
            self._spans.append(span_dict)
    
    def get_trace_data(self, ...) -> dict[str, Any]:
        with self._lock:
            return {
                "trace_id": self._trace_id or "unknown",
                "span_count": len(self._spans),
                "evicted_count": self._evicted_count,  # NEW
                "spans": self._spans,
                # ... rest ...
            }
```

**Test Coverage**:
```python
# tests/test_telemetry.py (UPDATE)
def test_trace_collector_span_limit_eviction(trace_collector):
    """Verify FIFO eviction with configurable limit."""
    collector = TraceCollector(max_spans=10)
    
    # Add 15 spans
    for i in range(15):
        mock_span = create_mock_span(name=f"span-{i}")
        collector.add_span(mock_span)
    
    trace_data = collector.get_trace_data()
    
    # Should have exactly 10 spans (oldest 5 evicted)
    assert trace_data["span_count"] == 10
    assert trace_data["evicted_count"] == 5
    
    # Verify oldest spans evicted (span-0 to span-4 gone)
    span_names = [s["name"] for s in trace_data["spans"]]
    assert "span-0" not in span_names
    assert "span-14" in span_names  # Most recent preserved
```

**Documentation Update**:
```yaml
# docs/TELEMETRY.md
## Memory Management

By default, the trace collector stores up to 1000 spans (~5MB). For longer workflows:

```bash
# Increase limit for 10,000-step workflows
export STRANDS_MAX_TRACE_SPANS=5000

# Run workflow
uv run strands run long-workflow.yaml --trace
```

**Warning**: Evicted spans won't appear in trace artifacts. Monitor logs for `span_evicted_fifo` warnings.
```

**Acceptance Criteria**:
- ✅ FIFO eviction at configurable limit
- ✅ Warning logged with eviction details
- ✅ `evicted_count` tracked in trace metadata
- ✅ Environment variable `STRANDS_MAX_TRACE_SPANS` respected
- ✅ Default 1000 spans works for 95% of workflows

---

### Step 1.3: Flush Timeout Handling (MAJOR #5)
**Priority**: P0 — User-facing trace completeness guarantee  
**Files**: `src/strands_cli/telemetry/otel.py`, `src/strands_cli/__main__.py`

**Implementation**:
```python
# otel.py
def force_flush_telemetry(timeout_millis: int = 30000) -> bool:
    """Force flush pending spans with timeout."""
    global _tracer_provider
    
    if hasattr(_tracer_provider, "force_flush"):
        success = _tracer_provider.force_flush(timeout_millis=timeout_millis)
        if not success:
            logger.warning(
                "telemetry_flush_timeout",
                timeout_ms=timeout_millis,
                message="Trace export incomplete - some spans may be missing",
            )
        return success
    return True  # No-op provider, nothing to flush

# __main__.py
def _write_trace_artifact(spec: Spec, out: str, force: bool) -> str | None:
    """Write trace artifact with flush verification."""
    if not (spec.telemetry and spec.telemetry.otel):
        return None
    
    # Flush with 5s timeout
    flush_success = force_flush_telemetry(timeout_millis=5000)
    if not flush_success:
        console.print(
            "[yellow]⚠ Warning:[/yellow] Trace export timed out. "
            "Artifact may be incomplete. Try increasing timeout or check OTLP endpoint."
        )
    
    collector = get_trace_collector()
    # ... rest of implementation ...
```

**Test Coverage**:
```python
# tests/test_telemetry.py
def test_force_flush_timeout_returns_false(mocker):
    """Verify timeout detection and logging."""
    mock_provider = mocker.Mock()
    mock_provider.force_flush.return_value = False  # Simulate timeout
    
    from strands_cli.telemetry import otel
    otel._tracer_provider = mock_provider
    
    with patch("structlog.get_logger") as mock_logger:
        result = force_flush_telemetry(timeout_millis=1000)
        
        assert result is False
        mock_logger().warning.assert_called_once()
        assert "telemetry_flush_timeout" in str(mock_logger().warning.call_args)

# tests/test_cli.py
def test_run_trace_flag_shows_timeout_warning(mocker, tmp_path):
    """Verify CLI shows user-facing warning on timeout."""
    # Mock flush timeout
    mocker.patch("strands_cli.__main__.force_flush_telemetry", return_value=False)
    
    result = runner.invoke(app, ["run", "spec.yaml", "--trace"])
    
    assert "⚠ Warning:" in result.stdout
    assert "Trace export timed out" in result.stdout
```

**Acceptance Criteria**:
- ✅ `force_flush_telemetry()` returns `False` on timeout
- ✅ Warning logged with structured fields
- ✅ CLI shows user-facing warning (yellow text)
- ✅ Trace artifact still written (best-effort)
- ✅ Guidance provided (increase timeout or check endpoint)

---

### Step 1.4: Update Version & Changelog
**Priority**: P0 — Documentation completeness  
**Files**: `pyproject.toml`, `CHANGELOG.md`, `README.md`

**Implementation**:
```toml
# pyproject.toml
[project]
version = "0.10.0"  # Confirm Phase 10 version
```

```markdown
# CHANGELOG.md
## [0.10.0] - 2025-11-09

### Fixed (Phase 10.1 Hotfix)
- **Thread-safe telemetry configuration** - Added lock protection for global `_tracer_provider` and `_trace_collector`
- **Bounded span collection** - FIFO eviction at 1000 spans (configurable via `STRANDS_MAX_TRACE_SPANS`) to prevent OOM
- **Flush timeout detection** - User warning when trace export times out with remediation guidance

### Breaking Changes
**None** - All fixes are backward compatible.
```

**Acceptance Criteria**:
- ✅ Version matches across `pyproject.toml`, `README.md`, `CHANGELOG.md`
- ✅ Changelog documents all critical fixes
- ✅ Breaking changes section confirmed empty

---

### Step 1.5: CI Validation
**Priority**: P0 — Ensure all fixes work together  
**Command**: `.\scripts\dev.ps1 ci`

**Checks**:
1. ✅ All 795+ tests pass
2. ✅ New concurrency test passes 100 iterations
3. ✅ Coverage remains ≥82%
4. ✅ Mypy strict mode passes
5. ✅ Ruff linting passes (zero violations)
6. ✅ Example specs validate successfully

**Deliverable**: PR ready for merge to `main`

---

## **Phase 2: Quality Improvements (Pre-Release)**
**Goal**: Harden implementation before v0.10.0 release  
**Timeline**: 4-6 hours  
**Branch**: `phase10-quality`

### Step 2.1: Fix API Key Redaction Over-Matching (MAJOR #2)
**Priority**: P1 — Trace usability improvement  
**Files**: `src/strands_cli/telemetry/redaction.py`

**Implementation**:
```python
class RedactionEngine:
    # Context-aware API key pattern
    API_KEY_PATTERN = re.compile(
        r"(?:api[_-]?key|token|secret|password|credential)[:\s=]*([A-Za-z0-9_-]{20,})",
        re.IGNORECASE
    )
    
    def redact_span_attributes(
        self,
        attributes: dict[str, Any],
        redact_tool_inputs: bool = False,
        redact_tool_outputs: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Redact PII with context-aware pattern matching."""
        redacted_attrs = {}
        initial_count = self.redaction_count
        
        for key, value in attributes.items():
            # Check if key suggests sensitive data
            key_lower = key.lower()
            is_sensitive_key = any(
                term in key_lower for term in ["key", "token", "secret", "password", "credential"]
            )
            
            # Apply appropriate patterns
            if (redact_tool_inputs and key.startswith("tool.input.")) or \
               (redact_tool_outputs and key.startswith("tool.output.")):
                redacted_attrs[key] = self.redact_value(value, is_sensitive_key)
            elif is_sensitive_key:
                # Only apply API key pattern if key name suggests sensitive data
                redacted_attrs[key] = self._redact_string_context_aware(str(value))
            else:
                # Non-sensitive keys: apply all patterns EXCEPT API key heuristic
                redacted_attrs[key] = self._redact_string_basic(str(value))
        
        was_redacted = self.redaction_count > initial_count
        if was_redacted:
            redacted_attrs["redacted"] = True
        
        return redacted_attrs, was_redacted
    
    def _redact_string_context_aware(self, text: str) -> str:
        """Apply all patterns including API key."""
        for pattern in self.patterns:  # Includes API_KEY_PATTERN
            text = pattern.sub(self.REDACTED_PLACEHOLDER, text)
        return text
    
    def _redact_string_basic(self, text: str) -> str:
        """Apply patterns excluding API key heuristic."""
        for pattern in [EMAIL_PATTERN, CREDIT_CARD_PATTERN, SSN_PATTERN, PHONE_PATTERN]:
            text = pattern.sub(self.REDACTED_PLACEHOLDER, text)
        return text
```

**Test Coverage**:
```python
# tests/test_redaction.py
def test_redaction_preserves_trace_ids():
    """Verify trace_id/span_id not redacted despite 32+ chars."""
    engine = RedactionEngine()
    
    attrs = {
        "trace_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",  # 32 chars
        "span_id": "1234567890abcdef",  # 16 chars
        "agent.id": "research_specialist_agent_v2",  # 30+ chars
    }
    
    redacted, was_redacted = engine.redact_span_attributes(attrs)
    
    # Should NOT redact (no sensitive key context)
    assert redacted["trace_id"] == attrs["trace_id"]
    assert redacted["span_id"] == attrs["span_id"]
    assert redacted["agent.id"] == attrs["agent.id"]
    assert not was_redacted

def test_redaction_catches_api_keys_with_context():
    """Verify API keys redacted when key name suggests sensitive data."""
    engine = RedactionEngine()
    
    attrs = {
        "openai_api_key": "sk-proj-1234567890abcdefghij",  # Sensitive key name
        "api_token": "ghp_abcdefghijklmnopqrstuvwxyz",  # GitHub token
        "workflow_id": "1234567890abcdefghij",  # NOT sensitive (no key context)
    }
    
    redacted, was_redacted = engine.redact_span_attributes(attrs)
    
    assert "***REDACTED***" in redacted["openai_api_key"]
    assert "***REDACTED***" in redacted["api_token"]
    assert redacted["workflow_id"] == attrs["workflow_id"]  # Preserved
    assert was_redacted
```

**Acceptance Criteria**:
- ✅ Trace IDs, span IDs, agent IDs not over-redacted
- ✅ API keys redacted when key name contains "key", "token", "secret", "password"
- ✅ 20+ char strings in non-sensitive keys preserved
- ✅ All existing redaction tests still pass

---

### Step 2.2: Standardize Tracer Imports (MINOR #4)
**Priority**: P2 — Code consistency  
**Files**: `src/strands_cli/exec/*.py`

**Implementation**:
```python
# Fix routing.py, parallel.py, etc.
# BEFORE:
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

# AFTER:
from strands_cli.telemetry import get_tracer
tracer = get_tracer(__name__)
```

**Files to Update**:
- `src/strands_cli/exec/routing.py:334`
- `src/strands_cli/exec/parallel.py:427`
- `src/strands_cli/exec/orchestrator_workers.py:475`
- `src/strands_cli/exec/graph.py:378`
- `src/strands_cli/exec/evaluator_optimizer.py:299`

**Test Coverage**: Existing tests should pass without changes (no behavior change)

**Acceptance Criteria**:
- ✅ All executors use `get_tracer()` from `strands_cli.telemetry`
- ✅ No direct imports of `opentelemetry.trace.get_tracer()`
- ✅ Grep search confirms consistency: `grep -r "trace.get_tracer" src/` returns zero matches

---

### Step 2.3: Enhanced Test Coverage
**Priority**: P2 — Confidence in edge cases  
**Files**: `tests/test_telemetry.py`, `tests/test_redaction.py`

**New Tests**:
1. **`test_redaction_nested_attributes`** (MINOR #6)
   ```python
   def test_redaction_nested_tool_inputs():
       """Verify nested tool.input structures are redacted."""
       engine = RedactionEngine()
       
       attrs = {
           "tool": {
               "input": {
                   "api_key": "sk-1234567890",
                   "user_email": "test@example.com"
               }
           }
       }
       
       redacted, _ = engine.redact_span_attributes(
           attrs, redact_tool_inputs=True
       )
       
       # Recursively check nested redaction
       assert "***REDACTED***" in str(redacted["tool"]["input"])
   ```

2. **`test_trace_collector_concurrent_add_span`**
   ```python
   @pytest.mark.asyncio
   async def test_concurrent_span_collection():
       """Verify TraceCollector thread-safety with 100 parallel adds."""
       collector = TraceCollector()
       
       async def add_spans(start_idx):
           for i in range(start_idx, start_idx + 10):
               span = create_mock_span(name=f"span-{i}")
               collector.add_span(span)
       
       await asyncio.gather(*[add_spans(i*10) for i in range(10)])
       
       trace_data = collector.get_trace_data()
       assert trace_data["span_count"] == 100
   ```

**Acceptance Criteria**:
- ✅ Coverage increases to ≥83%
- ✅ All edge cases documented in review covered
- ✅ No flaky tests (100 consecutive runs pass)

---

### Step 2.4: Documentation Updates
**Priority**: P2 — User-facing quality  
**Files**: `docs/TELEMETRY.md`, `README.md`

**Updates**:
```markdown
# docs/TELEMETRY.md

## Troubleshooting

### Trace Artifact Empty or Incomplete

**Symptom**: `trace.json` has 0 spans or fewer spans than expected.

**Causes & Solutions**:
1. **Flush timeout** - Slow OTLP collector or network
   ```bash
   # Check logs for: telemetry_flush_timeout
   # Increase timeout (default 5s):
   # Future: Add --trace-timeout flag
   ```

2. **Span eviction** - Workflow exceeded 1000 spans
   ```bash
   # Check logs for: span_evicted_fifo
   export STRANDS_MAX_TRACE_SPANS=5000
   uv run strands run workflow.yaml --trace
   ```

3. **Telemetry not configured** - Missing `telemetry.otel` in spec
   ```yaml
   telemetry:
     otel:
       service_name: "my-workflow"
       sample_ratio: 1.0
   ```

### Over-Redaction of Non-Sensitive Data

**Symptom**: Trace IDs, agent IDs, or workflow IDs redacted unexpectedly.

**Cause**: API key pattern matching 20+ char strings without context.

**Solution (v0.10.0+)**: Redaction now context-aware. Only keys containing "key", "token", "secret", "password" trigger API key pattern.

**Verify**:
```python
# Should NOT be redacted:
{"trace_id": "a1b2c3d4e5f6...", "agent.id": "research_agent_v2"}

# SHOULD be redacted:
{"openai_api_key": "sk-proj-...", "github_token": "ghp_..."}
```
```

**Acceptance Criteria**:
- ✅ Troubleshooting section added to `TELEMETRY.md`
- ✅ Environment variables documented in `README.md`
- ✅ Examples updated with best practices

---

## **Phase 3: Future Enhancements (Post-Release)**
**Goal**: Continuous improvement for v0.10.1+  
**Timeline**: 1-2 sprints (8-16 hours)  
**Branch**: Feature branches as needed

### Enhancement 3.1: Configurable Redaction Patterns
**Priority**: P3 — Enterprise customization  
**Scope**: Allow users to define custom PII patterns in YAML config

**Implementation Sketch**:
```yaml
# workflow.yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
    custom_patterns:
      - name: "internal_id"
        pattern: '\bINTERNAL-\d{6}\b'
        description: "Company-specific internal IDs"
      - name: "employee_badge"
        pattern: '\bEMP-[A-Z]{2}-\d{4}\b'
```

**Benefits**:
- Domain-specific secret protection
- No code changes for new PII types
- Audit-friendly (patterns in version control)

---

### Enhancement 3.2: Trace Compression
**Priority**: P3 — Storage optimization  
**Scope**: Gzip trace artifacts for large workflows

**Implementation Sketch**:
```bash
# CLI flag
uv run strands run workflow.yaml --trace --compress

# Output: trace.json.gz (50-70% smaller)
```

**Benefits**:
- Reduced artifact storage (S3, CI artifacts)
- Faster upload to trace backends
- Preserves full detail (decompress on demand)

---

### Enhancement 3.3: Smart Span Sampling
**Priority**: P3 — Better eviction strategy  
**Scope**: Replace FIFO with importance-based sampling

**Implementation Sketch**:
```python
class TraceCollector:
    def add_span(self, span: ReadableSpan):
        if len(self._spans) >= self._max_spans:
            # Keep first 20%, last 20%, sample middle 60%
            self._strategic_eviction()
```

**Benefits**:
- Preserves workflow start/end context
- Maintains debugging value at scale
- Better than FIFO for long workflows

---

## **Implementation Order & Dependencies**

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: Critical Fixes (MERGE-BLOCKING)                    │
├─────────────────────────────────────────────────────────────┤
│ Step 1.1: Thread-Safe Global State          [No deps]       │
│ Step 1.2: Bounded Span Collection           [No deps]       │
│ Step 1.3: Flush Timeout Handling            [Needs 1.2]     │
│ Step 1.4: Version & Changelog               [Needs 1.1-1.3] │
│ Step 1.5: CI Validation                     [Needs 1.1-1.4] │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: Quality Improvements (PRE-RELEASE)                 │
├─────────────────────────────────────────────────────────────┤
│ Step 2.1: API Key Redaction Fix             [Needs 1.5]     │
│ Step 2.2: Standardize Tracer Imports        [No deps]       │
│ Step 2.3: Enhanced Test Coverage            [Needs 2.1]     │
│ Step 2.4: Documentation Updates             [Needs 2.1-2.3] │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: Future Enhancements (POST-RELEASE)                 │
├─────────────────────────────────────────────────────────────┤
│ Enhancement 3.1: Configurable Redaction     [v0.10.1]       │
│ Enhancement 3.2: Trace Compression          [v0.10.1]       │
│ Enhancement 3.3: Smart Span Sampling        [v0.11.0]       │
└─────────────────────────────────────────────────────────────┘
```

---

## **Rollout Strategy**

### Phase 1 → `main` (v0.10.0 release)
1. Create branch `phase10-critical-fixes` from `Phase10`
2. Implement Steps 1.1-1.5 sequentially
3. PR review with maintainer approval
4. Merge to `main` → Tag `v0.10.0`
5. GitHub Release with updated `CHANGELOG.md`

### Phase 2 → `main` (v0.10.0 final)
1. Create branch `phase10-quality` from `main` (post-1.5)
2. Implement Steps 2.1-2.4 in parallel
3. PR review with automated checks
4. Merge to `main` → Update tag to `v0.10.0-final`

### Phase 3 → Feature branches
1. Each enhancement gets own branch (e.g., `feature/trace-compression`)
2. Implemented as time permits
3. Merged to `main` for minor releases (`v0.10.1`, `v0.11.0`)

---

## **Success Metrics**

### Phase 1 (Must-Have)
- ✅ Zero race conditions in production (20+ concurrent workflows)
- ✅ No OOM errors with 10,000-step workflows
- ✅ User-facing timeout warnings ≤5% false positive rate
- ✅ All 795+ tests pass with ≥82% coverage

### Phase 2 (Should-Have)
- ✅ Zero over-redaction complaints in user testing
- ✅ Code consistency: 100% executors use `get_tracer()`
- ✅ Documentation completeness: ≥90% troubleshooting coverage
- ✅ Test coverage increases to ≥83%

### Phase 3 (Nice-to-Have)
- ✅ 50%+ trace size reduction with compression
- ✅ Enterprise adoption with custom redaction patterns
- ✅ Trace quality maintained at 10,000+ spans (smart sampling)

---

## **Risk Mitigation**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Lock contention degrades performance | Low | Medium | Benchmark with 100+ parallel configs; optimize if >10ms overhead |
| FIFO eviction loses critical spans | Medium | Medium | Add warning threshold at 80% capacity; document in logs |
| Flush timeout breaks CI/CD | Low | High | Default 5s timeout tested with slow OTLP mocks; increase to 30s if needed |
| API key pattern breaks edge cases | Medium | Low | Extensive test suite with 50+ redaction scenarios |

---

## **Timeline Summary**

- **Phase 1**: 2-4 hours (same-day merge)
- **Phase 2**: 4-6 hours (1-2 day turnaround)
- **Phase 3**: 8-16 hours (next sprint)

**Total to v0.10.0 Release**: ~6-10 hours of focused work

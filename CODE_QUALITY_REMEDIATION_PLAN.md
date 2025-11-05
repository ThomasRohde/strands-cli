# Code Quality Remediation Plan

**Status**: Ready for Implementation  
**Priority**: 🟡 High  
**Estimated Effort**: 3-4 days  
**Target**: Clear all 8 C901 complexity violations and eliminate duplicate code  

---

## Executive Summary

The codebase has **8 C901 complexity violations** (cyclomatic complexity "too complex") affecting maintainability and testability. Additionally, duplicate helper functions across executors create drift risk. This plan systematically addresses these issues through:

1. **Modular extraction** of complex functions into focused helpers
2. **Shared utility modules** to eliminate duplication
3. **Incremental refactoring** with test coverage preservation
4. **Verification** via Ruff and test suite

---

## Issue Inventory

### Current C901 Violations (from Ruff)

| File | Function | Lines | Complexity | Impact |
|------|----------|-------|------------|--------|
| `__main__.py` | `run` | 82-238 | 🔴 High | Monolithic command handler |
| `__main__.py` | `plan` | 271-368 | 🟡 Medium | Complex formatting logic |
| `capability/checker.py` | `check_capability` | 67-433 | 🔴 Critical | 367-line function with 10+ validation checks |
| `exec/single_agent.py` | `run_single_agent` | 75-194 | 🟡 Medium | Pattern branching + template + retry |
| `exec/chain.py` | `run_chain` | 123-276 | 🟡 Medium | Loop + retry + budget + error handling |
| `exec/workflow.py` | `run_workflow` | 179-329 | 🟡 Medium | DAG execution + parallel logic |
| `loader/yaml_loader.py` | `load_spec` | 28-110 | 🟡 Medium | Multi-stage validation pipeline |
| `runtime/strands_adapter.py` | `build_agent` | 61-141 | 🟡 Medium | Tool loading + agent assembly |

### Duplicate Code Patterns

| Pattern | Files | Lines | Issue |
|---------|-------|-------|-------|
| `_get_retry_config(spec)` | `single_agent.py`, `chain.py`, `workflow.py`, `parallel.py` | 30-60 each | **4 identical copies** — config drift risk |
| `_check_budget_warning(...)` | `chain.py`, `workflow.py`, `parallel.py` | 20-30 each | **3 similar copies** — logic divergence |
| Agent execution with retry | All executors | ~40 each | Retry decorator pattern repeated 5+ times |

---

## Remediation Strategy

### Phase 1: Extract Shared Utilities (Priority 1)
**Goal**: Eliminate duplicate helpers and establish common patterns  
**Files to create**: `src/strands_cli/exec/utils.py`  
**Impact**: Removes 3 duplication patterns across 4 files  

#### 1.1 Create `exec/utils.py`

```python
"""Shared execution utilities for all pattern executors.

Provides common helpers for retry configuration, budget tracking,
and agent execution patterns used across chain, workflow, routing,
parallel, and single-agent executors.
"""

import asyncio
from typing import Any

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.types import Spec

logger = structlog.get_logger(__name__)

# Transient errors that should trigger retries across all executors
TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
)


class ExecutionUtilsError(Exception):
    """Raised when execution utility operations fail."""
    pass


def get_retry_config(spec: Spec) -> tuple[int, int, int]:
    """Get retry configuration from spec.

    Extracts retry policy from spec.runtime.failure_policy or uses defaults.
    Used by all executors for consistent retry behavior.

    Args:
        spec: Workflow spec with optional failure_policy

    Returns:
        Tuple of (max_attempts, wait_min, wait_max) in seconds

    Raises:
        ExecutionUtilsError: If retry configuration is invalid
    """
    max_attempts = 3
    wait_min = 1
    wait_max = 60

    if spec.runtime.failure_policy:
        policy = spec.runtime.failure_policy
        retries = policy.get("retries", max_attempts - 1)

        if retries < 0:
            raise ExecutionUtilsError(
                f"Invalid retry config: retries must be >= 0, got {retries}"
            )

        max_attempts = retries + 1
        backoff = policy.get("backoff", "exponential")

        if backoff == "exponential":
            wait_min = policy.get("wait_min", wait_min)
            wait_max = policy.get("wait_max", wait_max)

            if wait_min > wait_max:
                raise ExecutionUtilsError(
                    f"Invalid retry config: wait_min ({wait_min}s) "
                    f"must be <= wait_max ({wait_max}s)"
                )

    return max_attempts, wait_min, wait_max


def check_budget_threshold(
    cumulative_tokens: int,
    max_tokens: int | None,
    context_id: str,
    warn_threshold: float = 0.8,
) -> None:
    """Check token budget and log warnings or raise on exceed.

    Args:
        cumulative_tokens: Total tokens used so far
        max_tokens: Maximum tokens allowed (from budgets.max_tokens)
        context_id: Identifier for logging (step, task, branch)
        warn_threshold: Threshold for warning (default 0.8 = 80%)

    Raises:
        ExecutionUtilsError: If budget exceeded (100%)
    """
    if max_tokens is None:
        return

    usage_pct = (cumulative_tokens / max_tokens) * 100

    if usage_pct >= 100:
        logger.error(
            "token_budget_exceeded",
            context=context_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_pct=usage_pct,
        )
        raise ExecutionUtilsError(
            f"Token budget exceeded: {cumulative_tokens}/{max_tokens} tokens (100%)"
        )
    elif usage_pct >= (warn_threshold * 100):
        logger.warning(
            "token_budget_warning",
            context=context_id,
            cumulative=cumulative_tokens,
            max=max_tokens,
            usage_pct=f"{usage_pct:.1f}",
            threshold=f"{warn_threshold*100:.0f}%",
        )


def create_retry_decorator(
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> Any:
    """Create a retry decorator with exponential backoff.

    Centralizes retry decorator creation for consistent behavior
    across all executors.

    Args:
        max_attempts: Maximum number of attempts
        wait_min: Minimum wait time in seconds
        wait_max: Maximum wait time in seconds

    Returns:
        Configured retry decorator from tenacity
    """
    return retry(
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        reraise=True,
    )


async def invoke_agent_with_retry(
    agent: Any,
    input_text: str,
    max_attempts: int,
    wait_min: int,
    wait_max: int,
) -> Any:
    """Invoke an agent asynchronously with retry logic.

    Wraps agent invocation with stdout capture and retry handling.
    Used across all executors for consistent agent execution.

    Args:
        agent: Strands Agent instance
        input_text: Input prompt for the agent
        max_attempts: Maximum retry attempts
        wait_min: Minimum backoff wait (seconds)
        wait_max: Maximum backoff wait (seconds)

    Returns:
        Agent response (string or AgentResult)

    Raises:
        TRANSIENT_ERRORS: After all retry attempts exhausted
        Exception: For non-transient errors (fail immediately)
    """
    from strands_cli.utils import capture_and_display_stdout

    retry_decorator = create_retry_decorator(max_attempts, wait_min, wait_max)

    @retry_decorator
    async def _execute() -> Any:
        with capture_and_display_stdout():
            return await agent.invoke_async(input_text)

    return await _execute()


def estimate_tokens(input_text: str, output_text: str) -> int:
    """Estimate token count from text (simple word-based heuristic).

    Args:
        input_text: Input prompt
        output_text: Agent response

    Returns:
        Estimated token count
    """
    return len(input_text.split()) + len(output_text.split())
```

**Tests to add**: `tests/test_exec_utils.py`
- Test `get_retry_config` with valid/invalid configs
- Test `check_budget_threshold` warning and error thresholds
- Test `invoke_agent_with_retry` with mock agent and transient errors

---

### Phase 2: Refactor `capability/checker.py` (Priority 1)
**Goal**: Break 367-line `check_capability` into focused validation functions  
**Impact**: Clears largest C901 violation, improves testability  

#### 2.1 Extract Validation Functions

Create helpers in `capability/checker.py`:

```python
def _validate_agents(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate agent configuration."""
    if len(spec.agents) < 1:
        issues.append(
            CapabilityIssue(
                pointer="/agents",
                reason="No agents defined",
                remediation="Add at least one agent to the agents map",
            )
        )


def _validate_provider(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate runtime provider and provider-specific requirements."""
    if spec.runtime.provider not in {ProviderType.BEDROCK, ProviderType.OLLAMA, ProviderType.OPENAI}:
        issues.append(...)
    
    # Bedrock checks
    if spec.runtime.provider == ProviderType.BEDROCK and not spec.runtime.region:
        issues.append(...)
    
    # Ollama checks
    if spec.runtime.provider == ProviderType.OLLAMA and not spec.runtime.host:
        issues.append(...)
    
    # OpenAI checks
    if spec.runtime.provider == ProviderType.OPENAI:
        import os
        if not os.environ.get("OPENAI_API_KEY"):
            issues.append(...)


def _validate_pattern_type(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate pattern type is supported."""
    if spec.pattern.type not in {
        PatternType.CHAIN,
        PatternType.WORKFLOW,
        PatternType.ROUTING,
        PatternType.PARALLEL,
    }:
        issues.append(...)


def _validate_chain_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate chain-specific configuration."""
    if spec.pattern.type != PatternType.CHAIN:
        return
    
    if not spec.pattern.config.steps:
        issues.append(...)
    
    # Validate tool_overrides
    available_tools = _build_available_tools_set(spec)
    for i, step in enumerate(spec.pattern.config.steps):
        if step.tool_overrides:
            for tool_id in step.tool_overrides:
                if tool_id not in available_tools:
                    issues.append(...)


def _validate_workflow_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate workflow-specific configuration including DAG."""
    if spec.pattern.type != PatternType.WORKFLOW:
        return
    
    if not spec.pattern.config.tasks:
        issues.append(...)
        return
    
    # Validate dependencies
    _validate_task_dependencies(spec, issues)
    
    # Check for cycles
    cycle_errors = detect_cycles_in_dag(spec.pattern.config.tasks)
    for error in cycle_errors:
        issues.append(...)


def _validate_routing_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate routing-specific configuration."""
    if spec.pattern.type != PatternType.ROUTING:
        return
    
    # Router validation
    if not spec.pattern.config.router:
        issues.append(...)
    else:
        router_agent_id = spec.pattern.config.router.agent
        if router_agent_id not in spec.agents:
            issues.append(...)
    
    # Routes validation
    if not spec.pattern.config.routes:
        issues.append(...)
    else:
        for route_name, route in spec.pattern.config.routes.items():
            _validate_route(route_name, route, spec, issues)


def _validate_parallel_pattern(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate parallel-specific configuration."""
    if spec.pattern.type != PatternType.PARALLEL:
        return
    
    if not spec.pattern.config.branches or len(spec.pattern.config.branches) < 2:
        issues.append(...)
    else:
        _validate_branches(spec, issues)
    
    # Validate reduce step
    if spec.pattern.config.reduce and spec.pattern.config.reduce.agent not in spec.agents:
        issues.append(...)


def _validate_secrets(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate secret configurations."""
    if spec.env and spec.env.secrets:
        for i, secret in enumerate(spec.env.secrets):
            if secret.source != SecretSource.ENV:
                issues.append(...)


def _validate_tools(spec: Spec, issues: list[CapabilityIssue]) -> None:
    """Validate tool configurations."""
    if spec.tools and spec.tools.python:
        for i, tool in enumerate(spec.tools.python):
            if tool.callable not in ALLOWED_PYTHON_CALLABLES:
                issues.append(...)
    
    if spec.tools and spec.tools.mcp:
        issues.append(...)


# Refactored check_capability becomes orchestration
def check_capability(spec: Spec) -> CapabilityReport:
    """Check if a spec is compatible with current capabilities.
    
    Orchestrates validation across all feature areas.
    """
    issues: list[CapabilityIssue] = []
    
    # Run all validation checks
    _validate_agents(spec, issues)
    _validate_provider(spec, issues)
    _validate_pattern_type(spec, issues)
    _validate_chain_pattern(spec, issues)
    _validate_workflow_pattern(spec, issues)
    _validate_routing_pattern(spec, issues)
    _validate_parallel_pattern(spec, issues)
    _validate_secrets(spec, issues)
    _validate_tools(spec, issues)
    
    # Build normalized values if supported
    normalized = None
    if not issues:
        agent_id = next(iter(spec.agents.keys()))
        normalized = {
            "agent_id": agent_id,
            "agent": spec.agents[agent_id],
            "pattern_type": spec.pattern.type,
            "provider": spec.runtime.provider,
            "model_id": spec.runtime.model_id,
            "region": spec.runtime.region,
            "host": spec.runtime.host,
        }
    
    return CapabilityReport(
        supported=len(issues) == 0,
        issues=issues,
        normalized=normalized,
    )
```

**Tests to add**: `tests/test_capability_refactor.py`
- Test each `_validate_*` function independently
- Ensure existing `test_capability.py` tests still pass
- Add negative tests for each validation path

---

### Phase 3: Refactor `__main__.py` Commands (Priority 2)
**Goal**: Extract command handlers into separate functions  
**Impact**: Clears 2 C901 violations, improves CLI maintainability  

#### 3.1 Extract `run` Command Helpers

```python
def _load_and_validate_spec(
    spec_file: str,
    variables: dict[str, str] | None,
    verbose: bool,
) -> Spec:
    """Load and validate spec with error handling.
    
    Raises:
        SystemExit: With appropriate exit code on validation error
    """
    if verbose:
        console.print(f"[dim]Loading spec: {spec_file}[/dim]")
        if variables:
            console.print(f"[dim]Variables: {variables}[/dim]")
    
    try:
        return load_spec(spec_file, variables)
    except (LoadError, SchemaValidationError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_SCHEMA)


def _handle_unsupported_spec(
    spec: Spec,
    spec_file: str,
    capability_report: CapabilityReport,
    out: str,
) -> None:
    """Generate and display unsupported features report, then exit.
    
    Raises:
        SystemExit: With EX_UNSUPPORTED (18)
    """
    spec_content = Path(spec_file).read_text(encoding="utf-8")
    report_md = generate_markdown_report(spec_file, spec_content, capability_report)
    
    # Sanitize spec name for filesystem (Phase 3 security fix)
    from pathlib import Path
    import re
    safe_name = re.sub(r'[^\w\-_]', '_', spec.name)[:100]
    report_path = Path(out) / f"{safe_name}-unsupported.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    
    console.print("\n[yellow]Unsupported features detected.[/yellow]")
    console.print(f"Report written to: [cyan]{report_path}[/cyan]\n")
    
    # Show summary
    for issue in capability_report.issues[:3]:
        console.print(f"  • {issue.reason}")
        console.print(f"    [dim]→ {issue.remediation}[/dim]\n")
    
    if len(capability_report.issues) > 3:
        console.print(
            f"  [dim]... and {len(capability_report.issues) - 3} more issue(s)[/dim]\n"
        )
    
    sys.exit(EX_UNSUPPORTED)


def _dispatch_executor(
    spec: Spec,
    variables: dict[str, str] | None,
    verbose: bool,
) -> RunResult:
    """Route to appropriate executor based on pattern type.
    
    Raises:
        SystemExit: With EX_RUNTIME on execution error
    """
    console.print(f"[bold green]Running workflow:[/bold green] {spec.name}")
    if verbose:
        console.print(f"[dim]Provider: {spec.runtime.provider}[/dim]")
        console.print(f"[dim]Model: {spec.runtime.model_id or 'default'}[/dim]")
        console.print(f"[dim]Pattern: {spec.pattern.type}[/dim]")
    
    try:
        if spec.pattern.type == PatternType.CHAIN:
            if spec.pattern.config.steps and len(spec.pattern.config.steps) == 1:
                return run_single_agent(spec, variables)
            else:
                return run_chain(spec, variables)
        
        elif spec.pattern.type == PatternType.WORKFLOW:
            if spec.pattern.config.tasks and len(spec.pattern.config.tasks) == 1:
                return run_single_agent(spec, variables)
            else:
                return run_workflow(spec, variables)
        
        elif spec.pattern.type == PatternType.ROUTING:
            return run_routing(spec, variables)
        
        elif spec.pattern.type == PatternType.PARALLEL:
            return run_parallel(spec, variables)
        
        else:
            console.print(
                f"\n[red]Error:[/red] Pattern '{spec.pattern.type}' not supported yet"
            )
            sys.exit(EX_UNSUPPORTED)
    
    except ExecutionError as e:
        console.print(f"\n[red]Execution failed:[/red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(EX_RUNTIME)


def _write_and_report_artifacts(
    spec: Spec,
    result: RunResult,
    out: str,
    force: bool,
    variables: dict[str, str] | None,
) -> list[str]:
    """Write artifacts and handle errors.
    
    Returns:
        List of written artifact paths
    
    Raises:
        SystemExit: With EX_IO on write failure
    """
    if not spec.outputs or not spec.outputs.artifacts:
        return []
    
    try:
        return write_artifacts(
            spec.outputs.artifacts,
            result.last_response or "",
            out,
            force,
            variables=variables,
            execution_context=result.execution_context,
        )
    except ArtifactError as e:
        console.print(f"\n[red]Failed to write artifacts:[/red] {e}")
        sys.exit(EX_IO)


# Refactored run command
@app.command()
def run(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    var: Annotated[
        list[str] | None, typer.Option("--var", help="Variable override (key=value)")
    ] = None,
    out: Annotated[
        str, typer.Option("--out", help="Output directory for artifacts")
    ] = "./artifacts",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing artifacts")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Run a workflow from a YAML or JSON file."""
    try:
        # Parse variables
        variables = parse_variables(var) if var else {}
        
        # Load and validate spec
        spec = _load_and_validate_spec(spec_file, variables, verbose)
        
        # Check capability compatibility
        capability_report = check_capability(spec)
        if not capability_report.supported:
            _handle_unsupported_spec(spec, spec_file, capability_report, out)
        
        # Configure telemetry
        if spec.telemetry:
            configure_telemetry(spec.telemetry.model_dump() if spec.telemetry else None)
        
        # Execute workflow
        result = _dispatch_executor(spec, variables, verbose)
        
        if not result.success:
            console.print(f"\n[red]Workflow failed:[/red] {result.error}")
            sys.exit(EX_RUNTIME)
        
        # Write artifacts
        written_files = _write_and_report_artifacts(spec, result, out, force, variables)
        result.artifacts_written = written_files
        
        # Show success summary
        console.print("\n[bold green]✓ Workflow completed successfully[/bold green]")
        console.print(f"Duration: {result.duration_seconds:.2f}s")
        
        if result.artifacts_written:
            console.print("\nArtifacts written:")
            for artifact in result.artifacts_written:
                console.print(f"  • [cyan]{artifact}[/cyan]")
        
        sys.exit(EX_OK)
    
    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)
```

---

### Phase 4: Simplify Executor Functions (Priority 3)
**Goal**: Apply `exec/utils.py` to all executors, reduce local complexity  
**Impact**: Clears 3 C901 violations, consistent patterns across executors  

#### 4.1 Refactor `single_agent.py`

**Replace**:
- `_get_retry_config(spec)` → `from strands_cli.exec.utils import get_retry_config`
- Inline retry decorator → `invoke_agent_with_retry(...)`
- Token estimation → `estimate_tokens(...)`

**Before**:
```python
def _get_retry_config(spec: Spec) -> tuple[int, int, int]:
    # 30 lines of config extraction
    ...

# Inline retry decorator with 15 lines
@retry(...)
async def _execute_agent() -> AgentResult:
    ...
```

**After**:
```python
from strands_cli.exec.utils import get_retry_config, invoke_agent_with_retry

# Just get config
max_attempts, wait_min, wait_max = get_retry_config(spec)

# Use shared execution helper
response = await invoke_agent_with_retry(agent, task_input, max_attempts, wait_min, wait_max)
```

#### 4.2 Refactor `chain.py`, `workflow.py`, `parallel.py`

Apply same pattern:
- Remove local `_get_retry_config` (use `exec.utils`)
- Remove local `_check_budget_warning` (use `exec.utils.check_budget_threshold`)
- Use `invoke_agent_with_retry` instead of inline retry decorators

---

### Phase 5: Simplify Loader (Priority 3)

#### 5.1 Extract Helper in `yaml_loader.py`

```python
def _parse_file_content(file_path: Path) -> dict[str, Any]:
    """Parse YAML or JSON file content.
    
    Raises:
        LoadError: If file cannot be parsed
    """
    content = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    
    try:
        if suffix in {".yaml", ".yml"}:
            yaml = YAML(typ="safe", pure=True)
            return yaml.load(content)
        elif suffix == ".json":
            return json.loads(content)
        else:
            raise LoadError(f"Unsupported file extension: {suffix}")
    except Exception as e:
        raise LoadError(f"Failed to parse {file_path}: {e}") from e


def _merge_cli_variables(spec_data: dict[str, Any], variables: dict[str, str]) -> None:
    """Merge CLI variables into spec.inputs.values (mutates spec_data)."""
    if "inputs" not in spec_data:
        spec_data["inputs"] = {}
    if not isinstance(spec_data["inputs"], dict):
        spec_data["inputs"] = {}
    
    if "values" not in spec_data["inputs"]:
        spec_data["inputs"]["values"] = {}
    if not isinstance(spec_data["inputs"]["values"], dict):
        spec_data["inputs"]["values"] = {}
    
    spec_data["inputs"]["values"].update(variables)


def load_spec(file_path: str | Path, variables: dict[str, str] | None = None) -> Spec:
    """Load and validate a workflow spec from YAML or JSON."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise LoadError(f"Spec file not found: {file_path}")
    
    # Security check: file size
    file_size = file_path.stat().st_size
    if file_size > MAX_SPEC_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        max_mb = MAX_SPEC_SIZE_BYTES / (1024 * 1024)
        raise LoadError(f"Spec file too large: {size_mb:.1f}MB exceeds {max_mb:.0f}MB")
    
    # Parse file
    spec_data = _parse_file_content(file_path)
    
    if not isinstance(spec_data, dict):
        raise LoadError(f"Spec must be a dictionary, got {type(spec_data)}")
    
    # Merge CLI variables
    if variables:
        _merge_cli_variables(spec_data, variables)
    
    # Validate and convert
    validate_spec(spec_data)
    
    try:
        return Spec.model_validate(spec_data)
    except PydanticValidationError as e:
        raise LoadError(f"Failed to create typed Spec: {e}") from e
```

---

## Implementation Checklist

### Week 1: Foundation (Phase 1)
- [ ] Create `src/strands_cli/exec/utils.py` with shared utilities
- [ ] Write `tests/test_exec_utils.py` with 90%+ coverage
- [ ] Run `uv run pytest tests/test_exec_utils.py` — ensure all pass
- [ ] Run `uv run mypy src/strands_cli/exec/utils.py` — ensure strict type check passes

### Week 2: Major Refactors (Phases 2-3)
- [ ] Refactor `capability/checker.py` into validation functions
- [ ] Run `uv run pytest tests/test_capability.py` — ensure 100% existing tests pass
- [ ] Add `tests/test_capability_refactor.py` for new functions
- [ ] Refactor `__main__.py` run command into helpers
- [ ] Run `uv run pytest tests/test_cli_integration.py` — ensure CLI tests pass
- [ ] Run `uv run ruff check src/strands_cli/__main__.py` — verify C901 cleared

### Week 3: Executor Simplification (Phase 4)
- [ ] Refactor `single_agent.py` to use `exec.utils`
- [ ] Refactor `chain.py` to use `exec.utils`
- [ ] Refactor `workflow.py` to use `exec.utils`
- [ ] Refactor `parallel.py` to use `exec.utils`
- [ ] Run `uv run pytest tests/test_*.py` — ensure all executor tests pass
- [ ] Run `uv run ruff check src/strands_cli/exec/` — verify C901 cleared

### Week 4: Polish & Validation (Phase 5)
- [ ] Refactor `loader/yaml_loader.py` extraction helpers
- [ ] Run `uv run pytest tests/test_loader.py` — ensure loader tests pass
- [ ] Run **full CI pipeline**: `.\scripts\dev.ps1 ci`
  - [ ] Lint passes (no C901 violations)
  - [ ] Type check passes (mypy strict)
  - [ ] All tests pass (287+ tests)
  - [ ] Coverage ≥ 85% maintained
- [ ] Update `CHANGELOG.md` with refactoring summary
- [ ] Run `uv run strands validate examples/*.yaml` — smoke test all examples

---

## Verification Criteria

### Success Metrics
✅ **Zero C901 violations** in `uv run ruff check .`  
✅ **Zero new test failures** in `uv run pytest`  
✅ **Coverage ≥ 85%** maintained in `.\scripts\dev.ps1 test-cov`  
✅ **Zero mypy errors** in `uv run mypy src`  
✅ **All 287+ tests pass** after refactoring  
✅ **All example specs validate** successfully  

### Quality Gates
- [ ] Each extracted helper has docstring with Args/Returns/Raises
- [ ] Each new function has dedicated unit test
- [ ] No function exceeds 100 lines (target: 50-70 lines)
- [ ] No code duplication across executors
- [ ] All type hints use Python 3.12+ syntax (`str | None` not `Optional[str]`)

---

## Risk Mitigation

### Risk 1: Test Breakage
**Mitigation**: Refactor incrementally, run tests after each phase  
**Recovery**: Git branch per phase; revert if tests fail  

### Risk 2: Behavior Changes
**Mitigation**: Helpers are pure extractions (no logic changes)  
**Recovery**: Compare before/after execution on all example specs  

### Risk 3: Performance Regression
**Mitigation**: Shared utilities avoid overhead (single import, no runtime cost)  
**Recovery**: Benchmark `run_chain` on 10-step example before/after  

---

## Rollout Plan

### Option A: Big Bang (Fast, Higher Risk)
1. Complete all phases in feature branch
2. Run full CI pipeline
3. Merge to master in single PR

**Timeline**: 1 week  
**Risk**: High (all changes at once)  

### Option B: Incremental (Slower, Lower Risk) ✅ **RECOMMENDED**
1. Phase 1 → PR #1 (exec/utils.py)
2. Phase 2 → PR #2 (capability/checker.py)
3. Phase 3 → PR #3 (__main__.py)
4. Phase 4 → PR #4 (all executors)
5. Phase 5 → PR #5 (loader)

**Timeline**: 3-4 weeks  
**Risk**: Low (isolated changes, early validation)  

---

## Related Work

This plan complements security remediation (see `PHASE3.md` Security section):
- Template sandboxing (Priority 🔥 Critical)
- HTTP executor allowlists (Priority 🟡 High)
- Path sanitization (Priority 🟡 High)

**Sequence**: Can run in parallel with security fixes (no dependencies)

---

## Appendix: Complexity Reduction Examples

### Before: `check_capability` (367 lines, C901)
```python
def check_capability(spec: Spec) -> CapabilityReport:
    issues: list[CapabilityIssue] = []
    
    # 50 lines: Agent validation
    if len(spec.agents) != 1:
        ...
    
    # 40 lines: Provider validation
    if spec.runtime.provider not in {...}:
        ...
    
    # 100 lines: Pattern validation (chain, workflow, routing, parallel)
    if spec.pattern.type == PatternType.CHAIN:
        ...
    elif spec.pattern.type == PatternType.WORKFLOW:
        ...
    # ... 200 more lines
```

### After: `check_capability` (50 lines, no C901)
```python
def check_capability(spec: Spec) -> CapabilityReport:
    issues: list[CapabilityIssue] = []
    
    _validate_agents(spec, issues)
    _validate_provider(spec, issues)
    _validate_pattern_type(spec, issues)
    _validate_chain_pattern(spec, issues)
    _validate_workflow_pattern(spec, issues)
    _validate_routing_pattern(spec, issues)
    _validate_parallel_pattern(spec, issues)
    _validate_secrets(spec, issues)
    _validate_tools(spec, issues)
    
    normalized = _build_normalized_values(spec) if not issues else None
    
    return CapabilityReport(
        supported=len(issues) == 0,
        issues=issues,
        normalized=normalized,
    )
```

**Result**: Complexity reduced from 367 lines to 50 lines; each helper is 20-50 lines and independently testable.

---

## Next Steps

1. **Review this plan** with team
2. **Choose rollout strategy** (Option A vs B)
3. **Create feature branch**: `git checkout -b refactor/code-quality`
4. **Start Phase 1**: Create `exec/utils.py` with tests
5. **Track progress** using checklist above

---

**Document Version**: 1.0  
**Last Updated**: November 5, 2025  
**Author**: Code Quality Review (based on PHASE3.md analysis)

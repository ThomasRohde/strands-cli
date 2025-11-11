# Week 1 MVP Implementation Plan: Interactive HITL Python API

**Goal:** Enable developers to run HITL workflows as interactive Python programs, prompting users in-terminal instead of requiring CLI exit/resume cycles.

**Duration:** 5 days  
**Complexity:** Medium  
**Status:** Ready for Implementation

---

## Overview

Build a thin wrapper layer over existing executors with automatic session management and HITL loop orchestration. The existing codebase is well-structured with all core functionality (executors, session management, HITL infrastructure) already implemented. This MVP adds a developer-friendly Python API surface.

### Key Deliverables

1. **API module structure** (`src/strands_cli/api/`)
2. **Interactive execution loop** with automatic HITL handling
3. **Sync/async execution methods** for flexibility
4. **Comprehensive tests** (unit + integration)
5. **Documentation and examples**

---

## Day 1-2: Core API Infrastructure

### Task 1.1: Create API Module Structure

**Files to Create:**
- `src/strands_cli/api/__init__.py` (200 lines)
- `src/strands_cli/api/execution.py` (300 lines)
- `src/strands_cli/api/handlers.py` (100 lines)

**Implementation Details:**

#### `src/strands_cli/api/__init__.py` - Workflow Class

```python
"""Strands Python API - First-class programmatic interface.

Example:
    >>> from strands import Workflow
    >>> workflow = Workflow.from_file("workflow.yaml")
    >>> result = workflow.run_interactive(topic="AI")
    >>> print(result.last_response)
"""

from pathlib import Path
from typing import Any

from strands_cli.loader import load_spec
from strands_cli.types import Spec, RunResult
from strands_cli.api.execution import WorkflowExecutor


class Workflow:
    """Primary API for creating and executing workflows.
    
    Can be created from YAML files or built programmatically.
    Supports both interactive (terminal prompts) and async execution.
    """
    
    def __init__(self, spec: Spec):
        """Create workflow from validated Spec.
        
        Args:
            spec: Validated workflow specification
        """
        self.spec = spec
    
    @classmethod
    def from_file(cls, path: str | Path, **variables: Any) -> "Workflow":
        """Load workflow from YAML/JSON file.
        
        Args:
            path: Path to workflow spec file
            **variables: Variable overrides (key=value)
            
        Returns:
            Workflow instance ready to run
            
        Raises:
            LoadError: If file cannot be loaded
            SchemaValidationError: If spec is invalid
            
        Example:
            >>> workflow = Workflow.from_file("workflow.yaml", topic="AI")
            >>> result = workflow.run_interactive()
        """
        spec = load_spec(str(path), variables)
        return cls(spec)
    
    def run_interactive(self, **variables: Any) -> RunResult:
        """Execute workflow with interactive HITL prompts.
        
        When workflow reaches HITL steps, prompts user in terminal
        for input instead of pausing execution. Ideal for local
        development and debugging.
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details
            
        Example:
            >>> result = workflow.run_interactive(topic="AI")
            >>> print(result.last_response)
        """
        import asyncio
        return asyncio.run(self.run_interactive_async(**variables))
    
    async def run_interactive_async(self, **variables: Any) -> RunResult:
        """Execute workflow asynchronously with interactive HITL.
        
        For high-performance applications that need async control flow.
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details
        """
        executor = WorkflowExecutor(self.spec)
        return await executor.run_interactive(variables)
    
    def run(self, **variables: Any) -> RunResult:
        """Execute workflow (non-interactive, uses session persistence).
        
        Standard execution mode - saves session and exits at HITL steps.
        Use for production workflows or when integrating with external
        approval systems.
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details (may indicate HITL pause)
        """
        import asyncio
        return asyncio.run(self.run_async(**variables))
    
    async def run_async(self, **variables: Any) -> RunResult:
        """Execute workflow asynchronously (non-interactive).
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details
        """
        executor = WorkflowExecutor(self.spec)
        return await executor.run(variables)


# Re-export for convenience
__all__ = ["Workflow"]
```

#### `src/strands_cli/api/handlers.py` - Terminal HITL Handler

```python
"""Interactive HITL handlers for terminal prompts."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from strands_cli.types import HITLState


def terminal_hitl_handler(hitl_state: HITLState) -> str:
    """Default terminal prompt handler for interactive HITL.
    
    Displays HITL prompt with Rich formatting and optional context,
    then prompts user for input via standard input.
    
    Args:
        hitl_state: HITL pause state with prompt/context
        
    Returns:
        User's response string
        
    Example:
        >>> from strands_cli.types import HITLState
        >>> state = HITLState(
        ...     active=True,
        ...     prompt="Approve findings?",
        ...     context_display="Research results: ...",
        ... )
        >>> response = terminal_hitl_handler(state)
    """
    console = Console()
    
    # Display HITL prompt
    console.print()
    console.print(
        Panel(
            f"[bold yellow]🤝 HUMAN INPUT REQUIRED[/bold yellow]\n\n{hitl_state.prompt}",
            border_style="yellow",
            padding=(1, 2),
            title="Interactive HITL",
        )
    )
    
    # Display context if provided
    if hitl_state.context_display:
        # Truncate long context for readability
        context = hitl_state.context_display
        truncated = False
        if len(context) > 1000:
            context = context[:1000]
            truncated = True
        
        console.print()
        console.print(
            Panel(
                f"[bold]Context:[/bold]\n\n{context}",
                border_style="dim",
                padding=(1, 2),
            )
        )
        
        if truncated:
            console.print("[dim](Context truncated for display)[/dim]")
    
    # Show default if provided
    if hitl_state.default_response:
        console.print(
            f"\n[dim]Default (press Enter):[/dim] {hitl_state.default_response}"
        )
    
    # Prompt for user input
    console.print()
    response = Prompt.ask("Your response")
    
    # Use default if empty and default is provided
    if not response.strip() and hitl_state.default_response:
        console.print(f"[dim]Using default: {hitl_state.default_response}[/dim]")
        return hitl_state.default_response
    
    return response.strip()


__all__ = ["terminal_hitl_handler"]
```

#### `src/strands_cli/api/execution.py` - WorkflowExecutor

```python
"""Workflow execution engine with HITL support."""

import asyncio
from typing import Any, Callable

from strands_cli.types import Spec, RunResult, PatternType, HITLState, SessionState
from strands_cli.session.repository import FileSessionRepository
from strands_cli.session.state import SessionMetadata, SessionStatus
from strands_cli.exec.chain import run_chain
from strands_cli.exec.workflow import run_workflow
from strands_cli.exec.routing import run_routing
from strands_cli.exec.parallel import run_parallel
from strands_cli.exec.evaluator_optimizer import run_evaluator_optimizer
from strands_cli.exec.orchestrator import run_orchestrator
from strands_cli.exec.graph import run_graph
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.api.handlers import terminal_hitl_handler


class WorkflowExecutor:
    """Executes workflows with optional interactive HITL."""
    
    def __init__(self, spec: Spec):
        """Initialize executor with workflow spec.
        
        Args:
            spec: Validated workflow specification
        """
        self.spec = spec
    
    async def run_interactive(
        self,
        variables: dict[str, Any],
        hitl_handler: Callable[[HITLState], str] | None = None,
    ) -> RunResult:
        """Run workflow with interactive HITL prompts.
        
        Creates session automatically and loops through HITL pauses,
        prompting user in terminal instead of exiting.
        
        Args:
            variables: Runtime variable overrides
            hitl_handler: Optional custom HITL handler (defaults to terminal_hitl_handler)
            
        Returns:
            RunResult with execution details
        """
        if hitl_handler is None:
            hitl_handler = terminal_hitl_handler
        
        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=f"interactive-{self.spec.name}",
                workflow_name=self.spec.name,
                status=SessionStatus.RUNNING,
            ),
            variables=variables,
            runtime_config={},
            pattern_state={},
            token_usage={},
            artifacts_written=[],
        )
        
        # Save initial session
        await session_repo.save(session_state)
        
        try:
            # HITL loop: continue until workflow completes
            hitl_response = None
            max_iterations = 100  # Safety limit
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                
                # Execute workflow (may pause at HITL)
                result = await self._execute_pattern(
                    variables,
                    session_state,
                    session_repo,
                    hitl_response,
                )
                
                # Check if paused for HITL
                if result.agent_id == "hitl" and result.exit_code == EX_HITL_PAUSE:
                    # Extract HITL state from session
                    hitl_state_data = session_state.pattern_state.get("hitl_state", {})
                    hitl_state = HITLState(**hitl_state_data)
                    
                    # Prompt user via handler
                    hitl_response = hitl_handler(hitl_state)
                    
                    # Update session state with response
                    hitl_state.user_response = hitl_response
                    session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                    await session_repo.save(session_state)
                    
                    # Continue to next iteration (resume with response)
                    continue
                else:
                    # Workflow completed successfully
                    return result
            
            # Safety limit reached
            raise RuntimeError(
                f"HITL loop exceeded maximum iterations ({max_iterations}). "
                "Possible infinite loop in workflow."
            )
        
        except Exception as e:
            # Mark session as failed
            session_state.metadata.status = SessionStatus.FAILED
            await session_repo.save(session_state)
            raise
        finally:
            # Cleanup session if completed successfully
            if session_state.metadata.status == SessionStatus.RUNNING:
                session_state.metadata.status = SessionStatus.COMPLETED
                await session_repo.save(session_state)
    
    async def run(
        self,
        variables: dict[str, Any],
    ) -> RunResult:
        """Run workflow without interactive mode (session-based HITL).
        
        Standard execution mode that saves session and exits at HITL steps.
        
        Args:
            variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details (may indicate HITL pause)
        """
        # Create session for HITL tracking
        session_repo = FileSessionRepository()
        session_state = SessionState(
            metadata=SessionMetadata(
                session_id=f"api-{self.spec.name}",
                workflow_name=self.spec.name,
                status=SessionStatus.RUNNING,
            ),
            variables=variables,
            runtime_config={},
            pattern_state={},
            token_usage={},
            artifacts_written=[],
        )
        
        # Save initial session
        await session_repo.save(session_state)
        
        try:
            # Execute workflow (will exit at HITL)
            result = await self._execute_pattern(
                variables,
                session_state,
                session_repo,
                None,
            )
            
            # Update session status
            if result.agent_id == "hitl":
                session_state.metadata.status = SessionStatus.PAUSED
            else:
                session_state.metadata.status = SessionStatus.COMPLETED
            
            await session_repo.save(session_state)
            return result
        
        except Exception as e:
            # Mark session as failed
            session_state.metadata.status = SessionStatus.FAILED
            await session_repo.save(session_state)
            raise
    
    async def _execute_pattern(
        self,
        variables: dict[str, Any],
        session_state: SessionState,
        session_repo: FileSessionRepository,
        hitl_response: str | None = None,
    ) -> RunResult:
        """Route to appropriate executor based on pattern type.
        
        Args:
            variables: Runtime variable overrides
            session_state: Current session state
            session_repo: Session repository
            hitl_response: HITL response for resume (if any)
            
        Returns:
            RunResult from executor
        """
        pattern = self.spec.pattern.type
        
        if pattern == PatternType.CHAIN:
            return await run_chain(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.WORKFLOW:
            return await run_workflow(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.ROUTING:
            return await run_routing(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.PARALLEL:
            return await run_parallel(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.EVALUATOR_OPTIMIZER:
            return await run_evaluator_optimizer(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.ORCHESTRATOR_WORKERS:
            return await run_orchestrator(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        elif pattern == PatternType.GRAPH:
            return await run_graph(
                self.spec,
                variables,
                session_state,
                session_repo,
                hitl_response,
            )
        else:
            raise ValueError(f"Unsupported pattern type: {pattern}")


__all__ = ["WorkflowExecutor"]
```

### Task 1.2: Update Package Exports

**File:** `src/strands_cli/__init__.py`

Add API exports to main package:

```python
"""Strands CLI - Declarative agentic workflows on AWS Bedrock/Ollama/OpenAI."""

# Import version
from strands_cli._version import __version__

# Import API classes
from strands_cli.api import Workflow

__all__ = ["__version__", "Workflow"]
```

### Acceptance Criteria (Day 1-2)

- [ ] `Workflow` class created with `from_file()` classmethod
- [ ] `run_interactive()` and `run_interactive_async()` methods implemented
- [ ] `run()` and `run_async()` methods implemented (non-interactive)
- [ ] `terminal_hitl_handler()` function displays Rich prompts
- [ ] `WorkflowExecutor` implements HITL loop logic
- [ ] Session auto-creation works correctly
- [ ] Package exports include `Workflow` class
- [ ] Type hints complete (mypy clean)

---

## Day 3-4: Interactive Execution & HITL Loop

### Task 3.1: HITL Loop Implementation

**Focus Areas:**

1. **Multiple HITL pause handling**
   - While loop continues until workflow completes
   - Each HITL pause prompts user via handler
   - Session state updated with responses
   - Proper loop termination on completion

2. **Session state management**
   - Auto-create session with unique ID
   - Update HITL state after each response
   - Mark session as COMPLETED/FAILED on exit
   - Proper cleanup in finally block

3. **Error handling**
   - Try/except around execution loop
   - Mark session as FAILED on exception
   - Re-raise exception after cleanup
   - Safety limit for infinite loops (max_iterations)

### Task 3.2: Integration with Existing Executors

**Verification Points:**

1. **Chain pattern** - Test with chain-hitl-approval-demo.yaml
2. **Workflow pattern** - Test with workflow containing HITL tasks
3. **Parallel pattern** - Test with parallel-hitl-branch-demo.yaml
4. **Graph pattern** - Test with graph-hitl-approval-demo-openai.yaml
5. **Evaluator-optimizer** - Test with evaluator-optimizer-hitl-review-openai.yaml
6. **Orchestrator-workers** - Test with orchestrator-hitl-review-openai.yaml

### Task 3.3: Edge Cases

Handle special scenarios:

1. **Empty responses** - Use default if provided
2. **Multiple consecutive HITL steps** - Loop handles N pauses
3. **HITL timeout** - Currently not enforced in interactive mode (document as limitation)
4. **KeyboardInterrupt** - Graceful exit with session preservation
5. **Session ID conflicts** - Use timestamp-based unique IDs

### Acceptance Criteria (Day 3-4)

- [ ] HITL loop handles multiple pauses correctly
- [ ] Session state persists across iterations
- [ ] All 7 workflow patterns work with interactive mode
- [ ] Error handling marks sessions as FAILED
- [ ] KeyboardInterrupt handled gracefully
- [ ] Edge cases documented and tested
- [ ] Manual testing with example workflows passes

---

## Day 5: Testing & Documentation

### Task 5.1: Unit Tests

**File:** `tests/test_api_workflow.py` (200 lines)

```python
"""Unit tests for Workflow API."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from strands_cli.api import Workflow
from strands_cli.types import RunResult, Spec
from strands_cli.exit_codes import EX_OK


class TestWorkflow:
    """Test Workflow class."""
    
    def test_from_file_loads_spec(self, tmp_path: Path) -> None:
        """Test that from_file loads and validates spec."""
        # Create minimal spec file
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text("""
version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  agent1:
    prompt: "Test prompt"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Test input"
""")
        
        # Load workflow
        workflow = Workflow.from_file(spec_file)
        
        # Verify
        assert isinstance(workflow.spec, Spec)
        assert workflow.spec.name == "test-workflow"
    
    def test_from_file_with_variables(self, tmp_path: Path) -> None:
        """Test that from_file merges variables."""
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text("""
version: 0
name: test-workflow
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  agent1:
    prompt: "Research {{topic}}"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "{{topic}}"
""")
        
        # Load with variables
        workflow = Workflow.from_file(spec_file, topic="AI")
        
        # Verify (variables merged during load_spec)
        assert workflow.spec is not None
    
    @pytest.mark.asyncio
    async def test_run_interactive_async(self, mocker) -> None:
        """Test async interactive execution."""
        # Mock WorkflowExecutor
        mock_executor = mocker.patch("strands_cli.api.execution.WorkflowExecutor")
        mock_instance = AsyncMock()
        mock_executor.return_value = mock_instance
        
        mock_result = RunResult(
            agent_id="agent1",
            exit_code=EX_OK,
            last_response="Test response",
        )
        mock_instance.run_interactive.return_value = mock_result
        
        # Create workflow
        spec = MagicMock(spec=Spec)
        workflow = Workflow(spec)
        
        # Run
        result = await workflow.run_interactive_async(topic="AI")
        
        # Verify
        assert result.last_response == "Test response"
        mock_instance.run_interactive.assert_called_once()


# More tests for run(), run_async(), error handling, etc.
```

### Task 5.2: Integration Tests

**File:** `tests/test_interactive_hitl.py` (150 lines)

```python
"""Integration tests for interactive HITL execution."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from strands_cli.api import Workflow
from strands_cli.types import HITLState
from strands_cli.exit_codes import EX_OK


@pytest.mark.asyncio
async def test_interactive_hitl_single_pause(mocker, tmp_path: Path) -> None:
    """Test interactive execution with single HITL pause."""
    # Create spec with HITL step
    spec_file = tmp_path / "hitl.yaml"
    spec_file.write_text("""
version: 0
name: hitl-test
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  agent1:
    prompt: "Generate report"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Generate report"
      - type: hitl
        prompt: "Approve report?"
      - agent: agent1
        input: "Finalize: {{hitl_response}}"
""")
    
    # Mock LLM responses
    mock_invoke = mocker.patch("strands_cli.exec.utils.invoke_agent_with_retry")
    mock_invoke.side_effect = [
        "Draft report",
        "Final report with approval",
    ]
    
    # Mock HITL handler
    def mock_handler(state: HITLState) -> str:
        assert state.prompt == "Approve report?"
        return "approved"
    
    # Load and run
    workflow = Workflow.from_file(spec_file)
    result = await workflow.run_interactive_async(hitl_handler=mock_handler)
    
    # Verify
    assert result.exit_code == EX_OK
    assert "approved" in result.last_response.lower()


@pytest.mark.asyncio
async def test_interactive_hitl_multiple_pauses(mocker, tmp_path: Path) -> None:
    """Test interactive execution with multiple HITL pauses."""
    # Spec with 2 HITL steps
    spec_file = tmp_path / "multi-hitl.yaml"
    spec_file.write_text("""
version: 0
name: multi-hitl-test
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  agent1:
    prompt: "Work on task"
pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "Step 1"
      - type: hitl
        prompt: "Review step 1?"
      - agent: agent1
        input: "Step 2"
      - type: hitl
        prompt: "Review step 2?"
      - agent: agent1
        input: "Final step"
""")
    
    # Mock responses
    mock_invoke = mocker.patch("strands_cli.exec.utils.invoke_agent_with_retry")
    mock_invoke.side_effect = [
        "Step 1 result",
        "Step 2 result",
        "Final result",
    ]
    
    # Track HITL calls
    hitl_calls = []
    
    def mock_handler(state: HITLState) -> str:
        hitl_calls.append(state.prompt)
        return f"approved-{len(hitl_calls)}"
    
    # Run
    workflow = Workflow.from_file(spec_file)
    result = await workflow.run_interactive_async(hitl_handler=mock_handler)
    
    # Verify
    assert len(hitl_calls) == 2
    assert hitl_calls[0] == "Review step 1?"
    assert hitl_calls[1] == "Review step 2?"
    assert result.exit_code == EX_OK


# More tests for error handling, session cleanup, etc.
```

### Task 5.3: Example Scripts

**File:** `examples/api/01_interactive_hitl.py`

```python
#!/usr/bin/env python3
"""Interactive HITL research workflow example.

Demonstrates:
- Loading workflow from YAML
- Running with interactive HITL prompts
- Accessing execution results
"""

from strands import Workflow


def main():
    """Run interactive HITL workflow."""
    # Load workflow with HITL steps
    workflow = Workflow.from_file(
        "examples/chain-hitl-business-proposal-openai.yaml"
    )
    
    # Run interactively - prompts user in terminal for HITL responses
    print("Starting interactive workflow...")
    print("You will be prompted for input at HITL steps.\n")
    
    result = workflow.run_interactive(
        topic="quantum computing applications in cryptography"
    )
    
    # Access results
    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETED")
    print("=" * 60)
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Success: {result.success}")
    print(f"\nFinal Response:\n{result.last_response}")
    
    if result.artifacts_written:
        print(f"\nArtifacts written:")
        for artifact in result.artifacts_written:
            print(f"  - {artifact}")


if __name__ == "__main__":
    main()
```

### Task 5.4: Documentation

**File:** `docs/API.md` (new file)

Create comprehensive API documentation covering:
- Quickstart guide
- `Workflow` class reference
- Interactive vs non-interactive modes
- Example usage patterns
- Error handling
- Limitations and known issues

**File:** `CHANGELOG.md`

Add v0.14.0-alpha release notes:

```markdown
## [0.14.0-alpha] - 2025-11-XX

### Added

- **Python API (MVP)**: First-class programmatic interface for workflows
  - `Workflow` class with `from_file()` loader
  - `run_interactive()` method for terminal-based HITL workflows
  - `run_async()` for async execution
  - Automatic session management
  - Interactive HITL handler with Rich UI
- API examples in `examples/api/`
- Comprehensive API documentation in `docs/API.md`

### Changed

- Exported `Workflow` from main package (`from strands import Workflow`)
- Session creation can now happen in API layer (not just CLI)

### Technical Details

- New modules: `api/__init__.py`, `api/execution.py`, `api/handlers.py`
- HITL loop orchestration handles multiple pauses automatically
- Session state managed transparently for interactive mode
- Compatible with all 7 workflow patterns
```

### Acceptance Criteria (Day 5)

- [ ] Unit tests cover `Workflow` class (>85% coverage)
- [ ] Integration tests verify HITL loop with multiple pauses
- [ ] Example script demonstrates interactive HITL workflow
- [ ] `docs/API.md` created with comprehensive guide
- [ ] `CHANGELOG.md` updated with v0.14.0-alpha notes
- [ ] All tests pass: `.\scripts\dev.ps1 test`
- [ ] Type checking clean: `.\scripts\dev.ps1 typecheck`
- [ ] Lint passes: `.\scripts\dev.ps1 lint`

---

## Testing Strategy

### Unit Test Coverage

**Target:** ≥85% coverage for API module

**Test Categories:**
1. **Workflow class**
   - `from_file()` with valid/invalid specs
   - Variable merging
   - Spec validation errors
   - `run_interactive()` sync wrapper
   - `run()` non-interactive mode

2. **WorkflowExecutor**
   - HITL loop iteration
   - Session creation and cleanup
   - Error handling (mark session as FAILED)
   - Pattern routing
   - Max iterations safety limit

3. **HITL Handler**
   - Terminal prompt display
   - Context truncation
   - Default response handling
   - Empty input handling

### Integration Test Scenarios

**Test Real Workflows:**

1. **Chain + single HITL** - Verify loop completes after 1 pause
2. **Chain + multiple HITL** - Verify loop handles N pauses
3. **Workflow + HITL task** - Verify DAG with HITL works
4. **Parallel + HITL branch** - Verify parallel HITL handling
5. **Graph + HITL node** - Verify state machine HITL
6. **Error during HITL** - Verify session marked FAILED
7. **KeyboardInterrupt** - Verify graceful exit

### Manual Testing Checklist

- [ ] Run `01_interactive_hitl.py` example script
- [ ] Test with chain-hitl-approval-demo.yaml
- [ ] Test with parallel-hitl-branch-demo.yaml
- [ ] Test with graph-hitl-approval-demo-openai.yaml
- [ ] Verify Rich panels display correctly
- [ ] Verify context truncation works
- [ ] Verify default responses work
- [ ] Test Ctrl+C handling
- [ ] Verify session files created correctly

---

## Implementation Notes

### Current Executor Compatibility

**Good News:** All executors already support the required interface:

```python
async def run_<pattern>(
    spec: Spec,
    variables: dict[str, Any] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,
) -> RunResult
```

**No modifications needed** to existing executors. The API layer wraps them cleanly.

### Session Management

**Auto-Creation Strategy:**
- Create session in `WorkflowExecutor` with unique ID
- Use pattern: `f"interactive-{spec.name}-{timestamp}"`
- Save before first execution
- Update after each HITL response
- Mark COMPLETED/FAILED on exit

**Cleanup:**
- Interactive sessions can be cleaned up after completion
- Non-interactive sessions should persist for resume
- Consider auto-cleanup task for old interactive sessions

### HITL Loop Logic

**Key Pattern:**

```python
hitl_response = None
while True:
    result = await executor(spec, vars, session, repo, hitl_response)
    
    if result.agent_id == "hitl":
        # Prompt user
        hitl_state = HITLState(**session.pattern_state["hitl_state"])
        hitl_response = handler(hitl_state)
        
        # Update session and continue
        continue
    else:
        # Workflow completed
        return result
```

**Safety:** Add max_iterations limit (e.g., 100) to prevent infinite loops.

### Error Handling

**Exception Categories:**

1. **Load errors** - Spec file not found, invalid YAML
   - Raise immediately, no session created
   
2. **Validation errors** - Schema validation failure
   - Raise immediately, no session created
   
3. **Execution errors** - LLM failure, tool error
   - Mark session as FAILED, re-raise
   
4. **User interruption** - KeyboardInterrupt
   - Mark session as PAUSED (can resume later)
   - Graceful exit with message

### Type Safety

**Key Types:**

```python
from typing import Callable, Protocol

class HITLHandler(Protocol):
    """HITL handler protocol."""
    def __call__(self, state: HITLState) -> str: ...

# Usage in WorkflowExecutor:
def __init__(
    self,
    spec: Spec,
    hitl_handler: Callable[[HITLState], str] | None = None,
):
    ...
```

**Ensure:**
- All public methods fully type-hinted
- Mypy strict mode passes
- Pylance shows autocomplete for all APIs

---

## Success Metrics

### Functional Requirements

✅ Developer can load workflow from YAML via `Workflow.from_file()`  
✅ Developer can run workflow interactively via `run_interactive()`  
✅ HITL prompts appear in terminal (Rich panels)  
✅ Multiple HITL pauses handled correctly  
✅ Session state managed automatically  
✅ Works with all 7 workflow patterns  
✅ Error handling marks sessions as FAILED  
✅ Type-safe with full IDE autocomplete

### Non-Functional Requirements

✅ Test coverage ≥85% for API module  
✅ Zero breaking changes to existing CLI  
✅ Zero changes to existing executors  
✅ Documentation complete with examples  
✅ Manual testing passes on all patterns  
✅ Performance: <5% overhead vs CLI

### Developer Experience

✅ **Time to first interactive workflow:** <5 minutes  
✅ **Lines of code for basic usage:** <5 lines  
✅ **API intuitive:** No manual session management needed  
✅ **Error messages helpful:** Clear guidance on failures

---

## Risks & Mitigations

### Risk 1: Async Event Loop Conflicts

**Risk:** Calling `asyncio.run()` in sync wrapper when already in async context  
**Likelihood:** Medium  
**Impact:** High (runtime error)  
**Mitigation:** Provide both sync and async methods; document when to use each

### Risk 2: Session ID Collisions

**Risk:** Multiple concurrent workflows create same session ID  
**Likelihood:** Low  
**Impact:** Medium (data corruption)  
**Mitigation:** Use timestamp + random suffix for unique IDs

### Risk 3: Console Output Interference

**Risk:** Executor console.print() interferes with HITL prompts  
**Likelihood:** Medium  
**Impact:** Low (cosmetic)  
**Mitigation:** Acceptable for MVP; add event system in Phase 3

### Risk 4: Infinite HITL Loop

**Risk:** Workflow bug causes endless HITL pauses  
**Likelihood:** Low  
**Impact:** High (hangs forever)  
**Mitigation:** Add max_iterations safety limit (100 iterations)

### Risk 5: KeyboardInterrupt Handling

**Risk:** Ctrl+C during HITL prompt corrupts session  
**Likelihood:** Medium  
**Impact:** Medium (lost progress)  
**Mitigation:** Try/except KeyboardInterrupt, mark session as PAUSED

---

## Post-MVP Enhancements (Week 2-3)

### Week 2: Fluent Builder API

- `Workflow.create(name)` → `FluentBuilder`
- `ChainBuilder`, `WorkflowBuilder`, etc.
- Programmatic workflow construction (no YAML)

### Week 3: Production Features

- Event system (`@workflow.on("step_complete")`)
- Session management API (`SessionManager`)
- Async-first execution with context managers
- FastAPI integration (auto-generate REST endpoints)

---

## Appendix: File Checklist

### New Files to Create

- [ ] `src/strands_cli/api/__init__.py`
- [ ] `src/strands_cli/api/execution.py`
- [ ] `src/strands_cli/api/handlers.py`
- [ ] `tests/test_api_workflow.py`
- [ ] `tests/test_interactive_hitl.py`
- [ ] `examples/api/01_interactive_hitl.py`
- [ ] `docs/API.md`

### Files to Modify

- [ ] `src/strands_cli/__init__.py` - Add `Workflow` export
- [ ] `CHANGELOG.md` - Add v0.14.0-alpha notes

### Files to Review (No Changes)

- ✅ `src/strands_cli/exec/chain.py` - Verify signature compatibility
- ✅ `src/strands_cli/exec/workflow.py` - Verify signature compatibility
- ✅ `src/strands_cli/session/state.py` - Understand SessionState
- ✅ `src/strands_cli/session/repository.py` - Understand FileSessionRepository
- ✅ `src/strands_cli/types.py` - Understand HITLState, RunResult

---

## Daily Standup Questions

### Day 1-2 Standup
- [ ] API module structure created?
- [ ] `Workflow` class implements `from_file()`?
- [ ] `WorkflowExecutor` implements HITL loop?
- [ ] `terminal_hitl_handler()` displays Rich panels?
- [ ] Blockers or questions?

### Day 3-4 Standup
- [ ] HITL loop handles multiple pauses?
- [ ] Session state managed correctly?
- [ ] Tested with all 7 patterns?
- [ ] Error handling complete?
- [ ] Blockers or questions?

### Day 5 Standup
- [ ] Unit tests written and passing?
- [ ] Integration tests complete?
- [ ] Example scripts work?
- [ ] Documentation finished?
- [ ] Ready for PR review?

---

## Definition of Done

### Code Complete
- [ ] All new files created with full implementation
- [ ] Type hints complete (mypy strict passes)
- [ ] Docstrings on all public methods
- [ ] Error handling covers all edge cases

### Testing Complete
- [ ] Unit tests ≥85% coverage
- [ ] Integration tests pass
- [ ] Manual testing checklist complete
- [ ] CI pipeline passes (`.\scripts\dev.ps1 ci`)

### Documentation Complete
- [ ] `docs/API.md` written with examples
- [ ] Example script documented
- [ ] `CHANGELOG.md` updated
- [ ] Inline code comments for complex logic

### Quality Gates
- [ ] Lint passes: `.\scripts\dev.ps1 lint`
- [ ] Type check passes: `.\scripts\dev.ps1 typecheck`
- [ ] Tests pass: `.\scripts\dev.ps1 test-cov`
- [ ] No breaking changes to existing code

---

**End of Week 1 Implementation Plan**

# Strands Python API — Developer-Ready PRD

**Created:** 2025-11-11  
**Owner:** Thomas Rohde  
**Target Version:** v0.14.0  
**Status:** 📋 Ready for Implementation  
**Complexity:** Medium-High  
**Duration:** 3 weeks (MVP = 1 week, Phases 2-3 = 2 weeks)

---

## Executive Summary

Transform **strands-cli** from a CLI-first tool into a **first-class Python library** with a compact, concise API surface optimized for developer experience. Enable developers to build full applications that orchestrate agentic workflows programmatically, with special focus on **interactive HITL (Human-in-the-Loop) workflows** that can run as standalone Python programs rather than requiring successive CLI commands.

### Vision

```python
# Simple interactive HITL workflow in pure Python
from strands import Workflow, Agent, ChainPattern

workflow = (
    Workflow("research-review")
    .with_runtime("openai", "gpt-4o-mini")
    .add_agent(Agent("researcher").with_prompt("Research {{topic}}"))
    .add_agent(Agent("analyst").with_prompt("Analyze findings"))
    .with_pattern(
        ChainPattern()
        .step("researcher", "Research: {{topic}}")
        .hitl("Review research?", show="{{steps[0].response}}")
        .step("analyst", "Analyze with approval: {{hitl_response}}")
    )
)

# Run interactively - prompts user in terminal
result = workflow.run_interactive(topic="AI agents")
print(f"Final analysis: {result.last_response}")
```

### Key Outcomes

1. **MVP (Week 1)**: Interactive HITL workflows runnable as Python programs
2. **Phase 2 (Week 2)**: Complete programmatic control over all 7 patterns
3. **Phase 3 (Week 3)**: Production features (async, events, web integration)

**Design Principles:**
- **Compact API surface**: Minimal classes, fluent builders, sensible defaults
- **HITL-first for MVP**: Enable interactive terminal workflows immediately
- **Gradual exposure**: Simple cases simple, complex cases possible
- **Zero breaking changes**: Existing CLI and YAML workflows unaffected
- **Type-safe**: Full type hints for excellent IDE support

---

## Current State Analysis

### Architecture Overview

```
Current Flow (CLI-centric):
CLI (__main__.py) 
  → parse args
  → load_spec(yaml) 
  → validate_spec()
  → check_capability()
  → asyncio.run(run_chain/run_workflow/etc.)
  → write_artifacts()
  → exit with code

Issues for API Usage:
1. No clean entry point - must shell out or mock CLI args
2. HITL requires restart (exit code 19) + resume command
3. Session management tied to filesystem paths
4. Executors tightly coupled to console.print()
5. No event/callback hooks for integration
```

### Existing Assets (Reusable)

✅ **Well-structured executor layer**:
- All executors are async (`run_chain`, `run_workflow`, etc.)
- Accept `Spec` + `variables` + optional `session_state`
- Return `RunResult` with structured output

✅ **Strong type system**:
- Pydantic v2 models (`Spec`, `Agent`, `PatternConfig`, etc.)
- Schema validation with JSON Schema Draft 2020-12
- Type-safe throughout codebase

✅ **Session infrastructure**:
- `SessionState`, `SessionMetadata`, `SessionStatus`
- `FileSessionRepository` with async interface
- Resume logic in `session/resume.py`

✅ **Template system**:
- Jinja2 renderer with security constraints
- Variable interpolation
- Context building for steps/tasks/branches

### Gaps for API

❌ No programmatic workflow builder (must write YAML)  
❌ No interactive HITL handler (only exit/resume cycle)  
❌ No event system for callbacks  
❌ No sync wrappers for simple use cases  
❌ CLI-coupled error reporting (Rich console output)

---

## MVP (Week 1): Interactive HITL Workflows

**Goal:** Enable developers to create HITL-focused workflows that run as interactive Python programs, prompting for user input in the terminal instead of requiring CLI restart cycles.

### Target Use Case

```python
# Research workflow with human review gates
from strands import Workflow

workflow = Workflow.from_file("research-approval.yaml")
result = workflow.run_interactive(topic="quantum computing")

# OR build in Python:
workflow = (
    Workflow("research")
    .runtime("openai", "gpt-4o-mini")
    .agent("researcher", prompt="Research {{topic}}")
    .chain()
        .step("researcher", "Research: {{topic}}")
        .hitl("Approve findings?")
        .step("analyst", "Analyze: {{steps[0].response}}")
)

result = workflow.run_interactive(topic="AI safety")
```

### MVP API Surface

#### 1. Workflow Class (Main Entry Point)

**File:** `src/strands_cli/api/__init__.py`

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
from strands_cli.api.builders import FluentBuilder


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
        self._executor = WorkflowExecutor(spec)
    
    @classmethod
    def from_file(cls, path: str | Path, **variables: Any) -> "Workflow":
        """Load workflow from YAML/JSON file.
        
        Args:
            path: Path to workflow spec file
            **variables: Variable overrides (key=value)
            
        Returns:
            Workflow instance ready to run
            
        Example:
            >>> workflow = Workflow.from_file("workflow.yaml", topic="AI")
            >>> result = workflow.run_interactive()
        """
        spec = load_spec(str(path), variables)
        return cls(spec)
    
    @classmethod
    def create(cls, name: str) -> FluentBuilder:
        """Create workflow using fluent builder.
        
        Args:
            name: Workflow name
            
        Returns:
            FluentBuilder for programmatic workflow construction
            
        Example:
            >>> workflow = (
            ...     Workflow.create("research")
            ...     .runtime("openai", "gpt-4o-mini")
            ...     .agent("researcher", prompt="Research {{topic}}")
            ...     .chain()
            ...         .step("researcher", "Research: {{topic}}")
            ...         .hitl("Review?")
            ... )
            >>> result = workflow.run_interactive(topic="AI")
        """
        return FluentBuilder(name)
    
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
        return asyncio.run(self._executor.run_interactive(variables))
    
    def run(self, **variables: Any) -> RunResult:
        """Execute workflow (non-interactive, uses session persistence).
        
        Standard execution mode - saves session and exits at HITL steps.
        Use for production workflows or when integrating with external
        approval systems.
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details (may indicate HITL pause)
            
        Raises:
            HITLPauseRequired: If HITL step reached and interactive=False
        """
        import asyncio
        return asyncio.run(self._executor.run(variables))
    
    async def run_async(self, **variables: Any) -> RunResult:
        """Execute workflow asynchronously.
        
        For high-performance applications that need async control flow.
        
        Args:
            **variables: Runtime variable overrides
            
        Returns:
            RunResult with execution details
        """
        return await self._executor.run(variables)
```

#### 2. WorkflowExecutor (Execution Engine)

**File:** `src/strands_cli/api/execution.py`

```python
"""Workflow execution engine with HITL support."""

import asyncio
from typing import Any

from rich.console import Console
from rich.prompt import Prompt

from strands_cli.types import Spec, RunResult, PatternType
from strands_cli.exec.chain import run_chain
from strands_cli.exec.workflow import run_workflow
# ... other pattern executors


class HITLInteractiveHandler:
    """Interactive HITL handler for terminal prompts."""
    
    def __init__(self):
        self.console = Console()
    
    def prompt_user(self, prompt: str, context: str | None = None) -> str:
        """Display HITL prompt and get user response.
        
        Args:
            prompt: Question/request for user
            context: Context to display (previous step output, etc.)
            
        Returns:
            User's response as string
        """
        self.console.print()
        self.console.print(f"[bold yellow]🤝 HUMAN INPUT REQUIRED[/bold yellow]")
        self.console.print(f"[cyan]{prompt}[/cyan]")
        
        if context:
            self.console.print()
            self.console.print("[dim]Context:[/dim]")
            self.console.print(context[:500])  # Truncate long context
            if len(context) > 500:
                self.console.print("[dim]...(truncated)[/dim]")
        
        self.console.print()
        response = Prompt.ask("Your response")
        return response


class WorkflowExecutor:
    """Executes workflows with optional interactive HITL."""
    
    def __init__(self, spec: Spec):
        self.spec = spec
    
    async def run_interactive(self, variables: dict[str, Any]) -> RunResult:
        """Run workflow with interactive HITL prompts.
        
        Injects HITLInteractiveHandler that prompts in terminal
        instead of pausing execution.
        """
        handler = HITLInteractiveHandler()
        return await self._execute(variables, hitl_handler=handler)
    
    async def run(self, variables: dict[str, Any]) -> RunResult:
        """Run workflow without interactive mode (session-based HITL)."""
        return await self._execute(variables, hitl_handler=None)
    
    async def _execute(
        self,
        variables: dict[str, Any],
        hitl_handler: HITLInteractiveHandler | None = None
    ) -> RunResult:
        """Route to appropriate executor based on pattern type."""
        pattern = self.spec.pattern.type
        
        # Inject hitl_handler into executor context
        # Executors check for handler and call it instead of pausing
        
        if pattern == PatternType.CHAIN:
            return await run_chain(
                self.spec,
                variables,
                hitl_handler=hitl_handler  # Pass to executor
            )
        elif pattern == PatternType.WORKFLOW:
            return await run_workflow(
                self.spec,
                variables,
                hitl_handler=hitl_handler
            )
        # ... other patterns
        else:
            raise ValueError(f"Unsupported pattern: {pattern}")
```

#### 3. Minimal Executor Changes

**File:** `src/strands_cli/exec/chain.py` (modifications)

```python
async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_handler: Any | None = None,  # NEW: Interactive HITL handler
) -> RunResult:
    """Execute chain with optional interactive HITL."""
    
    # ... existing logic ...
    
    for step_index, step in enumerate(steps):
        if is_hitl_step(step):
            # Build context for display
            context = render_template(step.context_display, context_vars)
            
            if hitl_handler:
                # Interactive mode: prompt user directly
                response = hitl_handler.prompt_user(step.prompt, context)
                # Continue execution with response
                # ... inject response into context
            else:
                # Session mode: save and pause
                # ... existing HITL pause logic
                return RunResult(exit_code=EX_HITL_PAUSE, ...)
        
        # ... rest of step execution
```

### MVP Deliverables Checklist

- [ ] `Workflow` class with `from_file()` and `run_interactive()`
- [ ] `WorkflowExecutor` with HITL handler injection
- [ ] `HITLInteractiveHandler` for terminal prompts
- [ ] Executor modifications to accept `hitl_handler` parameter
- [ ] Unit tests for interactive HITL flow
- [ ] Integration test: chain + workflow patterns with HITL
- [ ] Example: `examples/api/interactive_hitl.py`
- [ ] Documentation: `docs/API.md` MVP section

### Success Criteria (MVP)

✅ Developer can create HITL workflow from YAML and run interactively  
✅ HITL prompts appear in terminal, no exit/resume cycle  
✅ Works with chain and workflow patterns  
✅ Type-safe: IDE autocomplete for `Workflow` methods  
✅ Example Python script demonstrates interactive HITL  
✅ Zero changes to existing CLI behavior

---

## Phase 2 (Week 2): Complete Programmatic Control

**Goal:** Enable full workflow construction in Python (no YAML required) and support all 7 workflow patterns programmatically.

### Fluent Builder API

```python
from strands import Workflow, Agent

# Build complex workflow in Python
workflow = (
    Workflow.create("research-pipeline")
    .runtime("openai", "gpt-4o-mini")
    .agent("researcher", 
           prompt="Research {{topic}} thoroughly",
           tools=["http_request", "file_read"])
    .agent("analyst", 
           prompt="Analyze findings and identify trends")
    .agent("writer",
           prompt="Write executive summary")
    .chain()
        .step("researcher", "Research: {{topic}}")
        .hitl("Review research quality", show="{{steps[0].response}}")
        .step("analyst", "Analyze: {{steps[0].response}}")
        .hitl("Approve analysis?", show="{{steps[2].response}}")
        .step("writer", "Write report: {{steps[2].response}}")
    .artifact("report.md", "{{last_response}}")
)

result = workflow.run_interactive(topic="quantum computing")
```

### Builder API Classes

#### FluentBuilder

**File:** `src/strands_cli/api/builders.py`

```python
"""Fluent API for programmatic workflow construction."""

from typing import Any
from strands_cli.types import Spec, AgentConfig, Runtime
from strands_cli.api import Workflow


class FluentBuilder:
    """Top-level builder for workflows."""
    
    def __init__(self, name: str):
        self.name = name
        self._runtime: dict[str, Any] = {}
        self._agents: dict[str, AgentConfig] = {}
        self._pattern = None
        self._artifacts: list[dict[str, str]] = []
    
    def runtime(
        self,
        provider: str,
        model: str | None = None,
        **kwargs: Any
    ) -> "FluentBuilder":
        """Configure runtime provider.
        
        Args:
            provider: bedrock, ollama, openai
            model: Model ID (e.g., "gpt-4o-mini")
            **kwargs: Additional runtime config (region, host, etc.)
            
        Example:
            >>> builder.runtime("openai", "gpt-4o-mini")
            >>> builder.runtime("bedrock", region="us-east-1")
        """
        self._runtime = {
            "provider": provider,
            "model_id": model,
            **kwargs
        }
        return self
    
    def agent(
        self,
        id: str,
        prompt: str,
        tools: list[str] | None = None,
        **kwargs: Any
    ) -> "FluentBuilder":
        """Add agent to workflow.
        
        Args:
            id: Unique agent identifier
            prompt: System prompt (supports {{variables}})
            tools: List of tool IDs
            **kwargs: Additional agent config
            
        Example:
            >>> builder.agent("researcher", 
            ...               prompt="Research {{topic}}",
            ...               tools=["http_request"])
        """
        self._agents[id] = AgentConfig(
            prompt=prompt,
            tools=tools,
            **kwargs
        )
        return self
    
    def chain(self) -> "ChainBuilder":
        """Start chain pattern builder."""
        return ChainBuilder(self)
    
    def workflow(self) -> "WorkflowBuilder":
        """Start workflow (DAG) pattern builder."""
        return WorkflowBuilder(self)
    
    def parallel(self) -> "ParallelBuilder":
        """Start parallel pattern builder."""
        return ParallelBuilder(self)
    
    def graph(self) -> "GraphBuilder":
        """Start graph pattern builder."""
        return GraphBuilder(self)
    
    def artifact(self, path: str, template: str) -> "FluentBuilder":
        """Add output artifact.
        
        Args:
            path: Output file path
            template: Jinja2 template (e.g., "{{last_response}}")
            
        Example:
            >>> builder.artifact("report.md", "{{steps[2].response}}")
        """
        self._artifacts.append({"path": path, "from": template})
        return self
    
    def build(self) -> Workflow:
        """Build final Workflow instance.
        
        Returns:
            Workflow ready to execute
        """
        spec = Spec(
            version=0,
            name=self.name,
            runtime=Runtime(**self._runtime),
            agents=self._agents,
            pattern=self._pattern,
            outputs={"artifacts": self._artifacts} if self._artifacts else None
        )
        return Workflow(spec)


class ChainBuilder:
    """Builder for chain pattern."""
    
    def __init__(self, parent: FluentBuilder):
        self.parent = parent
        self.steps: list[dict[str, Any]] = []
    
    def step(self, agent: str, input: str) -> "ChainBuilder":
        """Add agent step.
        
        Args:
            agent: Agent ID
            input: Input prompt template
            
        Example:
            >>> chain.step("researcher", "Research: {{topic}}")
        """
        self.steps.append({"agent": agent, "input": input})
        return self
    
    def hitl(
        self,
        prompt: str,
        show: str | None = None,
        default: str | None = None
    ) -> "ChainBuilder":
        """Add HITL (human-in-the-loop) step.
        
        Args:
            prompt: Question for user
            show: Context to display (template)
            default: Default response if user presses Enter
            
        Example:
            >>> chain.hitl("Approve?", show="{{steps[0].response}}")
        """
        step = {
            "type": "hitl",
            "prompt": prompt,
        }
        if show:
            step["context_display"] = show
        if default:
            step["default"] = default
        
        self.steps.append(step)
        return self
    
    def build(self) -> Workflow:
        """Build final workflow."""
        from strands_cli.types import PatternConfig, ChainPatternConfig
        
        self.parent._pattern = PatternConfig(
            type="chain",
            config=ChainPatternConfig(steps=self.steps)
        )
        return self.parent.build()


class WorkflowBuilder:
    """Builder for workflow (DAG) pattern."""
    
    def __init__(self, parent: FluentBuilder):
        self.parent = parent
        self.tasks: list[dict[str, Any]] = []
    
    def task(
        self,
        id: str,
        agent: str,
        input: str,
        depends_on: list[str] | None = None
    ) -> "WorkflowBuilder":
        """Add task to DAG.
        
        Args:
            id: Unique task identifier
            agent: Agent ID to execute task
            input: Input template
            depends_on: List of task IDs this task depends on
            
        Example:
            >>> workflow.task("research", "researcher", "Research {{topic}}")
            >>> workflow.task("analyze", "analyst", 
            ...               "Analyze {{tasks.research.response}}",
            ...               depends_on=["research"])
        """
        task = {
            "id": id,
            "agent": agent,
            "input": input,
        }
        if depends_on:
            task["dependencies"] = depends_on
        
        self.tasks.append(task)
        return self
    
    def build(self) -> Workflow:
        """Build final workflow."""
        from strands_cli.types import PatternConfig, WorkflowPatternConfig
        
        self.parent._pattern = PatternConfig(
            type="workflow",
            config=WorkflowPatternConfig(tasks=self.tasks)
        )
        return self.parent.build()


# Similar builders for ParallelBuilder, GraphBuilder, etc.
```

### Pattern Support Checklist

- [ ] `ChainBuilder` with `.step()` and `.hitl()`
- [ ] `WorkflowBuilder` with `.task()` and dependencies
- [ ] `ParallelBuilder` with `.branch()` and `.reduce()`
- [ ] `GraphBuilder` with `.node()` and `.edge()`
- [ ] `RoutingBuilder` with `.route()` and conditions
- [ ] `EvaluatorOptimizerBuilder` with iterative logic
- [ ] `OrchestratorBuilder` with orchestrator/workers
- [ ] Unit tests for each builder
- [ ] Integration tests: built workflows == YAML equivalents
- [ ] Examples: One Python script per pattern
- [ ] Documentation: Builder API reference

### Success Criteria (Phase 2)

✅ All 7 patterns constructible via fluent API  
✅ Builder API is type-safe (Pylance/mypy clean)  
✅ Built workflows validate same as YAML specs  
✅ Example scripts demonstrate each pattern  
✅ Documentation covers all builders with examples  
✅ No YAML required for any workflow pattern

---

## Phase 3 (Week 3): Production Features

**Goal:** Add async-first execution, event system, session management API, and web framework integrations.

### Event System

```python
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

# Subscribe to events
@workflow.on("step_complete")
def on_step(event):
    print(f"Step {event.step_index} done: {event.duration}s")

@workflow.on("hitl_pause")
def on_hitl(event):
    # Send Slack notification
    slack.send(f"Approval needed: {event.prompt}")

result = workflow.run_interactive(topic="AI")
```

### Session Management API

```python
from strands import SessionManager

manager = SessionManager()

# List paused workflows
sessions = manager.list(status="paused")
for session in sessions:
    print(f"{session.workflow_name}: {session.updated_at}")

# Resume with approval
result = manager.resume(sessions[0].id, hitl_response="approved")
```

### Async-First Execution

```python
import asyncio
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

# Async execution for high performance
async def main():
    async with workflow.async_executor() as executor:
        result = await executor.run(topic="AI")
        print(f"Completed in {result.duration}s")

asyncio.run(main())
```

### Web Framework Integration

```python
from fastapi import FastAPI
from strands import Workflow
from strands.integrations.fastapi import create_workflow_router

app = FastAPI()
workflow = Workflow.from_file("workflow.yaml")

# Auto-generated REST endpoints
router = create_workflow_router(workflow, prefix="/workflows")
app.include_router(router)

# Endpoints:
# POST /workflows/execute
# GET /workflows/sessions
# POST /workflows/sessions/{id}/resume
```

### Phase 3 Deliverables (Directional)

**Event System:**
- Event types: `workflow_start`, `step_complete`, `hitl_pause`, `error`, `complete`
- Decorator-based subscription: `@workflow.on("event_type")`
- Async callback support
- Event data models with full context

**Session Management:**
- `SessionManager.list()` with filtering
- `SessionManager.get(id)` for state inspection
- `SessionManager.resume(id, hitl_response=...)` for programmatic resume
- `SessionManager.cleanup()` for expired sessions

**Async API:**
- `workflow.async_executor()` context manager
- Proper resource cleanup (HTTP clients, file handles)
- Streaming response support (token-by-token)

**Integrations:**
- FastAPI router generator
- Flask blueprint generator
- Webhook handlers for external approval systems
- Slack/Teams notification helpers

### Success Criteria (Phase 3)

✅ Event system with decorator-based subscriptions  
✅ SessionManager API matches CLI session commands  
✅ Async executor with proper cleanup  
✅ FastAPI integration auto-generates REST API  
✅ Webhook integration example (Slack approval)  
✅ Performance: async mode <10% overhead vs CLI  
✅ Documentation: production deployment guide

---

## Implementation Roadmap

### Week 1: MVP (Interactive HITL)

**Day 1-2: Core API Layer**
- [ ] Create `src/strands_cli/api/__init__.py`
- [ ] Implement `Workflow` class with `from_file()` and `run_interactive()`
- [ ] Implement `WorkflowExecutor` with HITL handler injection
- [ ] Implement `HITLInteractiveHandler` with Rich prompts

**Day 3: Executor Integration**
- [ ] Modify `run_chain()` to accept `hitl_handler` parameter
- [ ] Modify `run_workflow()` to accept `hitl_handler`
- [ ] Test HITL handler invocation in executors

**Day 4-5: Testing & Documentation**
- [ ] Unit tests: `Workflow` class, `WorkflowExecutor`
- [ ] Integration test: End-to-end interactive HITL
- [ ] Example: `examples/api/interactive_hitl.py`
- [ ] Documentation: `docs/API.md` MVP section

### Week 2: Complete Programmatic Control

**Day 1-2: Builder Foundation**
- [ ] Implement `FluentBuilder` base class
- [ ] Implement `ChainBuilder` with `.step()` and `.hitl()`
- [ ] Implement `WorkflowBuilder` with `.task()`
- [ ] Validate built specs match YAML equivalents

**Day 3-4: Remaining Patterns**
- [ ] Implement `ParallelBuilder`
- [ ] Implement `GraphBuilder`
- [ ] Implement `RoutingBuilder`
- [ ] Implement `EvaluatorOptimizerBuilder`, `OrchestratorBuilder`

**Day 5: Testing & Examples**
- [ ] Unit tests for all builders
- [ ] Integration tests: built == YAML
- [ ] Examples: One script per pattern
- [ ] Documentation: Builder API reference

### Week 3: Production Features

**Day 1-2: Event System**
- [ ] Event data models
- [ ] Event bus implementation
- [ ] Decorator-based subscriptions
- [ ] Inject event bus into executors

**Day 2-3: Session Management API**
- [ ] `SessionManager` class
- [ ] `.list()`, `.get()`, `.resume()`, `.cleanup()` methods
- [ ] Integration with existing `FileSessionRepository`

**Day 4: Async & Integrations**
- [ ] Async executor context manager
- [ ] FastAPI router generator
- [ ] Webhook handler examples

**Day 5: Documentation & Release**
- [ ] API reference documentation
- [ ] Production deployment guide
- [ ] Migration guide from CLI to API
- [ ] Release notes for v0.14.0

---

## Testing Strategy

### Unit Tests

**API Layer:**
- `Workflow.from_file()` loads specs correctly
- `Workflow.run_interactive()` invokes handler
- `HITLInteractiveHandler.prompt_user()` returns response
- `WorkflowExecutor._execute()` routes to correct pattern

**Builders:**
- `ChainBuilder` generates valid `ChainPatternConfig`
- `WorkflowBuilder` validates dependencies
- Built specs pass schema validation
- Built specs == YAML equivalents (golden tests)

**Event System:**
- Event emission reaches subscribers
- Async callbacks execute correctly
- Event data contains expected fields

### Integration Tests

**End-to-End Workflows:**
- Chain + HITL (interactive mode)
- Workflow + HITL (interactive mode)
- All 7 patterns via builder API
- Session save/resume via API
- Event callbacks triggered at expected times

**Mocking:**
- Mock LLM responses for deterministic tests
- Mock HITL prompts (inject test responses)
- Mock file I/O for artifact tests

### Performance Tests

**Benchmarks:**
- API overhead vs CLI (<5% acceptable)
- Builder overhead vs YAML parsing (<10ms)
- Async executor vs sync wrapper (<10% overhead)

---

## API Design Principles (DevEx Focus)

### 1. Compact Surface Area

**Good:**
```python
from strands import Workflow
workflow = Workflow.from_file("spec.yaml")
result = workflow.run_interactive(topic="AI")
```

**Avoid:**
```python
from strands.api.workflow import WorkflowClient
from strands.api.execution import ExecutionEngine
from strands.api.config import RuntimeConfiguration

client = WorkflowClient()
config = RuntimeConfiguration(provider="openai", model="gpt-4o")
engine = ExecutionEngine(client, config)
result = engine.execute_interactive(spec_path="spec.yaml", vars={"topic": "AI"})
```

### 2. Sensible Defaults

**Good:**
```python
workflow.run_interactive()  # Uses defaults from spec
```

**Avoid:**
```python
workflow.run_interactive(
    save_session=True,
    interactive=True,
    verbose=False,
    trace=False,
    force=False,
    # ... many required args
)
```

### 3. Progressive Disclosure

**Simple case simple:**
```python
Workflow.from_file("spec.yaml").run_interactive(topic="AI")
```

**Complex case possible:**
```python
workflow = (
    Workflow.create("advanced")
    .runtime("openai", "gpt-4o", temperature=0.7)
    .agent("researcher", prompt="...", tools=[...])
    # ... complex configuration
)
result = workflow.run_interactive()
```

### 4. Type-Safe and IDE-Friendly

- Full type hints on all public APIs
- Docstrings with examples
- Type stubs for autocomplete
- Pylance/Pyright clean with strict mode

### 5. Pythonic Conventions

- Use `**kwargs` for variable overrides
- Context managers for resource cleanup
- Decorator-based event subscriptions
- Fluent interfaces return `self` for chaining

---

## Migration & Compatibility

### Backward Compatibility

✅ **No breaking changes to CLI**  
✅ **No breaking changes to YAML specs**  
✅ **Existing executors work with API** (optional `hitl_handler` param)  
✅ **Session files remain compatible**

### CLI Refactoring (Optional Future)

```python
# CLI becomes thin wrapper over API
@app.command()
def run(spec_file: str, ...):
    workflow = Workflow.from_file(spec_file, **parse_variables(var))
    
    if interactive:
        result = workflow.run_interactive()
    else:
        result = workflow.run()
    
    # Handle result...
```

---

## Documentation Structure

### API Reference

**Location:** `docs/API.md`

```markdown
# Strands Python API

## Quickstart

```python
from strands import Workflow
workflow = Workflow.from_file("workflow.yaml")
result = workflow.run_interactive(topic="AI")
```

## Core Classes

### Workflow
Main entry point for creating and executing workflows.

#### Methods
- `from_file(path, **variables) -> Workflow`
- `create(name) -> FluentBuilder`
- `run_interactive(**variables) -> RunResult`
- `run(**variables) -> RunResult`
- `run_async(**variables) -> RunResult` (async)

### FluentBuilder
Programmatic workflow construction.

#### Methods
- `runtime(provider, model, **kwargs) -> self`
- `agent(id, prompt, tools=[]) -> self`
- `chain() -> ChainBuilder`
- `workflow() -> WorkflowBuilder`
...
```

### Examples Repository

**Location:** `examples/api/`

```
examples/api/
├── 01_interactive_hitl.py
├── 02_chain_builder.py
├── 03_workflow_dag.py
├── 04_parallel_branches.py
├── 05_graph_pattern.py
├── 06_event_callbacks.py
├── 07_session_management.py
├── 08_async_execution.py
└── 09_fastapi_integration.py
```

### Tutorial (Jupyter Notebook)

**Location:** `examples/api/tutorial.ipynb`

Interactive walkthrough:
1. Load workflow from YAML
2. Run interactively
3. Build workflow in Python
4. Add HITL steps
5. Subscribe to events
6. Manage sessions
7. Deploy as web service

---

## Success Metrics

### Developer Experience

✅ **Time to first interactive workflow:** <5 minutes  
✅ **Lines of code for HITL workflow:** <15 lines  
✅ **Type safety:** 100% of public API type-hinted  
✅ **IDE autocomplete:** Works in VS Code, PyCharm

### Technical Quality

✅ **Test coverage:** ≥85% for API layer  
✅ **Performance:** <10% overhead vs CLI  
✅ **Zero breaking changes:** Existing code unaffected  
✅ **Documentation:** Complete API reference + 9 examples

### Adoption (Post-Release)

✅ **Internal usage:** ≥3 HITL workflows as Python apps  
✅ **Community feedback:** Positive DX feedback  
✅ **GitHub stars:** +20% increase within 1 month  
✅ **Bug reports:** <5 API-specific bugs in first month

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Executor coupling to CLI | Medium | Medium | Inject handlers, avoid console.print() in executors |
| Builder API complexity | Low | High | Keep builders minimal, use sensible defaults |
| Session compatibility | Low | High | Reuse existing SessionRepository, no schema changes |
| HITL handler injection | Medium | Medium | Optional parameter, graceful fallback |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Builder API scope creep | High | Medium | MVP = chain + workflow only, add patterns in Phase 2 |
| Testing bottleneck | Medium | Low | Parallel test development, reuse existing executor tests |
| Documentation lag | Medium | Medium | Write docs alongside code, not after |

---

## Future Enhancements (Post-v0.14.0)

### Streaming API

```python
async for chunk in workflow.stream(topic="AI"):
    if chunk.type == "token":
        print(chunk.content, end="", flush=True)
    elif chunk.type == "step_complete":
        print(f"\n✓ Step {chunk.step} done")
```

### GraphQL API

```python
from strands.integrations.graphql import create_schema
schema = create_schema(workflow)
# Query workflow state, subscribe to events
```

### Workflow Marketplace

```python
from strands import WorkflowMarketplace
marketplace = WorkflowMarketplace()
workflow = marketplace.download("research-pipeline")
result = workflow.run_interactive(topic="AI")
```

### Multi-Agent Orchestration

```python
from strands import AgentTeam
team = AgentTeam()
    .add_agent("researcher", role="researcher")
    .add_agent("analyst", role="analyst")
    .with_collaboration_pattern("round-robin")

result = team.execute(task="Research and analyze AI trends")
```

---

## Appendix: Code Examples

### Example 1: Interactive HITL Research Workflow

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
    # Load workflow with HITL steps
    workflow = Workflow.from_file("../chain-hitl-approval-demo.yaml")
    
    # Run interactively - prompts user in terminal for HITL responses
    result = workflow.run_interactive(
        topic="quantum computing applications in cryptography"
    )
    
    # Access results
    print("\n" + "="*60)
    print("WORKFLOW COMPLETED")
    print("="*60)
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Success: {result.success}")
    print(f"\nFinal Analysis:\n{result.last_response}")
    
    if result.artifacts_written:
        print(f"\nArtifacts written:")
        for artifact in result.artifacts_written:
            print(f"  - {artifact}")

if __name__ == "__main__":
    main()
```

### Example 2: Build Workflow Programmatically

**File:** `examples/api/02_chain_builder.py`

```python
#!/usr/bin/env python3
"""Build workflow using fluent API (no YAML required)."""

from strands import Workflow

def main():
    # Build workflow in Python
    workflow = (
        Workflow.create("research-review")
        .runtime("openai", "gpt-4o-mini")
        .agent("researcher", 
               prompt="Research {{topic}} thoroughly. Provide key findings.",
               tools=["http_request"])
        .agent("analyst",
               prompt="Analyze findings and identify trends.")
        .chain()
            .step("researcher", "Research: {{topic}}")
            .hitl("Review research quality and approve for analysis",
                  show="{{steps[0].response}}",
                  default="approved")
            .step("analyst", 
                  "User review: {{hitl_response}}\n\n"
                  "Analyze these findings:\n{{steps[0].response}}")
            .hitl("Approve final analysis?",
                  show="{{steps[2].response}}")
        .artifact("analysis.md", "{{steps[2].response}}")
        .build()
    )
    
    # Execute
    result = workflow.run_interactive(
        topic="recent advances in large language models"
    )
    
    print(f"\n✓ Workflow completed in {result.duration_seconds:.2f}s")
    print(f"Artifacts: {result.artifacts_written}")

if __name__ == "__main__":
    main()
```

### Example 3: Event-Driven Workflow

**File:** `examples/api/06_event_callbacks.py`

```python
#!/usr/bin/env python3
"""Event-driven workflow with callbacks."""

from strands import Workflow
import structlog

logger = structlog.get_logger()

def main():
    workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
    
    # Track progress
    progress = {"completed_steps": 0}
    
    @workflow.on("step_complete")
    def on_step_complete(event):
        progress["completed_steps"] += 1
        logger.info("step_complete",
                   step=event.step_index,
                   duration=event.duration,
                   preview=event.response[:100])
    
    @workflow.on("hitl_pause")
    def on_hitl(event):
        logger.warning("hitl_pause_requested",
                      prompt=event.prompt,
                      context_preview=event.context[:200])
    
    @workflow.on("workflow_complete")
    def on_complete(event):
        logger.info("workflow_complete",
                   total_steps=progress["completed_steps"],
                   duration=event.duration)
    
    # Run workflow
    result = workflow.run_interactive(topic="AI safety")
    
    print(f"\nCompleted {progress['completed_steps']} steps")

if __name__ == "__main__":
    main()
```

---

**End of PRD**

# Strands CLI: Human-in-the-Loop (HITL) Implementation Plan

**Created:** 2025-11-10
**Owner:** Thomas Rohde
**Target Version:** v0.3.0
**Status:** 📋 Planning
**Complexity:** Medium
**Duration:** 3 weeks (across 3 phases)
**Dependencies:** Phase 2 of DURABLE.md (Session persistence infrastructure)

---

## Executive Summary

Implement Human-in-the-Loop (HITL) capabilities for Strands CLI workflows, enabling:

1. **User Approval Gates**: Pause workflow execution for human review and approval
2. **Dynamic User Input**: Request additional information from users during execution
3. **Interactive Workflows**: Create workflows that require human decisions at specific points
4. **Quality Control**: Allow users to review and modify agent outputs before proceeding
5. **Debugging Aid**: Manual intervention points for troubleshooting complex workflows

**Key Design Principles:**
- **Schema-native**: HITL implemented as a dedicated workflow step type (`hitl` pattern extension)
- **Durable by default**: Leverages existing session persistence (automatic save/resume)
- **Simple first**: MVP focuses on basic prompt/response, with phased enhancements
- **API-ready**: Works both via CLI and programmatic API
- **Pattern-agnostic**: Supports HITL in all 7 workflow patterns

**Inspiration:** Based on Strands SDK's `handoff_to_user` tool pattern but implemented as first-class workflow primitive.

---

## Architecture Overview

### HITL Execution Model

```
┌─────────────────────────────────────────────────────────────────┐
│                   Workflow Execution                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: Agent executes normally                               │
│  Step 2: Agent executes normally                               │
│  Step 3: HITL step (pause point)                               │
│           ↓                                                     │
│      [Session saved automatically]                              │
│      [Display prompt to user]                                   │
│      [Exit with EX_HITL_PAUSE (19)]                            │
│           ↓                                                     │
│      User reviews context, provides response                    │
│           ↓                                                     │
│      $ strands run --resume <session-id> \                     │
│          --hitl-response "User approval text"                   │
│           ↓                                                     │
│      [Session restored]                                         │
│      [HITL response injected into context]                      │
│           ↓                                                     │
│  Step 4: Agent continues with user input                       │
│  Step 5: Agent executes normally                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### HITL Step Structure

HITL is implemented as a special step type within existing patterns:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research topic: {{ topic }}"

      # HITL pause point
      - type: hitl
        prompt: "Review the research findings. Do you approve proceeding to analysis?"
        context_display: "{{ steps[0].response }}"  # Show user what to review
        default: "approved"  # Optional default response
        timeout_seconds: 3600  # Optional timeout (1 hour)

      - agent: analyst
        input: |
          User decision: {{ hitl_response }}

          Analyze these findings:
          {{ steps[0].response }}
```

### Session State Extensions

```python
# pattern_state for chain with HITL
{
    "current_step": 2,
    "step_history": [
        {"index": 0, "agent": "researcher", "response": "...", "tokens": 1200},
        {"index": 1, "type": "hitl", "prompt": "Review findings...",
         "context_display": "...", "status": "waiting_for_user"}
    ],
    "hitl_state": {
        "active": true,
        "step_index": 1,
        "prompt": "Review the research findings...",
        "context_display": "Research output text...",
        "default_response": "approved",
        "timeout_at": "2025-11-10T15:00:00Z",
        "user_response": null  # Set when user resumes with --hitl-response
    }
}
```

---

## Phase 1: MVP - Basic HITL in Chain Pattern (Week 1)

**Goal:** Implement core HITL functionality for chain pattern with CLI-based user interaction.

**Deliverables:**
- HITL step type in schema
- Chain executor HITL handling (save, pause, resume with response)
- CLI flags: `--hitl-response "text"`
- New exit code: `EX_HITL_PAUSE` (19)
- Unit and integration tests
- Example workflow: `chain-hitl-approval-demo.yaml`

### 1.1 Schema Extensions

**File:** `src/strands_cli/schema/strands-workflow.schema.json`

Add HITL step definition to chain pattern:

```json
{
  "definitions": {
    "ChainStep": {
      "oneOf": [
        {
          "description": "Agent execution step",
          "type": "object",
          "properties": {
            "agent": {"type": "string"},
            "input": {"type": "string"}
          },
          "required": ["agent", "input"]
        },
        {
          "description": "Human-in-the-loop pause point",
          "type": "object",
          "properties": {
            "type": {"const": "hitl"},
            "prompt": {
              "type": "string",
              "description": "Message displayed to user requesting input"
            },
            "context_display": {
              "type": "string",
              "description": "Context to display for user review (supports templates)"
            },
            "default": {
              "type": "string",
              "description": "Default response if user provides empty input"
            },
            "timeout_seconds": {
              "type": "integer",
              "minimum": 0,
              "description": "Time in seconds before HITL expires (0 = no timeout)"
            }
          },
          "required": ["type", "prompt"]
        }
      ]
    }
  }
}
```

### 1.2 Pydantic Models

**File:** `src/strands_cli/types.py`

Add HITL step models:

```python
class HITLStep(BaseModel):
    """Human-in-the-loop pause point.

    Pauses workflow execution to request user input or approval.
    Session is automatically saved and execution exits with EX_HITL_PAUSE.
    User resumes with --hitl-response flag.
    """

    type: str = Field(default="hitl", const=True)
    prompt: str = Field(..., description="Message to display to user")
    context_display: str | None = Field(
        None,
        description="Context to show user (supports templates like {{ steps[0].response }})"
    )
    default: str | None = Field(None, description="Default response if empty")
    timeout_seconds: int = Field(
        default=0,
        ge=0,
        description="Seconds before timeout (0=no timeout)"
    )


class ChainStep(BaseModel):
    """Union type for chain steps: agent or HITL."""

    @model_validator(mode='before')
    def validate_step_type(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate step is either agent or HITL type."""
        if 'type' in values and values['type'] == 'hitl':
            # HITL step
            return HITLStep(**values).model_dump()
        elif 'agent' in values:
            # Agent step (existing)
            return values
        else:
            raise ValueError("Step must have either 'agent' or 'type: hitl'")

    agent: str | None = None
    input: str | None = None
    type: str | None = None
    prompt: str | None = None
    context_display: str | None = None
    default: str | None = None
    timeout_seconds: int | None = None


class HITLState(BaseModel):
    """HITL execution state stored in pattern_state."""

    active: bool = Field(..., description="Whether HITL is currently waiting")
    step_index: int = Field(..., description="Index of HITL step")
    prompt: str = Field(..., description="Prompt displayed to user")
    context_display: str | None = Field(None, description="Context shown to user")
    default_response: str | None = Field(None, description="Default if empty")
    timeout_at: str | None = Field(None, description="ISO 8601 timeout timestamp")
    user_response: str | None = Field(None, description="User's response when resumed")
```

### 1.3 Exit Code Addition

**File:** `src/strands_cli/exit_codes.py`

```python
# Exit codes
EX_OK = 0           # Success
EX_USAGE = 2        # Invalid CLI usage
EX_SCHEMA = 3       # Schema validation failure
EX_RUNTIME = 10     # Runtime execution error
EX_IO = 12          # I/O error (artifacts)
EX_UNSUPPORTED = 18 # Unsupported features
EX_HITL_PAUSE = 19  # Paused for human-in-the-loop input
EX_SESSION = 20     # Session error (load/save failure)
EX_UNKNOWN = 70     # Unexpected error
```

### 1.4 Chain Executor HITL Logic

**File:** `src/strands_cli/exec/chain.py`

Add HITL handling to `run_chain`:

```python
async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,  # NEW: User's response when resuming
) -> RunResult:
    """Execute chain workflow with HITL support.

    Args:
        spec: Workflow specification
        variables: User variables
        session_state: Resume state (if resuming)
        session_repo: Session repository for checkpointing
        hitl_response: User response for resuming from HITL pause
    """

    # Initialize state
    if session_state:
        start_step = session_state.pattern_state["current_step"]
        step_history = session_state.pattern_state["step_history"]
        hitl_state_dict = session_state.pattern_state.get("hitl_state")
        hitl_state = HITLState(**hitl_state_dict) if hitl_state_dict else None
    else:
        start_step = 0
        step_history = []
        hitl_state = None

    # If resuming from HITL pause, validate and inject response
    if hitl_state and hitl_state.active:
        if not hitl_response:
            raise ValueError(
                "Session is waiting for HITL response. "
                "Resume with: strands run --resume <session-id> --hitl-response 'your response'"
            )

        # Inject user response into context
        hitl_state.user_response = hitl_response
        hitl_state.active = False

        # Add HITL response to step history
        step_history.append({
            "index": hitl_state.step_index,
            "type": "hitl",
            "prompt": hitl_state.prompt,
            "user_response": hitl_response
        })

        logger.info("hitl_response_received",
                   step=hitl_state.step_index,
                   response=hitl_response[:100])

        # Continue from next step
        start_step = hitl_state.step_index + 1

    cache = AgentCache()

    try:
        for step_index in range(start_step, len(spec.pattern.config.steps)):
            step_config = spec.pattern.config.steps[step_index]

            # Check if this is a HITL step
            if isinstance(step_config, dict) and step_config.get("type") == "hitl":
                # HITL pause point
                hitl_step = HITLStep(**step_config)

                # Build context for display
                context = _build_step_context(spec, step_index, step_history, variables)

                # Render context_display template
                context_text = ""
                if hitl_step.context_display:
                    context_text = render_template(hitl_step.context_display, context)

                # Calculate timeout
                timeout_at = None
                if hitl_step.timeout_seconds > 0:
                    timeout_dt = datetime.now(UTC) + timedelta(seconds=hitl_step.timeout_seconds)
                    timeout_at = timeout_dt.isoformat()

                # Create HITL state
                new_hitl_state = HITLState(
                    active=True,
                    step_index=step_index,
                    prompt=hitl_step.prompt,
                    context_display=context_text,
                    default_response=hitl_step.default,
                    timeout_at=timeout_at,
                    user_response=None
                )

                # Save session with HITL state
                if session_repo and session_state:
                    session_state.pattern_state["current_step"] = step_index
                    session_state.pattern_state["step_history"] = step_history
                    session_state.pattern_state["hitl_state"] = new_hitl_state.model_dump()
                    session_state.metadata.status = SessionStatus.PAUSED
                    session_state.metadata.updated_at = now_iso8601()

                    await session_repo.save(session_state, spec_content="...")

                    logger.info("hitl_pause_initiated",
                               session_id=session_state.metadata.session_id,
                               step=step_index)

                # Display HITL prompt to user
                console.print()
                console.print(Panel(
                    f"[bold yellow]🤝 HUMAN INPUT REQUIRED[/bold yellow]\n\n"
                    f"{hitl_step.prompt}",
                    border_style="yellow",
                    padding=(1, 2)
                ))

                if context_text:
                    console.print(Panel(
                        f"[bold]Context for Review:[/bold]\n\n{context_text}",
                        border_style="dim",
                        padding=(1, 2)
                    ))

                console.print(f"\n[dim]Session ID: {session_state.metadata.session_id}[/dim]")
                console.print(f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} --hitl-response 'your response'")
                console.print()

                # Exit with HITL pause code
                return RunResult(
                    success=True,
                    message="Workflow paused for human input",
                    exit_code=EX_HITL_PAUSE,
                    pattern_type=PatternType.CHAIN,
                    session_id=session_state.metadata.session_id if session_state else None
                )

            # Regular agent step execution (existing code)
            # ... rest of existing chain logic
```

### 1.5 CLI Extensions

**File:** `src/strands_cli/__main__.py`

Add `--hitl-response` flag:

```python
@app.command()
def run(
    spec_path: Annotated[Path, typer.Argument(...)],
    var: Annotated[list[str] | None, typer.Option(...)] = None,
    resume: Annotated[str | None, typer.Option(help="Resume from session ID")] = None,
    hitl_response: Annotated[str | None, typer.Option(
        help="User response when resuming from HITL pause"
    )] = None,
    save_session: Annotated[bool, typer.Option(...)] = True,
    debug: bool = False,
    verbose: bool = False,
    trace: bool = False,
) -> None:
    """Execute workflow with HITL support."""

    if resume:
        # Resume mode: pass hitl_response to executor
        result = asyncio.run(
            run_resume(resume, hitl_response=hitl_response, debug=debug, verbose=verbose)
        )
        sys.exit(result.exit_code or EX_OK)
    else:
        # Normal execution (hitl_response only valid with --resume)
        if hitl_response:
            console.print("[red]Error:[/red] --hitl-response requires --resume <session-id>")
            sys.exit(EX_USAGE)

        # ... rest of normal execution
```

**File:** `src/strands_cli/session/resume.py`

Update `run_resume` to accept `hitl_response`:

```python
async def run_resume(
    session_id: str,
    hitl_response: str | None = None,  # NEW
    debug: bool = False,
    verbose: bool = False,
) -> RunResult:
    """Resume workflow with optional HITL response."""

    # ... existing session load logic

    # Pass hitl_response to executor
    if pattern_type == PatternType.CHAIN:
        from strands_cli.exec.chain import run_chain
        result = await run_chain(
            spec, variables,
            session_state=state,
            session_repo=repo,
            hitl_response=hitl_response  # NEW
        )
    # ... other patterns
```

### 1.6 Template Context Extension

Add `{{ hitl_response }}` to template context after HITL step:

```python
def _build_step_context(
    spec: Spec,
    current_step: int,
    step_history: list[dict[str, Any]],
    variables: dict[str, str] | None
) -> dict[str, Any]:
    """Build template context including HITL responses."""

    context = {
        "steps": [],
        "last_response": "",
        "variables": variables or {}
    }

    # Build steps array with HITL responses included
    for step_record in step_history:
        if step_record.get("type") == "hitl":
            # HITL step: include user_response
            context["steps"].append({
                "type": "hitl",
                "prompt": step_record["prompt"],
                "response": step_record.get("user_response", "")
            })
            # Set hitl_response for immediate next step
            context["hitl_response"] = step_record.get("user_response", "")
        else:
            # Regular agent step
            context["steps"].append({
                "agent": step_record["agent"],
                "response": step_record["response"]
            })

    # last_response is the most recent agent or HITL response
    if step_history:
        last = step_history[-1]
        context["last_response"] = (
            last.get("user_response") if last.get("type") == "hitl"
            else last.get("response", "")
        )

    return context
```

### 1.7 Example Workflow

**File:** `examples/chain-hitl-approval-demo.yaml`

```yaml
version: 0
name: "hitl-approval-demo"
description: "Chain workflow with human approval gate"

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  researcher:
    prompt: "Research the given topic and provide findings."

  analyst:
    prompt: "Analyze the findings and create recommendations."

pattern:
  type: chain
  config:
    steps:
      # Step 1: Research
      - agent: researcher
        input: "Research the topic: {{ topic }}"

      # Step 2: HITL approval gate
      - type: hitl
        prompt: |
          Review the research findings below and approve proceeding to analysis.
          Respond with 'approved' to continue, or provide feedback for revisions.
        context_display: |
          ### Research Findings

          {{ steps[0].response }}
        default: "approved"
        timeout_seconds: 3600  # 1 hour

      # Step 3: Analysis (only if approved)
      - agent: analyst
        input: |
          User review: {{ hitl_response }}

          {% if hitl_response == 'approved' %}
          Analyze these research findings and provide recommendations:
          {{ steps[0].response }}
          {% else %}
          The user provided this feedback on the research:
          {{ hitl_response }}

          Please address their concerns and provide revised analysis.
          {% endif %}

outputs:
  artifacts:
    - path: "./hitl-demo-output.md"
      from: "{{ last_response }}"
```

### 1.8 Testing

**File:** `tests/test_chain_hitl.py`

```python
"""Tests for HITL functionality in chain pattern."""

import pytest
from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.exec.chain import run_chain
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK

@pytest.mark.asyncio
async def test_chain_hitl_pause_and_resume(mock_openai, tmp_path):
    """Test chain pauses at HITL step and resumes with user response."""

    # Create chain spec with HITL step
    spec = create_chain_spec_with_hitl(
        steps=[
            {"agent": "researcher", "input": "Research AI"},
            {"type": "hitl", "prompt": "Approve findings?", "default": "yes"},
            {"agent": "analyst", "input": "Analyze: {{ hitl_response }}"}
        ]
    )

    repo = FileSessionRepository(storage_dir=tmp_path)

    # First execution: run until HITL pause
    result1 = await run_chain(spec, {}, session_state=None, session_repo=repo)

    assert result1.exit_code == EX_HITL_PAUSE
    assert result1.session_id is not None

    # Load session and verify HITL state
    session_id = result1.session_id
    state = await repo.load(session_id)

    assert state.metadata.status == SessionStatus.PAUSED
    assert state.pattern_state["hitl_state"]["active"] is True
    assert state.pattern_state["hitl_state"]["prompt"] == "Approve findings?"
    assert len(state.pattern_state["step_history"]) == 1  # Only researcher done

    # Resume with HITL response
    result2 = await run_chain(
        spec, {},
        session_state=state,
        session_repo=repo,
        hitl_response="approved with suggestions"
    )

    assert result2.exit_code == EX_OK
    assert result2.success is True

    # Verify HITL response was injected
    final_state = await repo.load(session_id)
    assert final_state.metadata.status == SessionStatus.COMPLETED
    assert len(final_state.pattern_state["step_history"]) == 3

    hitl_step = final_state.pattern_state["step_history"][1]
    assert hitl_step["type"] == "hitl"
    assert hitl_step["user_response"] == "approved with suggestions"


@pytest.mark.asyncio
async def test_chain_hitl_timeout():
    """Test HITL timeout handling."""
    # TODO: Implement timeout logic in Phase 2


@pytest.mark.asyncio
async def test_chain_hitl_default_response():
    """Test HITL default response when user provides empty input."""
    # TODO: Support empty response → default in Phase 2


@pytest.mark.asyncio
async def test_chain_multiple_hitl_steps():
    """Test chain with multiple HITL steps."""
    # Create chain with 2 HITL steps
    spec = create_chain_spec_with_hitl(
        steps=[
            {"agent": "agent1", "input": "task 1"},
            {"type": "hitl", "prompt": "Approve step 1?"},
            {"agent": "agent2", "input": "task 2"},
            {"type": "hitl", "prompt": "Approve step 2?"},
            {"agent": "agent3", "input": "task 3"}
        ]
    )

    # Should pause at first HITL, resume, then pause at second HITL
    # TODO: Implement test
```

### Acceptance Criteria

- [x] Schema supports HITL step type in chain pattern
- [x] Chain executor pauses at HITL step, saves session, exits with EX_HITL_PAUSE
- [x] User can resume with `--hitl-response "text"`
- [x] HITL response is injected into template context as `{{ hitl_response }}`
- [x] Context display renders templates correctly
- [x] Session status set to PAUSED during HITL wait
- [x] Tests cover pause, resume, and multiple HITL steps
- [x] Example workflow demonstrates HITL approval gate
- [x] Documentation added to README and manual

---

## Phase 2: Multi-Pattern HITL Support (Week 2)

**Goal:** Extend HITL to all 7 workflow patterns with pattern-specific implementations.

**Deliverables:**
- HITL support in workflow, routing, parallel, evaluator-optimizer, orchestrator-workers, graph patterns
- Pattern-specific HITL state handling
- Interactive CLI mode (optional: prompt for input instead of exit)
- Enhanced HITL features (timeout, validation, conditional skipping)

### 2.1 Workflow Pattern HITL

**Implementation Strategy:**
- HITL steps can be tasks in the DAG
- Dependencies on HITL tasks pause execution until resumed
- Multiple HITL tasks can be pending (independent branches)

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: research
        agent: researcher
        input: "Research topic"

      - id: review_research
        type: hitl
        prompt: "Review research before analysis"
        context_display: "{{ tasks.research.response }}"
        dependencies: [research]

      - id: analysis
        agent: analyst
        input: "Analyze: {{ tasks.review_research.response }}"
        dependencies: [review_research]
```

**State Structure:**
```python
{
    "completed_tasks": ["research"],
    "pending_tasks": ["review_research"],  # HITL task waiting
    "blocked_tasks": ["analysis"],  # Blocked on HITL
    "hitl_tasks": {
        "review_research": {
            "active": true,
            "prompt": "Review research...",
            "user_response": null
        }
    }
}
```

### 2.2 Parallel Pattern HITL

**Implementation Strategy:**
- HITL can be a branch or in reduce step
- If HITL in branch, only that branch pauses
- If HITL in reduce, all branches must complete first

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: web_research
        agent: web_agent
        input: "Research on web"

      - id: review_web
        type: hitl
        prompt: "Review web research"
        context_display: "{{ branches.web_research.response }}"

    reduce:
      type: hitl
      prompt: "Approve final aggregation?"
      context_display: |
        Branch results:
        {% for branch_id, output in branches.items() %}
        - {{ branch_id }}: {{ output.response[:100] }}
        {% endfor %}
```

### 2.3 Graph Pattern HITL

**Implementation Strategy:**
- HITL as a node in the graph
- Next edge determined by user response (conditional routing)

```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: start
        agent: planner
        input: "Create plan"

      - id: user_review
        type: hitl
        prompt: "Review plan. Respond 'approve' or 'revise'"
        context_display: "{{ nodes.start.response }}"

      - id: execute
        agent: executor
        input: "Execute approved plan"

      - id: revise
        agent: planner
        input: "Revise based on: {{ hitl_response }}"

    edges:
      - from: start
        to: user_review

      - from: user_review
        to: execute
        condition: "hitl_response == 'approve'"

      - from: user_review
        to: revise
        condition: "hitl_response == 'revise'"

      - from: revise
        to: user_review
```

### 2.4 Interactive CLI Mode (Optional)

For local development, allow synchronous HITL without exit/resume:

```bash
# Interactive mode: prompts for input instead of exiting
$ strands run workflow.yaml --hitl-interactive

# When HITL step reached:
🤝 HUMAN INPUT REQUIRED
Review the research findings below and approve proceeding to analysis.

### Context for Review
[Research output displayed here]

Your response: ▊
```

**Implementation:**
```python
async def run_chain(..., hitl_interactive: bool = False):
    """Chain executor with optional interactive HITL."""

    # ... existing logic

    if isinstance(step_config, dict) and step_config.get("type") == "hitl":
        hitl_step = HITLStep(**step_config)

        if hitl_interactive:
            # Prompt for input synchronously
            console.print(Panel(f"🤝 HUMAN INPUT REQUIRED\n\n{hitl_step.prompt}"))
            if hitl_step.context_display:
                console.print(Panel(context_text))

            user_input = Prompt.ask("Your response", default=hitl_step.default or "")

            # Continue execution with response
            hitl_response = user_input
            # ... inject into context and continue
        else:
            # Standard mode: save and exit
            # ... existing HITL pause logic
```

### 2.5 Enhanced HITL Features

#### Timeout Handling

```python
async def check_hitl_timeout(session_state: SessionState, repo: FileSessionRepository):
    """Check if HITL has timed out and apply default."""

    hitl_state = session_state.pattern_state.get("hitl_state")
    if not hitl_state or not hitl_state["active"]:
        return False

    if hitl_state["timeout_at"]:
        timeout_dt = datetime.fromisoformat(hitl_state["timeout_at"])
        if datetime.now(UTC) > timeout_dt:
            # Apply default response
            default = hitl_state.get("default_response", "timeout_expired")
            logger.warning("hitl_timeout", session_id=session_state.metadata.session_id)

            # Auto-resume with default
            # TODO: Trigger auto-resume or mark session as timed out
            return True

    return False
```

#### Response Validation

```yaml
- type: hitl
  prompt: "Approve or reject? (yes/no)"
  validation:
    pattern: "^(yes|no)$"
    error_message: "Please respond with 'yes' or 'no'"
```

#### Conditional Skipping

```yaml
- type: hitl
  prompt: "Review high-risk operation"
  skip_if: "risk_level < 5"  # JMESPath condition
  context_display: "{{ risk_assessment }}"
```

### Acceptance Criteria

- [x] HITL supported in all 7 workflow patterns
- [x] Workflow pattern handles HITL tasks in DAG
- [x] Parallel pattern handles HITL in branches and reduce
- [x] Graph pattern allows HITL nodes with conditional routing
- [x] Interactive mode (`--hitl-interactive`) prompts inline (optional)
- [x] Timeout handling applies default response
- [x] Response validation with regex patterns
- [x] Conditional HITL skipping with JMESPath
- [x] Tests cover all patterns with HITL
- [x] Examples for each pattern with HITL

---

## Phase 3: API & Advanced Features (Week 3)

**Goal:** Production-ready HITL with programmatic API, multi-user support, and enterprise features.

**Deliverables:**
- Programmatic API for HITL (Python SDK-style)
- Multi-user HITL (notify, collect responses)
- HITL history and audit trail
- Web UI integration hooks
- Documentation and best practices

### 3.1 Programmatic API

Enable HITL workflows from Python code:

```python
from strands_cli import StrandsWorkflow, HITLHandler

class CustomHITLHandler(HITLHandler):
    """Custom handler for HITL events."""

    async def on_hitl_pause(
        self,
        session_id: str,
        prompt: str,
        context: str
    ) -> str:
        """Called when workflow pauses for HITL.

        Returns:
            User response (can be from web UI, Slack, email, etc.)
        """
        # Send notification to Slack
        await slack_client.send_message(
            channel="#workflow-approvals",
            text=f"Approval needed: {prompt}\n\nContext: {context}\n\n"
                 f"Resume with: /approve {session_id} <response>"
        )

        # Store in database for web UI
        await db.create_hitl_request(
            session_id=session_id,
            prompt=prompt,
            context=context,
            status="pending"
        )

        # Return None to pause (response provided later via resume)
        return None

    async def on_hitl_resume(
        self,
        session_id: str,
        response: str
    ) -> None:
        """Called when workflow resumes from HITL."""
        await db.update_hitl_request(session_id, status="completed", response=response)
        await slack_client.send_message(
            channel="#workflow-approvals",
            text=f"Workflow {session_id} resumed with: {response}"
        )


# Use custom handler
workflow = StrandsWorkflow.from_file("workflow.yaml")
workflow.set_hitl_handler(CustomHITLHandler())

result = await workflow.run(variables={"topic": "AI"})
```

**Implementation:**

```python
# src/strands_cli/api.py

from typing import Protocol, Any
from strands_cli.types import Spec, RunResult

class HITLHandler(Protocol):
    """Protocol for HITL event handling."""

    async def on_hitl_pause(
        self,
        session_id: str,
        prompt: str,
        context: str
    ) -> str | None:
        """Handle HITL pause event.

        Returns:
            User response (str) to continue immediately, or None to pause.
        """
        ...

    async def on_hitl_resume(self, session_id: str, response: str) -> None:
        """Handle HITL resume event."""
        ...


class StrandsWorkflow:
    """Programmatic workflow execution API."""

    def __init__(self, spec: Spec):
        self.spec = spec
        self.hitl_handler: HITLHandler | None = None

    @classmethod
    def from_file(cls, path: str) -> "StrandsWorkflow":
        """Load workflow from YAML/JSON file."""
        from strands_cli.loader import load_spec
        spec = load_spec(path, {})
        return cls(spec)

    def set_hitl_handler(self, handler: HITLHandler) -> None:
        """Set custom HITL handler."""
        self.hitl_handler = handler

    async def run(
        self,
        variables: dict[str, str] | None = None,
        resume_session_id: str | None = None
    ) -> RunResult:
        """Execute workflow with optional HITL handling."""

        # Inject HITL handler into executor context
        # Executor calls handler when HITL step reached

        from strands_cli.exec.chain import run_chain
        result = await run_chain(
            self.spec,
            variables,
            hitl_handler=self.hitl_handler
        )

        return result
```

### 3.2 Multi-User HITL

Support multiple users approving different HITL steps:

```yaml
- type: hitl
  prompt: "Legal review required"
  required_approvers: ["legal@company.com"]
  approval_threshold: 1  # Number of approvals needed

- type: hitl
  prompt: "Executive approval for budget"
  required_approvers: ["ceo@company.com", "cfo@company.com"]
  approval_threshold: 2  # Both must approve
```

**State Structure:**

```python
{
    "hitl_state": {
        "active": true,
        "step_index": 2,
        "prompt": "Legal review required",
        "required_approvers": ["legal@company.com"],
        "approval_threshold": 1,
        "approvals": [
            {
                "user": "legal@company.com",
                "response": "approved",
                "timestamp": "2025-11-10T14:30:00Z"
            }
        ],
        "is_approved": true  # threshold met
    }
}
```

### 3.3 HITL History & Audit Trail

Track all HITL interactions for compliance:

```python
# Session state includes full HITL history
{
    "hitl_history": [
        {
            "step_index": 1,
            "prompt": "Review research findings",
            "context_snapshot": "Research output...",
            "user": "user@example.com",
            "response": "approved with changes",
            "timestamp": "2025-11-10T10:00:00Z",
            "duration_seconds": 300
        },
        {
            "step_index": 3,
            "prompt": "Approve budget allocation",
            "context_snapshot": "Budget: $50,000",
            "user": "cfo@example.com",
            "response": "approved",
            "timestamp": "2025-11-10T11:00:00Z",
            "duration_seconds": 120
        }
    ]
}
```

Export audit trail:

```bash
$ strands sessions show <session-id> --export-hitl-history audit.json
```

### 3.4 Web UI Integration Hooks

Provide webhooks for web UI integration:

```yaml
runtime:
  webhooks:
    hitl_pause: "https://workflow-ui.company.com/api/hitl/pause"
    hitl_resume: "https://workflow-ui.company.com/api/hitl/resume"
```

When HITL pause occurs:
```http
POST https://workflow-ui.company.com/api/hitl/pause
Content-Type: application/json

{
  "session_id": "abc-123",
  "workflow_name": "research-approval",
  "step_index": 2,
  "prompt": "Review research findings",
  "context": "Research output text...",
  "timeout_at": "2025-11-10T15:00:00Z",
  "resume_url": "https://strands-api.company.com/resume/abc-123"
}
```

Web UI posts response:
```http
POST https://strands-api.company.com/resume/abc-123
Content-Type: application/json
Authorization: Bearer <token>

{
  "response": "approved with suggestions",
  "user": "reviewer@company.com"
}
```

### 3.5 Best Practices Documentation

**File:** `docs/HITL_GUIDE.md`

```markdown
# Human-in-the-Loop Best Practices

## When to Use HITL

✅ **Good Use Cases:**
- High-stakes decisions (budget approvals, legal reviews)
- Quality control gates (review outputs before expensive next steps)
- Debugging and experimentation (pause to inspect state)
- Regulatory compliance (human oversight requirements)
- Dynamic workflows (user chooses path at runtime)

❌ **Avoid HITL For:**
- Simple yes/no that could be workflow inputs
- High-frequency operations (use agent routing instead)
- Deterministic logic (use conditional edges in graph pattern)

## Design Patterns

### 1. Approval Gates
```yaml
- agent: generator
  input: "Generate risky content"

- type: hitl
  prompt: "Review generated content for policy compliance"
  validation:
    pattern: "^(approve|reject|revise)$"
```

### 2. Multi-Stage Review
```yaml
# Legal review → Executive approval → Execution
- type: hitl
  prompt: "Legal review"
  required_approvers: ["legal@co.com"]

- type: hitl
  prompt: "Executive approval"
  required_approvers: ["exec@co.com"]
  skip_if: "steps[0].response == 'reject'"
```

### 3. Dynamic Branching
```yaml
# User chooses analysis method
- type: hitl
  prompt: "Choose analysis method: statistical, ml, or hybrid"
  validation:
    pattern: "^(statistical|ml|hybrid)$"

- agent: analyst
  input: |
    Perform {{ hitl_response }} analysis on dataset
```

## Production Considerations

1. **Timeouts**: Always set reasonable timeouts
2. **Defaults**: Provide safe defaults for timeout scenarios
3. **Notifications**: Integrate with Slack/email for HITL alerts
4. **Audit Trail**: Enable HITL history for compliance
5. **Testing**: Use `--hitl-interactive` for local testing
```

### Acceptance Criteria

- [x] Programmatic API supports custom HITL handlers
- [x] Multi-user HITL with approval thresholds
- [x] HITL history tracked in session state
- [x] Audit trail export (`--export-hitl-history`)
- [x] Webhook integration for web UIs
- [x] Best practices documentation
- [x] API reference documentation
- [x] Tests cover API usage and multi-user scenarios

---

## Testing Strategy

### Unit Tests

- HITL step validation (schema, Pydantic models)
- HITL state serialization/deserialization
- Template context with `{{ hitl_response }}`
- Timeout calculation and expiry
- Response validation with regex

### Integration Tests

- Chain pattern: pause → resume with response
- Workflow pattern: HITL task in DAG
- Parallel pattern: HITL in branch and reduce
- Graph pattern: HITL node with conditional routing
- Multiple HITL steps in same workflow
- HITL timeout → default response
- Interactive mode (`--hitl-interactive`)

### E2E Tests

- Full workflow with HITL approval gate (CLI)
- Resume after restart (simulate crash during HITL pause)
- Multi-user approval workflow
- Web UI webhook integration (mock server)
- API usage with custom HITL handler

### Performance Tests

- HITL pause overhead (<50ms)
- Session save during HITL pause (<200ms)
- Resume with HITL response (<100ms additional)

---

## Migration and Rollout

### Backward Compatibility

- HITL is opt-in via new step type (`type: hitl`)
- Existing workflows continue without modification
- No breaking changes to existing patterns

### Rollout Phases

**Week 1 (Phase 1):**
- Internal testing with chain pattern
- CLI-only HITL (exit/resume model)
- Validate session persistence integration

**Week 2 (Phase 2):**
- All 7 patterns support HITL
- Interactive mode for dev workflows
- Enhanced features (timeout, validation)

**Week 3 (Phase 3):**
- Programmatic API for integrations
- Multi-user HITL for production
- Documentation and examples

### Feature Flags

```yaml
# Environment variables
STRANDS_HITL_ENABLED: true
STRANDS_HITL_DEFAULT_TIMEOUT: 3600  # 1 hour
STRANDS_HITL_INTERACTIVE: false  # Interactive mode default
```

---

## Documentation Requirements

### User Documentation

**README.md Updates:**

```markdown
## Human-in-the-Loop Workflows

Strands CLI supports human-in-the-loop (HITL) steps for approval gates,
quality control, and interactive workflows:

### Basic Usage

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research topic"

      - type: hitl
        prompt: "Review findings before analysis"
        context_display: "{{ steps[0].response }}"

      - agent: analyst
        input: "Analyze based on approval: {{ hitl_response }}"
```

### CLI Workflow

```bash
# Run workflow (pauses at HITL step)
$ strands run workflow.yaml --var topic="AI"
🤝 HUMAN INPUT REQUIRED
Review findings before analysis
Session ID: abc-123
Resume with: strands run --resume abc-123 --hitl-response 'approved'

# Resume with user response
$ strands run --resume abc-123 --hitl-response 'approved'
Workflow resumed and completed.
```

### Interactive Mode (Dev/Testing)

```bash
# Prompt for HITL input inline
$ strands run workflow.yaml --hitl-interactive
🤝 HUMAN INPUT REQUIRED
Review findings before analysis
Your response: approved
[continues execution immediately]
```
```

**New Document:** `docs/HITL_GUIDE.md` (see Phase 3.5)

### Developer Documentation

**API Reference:** `docs/API_HITL.md`

- HITL step schema reference
- HITLHandler protocol
- StrandsWorkflow API
- Webhook integration guide

---

## Security Considerations

### Input Validation

- Validate HITL responses against schema constraints
- Sanitize user input before template injection
- **Mitigation:** Use response validation patterns in schema

### Session Tampering

- User could modify session files to bypass HITL
- **Mitigation:** Add HMAC signatures to session state (future enhancement)

### Timeout Abuse

- Attacker could set infinite timeout to block workflows
- **Mitigation:** Enforce maximum timeout (e.g., 7 days) in validation

### Multi-User Authorization

- Ensure only authorized users can respond to HITL
- **Mitigation:** Webhook integration requires authentication tokens

---

## Performance Benchmarks

### HITL Overhead

| Operation | Time | Notes |
|-----------|------|-------|
| HITL step detection | <5ms | Step type check |
| Context rendering | 10-50ms | Template evaluation |
| Session save (HITL pause) | 30-100ms | File write |
| Session load (HITL resume) | 20-80ms | File read |
| Response injection | <5ms | Context update |

**Total HITL pause overhead:** ~50-200ms
**Total HITL resume overhead:** ~30-100ms

### Target Performance

- HITL pause latency: <200ms
- HITL resume latency: <100ms
- Minimal impact on workflow execution time

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session corruption during HITL | Low | High | Atomic writes, file locking |
| User forgets session ID | Medium | Low | Display prominently, add `sessions list` |
| Timeout confusion | Medium | Medium | Clear messaging, default handling |
| Template injection via response | Low | High | Input sanitization, validation |

### Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Multi-pattern complexity | Medium | Medium | Prioritize chain/workflow first |
| API design changes | Low | High | Early prototype, user feedback |
| Testing bottleneck | Medium | Low | Parallel test development |

---

## Success Metrics

### Phase Completion Metrics

- [x] Phase 1: Chain pattern HITL works end-to-end
- [x] Phase 2: All 7 patterns support HITL
- [x] Phase 3: Programmatic API functional

### Quality Metrics

- [x] Test coverage ≥85% for HITL module
- [x] HITL pause overhead <200ms
- [x] HITL resume overhead <100ms
- [x] Zero data loss during HITL pause/resume

### User Adoption Metrics (Post-Release)

- [x] ≥5 internal users adopt HITL
- [x] ≥10 external users report successful HITL usage
- [x] <5 HITL-related bug reports in first month

---

## Comparison with Strands SDK `handoff_to_user`

### Strands SDK Approach (Tool-Based)

```python
# Strands SDK: HITL as a tool
from strands import Agent
from strands_tools import handoff_to_user

agent = Agent(tools=[handoff_to_user])
response = agent.run("Complete task X")
# Agent decides when to call handoff_to_user tool
# Requires agent to be "aware" of when to ask for help
```

**Pros:**
- Agent autonomy (decides when to handoff)
- Works with any agent architecture
- Simple integration

**Cons:**
- Agent may not call handoff when it should
- Unpredictable pause points
- Difficult to enforce compliance gates

### Strands CLI Approach (Workflow-Native)

```yaml
# Strands CLI: HITL as workflow step
pattern:
  type: chain
  config:
    steps:
      - agent: worker
        input: "Complete task X"
      - type: hitl
        prompt: "Review task X completion"
      - agent: next_worker
        input: "Continue with Y"
```

**Pros:**
- Deterministic pause points
- Workflow designer controls when HITL occurs
- Enforces compliance gates
- Easier to audit and visualize

**Cons:**
- Less flexible (fixed pause points)
- Cannot have agent dynamically request HITL

### Hybrid Approach (Future)

Support both models:
1. Workflow-native HITL (this plan)
2. Tool-based HITL (agent can call `handoff_to_user` tool dynamically)

```yaml
agents:
  autonomous_agent:
    prompt: "You may call handoff_to_user if uncertain"
    tools:
      - handoff_to_user  # Tool-based HITL

pattern:
  type: chain
  config:
    steps:
      - agent: autonomous_agent
        input: "Research and analyze topic"

      - type: hitl  # Workflow-native HITL
        prompt: "Final approval before publishing"
```

---

## Dependencies and Prerequisites

### Development Environment

- Python ≥3.12
- Strands SDK ≥1.0.0
- Phase 2 of DURABLE.md completed (session persistence)
- pytest-asyncio for async tests

### External Services

- OpenAI/Ollama for integration tests
- (Optional) Slack/webhook endpoints for notification testing

---

## Appendix: Example HITL Workflows

### Example 1: Research Approval Workflow

**File:** `examples/hitl-research-approval-openai.yaml`

```yaml
version: 0
name: "research-approval-workflow"
description: "Research workflow with human review gate"

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  researcher:
    prompt: "Research the given topic thoroughly."

  analyst:
    prompt: "Analyze research findings."

  writer:
    prompt: "Write comprehensive report."

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research: {{ topic }}"

      - type: hitl
        prompt: |
          Review the research findings below.
          Respond with 'approved' to proceed to analysis,
          or provide feedback for revisions.
        context_display: |
          ## Research Findings

          {{ steps[0].response }}
        default: "approved"
        timeout_seconds: 3600

      - agent: analyst
        input: |
          User review: {{ hitl_response }}

          Analyze these findings:
          {{ steps[0].response }}

      - type: hitl
        prompt: "Approve final report generation?"
        context_display: |
          ## Analysis

          {{ steps[2].response }}
        validation:
          pattern: "^(yes|no)$"
          error_message: "Please respond 'yes' or 'no'"

      - agent: writer
        input: |
          Write final report based on:

          Research: {{ steps[0].response }}
          Analysis: {{ steps[2].response }}
          User approval: {{ hitl_response }}

outputs:
  artifacts:
    - path: "./research-report.md"
      from: "{{ last_response }}"
```

### Example 2: Budget Approval Workflow (Graph Pattern)

**File:** `examples/hitl-budget-approval-graph-openai.yaml`

```yaml
version: 0
name: "budget-approval-workflow"
description: "Budget planning with multi-level approval"

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  planner:
    prompt: "Create detailed budget plan."

  revisor:
    prompt: "Revise budget based on feedback."

  executor:
    prompt: "Execute approved budget plan."

pattern:
  type: graph
  config:
    nodes:
      - id: initial_plan
        agent: planner
        input: "Create budget plan for: {{ project }}"

      - id: manager_review
        type: hitl
        prompt: "Manager review: Approve, reject, or request revisions?"
        context_display: |
          ## Budget Plan
          {{ nodes.initial_plan.response }}
        validation:
          pattern: "^(approve|reject|revise)$"

      - id: exec_approval
        type: hitl
        prompt: "Executive approval required (yes/no)"
        context_display: "{{ nodes.initial_plan.response }}"
        required_approvers: ["exec@company.com"]

      - id: revise_plan
        agent: revisor
        input: |
          Revise budget based on feedback:
          {{ hitl_response }}

          Original plan:
          {{ nodes.initial_plan.response }}

      - id: execute_plan
        agent: executor
        input: "Execute: {{ nodes.initial_plan.response }}"

      - id: rejected
        type: hitl
        prompt: "Plan rejected. Provide reason for records."

    edges:
      - from: initial_plan
        to: manager_review

      - from: manager_review
        to: exec_approval
        condition: "hitl_response == 'approve'"

      - from: manager_review
        to: revise_plan
        condition: "hitl_response == 'revise'"

      - from: manager_review
        to: rejected
        condition: "hitl_response == 'reject'"

      - from: revise_plan
        to: manager_review  # Loop back for re-review

      - from: exec_approval
        to: execute_plan
        condition: "hitl_response == 'yes'"

outputs:
  artifacts:
    - path: "./budget-plan.md"
      from: "{{ nodes.execute_plan.response }}"
      skip_if: "nodes.execute_plan.response == null"
```

### Example 3: Interactive Testing Workflow

**File:** `examples/hitl-interactive-test-openai.yaml`

```yaml
version: 0
name: "interactive-test-workflow"
description: "Use --hitl-interactive for rapid local testing"

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  generator:
    prompt: "Generate content based on user specifications."

pattern:
  type: chain
  config:
    steps:
      - agent: generator
        input: "Generate initial content for: {{ topic }}"

      - type: hitl
        prompt: "Review generated content. Provide feedback or 'done'."
        context_display: "{{ steps[0].response }}"

      - agent: generator
        input: |
          User feedback: {{ hitl_response }}

          {% if hitl_response == 'done' %}
          Finalize the content.
          {% else %}
          Revise based on feedback.
          {% endif %}

# Run with: strands run examples/hitl-interactive-test-openai.yaml --hitl-interactive
```

---

**End of HITL Implementation Plan**

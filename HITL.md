# Strands CLI: Human-in-the-Loop (HITL) Workflow Execution

**Created:** 2025-11-09
**Owner:** Thomas Rohde
**Target Version:** v0.12.0
**Status:** 📋 Proposal
**Complexity:** High
**Duration:** 3 weeks
**Dependencies:** DURABLE.md (Session persistence infrastructure)

---

## Executive Summary

Implement Human-in-the-Loop (HITL) capabilities for Strands CLI workflows, enabling:

1. **Manual Approval Gates**: Pause workflows at critical decision points for human review
2. **Interactive Input**: Request human input during execution for ambiguous decisions
3. **Quality Control**: Review and approve/reject agent outputs before proceeding
4. **Multi-Day Workflows**: Pause long-running workflows for human scheduling
5. **Debugging & Iteration**: Inspect state, modify variables, and continue execution

**Key Design Principles:**
- Leverage Strands SDK's native interrupt system (`event.interrupt()`, `tool_context.interrupt()`)
- CLI-based interaction with `--resume` and approval flags
- Programmatic API for integration with external systems (Slack, Jira, web UIs)
- Pattern-agnostic interrupt points (works across all 7 workflow types)
- State preservation via session management from DURABLE.md

---

## Architecture Overview

### HITL Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Workflow Execution                       │
│                                                              │
│  Step 1 → Step 2 → [INTERRUPT] ──┐                         │
│                                    │                         │
│                                    ↓                         │
│                          ┌─────────────────┐                │
│                          │  Session Save   │                │
│                          │  status=paused  │                │
│                          │  + interrupt    │                │
│                          │    metadata     │                │
│                          └─────────────────┘                │
│                                    │                         │
│                                    ↓                         │
│                          ┌─────────────────┐                │
│                          │  Human Review   │                │
│                          │  (CLI/API/UI)   │                │
│                          └─────────────────┘                │
│                                    │                         │
│                                    ↓                         │
│                          ┌─────────────────┐                │
│                          │ Resume with     │                │
│                          │ Response        │                │
│                          └─────────────────┘                │
│                                    │                         │
│                                    ↓                         │
│  [RESUME] → Step 3 → Step 4 → Complete                     │
└─────────────────────────────────────────────────────────────┘
```

### Interrupt Types

1. **Manual Gate Interrupts**: Explicit pause points in workflow spec
   - Defined in spec: `type: manual_gate`
   - Prompt for approval/rejection/modification
   - Optional timeout with fallback action

2. **Tool Approval Interrupts**: Request approval before dangerous tool execution
   - Implemented via Strands SDK hooks (`BeforeToolCallEvent`)
   - Tools marked as requiring approval (e.g., `delete_files`, `http_post`)
   - Auto-approve option for trusted contexts

3. **Quality Gate Interrupts**: Review agent output before proceeding
   - Check output quality/completeness
   - Approve, reject, or provide feedback for retry
   - Useful for evaluator-optimizer pattern

4. **Conditional Interrupts**: Dynamic pause based on runtime conditions
   - Evaluate condition: `if: "{{ score < 0.8 }}"`
   - Pause only when condition met
   - Useful for exception handling

### Session State for HITL

Extension to DURABLE.md session state:

```json
{
  "metadata": {
    "status": "paused",  // "paused" indicates waiting for human
    "interrupt_metadata": {
      "interrupt_id": "approval-001",
      "interrupt_type": "manual_gate",
      "interrupt_name": "review_research",
      "created_at": "2025-11-09T10:15:00Z",
      "timeout_at": "2025-11-09T18:00:00Z",  // Optional
      "fallback_action": "continue"  // or "cancel"
    }
  },
  "pattern_state": {
    "current_step": 2,
    "interrupt_context": {
      "prompt": "Review the research findings before analysis.",
      "data_to_review": {
        "step": 1,
        "agent": "researcher",
        "response": "Research findings...",
        "output_preview": "First 500 chars..."
      },
      "options": {
        "approve": "Continue to next step",
        "reject": "Cancel workflow",
        "modify": "Provide feedback and retry",
        "defer": "Pause for later review"
      }
    }
  }
}
```

---

## CLI Design

### Execution with Manual Gates

```bash
# Run workflow with manual gates
strands run workflow.yaml

# Output:
# ✓ Step 1 completed: researcher
# ⏸  Manual gate: review_research
#    → Review research findings before proceeding to analysis
#    → Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
#    → Use: strands resume a1b2c3... --approve

# Later: Resume with approval
strands resume a1b2c3d4-e5f6-7890-abcd-ef1234567890 --approve

# Resume with rejection (stops workflow)
strands resume a1b2c3d4-e5f6-7890-abcd-ef1234567890 --reject

# Resume with feedback (retries step with modifications)
strands resume a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --modify \
  --feedback "Focus more on recent developments (2024-2025)"
```

### Interactive Mode

```bash
# Run with interactive prompts (blocks until human responds)
strands run workflow.yaml --interactive

# Output:
# ✓ Step 1 completed: researcher
# ⏸  Manual gate: review_research
#    Review research findings before proceeding to analysis
#
#    [Preview]
#    Research findings about AI agents in 2025...
#    (500 characters shown, 2000 total)
#
#    Options:
#      [a] Approve - Continue to next step
#      [r] Reject - Cancel workflow
#      [m] Modify - Provide feedback and retry
#      [v] View full output
#      [d] Defer - Save session and exit
#
# Your choice: _
```

### Resume Options

```bash
# Basic resume with approval
strands resume <session-id> --approve

# Resume with rejection
strands resume <session-id> --reject [--reason "Not sufficient detail"]

# Resume with modifications
strands resume <session-id> --modify --feedback "Add more examples"

# Resume with variable overrides
strands resume <session-id> --approve --var focus="recent_trends"

# View interrupt details before deciding
strands sessions show <session-id> --interrupt-details

# Auto-approve all gates (dangerous, but useful for testing)
strands resume <session-id> --auto-approve
```

---

## Workflow Spec Extensions

### Manual Gate Step Type

```yaml
version: 0
name: "hitl-research-workflow"
runtime:
  provider: ollama
  model_id: "llama2"

agents:
  researcher:
    prompt: "Research {{topic}} thoroughly"
  analyst:
    prompt: "Analyze the research findings"
  writer:
    prompt: "Write report based on analysis"

pattern:
  type: chain
  config:
    steps:
      # Step 1: Research
      - agent: researcher
        input: "Research {{topic}}"

      # Manual gate after research
      - type: manual_gate
        id: review_research
        prompt: "Review research findings before analysis"
        timeout_minutes: 480  # 8 hours
        fallback_action: continue  # or cancel
        show_preview: true  # Show output preview
        preview_length: 500

      # Step 2: Analysis (runs after approval)
      - agent: analyst
        input: "Analyze: {{ steps[0].response }}"

      # Conditional interrupt (only if low quality)
      - type: manual_gate
        id: review_analysis
        prompt: "Analysis quality seems low. Review?"
        condition: "{{ steps[1].response|length < 1000 }}"  # Jinja2 condition
        fallback_action: continue

      # Step 3: Write report
      - agent: writer
        input: "Write report: {{ steps[1].response }}"
```

### Tool Approval Configuration

```yaml
version: 0
name: "hitl-tool-approval"
runtime:
  provider: bedrock

agents:
  admin:
    prompt: "You manage files and execute commands"
    tools:
      - python:
          callable: "strands_tools.delete_files"
          require_approval: true  # Pause before execution
          approval_prompt: "Approve deletion of files?"
      - python:
          callable: "strands_tools.read_file"
          require_approval: false  # Safe, no approval needed

pattern:
  type: single_agent
  config:
    agent: admin
    input: "Clean up old log files from /var/logs"
```

### Quality Gate in Evaluator Pattern

```yaml
pattern:
  type: evaluator_optimizer
  config:
    producer:
      agent: writer
      input: "Write article about {{topic}}"

    evaluator:
      agent: editor
      input: "Evaluate quality of article"
      output_schema:
        type: object
        properties:
          score:
            type: number
          feedback:
            type: string

    accept:
      min_score: 0.8
      max_iters: 5

      # HITL: Human review if quality gate not met after 3 iterations
      manual_review:
        after_iterations: 3
        prompt: "Quality gate not met after 3 attempts. Review output?"
        options:
          approve: "Accept current version"
          reject: "Cancel workflow"
          continue: "Continue optimization"
          modify: "Provide manual feedback"
```

---

## Programmatic API Design

### Python API for HITL Integration

```python
"""Example: Integrate HITL with external approval systems."""

from strands_cli.session import FileSessionRepository, SessionStatus
from strands_cli.hitl import InterruptHandler, InterruptResponse, InterruptType
from strands_cli.exec import run_workflow_async

async def run_with_slack_approvals(spec_path: Path, slack_client):
    """Run workflow with Slack-based approvals."""

    # Start workflow execution
    repo = FileSessionRepository()

    try:
        result = await run_workflow_async(
            spec_path,
            enable_hitl=True,
            interrupt_handler=SlackInterruptHandler(slack_client)
        )
    except InterruptPending as e:
        # Workflow paused for human input
        session_id = e.session_id
        interrupt_meta = e.interrupt_metadata

        # Send Slack message with approval buttons
        message = await slack_client.post_message(
            channel="#approvals",
            text=f"Workflow paused: {interrupt_meta['prompt']}",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": interrupt_meta['prompt']}
                },
                {
                    "type": "actions",
                    "elements": [
                        {"type": "button", "text": "Approve", "value": "approve"},
                        {"type": "button", "text": "Reject", "value": "reject"},
                        {"type": "button", "text": "Modify", "value": "modify"}
                    ]
                }
            ]
        )

        # Store session ID with message for callback
        await store_approval_request(message.ts, session_id)

        return {"status": "paused", "session_id": session_id}


async def handle_slack_approval(message_ts: str, action: str, feedback: str = None):
    """Handle Slack approval callback."""

    session_id = await get_session_for_message(message_ts)
    repo = FileSessionRepository()

    # Create interrupt response
    response = InterruptResponse(
        action=action,  # "approve" | "reject" | "modify"
        feedback=feedback
    )

    # Resume workflow with response
    result = await run_workflow_async(
        session_id=session_id,
        interrupt_response=response
    )

    return result
```

### REST API Endpoints (Optional Web Service)

```python
"""Optional: REST API for HITL workflows."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class WorkflowStartRequest(BaseModel):
    spec_path: str
    variables: dict[str, str] = {}
    enable_hitl: bool = True

class InterruptResponseRequest(BaseModel):
    session_id: str
    action: str  # "approve" | "reject" | "modify" | "defer"
    feedback: str | None = None
    variable_overrides: dict[str, str] = {}

@app.post("/workflows/run")
async def run_workflow(request: WorkflowStartRequest):
    """Start workflow execution."""
    try:
        result = await run_workflow_async(
            spec_path=request.spec_path,
            variables=request.variables,
            enable_hitl=request.enable_hitl
        )
        return {"status": "completed", "result": result}
    except InterruptPending as e:
        return {
            "status": "paused",
            "session_id": e.session_id,
            "interrupt": e.interrupt_metadata
        }

@app.post("/workflows/resume")
async def resume_workflow(request: InterruptResponseRequest):
    """Resume workflow with human response."""
    repo = FileSessionRepository()

    state = repo.load(request.session_id)
    if not state:
        raise HTTPException(404, "Session not found")

    if state.metadata.status != SessionStatus.PAUSED:
        raise HTTPException(400, "Session not paused")

    response = InterruptResponse(
        action=request.action,
        feedback=request.feedback,
        variable_overrides=request.variable_overrides
    )

    try:
        result = await run_workflow_async(
            session_id=request.session_id,
            interrupt_response=response
        )
        return {"status": "completed", "result": result}
    except InterruptPending as e:
        return {
            "status": "paused",
            "session_id": e.session_id,
            "interrupt": e.interrupt_metadata
        }

@app.get("/workflows/{session_id}")
async def get_workflow_status(session_id: str):
    """Get workflow status and interrupt details."""
    repo = FileSessionRepository()
    state = repo.load(session_id)

    if not state:
        raise HTTPException(404, "Session not found")

    return {
        "session_id": session_id,
        "status": state.metadata.status,
        "workflow_name": state.metadata.workflow_name,
        "pattern_type": state.metadata.pattern_type,
        "interrupt": state.metadata.interrupt_metadata if state.metadata.status == "paused" else None
    }
```

---

## Implementation Phases

### Phase 1: Manual Gate Infrastructure (Week 1)

**Goal:** Basic manual gate support in chain pattern

**Tasks:**
1. Extend session state with interrupt metadata
2. Add `manual_gate` step type to schema and types
3. Implement `InterruptPending` exception for pause
4. Add `--approve`, `--reject`, `--modify` flags to resume command
5. Chain executor: detect manual gates and pause
6. Unit tests for interrupt state serialization

**Deliverables:**
- Chain workflows can pause at manual gates
- Resume with approval/rejection works
- Session state includes interrupt context

### Phase 2: Interactive Mode & Tool Approvals (Week 2)

**Goal:** CLI interactive mode and tool approval hooks

**Tasks:**
1. Implement `--interactive` flag with Rich TUI
2. Create `ToolApprovalHook` using Strands SDK `BeforeToolCallEvent`
3. Add `require_approval` field to tool configurations
4. Implement timeout and fallback actions
5. Add conditional interrupts (Jinja2 conditions)
6. Extend to workflow, parallel, routing patterns

**Deliverables:**
- Interactive CLI prompts for approvals
- Tools can require human approval before execution
- Timeout with configurable fallback
- 4 patterns support manual gates (chain, workflow, parallel, routing)

### Phase 3: API & Advanced Patterns (Week 3)

**Goal:** Programmatic API and full pattern support

**Tasks:**
1. Create `InterruptHandler` protocol for custom integrations
2. Implement `run_workflow_async()` with interrupt support
3. Add quality gates to evaluator-optimizer pattern
4. Add manual gates to orchestrator-workers pattern
5. Add manual gates to graph pattern
6. Optional: REST API service with FastAPI
7. Documentation and examples

**Deliverables:**
- Python API for external integrations
- All 7 patterns support manual gates
- Example integrations (Slack, webhook)
- Comprehensive documentation

---

## Technical Implementation Details

### Extended Session State Model

```python
"""Extended session models for HITL support."""

from enum import Enum
from pydantic import BaseModel, Field

class InterruptType(str, Enum):
    """Type of interrupt."""
    MANUAL_GATE = "manual_gate"
    TOOL_APPROVAL = "tool_approval"
    QUALITY_GATE = "quality_gate"
    CONDITIONAL = "conditional"

class InterruptMetadata(BaseModel):
    """Metadata about active interrupt."""
    interrupt_id: str
    interrupt_type: InterruptType
    interrupt_name: str  # User-defined name (e.g., "review_research")
    prompt: str  # Human-readable prompt
    created_at: str  # ISO 8601
    timeout_at: str | None = None  # ISO 8601 (optional)
    fallback_action: str = "continue"  # or "cancel"

    # Context for review
    data_to_review: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, str] = Field(default_factory=dict)
    condition: str | None = None  # For conditional interrupts

class InterruptResponse(BaseModel):
    """Human response to interrupt."""
    action: str  # "approve" | "reject" | "modify" | "defer"
    feedback: str | None = None
    variable_overrides: dict[str, str] = Field(default_factory=dict)
    provided_at: str  # ISO 8601

class SessionMetadata(BaseModel):
    """Extended session metadata with interrupt support."""
    session_id: str
    workflow_name: str
    spec_hash: str
    pattern_type: str
    status: SessionStatus  # "running" | "paused" | "completed" | "failed"
    created_at: str
    updated_at: str
    error: str | None = None

    # HITL additions
    interrupt_metadata: InterruptMetadata | None = None
    interrupt_history: list[InterruptMetadata] = Field(default_factory=list)
```

### Manual Gate Executor Logic

```python
"""Manual gate execution in chain pattern."""

async def run_chain(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    interrupt_response: InterruptResponse | None = None
) -> RunResult:
    """Execute chain with manual gate support."""

    # ... existing setup ...

    for step_index in range(start_step, len(spec.pattern.config.steps)):
        step = spec.pattern.config.steps[step_index]

        # Check if this is a manual gate
        if step.type == "manual_gate":
            # If resuming with response, skip gate and continue
            if interrupt_response and interrupt_response.action == "approve":
                logger.info("manual_gate_approved", gate_id=step.id)
                continue

            # If reject, stop workflow
            if interrupt_response and interrupt_response.action == "reject":
                logger.info("manual_gate_rejected", gate_id=step.id)
                raise WorkflowRejectedError(f"Manual gate rejected: {step.id}")

            # If modify, apply feedback and retry previous step
            if interrupt_response and interrupt_response.action == "modify":
                logger.info("manual_gate_modify", gate_id=step.id)
                # Retry previous step with feedback injected
                step_index -= 1  # Go back one step
                context["human_feedback"] = interrupt_response.feedback
                continue

            # Evaluate condition (if present)
            if step.condition:
                condition_met = evaluate_condition(step.condition, context)
                if not condition_met:
                    logger.debug("manual_gate_condition_not_met", gate_id=step.id)
                    continue

            # Pause workflow at this gate
            interrupt_meta = InterruptMetadata(
                interrupt_id=f"gate-{step.id}",
                interrupt_type=InterruptType.MANUAL_GATE,
                interrupt_name=step.id,
                prompt=render_template(step.prompt, context),
                created_at=now_iso8601(),
                timeout_at=calculate_timeout(step.timeout_minutes) if step.timeout_minutes else None,
                fallback_action=step.fallback_action,
                data_to_review={
                    "previous_step": step_index - 1,
                    "output": step_history[-1] if step_history else None,
                    "preview": generate_preview(step_history[-1], step.preview_length)
                },
                options={
                    "approve": "Continue to next step",
                    "reject": "Cancel workflow",
                    "modify": "Provide feedback and retry previous step"
                }
            )

            # Save session with paused status
            if session_repo and session_state:
                session_state.metadata.status = SessionStatus.PAUSED
                session_state.metadata.interrupt_metadata = interrupt_meta
                session_state.pattern_state["current_step"] = step_index
                session_repo.save(session_state, spec_content="...")

            # Raise exception to exit execution loop
            raise InterruptPending(
                session_id=session_state.metadata.session_id,
                interrupt_metadata=interrupt_meta
            )

        # Normal step execution
        # ... existing step execution logic ...
```

### Tool Approval Hook

```python
"""Tool approval hook using Strands SDK."""

from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent
from strands_cli.hitl import InterruptPending, InterruptMetadata, InterruptType

class ToolApprovalHook(HookProvider):
    """Hook to request approval before tool execution."""

    def __init__(
        self,
        session_repo: FileSessionRepository,
        session_state: SessionState,
        tools_requiring_approval: set[str]
    ):
        self.session_repo = session_repo
        self.session_state = session_state
        self.tools_requiring_approval = tools_requiring_approval

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.request_approval)

    def request_approval(self, event: BeforeToolCallEvent) -> None:
        """Request approval before tool execution."""
        tool_name = event.tool_use["name"]

        # Check if this tool requires approval
        if tool_name not in self.tools_requiring_approval:
            return

        # Use Strands SDK interrupt
        approval = event.interrupt(
            f"tool-approval-{tool_name}",
            reason={
                "tool": tool_name,
                "input": event.tool_use["input"],
                "prompt": f"Approve execution of {tool_name}?"
            }
        )

        # Check approval response
        if approval.lower() not in ["y", "yes", "approve"]:
            event.cancel_tool = f"Tool execution denied by user: {tool_name}"
            logger.info("tool_execution_denied", tool=tool_name)
```

### Interactive CLI Mode

```python
"""Interactive CLI for manual gates."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

def handle_interrupt_interactive(
    interrupt_meta: InterruptMetadata,
    session_id: str
) -> InterruptResponse:
    """Handle interrupt with interactive CLI prompt."""

    # Display interrupt panel
    console.print()
    console.print(Panel(
        f"[bold yellow]⏸  Manual Gate: {interrupt_meta.interrupt_name}[/]\n\n"
        f"{interrupt_meta.prompt}\n\n"
        f"Session ID: {session_id}",
        title="Workflow Paused",
        border_style="yellow"
    ))

    # Show data preview if available
    if interrupt_meta.data_to_review:
        preview = interrupt_meta.data_to_review.get("preview")
        if preview:
            console.print("\n[bold]Preview:[/]")
            console.print(Panel(preview, border_style="dim"))

    # Show options
    console.print("\n[bold]Options:[/]")
    for key, description in interrupt_meta.options.items():
        console.print(f"  [{key[0]}] {description}")
    console.print(f"  [v] View full output")
    console.print(f"  [d] Defer - Save and exit")

    # Prompt user
    while True:
        choice = Prompt.ask("\nYour choice", choices=["a", "r", "m", "v", "d"])

        if choice == "a":
            return InterruptResponse(
                action="approve",
                provided_at=now_iso8601()
            )
        elif choice == "r":
            reason = Prompt.ask("Reason for rejection (optional)", default="")
            return InterruptResponse(
                action="reject",
                feedback=reason,
                provided_at=now_iso8601()
            )
        elif choice == "m":
            feedback = Prompt.ask("Provide feedback for retry")
            return InterruptResponse(
                action="modify",
                feedback=feedback,
                provided_at=now_iso8601()
            )
        elif choice == "v":
            # Show full output
            show_full_output(interrupt_meta.data_to_review)
            continue
        elif choice == "d":
            console.print(f"\n[yellow]Session saved. Resume with:[/]")
            console.print(f"  strands resume {session_id} --approve")
            sys.exit(0)
```

---

## Examples

### Example 1: Research Workflow with Review Gate

```yaml
version: 0
name: "research-with-review"
runtime:
  provider: ollama
  model_id: "llama2"

agents:
  researcher:
    prompt: "Research {{topic}} thoroughly. Cite sources."
  analyst:
    prompt: "Analyze findings and provide insights."
  writer:
    prompt: "Write a comprehensive report."

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research: {{topic}}"

      - type: manual_gate
        id: review_research
        prompt: "Review research quality before analysis"
        show_preview: true
        preview_length: 1000
        timeout_minutes: 480  # 8 hours
        fallback_action: continue

      - agent: analyst
        input: "Analyze: {{ steps[0].response }}"

      - agent: writer
        input: "Write report: {{ steps[1].response }}"

outputs:
  artifacts:
    - path: "./output/report.md"
      from: "{{ steps[2].response }}"
```

**Execution:**
```bash
# Start workflow
strands run research.yaml --var topic="AI Safety"

# Output:
# ✓ Step 1 completed: researcher (2000 tokens, 45s)
# ⏸  Manual gate: review_research
#    Review research quality before analysis
#    Session: abc123...
#    Timeout: 2025-11-09 18:00:00 (8 hours)
#    Resume: strands resume abc123... --approve

# Later: Resume
strands resume abc123... --approve

# Or: Reject and provide feedback
strands resume abc123... --modify \
  --feedback "Need more recent sources (2024-2025)"
```

### Example 2: File Management with Tool Approval

```yaml
version: 0
name: "cleanup-with-approval"
runtime:
  provider: bedrock

agents:
  admin:
    prompt: "You are a system administrator managing files."
    tools:
      - python:
          callable: "strands_tools.delete_files"
          require_approval: true
          approval_prompt: "Delete these files?"
      - python:
          callable: "strands_tools.list_files"

pattern:
  type: single_agent
  config:
    agent: admin
    input: "List and delete log files older than 30 days in /var/logs"
```

**Execution:**
```bash
# Run with interactive approval
strands run cleanup.yaml --interactive

# Output:
# Agent: admin
# Tool call: list_files(/var/logs)
# ✓ Found 15 log files older than 30 days
#
# Tool call: delete_files(["/var/logs/app.log.1", ...])
# ⏸  Tool Approval Required
#    Delete these files?
#      - /var/logs/app.log.1 (5MB)
#      - /var/logs/app.log.2 (5MB)
#      - ... (13 more files)
#
#    [a] Approve  [r] Reject  [v] View all files
# Your choice: a
#
# ✓ Files deleted successfully
```

### Example 3: Iterative Writing with Quality Gates

```yaml
version: 0
name: "iterative-writing"
runtime:
  provider: openai

agents:
  writer:
    prompt: "Write a technical blog post about {{topic}}"
  editor:
    prompt: |
      Evaluate the blog post quality.
      Return JSON: {"score": 0-10, "feedback": "..."}

pattern:
  type: evaluator_optimizer
  config:
    producer:
      agent: writer
      input: "Write blog post about {{topic}}"

    evaluator:
      agent: editor
      input: "Evaluate: {{ producer_output }}"

    accept:
      min_score: 8
      max_iters: 5

      # Human review if not converging
      manual_review:
        after_iterations: 3
        prompt: "Quality not meeting threshold. Approve current version?"
        condition: "{{ iteration >= 3 and score < 8 }}"
```

**Execution:**
```bash
strands run writing.yaml --var topic="Microservices Architecture"

# Output:
# Iteration 1: score=6, feedback="Needs more examples"
# Iteration 2: score=7, feedback="Good improvement, add diagrams"
# Iteration 3: score=7.5, feedback="Still missing best practices"
# ⏸  Quality Gate: manual_review
#    Quality not meeting threshold after 3 iterations
#    Current score: 7.5 (target: 8.0)
#
#    [a] Approve current version
#    [c] Continue optimization (2 iterations remaining)
#    [r] Reject and cancel
#    [m] Provide manual feedback
# Your choice: _
```

---

## Testing Strategy

### Unit Tests
- InterruptMetadata serialization
- InterruptResponse validation
- Condition evaluation (Jinja2)
- Timeout calculation
- Preview generation

### Integration Tests
- Chain pattern with manual gates
- Tool approval hooks
- Interactive CLI prompts (mocked stdin)
- Timeout and fallback actions
- Resume with approval/rejection/modification

### E2E Tests
- Full workflow with multiple gates
- Workflow pause → inspect → resume
- Tool approval with Strands SDK hooks
- Quality gates in evaluator-optimizer
- API endpoint integration

### User Acceptance Tests
- Research workflow with human review
- File operations with approval gates
- Long-running workflow pause/resume over days
- Integration with Slack/webhook

---

## Security Considerations

### Approval Bypass Prevention
- Require `--approve` flag explicitly (no auto-approve by default)
- Log all approval decisions to audit trail
- Optional: require authentication token for resume
- Optional: allowlist of approved users (via config)

### Timeout Safety
- Default timeout: 24 hours
- Max timeout: 7 days (configurable)
- Automatic cleanup of expired paused sessions
- Email/notification before timeout expires

### Data Privacy
- Preview length configurable (default: 500 chars)
- Redact sensitive data in previews (use telemetry redaction)
- Option to disable preview entirely
- Approval logs exclude full outputs

### Tool Approval Security
- Tools requiring approval explicitly marked in spec
- No bypass mechanism in production mode
- Optional: approval delegation (manager approves for team)

---

## Performance Considerations

### Pause Overhead
- Checkpoint save: <50ms (file-based), <200ms (S3)
- Session state size: ~10KB + output previews
- Preview generation: <10ms for 500 chars

### Resume Latency
- Session load: <100ms (file), <300ms (S3)
- State restoration: <50ms
- Agent initialization: ~500ms (warm start with cache)
- Total resume latency: <1s (typical)

### Interactive Mode
- Rich TUI overhead: <10ms per render
- No impact on non-interactive mode
- Input prompt blocks until response (by design)

---

## Documentation Requirements

### User Documentation
- **MANUAL.md**: Add HITL section with examples
- **QUICKSTART.md**: Add interactive mode example
- **README.md**: Feature list update
- New: **docs/HITL.md** - Comprehensive HITL guide

### Developer Documentation
- **CONTRIBUTING.md**: How to add manual gates to patterns
- **API_REFERENCE.md**: InterruptHandler protocol
- Integration examples (Slack, webhook, REST API)

### Migration Guide
- Existing workflows work unchanged
- Manual gates are opt-in
- Tool approval opt-in per tool
- No breaking changes

---

## Rollout Plan

### Week 1: Manual Gates in Chain Pattern
- [ ] Implement `manual_gate` step type
- [ ] Add `--approve/--reject/--modify` flags
- [ ] Chain executor pause/resume logic
- [ ] Unit and integration tests
- [ ] Internal testing with sample workflows

### Week 2: Interactive Mode & Tool Approvals
- [ ] Implement `--interactive` flag with Rich TUI
- [ ] Create `ToolApprovalHook`
- [ ] Add timeout and fallback actions
- [ ] Extend to 3 more patterns (workflow, parallel, routing)
- [ ] Beta testing with internal users

### Week 3: API & Production Hardening
- [ ] Python API: `InterruptHandler` protocol
- [ ] Extend to remaining patterns (evaluator, orchestrator, graph)
- [ ] Optional REST API service
- [ ] Documentation and examples
- [ ] Production rollout

---

## Success Metrics

### Functional Metrics
- [ ] All 7 patterns support manual gates
- [ ] Tool approval hooks work with Strands SDK
- [ ] Interactive mode provides good UX
- [ ] Resume latency <1s for typical workflows
- [ ] Test coverage ≥85%

### User Adoption (Post-Release)
- [ ] ≥5 internal workflows use manual gates
- [ ] ≥10 external users report successful HITL integration
- [ ] <3 HITL-related bug reports in first month
- [ ] ≥2 external integrations built (Slack, Jira, etc.)

---

## Dependencies

### Required
- **DURABLE.md**: Session persistence infrastructure (Phases 1-2)
- Strands SDK ≥1.0.0 with interrupt support

### Optional
- FastAPI (for REST API service)
- Slack SDK (for Slack integration example)
- Jira SDK (for Jira integration example)

---

## Future Enhancements (Post-v0.12.0)

### Multi-User Approvals
- Route approval to specific users/roles
- Require N-of-M approvals for critical actions
- Approval delegation chain

### Web UI
- React-based approval dashboard
- Visual workflow state inspector
- Bulk approval operations

### Advanced Notifications
- Email notifications on pause
- SMS alerts for urgent approvals
- Calendar integration for scheduled reviews

### Approval Policies
- Time-based auto-approval (business hours only)
- Context-based approval routing (cost, risk level)
- Compliance audit trail export

---

## References

### Strands SDK
- Interrupts: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/interrupts/
- Hooks: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/hooks/
- Session Management: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/session-management/
- ToolContext: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/python-tools/#toolcontext

### Strands CLI
- DURABLE.md: Session persistence design
- PLAN.md: Overall development roadmap
- CLAUDE.md: Project guidelines

---

**End of Proposal**

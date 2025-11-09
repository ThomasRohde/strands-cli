# HITL Implementation Plan
**Human-in-the-Loop Workflow Execution**

**Created:** 2025-11-09  
**Target Version:** v0.12.0  
**Duration:** 3 weeks  
**Status:** 🚀 Ready to Implement

---

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Phase 1: Manual Gate Infrastructure](#phase-1-manual-gate-infrastructure-week-1)
4. [Phase 2: Interactive Mode & Tool Approvals](#phase-2-interactive-mode--tool-approvals-week-2)
5. [Phase 3: API & Advanced Patterns](#phase-3-api--advanced-patterns-week-3)
6. [Testing Requirements](#testing-requirements)
7. [Definition of Done](#definition-of-done)

---

## Overview

### Goals
Implement Human-in-the-Loop (HITL) capabilities enabling:
- ✅ Manual approval gates at critical decision points
- ✅ Interactive input during workflow execution
- ✅ Tool approval before dangerous operations
- ✅ Quality control review gates
- ✅ Multi-day workflow pause/resume
- ✅ Programmatic API for external integrations

### Architecture Principles
- Leverage Strands SDK's native interrupt system (`event.interrupt()`, `tool_context.interrupt()`)
- CLI-based interaction with `--resume` and approval flags
- Pattern-agnostic (works across all 7 workflow types)
- State preservation via session management (DURABLE.md dependency)

### Key Components
```
Workflow → [INTERRUPT] → Session Save → Human Review → Resume → Continue
```

---

## Prerequisites

### Dependencies
- [x] ✅ **DURABLE.md Phases 1-2**: Session persistence infrastructure implemented
- [x] ✅ Strands SDK ≥1.14.0 with interrupt support
- [x] ✅ Rich console library for TUI
- [x] ✅ File-based session repository

### Development Environment
```powershell
# Verify environment
uv sync --dev
uv run strands --version  # Should be ≥0.11.0

# Verify session management
uv run strands sessions list

# Run full test suite
.\scripts\dev.ps1 ci
```

---

## Phase 1: Manual Gate Infrastructure (Week 1)

**Goal:** Basic manual gate support in chain pattern  
**Effort:** 5 days  
**Coverage Target:** ≥85%

### Task 1.1: Extend Session State Models
**File:** `src/strands_cli/types.py`  
**Effort:** 4 hours

#### Tasks
- [ ] Add `InterruptType` enum:
  ```python
  class InterruptType(str, Enum):
      MANUAL_GATE = "manual_gate"
      TOOL_APPROVAL = "tool_approval"
      QUALITY_GATE = "quality_gate"
      CONDITIONAL = "conditional"
  ```

- [ ] Add `InterruptMetadata` model:
  ```python
  class InterruptMetadata(BaseModel):
      interrupt_id: str
      interrupt_type: InterruptType
      interrupt_name: str
      prompt: str
      created_at: str  # ISO 8601
      timeout_at: str | None = None
      fallback_action: str = "continue"  # or "cancel"
      data_to_review: dict[str, Any] = Field(default_factory=dict)
      options: dict[str, str] = Field(default_factory=dict)
      condition: str | None = None
  ```

- [ ] Add `InterruptResponse` model:
  ```python
  class InterruptResponse(BaseModel):
      action: str  # "approve" | "reject" | "modify" | "defer"
      feedback: str | None = None
      variable_overrides: dict[str, str] = Field(default_factory=dict)
      provided_at: str  # ISO 8601
  ```

- [ ] Extend `SessionMetadata` with HITL fields:
  ```python
  class SessionMetadata(BaseModel):
      # ... existing fields ...
      interrupt_metadata: InterruptMetadata | None = None
      interrupt_history: list[InterruptMetadata] = Field(default_factory=list)
  ```

**Tests:**
- [ ] `test_interrupt_metadata_serialization`
- [ ] `test_interrupt_response_validation`
- [ ] `test_session_metadata_with_interrupt`

**Acceptance:**
- ✅ All models pass strict mypy validation
- ✅ Pydantic validation catches invalid interrupt states
- ✅ JSON serialization/deserialization works correctly

---

### Task 1.2: Add Manual Gate Step Type to Schema
**File:** `src/strands_cli/schema/strands-workflow.schema.json`  
**Effort:** 3 hours

#### Tasks
- [ ] Add `manual_gate` step type to chain pattern config:
  ```json
  {
    "type": "object",
    "properties": {
      "type": {"const": "manual_gate"},
      "id": {"type": "string"},
      "prompt": {"type": "string"},
      "timeout_minutes": {"type": "integer", "minimum": 1},
      "fallback_action": {"enum": ["continue", "cancel"]},
      "show_preview": {"type": "boolean"},
      "preview_length": {"type": "integer", "default": 500},
      "condition": {"type": "string"}
    },
    "required": ["type", "id", "prompt"]
  }
  ```

- [ ] Update `ChainStep` model in `types.py`:
  ```python
  class ChainStep(BaseModel):
      type: str | None = None  # "manual_gate" or None (agent step)
      agent: str | None = None
      id: str | None = None
      prompt: str | None = None
      timeout_minutes: int | None = None
      fallback_action: str | None = None
      show_preview: bool = True
      preview_length: int = 500
      condition: str | None = None
      # ... existing fields ...
  ```

- [ ] Add discriminated union validation to enforce either agent or manual_gate

**Tests:**
- [ ] `test_schema_validates_manual_gate_step`
- [ ] `test_schema_rejects_manual_gate_without_id`
- [ ] `test_chain_step_with_manual_gate_parses`

**Acceptance:**
- ✅ Schema validation accepts valid manual gate specs
- ✅ Capability checker recognizes manual gates (no unsupported error)
- ✅ Example specs validate successfully

---

### Task 1.3: Create InterruptPending Exception
**File:** `src/strands_cli/runtime/exceptions.py` (new file)  
**Effort:** 1 hour

#### Tasks
- [ ] Create exception hierarchy:
  ```python
  class InterruptPending(Exception):
      """Raised when workflow pauses for human input."""
      
      def __init__(
          self,
          session_id: str,
          interrupt_metadata: InterruptMetadata
      ):
          self.session_id = session_id
          self.interrupt_metadata = interrupt_metadata
          super().__init__(f"Workflow paused: {interrupt_metadata.prompt}")
  
  class WorkflowRejectedError(Exception):
      """Raised when human rejects workflow continuation."""
      pass
  ```

- [ ] Import in `__init__.py` for easy access

**Tests:**
- [ ] `test_interrupt_pending_exception_creation`
- [ ] `test_interrupt_pending_preserves_metadata`

**Acceptance:**
- ✅ Exception carries all necessary context for pause/resume
- ✅ Can be serialized to session state

---

### Task 1.4: Implement Manual Gate Logic in Chain Executor
**File:** `src/strands_cli/exec/chain.py`  
**Effort:** 8 hours

#### Tasks
- [ ] Add `interrupt_response` parameter to `run_chain()`:
  ```python
  async def run_chain(
      spec: Spec,
      variables: dict[str, str] | None = None,
      session_state: SessionState | None = None,
      session_repo: FileSessionRepository | None = None,
      interrupt_response: InterruptResponse | None = None
  ) -> RunResult:
  ```

- [ ] Detect manual gate steps in loop:
  ```python
  for step_index in range(start_step, len(steps)):
      step = steps[step_index]
      
      if step.type == "manual_gate":
          # Handle manual gate logic
  ```

- [ ] Implement pause logic:
  ```python
  # If resuming with approval, skip gate
  if interrupt_response and interrupt_response.action == "approve":
      logger.info("manual_gate_approved", gate_id=step.id)
      continue
  
  # If reject, stop workflow
  if interrupt_response and interrupt_response.action == "reject":
      raise WorkflowRejectedError(f"Manual gate rejected: {step.id}")
  
  # If modify, retry previous step with feedback
  if interrupt_response and interrupt_response.action == "modify":
      step_index -= 1
      context["human_feedback"] = interrupt_response.feedback
      continue
  
  # Evaluate condition (if present)
  if step.condition:
      condition_met = evaluate_condition(step.condition, context)
      if not condition_met:
          continue
  
  # Pause workflow
  interrupt_meta = create_interrupt_metadata(step, context, step_index)
  
  if session_repo and session_state:
      session_state.metadata.status = SessionStatus.PAUSED
      session_state.metadata.interrupt_metadata = interrupt_meta
      session_state.pattern_state["current_step"] = step_index
      session_repo.save(session_state, spec_content="...")
  
  raise InterruptPending(session_state.metadata.session_id, interrupt_meta)
  ```

- [ ] Add helper functions:
  ```python
  def create_interrupt_metadata(
      step: ChainStep,
      context: dict[str, Any],
      step_index: int
  ) -> InterruptMetadata:
      """Create interrupt metadata from manual gate step."""
      return InterruptMetadata(
          interrupt_id=f"gate-{step.id}",
          interrupt_type=InterruptType.MANUAL_GATE,
          interrupt_name=step.id,
          prompt=render_template(step.prompt, context),
          created_at=now_iso8601(),
          timeout_at=calculate_timeout(step.timeout_minutes),
          fallback_action=step.fallback_action or "continue",
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
  
  def evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
      """Evaluate Jinja2 condition expression."""
      from jinja2 import Template
      template = Template(f"{{{{% if {condition} %}}}}true{{{{% endif %}}}}")
      result = template.render(context)
      return result.strip() == "true"
  ```

**Tests:**
- [ ] `test_chain_pauses_at_manual_gate`
- [ ] `test_chain_resume_with_approval`
- [ ] `test_chain_resume_with_rejection`
- [ ] `test_chain_resume_with_modification`
- [ ] `test_manual_gate_condition_evaluation`
- [ ] `test_manual_gate_skipped_when_condition_false`
- [ ] `test_interrupt_metadata_includes_preview`

**Acceptance:**
- ✅ Chain executor detects manual gates and pauses
- ✅ Session saved with PAUSED status and interrupt metadata
- ✅ InterruptPending exception raised with full context
- ✅ Conditional gates only trigger when condition met

---

### Task 1.5: Add Resume Flags to CLI
**File:** `src/strands_cli/__main__.py`  
**Effort:** 4 hours

#### Tasks
- [ ] Add flags to `resume` command:
  ```python
  @app.command()
  def resume(
      session_id: Annotated[str, typer.Argument(...)],
      approve: Annotated[bool, typer.Option("--approve")] = False,
      reject: Annotated[bool, typer.Option("--reject")] = False,
      modify: Annotated[bool, typer.Option("--modify")] = False,
      feedback: Annotated[str | None, typer.Option("--feedback")] = None,
      var: Annotated[list[str] | None, typer.Option("--var")] = None,
      verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
  ) -> None:
      """Resume a paused workflow with human decision."""
  ```

- [ ] Validate flags are mutually exclusive:
  ```python
  flags_set = sum([approve, reject, modify])
  if flags_set > 1:
      console.print("[red]Error:[/] Only one of --approve, --reject, --modify allowed")
      sys.exit(EX_USAGE)
  
  if flags_set == 0:
      console.print("[red]Error:[/] Must specify --approve, --reject, or --modify")
      sys.exit(EX_USAGE)
  
  if modify and not feedback:
      console.print("[red]Error:[/] --modify requires --feedback")
      sys.exit(EX_USAGE)
  ```

- [ ] Build `InterruptResponse`:
  ```python
  action = "approve" if approve else "reject" if reject else "modify"
  variable_overrides = parse_variables(var) if var else {}
  
  interrupt_response = InterruptResponse(
      action=action,
      feedback=feedback,
      variable_overrides=variable_overrides,
      provided_at=now_iso8601()
  )
  ```

- [ ] Pass to executor:
  ```python
  # Load session and spec
  session_state = session_repo.load(session_id)
  spec = load_spec(session_state.metadata.spec_path)
  
  # Execute with interrupt response
  result = await run_chain(
      spec=spec,
      variables=session_state.variables,
      session_state=session_state,
      session_repo=session_repo,
      interrupt_response=interrupt_response
  )
  ```

- [ ] Handle `WorkflowRejectedError`:
  ```python
  try:
      result = await executor(...)
  except WorkflowRejectedError as e:
      console.print(f"[yellow]Workflow rejected:[/] {e}")
      session_state.metadata.status = SessionStatus.FAILED
      session_state.metadata.error = str(e)
      session_repo.save(session_state, spec_content="...")
      sys.exit(EX_OK)  # Successful rejection
  ```

**Tests:**
- [ ] `test_resume_command_with_approve_flag`
- [ ] `test_resume_command_with_reject_flag`
- [ ] `test_resume_command_with_modify_flag`
- [ ] `test_resume_command_validates_mutually_exclusive_flags`
- [ ] `test_resume_command_requires_feedback_with_modify`

**Acceptance:**
- ✅ `strands resume <id> --approve` continues workflow
- ✅ `strands resume <id> --reject` stops workflow gracefully
- ✅ `strands resume <id> --modify --feedback "..."` retries with feedback
- ✅ Proper error messages for invalid flag combinations

---

### Task 1.6: Update Run Command to Handle Interrupts
**File:** `src/strands_cli/__main__.py`  
**Effort:** 2 hours

#### Tasks
- [ ] Catch `InterruptPending` in run command:
  ```python
  try:
      result = asyncio.run(run_chain(spec, variables, ...))
  except InterruptPending as e:
      console.print()
      console.print(f"[yellow]⏸  Manual gate: {e.interrupt_metadata.interrupt_name}[/]")
      console.print(f"   → {e.interrupt_metadata.prompt}")
      console.print()
      console.print(f"   Session ID: [cyan]{e.session_id}[/]")
      console.print(f"   Use: [bold]strands resume {e.session_id} --approve[/]")
      sys.exit(EX_OK)  # Successful pause
  ```

- [ ] Add to exit codes if needed (already have EX_OK)

**Tests:**
- [ ] `test_run_command_handles_interrupt_pending`
- [ ] `test_run_command_displays_resume_instructions`

**Acceptance:**
- ✅ Run command displays helpful pause message
- ✅ Shows session ID and resume command
- ✅ Exits cleanly with EX_OK

---

### Phase 1 Deliverables Checklist
- [ ] **Models:** InterruptMetadata, InterruptResponse, extended SessionMetadata
- [ ] **Schema:** Manual gate step type in JSON Schema
- [ ] **Executor:** Chain pattern supports manual gates with pause/resume
- [ ] **CLI:** `--approve`, `--reject`, `--modify` flags work
- [ ] **Tests:** ≥20 new tests, coverage ≥85%
- [ ] **Example:** `examples/chain-manual-gate-demo.yaml` works end-to-end
- [ ] **Docs:** Updated MANUAL.md with manual gate examples

**Exit Criteria:**
```powershell
# All tests pass
.\scripts\dev.ps1 test

# Coverage ≥85%
.\scripts\dev.ps1 test-cov

# Example workflow works
uv run strands run examples/chain-manual-gate-demo.yaml --var topic="AI Safety"
# (pauses at gate)
uv run strands resume <session-id> --approve
# (completes successfully)
```

---

## Phase 2: Interactive Mode & Tool Approvals (Week 2)

**Goal:** CLI interactive mode and tool approval hooks  
**Effort:** 5 days  
**Coverage Target:** ≥85%

### Task 2.1: Implement Interactive CLI Mode
**File:** `src/strands_cli/hitl/interactive.py` (new file)  
**Effort:** 6 hours

#### Tasks
- [ ] Create interactive handler module:
  ```python
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
      
      # Show preview
      if interrupt_meta.data_to_review.get("preview"):
          console.print("\n[bold]Preview:[/]")
          console.print(Panel(
              interrupt_meta.data_to_review["preview"],
              border_style="dim"
          ))
      
      # Show options
      console.print("\n[bold]Options:[/]")
      for key, desc in interrupt_meta.options.items():
          console.print(f"  [{key[0]}] {desc}")
      console.print(f"  [v] View full output")
      console.print(f"  [d] Defer - Save and exit")
      
      # Prompt user
      while True:
          choice = Prompt.ask(
              "\nYour choice",
              choices=["a", "r", "m", "v", "d"]
          )
          
          if choice == "a":
              return InterruptResponse(
                  action="approve",
                  provided_at=now_iso8601()
              )
          elif choice == "r":
              reason = Prompt.ask("Reason (optional)", default="")
              return InterruptResponse(
                  action="reject",
                  feedback=reason,
                  provided_at=now_iso8601()
              )
          elif choice == "m":
              feedback = Prompt.ask("Provide feedback")
              return InterruptResponse(
                  action="modify",
                  feedback=feedback,
                  provided_at=now_iso8601()
              )
          elif choice == "v":
              show_full_output(interrupt_meta.data_to_review)
              continue
          elif choice == "d":
              console.print(f"\n[yellow]Session saved.[/]")
              console.print(f"Resume: [bold]strands resume {session_id} --approve[/]")
              sys.exit(EX_OK)
  
  def show_full_output(data: dict[str, Any]) -> None:
      """Display full output in pager."""
      output = data.get("output", "No output available")
      console.print(Panel(output, title="Full Output"))
  ```

- [ ] Add `--interactive` flag to run command:
  ```python
  @app.command()
  def run(
      spec_file: Annotated[str, typer.Argument(...)],
      var: Annotated[list[str] | None, typer.Option("--var")] = None,
      interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
      verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
  ) -> None:
  ```

- [ ] Integrate interactive handler:
  ```python
  try:
      result = asyncio.run(run_chain(...))
  except InterruptPending as e:
      if interactive:
          # Handle interactively
          response = handle_interrupt_interactive(
              e.interrupt_metadata,
              e.session_id
          )
          # Continue execution immediately
          result = asyncio.run(run_chain(
              ...,
              interrupt_response=response
          ))
      else:
          # Display pause message and exit
          display_pause_message(e)
          sys.exit(EX_OK)
  ```

**Tests:**
- [ ] `test_interactive_handler_approve` (mock stdin)
- [ ] `test_interactive_handler_reject` (mock stdin)
- [ ] `test_interactive_handler_modify` (mock stdin)
- [ ] `test_interactive_handler_defer` (mock stdin)
- [ ] `test_run_command_with_interactive_flag`

**Acceptance:**
- ✅ Interactive mode displays rich TUI
- ✅ User can approve/reject/modify inline
- ✅ Defer option saves and exits gracefully
- ✅ Full output viewer works

---

### Task 2.2: Implement Tool Approval Hook
**File:** `src/strands_cli/runtime/tool_approval.py` (new file)  
**Effort:** 8 hours

#### Tasks
- [ ] Create tool approval hook using Strands SDK:
  ```python
  from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent
  
  class ToolApprovalHook(HookProvider):
      """Hook to request approval before tool execution."""
      
      def __init__(
          self,
          session_repo: FileSessionRepository,
          session_state: SessionState,
          tools_requiring_approval: set[str],
          interactive: bool = False
      ):
          self.session_repo = session_repo
          self.session_state = session_state
          self.tools_requiring_approval = tools_requiring_approval
          self.interactive = interactive
      
      def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
          registry.add_callback(BeforeToolCallEvent, self.request_approval)
      
      def request_approval(self, event: BeforeToolCallEvent) -> None:
          """Request approval before tool execution."""
          tool_name = event.tool_use["name"]
          
          if tool_name not in self.tools_requiring_approval:
              return
          
          if self.interactive:
              # Interactive approval
              approved = self._prompt_interactive_approval(
                  tool_name,
                  event.tool_use["input"]
              )
              if not approved:
                  event.cancel_tool = f"Tool denied by user: {tool_name}"
                  logger.info("tool_denied", tool=tool_name)
          else:
              # Pause workflow for later approval
              interrupt_meta = InterruptMetadata(
                  interrupt_id=f"tool-{tool_name}",
                  interrupt_type=InterruptType.TOOL_APPROVAL,
                  interrupt_name=tool_name,
                  prompt=f"Approve execution of {tool_name}?",
                  created_at=now_iso8601(),
                  data_to_review={
                      "tool": tool_name,
                      "input": event.tool_use["input"]
                  },
                  options={
                      "approve": f"Execute {tool_name}",
                      "reject": "Cancel execution"
                  }
              )
              
              self.session_state.metadata.status = SessionStatus.PAUSED
              self.session_state.metadata.interrupt_metadata = interrupt_meta
              self.session_repo.save(self.session_state, spec_content="...")
              
              raise InterruptPending(
                  self.session_state.metadata.session_id,
                  interrupt_meta
              )
      
      def _prompt_interactive_approval(
          self,
          tool_name: str,
          tool_input: dict[str, Any]
      ) -> bool:
          """Prompt user for interactive tool approval."""
          console.print()
          console.print(Panel(
              f"[bold yellow]Tool Approval Required[/]\n\n"
              f"Tool: {tool_name}\n"
              f"Input: {json.dumps(tool_input, indent=2)}",
              title="⚠ Approval Required",
              border_style="yellow"
          ))
          
          choice = Prompt.ask("Approve?", choices=["y", "n"])
          return choice == "y"
  ```

- [ ] Add `require_approval` field to tool configs in schema:
  ```json
  "python": {
    "type": "array",
    "items": {
      "oneOf": [
        {"type": "string"},
        {
          "type": "object",
          "properties": {
            "callable": {"type": "string"},
            "require_approval": {"type": "boolean"}
          }
        }
      ]
    }
  }
  ```

- [ ] Update `PythonTool` model:
  ```python
  class PythonTool(BaseModel):
      callable: str
      require_approval: bool = False
  ```

- [ ] Integrate hook in agent builder:
  ```python
  def build_agent_with_tool_approval(
      spec: Spec,
      agent_config: Agent,
      tools_requiring_approval: set[str],
      session_state: SessionState,
      session_repo: FileSessionRepository,
      interactive: bool
  ) -> StrandsAgent:
      """Build agent with tool approval hook."""
      
      agent = build_agent(spec, agent_config, ...)
      
      if tools_requiring_approval:
          hook = ToolApprovalHook(
              session_repo,
              session_state,
              tools_requiring_approval,
              interactive
          )
          agent.hooks.append(hook)
      
      return agent
  ```

**Tests:**
- [ ] `test_tool_approval_hook_allows_safe_tools`
- [ ] `test_tool_approval_hook_pauses_for_dangerous_tools`
- [ ] `test_tool_approval_hook_interactive_approve`
- [ ] `test_tool_approval_hook_interactive_deny`
- [ ] `test_tool_approval_integrates_with_agent`

**Acceptance:**
- ✅ Tools marked with `require_approval: true` trigger pause
- ✅ Interactive mode prompts immediately
- ✅ Non-interactive mode saves session and exits
- ✅ Approval/denial propagates to agent correctly

---

### Task 2.3: Add Timeout and Fallback Actions
**File:** `src/strands_cli/exec/chain.py`  
**Effort:** 3 hours

#### Tasks
- [ ] Implement timeout checking:
  ```python
  def check_interrupt_timeout(interrupt_meta: InterruptMetadata) -> bool:
      """Check if interrupt has timed out."""
      if not interrupt_meta.timeout_at:
          return False
      
      from datetime import datetime
      timeout_dt = datetime.fromisoformat(interrupt_meta.timeout_at)
      now_dt = datetime.now(timezone.utc)
      
      return now_dt > timeout_dt
  ```

- [ ] Apply fallback action on timeout:
  ```python
  # In chain executor
  if session_state.metadata.interrupt_metadata:
      interrupt = session_state.metadata.interrupt_metadata
      
      if check_interrupt_timeout(interrupt):
          logger.warning(
              "interrupt_timeout",
              interrupt_id=interrupt.interrupt_id,
              fallback=interrupt.fallback_action
          )
          
          if interrupt.fallback_action == "cancel":
              raise WorkflowRejectedError("Manual gate timeout (cancelled)")
          elif interrupt.fallback_action == "continue":
              # Auto-approve and continue
              interrupt_response = InterruptResponse(
                  action="approve",
                  feedback="Auto-approved due to timeout",
                  provided_at=now_iso8601()
              )
  ```

- [ ] Add timeout check to resume command:
  ```python
  # In resume command
  if session_state.metadata.interrupt_metadata:
      if check_interrupt_timeout(session_state.metadata.interrupt_metadata):
          console.print("[yellow]Warning:[/] Interrupt has timed out")
          # Apply fallback automatically
  ```

**Tests:**
- [ ] `test_interrupt_timeout_check_returns_true_after_timeout`
- [ ] `test_interrupt_timeout_applies_fallback_continue`
- [ ] `test_interrupt_timeout_applies_fallback_cancel`
- [ ] `test_resume_command_warns_on_timeout`

**Acceptance:**
- ✅ Timeouts calculated correctly from `timeout_minutes`
- ✅ Fallback actions applied automatically
- ✅ Warnings logged for timeout events

---

### Task 2.4: Add Conditional Interrupts
**File:** `src/strands_cli/exec/chain.py`  
**Effort:** 2 hours

#### Tasks
- [ ] Already implemented in Task 1.4 (condition evaluation)
- [ ] Add tests for edge cases:
  - [ ] Complex Jinja2 conditions
  - [ ] Conditions with template variables
  - [ ] Invalid conditions (error handling)

**Tests:**
- [ ] `test_conditional_interrupt_with_complex_expression`
- [ ] `test_conditional_interrupt_with_variables`
- [ ] `test_conditional_interrupt_invalid_expression_logs_error`

**Acceptance:**
- ✅ Supports Jinja2 expressions in `condition` field
- ✅ Invalid conditions log errors and skip gate

---

### Task 2.5: Extend to Workflow, Parallel, Routing Patterns
**Files:**
- `src/strands_cli/exec/workflow.py`
- `src/strands_cli/exec/parallel.py`
- `src/strands_cli/exec/routing.py`

**Effort:** 6 hours total (2 hours each)

#### Tasks (per pattern)
- [ ] Add `interrupt_response` parameter
- [ ] Add manual gate detection logic (similar to chain)
- [ ] Handle pause/resume for pattern-specific context
- [ ] Update pattern state serialization

**Tests (per pattern):**
- [ ] `test_<pattern>_pauses_at_manual_gate`
- [ ] `test_<pattern>_resume_with_approval`
- [ ] `test_<pattern>_resume_with_rejection`

**Acceptance:**
- ✅ Workflow pattern supports manual gates
- ✅ Parallel pattern supports manual gates (per branch)
- ✅ Routing pattern supports manual gates

---

### Phase 2 Deliverables Checklist
- [ ] **Interactive Mode:** Rich TUI for inline approval
- [ ] **Tool Approval:** Hook system for dangerous tools
- [ ] **Timeouts:** Automatic fallback on timeout
- [ ] **Conditional Gates:** Jinja2 condition evaluation
- [ ] **Pattern Support:** Chain, workflow, parallel, routing all work
- [ ] **Tests:** ≥30 new tests, coverage ≥85%
- [ ] **Examples:**
  - `examples/interactive-mode-demo.yaml`
  - `examples/tool-approval-demo.yaml`
- [ ] **Docs:** MANUAL.md updated with interactive mode

**Exit Criteria:**
```powershell
# Interactive mode works
uv run strands run examples/interactive-mode-demo.yaml --interactive

# Tool approval works
uv run strands run examples/tool-approval-demo.yaml --interactive

# All 4 patterns support manual gates
.\scripts\dev.ps1 test -k manual_gate
```

---

## Phase 3: API & Advanced Patterns (Week 3)

**Goal:** Programmatic API and full pattern support  
**Effort:** 5 days  
**Coverage Target:** ≥85%

### Task 3.1: Create InterruptHandler Protocol
**File:** `src/strands_cli/hitl/handler.py` (new file)  
**Effort:** 3 hours

#### Tasks
- [ ] Define protocol:
  ```python
  from typing import Protocol
  
  class InterruptHandler(Protocol):
      """Protocol for custom interrupt handlers."""
      
      async def handle_interrupt(
          self,
          interrupt_meta: InterruptMetadata,
          session_id: str
      ) -> InterruptResponse:
          """Handle interrupt and return response.
          
          This method is called when workflow pauses at an interrupt point.
          Implementations can integrate with external systems (Slack, webhooks, etc.)
          
          Args:
              interrupt_meta: Details about the interrupt
              session_id: Session ID for this workflow
          
          Returns:
              InterruptResponse with action (approve/reject/modify)
          """
          ...
  ```

- [ ] Create webhook handler example:
  ```python
  class WebhookInterruptHandler:
      """Handler that sends webhook and polls for response."""
      
      def __init__(self, webhook_url: str, poll_interval: int = 5):
          self.webhook_url = webhook_url
          self.poll_interval = poll_interval
      
      async def handle_interrupt(
          self,
          interrupt_meta: InterruptMetadata,
          session_id: str
      ) -> InterruptResponse:
          """Send webhook and wait for response."""
          
          # Send webhook
          await httpx.post(self.webhook_url, json={
              "session_id": session_id,
              "interrupt": interrupt_meta.model_dump()
          })
          
          # Poll for response (or timeout)
          # ... implementation ...
          
          return InterruptResponse(...)
  ```

**Tests:**
- [ ] `test_interrupt_handler_protocol_compliance`
- [ ] `test_webhook_handler_sends_webhook`
- [ ] `test_webhook_handler_polls_for_response`

**Acceptance:**
- ✅ Protocol is well-documented
- ✅ Example handler implementations work
- ✅ Can be used in `run_workflow_async()`

---

### Task 3.2: Implement run_workflow_async()
**File:** `src/strands_cli/api/__init__.py` (new file)  
**Effort:** 4 hours

#### Tasks
- [ ] Create async API function:
  ```python
  async def run_workflow_async(
      spec_path: Path | None = None,
      spec: Spec | None = None,
      variables: dict[str, str] | None = None,
      session_id: str | None = None,
      interrupt_handler: InterruptHandler | None = None,
      interrupt_response: InterruptResponse | None = None
  ) -> RunResult:
      """Run workflow with optional HITL support.
      
      Args:
          spec_path: Path to workflow spec (if not resuming)
          spec: Pre-loaded spec (alternative to spec_path)
          variables: Workflow variables
          session_id: Session ID (for resume)
          interrupt_handler: Custom interrupt handler
          interrupt_response: Response to pending interrupt
      
      Returns:
          RunResult on completion
      
      Raises:
          InterruptPending: If workflow pauses for human input
      """
      
      # Load or resume
      if session_id:
          session_repo = FileSessionRepository()
          session_state = session_repo.load(session_id)
          spec = load_spec(session_state.metadata.spec_path)
      else:
          spec = spec or load_spec(spec_path)
      
      # Execute with interrupt handling
      try:
          executor = get_executor(spec.pattern.type)
          result = await executor(
              spec,
              variables,
              interrupt_response=interrupt_response
          )
          return result
      except InterruptPending as e:
          if interrupt_handler:
              # Handle with custom handler
              response = await interrupt_handler.handle_interrupt(
                  e.interrupt_metadata,
                  e.session_id
              )
              # Retry with response
              return await run_workflow_async(
                  spec=spec,
                  session_id=e.session_id,
                  interrupt_response=response,
                  interrupt_handler=interrupt_handler
              )
          else:
              # Re-raise for caller to handle
              raise
  ```

**Tests:**
- [ ] `test_run_workflow_async_completes_without_interrupts`
- [ ] `test_run_workflow_async_raises_interrupt_pending`
- [ ] `test_run_workflow_async_with_custom_handler`
- [ ] `test_run_workflow_async_resume_from_session`

**Acceptance:**
- ✅ API function is async-native
- ✅ Works with custom interrupt handlers
- ✅ Supports resume from session ID

---

### Task 3.3: Add Quality Gates to Evaluator-Optimizer
**File:** `src/strands_cli/exec/evaluator_optimizer.py`  
**Effort:** 3 hours

#### Tasks
- [ ] Add manual review config to schema:
  ```json
  "accept": {
    "properties": {
      "manual_review": {
        "type": "object",
        "properties": {
          "after_iterations": {"type": "integer", "minimum": 1},
          "prompt": {"type": "string"},
          "options": {
            "type": "object",
            "additionalProperties": {"type": "string"}
          }
        }
      }
    }
  }
  ```

- [ ] Extend `AcceptConfig` model:
  ```python
  class ManualReviewConfig(BaseModel):
      after_iterations: int
      prompt: str
      options: dict[str, str] | None = None
  
  class AcceptConfig(BaseModel):
      min_score: int
      max_iters: int
      manual_review: ManualReviewConfig | None = None
  ```

- [ ] Implement in evaluator executor:
  ```python
  # In evaluator loop
  if iteration >= accept.manual_review.after_iterations:
      if score < accept.min_score:
          # Trigger manual review
          interrupt_meta = InterruptMetadata(
              interrupt_id=f"quality-gate-iter-{iteration}",
              interrupt_type=InterruptType.QUALITY_GATE,
              interrupt_name="quality_review",
              prompt=accept.manual_review.prompt,
              created_at=now_iso8601(),
              data_to_review={
                  "iteration": iteration,
                  "score": score,
                  "target": accept.min_score,
                  "output": producer_output
              },
              options=accept.manual_review.options or {
                  "approve": "Accept current version",
                  "continue": "Continue optimization",
                  "reject": "Cancel workflow"
              }
          )
          
          # Pause workflow
          raise InterruptPending(session_id, interrupt_meta)
  ```

**Tests:**
- [ ] `test_evaluator_quality_gate_after_iterations`
- [ ] `test_evaluator_quality_gate_with_approval`
- [ ] `test_evaluator_quality_gate_with_continue`

**Acceptance:**
- ✅ Quality gates trigger after specified iterations
- ✅ Approval accepts current output
- ✅ Continue resumes optimization loop

---

### Task 3.4: Add Manual Gates to Orchestrator-Workers
**File:** `src/strands_cli/exec/orchestrator.py`  
**Effort:** 2 hours

#### Tasks
- [ ] Add manual gate support between orchestrator rounds
- [ ] Pattern similar to chain (detect manual_gate steps)
- [ ] Save orchestrator state with delegation progress

**Tests:**
- [ ] `test_orchestrator_pauses_at_manual_gate`
- [ ] `test_orchestrator_resume_continues_delegation`

**Acceptance:**
- ✅ Orchestrator pattern supports manual gates

---

### Task 3.5: Add Manual Gates to Graph Pattern
**File:** `src/strands_cli/exec/graph.py`  
**Effort:** 2 hours

#### Tasks
- [ ] Add manual gate nodes to graph
- [ ] Pattern similar to chain
- [ ] Save graph state with current node position

**Tests:**
- [ ] `test_graph_pauses_at_manual_gate_node`
- [ ] `test_graph_resume_continues_from_node`

**Acceptance:**
- ✅ Graph pattern supports manual gates

---

### Task 3.6: Documentation and Examples
**Files:**
- `docs/HITL.md` (new comprehensive guide)
- `docs/MANUAL.md` (add HITL section)
- `examples/` (multiple examples)

**Effort:** 4 hours

#### Tasks
- [ ] Create comprehensive HITL guide:
  - Overview and use cases
  - CLI usage examples
  - Interactive mode guide
  - Tool approval configuration
  - Programmatic API examples
  - Integration patterns (Slack, webhooks)

- [ ] Add to MANUAL.md:
  - Manual gate step type
  - Resume command flags
  - Interactive mode flag

- [ ] Create examples:
  - `examples/hitl-research-review.yaml`
  - `examples/hitl-tool-approval.yaml`
  - `examples/hitl-quality-gate.yaml`
  - `examples/hitl-conditional-gate.yaml`
  - `examples/hitl-api-integration.py`

**Acceptance:**
- ✅ Documentation is comprehensive and clear
- ✅ Examples are runnable and educational

---

### Task 3.7: Optional REST API Service
**File:** `src/strands_cli/api/rest.py` (new file)  
**Effort:** 6 hours (OPTIONAL)

#### Tasks
- [ ] Create FastAPI service with endpoints:
  - `POST /workflows/run` - Start workflow
  - `POST /workflows/resume` - Resume with response
  - `GET /workflows/{id}` - Get status
  - `GET /workflows/{id}/interrupt` - Get interrupt details

- [ ] Add authentication (API key)
- [ ] Add CORS configuration
- [ ] Deploy documentation

**Tests:**
- [ ] `test_rest_api_run_workflow`
- [ ] `test_rest_api_resume_workflow`
- [ ] `test_rest_api_get_status`

**Acceptance:**
- ✅ REST API is functional (if implemented)
- ✅ OpenAPI documentation available

---

### Phase 3 Deliverables Checklist
- [ ] **API:** `run_workflow_async()` with InterruptHandler protocol
- [ ] **Patterns:** All 7 patterns support manual gates
- [ ] **Quality Gates:** Evaluator-optimizer pattern
- [ ] **Tests:** ≥25 new tests, coverage ≥85%
- [ ] **Documentation:** Comprehensive HITL guide
- [ ] **Examples:** 5+ examples covering all features
- [ ] **Optional:** REST API service

**Exit Criteria:**
```powershell
# All patterns work
.\scripts\dev.ps1 test -k hitl

# API works
uv run python examples/hitl-api-integration.py

# Documentation complete
ls docs/HITL.md

# All examples validate
.\scripts\dev.ps1 validate-examples
```

---

## Testing Requirements

### Unit Tests (≥75 tests total)
**Coverage Target:** ≥85%

#### Phase 1 Tests (~20)
- [ ] Interrupt metadata serialization
- [ ] Interrupt response validation
- [ ] Session state with interrupts
- [ ] Chain executor pause/resume logic
- [ ] Manual gate condition evaluation
- [ ] CLI resume command flags
- [ ] Timeout calculation
- [ ] Fallback action logic

#### Phase 2 Tests (~30)
- [ ] Interactive handler (mock stdin)
- [ ] Tool approval hook
- [ ] Timeout enforcement
- [ ] Conditional interrupts
- [ ] Workflow pattern gates
- [ ] Parallel pattern gates
- [ ] Routing pattern gates
- [ ] Preview generation

#### Phase 3 Tests (~25)
- [ ] InterruptHandler protocol
- [ ] `run_workflow_async()` API
- [ ] Quality gates in evaluator
- [ ] Orchestrator gates
- [ ] Graph gates
- [ ] Webhook handler
- [ ] Custom handler integration

### Integration Tests (~15)
- [ ] End-to-end chain with manual gate
- [ ] Interactive mode full workflow
- [ ] Tool approval integration
- [ ] Quality gate with evaluator
- [ ] Timeout and fallback
- [ ] API with custom handler

### E2E Tests (~5)
- [ ] Multi-gate workflow with resume
- [ ] Interactive session across patterns
- [ ] Tool approval with real tools (safe)
- [ ] Conditional gates with complex conditions
- [ ] API integration with webhook

### Test Execution
```powershell
# Run all HITL tests
.\scripts\dev.ps1 test -k hitl

# Run with coverage
.\scripts\dev.ps1 test-cov -k hitl

# Run integration tests only
.\scripts\dev.ps1 test -k integration

# Run E2E tests
.\scripts\dev.ps1 test -k e2e
```

---

## Definition of Done

### Phase 1 Complete When:
- [x] ✅ All Phase 1 tasks completed
- [x] ✅ ≥20 tests passing with ≥85% coverage
- [x] ✅ Chain pattern supports manual gates
- [x] ✅ Resume command works with --approve/--reject/--modify
- [x] ✅ Example workflow demonstrates pause/resume
- [x] ✅ No regressions in existing tests
- [x] ✅ Code review approved
- [x] ✅ Documentation updated

### Phase 2 Complete When:
- [x] ✅ All Phase 2 tasks completed
- [x] ✅ ≥30 new tests passing with ≥85% coverage
- [x] ✅ Interactive mode works with Rich TUI
- [x] ✅ Tool approval hooks functional
- [x] ✅ Timeouts and fallbacks enforced
- [x] ✅ 4 patterns support manual gates (chain, workflow, parallel, routing)
- [x] ✅ Examples demonstrate all features
- [x] ✅ No regressions
- [x] ✅ Code review approved
- [x] ✅ Documentation updated

### Phase 3 Complete When:
- [x] ✅ All Phase 3 tasks completed
- [x] ✅ ≥25 new tests passing with ≥85% coverage
- [x] ✅ All 7 patterns support manual gates
- [x] ✅ Programmatic API works with custom handlers
- [x] ✅ Quality gates in evaluator pattern
- [x] ✅ Comprehensive documentation published
- [x] ✅ 5+ examples available
- [x] ✅ No regressions
- [x] ✅ Code review approved
- [x] ✅ Release notes drafted

### Release Ready When:
- [x] ✅ All 3 phases complete
- [x] ✅ ≥75 total HITL tests passing
- [x] ✅ Overall coverage ≥85%
- [x] ✅ All examples validate successfully
- [x] ✅ Documentation complete (HITL.md, MANUAL.md)
- [x] ✅ CHANGELOG.md updated
- [x] ✅ Version bumped to v0.12.0
- [x] ✅ Git tag created
- [x] ✅ Release announcement prepared

---

## Development Workflow

### Daily Standup Questions
1. What did I complete yesterday?
2. What am I working on today?
3. Any blockers or dependencies?

### Before Each Commit
```powershell
# Lint and format
.\scripts\dev.ps1 format
.\scripts\dev.ps1 lint

# Type check
.\scripts\dev.ps1 typecheck

# Run tests
.\scripts\dev.ps1 test

# Coverage check
.\scripts\dev.ps1 test-cov
```

### Pull Request Checklist
- [ ] All tasks in phase completed
- [ ] Tests passing (≥85% coverage)
- [ ] No mypy errors
- [ ] No ruff errors
- [ ] Examples validated
- [ ] Documentation updated
- [ ] CHANGELOG.md entry added
- [ ] Code review requested

### Git Commit Messages
```
feat(hitl): Add manual gate support to chain pattern

- Implement InterruptMetadata and InterruptResponse models
- Add manual_gate step type to schema
- Chain executor pauses at manual gates
- Resume command accepts --approve/--reject/--modify flags

Closes #123
```

---

## Risk Mitigation

### Risk: Strands SDK Interrupt API Changes
**Mitigation:** Pin to specific SDK version, test thoroughly

### Risk: Session State Corruption
**Mitigation:** Add validation and recovery logic, comprehensive tests

### Risk: Timeout Edge Cases
**Mitigation:** Extensive testing across timezones, DST transitions

### Risk: Interactive Mode Blocking Issues
**Mitigation:** Timeout on stdin reads, fallback to non-interactive

### Risk: Performance Impact of Hooks
**Mitigation:** Benchmark hook overhead, optimize critical paths

---

## Success Metrics

### Code Quality
- [ ] Test coverage ≥85%
- [ ] Mypy strict mode passes
- [ ] Ruff linter passes
- [ ] No TODO comments in production code

### Functionality
- [ ] All 7 patterns support manual gates
- [ ] Interactive mode provides good UX
- [ ] Tool approval prevents dangerous operations
- [ ] Resume latency <1s for typical workflows

### Documentation
- [ ] Comprehensive HITL.md guide
- [ ] 5+ runnable examples
- [ ] API reference complete
- [ ] Migration guide for existing workflows

### User Validation
- [ ] Internal testing with 3+ workflows
- [ ] Beta testing with external users
- [ ] <3 bug reports in first month
- [ ] Positive feedback on UX

---

## Post-Implementation

### Version Release
```powershell
# Bump version
# Edit pyproject.toml: version = "0.12.0"

# Create git tag
git tag -a v0.12.0 -m "Release v0.12.0: HITL support"
git push origin v0.12.0

# Build and publish
uv build
uv publish
```

### Announcement
- [ ] Update README.md with HITL features
- [ ] Blog post or announcement
- [ ] Social media posts
- [ ] User documentation updates

### Monitoring
- [ ] Track adoption via telemetry (opt-in)
- [ ] Monitor error rates for HITL code paths
- [ ] Collect user feedback
- [ ] Plan future enhancements

---

## Future Enhancements (Post-v0.12.0)

### Multi-User Approvals
- Route approvals to specific users/roles
- Require N-of-M approvals for critical actions
- Approval delegation chains

### Web UI Dashboard
- React-based approval interface
- Visual workflow state inspector
- Bulk approval operations
- Real-time status updates

### Advanced Notifications
- Email on pause
- SMS for urgent approvals
- Slack/Teams integration
- Calendar scheduling

### Approval Policies
- Time-based auto-approval (business hours)
- Context-based routing (cost, risk)
- Compliance audit trail export

---

## References

- **HITL Design:** HITL.md
- **Session Management:** DURABLE.md
- **Project Guidelines:** CLAUDE.md
- **Strands SDK Interrupts:** https://strandsagents.com/latest/documentation/docs/user-guide/concepts/interrupts/
- **Strands SDK Hooks:** https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/hooks/

---

**End of Implementation Plan**

*Ready to implement! Start with Phase 1, Task 1.1.*

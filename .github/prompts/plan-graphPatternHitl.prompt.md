# Graph Pattern HITL Implementation Plan

## Executive Summary

Implement Human-in-the-Loop (HITL) support for the graph workflow pattern, enabling pause points within graph nodes for human approval, decisions, and dynamic routing based on user responses.

**Key Features:**
- HITL as graph nodes (consistent with chain/workflow patterns)
- Conditional edge routing based on user responses
- Support for HITL in loops (iterative refinement workflows)
- Session persistence with pause/resume capability
- Template context access to all node outputs including HITL responses

**Estimated Effort:** 7-10 hours (1-2 days)

---

## Architecture Overview

### HITL Node Model

HITL nodes are first-class graph nodes (not edges) for consistency with other patterns:

```yaml
pattern:
  type: graph
  config:
    nodes:
      planner:
        agent: planner_agent
        input: "Create plan"
      
      review_hitl:
        type: hitl
        prompt: "Review plan. Respond 'approve' or 'revise'"
        context_display: "{{ nodes.planner.response }}"
        default: "approved"
        timeout_seconds: 3600
      
      executor:
        agent: executor_agent
        input: "Execute: {{ nodes.planner.response }}"
    
    edges:
      - from: planner
        to: [review_hitl]
      
      - from: review_hitl
        choose:
          - when: "{{ nodes.review_hitl.response == 'approve' }}"
            to: executor
          - when: else
            to: planner  # Loop back for revision
```

### State Management

**Session State Structure:**

```python
pattern_state = {
    "current_node": "review_hitl",  # HITL node ID (paused)
    "node_results": {
        "planner": {
            "response": "Plan: ...",
            "agent": "planner",
            "status": "success",
            "iteration": 1
        },
        "review_hitl": {
            "response": None,  # Set on resume
            "type": "hitl",
            "prompt": "Review plan. Respond...",
            "status": "waiting_for_user",
            "iteration": 1
        }
    },
    "iteration_counts": {
        "planner": 1,
        "review_hitl": 1
    },
    "total_steps": 2,
    "execution_path": ["planner", "review_hitl"],
    
    "hitl_state": {
        "active": true,
        "node_id": "review_hitl",  # Graph-specific field
        "step_index": None,  # Chain-specific (not used)
        "task_id": None,  # Workflow-specific (not used)
        "prompt": "Review plan. Respond...",
        "context_display": "Rendered context...",
        "default_response": "approved",
        "timeout_at": "2025-11-10T15:00:00Z",
        "user_response": None
    }
}
```

### Execution Flow

```
Graph execution starts
  ↓
Execute nodes sequentially following edges
  ↓
Encounter HITL node
  ↓
[Render context_display template]
[Create HITLState with node_id]
[Save session with status=PAUSED]
[Display prompt to user]
[Exit with EX_HITL_PAUSE]
  ↓
User reviews context
  ↓
$ strands run --resume <session-id> --hitl-response "approve"
  ↓
[Load session]
[Validate hitl_response provided]
[Inject response into node_results[hitl_node_id]["response"]]
[Mark hitl_state.active = false]
[Checkpoint session]
  ↓
[Find next node via edge traversal]
[Edge conditions can access {{ nodes.review_hitl.response }}]
  ↓
Continue execution from next node
```

---

## Implementation Tasks

### Task 1: Schema Extensions

**File:** `src/strands_cli/schema/strands-workflow.schema.json`

**Changes Required:**

1. Update `graphConfig.nodes` to support `oneOf` discriminator for agent OR hitl nodes:

```json
{
  "nodes": {
    "type": "object",
    "minProperties": 1,
    "additionalProperties": {
      "oneOf": [
        {
          "description": "Agent execution node",
          "type": "object",
          "required": ["agent"],
          "properties": {
            "agent": {"type": "string"},
            "input": {"type": "string"}
          }
        },
        {
          "description": "Human-in-the-loop pause node",
          "type": "object",
          "required": ["type", "prompt"],
          "properties": {
            "type": {"const": "hitl"},
            "prompt": {
              "type": "string",
              "description": "Message displayed to user"
            },
            "context_display": {
              "type": "string",
              "description": "Context for review (supports templates)"
            },
            "default": {
              "type": "string",
              "description": "Default response on timeout"
            },
            "timeout_seconds": {
              "type": "integer",
              "minimum": 0,
              "description": "Timeout in seconds (0=no timeout)"
            }
          }
        }
      ]
    }
  }
}
```

**Validation:**
- Run `uv run strands validate examples/graph-hitl-approval-demo-openai.yaml`
- Verify schema accepts both agent and HITL nodes
- Verify schema rejects invalid HITL nodes (missing prompt, invalid timeout)

---

### Task 2: Type Model Extensions

**File:** `src/strands_cli/types.py`

**Changes Required:**

1. Add `node_id` field to `HITLState` model:

```python
class HITLState(BaseModel):
    """HITL execution state in pattern_state."""
    
    active: bool = Field(..., description="Whether HITL is waiting")
    
    # Pattern-specific fields (mutually exclusive)
    step_index: int | None = Field(None, description="Chain: step index")
    task_id: str | None = Field(None, description="Workflow: task ID")
    layer_index: int | None = Field(None, description="Workflow: layer index")
    branch_id: str | None = Field(None, description="Parallel: branch ID")
    step_type: str | None = Field(None, description="Parallel: branch/reduce")
    node_id: str | None = Field(None, description="Graph: node ID")  # NEW
    
    # Common fields
    prompt: str
    context_display: str | None = None
    default_response: str | None = None
    timeout_at: str | None = None
    user_response: str | None = None
```

2. Update `GraphNode` model to support HITL nodes:

```python
class GraphNode(BaseModel):
    """Graph node configuration (agent or HITL)."""
    
    # Agent node fields
    agent: str | None = Field(None, description="Agent ID")
    input: str | None = Field(None, description="Input template")
    
    # HITL node fields
    type: str | None = Field(None, description="Node type (hitl)")
    prompt: str | None = Field(None, description="HITL prompt")
    context_display: str | None = Field(None, description="Context template")
    default: str | None = Field(None, description="Default response")
    timeout_seconds: int | None = Field(None, ge=0, description="Timeout")
    
    @model_validator(mode='after')
    def validate_node_type(self) -> "GraphNode":
        """Validate node is either agent or HITL."""
        is_agent = self.agent is not None
        is_hitl = self.type == "hitl" and self.prompt is not None
        
        if not (is_agent or is_hitl):
            raise ValueError("Node must be agent (with 'agent' field) or HITL (with 'type: hitl' and 'prompt')")
        
        if is_agent and is_hitl:
            raise ValueError("Node cannot be both agent and HITL")
        
        return self
```

**Validation:**
- Run `uv run pytest tests/test_types.py -k graph`
- Verify GraphNode accepts agent nodes
- Verify GraphNode accepts HITL nodes
- Verify GraphNode rejects hybrid/invalid nodes

---

### Task 3: Graph Executor HITL Pause Logic

**File:** `src/strands_cli/exec/graph.py`

**Changes Required:**

1. Import HITL dependencies:

```python
from strands_cli.types import HITLState
from strands_cli.exit_codes import EX_HITL_PAUSE
from strands_cli.loader.template import render_template
from rich.panel import Panel
from datetime import datetime, timedelta, UTC
```

2. Add HITL detection in execution loop (around line 494):

```python
# Inside while current_node_id loop, BEFORE _execute_graph_node

# Get node configuration
node_config = spec.pattern.config.nodes.get(current_node_id)
if not node_config:
    raise GraphExecutionError(f"Node {current_node_id} not found")

# Check if HITL node
if isinstance(node_config, dict) and node_config.get("type") == "hitl":
    # HITL pause point
    await _handle_hitl_pause(
        spec=spec,
        hitl_node_id=current_node_id,
        node_config=node_config,
        node_results=node_results,
        session_state=session_state,
        session_repo=session_repo,
        variables=variables
    )
    # Function exits with EX_HITL_PAUSE, never returns

# Regular agent node execution
node = node_config  # GraphNode model
response_text, response_tokens = await _execute_graph_node(...)
```

3. Implement `_handle_hitl_pause` helper function:

```python
async def _handle_hitl_pause(
    spec: Spec,
    hitl_node_id: str,
    node_config: dict[str, Any],
    node_results: dict[str, dict[str, Any]],
    session_state: SessionState | None,
    session_repo: FileSessionRepository | None,
    variables: dict[str, str]
) -> None:
    """Handle HITL pause in graph pattern.
    
    Saves session, displays prompt, and exits with EX_HITL_PAUSE.
    This function never returns.
    """
    from strands_cli.exit_codes import EX_HITL_PAUSE
    
    # Validate session persistence available
    if not session_repo or not session_state:
        raise GraphExecutionError(
            "HITL node requires session persistence. "
            "Remove --no-save-session flag or remove HITL nodes."
        )
    
    # Parse HITL node config
    hitl_prompt = node_config["prompt"]
    hitl_context_display = node_config.get("context_display")
    hitl_default = node_config.get("default")
    hitl_timeout_seconds = node_config.get("timeout_seconds", 0)
    
    # Build template context
    template_context = {
        "nodes": node_results,  # All node results
        **spec.inputs.get("values", {}),
        **variables
    }
    
    # Render context_display template
    context_text = ""
    if hitl_context_display:
        context_text = render_template(hitl_context_display, template_context)
    
    # Calculate timeout
    timeout_at = None
    if hitl_timeout_seconds and hitl_timeout_seconds > 0:
        timeout_dt = datetime.now(UTC) + timedelta(seconds=hitl_timeout_seconds)
        timeout_at = timeout_dt.isoformat()
    
    # Create HITL state
    new_hitl_state = HITLState(
        active=True,
        node_id=hitl_node_id,
        step_index=None,
        task_id=None,
        prompt=hitl_prompt,
        context_display=context_text,
        default_response=hitl_default,
        timeout_at=timeout_at,
        user_response=None
    )
    
    # Update node_results for this HITL node
    node_results[hitl_node_id] = {
        "response": None,
        "type": "hitl",
        "prompt": hitl_prompt,
        "status": "waiting_for_user",
        "iteration": node_results[hitl_node_id]["iteration"]
    }
    
    # CRITICAL: Save session BEFORE displaying prompt
    session_state.pattern_state["current_node"] = hitl_node_id
    session_state.pattern_state["node_results"] = node_results
    session_state.pattern_state["hitl_state"] = new_hitl_state.model_dump()
    session_state.metadata.status = SessionStatus.PAUSED
    session_state.metadata.updated_at = now_iso8601()
    
    await session_repo.save(session_state, spec_content="")
    
    logger.info("hitl_pause_initiated",
               session_id=session_state.metadata.session_id,
               node_id=hitl_node_id)
    
    # Display to user
    console.print()
    console.print(Panel(
        f"[bold yellow]>>> HUMAN INPUT REQUIRED <<<[/bold yellow]\n\n{hitl_prompt}",
        border_style="yellow",
        title="HITL Pause",
        padding=(1, 2)
    ))
    
    if context_text:
        console.print(Panel(
            f"[bold]Context for Review:[/bold]\n\n{context_text}",
            border_style="dim",
            padding=(1, 2)
        ))
    
    console.print(f"\n[dim]Session ID: {session_state.metadata.session_id}[/dim]")
    console.print(f"[dim]Node: {hitl_node_id}[/dim]")
    console.print(f"[dim]Resume with:[/dim] strands run --resume {session_state.metadata.session_id} --hitl-response 'your response'")
    console.print()
    
    # Exit with HITL pause code (never returns)
    from strands_cli.types import RunResult, PatternType
    result = RunResult(
        success=True,
        last_response=f"HITL pause at node {hitl_node_id}: {hitl_prompt}",
        pattern_type=PatternType.GRAPH,
        cumulative_tokens=session_state.pattern_state.get("cumulative_tokens", 0),
        session_id=session_state.metadata.session_id
    )
    
    # Raise special exception to exit executor cleanly
    raise HITLPauseException(result)
```

4. Add `HITLPauseException` to exit executor cleanly:

```python
class HITLPauseException(Exception):
    """Raised to exit executor when HITL pause occurs."""
    
    def __init__(self, result: RunResult):
        self.result = result
        super().__init__("HITL pause")
```

5. Update main `run_graph` to catch `HITLPauseException`:

```python
async def run_graph(...) -> RunResult:
    """Execute graph workflow with HITL support."""
    
    try:
        # ... existing execution loop
        
    except HITLPauseException as e:
        # HITL pause occurred - return result with EX_HITL_PAUSE
        return e.result
    
    except Exception as e:
        # ... existing error handling
```

**Validation:**
- Test HITL pause saves session correctly
- Verify exit code is EX_HITL_PAUSE
- Check console output displays prompt and resume command
- Confirm session status set to PAUSED

---

### Task 4: Graph Executor HITL Resume Logic

**File:** `src/strands_cli/exec/graph.py`

**Changes Required:**

1. Add HITL resume logic at start of `run_graph`:

```python
async def run_graph(
    spec: Spec,
    variables: dict[str, str] | None = None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
    hitl_response: str | None = None,  # NEW parameter
    debug: bool = False,
    verbose: bool = False,
) -> RunResult:
    """Execute graph workflow with HITL support."""
    
    # ... existing initialization
    
    # Check for HITL resume
    if session_state:
        hitl_state_dict = session_state.pattern_state.get("hitl_state")
        if hitl_state_dict:
            hitl_state = HITLState(**hitl_state_dict)
            if hitl_state.active:
                # Resuming from HITL pause
                if not hitl_response:
                    raise GraphExecutionError(
                        f"Session {session_state.metadata.session_id} is waiting for HITL response.\n"
                        f"Resume with: strands run --resume {session_state.metadata.session_id} "
                        f"--hitl-response 'your response'"
                    )
                
                # Inject user response into node_results
                hitl_node_id = hitl_state.node_id
                if not hitl_node_id:
                    raise GraphExecutionError("HITL state missing node_id")
                
                # Update node_results with response (same structure as agent nodes)
                node_results[hitl_node_id]["response"] = hitl_response
                node_results[hitl_node_id]["status"] = "success"
                
                # Mark HITL as inactive
                hitl_state.active = False
                hitl_state.user_response = hitl_response
                session_state.pattern_state["hitl_state"] = hitl_state.model_dump()
                
                # Update execution path
                execution_path.append(hitl_node_id)
                
                # Checkpoint BEFORE continuing
                if session_repo:
                    session_state.pattern_state["node_results"] = node_results
                    session_state.pattern_state["execution_path"] = execution_path
                    session_state.metadata.status = SessionStatus.RUNNING
                    await session_repo.save(session_state, spec_content="")
                
                logger.info("hitl_response_received",
                           session_id=session_state.metadata.session_id,
                           node_id=hitl_node_id,
                           response=hitl_response[:100])
                
                # Find next node via edge traversal
                # Edge conditions can now access {{ nodes.<hitl_node_id>.response }}
                next_node_id = _get_next_node(
                    current_node_id=hitl_node_id,
                    edges=spec.pattern.config.edges,
                    node_results=node_results
                )
                
                # Update current_node to continue from next node
                current_node_id = next_node_id
                
                # If no next node, workflow is complete
                if not current_node_id:
                    last_executed_node = hitl_node_id
                    # Skip to final result generation
```

**Validation:**
- Test resume validates hitl_response provided
- Verify response injected into node_results correctly
- Check edge traversal accesses {{ nodes.hitl_node.response }}
- Confirm session updated to RUNNING status
- Test workflow completes after HITL resume

---

### Task 5: Example Workflow

**File:** `examples/graph-hitl-approval-demo-openai.yaml`

**Content:**

```yaml
version: 0
name: "graph-hitl-approval-demo"
description: "Graph workflow with human approval gates and conditional routing"

runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    max_total_tokens: 10000

agents:
  planner:
    prompt: "You are a project planner. Create detailed plans based on requirements."
  
  revisor:
    prompt: "You are a project revisor. Revise plans based on feedback."
  
  executor:
    prompt: "You are a project executor. Execute approved plans."

pattern:
  type: graph
  config:
    max_iterations: 5
    
    nodes:
      # Initial planning
      initial_plan:
        agent: planner
        input: "Create a project plan for: {{ project_description }}"
      
      # Manager review (HITL)
      manager_review:
        type: hitl
        prompt: |
          Review the project plan below.
          Respond with:
          - 'approve' to proceed to execution
          - 'revise' to request changes
          - 'reject' to cancel project
        context_display: |
          ## Project Plan
          
          {{ nodes.initial_plan.response }}
          
          ## Review Instructions
          
          Evaluate the plan for:
          - Feasibility
          - Resource allocation
          - Timeline realism
          - Risk assessment
        timeout_seconds: 3600
      
      # Revision step
      revise_plan:
        agent: revisor
        input: |
          The manager requested revisions to the plan.
          Manager feedback: {{ nodes.manager_review.response }}
          
          Original plan:
          {{ nodes.initial_plan.response }}
          
          Please revise the plan addressing the feedback.
      
      # Executive approval (HITL) - only if manager approved
      exec_approval:
        type: hitl
        prompt: |
          Executive approval required.
          Review the plan and respond 'yes' to approve or 'no' to reject.
        context_display: |
          ## Plan for Executive Approval
          
          {{ nodes.initial_plan.response }}
          
          ## Manager Status
          Manager approved: {{ nodes.manager_review.response }}
        timeout_seconds: 7200
      
      # Execution step
      execute_plan:
        agent: executor
        input: |
          Execute the following approved plan:
          
          {{ nodes.initial_plan.response }}
          
          Manager approval: {{ nodes.manager_review.response }}
          Executive approval: {{ nodes.exec_approval.response }}
      
      # Rejection terminal
      rejected:
        type: hitl
        prompt: "Plan rejected. Provide reason for audit trail."
        context_display: |
          ## Rejection Context
          
          Original plan:
          {{ nodes.initial_plan.response }}
    
    edges:
      # Start with initial planning
      - from: initial_plan
        to: [manager_review]
      
      # Manager review routing
      - from: manager_review
        choose:
          - when: "{{ nodes.manager_review.response == 'approve' }}"
            to: exec_approval
          - when: "{{ nodes.manager_review.response == 'revise' }}"
            to: revise_plan
          - when: "{{ nodes.manager_review.response == 'reject' }}"
            to: rejected
          - when: else
            to: rejected  # Default to rejection for safety
      
      # Revision loop - back to manager review
      - from: revise_plan
        to: [manager_review]
      
      # Executive approval routing
      - from: exec_approval
        choose:
          - when: "{{ nodes.exec_approval.response == 'yes' }}"
            to: execute_plan
          - when: else
            to: rejected
      
      # No outgoing edges from execute_plan and rejected (terminal nodes)

outputs:
  artifacts:
    - path: "./graph-hitl-approval-output.md"
      from: |
        # Project Plan Execution Results
        
        ## Final Status
        
        {% if nodes.execute_plan.response %}
        **Status:** Executed Successfully
        
        ### Execution Details
        {{ nodes.execute_plan.response }}
        {% else %}
        **Status:** Rejected
        
        ### Rejection Reason
        {{ nodes.rejected.response }}
        {% endif %}
        
        ## Approval History
        
        - Manager Review: {{ nodes.manager_review.response }}
        {% if nodes.exec_approval.response %}
        - Executive Approval: {{ nodes.exec_approval.response }}
        {% endif %}
        
        ## Original Plan
        
        {{ nodes.initial_plan.response }}
        
        {% if nodes.revise_plan.response %}
        ## Revised Plan
        
        {{ nodes.revise_plan.response }}
        {% endif %}
```

**Usage:**

```bash
# Run workflow (pauses at manager_review)
$ strands run examples/graph-hitl-approval-demo-openai.yaml \
    --var project_description="Build internal analytics dashboard"

>>> HUMAN INPUT REQUIRED <<<

Review the project plan below.
Respond with 'approve', 'revise', or 'reject'

[Context displayed]

Session ID: abc-123-def
Resume with: strands run --resume abc-123-def --hitl-response 'your response'

# Manager approves (triggers executive approval)
$ strands run --resume abc-123-def --hitl-response 'approve'

>>> HUMAN INPUT REQUIRED <<<

Executive approval required.
Review the plan and respond 'yes' or 'no'

[Context displayed]

Session ID: abc-123-def
Resume with: strands run --resume abc-123-def --hitl-response 'yes'

# Executive approves (completes workflow)
$ strands run --resume abc-123-def --hitl-response 'yes'

Workflow completed successfully.
Output written to: ./graph-hitl-approval-output.md
```

**Validation:**
- Run workflow and verify pause at first HITL
- Resume with 'approve' and verify pause at second HITL
- Resume with 'yes' and verify execution completes
- Test 'revise' path creates loop back to manager_review
- Test 'reject' path terminates at rejected node
- Verify artifact templating accesses all node results

---

### Task 6: Comprehensive Testing

**File:** `tests/test_graph_hitl.py`

**Test Cases:**

```python
"""Tests for HITL functionality in graph pattern."""

import pytest
from pathlib import Path
from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.exec.graph import run_graph
from strands_cli.exit_codes import EX_HITL_PAUSE, EX_OK
from strands_cli.types import Spec, HITLState


@pytest.fixture
def graph_hitl_spec():
    """Graph spec with HITL nodes."""
    # TODO: Create minimal graph spec with HITL node
    pass


@pytest.mark.asyncio
async def test_graph_hitl_pause_saves_session(graph_hitl_spec, tmp_path, mock_openai):
    """Test graph pauses at HITL node and saves session."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    result = await run_graph(
        spec=graph_hitl_spec,
        variables={},
        session_state=None,
        session_repo=repo
    )
    
    assert result.exit_code == EX_HITL_PAUSE
    assert result.session_id is not None
    
    # Verify session saved
    state = await repo.load(result.session_id)
    assert state.metadata.status == SessionStatus.PAUSED
    assert state.pattern_state["hitl_state"]["active"] is True
    assert state.pattern_state["hitl_state"]["node_id"] is not None


@pytest.mark.asyncio
async def test_graph_hitl_resume_with_response(graph_hitl_spec, tmp_path, mock_openai):
    """Test resuming from HITL pause with user response."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    # First run: pause at HITL
    result1 = await run_graph(
        spec=graph_hitl_spec,
        variables={},
        session_repo=repo
    )
    assert result1.exit_code == EX_HITL_PAUSE
    
    # Load session
    state = await repo.load(result1.session_id)
    hitl_node_id = state.pattern_state["hitl_state"]["node_id"]
    
    # Resume with response
    result2 = await run_graph(
        spec=graph_hitl_spec,
        variables={},
        session_state=state,
        session_repo=repo,
        hitl_response="approved"
    )
    
    assert result2.exit_code == EX_OK
    assert result2.success is True
    
    # Verify response injected
    final_state = await repo.load(result1.session_id)
    assert final_state.pattern_state["node_results"][hitl_node_id]["response"] == "approved"
    assert final_state.pattern_state["node_results"][hitl_node_id]["status"] == "success"
    assert final_state.pattern_state["hitl_state"]["active"] is False


@pytest.mark.asyncio
async def test_graph_hitl_resume_without_response_raises_error(graph_hitl_spec, tmp_path, mock_openai):
    """Test resuming from HITL without response raises error."""
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    # Pause at HITL
    result = await run_graph(spec=graph_hitl_spec, session_repo=repo)
    state = await repo.load(result.session_id)
    
    # Attempt resume without hitl_response
    with pytest.raises(Exception, match="waiting for HITL response"):
        await run_graph(
            spec=graph_hitl_spec,
            session_state=state,
            session_repo=repo,
            hitl_response=None  # Missing response
        )


@pytest.mark.asyncio
async def test_graph_hitl_conditional_routing(tmp_path, mock_openai):
    """Test edge conditions access HITL node responses."""
    # Create graph with conditional edges based on HITL response
    spec = create_graph_spec_with_conditional_hitl(
        nodes={
            "start": {"agent": "agent1", "input": "Task 1"},
            "review": {"type": "hitl", "prompt": "Approve or reject?"},
            "approved_path": {"agent": "agent2", "input": "Approved task"},
            "rejected_path": {"agent": "agent3", "input": "Rejected task"}
        },
        edges=[
            {"from": "start", "to": ["review"]},
            {
                "from": "review",
                "choose": [
                    {"when": "{{ nodes.review.response == 'approve' }}", "to": "approved_path"},
                    {"when": "else", "to": "rejected_path"}
                ]
            }
        ]
    )
    
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    # Pause at review
    result1 = await run_graph(spec=spec, session_repo=repo)
    state = await repo.load(result1.session_id)
    
    # Resume with 'approve'
    result2 = await run_graph(
        spec=spec,
        session_state=state,
        session_repo=repo,
        hitl_response="approve"
    )
    
    # Verify approved_path executed (not rejected_path)
    final_state = await repo.load(result1.session_id)
    assert final_state.pattern_state["node_results"]["approved_path"]["status"] == "success"
    assert final_state.pattern_state["node_results"]["rejected_path"]["status"] == "not_executed"


@pytest.mark.asyncio
async def test_graph_hitl_in_loop(tmp_path, mock_openai):
    """Test HITL node in iterative refinement loop."""
    # Create graph with HITL in loop
    spec = create_graph_spec_with_loop(
        nodes={
            "write": {"agent": "writer", "input": "Write code"},
            "review": {"type": "hitl", "prompt": "Approve or request revision?"},
            "finalize": {"agent": "finalizer", "input": "Finalize"}
        },
        edges=[
            {"from": "write", "to": ["review"]},
            {
                "from": "review",
                "choose": [
                    {"when": "{{ nodes.review.response == 'approve' }}", "to": "finalize"},
                    {"when": "else", "to": "write"}  # Loop back
                ]
            }
        ],
        max_iterations=3
    )
    
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    # First iteration: request revision
    result1 = await run_graph(spec=spec, session_repo=repo)
    state1 = await repo.load(result1.session_id)
    
    result2 = await run_graph(
        spec=spec,
        session_state=state1,
        session_repo=repo,
        hitl_response="revise"  # Loop back to write
    )
    assert result2.exit_code == EX_HITL_PAUSE  # Paused again at review
    
    # Second iteration: approve
    state2 = await repo.load(result1.session_id)
    result3 = await run_graph(
        spec=spec,
        session_state=state2,
        session_repo=repo,
        hitl_response="approve"  # Continue to finalize
    )
    assert result3.exit_code == EX_OK
    
    # Verify iteration counts
    final_state = await repo.load(result1.session_id)
    assert final_state.pattern_state["iteration_counts"]["write"] == 2
    assert final_state.pattern_state["iteration_counts"]["review"] == 2


@pytest.mark.asyncio
async def test_graph_hitl_context_display_rendering(graph_hitl_spec, tmp_path, mock_openai):
    """Test context_display template renders with node results."""
    # TODO: Create spec with context_display accessing previous nodes
    # Verify rendered context includes previous node outputs
    pass


@pytest.mark.asyncio
async def test_graph_multiple_hitl_nodes(tmp_path, mock_openai):
    """Test graph with multiple HITL nodes in sequence."""
    spec = create_graph_spec_with_multiple_hitl(
        nodes={
            "task1": {"agent": "agent1", "input": "Task 1"},
            "review1": {"type": "hitl", "prompt": "Approve task 1?"},
            "task2": {"agent": "agent2", "input": "Task 2"},
            "review2": {"type": "hitl", "prompt": "Approve task 2?"},
            "final": {"agent": "agent3", "input": "Final task"}
        },
        edges=[
            {"from": "task1", "to": ["review1"]},
            {"from": "review1", "to": ["task2"]},
            {"from": "task2", "to": ["review2"]},
            {"from": "review2", "to": ["final"]}
        ]
    )
    
    repo = FileSessionRepository(storage_dir=tmp_path)
    
    # Pause at first HITL
    result1 = await run_graph(spec=spec, session_repo=repo)
    assert result1.exit_code == EX_HITL_PAUSE
    
    state1 = await repo.load(result1.session_id)
    assert state1.pattern_state["hitl_state"]["node_id"] == "review1"
    
    # Resume, pause at second HITL
    result2 = await run_graph(
        spec=spec,
        session_state=state1,
        session_repo=repo,
        hitl_response="yes"
    )
    assert result2.exit_code == EX_HITL_PAUSE
    
    state2 = await repo.load(result1.session_id)
    assert state2.pattern_state["hitl_state"]["node_id"] == "review2"
    
    # Resume, complete workflow
    result3 = await run_graph(
        spec=spec,
        session_state=state2,
        session_repo=repo,
        hitl_response="yes"
    )
    assert result3.exit_code == EX_OK


@pytest.mark.asyncio
async def test_graph_hitl_without_session_raises_error(graph_hitl_spec, mock_openai):
    """Test HITL without session persistence raises error."""
    with pytest.raises(Exception, match="requires session persistence"):
        await run_graph(
            spec=graph_hitl_spec,
            session_repo=None  # No session repo
        )
```

**Validation:**
- Run `uv run pytest tests/test_graph_hitl.py -v`
- Verify all tests pass
- Check coverage ≥85% for graph HITL code paths

---

### Task 7: Documentation Updates

**Files to Update:**

1. **HITL.md** - Update section 2.3 with implementation details
2. **README.md** - Add graph HITL example to HITL section
3. **docs/strands-workflow-manual.md** - Document graph HITL nodes

**HITL.md Section 2.3 Update:**

```markdown
### 2.3 Graph Pattern HITL

**Status:** ✅ Implemented

**Implementation Strategy:**
- HITL as graph nodes (not edges) for pattern consistency
- Conditional edge routing based on `{{ nodes.<hitl_node_id>.response }}`
- Support for HITL in loops (iteration counting applies)
- Session state stores `node_id` in `hitl_state`

**Example:**

```yaml
pattern:
  type: graph
  config:
    nodes:
      planner:
        agent: planner_agent
        input: "Create plan for {{ project }}"
      
      review:
        type: hitl
        prompt: "Review plan. Respond 'approve' or 'revise'"
        context_display: "{{ nodes.planner.response }}"
      
      executor:
        agent: executor_agent
        input: "Execute: {{ nodes.planner.response }}"
    
    edges:
      - from: planner
        to: [review]
      
      - from: review
        choose:
          - when: "{{ nodes.review.response == 'approve' }}"
            to: executor
          - when: else
            to: planner  # Loop back
```

**State Structure:**

```python
{
    "current_node": "review",  # HITL node ID
    "node_results": {
        "planner": {"response": "...", "status": "success"},
        "review": {"response": None, "type": "hitl", "status": "waiting_for_user"}
    },
    "hitl_state": {
        "active": true,
        "node_id": "review",  # Graph-specific field
        "prompt": "Review plan...",
        "context_display": "Rendered context...",
        "user_response": null
    }
}
```

**Key Features:**
- ✅ HITL nodes in graph pattern
- ✅ Conditional routing based on HITL responses
- ✅ HITL in loops (iteration counting)
- ✅ Template context: `{{ nodes.<id>.response }}`
- ✅ Session pause/resume

**Testing:**
- ✅ Pause at HITL node
- ✅ Resume with response
- ✅ Conditional edge evaluation
- ✅ HITL in loops
- ✅ Multiple HITL nodes
```

---

## Design Decisions

### Decision 1: HITL as Nodes vs Edges

**Chosen:** HITL as nodes

**Rationale:**
- Consistent with chain/workflow patterns (HITL as step/task)
- Nodes are execution units; edges are control flow
- Easier to track state (node_results dictionary)
- Simplifies template context (nodes.<id>.response)
- Allows HITL nodes to have multiple incoming/outgoing edges

**Alternative Rejected:** HITL on edges
- Inconsistent with other patterns
- Complicates state management (edge transitions vs node execution)
- Less intuitive for users

### Decision 2: node_id in HITLState

**Chosen:** Add `node_id: str | None` field to `HITLState`

**Rationale:**
- Graph pattern needs node ID for resume (not step_index)
- Keeps `HITLState` reusable across all patterns
- Pattern-specific fields are mutually exclusive (step_index OR task_id OR node_id)

### Decision 3: Iteration Counting for HITL Nodes

**Chosen:** HITL nodes count toward `max_iterations` per-node limit

**Rationale:**
- Prevents infinite HITL loops (user repeatedly requests revisions)
- Consistent with agent nodes (all nodes count)
- Forces workflow designer to set appropriate limits
- Safety valve for runaway workflows

**Alternative Rejected:** Exempt HITL from iteration counting
- Could enable infinite loops
- Inconsistent treatment of node types

### Decision 4: HITL Response Storage

**Chosen:** Store in `node_results[hitl_node_id]["response"]` (same field as agent responses)

**Rationale:**
- Template compatibility: `{{ nodes.review.response }}` works for both
- Simplifies edge condition evaluation
- Consistent data structure
- No special-casing in template engine

---

## Edge Cases and Error Handling

### Edge Case 1: HITL Node with No Outgoing Edges (Terminal HITL)

**Behavior:** Workflow completes after HITL response

**Example:**
```yaml
nodes:
  final_approval:
    type: hitl
    prompt: "Confirm completion and provide sign-off"

edges:
  - from: execute
    to: [final_approval]
  # No outgoing edge from final_approval
```

**Handling:** Treat as terminal node; workflow completes successfully

### Edge Case 2: HITL in Loop Exceeds max_iterations

**Behavior:** Raise `GraphExecutionError` with clear message

**Example:**
```yaml
config:
  max_iterations: 3  # Per-node limit

nodes:
  write: {agent: writer}
  review: {type: hitl, prompt: "Approve?"}

edges:
  - from: review
    choose:
      - when: "{{ nodes.review.response == 'revise' }}"
        to: write  # Loop back
```

**Error Message:**
```
GraphExecutionError: Node 'review' exceeded maximum iteration limit (3).
This may indicate a loop in the workflow. Review edge conditions or increase max_iterations.
Current iteration counts: {'write': 3, 'review': 3}
```

### Edge Case 3: Resume Session with Inactive HITL State

**Behavior:** Continue normal execution (no special handling)

**Scenario:** User resumes session that was paused for non-HITL reasons

**Handling:**
```python
if hitl_state and hitl_state.active:
    # HITL resume logic
else:
    # Normal resume (continue from current_node)
```

### Edge Case 4: Multiple Users Resume Same Session

**Behavior:** First response wins; second gets error

**Mitigation:** Session locking (future enhancement in Phase 3)

**Current Handling:**
```python
# Second resume attempt
if not hitl_state.active:
    raise GraphExecutionError(
        "Session already resumed by another user. "
        "HITL response was: {hitl_state.user_response}"
    )
```

---

## Performance Considerations

### HITL Pause Overhead

| Operation | Time | Notes |
|-----------|------|-------|
| HITL node detection | <5ms | Type check in execution loop |
| Context rendering | 10-50ms | Template evaluation with nodes dict |
| Session save | 30-100ms | File write with full state |
| Console display | 5-20ms | Rich Panel rendering |

**Total HITL pause overhead:** ~50-175ms

### HITL Resume Overhead

| Operation | Time | Notes |
|-----------|------|-------|
| Session load | 20-80ms | File read + JSON parse |
| Response injection | <5ms | Dictionary update |
| Edge traversal | 5-15ms | Condition evaluation |
| Session checkpoint | 30-100ms | File write |

**Total HITL resume overhead:** ~55-200ms

### Optimization Opportunities

1. **Lazy node_results pre-population** - Only create entries when needed
2. **Incremental session saves** - Only update changed fields
3. **Template caching** - Cache compiled templates for context_display

---

## Testing Strategy

### Unit Tests (4 hours)

- [ ] `test_graph_node_type_validation` - Agent vs HITL node validation
- [ ] `test_hitl_state_node_id_field` - HITLState with node_id
- [ ] `test_graph_hitl_detection` - Detect HITL nodes in execution loop
- [ ] `test_graph_hitl_context_rendering` - Template context with nodes dict
- [ ] `test_graph_hitl_session_save` - State persistence during pause
- [ ] `test_graph_hitl_response_injection` - Response stored in node_results

### Integration Tests (3 hours)

- [ ] `test_graph_hitl_pause_resume_cycle` - Full pause/resume flow
- [ ] `test_graph_hitl_conditional_routing` - Edge conditions access hitl response
- [ ] `test_graph_hitl_in_loop` - Iterative refinement with HITL
- [ ] `test_graph_multiple_hitl_nodes` - Sequential HITL nodes
- [ ] `test_graph_hitl_terminal_node` - HITL with no outgoing edges
- [ ] `test_graph_hitl_max_iterations` - Loop limit enforcement

### E2E Tests (2 hours)

- [ ] `test_graph_hitl_example_workflow` - Run full example workflow
- [ ] `test_graph_hitl_artifact_generation` - Output artifacts with HITL responses
- [ ] `test_graph_hitl_cli_resume` - CLI resume command with --hitl-response

---

## Open Questions for Review

### Question 1: Top-level hitl_response Variable

**Context:** Chain pattern adds `{{ hitl_response }}` convenience variable for most recent HITL response.

**Options:**
- A) Add to graph pattern (walk execution_path backwards to find last HITL node)
- B) Graph-only: Use `{{ nodes.<id>.response }}` explicitly (no convenience variable)

**Recommendation:** Option B - Graph pattern already has clear node access; avoid duplication

**Rationale:**
- Graph users already reference nodes explicitly
- Less ambiguous (chain is sequential, graph is not)
- Simpler implementation

---

### Question 2: Terminal HITL Nodes

**Context:** HITL node with no outgoing edges (workflow ends with human input).

**Options:**
- A) Allow terminal HITL nodes (workflow completes after response)
- B) Require schema validation: every HITL node must have outgoing edge

**Recommendation:** Option A - Allow terminal HITL nodes

**Rationale:**
- Valid use case: final sign-off, audit trail collection
- User can still add dummy terminal agent node if needed
- Consistent with agent nodes (can be terminal)

---

### Question 3: HITL Iteration Exemption

**Context:** HITL nodes in loops count toward max_iterations limit.

**Options:**
- A) HITL nodes exempt from iteration counting (unlimited human revisions)
- B) HITL nodes count toward max_iterations (current design)
- C) Add separate `max_hitl_iterations` config option

**Recommendation:** Option B - HITL counts toward max_iterations

**Rationale:**
- Safety valve prevents infinite loops
- Forces workflow designer to set reasonable limits
- Users can increase max_iterations if needed
- Simpler implementation (no special cases)

---

## Success Criteria

### Phase Completion

- [x] Schema supports HITL nodes in graph pattern
- [x] Graph executor pauses at HITL nodes with session save
- [x] Graph executor resumes with user response
- [x] Edge conditions can access `{{ nodes.<hitl_node>.response }}`
- [x] HITL nodes in loops tracked with iteration counting
- [x] Example workflow demonstrates graph HITL
- [x] Tests cover pause, resume, loops, conditional routing
- [x] Documentation updated (HITL.md, README, manual)

### Quality Metrics

- [ ] Test coverage ≥85% for graph HITL code
- [ ] HITL pause overhead <200ms
- [ ] HITL resume overhead <200ms
- [ ] No data loss during pause/resume
- [ ] Clear error messages for common mistakes

### User Experience

- [ ] Console output clearly shows HITL prompt and resume instructions
- [ ] Context display renders with proper formatting
- [ ] Error messages guide user to correct usage
- [ ] Example workflow demonstrates real-world use case

---

## Implementation Checklist

### Phase 1: Schema & Types (2 hours)
- [ ] Update `strands-workflow.schema.json` with graph HITL node oneOf
- [ ] Add `node_id` field to `HITLState` model
- [ ] Update `GraphNode` model with HITL fields and validation
- [ ] Run schema validation tests
- [ ] Validate example YAML files

### Phase 2: Executor Logic (4 hours)
- [ ] Add HITL detection in graph execution loop
- [ ] Implement `_handle_hitl_pause` helper function
- [ ] Add `HITLPauseException` for clean exit
- [ ] Implement HITL resume logic at executor start
- [ ] Update edge traversal to access HITL responses
- [ ] Add logging for HITL pause/resume events
- [ ] Test pause logic with mocked session repo
- [ ] Test resume logic with mocked session repo

### Phase 3: Example & Tests (3 hours)
- [ ] Create `graph-hitl-approval-demo-openai.yaml`
- [ ] Write unit tests for HITL node detection and state
- [ ] Write integration tests for pause/resume cycle
- [ ] Write tests for conditional routing
- [ ] Write tests for HITL in loops
- [ ] Write tests for multiple HITL nodes
- [ ] Run full test suite and verify coverage

### Phase 4: Documentation (1 hour)
- [ ] Update HITL.md section 2.3 with implementation details
- [ ] Add graph HITL example to README
- [ ] Update strands-workflow-manual.md
- [ ] Add inline code comments for complex logic
- [ ] Review all documentation for clarity

---

## Timeline

| Day | Tasks | Deliverables |
|-----|-------|--------------|
| Day 1 AM | Schema & Types | Updated schema, models validated |
| Day 1 PM | Executor pause logic | HITL pause working, tests passing |
| Day 2 AM | Executor resume logic | HITL resume working, tests passing |
| Day 2 PM | Example & remaining tests | Full example workflow, ≥85% coverage |
| Day 2 EOD | Documentation | All docs updated, PR ready |

**Total Time:** 10 hours (1.25 days)

---

## Post-Implementation

### Follow-up Tasks (Future)

1. **Interactive mode** - `--hitl-interactive` for inline prompts (Phase 2 feature)
2. **Timeout handling** - Auto-apply default response on timeout (Phase 2 feature)
3. **Response validation** - Regex pattern validation (Phase 2 feature)
4. **Multi-user HITL** - Approval thresholds, required approvers (Phase 3 feature)
5. **Web UI hooks** - Webhooks for HITL events (Phase 3 feature)

### Code Review Focus Areas

1. **Session state consistency** - Verify all HITL state fields populated correctly
2. **Edge case handling** - Terminal HITL nodes, loops, max_iterations
3. **Error messages** - Clear, actionable guidance for users
4. **Test coverage** - All code paths exercised, especially error cases
5. **Documentation** - Examples accurate, instructions clear

---

**END OF PLAN**

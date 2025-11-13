# Python API Guide

**Status:** Production Ready  
**Complexity:** Medium  
**Use Case:** Interactive HITL workflows, programmatic execution

---

## Overview

The Strands Python API provides a first-class programmatic interface for executing workflows with interactive Human-in-the-Loop (HITL) capabilities. Instead of requiring CLI exit/resume cycles, workflows can run as interactive Python programs that prompt users directly in the terminal.

### Key Features

- **Interactive HITL**: Workflows prompt users in-terminal instead of pausing execution
- **Automatic Session Management**: Sessions created and managed transparently
- **Sync & Async Execution**: Choose the execution model that fits your use case
- **Rich Terminal UI**: Beautiful prompts with context display and formatting
- **All Patterns Supported**: Works with all 7 workflow patterns (chain, workflow, routing, parallel, evaluator-optimizer, orchestrator-workers, graph)

### Quick Example

```python
from strands import Workflow

# Load workflow from YAML
workflow = Workflow.from_file("workflow.yaml")

# Run interactively - prompts appear in terminal
result = workflow.run_interactive(topic="AI")

print(result.last_response)
```

---

## Installation

The Python API is included in the standard Strands CLI installation:

```powershell
pip install strands-cli
```

Or with uv:

```powershell
uv add strands-cli
```

---

## Quickstart

### 1. Create a Workflow Spec

**File:** `my_workflow.yaml`

```yaml
version: 0
name: interactive-research
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  researcher:
    prompt: "Research the topic and provide key findings"
  writer:
    prompt: "Write a summary based on the research"
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
      - type: hitl
        prompt: "Review the research findings. Approve or request changes?"
        context_display: "{{ steps[0].response }}"
      - agent: writer
        input: "Write summary. HITL feedback: {{hitl_response}}"
```

### 2. Run Interactively

**File:** `run_workflow.py`

```python
from strands import Workflow

# Load workflow
workflow = Workflow.from_file("my_workflow.yaml")

# Run with interactive HITL prompts
result = workflow.run_interactive(topic="quantum computing")

# Access results
print(f"Success: {result.success}")
print(f"Duration: {result.duration_seconds:.2f}s")
print(f"\nFinal Output:\n{result.last_response}")
```

### 3. Execute

```powershell
python run_workflow.py
```

**Output:**

```
🤝 HUMAN INPUT REQUIRED

Review the research findings. Approve or request changes?

┌─────────────────────────────────────────────┐
│ Context:                                     │
│                                              │
│ Quantum computing uses quantum bits...       │
│ Key findings:                                │
│ 1. Superposition enables parallel compute   │
│ 2. Entanglement provides correlation        │
│ ...                                          │
└─────────────────────────────────────────────┘

Your response: Approved - excellent research!

✓ Workflow completed successfully
Duration: 12.34s

Final Output:
[Summary based on research with feedback incorporated]
```

---

## API Reference

### Workflow Class

```python
class Workflow:
    """Primary API for creating and executing workflows."""
    
    def __init__(self, spec: Spec):
        """Create workflow from validated Spec."""
    
    @classmethod
    def from_file(cls, path: str | Path, **variables: Any) -> "Workflow":
        """Load workflow from YAML/JSON file."""
    
    def run_interactive(self, **variables: Any) -> RunResult:
        """Execute workflow with interactive HITL prompts (sync)."""
    
    async def run_interactive_async(self, **variables: Any) -> RunResult:
        """Execute workflow with interactive HITL prompts (async)."""
    
    def run(self, **variables: Any) -> RunResult:
        """Execute workflow (non-interactive, uses session persistence)."""
    
    async def run_async(self, **variables: Any) -> RunResult:
        """Execute workflow asynchronously (non-interactive)."""
```

### from_file()

Load and validate a workflow specification from a YAML or JSON file.

**Signature:**

```python
@classmethod
def from_file(
    cls,
    path: str | Path,
    **variables: Any
) -> "Workflow"
```

**Parameters:**

- **path** (`str | Path`): Path to workflow specification file (`.yaml` or `.json`)
- **variables** (`**kwargs`): Variable overrides (e.g., `topic="AI"`, `max_retries=3`)

**Returns:**

- `Workflow` instance ready to execute

**Raises:**

- `LoadError`: File not found or invalid YAML/JSON
- `SchemaValidationError`: Spec doesn't match schema
- `CapabilityError`: Spec contains unsupported features

**Example:**

```python
# Basic usage
workflow = Workflow.from_file("workflow.yaml")

# With variable overrides
workflow = Workflow.from_file(
    "workflow.yaml",
    topic="machine learning",
    max_iterations=5
)

# With Path object
from pathlib import Path
spec_path = Path("specs/research.yaml")
workflow = Workflow.from_file(spec_path)
```

### run_interactive()

Execute workflow with interactive HITL prompts in the terminal. When the workflow encounters HITL steps, it prompts the user directly instead of pausing execution.

**Signature:**

```python
def run_interactive(self, **variables: Any) -> RunResult
```

**Parameters:**

- **variables** (`**kwargs`): Runtime variable overrides

**Returns:**

- `RunResult` with execution details (see [RunResult](#runresult))

**Behavior:**

1. Creates session automatically
2. Executes workflow pattern
3. On HITL step:
   - Displays prompt in Rich panel
   - Shows context if provided
   - Waits for user input
   - Continues execution with response
4. Loops until workflow completes
5. Cleans up session on success

**Example:**

```python
# Basic usage
result = workflow.run_interactive()

# With runtime variables
result = workflow.run_interactive(
    topic="climate change",
    detail_level="comprehensive"
)

# Access results
if result.success:
    print(f"Completed in {result.duration_seconds:.2f}s")
    print(result.last_response)
else:
    print(f"Failed: {result.error_message}")
```

### run_interactive_async()

Async version of `run_interactive()` for use in async contexts or high-performance applications.

**Signature:**

```python
async def run_interactive_async(self, **variables: Any) -> RunResult
```

**Parameters:**

- **variables** (`**kwargs`): Runtime variable overrides

**Returns:**

- `RunResult` with execution details

**Example:**

```python
import asyncio
from strands import Workflow

async def main():
    workflow = Workflow.from_file("workflow.yaml")
    result = await workflow.run_interactive_async(topic="AI")
    print(result.last_response)

asyncio.run(main())
```

**Use Cases:**

- FastAPI/Starlette endpoints
- Concurrent workflow execution
- Integration with async frameworks
- High-throughput batch processing

### run()

Execute workflow in standard mode (non-interactive). Saves session and exits at HITL steps, requiring resume via CLI or subsequent `run()` calls.

**Signature:**

```python
def run(self, **variables: Any) -> RunResult
```

**Parameters:**

- **variables** (`**kwargs`): Runtime variable overrides

**Returns:**

- `RunResult` with execution details (may indicate HITL pause)

**Example:**

```python
# First run - pauses at HITL
result = workflow.run(topic="AI")

if result.agent_id == "hitl":
    print("Workflow paused for HITL approval")
    print(f"Session ID: {result.session_id}")
    # User provides input via CLI: strands resume <session_id> --response "approved"

# Or use interactive mode instead
result = workflow.run_interactive(topic="AI")
```

### run_async()

Async version of `run()` for non-interactive execution.

**Signature:**

```python
async def run_async(self, **variables: Any) -> RunResult
```

**Parameters:**

- **variables** (`**kwargs`): Runtime variable overrides

**Returns:**

- `RunResult` with execution details

---

## Custom HITL Handlers

You can provide custom handlers for HITL prompts instead of the default terminal UI.

### Handler Protocol

```python
from typing import Callable
from strands_cli.types import HITLState

HITLHandler = Callable[[HITLState], str]
```

### HITLState

```python
@dataclass
class HITLState:
    active: bool
    prompt: str
    context_display: str | None = None
    default_response: str | None = None
    timeout_seconds: int | None = None
    user_response: str | None = None
```

### Custom Handler Example

```python
from strands import Workflow
from strands_cli.types import HITLState

def auto_approve_handler(hitl_state: HITLState) -> str:
    """Auto-approve all HITL prompts."""
    print(f"Auto-approving: {hitl_state.prompt}")
    return "approved"

def slack_handler(hitl_state: HITLState) -> str:
    """Send HITL prompt to Slack and wait for response."""
    import slack_sdk
    
    client = slack_sdk.WebClient(token="xoxb-...")
    response = client.chat_postMessage(
        channel="#approvals",
        text=f"🤝 Approval needed: {hitl_state.prompt}"
    )
    
    # Poll for response (simplified)
    while True:
        # Check for thread replies...
        pass

# Use custom handler
workflow = Workflow.from_file("workflow.yaml")
result = await workflow.run_interactive_async(
    hitl_handler=slack_handler,
    topic="AI"
)
```

---

## RunResult

The return type for all execution methods.

```python
@dataclass
class RunResult:
    agent_id: str                          # Last agent executed
    exit_code: int                         # Exit code (0 = success)
    last_response: str                     # Final agent response
    duration_seconds: float                # Execution duration
    success: bool                          # True if exit_code == 0
    error_message: str | None = None       # Error details if failed
    artifacts_written: list[str] = []      # Paths to output files
    session_id: str | None = None          # Session ID (for resume)
    token_usage: dict[str, int] = {}       # Token consumption by agent
    execution_context: dict[str, Any] = {} # Pattern-specific execution data
```

### Accessing Results

```python
result = workflow.run_interactive(topic="AI")

# Check success
if result.success:
    print("✓ Workflow completed")
else:
    print(f"✗ Failed: {result.error_message}")

# Access output
print(result.last_response)

# Check artifacts
if result.artifacts_written:
    print(f"Wrote {len(result.artifacts_written)} files:")
    for path in result.artifacts_written:
        print(f"  - {path}")

# Token usage
total_tokens = sum(result.token_usage.values())
print(f"Total tokens: {total_tokens}")
```

### Accessing Intermediate Results

The `execution_context` field provides access to intermediate step/task/branch/node outputs. The structure varies by pattern:

#### Chain Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access individual step outputs
steps = result.execution_context["steps"]
print(f"Step 0 output: {steps[0]['response']}")
print(f"Step 1 output: {steps[1]['response']}")
print(f"Step 2 tokens: {steps[2]['tokens']}")

# Iterate through all steps
for i, step in enumerate(steps):
    print(f"Step {i}: {step['response'][:100]}...")
```

#### Workflow Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access task results by ID
tasks = result.execution_context["tasks"]
print(f"Research task: {tasks['research']['response']}")
print(f"Analysis task: {tasks['analyze']['response']}")

# Iterate through all tasks
for task_id, task_data in tasks.items():
    print(f"{task_id}: {task_data['response'][:100]}...")
```

#### Parallel Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access branch outputs by ID
branches = result.execution_context["branches"]
print(f"Branch 1: {branches['branch_1']['response']}")
print(f"Branch 2: {branches['branch_2']['response']}")

# Check if reduce step was executed
if "reduce" in result.execution_context:
    print(f"Reduce output: {result.execution_context['reduce']['response']}")
```

#### Graph Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access node outputs by ID
nodes = result.execution_context["nodes"]
print(f"Initial node: {nodes['start']['response']}")
print(f"Decision node: {nodes['evaluate']['response']}")
print(f"Final node: {nodes['finish']['response']}")

# Check node execution order
if "execution_path" in result.execution_context:
    print(f"Nodes executed: {result.execution_context['execution_path']}")
```

#### Evaluator-Optimizer Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access iteration history
iterations = result.execution_context.get("iterations", [])
for i, iteration in enumerate(iterations):
    print(f"Iteration {i}:")
    print(f"  Producer output: {iteration['producer_response'][:100]}...")
    print(f"  Evaluator score: {iteration['score']}")
    print(f"  Issues: {iteration.get('issues', [])}")
```

#### Orchestrator-Workers Pattern

```python
result = workflow.run_interactive(topic="AI")

# Access worker outputs
workers = result.execution_context.get("workers", [])
for i, worker in enumerate(workers):
    print(f"Worker {i}: {worker['response'][:100]}...")

# Access orchestrator decomposition
if "decomposition" in result.execution_context:
    tasks = result.execution_context["decomposition"]
    print(f"Decomposed into {len(tasks)} tasks")
```

### Reading Artifact Files

Since `artifacts_written` contains absolute file paths, you can read the generated files directly:

```python
result = workflow.run_interactive(topic="AI")

# Read all generated artifacts
for artifact_path in result.artifacts_written:
    with open(artifact_path, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"\n=== {artifact_path} ===")
        print(content)

# Or access specific artifact by name pattern
report_files = [p for p in result.artifacts_written if "report" in p]
if report_files:
    with open(report_files[0], 'r', encoding='utf-8') as f:
        report = f.read()
        print(report)
```

---

## Pattern-Specific Features

### Chain Pattern

Sequential multi-step execution with HITL checkpoints.

```python
# Example: Research → HITL Review → Summarize
workflow = Workflow.from_file("chain-workflow.yaml")
result = workflow.run_interactive(topic="AI")

# Access final output
print(result.last_response)

# Access individual step outputs
for i, step in enumerate(result.execution_context["steps"]):
    print(f"Step {i}: {step['response'][:100]}...")
```

### Workflow Pattern

DAG execution with HITL tasks.

```python
# Example: Parallel research tasks → HITL approval → Final report
workflow = Workflow.from_file("workflow-dag.yaml")
result = workflow.run_interactive(
    topic="climate change",
    sources=["academic", "news", "reports"]
)

# Access specific task outputs by ID
tasks = result.execution_context["tasks"]
research_output = tasks["research_task"]["response"]
analysis_output = tasks["analysis_task"]["response"]
print(f"Research: {research_output[:200]}...")
print(f"Analysis: {analysis_output[:200]}...")
```

### Parallel Pattern

Concurrent branches with optional HITL in reduce step.

```python
# Example: Process 3 datasets in parallel → HITL review → Merge
workflow = Workflow.from_file("parallel-workflow.yaml")
result = workflow.run_interactive(
    datasets=["sales.csv", "marketing.csv", "support.csv"]
)

# Access branch outputs
branches = result.execution_context["branches"]
for branch_id, branch_data in branches.items():
    print(f"{branch_id}: {branch_data['response'][:100]}...")

# Access reduce step output (if present)
if "reduce" in result.execution_context:
    print(f"Final synthesis: {result.execution_context['reduce']['response']}")
```

### Graph Pattern

State machine with HITL at decision nodes.

```python
# Example: Iterative refinement with approval gates
workflow = Workflow.from_file("graph-workflow.yaml")
result = workflow.run_interactive(
    task="Generate business proposal",
    quality_threshold=0.9
)

# Access node outputs by ID
nodes = result.execution_context["nodes"]
for node_id, node_data in nodes.items():
    print(f"{node_id}: {node_data['response'][:100]}...")
```

### Evaluator-Optimizer Pattern

Iterative refinement with HITL override.

```python
# Example: Code review with human-in-the-loop corrections
workflow = Workflow.from_file("evaluator-optimizer.yaml")
result = workflow.run_interactive(
    code_file="main.py",
    max_iterations=5
)

# Access iteration history
iterations = result.execution_context.get("iterations", [])
print(f"Completed {len(iterations)} iterations")
for i, iteration in enumerate(iterations):
    print(f"Iteration {i}: Score={iteration['score']}")

# Access final optimized output
print(result.last_response)
```

### Orchestrator-Workers Pattern

Task decomposition with HITL review.

```python
# Example: Research swarm with approval checkpoints
workflow = Workflow.from_file("orchestrator-workers.yaml")
result = workflow.run_interactive(
    research_topic="quantum computing applications",
    num_workers=3
)

# Access worker outputs
workers = result.execution_context.get("workers", [])
print(f"Processed {len(workers)} worker tasks:")
for i, worker in enumerate(workers):
    print(f"  Worker {i}: {worker['response'][:100]}...")

# Access final synthesis/report
print(f"\nFinal report:\n{result.last_response}")
```

---

## Error Handling

### Exception Types

```python
from strands_cli.loader import LoadError
from strands_cli.schema.validator import SchemaValidationError
from strands_cli.exec.utils import ExecutionError

try:
    workflow = Workflow.from_file("workflow.yaml")
    result = workflow.run_interactive(topic="AI")
    
except LoadError as e:
    print(f"Failed to load spec: {e}")
    
except SchemaValidationError as e:
    print(f"Invalid spec: {e}")
    print(f"Location: {e.json_pointer}")
    
except ExecutionError as e:
    print(f"Execution failed: {e}")
    
except KeyboardInterrupt:
    print("Workflow interrupted by user")

# Note: CapabilityError is raised during load_spec(), caught as BuildError
# Unsupported features cause sys.exit(EX_UNSUPPORTED) before Workflow creation
```

### Graceful Degradation

```python
# Fallback to non-interactive mode on error
try:
    result = workflow.run_interactive(topic="AI")
except Exception as e:
    print(f"Interactive mode failed: {e}")
    print("Falling back to standard execution...")
    result = workflow.run(topic="AI")
```

---

## Integration Examples

### FastAPI Endpoint

```python
from fastapi import FastAPI, BackgroundTasks
from strands import Workflow
from typing import Dict, Any

app = FastAPI()

@app.post("/workflows/{workflow_name}/run")
async def run_workflow_async(
    workflow_name: str,
    variables: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """Execute workflow asynchronously."""
    workflow = Workflow.from_file(f"workflows/{workflow_name}.yaml")
    
    # Run in background (non-interactive for API)
    result = await workflow.run_async(**variables)
    
    return {
        "status": "completed" if result.success else "failed",
        "duration": result.duration_seconds,
        "output": result.last_response,
        "artifacts": result.artifacts_written
    }
```

### Jupyter Notebook

```python
# Cell 1: Import and load
from strands import Workflow
import IPython.display as display

workflow = Workflow.from_file("research.yaml")

# Cell 2: Custom handler for notebook
def notebook_hitl_handler(hitl_state):
    """Display HITL prompt in notebook."""
    display.display(display.HTML(f"<h3>🤝 {hitl_state.prompt}</h3>"))
    
    if hitl_state.context_display:
        display.display(display.Markdown(hitl_state.context_display))
    
    response = input("Your response: ")
    return response

# Cell 3: Run interactively
result = await workflow.run_interactive_async(
    hitl_handler=notebook_hitl_handler,
    topic="machine learning"
)

display.display(display.Markdown(result.last_response))
```

### Batch Processing

```python
import asyncio
from strands import Workflow

async def process_batch(topics: list[str]):
    """Process multiple workflows concurrently."""
    workflow = Workflow.from_file("research.yaml")
    
    # Run all workflows in parallel (non-interactive)
    tasks = [
        workflow.run_async(topic=topic)
        for topic in topics
    ]
    
    results = await asyncio.gather(*tasks)
    
    return [
        {
            "topic": topic,
            "success": result.success,
            "output": result.last_response
        }
        for topic, result in zip(topics, results)
    ]

# Execute
topics = ["AI", "quantum computing", "climate change"]
results = asyncio.run(process_batch(topics))

for r in results:
    print(f"{r['topic']}: {r['success']}")
```

---

## Performance Considerations

### Agent Caching

Agents are automatically cached and reused across steps:

```python
# 10-step chain with same agent → 1 agent instance (not 10)
workflow = Workflow.from_file("long-chain.yaml")
result = workflow.run_interactive()

# Cache managed automatically by AgentCache
```

### Model Client Pooling

Model clients are pooled via `@lru_cache`:

```python
# Multiple workflows with same runtime config → shared client
workflows = [
    Workflow.from_file("w1.yaml"),
    Workflow.from_file("w2.yaml"),
    Workflow.from_file("w3.yaml"),
]

# All use same OpenAI client instance
for w in workflows:
    await w.run_async()
```

### Concurrency Control

Parallel pattern respects `max_parallel` limit:

```yaml
runtime:
  max_parallel: 5  # Only 5 branches at once

pattern:
  type: parallel
  config:
    branches:
      - agent: worker  # × 20 branches
```

```python
# Semaphore automatically limits concurrency
result = workflow.run_interactive()
```

---

## Advanced Features

### Event System

Hook into workflow lifecycle with event callbacks:

```python
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

# Subscribe to events
@workflow.on("workflow_start")
def on_start(event):
    print(f"🚀 Starting: {event.spec_name}")

@workflow.on("step_complete")
def on_step(event):
    step = event.data.get("step_index", "?")
    print(f"✓ Step {step} completed")

@workflow.on("workflow_complete")
def on_complete(event):
    duration = event.data.get("duration_seconds", 0)
    print(f"✅ Completed in {duration:.2f}s")

result = workflow.run_interactive(topic="AI")
```

Available event types:
- `workflow_start` - Workflow begins
- `step_start` / `step_complete` - Chain pattern steps
- `task_start` / `task_complete` - Workflow pattern tasks
- `branch_start` / `branch_complete` - Parallel pattern branches
- `node_start` / `node_complete` - Graph pattern nodes
- `hitl_pause` - HITL step encountered
- `error` - Error occurred
- `workflow_complete` - Workflow finished

!!! tip "Example Code"
    See `examples/api/06_event_callbacks.py` in the repository for complete example.

### Session Management API

Programmatic session control:

```python
from strands import SessionManager
from strands.types import SessionStatus

async def manage_sessions():
    manager = SessionManager()
    
    # List sessions with pagination
    sessions = await manager.list(offset=0, limit=10)
    print(f"Found {len(sessions)} sessions")
    
    # Filter by status
    paused = await manager.list(status=SessionStatus.PAUSED)
    
    # Filter by workflow name
    specific = await manager.list(workflow_name="research-workflow")
    
    # Get specific session
    session = await manager.get("session-id")
    print(f"Status: {session.metadata['status']}")
    
    # Resume paused session
    result = await manager.resume("session-id", hitl_response="approved")
    
    # Cleanup old sessions (older than 7 days)
    removed = await manager.cleanup(older_than_days=7)
    print(f"Cleaned up {removed} sessions")
    
    # Delete specific session
    await manager.delete("session-id")

# Run async
import asyncio
asyncio.run(manage_sessions())
```

Features:
- **Pagination**: `offset` and `limit` parameters (max 1000)
- **Filtering**: By status and workflow name
- **Caching**: 5-minute TTL for improved performance
- **Cleanup**: Age and status-based deletion

!!! tip "Example Code"
    See `examples/api/07_session_management.py` in the repository for complete example.

### Async Context Manager

Proper resource management with async context managers:

```python
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

# Use async context manager for automatic cleanup
async with workflow.async_executor() as executor:
    result = await executor.run_async(topic="AI")
    print(result.last_response)
# Agent cache automatically cleaned up
```

Benefits:
- Automatic agent cache cleanup
- Exception-safe resource management
- Reusable across multiple executions
- Better performance (shared model clients)

!!! tip "Example Code"
    See `examples/api/08_async_execution.py` in the repository for complete example.

### Streaming API

Stream workflow execution events as they occur:

```python
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

async def stream_workflow():
    async for chunk in workflow.stream_async(topic="AI"):
        if chunk.chunk_type == "step_start":
            print(f"\n→ Starting step...")
        elif chunk.chunk_type == "step_complete":
            response = chunk.data.get("response", "")
            print(f"✓ {response[:100]}...")
        elif chunk.chunk_type == "complete":
            print("\n✅ Workflow complete!")

import asyncio
asyncio.run(stream_workflow())
```

Chunk types:
- `token` - Individual tokens (future)
- `step_start` - Step begins
- `step_complete` - Step finishes
- `complete` - Workflow finishes

**Note**: Token-by-token streaming not yet implemented. Currently returns complete responses as chunks.

!!! tip "Example Code"
    See `examples/api/11_streaming_responses.py` in the repository for complete example.

### FastAPI Integration

Deploy workflows as REST APIs:

```python
from fastapi import FastAPI
from strands import Workflow
from strands.integrations.fastapi_router import create_workflow_router

app = FastAPI()

workflow = Workflow.from_file("workflow.yaml")
router = create_workflow_router(workflow, prefix="/workflow")
app.include_router(router)

# Run with: uvicorn server:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `POST /workflow/execute` - Execute workflow
- `GET /workflow/sessions` - List sessions (paginated)
- `GET /workflow/sessions/{id}` - Get session details
- `POST /workflow/sessions/{id}/resume` - Resume paused session
- `DELETE /workflow/sessions/{id}` - Delete session

Install web extras: `pip install strands-cli[web]`

!!! tip "Example Code"
    See `examples/api/09_fastapi_integration.py` in the repository and the [Integrations Guide](../integrations.md) for complete details.

### Webhook Notifications

Send workflow events to external services:

```python
from strands import Workflow
from strands_cli.integrations.webhook_handler import GenericWebhookHandler

workflow = Workflow.from_file("workflow.yaml")

# Create webhook handler
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/events",
    headers={"Authorization": "Bearer TOKEN"}
)

# Subscribe to events
@workflow.on("workflow_complete")
def notify(event):
    webhook.send(event)

result = workflow.run_interactive(topic="AI")
```

Features:
- Automatic retry with exponential backoff (3 attempts)
- Extensible for Slack, Teams, Discord, etc.
- Error handling and logging
- HTTPS support with auth headers

!!! tip "Example Code"
    See `examples/api/10_webhook_notifications.py` in the repository and the [Integrations Guide](../integrations.md) for custom webhook handlers.

## Limitations

### Current Limitations

1. **Console output mixing**: Executor logs may interfere with HITL prompts (cosmetic)
2. **Timeout enforcement**: HITL timeouts not enforced in interactive mode
3. **Progress tracking**: No progress bars for long-running steps yet
4. **Token streaming**: Streaming API returns complete responses, not individual tokens


### Workarounds

```python
# 1. Console output - acceptable for MVP
# Use --quiet flag in CLI if needed

# 2. Session cleanup - now automated with SessionManager
from strands import SessionManager
import asyncio

async def cleanup():
    manager = SessionManager()
    removed = await manager.cleanup(older_than_days=7)
    print(f"Cleaned up {removed} sessions")

asyncio.run(cleanup())

# 3. Timeouts - use asyncio.wait_for
import asyncio

async def run_with_timeout(workflow, timeout=300):
    """Run workflow with overall timeout."""
    async with workflow.async_executor() as executor:
        return await asyncio.wait_for(
            executor.run_async(topic="AI"),
            timeout=timeout
        )
```

---

## Best Practices

### 1. Variable Validation

```python
# Validate inputs before running
def validate_topic(topic: str) -> str:
    if len(topic) < 3:
        raise ValueError("Topic must be at least 3 characters")
    return topic.strip()

topic = validate_topic(input("Enter topic: "))
result = workflow.run_interactive(topic=topic)
```

### 2. Error Recovery

```python
# Implement retry logic for transient failures
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def run_with_retry(workflow, **vars):
    return workflow.run_interactive(**vars)

result = run_with_retry(workflow, topic="AI")
```

### 3. Resource Cleanup

```python
# Use async context manager for automatic cleanup
async def run_workflow():
    workflow = Workflow.from_file("workflow.yaml")
    
    async with workflow.async_executor() as executor:
        result = await executor.run_async(topic="AI")
        return result
    # Agent cache auto-cleaned on exit

import asyncio
result = asyncio.run(run_workflow())
```

### 4. Event Monitoring

```python
from strands import Workflow

workflow = Workflow.from_file("workflow.yaml")

# Track execution progress
progress = {"steps": 0}

@workflow.on("step_complete")
def track_progress(event):
    progress["steps"] += 1
    print(f"Progress: {progress['steps']} steps completed")

@workflow.on("error")
def handle_error(event):
    print(f"Error: {event.data.get('error', 'Unknown')}")

result = workflow.run_interactive(topic="AI")
print(f"Total steps: {progress['steps']}")
```

### 5. Logging Integration

```python
import logging
from strands import Workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

workflow = Workflow.from_file("workflow.yaml")

logger.info("Starting workflow: %s", workflow.spec.name)
result = workflow.run_interactive(topic="AI")

if result.success:
    logger.info("Completed in %.2fs", result.duration_seconds)
else:
    logger.error("Failed: %s", result.error_message)
```

---

## See Also

- [Integrations Guide](../integrations.md) - Webhooks and FastAPI deployment
- [HITL How-To Guide](../../howto/hitl.md) - CLI-based HITL workflows
- [Session API Reference](../session-api.md) - Session persistence and resume
- [Workflow Spec Reference](../spec.md) - YAML specification format
- [CLI Commands](../cli.md) - Command-line interface

---

## Support

- **GitHub Issues**: https://github.com/ThomasRohde/strands-cli/issues
- **Documentation**: https://thomasrohde.github.io/strands-cli/
- **Examples**: See `examples/api/` directory in repository

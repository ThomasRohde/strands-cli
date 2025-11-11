# Strands Python API Examples

This directory contains example scripts demonstrating the **Strands Python API** for programmatic workflow execution.

## Overview

The Strands Python API provides a first-class programmatic interface for executing workflows, enabling developers to:

- Run workflows as Python programs (no CLI required)
- Handle HITL (Human-in-the-Loop) interactively in terminal
- Build custom approval logic and integrations
- Use async/await for high-performance applications

## Examples

### 01_interactive_hitl.py

**Basic interactive HITL workflow execution**

```python
from strands import Workflow

workflow = Workflow.from_file("examples/chain-hitl-business-proposal-openai.yaml")
result = workflow.run_interactive(topic="quantum computing")
print(result.last_response)
```

**Demonstrates:**
- Loading workflows from YAML files
- Running with interactive terminal prompts for HITL
- Accessing execution results and artifacts

**Usage:**
```powershell
python examples/api/01_interactive_hitl.py
```

---

### 02_simple_chain.py

**Minimal chain workflow with HITL approval**

```python
from strands import Workflow

workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
result = workflow.run_interactive(topic="AI in healthcare")

if result.success:
    print(f"✓ Completed in {result.duration_seconds:.2f}s")
```

**Demonstrates:**
- Simplest possible API usage
- Chain pattern with single HITL step
- Variable substitution with `--var` equivalent

**Usage:**
```powershell
python examples/api/02_simple_chain.py
```

---

### 03_async_execution.py

**Async workflow execution with run_interactive_async()**

```python
import asyncio
from strands import Workflow

async def main():
    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
    result = await workflow.run_interactive_async(topic="machine learning")
    print(result.last_response)

asyncio.run(main())
```

**Demonstrates:**
- Async API usage for high-performance applications
- Running multiple workflows with proper async patterns
- When to use async vs sync execution

**Usage:**
```powershell
python examples/api/03_async_execution.py
```

---

### 04_custom_hitl_handler.py

**Custom HITL handler with automated approval logic**

```python
from strands import Workflow
from strands_cli.types import HITLState

def auto_approve_handler(hitl_state: HITLState) -> str:
    print(f"Auto-approving: {hitl_state.prompt}")
    return "APPROVED"

workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")
result = workflow.run_interactive(
    topic="blockchain",
    hitl_handler=auto_approve_handler,
)
```

**Demonstrates:**
- Creating custom HITL handlers
- Automated approval based on business rules
- Accessing HITL state (prompt, context, defaults)
- Useful for testing and custom integrations

**Usage:**
```powershell
python examples/api/04_custom_hitl_handler.py
```

---

## Requirements

All examples require:

- **Python 3.12+**
- **strands-cli** installed (`uv pip install -e .` from project root)
- **OpenAI API key** set in `OPENAI_API_KEY` environment variable (for OpenAI examples)
- **Ollama** running locally (for Ollama examples, if using those workflows)

## Installation

From the project root:

```powershell
# Install strands-cli in development mode
uv pip install -e .

# Set OpenAI API key (for examples using OpenAI)
$env:OPENAI_API_KEY = "your-api-key-here"
```

## Running Examples

```powershell
# Run individual examples
python examples/api/01_interactive_hitl.py
python examples/api/02_simple_chain.py
python examples/api/03_async_execution.py
python examples/api/04_custom_hitl_handler.py

# Or from uv
uv run python examples/api/01_interactive_hitl.py
```

## Interactive vs Non-Interactive Mode

### Interactive Mode (Terminal Prompts)

Use `run_interactive()` for local development and debugging:

```python
# User is prompted in terminal for HITL responses
result = workflow.run_interactive()
```

**Best for:**
- Local development and testing
- Manual approval workflows
- Interactive debugging
- Quick prototyping

### Non-Interactive Mode (Session Persistence)

Use `run()` for production workflows with external approval systems:

```python
# Saves session and exits at HITL steps
result = workflow.run()

# Later, resume with approval from external system
# (CLI: strands resume <session-id> --response "approved")
```

**Best for:**
- Production deployments
- Integration with approval systems (Slack, email, etc.)
- Long-running workflows
- Distributed systems

## API Quick Reference

### Workflow Class

```python
from strands import Workflow

# Load from file
workflow = Workflow.from_file("workflow.yaml", **variables)

# Run interactively (sync)
result = workflow.run_interactive(**variables)

# Run interactively (async)
result = await workflow.run_interactive_async(**variables)

# Run non-interactive (session-based)
result = workflow.run(**variables)

# Run non-interactive (async)
result = await workflow.run_async(**variables)
```

### Custom HITL Handler

```python
from strands_cli.types import HITLState

def my_handler(hitl_state: HITLState) -> str:
    """Custom HITL handler.
    
    Args:
        hitl_state: HITL pause state with:
            - prompt: str - HITL prompt text
            - context_display: str | None - Optional context
            - default_response: str | None - Optional default
            - user_response: str | None - Previous response (if any)
    
    Returns:
        User's response string
    """
    print(f"HITL Prompt: {hitl_state.prompt}")
    return "my response"

# Use with workflow
result = workflow.run_interactive(hitl_handler=my_handler)
```

### RunResult

```python
# Access execution results
result = workflow.run_interactive()

result.success                # bool - Whether workflow succeeded
result.exit_code             # int - Exit code (0 = success)
result.agent_id              # str - Last agent executed
result.last_response         # str - Final LLM response
result.duration_seconds      # float - Execution time
result.artifacts_written     # list[str] - Artifact file paths
```

## Supported Workflow Patterns

All 7 workflow patterns work with the Python API:

- ✅ **chain** - Sequential multi-step execution
- ✅ **workflow** - Multi-task DAG with dependencies
- ✅ **routing** - Dynamic agent selection
- ✅ **parallel** - Concurrent branch execution
- ✅ **evaluator-optimizer** - Iterative refinement
- ✅ **orchestrator-workers** - Task decomposition
- ✅ **graph** - State machine with transitions

## Additional Resources

- **Full API Documentation**: See `docs/API.md`
- **HITL Documentation**: See `docs/HITL.md`
- **Workflow Manual**: See `docs/strands-workflow-manual.md`
- **CLI Documentation**: See `README.md`

## Troubleshooting

### "No module named 'strands'"

Install strands-cli in development mode:

```powershell
uv pip install -e .
```

### "OPENAI_API_KEY not set"

Set your OpenAI API key:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### "Workflow file not found"

Run examples from project root:

```powershell
cd c:\Users\thoma\Projects\artifacts\Projects\strands-cli
python examples/api/01_interactive_hitl.py
```

### "Event loop already running"

If you see `RuntimeError: asyncio.run() cannot be called from a running event loop`:

- Use `run_interactive_async()` instead of `run_interactive()` in async contexts
- Or use `asyncio.create_task()` instead of `asyncio.run()`

## Contributing

When adding new examples:

1. Follow naming convention: `NN_descriptive_name.py`
2. Include comprehensive docstring with usage instructions
3. Add example to this README
4. Test with both OpenAI and Ollama providers (where applicable)
5. Keep examples focused on single concept

## License

MIT License - See LICENSE file in project root

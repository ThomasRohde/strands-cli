# Strands CLI

<div align="center">

**Execute declarative agentic workflows on AWS Bedrock, Ollama, and OpenAI**

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.4.0-brightgreen.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-1549+-success.svg)](#development)
[![Coverage](https://img.shields.io/badge/coverage-83%25-yellow.svg)](#development)

*Schema-validated • Multi-provider • Production-ready observability*

[Quick Start](#quick-start) • [Documentation](#documentation) • [Examples](examples/) • [Contributing](CONTRIBUTING.md)

</div>

---

## Overview

Strands CLI is a Python 3.12+ command-line tool that executes declarative agentic workflows defined in YAML. It provides enterprise-grade orchestration for AI agent workflows with comprehensive observability, strict schema validation, and multi-provider support.

### Key Features

🎯 **7 Workflow Patterns**
- **Chain**: Sequential multi-step execution with context threading
- **Workflow**: DAG-based parallel task execution with dependency resolution  
- **Routing**: Dynamic agent selection based on input classification
- **Parallel**: Concurrent branch execution with optional reduce/aggregation
- **Evaluator-Optimizer**: Iterative refinement with quality gates
- **Orchestrator-Workers**: Dynamic task delegation to worker pools
- **Graph**: Explicit control flow with conditionals, loops, and cycle protection

🐍 **Python API & Builder API**
- **Programmatic workflow execution** - Run workflows directly from Python code
- **Interactive HITL workflows** - Handle human-in-the-loop prompts in terminal without CLI restart
- **Fluent builder API** - Construct workflows in Python without writing YAML
- **Type-safe construction** - Full IDE autocomplete and type checking
- **7 patterns supported** - Chain, Workflow, Parallel, Graph, Routing, Evaluator-Optimizer, Orchestrator
- **Async execution** - High-performance async/await support
- **Zero breaking changes** - Existing CLI and YAML workflows unchanged

💾 **Durable Session Management**
- Automatic session persistence with crash recovery
- Resume workflows from any checkpoint
- Agent conversation history restoration via Strands SDK
- Session management CLI (list, show, delete)
- Cost optimization by skipping completed steps

🤝 **Human-in-the-Loop (HITL)**
- Pause workflows for human approval or input
- Review agent outputs before proceeding
- Quality control gates with resume capability
- Built-in session integration for seamless pause/resume

🔌 **Multi-Provider Support**
- **AWS Bedrock** (Anthropic Claude, Amazon Titan)
- **Ollama** (local models: llama2, mistral, mixtral, etc.)
- **OpenAI** (GPT-4, GPT-4o, o1-preview, o1-mini)

📊 **Production Observability**
- Full OpenTelemetry tracing (OTLP/Console exporters)
- Trace artifact export with `{{ $TRACE }}` or `--trace` flag
- PII redaction for sensitive data protection
- Structured debug logging with `--debug` flag
- Comprehensive span instrumentation across all patterns

🔒 **Security & Validation**
- JSON Schema Draft 2020-12 validation with JSONPointer error reporting
- Sandboxed Jinja2 templates (blocks code execution)
- HTTP URL validation (SSRF prevention)
- Path traversal protection for artifact writes
- Environment-based secrets management

⚡ **Performance Optimizations**
- Agent caching (90% reduction in multi-step workflow overhead)
- Model client pooling (LRU cache for Bedrock/Ollama/OpenAI)
- Single async event loop per workflow execution
- Proper resource cleanup (HTTP clients, tool adapters)

🛠️ **Built-in Tools**
- HTTP executors with timeout/retry
- Python tools: `http_request`, `file_read`, `file_write`, `calculator`, `current_time`
- Native tool registry with auto-discovery
- MCP (Model Context Protocol) support (experimental)

---

## Quick Start

### Prerequisites

- **Python 3.12+** ([Download](https://www.python.org/downloads/))
- **uv package manager** (recommended): `pip install uv` or see [uv docs](https://github.com/astral-sh/uv)

**Provider-specific requirements:**

<details>
<summary><b>Ollama</b> (local models)</summary>

1. [Install Ollama](https://ollama.ai/)
2. Start the server: `ollama serve`
3. Pull a model: `ollama pull llama2`
4. Verify: `curl http://localhost:11434/api/tags`

</details>

<details>
<summary><b>AWS Bedrock</b> (cloud models)</summary>

1. Configure AWS credentials: `aws configure`
2. Ensure model access in your region (e.g., `us-east-1`)
3. Verify: `aws bedrock list-foundation-models`

</details>

<details>
<summary><b>OpenAI</b> (GPT models)</summary>

1. Get API key from [OpenAI Platform](https://platform.openai.com/api-keys)
2. Set environment variable: `export OPENAI_API_KEY=your-key-here`

</details>

### Installation

**From source** (not yet published to PyPI):

```bash
git clone https://github.com/ThomasRohde/strands-cli.git
cd strands-cli
uv sync
```

**Verify installation:**

```bash
uv run strands --version
uv run strands doctor  # Run health check
```

### Your First Workflow

Create a simple workflow file `hello.yaml`:

```yaml
name: hello-world
version: 1
description: A simple greeting workflow

runtime:
  provider: ollama  # or bedrock, openai
  model_id: llama2

agents:
  greeter:
    prompt: "You are a friendly assistant. Greet the user warmly."

pattern:
  type: chain
  config:
    steps:
      - agent_id: greeter
        prompt: "Say hello to {{ name }}!"

inputs:
  values:
    name: "World"

outputs:
  artifacts:
    - path: "./greeting.txt"
      from: "{{ last_response }}"
```

**Run it:**

```bash
# Using default variable
uv run strands run hello.yaml

# Override variable
uv run strands run hello.yaml --var name="Alice"

# Force overwrite output
uv run strands run hello.yaml --force

# Enable debug logging
uv run strands run hello.yaml --debug --verbose
```

**Output:**

```
Running workflow: hello-world

✓ Workflow completed successfully
Duration: 1.23s

Artifacts written:
  • ./greeting.txt
```

---

## Human-in-the-Loop (HITL) Workflows

Strands CLI supports human-in-the-loop steps for approval gates, quality control, and interactive workflows across **all workflow patterns** (chain, workflow, parallel). HITL steps pause execution, save the session automatically, and wait for user input before continuing.

### Quick Example

Add a HITL step in any workflow:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research topic: {{ topic }}"

      # HITL approval gate
      - type: hitl
        prompt: "Review the research findings. Approve to proceed?"
        context_display: "{{ steps[0].response }}"

      - agent: analyst
        input: |
          User decision: {{ hitl_response }}
          Analyze: {{ steps[0].response }}
```

### CLI Workflow

```bash
# Run workflow (pauses at HITL step)
uv run strands run workflow.yaml --var topic="AI Safety"

# Output:
# ⏸️  HITL Pause at step 1
# 
# Prompt: Review the research findings. Approve to proceed?
# Context: [Research findings shown here]
# 
# Session ID: abc-123-def
# Resume with: strands run --resume abc-123-def --hitl-response "your response"

# Resume with user response
uv run strands run --resume abc-123-def --hitl-response "approved"
```

### Supported Patterns

**✅ Chain Pattern**: HITL steps between any sequential steps  
**✅ Workflow Pattern (DAG)**: HITL tasks with dependencies  
**✅ Parallel Pattern**: HITL in branches OR at reduce step  
**✅ Graph Pattern**: HITL nodes with conditional routing based on user responses

Example workflows:
- Chain: [`examples/chain-hitl-approval-demo.yaml`](examples/chain-hitl-approval-demo.yaml)
- Workflow: [`examples/workflow-hitl-approval-demo.yaml`](examples/workflow-hitl-approval-demo.yaml)
- Parallel (branch): [`examples/parallel-hitl-branch-demo.yaml`](examples/parallel-hitl-branch-demo.yaml)
- Parallel (reduce): [`examples/parallel-hitl-reduce-demo.yaml`](examples/parallel-hitl-reduce-demo.yaml)
- Graph: [`examples/graph-hitl-approval-demo-openai.yaml`](examples/graph-hitl-approval-demo-openai.yaml)

### Key Features

- **Multi-Pattern Support**: Works with chain, workflow, parallel, and graph patterns
- **Automatic Pause**: Workflow saves state and exits with code 20 (EX_HITL_PAUSE)
- **Context Display**: Show users what to review using template variables
- **Template Access**: Access HITL responses via `{{ hitl_response }}` (chain/workflow/parallel) or `{{ nodes.<id>.response }}` (graph)
- **Session Integration**: Leverages durable session management for seamless resume
- **Context Isolation**: Parallel branch HITL only sees its own branch context
- **Conditional Routing**: Graph pattern HITL enables dynamic workflow paths based on user decisions

---

## Builder API (Code-First Workflows)

Build workflows programmatically in Python without YAML!

The **fluent builder API** provides type-safe, fail-fast workflow construction with full IDE autocomplete. Perfect for developers who prefer code over configuration.

### Quick Example

```python
from strands_cli.api import FluentBuilder

# Build workflow programmatically
workflow = (
    FluentBuilder("research-workflow")
    .description("Three-step research with approval gates")
    .runtime("openai", model="gpt-4o-mini", temperature=0.7)
    .agent("researcher", "You are a thorough research assistant")
    .agent("writer", "You are a technical writer")
    .chain()
    .step("researcher", "Research {{topic}} thoroughly")
    .hitl("Review research. Type 'continue' to proceed.",
          show="{{ steps[0].response }}")
    .step("writer", "Write report based on: {{ steps[0].response }}")
    .artifact("{{topic}}-report.md", "# {{topic}}\n\n{{ last_response }}")
    .build()
)

# Execute workflow
result = workflow.run_interactive(topic="AI safety")

if result.success:
    print(f"✓ Completed in {result.duration_seconds:.2f}s")
    print(f"Output: {result.last_response}")
```

### Key Features

✅ **Type-safe** - Full IDE autocomplete and type checking  
✅ **Fail-fast** - Errors caught at build time with actionable messages  
✅ **All 7 patterns** - Chain, Workflow, Parallel, Graph, Routing, Evaluator-Optimizer, Orchestrator-Workers  
✅ **HITL integration** - Pattern-specific human-in-the-loop methods  
✅ **Same execution** - Uses identical runtime as YAML workflows  

### Supported Patterns

```python
# Chain pattern
.chain().step("agent", "input").hitl("prompt").build()

# Workflow pattern (DAG)
.workflow().task("id", "agent", "input", depends_on=["task1"]).build()

# Parallel pattern
.parallel().branch("id").step("agent", "input").done().reduce("agent", "input").build()

# Graph pattern
.graph().node("id", "agent", "input").edge("from", "to").build()

# Routing pattern
.routing().router("agent", "input").route("id").step("agent", "input").done().build()

# Evaluator-Optimizer pattern
.evaluator_optimizer().producer("agent", "input").evaluator("agent", "input").accept(min_score=8).build()

# Orchestrator-Workers pattern
.orchestrator_workers().orchestrator("agent", "input").worker_template("agent").reduce_step("agent", "input").build()
```

### Migration from YAML

**YAML:**
```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  researcher:
    prompt: "You are a researcher"
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
```

**Builder API:**
```python
workflow = (
    FluentBuilder("research")
    .runtime("openai", model="gpt-4o-mini")
    .agent("researcher", "You are a researcher")
    .chain()
    .step("researcher", "Research {{topic}}")
    .build()
)
```

### Examples

See `examples/api/` directory:
- `01_interactive_hitl.py` - Basic interactive workflow
- `02_chain_builder.py` - Chain pattern with builder API
- `03_async_execution.py` - Async workflow execution
- `04_custom_hitl_handler.py` - Custom HITL logic

**📖 See [Builder API Tutorial](manual/tutorials/builder-api.md) and [API Reference](manual/reference/api/builders.md) for complete documentation.**

---

## Durable Execution (Session Resume)

Strands CLI supports **session persistence** for crash recovery and long-running workflows. When enabled (default), workflows automatically checkpoint their state, allowing you to resume from the last completed step.

### Basic Usage

```bash
# Run with session saving (enabled by default)
uv run strands run workflow.yaml

# Resume from session after crash or pause
uv run strands run --resume <session-id>

# Disable session saving
uv run strands run workflow.yaml --no-save-session
```

### Session Management

```bash
# List all sessions
uv run strands sessions list

# Filter by status
uv run strands sessions list --status running
uv run strands sessions list --status completed

# Show detailed session information
uv run strands sessions show <session-id>

# Delete old sessions
uv run strands sessions delete <session-id>
uv run strands sessions delete <session-id> --force  # Skip confirmation
```

### How It Works

- **Automatic Checkpoints**: After each step/task/branch completion, session state is saved to `~/.strands/sessions/`
- **Agent Conversation Restoration**: Full conversation history restored on resume via Strands SDK session management
- **Cost Optimization**: Completed steps are skipped; only remaining work is executed
- **Spec Validation**: CLI warns if workflow spec has changed since session creation (but allows execution)
- **Token Tracking**: Cumulative token usage preserved across resume sessions

### Supported Patterns

- ✅ **Chain**: Full resume support with step skipping and conversation restoration
  - Resumes from any step (0 to N-1)
  - Agent conversation history preserved via FileSessionManager
  - Token usage accumulates across resume sessions
  - Spec change detection with warnings

- 🚧 **Other Patterns**: Multi-pattern support under development
  - Workflow, Parallel, Routing, Graph patterns

### Example: Resume After Crash

```bash
# Start a 3-step chain workflow
uv run strands run examples/chain-3-step-resume-demo.yaml --var topic="AI agents"

# Note the session ID in output: "Session ID: a1b2c3d4..."

# Simulate crash (Ctrl+C) after step 2

# Resume from checkpoint (skips steps 0-1, executes only remaining steps)
uv run strands run --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### Session Storage Structure

```
~/.strands/sessions/  (or %USERPROFILE%\.strands\sessions\ on Windows)
└── session_<uuid>/
    ├── session.json              # Metadata, variables, token usage
    ├── pattern_state.json        # Execution state (step history, current position)
    ├── spec_snapshot.yaml        # Original workflow spec (for change detection)
    └── agents/                   # Strands SDK agent conversation sessions
        └── <session-id>_<agent-id>/
            ├── agent.json        # Agent state and configuration
            └── messages/         # Full conversation history
                ├── message_0.json
                ├── message_1.json
                └── ...
```

---

## Core Concepts

### Workflow Patterns

Strands CLI supports seven execution patterns, each optimized for different use cases:

#### 1. Chain Pattern
Sequential execution with context passing between steps.

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Research {{ topic }}"
      - agent_id: writer
        prompt: "Write a summary based on: {{ steps[0].response }}"
      - agent_id: editor
        prompt: "Edit this draft: {{ steps[1].response }}"
```

**Use cases:** Research → Write → Edit pipelines, multi-stage processing

#### 2. Workflow Pattern
DAG-based parallel execution with dependency resolution.

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: fetch_data
        agent_id: fetcher
        prompt: "Fetch data for {{ query }}"
      
      - id: analyze_data
        agent_id: analyst
        depends_on: [fetch_data]
        prompt: "Analyze: {{ tasks.fetch_data.response }}"
      
      - id: visualize_data
        agent_id: visualizer
        depends_on: [fetch_data]
        prompt: "Visualize: {{ tasks.fetch_data.response }}"
      
      - id: report
        agent_id: reporter
        depends_on: [analyze_data, visualize_data]
        prompt: "Create report from analysis and visualization"
```

**Use cases:** Data pipelines, parallel processing with dependencies

#### 3. Routing Pattern
Dynamic agent selection based on input classification.

```yaml
pattern:
  type: routing
  config:
    classifier_id: router
    routes:
      - agent_id: tech_support
        condition: "technical issue"
      - agent_id: sales
        condition: "pricing or purchase"
      - agent_id: general
        condition: "general inquiry"
```

**Use cases:** Customer support routing, task classification, conditional execution

#### 4. Parallel Pattern
Concurrent execution with optional result aggregation.

```yaml
pattern:
  type: parallel
  config:
    branches:
      - id: perspective_a
        agent_id: analyst_a
        steps:
          - prompt: "Analyze from perspective A"
      
      - id: perspective_b
        agent_id: analyst_b
        steps:
          - prompt: "Analyze from perspective B"
    
    reduce:
      agent_id: synthesizer
      prompt: "Synthesize: {{ branches.perspective_a.response }} and {{ branches.perspective_b.response }}"
```

**Use cases:** Multi-perspective analysis, A/B testing, concurrent research

#### 5. Evaluator-Optimizer Pattern
Iterative refinement with quality gates.

```yaml
pattern:
  type: evaluator_optimizer
  config:
    generator_id: writer
    evaluator_id: critic
    max_iterations: 5
    acceptance:
      min_score: 8.0
      convergence_threshold: 0.1
```

**Use cases:** Iterative content improvement, quality-driven generation

#### 6. Orchestrator-Workers Pattern
Dynamic task delegation to worker pools.

```yaml
pattern:
  type: orchestrator_workers
  config:
    orchestrator:
      agent_id: task_planner
      limits:
        max_workers: 5
        max_rounds: 3
    
    worker_template:
      agent_id: worker
    
    reduce:
      agent_id: aggregator
```

**Use cases:** Dynamic task decomposition, research swarms, data processing

#### 7. Graph Pattern
Explicit control flow with conditionals and loops.

```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: start
        agent_id: analyzer
        edges:
          - choose:
              - when: "{{ node.start.response.needs_refinement }}"
                to: refine
              - when: "{{ node.start.response.is_complete }}"
                to: finalize
      
      - id: refine
        agent_id: refiner
        edges:
          - to: start  # Loop back
      
      - id: finalize
        agent_id: finalizer
```

**Use cases:** State machines, iterative refinement with conditionals, decision trees

### Template Variables

Access execution context in prompts and artifact outputs:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{ last_response }}` | Most recent agent response | Basic chain output |
| `{{ steps[0].response }}` | Specific step output (0-indexed) | Reference earlier step |
| `{{ tasks.task_id.response }}` | Task output by ID | Workflow DAG results |
| `{{ branches.branch_id.response }}` | Branch output by ID | Parallel execution results |
| `{{ nodes.node_id.response }}` | Node output by ID | Graph execution results |
| `{{ $TRACE }}` | Complete execution trace | Debugging/observability |

**Example artifact with templates:**

```yaml
outputs:
  artifacts:
    - path: "./report-{{ topic }}.md"
      from: |
        # Research Report: {{ topic }}
        
        ## Initial Analysis
        {{ steps[0].response }}
        
        ## Detailed Findings
        {{ steps[1].response }}
        
        ## Conclusions
        {{ steps[2].response }}
```

### Budget Enforcement

Control resource usage with token and time limits:

```yaml
runtime:
  budgets:
    max_tokens: 100000  # Total tokens across all LLM calls
    max_duration_s: 300  # Maximum execution time (5 minutes)
```

**Behavior:**
- **80% threshold**: Warning logged, execution continues
- **100% threshold**: Execution halts with `BudgetExceededError`
- **Cumulative tracking**: Tokens summed across all steps/tasks/branches

### Concurrency Control

Limit parallel execution with semaphores:

```yaml
runtime:
  max_parallel: 3  # Max 3 concurrent tasks/branches
```

**Applies to:**
- Workflow tasks (when dependencies allow)
- Parallel branches
- Orchestrator workers

---

## CLI Commands

### `strands run`

Execute a workflow from a YAML/JSON specification.

```bash
# Basic execution (with session saving enabled by default)
uv run strands run workflow.yaml

# Override variables
uv run strands run workflow.yaml --var topic="AI" --var format="markdown"

# Resume from saved session
uv run strands run --resume <session-id>

# Resume from HITL pause with user response
uv run strands run --resume <session-id> --hitl-response "approved"

# Disable session saving
uv run strands run workflow.yaml --no-save-session

# Custom output directory
uv run strands run workflow.yaml --out ./results

# Force overwrite existing artifacts
uv run strands run workflow.yaml --force

# Skip file_write consent prompts (for CI/CD)
uv run strands run workflow.yaml --bypass-tool-consent

# Generate trace artifact
uv run strands run workflow.yaml --trace

# Enable debug logging
uv run strands run workflow.yaml --debug

# Combine options
uv run strands run workflow.yaml --var topic="ML" --trace --debug --force
```

**Exit codes:**
- `0` - Success
- `3` - Schema validation failed
- `10` - Runtime error (provider/model/tool)
- `12` - I/O error (artifact write)
- `18` - Unsupported features detected
- `19` - HITL pause (workflow waiting for human input)
- `20` - Session error (load/save failure)
- `70` - Unexpected error

### `strands validate`

Validate a workflow spec against the JSON Schema.

```bash
uv run strands validate workflow.yaml

# With debug output
uv run strands validate workflow.yaml --debug --verbose
```

**Output:**
```
✓ Spec is valid: my-workflow
  Version: 1
  Agents: 3
  Pattern: chain
```

### `strands plan`

Display execution plan without running the workflow.

```bash
# Human-readable Markdown format (default)
uv run strands plan workflow.yaml

# JSON format for scripting
uv run strands plan workflow.yaml --format=json

# With debug output
uv run strands plan workflow.yaml --debug
```

**Output includes:**
- Runtime configuration (provider, model, region)
- Agent inventory
- Pattern type and configuration
- MVP compatibility status
- Graph visualization (for graph patterns)

### `strands explain`

Show unsupported features and migration guidance.

```bash
uv run strands explain legacy-workflow.yaml
```

**Output:**
```
Unsupported Features in legacy-workflow:

1. /pattern/type
   Reason: Pattern 'custom_pattern' is not supported
   → Remediation: Use one of: chain, workflow, routing, parallel, evaluator_optimizer, orchestrator_workers, graph

2. /tools/mcp
   Reason: MCP tools are experimental
   → Remediation: Use http_executors or allowlisted Python tools
```

### `strands list-supported`

Display all supported features in the current version.

```bash
uv run strands list-supported
```

### `strands list-tools`

List all available native tools from the registry.

```bash
uv run strands list-tools
```

### `strands doctor`

Run diagnostic checks on your installation.

```bash
uv run strands doctor
```

**Checks:**
- Python version (≥3.12)
- Schema file integrity
- Core dependencies
- Ollama connectivity (optional)

### `strands version`

Show the CLI version.

```bash
uv run strands version
# Output: strands-cli version 0.4.0
```

### `strands sessions`

Manage saved workflow sessions for resume capabilities.

```bash
# List all sessions
uv run strands sessions list

# Filter by status
uv run strands sessions list --status running
uv run strands sessions list --status completed
uv run strands sessions list --status failed

# Show detailed session information
uv run strands sessions show <session-id>

# Delete a session
uv run strands sessions delete <session-id>

# Delete without confirmation prompt
uv run strands sessions delete <session-id> --force
```

**Session list output:**
```
Sessions:

1. a1b2c3d4-e5f6-7890-abcd-ef1234567890
   Workflow: chain-3-step-research
   Pattern: chain
   Status: completed
   Created: 2025-11-09T10:00:00Z
   Updated: 2025-11-09T10:15:23Z

2. b2c3d4e5-f6a7-8901-bcde-f12345678901
   Workflow: parallel-analysis
   Pattern: parallel
   Status: running
   Created: 2025-11-09T11:30:00Z
   Updated: 2025-11-09T11:45:12Z
```

---

## Configuration

### Environment Variables

Configure Strands CLI behavior with environment variables (prefix: `STRANDS_`):

| Variable | Description | Default |
|----------|-------------|---------|
| `STRANDS_AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `STRANDS_BEDROCK_MODEL_ID` | Default Bedrock model | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `STRANDS_VERBOSE` | Enable verbose logging | `false` |
| `STRANDS_DEBUG` | Enable debug logging | `false` |
| `STRANDS_CONFIG_DIR` | Config directory path | `~/.config/strands` (Linux/macOS)<br>`%APPDATA%\strands` (Windows) |
| `STRANDS_MAX_TRACE_SPANS` | Max spans in trace collector | `1000` |
| `STRANDS_SESSION_DIR` | Session storage directory | `~/.strands/sessions` (Linux/macOS)<br>`%USERPROFILE%\.strands\sessions` (Windows) |
| `OPENAI_API_KEY` | OpenAI API key | *(required for OpenAI provider)* |

**Example:**

```bash
# Set AWS region
export STRANDS_AWS_REGION=us-west-2

# Set OpenAI API key
export OPENAI_API_KEY=sk-...

# Increase trace span limit for long workflows
export STRANDS_MAX_TRACE_SPANS=5000
```

### Runtime Configuration

Specify provider and model in workflow specs:

```yaml
runtime:
  # Provider selection
  provider: bedrock  # or ollama, openai
  
  # Model configuration
  model_id: anthropic.claude-3-sonnet-20240229-v1:0
  
  # AWS-specific
  region: us-east-1
  
  # Ollama-specific
  host: http://localhost:11434
  
  # Budgets
  budgets:
    max_tokens: 100000
    max_duration_s: 600
  
  # Concurrency
  max_parallel: 5
  
  # Retries
  failure_policy:
    retry_count: 3
    wait_min: 1.0
    wait_max: 10.0
```

### Security Configuration

Configure security features for production deployments:

```yaml
# Block additional HTTP endpoints
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://internal\.company\.com"]'

# Enforce HTTP allowlist
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\.openai\.com", "^https://api\.anthropic\.com"]'
```

---

## Observability & Debugging

### OpenTelemetry Tracing

Enable production observability with OTLP exporters:

```yaml
telemetry:
  otel:
    enabled: true
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
    sample_ratio: 1.0  # 100% sampling
    exporter: otlp  # or console
  
  redact:
    tool_inputs: true   # Redact PII from tool inputs
    tool_outputs: true  # Redact PII from tool outputs
```

**Supported backends:**
- Jaeger
- Zipkin
- Honeycomb
- Any OTLP-compatible collector

**Span hierarchy:**
```
execute.chain
├── execute.chain.step[0]
│   ├── llm.completion
│   └── tool.http_request
├── execute.chain.step[1]
│   └── llm.completion
└── execute.chain.step[2]
    └── llm.completion
```

### Trace Artifacts

Export execution traces to JSON for analysis:

**Method 1: Template variable**
```yaml
outputs:
  artifacts:
    - path: "./traces/{{ spec.name }}-trace.json"
      from: "{{ $TRACE }}"
```

**Method 2: CLI flag**
```bash
uv run strands run workflow.yaml --trace
# Generates: ./artifacts/workflow-trace.json
```

**Trace format:**
```json
{
  "metadata": {
    "spec_name": "my-workflow",
    "pattern_type": "chain",
    "total_duration_ms": 5234.56
  },
  "trace_id": "abc123...",
  "spans": [
    {
      "span_id": "def456...",
      "name": "execute.chain.step[0]",
      "start_time": "2025-11-09T10:30:00Z",
      "end_time": "2025-11-09T10:30:02Z",
      "attributes": {
        "agent.id": "researcher",
        "runtime.provider": "bedrock",
        "runtime.model_id": "claude-3-sonnet-20240229-v1:0"
      }
    }
  ]
}
```

### PII Redaction

Automatically scrub sensitive data from traces:

**Redacted patterns:**
- Email addresses: `user@example.com` → `***REDACTED***`
- Credit cards: `4111-1111-1111-1111` → `***REDACTED***`
- SSN: `123-45-6789` → `***REDACTED***`
- Phone numbers: `555-123-4567` → `***REDACTED***`
- API keys: Long alphanumeric strings → `***REDACTED***`

**Custom patterns:**
```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
    custom_patterns:
      - '\bINTERNAL-[A-Z0-9]{8}\b'  # Internal IDs
      - '\b[A-Z]{3}-\d{6}\b'         # Ticket numbers
```

### Debug Logging

Enable structured debug logging for troubleshooting:

```bash
uv run strands run workflow.yaml --debug
```

**Debug output includes:**
- Variable resolution steps (parse → merge → final context)
- Template rendering (before/after with previews)
- Capability check details
- Agent cache hits/misses
- LLM request/response metadata

**Example output:**
```
[DEBUG] variable.resolution parsed_vars={'topic': 'AI'} source='cli_flags'
[DEBUG] template.render template='{{ topic }}' rendered='AI' truncated=False
[DEBUG] agent_cache.miss agent_id='researcher' reason='first_use'
[DEBUG] llm.request provider='bedrock' model='claude-3-sonnet' input_tokens=245
[DEBUG] llm.response output_tokens=1523 duration_ms=2341.2
[DEBUG] agent_cache.hit agent_id='researcher' reused=True
```

---

## Examples

The [`examples/`](examples/) directory contains 50+ workflow specifications demonstrating all patterns and features.

### Chain Pattern Examples

- [`single-agent-chain-ollama.yaml`](examples/single-agent-chain-ollama.yaml) - Basic sequential workflow
- [`chain-3-step-research-openai.yaml`](examples/chain-3-step-research-openai.yaml) - Research → Write → Edit pipeline
- [`chain-calculator-openai.yaml`](examples/chain-calculator-openai.yaml) - Multi-step math with calculator tool
- [`chain-hitl-approval-demo.yaml`](examples/chain-hitl-approval-demo.yaml) - Human-in-the-loop approval gate

### Workflow Pattern Examples

- [`single-agent-workflow-ollama.yaml`](examples/single-agent-workflow-ollama.yaml) - Basic DAG workflow
- [`workflow-parallel-research-openai.yaml`](examples/workflow-parallel-research-openai.yaml) - Parallel data collection
- [`workflow-linear-dag-openai.yaml`](examples/workflow-linear-dag-openai.yaml) - Linear dependency chain

### Routing Pattern Examples

- [`routing-customer-support-openai.yaml`](examples/routing-customer-support-openai.yaml) - Support ticket routing
- [`routing-task-classification-openai.yaml`](examples/routing-task-classification-openai.yaml) - Dynamic task routing
- [`routing-multi-tool-openai.yaml`](examples/routing-multi-tool-openai.yaml) - Tool-specific routing

### Parallel Pattern Examples

- [`parallel-simple-2-branches.yaml`](examples/parallel-simple-2-branches.yaml) - Basic concurrent execution
- [`parallel-with-reduce.yaml`](examples/parallel-with-reduce.yaml) - Multi-perspective analysis with synthesis
- [`parallel-multi-step-branches.yaml`](examples/parallel-multi-step-branches.yaml) - Complex multi-step branches

### Evaluator-Optimizer Examples

- [`evaluator-optimizer-writing-openai.yaml`](examples/evaluator-optimizer-writing-openai.yaml) - Iterative writing improvement
- [`evaluator-optimizer-code-review-openai.yaml`](examples/evaluator-optimizer-code-review-openai.yaml) - Code quality iteration

### Orchestrator-Workers Examples

- [`orchestrator-research-swarm-openai.yaml`](examples/orchestrator-research-swarm-openai.yaml) - Research task delegation
- [`orchestrator-data-processing-openai.yaml`](examples/orchestrator-data-processing-openai.yaml) - Data processing swarm
- [`orchestrator-minimal-openai.yaml`](examples/orchestrator-minimal-openai.yaml) - Minimal orchestrator setup

### Graph Pattern Examples

- [`graph-decision-tree-openai.yaml`](examples/graph-decision-tree-openai.yaml) - Multi-branch decision tree
- [`graph-iterative-refinement-openai.yaml`](examples/graph-iterative-refinement-openai.yaml) - Loop-based refinement
- [`graph-state-machine-openai.yaml`](examples/graph-state-machine-openai.yaml) - State machine workflow

### Telemetry & Debugging Examples

- [`telemetry-simple-openai.yaml`](examples/telemetry-simple-openai.yaml) - Basic OTLP tracing
- [`telemetry-redaction-demo-openai.yaml`](examples/telemetry-redaction-demo-openai.yaml) - PII redaction demo
- [`debug-demo-openai.yaml`](examples/debug-demo-openai.yaml) - Debug logging examples

### Tool Usage Examples

- [`simple-file-read-openai.yaml`](examples/simple-file-read-openai.yaml) - File reading
- [`workflow-file-operations-openai.yaml`](examples/workflow-file-operations-openai.yaml) - File read/write
- [`github-api-example-openai.yaml`](examples/github-api-example-openai.yaml) - HTTP executor with GitHub API

---

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/ThomasRohde/strands-cli.git
cd strands-cli

# Install dependencies (including dev tools)
uv sync --dev

# Verify installation
uv run strands doctor
```

### Development Commands

**PowerShell automation** (recommended on Windows):

```powershell
.\scripts\dev.ps1 test          # Run all tests
.\scripts\dev.ps1 test-cov      # Tests + coverage report
.\scripts\dev.ps1 lint          # Ruff linting
.\scripts\dev.ps1 format        # Auto-format code
.\scripts\dev.ps1 typecheck     # Mypy strict type checking
.\scripts\dev.ps1 ci            # Full CI pipeline (lint + typecheck + test-cov)
.\scripts\dev.ps1 validate-examples  # Validate all example specs
```

**Direct commands** (cross-platform):

```bash
uv run pytest                                           # Run tests
uv run pytest --cov=src/strands_cli --cov-report=html  # Coverage report
uv run ruff check .                                     # Lint
uv run ruff format .                                    # Format
uv run mypy src                                         # Type check
```

### Code Quality Requirements

Before committing, ensure all checks pass:

```powershell
.\scripts\dev.ps1 ci
```

**Requirements:**
- ✅ Ruff linting (zero violations)
- ✅ Mypy type checking (strict mode)
- ✅ Pytest (all 795+ tests passing)
- ✅ Coverage ≥83%

### Project Structure

```
strands-cli/
├── src/strands_cli/          # Main package
│   ├── __main__.py           # CLI entry point (Typer)
│   ├── types.py              # Pydantic models
│   ├── config.py             # Settings
│   ├── exit_codes.py         # Exit code constants
│   ├── session/              # Durable session management
│   │   ├── __init__.py       # Session models
│   │   ├── file_repository.py # File-based persistence
│   │   ├── utils.py          # Session utilities
│   │   └── resume.py         # Resume logic
│   ├── schema/               # JSON Schema validation
│   │   ├── strands-workflow.schema.json
│   │   └── validator.py
│   ├── loader/               # YAML/JSON parsing
│   │   ├── yaml_loader.py
│   │   └── template.py       # Jinja2 rendering
│   ├── capability/           # MVP constraint checking
│   │   ├── checker.py
│   │   └── reporter.py
│   ├── runtime/              # Provider adapters
│   │   ├── providers.py      # Bedrock/Ollama/OpenAI clients
│   │   ├── strands_adapter.py
│   │   └── tools.py          # Tool adapters
│   ├── exec/                 # Workflow executors
│   │   ├── single_agent.py
│   │   ├── chain.py
│   │   ├── workflow.py
│   │   ├── routing.py
│   │   ├── parallel.py
│   │   ├── evaluator_optimizer.py
│   │   ├── orchestrator_workers.py
│   │   └── graph.py
│   ├── artifacts/            # Output handling
│   │   └── io.py
│   ├── telemetry/            # Observability
│   │   ├── otel.py           # OpenTelemetry
│   │   └── redaction.py      # PII scrubbing
│   └── tools/                # Native tool registry
│       ├── registry.py
│       └── python_exec.py
├── tests/                    # Test suite (805+ tests, 80% coverage)
│   ├── conftest.py           # Shared fixtures
│   ├── test_schema.py
│   ├── test_loader.py
│   ├── test_capability.py
│   ├── test_runtime.py
│   ├── test_session.py       # Session persistence tests
│   ├── test_chain.py
│   ├── test_chain_resume.py  # Chain resume integration tests
│   ├── test_workflow.py
│   ├── test_routing.py
│   ├── test_parallel.py
│   ├── test_evaluator_optimizer.py
│   ├── test_orchestrator_workers.py
│   ├── test_graph.py
│   └── test_e2e.py
├── examples/                 # 50+ workflow examples
├── scripts/                  # Automation
│   └── dev.ps1               # PowerShell dev workflow
├── pyproject.toml            # Project config
├── README.md                 # This file
├── CHANGELOG.md              # Version history
└── CONTRIBUTING.md           # Contribution guidelines
```

### Adding Features

1. **Update JSON Schema** (`src/strands_cli/schema/strands-workflow.schema.json`)
2. **Update Pydantic models** (`src/strands_cli/types.py`)
3. **Write tests first** (TDD approach)
4. **Implement feature** (follow existing patterns)
5. **Run CI pipeline** (`.\scripts\dev.ps1 ci`)
6. **Update docs** (`README.md`, `CHANGELOG.md`)
7. **Submit PR** (see [`CONTRIBUTING.md`](CONTRIBUTING.md))

### Writing Native Tools

Create new tools in `src/strands_cli/tools/`:

```python
"""My custom tool."""

from typing import Any

# Required: Export TOOL_SPEC for auto-discovery
TOOL_SPEC = {
    "name": "my_tool",
    "description": "What my tool does",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "param": {"type": "string"}
            },
            "required": ["param"]
        }
    }
}

def my_tool(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Tool implementation."""
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    
    try:
        result = f"Processed: {tool_input.get('param')}"
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": result}]
        }
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": str(e)}]
        }
```

---

## Documentation

### Core Documentation

- **[Contributing](CONTRIBUTING.md)** - Development workflow and code conventions
- **[Changelog](CHANGELOG.md)** - Version history and migration guides

### Schema Reference

- **JSON Schema**: [`src/strands_cli/schema/strands-workflow.schema.json`](src/strands_cli/schema/strands-workflow.schema.json)
- **Validation**: Draft 2020-12 with JSONPointer error reporting

### Additional Resources

- **Examples**: [`examples/`](examples/) - 50+ workflow specifications

---

## Troubleshooting

### Schema Validation Errors (Exit Code 3)

```bash
# Get detailed error with JSONPointer
uv run strands validate workflow.yaml --verbose
```

**Common issues:**
- Missing required fields (check schema for `required` array)
- Type mismatches (e.g., string instead of array)
- Unknown properties (schema uses `"additionalProperties": false`)

### Unsupported Features (Exit Code 18)

```bash
# Get remediation guidance
uv run strands explain workflow.yaml
```

**Common patterns:**
- MCP tools → Use `http_executors` or Python tools
- Custom patterns → Use one of the 7 supported patterns
- Secrets Manager → Use `source: env`

### Runtime Errors (Exit Code 10)

**Bedrock connectivity:**
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Test Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

**Ollama connectivity:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

**OpenAI connectivity:**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Debugging Workflows

```bash
# Enable debug logging
uv run strands run workflow.yaml --debug --verbose

# Generate trace artifact for inspection
uv run strands run workflow.yaml --trace

# Check execution plan before running
uv run strands plan workflow.yaml
```

### Health Check

```bash
# Run comprehensive diagnostics
uv run strands doctor
```

---

## Features

### Workflow Execution
- **7 workflow patterns** - Chain, Workflow, Routing, Parallel, Evaluator-Optimizer, Orchestrator-Workers, Graph
- **Multi-provider support** - AWS Bedrock, Ollama, OpenAI
- **Python API & Builder API** - Programmatic workflow construction and execution
- **Interactive HITL workflows** - Human-in-the-loop with pause/resume
- **Durable session management** - Crash recovery and workflow resume (Chain pattern)

### Observability & Security
- **OpenTelemetry tracing** - Full OTLP export support
- **PII redaction** - Automatic sensitive data scrubbing
- **Trace artifacts** - Export execution traces to JSON
- **Security controls** - SSRF prevention, path traversal protection, sandboxed templates

### Tools & Integrations
- **Native tool registry** - Auto-discovery with TOOL_SPEC pattern
- **Built-in tools** - HTTP executors, file operations, calculator, time
- **MCP support** - Model Context Protocol integration (experimental)

### Performance
- **Agent caching** - 90% overhead reduction in multi-step workflows
- **Model client pooling** - LRU cache for provider clients
- **Async execution** - High-performance event loop architecture

See [`CHANGELOG.md`](CHANGELOG.md) for version history.

---

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for:

- Development setup
- Code style guidelines
- Testing requirements
- Pull request process
- Architecture guidelines

**Quick start:**

```bash
# Fork and clone
git clone https://github.com/YOUR-USERNAME/strands-cli.git
cd strands-cli

# Install dev dependencies
uv sync --dev

# Run tests
.\scripts\dev.ps1 ci

# Submit PR
```

---

## License

Apache-2.0 License - see [`LICENSE`](LICENSE) for details.

---

## Acknowledgments

Built with:
- [Strands Agents SDK](https://github.com/awslabs/strands) - Agent framework
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [OpenTelemetry](https://opentelemetry.io/) - Observability
- [Rich](https://rich.readthedocs.io/) - Terminal output

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ThomasRohde/strands-cli/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ThomasRohde/strands-cli/discussions)

---

<div align="center">

**[⬆ Back to Top](#strands-cli)**

Made with ❤️ by [Thomas Klok Rohde](https://github.com/ThomasRohde)

</div>

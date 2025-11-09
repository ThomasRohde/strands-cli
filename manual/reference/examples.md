# Example Workflows

Comprehensive catalog of workflow examples organized by pattern type and use case.

!!! tip "Running Examples"
    ```bash
    # Validate before running
    uv run strands validate examples/<file>.yaml
    
    # Run with required variables
    uv run strands run examples/<file>.yaml --var key=value
    
    # Force overwrite artifacts
    uv run strands run examples/<file>.yaml --force
    ```

## By Pattern Type

### Chain Pattern

Sequential multi-step workflows with context passing.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [chain-3-step-research-openai.yaml](../../examples/chain-3-step-research-openai.yaml) | Three-step research workflow with context passing | OpenAI | Sequential steps, `steps[n].response` references |
| [chain-3-step-research.yaml](../../examples/chain-3-step-research.yaml) | Same as above (Ollama) | Ollama | Budget limits, temperature control |
| [chain-calculator-openai.yaml](../../examples/chain-calculator-openai.yaml) | Multi-step calculation workflow | OpenAI | Calculator tool, step chaining |

**Learn More**: [Chain Pattern Guide](../howto/patterns/chain.md)

---

### Workflow (DAG) Pattern

Task-based workflows with dependency graphs.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [research-workflow-notes-openai.yaml](../../examples/research-workflow-notes-openai.yaml) | Research with structured notes | OpenAI | DAG dependencies, notes integration |

**Learn More**: [Workflow Pattern Guide](../howto/patterns/workflow.md)

---

### Routing Pattern

Dynamic agent selection based on classifier decisions.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [routing-customer-support-openai.yaml](../../examples/routing-customer-support-openai.yaml) | Customer support ticket routing | OpenAI | Multi-route classifier, dynamic paths |
| [routing-customer-support.yaml](../../examples/routing-customer-support.yaml) | Same as above (Ollama) | Ollama | Cost-effective routing |
| [routing-task-classification-openai.yaml](../../examples/routing-task-classification-openai.yaml) | Task classification router | OpenAI | Route selection logic |
| [routing-task-classification.yaml](../../examples/routing-task-classification.yaml) | Same as above (Ollama) | Ollama | Budget-friendly |
| [routing-multi-tool-openai.yaml](../../examples/routing-multi-tool-openai.yaml) | Tool selection based on request type | OpenAI | HTTP executors, dynamic tool routing |

**Learn More**: [Routing Pattern Guide](../howto/patterns/routing.md)

---

### Parallel Pattern

Concurrent branch execution with optional reduce step.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [parallel-simple-2-branches.yaml](../../examples/parallel-simple-2-branches.yaml) | Two-branch parallel execution | OpenAI | Basic parallel, no reduce |
| [parallel-with-reduce.yaml](../../examples/parallel-with-reduce.yaml) | Parallel branches with aggregation | OpenAI | Reduce step, branch merging |
| [parallel-multi-step-branches.yaml](../../examples/parallel-multi-step-branches.yaml) | Multi-step branches in parallel | OpenAI | Complex branches, sequential within parallel |

**Learn More**: [Parallel Pattern Guide](../howto/patterns/parallel.md)

---

### Evaluator-Optimizer Pattern

Iterative refinement with evaluation feedback loops.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [evaluator-optimizer-writing-openai.yaml](../../examples/evaluator-optimizer-writing-openai.yaml) | Content writing with iterative refinement | OpenAI | Min score threshold, max iterations |
| [evaluator-optimizer-writing-ollama.yaml](../../examples/evaluator-optimizer-writing-ollama.yaml) | Same as above (Ollama) | Ollama | Local model refinement |
| [evaluator-optimizer-code-review-openai.yaml](../../examples/evaluator-optimizer-code-review-openai.yaml) | Code review feedback loop | OpenAI | JSON scoring, structured feedback |
| [evaluator-optimizer-code-review-bedrock.yaml](../../examples/evaluator-optimizer-code-review-bedrock.yaml) | Same as above (Bedrock) | Bedrock | AWS Claude models |

**Learn More**: [Evaluator-Optimizer Pattern Guide](../howto/patterns/evaluator-optimizer.md)

---

### Orchestrator-Workers Pattern

Orchestrator decomposes tasks, workers execute in parallel.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [orchestrator-minimal-openai.yaml](../../examples/orchestrator-minimal-openai.yaml) | Minimal orchestrator example | OpenAI | Basic orchestration, worker pool |
| [orchestrator-research-swarm-openai.yaml](../../examples/orchestrator-research-swarm-openai.yaml) | Research team with orchestrator | OpenAI | Multi-worker coordination, reduce step |
| [orchestrator-data-processing-openai.yaml](../../examples/orchestrator-data-processing-openai.yaml) | Data processing pipeline | OpenAI | Parallel workers, aggregation |

**Learn More**: [Orchestrator-Workers Pattern Guide](../howto/patterns/orchestrator-workers.md)

---

### Graph Pattern

State machines with conditional transitions and loops.

| Example | Description | Provider | Key Features |
|---------|-------------|----------|--------------|
| [graph-state-machine-openai.yaml](../../examples/graph-state-machine-openai.yaml) | Customer support state machine | OpenAI | Conditional edges, terminal nodes |
| [graph-decision-tree-openai.yaml](../../examples/graph-decision-tree-openai.yaml) | Approval workflow decision tree | OpenAI | Multi-path decisions, `when` conditions |
| [graph-iterative-refinement-openai.yaml](../../examples/graph-iterative-refinement-openai.yaml) | Code review refinement loop | OpenAI | Iterative loops, cycle protection |

**Learn More**: [Graph Pattern Guide](../howto/patterns/graph.md)

---

## By Feature

### Context Management

Examples demonstrating Phase 6 context features.

| Example | Description | Features |
|---------|-------------|----------|
| [context-notes-demo-openai.yaml](../../examples/context-notes-demo-openai.yaml) | Structured notes across steps | `context_policy.notes`, note persistence |
| [presets-minimal-openai.yaml](../../examples/presets-minimal-openai.yaml) | Minimal context preset | `context_policy.preset: minimal` |
| [presets-balanced-openai.yaml](../../examples/presets-balanced-openai.yaml) | Balanced context preset | `context_policy.preset: balanced` |
| [presets-long_run-openai.yaml](../../examples/presets-long_run-research-openai.yaml) | Long-running research preset | `context_policy.preset: long_run` |
| [presets-interactive-chat-openai.yaml](../../examples/presets-interactive-chat-openai.yaml) | Interactive chat preset | `context_policy.preset: interactive` |

**Learn More**: [Context Management Guide](../howto/context-management.md)

---

### JIT Retrieval Tools

Just-In-Time file system tools for on-demand retrieval.

| Example | Description | Tools Used |
|---------|-------------|------------|
| [jit-codebase-analysis-openai.yaml](../../examples/jit-codebase-analysis-openai.yaml) | Codebase analysis with grep/search | `grep`, `search` |
| [jit-config-audit-openai.yaml](../../examples/jit-config-audit-openai.yaml) | Configuration file audit | `head`, `tail`, `grep` |
| [jit-log-analysis-openai.yaml](../../examples/jit-log-analysis-openai.yaml) | Log file analysis | `tail`, `grep` |
| [jit-tools-test-openai.yaml](../../examples/jit-tools-test-openai.yaml) | JIT tools test suite | All JIT tools |

**Learn More**: [Workflow Spec Reference - JIT Retrieval](workflow-manual.md#83-jit-retrieval-tools)

---

### Tools & Integrations

#### HTTP Executors

| Example | Description | Integration |
|---------|-------------|-------------|
| [github-api-example-openai.yaml](../../examples/github-api-example-openai.yaml) | GitHub API integration | GitHub REST API |

**Learn More**: [Tools Guide](../howto/tools.md)

---

#### MCP Servers

Model Context Protocol server integrations.

| Example | Description | MCP Server |
|---------|-------------|------------|
| [mcp-simple-openai.yaml](../../examples/mcp-simple-openai.yaml) | Basic MCP integration | Generic MCP server |
| [mcp-filesystem-openai.yaml](../../examples/mcp-filesystem-openai.yaml) | Filesystem MCP server | `@modelcontextprotocol/server-filesystem` |
| [mcp-multi-server-openai.yaml](../../examples/mcp-multi-server-openai.yaml) | Multiple MCP servers | Multiple servers |

**Learn More**: [Workflow Spec Reference - MCP](workflow-manual.md#tools)

---

#### Python Tools

| Example | Description | Tools |
|---------|-------------|-------|
| [python-exec-demo-openai.yaml](../../examples/python-exec-demo-openai.yaml) | Python code execution | `python_exec` native tool |

**Learn More**: [Develop Tools Guide](../howto/develop-tools.md)

---

### Telemetry & Observability

| Example | Description | Features |
|---------|-------------|----------|
| [debug-demo-openai.yaml](../../examples/debug-demo-openai.yaml) | Debug mode with verbose tracing | `telemetry.otel`, debug spans |

**Learn More**: [Telemetry Guide](../howto/telemetry.md)

---

## By Provider

### OpenAI Examples

All `*-openai.yaml` examples use OpenAI models (gpt-4o, gpt-4o-mini, gpt-5-nano).

**Setup**:
```bash
export OPENAI_API_KEY="sk-..."
uv run strands run examples/<file>-openai.yaml
```

---

### Bedrock Examples

All `*-bedrock.yaml` examples use AWS Bedrock (Claude models).

**Setup**:
```bash
aws configure  # Set credentials and region
uv run strands run examples/<file>-bedrock.yaml
```

**Available**:
- [evaluator-optimizer-code-review-bedrock.yaml](../../examples/evaluator-optimizer-code-review-bedrock.yaml)

---

### Ollama Examples

All `*-ollama.yaml` or non-provider-suffixed examples use Ollama (local models).

**Setup**:
```bash
ollama serve  # Start Ollama server
ollama pull llama3.2:3b  # Pull model
uv run strands run examples/<file>.yaml
```

**Available**:
- [chain-3-step-research.yaml](../../examples/chain-3-step-research.yaml)
- [evaluator-optimizer-writing-ollama.yaml](../../examples/evaluator-optimizer-writing-ollama.yaml)
- [routing-customer-support.yaml](../../examples/routing-customer-support.yaml)
- [routing-task-classification.yaml](../../examples/routing-task-classification.yaml)
- And more...

---

## Special Examples

### Backward Compatibility

| Example | Description | Purpose |
|---------|-------------|---------|
| [backward-compatibility-test.yaml](../../examples/backward-compatibility-test.yaml) | Tests legacy format compatibility | Regression testing |

---

### Unsupported Features (Exit Code 18)

Examples demonstrating unsupported MVP features (will fail with explanatory report).

| Example | Description | Unsupported Feature |
|---------|-------------|---------------------|
| [multi-agent-unsupported.yaml](../../examples/multi-agent-unsupported.yaml) | Multiple agents | Multiple agents in same workflow |
| [multi-step-unsupported.yaml](../../examples/multi-step-unsupported.yaml) | Multi-step chain | Chain with >1 step |

**Learn More**: [Exit Codes Reference](exit-codes.md)

---

## Example Template

Want to create your own? Use this template:

```yaml
version: 0
name: "my-workflow"
description: "Brief description of what this workflow does"
tags: ["pattern-type", "use-case"]

runtime:
  provider: openai  # or bedrock, ollama
  model_id: "gpt-4o-mini"
  temperature: 0.7
  budgets:
    max_tokens: 50000
    max_steps: 100

agents:
  assistant:
    prompt: |
      You are a helpful assistant.
      Task: {{ task_description }}

pattern:
  type: chain  # or workflow, routing, parallel, evaluator_optimizer, orchestrator_workers, graph
  config:
    steps:
      - agent: assistant
        input: "{{ user_input }}"

inputs:
  required:
    user_input: string
  optional:
    task_description:
      type: string
      default: "Help the user"

outputs:
  artifacts:
    - path: "./result.md"
      from: "{{ last_response }}"
```

---

## Contributing Examples

Have a useful workflow? Consider contributing!

1. Follow the naming convention: `<pattern>-<use-case>-<provider>.yaml`
2. Add clear `description` and `tags`
3. Include `inputs.required` documentation
4. Test with `strands validate` and `strands run`
5. Submit PR with example + entry in this catalog

**See**: [CONTRIBUTING.md](../../CONTRIBUTING.md)

---

## Quick Reference

**Pattern Guides**:
- [Chain](../howto/patterns/chain.md)
- [Workflow](../howto/patterns/workflow.md)
- [Routing](../howto/patterns/routing.md)
- [Parallel](../howto/patterns/parallel.md)
- [Evaluator-Optimizer](../howto/patterns/evaluator-optimizer.md)
- [Orchestrator-Workers](../howto/patterns/orchestrator-workers.md)
- [Graph](../howto/patterns/graph.md)

**Feature Guides**:
- [Context Management](../howto/context-management.md)
- [Telemetry](../howto/telemetry.md)
- [Tools](../howto/tools.md)
- [Develop Tools](../howto/develop-tools.md)

**Reference**:
- [Complete Workflow Manual](workflow-manual.md)
- [Spec Quick Reference](spec.md)
- [Exit Codes](exit-codes.md)
- [Environment Variables](environment.md)

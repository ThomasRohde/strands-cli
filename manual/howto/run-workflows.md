---
title: Running Workflows
description: Execute workflows with variable overrides, debugging, and output control
keywords: run, execute, workflow, variables, override, debug, verbose, output, artifacts, trace
---

# How to Run Workflows

This guide shows you how to execute Strands workflows with various options and configurations.

## Basic Execution

Run a workflow with default settings:

```bash
strands run workflow.yaml
```

The workflow will execute and display output in the console.

## Command-Line Options

### Variable Overrides

Override variables defined in your workflow:

```bash
strands run workflow.yaml --var topic="Machine Learning" --var format="markdown"
```

Variables are substituted using Jinja2 templates in your workflow:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent_id: writer
        prompt: "Write about {{ topic }} in {{ format }} format"
```

### Interactive Variable Prompting

Use the `--ask` flag to prompt interactively for missing required variables:

```bash
# Prompt for all missing required variables
strands run workflow.yaml --ask
```

**How it works:**

1. CLI detects required variables without values or defaults
2. Prompts user for each missing variable with type coercion
3. Supports `string`, `integer`, `number`, and `boolean` types
4. Shows descriptions and enum choices if defined in spec
5. Retries on invalid input (e.g., "abc" for integer type)

**Example workflow with required variables:**

```yaml
inputs:
  required:
    topic:
      type: string
      description: "Topic to research"
    
    word_limit:
      type: integer
      description: "Maximum word count"
    
    format:
      type: string
      description: "Output format"
      enum: ["markdown", "html", "plain"]
```

**Interactive session:**

```bash
$ strands run workflow.yaml --ask

╭─────────────── Interactive Variable Input ───────────────╮
│ ⚠  Required variables missing: 3                         │
│                                                           │
│ Please provide values for the following variables.       │
│ Simply type your answer and press Enter.                 │
╰───────────────────────────────────────────────────────────╯

╭──────────────────── Variable Input ─────────────────────╮
│ topic                                                    │
│ Research topic or question to investigate deeply         │
│                                                          │
│ Example: AI safety alignment                             │
╰──────────────────────────────────────────────────────────╯
Enter value: AI safety

✓ Accepted: AI safety

╭──────────────────── Variable Input ─────────────────────╮
│ depth                                                    │
│ Research depth level                                     │
│                                                          │
│ Choices: quick, standard, comprehensive                  │
│ Example: quick                                           │
╰──────────────────────────────────────────────────────────╯
Enter value: comprehensive

✓ Accepted: comprehensive

╭──────────────────── Variable Input ─────────────────────╮
│ max_sources                                              │
│ Maximum sources per search (3-10 recommended)            │
│                                                          │
│ Type: integer                                            │
│ Example: 42                                              │
╰──────────────────────────────────────────────────────────╯
Enter value: 8

✓ Accepted: 8

╭────────────── Variables Collected ───────────────────────╮
│ ✓ All variables collected successfully!                  │
│                                                          │
│   topic: AI safety                                       │
│   depth: comprehensive                                   │
│   max_sources: 8                                         │
╰──────────────────────────────────────────────────────────╯

Running workflow: my-workflow
...
```

**Combining with --var:**

You can mix `--var` flags with `--ask` to provide some variables via CLI and prompt for the rest:

```bash
# Provide format via CLI, prompt for topic and word_limit
strands run workflow.yaml --var format="markdown" --ask
```

**Non-interactive mode (CI/CD):**

In non-interactive environments (piped input, CI/CD), `--ask` will fail with a helpful error message:

```bash
$ echo "data" | strands run workflow.yaml --ask

Error: Cannot prompt for variables in non-interactive mode

Missing required variables: topic, word_limit, format

To fix, choose one:
  1. Provide variables via --var flags:
     --var topic=<value> --var word_limit=<value> --var format=<value>
  2. Add default values in workflow spec (inputs.required.<var>.default)
  3. Run in interactive terminal (not piped/CI/CD)
```

**See also:** [`examples/chain-interactive-prompts-openai.yaml`](../../examples/chain-interactive-prompts-openai.yaml) for a complete example.

### Debug and Verbose Output

Enable detailed logging to troubleshoot issues:

```bash
# Debug mode with verbose output
strands run workflow.yaml --debug --verbose

# Debug only
strands run workflow.yaml --debug

# Verbose only
strands run workflow.yaml --verbose
```

Debug mode shows:
- Detailed execution traces
- Agent invocations and responses
- Context management operations
- Tool calls and results

### Artifact Output

Specify where to save workflow artifacts:

```bash
# Save to specific directory
strands run workflow.yaml --out ./output

# Default is current directory
strands run workflow.yaml
```

Artifacts include:
- Final workflow results
- Intermediate step outputs (if configured)
- Telemetry traces (if enabled)
- Execution metadata

### Telemetry Tracing

Enable OpenTelemetry tracing:

```bash
# Export trace to artifacts
strands run workflow.yaml --trace

# Trace is saved as artifacts/trace_<timestamp>.json
```

## Working with Different Providers

### AWS Bedrock

```bash
# Using default Bedrock configuration
strands run workflow-bedrock.yaml

# Override region
export STRANDS_AWS_REGION=us-west-2
strands run workflow-bedrock.yaml

# Override model
export STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-opus-20240229-v1:0
strands run workflow-bedrock.yaml
```

### Ollama

```bash
# Ensure Ollama is running
ollama serve

# Run workflow
strands run workflow-ollama.yaml

# Custom Ollama host
export OLLAMA_HOST=http://custom-host:11434
strands run workflow-ollama.yaml
```

### OpenAI

```bash
# Set API key
export OPENAI_API_KEY=sk-...

# Run workflow
strands run workflow-openai.yaml
```

## Execution Patterns

### Chain Pattern

Sequential steps with context threading:

```bash
strands run examples/chain-3-step-research.yaml
```

Output shows each step executing in order with results passed to next step.

### Workflow Pattern (DAG)

Parallel task execution with dependencies:

```bash
strands run examples/workflow-parallel-research.yaml
```

Tasks run concurrently where dependencies allow, then merge results.

### Routing Pattern

Dynamic agent selection:

```bash
strands run examples/routing-task-classification.yaml
```

The router agent selects the appropriate specialist based on input.

### Parallel Pattern

Concurrent branch execution:

```bash
strands run examples/parallel-simple-2-branches.yaml
```

All branches run simultaneously with optional reduce step.

### Evaluator-Optimizer Pattern

Iterative refinement:

```bash
strands run examples/evaluator-optimizer-writing.yaml
```

Content is refined until quality criteria are met.

### Orchestrator-Workers Pattern

Dynamic task delegation:

```bash
strands run examples/orchestrator-research-swarm.yaml
```

Orchestrator decomposes work and delegates to worker pool.

### Graph Pattern

State machine with conditionals:

```bash
strands run examples/graph-decision-tree.yaml
```

Execution follows conditional paths and loops.

## Output Customization

### Controlling Console Output

```bash
# Minimal output
strands run workflow.yaml

# Verbose with step-by-step details
strands run workflow.yaml --verbose

# Debug with full traces
strands run workflow.yaml --debug --verbose
```

### Artifact Configuration

In your workflow, configure artifact outputs:

```yaml
artifacts:
  - path: result.txt
    content: "{{ last_response }}"
  - path: trace.json
    content: "{{ $TRACE }}"
    format: json
```

Then run:

```bash
strands run workflow.yaml --artifacts-dir ./output
```

Results appear in:
- `./output/result.txt`
- `./output/trace.json`

## Error Handling

### Understanding Exit Codes

Strands uses specific exit codes for different error types:

```bash
strands run workflow.yaml
echo $?  # Check exit code
```

Exit codes:
- `0`: Success
- `2`: Invalid CLI usage
- `3`: Schema validation failed
- `10`: Runtime error (provider, model, tool)
- `12`: File I/O error
- `18`: Unsupported feature
- `70`: Unexpected error

### Handling Runtime Errors

If a workflow fails during execution:

```bash
# Run with debug to see detailed error
strands run workflow.yaml --debug --verbose
```

Common runtime errors:
- **Provider errors**: Check credentials, region, model availability
- **Tool errors**: Verify tool configuration and permissions
- **Timeout errors**: Increase timeout in runtime config
- **Budget exceeded**: Adjust token/time budgets

## Performance Optimization

### Agent Caching

Strands automatically caches agents with identical configurations. In multi-step workflows, this provides 90% overhead reduction.

No configuration needed - works automatically.

### Model Client Pooling

Model clients are automatically pooled and reused across steps. This reduces connection overhead for Bedrock, Ollama, and OpenAI.

### Context Management

Use presets to optimize context handling:

```yaml
runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  preset: balanced  # Options: minimal, balanced, long_run, interactive
```

Presets control:
- Maximum context size
- Compaction strategy
- Note retention
- Memory management

## Advanced Execution

### Using Presets

Presets provide pre-configured context management:

```bash
# Minimal context (fastest, lowest cost)
strands run workflow.yaml  # Uses minimal by default

# Balanced (good for most cases)
# Set in workflow: preset: balanced

# Long-running research (maximum context retention)
# Set in workflow: preset: long_run

# Interactive chat (conversational style)
# Set in workflow: preset: interactive
```

### Environment Variable Configuration

Set defaults via environment:

```bash
# AWS Bedrock
export STRANDS_AWS_REGION=us-east-1
export STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0

# Debug
export STRANDS_DEBUG=true
export STRANDS_VERBOSE=true

# Paths
export STRANDS_CONFIG_DIR=~/.config/strands

# Telemetry
export STRANDS_MAX_TRACE_SPANS=5000

# Run workflow
strands run workflow.yaml
```

### Batch Execution

Run multiple workflows:

```bash
# Bash
for workflow in workflows/*.yaml; do
  echo "Running $workflow"
  strands run "$workflow"
done

# PowerShell
Get-ChildItem workflows/*.yaml | ForEach-Object {
  Write-Host "Running $($_.Name)"
  strands run $_.FullName
}
```

### CI/CD Integration

Run workflows in continuous integration:

```yaml
# .github/workflows/execute.yml
name: Execute Workflows
on: [push]

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install Strands
        run: pip install strands-cli
      - name: Run workflow
        env:
          AWS_REGION: us-east-1
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: strands run workflow.yaml --artifacts-dir ./results
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: workflow-results
          path: ./results
```

## Monitoring and Observability

### Enable Telemetry

Configure OpenTelemetry in your workflow:

```yaml
telemetry:
  enabled: true
  otlp:
    endpoint: http://localhost:4318
    protocol: http
  console:
    enabled: true
  artifacts:
    enabled: true
```

Then run:

```bash
strands run workflow.yaml
```

Traces export to:
- OTLP collector (if configured)
- Console output (if enabled)
- Artifact files (if enabled)

### PII Redaction

Enable automatic PII scrubbing:

```yaml
telemetry:
  enabled: true
  redaction:
    enabled: true
    patterns:
      - email
      - credit_card
      - ssn
      - phone
```

## Troubleshooting

### Workflow Not Starting

Check validation:

```bash
strands validate workflow.yaml
strands plan workflow.yaml
```

### Provider Connection Issues

Verify credentials and connectivity:

```bash
# Bedrock - test AWS credentials
aws sts get-caller-identity

# Ollama - test connectivity
curl http://localhost:11434/api/tags

# OpenAI - verify API key
echo $OPENAI_API_KEY
```

### Performance Issues

Enable profiling:

```bash
strands run workflow.yaml --debug --verbose
```

Check for:
- Excessive context sizes
- Inefficient prompts
- Large tool outputs
- Network latency

### Getting Help

If issues persist:

1. Run with `--debug --verbose` for detailed logs
2. Check the [troubleshooting guide](../reference/troubleshooting.md)
3. Review [exit codes reference](../reference/exit-codes.md)
4. Check GitHub issues for similar problems

## See Also

- [Validate Workflows](validate-workflows.md) - Pre-execution validation
- [Context Management](context-management.md) - Optimize context handling
- [Telemetry](telemetry.md) - Observability and tracing
- [CLI Reference](../reference/cli.md) - Complete command documentation

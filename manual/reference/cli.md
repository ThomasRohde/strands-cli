---
title: CLI Reference
description: Complete command-line interface reference for all Strands commands
keywords: cli, command line, reference, run, validate, plan, explain, tools, version, commands
---

# CLI Reference

Complete command-line interface reference for Strands CLI.

## Installation

```bash
# Install with uv
uv pip install strands-cli

# Verify installation
strands version
```

## Global Options

All commands support the following global options:

- `--debug` - Enable debug logging
- `--verbose` - Enable verbose output
- `--help` - Show help message and exit

## Commands

### version

Display the current version of Strands CLI.

```bash
strands version
```

**Output**: Displays the semantic version number (e.g., `0.2.0`)

---

### run

Execute a workflow specification file.

```bash
strands run [OPTIONS] SPEC_FILE
```

**Arguments**:

- `SPEC_FILE` - Path to the YAML/JSON workflow specification file (required)

**Options**:

- `--var KEY=VALUE` - Override template variables (can be used multiple times)
- `--out TEXT` - Output directory for artifacts (default: current directory)
- `--format [json|text]` - Output format for results (default: `text`)
- `--force` - Force overwrite existing artifact files
- `--trace` - Enable trace artifact generation
- `--debug` - Enable debug logging
- `--verbose` - Enable verbose output

**Examples**:

```bash
# Basic execution
strands run workflow.yaml

# With variable overrides
strands run workflow.yaml --var topic="AI" --var format="markdown"

# Save artifacts to specific directory
strands run workflow.yaml --out ./output

# Enable debugging and tracing
strands run workflow.yaml --debug --verbose --trace

# JSON output format
strands run workflow.yaml --format json
```

**Exit Codes**:

- `0` - Success
- `2` - Invalid CLI usage
- `3` - Schema validation failure
- `10` - Runtime error (provider/model/tool)
- `12` - File I/O error
- `18` - Unsupported feature
- `70` - Unexpected exception

---

### validate

Validate a workflow specification against the JSON Schema.

```bash
strands validate [OPTIONS] SPEC_FILE
```

**Arguments**:

- `SPEC_FILE` - Path to the YAML/JSON workflow specification file (required)

**Options**:

- `--format [text|json]` - Output format (default: `text`)
- `--debug` - Enable debug logging

**Examples**:

```bash
# Validate a workflow
strands validate workflow.yaml

# JSON output
strands validate workflow.yaml --format json
```

**Output**:

- On success: Displays validation success message with workflow details
- On failure: Shows detailed validation errors with JSONPointer paths

---

### plan

Display an execution plan for a workflow without running it.

```bash
strands plan [OPTIONS] SPEC_FILE
```

**Arguments**:

- `SPEC_FILE` - Path to the YAML/JSON workflow specification file (required)

**Options**:

- `--format [text|json]` - Output format (default: `text`)
- `--debug` - Enable debug logging

**Examples**:

```bash
# Show execution plan
strands plan workflow.yaml

# JSON format
strands plan workflow.yaml --format json
```

**Output**:

Displays:
- Workflow metadata (name, description, pattern)
- Agent configurations
- Execution steps/tasks/branches/nodes
- Capability compatibility report
- Warnings for unsupported features

---

### explain

Explain a workflow specification in natural language.

```bash
strands explain [OPTIONS] SPEC_FILE
```

**Arguments**:

- `SPEC_FILE` - Path to the YAML/JSON workflow specification file (required)

**Options**:

- `--debug` - Enable debug logging

**Examples**:

```bash
# Get workflow explanation
strands explain workflow.yaml
```

**Output**:

Human-readable explanation of:
- What the workflow does
- Agent roles and configurations
- Execution flow
- Tool usage
- Context management strategy

---

### list-supported

List all supported workflow patterns and features.

```bash
strands list-supported
```

**Output**:

Displays a table of:
- Supported workflow patterns (Chain, Workflow, Routing, etc.)
- Supported providers (AWS Bedrock, Ollama, OpenAI)
- Available features and capabilities

---

### list-tools

List all available native tools.

```bash
strands list-tools [OPTIONS]
```

**Options**:

- `--format [text|json]` - Output format (default: `text`)

**Examples**:

```bash
# List tools
strands list-tools

# JSON format
strands list-tools --format json
```

**Output**:

Displays:
- Tool names
- Tool descriptions
- Input schema specifications
- Usage examples

---

### doctor

Run system health checks and display configuration.

```bash
strands doctor
```

**Output**:

Displays:
- Strands CLI version
- Python version
- Environment configuration
- Provider availability (AWS Bedrock, Ollama, OpenAI)
- Tool registry status
- Configuration directory
- System diagnostics

---

## Environment Variables

See [Environment Variables Reference](environment.md) for a complete list of supported environment variables.

## Exit Codes

See [Exit Codes Reference](exit-codes.md) for detailed exit code documentation.

## Common Workflows

### Development Workflow

```bash
# 1. Validate your workflow
strands validate workflow.yaml

# 2. Preview execution plan
strands plan workflow.yaml

# 3. Run with debugging
strands run workflow.yaml --debug --verbose

# 4. Generate trace for analysis
strands run workflow.yaml --trace --out ./traces
```

### CI/CD Integration

```bash
# Validate in CI pipeline
strands validate workflow.yaml --format json || exit 1

# Run workflow with controlled output
strands run workflow.yaml --out ./artifacts --force --format json
```

### Troubleshooting

```bash
# Check system health
strands doctor

# List available tools
strands list-tools

# Explain workflow behavior
strands explain workflow.yaml

# Run with maximum verbosity
strands run workflow.yaml --debug --verbose --trace
```

## See Also

- [Schema Reference](schema.md) - Workflow specification schema
- [Examples](examples.md) - Example workflows
- [Tutorials](../tutorials/quickstart-ollama.md) - Getting started guides

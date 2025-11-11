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

**Output**: Displays the semantic version number (e.g., `0.3.0`)

---

### run

Execute a workflow specification file.

```bash
strands run [OPTIONS] SPEC_FILE
```

**Arguments**:

- `SPEC_FILE` - Path to the YAML/JSON workflow specification file (optional when using --resume)

**Options**:

- `--var KEY=VALUE` - Override template variables (can be used multiple times)
- `--out TEXT` - Output directory for artifacts (default: `./artifacts`)
- `--force` - Force overwrite existing artifact files
- `--bypass-tool-consent` - Skip interactive tool confirmations (e.g., file_write prompts). Sets `BYPASS_TOOL_CONSENT=true` for the workflow execution. Useful for CI/CD automation where human approval isn't available.
- `--trace` - Auto-generate trace artifact with OTEL spans (writes `<spec-name>-trace.json`)
- `--debug` - Enable debug logging (variable resolution, templates, etc.)
- `--verbose` - Enable detailed logging and error traces
- `--resume SESSION_ID` - Resume workflow from saved session (mutually exclusive with SPEC_FILE)
- `--save-session / --no-save-session` - Enable/disable session saving (default: enabled)
- `--auto-resume` - Auto-resume from most recent failed/paused session if spec matches. Automatically finds and resumes the most recent session with matching spec hash, eliminating need to manually specify session ID.
- `--hitl-response TEXT` - User response when resuming from HITL pause (requires `--resume`)

**Examples**:

```bash
# Basic execution (creates session by default)
strands run workflow.yaml

# Resume from saved session
strands run --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Auto-resume from most recent failed/paused session
strands run workflow.yaml --auto-resume

# Disable session saving
strands run workflow.yaml --no-save-session

# With variable overrides
strands run workflow.yaml --var topic="AI" --var format="markdown"

# Save artifacts to specific directory
strands run workflow.yaml --out ./output

# Enable debugging and tracing
strands run workflow.yaml --debug --verbose --trace

# Skip tool consent prompts for CI/CD
strands run workflow.yaml --bypass-tool-consent
```

**Session Output**:

When session saving is enabled (default), the CLI displays the session ID in the output:

```
Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
Running workflow: my-workflow
Step 1/3: researcher - COMPLETE
Step 2/3: analyst - COMPLETE
Step 3/3: writer - COMPLETE
✓ Workflow completed successfully

Artifacts written:
  • ./output/result.md
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

### sessions

Manage workflow sessions for crash recovery and resume functionality.

```bash
strands sessions COMMAND [OPTIONS]
```

**Subcommands**:

- `list` - List all saved sessions
- `show SESSION_ID` - Show detailed session information
- `delete SESSION_ID` - Delete a saved session

---

#### sessions list

List all saved workflow sessions.

```bash
strands sessions list [OPTIONS]
```

**Options**:

- `--status [running|paused|completed|failed]` - Filter sessions by status
- `--verbose` - Show extended session information

**Examples**:

```bash
# List all sessions
strands sessions list

# Show only running sessions
strands sessions list --status running

# Show only completed sessions
strands sessions list --status completed
```

**Output**: Rich table with session ID, workflow name, pattern type, status, and last updated timestamp.

---

#### sessions show

Display detailed information about a specific session.

```bash
strands sessions show SESSION_ID
```

**Arguments**:

- `SESSION_ID` - Session ID to inspect (full UUID)

**Examples**:

```bash
# Show session details
strands sessions show a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Output**: Panel with complete session metadata including:
- Session ID and workflow name
- Pattern type and execution status
- Created/updated timestamps
- Variables and runtime configuration
- Token usage breakdown
- Pattern-specific execution state

---

#### sessions delete

Delete a saved workflow session.

```bash
strands sessions delete [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID` - Session ID to delete (full UUID)

**Options**:

- `--force` - Skip confirmation prompt

**Examples**:

```bash
# Delete session (with confirmation)
strands sessions delete a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Delete without confirmation
strands sessions delete a1b2c3d4-e5f6-7890-abcd-ef1234567890 --force
```

**Exit Codes**:

- `0` - Success (session deleted)
- `2` - Invalid usage (session not found)

---

#### sessions cleanup

Clean up expired workflow sessions to prevent storage bloat.

```bash
strands sessions cleanup [OPTIONS]
```

**Options**:

- `--max-age-days INTEGER` - Delete sessions older than this many days (default: 7)
- `--keep-completed / --no-keep-completed` - Keep completed sessions regardless of age (default: true)
- `--force` - Skip confirmation prompt

**Examples**:

```bash
# Delete failed/paused sessions older than 7 days (keeps completed)
strands sessions cleanup

# Delete all sessions older than 30 days
strands sessions cleanup --max-age-days 30

# Delete everything including completed sessions
strands sessions cleanup --max-age-days 7 --no-keep-completed

# Delete without confirmation
strands sessions cleanup --force
```

**Behavior**:

- By default, keeps completed sessions for audit purposes
- Only removes failed, paused, or running sessions older than the specified age
- Use `--no-keep-completed` to remove all old sessions regardless of status

**Exit Codes**:

- `0` - Success (cleanup completed)
- `2` - Invalid usage

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

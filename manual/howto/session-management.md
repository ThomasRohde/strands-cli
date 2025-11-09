# Session Management

Learn how to manage workflow sessions for crash recovery and long-running workflows.

## Overview

Strands CLI automatically saves workflow execution state (sessions) to enable:

- **Crash Recovery**: Resume workflows after failures without re-executing completed steps
- **Cost Optimization**: Avoid re-running expensive LLM calls
- **Long-Running Workflows**: Pause and resume multi-hour workflows across CLI sessions
- **Debugging**: Inspect workflow state between steps

Sessions are enabled by default and stored in `~/.strands/sessions/`.

---

## Basic Session Usage

### Run with Session Saving (Default)

```bash
# Sessions are automatically saved
uv run strands run workflow.yaml

# Output includes session ID:
# Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
# Running workflow: my-workflow
# ...
```

### Resume from Session

```bash
# Resume from checkpoint after crash or manual interruption
uv run strands run --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Output shows skip behavior:
# Resuming session: a1b2c3d4...
# Skipping completed step 0: researcher
# Skipping completed step 1: analyst
# Executing step 2: writer
# ...
```

### Disable Session Saving

```bash
# Run without creating a session
uv run strands run workflow.yaml --no-save-session
```

---

## Session Management Commands

### List Sessions

```bash
# List all sessions
uv run strands sessions list

# Output (table format):
# ┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┓
# ┃ Session ID     ┃ Workflow       ┃ Pattern ┃ Status    ┃ Updated    ┃
# ┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━┩
# │ a1b2c3d4...    │ research-chain │ chain   │ running   │ 2025-11-09 │
# │ e5f6g7h8...    │ analysis-dag   │ workflow│ completed │ 2025-11-08 │
# └────────────────┴────────────────┴─────────┴───────────┴────────────┘
```

### Filter Sessions by Status

```bash
# Show only running sessions
uv run strands sessions list --status running

# Show only completed sessions
uv run strands sessions list --status completed

# Show failed sessions
uv run strands sessions list --status failed

# Valid statuses: running, paused, completed, failed
```

### Show Session Details

```bash
# Display detailed session information
uv run strands sessions show a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Output (panel format):
# ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Session a1b2c3d4...                                    ┃
# ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
# │ Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890       │
# │ Workflow: research-chain                               │
# │ Pattern: chain                                         │
# │ Status: running                                        │
# │ Created: 2025-11-09T10:00:00Z                          │
# │ Updated: 2025-11-09T10:15:00Z                          │
# │                                                        │
# │ Variables:                                             │
# │ {                                                      │
# │   "topic": "AI agents",                                │
# │   "format": "markdown"                                 │
# │ }                                                      │
# │                                                        │
# │ Token Usage:                                           │
# │   Total: 5000                                          │
# │   Input: 3000                                          │
# │   Output: 2000                                         │
# │                                                        │
# │ Pattern State:                                         │
# │ {                                                      │
# │   "current_step": 2,                                   │
# │   "step_history": [...]                                │
# │ }                                                      │
# └────────────────────────────────────────────────────────┘
```

### Delete Sessions

```bash
# Delete a session (with confirmation prompt)
uv run strands sessions delete a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Prompt:
# Delete session a1b2c3d4...? [y/N]:

# Skip confirmation with --force
uv run strands sessions delete a1b2c3d4-e5f6-7890-abcd-ef1234567890 --force
```

---

## How Session Resume Works

### Checkpointing

After each step/task/branch completes, the CLI saves:

1. **Execution State**: Current position, completed work, pending work
2. **Step/Task Outputs**: Full responses from completed steps
3. **Token Usage**: Cumulative token counts by agent
4. **Agent Conversations**: Full message history via Strands SDK
5. **Spec Snapshot**: Original workflow spec for validation

### Resume Behavior

When you resume a session:

1. **Load Session State**: CLI loads saved execution state
2. **Validate Spec**: Warns if workflow spec has changed (but allows execution)
3. **Skip Completed Work**: Jumps to first incomplete step/task/branch
4. **Restore Agent Context**: Agents remember previous conversation turns
5. **Continue Execution**: Executes remaining work with full context

### Example: 3-Step Chain Resume

**Initial Run:**
```bash
uv run strands run chain-3-step.yaml --var topic="AI"

# Output:
# Session ID: abc123...
# Step 1/3: researcher - COMPLETE (2000 tokens)
# Step 2/3: analyst - COMPLETE (3000 tokens)
# [Crash or Ctrl+C]
```

**Resume:**
```bash
uv run strands run --resume abc123

# Output:
# Resuming session: abc123...
# Skipping completed step 0: researcher
# Skipping completed step 1: analyst
# Step 3/3: writer - EXECUTING
# ✓ Workflow complete
# Total tokens: 8000 (5000 from resumed session + 3000 new)
```

---

## Session Storage

### Directory Structure

```
~/.strands/sessions/
└── session_a1b2c3d4-e5f6-7890-abcd-ef1234567890/
    ├── session.json              # Metadata, variables, token usage
    ├── pattern_state.json        # Execution state (pattern-specific)
    ├── spec_snapshot.yaml        # Original workflow spec
    └── agents/                   # Strands SDK agent sessions
        ├── researcher/
        │   ├── agent.json        # Agent state (key-value store)
        │   └── messages/
        │       ├── message_0.json
        │       └── message_1.json
        └── analyst/
            └── ...
```

### File Descriptions

- **`session.json`**: Core session metadata (ID, name, status, timestamps, variables, runtime config, token usage, artifacts written)
- **`pattern_state.json`**: Pattern-specific execution state:
  - Chain: `current_step`, `step_history`
  - Workflow: `completed_tasks`, `task_outputs`
  - Parallel: `completed_branches`, `branch_outputs`
  - (Other patterns in Phase 3)
- **`spec_snapshot.yaml`**: Original workflow spec for hash validation
- **`agents/<agent_id>/`**: Strands SDK agent session directory with conversation history

---

## Supported Patterns

### Phase 2 (Current)

- ✅ **Chain**: Resume from any step
  - Skips completed steps
  - Restores step outputs in template context: `{{ steps[n].response }}`
  - Preserves agent conversation history

### Phase 3 (Planned)

- 🔜 **Workflow**: Multi-task DAG resume
  - Tracks completed vs pending tasks
  - Restores task outputs: `{{ tasks.<id>.response }}`
  - Resolves dependencies on resume

- 🔜 **Parallel**: Branch completion tracking
  - Skips completed branches
  - Re-executes failed branches
  - Restores reduce step state

- 🔜 **Routing**: Router decision preservation
  - Caches router agent choice
  - Skips router execution on resume
  - Continues with selected agent

- 🔜 **Evaluator-Optimizer**: Iteration state restoration
  - Preserves iteration history
  - Continues from last iteration
  - Maintains quality gate state

- 🔜 **Orchestrator-Workers**: Round state tracking
  - Tracks completed rounds
  - Restores worker outputs
  - Preserves orchestrator decisions

- 🔜 **Graph**: Node history and cycle detection
  - Restores node transition history
  - Preserves iteration counts
  - Continues from current node

---

## Spec Change Detection

### Hash Validation

The CLI computes a SHA256 hash of your workflow spec when creating a session. On resume, it re-hashes the spec and compares:

```bash
# If spec changed:
# ⚠ Warning: Spec file has changed since session creation
# Original: abc123de...
# Current:  def456gh...
# Continuing with execution...
```

### Behavior

- **No Hash Match**: Warning logged, but execution **continues** (allows spec fixes)
- **Recommendation**: Only resume with unchanged specs for consistent behavior
- **Use Case**: Helpful for fixing typos in prompts or adding missing outputs

---

## Advanced Use Cases

### Manual Session Cleanup

```bash
# List old sessions
uv run strands sessions list

# Delete completed sessions older than 7 days
for session_id in $(strands sessions list --status completed | tail -n +3 | awk '{print $1}'); do
  uv run strands sessions delete $session_id --force
done
```

### Session Inspection for Debugging

```bash
# Show detailed session state
uv run strands sessions show <session-id>

# Manually inspect files
cat ~/.strands/sessions/session_<uuid>/pattern_state.json | jq .

# View agent conversation
cat ~/.strands/sessions/session_<uuid>/agents/researcher/messages/message_0.json | jq .
```

### Resume with Variable Overrides

**Not supported in Phase 2**: Resume uses original session variables. Variable overrides are ignored.

**Workaround**: Modify `session.json` manually before resuming (advanced users only).

---

## Troubleshooting

### Session Not Found

```bash
uv run strands run --resume invalid-id

# Error: Session not found: invalid-id
# Exit code: 2 (EX_USAGE)
```

**Solution**: List sessions with `strands sessions list` to find valid IDs.

### Session Already Completed

```bash
uv run strands run --resume <completed-session-id>

# Error: Session already completed: <session-id>
# Exit code: 2 (EX_USAGE)
```

**Solution**: Completed sessions cannot be resumed. Start a new execution instead.

### Spec Hash Mismatch

```bash
# Warning: Spec file has changed since session creation
```

**Solution**: If intentional (e.g., fixing typos), ignore warning. If accidental, restore original spec from `spec_snapshot.yaml`.

### Session Corruption

**Symptoms**: JSON parse errors, missing files in session directory

**Solution**: Delete corrupted session and re-run workflow:
```bash
uv run strands sessions delete <session-id> --force
uv run strands run workflow.yaml
```

---

## Best Practices

1. **Monitor Session IDs**: Save session IDs from CLI output for later resumption
2. **Clean Up Regularly**: Delete old completed sessions to save disk space
3. **Use Stable Specs**: Avoid modifying specs mid-execution for consistent behavior
4. **Backup Critical Sessions**: Copy session directories before manual edits
5. **Leverage --force**: Use `--force` flag for automated cleanup scripts

---

## Limitations (Phase 2)

- **Single Pattern Support**: Only chain pattern supports resume (Phase 3 adds others)
- **File Storage Only**: Sessions stored locally in `~/.strands/sessions/` (S3 in Phase 4)
- **No Concurrent Safety**: File locking not implemented yet (Phase 4)
- **Manual Cleanup**: No automatic session expiration (Phase 4)
- **No Auto-Resume**: Must manually specify `--resume` flag (Phase 4 adds `--auto-resume`)

---

## Next Steps

- **Phase 3**: Multi-pattern resume for all 7 workflow patterns
- **Phase 4**: S3 storage, file locking, auto-cleanup, auto-resume on failure
- **Phase 12**: Human-in-the-loop with approval gates using pause/resume

---

## Related Documentation

- [DURABLE.md](../../DURABLE.md) - Complete session architecture and roadmap
- [Session API Reference](../reference/session-api.md) - Pydantic models and repository API
- [Workflow Manual](../reference/workflow-manual.md) - Workflow spec reference
- [Exit Codes](../reference/exit-codes.md) - CLI exit code meanings

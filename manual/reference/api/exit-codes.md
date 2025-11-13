# Exit Codes

Standard exit codes for the Strands CLI.

## Exit Code Constants

::: strands_cli.exit_codes
    options:
      show_root_heading: true
      heading_level: 3

## Additional Exit Code Details

### EX_SESSION (17) - Session Errors

**Common Conditions:**
- Session ID not found during resume attempt
- Session data corrupted or invalid JSON
- Attempting to resume an already-completed session
- **Session spec hash mismatch** (spec file changed since session creation)
- **HITL resume attempted without `--hitl-response` flag**

**Resolution Steps:**
1. Verify session ID exists: `strands sessions list`
2. Inspect session state: `strands sessions show <session-id>`
3. **For HITL sessions:** Provide `--hitl-response` flag when resuming:
   ```bash
   strands run --resume <session-id> --hitl-response "approved"
   ```
4. **For spec changes:** Review warning message about spec hash mismatch and decide whether to proceed
5. Delete corrupted sessions: `strands sessions delete <session-id>`

### EX_BUDGET_EXCEEDED (20) - Budget Limits

**Triggers:**
- Cumulative **token usage** exceeds `budgets.max_tokens`
- Note: Currently only enforces **token budget**, not time budget (`max_duration_s`)

**Resolution:**
- Increase `budgets.max_tokens` in workflow spec
- Enable `context_policy.compaction` to reduce context size
- Optimize prompts to use fewer tokens
- Split workflow into smaller parts

See also: [Exit Codes Reference](../exit-codes.md)

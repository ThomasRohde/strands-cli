# Exit Codes Reference

Strands CLI follows Unix conventions for exit codes, providing consistent error reporting across different failure modes.

## Overview

Exit codes allow shell scripts and CI/CD pipelines to distinguish between validation errors, runtime failures, and unsupported features programmatically.

**Best Practice**: Always use named constants instead of raw integers:

```python
from strands_cli.exit_codes import EX_SCHEMA, EX_OK
sys.exit(EX_SCHEMA)  # GOOD
sys.exit(3)  # BAD - unclear meaning
```

## Exit Code Categories

| Category | Range | Description |
|----------|-------|-------------|
| Success | 0 | Successful execution |
| User/Input Errors | 2-3 | Invalid CLI usage or spec validation failures |
| Runtime Errors | 10-19 | Provider failures, I/O errors, budget exceeded |
| System Errors | 70 | Unexpected exceptions |

---

## Success Codes

### `EX_OK` (0)

**Meaning**: Successful execution

**When returned**:
- Workflow completed successfully
- All validation checks passed
- Artifacts written without errors

**Example**:
```bash
strands run workflow.yaml
echo $?  # Output: 0
```

---

## User/Input Error Codes

### `EX_USAGE` (2)

**Meaning**: Command-line usage error

**When returned**:
- Invalid command-line flags
- Missing required arguments
- File not found
- Invalid output format specified

**Examples**:
```bash
# Missing spec file
strands run
# Exit code: 2

# Invalid format option
strands run workflow.yaml --format invalid
# Exit code: 2
```

**Resolution**:
- Check command syntax with `strands --help`
- Verify file paths exist
- Review available options for each command

---

### `EX_SCHEMA` (3)

**Meaning**: JSON Schema validation error

**When returned**:
- Workflow spec doesn't conform to `strands-workflow.schema.json`
- Required fields are missing
- Invalid data types
- Additional properties not allowed

**Validation details**:
- Uses JSON Schema Draft 2020-12
- Reports precise error locations using JSONPointer paths
- Provides detailed error messages

**Example**:
```bash
strands validate invalid-workflow.yaml
# Output:
# Schema validation error at /runtime/provider: 'invalid_provider' is not valid under any of the given schemas
# Exit code: 3
```

**Resolution**:
1. Run `strands validate workflow.yaml` to see specific errors
2. Check JSONPointer paths to locate issues
3. Review [Schema Reference](schema.md) for valid values
4. Examine example workflows in `examples/`

---

## Runtime Error Codes

### `EX_RUNTIME` (10)

**Meaning**: Provider/model/tool runtime failure

**When returned**:
- AWS Bedrock API errors (throttling, invalid credentials)
- Ollama connection failures
- OpenAI API errors
- Tool execution crashes
- Model invocation failures

**Examples**:
```bash
# Ollama not running
strands run workflow-ollama.yaml
# Exit code: 10

# Invalid AWS credentials
strands run workflow-bedrock.yaml
# Exit code: 10
```

**Resolution**:
- Run `strands doctor` to check system health
- Verify provider credentials (AWS, OpenAI API key)
- Check Ollama is running (`ollama serve`)
- Review error messages with `--debug --verbose`
- Check provider-specific logs

---

### `EX_IO` (12)

**Meaning**: Artifact write or I/O error

**When returned**:
- Cannot create output directory
- Permission denied when writing artifacts
- Disk full
- Invalid output path

**Examples**:
```bash
# Read-only directory
strands run workflow.yaml --out /read-only/
# Exit code: 12

# Invalid path
strands run workflow.yaml --out /invalid/../path
# Exit code: 12
```

**Resolution**:
- Check directory permissions
- Verify disk space availability
- Use valid output paths
- Use `--force` to overwrite existing files (if intended)

---

### `EX_UNSUPPORTED` (18)

**Meaning**: Feature present in spec but not supported

**When returned**:
- Workflow uses features not yet implemented
- Capability check detects unsupported patterns
- Provider doesn't support requested features

**Special behavior**:
When this code is returned, a detailed Markdown remediation report is automatically written to the artifacts directory with:
- JSONPointer locations of unsupported features
- Reason each feature is unsupported
- Specific remediation steps
- Minimal working example

**Example**:
```bash
strands run workflow-with-unsupported.yaml
# Output:
# Unsupported features detected. Remediation report: ./remediation_report_YYYYMMDD_HHMMSS.md
# Exit code: 18
```

**Resolution**:
1. Read the generated remediation report
2. Follow suggested remediation steps
3. Use `strands list-supported` to see available features
4. Modify workflow to use supported alternatives
5. Check for CLI updates

---

### `EX_BUDGET_EXCEEDED` (19)

**Meaning**: Token budget exhausted during execution

**When returned**:
- Cumulative token usage reaches 100% of `budgets.max_tokens`
- Budget enforcement is enabled
- Token consumption exceeds configured limits

**Behavior**:
- Warning logged at threshold (default 80%)
- Automatic context compaction triggered (if enabled)
- Workflow aborted to prevent cost overruns

**Example**:
```yaml
# workflow.yaml
budgets:
  max_tokens: 10000
  threshold: 0.8
```

```bash
strands run workflow.yaml
# Output:
# Warning: Token budget at 82% (8200/10000)
# Error: Token budget exceeded (10100/10000) - aborting workflow
# Exit code: 19
```

**Resolution**:
- Increase `budgets.max_tokens` if legitimate
- Enable `context_policy.compaction` to reduce context
- Optimize prompts to use fewer tokens
- Split complex workflows into smaller ones
- Review token usage with `--trace`

---

## System Error Codes

### `EX_UNKNOWN` (70)

**Meaning**: Unexpected exception not handled by specific error codes

**When returned**:
- Unhandled Python exceptions
- Internal CLI bugs
- Unexpected edge cases

**Example**:
```bash
strands run workflow.yaml --debug --verbose
# Output:
# Unexpected error: [detailed traceback]
# Exit code: 70
```

**Resolution**:
1. Run with `--verbose` to see full traceback
2. Check for known issues on GitHub
3. Report the bug with traceback and workflow spec
4. Try updating to latest CLI version

---

## Shell Script Integration

### Basic Error Handling

```bash
#!/bin/bash
set -e  # Exit on any error

strands run workflow.yaml
if [ $? -eq 0 ]; then
    echo "Success!"
else
    echo "Workflow failed with code: $?"
fi
```

### Advanced Error Handling

```bash
#!/bin/bash

strands run workflow.yaml
exit_code=$?

case $exit_code in
    0)
        echo "Workflow completed successfully"
        ;;
    2)
        echo "Usage error - check command syntax"
        exit 1
        ;;
    3)
        echo "Schema validation failed - check workflow spec"
        exit 1
        ;;
    10)
        echo "Runtime error - check provider status"
        strands doctor
        exit 1
        ;;
    12)
        echo "I/O error - check permissions and disk space"
        exit 1
        ;;
    18)
        echo "Unsupported features - see remediation report"
        exit 1
        ;;
    19)
        echo "Token budget exceeded - increase limits or optimize"
        exit 1
        ;;
    70)
        echo "Unexpected error - report as bug"
        exit 1
        ;;
    *)
        echo "Unknown exit code: $exit_code"
        exit 1
        ;;
esac
```

### CI/CD Integration

```yaml
# GitHub Actions example
- name: Validate workflow
  run: |
    strands validate workflow.yaml
    if [ $? -ne 0 ]; then
      echo "Validation failed"
      exit 1
    fi

- name: Run workflow
  run: |
    strands run workflow.yaml --out ./artifacts
    exit_code=$?
    if [ $exit_code -eq 18 ]; then
      echo "::warning::Unsupported features detected"
      cat ./remediation_report_*.md
      exit 1
    elif [ $exit_code -ne 0 ]; then
      echo "::error::Workflow failed with exit code $exit_code"
      exit 1
    fi
```

---

## Programmatic Access

### Python

```python
from strands_cli.exit_codes import (
    EX_OK,
    EX_USAGE,
    EX_SCHEMA,
    EX_RUNTIME,
    EX_IO,
    EX_UNSUPPORTED,
    EX_BUDGET_EXCEEDED,
    EX_UNKNOWN,
)

import subprocess

result = subprocess.run(
    ["strands", "run", "workflow.yaml"],
    capture_output=True,
    text=True
)

if result.returncode == EX_OK:
    print("Success!")
elif result.returncode == EX_SCHEMA:
    print("Schema validation failed")
elif result.returncode == EX_UNSUPPORTED:
    print("Unsupported features detected")
```

---

## See Also

- [CLI Reference](cli.md) - Command-line interface
- [Schema Reference](schema.md) - Workflow specification
- [Troubleshooting Guide](../howto/validate-workflows.md) - Common issues

---
title: Validating Workflows
description: Validate workflow specifications and fix schema errors
keywords: validate, validation, schema, json schema, errors, debugging, troubleshooting
---

# How to Validate Workflows

This guide shows you how to validate your Strands workflow specifications before execution.

## Basic Validation

Use the `validate` command to check your workflow against the JSON Schema:

```bash
strands validate workflow.yaml
```

If validation succeeds, you'll see:

```
✓ Workflow validation successful
```

## Understanding Validation Errors

When validation fails, Strands provides detailed error messages with JSONPointer paths to help you locate the issue.

### Example: Missing Required Field

```bash
strands validate workflow.yaml
```

Error output:

```
✗ Schema validation failed:
  /runtime/provider: 'provider' is a required property
```

**Fix**: Add the missing `provider` field to your runtime configuration:

```yaml
runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
```

### Example: Invalid Pattern Type

Error output:

```
✗ Schema validation failed:
  /pattern/type: 'invalid_pattern' is not one of ['chain', 'workflow', 'routing', 'parallel', 'evaluator_optimizer', 'orchestrator_workers', 'graph']
```

**Fix**: Use a valid pattern type:

```yaml
pattern:
  type: chain
```

### Example: Invalid Property Type

Error output:

```
✗ Schema validation failed:
  /runtime/timeout: 'not-a-number' is not of type 'number'
```

**Fix**: Provide a numeric value:

```yaml
runtime:
  timeout: 300
```

## Common Validation Issues

### Missing Pattern Configuration

Each pattern requires specific configuration. For example, the chain pattern requires a `steps` array:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent_id: step1
        prompt: "First step"
```

### Invalid Agent References

When using routing or workflow patterns, ensure all referenced agent IDs exist:

```yaml
agents:
  - id: analyzer
    system: "You analyze input"

pattern:
  type: routing
  config:
    routes:
      - condition: "input.type == 'analysis'"
        agent_id: analyzer  # Must match an agent ID above
```

### Malformed YAML Syntax

If your YAML is malformed, you'll see a parsing error:

```
✗ Failed to load workflow: YAML parsing error at line 15, column 3
```

**Fix**: Check for:
- Proper indentation (use spaces, not tabs)
- Missing colons after keys
- Unmatched quotes
- Invalid escape sequences

## Validation Best Practices

### 1. Validate Early and Often

Validate your workflow during development:

```bash
# Validate after each change
strands validate workflow.yaml
```

### 2. Use the Plan Command

The `plan` command performs validation and shows the execution plan:

```bash
strands plan workflow.yaml
```

This helps you:
- Verify validation passes
- Understand execution order
- Check variable substitution
- Preview the workflow structure

### 3. Check for Unsupported Features

Some workflows may validate but use unsupported features. Use the capability checker:

```bash
strands run workflow.yaml
```

If unsupported features are detected, you'll get exit code 18 and a detailed report.

### 4. Validate with Variable Substitution

If your workflow uses template variables, validate with actual values:

```bash
strands validate workflow.yaml --var topic="AI" --var format="markdown"
```

This ensures variable substitution doesn't break the schema.

## Advanced Validation

### Custom Schema Validation

You can validate against the schema directly using standard tools:

```bash
# Using Python jsonschema
python -c "
import json
import yaml
from jsonschema import validate

with open('workflow.yaml') as f:
    workflow = yaml.safe_load(f)

with open('src/strands_cli/schema/strands-workflow.schema.json') as f:
    schema = json.load(f)

validate(workflow, schema)
print('Valid!')
"
```

### Validation in CI/CD

Add validation to your continuous integration pipeline:

```yaml
# .github/workflows/validate.yml
name: Validate Workflows
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install Strands CLI
        run: pip install strands-cli
      - name: Validate all workflows
        run: |
          for workflow in workflows/*.yaml; do
            echo "Validating $workflow"
            strands validate "$workflow"
          done
```

### Pre-commit Hook

Validate workflows before committing:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-strands
        name: Validate Strands Workflows
        entry: strands validate
        language: system
        files: '\.yaml$'
        pass_filenames: true
```

## Troubleshooting

### JSONPointer Paths

Error messages use JSONPointer notation to indicate where errors occur:

- `/runtime/provider` → Root level `runtime` object, `provider` field
- `/agents/0/system` → First agent in `agents` array, `system` field
- `/pattern/config/steps/2/prompt` → Third step in chain, `prompt` field

### Schema Version Compatibility

Ensure your workflow schema version matches the CLI version:

```yaml
schema: https://raw.githubusercontent.com/ThomasRohde/strands-cli/main/src/strands_cli/schema/strands-workflow.schema.json
```

### Getting Help

If validation errors are unclear:

1. Check the [Schema Reference](../reference/schema.md) for field documentation
2. Review [examples](../../examples/) for pattern-specific templates
3. Run with `--debug --verbose` for detailed error information
4. Consult the [troubleshooting guide](../reference/troubleshooting.md)

## Exit Codes

The `validate` command uses these exit codes:

- `0` (EX_OK): Validation successful
- `2` (EX_USAGE): Invalid CLI usage (missing file, bad arguments)
- `3` (EX_SCHEMA): Schema validation failed
- `70` (EX_UNKNOWN): Unexpected error

## See Also

- [Running Workflows](run-workflows.md) - Execute validated workflows
- [Schema Reference](../reference/schema.md) - Complete schema documentation
- [CLI Reference](../reference/cli.md) - All CLI commands and options

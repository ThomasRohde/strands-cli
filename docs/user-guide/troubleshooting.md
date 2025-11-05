# Troubleshooting Guide

Common issues and solutions for strands-cli users.

## Quick Diagnostics

Always start with the health check:

```bash
uv run strands doctor
```

This will identify most common issues with your installation.

---

## Installation Issues

### Python Version Too Old

**Symptom**: Error message stating `Python >= 3.12 required`

**Solution**:
1. Check your Python version: `python --version`
2. Install Python 3.12 or newer from [python.org](https://www.python.org/downloads/)
3. Verify with: `python3.12 --version`
4. Reinstall strands-cli using the new Python version

### Missing Dependencies

**Symptom**: `ModuleNotFoundError` or `ImportError` when running commands

**Solution**:
```bash
# Reinstall all dependencies
uv sync --dev

# Verify installation
uv run strands doctor
```

### Schema File Not Found

**Symptom**: Error about missing `strands-workflow.schema.json`

**Solution**:
```bash
# Ensure you're in the strands-cli directory
cd strands-cli

# Verify schema file exists
ls src/strands_cli/schema/strands-workflow.schema.json

# If missing, re-clone the repository
git pull origin main
```

---

## Ollama Issues

### Ollama Server Not Running

**Symptom**: 
- `strands doctor` shows Ollama not reachable
- Error: `Connection refused` when running workflows

**Solution**:
```bash
# Start Ollama server
ollama serve

# In another terminal, verify it's running
curl http://localhost:11434/api/tags
```

**Alternative**: Ollama may be running on a different port or host. Check your `runtime.host` in the spec:
```yaml
runtime:
  provider: ollama
  host: "http://localhost:11434"  # Verify this matches your setup
```

### Ollama Model Not Found

**Symptom**: Error: `model 'gpt-oss' not found`

**Solution**:
```bash
# List available models
ollama list

# Pull the required model
ollama pull gpt-oss

# Or use a different model in your spec
# Update runtime.model_id to match an installed model
```

### Ollama Not Installed

**Symptom**: `ollama: command not found`

**Solution**:
1. Install Ollama from [https://ollama.ai](https://ollama.ai)
2. Follow platform-specific instructions:
   - **macOS**: `brew install ollama`
   - **Linux**: `curl https://ollama.ai/install.sh | sh`
   - **Windows**: Download installer from ollama.ai
3. Verify: `ollama --version`
4. Start server: `ollama serve`

---

## AWS Bedrock Issues

### AWS Credentials Not Configured

**Symptom**: 
- Error: `NoCredentialsError` or `Unable to locate credentials`
- Workflow fails immediately with authentication error

**Solution**:
```bash
# Option 1: Configure via AWS CLI
aws configure
# Enter your: Access Key ID, Secret Access Key, Region, Output format

# Option 2: Set environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"

# Option 3: Use named profile
export AWS_PROFILE="your-profile-name"

# Verify credentials
aws sts get-caller-identity
```

### Bedrock Model Access Denied

**Symptom**: Error: `AccessDeniedException` or `You don't have access to the model`

**Solution**:
1. Log into AWS Console → Bedrock → Model access
2. Request access to the model you want to use (e.g., Claude 3 Sonnet)
3. Wait for approval (usually instant for most models)
4. Verify in your spec that `runtime.model_id` matches an approved model

### Wrong AWS Region

**Symptom**: Error: `Model not found in region`

**Solution**:
```yaml
# Update your spec or set environment variable
runtime:
  provider: bedrock
  region: "us-east-1"  # Ensure Bedrock is available in this region
```

Or:
```bash
export STRANDS_AWS_REGION="us-east-1"
```

**Note**: Bedrock availability varies by region. Use `us-east-1` or `us-west-2` for broadest model access.

---

## Schema Validation Errors

### Invalid YAML Syntax

**Symptom**: 
- `Failed to parse spec.yaml`
- Error points to specific line number

**Solution**:
1. Validate YAML syntax: [yamllint.com](http://www.yamllint.com/)
2. Common issues:
   - Incorrect indentation (use spaces, not tabs)
   - Missing colons after keys
   - Unquoted special characters
3. Example fix:
```yaml
# ❌ Wrong (tab indentation, no colon)
runtime
	provider bedrock

# ✅ Correct
runtime:
  provider: bedrock
```

### Schema Validation Failed

**Symptom**: Error with JSONPointer like `/runtime/provider: must be one of [bedrock, ollama]`

**Solution**:
1. Run validation: `uv run strands validate spec.yaml --verbose`
2. Error message includes exact location (JSONPointer) and expected format
3. Check schema reference: `src/strands_cli/schema/strands-workflow.schema.json`
4. Common fixes:
   - Enum values must be exact: `bedrock` not `Bedrock`
   - Required fields must be present: `name`, `version`, `agents`, `runtime`, `pattern`
   - Field types must match: `version` is an integer, not string

### Missing Required Fields

**Symptom**: `Missing required property: 'agents'`

**Solution**:
```yaml
# Minimum valid spec requires:
name: my-workflow
version: 1
agents:
  analyst:  # At least one agent required
    prompt: "You are a helpful analyst."
runtime:
  provider: ollama  # or bedrock
  host: "http://localhost:11434"  # for ollama
pattern:
  type: chain  # or workflow
  config:
    steps:  # for chain
      - id: step1
        agent_id: analyst
        input: "Analyze this."
```

---

## Unsupported Features (Exit Code 18)

### Multiple Agents

**Symptom**: `Unsupported feature: multiple agents detected`

**Solution**:
MVP only supports single-agent workflows. Reduce to one agent:
```yaml
# ❌ Not supported in MVP
agents:
  analyst: ...
  critic: ...

# ✅ Supported
agents:
  analyst: ...
```

### Multi-Step Workflows

**Symptom**: `Unsupported: chain with >1 steps`

**Solution**:
```yaml
# ❌ Not supported in MVP
pattern:
  type: chain
  config:
    steps:
      - id: step1
        ...
      - id: step2  # Second step not supported
        ...

# ✅ Supported
pattern:
  type: chain
  config:
    steps:
      - id: step1
        ...
```

### Routing/Parallel Patterns

**Symptom**: `Unsupported pattern type: routing`

**Solution**:
MVP only supports `chain` (1 step) or `workflow` (1 task). Use `chain`:
```yaml
pattern:
  type: chain  # Supported
  # type: routing  # Not supported in MVP
```

**Get Details**:
```bash
uv run strands explain spec.yaml
```

This generates a detailed report of unsupported features with remediation steps.

---

## Runtime Execution Errors

### Template Rendering Failed

**Symptom**: `Failed to render task input: 'topic' is undefined`

**Solution**:
Ensure all template variables are provided:
```bash
# ❌ Missing variable
uv run strands run spec.yaml

# ✅ Provide required variables
uv run strands run spec.yaml --var topic="AI ethics"
```

Or define defaults in spec:
```yaml
inputs:
  values:
    topic: "default topic"  # Fallback if --var not provided
```

### Agent Build Failed

**Symptom**: `Failed to build agent: No such tool`

**Solution**:
Verify tool names match allowlist:
```yaml
agents:
  analyst:
    tools:
      # ✅ Allowed
      - python:strands_tools.http_request
      - python:strands_tools.file_read
      # ❌ Not allowed (security restriction)
      - python:my_custom_tool
```

### Timeout Errors

**Symptom**: Workflow fails after long wait

**Solution**:
Increase timeout in failure policy:
```yaml
runtime:
  failure_policy:
    retries: 3
    wait_max: 120  # Increase from default 60s
```

---

## Artifact Output Issues

### File Already Exists

**Symptom**: `Artifact file exists, use --force to overwrite`

**Solution**:
```bash
# Option 1: Use --force flag
uv run strands run spec.yaml --force

# Option 2: Use different output directory
uv run strands run spec.yaml --out ./output-$(date +%s)

# Option 3: Delete existing artifacts
rm -rf ./artifacts
```

### Permission Denied

**Symptom**: `PermissionError: [Errno 13] Permission denied`

**Solution**:
```bash
# Check directory permissions
ls -la ./artifacts

# Ensure write access
chmod +w ./artifacts

# Or use different output directory
uv run strands run spec.yaml --out ~/my-artifacts
```

---

## Performance Issues

### Slow Validation

**Symptom**: `strands validate` takes >1 second

**Solution**:
This may indicate a very large spec file. Check:
```bash
# Check file size
ls -lh spec.yaml

# Maximum allowed: 10MB
# If larger, split into smaller specs or remove unused content
```

### Slow Execution

**Symptom**: Workflow takes much longer than expected

**Solution**:
1. Check Ollama/Bedrock latency: `time curl http://localhost:11434/api/tags`
2. Review retry configuration (excessive retries slow things down)
3. Use `--verbose` to see where time is spent
4. Consider using faster models (e.g., `gpt-oss` vs larger models)

---

## Getting More Help

### Enable Verbose Mode

```bash
uv run strands run spec.yaml --verbose
```

This shows detailed logs including:
- Workflow lifecycle events
- Provider requests/responses
- Template rendering details
- Timing information

### Check Exit Codes

Exit codes indicate failure type:
- **0**: Success
- **3**: Schema validation error
- **10**: Runtime error (provider, model, tool)
- **12**: I/O error (artifact write)
- **18**: Unsupported features
- **70**: Unknown error

### Run Health Check

```bash
uv run strands doctor
```

### Review Logs

Structured logs are written to stdout in JSON format (when `STRANDS_LOG_FORMAT=json`):
```bash
export STRANDS_LOG_FORMAT=console  # Human-readable
export STRANDS_LOG_LEVEL=DEBUG     # More detail

uv run strands run spec.yaml
```

### Report Issues

If you encounter a bug:
1. Run with `--verbose` and capture output
2. Check [GitHub Issues](https://github.com/ThomasRohde/strands-cli/issues)
3. Create new issue with:
   - strands-cli version: `uv run strands version`
   - Python version: `python --version`
   - OS: Windows/macOS/Linux
   - Minimal reproducible spec
   - Full error output with `--verbose`

---

## Common Error Messages Reference

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Spec file not found` | Wrong path or file doesn't exist | Check path with `ls spec.yaml` |
| `Spec file too large` | File >10MB | Reduce spec size or split into multiple files |
| `Invalid variable format` | Wrong `--var` syntax | Use `--var key=value` (no spaces around `=`) |
| `No such tool` | Tool not in allowlist | Use allowed tools: `strands_tools.http_request`, `strands_tools.file_read` |
| `Provider requires runtime.host` | Missing Ollama host | Add `runtime.host: "http://localhost:11434"` |
| `Provider requires runtime.region` | Missing AWS region | Add `runtime.region: "us-east-1"` or set `STRANDS_AWS_REGION` |
| `Invalid retry config` | wait_min > wait_max | Fix `failure_policy`: ensure `wait_min <= wait_max` |
| `Unsupported pattern type` | Using MVP-unsupported pattern | Change to `chain` or `workflow`, or run `strands explain` |

---

## Additional Resources

- **Schema Reference**: `src/strands_cli/schema/strands-workflow.schema.json`
- **Full Manual**: `docs/strands-workflow-manual.md`
- **MVP Requirements**: `docs/PRD_SingleAgent_MVP.md`
- **Examples**: `examples/` directory
- **GitHub Repository**: https://github.com/ThomasRohde/strands-cli

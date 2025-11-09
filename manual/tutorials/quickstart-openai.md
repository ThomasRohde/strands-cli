---
title: Quickstart with OpenAI
description: Get started with Strands CLI using OpenAI API for GPT-4 and o1 models
keywords: openai, quickstart, tutorial, gpt-4, gpt-4o, o1, api key, chatgpt
---

# Quickstart with OpenAI

This tutorial will guide you through setting up and running your first Strands workflow using OpenAI's API. OpenAI provides access to powerful models like GPT-4o, GPT-4, and o1 with a simple pay-as-you-go pricing model.

## What You'll Learn

- How to set up an OpenAI API key
- How to configure and use OpenAI models
- How to create and run an OpenAI workflow
- Understanding model selection and pricing
- Best practices for API usage

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **OpenAI account** with API access
- **Basic command-line experience**
- **Payment method** added to OpenAI account

## Step 1: Create an OpenAI API Key

### Sign Up for OpenAI

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign in or create an account
3. Add a payment method under **Settings → Billing**

!!! tip "Free Credits"
    New OpenAI accounts may receive free trial credits. Check your billing dashboard.

### Generate API Key

1. Navigate to [API Keys](https://platform.openai.com/api-keys)
2. Click "Create new secret key"
3. Give it a name (e.g., "Strands CLI")
4. Copy the key immediately (you won't see it again!)
5. Store it securely

!!! warning "Keep Your Key Safe"
    Never commit API keys to version control. Use environment variables or secrets managers.

## Step 2: Configure Your API Key

### Option 1: Environment Variable (Recommended)

```bash
# Linux/macOS
export OPENAI_API_KEY=sk-proj-...

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'export OPENAI_API_KEY=sk-proj-...' >> ~/.bashrc

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-proj-..."

# Add to PowerShell profile for persistence
Add-Content $PROFILE "`n`$env:OPENAI_API_KEY = 'sk-proj-...'"
```

### Option 2: .env File (Development)

Create a `.env` file in your project directory:

```bash
OPENAI_API_KEY=sk-proj-...
```

Then load it before running workflows:

```bash
# Linux/macOS
export $(cat .env | xargs)

# Or use a tool like direnv or python-dotenv
```

!!! warning "Don't Commit .env Files"
    Add `.env` to your `.gitignore` file!

### Verify Setup

```bash
# Quick test using curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | head -20
```

## Step 3: Install Strands CLI

Install Strands CLI using pip or uv:

=== "Using uv (recommended)"

    ```bash
    # Install uv if not already installed
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install Strands CLI
    uv pip install strands-cli

    # Verify installation
    uv run strands --version
    ```

=== "Using pip"

    ```bash
    # Install Strands CLI
    pip install strands-cli

    # Verify installation
    strands --version
    ```

## Step 4: Choose a Model

OpenAI offers several models with different capabilities and pricing:

| Model | ID | Use Case | Cost (per 1M tokens) |
|-------|-----|----------|---------------------|
| GPT-4o | `gpt-4o` | Best overall, multimodal | Input: $2.50, Output: $10.00 |
| GPT-4o mini | `gpt-4o-mini` | Fast and affordable | Input: $0.15, Output: $0.60 |
| o1 | `o1` | Advanced reasoning | Input: $15.00, Output: $60.00 |
| o1-mini | `o1-mini` | Fast reasoning | Input: $3.00, Output: $12.00 |
| GPT-4 Turbo | `gpt-4-turbo` | Previous flagship | Input: $10.00, Output: $30.00 |

!!! tip "Start with GPT-4o mini"
    For learning and testing, use `gpt-4o-mini` - it's fast and cost-effective.

## Step 5: Create Your First OpenAI Workflow

Create a new file called `my-openai-workflow.yaml`:

```yaml
version: 0
name: my-openai-workflow
description: My first Strands workflow using OpenAI

runtime:
  provider: openai
  model_id: gpt-4o-mini

inputs:
  values:
    language: "Python"
    task: "read a CSV file and calculate the average of a numeric column"

agents:
  code_assistant:
    prompt: |
      You are an expert software developer who writes clean, well-documented code.
      Provide complete, working examples with helpful comments.
      Format code blocks with proper syntax highlighting.

pattern:
  type: single_agent
  config:
    agent: code_assistant
    input: |
      Write a {{ language }} script to {{ task }}.

      Include:
      - Clear comments explaining each step
      - Error handling for common edge cases
      - Example usage

outputs:
  artifacts:
    - path: ./generated-code.md
      from: "{{ last_response }}"
```

### Understanding OpenAI-Specific Settings

- **`provider: openai`**: Tells Strands to use OpenAI's API
- **`model_id: gpt-4o-mini`**: Specifies which model to use
  - No region required (OpenAI routes automatically)
  - Model ID is simpler than Bedrock (no version suffix)

## Step 6: Validate Your Workflow

```bash
uv run strands validate my-openai-workflow.yaml
```

Expected output:

```
✓ Workflow is valid
```

## Step 7: Run Your Workflow

```bash
uv run strands run my-openai-workflow.yaml
```

Expected output:

```
🚀 Starting workflow: my-openai-workflow
📊 Runtime: openai (gpt-4o-mini)
🤖 Agent: code_assistant
✅ Workflow completed successfully
📝 Artifact written: ./generated-code.md
```

## Step 8: Check the Output

```bash
cat generated-code.md
```

You'll see GPT-4o mini's generated Python code with documentation.

## Step 9: Use Different Models

Try different models by overriding the model_id:

```bash
# Use GPT-4o (more capable, higher cost)
uv run strands run my-openai-workflow.yaml \
  --var model_override=gpt-4o

# Use o1-mini for complex reasoning
uv run strands run my-openai-workflow.yaml \
  --var model_override=o1-mini
```

Or update your workflow to use environment variables:

```yaml
runtime:
  provider: openai
  model_id: ${OPENAI_MODEL_ID:-gpt-4o-mini}  # Default to gpt-4o-mini
```

## Step 10: Customize with Variables

```bash
# Generate JavaScript code instead
uv run strands run my-openai-workflow.yaml \
  --var language="JavaScript" \
  --var task="fetch data from a REST API and parse JSON"

# Generate a different kind of script
uv run strands run my-openai-workflow.yaml \
  --var language="Bash" \
  --var task="backup files older than 30 days to a tar archive"
```

## Troubleshooting

### Authentication Error

**Problem**: `AuthenticationError: Invalid API key`

**Solution**:
1. Verify API key is correct (starts with `sk-proj-`)
2. Check environment variable is set: `echo $OPENAI_API_KEY`
3. Ensure key is active in OpenAI dashboard

```bash
# Test API key manually
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Rate Limit Exceeded

**Problem**: `RateLimitError: Rate limit exceeded`

**Solution**:
1. Wait a few seconds and retry (Strands has automatic retry)
2. Upgrade to a paid tier for higher limits
3. Implement longer delays between requests
4. Use token budgets to limit usage

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    token_budget:
      max_input_tokens: 10000
      max_output_tokens: 5000
```

### Insufficient Quota

**Problem**: `InsufficientQuotaError: You have exceeded your quota`

**Solution**:
1. Add payment method to your OpenAI account
2. Check usage dashboard for current spending
3. Set up billing alerts
4. Request quota increase if needed

### Model Not Found

**Problem**: `NotFoundError: Model not found`

**Solution**:
1. Verify model ID spelling (e.g., `gpt-4o-mini` not `gpt-4-mini`)
2. Check model availability for your account tier
3. Use a different model

```bash
# List available models
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | grep '"id":'
```

## Cost Management

### Understanding Pricing

OpenAI charges per token, with different rates for input and output:

```
Cost = (Input tokens / 1M × Input price) + (Output tokens / 1M × Output price)
```

**Example**: Using `gpt-4o-mini` with 1,000 input tokens and 500 output tokens:
```
Cost = (1000/1M × $0.15) + (500/1M × $0.60) = $0.00045
```

### Monitor Usage

1. **OpenAI Dashboard**: Check [platform.openai.com/usage](https://platform.openai.com/usage)
2. **Set Budget Alerts**: Configure email alerts for spending thresholds
3. **Use Token Budgets**: Limit workflow token consumption

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  budgets:
    token_budget:
      max_input_tokens: 50000   # Hard limit
      max_output_tokens: 10000
```

### Cost Optimization Tips

1. **Use gpt-4o-mini for simple tasks**: 16x cheaper than gpt-4o
2. **Minimize prompt size**: Remove unnecessary context
3. **Set max_tokens**: Control output length
4. **Cache agents**: Strands reuses agents to reduce overhead
5. **Batch workflows**: Combine multiple tasks into one workflow

## Model Selection Guide

### When to Use Each Model

| Scenario | Recommended Model | Reason |
|----------|------------------|---------|
| Simple Q&A, content generation | `gpt-4o-mini` | Cost-effective, fast |
| Complex analysis, multimodal | `gpt-4o` | Better reasoning, image support |
| Advanced math, coding, research | `o1` | Superior reasoning capabilities |
| Budget-constrained reasoning | `o1-mini` | Cheaper than o1, better than gpt-4o |
| Legacy workflows | `gpt-4-turbo` | Compatibility with older code |

### Model Capabilities

| Feature | gpt-4o-mini | gpt-4o | o1-mini | o1 |
|---------|-------------|--------|---------|-----|
| Text generation | ✅ | ✅ | ✅ | ✅ |
| Code generation | ✅ | ✅ | ✅ | ✅ |
| Image analysis | ✅ | ✅ | ❌ | ❌ |
| Function calling | ✅ | ✅ | ❌ | ❌ |
| Reasoning | Good | Great | Excellent | Superior |
| Speed | Fast | Fast | Medium | Slow |
| Cost | Lowest | Medium | Medium | Highest |

## Best Practices

### 1. Secure API Key Management

```bash
# Good: Environment variable
export OPENAI_API_KEY=sk-proj-...

# Bad: Hardcoded in YAML
runtime:
  provider: openai
  api_key: sk-proj-...  # Don't do this!
```

### 2. Implement Error Handling

Strands automatically retries failed API calls, but you can enhance this:

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  max_retries: 3       # Retry failed calls
  timeout_seconds: 60  # Per-request timeout
```

### 3. Use Telemetry for Debugging

```bash
# Enable debug mode
uv run strands run workflow.yaml --debug --verbose

# Export execution traces
uv run strands run workflow.yaml --trace
```

### 4. Version Control Workflows

```bash
# Good: Track workflow files
git add my-openai-workflow.yaml

# Bad: Track API keys
git add .env  # Never commit this!
```

### 5. Test Before Production

```bash
# Validate first
strands validate workflow.yaml

# Run with minimal input for testing
strands run workflow.yaml --var task="simple test"
```

## Next Steps

Now that you have OpenAI configured, explore advanced features:

1. **Multi-step workflows**: Learn the [chain pattern tutorial](first-multi-step.md)
2. **Add tools**: Use [HTTP executors](../howto/tools.md) for API integration
3. **Enable observability**: Set up [OpenTelemetry](../howto/telemetry.md)
4. **Browse examples**: Check `examples/` for OpenAI workflows:
   - `examples/single-agent-workflow-openai.yaml` - Basic single agent
   - `examples/chain-3-step-research-openai.yaml` - Sequential workflow
   - `examples/github-api-example-openai.yaml` - API integration

## Key Concepts Recap

| Concept | Description |
|---------|-------------|
| **API Key** | Secret key for OpenAI authentication (starts with `sk-`) |
| **Model ID** | Simple model identifier (e.g., `gpt-4o-mini`) |
| **Token** | Unit of text used for pricing (≈4 chars) |
| **Rate Limit** | Maximum requests per minute based on tier |
| **Quota** | Maximum monthly spending limit |

## Common Commands Reference

```bash
# Validate workflow
strands validate workflow.yaml

# Run workflow
strands run workflow.yaml

# Run with variable overrides
strands run workflow.yaml --var key=value

# Debug mode
strands run workflow.yaml --debug --verbose

# Check Strands version
strands --version

# Test OpenAI API access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | None |
| `OPENAI_BASE_URL` | Custom API endpoint | `https://api.openai.com/v1` |
| `OPENAI_ORG_ID` | Organization ID | None |
| `OPENAI_TIMEOUT` | Request timeout (seconds) | 60 |

## Further Reading

- [OpenAI Documentation](https://platform.openai.com/docs/) - Official API docs
- [OpenAI Models Guide](https://platform.openai.com/docs/models) - Model comparison
- [OpenAI Pricing](https://openai.com/api/pricing/) - Detailed pricing information
- [Workflow Schema Reference](../reference/schema.md) - Complete YAML spec
- [Token Budgets Guide](../howto/budgets.md) - Cost control strategies

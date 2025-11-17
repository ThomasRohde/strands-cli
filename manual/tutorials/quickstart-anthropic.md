---
title: Quickstart with Anthropic
description: Get started with Strands CLI using Anthropic's Claude API
keywords: anthropic, claude, quickstart, tutorial, api key, claude-sonnet
---

# Quickstart with Anthropic

This tutorial will guide you through setting up and running your first Strands workflow using Anthropic's Claude API. Claude provides state-of-the-art language models with strong reasoning capabilities.

## What You'll Learn

- How to install the Anthropic provider
- How to set up an Anthropic API key
- How to configure and use Claude models
- How to create and run an Anthropic workflow
- Understanding model selection and pricing

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **Anthropic account** with API access
- **Basic command-line experience**
- **Strands CLI** installed

## Step 1: Install Anthropic Provider

The Anthropic provider is an optional extra that must be installed separately:

```bash
# Install the Anthropic provider extra
uv pip install -e ".[anthropic]"

# Or install all optional providers
uv pip install -e ".[all-providers]"
```

## Step 2: Create an Anthropic API Key

### Sign Up for Anthropic

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign in or create an account
3. Add a payment method or use your free credits

!!! tip "Free Credits"
    New Anthropic accounts typically receive $5 in free credits to get started.

### Generate API Key

1. Navigate to [API Keys](https://console.anthropic.com/settings/keys)
2. Click "Create Key"
3. Give it a name (e.g., "Strands CLI")
4. Copy the key immediately (you won't see it again!)
5. Store it securely

!!! warning "Keep Your Key Safe"
    Never commit API keys to version control. Use environment variables or secrets managers.

## Step 3: Configure Your API Key

### Option 1: Environment Variable (Recommended)

```bash
# Linux/macOS
export ANTHROPIC_API_KEY=sk-ant-...

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Add to PowerShell profile for persistence
Add-Content $PROFILE "`n`$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
```

### Option 2: .env File (Development)

Create a `.env` file in your project directory:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

!!! warning "Don't Commit .env Files"
    Add `.env` to your `.gitignore` file!

### Verify Setup

```bash
# Quick test using curl
curl https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 256,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Step 4: Choose a Model

Anthropic offers several Claude models with different capabilities:

| Model | ID | Use Case | Context | Cost (per 1M tokens) |
|-------|-----|----------|---------|---------------------|
| Claude Sonnet 4 | `claude-sonnet-4-20250514` | Best balance | 200K | Input: $3.00, Output: $15.00 |
| Claude Opus 4 | `claude-opus-4-20250514` | Most capable | 200K | Input: $15.00, Output: $75.00 |
| Claude 3.5 Sonnet | `claude-3-5-sonnet-20241022` | Previous gen | 200K | Input: $3.00, Output: $15.00 |

!!! tip "Start with Claude Sonnet 4"
    For most use cases, `claude-sonnet-4-20250514` offers the best balance of capability and cost.

## Step 5: Create Your First Anthropic Workflow

Create a new file called `my-anthropic-workflow.yaml`:

```yaml
version: 0
name: my-anthropic-workflow
description: My first Strands workflow using Anthropic Claude

runtime:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  temperature: 0.7
  max_tokens: 2048

inputs:
  values:
    topic: "artificial intelligence"

agents:
  analyst:
    prompt: |
      You are an expert analyst who provides clear, concise, and well-structured analysis.
      Focus on key insights and practical implications.

pattern:
  type: single_agent
  config:
    agent: analyst
    input: |
      Provide a brief analysis of {{ topic }}, including:
      1. A concise definition (2-3 sentences)
      2. Key considerations or challenges (3-5 bullet points)
      3. Potential implications or applications (2-3 bullet points)

outputs:
  artifacts:
    - path: ./analysis.md
      from: "{{ last_response }}"
```

### Understanding Anthropic-Specific Settings

- **`provider: anthropic`**: Tells Strands to use Anthropic's API
- **`model_id: claude-sonnet-4-20250514`**: Specifies Claude Sonnet 4
- **`temperature: 0.7`**: Controls randomness (0.0-1.0)
- **`max_tokens: 2048`**: Maximum output length (required for Anthropic)

## Step 6: Validate Your Workflow

```bash
uv run strands validate my-anthropic-workflow.yaml
```

Expected output:

```
[OK] No unsupported features detected.
This workflow is compatible with the current MVP.
```

## Step 7: Run Your Workflow

```bash
uv run strands run my-anthropic-workflow.yaml
```

Expected output:

```
Running workflow: my-anthropic-workflow
[OK] Workflow completed successfully
Duration: 3.45s

Artifacts written:
  ./analysis.md
```

## Step 8: Check the Output

```bash
cat analysis.md
```

You'll see Claude's comprehensive analysis of artificial intelligence.

## Step 9: Customize with Variables

```bash
# Analyze a different topic
uv run strands run my-anthropic-workflow.yaml \
  --var topic="quantum computing" --force

# Use a more capable model
uv run strands run my-anthropic-workflow.yaml \
  --var topic="climate change" --force
```

Update your workflow to use Claude Opus 4 for more complex tasks:

```yaml
runtime:
  provider: anthropic
  model_id: claude-opus-4-20250514  # More capable model
  temperature: 0.7
  max_tokens: 4096
```

## Troubleshooting

### Authentication Error

**Problem**: `Error code: 401 - Authentication error`

**Solution**:
1. Verify API key is correct (starts with `sk-ant-`)
2. Check environment variable: `echo $ANTHROPIC_API_KEY`
3. Ensure key is active in Anthropic Console

### Credit Balance Error

**Problem**: `Error code: 400 - Credit balance is too low`

**Solution**:
1. Add credits in [Anthropic Console](https://console.anthropic.com/settings/billing)
2. Add a payment method for auto-recharge
3. Check current balance and usage

### Rate Limit Exceeded

**Problem**: `Error code: 429 - Rate limit exceeded`

**Solution**:
1. Wait briefly and retry (Strands has automatic retry)
2. Upgrade to a higher tier for increased limits
3. Implement rate limiting in your workflows

## Cost Management

### Understanding Pricing

Anthropic charges per token with different rates for input and output:

**Example**: Using Claude Sonnet 4 with 1,000 input tokens and 500 output tokens:
```
Cost = (1000/1M × $3.00) + (500/1M × $15.00) = $0.0105
```

### Monitor Usage

1. **Anthropic Console**: Check [console.anthropic.com](https://console.anthropic.com/settings/usage)
2. **Set Budget Limits**: Configure spending alerts
3. **Use Token Budgets**: Limit workflow consumption

```yaml
runtime:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  budgets:
    token_budget:
      max_input_tokens: 50000
      max_output_tokens: 10000
```

## Best Practices

### 1. Secure API Key Management

```bash
# Good: Environment variable
export ANTHROPIC_API_KEY=sk-ant-...

# Bad: Hardcoded in YAML
runtime:
  api_key: sk-ant-...  # Don't do this!
```

### 2. Set Appropriate max_tokens

Claude requires `max_tokens` to be set. Choose based on your needs:

```yaml
runtime:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 2048  # Required field
```

### 3. Use Telemetry for Debugging

```bash
# Enable debug mode
uv run strands run workflow.yaml --debug --verbose

# Export execution traces
uv run strands run workflow.yaml --trace
```

## Next Steps

Now that you have Anthropic configured, explore advanced features:

1. **Multi-step workflows**: Learn the [chain pattern tutorial](first-multi-step.md)
2. **Add tools**: Use [HTTP executors](../howto/tools.md) for API integration
3. **Enable observability**: Set up [OpenTelemetry](../howto/telemetry.md)
4. **Browse examples**: Check `examples/single-agent-chain-anthropic.yaml`

## Common Commands Reference

```bash
# Validate workflow
strands validate workflow.yaml

# Run workflow
strands run workflow.yaml

# Run with variable overrides
strands run workflow.yaml --var topic="machine learning"

# Debug mode
strands run workflow.yaml --debug --verbose

# Force overwrite artifacts
strands run workflow.yaml --force
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (required) | None |

## Further Reading

- [Anthropic Documentation](https://docs.anthropic.com/) - Official API docs
- [Claude Models](https://docs.anthropic.com/en/docs/models-overview) - Model comparison
- [Anthropic Pricing](https://www.anthropic.com/pricing#anthropic-api) - Detailed pricing
- [Workflow Schema Reference](../reference/spec.md) - Complete YAML spec
- [Token Budgets Guide](../howto/budgets.md) - Cost control strategies

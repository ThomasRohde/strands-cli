---
title: Quickstart with Google Gemini
description: Get started with Strands CLI using Google's Gemini API
keywords: gemini, google, quickstart, tutorial, api key, gemini-flash, gemini-pro
---

# Quickstart with Google Gemini

This tutorial will guide you through setting up and running your first Strands workflow using Google's Gemini API. Gemini provides powerful, fast, and cost-effective models for a wide range of tasks.

## What You'll Learn

- How to install the Gemini provider
- How to set up a Google API key
- How to configure and use Gemini models
- How to create and run a Gemini workflow
- Understanding model selection and pricing

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **Google account** for API access
- **Basic command-line experience**
- **Strands CLI** installed

## Step 1: Install Gemini Provider

The Gemini provider is an optional extra that must be installed separately:

```bash
# Install the Gemini provider extra
uv pip install -e ".[gemini]"

# Or install all optional providers
uv pip install -e ".[all-providers]"
```

## Step 2: Create a Google API Key

### Access Google AI Studio

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. No payment method required to start!

!!! tip "Free Tier"
    Google AI Studio offers a generous free tier for Gemini API usage, perfect for learning and development.

### Generate API Key

1. Click on "Get API key" in AI Studio
2. Create a new API key or use an existing one
3. Copy the key (starts with `AIza...`)
4. Store it securely

!!! warning "Keep Your Key Safe"
    Never commit API keys to version control. Use environment variables or secrets managers.

## Step 3: Configure Your API Key

### Option 1: Environment Variable (Recommended)

```bash
# Linux/macOS - Standard Google API key name
export GOOGLE_API_KEY=AIza...

# Alternative: Gemini-specific name (also supported)
export GEMINI_API_KEY=AIza...

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'export GOOGLE_API_KEY=AIza...' >> ~/.bashrc

# Windows PowerShell
$env:GOOGLE_API_KEY = "AIza..."

# Add to PowerShell profile for persistence
Add-Content $PROFILE "`n`$env:GOOGLE_API_KEY = 'AIza...'"
```

!!! note "Flexible Environment Variable Names"
    Strands supports both `GOOGLE_API_KEY` and `GEMINI_API_KEY`. Use whichever you prefer!

### Option 2: .env File (Development)

Create a `.env` file in your project directory:

```bash
GOOGLE_API_KEY=AIza...
# or
GEMINI_API_KEY=AIza...
```

!!! warning "Don't Commit .env Files"
    Add `.env` to your `.gitignore` file!

### Verify Setup

```bash
# Quick test using curl (replace YOUR_API_KEY)
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GOOGLE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'
```

## Step 4: Choose a Model

Google offers several Gemini models optimized for different use cases:

| Model | ID | Use Case | Context | Cost (per 1M tokens) |
|-------|-----|----------|---------|---------------------|
| Gemini 2.5 Flash | `gemini-2.5-flash` | Best balance | 1M | Input: $0.075, Output: $0.30 |
| Gemini 2.5 Pro | `gemini-2.5-pro` | Advanced reasoning | 2M | Input: $1.25, Output: $5.00 |
| Gemini 2.5 Flash Lite | `gemini-2.5-flash-lite` | Most efficient | 1M | Input: $0.015, Output: $0.06 |

!!! tip "Start with Gemini 2.5 Flash"
    `gemini-2.5-flash` offers excellent performance at a very competitive price point. Perfect for most applications!

!!! info "Pricing Note"
    Prices shown are for standard usage. Check [Google AI Pricing](https://ai.google.dev/pricing) for current rates and free tier limits.

## Step 5: Create Your First Gemini Workflow

Create a new file called `my-gemini-workflow.yaml`:

```yaml
version: 0
name: my-gemini-workflow
description: My first Strands workflow using Google Gemini

runtime:
  provider: gemini
  model_id: gemini-2.5-flash
  temperature: 0.7
  max_tokens: 2048
  top_p: 0.9

inputs:
  values:
    topic: "renewable energy"

agents:
  analyst:
    prompt: |
      You are a concise technical analyst specializing in clear, actionable insights.

      Your analysis should:
      - Be structured with clear sections
      - Use bullet points for readability
      - Provide specific examples
      - Keep the total response under 500 words

pattern:
  type: single_agent
  config:
    agent: analyst
    input: |
      Analyze the following topic and provide a brief overview:

      Topic: {{ topic }}

      Please provide:
      1. A brief definition/overview (2-3 sentences)
      2. Key considerations or challenges (3-5 bullet points)
      3. Potential implications or applications (2-3 bullet points)

outputs:
  artifacts:
    - path: ./analysis.md
      from: "{{ last_response }}"
```

### Understanding Gemini-Specific Settings

- **`provider: gemini`**: Tells Strands to use Google's Gemini API
- **`model_id: gemini-2.5-flash`**: Specifies which Gemini model
- **`temperature: 0.7`**: Controls randomness (0.0-2.0 for Gemini)
- **`max_tokens: 2048`**: Maximum output length
- **`top_p: 0.9`**: Nucleus sampling parameter (optional)

## Step 6: Validate Your Workflow

```bash
uv run strands validate my-gemini-workflow.yaml
```

Expected output:

```
[OK] No unsupported features detected.
This workflow is compatible with the current MVP.
```

## Step 7: Run Your Workflow

```bash
uv run strands run my-gemini-workflow.yaml
```

Expected output:

```
Running workflow: my-gemini-workflow
[OK] Workflow completed successfully
Duration: 2.14s

Artifacts written:
  ./analysis.md
```

## Step 8: Check the Output

```bash
cat analysis.md
```

You'll see Gemini's fast, comprehensive analysis of renewable energy.

## Step 9: Experiment with Different Models

Try different Gemini models for various use cases:

```bash
# Use Gemini 2.5 Pro for complex analysis
uv run strands run my-gemini-workflow.yaml \
  --var topic="quantum mechanics" --force

# Use Gemini 2.5 Flash Lite for simple tasks (super cost-effective)
uv run strands run my-gemini-workflow.yaml \
  --var topic="healthy recipes" --force
```

Update your workflow to use a different model:

```yaml
runtime:
  provider: gemini
  model_id: gemini-2.5-pro  # For advanced reasoning
  temperature: 0.9
  max_tokens: 4096
```

## Step 10: Customize with Variables

```bash
# Analyze climate change
uv run strands run my-gemini-workflow.yaml \
  --var topic="climate change" --force

# Analyze blockchain technology
uv run strands run my-gemini-workflow.yaml \
  --var topic="blockchain technology" --force

# Analyze neural networks
uv run strands run my-gemini-workflow.yaml \
  --var topic="neural networks" --force
```

## Troubleshooting

### Authentication Error

**Problem**: `API key not valid`

**Solution**:
1. Verify API key is correct (starts with `AIza`)
2. Check environment variable: `echo $GOOGLE_API_KEY`
3. Ensure key is active in Google AI Studio
4. Try both `GOOGLE_API_KEY` and `GEMINI_API_KEY` names

```bash
# Test both variable names
echo $GOOGLE_API_KEY
echo $GEMINI_API_KEY
```

### Rate Limit Exceeded

**Problem**: `429 Resource has been exhausted`

**Solution**:
1. Wait briefly and retry (Strands has automatic retry)
2. Use the free tier rate limits as guidance
3. Consider upgrading to paid tier for higher limits

### Quota Exceeded

**Problem**: `Quota exceeded`

**Solution**:
1. Check your usage in Google AI Studio
2. Wait for quota reset (typically per-minute)
3. Upgrade to paid tier for higher quotas

## Cost Management

### Understanding Pricing

Gemini is very cost-effective compared to other providers:

**Example**: Using Gemini 2.5 Flash with 1,000 input tokens and 500 output tokens:
```
Cost = (1000/1M × $0.075) + (500/1M × $0.30) = $0.00023
```

This is approximately **20x cheaper** than comparable models from other providers!

### Free Tier Limits

Google AI Studio offers generous free tier limits:
- 15 requests per minute (RPM)
- 1 million tokens per minute (TPM)
- 1,500 requests per day (RPD)

### Monitor Usage

1. **Google AI Studio Dashboard**: Check usage and quotas
2. **Use Token Budgets**: Limit workflow consumption

```yaml
runtime:
  provider: gemini
  model_id: gemini-2.5-flash
  budgets:
    token_budget:
      max_input_tokens: 100000
      max_output_tokens: 20000
```

## Model Selection Guide

### When to Use Each Model

| Scenario | Recommended Model | Reason |
|----------|------------------|---------|
| General Q&A, content generation | `gemini-2.5-flash` | Best balance of speed, quality, cost |
| Complex analysis, long documents | `gemini-2.5-pro` | Superior reasoning, 2M token context |
| High-volume, simple tasks | `gemini-2.5-flash-lite` | Ultra cost-effective |

### Model Capabilities Comparison

| Feature | Flash Lite | Flash | Pro |
|---------|-----------|-------|-----|
| Speed | Very Fast | Fast | Medium |
| Quality | Good | Excellent | Superior |
| Context Window | 1M tokens | 1M tokens | 2M tokens |
| Cost | Lowest | Low | Medium |
| Reasoning | Good | Great | Excellent |

## Best Practices

### 1. Secure API Key Management

```bash
# Good: Environment variable
export GOOGLE_API_KEY=AIza...

# Bad: Hardcoded in YAML
runtime:
  api_key: AIza...  # Don't do this!
```

### 2. Optimize Token Usage

Gemini's pricing makes it very affordable, but you can optimize further:

```yaml
runtime:
  provider: gemini
  model_id: gemini-2.5-flash
  temperature: 0.7
  max_tokens: 1024  # Set based on actual needs
```

### 3. Use Telemetry for Debugging

```bash
# Enable debug mode
uv run strands run workflow.yaml --debug --verbose

# Export execution traces
uv run strands run workflow.yaml --trace
```

### 4. Leverage Fast Response Times

Gemini models are particularly fast. Use this for:
- Interactive applications
- Real-time analysis
- High-throughput workflows

## Performance Tips

1. **Use Flash for most tasks**: It's fast and cost-effective
2. **Leverage large context**: Gemini handles 1M-2M tokens efficiently
3. **Batch similar requests**: Combine multiple analyses into one workflow
4. **Set appropriate max_tokens**: Don't over-allocate if not needed

## Next Steps

Now that you have Gemini configured, explore advanced features:

1. **Multi-step workflows**: Learn the [chain pattern tutorial](first-multi-step.md)
2. **Add tools**: Use [HTTP executors](../howto/tools.md) for API integration
3. **Enable observability**: Set up [OpenTelemetry](../howto/telemetry.md)
4. **Browse examples**: Check `examples/single-agent-chain-gemini.yaml`

## Common Commands Reference

```bash
# Validate workflow
strands validate workflow.yaml

# Run workflow
strands run workflow.yaml

# Run with variable overrides
strands run workflow.yaml --var topic="AI ethics"

# Debug mode
strands run workflow.yaml --debug --verbose

# Force overwrite artifacts
strands run workflow.yaml --force
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Google API key (primary name) | None |
| `GEMINI_API_KEY` | Google API key (alternative name) | None |

!!! note
    Both variable names are supported. The provider checks `GOOGLE_API_KEY` first, then `GEMINI_API_KEY`.

## Further Reading

- [Google AI Documentation](https://ai.google.dev/docs) - Official Gemini docs
- [Gemini Models](https://ai.google.dev/models/gemini) - Model details
- [Google AI Pricing](https://ai.google.dev/pricing) - Detailed pricing and quotas
- [Workflow Schema Reference](../reference/spec.md) - Complete YAML spec
- [Token Budgets Guide](../howto/budgets.md) - Cost control strategies

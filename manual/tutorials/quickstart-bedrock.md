---
title: Quickstart with AWS Bedrock
description: Get started with Strands CLI using AWS Bedrock for managed AI model execution
keywords: aws, bedrock, quickstart, tutorial, claude, anthropic, amazon, credentials, iam
---

# Quickstart with AWS Bedrock

This tutorial will guide you through setting up and running your first Strands workflow using AWS Bedrock, Amazon's managed service for foundation models. Bedrock provides enterprise-grade AI with built-in security, compliance, and scalability.

## What You'll Learn

- How to configure AWS credentials for Bedrock
- How to select and use Bedrock models
- How to create and run a Bedrock workflow
- Understanding regions and model availability
- Best practices for production deployments

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **AWS Account** with Bedrock access
- **Basic command-line experience**
- **AWS CLI** installed (recommended)
- **IAM permissions** for Bedrock model invocation

## Step 1: Enable Bedrock Model Access

AWS Bedrock requires explicit model access activation in your AWS account.

1. **Sign in to AWS Console**: Navigate to the [AWS Bedrock Console](https://console.aws.amazon.com/bedrock/)
2. **Select Region**: Choose your preferred region (e.g., `us-east-1`)
3. **Enable Model Access**:
   - Click "Model access" in the left sidebar
   - Click "Manage model access"
   - Select the models you want to use (we recommend starting with Claude 3 Sonnet)
   - Click "Request model access"

!!! warning "Model Access Approval"
    Some models require approval, which may take a few minutes to several hours. Claude models are typically instant.

### Recommended Models

| Model | ID | Use Case |
|-------|-----|----------|
| Claude 3.5 Sonnet | `us.anthropic.claude-3-5-sonnet-20241022-v2:0` | Best overall performance |
| Claude 3 Sonnet | `us.anthropic.claude-3-sonnet-20240229-v1:0` | Balanced performance/cost |
| Claude 3 Haiku | `us.anthropic.claude-3-haiku-20240307-v1:0` | Fast, cost-effective |

!!! note "Regional Prefixes"
    Bedrock model IDs must include a regional prefix:
    - US regions: `us.anthropic.claude-...`
    - EU regions: `eu.anthropic.claude-...`
    - Asia-Pacific: `ap-northeast.anthropic.claude-...` or `ap-southeast.anthropic.claude-...`

## Step 2: Configure AWS Credentials

### Option 1: AWS CLI (Recommended)

```bash
# Install AWS CLI if not already installed
# macOS: brew install awscli
# Windows: Download from aws.amazon.com/cli/
# Linux: pip install awscli

# Configure credentials
aws configure
```

You'll be prompted for:

- **AWS Access Key ID**: Your IAM access key
- **AWS Secret Access Key**: Your IAM secret key
- **Default region**: e.g., `us-east-1`
- **Default output format**: `json`

### Option 2: Environment Variables

```bash
# Linux/macOS
export AWS_ACCESS_KEY_ID=your-access-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-access-key
export AWS_DEFAULT_REGION=us-east-1

# Windows PowerShell
$env:AWS_ACCESS_KEY_ID = "your-access-key-id"
$env:AWS_SECRET_ACCESS_KEY = "your-secret-access-key"
$env:AWS_DEFAULT_REGION = "us-east-1"
```

### Option 3: IAM Role (EC2/ECS/Lambda)

If running on AWS infrastructure, use IAM roles instead of credentials. No configuration needed!

### Verify Access

```bash
# Test Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

## Step 3: Check IAM Permissions

Your IAM user or role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
      ]
    }
  ]
}
```

!!! tip "Least Privilege"
    For production, restrict to specific model ARNs and regions you actually use.

## Step 4: Install Strands CLI

Install Strands CLI with AWS dependencies:

=== "Using uv (recommended)"

    ```bash
    # Install uv if not already installed
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install Strands CLI with AWS support
    uv pip install "strands-cli[aws]"

    # Verify installation
    uv run strands --version
    ```

=== "Using pip"

    ```bash
    # Install Strands CLI with AWS support
    pip install "strands-cli[aws]"

    # Verify installation
    strands --version
    ```

## Step 5: Create Your First Bedrock Workflow

Create a new file called `my-bedrock-workflow.yaml`:

```yaml
version: 0
name: my-bedrock-workflow
description: My first Strands workflow using AWS Bedrock

runtime:
  provider: bedrock
  model_id: anthropic.claude-3-sonnet-20240229-v1:0
  region: us-east-1

inputs:
  values:
    company: "Acme Corp"
    product: "cloud storage solution"

agents:
  copywriter:
    prompt: |
      You are a professional marketing copywriter with expertise in B2B SaaS.
      Create compelling, benefit-focused copy that resonates with decision-makers.
      Format your response in clean Markdown.

pattern:
  type: single_agent
  config:
    agent: copywriter
    input: |
      Write a compelling product tagline and 3-sentence value proposition
      for {{ company }}'s {{ product }}.

      Focus on benefits, not features. Make it memorable and actionable.

outputs:
  artifacts:
    - path: ./marketing-copy.md
      from: "{{ last_response }}"
```

### Understanding Bedrock-Specific Settings

- **`provider: bedrock`**: Tells Strands to use AWS Bedrock
- **`model_id`**: Full Bedrock model identifier (includes version)
- **`region`**: AWS region where your model access is enabled
  - If omitted, uses `AWS_DEFAULT_REGION` or `us-east-1`

## Step 6: Validate Your Workflow

```bash
uv run strands validate my-bedrock-workflow.yaml
```

Expected output:

```
✓ Workflow is valid
```

## Step 7: Run Your Workflow

```bash
uv run strands run my-bedrock-workflow.yaml
```

Expected output:

```
🚀 Starting workflow: my-bedrock-workflow
📊 Runtime: bedrock (anthropic.claude-3-sonnet-20240229-v1:0)
🌍 Region: us-east-1
🤖 Agent: copywriter
✅ Workflow completed successfully
📝 Artifact written: ./marketing-copy.md
```

## Step 8: Check the Output

```bash
cat marketing-copy.md
```

You'll see Claude's marketing copy for your fictional product.

## Step 9: Use Environment Configuration

Instead of hardcoding settings, use environment variables:

```yaml
version: 0
name: configurable-bedrock-workflow
description: Workflow with environment-based configuration

runtime:
  provider: bedrock
  # model_id and region will use environment defaults
  # Override with STRANDS_BEDROCK_MODEL_ID and STRANDS_AWS_REGION

agents:
  assistant:
    prompt: "You are a helpful AI assistant."

pattern:
  type: single_agent
  config:
    agent: assistant
    input: "{{ prompt }}"
```

Then run with overrides:

```bash
# Set defaults
export STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
export STRANDS_AWS_REGION=us-west-2

# Run with variable override
uv run strands run configurable-bedrock-workflow.yaml \
  --var prompt="Explain serverless computing"
```

## Region and Model Availability

Different models are available in different AWS regions:

| Region | Code | Claude 3.5 Sonnet | Claude 3 Sonnet | Claude 3 Haiku |
|--------|------|-------------------|-----------------|----------------|
| US East (N. Virginia) | `us-east-1` | ✅ | ✅ | ✅ |
| US West (Oregon) | `us-west-2` | ✅ | ✅ | ✅ |
| Europe (Frankfurt) | `eu-central-1` | ✅ | ✅ | ✅ |
| Asia Pacific (Tokyo) | `ap-northeast-1` | ✅ | ✅ | ✅ |
| Asia Pacific (Singapore) | `ap-southeast-1` | ✅ | ✅ | ✅ |

Check the [AWS Bedrock documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html) for the latest availability.

## Troubleshooting

### Access Denied Errors

**Problem**: `AccessDeniedException: User is not authorized to perform: bedrock:InvokeModel`

**Solution**:
1. Verify IAM permissions include `bedrock:InvokeModel`
2. Check the resource ARN matches your model
3. Ensure credentials are correctly configured

```bash
# Verify current identity
aws sts get-caller-identity

# List accessible models
aws bedrock list-foundation-models --region us-east-1
```

### Model Not Found

**Problem**: `ResourceNotFoundException: Could not find model`

**Solution**:
1. Verify model access is enabled in Bedrock console
2. Check model ID is correct (including version)
3. Verify model is available in your selected region

### Throttling Errors

**Problem**: `ThrottlingException: Rate exceeded`

**Solution**:
1. Add retry logic (Strands does this automatically)
2. Request a quota increase in AWS Service Quotas
3. Implement exponential backoff in high-volume scenarios
4. Use multiple models or regions for load balancing

### Invalid Region

**Problem**: `ValidationException: Invalid region`

**Solution**:
1. Use a region where Bedrock is available
2. Set region explicitly in workflow or environment
3. Check `aws bedrock list-foundation-models --region <region>`

## Cost Optimization

### Understanding Bedrock Pricing

Bedrock charges per token (input and output separately):

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|-------|-----------------------|------------------------|
| Claude 3.5 Sonnet | $0.003 | $0.015 |
| Claude 3 Sonnet | $0.003 | $0.015 |
| Claude 3 Haiku | $0.00025 | $0.00125 |

### Tips to Reduce Costs

1. **Use Haiku for simple tasks**: 10x cheaper than Sonnet
2. **Minimize prompt size**: Remove unnecessary context
3. **Set output limits**: Use max_tokens in agent configuration
4. **Cache prompts**: Use Strands' agent caching for repeated tasks
5. **Monitor with CloudWatch**: Track token usage and costs

## Production Best Practices

### 1. Use IAM Roles Instead of Keys

```yaml
# Good: Implicit credentials from IAM role (EC2/ECS/Lambda)
runtime:
  provider: bedrock
  model_id: anthropic.claude-3-sonnet-20240229-v1:0
  region: us-east-1
```

### 2. Enable CloudWatch Logging

```bash
# Enable model invocation logging in Bedrock console
# Settings → Model invocation logging → Enable
```

### 3. Implement Budget Controls

```yaml
runtime:
  provider: bedrock
  model_id: anthropic.claude-3-sonnet-20240229-v1:0
  region: us-east-1
  budgets:
    token_budget:
      max_input_tokens: 50000
      max_output_tokens: 10000
```

### 4. Use Multi-Region Fallback

```bash
# Primary region
STRANDS_AWS_REGION=us-east-1

# Fallback to us-west-2 if us-east-1 has issues
# (Requires application-level logic or load balancer)
```

### 5. Tag Resources for Cost Tracking

Use AWS tags to track Bedrock usage by project, environment, or team.

## Next Steps

Now that you have Bedrock configured, explore advanced features:

1. **Multi-step workflows**: Learn the [chain pattern tutorial](first-multi-step.md)
2. **Add custom tools**: Integrate APIs with [HTTP executors](../howto/tools.md)
3. **Enable telemetry**: Track execution with [OpenTelemetry](../howto/telemetry.md)
4. **Explore examples**: Check `examples/` for Bedrock workflows:
   - `examples/minimal-bedrock.yaml` - Minimal configuration
   - `examples/evaluator-optimizer-code-review-bedrock.yaml` - Iterative refinement

## Key Concepts Recap

| Concept | Description |
|---------|-------------|
| **Model ID** | Full Bedrock model identifier including version |
| **Region** | AWS region where model access is enabled |
| **IAM Role** | Preferred authentication method for AWS resources |
| **Model Access** | Must be explicitly enabled per region in console |
| **Streaming** | Bedrock supports streaming responses (automatic) |

## Common Commands Reference

```bash
# Validate workflow
strands validate workflow.yaml

# Run workflow
strands run workflow.yaml

# Run with specific region
strands run workflow.yaml --var region=us-west-2

# Debug mode
strands run workflow.yaml --debug --verbose

# Check available Bedrock models
aws bedrock list-foundation-models --region us-east-1

# Test Bedrock access
aws bedrock-runtime invoke-model \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":100,"messages":[{"role":"user","content":"Hi"}]}' \
  --region us-east-1 \
  output.json
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `STRANDS_AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `STRANDS_BEDROCK_MODEL_ID` | Default Bedrock model | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `AWS_ACCESS_KEY_ID` | AWS access key | (from AWS CLI) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | (from AWS CLI) |
| `AWS_SESSION_TOKEN` | Temporary session token | (optional) |
| `AWS_PROFILE` | AWS CLI profile name | `default` |

## Further Reading

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/) - Official AWS docs
- [Claude on Bedrock Guide](https://docs.anthropic.com/claude/docs/claude-on-amazon-bedrock) - Anthropic's guide
- [Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) - Cost calculator
- [Workflow Schema Reference](../reference/schema.md) - Complete YAML spec
- [Security Best Practices](../explanation/security-model.md) - Production security

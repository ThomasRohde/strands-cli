# How to Manage Secrets and Environment Variables

This guide shows you how to securely manage secrets, API keys, and environment variables in Strands workflows.

## Environment Variable Secrets

The current MVP supports secrets from environment variables using `source: env`.

### Basic Usage

```yaml
version: 0
name: secure-workflow
runtime:
  provider: openai
  model_id: gpt-4o-mini

env:
  secrets:
    - name: OPENAI_API_KEY
      source: env
      description: "OpenAI API key"

agents:
  assistant:
    prompt: "You are a helpful assistant"

pattern:
  type: chain
  config:
    steps:
      - agent_id: assistant
        prompt: "Hello!"
```

Set the environment variable before running:

```bash
export OPENAI_API_KEY="sk-..."
strands run workflow.yaml
```

### Referencing Secrets

Use secrets in templates with `{{ secrets.NAME }}`:

```yaml
tools:
  http_executors:
    - id: github_api
      base_url: https://api.github.com
      headers:
        Authorization: "Bearer {{ secrets.GITHUB_TOKEN }}"
      endpoints:
        - path: /user
          method: GET

env:
  secrets:
    - name: GITHUB_TOKEN
      source: env
      description: "GitHub personal access token"
```

### Multiple Secrets

```yaml
env:
  secrets:
    - name: API_KEY
      source: env
      description: "Primary API key"
    
    - name: DATABASE_URL
      source: env
      description: "Database connection string"
    
    - name: AWS_ACCESS_KEY_ID
      source: env
      description: "AWS access key"
    
    - name: AWS_SECRET_ACCESS_KEY
      source: env
      description: "AWS secret key"
```

## Best Practices

### 1. Never Hardcode Secrets

❌ **Don't do this:**

```yaml
tools:
  http_executors:
    - id: api
      headers:
        X-API-Key: "hardcoded-secret-key-123"  # NEVER DO THIS
```

✅ **Do this instead:**

```yaml
tools:
  http_executors:
    - id: api
      headers:
        X-API-Key: "{{ secrets.API_KEY }}"

env:
  secrets:
    - name: API_KEY
      source: env
```

### 2. Use .env Files Locally

Create `.env` file (add to `.gitignore`):

```bash
# .env
OPENAI_API_KEY=sk-proj-...
GITHUB_TOKEN=ghp_...
DATABASE_URL=postgresql://user:pass@localhost/db
```

Load with your shell or tool:

```bash
# PowerShell
Get-Content .env | ForEach-Object {
  $parts = $_ -split '=', 2
  [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
}
strands run workflow.yaml

# Bash
export $(cat .env | xargs)
strands run workflow.yaml

# Or use dotenv tool
dotenv run -- strands run workflow.yaml
```

### 3. Document Required Secrets

Add clear descriptions:

```yaml
env:
  secrets:
    - name: OPENAI_API_KEY
      source: env
      description: |
        OpenAI API key (get from https://platform.openai.com/api-keys)
        Format: sk-proj-...
    
    - name: GITHUB_TOKEN
      source: env
      description: |
        GitHub personal access token with 'repo' scope
        Generate at: https://github.com/settings/tokens
```

### 4. Validate Secrets Early

Check secrets exist before workflow runs:

```bash
# PowerShell
if (-not $env:OPENAI_API_KEY) {
  Write-Error "OPENAI_API_KEY not set"
  exit 1
}
strands run workflow.yaml

# Bash
if [ -z "$OPENAI_API_KEY" ]; then
  echo "Error: OPENAI_API_KEY not set"
  exit 1
fi
strands run workflow.yaml
```

### 5. Use Secret Scoping

Only declare secrets you actually use:

```yaml
# Only declare what you need
env:
  secrets:
    - name: API_KEY
      source: env

# Don't declare unused secrets
```

## CI/CD Integration

### GitHub Actions

Store secrets in GitHub repository settings, then:

```yaml
# .github/workflows/workflow.yml
name: Run Workflow
on: [push]

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install Strands CLI
        run: pip install strands-cli
      
      - name: Run workflow
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: strands run workflow.yaml
```

### GitLab CI

```yaml
# .gitlab-ci.yml
run_workflow:
  image: python:3.12
  script:
    - pip install strands-cli
    - strands run workflow.yaml
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY
    GITHUB_TOKEN: $GITHUB_TOKEN
```

Configure secrets in GitLab CI/CD settings.

### Docker

```dockerfile
# Dockerfile
FROM python:3.12
RUN pip install strands-cli
COPY workflow.yaml .
CMD ["strands", "run", "workflow.yaml"]
```

Run with secrets:

```bash
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY my-workflow
```

## Common Secret Patterns

### AWS Credentials

```yaml
env:
  secrets:
    - name: AWS_ACCESS_KEY_ID
      source: env
      description: "AWS access key ID"
    
    - name: AWS_SECRET_ACCESS_KEY
      source: env
      description: "AWS secret access key"
    
    - name: AWS_REGION
      source: env
      description: "AWS region (e.g., us-east-1)"
```

For Bedrock workflows, these are used automatically.

### API Authentication

```yaml
env:
  secrets:
    - name: API_KEY
      source: env

tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      headers:
        X-API-Key: "{{ secrets.API_KEY }}"
```

### Database Connections

```yaml
env:
  secrets:
    - name: DATABASE_URL
      source: env
      description: "Format: postgresql://user:pass@host:port/db"

# Use in tools or runtime config
```

### OAuth Tokens

```yaml
env:
  secrets:
    - name: OAUTH_TOKEN
      source: env

tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      auth:
        type: bearer
        token: "{{ secrets.OAUTH_TOKEN }}"
```

## Security Considerations

### PII Redaction

Enable PII redaction for traces and logs:

```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
```

This prevents secrets from appearing in telemetry data.

### Secret Validation

Secrets are validated at runtime:

- Missing secrets cause immediate failure
- No default values (fail fast if not set)
- Clear error messages indicate which secret is missing

### Scope Limitation

Secrets are only available:
- Within the workflow execution
- For template rendering
- Not exposed to agents directly
- Redacted from traces (when PII redaction enabled)

## Future: AWS Secrets Manager

Future versions will support AWS Secrets Manager:

```yaml
# Future syntax (not yet implemented)
env:
  secrets:
    - name: API_KEY
      source: aws_secrets_manager
      secret_id: "prod/api/key"
      region: "us-east-1"
```

And AWS Systems Manager Parameter Store:

```yaml
# Future syntax (not yet implemented)
env:
  secrets:
    - name: DATABASE_URL
      source: aws_ssm
      parameter_name: "/app/database/url"
      region: "us-east-1"
```

## Troubleshooting

### Secret Not Found

**Error**: `Secret 'API_KEY' not found in environment`

**Fix**: Set the environment variable:

```bash
export API_KEY="your-key-here"
```

### Secret Empty

**Error**: `Secret 'API_KEY' is empty`

**Fix**: Ensure variable has a value:

```bash
echo $API_KEY  # Should show value
export API_KEY="actual-value"
```

### Template Rendering Error

**Error**: `Failed to render template: 'secrets' is undefined`

**Fix**: Declare secret in spec:

```yaml
env:
  secrets:
    - name: API_KEY
      source: env
```

### Secret Exposed in Logs

**Fix**: Enable PII redaction:

```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
```

## Example: Complete Secure Workflow

```yaml
version: 0
name: secure-api-workflow
description: Demonstrates secure secret management

runtime:
  provider: openai
  model_id: gpt-4o-mini

# Declare all required secrets
env:
  secrets:
    - name: OPENAI_API_KEY
      source: env
      description: "OpenAI API key for LLM calls"
    
    - name: GITHUB_TOKEN
      source: env
      description: "GitHub PAT for API access"
    
    - name: SLACK_WEBHOOK
      source: env
      description: "Slack webhook URL for notifications"

# Enable PII redaction
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true

agents:
  researcher:
    prompt: "You research GitHub repositories"

# Use secrets in tools
tools:
  http_executors:
    - id: github
      base_url: https://api.github.com
      headers:
        Authorization: "Bearer {{ secrets.GITHUB_TOKEN }}"
      endpoints:
        - path: /repos/{owner}/{repo}
          method: GET
    
    - id: slack
      base_url: "{{ secrets.SLACK_WEBHOOK }}"
      endpoints:
        - path: ""
          method: POST

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Get info about tensorflow/tensorflow repo"
      
      - agent_id: researcher
        prompt: "Send summary to Slack"
```

Run securely:

```bash
# Load secrets from .env
export $(cat .env | xargs)

# Verify secrets are set
echo "Checking secrets..."
test -n "$OPENAI_API_KEY" && echo "✓ OPENAI_API_KEY set"
test -n "$GITHUB_TOKEN" && echo "✓ GITHUB_TOKEN set"
test -n "$SLACK_WEBHOOK" && echo "✓ SLACK_WEBHOOK set"

# Run workflow
strands run secure-api-workflow.yaml --trace
```

## See Also

- [Tools Guide](tools.md) - Using secrets in HTTP executors
- [Security Model](../explanation/security-model.md) - Security architecture
- [Environment Variables Reference](../reference/environment.md) - All env vars

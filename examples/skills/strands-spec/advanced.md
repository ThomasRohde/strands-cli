# Advanced Features Guide

Deep dive into context management, telemetry, security, and performance optimization.

## Context Management

### Context Policy Configuration

```yaml
context_policy:
  compression:
    enabled: true
    threshold_tokens: 50000      # Compress when context exceeds this
    target_ratio: 0.5            # Target 50% compression
    strategy: summarization      # or: truncation, sliding_window
    
  notes:
    enabled: true
    max_size_kb: 100             # Max notes storage
    auto_summarize: true         # Compress notes automatically
    
  jit_context:
    enabled: true
    retrieval_fn: "semantic_search"  # Custom retrieval function
    max_retrieved_tokens: 10000
```

### Compression Strategies

**Summarization** (Recommended)
- Uses LLM to compress context
- Preserves semantic meaning
- Best for narrative/reasoning chains

**Truncation**
- Removes oldest messages
- Fast, deterministic
- Best for sliding window patterns

**Sliding Window**
- Keeps first N and last M messages
- Preserves context boundaries
- Best for long chains with stable start/end

### Notes System

Share context between agents efficiently:

```yaml
agents:
  researcher:
    tools: ["notes"]
    prompt: |
      Research {{ topic }}.
      Save key findings to notes under "research_findings".
      
  writer:
    tools: ["notes"]
    prompt: |
      Retrieve "research_findings" from notes.
      Write article based on findings.
```

**Notes API:**
```python
# Agent can call notes tool with:
{
  "action": "write",
  "key": "research_findings",
  "value": "Key insights from research..."
}

{
  "action": "read",
  "key": "research_findings"
}

{
  "action": "list"  # List all note keys
}
```

## Telemetry & Observability

### OpenTelemetry Configuration

```yaml
telemetry:
  enabled: true
  
  otel:
    endpoint: "http://localhost:4317"      # OTLP gRPC endpoint
    protocol: grpc                          # or: http/protobuf
    service_name: "strands-workflow"
    export_interval_ms: 5000
    
    headers:
      x-api-key: "${OTEL_API_KEY}"         # From env var
      
    attributes:
      environment: production
      team: data-science
      
  redaction:
    enabled: true
    patterns:
      - type: email
      - type: phone
      - type: ssn
      - type: credit_card
      - type: custom
        regex: "sk-[a-zA-Z0-9]{48}"        # OpenAI API keys
        replacement: "[REDACTED_API_KEY]"
```

### Trace Export

Export full execution trace:

```yaml
outputs:
  artifacts:
    - path: "./traces/execution-{{ timestamp }}.json"
      from: "{{ $TRACE }}"
```

**Trace structure:**
```json
{
  "workflow_id": "abc123",
  "start_time": "2025-01-15T10:30:00Z",
  "end_time": "2025-01-15T10:35:00Z",
  "pattern": "chain",
  "spans": [
    {
      "span_id": "span-1",
      "name": "agent.researcher.invoke",
      "start_time": "...",
      "end_time": "...",
      "attributes": {
        "agent.name": "researcher",
        "agent.model": "claude-3-sonnet",
        "tokens.input": 1500,
        "tokens.output": 3000
      }
    }
  ],
  "metrics": {
    "total_tokens": 85000,
    "total_cost": 0.42,
    "duration_ms": 300000
  }
}
```

### Budget Tracking

Monitor and enforce budgets:

```yaml
runtime:
  budgets:
    max_tokens: 100000       # Total token limit
    max_duration_s: 600      # Timeout
    max_steps: 50            # Max agent invocations
    
    alerts:
      - threshold: 0.8       # Alert at 80%
        notification: email
        recipient: "team@example.com"
```

**Budget exceeded behavior:**
- Workflow halts immediately
- Current step completes
- Returns partial results with budget exceeded status
- Trace includes budget violation details

## Security Features

### Network Security

```yaml
security:
  network:
    http_request:
      allowlist: ["*.company.com", "api.trusted.org"]
      blocklist: ["admin.company.com"]
      block_private_ips: true              # Block RFC1918 addresses
      block_localhost: true                # Block 127.0.0.1
      max_redirects: 3
      verify_ssl: true
      
  filesystem:
    allowed_paths:
      - "./artifacts"
      - "./data"
    blocked_paths:
      - "/etc"
      - "~/.ssh"
```

### PII Redaction

```yaml
security:
  pii_redaction:
    enabled: true
    
    # Built-in patterns
    patterns:
      - email              # name@example.com
      - phone              # (555) 123-4567
      - ssn                # 123-45-6789
      - credit_card        # 4111-1111-1111-1111
      - ip_address         # 192.168.1.1
      
    # Custom patterns
    custom_patterns:
      - name: employee_id
        regex: "EMP-\\d{6}"
        replacement: "[REDACTED_EMPLOYEE_ID]"
        
      - name: api_key
        regex: "api_key_[a-zA-Z0-9]{32}"
        replacement: "[REDACTED_API_KEY]"
        
    # Scope
    scope:
      - inputs           # Redact workflow inputs
      - outputs          # Redact agent outputs
      - traces           # Redact telemetry traces
      - artifacts        # Redact saved artifacts
```

### Secrets Management

```yaml
env:
  secrets:
    - name: DATABASE_URL
      source: secrets_manager           # AWS Secrets Manager
      secret_id: "prod/db/url"
      
    - name: API_KEY
      source: ssm                       # AWS Systems Manager
      parameter: "/prod/api/key"
      
    - name: GITHUB_TOKEN
      source: env                       # Environment variable
      
    - name: SSH_KEY
      source: file                      # File path
      path: "~/.ssh/deploy_key"
```

**Never hardcode secrets:**
```yaml
# ❌ WRONG
agents:
  api-client:
    prompt: "Use API key: sk-abc123..."

# ✅ CORRECT
env:
  secrets:
    - name: API_KEY
      source: env
      
agents:
  api-client:
    prompt: "Use API key from environment"
```

## Performance Optimization

### Agent Caching

Reuse agents across steps with same configuration:

```yaml
agents:
  analyzer:
    prompt: "Analyze data"
    runtime:
      model_id: "claude-3-sonnet"
      temperature: 0.3

pattern:
  type: chain
  config:
    steps:
      - agent: analyzer
        input: "Analyze dataset 1"
      - agent: analyzer          # Reuses cached agent
        input: "Analyze dataset 2"
      - agent: analyzer          # Reuses cached agent
        input: "Analyze dataset 3"
```

**Cache behavior:**
- Agent cached by: agent_id + runtime config hash
- 90% reduction in overhead for multi-step workflows
- HTTP clients pooled and reused
- Automatic cleanup on workflow completion

### Model Client Pooling

Shared HTTP clients across agents:

```yaml
runtime:
  provider: bedrock
  model_id: "claude-3-sonnet"
  region: "us-east-1"

agents:
  agent-1:
    # Uses pooled client (provider+model+region)
  agent-2:
    # Reuses same pooled client
  agent-3:
    runtime:
      temperature: 0.8    # Still uses same pooled client
```

**Pooling key:** `(provider, model_id, region)`

### Parallel Execution Tuning

```yaml
runtime:
  max_parallel: 10         # Max concurrent agent invocations

pattern:
  type: parallel
  config:
    branches:
      - name: task-1
        # ... (up to 10 execute concurrently)
```

**Optimization guidelines:**
- I/O-bound tasks: `max_parallel: 10-20`
- CPU-bound tasks: `max_parallel: 4-8`
- Rate-limited APIs: `max_parallel: 2-5`
- Monitor token usage across parallel branches

### Token Optimization

```yaml
agents:
  researcher:
    prompt: "Research {{ topic }}"
    runtime:
      max_tokens: 1000         # Limit response size
      
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research topic"
        context_mode: summary   # Only pass summary to next step
```

**Context modes:**
- `full`: Pass complete response (default)
- `summary`: Auto-summarize before passing
- `none`: Don't pass context

## Advanced Templating

### Jinja2 Templates

```yaml
agents:
  reporter:
    prompt: |
      Generate report for {{ client }}.
      
      {% if priority == 'high' %}
      URGENT: Complete within 24 hours.
      {% else %}
      Standard timeline: 1 week.
      {% endif %}
      
      Include sections:
      {% for section in sections %}
      - {{ section }}
      {% endfor %}
```

**Template variables:**
- Workflow inputs: `{{ variable_name }}`
- Step outputs: `{{ steps[N].response }}`
- Task outputs: `{{ tasks.task_id.response }}`
- Branch outputs: `{{ branches.branch_id.response }}`
- Node outputs: `{{ nodes.node_id.response }}`
- Trace data: `{{ $TRACE }}`
- Timestamp: `{{ timestamp }}`

### Conditional Artifacts

```yaml
outputs:
  artifacts:
    - path: "./reports/{{ client }}-{{ timestamp }}.md"
      from: "{{ last_response }}"
      condition: "{{ generate_report }}"  # Only if true
      
    - path: "./debug/trace.json"
      from: "{{ $TRACE }}"
      condition: "{{ debug_mode }}"
```

## Error Handling & Retries

### Retry Configuration

```yaml
runtime:
  failure_policy:
    retries: 3                    # Retry count
    backoff: exponential          # constant | exponential | jittered
    initial_delay_ms: 1000        # First retry delay
    max_delay_ms: 30000           # Max delay cap
    multiplier: 2.0               # Exponential multiplier
    
    retry_on:                     # Retry conditions
      - status_code: 429          # Rate limit
      - status_code: 500          # Server error
      - status_code: 503          # Service unavailable
      - error_type: "timeout"
      
    no_retry_on:                  # Never retry
      - status_code: 400          # Bad request
      - status_code: 401          # Unauthorized
      - status_code: 403          # Forbidden
```

### Circuit Breaker

```yaml
runtime:
  circuit_breaker:
    enabled: true
    failure_threshold: 5          # Open after N failures
    timeout_ms: 60000             # Timeout duration
    half_open_max_calls: 3        # Test calls before closing
```

## Durable Execution

### Session Persistence

```yaml
# Automatically enabled by default
# Sessions saved to ~/.strands/sessions/

# Run workflow (saves session)
$ uv run strands run workflow.yaml --var topic="AI"

# Resume from failure point
$ uv run strands run --resume <session-id>

# Disable session saving
$ uv run strands run workflow.yaml --no-save-session
```

### Checkpointing

```yaml
pattern:
  type: chain
  config:
    checkpoint_interval: 5        # Checkpoint every 5 steps
    checkpoint_path: "./checkpoints"
    
    steps:
      # ... (long-running steps)
```

**Resume behavior:**
- Skips completed steps
- Restarts from last checkpoint
- Preserves context and state
- Budget tracking continues from checkpoint

## Monitoring & Alerting

### Health Checks

```bash
# Check strands-cli health
uv run strands doctor

# Validate workflow spec
uv run strands validate workflow.yaml

# Test provider connectivity
uv run strands test-provider --provider bedrock --region us-east-1
```

### Metrics Collection

```yaml
telemetry:
  metrics:
    enabled: true
    
    collectors:
      - type: prometheus
        endpoint: "http://localhost:9090"
        interval_ms: 10000
        
      - type: cloudwatch
        namespace: "Strands/Workflows"
        region: "us-east-1"
        
    custom_metrics:
      - name: workflow_success_rate
        type: gauge
        
      - name: agent_latency
        type: histogram
        buckets: [100, 500, 1000, 5000, 10000]
```

## Environment-Specific Configs

### Multi-Environment Setup

```yaml
# base.yaml (shared config)
version: 0
name: "data-pipeline"

runtime:
  provider: bedrock
  budgets:
    max_duration_s: 600

# Production overrides
# prod.yaml
runtime:
  region: "us-east-1"
  model_id: "claude-3-opus"  # More capable model
  
telemetry:
  enabled: true
  otel:
    endpoint: "https://otel.prod.company.com"

# Development overrides  
# dev.yaml
runtime:
  region: "us-west-2"
  model_id: "claude-3-haiku"  # Faster, cheaper
  
telemetry:
  enabled: false  # No telemetry in dev
```

**Usage:**
```bash
# Merge configs (later overrides earlier)
uv run strands run base.yaml dev.yaml

# Production
uv run strands run base.yaml prod.yaml
```

## Best Practices Summary

1. **Context Management**
   - Enable compression for workflows > 10 steps
   - Use notes for cross-agent data sharing
   - Set realistic context limits

2. **Security**
   - Always use secrets management (never hardcode)
   - Enable PII redaction for production
   - Use network allowlists for HTTP tools

3. **Performance**
   - Leverage agent caching for repeated configs
   - Set appropriate `max_parallel` for workload
   - Monitor token usage across workflow

4. **Observability**
   - Enable OpenTelemetry in production
   - Export traces for debugging
   - Set up budget alerts

5. **Reliability**
   - Configure retries with exponential backoff
   - Enable session persistence
   - Set realistic budgets and timeouts

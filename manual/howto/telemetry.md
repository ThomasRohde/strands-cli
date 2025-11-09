---
title: Telemetry and Observability
description: OpenTelemetry setup, trace exports, and PII redaction
keywords: telemetry, observability, opentelemetry, otel, tracing, spans, otlp, pii redaction
---

# How to Use Telemetry and Observability

This guide shows you how to enable OpenTelemetry tracing, export traces, enable debug logging, and redact PII in Strands workflows.

## Quick Start

### Enable Trace Export

Add `--trace` flag to export the execution trace:

```bash
strands run workflow.yaml --trace
```

This creates `artifacts/<workflow-name>-trace.json` with complete execution details.

### Enable Debug Logging

Use `--debug` for detailed structured logs:

```bash
strands run workflow.yaml --debug
```

Debug mode shows:
- Variable resolution
- Template rendering
- Agent invocations
- Tool executions
- Context management operations

### Enable Verbose Output

Add `--verbose` for more console output:

```bash
strands run workflow.yaml --verbose --debug
```

## OpenTelemetry Configuration

### OTLP Export to Collector

Configure OTLP export in your workflow spec:

```yaml
version: 0
name: my-workflow
runtime:
  provider: openai
  model_id: gpt-4o-mini

telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
    sample_ratio: 1.0

agents:
  analyst:
    prompt: "Analyze the data"

pattern:
  type: chain
  config:
    steps:
      - agent_id: analyst
        prompt: "Analyze {{ topic }}"
```

### OTLP Endpoints

Common collector endpoints:

| Platform | Endpoint |
|----------|----------|
| **Jaeger** | `http://localhost:4318/v1/traces` |
| **Zipkin** | `http://localhost:9411/api/v2/spans` |
| **Honeycomb** | `https://api.honeycomb.io/v1/traces` |
| **New Relic** | `https://otlp.nr-data.net/v1/traces` |
| **Datadog** | `http://localhost:4318/v1/traces` |

### Environment Variables

Override telemetry settings via environment:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318/v1/traces"
export OTEL_SERVICE_NAME="production-workflow"
export STRANDS_DEBUG=true
```

## Trace Artifacts

### Using `{{ $TRACE }}` Variable

Include trace in workflow artifacts:

```yaml
outputs:
  artifacts:
    - path: "./artifacts/trace.json"
      from: "{{ $TRACE }}"
```

This renders the complete execution trace as JSON.

### Trace Structure

Trace JSON contains:

```json
{
  "trace_id": "unique-trace-id",
  "spec_name": "workflow-name",
  "pattern": "chain",
  "duration_ms": 3421,
  "spans": [
    {
      "name": "execute.chain",
      "span_id": "span-id",
      "start_time": "2025-11-09T10:30:00Z",
      "end_time": "2025-11-09T10:30:03Z",
      "attributes": {
        "spec.name": "workflow-name",
        "pattern.type": "chain",
        "runtime.provider": "openai"
      },
      "events": [
        {
          "name": "step_start",
          "timestamp": "2025-11-09T10:30:00Z",
          "attributes": {"step.index": 0}
        }
      ],
      "status": "OK"
    }
  ]
}
```

### Analyzing Traces

Use trace data to:

- Debug workflow execution issues
- Identify performance bottlenecks
- Track token usage per step
- Monitor error rates
- Audit LLM interactions

## PII Redaction

### Enable Redaction

Protect sensitive data in traces:

```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
```

### Built-in PII Patterns

Automatically redacts:

- **Email addresses**: `user@example.com` → `***REDACTED***`
- **Credit cards**: `4111-1111-1111-1111` → `***REDACTED***`
- **SSN**: `123-45-6789` → `***REDACTED***`
- **Phone numbers**: `555-123-4567` → `***REDACTED***`
- **API keys**: `sk_live_abc123...` → `***REDACTED***`

### Custom Redaction Patterns

Add domain-specific patterns:

```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
    custom_patterns:
      # AWS Access Keys
      - "\\b(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\\b"
      # GitHub Tokens
      - "\\bghp_[A-Za-z0-9]{36}\\b"
      # Custom internal IDs
      - "\\bINT-[0-9]{8}\\b"
```

Patterns use Python regex syntax.

## Debug Logging

### Enable Debug Mode

```bash
strands run workflow.yaml --debug
```

Debug logs show:

```json
{
  "event": "variable_resolution",
  "timestamp": "2025-11-09T10:30:00Z",
  "variables": {
    "topic": "AI safety",
    "format": "markdown"
  }
}

{
  "event": "template_render",
  "timestamp": "2025-11-09T10:30:00Z",
  "template": "Analyze {{ topic }}",
  "result": "Analyze AI safety"
}

{
  "event": "agent_invoke",
  "timestamp": "2025-11-09T10:30:01Z",
  "agent_id": "analyst",
  "prompt": "Analyze AI safety",
  "model": "gpt-4o-mini"
}

{
  "event": "llm_response",
  "timestamp": "2025-11-09T10:30:03Z",
  "tokens_used": 1234,
  "response_length": 567
}
```

### Debug with Verbose

Combine for maximum visibility:

```bash
strands run workflow.yaml --debug --verbose
```

Shows both structured JSON logs and human-readable console output.

## Span Hierarchy

Strands emits structured spans for all workflow patterns:

### Chain Pattern

```
execute.chain
├── step.0
│   ├── agent.invoke
│   │   ├── llm.request
│   │   └── tool.http_request
│   └── template.render
└── step.1
    └── agent.invoke
```

### Workflow Pattern (DAG)

```
execute.workflow
├── task.overview
│   └── agent.invoke
├── task.technical (parallel)
│   └── agent.invoke
└── task.business (parallel)
    └── agent.invoke
```

### Parallel Pattern

```
execute.parallel
├── branch.technical
│   └── step.0
│       └── agent.invoke
├── branch.business
│   └── step.0
│       └── agent.invoke
└── reduce
    └── agent.invoke
```

## Best Practices

### Production Deployments

1. **Use OTLP endpoint** for centralized trace collection
2. **Set appropriate sample_ratio** (e.g., 0.1 for 10% sampling)
3. **Enable PII redaction** for sensitive data
4. **Monitor trace storage** - high volume can be costly

Example production config:

```yaml
telemetry:
  otel:
    endpoint: "https://otlp.company.com/v1/traces"
    service_name: "production-workflow"
    sample_ratio: 0.1
  redact:
    tool_inputs: true
    tool_outputs: true
```

### Development Workflows

1. **Use --trace flag** for quick exports
2. **Enable --debug** for troubleshooting
3. **Use console exporter** for local testing
4. **Keep sample_ratio at 1.0** to capture everything

Example development config:

```yaml
telemetry:
  otel:
    exporter: console
    sample_ratio: 1.0
```

### Troubleshooting with Traces

1. **Check span hierarchy** for execution flow
2. **Review span attributes** for configuration
3. **Examine span events** for timing details
4. **Filter by error.type** to find failures

### Performance Analysis

Use trace data to identify:

- **Long-running steps**: High `duration_ms` in step spans
- **Token usage**: `tokens.total` attributes
- **Retry patterns**: Multiple `llm.request` spans
- **Tool performance**: `tool.*` span durations

## Common Use Cases

### Debugging Failed Workflows

```bash
# Run with full tracing and debug logging
strands run workflow.yaml --trace --debug --verbose

# Check artifacts/workflow-trace.json for error details
cat artifacts/workflow-trace.json | jq '.spans[] | select(.status == "ERROR")'
```

### Monitoring Production Workflows

```yaml
# Send to centralized collector
telemetry:
  otel:
    endpoint: "https://otlp.company.com/v1/traces"
    service_name: "production-workflow"
    sample_ratio: 0.1  # Sample 10%
  redact:
    tool_inputs: true
    tool_outputs: true
```

### Local Development Testing

```bash
# Console output for quick inspection
strands run workflow.yaml --debug

# Or use console exporter in spec
telemetry:
  otel:
    exporter: console
```

## See Also

- [Debug Mode Reference](../reference/environment.md#debug-mode)
- [OTLP Configuration](../reference/schema.md#telemetry)
- [Security Model](../explanation/security-model.md)

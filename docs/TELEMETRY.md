# OpenTelemetry Tracing and Observability

**Version:** v0.10.0  
**Status:** Production Ready  
**Last Updated:** November 9, 2025

This guide covers the full OpenTelemetry (OTEL) tracing capabilities in strands-cli, including trace export, PII redaction, debugging, and integration with observability platforms.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Configuration](#configuration)
4. [Trace Artifacts](#trace-artifacts)
5. [PII Redaction](#pii-redaction)
6. [Debug Logging](#debug-logging)
7. [OTLP Collectors](#otlp-collectors)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

---

## Quick Start

### Enable OTLP Export

Add `telemetry.otel` configuration to your workflow spec:

```yaml
version: 0
name: "my-workflow"
runtime:
  provider: openai
  model_id: "gpt-4o-mini"

telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
    sample_ratio: 1.0  # 100% sampling

agents:
  analyst:
    prompt: "Analyze the data"

pattern:
  type: chain
  config:
    steps:
      - agent: analyst
        input: "Analyze {{topic}}"
```

### Export Trace Artifact

**Option 1: Using `{{ $TRACE }}` variable**

```yaml
outputs:
  artifacts:
    - path: "./artifacts/trace.json"
      from: "{{ $TRACE }}"
```

**Option 2: Using `--trace` flag**

```bash
uv run strands run workflow.yaml --trace
# Creates: ./artifacts/my-workflow-trace.json
```

### Enable Debug Logging

```bash
uv run strands run workflow.yaml --debug
# Shows structured debug logs for variable resolution, templates, LLM calls
```

---

## Architecture

### Span Hierarchy

Strands-cli emits spans with parent-child relationships across all workflow patterns:

```
execute.<pattern>                    # Root span (chain, workflow, routing, etc.)
├── step.0                          # Chain step span
│   ├── agent.invoke                # Agent invocation
│   │   ├── llm.request            # LLM API call
│   │   └── tool.http_request      # Tool execution
│   └── template.render            # Template rendering
├── step.1
│   └── ...
└── reduce                          # Reduce step (if applicable)
```

### Span Attributes

Every span includes:

| Attribute | Description | Example |
|-----------|-------------|---------|
| `spec.name` | Workflow name | `"research-workflow"` |
| `spec.version` | Spec version | `0` |
| `runtime.provider` | LLM provider | `"openai"` |
| `runtime.model_id` | Model identifier | `"gpt-4o-mini"` |
| `pattern.type` | Workflow pattern | `"chain"` |
| `agent.id` | Agent identifier | `"analyst"` |
| `step.index` | Step/task index | `0` |
| `tool.id` | Tool identifier | `"http_request"` |
| `error.type` | Exception type (on failure) | `"RuntimeError"` |
| `error.message` | Error description | `"API timeout"` |

### Exporters

Strands-cli supports two OTEL exporters:

1. **OTLP Exporter** (Production) - Sends traces to remote collectors via HTTP/gRPC
2. **Console Exporter** (Development) - Prints spans to console as JSON

The system automatically falls back to Console exporter if OTLP endpoint is unavailable.

---

## Configuration

### OTEL Configuration Options

```yaml
telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"  # OTLP HTTP endpoint
    service_name: "my-workflow"                  # Service identifier
    sample_ratio: 1.0                            # Sampling rate (0.0-1.0)
    exporter: "otlp"                             # "otlp" or "console"
```

#### Parameters

- **`endpoint`** (string, optional)
  - OTLP collector endpoint URL
  - Default: `"http://localhost:4318/v1/traces"` (Jaeger default)
  - Examples:
    - Jaeger: `"http://localhost:4318/v1/traces"`
    - Zipkin: `"http://localhost:9411/api/v2/spans"`
    - Honeycomb: `"https://api.honeycomb.io/v1/traces"`

- **`service_name`** (string, optional)
  - Service identifier in trace backend
  - Default: `"strands-cli"`
  - Used for filtering/grouping traces in UI

- **`sample_ratio`** (float, optional)
  - Sampling rate: `0.0` (0%) to `1.0` (100%)
  - Default: `1.0` (100% sampling)
  - Production recommendation: `0.1` (10%) for high-volume workflows

- **`exporter`** (string, optional)
  - Exporter type: `"otlp"` or `"console"`
  - Default: `"otlp"`
  - Console exporter useful for local debugging

### Environment Variables

Override config via environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318/v1/traces"
export OTEL_SERVICE_NAME="my-workflow"
export STRANDS_DEBUG=true  # Enable debug logging
```

---

## Trace Artifacts

### Using `{{ $TRACE }}` Variable

The `{{ $TRACE }}` special variable renders the complete execution trace as JSON:

```yaml
outputs:
  artifacts:
    - path: "./artifacts/trace.json"
      from: "{{ $TRACE }}"
```

**Trace JSON Structure:**

```json
{
  "trace_id": "a1b2c3d4e5f6...",
  "spec_name": "research-workflow",
  "spec_version": 0,
  "pattern": "chain",
  "duration_ms": 3421,
  "spans": [
    {
      "name": "execute.chain",
      "span_id": "abc123...",
      "parent_span_id": null,
      "start_time": "2025-11-09T10:30:00.123Z",
      "end_time": "2025-11-09T10:30:03.544Z",
      "attributes": {
        "spec.name": "research-workflow",
        "pattern.type": "chain",
        "runtime.provider": "openai",
        "runtime.model_id": "gpt-4o-mini"
      },
      "events": [
        {
          "name": "step_start",
          "timestamp": "2025-11-09T10:30:00.150Z",
          "attributes": {"step.index": 0, "agent.id": "researcher"}
        },
        {
          "name": "step_complete",
          "timestamp": "2025-11-09T10:30:02.300Z",
          "attributes": {"step.index": 0, "tokens.total": 1234}
        }
      ],
      "status": "OK"
    },
    {
      "name": "step.0",
      "span_id": "def456...",
      "parent_span_id": "abc123...",
      "start_time": "2025-11-09T10:30:00.150Z",
      "end_time": "2025-11-09T10:30:02.300Z",
      "attributes": {
        "step.index": 0,
        "agent.id": "researcher"
      },
      "status": "OK"
    }
  ]
}
```

### Using `--trace` Flag

Auto-generate trace artifact without modifying spec:

```bash
uv run strands run workflow.yaml --trace
```

Creates: `./artifacts/<spec-name>-trace.json` with the same structure as `{{ $TRACE }}`.

**Benefits:**
- No spec modification required
- Quick trace export for debugging
- Automatically includes all workflow metadata

---

## PII Redaction

Protect sensitive data in traces with automatic PII scrubbing.

### Configuration

```yaml
telemetry:
  redact:
    tool_inputs: true      # Redact tool input parameters
    tool_outputs: true     # Redact tool response content
    custom_patterns:       # Custom regex patterns (optional)
      - "\\bAWSAccessKey=[A-Z0-9]{20}\\b"
      - "\\btoken=[a-zA-Z0-9_-]{40,}\\b"
```

### Built-in PII Patterns

Strands-cli automatically detects and redacts:

| Pattern | Regex | Example |
|---------|-------|---------|
| **Email** | `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z\|a-z]{2,}\b` | `user@example.com` → `***REDACTED***` |
| **Credit Card** | `\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b` | `4111-1111-1111-1111` → `***REDACTED***` |
| **SSN** | `\b\d{3}-\d{2}-\d{4}\b` | `123-45-6789` → `***REDACTED***` |
| **Phone** | `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` | `555-123-4567` → `***REDACTED***` |
| **API Key** | `\b[A-Za-z0-9_-]{20,}\b` | `sk_live_abc123...` → `***REDACTED***` |

### Custom Patterns

Add domain-specific patterns:

```yaml
telemetry:
  redact:
    tool_inputs: true
    tool_outputs: true
    custom_patterns:
      # AWS Access Key
      - "\\b(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\\b"
      # GitHub Token
      - "\\bghp_[A-Za-z0-9_]{36,}\\b"
      # Internal Employee ID
      - "\\bEMP-\\d{6}\\b"
```

### Redaction Metadata

Redacted attributes are tagged for audit:

```json
{
  "tool.input.api_key": "***REDACTED***",
  "redacted": true
}
```

### Audit Logging

Redaction events are logged for compliance:

```json
{
  "event": "pii_redaction",
  "timestamp": "2025-11-09T10:30:00.123Z",
  "redaction_count": 3,
  "patterns_matched": ["email", "api_key"],
  "attribute_names": ["tool.input.email", "tool.input.api_key", "tool.output.response"]
}
```

---

## Debug Logging

Enhanced debugging with `--debug` flag.

### Enable Debug Mode

```bash
uv run strands run workflow.yaml --debug
```

Sets:
- `STRANDS_DEBUG=true` environment variable
- Python logging level to `DEBUG`
- Structured JSON output via `structlog`

### Debug Output Includes

1. **Variable Resolution**
   ```json
   {"event": "parse_variables_start", "var_count": 2}
   {"event": "variable_parsed", "key": "topic", "value": "AI", "source": "cli_flag"}
   {"event": "variable_merge_complete", "cli_overrides": {"topic": "AI"}}
   ```

2. **Template Rendering**
   ```json
   {"event": "template_render_start", "template_preview": "{{ topic }}", "variable_keys": ["topic"]}
   {"event": "template_rendered", "rendered_preview": "AI ethics", "rendered_length": 9}
   ```

3. **Agent Cache**
   ```json
   {"event": "agent_cache_hit", "agent_id": "analyst", "cache_key": "analyst:openai:gpt-4o-mini"}
   {"event": "agent_cache_miss", "agent_id": "researcher", "building_new": true}
   ```

4. **LLM Requests**
   ```json
   {"event": "llm_request_start", "agent_name": "analyst", "model": "gpt-4o-mini", "input_length": 123}
   {"event": "llm_response_received", "response_length": 456, "tokens_used": 1234}
   ```

5. **Capability Checks**
   ```json
   {"event": "capability_check_start", "spec_name": "workflow", "pattern": "chain"}
   {"event": "capability_check_complete", "supported": true, "agents": 2, "issues": []}
   ```

### Combine with Verbose

```bash
uv run strands run workflow.yaml --debug --verbose
```

Enables both structured debug logs and Rich console progress output.

---

## OTLP Collectors

### Jaeger (Recommended for Local Development)

**Start Jaeger:**

```bash
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

**Access UI:** http://localhost:16686

**Configure Strands:**

```yaml
telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "my-workflow"
```

### Zipkin

**Start Zipkin:**

```bash
docker run -d --name zipkin \
  -p 9411:9411 \
  openzipkin/zipkin:latest
```

**Access UI:** http://localhost:9411

**Configure Strands:**

```yaml
telemetry:
  otel:
    endpoint: "http://localhost:9411/api/v2/spans"
    service_name: "my-workflow"
```

### Honeycomb (Production)

**Get API Key:** https://ui.honeycomb.io/account

**Configure Strands:**

```yaml
telemetry:
  otel:
    endpoint: "https://api.honeycomb.io/v1/traces"
    service_name: "my-workflow"
```

**Set API Key:**

```bash
export HONEYCOMB_API_KEY="your-api-key-here"
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=$HONEYCOMB_API_KEY"
```

### Custom OTLP Collector

Any OTLP-compatible collector works (OpenTelemetry Collector, Datadog, New Relic, etc.).

**Example OpenTelemetry Collector Config:**

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  logging:
    loglevel: debug
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging, jaeger]
```

---

## Troubleshooting

### OTLP Endpoint Unreachable

**Symptom:** Warning logs about failed OTLP export

**Solution:** Check collector is running:

```bash
# Jaeger
curl http://localhost:4318/v1/traces

# Zipkin
curl http://localhost:9411/api/v2/spans
```

**Fallback:** Strands-cli automatically falls back to Console exporter if OTLP fails.

### No Traces in UI

**Check:**

1. **Service name filter** - Match `telemetry.otel.service_name` in UI
2. **Time range** - Adjust UI time filter to include recent traces
3. **Sampling** - If `sample_ratio < 1.0`, traces may be sampled out

**Verify trace emission:**

```bash
# Use Console exporter to verify spans
uv run strands run workflow.yaml --debug
# Look for span JSON in logs
```

### Large Trace Files

**Symptom:** Trace JSON files >10MB or warning about span eviction

**Cause:** Long workflows exceeding the span collection limit (default: 1000 spans)

**Solutions:**

1. **Increase span limit** (for comprehensive traces):
   ```bash
   # Increase to 5000 spans for longer workflows
   export STRANDS_MAX_TRACE_SPANS=5000
   uv run strands run workflow.yaml --trace
   ```

2. **Check logs for eviction warnings:**
   ```bash
   # Look for span_evicted_fifo warnings
   uv run strands run workflow.yaml --debug | grep "span_evicted_fifo"
   ```

3. **Reduce sampling** (for production):
   ```yaml
   telemetry:
     otel:
       sample_ratio: 0.1  # 10% sampling
   ```

4. **Split long workflows** into smaller specs

**Note:** Evicted spans won't appear in trace artifacts. Monitor logs for `span_evicted_fifo` warnings and check the `evicted_count` field in trace metadata.

### Trace Artifact Empty or Incomplete

**Symptom:** `trace.json` has 0 spans or fewer spans than expected, or timeout warning displayed

**Causes & Solutions:**

1. **Flush timeout** - Slow OTLP collector or network
   ```bash
   # Check logs for: telemetry_flush_timeout
   # Look for the warning:
   # "⚠ Warning: Trace export timed out. Artifact may be incomplete."
   ```
   **Solution:** Check OTLP endpoint connectivity or increase timeout (future enhancement)

2. **Span eviction** - Workflow exceeded span limit
   ```bash
   # Check logs for: span_evicted_fifo
   export STRANDS_MAX_TRACE_SPANS=5000
   uv run strands run workflow.yaml --trace
   ```

3. **Telemetry not configured** - Missing `telemetry.otel` in spec
   ```yaml
   telemetry:
     otel:
       service_name: "my-workflow"
       sample_ratio: 1.0
   ```

### Over-Redaction

**Symptom:** Too much data redacted (e.g., legitimate numbers mistaken for credit cards)

**Solution:** Review `custom_patterns` and built-in patterns. Disable specific patterns if needed (requires code modification in `telemetry/redaction.py`).

### Debug Logs Too Verbose

**Solution:**

```bash
# Use --verbose without --debug for less output
uv run strands run workflow.yaml --verbose

# Or filter structlog output
uv run strands run workflow.yaml --debug 2>&1 | grep "event"
```

---

## Best Practices

### Production Deployments

1. **Reduce Sampling**
   ```yaml
   telemetry:
     otel:
       sample_ratio: 0.1  # 10% sampling
   ```

2. **Enable PII Redaction**
   ```yaml
   telemetry:
     redact:
       tool_inputs: true
       tool_outputs: true
   ```

3. **Use Remote Collector**
   - Don't rely on Console exporter
   - Configure OTLP endpoint (Honeycomb, Datadog, etc.)

4. **Monitor Trace Size**
   - Alert on traces >5MB
   - Consider workflow refactoring if too large

### Development Workflows

1. **Use `--trace` for Ad-Hoc Debugging**
   ```bash
   uv run strands run workflow.yaml --trace --debug
   ```

2. **Local Jaeger for Visualization**
   ```bash
   docker run -d --name jaeger -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest
   ```

3. **Combine `--debug` and `--verbose`**
   ```bash
   uv run strands run workflow.yaml --debug --verbose
   ```

### Security & Compliance

1. **Always Enable Redaction for Sensitive Workflows**
   ```yaml
   telemetry:
     redact:
       tool_inputs: true
       tool_outputs: true
   ```

2. **Audit Redaction Events**
   - Review structured logs for `pii_redaction` events
   - Ensure all sensitive data is caught

3. **Custom Patterns for Domain Secrets**
   ```yaml
   telemetry:
     redact:
       custom_patterns:
         - "\\bINTERNAL-API-KEY-[A-Z0-9]{32}\\b"
   ```

4. **Rotate OTLP Credentials Regularly**
   - Honeycomb API keys, Datadog API keys, etc.

### Performance Optimization

1. **Sampling in High-Volume Workflows**
   - Use `sample_ratio: 0.1` for workflows with >100 steps
   - Full sampling only for critical debugging

2. **Monitor OTLP Export Latency**
   - Check collector metrics for slow exports
   - Consider batch size tuning (advanced)

3. **Async OTLP Export**
   - Strands-cli uses non-blocking OTLP export (async)
   - No workflow slowdown from trace emission

---

## Examples

### Full Observability Workflow

```yaml
version: 0
name: "observable-research"
runtime:
  provider: openai
  model_id: "gpt-4o-mini"

telemetry:
  otel:
    endpoint: "http://localhost:4318/v1/traces"
    service_name: "research-workflow"
    sample_ratio: 1.0
  redact:
    tool_inputs: true
    tool_outputs: true

agents:
  researcher:
    prompt: "Research {{topic}}"
    tools:
      - python:
          - callable: "strands_tools.http_request.http_request"
  analyst:
    prompt: "Analyze the research findings"

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{topic}}"
      - agent: analyst
        input: "Analyze: {{ steps[0].response }}"

outputs:
  artifacts:
    - path: "./artifacts/analysis.md"
      from: "{{ last_response }}"
    - path: "./artifacts/trace.json"
      from: "{{ $TRACE }}"
```

**Run with debugging:**

```bash
uv run strands run observable-research.yaml --var topic="AI ethics" --debug
```

**View trace in Jaeger:** http://localhost:16686

---

## Additional Resources

- **OpenTelemetry Python Docs:** https://opentelemetry.io/docs/instrumentation/python/
- **OTLP Specification:** https://opentelemetry.io/docs/specs/otlp/
- **Jaeger Documentation:** https://www.jaegertracing.io/docs/
- **Honeycomb Guide:** https://docs.honeycomb.io/getting-data-in/opentelemetry/
- **Strands Workflow Manual:** `docs/strands-workflow-manual.md`

---

**End of Telemetry Guide**

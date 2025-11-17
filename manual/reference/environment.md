# Environment Variables Reference

Complete reference for all environment variables used by Strands CLI.

## Overview

Strands CLI uses environment variables for configuration management. All Strands-specific variables use the `STRANDS_` prefix, following Pydantic Settings conventions.

### Configuration Priority

Settings cascade in the following order (highest priority first):

1. Explicit command-line arguments
2. Environment variables (`STRANDS_*`)
3. `.env` file in current directory
4. Default values

### .env File Support

You can create a `.env` file in your project directory:

```bash
# .env
STRANDS_AWS_REGION=us-west-2
STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
STRANDS_LOG_LEVEL=DEBUG
```

---

## AWS Configuration

### `STRANDS_AWS_REGION`

**Type**: `string`
**Default**: `us-east-1`
**Description**: AWS region for Bedrock API calls

**Usage**:
```bash
export STRANDS_AWS_REGION=us-west-2
strands run workflow-bedrock.yaml
```

**Supported regions**: Any AWS region with Bedrock availability (e.g., `us-east-1`, `us-west-2`, `eu-west-1`)

---

### `STRANDS_AWS_PROFILE`

**Type**: `string`
**Default**: `None` (uses default profile)
**Description**: AWS CLI profile name for credentials

**Usage**:
```bash
export STRANDS_AWS_PROFILE=bedrock-dev
strands run workflow-bedrock.yaml
```

**Note**: If not set, uses AWS CLI default credentials chain (environment variables, `~/.aws/credentials`, IAM roles)

---

## Bedrock Configuration

### `STRANDS_BEDROCK_MODEL_ID`

**Type**: `string`
**Default**: `anthropic.claude-3-sonnet-20240229-v1:0`
**Description**: Default Bedrock model ID

**Usage**:
```bash
export STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
strands run workflow-bedrock.yaml
```

**Common values**:
- `anthropic.claude-3-opus-20240229-v1:0` - Claude 3 Opus (most capable)
- `anthropic.claude-3-sonnet-20240229-v1:0` - Claude 3 Sonnet (balanced)
- `anthropic.claude-3-haiku-20240307-v1:0` - Claude 3 Haiku (fastest)

---

## Workflow Configuration

### `STRANDS_WORKFLOW_SCHEMA_PATH`

**Type**: `path`
**Default**: `None` (uses bundled schema)
**Description**: Path to custom workflow JSON Schema file

**Usage**:
```bash
export STRANDS_WORKFLOW_SCHEMA_PATH=/path/to/custom-schema.json
strands validate workflow.yaml
```

**Note**: Only needed for custom schema validation. Default schema is bundled with the CLI.

---

## Cache Configuration

### `STRANDS_CACHE_ENABLED`

**Type**: `boolean`
**Default**: `true`
**Description**: Enable/disable agent caching

**Usage**:
```bash
export STRANDS_CACHE_ENABLED=false
strands run workflow.yaml
```

**Impact**: Disabling cache will rebuild agents for every step, increasing latency.

---

### `STRANDS_CACHE_DIR`

**Type**: `path`
**Default**: `None` (uses system default)
**Description**: Custom cache directory path

**Usage**:
```bash
export STRANDS_CACHE_DIR=/tmp/strands-cache
strands run workflow.yaml
```

---

## Observability

### `STRANDS_OTEL_ENABLED`

**Type**: `boolean`
**Default**: `false`
**Description**: Enable OpenTelemetry tracing

**Usage**:
```bash
export STRANDS_OTEL_ENABLED=true
export STRANDS_OTEL_ENDPOINT=http://localhost:4317
strands run workflow.yaml
```

**Note**: Requires `STRANDS_OTEL_ENDPOINT` to be set for OTLP export.

---

### `STRANDS_OTEL_ENDPOINT`

**Type**: `string`
**Default**: `None`
**Description**: OpenTelemetry collector endpoint (OTLP/gRPC)

**Usage**:
```bash
export STRANDS_OTEL_ENDPOINT=http://localhost:4317
strands run workflow.yaml --trace
```

**Common endpoints**:
- `http://localhost:4317` - Local OTLP collector (gRPC)
- `http://localhost:4318` - Local OTLP collector (HTTP)
- `https://api.honeycomb.io:443` - Honeycomb
- `https://otlp.nr-data.net:4317` - New Relic

---

## Logging

### `STRANDS_LOG_LEVEL`

**Type**: `string`
**Default**: `INFO`
**Description**: Logging verbosity level

**Usage**:
```bash
export STRANDS_LOG_LEVEL=DEBUG
strands run workflow.yaml
```

**Allowed values**:
- `DEBUG` - Verbose debugging output
- `INFO` - General information
- `WARNING` - Warning messages only
- `ERROR` - Error messages only
- `CRITICAL` - Critical errors only

---

### `STRANDS_LOG_FORMAT`

**Type**: `string`
**Default**: `console`
**Description**: Log output format

**Usage**:
```bash
export STRANDS_LOG_FORMAT=json
strands run workflow.yaml
```

**Allowed values**:
- `console` - Human-readable console output
- `json` - Structured JSON logs (for log aggregation)

---

## HTTP Security

### `STRANDS_HTTP_ALLOWED_DOMAINS`

**Type**: `list[string]` (comma-separated)
**Default**: `[]` (empty list)
**Description**: Allowed domain patterns for HTTP executor tools (regex)

**Usage**:
```bash
export STRANDS_HTTP_ALLOWED_DOMAINS="api\.github\.com,.*\.amazonaws\.com"
strands run workflow.yaml
```

**Example**:
```bash
# Allow only GitHub API and AWS domains
export STRANDS_HTTP_ALLOWED_DOMAINS="api\.github\.com,.*\.amazonaws\.com"
```

**Security**: When set, HTTP executors will only allow requests to matching domains.

---

### `STRANDS_HTTP_BLOCKED_PATTERNS`

**Type**: `list[string]` (comma-separated)
**Default**: `[]` (built-in SSRF protection patterns)
**Description**: Additional blocked URL patterns for HTTP executors (regex)

**Usage**:
```bash
export STRANDS_HTTP_BLOCKED_PATTERNS="169\.254\..*,10\..*"
strands run workflow.yaml
```

**Example**:
```bash
# Block internal IP ranges
export STRANDS_HTTP_BLOCKED_PATTERNS="169\.254\..*,10\..*,192\.168\..*"
```

**Security**: Adds extra protection beyond built-in SSRF prevention.

---

## Provider-Specific Variables

### OpenAI

#### `OPENAI_API_KEY`

**Type**: `string`
**Default**: `None` (required for OpenAI)
**Description**: OpenAI API key

**Usage**:
```bash
export OPENAI_API_KEY=sk-...
strands run workflow-openai.yaml
```

**Note**: This is an OpenAI SDK variable, not a Strands variable.

---

### Anthropic

#### `ANTHROPIC_API_KEY`

**Type**: `string`
**Default**: `None` (required for Anthropic provider)
**Description**: Anthropic API key for Claude models

**Usage**:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
strands run workflow-anthropic.yaml
```

**Requirements**:
- Install provider extra: `uv pip install -e ".[anthropic]"`
- Get API key from [Anthropic Console](https://console.anthropic.com/)

**Note**: This is an Anthropic SDK variable, not a Strands variable.

---

### Google Gemini

#### `GOOGLE_API_KEY` or `GEMINI_API_KEY`

**Type**: `string`
**Default**: `None` (required for Gemini provider)
**Description**: Google API key for Gemini models

**Usage**:
```bash
# Option 1: Standard Google API key name
export GOOGLE_API_KEY=AIza...
strands run workflow-gemini.yaml

# Option 2: Alternative Gemini-specific name
export GEMINI_API_KEY=AIza...
strands run workflow-gemini.yaml
```

**Requirements**:
- Install provider extra: `uv pip install -e ".[gemini]"`
- Get API key from [Google AI Studio](https://aistudio.google.com/apikey)

**Note**: Both environment variable names are supported. The provider checks `GOOGLE_API_KEY` first, then falls back to `GEMINI_API_KEY`.

---

## Telemetry Configuration

### `STRANDS_MAX_TRACE_SPANS`

**Type**: `integer`
**Default**: `1000`
**Description**: Maximum spans to include in trace artifacts

**Usage**:
```bash
export STRANDS_MAX_TRACE_SPANS=5000
strands run workflow.yaml --trace
```

**Note**: Prevents trace files from becoming too large in complex workflows.

---

## Debug Configuration

### `STRANDS_DEBUG`

**Type**: `boolean` (runtime environment variable)
**Default**: `false`
**Description**: Enable debug mode (equivalent to `--debug` flag)

**Usage**:
```bash
export STRANDS_DEBUG=true
strands run workflow.yaml
```

**Impact**: Enables verbose logging and additional diagnostics.

**Note**: This variable is checked at runtime in `__main__.py` and is **not** part of the Pydantic Settings configuration. It's primarily used for CLI debugging rather than application configuration.

---

### `STRANDS_VERBOSE`

**Type**: `boolean` (runtime environment variable)
**Default**: `false`
**Description**: Enable verbose output (equivalent to `--verbose` flag)

**Usage**:
```bash
export STRANDS_VERBOSE=true
strands run workflow.yaml
```

**Note**: This variable is checked at runtime in `__main__.py` and is **not** part of the Pydantic Settings configuration. Use the `--verbose` CLI flag for most use cases.

---

## Configuration Examples

### Development Environment

```bash
# .env
STRANDS_LOG_LEVEL=DEBUG
STRANDS_LOG_FORMAT=console
STRANDS_CACHE_ENABLED=true
STRANDS_OTEL_ENABLED=true
STRANDS_OTEL_ENDPOINT=http://localhost:4317
STRANDS_AWS_REGION=us-east-1
```

### Production Environment

```bash
# .env
STRANDS_LOG_LEVEL=INFO
STRANDS_LOG_FORMAT=json
STRANDS_CACHE_ENABLED=true
STRANDS_OTEL_ENABLED=true
STRANDS_OTEL_ENDPOINT=https://otlp.company.com:4317
STRANDS_AWS_REGION=us-west-2
STRANDS_AWS_PROFILE=production
STRANDS_HTTP_ALLOWED_DOMAINS="api\.company\.com,.*\.amazonaws\.com"
```

### CI/CD Environment

```bash
# GitHub Actions
STRANDS_LOG_LEVEL=INFO
STRANDS_LOG_FORMAT=json
STRANDS_CACHE_ENABLED=false
STRANDS_AWS_REGION=us-east-1
# AWS credentials via OIDC, not environment variables
```

---

## Verification

Check current configuration with the `doctor` command:

```bash
strands doctor
```

This will display:
- Active environment variable values
- Provider availability
- Configuration directory
- System diagnostics

---

## See Also

- [CLI Reference](cli.md) - Command-line interface
- [Configuration API](api/config.md) - Pydantic Settings models
- Tutorials: [Quickstart](../tutorials/quickstart-ollama.md)

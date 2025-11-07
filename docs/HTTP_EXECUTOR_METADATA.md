# HTTP Executor Metadata Enhancement

## Overview

HTTP executors can now be adorned with rich metadata that helps LLM agents understand and use API tools more effectively. This metadata is embedded in the `TOOL_SPEC` description, providing agents with contextual guidance about:

- What the API does and when to use it
- Available endpoints and their purposes
- Expected request/response formats
- Authentication requirements
- Usage examples

## Metadata Fields

### Core Fields (Required)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Unique identifier for the HTTP executor |
| `base_url` | `string` | Base URL for all API requests (validated for SSRF prevention) |

### Optional Metadata Fields

| Field | Type | Description | Impact on Agent Behavior |
|-------|------|-------------|--------------------------|
| `description` | `string` | Human-readable description of what this API does and when to use it | Helps agent decide when to invoke this tool vs others |
| `response_format` | `string` | Expected format (e.g., "JSON", "XML", "plain text") | Guides agent's response parsing expectations |
| `authentication_info` | `string` | Information about auth requirements (for documentation, not credentials) | Helps agent understand access patterns and requirements |
| `common_endpoints` | `array[object]` | List of available endpoints with descriptions | Guides agent to correct endpoints for specific tasks |
| `examples` | `array[object]` | Example requests showing proper usage | Provides concrete patterns for agent to follow |

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `headers` | `object` | `null` | Default headers (supports `${SECRET}` placeholders) |
| `timeout` | `integer` | `30` | Request timeout in seconds |

## Example: Basic HTTP Executor

```yaml
tools:
  http_executors:
    - id: simple_api
      base_url: https://api.example.com
      headers:
        Accept: application/json
```

**Generated TOOL_SPEC:**
```json
{
  "name": "simple_api",
  "description": "HTTP executor for https://api.example.com",
  "inputSchema": { ... }
}
```

## Example: Enhanced HTTP Executor with Metadata

```yaml
tools:
  http_executors:
    - id: gh
      base_url: https://api.github.com
      headers:
        Authorization: "Bearer ${GITHUB_TOKEN}"
        Accept: "application/vnd.github+json"
      
      # Rich metadata for agent guidance
      description: |
        GitHub REST API client for fetching repository information, user profiles, 
        issues, pull requests, and other GitHub data. Use this tool to interact 
        with any public or accessible private repositories.
      
      response_format: JSON
      
      authentication_info: |
        Requires GitHub Personal Access Token (PAT) in Authorization header. 
        Token must have appropriate scopes for the requested resources.
      
      # Guide agent to correct endpoints
      common_endpoints:
        - method: GET
          path: /repos/{owner}/{repo}
          description: Get repository information
        
        - method: GET
          path: /repos/{owner}/{repo}/issues
          description: List repository issues
        
        - method: GET
          path: /users/{username}
          description: Get user profile information
      
      # Show agent how to construct requests
      examples:
        - description: Fetch repository information
          method: GET
          path: /repos/octocat/Hello-World
        
        - description: List open bug issues
          method: GET
          path: /repos/octocat/Hello-World/issues?state=open&labels=bug
```

**Generated TOOL_SPEC:**
```json
{
  "name": "gh",
  "description": "GitHub REST API client for fetching repository information, user profiles, 
issues, pull requests, and other GitHub data. Use this tool to interact 
with any public or accessible private repositories.

Authentication: Requires GitHub Personal Access Token (PAT) in Authorization header. 
Token must have appropriate scopes for the requested resources.

Response format: JSON

Common endpoints:
- GET /repos/{owner}/{repo}: Get repository information
- GET /repos/{owner}/{repo}/issues: List repository issues
- GET /users/{username}: Get user profile information

Examples:
1. Fetch repository information
   Method: GET, Path: /repos/octocat/Hello-World
2. List open bug issues
   Method: GET, Path: /repos/octocat/Hello-World/issues?state=open&labels=bug",
  "inputSchema": { ... }
}
```

## Common Endpoints Schema

```yaml
common_endpoints:
  - method: GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS  # HTTP method
    path: /path/to/endpoint                          # Path template (use {param} for variables)
    description: What this endpoint does             # Human-readable description
```

**Best Practices:**
- Use path templates with `{param}` notation for variable segments
- Include most frequently used endpoints (3-10 is optimal)
- Order by importance/usage frequency
- Provide clear, concise descriptions

## Examples Schema

```yaml
examples:
  - description: What this example demonstrates  # Required
    method: GET                                  # HTTP method
    path: /actual/path                          # Actual path (not template)
    json_data:                                  # Optional: request body
      key: value
```

**Best Practices:**
- Show 2-5 representative examples
- Include simple and complex use cases
- Use real, working examples when possible
- Demonstrate common patterns (filtering, pagination, etc.)

## Benefits

### Agent Performance Improvements

1. **Reduced Trial-and-Error**: Agent knows available endpoints upfront
2. **Better Tool Selection**: Rich descriptions help agent choose right tool for task
3. **Correct Request Construction**: Examples show proper path/parameter patterns
4. **Comprehensive Responses**: Agent makes multiple related calls when it knows available endpoints

### Example: Impact on Agent Behavior

**Without Metadata (Basic):**
```yaml
- id: gh
  base_url: https://api.github.com
```
Agent response: Makes 1-2 calls to basic repository endpoint, provides minimal info.

**With Metadata (Enhanced):**
```yaml
- id: gh
  base_url: https://api.github.com
  description: GitHub REST API client...
  common_endpoints: [...]
  examples: [...]
```
Agent response: Makes 7+ calls to multiple endpoints (repo, issues, contributors, languages, README), provides comprehensive analysis.

## Implementation Details

### How Metadata is Used

1. **Load Time**: YAML/JSON → Pydantic `HttpExecutor` model validates metadata
2. **Tool Creation**: `_build_tool_description()` formats metadata into rich description
3. **Agent Invocation**: LLM receives enriched TOOL_SPEC with all guidance
4. **Runtime**: Agent makes informed decisions based on metadata context

### Secret Resolution

Metadata supports secret placeholders in headers:

```yaml
headers:
  Authorization: "Bearer ${GITHUB_TOKEN}"

env:
  secrets:
    - name: GITHUB_TOKEN
      source: env
      key: MY_GITHUB_PAT
```

Secrets are resolved before creating the HTTP client, ensuring credentials are never exposed in metadata.

## Validation

Metadata fields are validated via JSON Schema (`strands-workflow.schema.json`) and Pydantic models (`types.HttpExecutor`).

**Schema Validation Rules:**
- All metadata fields are optional
- `common_endpoints` requires `path` and `description`
- `examples` can include any combination of `description`, `method`, `path`, `json_data`
- Arrays can be empty but must be valid JSON arrays if provided

## Testing

Validate your HTTP executor configuration:

```bash
uv run strands validate path/to/workflow.yaml
```

Test with actual execution:

```bash
uv run strands run path/to/workflow.yaml --var key=value
```

## Migration Guide

### Upgrading Existing HTTP Executors

1. **Identify APIs**: Review your HTTP executors and identify which would benefit from metadata
2. **Add Description**: Start with clear `description` field explaining the API
3. **Document Endpoints**: Add `common_endpoints` for frequently used paths
4. **Add Examples**: Include 2-3 `examples` showing typical usage patterns
5. **Test**: Validate and run to verify agent improvements

### Minimal Enhancement

For quick improvement, add just the description:

```yaml
tools:
  http_executors:
    - id: my_api
      base_url: https://api.example.com
      description: |
        Brief description of what this API does and when to use it.
        Include key capabilities and common use cases.
```

### Full Enhancement

For maximum agent effectiveness, include all metadata:

```yaml
tools:
  http_executors:
    - id: my_api
      base_url: https://api.example.com
      description: Detailed API description...
      response_format: JSON
      authentication_info: Auth requirements...
      common_endpoints: [...]
      examples: [...]
```

## Best Practices

### Writing Effective Descriptions

✅ **Good:**
```yaml
description: |
  Stripe Payment API for processing payments, managing subscriptions, 
  and handling customer billing. Use for payment processing, subscription 
  management, and invoice generation.
```

❌ **Poor:**
```yaml
description: API for payments
```

### Choosing Common Endpoints

✅ **Good:** Include 5-7 most frequently used endpoints with clear descriptions
```yaml
common_endpoints:
  - method: POST
    path: /v1/payment_intents
    description: Create a new payment intent for card transactions
  - method: GET
    path: /v1/customers/{customer_id}
    description: Retrieve customer details and payment methods
```

❌ **Poor:** Include all 50+ endpoints or only 1 endpoint

### Creating Useful Examples

✅ **Good:** Show real-world usage patterns
```yaml
examples:
  - description: Create customer and subscribe to monthly plan
    method: POST
    path: /v1/subscriptions
    json_data:
      customer: cus_123
      items: [{price: price_monthly}]
```

❌ **Poor:** Generic placeholder examples
```yaml
examples:
  - description: Example
    method: GET
    path: /endpoint
```

## Future Enhancements

Potential future additions to HTTP executor metadata:

- **Rate limiting hints**: Help agent respect API rate limits
- **Pagination patterns**: Automatic handling of paginated responses
- **Error handling**: Expected error codes and retry strategies
- **Response schemas**: Structured schemas for response validation
- **Dependent requests**: Chains of requests that depend on each other

## See Also

- [Secrets Documentation](../docs/security.md) - How to manage API credentials
- [Tool Development Guide](../docs/TOOL_DEVELOPMENT.md) - Creating native tools
- [HTTP Executor Examples](../examples/) - Working examples with metadata

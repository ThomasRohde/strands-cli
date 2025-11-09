# How to Work with Tools

This guide shows you how to use tools in Strands workflows, including HTTP executors, Python tools, and file operations.

## Tool Types

Strands supports three types of tools:

1. **Python Tools** - Native Python functions (allowlisted)
2. **HTTP Executors** - REST API integrations
3. **MCP Servers** - Model Context Protocol integrations

## Python Tools

### Allowlisted Python Tools

For security, only allowlisted Python callables can be used:

**Legacy Tools:**
- `strands_tools.http_request` - Make HTTP requests
- `strands_tools.file_read` - Read files (with consent)
- `strands_tools.file_write` - Write files (with consent)

**Native Tools (auto-discovered):**
- `python_exec` - Execute Python code in sandbox
- Plus any custom tools in `src/strands_cli/tools/`

### Using Python Tools

```yaml
version: 0
name: python-tools-demo
runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  coder:
    prompt: "You write and execute Python code to solve problems."

tools:
  python:
    - python_exec
    - strands_tools.http_request

pattern:
  type: chain
  config:
    steps:
      - agent_id: coder
        prompt: "Calculate the first 10 Fibonacci numbers using Python"
```

### Python Execution Tool

The `python_exec` tool runs Python code in a controlled environment:

```yaml
tools:
  python:
    - python_exec
```

Agent can request code execution:

```python
# Agent provides this as tool input
{
  "code": "result = sum(range(1, 101))\nprint(result)",
  "timeout": 5
}

# Tool returns
{
  "stdout": "5050",
  "stderr": "",
  "exit_code": 0
}
```

**Security**: Code runs in subprocess with timeout and no network access.

### File Operations

Read files with consent:

```yaml
tools:
  python:
    - strands_tools.file_read

env:
  filesystem:
    read_paths:
      - path: ./data
        consent: true
      - path: ./config.yaml
        consent: true
```

Write files with consent:

```yaml
tools:
  python:
    - strands_tools.file_write

env:
  filesystem:
    write_paths:
      - path: ./output
        consent: true
```

## HTTP Executors

### Basic HTTP Tool

Make REST API calls:

```yaml
version: 0
name: http-demo
runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  researcher:
    prompt: "You research information using APIs."

tools:
  http_executors:
    - id: github_api
      base_url: https://api.github.com
      description: "GitHub REST API"
      endpoints:
        - path: /repos/{owner}/{repo}
          method: GET
          description: "Get repository information"

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Get info about the tensorflow/tensorflow repository"
```

### HTTP Executor Configuration

```yaml
tools:
  http_executors:
    - id: my_api
      base_url: https://api.example.com
      description: "Example API"
      
      # Optional: Headers
      headers:
        Accept: application/json
        User-Agent: Strands-CLI/0.11.0
      
      # Optional: Authentication
      auth:
        type: bearer
        token: "{{ secrets.api_token }}"
      
      # Endpoints
      endpoints:
        - path: /users/{id}
          method: GET
          description: "Get user by ID"
          
        - path: /users
          method: POST
          description: "Create new user"
          body_schema:
            type: object
            properties:
              name:
                type: string
              email:
                type: string
```

### Authentication Types

**Bearer Token:**

```yaml
tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      auth:
        type: bearer
        token: "{{ secrets.api_token }}"
```

**Basic Auth:**

```yaml
tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      auth:
        type: basic
        username: "{{ secrets.api_user }}"
        password: "{{ secrets.api_pass }}"
```

**API Key:**

```yaml
tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      headers:
        X-API-Key: "{{ secrets.api_key }}"
```

### Path Parameters

Use `{param}` syntax for dynamic paths:

```yaml
tools:
  http_executors:
    - id: github
      base_url: https://api.github.com
      endpoints:
        - path: /repos/{owner}/{repo}/issues/{issue_number}
          method: GET
          description: "Get issue details"
```

Agent provides parameters:

```json
{
  "owner": "tensorflow",
  "repo": "tensorflow",
  "issue_number": 12345
}
```

### Request Bodies

Define schema for POST/PUT requests:

```yaml
tools:
  http_executors:
    - id: api
      base_url: https://api.example.com
      endpoints:
        - path: /comments
          method: POST
          description: "Create comment"
          body_schema:
            type: object
            properties:
              text:
                type: string
                description: "Comment text"
              author:
                type: string
                description: "Author name"
            required: [text, author]
```

## MCP Server Integration

### Enable MCP Servers

Use Model Context Protocol servers:

```yaml
version: 0
name: mcp-demo
runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  analyst:
    prompt: "You analyze files using MCP tools."

tools:
  mcp_servers:
    filesystem:
      command: npx
      args:
        - -y
        - "@modelcontextprotocol/server-filesystem"
        - /path/to/allowed/directory

pattern:
  type: chain
  config:
    steps:
      - agent_id: analyst
        prompt: "List files in the directory and read README.md"
```

### Multiple MCP Servers

```yaml
tools:
  mcp_servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "./data"]
    
    sqlite:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-sqlite", "./db.sqlite"]
    
    github:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: "{{ secrets.github_token }}"
```

### MCP Tool Usage

MCP servers expose tools that agents can call:

```yaml
# MCP filesystem server provides:
# - read_file(path)
# - write_file(path, content)
# - list_directory(path)
# - search_files(pattern)

# Agent can use these tools automatically
pattern:
  type: chain
  config:
    steps:
      - agent_id: analyst
        prompt: |
          Read the file 'config.yaml' and analyze its structure.
          List all JSON files in the current directory.
```

## Tool Security

### Allowlisting

Only allowlisted Python callables are permitted:

```python
# Allowed (built-in)
- python_exec
- strands_tools.http_request
- strands_tools.file_read
- strands_tools.file_write

# Not allowed (will fail validation)
- os.system
- subprocess.run
- eval
- exec
```

### File Access Control

Require explicit consent for file operations:

```yaml
env:
  filesystem:
    read_paths:
      - path: ./data
        consent: true  # Explicit consent required
    
    write_paths:
      - path: ./output
        consent: true
```

### HTTP Security

**SSRF Prevention**: HTTP executors validate URLs against:
- No private IP ranges (10.x, 192.168.x, 127.x)
- No file:// or other dangerous schemes
- Only http:// and https:// allowed

**Path Traversal Prevention**: Paths are sanitized to prevent `../` attacks.

## Common Patterns

### API Integration

```yaml
tools:
  http_executors:
    - id: weather_api
      base_url: https://api.weather.com
      headers:
        X-API-Key: "{{ secrets.weather_key }}"
      endpoints:
        - path: /current/{city}
          method: GET
          description: "Get current weather"

pattern:
  type: chain
  config:
    steps:
      - agent_id: assistant
        prompt: "What's the weather in {{ city }}?"
```

### File Analysis

```yaml
tools:
  python:
    - strands_tools.file_read

env:
  filesystem:
    read_paths:
      - path: ./logs
        consent: true

pattern:
  type: chain
  config:
    steps:
      - agent_id: analyst
        prompt: "Read error.log and summarize the errors"
```

### Code Execution

```yaml
tools:
  python:
    - python_exec

pattern:
  type: chain
  config:
    steps:
      - agent_id: coder
        prompt: |
          Write Python code to:
          1. Generate 100 random numbers
          2. Calculate mean and standard deviation
          3. Print results
```

### Multi-Tool Workflow

```yaml
tools:
  python:
    - python_exec
    - strands_tools.http_request
  
  http_executors:
    - id: github_api
      base_url: https://api.github.com
      endpoints:
        - path: /repos/{owner}/{repo}
          method: GET

pattern:
  type: chain
  config:
    steps:
      - agent_id: researcher
        prompt: "Fetch tensorflow repo info from GitHub"
      
      - agent_id: analyst
        prompt: |
          Analyze this data using Python:
          {{ steps[0].response }}
          
          Calculate repository age in days.
```

## Tool Override per Agent

Override tools for specific agents:

```yaml
agents:
  analyst:
    prompt: "You analyze data"
    tools:
      - python_exec  # Only this tool for this agent

  researcher:
    prompt: "You research information"
    tools:
      - strands_tools.http_request

# Global tools (used by agents without tool overrides)
tools:
  python:
    - python_exec
    - strands_tools.file_read
```

## Developing Custom Native Tools

Create new tools in `src/strands_cli/tools/`:

```python
# src/strands_cli/tools/my_tool.py
from typing import Any

TOOL_SPEC = {
    "name": "my_tool",
    "description": "Does something useful",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "Parameter description"
                }
            },
            "required": ["param"]
        }
    }
}

def my_tool(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    param = tool_input.get("param", "")
    
    # Process...
    result = f"Processed: {param}"
    
    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"text": result}]
    }
```

Tool is auto-discovered and available as `my_tool` in workflows.

See [Tool Development Guide](../../docs/TOOL_DEVELOPMENT.md) for complete documentation.

## Troubleshooting

### Tool Not Found

**Error**: `Tool 'my_tool' not in allowlist`

**Fix**: Ensure tool is:
1. In allowlist (legacy tools or native tools with TOOL_SPEC)
2. Correctly referenced in workflow (check spelling)
3. Exported with TOOL_SPEC (for native tools)

### HTTP Executor Fails

**Error**: `HTTP request failed: 403 Forbidden`

**Fix**: Check:
1. Authentication credentials are correct
2. Headers are properly configured
3. Endpoint path matches API documentation
4. Base URL is correct (no trailing slash issues)

### MCP Server Won't Start

**Error**: `Failed to start MCP server: command not found`

**Fix**:
1. Ensure command is installed (`npx`, `python`, etc.)
2. Check MCP server package is available
3. Verify environment variables are set
4. Check file paths are absolute

### File Access Denied

**Error**: `File access denied: ./data/file.txt`

**Fix**: Add explicit consent:

```yaml
env:
  filesystem:
    read_paths:
      - path: ./data
        consent: true
```

## See Also

- [Tool Development Guide](../../docs/TOOL_DEVELOPMENT.md)
- [Security Model](../explanation/security-model.md)
- [Secrets Management](secrets.md)
- [Schema Reference: Tools](../reference/schema.md#tools)

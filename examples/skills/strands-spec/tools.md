# Tool Configuration Guide

Complete reference for configuring and using tools in strands-cli workflows.

## Tool Types

1. **Native Tools**: Built into strands-cli (`python_exec`, `http_request`, `grep`, `notes`)
2. **Custom Tools**: Python callables defined in spec
3. **MCP Servers**: Model Context Protocol servers (future)
4. **Skill Loader**: Auto-injected when skills are defined

## Native Tools Quick Reference

Strands-cli includes **14 native tools** discoverable via auto-registration. Use `uv run strands list-tools` to see all available tools.

### Core Tools

**python_exec** - Execute Python code
```yaml
agents:
  data-analyst:
    prompt: "Analyze data and generate charts"
    tools: ["python_exec"]
```

**What it can do:**
- Data processing with pandas, numpy
- Mathematical computations
- JSON/CSV parsing
- Basic file operations

**Security:**
- Restricted builtins (MVP implementation)
- Import restrictions

**http_request** - Make HTTP requests
```yaml
agents:
  api-client:
    prompt: "Fetch data from API"
    tools: ["http_request"]
```

Supports: GET, POST, PUT, DELETE with headers and body

### File Tools

**file_read** - Read file contents
```yaml
tools: ["file_read"]
```

**file_write** - Write contents to file
```yaml
tools: ["file_write"]
```

**head** - Read first N lines from file
```yaml
tools: ["head"]
```
Useful for previewing files without loading entirely

**tail** - Read last N lines from file
```yaml
tools: ["tail"]
```
Useful for reading recent log entries

### Search Tools

**grep** - Search with regex patterns and context
```yaml
agents:
  code-searcher:
    prompt: "Find all function definitions"
    tools: ["grep"]
```
Returns matching lines with context (cross-platform pure Python)

**search** - Simple keyword/regex search
```yaml
tools: ["search"]
```
Returns direct matches with line numbers (simpler than grep)

### Web Tools

**web_fetch** - Fetch static web pages
```yaml
tools: ["web_fetch"]
```
Optionally converts content to markdown

**duckduckgo_search** - DuckDuckGo search
```yaml
tools: ["duckduckgo_search"]
```
Search for text results or news with automatic fallback

**tavily_search** - AI-powered web search
```yaml
tools: ["tavily_search"]
```
Requires `TAVILY_API_KEY` environment variable
Returns results with relevance scores and optional AI answers

### Utility Tools

**calculator** - Basic mathematical calculations
```yaml
tools: ["calculator"]
```
Supports: addition, subtraction, multiplication, division, exponentiation

**current_time** - Get current date/time
```yaml
tools: ["current_time"]
```
Supports various formats and timezones

**spec_verify** - Validate workflow specs ⭐ **Critical for spec generation!**
```yaml
tools: ["spec_verify"]
```

**Programmatically validates specs** and returns structured reports. Essential for agents building workflow specs.

**Input:**
```json
{
  "spec_content": "<YAML or JSON string>",
  "check_capability": true  // Optional: check MVP compatibility (default: true)
}
```

**Output (success):**
```json
{
  "schema_valid": true,
  "pydantic_valid": true,
  "capability_supported": true,
  "errors": [],
  "issues": [],
  "spec_info": {
    "name": "my-workflow",
    "version": "1.0.0",
    "pattern_type": "chain",
    "provider": "bedrock",
    "agent_count": 2
  }
}
```

**Output (validation errors):**
```json
{
  "schema_valid": false,
  "pydantic_valid": false,
  "errors": [
    {
      "phase": "schema",
      "type": "SchemaValidationError",
      "message": "Property 'version' is required",
      "validation_errors": [...]
    }
  ]
}
```

**Usage pattern:** Iteratively refine specs until both `schema_valid` and `pydantic_valid` are true.

**Example agent workflow:**
1. Generate initial spec
2. Call spec_verify with spec_content
3. If errors, analyze and fix
4. Repeat until valid

## Custom Python Tools

Define tools inline in the spec:

```yaml
tools:
  - name: database_query
    type: python_callable
    description: "Query PostgreSQL database"
    input_schema:
      type: object
      properties:
        query:
          type: string
          description: "SQL query to execute"
        params:
          type: array
          description: "Query parameters"
      required: [query]
    implementation: |
      import psycopg2
      
      def database_query(tool_input):
          query = tool_input.get("query")
          params = tool_input.get("params", [])
          
          conn = psycopg2.connect(os.environ["DATABASE_URL"])
          cursor = conn.cursor()
          cursor.execute(query, params)
          results = cursor.fetchall()
          conn.close()
          
          return {
              "status": "success",
              "results": results
          }
      
      return database_query(tool_input)

agents:
  data-analyst:
    tools: ["database_query"]
```

**Custom Tool Structure:**
- `name`: Unique tool identifier
- `type`: `python_callable`
- `description`: What the tool does (shown to agent)
- `input_schema`: JSON Schema for tool input validation
- `implementation`: Python code (must return dict with `status` and result data)

## Tool Input Schemas

Use JSON Schema to validate tool inputs:

```yaml
input_schema:
  type: object
  properties:
    query:
      type: string
      description: "Search query"
      minLength: 1
    limit:
      type: integer
      description: "Max results"
      minimum: 1
      maximum: 100
      default: 10
    filters:
      type: array
      items:
        type: string
      description: "Filter criteria"
  required: [query]
```

**Schema validation:**
- Validates before tool execution
- Provides clear error messages to agent
- Supports defaults and constraints

## Skill Loader Tool

**Note:** The skill_loader tool is auto-injected when `skills` are defined in the spec, but is NOT listed in the tool registry (no TOOL_SPEC export).

```yaml
skills:
  - id: data-science
    path: ./skills/data-science
    description: "Advanced data analysis techniques"

agents:
  analyst:
    prompt: |
      When you need data science expertise, load the skill:
      Skill("data-science")
```

**How it works:**
1. Skill metadata in system prompt (ID + description)
2. Agent calls `Skill("skill-id")` when needed
3. Full skill content loaded into context
4. Subsequent prompts have skill knowledge

**Best practices:**
- Load skills only when needed (progressive loading)
- Keep skill files focused (< 2000 lines)
- Avoid loading multiple large skills simultaneously

## Complete Native Tools List

Use `uv run strands list-tools` to see the current list:

1. **calculator** - Basic math operations
2. **current_time** - Date/time in various formats
3. **duckduckgo_search** - Web search with fallback
4. **file_read** - Read file contents
5. **file_write** - Write file contents
6. **grep** - Regex search with context
7. **head** - First N lines of file
8. **http_request** - HTTP GET/POST/PUT/DELETE
9. **python_exec** - Execute Python code
10. **search** - Simple keyword search
11. **spec_verify** - Validate workflow specs
12. **tail** - Last N lines of file
13. **tavily_search** - AI-powered web search (requires API key)
14. **web_fetch** - Fetch and convert web pages

## Tool Execution Flow

```
1. Agent decides to use tool
2. Agent generates tool call with input
3. Strands validates input against schema
4. Tool executes with validated input
5. Tool returns result to agent
6. Agent continues with result
```

## Error Handling

Tools should return structured errors:

```python
try:
    result = perform_operation()
    return {
        "status": "success",
        "data": result
    }
except ValueError as e:
    return {
        "status": "error",
        "error_type": "validation_error",
        "message": str(e)
    }
except Exception as e:
    return {
        "status": "error",
        "error_type": "unknown_error",
        "message": str(e)
    }
```

## Tool Configuration per Agent

Override tool config at agent level:

```yaml
tools:
  - type: http_request
    name: api-client
    config:
      allowlist: ["*.example.com"]

agents:
  public-api-agent:
    tools:
      - type: http_request
        config:
          allowlist: ["api.public-data.org"]  # Override for this agent
          
  internal-api-agent:
    tools: ["api-client"]  # Use global config
```

## Tool Access Control

Restrict tools per agent:

```yaml
agents:
  safe-agent:
    tools: ["grep", "notes"]  # Read-only tools
    
  power-agent:
    tools: ["python_exec", "http_request"]  # Execution tools
    
  no-tools-agent:
    tools: []  # No tools allowed
```

## Testing Tools

Test custom tools before deployment:

```python
# test_tools.py
import json

def test_database_query():
    tool_input = {
        "query": "SELECT * FROM users LIMIT 5",
        "params": []
    }
    
    result = database_query(tool_input)
    
    assert result["status"] == "success"
    assert len(result["results"]) <= 5
```

## Common Tool Patterns

### Data Fetcher + Processor

```yaml
agents:
  fetcher:
    tools: ["http_request"]
    prompt: "Fetch data from {{ api_url }}"
    
  processor:
    tools: ["python_exec"]
    prompt: |
      Process data: {{ steps[0].response }}
      Calculate statistics and save to CSV.
```

### Research + Code Generation

```yaml
agents:
  researcher:
    tools: ["http_request", "grep"]
    prompt: "Research best practices for {{ topic }}"
    
  coder:
    tools: ["python_exec"]
    prompt: |
      Based on research: {{ steps[0].response }}
      Generate production-ready code.
```

### Multi-Tool Analysis

```yaml
agents:
  analyst:
    tools: ["python_exec", "http_request", "notes"]
    prompt: |
      1. Fetch data from API
      2. Analyze with Python
      3. Save findings to notes
      4. Generate report
```

## Tool Security Best Practices

1. **Principle of Least Privilege**: Only grant tools agents need
2. **Input Validation**: Use strict JSON schemas
3. **Network Isolation**: Use allowlists for HTTP requests
4. **File System Limits**: Restrict python_exec to safe directories
5. **Audit Logging**: Enable telemetry for tool usage tracking

## Debugging Tool Issues

### Tool not found
```yaml
# Error: Tool 'my_tool' not found
agents:
  agent-a:
    tools: ["my_tool"]  # Typo or not defined

# Fix: Define tool or use correct name
tools:
  - name: my_tool
    type: python_callable
    # ...
```

### Input validation failure
```yaml
# Error: Input missing required property 'query'

# Fix: Check input_schema matches agent's tool call
input_schema:
  required: [query]  # Ensure agent provides this
```

### Execution timeout
```yaml
# Fix: Increase timeout or optimize tool code
tools:
  - type: http_request
    config:
      timeout: 60  # Increase from default 30
```

## Advanced: Tool Chaining

Tools can call other tools (via agent multi-turn):

```yaml
agents:
  orchestrator:
    tools: ["http_request", "python_exec"]
    prompt: |
      1. Fetch data using http_request
      2. Process results using python_exec
      3. Return final analysis
```

Agent will automatically chain tool calls as needed.

# Troubleshooting Guide

Comprehensive debugging guide for strands-cli workflows.

## Common Validation Errors

### Schema Validation Failures

#### Error: "Property 'version' is required"
```
ValidationError at $: Required property 'version' missing
```

**Cause:** Missing top-level `version` field  
**Fix:**
```yaml
version: 0  # Add this at the top
name: "my-workflow"
# ...
```

---

#### Error: "Invalid pattern type"
```
ValidationError at $.pattern.type: Value must be one of: chain, routing, parallel, workflow, graph, evaluator-optimizer, orchestrator-workers
```

**Cause:** Typo or unsupported pattern type  
**Fix:** Use exact pattern name from supported list
```yaml
pattern:
  type: chain  # NOT: sequential, steps, etc.
```

---

#### Error: "Agent 'xyz' not found"
```
ValidationError at $.pattern.config.steps[0].agent: Agent 'researcher' not defined in agents
```

**Cause:** Referenced agent doesn't exist in `agents:` section  
**Fix:** Define the agent or fix the reference
```yaml
agents:
  researcher:  # Must match exactly
    prompt: "..."

pattern:
  type: chain
  config:
    steps:
      - agent: researcher  # Must match agent name
```

---

#### Error: "Additional properties not allowed"
```
ValidationError at $.runtime: Additional property 'model' not allowed
```

**Cause:** Using wrong property name (often typos)  
**Fix:** Use correct schema property
```yaml
runtime:
  model_id: "..."  # NOT: model, model_name, etc.
  provider: "bedrock"
  region: "us-east-1"
```

---

#### Error: "Invalid provider"
```
ValidationError at $.runtime.provider: Value must be one of: bedrock, openai, ollama
```

**Cause:** Unsupported or misspelled provider  
**Fix:** Use supported provider
```yaml
runtime:
  provider: bedrock  # NOT: aws, anthropic, claude, etc.
```

---

## Runtime Errors

### Provider Configuration Issues

#### Error: "AWS credentials not found"
```
RuntimeError: Unable to locate credentials for Bedrock
```

**Cause:** Missing AWS credentials  
**Fix:** Configure AWS credentials
```bash
# Option 1: AWS CLI
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

# Option 3: IAM role (when running on AWS)
# No configuration needed
```

---

#### Error: "OpenAI API key not found"
```
RuntimeError: OPENAI_API_KEY environment variable not set
```

**Cause:** Missing OpenAI API key  
**Fix:**
```bash
export OPENAI_API_KEY=sk-...

# Or in workflow spec (not recommended):
env:
  secrets:
    - name: OPENAI_API_KEY
      source: env
```

---

#### Error: "Failed to connect to Ollama"
```
RuntimeError: Connection refused to http://localhost:11434
```

**Cause:** Ollama server not running  
**Fix:**
```bash
# Start Ollama server
ollama serve

# Or use custom host in spec:
runtime:
  provider: ollama
  host: "http://192.168.1.100:11434"
```

---

#### Error: "Model not found"
```
RuntimeError: Model 'claude-3-opus' not found in region us-east-1
```

**Cause:** Model ID doesn't exist or wrong region  
**Fix:** Use correct model ID for provider
```yaml
# Bedrock
runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"  # Full ARN
  region: "us-east-1"

# OpenAI
runtime:
  provider: openai
  model_id: "gpt-4o-mini"  # Simple name

# Ollama
runtime:
  provider: ollama
  model_id: "llama3"  # Model pulled with `ollama pull`
```

---

### Budget and Timeout Errors

#### Error: "Token budget exceeded"
```
BudgetExceeded: Workflow exceeded max_tokens budget (100000)
Current usage: 102350 tokens
```

**Cause:** Workflow consumed more tokens than budgeted  
**Fix:** Increase budget or optimize workflow
```yaml
runtime:
  budgets:
    max_tokens: 200000  # Increase budget

# OR optimize agents
agents:
  researcher:
    runtime:
      max_tokens: 1000  # Limit per-agent tokens
```

---

#### Error: "Workflow timeout"
```
TimeoutError: Workflow exceeded max_duration_s (600 seconds)
```

**Cause:** Workflow took longer than timeout  
**Fix:**
```yaml
runtime:
  budgets:
    max_duration_s: 1200  # Increase timeout

  failure_policy:
    retries: 2  # Reduce retries if needed
```

---

#### Error: "Max steps exceeded"
```
BudgetExceeded: Workflow exceeded max_steps budget (50)
```

**Cause:** Too many agent invocations (common in loops)  
**Fix:**
```yaml
runtime:
  budgets:
    max_steps: 100  # Increase limit

# OR for graph pattern:
pattern:
  type: graph
  config:
    max_iterations: 5  # Limit loop iterations
```

---

### Tool Execution Errors

#### Error: "Tool not found"
```
ToolError: Tool 'database_query' not found in registry
```

**Cause:** Tool not defined or typo  
**Fix:**
```yaml
tools:
  - name: database_query  # Define tool first
    type: python_callable
    # ...

agents:
  analyst:
    tools: ["database_query"]  # Then reference it
```

---

#### Error: "Tool input validation failed"
```
ToolError: Input validation failed for tool 'http_request'
Missing required property: 'url'
```

**Cause:** Agent didn't provide required tool input  
**Fix:** Improve agent prompt
```yaml
agents:
  api-caller:
    tools: ["http_request"]
    prompt: |
      Fetch data from https://api.example.com/data
      
      IMPORTANT: When using http_request tool, always provide:
      - url: The full URL to request
      - method: GET, POST, etc.
```

---

#### Error: "HTTP request blocked"
```
SecurityError: HTTP request to 'http://internal-server.local' blocked by security policy
```

**Cause:** URL blocked by allowlist/blocklist  
**Fix:**
```yaml
tools:
  - type: http_request
    config:
      allowlist: ["*.example.com", "internal-server.local"]  # Add to allowlist
      block_private_ips: false  # Or disable private IP blocking (not recommended)
```

---

## Pattern-Specific Issues

### Chain Pattern

#### Error: "Step reference out of bounds"
```
TemplateError: steps[5] does not exist (chain has 3 steps)
```

**Cause:** Referencing step index that doesn't exist  
**Fix:** Use correct 0-indexed step numbers
```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: step-0  # Index 0
      - agent: step-1  # Index 1
      - agent: step-2  # Index 2
        input: "Use output from step 1: {{ steps[1].response }}"
        # NOT steps[3], steps[4], etc.
```

---

### Routing Pattern

#### Error: "No route matched and no default specified"
```
RoutingError: No route condition matched classification and default route not configured
```

**Cause:** All conditions failed and no default route  
**Fix:** Always provide default route
```yaml
pattern:
  type: routing
  config:
    routes:
      - name: route-a
        condition: "category == 'a'"
        # ...
        
    default: fallback-agent  # Always specify default
    default_input: "Handle unmatched case"
```

---

#### Error: "Invalid JMESPath condition"
```
RoutingError: Invalid JMESPath expression: "category = 'a'"
Syntax error at position 10
```

**Cause:** Incorrect JMESPath syntax  
**Fix:** Use correct JMESPath operators
```yaml
routes:
  - condition: "category == 'a'"  # Use == not =
  - condition: "score > `5`"       # Quote numbers with backticks
  - condition: "contains(tags, 'urgent')"  # Use JMESPath functions
```

---

### Workflow Pattern (DAG)

#### Error: "Circular dependency detected"
```
WorkflowError: Circular dependency in workflow DAG:
  task-a depends_on task-b
  task-b depends_on task-c
  task-c depends_on task-a
```

**Cause:** Tasks form dependency cycle  
**Fix:** Remove circular dependency
```yaml
tasks:
  - id: task-a
    depends_on: []  # Start point (no dependencies)
    
  - id: task-b
    depends_on: [task-a]  # Depends on a
    
  - id: task-c
    depends_on: [task-b]  # Depends on b (NOT a - would create cycle)
```

---

#### Error: "Task not found in dependency"
```
WorkflowError: Task 'task-x' referenced in depends_on not found in workflow
```

**Cause:** Task ID in `depends_on` doesn't exist  
**Fix:** Use correct task IDs
```yaml
tasks:
  - id: fetch-data  # This is the ID
    # ...
    
  - id: process-data
    depends_on: [fetch-data]  # Must match exactly
```

---

### Graph Pattern

#### Error: "Unreachable nodes detected"
```
GraphError: Nodes [node-c, node-d] are unreachable from start_node
```

**Cause:** Nodes have no incoming edges  
**Fix:** Add edges to connect all nodes
```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: start
      - id: node-a
      - id: node-b
        
    edges:
      - from: start
        to: node-a
      - from: node-a
        to: node-b  # Connect all nodes to start
        
    start_node: start
```

---

#### Error: "Multiple edges from same node with no conditions"
```
GraphError: Node 'review' has multiple outgoing edges but no conditions
```

**Cause:** Multiple edges without conditions (ambiguous routing)  
**Fix:** Add conditions to all but one edge
```yaml
edges:
  - from: review
    to: approve
    condition: "score >= `8`"  # Condition required
    
  - from: review
    to: revise
    condition: "score < `8`"   # Condition required
```

---

### Evaluator-Optimizer Pattern

#### Error: "Score not found in evaluation"
```
EvaluatorError: Could not extract score from evaluation using path 'score'
Evaluation output: "The quality is good"
```

**Cause:** Evaluator didn't return numeric score  
**Fix:** Ensure evaluator returns structured JSON
```yaml
agents:
  evaluator:
    prompt: |
      Evaluate the output and return JSON:
      {
        "score": 7.5,  # MUST include numeric score
        "feedback": "Good but needs improvement"
      }

pattern:
  type: evaluator-optimizer
  config:
    score_path: "score"  # JMESPath to extract score
```

---

### Orchestrator-Workers Pattern

#### Error: "Invalid task format from orchestrator"
```
OrchestratorError: Orchestrator output missing 'tasks' array
```

**Cause:** Orchestrator didn't return expected format  
**Fix:** Ensure orchestrator returns correct JSON
```yaml
agents:
  orchestrator:
    prompt: |
      Create task list in this EXACT format:
      {
        "tasks": [
          {
            "id": "task-1",
            "description": "Task description",
            "worker": "worker-id",
            "input": "Worker input"
          }
        ]
      }
```

---

## Debugging Strategies

### Enable Debug Logging

```bash
# Full debug output
uv run strands run workflow.yaml --debug --verbose

# Or set environment variable
export STRANDS_DEBUG=true
uv run strands run workflow.yaml
```

### Export Execution Trace

```yaml
outputs:
  artifacts:
    - path: "./debug/trace-{{ timestamp }}.json"
      from: "{{ $TRACE }}"
```

Then analyze:
```bash
# Pretty-print trace
uv run python -m json.tool debug/trace.json

# Check token usage per step
cat debug/trace.json | jq '.spans[] | {name, tokens_input, tokens_output}'
```

### Validate Before Running

```bash
# Validate spec structure
uv run strands validate workflow.yaml

# Dry-run planner (workflow/graph patterns)
uv run strands plan workflow.yaml

# Check provider connectivity
uv run strands doctor
```

### Test with Simple Inputs

```yaml
# Add test inputs for debugging
inputs:
  optional:
    test_mode:
      type: boolean
      default: false

agents:
  researcher:
    prompt: |
      {% if test_mode %}
      TESTING MODE: Return mock data immediately
      {% else %}
      Perform actual research on {{ topic }}
      {% endif %}
```

### Incremental Development

1. **Start minimal:**
```yaml
version: 0
name: "test"
runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-haiku-20240307-v1:0"  # Fast, cheap
  region: "us-east-1"

agents:
  test-agent:
    prompt: "Say hello"

pattern:
  type: chain
  config:
    steps:
      - agent: test-agent
        input: "Test"
```

2. **Add one feature at a time**
3. **Test after each change**
4. **Use version control to track changes**

### Check Session State

```bash
# List all sessions
uv run strands sessions list

# Show specific session details
uv run strands sessions show <session-id>

# Delete a session
uv run strands sessions delete <session-id>

# Cleanup expired sessions
uv run strands sessions cleanup

# Resume failed session for debugging
uv run strands run --resume <session-id> --debug
```

## Performance Issues

### Slow Execution

**Symptoms:** Workflow takes much longer than expected

**Diagnostics:**
```bash
# Check trace for slow spans
cat trace.json | jq '.spans[] | {name, duration_ms}'

# Monitor token usage
cat trace.json | jq '.metrics'
```

**Common causes:**
1. **Large context:** Enable compression
2. **Sequential when parallel:** Use parallel/workflow pattern
3. **Too many retries:** Reduce retry count
4. **Slow model:** Switch to faster model for development

**Fixes:**
```yaml
# Enable context compression
context_policy:
  compression:
    enabled: true
    threshold_tokens: 30000

# Use parallel execution
runtime:
  max_parallel: 10

# Reduce retries
runtime:
  failure_policy:
    retries: 1
```

---

### High Token Usage

**Symptoms:** Exceeding token budgets quickly

**Diagnostics:**
```yaml
outputs:
  artifacts:
    - path: "./debug/trace.json"
      from: "{{ $TRACE }}"
```

Check token usage:
```bash
cat debug/trace.json | jq '.spans[] | {agent: .attributes["agent.name"], tokens_input, tokens_output}'
```

**Fixes:**
1. **Limit agent output:**
```yaml
agents:
  researcher:
    runtime:
      max_tokens: 1000  # Limit response size
```

2. **Use context compression:**
```yaml
context_policy:
  compression:
    enabled: true
```

3. **Avoid redundant context:**
```yaml
steps:
  - agent: analyzer
    input: "Analyze"
    context_mode: summary  # Don't pass full previous responses
```

---

## Getting Help

### Check Documentation

1. **JSON Schema:** `src/strands_cli/schema/strands-workflow.schema.json`
2. **Manual:** `docs/strands-workflow-manual.md`
3. **Examples:** `examples/` directory

### Run Health Check

```bash
uv run strands doctor
```

### Enable Telemetry

```yaml
telemetry:
  enabled: true
  otel:
    endpoint: "http://localhost:4317"
```

Then analyze traces in your observability platform.

### Common Error Patterns

| Error Message Contains | Likely Cause | Fix |
|----------------------|--------------|-----|
| "Property ... required" | Missing required field | Add field to spec |
| "not defined in agents" | Agent reference typo | Check agent name |
| "Additional property" | Wrong property name | Check schema |
| "credentials not found" | Missing AWS/API key | Configure credentials |
| "Budget exceeded" | Too many tokens/time | Increase budget or optimize |
| "Tool not found" | Tool not defined | Define tool in spec |
| "Circular dependency" | Cycle in workflow DAG | Remove dependency cycle |
| "Invalid JMESPath" | Syntax error in condition | Fix JMESPath expression |
| "Score not found" | Evaluator format wrong | Return structured JSON |

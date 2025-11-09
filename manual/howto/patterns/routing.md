# Routing Pattern

The Routing pattern dynamically selects the appropriate execution path based on input classification. A router agent analyzes the input and chooses which route to follow, then executes a sequence of steps specific to that route. This is ideal for scenarios where different inputs require different handling strategies.

## When to Use

Use the Routing pattern when you need to:

- Classify inputs and route to specialized handlers
- Implement different workflows for different input types
- Build intelligent dispatching systems (support tickets, task classification)
- Create multi-path workflows with conditional branching
- Avoid running unnecessary processing for specific input types

## Basic Example

```yaml
version: 0
name: simple-router
description: Route tasks to appropriate specialists

runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0

inputs:
  task:
    type: string
    description: "Task description"
    default: "Write a Python function to sort a list"

agents:
  - id: classifier
    system: |
      You are a task classifier. Analyze tasks and determine their type.
      Respond with ONLY valid JSON: {"route": "<route_name>"}

  - id: coder
    system: "You are an expert programmer. Write clean, documented code."

  - id: writer
    system: "You are a technical writer. Create clear documentation."

  - id: researcher
    system: "You are a researcher. Provide comprehensive information."

pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: |
        Task: {{ task }}

        Classify as: coding, writing, or research
      max_retries: 3

    routes:
      coding:
        then:
          - agent: coder
            input: |
              Task: {{ task }}

              Implement with code examples and explanations.

      writing:
        then:
          - agent: writer
            input: |
              Task: {{ task }}

              Create well-structured content.

      research:
        then:
          - agent: researcher
            input: |
              Task: {{ task }}

              Conduct thorough research.
```

## Router Configuration

### Router Agent

The router agent analyzes input and selects a route:

```yaml
router:
  agent: classifier          # Agent that makes routing decision
  input: "{{ user_query }}"  # Input to analyze
  max_retries: 3             # Retry if JSON parsing fails
```

**Critical**: Router must respond with valid JSON:

```json
{"route": "route_name"}
```

### Router Input Template

Access workflow inputs in the router prompt:

```yaml
router:
  agent: classifier
  input: |
    User Query: {{ query }}
    Context: {{ context }}
    Priority: {{ priority }}

    Classify into: urgent, standard, or low_priority
```

## Route Definitions

### Basic Route

Each route defines a sequence of steps to execute:

```yaml
routes:
  technical:
    then:
      - agent: tech_specialist
        input: "Handle technical issue: {{ input_query }}"
```

### Multi-Step Routes

Routes can have multiple sequential steps:

```yaml
routes:
  escalate:
    then:
      - agent: analyst
        input: "Analyze issue: {{ input_query }}"

      - agent: manager
        input: |
          Analysis: {{ steps[0].response }}

          Provide management response.

      - agent: writer
        input: |
          Create formal response based on:
          {{ steps[1].response }}
```

### Fallback Routes

Use `when: else` for default routing:

```yaml
routes:
  technical:
    then: [...]

  billing:
    then: [...]

  general:
    when: else  # Catches anything not routed to technical or billing
    then:
      - agent: general_support
        input: "Handle general inquiry"
```

## Accessing Router Results

### Router Output

Access the routing decision and router response:

```yaml
routes:
  coding:
    then:
      - agent: coder
        input: |
          Routed to: {{ router.chosen_route }}
          Router analysis: {{ router.response }}

          Original task: {{ task }}
```

### Using in Artifacts

Reference router information in output files:

```yaml
outputs:
  artifacts:
    - path: "./response-{{ router.chosen_route }}.md"
      content: |
        # Response (Route: {{ router.chosen_route }})

        {{ last_response }}
```

## Conditional Routing with JMESPath

### Simple Conditions

Use JMESPath expressions for additional routing logic:

```yaml
routes:
  high_priority:
    when: "priority == 'high'"
    then:
      - agent: urgent_handler
        input: "Handle urgently"

  normal:
    when: else
    then:
      - agent: standard_handler
        input: "Handle normally"
```

### Complex Conditions

Combine multiple conditions:

```yaml
routes:
  premium_urgent:
    when: "priority == 'high' && customer_tier == 'premium'"
    then: [...]

  standard_urgent:
    when: "priority == 'high' && customer_tier != 'premium'"
    then: [...]

  routine:
    when: else
    then: [...]
```

## Advanced Features

### Route-Specific Variables

Pass different variables to different routes:

```yaml
routes:
  technical:
    then:
      - agent: tech_specialist
        input: "{{ issue }}"
        vars:
          expertise_level: "advanced"
          include_code: true

  general:
    then:
      - agent: general_support
        input: "{{ issue }}"
        vars:
          expertise_level: "beginner"
          include_code: false
```

### Accessing Step Results in Routes

Reference previous steps within a route:

```yaml
routes:
  research:
    then:
      - agent: researcher
        input: "Research {{ topic }}"

      - agent: analyst
        input: |
          Research findings:
          {{ steps[0].response }}

          Analyze key insights.

      - agent: writer
        input: |
          Research: {{ steps[0].response }}
          Analysis: {{ steps[1].response }}

          Write comprehensive report.
```

### Multiple Agents in Routes

Different routes can use different agent configurations:

```yaml
agents:
  - id: classifier
    system: "Classify customer queries"

  - id: faq_bot
    system: "Answer common questions briefly"
    max_tokens: 200

  - id: tech_expert
    system: "Provide detailed technical support"
    max_tokens: 1000

  - id: escalation_manager
    system: "Handle complex escalations"
    max_tokens: 500

routes:
  faq:
    then:
      - agent: faq_bot
        input: "{{ query }}"

  technical:
    then:
      - agent: tech_expert
        input: "{{ query }}"
      - agent: faq_bot
        input: "Summarize: {{ steps[0].response }}"

  escalate:
    then:
      - agent: escalation_manager
        input: "{{ query }}"
```

## Error Handling

### Router Retry Logic

If the router returns invalid JSON, it retries:

```yaml
router:
  agent: classifier
  input: "{{ query }}"
  max_retries: 3  # Try up to 3 times to get valid JSON
```

After `max_retries` failures, the workflow exits with an error.

### Route Execution Failures

Configure retry behavior for route steps:

```yaml
runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  failure_policy:
    retries: 2
    backoff: exponential
```

Each step in the selected route gets retry attempts.

### Budget Limits

Prevent runaway routing workflows:

```yaml
runtime:
  budgets:
    max_steps: 10          # Maximum total steps
    max_tokens: 50000      # Maximum total tokens
    max_duration_s: 300    # Maximum 5 minutes
```

## Best Practices

### 1. Clear Router Instructions

Provide explicit routing criteria:

```yaml
agents:
  - id: classifier
    system: |
      You are a customer support classifier.

      Available routes:
      - faq: Simple questions (password resets, account setup)
      - technical: Complex issues (bugs, errors, performance)
      - escalate: Urgent issues (security, billing disputes)

      Respond with ONLY valid JSON: {"route": "<route_name>"}
```

### 2. Validate Router Output

The router MUST return valid JSON with a `route` field:

```yaml
# Good - valid JSON
{"route": "technical"}

# Bad - will cause retries
Technical support needed

# Bad - invalid JSON
{route: technical}
```

Use `max_retries` to handle occasional formatting issues.

### 3. Design for Coverage

Ensure all possible inputs have a route:

```yaml
routes:
  route1:
    then: [...]

  route2:
    then: [...]

  default:
    when: else  # Catch-all for unmatched cases
    then:
      - agent: default_handler
        input: "Handle unknown case"
```

### 4. Keep Routes Focused

Each route should handle a specific type of input:

```yaml
# Good - clear separation
routes:
  bug_report:
    then:
      - agent: bug_analyst
        input: "Analyze bug"
      - agent: dev_team
        input: "Triage: {{ steps[0].response }}"

  feature_request:
    then:
      - agent: product_manager
        input: "Evaluate request"

# Avoid - mixing concerns
routes:
  everything:
    then:
      - agent: do_it_all
        input: "Handle anything"
```

### 5. Test Router Classification

Validate router behavior with different inputs:

```bash
# Test different input types
strands run router.yaml --var query="How do I reset my password?"
strands run router.yaml --var query="App crashes on startup"
strands run router.yaml --var query="Cancel my subscription"
```

## Common Patterns

### Customer Support Routing

```yaml
router:
  agent: support_classifier
  input: "Customer query: {{ query }}"

routes:
  faq:
    then:
      - agent: faq_bot
        input: "Answer: {{ query }}"

  technical:
    then:
      - agent: tech_support
        input: "Debug: {{ query }}"
      - agent: summarizer
        input: "Simplify: {{ steps[0].response }}"

  escalate:
    then:
      - agent: manager
        input: "Escalate: {{ query }}"
```

### Content Type Routing

```yaml
router:
  agent: content_classifier
  input: "User request: {{ request }}"

routes:
  code:
    then:
      - agent: developer
        input: "Write code for: {{ request }}"
      - agent: documenter
        input: "Document: {{ steps[0].response }}"

  documentation:
    then:
      - agent: technical_writer
        input: "Write docs for: {{ request }}"

  tutorial:
    then:
      - agent: educator
        input: "Create tutorial for: {{ request }}"
```

### Priority-Based Routing

```yaml
router:
  agent: priority_classifier
  input: |
    Task: {{ task }}
    Deadline: {{ deadline }}
    Impact: {{ impact }}

routes:
  urgent:
    when: "priority == 'urgent'"
    then:
      - agent: senior_engineer
        input: "Fast-track: {{ task }}"

  normal:
    when: "priority == 'normal'"
    then:
      - agent: engineer
        input: "Process: {{ task }}"

  low:
    when: else
    then:
      - agent: junior_engineer
        input: "Queue: {{ task }}"
```

## Performance Considerations

### Router Overhead

The routing pattern adds one agent invocation for classification:

```
Total time = Router time + Selected route time
            ≈ 1-3s      + Route execution time
```

For simple binary decisions, consider using the Graph pattern with conditions instead.

### Agent Caching

Strands caches agents across route steps:

```yaml
routes:
  technical:
    then:
      - agent: tech_support  # Agent built
      - agent: tech_support  # Cached - no rebuild
      - agent: tech_support  # Cached - no rebuild
```

### Route Execution

Only the selected route executes - other routes are never processed.

## Troubleshooting

### Router Returning Invalid JSON

Check router agent output:

```bash
strands run router.yaml --debug --verbose
```

Look for:
```
Router response: "The task should be routed to technical support"
Error: Failed to parse router JSON after 3 retries
```

Fix: Improve router system prompt to enforce JSON output.

### Wrong Route Selected

Verify router logic with explicit inputs:

```yaml
router:
  agent: classifier
  input: |
    Query: {{ query }}

    Classification criteria:
    - If contains "error" or "bug" → technical
    - If contains "billing" or "payment" → billing
    - Otherwise → general

    Respond with JSON: {"route": "<route>"}
```

### Route Not Found

Ensure route names match exactly:

```yaml
# Router returns
{"route": "technical"}

# Routes must have exact match
routes:
  technical:     # ✓ Matches
    then: [...]

  Technical:     # ✗ Case mismatch
    then: [...]
```

### Steps Within Route Failing

Enable debug mode to see route execution:

```bash
strands run router.yaml --debug --verbose
```

Look for:
```
Selected route: technical
Executing step 1/3 in route 'technical'
Step failed: <error>
```

## Routing vs. Other Patterns

### Routing vs. Graph

Use Routing for dynamic classification, Graph for explicit control flow:

```yaml
# Routing: Decision made by AI router
pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: "{{ input }}"  # AI decides which route
    routes:
      route1: [...]
      route2: [...]

# Graph: Decision based on explicit conditions
pattern:
  type: graph
  config:
    nodes:
      classify: {...}
    edges:
      - from: classify
        choose:
          - when: "{{ 'technical' in nodes.classify.response }}"
            to: tech_handler
          - when: else
            to: general_handler
```

### Routing vs. Conditional Chain

Routing executes different step sequences, Chain executes all steps:

```yaml
# Routing: Only selected route executes
pattern:
  type: routing
  config:
    router: {...}
    routes:
      route_a:
        then: [step1, step2]  # OR
      route_b:
        then: [step3, step4]  # Only one route runs

# Chain: All steps execute
pattern:
  type: chain
  config:
    steps:
      - agent: step1
      - agent: step2  # AND
      - agent: step3  # All steps run
```

## Examples

Complete examples in the repository:

- `examples/routing-task-classification.yaml` - Task classifier routing to specialists
- `examples/routing-customer-support.yaml` - Customer support ticket routing
- `examples/routing-multi-tool-openai.yaml` - Multi-tool routing workflow

## See Also

- [Graph Pattern](graph.md) - For explicit conditional control flow
- [Chain Pattern](chain.md) - For sequential execution
- [Workflow Pattern](workflow.md) - For parallel task execution
- [Run Workflows](../run-workflows.md) - Execution guide
- [JMESPath Conditions](../jmespath.md) - Writing route conditions

# Graph Pattern

The Graph pattern implements state machines with explicit control flow using nodes and conditional edges. Unlike other patterns, Graph gives you complete control over execution order through JMESPath conditions, enabling loops, branching, and complex decision trees. This is ideal for workflows requiring dynamic routing based on runtime conditions.

## When to Use

Use the Graph pattern when you need to:

- Implement complex conditional logic and branching
- Create loops with exit conditions
- Build state machines with multiple execution paths
- Make routing decisions based on node outputs
- Implement decision trees or approval workflows
- Handle dynamic workflows that vary based on runtime data

## Basic Example

```yaml
version: 0
name: simple-graph
description: Basic graph with conditional routing

runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0

agents:
  - id: classifier
    system: "You classify input and provide category in your response."

  - id: handler_a
    system: "You handle category A requests."

  - id: handler_b
    system: "You handle category B requests."

pattern:
  type: graph
  config:
    max_iterations: 5  # Prevent infinite loops

    nodes:
      classify:
        agent: classifier
        input: "Classify this request: {{ request }}"

      handle_a:
        agent: handler_a

      handle_b:
        agent: handler_b

    edges:
      - from: classify
        choose:
          - when: "{{ 'category a' in nodes.classify.response.lower() }}"
            to: handle_a
          - when: "{{ 'category b' in nodes.classify.response.lower() }}"
            to: handle_b

inputs:
  request:
    type: string
    description: "User request"
    default: "I need help with category A"
```

## Graph Components

### Nodes

Nodes represent execution states:

```yaml
nodes:
  node_id:
    agent: agent_id
    input: "{{ template }}"  # Optional, uses default if omitted
```

Each node executes an agent invocation. The first node defined becomes the start node unless `start_node` is specified.

### Edges

Edges define transitions between nodes:

```yaml
edges:
  - from: source_node
    choose:
      - when: "{{ condition_1 }}"
        to: target_node_1
      - when: "{{ condition_2 }}"
        to: target_node_2
      - when: else
        to: default_node
```

Edges use JMESPath conditions to determine next node.

### Start Node

Explicitly set the starting node:

```yaml
config:
  start_node: intake  # Start here instead of first defined node

  nodes:
    intake: {...}
    process: {...}
```

## Conditional Edges

### Simple Conditions

Check for text in node responses:

```yaml
edges:
  - from: analyze
    choose:
      - when: "{{ 'approved' in nodes.analyze.response.lower() }}"
        to: proceed
      - when: "{{ 'rejected' in nodes.analyze.response.lower() }}"
        to: reject
```

### Numeric Comparisons

Compare numeric values:

```yaml
edges:
  - from: validate
    choose:
      - when: "{{ 'amount: 50' in nodes.validate.response }}"
        to: auto_approve
      - when: "{{ 'amount: 500' in nodes.validate.response }}"
        to: manager_review
      - when: else
        to: director_review
```

### Multiple Conditions

Combine conditions with AND/OR:

```yaml
edges:
  - from: classify
    choose:
      - when: "{{ 'urgent' in nodes.classify.response and 'premium' in nodes.classify.response }}"
        to: fast_track
      - when: "{{ 'urgent' in nodes.classify.response }}"
        to: standard_urgent
      - when: else
        to: normal_queue
```

### Else Clause

Always provide a fallback:

```yaml
edges:
  - from: node_a
    choose:
      - when: "{{ condition_1 }}"
        to: node_b
      - when: "{{ condition_2 }}"
        to: node_c
      - when: else  # Required for complete coverage
        to: default_node
```

## Accessing Node Results

### Specific Node Outputs

Access any completed node by ID:

```yaml
nodes:
  analyze:
    agent: analyst
    input: |
      Previous classification:
      {{ nodes.classify.response }}

      Perform detailed analysis.
```

### Node Metadata

Access node execution status:

```yaml
outputs:
  artifacts:
    - path: "execution_log.md"
      content: |
        ## Execution Path

        {% if nodes.classify %}
        Classification: {{ nodes.classify.response }}
        {% endif %}

        {% if nodes.approve %}
        Approval: {{ nodes.approve.response }}
        {% endif %}
```

### Terminal Node

Access the final node reached:

```yaml
outputs:
  artifacts:
    - path: "result.md"
      content: |
        **Terminal Node**: {{ terminal_node }}
        **Total Steps**: {{ total_steps }}

        {{ last_response }}
```

## Loops and Cycles

### Implementing Loops

Create cycles by routing back to previous nodes:

```yaml
nodes:
  generate:
    agent: generator
    input: "Generate content for {{ topic }}"

  check:
    agent: validator
    input: |
      Validate: {{ nodes.generate.response }}

      Respond with "valid" or "invalid"

edges:
  - from: generate
    to: check

  - from: check
    choose:
      - when: "{{ 'invalid' in nodes.check.response.lower() }}"
        to: generate  # Loop back
      - when: else
        to: done  # Exit loop

  done:
    agent: finalizer
```

### Maximum Iterations

Prevent infinite loops:

```yaml
config:
  max_iterations: 10  # Maximum node executions

  nodes: {...}
  edges: {...}
```

After `max_iterations`, execution stops at current node.

### Loop Counters

Track iteration count in conditions:

```yaml
edges:
  - from: process
    choose:
      - when: "{{ iteration < 5 and 'retry' in nodes.process.response }}"
        to: process  # Loop with limit
      - when: else
        to: complete
```

## Terminal Nodes

### Implicit Terminal Nodes

Nodes with no outgoing edges are terminal:

```yaml
nodes:
  start:
    agent: processor

  finish:
    agent: finalizer

edges:
  - from: start
    to: finish

  # finish has no outgoing edges = terminal node
```

### Multiple Terminal Nodes

Different paths can end at different terminals:

```yaml
nodes:
  classify: {...}
  approve: {...}
  reject: {...}

edges:
  - from: classify
    choose:
      - when: "{{ 'accept' in nodes.classify.response }}"
        to: approve  # Terminal
      - when: else
        to: reject   # Terminal

  # Both approve and reject are terminal nodes
```

## Advanced Features

### Multi-Path Workflows

Complex branching logic:

```yaml
nodes:
  intake: {...}
  technical: {...}
  billing: {...}
  general: {...}
  escalate: {...}

edges:
  # Initial routing
  - from: intake
    choose:
      - when: "{{ 'technical' in nodes.intake.response }}"
        to: technical
      - when: "{{ 'billing' in nodes.intake.response }}"
        to: billing
      - when: else
        to: general

  # Escalation from technical
  - from: technical
    choose:
      - when: "{{ 'high priority' in nodes.intake.response }}"
        to: escalate
      # Else: terminal

  # Escalation from billing
  - from: billing
    choose:
      - when: "{{ 'high priority' in nodes.intake.response }}"
        to: escalate
      # Else: terminal

  # escalate is terminal
```

### Decision Trees

Hierarchical decision-making:

```yaml
nodes:
  validate: {...}
  auto_approve: {...}
  manager: {...}
  director: {...}
  reject: {...}

edges:
  - from: validate
    choose:
      - when: "{{ 'invalid' in nodes.validate.response }}"
        to: reject
      - when: "{{ 'amount: 50' in nodes.validate.response }}"
        to: auto_approve
      - when: "{{ 'amount: 500' in nodes.validate.response }}"
        to: manager
      - when: else
        to: director

  - from: manager
    choose:
      - when: "{{ 'approve' in nodes.manager.response }}"
        to: director
      - when: else
        to: reject
```

### Retry Logic

Implement automatic retries:

```yaml
nodes:
  execute:
    agent: executor
    input: "Perform operation: {{ task }}"

  verify:
    agent: verifier
    input: "Verify: {{ nodes.execute.response }}"

  retry_check:
    agent: checker
    input: |
      Attempts: {{ retry_count | default(0) }}
      Max retries: 3

      Can retry? {{ retry_count | default(0) < 3 }}

edges:
  - from: execute
    to: verify

  - from: verify
    choose:
      - when: "{{ 'success' in nodes.verify.response }}"
        to: complete
      - when: else
        to: execute  # Retry (limited by max_iterations)
```

## Error Handling

### Node Failure

If a node fails:
- Execution stops at that node
- Workflow exits with error
- No outgoing edges are followed

### Cycle Detection

Strands detects infinite cycles:

```yaml
# This would be detected as a cycle
edges:
  - from: node_a
    to: node_b
  - from: node_b
    to: node_a  # Unconditional cycle = error
```

Use conditional edges to avoid infinite cycles.

### Budget Limits

Prevent runaway graphs:

```yaml
runtime:
  budgets:
    max_steps: 20          # Maximum total nodes
    max_tokens: 100000     # Maximum total tokens
    max_duration_s: 600    # Maximum 10 minutes

pattern:
  type: graph
  config:
    max_iterations: 10  # Additional graph-specific limit
```

## Output Artifacts

### Using Node Results

Access specific nodes in artifacts:

```yaml
outputs:
  artifacts:
    - path: "decision_log.md"
      content: |
        # Decision Log

        ## Initial Classification
        {{ nodes.classify.response }}

        {% if nodes.technical %}
        ## Technical Resolution
        {{ nodes.technical.response }}
        {% endif %}

        {% if nodes.escalate %}
        ## Escalation
        {{ nodes.escalate.response }}
        {% endif %}

        ## Final Decision
        Terminal Node: {{ terminal_node }}
```

### Execution Trace

Include execution path:

```yaml
outputs:
  artifacts:
    - path: "trace.md"
      content: |
        # Execution Trace

        **Total Steps**: {{ total_steps }}
        **Terminal Node**: {{ terminal_node }}

        ## Nodes Executed
        {% for node_id, node in nodes.items() %}
        - {{ node_id }}: {{ node.status }}
        {% endfor %}

        ## Final Output
        {{ last_response }}
```

## Best Practices

### 1. Always Provide Else Clauses

Ensure all paths are covered:

```yaml
# Good - complete coverage
edges:
  - from: classify
    choose:
      - when: "{{ condition_1 }}"
        to: path1
      - when: "{{ condition_2 }}"
        to: path2
      - when: else
        to: default_path

# Avoid - missing else clause
edges:
  - from: classify
    choose:
      - when: "{{ condition }}"
        to: path1
      # Missing else = error if condition false
```

### 2. Set Reasonable max_iterations

Prevent infinite loops:

```yaml
# Good - reasonable limit
config:
  max_iterations: 10  # Allows some loops but prevents runaway

# Avoid - too permissive
config:
  max_iterations: 1000  # Could run forever
```

### 3. Use Descriptive Node Names

Make graph structure clear:

```yaml
# Good - clear purpose
nodes:
  validate_input:
    agent: validator
  auto_approve:
    agent: approver
  manager_review:
    agent: manager

# Avoid - generic names
nodes:
  node1: {...}
  node2: {...}
  node3: {...}
```

### 4. Document Complex Logic

Use comments for complex conditions:

```yaml
edges:
  - from: validate
    choose:
      # Auto-approve for amounts under $100
      - when: "{{ 'amount: 50' in nodes.validate.response }}"
        to: auto_approve

      # Manager review for $100-$5000
      - when: "{{ 'amount: 500' in nodes.validate.response }}"
        to: manager

      # Director approval for > $5000
      - when: else
        to: director
```

### 5. Test All Paths

Validate all execution paths:

```bash
# Test different inputs to cover all paths
strands run graph.yaml --var input="approve"
strands run graph.yaml --var input="reject"
strands run graph.yaml --var input="escalate"
```

## Common Patterns

### Approval Workflow

```yaml
nodes:
  validate:
    agent: validator
  auto_approve:
    agent: approver
  manager:
    agent: manager_agent
  director:
    agent: director_agent
  reject:
    agent: rejector

edges:
  - from: validate
    choose:
      - when: "{{ 'invalid' in nodes.validate.response }}"
        to: reject
      - when: "{{ 'low amount' in nodes.validate.response }}"
        to: auto_approve
      - when: "{{ 'medium amount' in nodes.validate.response }}"
        to: manager
      - when: else
        to: director

  - from: manager
    choose:
      - when: "{{ 'approve' in nodes.manager.response }}"
        to: director
      - when: else
        to: reject
```

### State Machine

```yaml
nodes:
  intake: {...}
  process: {...}
  verify: {...}
  complete: {...}
  retry: {...}

edges:
  - from: intake
    to: process

  - from: process
    to: verify

  - from: verify
    choose:
      - when: "{{ 'success' in nodes.verify.response }}"
        to: complete
      - when: "{{ retry_count | default(0) < 3 }}"
        to: process  # Retry
      - when: else
        to: complete  # Give up
```

### Conditional Loop

```yaml
nodes:
  generate:
    agent: generator
  evaluate:
    agent: evaluator
  refine:
    agent: refiner
  finalize:
    agent: finalizer

edges:
  - from: generate
    to: evaluate

  - from: evaluate
    choose:
      - when: "{{ 'score: 90' in nodes.evaluate.response or 'score: 95' in nodes.evaluate.response }}"
        to: finalize  # Good enough
      - when: "{{ iteration < 5 }}"
        to: generate  # Try again
      - when: else
        to: finalize  # Max iterations
```

## Performance Considerations

### Execution Overhead

Graph pattern has minimal overhead per node:

```
Total time = Sum of node execution times
```

No scheduling overhead like Workflow pattern.

### Agent Caching

Agents are cached across nodes:

```yaml
agents:
  - id: processor
    system: "Process requests"

nodes:
  step1:
    agent: processor  # Agent built
  step2:
    agent: processor  # Cached
  step3:
    agent: processor  # Cached
```

### Optimal Path Length

Shorter paths are faster:

```yaml
# Fast - direct path to terminal
classify → handle → complete (3 nodes)

# Slower - long path with loops
classify → process → verify → refine → verify → refine → complete (7 nodes)
```

## Troubleshooting

### Graph Not Progressing

Check for missing edges:

```bash
strands validate workflow.yaml
```

Look for:
```
Node 'node_id' has no outgoing edges and condition not met
```

### Infinite Loop Detected

If max_iterations is reached:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Max iterations (10) reached
Current node: process
Execution stopped
```

### Condition Never True

Debug condition evaluation:

```yaml
# Add debug node to check values
nodes:
  debug:
    agent: debugger
    input: |
      Check condition:
      Response: {{ nodes.classify.response }}
      Contains 'approve': {{ 'approve' in nodes.classify.response.lower() }}
```

### Wrong Path Taken

Verify condition logic:

```yaml
edges:
  - from: classify
    choose:
      # Check exact condition matching
      - when: "{{ 'category a' in nodes.classify.response.lower() }}"
        to: handle_a
      - when: "{{ 'category b' in nodes.classify.response.lower() }}"
        to: handle_b
      - when: else
        to: default  # Add else to catch mismatches
```

## Graph vs. Other Patterns

### Graph vs. Routing

Graph has explicit conditions, Routing uses AI classification:

```yaml
# Graph: Explicit conditions
pattern:
  type: graph
  config:
    edges:
      - from: classify
        choose:
          - when: "{{ 'technical' in nodes.classify.response }}"
            to: tech_handler

# Routing: AI-based classification
pattern:
  type: routing
  config:
    router:
      agent: classifier  # AI decides route
```

### Graph vs. Workflow

Graph has conditional flow, Workflow has fixed DAG:

```yaml
# Graph: Conditional routing
edges:
  - from: analyze
    choose:
      - when: "{{ condition }}"
        to: path_a  # Dynamic choice
      - when: else
        to: path_b

# Workflow: Fixed dependencies
tasks:
  - id: task1
  - id: task2
    deps: [task1]  # Always follows task1
```

### Graph vs. Chain

Graph supports branching, Chain is linear:

```yaml
# Graph: Multiple paths
edges:
  - from: classify
    choose:
      - when: "{{ condition_a }}"
        to: handler_a
      - when: "{{ condition_b }}"
        to: handler_b

# Chain: Single path
steps:
  - agent_id: step1
  - agent_id: step2  # Always follows step1
```

## Examples

Complete examples in the repository:

- `examples/graph-decision-tree-openai.yaml` - Multi-level decision tree
- `examples/graph-state-machine-openai.yaml` - State machine with loops
- `examples/graph-iterative-refinement-openai.yaml` - Conditional refinement loop

## See Also

- [Routing Pattern](routing.md) - For AI-based routing
- [Workflow Pattern](workflow.md) - For DAG execution
- [Chain Pattern](chain.md) - For sequential execution
- [JMESPath Conditions](../jmespath.md) - Writing graph conditions
- [Run Workflows](../run-workflows.md) - Execution guide

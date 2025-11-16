# Workflow Patterns Deep Dive

Comprehensive guide to all 7 strands-cli orchestration patterns with real-world examples.

**All patterns are fully implemented and production-ready.** See `examples/` directory for working examples of each pattern.

## Pattern Selection Guide

| Pattern | Coordination | Parallelism | Loops | Conditionals | State |
|---------|-------------|-------------|-------|--------------|-------|
| Chain | Sequential | ❌ | ❌ | ❌ | Implicit |
| Routing | Dynamic | ❌ | ❌ | ✅ Input-based | None |
| Parallel | Fork-join | ✅ | ❌ | ❌ | Per-branch |
| Workflow | DAG | ✅ | ❌ | ❌ | Per-task |
| Graph | Explicit | ✅ | ✅ | ✅ JMESPath | Shared |
| Evaluator-Optimizer | Iterative | ❌ | ✅ Quality-based | ✅ Score threshold | Iterations |
| Orchestrator-Workers | Dynamic delegation | ✅ | ❌ | ❌ | Workers |

## 1. Chain Pattern

**Use when:** Steps must execute sequentially, each building on previous results.

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{ topic }}"
        
      - agent: analyzer
        input: "Analyze this research: {{ steps[0].response }}"
        
      - agent: writer
        input: "Write report based on analysis"
        context: "{{ steps[1].response }}"
```

**Key Features:**
- Steps execute in order
- Later steps access earlier outputs via `{{ steps[N].response }}`
- Context automatically threads through steps
- Budget enforcement across entire chain

**Best Practices:**
- Keep chains under 10 steps (use workflow pattern for more)
- Each step should have clear, single responsibility
- Use `context` field to pass large data without prompting

## 2. Routing Pattern

**Use when:** Agent selection depends on input classification.

```yaml
pattern:
  type: routing
  config:
    router: classifier
    router_input: "Classify this request: {{ user_query }}"
    routes:
      - name: technical
        condition: "contains(lower(classification), 'code')"
        agent: engineer
        input: "Handle technical request: {{ user_query }}"
        
      - name: creative
        condition: "contains(lower(classification), 'creative')"
        agent: writer
        input: "Handle creative request: {{ user_query }}"
        
    default: general-assistant
    default_input: "Handle general request: {{ user_query }}"
```

**Key Features:**
- Router agent classifies input
- JMESPath conditions select route
- First matching route wins
- Fallback to default if no match

**Condition Examples:**
```yaml
# String matching
condition: "contains(classification, 'urgent')"

# Multiple conditions
condition: "confidence > `0.8` && category == 'technical'"

# Array membership
condition: "contains(tags, 'priority')"
```

## 3. Parallel Pattern

**Use when:** Independent tasks can run concurrently.

```yaml
pattern:
  type: parallel
  config:
    branches:
      - name: market-research
        agent: researcher
        input: "Research market trends"
        
      - name: competitor-analysis
        agent: analyst
        input: "Analyze competitors"
        
      - name: customer-feedback
        agent: analyst
        input: "Summarize customer feedback"
        
    reduce:
      enabled: true
      agent: synthesizer
      input: |
        Combine insights:
        Market: {{ branches.market-research.response }}
        Competitors: {{ branches.competitor-analysis.response }}
        Customers: {{ branches.customer-feedback.response }}
```

**Key Features:**
- All branches execute concurrently
- Optional reduce step aggregates results
- Access branch outputs: `{{ branches.branch-name.response }}`
- Respects `runtime.max_parallel` limit

**Performance:**
- Set `max_parallel: 10` for I/O-bound tasks
- Monitor token usage across branches
- Use reduce for final synthesis

## 4. Workflow Pattern (DAG)

**Use when:** Complex dependencies with optimal parallelization.

```yaml
pattern:
  type: workflow
  config:
    tasks:
      - id: fetch-data
        agent: data-fetcher
        input: "Fetch data from {{ source }}"
        
      - id: clean-data
        agent: data-cleaner
        input: "Clean data"
        depends_on: [fetch-data]
        context: "{{ tasks.fetch-data.response }}"
        
      - id: analyze-trends
        agent: trend-analyzer
        input: "Analyze trends"
        depends_on: [clean-data]
        
      - id: analyze-anomalies
        agent: anomaly-detector
        input: "Detect anomalies"
        depends_on: [clean-data]
        
      - id: final-report
        agent: report-writer
        input: "Generate report"
        depends_on: [analyze-trends, analyze-anomalies]
        context: |
          Trends: {{ tasks.analyze-trends.response }}
          Anomalies: {{ tasks.analyze-anomalies.response }}
```

**Execution Order:**
1. `fetch-data` (parallel with nothing)
2. `clean-data` (depends on fetch-data)
3. `analyze-trends` AND `analyze-anomalies` (parallel, both depend on clean-data)
4. `final-report` (waits for both analyses)

**Key Features:**
- Automatic dependency resolution
- Maximum parallelization within constraints
- Cycle detection (fails fast on circular dependencies)
- Access task outputs: `{{ tasks.task-id.response }}`

## 5. Graph Pattern (State Machine)

**Use when:** Complex control flow with loops and conditionals.

```yaml
pattern:
  type: graph
  config:
    nodes:
      - id: draft
        agent: writer
        input: "Write draft about {{ topic }}"
        
      - id: review
        agent: reviewer
        input: "Review this draft: {{ nodes.draft.response }}"
        
      - id: revise
        agent: writer
        input: "Revise based on feedback: {{ nodes.review.response }}"
        
      - id: finalize
        agent: editor
        input: "Finalize the document"
        
    edges:
      - from: draft
        to: review
        
      - from: review
        to: revise
        condition: "score < `8`"
        
      - from: review
        to: finalize
        condition: "score >= `8`"
        
      - from: revise
        to: review  # Loop back for re-review
        
    start_node: draft
    end_nodes: [finalize]
    max_iterations: 5
```

**Key Features:**
- Explicit control flow via edges
- JMESPath conditions on edges
- Loop detection and max iteration protection
- Multiple end nodes supported
- Shared state across iterations

**Safety:**
- Always set `max_iterations` (default: 10)
- Define `end_nodes` for graceful termination
- Avoid infinite loops with proper conditions

## 6. Evaluator-Optimizer Pattern

**Use when:** Iterative refinement with quality gates.

```yaml
pattern:
  type: evaluator-optimizer
  config:
    generator: code-writer
    generator_input: "Write Python function for {{ task }}"
    
    evaluator: code-reviewer
    evaluator_input: "Review this code: {{ current_output }}"
    
    optimizer: code-improver
    optimizer_input: |
      Improve code based on feedback:
      Code: {{ current_output }}
      Feedback: {{ evaluation }}
      
    max_iterations: 5
    quality_threshold: 8.0
    score_path: "score"  # JMESPath to extract score from evaluation
```

**Workflow:**
1. Generator creates initial output
2. Evaluator scores output (must include numeric score)
3. If score < threshold: Optimizer improves, go to step 2
4. If score >= threshold: Done
5. If max_iterations reached: Return best attempt

**Key Features:**
- Automatic iteration until quality threshold met
- Configurable score extraction via JMESPath
- Best attempt tracking (highest score)
- Quality gate enforcement

## 7. Orchestrator-Workers Pattern

**Use when:** Dynamic task delegation to worker pools.

```yaml
pattern:
  type: orchestrator-workers
  config:
    orchestrator: task-planner
    orchestrator_input: "Break down project: {{ project_description }}"
    
    workers:
      - id: backend-dev
        agent: backend-engineer
        description: "Backend development tasks"
        
      - id: frontend-dev
        agent: frontend-engineer
        description: "Frontend development tasks"
        
      - id: qa-tester
        agent: qa-engineer
        description: "Testing and quality assurance"
        
    aggregator: project-manager
    aggregator_input: |
      Review completed work:
      {% for worker_id, result in worker_results.items() %}
      {{ worker_id }}: {{ result }}
      {% endfor %}
      
    max_tasks: 20
```

**Orchestrator Output Format:**
```json
{
  "tasks": [
    {
      "id": "task-1",
      "description": "Implement user authentication",
      "worker": "backend-dev",
      "input": "Create JWT-based auth system"
    },
    {
      "id": "task-2",
      "description": "Build login UI",
      "worker": "frontend-dev",
      "input": "Create React login form"
    }
  ]
}
```

**Key Features:**
- Orchestrator dynamically creates task list
- Tasks routed to workers by ID
- Parallel worker execution
- Aggregator synthesizes results

## Pattern Migration Strategies

### Chain → Workflow
When chain grows beyond 5-7 steps:
1. Identify independent steps
2. Add `depends_on` for sequential dependencies
3. Convert to workflow tasks

### Routing → Graph
When routes need loops or complex flow:
1. Convert routes to nodes
2. Add conditional edges
3. Define start/end nodes

### Parallel → Workflow
When branches have dependencies:
1. Convert branches to tasks
2. Add `depends_on` between related tasks

## Testing Patterns

```bash
# Validate spec structure
uv run strands validate workflow.yaml

# Dry-run visualization (workflow/graph patterns)
uv run strands plan workflow.yaml

# Debug with trace output
uv run strands run workflow.yaml --debug --trace ./trace.json
```

## Common Anti-Patterns

❌ **Using chain for independent tasks**
```yaml
# Bad: Sequential when parallel works
pattern:
  type: chain
  config:
    steps:
      - agent: task-a  # Independent
      - agent: task-b  # Independent
```

✅ **Use parallel instead**
```yaml
pattern:
  type: parallel
  config:
    branches:
      - name: a
        agent: task-a
      - name: b
        agent: task-b
```

❌ **Graph without max_iterations**
```yaml
# Bad: Potential infinite loop
pattern:
  type: graph
  config:
    nodes: [...]
    edges:
      - from: review
        to: revise
        condition: "needs_work"
      - from: revise
        to: review  # Loop!
```

✅ **Set iteration limit**
```yaml
pattern:
  type: graph
  config:
    max_iterations: 10  # Safety limit
    # ...
```

# Evaluator-Optimizer Pattern

The Evaluator-Optimizer pattern implements iterative refinement through a producer-evaluator-optimizer loop. A producer generates initial output, an evaluator scores it against quality criteria, and if the score is below threshold, the producer revises the output based on feedback. This continues until quality criteria are met or maximum iterations are reached.

## When to Use

Use the Evaluator-Optimizer pattern when you need to:

- Ensure output meets specific quality standards
- Implement iterative refinement workflows
- Generate content that improves through feedback
- Enforce quality gates before accepting results
- Implement code review or content review cycles

## Basic Example

```yaml
version: 0
name: simple-evaluator-optimizer
description: Iterative content refinement

runtime:
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0

agents:
  - id: writer
    system: "You are an expert writer. Create clear, engaging content."

  - id: critic
    system: |
      You are a critical editor. Evaluate content quality.
      Respond with JSON: {"score": 0-100, "issues": [...], "fixes": [...]}

pattern:
  type: evaluator_optimizer
  config:
    producer: writer

    evaluator:
      agent: critic
      input: |
        Evaluate this draft:
        {{ draft }}

        Return JSON with score (0-100), issues array, and fixes array.

    accept:
      min_score: 85
      max_iters: 3

inputs:
  topic:
    type: string
    description: "Content topic"
    default: "artificial intelligence"
```

## Pattern Components

### Producer Agent

The producer generates initial output and revisions:

```yaml
agents:
  - id: writer
    system: |
      You are a content writer.
      Write a blog post about the given topic.

config:
  producer: writer  # Agent that produces drafts
```

The producer is invoked initially, then again for each revision iteration.

### Evaluator Configuration

The evaluator scores output quality:

```yaml
evaluator:
  agent: critic                    # Agent that evaluates quality
  input: |                         # Template for evaluation
    Evaluate this draft:
    {{ draft }}

    Score 0-100 based on:
    - Clarity
    - Accuracy
    - Engagement
    - Structure

    Return JSON: {"score": 85, "issues": [...], "fixes": [...]}
```

**Critical**: Evaluator must return valid JSON with `score` field (0-100).

### Acceptance Criteria

Define when to accept output:

```yaml
accept:
  min_score: 85      # Minimum score to accept (0-100)
  max_iters: 3       # Maximum revision iterations
```

Workflow stops when either:
- Score meets `min_score` threshold
- `max_iters` iterations reached

## Revision Prompt

### Default Revision Behavior

Without a custom revision prompt, Strands uses a generic template:

```yaml
# Default behavior
config:
  producer: writer
  evaluator: {...}
  accept: {...}
  # No revise_prompt - uses default
```

Default template includes:
- Current draft
- Evaluation score
- Issues identified
- Suggested fixes

### Custom Revision Prompt

Provide domain-specific revision guidance:

```yaml
config:
  producer: writer
  evaluator: {...}
  accept: {...}

  revise_prompt: |
    Your previous draft scored {{ evaluation.score }}/100.

    Issues identified:
    {% for issue in evaluation.issues %}
    - {{ issue }}
    {% endfor %}

    Suggested fixes:
    {% for fix in evaluation.fixes %}
    - {{ fix }}
    {% endfor %}

    Revise the draft to address ALL issues.
    Maintain the original topic and style.
```

### Accessing Evaluation Results

Available variables in revision prompt:

```yaml
revise_prompt: |
  Score: {{ evaluation.score }}
  Iteration: {{ iteration }}

  Issues: {{ evaluation.issues | join(', ') }}
  Fixes: {{ evaluation.fixes | join(', ') }}

  Previous draft:
  {{ draft }}

  Please revise.
```

## Iteration Workflow

### Execution Flow

```
1. Producer generates initial draft
2. Evaluator scores draft
3. If score >= min_score → Accept and finish
4. If score < min_score → Producer revises based on feedback
5. Repeat steps 2-4 until accepted or max_iters reached
```

### Example Execution

```yaml
accept:
  min_score: 85
  max_iters: 3
```

Timeline:
```
Iteration 1:
  Producer → Draft v1
  Evaluator → Score: 65 (below threshold)

Iteration 2:
  Producer → Draft v2 (revised)
  Evaluator → Score: 78 (below threshold)

Iteration 3:
  Producer → Draft v3 (revised)
  Evaluator → Score: 87 (above threshold)
  Result: Accept draft v3
```

If max_iters reached without meeting min_score:
```
Iteration 3:
  Producer → Draft v3 (revised)
  Evaluator → Score: 82 (below threshold)
  Result: Accept draft v3 (max iterations reached)
```

## Accessing Results

### Final Output

The accepted draft is available as `last_response`:

```yaml
outputs:
  artifacts:
    - path: "final_output.md"
      content: "{{ last_response }}"
```

### Iteration History

Access evaluation metadata:

```yaml
outputs:
  artifacts:
    - path: "review_report.md"
      content: |
        # Review Report

        **Final Score**: {{ evaluation.score }}
        **Iterations**: {{ iteration }}
        **Accepted**: {{ evaluation.score >= 85 }}

        ## Final Output
        {{ last_response }}
```

## Advanced Features

### Different Models for Different Roles

Use specialized models:

```yaml
agents:
  - id: fast_writer
    model: anthropic.claude-3-haiku-20240307-v1:0
    system: "Fast content generation"

  - id: critical_evaluator
    model: anthropic.claude-3-opus-20240229-v1:0
    system: "Thorough quality evaluation"

config:
  producer: fast_writer
  evaluator:
    agent: critical_evaluator
```

### Complex Evaluation Criteria

Multiple quality dimensions:

```yaml
evaluator:
  agent: critic
  input: |
    Evaluate on multiple dimensions:

    Draft: {{ draft }}

    Score each dimension 0-100:
    1. Technical accuracy
    2. Clarity and readability
    3. Completeness
    4. Code quality (if applicable)

    Return JSON:
    {
      "score": <average of all dimensions>,
      "technical": <score>,
      "clarity": <score>,
      "completeness": <score>,
      "code_quality": <score>,
      "issues": [...],
      "fixes": [...]
    }
```

### Iteration-Aware Revision

Adjust guidance based on iteration count:

```yaml
revise_prompt: |
  Revision {{ iteration }} of {{ max_iters }}
  Current score: {{ evaluation.score }}/{{ min_score }} required

  {% if iteration == 1 %}
  First revision: Focus on major issues first.
  {% elif iteration == 2 %}
  Second revision: Address remaining issues thoroughly.
  {% else %}
  Final revision: Make targeted improvements to meet threshold.
  {% endif %}

  Issues: {{ evaluation.issues | join(', ') }}
  Fixes: {{ evaluation.fixes | join(', ') }}
```

## Error Handling

### Evaluator Returning Invalid JSON

If evaluator returns invalid JSON, the workflow fails:

```bash
Error: Evaluator response is not valid JSON
Expected: {"score": 85, "issues": [...], "fixes": [...]}
Received: "The content is good quality"
```

Fix: Enforce JSON output in evaluator system prompt.

### Quality Never Reached

If min_score is never reached:

```yaml
accept:
  min_score: 95    # Very high threshold
  max_iters: 3
```

Result: Workflow completes with best available draft after 3 iterations.

### Budget Limits

Prevent excessive iteration:

```yaml
runtime:
  budgets:
    max_steps: 10          # Limit total iterations
    max_tokens: 100000     # Limit total tokens
    max_duration_s: 600    # Maximum 10 minutes
```

## Best Practices

### 1. Set Realistic Thresholds

Balance quality and iteration count:

```yaml
# Good - achievable threshold
accept:
  min_score: 85
  max_iters: 3

# Avoid - unrealistic threshold
accept:
  min_score: 99  # May never reach
  max_iters: 10  # Too many iterations
```

### 2. Provide Specific Evaluation Criteria

Clear criteria lead to better feedback:

```yaml
# Good - specific criteria
evaluator:
  agent: critic
  input: |
    Evaluate based on:
    1. Code correctness (no bugs)
    2. Type hints (complete coverage)
    3. Docstrings (all functions documented)
    4. Error handling (comprehensive)

# Avoid - vague criteria
evaluator:
  agent: critic
  input: "Is this code good? Score it."
```

### 3. Use Structured Feedback

Request actionable fixes:

```yaml
evaluator:
  agent: critic
  input: |
    Return JSON with:
    {
      "score": <0-100>,
      "issues": ["Specific issue 1", "Specific issue 2"],
      "fixes": ["How to fix issue 1", "How to fix issue 2"]
    }
```

### 4. Monitor Iteration Progress

Track improvement across iterations:

```yaml
outputs:
  artifacts:
    - path: "iteration_log.md"
      content: |
        # Iteration Log

        **Iterations Used**: {{ iteration }}
        **Final Score**: {{ evaluation.score }}
        **Target Score**: 85

        Improvement achieved: {{ evaluation.score >= 85 }}
```

### 5. Handle Edge Cases

Ensure evaluator handles all inputs:

```yaml
evaluator:
  agent: critic
  input: |
    Evaluate: {{ draft }}

    If draft is empty or invalid, return:
    {"score": 0, "issues": ["Empty draft"], "fixes": ["Generate content"]}

    Otherwise evaluate normally.
```

## Common Patterns

### Code Quality Refinement

```yaml
config:
  producer: coder

  evaluator:
    agent: reviewer
    input: |
      Review this code: {{ draft }}

      Check:
      1. Correctness
      2. Type hints
      3. Docstrings
      4. Error handling
      5. Performance

      Return JSON with score and detailed feedback.

  accept:
    min_score: 85
    max_iters: 4

  revise_prompt: |
    Code review score: {{ evaluation.score }}/100

    Issues: {{ evaluation.issues | join('\n- ') }}
    Fixes: {{ evaluation.fixes | join('\n- ') }}

    Revise the code to address ALL issues.
```

### Content Writing Refinement

```yaml
config:
  producer: writer

  evaluator:
    agent: editor
    input: |
      Edit this content: {{ draft }}

      Evaluate:
      1. Grammar and spelling
      2. Clarity and flow
      3. Engagement
      4. Structure

      Return JSON with score and feedback.

  accept:
    min_score: 90
    max_iters: 3

  revise_prompt: |
    Editorial feedback ({{ evaluation.score }}/100):

    Issues found:
    {% for issue in evaluation.issues %}
    - {{ issue }}
    {% endfor %}

    Please revise to address these issues while maintaining voice and style.
```

### Design Review Cycle

```yaml
config:
  producer: designer

  evaluator:
    agent: design_critic
    input: |
      Review this design: {{ draft }}

      Criteria:
      1. Usability
      2. Accessibility
      3. Visual hierarchy
      4. Consistency

      Return JSON score and recommendations.

  accept:
    min_score: 80
    max_iters: 5
```

## Performance Considerations

### Iteration Overhead

Each iteration adds time:

```
Total time = Initial draft + (Iterations × (Evaluation + Revision))
           ≈ 3s + (N × (2s + 3s))
           ≈ 3s + (N × 5s)
```

Balance quality vs. time by setting appropriate `max_iters`.

### Agent Caching

Producer and evaluator agents are cached:

```yaml
# Agent built once, reused for all iterations
producer: writer     # Built on first iteration
evaluator:
  agent: critic      # Built on first evaluation
```

## Troubleshooting

### Evaluator Not Returning JSON

Check evaluator output:

```bash
strands run workflow.yaml --debug --verbose
```

Look for:
```
Evaluator response: "This is good content, score is 85"
Error: Invalid JSON from evaluator
```

Fix: Enforce JSON-only output in system prompt.

### Score Not Improving

If score plateaus:

```
Iteration 1: Score 60
Iteration 2: Score 62
Iteration 3: Score 63
```

Possible causes:
- Vague evaluation criteria
- Insufficient revision guidance
- Unrealistic target score

### Max Iterations Reached

If workflow always hits max_iters:

```yaml
# Lower threshold or increase iterations
accept:
  min_score: 80      # Was 95
  max_iters: 5       # Was 3
```

## Evaluator-Optimizer vs. Other Patterns

### vs. Chain

Evaluator-Optimizer has quality gates, Chain doesn't:

```yaml
# Evaluator-Optimizer: Iterates until quality threshold
pattern:
  type: evaluator_optimizer
  config:
    accept:
      min_score: 85  # Must meet threshold

# Chain: Executes steps once
pattern:
  type: chain
  config:
    steps: [...]  # No quality feedback loop
```

### vs. Graph with Loops

Evaluator-Optimizer has structured evaluation, Graph has custom conditions:

```yaml
# Evaluator-Optimizer: Built-in quality scoring
pattern:
  type: evaluator_optimizer
  config:
    evaluator: {...}
    accept: {...}

# Graph: Custom loop logic
pattern:
  type: graph
  config:
    nodes:
      generate: {...}
      check: {...}
    edges:
      - from: check
        choose:
          - when: "{{ custom_condition }}"
            to: generate  # Loop back
```

## Examples

Complete examples in the repository:

- `examples/evaluator-optimizer-writing-openai.yaml` - Content refinement
- `examples/evaluator-optimizer-code-review-openai.yaml` - Code quality
- `examples/evaluator-optimizer-writing-ollama.yaml` - Local model refinement

## See Also

- [Chain Pattern](chain.md) - For sequential execution
- [Graph Pattern](graph.md) - For custom control flow
- [Run Workflows](../run-workflows.md) - Execution guide
- [Budgets](../budgets.md) - Implementing budget and quality constraints

# Human-in-the-Loop (HITL) Workflows

Learn how to add human approval gates and interactive decision points to your workflows using Human-in-the-Loop (HITL) steps.

## Overview

HITL steps allow you to pause workflow execution for:

- **Approval Gates**: Review agent outputs before expensive next steps
- **Quality Control**: Human validation of generated content
- **Interactive Workflows**: User-guided decision making
- **Debugging**: Inspect intermediate results during development
- **Compliance**: Human oversight for regulated processes

HITL integrates seamlessly with session management for automatic save/resume.

---

## Basic HITL Step

### Simple Approval Gate

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: generator
        input: "Generate content about {{ topic }}"

      # HITL approval gate
      - type: hitl
        prompt: "Review the generated content. Approve to continue?"
        context_display: "{{ steps[0].response }}"

      - agent: publisher
        input: "Publish: {{ steps[0].response }}"
```

### HITL Step Properties

| Property | Required | Description |
|----------|----------|-------------|
| `type` | Yes | Must be `"hitl"` |
| `prompt` | Yes | Message displayed to user requesting input |
| `context_display` | No | Context to show user (supports templates) |
| `default` | No | Default response if user provides empty input |
| `timeout_seconds` | No | Time before expiration (0 = no timeout, not enforced in Phase 1) |

---

## CLI Workflow

### Step 1: Run Workflow

```bash
uv run strands run workflow.yaml --var topic="AI Safety"

# Output:
# Running workflow: approval-workflow
# Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
# Step 1/3: generator - COMPLETE
#
# 🤝 HUMAN INPUT REQUIRED
#
# Review the generated content. Approve to continue?
#
# ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Context for Review                                       ┃
# ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
# │ [Generated content displayed here]                       │
# └───────────────────────────────────────────────────────────┘
#
# Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
# Resume with: strands run --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890 --hitl-response 'your response'
#
# Exit code: 19 (EX_HITL_PAUSE)
```

### Step 2: Review Context

Examine the displayed context and decide on your response:

- **Approve**: `"approved"`, `"yes"`, `"proceed"`, etc.
- **Request changes**: Provide specific feedback
- **Reject**: `"rejected"`, `"no"`, etc.

### Step 3: Resume with Response

```bash
# Approve and continue
uv run strands run --resume a1b2c3d4 --hitl-response "approved"

# Or provide feedback
uv run strands run --resume a1b2c3d4 --hitl-response "Please focus more on safety considerations"

# Output:
# Resuming session: a1b2c3d4...
# Skipping completed step 0: generator
# HITL response received: approved
# Step 3/3: publisher - EXECUTING
# ✓ Workflow complete
```

---

## Template Access

Access HITL responses in subsequent steps using `{{ steps[n].response }}`:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Write article about {{ topic }}"

      - type: hitl
        prompt: "Review article. Approve or provide feedback?"
        context_display: "{{ steps[0].response }}"

      - agent: editor
        input: |
          User review: {{ steps[1].response }}
          
          {% if steps[1].response == 'approved' %}
          Finalize this article for publication:
          {{ steps[0].response }}
          {% else %}
          Revise the article based on this feedback:
          {{ steps[1].response }}
          
          Original article:
          {{ steps[0].response }}
          {% endif %}
```

**Template variables in HITL context:**

- `{{ steps[n].response }}` - Previous step outputs
- `{{ last_response }}` - Most recent agent response
- `{{ variables.* }}` - User-provided variables
- Any custom variables from inputs

---

## Examples

### Example 1: Research Approval

```yaml
version: 0
name: "research-approval"
description: "Research workflow with approval gate"

runtime:
  provider: openai
  model_id: gpt-4o-mini

agents:
  researcher:
    prompt: "Research the given topic thoroughly."
  
  analyst:
    prompt: "Analyze research findings."

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research: {{ topic }}"

      - type: hitl
        prompt: |
          Review the research findings.
          Respond 'approved' to proceed, or provide feedback.
        context_display: |
          ## Research Findings
          {{ steps[0].response }}
        default: "approved"

      - agent: analyst
        input: |
          User: {{ steps[1].response }}
          {% if steps[1].response == 'approved' %}
          Analyze: {{ steps[0].response }}
          {% else %}
          Address this feedback: {{ steps[1].response }}
          Research: {{ steps[0].response }}
          {% endif %}
```

**Usage:**
```bash
# Run
uv run strands run research-approval.yaml --var topic="Quantum Computing"

# Resume with approval
uv run strands run --resume <session-id> --hitl-response "approved"

# Or with feedback
uv run strands run --resume <session-id> --hitl-response "Add more recent sources"
```

### Example 2: Multi-Gate Workflow

```yaml
pattern:
  type: chain
  config:
    steps:
      # Step 1: Generate draft
      - agent: writer
        input: "Write draft about {{ topic }}"

      # Gate 1: Content review
      - type: hitl
        prompt: "Review draft content (approve/revise/reject)"
        context_display: "{{ steps[0].response }}"

      # Step 2: Revise or continue
      - agent: writer
        input: |
          {% if steps[1].response == 'revise' %}
          Revise draft based on feedback
          {% elif steps[1].response == 'approve' %}
          Finalize draft: {{ steps[0].response }}
          {% endif %}

      # Gate 2: Final approval
      - type: hitl
        prompt: "Final approval for publication (yes/no)"
        context_display: "{{ steps[2].response }}"

      # Step 3: Publish
      - agent: publisher
        input: |
          {% if steps[3].response == 'yes' %}
          Publish: {{ steps[2].response }}
          {% else %}
          Archive without publishing
          {% endif %}
```

### Example 3: Debug Inspection

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: data_processor
        input: "Process dataset: {{ data_path }}"

      # Debug checkpoint
      - type: hitl
        prompt: "Inspect processing results. Continue or abort?"
        context_display: |
          ## Processing Results
          {{ steps[0].response }}
          
          ## Debug Info
          Dataset: {{ data_path }}
          Timestamp: {{ steps[0].timestamp }}

      - agent: analyzer
        input: "Analyze: {{ steps[0].response }}"
```

### Example 4: Multi-Stage Business Proposal

A sophisticated workflow with multiple HITL approval gates for executive and CFO review:

```yaml
version: 0
name: "hitl-business-proposal"
description: "Chain workflow with 2 HITL approval gates for business proposal review"

runtime:
  provider: openai
  model_id: gpt-5-nano
  budgets:
    max_tokens: 15000

agents:
  market_analyst:
    prompt: |
      You are a senior market analyst with expertise in competitive analysis.
      Provide detailed, data-driven market analysis with clear insights.

  financial_analyst:
    prompt: |
      You are a financial analyst specializing in business case development.
      Create comprehensive financial projections and ROI analysis.

  strategist:
    prompt: |
      You are a business strategist who synthesizes market and financial data
      into actionable strategic recommendations.

pattern:
  type: chain
  config:
    steps:
      # Step 1: Market Analysis
      - agent: market_analyst
        input: |
          Conduct market analysis for:
          Business: {{ business_concept }}
          Market: {{ target_market }}
          Geography: {{ geographic_scope }}

      # Step 2: Executive Review Gate
      - type: hitl
        prompt: |
          **EXECUTIVE REVIEW REQUIRED**
          
          Review market analysis. You may:
          - Type 'approved' to proceed to financial analysis
          - Provide feedback for revisions
          - Type 'reject' to halt the proposal
        context_display: |
          ## Market Analysis Report
          {{ steps[0].response }}
          
          **Decision Options:**
          - ✅ approved - Proceed to financial analysis
          - 📝 [feedback] - Request revisions
          - ❌ reject - Stop proposal
        default: "approved"
        timeout_seconds: 7200  # 2 hours

      # Step 3: Financial Analysis (conditional)
      - agent: financial_analyst
        input: |
          {% if steps[1].response == 'reject' %}
          Rejected. Summarize why this opportunity is not viable.
          {% elif steps[1].response == 'approved' %}
          Develop financial model based on approved analysis:
          {{ steps[0].response }}
          {% else %}
          Revise analysis addressing: {{ steps[1].response }}
          Original: {{ steps[0].response }}
          {% endif %}

      # Step 4: CFO Review Gate
      - type: hitl
        prompt: |
          **CFO REVIEW REQUIRED**
          
          Review financial analysis and projections.
        context_display: |
          ## Financial Analysis Report
          {{ steps[2].response }}
          
          **Decision Options:**
          - ✅ approved - Proceed to strategy
          - 📝 [feedback] - Request adjustments
          - ❌ reject - Insufficient financial case
        default: "approved"
        timeout_seconds: 7200

      # Step 5: Strategic Recommendations
      - agent: strategist
        input: |
          {% if steps[3].response == 'reject' %}
          Financial rejected. Explain why this doesn't meet criteria.
          {% elif steps[3].response == 'approved' %}
          Synthesize into strategic recommendations:
          Market: {{ steps[0].response }}
          Financial: {{ steps[2].response }}
          {% else %}
          Adjust recommendations per CFO feedback:
          {{ steps[3].response }}
          {% endif %}

outputs:
  artifacts:
    - path: "./business-proposal.md"
      from: |
        # Business Proposal: {{ business_concept }}
        
        **Status:** Approved for Execution
        
        ## 1. Market Analysis
        {{ steps[0].response }}
        
        ### Executive Review: {{ steps[1].response }}
        
        ## 2. Financial Analysis
        {{ steps[2].response }}
        
        ### CFO Review: {{ steps[3].response }}
        
        ## 3. Strategic Recommendations
        {{ steps[4].response }}
        
        ## Approval Chain
        | Stage | Reviewer | Decision |
        |-------|----------|----------|
        | Market | Executive | {{ steps[1].response }} |
        | Financial | CFO | {{ steps[3].response }} |
```

**Usage:**
```bash
# Run workflow
uv run strands run chain-hitl-business-proposal-openai.yaml \
  --var business_concept="AI Customer Service Platform" \
  --var target_market="Mid-market B2B SaaS" \
  --var geographic_scope="North America"

# Output shows session ID and first HITL gate
# Session ID: abc123...

# Executive approval
uv run strands run --resume abc123 --hitl-response "approved"

# CFO approval (second gate)
uv run strands run --resume abc123 --hitl-response "approved"

# Or provide feedback at any gate
uv run strands run --resume abc123 \
  --hitl-response "Please use more conservative revenue projections"
```

**Key Features:**
- **Multi-stakeholder**: Executive → CFO → Strategy team review
- **Conditional logic**: Different prompts based on approval/rejection
- **Rich context**: Formatted decision options in `context_display`
- **Structured output**: Complete proposal with approval chain summary
- **Resume workflow**: Each gate creates a resume point with full context

---

## Session Integration

### Automatic Session Saving

When a HITL step is encountered:

1. **Current state saved**: All completed steps, outputs, and token usage
2. **Session marked as PAUSED**: Status updated in session metadata
3. **Workflow exits**: Exit code 19 (EX_HITL_PAUSE)
4. **User notified**: Prompt, context, and resume instructions displayed

### Session State

```json
{
  "metadata": {
    "session_id": "abc123...",
    "status": "paused",
    "workflow_name": "approval-workflow"
  },
  "pattern_state": {
    "current_step": 1,
    "step_history": [
      {
        "index": 0,
        "agent": "generator",
        "response": "Generated content...",
        "tokens_estimated": 1500
      }
    ]
  }
}
```

### Resume Behavior

When resuming with `--resume` and `--hitl-response`:

1. **Session loaded**: State restored from disk
2. **HITL response recorded**: User input saved in step history
3. **Skip completed work**: Jump to next step after HITL
4. **Context updated**: HITL response available as `{{ steps[1].response }}`
5. **Execution continues**: Remaining steps execute with full context

---

## Best Practices

### 1. Clear Prompts

Write specific, actionable prompts:

✅ **Good:**
```yaml
prompt: "Review the API design. Respond 'approved' if complete, or list missing endpoints."
```

❌ **Avoid:**
```yaml
prompt: "Check this"
```

### 2. Provide Context

Always use `context_display` to show what to review:

```yaml
- type: hitl
  prompt: "Review analysis quality"
  context_display: |
    ## Analysis Results
    {{ steps[0].response }}
    
    ## Metrics
    Token usage: {{ steps[0].tokens }}
    Duration: {{ steps[0].duration }}
```

### 3. Use Default Responses

Provide safe defaults for non-critical approvals:

```yaml
- type: hitl
  prompt: "Approve to continue (default: yes)"
  default: "yes"
  timeout_seconds: 300  # 5 minutes
```

### 4. Document Expected Responses

Add comments or include options in prompt:

```yaml
- type: hitl
  prompt: |
    Select deployment environment:
    - production
    - staging
    - development
  context_display: "{{ deployment_plan }}"
```

### 5. Handle Different Responses

Use Jinja2 conditionals in subsequent steps:

```yaml
- agent: deployer
  input: |
    {% if steps[1].response == 'production' %}
    Deploy to production with validation
    {% elif steps[1].response == 'staging' %}
    Deploy to staging for testing
    {% else %}
    Deploy to development for debugging
    {% endif %}
```

### 6. Save Session ID

Keep track of session IDs for later resumption:

```bash
# Save to file
uv run strands run workflow.yaml | tee session.log
SESSION_ID=$(grep "Session ID:" session.log | awk '{print $3}')

# Resume later
uv run strands run --resume $SESSION_ID --hitl-response "approved"
```

### 7. Use Sessions List

View all pending HITL sessions:

```bash
# List paused sessions
uv run strands sessions list --status paused

# Show details
uv run strands sessions show <session-id>
```

---

## Supported Patterns

### Pattern Support Status

✅ **Fully Supported:**
- **Chain pattern**: HITL steps between sequential steps
- **Workflow pattern (DAG)**: HITL tasks with dependencies
- **Parallel pattern**: HITL in branches OR at reduce step
- **Graph pattern**: HITL nodes with conditional routing

### Pattern-Specific Features

**Routing Pattern** - HITL support in two locations:

**1. Route Step HITL** (within route sequences):

```yaml
pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: "Classify inquiry: technical, billing, general"
    routes:
      technical:
        then:
          - agent: tech_support
            input: "Diagnose: {{ inquiry }}"
          
          # HITL approval within route
          - type: hitl
            prompt: "Review technical solution. Approve to send?"
            context_display: "{{ steps[0].response }}"
```

**2. Router Review HITL** (review/override router decisions):

```yaml
pattern:
  type: routing
  config:
    router:
      agent: classifier
      input: "Classify: {{ inquiry }}"
      
      # Router review HITL gate
      review_router:
        type: hitl
        prompt: |
          Review router classification. Respond with:
          - "approved" to accept router's choice
          - "route:<name>" to override (e.g., "route:billing")
        context_display: |
          Router chose: {{ router.chosen_route }}
          Reasoning: {{ router.response }}
    
    routes:
      technical:
        then:
          - agent: tech_support
            input: "Handle technical inquiry"
      billing:
        then:
          - agent: billing_support
            input: "Handle billing inquiry"
```

**Router Template Variables:**
- `{{ router.chosen_route }}` - Final route name (after HITL approval/override)
- `{{ router.response }}` - Router agent's full response text

**Override Format:**
- `"approved"` - Accept router's decision
- `"route:<route_name>"` - Force specific route (e.g., `"route:billing"`)

---

**Graph Pattern** - HITL nodes enable dynamic routing:

```yaml
pattern:
  type: graph
  config:
    nodes:
      planner:
        agent: planner_agent
        input: "Create plan"
      
      review:
        type: hitl
        prompt: "Review plan. Respond 'approve' or 'revise'"
        context_display: "{{ nodes.planner.response }}"
      
      executor:
        agent: executor_agent
        input: "Execute plan"
    
    edges:
      - from: planner
        to: [review]
      
      - from: review
        choose:
          - when: "{{ nodes.review.response == 'approve' }}"
            to: executor
          - when: else
            to: planner  # Loop back for revision
```

**Template Access by Pattern:**
- **Chain**: `{{ steps[n].response }}` or `{{ hitl_response }}`
- **Workflow**: `{{ tasks.<id>.response }}`
- **Routing**: `{{ router.chosen_route }}`, `{{ router.response }}`, `{{ steps[n].response }}`
- **Parallel**: `{{ branches.<id>.response }}`
- **Graph**: `{{ nodes.<id>.response }}`

See pattern-specific examples:
- [chain-hitl-approval-demo.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/chain-hitl-approval-demo.yaml)
- [routing-hitl-review-openai.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/routing-hitl-review-openai.yaml)
- [workflow-hitl-approval-demo.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/workflow-hitl-approval-demo.yaml)
- [parallel-hitl-branch-demo.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/parallel-hitl-branch-demo.yaml)
- [parallel-hitl-reduce-demo.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/parallel-hitl-reduce-demo.yaml)
- [graph-hitl-approval-demo-openai.yaml](https://github.com/ThomasRohde/strands-cli/blob/main/examples/graph-hitl-approval-demo-openai.yaml)

---

## Current Limitations

### Phase 2 Constraints

- **CLI-based interaction**: Must use `--resume` and `--hitl-response` flags
- **No timeout enforcement**: `timeout_seconds` parsed but not enforced
- **No validation**: Response validation not implemented yet
- **No multi-user**: Single-user approval only

### Workarounds

**For interactive mode**: Use `--hitl-response` with a wrapper script:

```bash
#!/bin/bash
# hitl-interactive.sh - Wrapper for interactive HITL

SESSION_ID=$1

echo "Enter your response:"
read USER_RESPONSE

uv run strands run --resume $SESSION_ID --hitl-response "$USER_RESPONSE"
```

---

## Troubleshooting

### HITL Response Required Error

```bash
uv run strands run --resume abc123
# Error: Session is waiting for HITL response.
# Resume with: strands run --resume <session-id> --hitl-response 'your response'
```

**Solution**: Provide `--hitl-response` flag when resuming from HITL pause.

### HITL Response Without Resume

```bash
uv run strands run workflow.yaml --hitl-response "approved"
# Error: --hitl-response requires --resume <session-id>
```

**Solution**: `--hitl-response` only valid when resuming a paused session.

### Empty HITL Response

If you provide empty string:

```bash
uv run strands run --resume abc123 --hitl-response ""
```

**Behavior**: Empty string recorded as response (default not applied in Phase 1).

**Workaround**: Explicitly provide default value if that's your intent.

---

## Implementation Status

✅ **Fully Implemented (All Patterns):**
- HITL step type in **all 7 patterns**: chain, workflow, parallel, routing, evaluator-optimizer, orchestrator-workers, and graph
- HITL review gates for orchestrator-workers (decomposition_review, reduce_review)
- Automatic session pause on HITL step
- Exit code 19 (EX_HITL_PAUSE)
- Timeout enforcement with auto-resume using default response
- CLI flags: `--hitl-response`, `--auto-resume`
- Template access: Pattern-specific (`{{ steps[n].response }}`, `{{ nodes.<id>.response }}`, `{{ workers }}`, etc.)
- Context display with Jinja2 templates
- Session integration (save/resume)
- Multi-pattern support with conditional routing (graph)
- Example workflows for all supported patterns

🔜 **Coming in Future Releases:**
- Response validation with regex patterns
- Conditional HITL skipping based on criteria
- Interactive CLI mode (inline prompts without resume)
- Programmatic API for custom handlers
- Multi-user approval workflows
- HITL history and audit trails
- Web UI integration hooks
- Webhook notifications

---

## Next Steps

- **Try the example**: Run `chain-hitl-approval-demo.yaml` from the examples directory
- **Read the plan**: [HITL.md](https://github.com/ThomasRohde/strands-cli/blob/main/HITL.md) - Complete implementation roadmap
- **Session management**: [Session Management Guide](./session-management.md)
- **Chain pattern**: [Workflow Manual](../reference/workflow-manual.md)

---

## Related Documentation

- [HITL Implementation Plan](https://github.com/ThomasRohde/strands-cli/blob/main/HITL.md) - Complete HITL roadmap
- [Session Management](./session-management.md) - Session persistence guide
- [Workflow Manual](../reference/workflow-manual.md) - Workflow spec reference
- [Exit Codes](../reference/exit-codes.md) - CLI exit code meanings
- [Examples](../reference/examples.md) - More workflow examples

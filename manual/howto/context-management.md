# How to Manage Context

This guide shows you how to manage conversation context in Strands workflows using presets, notes, JIT tools, and context compaction.

## Understanding Context Management

Context management controls how much conversation history agents retain and how efficiently that memory is used. Without management, long workflows can:

- Exceed model context limits
- Incur excessive costs from repeated long contexts
- Lose important information when history is truncated

Strands provides four context management features:

1. **Presets** - Pre-configured settings for common scenarios
2. **Compaction** - Automatic summarization when context grows too large
3. **Notes** - Persistent structured memory across workflow steps
4. **JIT Retrieval** - On-demand tools to fetch specific information

## Using Presets

Presets provide battle-tested configurations optimized for different workflow types.

### Available Presets

| Preset | Best For | Compaction | Notes | Max Context |
|--------|----------|------------|-------|-------------|
| `minimal` | Short workflows (1-3 steps) | Disabled | No | Full |
| `balanced` | Most workflows (3-10 steps) | At 100K tokens | No | Medium |
| `long_run` | Research, multi-step (10+ steps) | At 80K tokens | Yes (20 notes) | Large |
| `interactive` | Chat, conversational | At 50K tokens | No | Moderate |

### Applying a Preset

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini
  preset: balanced  # Automatic context management
```

That's it! The preset configures:
- When to trigger compaction
- How much context to preserve
- What gets summarized vs. kept verbatim

### Preset Details

#### Minimal
```yaml
# Automatically configured when preset: minimal
context_policy:
  compaction:
    enabled: false
```

Use for:
- Simple single-agent tasks
- When you want full control
- Testing and development

#### Balanced (Recommended)
```yaml
# Automatically configured when preset: balanced
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 100000
    summary_ratio: 0.35
    preserve_recent_messages: 12
```

Use for:
- General-purpose workflows
- 3-10 step chains
- Moderate context requirements

#### Long Run
```yaml
# Automatically configured when preset: long_run
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 80000
    summary_ratio: 0.40
    preserve_recent_messages: 20
  notes:
    file: artifacts/notes.md
    include_last: 20
    format: markdown
  retrieval:
    jit_tools:
      - grep
      - search
      - head
      - tail
```

Use for:
- Research workflows
- Multi-agent collaboration
- Long-running processes
- Cross-step continuity

#### Interactive
```yaml
# Automatically configured when preset: interactive
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 50000
    summary_ratio: 0.30
    preserve_recent_messages: 16
```

Use for:
- Chat interfaces
- Conversational agents
- Frequent exchanges

## Custom Context Policies

For fine-grained control, configure `context_policy` directly:

```yaml
runtime:
  provider: openai
  model_id: gpt-4o-mini

context_policy:
  compaction:
    enabled: true
    when_tokens_over: 80000
    summary_ratio: 0.35
    preserve_recent_messages: 15
    summarization_model: gpt-4o-mini  # Optional: cheaper model for summaries

  notes:
    file: ./artifacts/workflow-notes.md
    include_last: 10
    format: markdown

  retrieval:
    jit_tools:
      - grep
      - head
      - tail
```

### Compaction Configuration

Control when and how context is summarized:

```yaml
context_policy:
  compaction:
    enabled: true                     # Turn on automatic compaction
    when_tokens_over: 100000          # Trigger at this token count
    summary_ratio: 0.35               # Keep 35% of content as summary
    preserve_recent_messages: 12      # Always keep last 12 messages verbatim
    summarization_model: gpt-4o-mini  # Optional: use cheaper model
```

**How it works:**

1. Workflow tracks cumulative tokens after each step
2. When tokens exceed `when_tokens_over`, compaction triggers
3. Older messages are summarized (except tool calls, which are preserved)
4. Recent messages (controlled by `preserve_recent_messages`) are kept intact
5. Summary replaces older messages, reducing total tokens by ~65%

**Token calculation example:**

- Original context: 120,000 tokens
- Compaction triggered at: 100,000
- After compaction: ~78,000 tokens
  - Summary of old messages: ~42,000 (35% of 120K)
  - Recent messages preserved: ~36,000

### Using a Cheaper Summarization Model

Save costs by using a smaller model for summarization:

```yaml
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 80000
    summarization_model: gpt-4o-mini  # Use mini for summaries, main model for work
```

This is especially valuable when your main workflow uses expensive models like GPT-4o or Claude Opus.

## Structured Notes

Notes provide persistent memory across workflow steps, stored in a Markdown file with timestamps and agent attribution.

### Basic Configuration

```yaml
context_policy:
  notes:
    file: ./artifacts/workflow-notes.md
    include_last: 10
    format: markdown
```

### How Notes Work

After each step, Strands appends a note entry:

```markdown
## [2025-11-09T14:32:00Z] — Agent: researcher (Step 1)
- Input: Analyze customer reviews for sentiment
- Tools used: http_request, file_read
- Outcome: Positive sentiment (0.82 score), 247 reviews analyzed
```

On subsequent steps, the last N notes are injected into agent context:

```
System: Previous Workflow Steps
[Last 10 note entries appear here]

User: [Current step prompt]
```

### Example Workflow with Notes

```yaml
version: 0
name: research-with-memory
runtime:
  provider: openai
  model_id: gpt-4o-mini

context_policy:
  notes:
    file: ./artifacts/research-notes.md
    include_last: 5

agents:
  researcher:
    prompt: |
      You are a research assistant. Analyze the given topic.
      Review "Previous Workflow Steps" to avoid repeating work.

  synthesizer:
    prompt: |
      You synthesize findings from research.
      Use "Previous Workflow Steps" to see what was already discovered.

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Research {{ topic }}"

      - agent: researcher
        input: "Find additional sources on {{ topic }}"

      - agent: synthesizer
        input: "Synthesize findings from previous research"

inputs:
  values:
    topic: "AI ethics in healthcare"
```

### Notes Across Sessions

Notes persist to disk, enabling multi-session workflows:

**Session 1:**
```bash
strands run research.yaml --var topic="climate change"
# Creates artifacts/research-notes.md with findings
```

**Session 2 (days later):**
```bash
strands run research.yaml --var topic="renewable energy"
# Loads previous notes, maintaining continuity
```

### Notes File Format

The notes file is human-readable Markdown:

```markdown
## [2025-11-09T10:15:00Z] — Agent: researcher (Step 1)
- Input: Research climate change impacts
- Tools used: None
- Outcome: Identified 5 major impact areas: sea level, temperature, ecosystems, agriculture, health

## [2025-11-09T10:16:23Z] — Agent: researcher (Step 2)
- Input: Find additional sources on climate change
- Tools used: http_request
- Outcome: Retrieved 12 peer-reviewed papers from nature.com, science.org

## [2025-11-09T10:17:45Z] — Agent: synthesizer (Step 3)
- Input: Synthesize findings from previous research
- Tools used: None
- Outcome: Created comprehensive synthesis covering all 5 impact areas with citations
```

You can review this file to understand what the workflow accomplished.

## JIT Retrieval Tools

JIT (Just-In-Time) tools let agents fetch specific information on demand instead of loading everything into context upfront.

### Configuration

```yaml
context_policy:
  retrieval:
    jit_tools:
      - grep      # Search files for patterns
      - search    # Full-text search
      - head      # Read start of files
      - tail      # Read end of files
```

### How JIT Tools Work

Instead of:
```yaml
# Bad: Load entire codebase into context
agents:
  analyst:
    prompt: |
      Here are all 50,000 lines of code:
      {{ entire_codebase }}

      Now find the bug.
```

Do this:
```yaml
# Good: Agent uses grep to find relevant code
agents:
  analyst:
    prompt: |
      You can search the codebase using the grep tool.
      Find code related to authentication errors.

context_policy:
  retrieval:
    jit_tools:
      - grep
```

The agent will invoke `grep` with search patterns as needed:

```
Agent: [Uses grep tool to search for "authentication"]
grep result: Found 3 files with "authentication"
Agent: [Reads specific files]
Agent: Found the bug in auth.py line 42
```

### Available JIT Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `grep` | Search files for text patterns | Find all TODO comments |
| `search` | Full-text search in files | Locate specific function definitions |
| `head` | Read first N lines of file | Check file headers |
| `tail` | Read last N lines of file | View log file endings |

### Example: Code Analysis with JIT

```yaml
version: 0
name: code-analyzer
runtime:
  provider: openai
  model_id: gpt-4o-mini

context_policy:
  retrieval:
    jit_tools:
      - grep
      - head
      - tail

agents:
  analyzer:
    prompt: |
      You analyze code for bugs and improvements.
      Use the available tools to search and inspect files:
      - grep: Search for patterns
      - head: Check file starts
      - tail: Check file ends

      Do NOT try to read entire files into context.

pattern:
  type: chain
  config:
    steps:
      - agent: analyzer
        input: "Find potential security issues in the authentication code"
```

## Combining Features

The most powerful context management combines all features:

```yaml
version: 0
name: comprehensive-research
runtime:
  provider: openai
  model_id: gpt-4o-mini
  preset: long_run  # Enables compaction, notes, and JIT tools

agents:
  researcher:
    prompt: |
      You are a research assistant with access to:
      1. Previous workflow steps (from notes)
      2. Search tools (grep, head, tail)
      3. Summarized conversation history (via compaction)

      Use these efficiently:
      - Check notes to avoid repeating work
      - Use grep to find specific information
      - Rely on summarized context for broad understanding

pattern:
  type: chain
  config:
    steps:
      - agent: researcher
        input: "Phase 1: Research {{ topic }}"

      - agent: researcher
        input: "Phase 2: Deep dive into findings from Phase 1"

      - agent: researcher
        input: "Phase 3: Synthesize comprehensive report"
```

This workflow:
- Uses `long_run` preset for optimal long-running performance
- Maintains notes for cross-step continuity
- Compacts context automatically when it exceeds 80K tokens
- Provides JIT tools for targeted information retrieval
- Preserves recent messages for immediate context

## Best Practices

### 1. Choose the Right Preset

Start with presets, customize only when needed:

```yaml
# Good: Use preset for common case
runtime:
  preset: balanced

# Only customize if you have specific requirements
context_policy:
  compaction:
    when_tokens_over: 120000  # Custom threshold
```

### 2. Monitor Token Usage

Use debug mode to see when compaction triggers:

```bash
strands run workflow.yaml --debug
```

Look for log entries:
```
context_compaction_triggered: tokens=103450 threshold=100000
context_compacted: before=103450 after=68230 reduction=34%
```

### 3. Set Appropriate Thresholds

Balance cost vs. information retention:

- **Conservative** (keep more context): `when_tokens_over: 120000`
- **Aggressive** (save costs): `when_tokens_over: 60000`
- **Balanced**: `when_tokens_over: 100000` (default)

### 4. Use Notes for Critical Information

Notes are never compacted, making them ideal for:

- Key decisions and their rationale
- Important findings that must persist
- Cross-step dependencies
- Session-spanning workflows

### 5. Combine with Budgets

Prevent runaway costs:

```yaml
runtime:
  preset: long_run
  budgets:
    max_tokens: 200000  # Hard limit across entire workflow

context_policy:
  compaction:
    when_tokens_over: 100000  # Compact at 50% of budget
```

## Troubleshooting

### Context Still Exceeds Model Limits

**Symptom:** Errors about context window exceeded

**Solutions:**

1. Lower `when_tokens_over` threshold:
   ```yaml
   context_policy:
     compaction:
       when_tokens_over: 60000  # More aggressive compaction
   ```

2. Increase `summary_ratio` (more aggressive summarization):
   ```yaml
   context_policy:
     compaction:
       summary_ratio: 0.25  # Keep only 25% (was 35%)
   ```

3. Reduce `preserve_recent_messages`:
   ```yaml
   context_policy:
     compaction:
       preserve_recent_messages: 8  # Keep fewer recent messages
   ```

### Important Information Lost in Summaries

**Symptom:** Agent "forgets" critical details from earlier steps

**Solutions:**

1. Increase `preserve_recent_messages`:
   ```yaml
   context_policy:
     compaction:
       preserve_recent_messages: 20  # Keep more verbatim
   ```

2. Use notes for critical information:
   ```yaml
   context_policy:
     notes:
       file: ./artifacts/notes.md
       include_last: 15  # More note context
   ```

3. Raise compaction threshold:
   ```yaml
   context_policy:
     compaction:
       when_tokens_over: 120000  # Delay compaction
   ```

### Notes File Growing Too Large

**Symptom:** Notes file becomes difficult to read or parse

**Solutions:**

1. Reduce `include_last`:
   ```yaml
   context_policy:
     notes:
       include_last: 5  # Only inject last 5 notes
   ```

2. Archive old notes between major workflow phases:
   ```bash
   mv artifacts/notes.md artifacts/notes-archive-2025-11-09.md
   # Start fresh notes file
   ```

### Compaction Happening Too Often

**Symptom:** Excessive compaction in short workflows

**Solutions:**

1. Use `minimal` or `balanced` preset instead of `long_run`:
   ```yaml
   runtime:
     preset: balanced  # Higher threshold
   ```

2. Increase threshold:
   ```yaml
   context_policy:
     compaction:
       when_tokens_over: 150000  # Less frequent compaction
   ```

## See Also

- [Budgets](budgets.md) - Token and time limits
- [Running Workflows](run-workflows.md) - Execution options
- [Telemetry](telemetry.md) - Monitoring context usage

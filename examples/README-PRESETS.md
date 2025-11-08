# Context Management Preset Examples

This directory contains example workflows demonstrating the four context management presets available in strands-cli.

## Available Presets

### 1. `minimal` - Short Workflows
**File**: `presets-minimal-openai.yaml`

**Best for**:
- Short workflows (1-3 steps)
- Simple tasks with small context
- When you want full control over context

**Configuration**:
- Compaction: **DISABLED**
- Notes: Not configured
- Retrieval: Not configured

**Run**:
```bash
# Uses default topic: "machine learning fundamentals"
uv run strands run examples/presets-minimal-openai.yaml

# Or override with custom topic
uv run strands run examples/presets-minimal-openai.yaml --var topic="AI safety"
```

---

### 2. `balanced` - General Purpose
**File**: `presets-balanced-openai.yaml`

**Best for**:
- Most workflows (3-10 steps)
- Medium context requirements
- General-purpose tasks

**Configuration**:
- Compaction: Enabled at 100K tokens
- Summary ratio: 35%
- Recent messages: 12 preserved
- Notes: Optional (not in preset)
- Retrieval: Optional (not in preset)

**Run**:
```bash
# Uses default focus_area: "customer behavior patterns"
uv run strands run examples/presets-balanced-openai.yaml

# Or override with custom focus area
uv run strands run examples/presets-balanced-openai.yaml --var focus_area="market trends"
```

---

### 3. `long_run` - Research Workflows
**File**: `presets-long-run-research-openai.yaml`

**Best for**:
- Research workflows (10+ steps)
- Multi-agent collaboration
- Long context requirements
- Cross-step continuity

**Configuration**:
- Compaction: Enabled at 80K tokens (earlier trigger)
- Summary ratio: 40% (more aggressive)
- Recent messages: 20 preserved (more context)
- Notes: Enabled with last 20 entries
- Retrieval: All JIT tools enabled (grep, search, head, tail)

**Run**:
```bash
# Uses default topic: "context management patterns"
uv run strands run examples/presets-long-run-research-openai.yaml

# Or override with custom topic
uv run strands run examples/presets-long-run-research-openai.yaml --var topic="distributed systems"
```

**Special Features**:
- Automatically injects last 20 notes into agent context
- JIT tools available for file access without loading entire files
- Optimized for long-running research and analysis

---

### 4. `interactive` - Chat Workflows
**File**: `presets-interactive-chat-openai.yaml`

**Best for**:
- Conversational agents
- User-facing chat interfaces
- Frequent back-and-forth exchanges

**Configuration**:
- Compaction: Enabled at 50K tokens (early trigger for responsiveness)
- Summary ratio: 30% (less aggressive)
- Recent messages: 16 preserved (more recent context)
- Notes: Not configured (history is primary)
- Retrieval: Not configured (minimal tool use)

**Run**:
```bash
# Uses default query: "What are the key benefits of AI?"
uv run strands run examples/presets-interactive-chat-openai.yaml

# Or override with custom query
uv run strands run examples/presets-interactive-chat-openai.yaml --var query="Explain machine learning"
```

---

## Preset Comparison

| Feature | minimal | balanced | long_run | interactive |
|---------|---------|----------|----------|-------------|
| **Compaction** | ❌ Disabled | ✅ 100K tokens | ✅ 80K tokens | ✅ 50K tokens |
| **Summary Ratio** | N/A | 35% | 40% | 30% |
| **Recent Messages** | N/A | 12 | 20 | 16 |
| **Notes** | ❌ | ❌ | ✅ 20 entries | ❌ |
| **JIT Tools** | ❌ | ❌ | ✅ All | ❌ |
| **Best Steps** | 1-3 | 3-10 | 10+ | 3-8 |
| **Use Case** | Quick tasks | General | Research | Chat |

---

## Customizing Presets

You can override preset values by specifying them explicitly in your spec:

```yaml
# Start with long_run preset values
context_policy:
  compaction:
    enabled: true
    when_tokens_over: 80000
    summary_ratio: 0.40
    preserve_recent_messages: 20
  
  notes:
    file: "artifacts/research-notes.md"
    include_last: 20
  
  retrieval:
    jit_tools: ["grep", "search", "head", "tail"]

  # Override: Use custom notes file path
  notes:
    file: "my-custom-notes.md"  # Your value takes precedence
    include_last: 30            # Custom value
```

---

## Using Presets Programmatically

```python
from strands_cli.presets import get_context_preset, apply_preset_to_spec

# Get preset configuration
policy = get_context_preset("long_run")

# Apply to spec data (merges with existing config)
spec_data = {
    "version": 0,
    "name": "my-workflow",
    # ... rest of spec
}
apply_preset_to_spec(spec_data, "long_run")

# Or set directly
spec.context_policy = policy
```

---

## Requirements

All examples require:
- **OpenAI API key**: Set `OPENAI_API_KEY` environment variable
- **strands-cli**: Installed via `uv sync`

```bash
export OPENAI_API_KEY="your-api-key-here"
```

---

## Output Artifacts

Each example generates artifacts in the `artifacts/` directory:

- `minimal` → `artifacts/quick-summary.md`
- `balanced` → `artifacts/analysis-report.md`
- `long_run` → `artifacts/research-report.md` + `artifacts/research-notes.md`
- `interactive` → `artifacts/chat-response.md`

---

## Learn More

- **Preset Implementation**: `src/strands_cli/presets.py`
- **Preset Tests**: `tests/test_presets.py`
- **Context Management**: See `docs/strands-workflow-manual.md`

---

## Tips

1. **Start with `balanced`** for most workflows
2. **Use `long_run`** when you need notes or JIT tools
3. **Use `interactive`** for conversational/chat interfaces
4. **Use `minimal`** for quick, simple tasks
5. **Customize** by overriding specific fields in your spec

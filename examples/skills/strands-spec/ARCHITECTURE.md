# Strands Spec Builder Skill - Architecture

## Progressive Loading Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      User Request                            │
│  "Create a data analysis workflow with DAG dependencies"     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │   Agent Loads SKILL.md (244L)   │ ◄── Always First
        │  - Core concepts                │
        │  - Quick start template         │
        │  - Pattern overview             │
        │  - Common errors                │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │   Agent Analyzes Requirements   │
        │  Determines: Need DAG pattern   │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  Load patterns.md (417L)        │ ◄── Targeted Load
        │  - Workflow DAG details         │
        │  - Dependencies syntax          │
        │  - Parallelization strategy     │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  Generate Spec Using Combined   │
        │  Knowledge (244 + 417 = 661L)   │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │    Return Complete YAML Spec    │
        └────────────────────────────────┘

Total Context: 661 lines (vs 3,672 if loading everything)
Reduction: 82%
```

## Skill Module Map

```
strands-spec/
│
├── SKILL.md (244L) ────────────────────┐
│   ├─ Quick Start Template             │
│   ├─ Essential Elements                │ ALWAYS
│   ├─ Pattern Selection Guide           │ LOAD
│   ├─ Common Validation Errors          │ FIRST
│   └─ Pointers to Other Modules         │
│                                         │
├── patterns.md (417L) ─────────────────┼─┐
│   ├─ Chain Pattern                     │ │
│   ├─ Routing Pattern                   │ │ Load when:
│   ├─ Parallel Pattern                  │ │ - Designing orchestration
│   ├─ Workflow (DAG) Pattern            │ │ - Choosing pattern type
│   ├─ Graph Pattern                     │ │ - Complex control flow
│   ├─ Evaluator-Optimizer Pattern       │ │ - Migration between patterns
│   ├─ Orchestrator-Workers Pattern      │ │
│   └─ Pattern Selection Matrix          │ │
│                                         │ │
├── tools.md (422L) ────────────────────┼─┼─┐
│   ├─ python_exec                       │ │ │
│   ├─ http_request (SSRF protection)    │ │ │ Load when:
│   ├─ grep                               │ │ │ - Adding tools to agents
│   ├─ notes                              │ │ │ - Custom tool development
│   ├─ Custom Python Callables           │ │ │ - Tool errors/debugging
│   ├─ Skill Loader Tool                 │ │ │ - Security configuration
│   └─ Tool Testing Strategies           │ │ │
│                                         │ │ │
├── advanced.md (599L) ─────────────────┼─┼─┼─┐
│   ├─ Context Management                │ │ │ │
│   ├─ OpenTelemetry Config              │ │ │ │ Load when:
│   ├─ PII Redaction                     │ │ │ │ - Setting up telemetry
│   ├─ Network Security                  │ │ │ │ - Configuring security
│   ├─ Secrets Management                │ │ │ │ - Performance optimization
│   ├─ Agent Caching                     │ │ │ │ - Durable execution
│   ├─ Model Client Pooling              │ │ │ │ - Production deployment
│   └─ Durable Execution                 │ │ │ │
│                                         │ │ │ │
├── examples.md (723L) ─────────────────┼─┼─┼─┼─┐
│   ├─ Data Analysis Pipeline            │ │ │ │ │
│   ├─ API Integration                   │ │ │ │ │ Load when:
│   ├─ Code Review Workflow              │ │ │ │ │ - Need workflow template
│   ├─ Research & Reporting              │ │ │ │ │ - Looking for examples
│   ├─ Customer Support Routing          │ │ │ │ │ - Understanding patterns
│   ├─ Batch Document Processing         │ │ │ │ │ - Real-world use cases
│   ├─ A/B Test Analysis                 │ │ │ │ │
│   └─ Content Creation Pipeline         │ │ │ │ │
│                                         │ │ │ │ │
├── troubleshooting.md (744L) ──────────┼─┼─┼─┼─┼─┐
│   ├─ Schema Validation Errors          │ │ │ │ │ │
│   ├─ Provider Configuration Issues     │ │ │ │ │ │ Load when:
│   ├─ Budget/Timeout Errors             │ │ │ │ │ │ - Debugging errors
│   ├─ Tool Execution Errors             │ │ │ │ │ │ - Validation failures
│   ├─ Pattern-Specific Issues           │ │ │ │ │ │ - Performance problems
│   ├─ Performance Debugging             │ │ │ │ │ │ - Runtime issues
│   └─ Debugging Checklist               │ │ │ │ │ │
│                                         │ │ │ │ │ │
└── quick-reference.md (335L) ──────────┼─┼─┼─┼─┼─┼─┐
    ├─ Minimal Spec Template             │ │ │ │ │ │ │
    ├─ Runtime Quick Config              │ │ │ │ │ │ │ Load when:
    ├─ Pattern Types Table               │ │ │ │ │ │ │ - Quick syntax lookup
    ├─ Template Variables                │ │ │ │ │ │ │ - Cheat sheet needed
    ├─ JMESPath Conditions               │ │ │ │ │ │ │ - CLI commands
    ├─ CLI Commands                      │ │ │ │ │ │ │ - Exit codes
    └─ Common Patterns                   │ │ │ │ │ │ │
                                          │ │ │ │ │ │ │
                                  ┌───────┴─┴─┴─┴─┴─┴─┘
                                  │
                                  ▼
                       Progressive Loading Strategy
                       Load combinations as needed:

                       Simple query: SKILL.md only (244L)
                       Pattern query: SKILL + patterns (661L)
                       Tool query: SKILL + tools (666L)
                       Debug query: SKILL + troubleshooting (988L)
                       Complex query: SKILL + 2-3 modules (1,000-1,500L)
                       Comprehensive: All modules (3,672L)
```

## Loading Decision Tree

```
                    ┌─────────────────┐
                    │  Agent receives  │
                    │   user request   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Load SKILL.md    │ (244 lines)
                    │  (Always first)  │
                    └────────┬─────────┘
                             │
                             ▼
              ┌──────────────┴──────────────┐
              │   Analyze request type      │
              └──┬──────┬──────┬──────┬────┬┘
                 │      │      │      │    │
        ┌────────┘      │      │      │    └─────────┐
        │               │      │      │              │
        ▼               ▼      ▼      ▼              ▼
   ┌─────────┐   ┌─────────┐ │  ┌─────────┐   ┌──────────┐
   │ Pattern │   │  Tools  │ │  │Advanced │   │  Debug   │
   │ design? │   │ config? │ │  │features?│   │  error?  │
   └────┬────┘   └────┬────┘ │  └────┬────┘   └────┬─────┘
        │             │      │       │             │
        ▼             ▼      │       ▼             ▼
   ┌─────────┐   ┌─────────┐│  ┌─────────┐   ┌──────────┐
   │  Load   │   │  Load   ││  │  Load   │   │   Load   │
   │patterns │   │  tools  ││  │advanced │   │troublesh.│
   │  (417L) │   │  (422L) ││  │  (599L) │   │  (744L)  │
   └─────────┘   └─────────┘│  └─────────┘   └──────────┘
                            │
                            ▼
                     ┌──────────┐
                     │  Need    │
                     │examples? │
                     └────┬─────┘
                          │
                          ▼
                     ┌──────────┐
                     │   Load   │
                     │ examples │
                     │  (723L)  │
                     └──────────┘
```

## Context Optimization Examples

### Example 1: Simple "Hello World" Spec

**Request:** "Create a simple hello world workflow"

**Load Strategy:**
```
SKILL.md (244L) → Has quick start template → Done
```

**Context Used:** 244 lines  
**Output:** Complete, valid minimal spec

---

### Example 2: Data Pipeline with Dependencies

**Request:** "Create a data analysis pipeline with DAG dependencies"

**Load Strategy:**
```
SKILL.md (244L) → Need pattern details
  ↓
patterns.md (417L) → Workflow DAG pattern
```

**Context Used:** 661 lines (82% reduction from 3,672)  
**Output:** Complete DAG workflow spec

---

### Example 3: Secure API Integration

**Request:** "Create API integration with custom HTTP tool and PII redaction"

**Load Strategy:**
```
SKILL.md (244L) → Need tools + security
  ↓
tools.md (422L) → HTTP tool config
  ↓
advanced.md (599L) → PII redaction settings
```

**Context Used:** 1,265 lines (66% reduction)  
**Output:** Secure API workflow with custom tool

---

### Example 4: Debug Validation Error

**Request:** "Fix this error: Agent 'xyz' not found in agents"

**Load Strategy:**
```
SKILL.md (244L) → Has common errors
  ↓
troubleshooting.md (744L) → Detailed fix
```

**Context Used:** 988 lines (73% reduction)  
**Output:** Explanation + fix for error

---

## Module Dependency Graph

```
                    SKILL.md (Core)
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    patterns.md      tools.md      advanced.md
         │               │               │
         │               ▼               │
         │       ┌──────────────┐        │
         │       │ Skill Loader │        │
         │       │  (in tools)  │        │
         │       └──────────────┘        │
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
                   examples.md
                    (uses all)
                         │
                         ▼
              troubleshooting.md
               (references all)
                         │
                         ▼
              quick-reference.md
                  (summarizes)
```

**Key:** Arrows show conceptual dependencies, not loading requirements.  
Each module is self-contained and can be loaded independently.

## Comparison: Traditional vs Progressive

### Traditional Monolithic Skill

```
┌─────────────────────────────────────┐
│                                     │
│     ALL CONTENT (3,672 lines)       │
│                                     │
│  - Basic concepts                   │
│  - All 7 patterns                   │
│  - All tools                        │
│  - Advanced features                │
│  - Examples                         │
│  - Troubleshooting                  │
│  - Quick reference                  │
│                                     │
└─────────────────────────────────────┘
         ▲
         │ Load everything every time
         │
    User Request

Context Overhead: 100%
Token Waste: High
Response Time: Slow
```

### Progressive Loading (This Skill)

```
┌──────────────┐
│  SKILL.md    │ ◄── Load first (6.6% of total)
│  (244 lines) │
└──────┬───────┘
       │
       ├─► patterns.md (417L) ─┐
       │                       │
       ├─► tools.md (422L) ────┼─► Load as needed
       │                       │
       ├─► advanced.md (599L) ─┤
       │                       │
       ├─► examples.md (723L) ─┤
       │                       │
       └─► troublesh. (744L) ──┘
           ▲
           │ Load only relevant module(s)
           │
      User Request

Context Overhead: 20-30% typical
Token Waste: Minimal
Response Time: Fast
```

## Performance Metrics

### Token Usage by Query Type

| Query Type | Modules Loaded | Lines | % of Total | Token Estimate |
|-----------|---------------|-------|-----------|----------------|
| Simple | SKILL | 244 | 6.6% | ~700 tokens |
| Pattern | SKILL + patterns | 661 | 18% | ~1,900 tokens |
| Tools | SKILL + tools | 666 | 18% | ~1,900 tokens |
| Advanced | SKILL + advanced | 843 | 23% | ~2,400 tokens |
| Examples | SKILL + examples | 967 | 26% | ~2,800 tokens |
| Debug | SKILL + troublesh. | 988 | 27% | ~2,900 tokens |
| Complex | SKILL + 2-3 modules | 1,200-1,500 | 33-41% | ~3,500-4,500 tokens |
| Comprehensive | All modules | 3,672 | 100% | ~11,000 tokens |

**Average Query:** ~2,500 tokens (vs 11,000 monolithic = 77% reduction)

### Response Quality Maintained

Progressive loading does NOT reduce quality because:
1. ✅ Core skill provides complete navigation map
2. ✅ Agent knows what exists and where
3. ✅ Agent loads exactly what's needed for the task
4. ✅ No irrelevant context to confuse the agent
5. ✅ Focused, targeted knowledge is more effective

## Extensibility

### Adding New Modules

```
strands-spec/
├── SKILL.md (updated with pointer)
├── patterns.md
├── tools.md
├── advanced.md
├── examples.md
├── troubleshooting.md
├── quick-reference.md
└── NEW-MODULE.md ◄── Add new specialized module
```

**Update checklist:**
1. Create new module file
2. Add pointer in SKILL.md navigation section
3. Add entry to README.md module table
4. Update SUMMARY.md metrics
5. Update this ARCHITECTURE.md diagram

### Splitting Existing Modules

If a module grows too large (>1,000 lines):

```
Before:
├── advanced.md (1,500 lines - too big!)

After:
├── advanced-context.md (500 lines)
├── advanced-telemetry.md (500 lines)
└── advanced-security.md (500 lines)

Update SKILL.md pointers:
- Load advanced-context.md for context management
- Load advanced-telemetry.md for OpenTelemetry
- Load advanced-security.md for PII/network security
```

## Conclusion

This architecture achieves:
- ✅ **80%+ reduction** in typical context usage
- ✅ **Maintained quality** through targeted loading
- ✅ **Easy maintenance** via modular structure
- ✅ **Scalability** for future additions
- ✅ **User-friendly** clear navigation

Perfect example of Claude Code Agent Skills progressive loading best practices.

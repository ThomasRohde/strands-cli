# Copilot Customization for Code Reviews

This guide shows how to configure GitHub Copilot to assist with systematic code reviews using the `REVIEW.md` plan.

## Overview

We'll use **four Copilot customization methods** to make code reviews efficient:

1. **Custom Instructions** - Auto-apply review standards to all chat requests
2. **Prompt Files** - Reusable review commands for each layer
3. **Custom Agents** - Specialized review agents (security, performance, comments)
4. **Settings** - Code review-specific instructions

---

## Setup Instructions

### Step 1: Enable Required Settings

Add to your `.vscode/settings.json`:

```json
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "chat.promptFiles": true,
  "chat.instructionsFilesLocations": [
    ".github/instructions"
  ],
  "chat.promptFilesLocations": [
    ".github/prompts"
  ]
}
```

### Step 2: Create Review Instructions File

The file structure will be:
```
.github/
├── copilot-instructions.md          # Already exists (project standards)
├── instructions/
│   └── code-review.instructions.md  # Code review standards
├── prompts/
│   ├── review-layer.prompt.md       # Review a specific layer
│   ├── review-unit.prompt.md        # Review a specific unit
│   ├── review-checklist.prompt.md   # Run checklist for current file
│   └── review-comments.prompt.md    # Review code comments
└── agents/
    ├── security-reviewer.agent.md   # Security-focused agent
    ├── performance-reviewer.agent.md # Performance-focused agent
    └── comment-reviewer.agent.md    # Documentation-focused agent
```

---

## File Templates

### 1. Code Review Instructions

**File**: `.github/instructions/code-review.instructions.md`

```markdown
---
name: Code Review Standards
description: Standards and guidelines for reviewing strands-cli code
applyTo: "**/*.py"
---

# Code Review Standards for Strands CLI

When reviewing code, always reference the [REVIEW.md](../../REVIEW.md) file for:
- Architectural layer structure (9 layers)
- Cross-cutting concerns (security, performance, error handling, testing, comments)
- Review checklists for each component type
- Coverage targets by layer

## Review Principles
1. **Bottom-Up Review** - Check foundation layers before dependent layers
2. **Concern Separation** - Each review focuses on single architectural concern
3. **Test Coverage** - Review implementation alongside tests
4. **Cross-Cutting** - Apply security, performance, error handling, and comment checklists
5. **Exit Codes** - Always use constants from exit_codes.py (never generic exit(1))

## Strands CLI Specific Rules
- **Python 3.12+ only** - Use modern type hints (str | None, not Optional[str])
- **Pydantic v2** - All models must be BaseModel with strict validation
- **Mypy strict** - No type: ignore without comments
- **Async patterns** - Single event loop per workflow (no asyncio.run in executors)
- **Agent caching** - Always use AgentCache.get_or_build_agent() (not build_agent)
- **Model pooling** - Rely on @lru_cache via create_model()
- **Line length** - 100 chars max (ruff configured)

## What to Look For
- Missing docstrings (all public classes/functions)
- Type annotations incomplete or using Any without justification
- Security issues (path traversal, code injection, secrets in logs)
- Performance issues (agent cache misses, redundant model clients)
- Error handling (wrong exit codes, generic exceptions)
- Test coverage gaps (target ≥85%, critical paths 100%)
- Code comments (explain "why" not "what")
- Stale TODOs or commented-out code
```

---

### 2. Layer Review Prompt

**File**: `.github/prompts/review-layer.prompt.md`

```markdown
---
name: review-layer
description: Review a complete architectural layer from REVIEW.md
argument-hint: "layer number (1-9) or name (e.g., 'foundation', 'execution')"
agent: agent
tools: ['search', 'fetch', 'usages']
---

# Layer Review Task

You are reviewing **${input:layer}** from the strands-cli codebase according to [REVIEW.md](../../REVIEW.md).

## Steps to Execute:

1. **Identify Layer Files**
   - Read REVIEW.md to find which files belong to this layer
   - List all source files and corresponding test files

2. **Apply Layer-Specific Checklist**
   - Use the review checklist from REVIEW.md for this layer
   - Check all items in the layer's review focus

3. **Run Cross-Cutting Checks**
   - Code Comments & Documentation (docstrings, inline comments, TODOs)
   - Security (input validation, secrets, code injection)
   - Performance (caching, async patterns, memory)
   - Error Handling (exit codes, exceptions, retry logic)
   - Testing (coverage, fixtures, mocking)

4. **Generate Review Report**
   Use the review output template from REVIEW.md:
   - Summary
   - Checklist results (✓/✗/⚠)
   - Issues found (with severity, location, impact, recommendation)
   - Positive observations
   - Recommendations (prioritized P0/P1/P2)
   - Test coverage gaps
   - Next steps

## Output Format
Generate a Markdown document following the "Review Output Template" section in REVIEW.md.

Include:
- File paths reviewed
- Pass/fail for each checklist item
- Specific line numbers for issues
- Actionable recommendations
```

---

### 3. Unit Review Prompt

**File**: `.github/prompts/review-unit.prompt.md`

```markdown
---
name: review-unit
description: Review a specific review unit (e.g., Layer 1.1, Layer 5.2)
argument-hint: "unit ID (e.g., '1.1', '5.2') from REVIEW.md"
agent: agent
tools: ['search', 'usages']
---

# Review Unit: ${input:unit}

Review the specific unit **${input:unit}** from [REVIEW.md](../../REVIEW.md).

## Process:

1. **Locate Unit in REVIEW.md**
   - Find the unit definition (e.g., "1.1 Type System & Models")
   - Read the "Review Focus" checklist
   - Note the "Red Flags" to watch for

2. **Read Source Files**
   - Read all files listed in the unit
   - Read corresponding test files

3. **Execute Checklist**
   - Go through each item in "Review Focus"
   - Mark each as ✓ (pass), ✗ (fail), or ⚠ (needs attention)

4. **Check Red Flags**
   - Specifically look for each red flag mentioned
   - Document any found with severity

5. **Cross-Cutting Review**
   - Apply comment quality checklist
   - Apply security checklist
   - Apply performance checklist
   - Apply error handling checklist
   - Apply testing checklist

6. **Generate Findings**
   Format output using the template from REVIEW.md section "Review Output Template"

## Focus on Actionable Output
- Specific line numbers for issues
- Severity ratings (Critical/High/Medium/Low)
- Clear recommendations for fixes
- Priority rankings (P0/P1/P2)
```

---

### 4. Checklist Review Prompt

**File**: `.github/prompts/review-checklist.prompt.md`

```markdown
---
name: review-checklist
description: Run review checklists on the current file/selection
agent: agent
tools: ['search']
---

# Review Checklist for ${fileBasename}

Run comprehensive review checklists on **${file}** according to [REVIEW.md](../../REVIEW.md).

## Checklists to Apply:

### 1. Code Comments & Documentation
- [ ] All public classes/functions have docstrings (Google/NumPy style)
- [ ] Docstrings match current implementation (no stale docs)
- [ ] All parameters documented, edge cases explained
- [ ] Inline comments explain "why" not "what"
- [ ] Complex algorithms explained
- [ ] Security considerations noted
- [ ] Performance optimizations explained
- [ ] TODOs are actionable and tracked
- [ ] No stale TODOs from completed work
- [ ] Type annotations complete (mypy strict compliance)
- [ ] Module-level docstring explains purpose
- [ ] No commented-out code (delete or explain)
- [ ] No obvious comments (e.g., `# increment counter` for `counter += 1`)
- [ ] No misleading comments (out of sync with code)

### 2. Security
- [ ] All user inputs validated
- [ ] File paths sanitized (no ../ attacks)
- [ ] No eval(), exec(), or unsafe deserialization
- [ ] No secrets in logs, error messages, or traces
- [ ] PII redaction enabled where needed
- [ ] Tool execution is allowlisted
- [ ] Condition evaluation uses restricted builtins

### 3. Performance
- [ ] Agent caching used (AgentCache.get_or_build_agent)
- [ ] Model client pooling via @lru_cache
- [ ] max_parallel enforced with semaphores
- [ ] No unbounded memory growth
- [ ] Single event loop per workflow
- [ ] No expensive operations in hot paths

### 4. Error Handling
- [ ] Correct exit codes from exit_codes.py (not generic exit(1))
- [ ] Error messages are actionable and user-friendly
- [ ] Domain-specific exceptions used
- [ ] Stack traces preserve context
- [ ] Retry logic with exponential backoff
- [ ] Fail-fast or graceful degradation as appropriate

### 5. Testing
- [ ] Unit tests for core logic
- [ ] Integration tests for end-to-end workflows
- [ ] External dependencies mocked
- [ ] Reusable fixtures in conftest.py
- [ ] Coverage ≥85% overall, critical paths 100%
- [ ] Async tests use pytest-asyncio correctly
- [ ] Negative tests for expected failures

## Output Format
For each checklist item:
- ✓ Item passed
- ✗ Item failed (include line number and explanation)
- ⚠ Item needs attention (include suggestion)

Summarize findings with severity and priority.
```

---

### 5. Comment Review Prompt

**File**: `.github/prompts/review-comments.prompt.md`

```markdown
---
name: review-comments
description: Review code comments and documentation quality
agent: comment-reviewer
tools: ['search']
---

# Comment & Documentation Review: ${fileBasename}

Review the quality of comments and documentation in **${file}**.

## Review Criteria from REVIEW.md:

### Docstrings
- Format: Google/NumPy style with parameters, returns, raises
- Accuracy: Match current implementation
- Completeness: All parameters documented, edge cases explained

### Inline Comments
- Explain "why" not "what"
- Complex algorithms explained
- Non-obvious design decisions justified
- Security considerations noted
- Performance optimizations explained

### TODOs/FIXMEs
- Every TODO has context (why deferred, what's needed)
- FIXMEs have issue numbers or remediation plan
- No stale TODOs from completed work

### Type Annotations
- All functions fully annotated (mypy strict compliance)
- Return types specified
- Complex types documented

### Module-level Docstrings
- Purpose statement
- Key classes/functions exported
- Dependencies/integration points

### Anti-patterns to Flag
❌ Commented-out code (delete or explain)
❌ Obvious comments: `# increment counter` for `counter += 1`
❌ Misleading comments (out of sync with code)
❌ Excessive comments (self-documenting code is better)

## Questions to Answer
- Can a new developer understand the code without asking questions?
- Do comments explain *why* decisions were made?
- Are edge cases and error conditions documented?
- Would you understand this code 6 months from now?

## Output
List each issue found with:
- Line number
- Issue type (missing docstring, obvious comment, etc.)
- Severity (High/Medium/Low)
- Suggested fix
```

---

### 6. Security Reviewer Agent

**File**: `.github/agents/security-reviewer.agent.md`

```markdown
---
name: Security Reviewer
description: Specialized agent for security-focused code review
tools: ['search', 'usages']
model: Claude Sonnet 4
handoffs:
  - label: Review Performance
    agent: performance-reviewer
    prompt: Now review the same files for performance issues.
    send: false
---

# Security Review Agent

You are a security-focused code reviewer for the strands-cli project. Use [REVIEW.md](../../REVIEW.md) security checklist.

## Primary Focus Areas

### Input Validation
- All user inputs validated (schemas, allowlists)
- YAML/JSON parsing uses safe methods
- Template rendering is sandboxed
- File paths validated against traversal attacks

### Code Injection Prevention
- No eval() or exec() usage
- Graph conditions use restricted builtins only
- Python tool execution is allowlisted
- Template variables properly escaped

### Secrets & Credentials
- No secrets in logs, error messages, or traces
- API keys from environment variables only
- Secrets never appear in span attributes
- PII redaction enabled where needed

### Tool Execution Safety
- Python tools allowlisted: strands_tools.{http_request,file_read,file_write,calculator,current_time}
- file_write requires user consent (--bypass-tool-consent flag documented)
- HTTP executors have timeout limits
- Path traversal protection in file operations

### Strands CLI Specific Threats
- Skills with executable=true blocked (metadata-only in MVP)
- MCP tools properly sandboxed
- Guardrails enforcement (parse, don't execute yet)
- OTEL trace PII redaction

## Review Process
1. Check each security checklist item from REVIEW.md
2. Flag violations with severity: Critical/High/Medium/Low
3. Provide specific remediation for each issue
4. Reference security.md for threat model context

## Output Format
- **Critical**: Exploitable vulnerabilities (immediate fix required)
- **High**: Significant security gaps (fix before release)
- **Medium**: Defense-in-depth improvements
- **Low**: Best practice enhancements
```

---

### 7. Performance Reviewer Agent

**File**: `.github/agents/performance-reviewer.agent.md`

```markdown
---
name: Performance Reviewer
description: Specialized agent for performance-focused code review
tools: ['search', 'usages']
model: Claude Sonnet 4
handoffs:
  - label: Review Comments
    agent: comment-reviewer
    prompt: Now review the code comments and documentation.
    send: false
---

# Performance Review Agent

You are a performance-focused code reviewer for the strands-cli project. Use [REVIEW.md](../../REVIEW.md) performance checklist.

## Primary Focus Areas

### Agent Caching
- **Expected**: Agents reused across steps/tasks via AgentCache
- **Anti-pattern**: Direct build_agent() calls
- **Verification**: Check AgentCache.get_or_build_agent() usage
- **Target**: 10-step chain with same runtime → 1 model client (not 10)

### Model Client Pooling
- **Expected**: Model clients cached via @lru_cache on create_model()
- **Anti-pattern**: Creating BedrockModel/OllamaModel/OpenAIModel directly
- **Verification**: RuntimeConfig → _create_model_cached flow
- **Target**: 1 model client per unique runtime config

### Concurrency Control
- **Expected**: max_parallel enforced via semaphore
- **Anti-pattern**: Unbounded asyncio.gather() calls
- **Verification**: Semaphore creation and acquire/release
- **Target**: Resource limits respected

### Memory Management
- **Expected**: No unbounded growth (trace spans FIFO eviction)
- **Anti-pattern**: Infinite lists, unclosed HTTP clients
- **Verification**: AgentCache.close(), trace collector limits
- **Target**: <5MB memory per 1000 spans

### Async Patterns
- **Expected**: Single event loop per workflow (asyncio.run in CLI only)
- **Anti-pattern**: asyncio.run() inside executors
- **Verification**: Executor signatures use async def, await (not asyncio.run)
- **Target**: All executors use single event loop from CLI

### Hot Path Optimization
- **Expected**: Expensive operations avoided in loops
- **Anti-pattern**: Repeated schema validation, file I/O in tight loops
- **Verification**: Check for schema precompilation, file caching
- **Target**: Minimal overhead per step (<5%)

## Review Process
1. Check each performance item from REVIEW.md
2. Measure against targets (agent cache hit rate, model reuse, etc.)
3. Flag violations with impact: Critical/High/Medium/Low
4. Provide specific optimization recommendations

## Output Format
- **Critical**: Performance bugs (memory leaks, infinite loops)
- **High**: Significant inefficiency (redundant work, cache misses)
- **Medium**: Optimization opportunities
- **Low**: Micro-optimizations
```

---

### 8. Comment Reviewer Agent

**File**: `.github/agents/comment-reviewer.agent.md`

```markdown
---
name: Comment Reviewer
description: Specialized agent for documentation and comment quality
tools: ['search']
model: Claude Sonnet 4
---

# Comment & Documentation Review Agent

You are a documentation-focused code reviewer for the strands-cli project. Use [REVIEW.md](../../REVIEW.md) comment quality checklist.

## Primary Focus Areas

### Docstrings (Google/NumPy Style)
- **Required**: All public classes, functions, methods
- **Format**: Parameters, returns, raises sections
- **Accuracy**: Match current implementation (no stale docs)
- **Completeness**: All parameters documented, edge cases explained

### Inline Comments
- **Principle**: Explain "why" not "what"
- **Good**: "Agent caching prevents redundant builds (performance)"
- **Bad**: "Increment counter" for `counter += 1`
- **Required for**:
  - Complex algorithms (e.g., topological sort)
  - Non-obvious design decisions (e.g., @lru_cache usage)
  - Security considerations (e.g., restricted builtins)
  - Performance optimizations (e.g., semaphore control)

### TODO/FIXME Comments
- **Required**: Context (why deferred, what's needed)
- **Good**: `# TODO(Phase 3): Add AWS Secrets Manager (see ARK_PRD.md)`
- **Bad**: `# TODO: fix this`
- **Check**: No stale TODOs from completed work

### Type Annotations
- **Required**: All functions (mypy strict mode)
- **Format**: Return types specified (not just parameters)
- **Complex types**: Document structure in comment
  - Example: `dict[str, Any]  # {"step_index": 0, "response": "...", "tokens": 100}`

### Module-level Docstrings
- **Required**: Every module
- **Content**:
  - Module's role in architecture
  - Key classes/functions exported
  - Dependencies/integration points

## Anti-patterns to Flag
❌ Commented-out code (delete or explain why kept)
❌ Obvious comments that restate code
❌ Misleading comments (out of sync)
❌ Excessive comments (prefer self-documenting code)

## Review Questions
1. Can a new developer understand the code without asking?
2. Do comments explain *why* decisions were made?
3. Are edge cases and error conditions documented?
4. Would you understand this code 6 months from now?

## Output Format
For each issue:
- **Line number**
- **Issue type**: missing-docstring, obvious-comment, stale-todo, etc.
- **Severity**: High (missing critical docs) / Medium (quality issue) / Low (style)
- **Suggested fix**: Specific improvement
```

---

## Usage Guide

### Basic Review Workflow

#### 1. Review a Specific Layer
```
In chat: /review-layer foundation
In chat: /review-layer execution
In chat: /review-layer 5
```

#### 2. Review a Specific Unit
```
In chat: /review-unit 1.1
In chat: /review-unit 5.2
```

#### 3. Review Current File
```
In chat: /review-checklist
```

#### 4. Review Comments Only
```
In chat: /review-comments
```

### Using Specialized Agents

#### Security Review
1. Switch to `@security-reviewer` agent
2. Ask: "Review src/strands_cli/exec/graph.py for security issues"
3. Review output, then click "Review Performance" handoff button

#### Performance Review
1. Switch to `@performance-reviewer` agent
2. Ask: "Review src/strands_cli/runtime/strands_adapter.py for performance issues"
3. Review output, then click "Review Comments" handoff button

#### Comment Review
1. Switch to `@comment-reviewer` agent
2. Ask: "Review documentation in src/strands_cli/types.py"

### Advanced Workflows

#### Full Layer Review (Sequential Agents)
```
1. /review-layer 5  (comprehensive layer review)
2. @security-reviewer: Focus on security in Layer 5
3. Handoff → @performance-reviewer
4. Handoff → @comment-reviewer
5. Document findings in REVIEW_FINDINGS.md
```

#### Targeted File Review (Parallel Checks)
```
1. Open file in editor
2. Run in parallel:
   - /review-checklist
   - @security-reviewer: Review this file
   - @performance-reviewer: Review this file
   - @comment-reviewer: Review this file
3. Combine results
```

---

## Tips for Effective Reviews

### 1. Reference REVIEW.md Explicitly
Always mention REVIEW.md in prompts to load context:
```
"Review types.py according to Layer 1.1 checklist in REVIEW.md"
```

### 2. Use File Selection Context
Select code before running prompts:
```
Select function → /review-checklist
```

### 3. Combine Prompts and Instructions
Instructions auto-apply, prompts are triggered on-demand:
```
code-review.instructions.md → Always active for *.py
review-layer.prompt.md → Trigger with /review-layer
```

### 4. Leverage Handoffs for Workflows
Security → Performance → Comments provides comprehensive coverage:
```
@security-reviewer → Click "Review Performance" → Click "Review Comments"
```

### 5. Document Findings Incrementally
After each review unit, add to tracking file:
```
In chat: "Add these findings to REVIEW_FINDINGS.md under Layer 5.2"
```

---

## Automation Scripts

Run these before reviewing to prepare context:

```powershell
# Generate coverage report (reference in review)
.\scripts\dev.ps1 test-cov

# Find TODOs (review for staleness)
rg "TODO|FIXME|XXX|HACK" src/

# Find missing docstrings
rg "^(class|def|async def) " src/ | rg -v '"""'

# Find commented-out code
rg "^\s*#\s*(def|class|import|from)" src/

# Check mypy compliance
uv run mypy src
```

---

## Tracking Review Progress

Create `.github/REVIEW_PROGRESS.md`:

```markdown
# Code Review Progress

**Started**: 2025-11-14
**Reviewer**: [Your Name]
**Goal**: Complete all 9 layers per REVIEW.md

## Layer Status

- [ ] Layer 1: Foundation & Core Types
  - [ ] 1.1 Type System & Models
  - [ ] 1.2 JSON Schema Validation
  - [ ] 1.3 Configuration & Settings
- [ ] Layer 2: Data Loading & Templating
  - [ ] 2.1 YAML/JSON Loading
- [ ] Layer 3: Capability Checking
  - [ ] 3.1 Capability Checker
- [ ] Layer 4: Runtime & Agent Management
  - [ ] 4.1 Provider Adapters
  - [ ] 4.2 Strands Agent Adapter
  - [ ] 4.3 Tool Execution
- [ ] Layer 5: Execution Patterns
  - [ ] 5.1 Single-Agent Executor
  - [ ] 5.2 Chain Pattern
  - [ ] 5.3 Workflow/DAG Pattern
  - [ ] 5.4 Routing Pattern
  - [ ] 5.5 Parallel Pattern
  - [ ] 5.6 Evaluator-Optimizer Pattern
  - [ ] 5.7 Orchestrator-Workers Pattern
  - [ ] 5.8 Graph Pattern
  - [ ] 5.9 Cross-Pattern Utilities
- [ ] Layer 6: Session & State Management
  - [ ] 6.1 Session Models & Storage
  - [ ] 6.2 Resume Logic
- [ ] Layer 7: Observability & Debugging
  - [ ] 7.1 OpenTelemetry Integration
  - [ ] 7.2 Structured Logging
- [ ] Layer 8: CLI & User Interface
  - [ ] 8.1 CLI Commands
  - [ ] 8.2 Artifact Output
  - [ ] 8.3 Presets & UX
- [ ] Layer 9: Python API
  - [ ] 9.1 Workflow Execution API
  - [ ] 9.2 Builder API

## Issues Found

### Critical (P0)
- None yet

### High (P1)
- None yet

### Medium (P2)
- None yet

### Low
- None yet

## Coverage Gaps Identified
- CLI commands (__main__.py): 58% (target: 70%+)
- Capability checker: 63% (target: 80%+)
```

---

## Settings for Code Review

Add to workspace `.vscode/settings.json`:

```json
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "chat.promptFiles": true,
  "chat.instructionsFilesLocations": [".github/instructions"],
  "chat.promptFilesLocations": [".github/prompts"],
  
  "github.copilot.chat.reviewSelection.instructions": [
    { "file": "REVIEW.md" },
    { "text": "Apply relevant checklists from REVIEW.md. Reference line numbers and provide specific, actionable feedback." }
  ],
  
  "chat.promptFilesRecommendations": true,
  
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true,
    "**/.ruff_cache": true
  }
}
```

---

## Summary

This Copilot customization setup provides:

✅ **Automated Context** - Review standards auto-apply via instructions  
✅ **Reusable Commands** - Prompt files for common review tasks  
✅ **Specialized Agents** - Security, performance, and comment reviewers  
✅ **Guided Workflows** - Handoffs between agents for comprehensive coverage  
✅ **Consistent Output** - All reviews follow REVIEW.md template  
✅ **Incremental Progress** - Track completion in REVIEW_PROGRESS.md  

Use this setup to systematically review the entire strands-cli codebase with AI assistance while maintaining rigor and consistency.

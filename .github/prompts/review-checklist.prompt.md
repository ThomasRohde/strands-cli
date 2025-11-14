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

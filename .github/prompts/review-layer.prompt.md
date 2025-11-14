---
name: review-layer
description: Review a complete architectural layer from REVIEW.md
argument-hint: "layer number (1-9) or name (e.g., 'foundation', 'execution')"
agent: agent
tools: ['edit', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'Context7/*', 'Ref tools/*', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'openSimpleBrowser', 'fetch', 'githubRepo', 'extensions', 'todos', 'runSubagent', 'runTests']
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

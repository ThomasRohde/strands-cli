---
name: review-comments
description: Review code comments and documentation quality
agent: agent
tools: ['edit', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'Ref tools/*', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'openSimpleBrowser', 'fetch', 'githubRepo', 'extensions', 'todos', 'runSubagent', 'runTests']
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

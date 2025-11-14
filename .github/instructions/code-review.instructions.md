---
name: code-review-standards
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

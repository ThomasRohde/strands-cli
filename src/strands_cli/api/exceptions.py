"""Exceptions for the fluent builder API.

This module defines custom exceptions for builder validation errors.
All exceptions provide actionable error messages to help developers
fix configuration issues quickly.
"""


class BuildError(Exception):
    """Raised when workflow builder validation fails.

    BuildError indicates that the workflow configuration is invalid
    and cannot be built into a valid Spec. Common causes:

    - Missing required configuration (runtime, agents, pattern)
    - Invalid provider or pattern type
    - Agent referenced in step but not defined
    - Template syntax errors
    - Circular dependencies in workflow tasks
    - Invalid parameter values (negative timeouts, etc.)

    Error messages include:
    - Clear description of what's wrong
    - Suggestions for similar values (e.g., agent names)
    - Remediation instructions

    Example:
        >>> try:
        ...     builder.chain().step("unknown_agent", "input").build()
        ... except BuildError as e:
        ...     print(e)
        Agent 'unknown_agent' not found. Did you mean: 'researcher'?
        Use .agent('unknown_agent', ...) to define it before referencing in .step().
    """

    pass

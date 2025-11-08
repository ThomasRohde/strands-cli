"""Exit codes for the Strands CLI.

Follows Unix conventions for consistent error reporting across different
failure modes. These codes allow shell scripts and CI/CD pipelines to
distinguish between validation errors, runtime failures, and unsupported features.

Usage:
    Always use named constants instead of raw integers:

    from strands_cli.exit_codes import EX_SCHEMA, EX_OK
    sys.exit(EX_SCHEMA)  # GOOD
    sys.exit(3)  # BAD - unclear meaning

Exit Code Categories:
    0: Success
    2-3: User/input errors (bad flags, invalid spec)
    10-18: Runtime errors (provider failures, unsupported features)
    70: System/unexpected errors
"""

# Success
EX_OK = 0
"""Successful execution."""

# User errors
EX_USAGE = 2
"""Command-line usage error (bad flags, missing file, etc.)."""

EX_SCHEMA = 3
"""JSON Schema validation error.

The workflow spec doesn't conform to the strands-workflow.schema.json.
Validation uses JSON Schema Draft 2020-12 and reports precise error
locations using JSONPointer paths.
"""

# Runtime errors
EX_RUNTIME = 10
"""Provider/model/tool runtime failure (Bedrock error, tool crash, etc.)."""

EX_IO = 12
"""Artifact write or I/O error (can't create directory, write file, etc.)."""

EX_UNSUPPORTED = 18
"""Feature present in spec but not supported in current implementation.

When this code is returned, a detailed Markdown remediation report is written
to the artifacts directory. The report includes:
- JSONPointer locations of unsupported features
- Reason each feature is unsupported
- Specific remediation steps
- Minimal working example

This allows graceful degradation: parse the full schema but reject unsupported
features with actionable guidance rather than silently ignoring them.
"""

EX_BUDGET_EXCEEDED = 19
"""Token budget exhausted during workflow execution.

The workflow exceeded the configured `budgets.max_tokens` limit and was aborted
to prevent cost overruns. This exit code is returned when:
- Cumulative token usage reaches 100% of max_tokens
- Budget enforcement is enabled (budgets.max_tokens is set)

A warning is logged at the configured threshold (default 80%) before abort.
If context compaction is enabled, it will be triggered automatically on warning
to attempt extending the workflow runway.

To resolve:
- Increase budgets.max_tokens if the workflow legitimately needs more tokens
- Enable context_policy.compaction to reduce context size during execution
- Optimize prompts and agent responses to use fewer tokens
- Split complex workflows into multiple smaller workflows
"""

# System errors
EX_UNKNOWN = 70
"""Unexpected exception not handled by specific error codes.

Indicates a bug in the CLI or an unhandled edge case. When this occurs,
use --verbose to see the full traceback and report the issue.
"""

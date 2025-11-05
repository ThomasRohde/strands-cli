"""Utility functions and context managers for strands-cli.

Provides common utilities used across the codebase.
"""

import io
import sys
from collections.abc import Generator
from contextlib import contextmanager

from rich.console import Console


@contextmanager
def capture_and_display_stdout(prefix: str = "") -> Generator[None, None, None]:
    """Context manager to capture stdout and display it with Rich formatting.

    Captures stdout (e.g., LLM streaming responses) and displays it using Rich
    with optional dimmed formatting to distinguish from structured logs.
    This preserves the visual progress feedback while keeping output clean.

    Args:
        prefix: Optional prefix to add before captured output (e.g., agent name)

    Example:
        with capture_and_display_stdout(prefix="[Agent] "):
            response = await agent.invoke_async(prompt)
            # Streaming output appears with prefix/formatting

    Yields:
        None
    """
    console = Console()
    captured = io.StringIO()
    original_stdout = sys.stdout

    try:
        # Redirect stdout to our StringIO buffer
        sys.stdout = captured
        yield
    finally:
        # Restore original stdout
        sys.stdout = original_stdout

        # Get captured content
        content = captured.getvalue()

        # Display captured content with Rich formatting if non-empty
        if content.strip():
            # Display with dimmed style to distinguish from logs
            console.print(f"[dim]{prefix}{content.rstrip()}[/dim]")

        captured.close()

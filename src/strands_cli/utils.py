"""Utility functions and context managers for strands-cli.

Provides common utilities used across the codebase.
"""

import io
from collections.abc import Generator
from contextlib import contextmanager, redirect_stdout


@contextmanager
def suppress_stdout() -> Generator[None, None, None]:
    """Context manager to suppress stdout during execution.

    Redirects stdout to StringIO to prevent unwanted console output
    from third-party libraries (e.g., Strands SDK agent responses).
    Uses contextlib.redirect_stdout for proper async compatibility.

    Example:
        with suppress_stdout():
            response = await agent.invoke_async(prompt)
            # Agent's stdout is suppressed; only structured logs appear

    Yields:
        None
    """
    with redirect_stdout(io.StringIO()):
        yield

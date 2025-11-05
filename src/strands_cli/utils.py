"""Utility functions and context managers for strands-cli.

Provides common utilities used across the codebase.
"""

import io
import sys
from collections.abc import Generator
from contextlib import contextmanager


class _TeeStream:
    """Stream wrapper that writes to both original stream and a buffer.

    This allows us to capture stdout while still allowing other code
    (like Rich and structlog) to write to the original stream safely.
    """

    def __init__(self, original_stream: object, buffer: io.StringIO):
        self.original_stream = original_stream
        self.buffer = buffer

    def write(self, text: str) -> int:
        # Write to buffer for capture
        self.buffer.write(text)
        # Also write to original stream for immediate streaming display
        if hasattr(self.original_stream, 'write'):
            self.original_stream.write(text)
        return len(text)

    def flush(self) -> None:
        self.buffer.flush()
        # Also flush the original stream
        if hasattr(self.original_stream, 'flush'):
            self.original_stream.flush()

    def __getattr__(self, name: str) -> object:
        # Delegate all other attributes to the original stream
        return getattr(self.original_stream, name)


@contextmanager
def capture_and_display_stdout(prefix: str = "") -> Generator[None, None, None]:
    """Context manager to capture stdout while allowing normal console operations.

    Uses a tee-like approach to capture stdout (e.g., LLM streaming responses)
    without breaking Rich Console, structlog, or other stdout users.
    The captured output is displayed as it's generated (streaming effect).

    Args:
        prefix: Optional prefix to add before captured output (not currently used
                since we're displaying in real-time)

    Example:
        with capture_and_display_stdout():
            response = await agent.invoke_async(prompt)
            # Streaming output appears in real-time

    Yields:
        None
    """
    captured = io.StringIO()
    original_stdout = sys.stdout

    try:
        # Use tee stream to capture without breaking other stdout users
        sys.stdout = _TeeStream(original_stdout, captured)
        yield
    finally:
        # Restore original stdout FIRST before any operations
        sys.stdout = original_stdout
        # Close the buffer
        captured.close()

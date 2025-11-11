"""Tests for utility functions in utils.py.

Tests the capture_and_display_stdout context manager and _TeeStream.
"""

import io
import sys

from strands_cli.utils import capture_and_display_stdout


def test_capture_and_display_stdout_basic() -> None:
    """Test basic stdout capture and display."""
    with capture_and_display_stdout():
        print("test output")

    # If we get here without exceptions, the basic flow works


def test_capture_and_display_stdout_restores_stdout() -> None:
    """Test that original stdout is restored after context."""
    original_stdout = sys.stdout

    with capture_and_display_stdout():
        print("test output")

    # Verify stdout was restored
    assert sys.stdout == original_stdout


def test_capture_and_display_stdout_with_exception() -> None:
    """Test that stdout is restored even when exception occurs."""
    original_stdout = sys.stdout

    try:
        with capture_and_display_stdout():
            print("before exception")
            raise ValueError("test exception")
    except ValueError:
        pass

    # Verify stdout was restored despite exception
    assert sys.stdout == original_stdout


def test_capture_and_display_stdout_multiple_prints() -> None:
    """Test capturing multiple print statements."""
    with capture_and_display_stdout():
        print("line 1")
        print("line 2")
        print("line 3")

    # Should not raise any exceptions


def test_capture_and_display_stdout_with_prefix() -> None:
    """Test using prefix parameter (currently unused but accepted)."""
    with capture_and_display_stdout(prefix="[PREFIX] "):
        print("test output")

    # Should not raise any exceptions


def test_tee_stream_write() -> None:
    """Test _TeeStream write method."""
    from strands_cli.utils import _TeeStream

    original = io.StringIO()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)

    # Write some text
    result = tee.write("test")

    # Should return length of text
    assert result == 4

    # Both streams should have the text
    assert buffer.getvalue() == "test"
    assert original.getvalue() == "test"


def test_tee_stream_flush() -> None:
    """Test _TeeStream flush method."""
    from strands_cli.utils import _TeeStream

    original = io.StringIO()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)
    tee.write("test")

    # Should not raise
    tee.flush()


def test_tee_stream_with_closed_buffer() -> None:
    """Test _TeeStream handles closed buffer gracefully."""
    from strands_cli.utils import _TeeStream

    original = io.StringIO()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)

    # Close the buffer
    buffer.close()

    # Writing should still work (writes to original)
    result = tee.write("test after close")

    # Should still return length
    assert result == len("test after close")

    # Original should have the text
    assert "test after close" in original.getvalue()


def test_tee_stream_getattr() -> None:
    """Test _TeeStream delegates unknown attributes to original stream."""
    from strands_cli.utils import _TeeStream

    original = io.StringIO()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)

    # Access attribute from original stream
    assert hasattr(tee, "getvalue")


def test_tee_stream_flush_with_closed_buffer() -> None:
    """Test _TeeStream flush with closed buffer doesn't crash."""
    from strands_cli.utils import _TeeStream

    original = io.StringIO()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)
    buffer.close()

    # Should not raise
    tee.flush()


def test_capture_and_display_stdout_nested() -> None:
    """Test nested context managers restore stdout correctly."""
    original_stdout = sys.stdout

    with capture_and_display_stdout():
        print("outer 1")

        with capture_and_display_stdout():
            print("inner")

        print("outer 2")

    # Verify stdout was restored
    assert sys.stdout == original_stdout


def test_tee_stream_without_write_method() -> None:
    """Test _TeeStream with original stream that doesn't have write method."""
    from strands_cli.utils import _TeeStream

    # Create a mock stream without write method
    class NoWriteStream:
        pass

    original = NoWriteStream()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)

    # Should not crash even if original doesn't have write
    result = tee.write("test")
    assert result == 4


def test_tee_stream_without_flush_method() -> None:
    """Test _TeeStream with original stream that doesn't have flush method."""
    from strands_cli.utils import _TeeStream

    # Create a mock stream without flush method
    class NoFlushStream:
        def write(self, text: str) -> None:
            pass

    original = NoFlushStream()
    buffer = io.StringIO()

    tee = _TeeStream(original, buffer)

    # Should not crash even if original doesn't have flush
    tee.flush()

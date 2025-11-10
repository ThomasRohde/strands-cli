"""Test version information."""

import strands_cli


def test_version() -> None:
    """Test that version is defined."""
    assert strands_cli.__version__ == "0.3.0"

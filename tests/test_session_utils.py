"""Tests for session utility functions.

Tests generate_session_id, compute_spec_hash, now_iso8601, and load_spec_content.
"""

from pathlib import Path

import pytest

from strands_cli.session.utils import (
    compute_spec_hash,
    generate_session_id,
    load_spec_content,
    now_iso8601,
)


def test_generate_session_id_format():
    """Test session ID is valid UUID4 format."""
    session_id = generate_session_id()

    # UUID4 format: 8-4-4-4-12 hex digits with hyphens
    assert len(session_id) == 36
    assert session_id.count("-") == 4

    # Verify parseable as UUID
    import uuid

    parsed = uuid.UUID(session_id)
    assert str(parsed) == session_id


def test_generate_session_id_uniqueness():
    """Test session IDs are unique."""
    ids = [generate_session_id() for _ in range(100)]

    # All should be unique
    assert len(set(ids)) == 100


def test_compute_spec_hash(tmp_path: Path):
    """Test spec hash computation."""
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("version: 0\nname: test", encoding="utf-8")

    hash1 = compute_spec_hash(spec_file)

    # SHA256 hex digest is 64 characters
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)

    # Same file = same hash
    hash2 = compute_spec_hash(spec_file)
    assert hash1 == hash2


def test_compute_spec_hash_detects_changes(tmp_path: Path):
    """Test spec hash changes when content changes."""
    spec_file = tmp_path / "test.yaml"

    spec_file.write_text("version: 0\nname: test1", encoding="utf-8")
    hash1 = compute_spec_hash(spec_file)

    spec_file.write_text("version: 0\nname: test2", encoding="utf-8")
    hash2 = compute_spec_hash(spec_file)

    assert hash1 != hash2


def test_compute_spec_hash_nonexistent_file(tmp_path: Path):
    """Test compute_spec_hash raises for non-existent file."""
    spec_file = tmp_path / "nonexistent.yaml"

    with pytest.raises(FileNotFoundError):
        compute_spec_hash(spec_file)


def test_now_iso8601_format():
    """Test ISO 8601 timestamp format."""
    timestamp = now_iso8601()

    # Contains date/time separator
    assert "T" in timestamp

    # Contains UTC timezone offset
    assert "+00:00" in timestamp or "Z" in timestamp

    # Parseable as ISO 8601
    from datetime import datetime

    parsed = datetime.fromisoformat(timestamp)
    assert parsed is not None


def test_now_iso8601_uniqueness():
    """Test timestamps are unique (microsecond precision)."""
    timestamps = [now_iso8601() for _ in range(10)]

    # Most should be unique (microsecond precision)
    # Allow some duplicates due to fast execution
    assert len(set(timestamps)) >= 5


def test_load_spec_content(tmp_path: Path):
    """Test loading spec file content."""
    spec_file = tmp_path / "workflow.yaml"
    content = "version: 0\nname: test-workflow\npattern:\n  type: chain"
    spec_file.write_text(content, encoding="utf-8")

    loaded = load_spec_content(spec_file)

    assert loaded == content
    assert "version:" in loaded
    assert "test-workflow" in loaded


def test_load_spec_content_json(tmp_path: Path):
    """Test loading JSON spec file."""
    spec_file = tmp_path / "workflow.json"
    content = '{"version": 0, "name": "test"}'
    spec_file.write_text(content, encoding="utf-8")

    loaded = load_spec_content(spec_file)

    assert loaded == content
    assert '"version"' in loaded


def test_load_spec_content_nonexistent_file(tmp_path: Path):
    """Test load_spec_content raises for non-existent file."""
    spec_file = tmp_path / "nonexistent.yaml"

    with pytest.raises(FileNotFoundError):
        load_spec_content(spec_file)


def test_load_spec_content_invalid_utf8(tmp_path: Path):
    """Test load_spec_content raises for invalid UTF-8."""
    spec_file = tmp_path / "invalid.yaml"
    spec_file.write_bytes(b"\xff\xfe invalid utf-8")

    with pytest.raises(UnicodeDecodeError):
        load_spec_content(spec_file)

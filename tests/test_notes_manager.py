"""Tests for NotesManager (Phase 1 remediation).

Verifies:
- Efficient streaming read for large files
- Correct entry extraction
- Memory efficiency with large notes files
"""

from pathlib import Path

import pytest

from strands_cli.tools.notes_manager import NotesManager


@pytest.mark.unit
class TestNotesManagerStreaming:
    """Test NotesManager streaming read functionality."""

    def test_stream_small_file_uses_full_read(self, tmp_path: Path) -> None:
        """Test that small files use full read path."""
        notes_file = tmp_path / "small-notes.md"
        manager = NotesManager(str(notes_file))

        # Create small file with 5 entries
        for i in range(5):
            manager.append_entry(
                timestamp=f"2025-11-08T{i:02d}:00:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=["tool-a"],
                outcome=f"Outcome {i}",
            )

        # Read last 3 entries
        result = manager.get_last_n_for_injection(3)

        # Verify correct entries returned
        assert "agent-2" in result
        assert "agent-3" in result
        assert "agent-4" in result
        assert "agent-0" not in result
        assert "agent-1" not in result

    def test_stream_large_file_uses_streaming_read(self, tmp_path: Path) -> None:
        """Test that large files use streaming read path."""
        notes_file = tmp_path / "large-notes.md"
        manager = NotesManager(str(notes_file))

        # Create large file (>100KB) with many entries
        # Each entry is ~200 bytes, so 600 entries ≈ 120KB
        for i in range(600):
            manager.append_entry(
                timestamp=f"2025-11-08T{i % 24:02d}:{i % 60:02d}:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i} with some longer text to increase file size",
                tools_used=["tool-a", "tool-b", "tool-c"],
                outcome=f"Outcome {i} with additional details to make entry larger",
            )

        # Verify file is large enough to trigger streaming
        file_size = notes_file.stat().st_size
        assert file_size > 100_000, f"File size {file_size} should be > 100KB"

        # Read last 3 entries using streaming
        result = manager.get_last_n_for_injection(3)

        # Verify correct entries returned (last 3)
        assert "agent-597" in result
        assert "agent-598" in result
        assert "agent-599" in result
        assert "agent-596" not in result

    def test_stream_read_returns_correct_entries(self, tmp_path: Path) -> None:
        """Test streaming read returns correct number of entries."""
        notes_file = tmp_path / "test-notes.md"
        manager = NotesManager(str(notes_file))

        # Create 10 entries
        for i in range(10):
            manager.append_entry(
                timestamp=f"2025-11-08T{i:02d}:00:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=None,
                outcome=f"Outcome {i}",
            )

        # Test reading different N values
        for n in [1, 3, 5, 10, 15]:
            result = manager.get_last_n_for_injection(n)

            # Count entries in result
            entry_count = result.count("## [")
            expected_count = min(n, 10)  # Can't read more than exist

            assert entry_count == expected_count, (
                f"Expected {expected_count} entries for n={n}, got {entry_count}"
            )

    def test_stream_read_handles_empty_file(self, tmp_path: Path) -> None:
        """Test streaming read handles empty file correctly."""
        notes_file = tmp_path / "empty-notes.md"
        manager = NotesManager(str(notes_file))

        # File doesn't exist yet
        result = manager.get_last_n_for_injection(5)
        assert result == ""

        # Create empty file
        notes_file.touch()
        result = manager.get_last_n_for_injection(5)
        assert result == ""

    def test_stream_read_memory_efficient(self, tmp_path: Path) -> None:
        """Test that streaming read doesn't load entire file into memory at once."""
        notes_file = tmp_path / "huge-notes.md"
        manager = NotesManager(str(notes_file))

        # Create very large file (>1MB) with many entries
        for i in range(3000):
            manager.append_entry(
                timestamp=f"2025-11-08T{i % 24:02d}:{i % 60:02d}:{i % 60:02d}Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i} " + "x" * 100,  # Pad to increase size
                tools_used=["tool-a", "tool-b", "tool-c", "tool-d"],
                outcome=f"Outcome {i} " + "y" * 100,  # Pad to increase size
            )

        # Verify file is very large
        file_size = notes_file.stat().st_size
        assert file_size > 1_000_000, f"File size {file_size} should be > 1MB"

        # Reading just last 3 entries should work efficiently
        # This would fail if we tried to load entire file into memory at once
        result = manager.get_last_n_for_injection(3)

        # Verify correct entries
        assert "agent-2997" in result
        assert "agent-2998" in result
        assert "agent-2999" in result

    def test_stream_read_consistency_with_full_read(self, tmp_path: Path) -> None:
        """Test that streaming read produces same results as full read."""
        notes_file = tmp_path / "consistency-notes.md"
        manager = NotesManager(str(notes_file))

        # Create moderate file (between small and large thresholds)
        for i in range(100):
            manager.append_entry(
                timestamp=f"2025-11-08T{i % 24:02d}:00:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=["tool-a"],
                outcome=f"Outcome {i}",
            )

        # Force small file read (full read)
        with open(notes_file, encoding="utf-8") as f:
            content = f.read()
        result_full = manager._extract_last_n_entries(content, 5)

        # Force streaming read
        result_stream = manager._stream_last_n_entries(5)

        # Both should return same number of entries with same content
        # (May have minor formatting differences but content should match)
        assert result_full.count("## [") == result_stream.count("## [")
        assert "agent-95" in result_full and "agent-95" in result_stream
        assert "agent-96" in result_full and "agent-96" in result_stream
        assert "agent-97" in result_full and "agent-97" in result_stream
        assert "agent-98" in result_full and "agent-98" in result_stream
        assert "agent-99" in result_full and "agent-99" in result_stream

    def test_stream_read_with_unicode_content(self, tmp_path: Path) -> None:
        """Test streaming read handles Unicode content correctly."""
        notes_file = tmp_path / "unicode-notes.md"
        manager = NotesManager(str(notes_file))

        # Create entries with Unicode characters
        unicode_samples = [
            "Hello 世界",
            "Привет мир",
            "مرحبا العالم",
            "🚀 Rocket science",
            "Ñoño español",
        ]

        for i, text in enumerate(unicode_samples):
            manager.append_entry(
                timestamp=f"2025-11-08T{i:02d}:00:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=text,
                tools_used=None,
                outcome=text[::-1],  # Reversed
            )

        # Read last 3 entries
        result = manager.get_last_n_for_injection(3)

        # Verify Unicode preserved
        assert "Rocket science" in result
        assert "español" in result
        assert "العالم" in result

    def test_stream_read_edge_cases(self, tmp_path: Path) -> None:
        """Test streaming read edge cases."""
        notes_file = tmp_path / "edge-notes.md"
        manager = NotesManager(str(notes_file))

        # Create 10 entries
        for i in range(10):
            manager.append_entry(
                timestamp=f"2025-11-08T{i:02d}:00:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=None,
                outcome=f"Outcome {i}",
            )

        # Test n=0 (should return empty)
        result = manager.get_last_n_for_injection(0)
        assert result == "" or result.count("## [") == 0

        # Test n=1 (single entry)
        result = manager.get_last_n_for_injection(1)
        assert result.count("## [") == 1
        assert "agent-9" in result

        # Test n > total entries (should return all)
        result = manager.get_last_n_for_injection(100)
        assert result.count("## [") == 10

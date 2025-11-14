"""Unit tests for structured notes manager.

Tests NotesManager functionality:
- Markdown formatting and entry structure
- File append operations with locking
- Read last N entries with correct slicing
- Timestamp generation (ISO8601 format)
- Concurrent writes safety
- Cross-session continuity
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from strands_cli.tools.notes_manager import NotesManager, NotesManagerError


class TestNotesManager:
    """Test suite for NotesManager."""

    def test_initialize_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test that NotesManager creates parent directories."""
        notes_path = tmp_path / "artifacts" / "notes.md"
        manager = NotesManager(str(notes_path))

        assert notes_path.parent.exists()
        assert manager.file_path == notes_path

    def test_append_entry_creates_file(self, tmp_path: Path) -> None:
        """Test that append_entry creates the notes file."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="test-agent",
            step_index=1,
            input_summary="Test input",
            tools_used=["tool1", "tool2"],
            outcome="Test outcome",
        )

        assert notes_path.exists()

    def test_format_entry_correct_markdown(self, tmp_path: Path) -> None:
        """Test that entries are formatted correctly as Markdown."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="research-agent",
            step_index=1,
            input_summary="Analyze customer reviews",
            tools_used=["http_request", "file_read"],
            outcome="Positive sentiment (0.82 score)",
        )

        content = notes_path.read_text(encoding="utf-8")

        # Check Markdown structure
        assert "## [2025-11-07T14:32:00Z] — Agent: research-agent (Step 1)" in content
        assert "- **Input**: Analyze customer reviews" in content
        assert "- **Tools used**: http_request, file_read" in content
        assert "- **Outcome**: Positive sentiment (0.82 score)" in content

    def test_format_entry_no_tools(self, tmp_path: Path) -> None:
        """Test formatting when no tools are used."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="summarizer",
            step_index=2,
            input_summary="Summarize findings",
            tools_used=None,
            outcome="Generated summary",
        )

        content = notes_path.read_text(encoding="utf-8")
        assert "- **Tools used**: None" in content

    def test_format_entry_truncates_long_input(self, tmp_path: Path) -> None:
        """Test that long inputs are truncated to 200 chars."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        long_input = "A" * 250

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="test-agent",
            step_index=1,
            input_summary=long_input,
            tools_used=[],
            outcome="Done",
        )

        content = notes_path.read_text(encoding="utf-8")

        # Should be truncated with "..."
        assert "..." in content
        # Truncated version should not contain full string
        assert long_input not in content

    def test_get_last_n_for_injection_alias(self, tmp_path: Path) -> None:
        """Test get_last_n_for_injection is an alias for read_last_n."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-08T00:00:00Z",
            agent_name="agent-1",
            step_index=1,
            input_summary="Test",
            tools_used=None,
            outcome="Result",
        )

        result1 = manager.read_last_n(1)
        result2 = manager.get_last_n_for_injection(1)

        assert result1 == result2
        assert "agent-1" in result1

    def test_get_last_n_for_injection_empty_file(self, tmp_path: Path) -> None:
        """Test get_last_n_for_injection returns empty string for non-existent file."""
        notes_path = tmp_path / "nonexistent.md"
        manager = NotesManager(str(notes_path))

        result = manager.get_last_n_for_injection(5)
        assert result == ""

    def test_format_entry_truncates_long_outcome(self, tmp_path: Path) -> None:
        """Test that long outcomes are truncated to 200 chars."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        long_outcome = "B" * 250

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="test-agent",
            step_index=1,
            input_summary="Test",
            tools_used=[],
            outcome=long_outcome,
        )

        content = notes_path.read_text(encoding="utf-8")
        assert "B" * 200 + "..." in content

    def test_append_multiple_entries_maintains_order(self, tmp_path: Path) -> None:
        """Test that multiple entries are appended in correct order."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        for i in range(3):
            manager.append_entry(
                timestamp=f"2025-11-07T14:3{i}:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=[],
                outcome=f"Outcome {i}",
            )

        content = notes_path.read_text(encoding="utf-8")

        # Check all entries present
        assert "agent-0" in content
        assert "agent-1" in content
        assert "agent-2" in content

        # Check order
        idx0 = content.index("agent-0")
        idx1 = content.index("agent-1")
        idx2 = content.index("agent-2")
        assert idx0 < idx1 < idx2

    def test_read_last_n_empty_file(self, tmp_path: Path) -> None:
        """Test read_last_n returns empty string for non-existent file."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        result = manager.read_last_n(5)
        assert result == ""

    def test_read_last_n_single_entry(self, tmp_path: Path) -> None:
        """Test read_last_n with single entry."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="test-agent",
            step_index=1,
            input_summary="Test",
            tools_used=[],
            outcome="Done",
        )

        result = manager.read_last_n(5)

        assert "test-agent" in result
        assert "Step 1" in result

    def test_read_last_n_correct_count(self, tmp_path: Path) -> None:
        """Test that read_last_n returns correct number of entries."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        # Add 5 entries
        for i in range(5):
            manager.append_entry(
                timestamp=f"2025-11-07T14:3{i}:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=[],
                outcome=f"Outcome {i}",
            )

        # Request last 3
        result = manager.read_last_n(3)

        # Should have agents 2, 3, 4 (last 3)
        assert "agent-2" in result
        assert "agent-3" in result
        assert "agent-4" in result

        # Should NOT have agents 0, 1
        assert "agent-0" not in result
        assert "agent-1" not in result

        # Count ## headers (should be 3)
        assert result.count("## [") == 3

    def test_read_last_n_more_than_available(self, tmp_path: Path) -> None:
        """Test read_last_n when requesting more entries than exist."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        # Add 2 entries
        for i in range(2):
            manager.append_entry(
                timestamp=f"2025-11-07T14:3{i}:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=[],
                outcome=f"Outcome {i}",
            )

        # Request last 10 (more than available)
        result = manager.read_last_n(10)

        # Should return all 2 entries
        assert "agent-0" in result
        assert "agent-1" in result
        assert result.count("## [") == 2

    def test_generate_timestamp_format(self) -> None:
        """Test that generated timestamps are in correct ISO8601 format."""
        timestamp = NotesManager.generate_timestamp()

        # Should be format: 2025-11-07T14:32:00Z
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        assert len(timestamp.split("T")) == 2

        # Should be parseable
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_generate_timestamp_utc(self) -> None:
        """Test that generated timestamps are in UTC."""
        timestamp = NotesManager.generate_timestamp()
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Should be UTC
        assert parsed.tzinfo == UTC

    def test_concurrent_writes_with_locking(self, tmp_path: Path) -> None:
        """Test that concurrent writes are handled safely with locking."""
        import threading

        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        errors = []

        def write_entry(agent_id: int) -> None:
            try:
                manager.append_entry(
                    timestamp=f"2025-11-07T14:3{agent_id}:00Z",
                    agent_name=f"agent-{agent_id}",
                    step_index=agent_id + 1,
                    input_summary=f"Input {agent_id}",
                    tools_used=[],
                    outcome=f"Outcome {agent_id}",
                )
            except Exception as e:
                errors.append(e)

        # Create 5 threads writing concurrently
        threads = [threading.Thread(target=write_entry, args=(i,)) for i in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # No errors should occur
        assert len(errors) == 0

        # All entries should be present
        content = notes_path.read_text(encoding="utf-8")
        for i in range(5):
            assert f"agent-{i}" in content

    def test_read_after_write_consistency(self, tmp_path: Path) -> None:
        """Test that reading after writing returns consistent data."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        # Write 3 entries
        for i in range(3):
            manager.append_entry(
                timestamp=f"2025-11-07T14:3{i}:00Z",
                agent_name=f"agent-{i}",
                step_index=i + 1,
                input_summary=f"Input {i}",
                tools_used=[f"tool-{i}"],
                outcome=f"Outcome {i}",
            )

        # Read last 2
        result = manager.read_last_n(2)

        # Should have correct entries
        assert "agent-1" in result
        assert "agent-2" in result
        assert "tool-1" in result
        assert "tool-2" in result

    def test_cross_session_continuity(self, tmp_path: Path) -> None:
        """Test that notes persist across NotesManager instances (sessions)."""
        notes_path = tmp_path / "notes.md"

        # Session 1: Write entries
        manager1 = NotesManager(str(notes_path))
        manager1.append_entry(
            timestamp="2025-11-07T14:30:00Z",
            agent_name="session1-agent",
            step_index=1,
            input_summary="Session 1 work",
            tools_used=[],
            outcome="Done",
        )

        # Session 2: New manager, read and append
        manager2 = NotesManager(str(notes_path))

        # Should read previous session's notes
        previous_notes = manager2.read_last_n(10)
        assert "session1-agent" in previous_notes

        # Append new entry
        manager2.append_entry(
            timestamp="2025-11-07T14:31:00Z",
            agent_name="session2-agent",
            step_index=2,
            input_summary="Session 2 work",
            tools_used=[],
            outcome="Done",
        )

        # Session 3: Verify both entries present
        manager3 = NotesManager(str(notes_path))
        all_notes = manager3.read_last_n(10)

        assert "session1-agent" in all_notes
        assert "session2-agent" in all_notes

    def test_file_write_error_raises_manager_error(self, tmp_path: Path, mocker) -> None:
        """Test that file write errors are wrapped in NotesManagerError."""
        # Use mock to simulate file write error (cross-platform)
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        # Mock the open() call to raise an OSError
        mock_open = mocker.patch("builtins.open", side_effect=OSError("Permission denied"))

        with pytest.raises(NotesManagerError, match="Failed to append note entry"):
            manager.append_entry(
                timestamp="2025-11-07T14:32:00Z",
                agent_name="test-agent",
                step_index=1,
                input_summary="Test",
                tools_used=[],
                outcome="Done",
            )

        # Verify open was called
        mock_open.assert_called_once()

    def test_empty_tools_list_formats_as_none(self, tmp_path: Path) -> None:
        """Test that empty tools list formats as 'None'."""
        notes_path = tmp_path / "notes.md"
        manager = NotesManager(str(notes_path))

        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="test-agent",
            step_index=1,
            input_summary="Test",
            tools_used=[],
            outcome="Done",
        )

        content = notes_path.read_text(encoding="utf-8")
        assert "- **Tools used**: None" in content

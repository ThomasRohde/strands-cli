"""Unit tests for Pydantic type models (src/strands_cli/types.py).

Tests field validation, constraints, and model behavior for:
- Compaction model (context_policy.compaction)
- Notes model (context_policy.notes)
- ContextNote model (structured note-taking)
"""

from typing import Any

import pytest
from pydantic import ValidationError

from strands_cli.types import Compaction, ContextNote, Notes


@pytest.mark.unit
class TestCompactionModel:
    """Test Compaction Pydantic model validation."""

    def test_compaction_defaults(self) -> None:
        """Test that Compaction model has correct default values."""
        compaction = Compaction()

        assert compaction.enabled is True
        assert compaction.when_tokens_over is None
        assert compaction.summary_ratio == 0.35
        assert compaction.preserve_recent_messages == 12
        assert compaction.summarization_model is None

    def test_compaction_with_all_fields(self) -> None:
        """Test creating Compaction with all fields specified."""
        compaction = Compaction(
            enabled=True,
            when_tokens_over=5000,
            summary_ratio=0.4,
            preserve_recent_messages=10,
            summarization_model="gpt-4o-mini",
        )

        assert compaction.enabled is True
        assert compaction.when_tokens_over == 5000
        assert compaction.summary_ratio == 0.4
        assert compaction.preserve_recent_messages == 10
        assert compaction.summarization_model == "gpt-4o-mini"

    def test_compaction_summary_ratio_valid_range(self) -> None:
        """Test that summary_ratio accepts valid values in range [0.0, 1.0]."""
        # Test boundary values
        compaction_min = Compaction(summary_ratio=0.0)
        assert compaction_min.summary_ratio == 0.0

        compaction_max = Compaction(summary_ratio=1.0)
        assert compaction_max.summary_ratio == 1.0

        # Test middle values
        compaction_mid = Compaction(summary_ratio=0.5)
        assert compaction_mid.summary_ratio == 0.5

    def test_compaction_summary_ratio_rejects_above_max(self) -> None:
        """Test that summary_ratio rejects values > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            Compaction(summary_ratio=1.5)

        error_text = str(exc_info.value)
        assert "summary_ratio" in error_text.lower()

    def test_compaction_summary_ratio_rejects_below_min(self) -> None:
        """Test that summary_ratio rejects values < 0.0."""
        with pytest.raises(ValidationError) as exc_info:
            Compaction(summary_ratio=-0.1)

        error_text = str(exc_info.value)
        assert "summary_ratio" in error_text.lower()

    def test_compaction_preserve_recent_messages_valid(self) -> None:
        """Test that preserve_recent_messages accepts valid values >= 1."""
        compaction_min = Compaction(preserve_recent_messages=1)
        assert compaction_min.preserve_recent_messages == 1

        compaction_typical = Compaction(preserve_recent_messages=20)
        assert compaction_typical.preserve_recent_messages == 20

    def test_compaction_preserve_recent_messages_rejects_zero(self) -> None:
        """Test that preserve_recent_messages rejects 0."""
        with pytest.raises(ValidationError) as exc_info:
            Compaction(preserve_recent_messages=0)

        error_text = str(exc_info.value)
        assert "preserve_recent_messages" in error_text.lower()

    def test_compaction_preserve_recent_messages_rejects_negative(self) -> None:
        """Test that preserve_recent_messages rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            Compaction(preserve_recent_messages=-5)

        error_text = str(exc_info.value)
        assert "preserve_recent_messages" in error_text.lower()

    def test_compaction_when_tokens_over_valid(self) -> None:
        """Test that when_tokens_over accepts valid values >= 1000."""
        compaction_min = Compaction(when_tokens_over=1000)
        assert compaction_min.when_tokens_over == 1000

        compaction_typical = Compaction(when_tokens_over=5000)
        assert compaction_typical.when_tokens_over == 5000

    def test_compaction_when_tokens_over_rejects_below_minimum(self) -> None:
        """Test that when_tokens_over rejects values < 1000."""
        with pytest.raises(ValidationError) as exc_info:
            Compaction(when_tokens_over=500)

        error_text = str(exc_info.value)
        assert "when_tokens_over" in error_text.lower()

    def test_compaction_when_tokens_over_none_allowed(self) -> None:
        """Test that when_tokens_over can be None (disabled)."""
        compaction = Compaction(when_tokens_over=None)
        assert compaction.when_tokens_over is None


@pytest.mark.unit
class TestNotesModel:
    """Test Notes Pydantic model validation."""

    def test_notes_with_required_fields(self) -> None:
        """Test creating Notes with required fields only."""
        notes = Notes(file="artifacts/notes.md")

        assert notes.file == "artifacts/notes.md"
        assert notes.include_last == 12  # Default
        assert notes.format == "markdown"  # Default

    def test_notes_with_all_fields(self) -> None:
        """Test creating Notes with all fields specified."""
        notes = Notes(
            file="artifacts/custom-notes.md",
            include_last=8,
            format="json",
        )

        assert notes.file == "artifacts/custom-notes.md"
        assert notes.include_last == 8
        assert notes.format == "json"

    def test_notes_include_last_valid(self) -> None:
        """Test that include_last accepts valid values >= 1."""
        notes_min = Notes(file="notes.md", include_last=1)
        assert notes_min.include_last == 1

        notes_typical = Notes(file="notes.md", include_last=20)
        assert notes_typical.include_last == 20

    def test_notes_include_last_rejects_zero(self) -> None:
        """Test that include_last rejects 0."""
        with pytest.raises(ValidationError) as exc_info:
            Notes(file="notes.md", include_last=0)

        error_text = str(exc_info.value)
        assert "include_last" in error_text.lower()

    def test_notes_include_last_rejects_negative(self) -> None:
        """Test that include_last rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            Notes(file="notes.md", include_last=-3)

        error_text = str(exc_info.value)
        assert "include_last" in error_text.lower()

    def test_notes_format_markdown_valid(self) -> None:
        """Test that format accepts 'markdown'."""
        notes = Notes(file="notes.md", format="markdown")
        assert notes.format == "markdown"

    def test_notes_format_json_valid(self) -> None:
        """Test that format accepts 'json'."""
        notes = Notes(file="notes.json", format="json")
        assert notes.format == "json"

    def test_notes_format_rejects_invalid(self) -> None:
        """Test that format rejects unsupported values."""
        with pytest.raises(ValidationError) as exc_info:
            Notes(file="notes.xml", format="xml")

        error_text = str(exc_info.value)
        assert "format" in error_text.lower()

    def test_notes_file_required(self) -> None:
        """Test that file field is required."""
        with pytest.raises(ValidationError) as exc_info:
            Notes()  # type: ignore

        error_text = str(exc_info.value)
        assert "file" in error_text.lower() or "required" in error_text.lower()


@pytest.mark.unit
class TestContextNoteModel:
    """Test ContextNote Pydantic model for structured note-taking."""

    def test_context_note_with_required_fields(self) -> None:
        """Test creating ContextNote with required fields."""
        note = ContextNote(
            timestamp="2025-01-01T10:00:00Z",
            step_id="step_0",
            agent_id="researcher",
            content="Found important insight about X",
        )

        assert note.timestamp == "2025-01-01T10:00:00Z"
        assert note.step_id == "step_0"
        assert note.agent_id == "researcher"
        assert note.content == "Found important insight about X"
        assert note.metadata is None

    def test_context_note_with_metadata(self) -> None:
        """Test creating ContextNote with optional metadata."""
        metadata: dict[str, Any] = {
            "tags": ["important", "research"],
            "importance": "high",
            "source": "web_search",
        }

        note = ContextNote(
            timestamp="2025-01-01T10:00:00Z",
            step_id="step_1",
            agent_id="analyzer",
            content="Analysis complete",
            metadata=metadata,
        )

        assert note.metadata == metadata
        assert note.metadata["tags"] == ["important", "research"]
        assert note.metadata["importance"] == "high"

    def test_context_note_all_fields_required(self) -> None:
        """Test that all non-optional fields are required."""
        with pytest.raises(ValidationError) as exc_info:
            ContextNote()  # type: ignore

        error_text = str(exc_info.value)
        assert "required" in error_text.lower()

    def test_context_note_timestamp_required(self) -> None:
        """Test that timestamp field is required."""
        with pytest.raises(ValidationError) as exc_info:
            ContextNote(
                step_id="step_0",
                agent_id="agent",
                content="content",
            )  # type: ignore

        error_text = str(exc_info.value)
        assert "timestamp" in error_text.lower()

    def test_context_note_step_id_required(self) -> None:
        """Test that step_id field is required."""
        with pytest.raises(ValidationError) as exc_info:
            ContextNote(
                timestamp="2025-01-01T10:00:00Z",
                agent_id="agent",
                content="content",
            )  # type: ignore

        error_text = str(exc_info.value)
        assert "step_id" in error_text.lower()

    def test_context_note_agent_id_required(self) -> None:
        """Test that agent_id field is required."""
        with pytest.raises(ValidationError) as exc_info:
            ContextNote(
                timestamp="2025-01-01T10:00:00Z",
                step_id="step_0",
                content="content",
            )  # type: ignore

        error_text = str(exc_info.value)
        assert "agent_id" in error_text.lower()

    def test_context_note_content_required(self) -> None:
        """Test that content field is required."""
        with pytest.raises(ValidationError) as exc_info:
            ContextNote(
                timestamp="2025-01-01T10:00:00Z",
                step_id="step_0",
                agent_id="agent",
            )  # type: ignore

        error = str(exc_info.value)
        assert "content" in error.lower()


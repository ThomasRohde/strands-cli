"""Tests for configuration presets.

Phase 2 Remediation: Configuration ergonomics
"""

import pytest

from strands_cli.presets import (
    ContextPreset,
    apply_preset_to_spec,
    describe_presets,
    get_context_preset,
)


class TestContextPresets:
    """Test suite for context management presets."""

    def test_minimal_preset(self) -> None:
        """Verify minimal preset configuration."""
        policy = get_context_preset(ContextPreset.MINIMAL)

        assert policy.compaction is not None
        assert policy.compaction.enabled is False
        assert policy.notes is None
        assert policy.retrieval is None

    def test_balanced_preset(self) -> None:
        """Verify balanced preset configuration."""
        policy = get_context_preset(ContextPreset.BALANCED)

        assert policy.compaction is not None
        assert policy.compaction.enabled is True
        assert policy.compaction.when_tokens_over == 100_000
        assert policy.compaction.summary_ratio == 0.35
        assert policy.compaction.preserve_recent_messages == 12
        assert policy.notes is None
        assert policy.retrieval is None

    def test_long_run_preset(self) -> None:
        """Verify long_run preset configuration."""
        policy = get_context_preset(ContextPreset.LONG_RUN)

        # Compaction configured for longer workflows
        assert policy.compaction is not None
        assert policy.compaction.enabled is True
        assert policy.compaction.when_tokens_over == 80_000
        assert policy.compaction.summary_ratio == 0.40
        assert policy.compaction.preserve_recent_messages == 20

        # Notes enabled with default file
        assert policy.notes is not None
        assert policy.notes.file == "artifacts/notes.md"
        assert policy.notes.include_last == 20
        assert policy.notes.format == "markdown"

        # JIT tools enabled
        assert policy.retrieval is not None
        assert policy.retrieval.jit_tools == ["grep", "search", "head", "tail"]

    def test_interactive_preset(self) -> None:
        """Verify interactive preset configuration."""
        policy = get_context_preset(ContextPreset.INTERACTIVE)

        assert policy.compaction is not None
        assert policy.compaction.enabled is True
        assert policy.compaction.when_tokens_over == 50_000
        assert policy.compaction.summary_ratio == 0.30
        assert policy.compaction.preserve_recent_messages == 16
        assert policy.notes is None
        assert policy.retrieval is None

    def test_preset_from_string(self) -> None:
        """Verify presets can be loaded from string names."""
        policy = get_context_preset("balanced")
        assert policy.compaction is not None
        assert policy.compaction.enabled is True

    def test_invalid_preset_raises_error(self) -> None:
        """Verify invalid preset names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid preset"):
            get_context_preset("nonexistent")

    def test_custom_preset_raises_error(self) -> None:
        """Verify CUSTOM preset raises error (requires explicit config)."""
        with pytest.raises(ValueError, match="Cannot generate config for CUSTOM"):
            get_context_preset(ContextPreset.CUSTOM)


class TestApplyPreset:
    """Test suite for applying presets to specs."""

    def test_apply_preset_to_empty_spec(self) -> None:
        """Verify preset can be applied to spec without context_policy."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "chain", "config": {"steps": []}},
        }

        apply_preset_to_spec(spec_data, "balanced")

        assert "context_policy" in spec_data
        assert spec_data["context_policy"]["compaction"]["enabled"] is True
        assert spec_data["context_policy"]["compaction"]["when_tokens_over"] == 100_000

    def test_apply_preset_preserves_existing_values(self) -> None:
        """Verify existing context_policy values take precedence over preset."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "chain", "config": {"steps": []}},
            "context_policy": {
                "compaction": {
                    "enabled": True,
                    "when_tokens_over": 50_000,  # Custom value
                }
            },
        }

        apply_preset_to_spec(spec_data, "long_run")

        # Custom value should be preserved
        assert spec_data["context_policy"]["compaction"]["when_tokens_over"] == 50_000

        # Preset values should fill in missing fields
        assert spec_data["context_policy"]["compaction"]["summary_ratio"] == 0.40
        assert spec_data["context_policy"]["compaction"]["preserve_recent_messages"] == 20

        # Preset should add notes and retrieval
        assert "notes" in spec_data["context_policy"]
        assert "retrieval" in spec_data["context_policy"]

    def test_apply_preset_merges_nested_dicts(self) -> None:
        """Verify nested dictionary merging works correctly."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "chain", "config": {"steps": []}},
            "context_policy": {
                "compaction": {
                    "enabled": False,  # User wants to disable
                }
            },
        }

        apply_preset_to_spec(spec_data, "balanced")

        # User's disabled flag should be preserved
        assert spec_data["context_policy"]["compaction"]["enabled"] is False

        # But preset values should fill in missing fields
        assert spec_data["context_policy"]["compaction"]["when_tokens_over"] == 100_000

    def test_apply_long_run_preset_with_custom_notes_file(self) -> None:
        """Verify long_run preset can be customized with different notes file."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "chain", "config": {"steps": []}},
            "context_policy": {
                "notes": {
                    "file": "custom/notes.md",  # Custom path
                }
            },
        }

        apply_preset_to_spec(spec_data, "long_run")

        # Custom notes file should be preserved
        assert spec_data["context_policy"]["notes"]["file"] == "custom/notes.md"

        # But preset values should fill in defaults
        assert spec_data["context_policy"]["notes"]["include_last"] == 20


class TestDescribePresets:
    """Test suite for preset descriptions."""

    def test_describe_presets_returns_markdown(self) -> None:
        """Verify describe_presets returns formatted markdown."""
        description = describe_presets()

        assert isinstance(description, str)
        assert "# Context Management Presets" in description
        assert "## minimal" in description
        assert "## balanced" in description
        assert "## long_run" in description
        assert "## interactive" in description

    def test_describe_presets_includes_use_cases(self) -> None:
        """Verify descriptions include use case information."""
        description = describe_presets()

        # Check for use case keywords (case-insensitive)
        lower_desc = description.lower()
        assert "best for" in lower_desc or "workflows" in lower_desc
        assert "compaction" in lower_desc


@pytest.mark.integration
class TestPresetIntegration:
    """Integration tests for presets with full workflow specs."""

    def test_load_spec_with_preset_string(self) -> None:
        """Verify specs can use preset strings in YAML."""
        from tempfile import NamedTemporaryFile

        from strands_cli.loader.yaml_loader import load_spec

        # Note: This would require implementing preset support in loader
        # For now, test manual application
        spec_yaml = """
version: 0
name: test-preset
runtime:
  provider: ollama
  model_id: llama3.2
agents:
  writer:
    prompt: "You are a helpful assistant"
pattern:
  type: chain
  config:
    steps:
      - agent: writer
        input: "Test"
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_yaml)
            f.flush()
            spec = load_spec(f.name)

        # Manually apply preset
        from strands_cli.presets import get_context_preset

        spec.context_policy = get_context_preset("balanced")

        # Verify preset was applied
        assert spec.context_policy is not None
        assert spec.context_policy.compaction is not None
        assert spec.context_policy.compaction.enabled is True

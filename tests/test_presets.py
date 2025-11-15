"""Tests for configuration presets.

Phase 2 Remediation: Configuration ergonomics
"""

import pytest

from strands_cli.presets import (
    ContextPreset,
    apply_preset_to_spec,
    describe_presets,
    get_adaptive_preserve_messages,
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
        # Adaptive: without pattern_type, uses base value of 15
        assert policy.compaction.preserve_recent_messages == 15

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
        # Adaptive: chain pattern extracts from spec → preserve=8
        assert spec_data["context_policy"]["compaction"]["preserve_recent_messages"] == 8

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


class TestAdaptivePreserveMessages:
    """Test suite for adaptive preserve_recent_messages based on pattern type."""

    def test_get_adaptive_preserve_chain_pattern(self) -> None:
        """Verify chain pattern uses lower preserve value."""
        preserve = get_adaptive_preserve_messages("chain", base_value=12)
        assert preserve == 8

    def test_get_adaptive_preserve_evaluator_pattern(self) -> None:
        """Verify evaluator_optimizer pattern uses lower preserve value."""
        preserve = get_adaptive_preserve_messages("evaluator_optimizer", base_value=12)
        assert preserve == 8

    def test_get_adaptive_preserve_workflow_pattern(self) -> None:
        """Verify workflow pattern uses medium preserve value."""
        preserve = get_adaptive_preserve_messages("workflow", base_value=12)
        assert preserve == 12

    def test_get_adaptive_preserve_parallel_pattern(self) -> None:
        """Verify parallel pattern uses medium preserve value."""
        preserve = get_adaptive_preserve_messages("parallel", base_value=12)
        assert preserve == 12

    def test_get_adaptive_preserve_routing_pattern(self) -> None:
        """Verify routing pattern uses medium preserve value."""
        preserve = get_adaptive_preserve_messages("routing", base_value=12)
        assert preserve == 12

    def test_get_adaptive_preserve_orchestrator_pattern(self) -> None:
        """Verify orchestrator pattern uses higher preserve value."""
        preserve = get_adaptive_preserve_messages("orchestrator", base_value=12)
        assert preserve == 15

    def test_get_adaptive_preserve_graph_pattern(self) -> None:
        """Verify graph pattern uses highest preserve value."""
        preserve = get_adaptive_preserve_messages("graph", base_value=12)
        assert preserve == 20

    def test_get_adaptive_preserve_unknown_pattern(self) -> None:
        """Verify unknown pattern uses base value."""
        preserve = get_adaptive_preserve_messages("unknown", base_value=12)
        assert preserve == 12

    def test_get_adaptive_preserve_none_pattern(self) -> None:
        """Verify None pattern uses base value."""
        preserve = get_adaptive_preserve_messages(None, base_value=12)
        assert preserve == 12

    def test_get_adaptive_preserve_case_insensitive(self) -> None:
        """Verify pattern matching is case-insensitive."""
        preserve_upper = get_adaptive_preserve_messages("CHAIN", base_value=12)
        preserve_lower = get_adaptive_preserve_messages("chain", base_value=12)
        preserve_mixed = get_adaptive_preserve_messages("Chain", base_value=12)

        assert preserve_upper == preserve_lower == preserve_mixed == 8


class TestAdaptivePresets:
    """Test suite for adaptive preset behavior with pattern types."""

    def test_balanced_preset_adapts_to_chain(self) -> None:
        """Verify balanced preset adapts preserve_recent_messages for chain pattern."""
        policy = get_context_preset("balanced", pattern_type="chain")

        assert policy.compaction is not None
        assert policy.compaction.preserve_recent_messages == 8

    def test_balanced_preset_adapts_to_graph(self) -> None:
        """Verify balanced preset adapts preserve_recent_messages for graph pattern."""
        policy = get_context_preset("balanced", pattern_type="graph")

        assert policy.compaction is not None
        assert policy.compaction.preserve_recent_messages == 20

    def test_long_run_preset_adapts_to_workflow(self) -> None:
        """Verify long_run preset adapts preserve_recent_messages for workflow pattern."""
        policy = get_context_preset("long_run", pattern_type="workflow")

        assert policy.compaction is not None
        assert policy.compaction.preserve_recent_messages == 12

    def test_interactive_preset_adapts_to_orchestrator(self) -> None:
        """Verify interactive preset adapts preserve_recent_messages for orchestrator."""
        policy = get_context_preset("interactive", pattern_type="orchestrator")

        assert policy.compaction is not None
        assert policy.compaction.preserve_recent_messages == 15

    def test_preset_without_pattern_uses_base_value(self) -> None:
        """Verify presets use base value when pattern_type not provided."""
        policy = get_context_preset("balanced")  # No pattern_type

        assert policy.compaction is not None
        assert policy.compaction.preserve_recent_messages == 12  # Base value for balanced

    def test_apply_preset_extracts_pattern_from_spec(self) -> None:
        """Verify apply_preset_to_spec extracts pattern type from spec_data."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "graph", "config": {}},
        }

        apply_preset_to_spec(spec_data, "long_run")

        # Should extract pattern type "graph" and use preserve=20
        assert spec_data["context_policy"]["compaction"]["preserve_recent_messages"] == 20

    def test_apply_preset_with_explicit_pattern_type(self) -> None:
        """Verify apply_preset_to_spec can use explicit pattern_type parameter."""
        spec_data = {
            "version": 0,
            "name": "test",
            "runtime": {"provider": "ollama"},
            "agents": {"a": {"prompt": "test"}},
            "pattern": {"type": "workflow", "config": {}},
        }

        # Override with explicit pattern_type (ignores spec pattern)
        apply_preset_to_spec(spec_data, "balanced", pattern_type="chain")

        # Should use explicit "chain" pattern → preserve=8
        assert spec_data["context_policy"]["compaction"]["preserve_recent_messages"] == 8

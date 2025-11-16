"""Configuration presets for common workflow scenarios.

Provides high-level presets for context management (compaction, notes, retrieval)
to simplify onboarding and configuration. Users can select presets instead of
manually configuring individual parameters.

Phase 2 Remediation: Configuration ergonomics

Adaptive Behavior: Presets automatically adjust preserve_recent_messages based
on workflow pattern type to optimize for typical message counts:
- Chain/Evaluator: 8 messages (sequential, fewer steps)
- Workflow/Parallel: 12 messages (moderate branching)
- Orchestrator: 15 messages (worker coordination)
- Graph: 20 messages (potential loops, state tracking)
"""

from enum import Enum
from typing import Any

from strands_cli.types import Compaction, ContextPolicy, Notes, Retrieval


class ContextPreset(str, Enum):
    """Predefined context management presets.

    Each preset configures compaction, notes, and retrieval settings
    for common workflow scenarios. Presets adapt preserve_recent_messages
    based on workflow pattern type for optimal context management.
    """

    # Minimal context management (default)
    MINIMAL = "minimal"

    # Balanced for most workflows
    BALANCED = "balanced"

    # Optimized for long-running workflows (research, multi-step analysis)
    LONG_RUN = "long_run"

    # Optimized for interactive/chat-like workflows
    INTERACTIVE = "interactive"

    # Custom (user provides their own config)
    CUSTOM = "custom"


def get_adaptive_preserve_messages(pattern_type: str | None, base_value: int) -> int:
    """Calculate adaptive preserve_recent_messages based on pattern type.

    Different patterns have different message accumulation characteristics:
    - Chain/Evaluator: Sequential, fewer total messages → lower preserve
    - Workflow/Parallel: Moderate branching → medium preserve
    - Orchestrator: Worker coordination → higher preserve
    - Graph: Loops and state transitions → highest preserve

    Args:
        pattern_type: Workflow pattern type (chain, workflow, etc.)
        base_value: Default preserve value if pattern unknown

    Returns:
        Adaptive preserve_recent_messages value

    Examples:
        >>> get_adaptive_preserve_messages("chain", 12)
        8
        >>> get_adaptive_preserve_messages("graph", 12)
        20
        >>> get_adaptive_preserve_messages(None, 12)
        12
    """
    if not pattern_type:
        return base_value

    pattern_lower = pattern_type.lower()

    # Sequential patterns - fewer messages
    if pattern_lower in ("chain", "evaluator_optimizer"):
        return 8

    # Moderate branching patterns
    if pattern_lower in ("workflow", "parallel", "routing"):
        return 12

    # Coordination patterns - more messages
    if pattern_lower == "orchestrator":
        return 15

    # Graph patterns - potential loops, need more history
    if pattern_lower == "graph":
        return 20

    # Unknown pattern - use base value
    return base_value


def get_context_preset(
    preset: str | ContextPreset, pattern_type: str | None = None
) -> ContextPolicy:
    """Get a context policy configuration from a preset name.

    Args:
        preset: Preset name or ContextPreset enum value
        pattern_type: Optional workflow pattern type for adaptive settings

    Returns:
        Configured ContextPolicy instance with adaptive preserve_recent_messages

    Raises:
        ValueError: If preset name is invalid

    Examples:
        >>> policy = get_context_preset("long_run", pattern_type="chain")
        >>> policy.compaction.enabled
        True
        >>> policy.compaction.preserve_recent_messages
        8
        >>> policy = get_context_preset("long_run", pattern_type="graph")
        >>> policy.compaction.preserve_recent_messages
        20
    """
    if isinstance(preset, str):
        try:
            preset = ContextPreset(preset)
        except ValueError as e:
            valid_presets = [p.value for p in ContextPreset if p != ContextPreset.CUSTOM]
            raise ValueError(f"Invalid preset '{preset}'. Valid presets: {valid_presets}") from e

    if preset == ContextPreset.MINIMAL:
        return _minimal_preset()
    elif preset == ContextPreset.BALANCED:
        return _balanced_preset(pattern_type)
    elif preset == ContextPreset.LONG_RUN:
        return _long_run_preset(pattern_type)
    elif preset == ContextPreset.INTERACTIVE:
        return _interactive_preset(pattern_type)
    else:
        raise ValueError(
            "Cannot generate config for CUSTOM preset. "
            "Please provide explicit context_policy configuration."
        )


def _minimal_preset() -> ContextPolicy:
    """Minimal context management (compaction disabled).

    Best for:
    - Short workflows (1-3 steps)
    - Small context windows
    - When you want full control

    Configuration:
    - Compaction: Disabled
    - Notes: Not configured
    - Retrieval: Not configured
    """
    return ContextPolicy(
        compaction=Compaction(enabled=False),
        notes=None,
        retrieval=None,
    )


def _balanced_preset(pattern_type: str | None = None) -> ContextPolicy:
    """Balanced context management for typical workflows.

    Best for:
    - Most workflows (3-10 steps)
    - Medium context windows
    - General-purpose use

    Configuration:
    - Compaction: Enabled at 100K tokens, 35% summary ratio
    - Adaptive preserve_recent_messages: 8-20 based on pattern type
    - Notes: Not configured (optional)
    - Retrieval: Not configured (optional)

    Adaptive Behavior:
    - Chain/Evaluator: 8 messages
    - Workflow/Parallel/Routing: 12 messages
    - Orchestrator: 15 messages
    - Graph: 20 messages
    """
    preserve_messages = get_adaptive_preserve_messages(pattern_type, base_value=12)

    return ContextPolicy(
        compaction=Compaction(
            enabled=True,
            when_tokens_over=100_000,
            summary_ratio=0.35,
            preserve_recent_messages=preserve_messages,
        ),
        notes=None,
        retrieval=None,
    )


def _long_run_preset(pattern_type: str | None = None) -> ContextPolicy:
    """Optimized for long-running, multi-step workflows.

    Best for:
    - Research workflows (10+ steps)
    - Multi-agent collaboration
    - Long context requirements
    - Cross-step continuity

    Configuration:
    - Compaction: Enabled at 80K tokens, 40% summary ratio
    - Adaptive preserve_recent_messages: 8-20 based on pattern type
    - Notes: Configured with 20 recent notes (requires file path from user)
    - Retrieval: JIT tools enabled (grep, search, head, tail)

    Adaptive Behavior:
    - Chain/Evaluator: 8 messages (fewer total steps)
    - Workflow/Parallel/Routing: 12 messages
    - Orchestrator: 15 messages (worker coordination)
    - Graph: 20 messages (loops require more history)
    """
    preserve_messages = get_adaptive_preserve_messages(pattern_type, base_value=15)

    return ContextPolicy(
        compaction=Compaction(
            enabled=True,
            when_tokens_over=80_000,
            summary_ratio=0.40,
            preserve_recent_messages=preserve_messages,
        ),
        notes=Notes(
            file="artifacts/notes.md",
            include_last=20,
            format="markdown",
        ),
        retrieval=Retrieval(
            jit_tools=["grep", "search", "head", "tail"],
            mcp_servers=None,
        ),
    )


def _interactive_preset(pattern_type: str | None = None) -> ContextPolicy:
    """Optimized for interactive, chat-like workflows.

    Best for:
    - Conversational agents
    - User-facing chat interfaces
    - Frequent back-and-forth exchanges

    Configuration:
    - Compaction: Enabled at 50K tokens, 30% summary ratio
    - Adaptive preserve_recent_messages: 8-20 based on pattern type
    - Notes: Not configured (history is the primary context)
    - Retrieval: Not configured (minimal tool use)

    Adaptive Behavior:
    - Chain/Evaluator: 8 messages
    - Workflow/Parallel/Routing: 12 messages
    - Orchestrator: 15 messages
    - Graph: 20 messages
    """
    preserve_messages = get_adaptive_preserve_messages(pattern_type, base_value=16)

    return ContextPolicy(
        compaction=Compaction(
            enabled=True,
            when_tokens_over=50_000,
            summary_ratio=0.30,
            preserve_recent_messages=preserve_messages,
        ),
        notes=None,
        retrieval=None,
    )


def apply_preset_to_spec(
    spec_data: dict[str, Any], preset: str | ContextPreset, pattern_type: str | None = None
) -> None:
    """Apply a context preset to a spec dictionary (in-place modification).

    This function modifies the spec_data dictionary to include the preset's
    context_policy configuration. If context_policy already exists, it will
    be merged with preset values (existing values take precedence).

    Args:
        spec_data: Workflow specification dictionary (will be modified)
        preset: Preset name or ContextPreset enum value
        pattern_type: Optional workflow pattern type for adaptive preserve_recent_messages

    Examples:
        >>> spec_data = {"version": 0, "name": "test", ...}
        >>> apply_preset_to_spec(spec_data, "long_run", pattern_type="chain")
        >>> spec_data["context_policy"]["compaction"]["enabled"]
        True
        >>> spec_data["context_policy"]["compaction"]["preserve_recent_messages"]
        8
    """
    # Extract pattern type from spec_data if not provided
    if pattern_type is None and "pattern" in spec_data:
        pattern_type = spec_data["pattern"].get("type")

    preset_policy = get_context_preset(preset, pattern_type=pattern_type)

    # Convert to dict for merging
    preset_dict = preset_policy.model_dump(exclude_none=True)

    # Merge with existing context_policy (existing values win)
    if "context_policy" not in spec_data:
        spec_data["context_policy"] = preset_dict
    else:
        # Merge top-level keys (compaction, notes, retrieval)
        for key, value in preset_dict.items():
            if key not in spec_data["context_policy"]:
                spec_data["context_policy"][key] = value
            elif isinstance(value, dict):
                # Merge nested dictionaries
                if not isinstance(spec_data["context_policy"][key], dict):
                    spec_data["context_policy"][key] = value
                else:
                    for nested_key, nested_value in value.items():
                        if nested_key not in spec_data["context_policy"][key]:
                            spec_data["context_policy"][key][nested_key] = nested_value


def describe_presets() -> str:
    """Generate a human-readable description of all available presets.

    Returns:
        Markdown-formatted string describing all presets

    Examples:
        >>> print(describe_presets())
        # Context Management Presets
        ...
    """
    descriptions = [
        "# Context Management Presets\n",
        "Available presets for workflow context management:\n",
        "\n## minimal",
        _minimal_preset().__doc__ or "",
        "\n## balanced",
        _balanced_preset().__doc__ or "",
        "\n## long_run",
        _long_run_preset().__doc__ or "",
        "\n## interactive",
        _interactive_preset().__doc__ or "",
    ]
    return "\n".join(descriptions)

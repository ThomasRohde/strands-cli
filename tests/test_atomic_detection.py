"""Unit tests for atomic detection and resolution utilities."""

from pathlib import Path

from strands_cli.atomic.core import (
    ATOMIC_LABEL,
    ATOMIC_LABEL_VALUE,
    check_atomic_invariants,
    find_atomic_specs,
    is_atomic_spec,
    resolve_atomic_spec,
)
from strands_cli.types import PatternType, Spec


def _atomic_spec(pattern: PatternType = PatternType.CHAIN) -> Spec:
    """Build a minimal atomic spec for testing."""
    pattern_block = (
        {
            "type": "chain",
            "config": {
                "steps": [
                    {
                        "agent": "worker",
                        "input": "Go",
                    }
                ]
            },
        }
        if pattern == PatternType.CHAIN
        else {
            "type": "workflow",
            "config": {
                "tasks": [
                    {
                        "id": "only",
                        "agent": "worker",
                    }
                ]
            },
        }
    )

    return Spec.model_validate(
        {
            "version": 0,
            "name": "atomic-test",
            "runtime": {
                "provider": "openai",
                "model_id": "gpt-4o-mini",
            },
            "agents": {
                "worker": {
                    "prompt": "Do work",
                }
            },
            "pattern": pattern_block,
            "metadata": {
                "labels": {
                    ATOMIC_LABEL: ATOMIC_LABEL_VALUE,
                }
            },
        }
    )


def test_check_atomic_invariants_chain_passes() -> None:
    """Valid atomic chain spec yields no errors."""
    spec = _atomic_spec(PatternType.CHAIN)
    assert check_atomic_invariants(spec) == []


def test_check_atomic_invariants_workflow_with_deps_fails() -> None:
    """Workflow with deps is not atomic."""
    spec = _atomic_spec(PatternType.WORKFLOW)
    # Inject a dependency to violate invariant
    task = spec.pattern.config.tasks[0]  # type: ignore[index]
    task.deps = ["other"]

    errors = check_atomic_invariants(spec)
    assert any("dependencies" in err for err in errors)


def test_check_atomic_invariants_multiple_agents_fails() -> None:
    """Multiple agents break atomicity."""
    spec = _atomic_spec()
    spec.agents["another"] = spec.agents["worker"].model_copy()

    errors = check_atomic_invariants(spec)
    assert any("exactly one agent" in err.lower() for err in errors)


def test_is_atomic_spec_true_with_label(tmp_path: Path) -> None:
    """Label plus invariants produces True."""
    spec = _atomic_spec()
    # Save to a non-atomic path to ensure label drives detection
    path = tmp_path / "agent.yaml"
    path.write_text("metadata:\n  labels:\n    strands.io/agent_type: atomic\n", encoding="utf-8")

    assert is_atomic_spec(spec, source_path=path)


def test_find_and_resolve_atomic_specs(tmp_path: Path) -> None:
    """Resolver prefers agents/atomic/<name> subdirs and falls back to label detection."""
    atomic_dir = tmp_path / "agents" / "atomic" / "alpha"
    atomic_dir.mkdir(parents=True)
    preferred = atomic_dir / "alpha.yaml"
    preferred.write_text("kind: agent\n", encoding="utf-8")

    labeled_dir = tmp_path / "agents" / "misc"
    labeled_dir.mkdir(parents=True)
    labeled = labeled_dir / "beta.yaml"
    labeled.write_text(
        "metadata:\n  labels:\n    strands.io/agent_type: atomic\n", encoding="utf-8"
    )

    discovered = find_atomic_specs(tmp_path)
    assert preferred in discovered
    assert labeled in discovered

    resolved = resolve_atomic_spec("alpha", tmp_path)
    assert resolved == preferred

    resolved_labeled = resolve_atomic_spec("beta", tmp_path)
    assert resolved_labeled == labeled

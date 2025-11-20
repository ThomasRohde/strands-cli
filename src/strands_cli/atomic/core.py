"""Core helpers for working with atomic agents.

These utilities are used by CLI commands to:
  - Detect whether a spec is atomic (label + invariants)
  - Resolve atomic manifests by name from the repository
  - Enumerate atomic manifests for discovery

The runtime does not enforce atomic semantics; these are tooling-level checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ruamel.yaml import YAML

from strands_cli.types import PatternType, Spec

ATOMIC_LABEL = "strands.io/agent_type"
ATOMIC_LABEL_VALUE = "atomic"


def _path_is_under_atomic(root: Path, path: Path) -> bool:
    """Return True if path is within agents/atomic under the root."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    parts = [p.lower() for p in rel.parts]
    return "agents" in parts and "atomic" in parts


def _has_atomic_label(metadata: Any) -> bool:
    """Check metadata.labels for the atomic marker."""
    if not isinstance(metadata, dict):
        return False
    labels = metadata.get("labels")
    if not isinstance(labels, dict):
        return False
    return labels.get(ATOMIC_LABEL) == ATOMIC_LABEL_VALUE


def check_atomic_invariants(spec: Spec) -> list[str]:
    """Validate atomic invariants on a spec.

    Returns:
        List of violation messages (empty means compliant).
    """
    errors: list[str] = []

    if len(spec.agents) != 1:
        errors.append("Atomic spec must declare exactly one agent")

    if spec.pattern.type not in (PatternType.CHAIN, PatternType.WORKFLOW):
        errors.append(f"Atomic spec must use chain or workflow pattern, found {spec.pattern.type}")
        return errors

    if spec.pattern.config is None:
        errors.append("Atomic spec missing pattern config")
        return errors

    if spec.pattern.type == PatternType.CHAIN:
        steps = spec.pattern.config.steps or []
        if len(steps) != 1:
            errors.append(f"Atomic chain must have exactly one step, found {len(steps)}")
        elif steps[0].agent and steps[0].agent not in spec.agents:
            errors.append(f"Step references unknown agent '{steps[0].agent}'")

    if spec.pattern.type == PatternType.WORKFLOW:
        tasks = spec.pattern.config.tasks or []
        if len(tasks) != 1:
            errors.append(f"Atomic workflow must have exactly one task, found {len(tasks)}")
        else:
            task = tasks[0]
            if task.agent and task.agent not in spec.agents:
                errors.append(f"Task references unknown agent '{task.agent}'")
            if task.deps:
                errors.append("Atomic workflow task must not declare dependencies")

    return errors


def is_atomic_spec(spec: Spec, source_path: Path | None = None) -> bool:
    """Determine if a spec should be treated as atomic."""
    if _has_atomic_label(spec.metadata.model_dump() if spec.metadata else None):
        return not check_atomic_invariants(spec)

    if source_path is not None:
        root = Path.cwd()
        if _path_is_under_atomic(root, source_path):
            return not check_atomic_invariants(spec)

    return False


def _load_metadata_labels(path: Path) -> dict[str, str] | None:
    """Lightweight YAML metadata.labels loader for discovery."""
    yaml = YAML(typ="safe", pure=True)
    try:
        data = yaml.load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    labels = metadata.get("labels")
    return labels if isinstance(labels, dict) else None


def _iter_candidate_files(root: Path) -> Iterable[Path]:
    """Yield YAML files that could hold atomic agents."""
    yield from root.glob("agents/atomic/**/*.yaml")
    yield from root.glob("agents/atomic/**/*.yml")
    # Fallback: any agents directory with a label
    yield from root.glob("agents/**/*.yaml")
    yield from root.glob("agents/**/*.yml")


def find_atomic_specs(root: Path | str = ".") -> list[Path]:
    """Discover atomic manifest files under the repository root."""
    root_path = Path(root)
    seen: set[Path] = set()
    results: list[Path] = []

    for candidate in _iter_candidate_files(root_path):
        if candidate in seen:
            continue
        seen.add(candidate)
        
        # Skip test files
        if candidate.name in ("tests.yaml", "tests.yml"):
            continue

        # Directories under agents/atomic are treated as atomic
        if _path_is_under_atomic(root_path, candidate):
            results.append(candidate)
            continue

        labels = _load_metadata_labels(candidate)
        if labels and labels.get(ATOMIC_LABEL) == ATOMIC_LABEL_VALUE:
            results.append(candidate)

    return results


def resolve_atomic_spec(name: str, root: Path | str = ".") -> Path | None:
    """Resolve an atomic manifest path by name.

    Search order:
        1) agents/atomic/<name>/<name>.yaml (new self-contained structure)
        2) agents/atomic/<name>.yaml (legacy flat structure)
        3) any file under agents/atomic/** matching name
        4) any labeled atomic manifest under agents/** matching name
    """
    root_path = Path(root)

    # Try new self-contained structure first
    preferred_new = root_path / "agents" / "atomic" / name / f"{name}.yaml"
    if preferred_new.exists():
        return preferred_new
    
    # Try with .yml extension
    preferred_new_yml = root_path / "agents" / "atomic" / name / f"{name}.yml"
    if preferred_new_yml.exists():
        return preferred_new_yml

    # Legacy flat structure (for backward compatibility during transition)
    preferred_legacy = [
        root_path / "agents" / "atomic" / f"{name}.yaml",
        root_path / "agents" / "atomic" / f"{name}.yml",
    ]
    for path in preferred_legacy:
        if path.exists():
            return path

    # Fallback: search by filename match
    matches: list[Path] = []
    for path in _iter_candidate_files(root_path):
        if path.stem != name:
            continue
        if _path_is_under_atomic(root_path, path):
            return path
        labels = _load_metadata_labels(path)
        if labels and labels.get(ATOMIC_LABEL) == ATOMIC_LABEL_VALUE:
            matches.append(path)

    return matches[0] if matches else None

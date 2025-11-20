"""Atomic agent utilities (detection and resolution)."""

from strands_cli.atomic.core import (
    ATOMIC_LABEL,
    ATOMIC_LABEL_VALUE,
    check_atomic_invariants,
    find_atomic_specs,
    is_atomic_spec,
    resolve_atomic_spec,
)

__all__ = [
    "ATOMIC_LABEL",
    "ATOMIC_LABEL_VALUE",
    "check_atomic_invariants",
    "find_atomic_specs",
    "is_atomic_spec",
    "resolve_atomic_spec",
]

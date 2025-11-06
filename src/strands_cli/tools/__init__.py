"""Native tools registry and discovery."""

from strands_cli.tools.registry import get_registry

# Auto-discover happens on first get_registry() call (singleton pattern)
# No explicit initialization needed

__all__ = ["get_registry"]

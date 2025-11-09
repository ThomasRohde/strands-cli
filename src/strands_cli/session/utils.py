"""Session management utilities.

Provides helper functions for session ID generation, spec hash computation,
timestamp formatting, and spec content loading.

Functions:
    generate_session_id: Create unique UUID4 session identifier
    compute_spec_hash: SHA256 hash of workflow spec for change detection
    now_iso8601: Current UTC timestamp in ISO 8601 format
    load_spec_content: Read original spec file content for snapshots
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path


def generate_session_id() -> str:
    """Generate unique session ID.

    Creates a UUID4 identifier for new sessions. Used during session
    initialization in Phase 2 checkpoint logic.

    Returns:
        UUID4 string (e.g., 'a1b2c3d4-e5f6-7890-abcd-ef1234567890')

    Example:
        >>> session_id = generate_session_id()
        >>> len(session_id)
        36
        >>> '-' in session_id
        True
    """
    return str(uuid.uuid4())


def compute_spec_hash(spec_path: Path) -> str:
    """Compute SHA256 hash of workflow spec.

    Reads spec file as bytes and computes hex-encoded SHA256 hash for
    change detection. Stored in SessionMetadata.spec_hash and compared
    on resume to warn users if spec has changed since session creation.

    Args:
        spec_path: Path to workflow spec file (YAML or JSON)

    Returns:
        Hex-encoded SHA256 hash (64 characters)

    Raises:
        FileNotFoundError: If spec_path doesn't exist
        PermissionError: If spec_path isn't readable

    Example:
        >>> from pathlib import Path
        >>> spec_path = Path("workflow.yaml")
        >>> hash1 = compute_spec_hash(spec_path)
        >>> hash2 = compute_spec_hash(spec_path)
        >>> hash1 == hash2  # Same file = same hash
        True
    """
    content = spec_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def now_iso8601() -> str:
    """Get current timestamp in ISO 8601 format.

    Returns UTC timestamp with timezone info for consistent session
    metadata timestamps across different system configurations.

    Returns:
        ISO 8601 timestamp string (e.g., '2025-11-09T10:15:30.123456+00:00')

    Example:
        >>> timestamp = now_iso8601()
        >>> 'T' in timestamp  # Contains date/time separator
        True
        >>> timestamp.endswith('+00:00')  # UTC timezone
        True
    """
    return datetime.now(UTC).isoformat()


def load_spec_content(spec_path: Path) -> str:
    """Read original spec file content for snapshot storage.

    Loads workflow spec as UTF-8 text for storage in spec_snapshot.yaml
    during session creation. Enables spec comparison and resume from
    stored snapshot without requiring original spec file.

    Args:
        spec_path: Path to workflow spec file (YAML or JSON)

    Returns:
        Spec file content as string

    Raises:
        FileNotFoundError: If spec_path doesn't exist
        PermissionError: If spec_path isn't readable
        UnicodeDecodeError: If spec_path contains invalid UTF-8

    Example:
        >>> from pathlib import Path
        >>> spec_path = Path("workflow.yaml")
        >>> content = load_spec_content(spec_path)
        >>> 'version:' in content or '"version"' in content
        True
    """
    return spec_path.read_text(encoding="utf-8")

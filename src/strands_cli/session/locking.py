"""File-based locking for concurrent session access.

This module provides file locking mechanisms to prevent concurrent writes
to the same session, ensuring data integrity in multi-process environments.
"""

from contextlib import contextmanager
from pathlib import Path

import structlog
from filelock import FileLock, Timeout

logger = structlog.get_logger(__name__)


@contextmanager
def session_lock(session_dir: Path, timeout: float = 10.0):
    """Acquire exclusive lock on session directory.

    Prevents concurrent writes to the same session by acquiring an exclusive
    file lock. The lock file is stored at the session directory root as `.lock`.

    Args:
        session_dir: Path to session directory (e.g., session_{uuid}/)
        timeout: Lock acquisition timeout in seconds (default: 10.0)

    Raises:
        Timeout: If lock cannot be acquired within timeout period

    Example:
        >>> from pathlib import Path
        >>> session_dir = Path("/tmp/session_abc123")
        >>> with session_lock(session_dir):
        ...     # Critical section - safe concurrent access
        ...     write_session_data(session_dir)
    """
    lock_file = session_dir / ".lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(lock_file, timeout=timeout)

    logger.debug(
        "session_lock_acquire",
        session_dir=str(session_dir),
        timeout=timeout,
    )

    try:
        with lock:
            logger.debug("session_lock_acquired", session_dir=str(session_dir))
            yield
    except Timeout as e:
        logger.error(
            "session_lock_timeout",
            session_dir=str(session_dir),
            timeout=timeout,
        )
        raise TimeoutError(
            f"Failed to acquire lock for session {session_dir.name} "
            f"within {timeout}s. Another process may be writing to this session."
        ) from e
    finally:
        logger.debug("session_lock_released", session_dir=str(session_dir))

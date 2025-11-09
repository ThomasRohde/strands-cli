"""Session cleanup and expiration utilities.

Provides utilities for cleaning up expired sessions to prevent storage bloat.
Sessions can be cleaned based on age, status, and other criteria.
"""

from datetime import UTC, datetime, timedelta

import structlog

from strands_cli.session import SessionStatus
from strands_cli.session.file_repository import FileSessionRepository

logger = structlog.get_logger(__name__)


async def cleanup_expired_sessions(
    repo: FileSessionRepository,
    max_age_days: int = 7,
    keep_completed: bool = True,
) -> int:
    """Delete expired sessions based on age and status.

    Removes sessions older than the specified age threshold. Optionally
    preserves completed sessions regardless of age for audit purposes.

    Args:
        repo: Session repository to clean
        max_age_days: Delete sessions older than this many days (default: 7)
        keep_completed: Keep completed sessions regardless of age (default: True)

    Returns:
        Number of sessions deleted

    Example:
        >>> repo = FileSessionRepository()
        >>> deleted = await cleanup_expired_sessions(repo, max_age_days=30)
        >>> print(f"Deleted {deleted} expired sessions")
    """
    deleted = 0
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

    logger.info(
        "session_cleanup_start",
        max_age_days=max_age_days,
        keep_completed=keep_completed,
        cutoff=cutoff.isoformat(),
    )

    sessions = await repo.list_sessions()

    for session in sessions:
        # Parse updated timestamp
        try:
            updated = datetime.fromisoformat(session.updated_at)
        except ValueError:
            logger.warning(
                "invalid_timestamp",
                session_id=session.session_id,
                updated_at=session.updated_at,
            )
            continue

        # Check if session is expired
        if updated < cutoff:
            # Optionally skip completed sessions
            if keep_completed and session.status == SessionStatus.COMPLETED:
                logger.debug(
                    "session_kept_completed",
                    session_id=session.session_id,
                    status=session.status.value,
                    updated_at=session.updated_at,
                )
                continue

            # Delete expired session
            try:
                await repo.delete(session.session_id)
                deleted += 1
                logger.info(
                    "session_cleaned",
                    session_id=session.session_id,
                    status=session.status.value,
                    age_days=(datetime.now(UTC) - updated).days,
                )
            except Exception as e:
                logger.error(
                    "session_cleanup_failed",
                    session_id=session.session_id,
                    error=str(e),
                )

    logger.info("session_cleanup_complete", deleted_count=deleted)
    return deleted

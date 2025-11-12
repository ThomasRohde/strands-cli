"""Session management API with pagination and caching.

Provides a high-level API for session lifecycle management: listing,
retrieving, resuming, and cleaning up workflow sessions. Wraps
FileSessionRepository with LRU caching for improved performance.

Example:
    >>> manager = SessionManager()
    >>> # List recent paused sessions
    >>> sessions = await manager.list_sessions(status=SessionStatus.PAUSED, limit=10)
    >>> # Resume first session
    >>> if sessions:
    ...     result = await manager.resume(sessions[0].metadata.session_id, hitl_response="approved")
    >>> # Clean up old sessions
    >>> deleted = await manager.cleanup(older_than_days=7)
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from strands_cli.session import (
    SessionMetadata,
    SessionState,
    SessionStatus,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.resume import run_resume
from strands_cli.types import RunResult

logger = structlog.get_logger(__name__)


class SessionManager:
    """High-level session management API with caching.

    Wraps FileSessionRepository with pagination, filtering, and LRU cache
    for improved performance. Provides convenient methods for common session
    operations without exposing low-level repository details.

    Caching Strategy:
        - Cache key: session_id
        - Cache value: (SessionState, timestamp)
        - TTL: 5 minutes
        - Max size: 100 sessions (LRU eviction)
        - Invalidate on: delete(), resume() completion

    Thread Safety:
        Not thread-safe. Create separate instances per thread/async context.
    """

    def __init__(self, storage_dir: Path | None = None):
        """Initialize session manager.

        Args:
            storage_dir: Base directory for sessions
                (default: {data_dir}/sessions from platformdirs)
        """
        self.repo = FileSessionRepository(storage_dir)
        self._cache: OrderedDict[str, tuple[SessionState, datetime]] = OrderedDict()
        self._cache_ttl = timedelta(minutes=5)
        self._max_cache_size = 100
        logger.debug(
            "session_manager_init",
            storage_dir=str(self.repo.storage_dir),
            cache_ttl_minutes=5,
            max_cache_size=100,
        )

    def _is_cache_valid(self, timestamp: datetime) -> bool:
        """Check if cache entry is within TTL.

        Args:
            timestamp: Cache entry timestamp

        Returns:
            True if entry is still valid
        """
        return datetime.now(UTC) - timestamp < self._cache_ttl

    def _invalidate_cache(self, session_id: str) -> None:
        """Remove session from cache.

        Args:
            session_id: Session ID to invalidate
        """
        if session_id in self._cache:
            del self._cache[session_id]
            logger.debug("cache_invalidated", session_id=session_id)

    async def list_sessions(
        self,
        offset: int = 0,
        limit: int = 100,
        status: SessionStatus | None = None,
        workflow_name: str | None = None,
    ) -> list[SessionState]:
        """List sessions with pagination and filtering.

        Returns sessions sorted by updated_at descending (newest first).

        Args:
            offset: Skip this many sessions (default: 0)
            limit: Return at most this many sessions (default: 100, max: 1000)
            status: Filter by session status (optional)
            workflow_name: Filter by workflow name (optional)

        Returns:
            List of session states matching filters

        Raises:
            ValueError: If offset < 0 or limit < 1 or limit > 1000

        Example:
            >>> # Get 10 most recent paused sessions
            >>> sessions = await manager.list(status=SessionStatus.PAUSED, limit=10)
            >>> # Paginate through all sessions
            >>> page1 = await manager.list(offset=0, limit=100)
            >>> page2 = await manager.list(offset=100, limit=100)
        """
        # Validate pagination parameters
        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if limit > 1000:
            raise ValueError(f"limit must be <= 1000, got {limit}")

        logger.info(
            "session_list_requested",
            offset=offset,
            limit=limit,
            status=status.value if status else None,
            workflow_name=workflow_name,
        )

        # Get all session metadata
        metadata_list = await self.repo.list_sessions()

        # Filter by status
        if status:
            metadata_list = [m for m in metadata_list if m.status == status]

        # Filter by workflow name
        if workflow_name:
            metadata_list = [m for m in metadata_list if m.workflow_name == workflow_name]

        # Sort by updated_at descending (newest first)
        metadata_list.sort(
            key=lambda m: datetime.fromisoformat(m.updated_at),
            reverse=True,
        )

        # Apply pagination
        paginated = metadata_list[offset : offset + limit]

        # Load full session states for paginated results
        states = []
        for metadata in paginated:
            state = await self.get(metadata.session_id)
            if state:
                states.append(state)

        logger.info(
            "session_list_complete",
            total_count=len(metadata_list),
            returned_count=len(states),
        )

        return states

    async def list(
        self,
        offset: int = 0,
        limit: int = 100,
        status: SessionStatus | None = None,
        workflow_name: str | None = None,
    ) -> list[SessionState]:
        """Backward-compatible alias for list_sessions().

        Args:
            offset: Skip this many sessions (default: 0)
            limit: Return at most this many sessions (default: 100, max: 1000)
            status: Filter by session status (optional)
            workflow_name: Filter by workflow name (optional)

        Returns:
            List of session states matching filters
        """
        return await self.list_sessions(
            offset=offset,
            limit=limit,
            status=status,
            workflow_name=workflow_name,
        )

    async def get(self, session_id: str) -> SessionState | None:
        """Get session by ID with caching.

        Retrieves session from cache if available and valid, otherwise
        loads from repository and updates cache.

        Args:
            session_id: Session ID to retrieve

        Returns:
            SessionState if found, None otherwise

        Raises:
            FileNotFoundError: If session doesn't exist

        Example:
            >>> state = await manager.get("abc-123")
            >>> if state:
            ...     print(state.metadata.status)
        """
        # Check cache first
        if session_id in self._cache:
            cached_state, timestamp = self._cache[session_id]
            if self._is_cache_valid(timestamp):
                logger.debug("cache_hit", session_id=session_id)
                # Move to end (most recently used)
                self._cache.move_to_end(session_id)
                return cached_state
            else:
                # Cache expired
                logger.debug("cache_expired", session_id=session_id)
                del self._cache[session_id]

        # Load from repository
        logger.debug("cache_miss", session_id=session_id)
        state = await self.repo.load(session_id)

        if state is None:
            logger.debug("session_not_found", session_id=session_id)
            return None

        # Update cache with LRU eviction
        if session_id in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(session_id)
            self._cache[session_id] = (state, datetime.now(UTC))
        else:
            # Add new entry
            self._cache[session_id] = (state, datetime.now(UTC))
            # Evict oldest if over max size
            if len(self._cache) > self._max_cache_size:
                evicted_id = next(iter(self._cache))
                del self._cache[evicted_id]
                logger.debug("cache_evicted", evicted_session_id=evicted_id)

        logger.debug("cache_updated", session_id=session_id)

        return state

    async def resume(
        self,
        session_id: str,
        hitl_response: str | None = None,
        debug: bool = False,
        verbose: bool = False,
        trace: bool = False,
    ) -> RunResult:
        """Resume paused session.

        Delegates to run_resume() from session.resume module. Invalidates
        cache after successful resume.

        Args:
            session_id: Session ID to resume
            hitl_response: User response when resuming from HITL pause (optional)
            debug: Enable debug logging
            verbose: Enable verbose output
            trace: Enable trace export

        Returns:
            RunResult from resumed execution

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionAlreadyCompletedError: If session already completed
            ValueError: If spec hash mismatch or other validation failure

        Example:
            >>> result = await manager.resume("abc-123", hitl_response="approved")
            >>> if result.success:
            ...     print("Resume successful")
        """
        logger.info("session_resume_requested", session_id=session_id)

        try:
            # Delegate to run_resume
            result = await run_resume(
                session_id=session_id,
                hitl_response=hitl_response,
                debug=debug,
                verbose=verbose,
                trace=trace,
            )

            logger.info(
                "session_resume_complete",
                session_id=session_id,
                success=result.success,
            )

            return result
        finally:
            # Always invalidate cache to prevent stale entries
            self._invalidate_cache(session_id)

    async def cleanup(
        self,
        older_than_days: int = 7,
        status_filter: Sequence[SessionStatus] | None = None,
    ) -> int:
        """Clean up old sessions.

        Deletes sessions older than the specified age. Optionally filters
        by status to preserve specific session types.

        Args:
            older_than_days: Delete sessions older than this many days (default: 7)
            status_filter: Only delete sessions with these statuses (default: None = all)

        Returns:
            Number of sessions deleted

        Example:
            >>> # Clean up all sessions older than 30 days
            >>> deleted = await manager.cleanup(older_than_days=30)
            >>> # Clean up only failed sessions older than 7 days
            >>> deleted = await manager.cleanup(
            ...     older_than_days=7, status_filter=[SessionStatus.FAILED]
            ... )
        """
        logger.info(
            "session_cleanup_requested",
            older_than_days=older_than_days,
            status_filter=[s.value for s in status_filter] if status_filter else None,
        )

        deleted = 0
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        # Get all sessions
        metadata_list: list[SessionMetadata] = await self.repo.list_sessions()

        for metadata in metadata_list:
            # Parse updated timestamp
            try:
                updated = datetime.fromisoformat(metadata.updated_at)
            except ValueError:
                logger.warning(
                    "invalid_timestamp",
                    session_id=metadata.session_id,
                    updated_at=metadata.updated_at,
                )
                continue

            # Check if session is expired
            if updated < cutoff:
                # Apply status filter if provided
                if status_filter is not None and metadata.status not in status_filter:
                    logger.debug(
                        "session_kept_status_filter",
                        session_id=metadata.session_id,
                        status=metadata.status.value,
                    )
                    continue

                # Delete expired session
                try:
                    await self.repo.delete(metadata.session_id)
                    self._invalidate_cache(metadata.session_id)
                    deleted += 1
                    logger.info(
                        "session_cleaned",
                        session_id=metadata.session_id,
                        status=metadata.status.value,
                        age_days=(datetime.now(UTC) - updated).days,
                    )
                except Exception as e:
                    logger.error(
                        "session_cleanup_failed",
                        session_id=metadata.session_id,
                        error=str(e),
                    )

        logger.info("session_cleanup_complete", deleted_count=deleted)
        return deleted

    async def delete(self, session_id: str) -> None:
        """Delete session by ID.

        Removes session from repository and invalidates cache.

        Args:
            session_id: Session ID to delete

        Example:
            >>> await manager.delete("abc-123")
        """
        logger.info("session_delete_requested", session_id=session_id)

        await self.repo.delete(session_id)
        self._invalidate_cache(session_id)

        logger.info("session_delete_complete", session_id=session_id)

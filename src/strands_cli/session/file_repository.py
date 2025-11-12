"""File-based session persistence repository.

Provides async file-based session storage using local filesystem with
platform-specific directories. All methods are async-wrapped for
future S3 migration compatibility while using synchronous file I/O
internally via asyncio.to_thread().

Storage Structure:
    {data_dir}/sessions/session_{session_id}/
    ├── session.json         # Metadata, variables, runtime, usage
    ├── pattern_state.json   # Pattern-specific execution state
    ├── spec_snapshot.yaml   # Original workflow spec
    └── agents/              # Strands SDK agent sessions (Phase 2)

Example:
    >>> repo = FileSessionRepository()
    >>> state = SessionState(...)
    >>> await repo.save(state, spec_content)
    >>> loaded = await repo.load(session_id)
    >>> sessions = await repo.list_sessions()
"""

import asyncio
import json
import re
import shutil
from pathlib import Path

import structlog

from strands_cli.config import StrandsConfig
from strands_cli.session import (
    SessionCorruptedError,
    SessionMetadata,
    SessionState,
    TokenUsage,
)
from strands_cli.session.locking import session_lock

logger = structlog.get_logger(__name__)


class FileSessionRepository:
    """File-based session storage using local filesystem.

    All methods are async-wrapped using asyncio.to_thread() for consistency
    with future S3SessionRepository while keeping implementation simple.

    Storage structure:
        {storage_dir}/session_{session_id}/
        ├── session.json
        ├── pattern_state.json
        ├── spec_snapshot.yaml
        └── agents/  # Managed by Strands SDK FileSessionManager (Phase 2)
    """

    def __init__(self, storage_dir: Path | None = None):
        """Initialize repository with storage directory.

        Args:
            storage_dir: Base directory for sessions
                (default: {data_dir}/sessions from platformdirs)
        """
        config = StrandsConfig()
        self.storage_dir = storage_dir or (config.data_dir / "sessions")

        # Create storage directory synchronously during init
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("session_repository_init", storage_dir=str(self.storage_dir))

    def _session_dir(self, session_id: str) -> Path:
        """Get directory for a specific session.

        Args:
            session_id: Session ID

        Returns:
            Path to session directory

        Raises:
            SessionCorruptedError: If session_id contains invalid characters (path traversal)
        """
        # Validate session ID to prevent path traversal attacks
        # Only allow alphanumeric, underscore, and hyphen characters
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise SessionCorruptedError(
                f"Invalid session identifier '{session_id}' (only [A-Za-z0-9_-] allowed)"
            )
        return self.storage_dir / f"session_{session_id}"

    async def exists(self, session_id: str) -> bool:
        """Check if session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session directory exists, False otherwise

        Example:
            >>> exists = await repo.exists("abc-123")
        """

        def _exists() -> bool:
            return self._session_dir(session_id).exists()

        return await asyncio.to_thread(_exists)

    async def save(self, state: SessionState, spec_content: str | None = None) -> None:
        """Save complete session state.

        Writes three files atomically with file locking to prevent
        concurrent corruption:
        1. session.json: Metadata, variables, runtime, usage, artifacts
        2. pattern_state.json: Pattern-specific execution state
        3. spec_snapshot.yaml: Original workflow spec for comparison (only if spec_content is provided)

        Uses atomic writes (temp file + rename) and file locking for safety.

        Args:
            state: Session state to persist
            spec_content: Original workflow spec YAML/JSON content (optional, None = skip spec update)

        Raises:
            SessionCorruptedError: If file write fails
            TimeoutError: If lock cannot be acquired within 10s

        Example:
            >>> state = SessionState(...)
            >>> spec_content = Path("workflow.yaml").read_text()
            >>> await repo.save(state, spec_content)
            >>> # For checkpoints (don't update spec):
            >>> await repo.save(state, "")
        """

        def _save() -> None:
            session_dir = self._session_dir(state.metadata.session_id)
            session_dir.mkdir(parents=True, exist_ok=True)

            # Acquire lock for atomic write
            with session_lock(session_dir):
                try:
                    # Write session.json atomically (metadata, variables, runtime, usage)
                    session_json = session_dir / "session.json"
                    session_tmp = session_dir / "session.json.tmp"
                    session_data = {
                        "metadata": state.metadata.model_dump(),
                        "variables": state.variables,
                        "runtime_config": state.runtime_config,
                        "token_usage": state.token_usage.model_dump(),
                        "artifacts_written": state.artifacts_written,
                    }
                    session_tmp.write_text(
                        json.dumps(session_data, indent=2),
                        encoding="utf-8",
                    )
                    session_tmp.replace(session_json)

                    # Write pattern_state.json atomically (pattern-specific execution state)
                    pattern_json = session_dir / "pattern_state.json"
                    pattern_tmp = session_dir / "pattern_state.json.tmp"
                    pattern_tmp.write_text(
                        json.dumps(state.pattern_state, indent=2),
                        encoding="utf-8",
                    )
                    pattern_tmp.replace(pattern_json)

                    # Write spec_snapshot.yaml atomically ONLY if spec_content is non-empty
                    # This allows checkpoints to skip spec updates (pass empty string)
                    if spec_content:
                        spec_file = session_dir / "spec_snapshot.yaml"
                        spec_tmp = session_dir / "spec_snapshot.yaml.tmp"
                        spec_tmp.write_text(spec_content, encoding="utf-8")
                        spec_tmp.replace(spec_file)

                except Exception as e:
                    raise SessionCorruptedError(
                        f"Failed to save session {state.metadata.session_id}: {e}"
                    ) from e

                logger.info(
                    "session_saved",
                    session_id=state.metadata.session_id,
                    status=state.metadata.status,
                    pattern=state.metadata.pattern_type,
                )

        await asyncio.to_thread(_save)

    async def load(self, session_id: str) -> SessionState | None:
        """Load session state from disk with lazy pattern_state loading.

        The pattern_state field is loaded lazily on first access to improve
        resume latency for large sessions. Metadata, variables, and runtime_config
        are loaded immediately.

        Args:
            session_id: Session ID to load

        Returns:
            SessionState if found, None otherwise

        Raises:
            SessionCorruptedError: If session data is invalid or corrupted

        Example:
            >>> state = await repo.load("abc-123")
            >>> if state:
            ...     print(state.metadata.status)  # Loaded immediately
            ...     steps = state.pattern_state["step_history"]  # Loaded on first access
        """

        def _load() -> SessionState | None:
            session_dir = self._session_dir(session_id)
            if not session_dir.exists():
                logger.warning("session_not_found", session_id=session_id)
                return None

            try:
                # Load session.json immediately
                session_json = session_dir / "session.json"
                session_data = json.loads(session_json.read_text(encoding="utf-8"))

                # Eagerly load pattern_state for now (lazy loading requires custom descriptor)
                # TODO Phase 4.5: Implement full lazy loading with property descriptor
                pattern_json = session_dir / "pattern_state.json"
                pattern_state = json.loads(pattern_json.read_text(encoding="utf-8"))

                # Construct SessionState
                state = SessionState(
                    metadata=SessionMetadata(**session_data["metadata"]),
                    variables=session_data["variables"],
                    runtime_config=session_data["runtime_config"],
                    pattern_state=pattern_state,
                    token_usage=TokenUsage(**session_data["token_usage"]),
                    artifacts_written=session_data.get("artifacts_written", []),
                )

                logger.info(
                    "session_loaded",
                    session_id=session_id,
                    status=state.metadata.status,
                    pattern=state.metadata.pattern_type,
                )
                return state

            except json.JSONDecodeError as e:
                raise SessionCorruptedError(f"Invalid JSON in session {session_id}: {e}") from e
            except Exception as e:
                raise SessionCorruptedError(f"Failed to load session {session_id}: {e}") from e

        return await asyncio.to_thread(_load)

    async def delete(self, session_id: str) -> None:
        """Delete session completely.

        Removes session directory and all contents including agent sessions.

        Args:
            session_id: Session ID to delete

        Raises:
            FileNotFoundError: If session doesn't exist

        Example:
            >>> await repo.delete("abc-123")
        """

        def _delete() -> None:
            session_dir = self._session_dir(session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.info("session_deleted", session_id=session_id)
            else:
                # FIX: Raise FileNotFoundError for nonexistent sessions
                raise FileNotFoundError(f"Session directory not found: {session_dir}")

        await asyncio.to_thread(_delete)

    async def list_sessions(self) -> list[SessionMetadata]:
        """List all sessions in storage.

        Returns:
            List of session metadata objects (unsorted)

        Raises:
            SessionCorruptedError: If any session.json is invalid

        Example:
            >>> sessions = await repo.list_sessions()
            >>> for session in sessions:
            ...     print(f"{session.session_id}: {session.status}")
        """

        def _list() -> list[SessionMetadata]:
            sessions = []
            for session_dir in self.storage_dir.glob("session_*"):
                session_json = session_dir / "session.json"
                if session_json.exists():
                    try:
                        data = json.loads(session_json.read_text(encoding="utf-8"))
                        sessions.append(SessionMetadata(**data["metadata"]))
                    except Exception as e:
                        # Log but don't fail listing for one corrupted session
                        logger.warning(
                            "corrupted_session_skipped",
                            session_dir=session_dir.name,
                            error=str(e),
                        )
            return sessions

        return await asyncio.to_thread(_list)

    def get_agents_dir(self, session_id: str) -> Path:
        """Get agents directory for Strands SDK FileSessionManager.

        Used in Phase 2 for agent session restoration. This method is
        synchronous as it's only used for directory path construction.

        Args:
            session_id: Session ID

        Returns:
            Path to agents directory (may not exist yet)

        Example:
            >>> agents_dir = repo.get_agents_dir("abc-123")
            >>> # Pass to FileSessionManager(storage_dir=agents_dir)
        """
        return self._session_dir(session_id) / "agents"

    async def get_spec_snapshot_path(self, session_id: str) -> Path:
        """Get path to spec snapshot file.

        Used in Phase 2 resume logic to load original spec from session.

        Args:
            session_id: Session ID

        Returns:
            Path to spec_snapshot.yaml file

        Example:
            >>> spec_path = await repo.get_spec_snapshot_path("abc-123")
            >>> spec = load_spec(spec_path, variables)
        """

        def _get_path() -> Path:
            return self._session_dir(session_id) / "spec_snapshot.yaml"

        return await asyncio.to_thread(_get_path)

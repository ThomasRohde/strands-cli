"""Structured notes manager for workflow execution history.

Provides persistent note-taking capabilities for long-running workflows,
enabling cross-step continuity and multi-session workflow resumption.

Key features:
- Markdown-formatted notes with ISO8601 timestamps
- Agent attribution and step tracking
- Thread-safe concurrent writes via filelock
- Read last N notes for context injection
- Atomic writes for reliability

Format:
    ## [2025-11-07T14:32:00Z] — Agent: research-agent (Step 1)
    - **Input**: Analyze sentiment of customer reviews
    - **Tools used**: http_request, file_read
    - **Outcome**: Positive sentiment (0.82 score)
"""

from datetime import UTC, datetime
from pathlib import Path

import structlog
from filelock import FileLock

logger = structlog.get_logger(__name__)


class NotesManagerError(Exception):
    """Raised when notes operations fail."""

    pass


class NotesManager:
    """Manages structured workflow notes with thread-safe file operations.

    Handles:
    - Appending notes after each workflow step/task
    - Reading last N notes for context injection
    - Markdown formatting with timestamps and agent attribution
    - Concurrent write safety via file locking

    Example:
        manager = NotesManager("artifacts/workflow-notes.md")
        manager.append_entry(
            timestamp="2025-11-07T14:32:00Z",
            agent_name="research-agent",
            step_index=1,
            input_summary="Analyze reviews",
            tools_used=["http_request", "file_read"],
            outcome="Found 247 positive reviews"
        )
        last_notes = manager.read_last_n(3)
    """

    def __init__(self, file_path: str):
        """Initialize notes manager.

        Args:
            file_path: Path to notes file (e.g., "artifacts/workflow-notes.md")
        """
        self.file_path = Path(file_path)
        self.lock_path = Path(f"{file_path}.lock")

        # Ensure parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "notes_manager_initialized",
            file_path=str(self.file_path),
            lock_path=str(self.lock_path),
        )

    def append_entry(
        self,
        timestamp: str,
        agent_name: str,
        step_index: int,
        input_summary: str,
        tools_used: list[str] | None,
        outcome: str,
    ) -> None:
        """Append a note entry to the notes file.

        Thread-safe operation using file locking for concurrent writes.

        Args:
            timestamp: ISO8601 timestamp (e.g., "2025-11-07T14:32:00Z")
            agent_name: Name/ID of the agent that executed this step
            step_index: Step number (1-based)
            input_summary: Brief description of step input/prompt
            tools_used: List of tool names used, or None
            outcome: Brief description of step outcome/result

        Raises:
            NotesManagerError: If file write fails
        """
        entry = self._format_entry(
            timestamp=timestamp,
            agent_name=agent_name,
            step_index=step_index,
            input_summary=input_summary,
            tools_used=tools_used,
            outcome=outcome,
        )

        logger.debug(
            "appending_note_entry",
            agent=agent_name,
            step=step_index,
            file=str(self.file_path),
        )

        try:
            # Use file lock for concurrent write safety
            lock = FileLock(self.lock_path, timeout=10)
            with lock, open(self.file_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n\n")

        except Exception as e:
            logger.error(
                "note_append_failed",
                error=str(e),
                file=str(self.file_path),
            )
            raise NotesManagerError(f"Failed to append note entry: {e}") from e

    def read_last_n(self, n: int) -> str:
        """Read the last N note entries from the file.

        Args:
            n: Number of recent entries to read

        Returns:
            Markdown string containing last N entries, or empty string if file doesn't exist

        Raises:
            NotesManagerError: If file read fails
        """
        return self.get_last_n_for_injection(n)

    def get_last_n_for_injection(self, n: int) -> str:
        """Read the last N note entries for injection into agent context.

        This is the primary method for retrieving notes to inject into agent prompts.
        Alias: read_last_n() is maintained for backwards compatibility.

        Args:
            n: Number of recent entries to read

        Returns:
            Markdown string containing last N entries, or empty string if file doesn't exist

        Raises:
            NotesManagerError: If file read fails
        """
        if not self.file_path.exists():
            logger.debug("notes_file_not_found", file=str(self.file_path))
            return ""

        try:
            with open(self.file_path, encoding="utf-8") as f:
                content = f.read()

            # Split on ## headers (note entries)
            entries = [
                entry.strip()
                for entry in content.split("##")
                if entry.strip()
            ]

            if not entries:
                return ""

            # Get last N entries
            selected_entries = entries[-n:] if len(entries) > n else entries

            # Reconstruct with ## prefixes
            result = "\n\n".join(f"## {entry}" for entry in selected_entries)

            logger.debug(
                "read_last_n_notes",
                requested=n,
                found=len(entries),
                returned=len(selected_entries),
            )

            return result

        except Exception as e:
            logger.error(
                "note_read_failed",
                error=str(e),
                file=str(self.file_path),
            )
            raise NotesManagerError(f"Failed to read notes: {e}") from e

    def _format_entry(
        self,
        timestamp: str,
        agent_name: str,
        step_index: int,
        input_summary: str,
        tools_used: list[str] | None,
        outcome: str,
    ) -> str:
        """Format a note entry as Markdown.

        Args:
            timestamp: ISO8601 timestamp
            agent_name: Agent name/ID
            step_index: Step number
            input_summary: Step input description
            tools_used: List of tool names, or None
            outcome: Step outcome description

        Returns:
            Formatted Markdown entry
        """
        tools_str = ", ".join(tools_used) if tools_used else "None"

        # Truncate long inputs/outcomes for readability
        input_truncated = (
            input_summary[:200] + "..."
            if len(input_summary) > 200
            else input_summary
        )
        outcome_truncated = (
            outcome[:200] + "..." if len(outcome) > 200 else outcome
        )

        return f"""## [{timestamp}] — Agent: {agent_name} (Step {step_index})
- **Input**: {input_truncated}
- **Tools used**: {tools_str}
- **Outcome**: {outcome_truncated}"""

    @staticmethod
    def generate_timestamp() -> str:
        """Generate ISO8601 timestamp for current UTC time.

        Returns:
            ISO8601 timestamp string (e.g., "2025-11-07T14:32:00Z")
        """
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

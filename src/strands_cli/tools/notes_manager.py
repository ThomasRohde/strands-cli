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
        Uses efficient streaming read from end of file to handle large notes files
        without loading entire file into memory.

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
            # For small N, use efficient streaming read from end of file
            # For large N or small files, fall back to full read
            file_size = self.file_path.stat().st_size

            # If file is small (<100KB) or N is large, just read entire file
            if file_size < 100_000 or n > 50:
                with open(self.file_path, encoding="utf-8") as f:
                    content = f.read()
                return self._extract_last_n_entries(content, n)

            # For larger files with small N, read from end efficiently
            return self._stream_last_n_entries(n)

        except Exception as e:
            logger.error(
                "note_read_failed",
                error=str(e),
                file=str(self.file_path),
            )
            raise NotesManagerError(f"Failed to read notes: {e}") from e

    def _extract_last_n_entries(self, content: str, n: int) -> str:
        """Extract last N entries from content string.

        Args:
            content: Full file content
            n: Number of entries to extract

        Returns:
            Formatted string with last N entries
        """
        # Handle n=0 case
        if n <= 0:
            return ""

        # Split on ## headers (note entries)
        entries = [entry.strip() for entry in content.split("##") if entry.strip()]

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

    def _stream_last_n_entries(self, n: int) -> str:
        """Stream last N entries from file without loading entire file.

        Reads file in chunks from the end, accumulating entries until we have
        enough. This is memory-efficient for large files.

        Args:
            n: Number of entries to read

        Returns:
            Formatted string with last N entries
        """
        # Handle n=0 case
        if n <= 0:
            return ""

        chunk_size = 8192  # 8KB chunks
        entries: list[str] = []
        partial_entry = ""

        with open(self.file_path, "rb") as f:
            # Get file size and start from end
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()

            # Read chunks from end until we have N entries
            offset = 0
            while offset < file_size and len(entries) < n:
                # Calculate chunk position (read backwards)
                chunk_start = max(0, file_size - offset - chunk_size)
                chunk_end = file_size - offset

                # Read chunk
                f.seek(chunk_start)
                chunk_bytes = f.read(chunk_end - chunk_start)
                chunk_text = chunk_bytes.decode("utf-8", errors="replace")

                # Prepend to partial entry (we're reading backwards)
                chunk_text = chunk_text + partial_entry

                # Split on ## headers
                parts = chunk_text.split("##")

                # Last part might be incomplete (unless we're at start of file)
                if chunk_start > 0:
                    partial_entry = parts[0] if parts else ""
                    chunk_entries = parts[1:]
                else:
                    # At start of file, all parts are complete
                    partial_entry = ""
                    chunk_entries = parts

                # Filter empty entries and add to list (reverse because we're reading backwards)
                for entry in reversed([e.strip() for e in chunk_entries if e.strip()]):
                    entries.insert(0, entry)
                    if len(entries) >= n:
                        break

                offset += chunk_size

        # Take last N entries (we might have collected more)
        selected_entries = entries[-n:] if len(entries) > n else entries

        # Reconstruct with ## prefixes
        result = "\n\n".join(f"## {entry}" for entry in selected_entries)

        logger.debug(
            "streamed_last_n_notes",
            requested=n,
            returned=len(selected_entries),
            file_size=file_size,
        )

        return result

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
        input_truncated = input_summary[:200] + "..." if len(input_summary) > 200 else input_summary
        outcome_truncated = outcome[:200] + "..." if len(outcome) > 200 else outcome

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

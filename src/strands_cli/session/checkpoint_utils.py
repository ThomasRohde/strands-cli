"""Shared utilities for session checkpointing across all patterns."""

from typing import Any

import structlog

from strands_cli.session import SessionState, SessionStatus
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.session.utils import now_iso8601

logger = structlog.get_logger(__name__)


def validate_session_params(
    session_state: SessionState | None,
    session_repo: FileSessionRepository | None,
) -> None:
    """Validate that both or neither session parameters are provided.

    Args:
        session_state: Session state for resume
        session_repo: Session repository for checkpointing

    Raises:
        ValueError: If only one parameter is provided
    """
    if (session_state is None) != (session_repo is None):
        raise ValueError(
            "session_state and session_repo must both be provided or both be None"
        )


async def checkpoint_pattern_state(
    session_state: SessionState,
    session_repo: FileSessionRepository,
    pattern_state_updates: dict[str, Any],
    token_increment: int = 0,
    status: SessionStatus = SessionStatus.RUNNING,
) -> None:
    """Update pattern state and checkpoint to disk.

    Args:
        session_state: Current session state
        session_repo: Repository for persistence
        pattern_state_updates: Updates to merge into pattern_state
        token_increment: Tokens to add to cumulative usage
        status: Session status to set
    """
    # Update pattern state
    session_state.pattern_state.update(pattern_state_updates)

    # Update metadata
    session_state.metadata.updated_at = now_iso8601()
    session_state.metadata.status = status

    # Update token usage
    if token_increment:
        # Simplified: split evenly between input/output
        # Real implementation tracks actual input/output tokens
        session_state.token_usage.total_input_tokens += token_increment // 2
        session_state.token_usage.total_output_tokens += token_increment - (
            token_increment // 2
        )

    # Persist to disk
    await session_repo.save(session_state, "")

    logger.debug(
        "checkpoint_saved",
        session_id=session_state.metadata.session_id,
        status=status.value,
        tokens=token_increment,
    )


async def finalize_session(
    session_state: SessionState,
    session_repo: FileSessionRepository,
) -> None:
    """Mark session as completed and checkpoint.

    Args:
        session_state: Current session state
        session_repo: Repository for persistence
    """
    session_state.metadata.status = SessionStatus.COMPLETED
    session_state.metadata.updated_at = now_iso8601()
    await session_repo.save(session_state, "")

    logger.info("session_completed", session_id=session_state.metadata.session_id)


def get_cumulative_tokens(session_state: SessionState | None) -> int:
    """Get cumulative token usage from session state.

    Args:
        session_state: Session state or None for fresh start

    Returns:
        Total tokens used so far
    """
    if not session_state:
        return 0
    return (
        session_state.token_usage.total_input_tokens
        + session_state.token_usage.total_output_tokens
    )

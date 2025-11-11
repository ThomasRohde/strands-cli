"""HITL utilities for timeout enforcement and default response handling."""

from datetime import UTC, datetime

import structlog

from strands_cli.session import SessionState
from strands_cli.types import HITLState

logger = structlog.get_logger(__name__)


def check_hitl_timeout(session_state: SessionState) -> tuple[bool, str | None]:
    """Check if HITL has timed out and return default response if applicable.

    Args:
        session_state: Current session state with HITL state

    Returns:
        Tuple of (timed_out: bool, default_response: str | None)
        - If timeout not configured or not expired: (False, None)
        - If timed out with default: (True, "default_value")
        - If timed out without default: (True, "timeout_expired")
    """
    hitl_state_dict = session_state.pattern_state.get("hitl_state")
    if not hitl_state_dict:
        return (False, None)

    hitl_state = HITLState(**hitl_state_dict)
    if not hitl_state.active:
        return (False, None)

    # Check if timeout configured
    if not hitl_state.timeout_at:
        return (False, None)

    # Compare current time vs timeout
    try:
        timeout_dt = datetime.fromisoformat(hitl_state.timeout_at)
    except ValueError:
        logger.warning(
            "hitl_timeout_parse_error",
            session_id=session_state.metadata.session_id,
            timeout_at=hitl_state.timeout_at,
        )
        return (False, None)

    now = datetime.now(UTC)

    if now > timeout_dt:
        # Timeout expired
        default = hitl_state.default_response or "timeout_expired"

        logger.warning(
            "hitl_timeout_expired",
            session_id=session_state.metadata.session_id,
            timeout_at=hitl_state.timeout_at,
            current_time=now.isoformat(),
            default_response=default,
        )

        return (True, default)

    return (False, None)


def format_timeout_warning(timeout_at: str | None, default_response: str | None) -> str:
    """Format console warning message for timeout.

    Args:
        timeout_at: ISO 8601 timestamp when timeout occurred (or None if unknown)
        default_response: Default response being used

    Returns:
        Formatted warning message for console output
    """
    timeout_str = timeout_at if timeout_at else "unknown"
    fallback = default_response or "timeout_expired"
    return (
        f"⏱️ HITL timeout expired at {timeout_str}\n"
        f"Using default response: {fallback}"
    )

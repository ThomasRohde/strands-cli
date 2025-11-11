"""Session management for durable workflow execution.

Provides session persistence and resume capabilities for Strands CLI workflows,
enabling crash recovery, long-running workflows, and debugging across CLI sessions.

Key Components:
    SessionState: Complete session state for persistence
    SessionMetadata: Core metadata (ID, status, timestamps)
    TokenUsage: Token consumption tracking
    SessionStatus: Enum for session lifecycle states
    FileSessionRepository: File-based session storage
    SessionError: Base exception for session operations

Phase 1 (MVP):
    - File-based session persistence
    - Session save/load primitives
    - Session metadata models
    - Basic error handling

Phase 2:
    - Chain pattern resume
    - Agent session restoration via Strands SDK
    - Checkpoint/resume logic

Phase 3:
    - Multi-pattern resume (workflow, parallel, graph, etc.)
    - Complex dependency restoration

Phase 4:
    - S3-based storage for production
    - Session expiration and cleanup
    - Auto-resume on failure
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    """Session execution status.

    Tracks the lifecycle state of a workflow session from creation through
    completion or failure. Used for filtering and resume logic.
    """

    RUNNING = "running"
    """Session is actively executing."""

    PAUSED = "paused"
    """Session paused, awaiting manual resume or approval."""

    COMPLETED = "completed"
    """Session finished successfully."""

    FAILED = "failed"
    """Session terminated due to error."""


class SessionMetadata(BaseModel):
    """Core session metadata.

    Contains identifying information and lifecycle tracking for a session.
    Persisted in session.json alongside execution state.
    """

    session_id: str = Field(..., description="Unique session identifier (UUID4)")
    workflow_name: str = Field(..., description="Workflow name from spec")
    spec_hash: str = Field(
        ...,
        description="SHA256 hash of original spec for change detection",
    )
    pattern_type: str = Field(
        ...,
        description="PatternType enum value (chain, workflow, parallel, etc.)",
    )
    status: SessionStatus = Field(..., description="Current session status")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    error: str | None = Field(
        default=None,
        description="Error message if status=FAILED",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary session metadata collected during execution",
    )


class TokenUsage(BaseModel):
    """Token usage tracking across workflow execution.

    Accumulates token consumption for budget enforcement and cost tracking.
    Updated after each step/task/branch completion.
    """

    total_input_tokens: int = Field(default=0, description="Total input tokens consumed")
    total_output_tokens: int = Field(
        default=0,
        description="Total output tokens consumed",
    )
    by_agent: dict[str, int] = Field(
        default_factory=dict,
        description="Token usage per agent ID",
    )


class SessionState(BaseModel):
    """Complete session state for persistence.

    Captures all information needed to resume workflow execution from a
    checkpoint: metadata, variables, runtime config, pattern-specific state,
    token usage, and artifacts already written.

    Agent conversation history is stored separately via Strands SDK
    FileSessionManager in the agents/ subdirectory.
    """

    metadata: SessionMetadata = Field(..., description="Session metadata")
    variables: dict[str, str] = Field(
        ...,
        description="User-provided variables from --var flags",
    )
    runtime_config: dict[str, Any] = Field(
        ...,
        description="Runtime configuration (provider, model_id, region, etc.)",
    )
    pattern_state: dict[str, Any] = Field(
        ...,
        description="Pattern-specific execution state (step_history, task_outputs, etc.)",
    )
    token_usage: TokenUsage = Field(..., description="Cumulative token usage")
    artifacts_written: list[str] = Field(
        default_factory=list,
        description="Paths to artifacts already written (for idempotent resume)",
    )


# Exception classes for session operations
class SessionError(Exception):
    """Base exception for session-related errors.

    All session-specific exceptions inherit from this class for consistent
    error handling and exit code mapping to EX_SESSION.
    """

    pass


class SessionNotFoundError(SessionError):
    """Raised when session ID doesn't exist in storage.

    Occurs during resume attempt with invalid or deleted session ID.
    """

    pass


class SessionCorruptedError(SessionError):
    """Raised when session data is invalid or corrupted.

    Occurs when session.json or pattern_state.json cannot be parsed or
    validated. May indicate filesystem corruption or partial writes.
    """

    pass


class SessionAlreadyCompletedError(SessionError):
    """Raised when attempting to resume an already-completed session.

    Prevents unnecessary re-execution of finished workflows. Users should
    delete completed sessions or start fresh workflows instead.
    """

    pass


# Export public API
__all__ = [
    "SessionAlreadyCompletedError",
    "SessionCorruptedError",
    "SessionError",
    "SessionMetadata",
    "SessionNotFoundError",
    "SessionState",
    "SessionStatus",
    "TokenUsage",
]

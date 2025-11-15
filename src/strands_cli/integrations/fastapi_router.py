"""FastAPI router for workflow execution.

This module provides a FastAPI router factory for exposing workflow execution
and session management as REST APIs.

Example:
    >>> from fastapi import FastAPI
    >>> from strands_cli.api import Workflow
    >>> from strands_cli.integrations.fastapi_router import create_workflow_router
    >>>
    >>> app = FastAPI()
    >>> workflow = Workflow.from_file("workflow.yaml")
    >>> router = create_workflow_router(workflow)
    >>> app.include_router(router)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    from fastapi import APIRouter, HTTPException, Query  # type: ignore[import-not-found]
except ImportError as e:
    raise ImportError(
        "FastAPI is required for web integrations. Install with: pip install \"strands-cli[web]\""
    ) from e

from strands_cli.api import SessionManager, Workflow
from strands_cli.session import SessionStatus


class ExecuteRequest(BaseModel):
    """Request model for workflow execution."""

    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Variables to pass to the workflow",
    )


class ExecuteResponse(BaseModel):
    """Response model for workflow execution."""

    session_id: str = Field(description="Unique session identifier")
    status: str = Field(description="Session status")
    last_response: str | None = Field(None, description="Last response from the workflow")
    error: str | None = Field(None, description="Error message if failed")
    duration_seconds: float | None = Field(None, description="Execution duration in seconds")


class SessionInfo(BaseModel):
    """Response model for session information."""

    session_id: str = Field(description="Unique session identifier")
    workflow_name: str = Field(description="Workflow name")
    status: str = Field(description="Session status")
    created_at: str = Field(description="Session creation timestamp")
    updated_at: str = Field(description="Last update timestamp")
    variables: dict[str, Any] = Field(default_factory=dict, description="Session variables")
    last_response: str | None = Field(None, description="Last response from the workflow")


class ResumeRequest(BaseModel):
    """Request model for resuming a paused session."""

    hitl_response: str | None = Field(
        None,
        description="Human-in-the-loop response (required for HITL paused sessions)",
    )


def create_workflow_router(
    workflow: Workflow,
    prefix: str = "/workflow",
    storage_dir: Path | None = None,
) -> APIRouter:
    """Create FastAPI router for workflow execution.

    Args:
        workflow: Workflow instance to expose via API
        prefix: URL prefix for all routes (default: "/workflow")
        storage_dir: Directory for session storage (default: platform-specific)

    Returns:
        Configured FastAPI router

    Example:
        >>> from fastapi import FastAPI
        >>> from strands_cli.api import Workflow
        >>> from strands_cli.integrations.fastapi_router import create_workflow_router
        >>>
        >>> app = FastAPI(title="Strands Workflow API")
        >>> workflow = Workflow.from_file("workflow.yaml")
        >>> router = create_workflow_router(workflow, prefix="/workflows")
        >>> app.include_router(router)
    """
    router = APIRouter(prefix=prefix, tags=["workflow"])
    session_manager = SessionManager(storage_dir=storage_dir)

    @router.post("/execute", response_model=ExecuteResponse)  # type: ignore[misc]
    async def execute_workflow(request: ExecuteRequest) -> ExecuteResponse:
        """Execute workflow asynchronously.

        Args:
            request: Execution request with variables

        Returns:
            Execution response with session ID and status

        Raises:
            HTTPException: If execution fails
        """
        try:
            # Execute workflow asynchronously
            async with workflow.async_executor() as executor:
                result = await executor.run(request.variables)

            # Validate session_id is present
            if not result.session_id:
                raise ValueError(
                    "Executor failed to populate session_id. This indicates a bug in the executor."
                )

            # Determine status
            status = "completed" if result.success else "failed"

            return ExecuteResponse(
                session_id=result.session_id,
                status=status,
                last_response=result.last_response,
                error=result.error,
                duration_seconds=result.duration_seconds,
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Workflow execution failed: {e}",
            ) from e

    @router.get("/sessions", response_model=list[SessionInfo])  # type: ignore[misc]
    async def list_sessions(
        offset: int = Query(0, ge=0, description="Pagination offset"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum results (1-1000)"),
        status: str | None = Query(
            None, description="Filter by status (paused, running, completed, failed)"
        ),
        workflow_name: str | None = Query(None, description="Filter by workflow name"),
    ) -> list[SessionInfo]:
        """List workflow sessions with pagination and filtering.

        Args:
            offset: Pagination offset (default: 0)
            limit: Maximum results (default: 100, max: 1000)
            status: Filter by session status
            workflow_name: Filter by workflow name

        Returns:
            List of session information
        """
        # Convert status string to enum if provided
        status_filter: SessionStatus | None = None
        if status:
            try:
                status_filter = SessionStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. "
                    f"Must be one of: paused, running, completed, failed",
                ) from None

        # Get sessions from manager
        sessions = await session_manager.list_sessions(
            offset=offset,
            limit=limit,
            status=status_filter,
            workflow_name=workflow_name,
        )

        # Convert to response models
        return [
            SessionInfo(
                session_id=session.metadata.session_id,
                workflow_name=session.metadata.workflow_name,
                status=session.metadata.status.value,
                created_at=session.metadata.created_at,
                updated_at=session.metadata.updated_at,
                variables=session.variables,
                last_response=None,  # TODO: Design how to expose last_response
            )
            for session in sessions
        ]

    @router.get("/sessions/{session_id}", response_model=SessionInfo)  # type: ignore[misc]
    async def get_session(session_id: str) -> SessionInfo:
        """Get session details.

        Args:
            session_id: Session identifier

        Returns:
            Session information

        Raises:
            HTTPException: If session not found
        """
        try:
            session = await session_manager.get(session_id)

            if session is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session not found: {session_id}",
                )

            return SessionInfo(
                session_id=session.metadata.session_id,
                workflow_name=session.metadata.workflow_name,
                status=session.metadata.status.value,
                created_at=session.metadata.created_at,
                updated_at=session.metadata.updated_at,
                variables=session.variables,
                last_response=None,  # TODO: Design how to expose last_response
            )

        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Session not found: {session_id}",
            ) from None

    @router.post("/sessions/{session_id}/resume", response_model=ExecuteResponse)  # type: ignore[misc]
    async def resume_session(session_id: str, request: ResumeRequest) -> ExecuteResponse:
        """Resume paused session.

        Args:
            session_id: Session identifier
            request: Resume request with optional HITL response

        Returns:
            Execution response

        Raises:
            HTTPException: If session not found or resume fails
        """
        try:
            result = await session_manager.resume(
                session_id=session_id,
                hitl_response=request.hitl_response,
            )

            # Determine status
            status = "completed" if result.success else "failed"

            return ExecuteResponse(
                session_id=session_id,
                status=status,
                last_response=result.last_response,
                error=result.error,
                duration_seconds=result.duration_seconds,
            )

        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Session not found: {session_id}",
            ) from None
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resume session: {e}",
            ) from e

    @router.delete("/sessions/{session_id}", status_code=204)  # type: ignore[misc]
    async def delete_session(session_id: str) -> None:
        """Delete session.

        Args:
            session_id: Session identifier

        Raises:
            HTTPException: If session not found
        """
        try:
            await session_manager.delete(session_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Session not found: {session_id}",
            ) from None

    return router

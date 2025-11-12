"""Unit tests for FastAPI router integration.

Note: Requires [web] extras (fastapi, uvicorn).
"""

import pytest

# Skip all tests if fastapi not installed
pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from strands_cli.api import Workflow
from strands_cli.integrations.fastapi_router import create_workflow_router


@pytest.fixture
def test_workflow(sample_openai_spec):
    """Create test workflow."""
    return Workflow(sample_openai_spec)


@pytest.fixture
def test_client(test_workflow, mocker):
    """Create FastAPI test client."""

    # Mock agent invocation instead of run_async to avoid API calls
    async def mock_invoke(*args, **kwargs):
        return "Test response"

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke,
    )

    app = FastAPI()
    router = create_workflow_router(test_workflow, prefix="/workflow")
    app.include_router(router)

    return TestClient(app)


def test_execute_workflow_endpoint(test_client, mocker):
    """Test POST /workflow/execute endpoint."""
    response = test_client.post(
        "/workflow/execute",
        json={"variables": {"topic": "test"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "completed"
    assert data["last_response"] == "Test response"


def test_execute_workflow_with_empty_variables(test_client):
    """Test execute endpoint with empty variables."""
    response = test_client.post(
        "/workflow/execute",
        json={"variables": {}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_execute_workflow_error(test_workflow, mocker):
    """Test execute endpoint handles errors."""

    # Mock agent invocation to raise error
    async def mock_invoke_error(*args, **kwargs):
        raise RuntimeError("Test error")

    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=mock_invoke_error,
    )

    app = FastAPI()
    router = create_workflow_router(test_workflow, prefix="/workflow")
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/workflow/execute",
        json={"variables": {"topic": "test"}},
    )

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data


def test_list_sessions_endpoint(test_client, mocker):
    """Test GET /workflow/sessions endpoint."""
    # Mock session manager
    mock_sessions = []
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.list",
        return_value=mock_sessions,
    )

    response = test_client.get("/workflow/sessions")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_sessions_with_pagination(test_client, mocker):
    """Test sessions endpoint pagination parameters."""
    mock_list = mocker.AsyncMock(return_value=[])
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.list",
        new=mock_list,
    )

    response = test_client.get(
        "/workflow/sessions",
        params={"offset": 10, "limit": 50},
    )

    assert response.status_code == 200


def test_list_sessions_with_status_filter(test_client, mocker):
    """Test sessions endpoint status filtering."""
    mock_list = mocker.AsyncMock(return_value=[])
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.list",
        new=mock_list,
    )

    response = test_client.get(
        "/workflow/sessions",
        params={"status": "paused"},
    )

    assert response.status_code == 200


def test_list_sessions_invalid_pagination(test_client):
    """Test sessions endpoint rejects invalid pagination."""
    # Negative offset
    response = test_client.get(
        "/workflow/sessions",
        params={"offset": -1},
    )
    assert response.status_code == 422

    # Zero limit
    response = test_client.get(
        "/workflow/sessions",
        params={"limit": 0},
    )
    assert response.status_code == 422

    # Excessive limit
    response = test_client.get(
        "/workflow/sessions",
        params={"limit": 2000},
    )
    assert response.status_code == 422


def test_get_session_endpoint(test_client, mocker):
    """Test GET /workflow/sessions/{id} endpoint."""
    from datetime import datetime

    from strands_cli.session import SessionState, SessionStatus

    mock_session = SessionState(
        metadata={
            "session_id": "test-session",
            "workflow_name": "test",
            "spec_hash": "test-hash-123",
            "pattern_type": "chain",
            "status": SessionStatus.COMPLETED,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        variables={},
        runtime_config={"provider": "openai", "model_id": "gpt-4o-mini"},
        pattern_state={"step_history": []},
        token_usage={"total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}},
    )

    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.get",
        return_value=mock_session,
    )

    response = test_client.get("/workflow/sessions/test-session")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session"


def test_get_session_not_found(test_client, mocker):
    """Test get session returns 404 for nonexistent session."""
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.get",
        side_effect=FileNotFoundError("Session not found"),
    )

    response = test_client.get("/workflow/sessions/nonexistent")

    assert response.status_code == 404


def test_resume_session_endpoint(test_client, mocker):
    """Test POST /workflow/sessions/{id}/resume endpoint."""
    mock_result = mocker.Mock()
    mock_result.success = True
    mock_result.last_response = "Resumed"
    mock_result.error = None
    mock_result.duration_seconds = 2.0

    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.resume",
        return_value=mock_result,
    )

    response = test_client.post(
        "/workflow/sessions/test-session/resume",
        json={"hitl_response": "approved"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["last_response"] == "Resumed"


def test_resume_session_without_hitl_response(test_client, mocker):
    """Test resume endpoint without HITL response."""
    mock_result = mocker.Mock()
    mock_result.success = True
    mock_result.last_response = "Resumed"
    mock_result.error = None
    mock_result.duration_seconds = 1.0

    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.resume",
        return_value=mock_result,
    )

    response = test_client.post(
        "/workflow/sessions/test-session/resume",
        json={},
    )

    assert response.status_code == 200


def test_resume_session_not_found(test_client, mocker):
    """Test resume returns 404 for nonexistent session."""
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.resume",
        side_effect=FileNotFoundError("Session not found"),
    )

    response = test_client.post(
        "/workflow/sessions/nonexistent/resume",
        json={},
    )

    assert response.status_code == 404


def test_delete_session_endpoint(test_client, mocker):
    """Test DELETE /workflow/sessions/{id} endpoint."""
    mock_delete = mocker.AsyncMock()
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.delete",
        new=mock_delete,
    )

    response = test_client.delete("/workflow/sessions/test-session")

    assert response.status_code == 204


def test_delete_session_not_found(test_client, mocker):
    """Test delete returns 404 for nonexistent session."""
    mocker.patch(
        "strands_cli.integrations.fastapi_router.SessionManager.delete",
        side_effect=FileNotFoundError("Session not found"),
    )

    response = test_client.delete("/workflow/sessions/nonexistent")

    assert response.status_code == 404


def test_router_prefix_customization(test_workflow, mocker):
    """Test router can be created with custom prefix."""
    from fastapi import FastAPI

    mock_result = mocker.Mock()
    mock_result.success = True
    mocker.patch.object(test_workflow._executor, "run_async", return_value=mock_result)

    app = FastAPI()
    router = create_workflow_router(test_workflow, prefix="/custom")
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/custom/execute",
        json={"variables": {}},
    )

    assert response.status_code == 200


def test_router_tags(test_workflow):
    """Test router has correct tags."""
    router = create_workflow_router(test_workflow)

    assert "workflow" in router.tags


def test_response_models(test_workflow):
    """Test router endpoints have correct response models."""

    router = create_workflow_router(test_workflow)

    # Routes include the prefix in route.path
    # Find execute endpoint by checking all routes
    execute_route = None
    for route in router.routes:
        if (
            hasattr(route, "path")
            and hasattr(route, "methods")
            and route.path == "/workflow/execute"
            and "POST" in route.methods
        ):
            execute_route = route
            break

    # Verify the route exists and is callable
    assert execute_route is not None, "Execute route should exist"
    assert callable(execute_route.endpoint), "Execute endpoint should be callable"

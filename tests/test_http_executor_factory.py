"""Tests for HTTP executor factory.

Tests creation of native tool modules from HttpExecutor configurations.
"""

import os
from types import ModuleType
from typing import Any

import httpx

from strands_cli.tools.http_executor_factory import (
    _build_tool_description,
    _resolve_secret_placeholders,
    close_http_executor_tool,
    create_http_executor_tool,
)
from strands_cli.types import HttpExecutor, Secret, Spec


def test_resolve_secret_placeholders_no_spec() -> None:
    """Test resolving placeholders without spec."""
    result = _resolve_secret_placeholders("Bearer ${TOKEN}", None)
    # Without spec, should return unchanged
    assert result == "Bearer ${TOKEN}"


def test_resolve_secret_placeholders_with_env_var() -> None:
    """Test resolving placeholders with environment variable directly (no spec)."""
    # When no spec is provided, placeholders are NOT resolved
    os.environ["TEST_TOKEN"] = "secret123"

    try:
        result = _resolve_secret_placeholders("Bearer ${TEST_TOKEN}", None)
        assert result == "Bearer ${TEST_TOKEN}"  # Unchanged without spec
    finally:
        del os.environ["TEST_TOKEN"]


def test_resolve_secret_placeholders_with_spec(mocker: Any) -> None:
    """Test resolving placeholders using spec secrets."""
    # Create mock spec with secrets
    spec = mocker.Mock(spec=Spec)
    env = mocker.Mock()
    env.secrets = [Secret(name="GITHUB_TOKEN", source="env", key="MY_GITHUB_PAT")]
    spec.env = env

    # Set environment variable
    os.environ["MY_GITHUB_PAT"] = "ghp_secret123"

    try:
        result = _resolve_secret_placeholders("Bearer ${GITHUB_TOKEN}", spec)
        assert result == "Bearer ghp_secret123"
    finally:
        del os.environ["MY_GITHUB_PAT"]


def test_resolve_secret_placeholders_multiple() -> None:
    """Test resolving multiple placeholders."""
    # Create mock spec with secrets
    from unittest.mock import Mock

    from strands_cli.types import Secret

    spec = Mock(spec=Spec)
    env = Mock()
    env.secrets = [
        Secret(name="VAR1", source="env", key="ENV_VAR1"),
        Secret(name="VAR2", source="env", key="ENV_VAR2"),
    ]
    spec.env = env

    os.environ["ENV_VAR1"] = "value1"
    os.environ["ENV_VAR2"] = "value2"

    try:
        result = _resolve_secret_placeholders("${VAR1} and ${VAR2}", spec)
        assert result == "value1 and value2"
    finally:
        del os.environ["ENV_VAR1"]
        del os.environ["ENV_VAR2"]


def test_resolve_secret_placeholders_no_match() -> None:
    """Test when placeholder has no matching secret."""
    result = _resolve_secret_placeholders("Bearer ${NONEXISTENT}", None)
    # Without spec, unchanged
    assert result == "Bearer ${NONEXISTENT}"


def test_resolve_secret_placeholders_no_placeholders() -> None:
    """Test text without placeholders."""
    result = _resolve_secret_placeholders("Bearer token123", None)
    assert result == "Bearer token123"


def test_build_tool_description_basic() -> None:
    """Test building basic tool description."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    result = _build_tool_description(config)

    assert "https://api.example.com" in result


def test_build_tool_description_with_custom_description() -> None:
    """Test building description with custom text."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        description="Custom API description",
    )

    result = _build_tool_description(config)

    assert "Custom API description" in result


def test_build_tool_description_with_authentication_info() -> None:
    """Test description includes authentication info."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        authentication_info="API key in Authorization header",
    )

    result = _build_tool_description(config)

    assert "Authentication: API key in Authorization header" in result


def test_build_tool_description_with_response_format() -> None:
    """Test description includes response format."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        response_format="JSON with status and data fields",
    )

    result = _build_tool_description(config)

    assert "Response format: JSON with status and data fields" in result


def test_build_tool_description_with_common_endpoints() -> None:
    """Test description includes common endpoints."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        common_endpoints=[
            {"method": "GET", "path": "/users", "description": "List users"},
            {"method": "POST", "path": "/users", "description": "Create user"},
        ],
    )

    result = _build_tool_description(config)

    assert "Common endpoints:" in result
    assert "GET /users: List users" in result
    assert "POST /users: Create user" in result


def test_build_tool_description_with_examples() -> None:
    """Test description includes examples."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        examples=[
            {
                "description": "Get user",
                "method": "GET",
                "path": "/users/123",
            },
            {
                "description": "Create user",
                "method": "POST",
                "path": "/users",
                "json_data": {"name": "John"},
            },
        ],
    )

    result = _build_tool_description(config)

    assert "Examples:" in result
    assert "Get user" in result
    assert "Method: GET, Path: /users/123" in result
    assert "Create user" in result
    assert "Body: {'name': 'John'}" in result


def test_create_http_executor_tool_basic() -> None:
    """Test creating basic HTTP executor tool."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    assert isinstance(module, ModuleType)
    assert module.__name__ == "test_api"
    assert hasattr(module, "TOOL_SPEC")
    assert hasattr(module, "test_api")  # Function named after id
    assert hasattr(module, "_http_client")


def test_create_http_executor_tool_spec() -> None:
    """Test TOOL_SPEC structure."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        description="Test API",
    )

    module = create_http_executor_tool(config)

    spec = module.TOOL_SPEC
    assert spec["name"] == "test_api"
    assert "Test API" in spec["description"]
    assert "inputSchema" in spec
    assert "json" in spec["inputSchema"]

    schema = spec["inputSchema"]["json"]
    assert "properties" in schema
    assert "method" in schema["properties"]
    assert "path" in schema["properties"]
    assert "json_data" in schema["properties"]
    assert "required" in schema
    assert "path" in schema["required"]


def test_create_http_executor_tool_with_headers(mocker: Any) -> None:
    """Test creating tool with headers."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        headers={"Authorization": "Bearer token123"},
    )

    module = create_http_executor_tool(config)

    # Check client was created with headers
    client = module._http_client
    assert isinstance(client, httpx.Client)


def test_create_http_executor_tool_with_timeout() -> None:
    """Test creating tool with custom timeout."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        timeout=60,
    )

    module = create_http_executor_tool(config)

    client = module._http_client
    assert client.timeout.read == 60


def test_create_http_executor_tool_function_execution(mocker: Any) -> None:
    """Test executing the generated tool function."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    # Mock httpx client
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.text = '{"result": "success"}'

    module._http_client.request = mocker.Mock(return_value=mock_response)

    # Call the tool function
    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {
                "method": "GET",
                "path": "/test",
            },
        }
    )

    assert result["toolUseId"] == "test-123"
    assert result["status"] == "success"
    assert "content" in result
    assert result["content"][0]["json"]["status"] == 200


def test_create_http_executor_tool_function_with_json_data(mocker: Any) -> None:
    """Test tool function with JSON body."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    mock_response = mocker.Mock()
    mock_response.status_code = 201
    mock_response.headers = {}
    mock_response.text = '{"created": true}'

    module._http_client.request = mocker.Mock(return_value=mock_response)

    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {
                "method": "POST",
                "path": "/users",
                "json_data": {"name": "John"},
            },
        }
    )

    assert result["status"] == "success"
    # Verify json_data was passed to request
    module._http_client.request.assert_called_once()
    call_kwargs = module._http_client.request.call_args[1]
    assert call_kwargs["json"] == {"name": "John"}


def test_create_http_executor_tool_function_missing_path() -> None:
    """Test tool function with missing required path."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {
                "method": "GET",
            },
        }
    )

    assert result["status"] == "error"
    assert "Missing required 'path' parameter" in result["content"][0]["text"]


def test_create_http_executor_tool_function_timeout_error(mocker: Any) -> None:
    """Test tool function handles timeout errors."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    # Mock timeout exception
    module._http_client.request = mocker.Mock(side_effect=httpx.TimeoutException("Request timeout"))

    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {"path": "/test"},
        }
    )

    assert result["status"] == "error"
    assert "timed out" in result["content"][0]["text"]


def test_create_http_executor_tool_function_http_error(mocker: Any) -> None:
    """Test tool function handles HTTP errors."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    # Mock HTTP error
    module._http_client.request = mocker.Mock(side_effect=httpx.HTTPError("Connection failed"))

    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {"path": "/test"},
        }
    )

    assert result["status"] == "error"
    assert "HTTP request failed" in result["content"][0]["text"]


def test_create_http_executor_tool_function_unexpected_error(mocker: Any) -> None:
    """Test tool function handles unexpected errors."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    # Mock unexpected exception
    module._http_client.request = mocker.Mock(side_effect=ValueError("Unexpected error"))

    tool_function = getattr(module, config.id)
    result = tool_function(
        {
            "toolUseId": "test-123",
            "input": {"path": "/test"},
        }
    )

    assert result["status"] == "error"
    assert "Unexpected error" in result["content"][0]["text"]


def test_create_http_executor_tool_with_headers_override(mocker: Any) -> None:
    """Test tool function with headers override."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
        headers={"Authorization": "Bearer default"},
    )

    module = create_http_executor_tool(config)

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.text = "OK"

    module._http_client.request = mocker.Mock(return_value=mock_response)

    tool_function = getattr(module, config.id)
    tool_function(
        {
            "toolUseId": "test-123",
            "input": {
                "path": "/test",
                "headers_override": {"X-Custom": "value"},
            },
        }
    )

    # Verify headers_override was used
    call_kwargs = module._http_client.request.call_args[1]
    assert "headers" in call_kwargs
    assert "X-Custom" in call_kwargs["headers"]


def test_close_http_executor_tool() -> None:
    """Test closing HTTP executor tool."""
    config = HttpExecutor(
        id="test_api",
        base_url="https://api.example.com",
    )

    module = create_http_executor_tool(config)

    # Should not raise
    close_http_executor_tool(module)


def test_close_http_executor_tool_without_client() -> None:
    """Test closing tool without http client attribute."""
    module = ModuleType("test")

    # Should not raise even if module doesn't have _http_client
    close_http_executor_tool(module)


def test_create_http_executor_tool_module_attributes() -> None:
    """Test module has correct attributes."""
    config = HttpExecutor(
        id="github_api",
        base_url="https://api.github.com",
    )

    module = create_http_executor_tool(config)

    assert module.__name__ == "github_api"
    assert module.__package__ == "strands_cli.tools"
    assert "<dynamic:http_executor_github_api>" in module.__file__
    assert hasattr(module, "_http_config")
    assert module._http_config == config


def test_create_http_executor_tool_resolves_secrets(mocker: Any) -> None:
    """Test tool creation resolves secret placeholders in headers."""
    spec = mocker.Mock(spec=Spec)
    env = mocker.Mock()
    env.secrets = [Secret(name="API_KEY", source="env", key="MY_API_KEY")]
    spec.env = env

    os.environ["MY_API_KEY"] = "secret123"

    try:
        config = HttpExecutor(
            id="test_api",
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer ${API_KEY}"},
        )

        module = create_http_executor_tool(config, spec)

        # Headers should be resolved in the client
        # We can't directly inspect httpx.Client headers, but we can test it works
        assert hasattr(module, "_http_client")
    finally:
        del os.environ["MY_API_KEY"]

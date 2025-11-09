"""Tests for approval hooks (Phase 12.1).

Tests ApprovalHook registration, interrupt triggering, fallback behaviors,
and integration with the invoke_agent_with_retry interrupt loop.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.utils import ApprovalTimeoutError, InterruptError
from strands_cli.runtime.hooks import ApprovalHook, ApprovalHookError


class MockBeforeToolCallEvent:
    """Mock BeforeToolCallEvent for testing."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any] | None = None):
        """Initialize mock event.

        Args:
            tool_name: Name of the tool being called
            tool_input: Optional tool input parameters
        """
        self.tool_use = {
            "name": tool_name,
            "input": tool_input or {},
        }
        self.cancel_tool = None
        self.interrupted = False
        self.interrupt_data: dict[str, Any] | None = None

    def interrupt(self, reason: str, data: Any) -> None:
        """Mock interrupt method.

        Args:
            reason: Interrupt reason/namespace
            data: Interrupt data payload
        """
        self.interrupted = True
        self.interrupt_data = {"reason": reason, "data": data}


class MockHookRegistry:
    """Mock HookRegistry for testing."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self.callbacks: dict[Any, list[Any]] = {}

    def add_callback(self, event_type: Any, callback: Any) -> None:
        """Add callback to registry.

        Args:
            event_type: Event type to register for
            callback: Callback function
        """
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)


@pytest.fixture
def mock_strands_hooks() -> Any:
    """Mock Strands SDK hooks for testing.

    Returns:
        Mock module with HookProvider, HookRegistry, BeforeToolCallEvent
    """
    with patch("strands_cli.runtime.hooks.STRANDS_HOOKS_AVAILABLE", True):
        yield


def test_approval_hook_initialization(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook initializes with correct parameters."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors", "file_write"],
        timeout_s=300,
        fallback="deny",
        prompt="Custom approval prompt",
    )

    assert hook.app_name == "test-app"
    assert hook.approval_tools == ["http_executors", "file_write"]
    assert hook.timeout_s == 300
    assert hook.fallback == "deny"
    assert hook.custom_prompt == "Custom approval prompt"


def test_approval_hook_without_strands_sdk() -> None:
    """Test ApprovalHook raises error when Strands SDK not available."""
    with (
        patch("strands_cli.runtime.hooks.STRANDS_HOOKS_AVAILABLE", False),
        pytest.raises(ApprovalHookError, match="Strands SDK hooks not available"),
    ):
        ApprovalHook(
            app_name="test-app",
            approval_tools=["http_executors"],
        )


def test_approval_hook_register_hooks(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook registers callback with hook registry."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
    )

    registry = MockHookRegistry()
    hook.register_hooks(registry)

    # Should have registered for BeforeToolCallEvent
    assert len(registry.callbacks) == 1
    # Get the event type (first key)
    event_type = next(iter(registry.callbacks.keys()))
    assert len(registry.callbacks[event_type]) == 1
    assert registry.callbacks[event_type][0] == hook.approve


def test_approval_hook_interrupts_for_approved_tool(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook interrupts for tools in approval list."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
        timeout_s=300,
        fallback="deny",
        prompt="Approve HTTP request?",
    )

    event = MockBeforeToolCallEvent(
        tool_name="http_executors", tool_input={"url": "https://example.com"}
    )
    hook.approve(event)

    # Should have interrupted
    assert event.interrupted
    assert event.interrupt_data is not None
    assert event.interrupt_data["reason"] == "test-app-approval"
    assert event.interrupt_data["data"]["tool"] == "http_executors"
    assert event.interrupt_data["data"]["prompt"] == "Approve HTTP request?"
    assert event.interrupt_data["data"]["timeout_s"] == 300
    assert event.interrupt_data["data"]["fallback"] == "deny"


def test_approval_hook_skips_unapproved_tool(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook skips tools not in approval list."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
    )

    event = MockBeforeToolCallEvent(tool_name="file_read")
    hook.approve(event)

    # Should NOT have interrupted
    assert not event.interrupted
    assert event.interrupt_data is None


def test_approval_hook_default_prompt(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook uses default prompt when not provided."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
    )

    event = MockBeforeToolCallEvent(tool_name="http_executors")
    hook.approve(event)

    assert event.interrupted
    assert event.interrupt_data is not None
    # Should use default prompt with tool name
    assert "http_executors" in event.interrupt_data["data"]["prompt"]


def test_approval_hook_fallback_deny(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook with deny fallback."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
        fallback="deny",
    )

    event = MockBeforeToolCallEvent(tool_name="http_executors")
    hook.approve(event)

    assert event.interrupt_data is not None
    assert event.interrupt_data["data"]["fallback"] == "deny"


def test_approval_hook_fallback_approve(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook with approve fallback."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
        fallback="approve",
    )

    event = MockBeforeToolCallEvent(tool_name="http_executors")
    hook.approve(event)

    assert event.interrupt_data is not None
    assert event.interrupt_data["data"]["fallback"] == "approve"


def test_approval_hook_fallback_abort(mock_strands_hooks: Any) -> None:
    """Test ApprovalHook with abort fallback."""
    hook = ApprovalHook(
        app_name="test-app",
        approval_tools=["http_executors"],
        fallback="abort",
    )

    event = MockBeforeToolCallEvent(tool_name="http_executors")
    hook.approve(event)

    assert event.interrupt_data is not None
    assert event.interrupt_data["data"]["fallback"] == "abort"


@pytest.mark.asyncio
async def test_invoke_with_retry_non_interactive_raises_interrupt_error() -> None:
    """Test invoke_agent_with_retry raises InterruptError in non-interactive mode."""
    from strands_cli.exec.utils import invoke_agent_with_retry

    # Create mock agent with interrupt response
    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.stop_reason = "interrupt"
    mock_result.interrupts = [
        MagicMock(
            id="interrupt-1",
            reason="test-app-approval",
            value={"tool": "http_executors", "prompt": "Approve?", "fallback": "deny"},
        )
    ]
    mock_agent.invoke_async.return_value = mock_result

    # Should raise InterruptError in non-interactive mode
    with pytest.raises(InterruptError, match="Workflow paused for approval"):
        await invoke_agent_with_retry(
            mock_agent, "test prompt", max_attempts=3, wait_min=1, wait_max=60, interactive=False
        )


@pytest.mark.asyncio
async def test_invoke_with_retry_interactive_prompts_user(mocker: Any) -> None:
    """Test invoke_agent_with_retry prompts user in interactive mode."""
    from strands_cli.exec.utils import invoke_agent_with_retry

    # Mock Rich console and Confirm
    mock_confirm = mocker.patch("rich.prompt.Confirm.ask", return_value=True)

    # Create mock agent with interrupt then success
    mock_agent = AsyncMock()

    # First call: interrupt response
    mock_interrupt_result = MagicMock()
    mock_interrupt_result.stop_reason = "interrupt"
    mock_interrupt_result.interrupts = [
        MagicMock(
            id="interrupt-1",
            reason="test-app-approval",
            value={
                "tool": "http_executors",
                "prompt": "Approve HTTP request?",
                "fallback": "deny",
            },
        )
    ]

    # Second call: success response
    mock_success_result = MagicMock()
    mock_success_result.stop_reason = "complete"
    mock_success_result.interrupts = []

    mock_agent.invoke_async.side_effect = [mock_interrupt_result, mock_success_result]

    # Should prompt user and continue
    result = await invoke_agent_with_retry(
        mock_agent, "test prompt", max_attempts=3, wait_min=1, wait_max=60, interactive=True
    )

    # Should have returned success result
    assert result == mock_success_result

    # Should have called Confirm.ask once
    assert mock_confirm.call_count == 1

    # Should have resumed agent with approval response
    assert mock_agent.invoke_async.call_count == 2

    # Check resume call arguments
    resume_call = mock_agent.invoke_async.call_args_list[1]
    resume_args = resume_call[0][0]  # First positional argument
    assert isinstance(resume_args, list)
    assert len(resume_args) == 1
    assert "interruptResponse" in resume_args[0]
    assert resume_args[0]["interruptResponse"]["interruptId"] == "interrupt-1"
    assert resume_args[0]["interruptResponse"]["response"] == "y"  # Approved


@pytest.mark.asyncio
async def test_invoke_with_retry_abort_fallback_raises_error(mocker: Any) -> None:
    """Test invoke_agent_with_retry raises ApprovalTimeoutError with abort fallback."""
    from strands_cli.exec.utils import invoke_agent_with_retry

    # Mock Rich console and Confirm (user denies approval)
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    # Create mock agent with interrupt
    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.stop_reason = "interrupt"
    mock_result.interrupts = [
        MagicMock(
            id="interrupt-1",
            reason="test-app-approval",
            value={"tool": "http_executors", "prompt": "Approve?", "fallback": "abort"},
        )
    ]
    mock_agent.invoke_async.return_value = mock_result

    # Should raise ApprovalTimeoutError when user denies with abort fallback
    with pytest.raises(ApprovalTimeoutError, match="User denied approval"):
        await invoke_agent_with_retry(
            mock_agent, "test prompt", max_attempts=3, wait_min=1, wait_max=60, interactive=True
        )


@pytest.mark.asyncio
async def test_invoke_with_retry_deny_fallback_continues(mocker: Any) -> None:
    """Test invoke_agent_with_retry continues execution with deny fallback."""
    from strands_cli.exec.utils import invoke_agent_with_retry

    # Mock Rich console and Confirm (user denies approval)
    mock_confirm = mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    # Create mock agent with interrupt then success
    mock_agent = AsyncMock()

    # First call: interrupt response
    mock_interrupt_result = MagicMock()
    mock_interrupt_result.stop_reason = "interrupt"
    mock_interrupt_result.interrupts = [
        MagicMock(
            id="interrupt-1",
            reason="test-app-approval",
            value={"tool": "http_executors", "prompt": "Approve?", "fallback": "deny"},
        )
    ]

    # Second call: success (tool cancelled, agent continues)
    mock_success_result = MagicMock()
    mock_success_result.stop_reason = "complete"

    mock_agent.invoke_async.side_effect = [mock_interrupt_result, mock_success_result]

    # Should continue with deny fallback
    result = await invoke_agent_with_retry(
        mock_agent, "test prompt", max_attempts=3, wait_min=1, wait_max=60, interactive=True
    )

    # Should have returned success result
    assert result == mock_success_result

    # Should have prompted user
    assert mock_confirm.call_count == 1

    # Should have resumed with denial response
    assert mock_agent.invoke_async.call_count == 2
    resume_call = mock_agent.invoke_async.call_args_list[1]
    resume_args = resume_call[0][0]
    assert resume_args[0]["interruptResponse"]["response"] == "n"  # Denied


@pytest.mark.asyncio
async def test_invoke_with_retry_approve_fallback_overrides_denial(mocker: Any) -> None:
    """Test invoke_agent_with_retry auto-approves with approve fallback."""
    from strands_cli.exec.utils import invoke_agent_with_retry

    # Mock Rich console and Confirm (user denies, but fallback approves)
    mock_confirm = mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    # Create mock agent with interrupt then success
    mock_agent = AsyncMock()

    # First call: interrupt response
    mock_interrupt_result = MagicMock()
    mock_interrupt_result.stop_reason = "interrupt"
    mock_interrupt_result.interrupts = [
        MagicMock(
            id="interrupt-1",
            reason="test-app-approval",
            value={"tool": "http_executors", "prompt": "Approve?", "fallback": "approve"},
        )
    ]

    # Second call: success (tool approved via fallback)
    mock_success_result = MagicMock()
    mock_success_result.stop_reason = "complete"

    mock_agent.invoke_async.side_effect = [mock_interrupt_result, mock_success_result]

    # Should override denial with approval
    result = await invoke_agent_with_retry(
        mock_agent, "test prompt", max_attempts=3, wait_min=1, wait_max=60, interactive=True
    )

    # Should have returned success result
    assert result == mock_success_result

    # Should have prompted user
    assert mock_confirm.call_count == 1

    # Should have resumed with approval (fallback override)
    assert mock_agent.invoke_async.call_count == 2
    resume_call = mock_agent.invoke_async.call_args_list[1]
    resume_args = resume_call[0][0]
    assert resume_args[0]["interruptResponse"]["response"] == "y"  # Approved via fallback

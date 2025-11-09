"""Approval hooks for human-in-the-loop workflows.

Phase 12.1: SDK-Native Interrupts

Implements manual approval gates using Strands SDK interrupts with configurable
timeout behavior and fallback actions. Supports inline interactive CLI approval
with integration hooks deferred to Phase 12.4.

Key Components:
- ApprovalHook: HookProvider that interrupts before tool execution
- Timeout enforcement via asyncio.wait_for() (future enhancement)
- Fallback actions: deny (cancel tool), approve (allow), abort (stop workflow)

Design:
The ApprovalHook uses Strands SDK's BeforeToolCallEvent to interrupt tool execution
and request human approval. The interrupt mechanism is handled by the SDK, with
responses collected in the executor's invoke loop.

Example:
    hook = ApprovalHook(
        app_name="strands-cli",
        approval_tools=["http_executors", "file_write"],
        timeout_s=300,
        fallback="deny",
        prompt="Approve external API call?"
    )

    agent = Agent(
        name="researcher",
        model=model,
        tools=tools,
        hooks=[hook]
    )
"""

from typing import Any, Literal

import structlog

try:
    from strands.agent import (  # type: ignore[attr-defined]
        BeforeToolCallEvent,
        HookProvider,
        HookRegistry,
    )

    STRANDS_HOOKS_AVAILABLE = True
except ImportError:
    STRANDS_HOOKS_AVAILABLE = False
    HookProvider = object  # type: ignore[misc, assignment]
    HookRegistry = Any
    BeforeToolCallEvent = Any


logger = structlog.get_logger(__name__)


class ApprovalHookError(Exception):
    """Raised when approval hook encounters an error."""

    pass


class ApprovalHook(HookProvider):
    """Request human approval before tool execution.

    Uses Strands SDK interrupt mechanism to pause agent execution before
    designated tools are invoked. Supports configurable timeout and fallback
    actions when approval is denied or times out.

    The hook interrupts execution for tools in the approval_tools list,
    pausing the agent and waiting for a response. The executor loop handles
    collecting approval responses from the user.

    Fallback Behaviors:
        - deny: Cancel tool execution (set event.cancel_tool)
        - approve: Allow tool execution (no-op on timeout/denial)
        - abort: Raise ExecutionError to stop workflow

    Note: Timeout enforcement requires async context in executor. Current
    implementation relies on SDK's interrupt/resume mechanism. Phase 12.2
    will add explicit timeout handling via asyncio.wait_for() wrappers.

    Args:
        app_name: Application identifier for interrupt namespace
        approval_tools: List of tool IDs requiring approval (e.g., ["http_executors"])
        timeout_s: Approval timeout in seconds (currently advisory only)
        fallback: Action on timeout/denial - "deny", "approve", or "abort"
        prompt: Custom approval prompt shown to user

    Example:
        hook = ApprovalHook(
            app_name="strands-cli",
            approval_tools=["http_executors"],
            timeout_s=300,
            fallback="deny",
            prompt="Approve HTTP request?"
        )

        agent = Agent(tools=[...], hooks=[hook])
    """

    def __init__(
        self,
        app_name: str,
        approval_tools: list[str],
        timeout_s: int | None = None,
        fallback: Literal["deny", "approve", "abort"] = "deny",
        prompt: str | None = None,
    ):
        """Initialize approval hook.

        Args:
            app_name: Application identifier for interrupt namespace
            approval_tools: List of tool IDs requiring approval
            timeout_s: Approval timeout in seconds (advisory only in Phase 12.1)
            fallback: Action on timeout/denial
            prompt: Custom approval prompt
        """
        if not STRANDS_HOOKS_AVAILABLE:
            raise ApprovalHookError(
                "Strands SDK hooks not available. Update strands-agents to version with hook support."
            )

        self.app_name = app_name
        self.approval_tools = approval_tools
        self.timeout_s = timeout_s
        self.fallback = fallback
        self.custom_prompt = prompt

        logger.debug(
            "approval_hook_initialized",
            app_name=app_name,
            approval_tools=approval_tools,
            timeout_s=timeout_s,
            fallback=fallback,
        )

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register the approval callback with Strands SDK.

        Called by Strands SDK during agent construction to register
        hook callbacks. Adds the approve() method as a BeforeToolCallEvent
        callback.

        Args:
            registry: Strands hook registry
            **kwargs: Additional context from SDK (unused)
        """
        registry.add_callback(BeforeToolCallEvent, self.approve)
        logger.debug(
            "approval_hook_registered",
            app_name=self.app_name,
            approval_tools=self.approval_tools,
        )

    def approve(self, event: BeforeToolCallEvent) -> None:
        """Approval callback invoked before tool execution.

        Checks if the tool requires approval based on approval_tools list.
        If approval is required, interrupts execution and waits for user response.

        The interrupt response is handled by the executor's invoke loop, which
        collects user input and resumes the agent with approval/denial responses.

        Fallback logic:
            - If user denies (response != "y"), apply fallback action
            - deny: Cancel tool execution
            - approve: Allow tool execution (no-op)
            - abort: Raise error to stop workflow

        Args:
            event: BeforeToolCallEvent from Strands SDK with tool_use details

        Raises:
            ApprovalHookError: If fallback is "abort" and approval is denied
        """
        tool_name = event.tool_use.get("name", "<unknown>")

        # Check if this tool requires approval
        if tool_name not in self.approval_tools:
            logger.debug(
                "approval_hook_skipped",
                tool=tool_name,
                approval_tools=self.approval_tools,
            )
            return

        # Extract tool input for display in prompt
        tool_input = event.tool_use.get("input", {})

        logger.info(
            "approval_hook_interrupting",
            tool=tool_name,
            tool_input=tool_input,
            timeout_s=self.timeout_s,
            fallback=self.fallback,
        )

        # Interrupt for approval - SDK will pause execution and collect response
        # The interrupt response is handled in the executor's invoke_with_interrupts loop
        approval_data = {
            "tool": tool_name,
            "input": tool_input,
            "prompt": self.custom_prompt or f"Approve {tool_name} execution?",
            "timeout_s": self.timeout_s,
            "fallback": self.fallback,
        }

        # Call SDK interrupt - this will pause execution and return control to executor
        # The executor will collect user input and resume with response
        event.interrupt(f"{self.app_name}-approval", approval_data)

        # Note: The actual approval/denial logic is handled in the executor's
        # invoke_with_interrupts() function, which processes interrupt responses
        # and applies fallback actions. This hook just triggers the interrupt.

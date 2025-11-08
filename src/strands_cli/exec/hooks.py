"""Context management hooks for intelligent workflow execution.

This module provides hooks that integrate with Strands SDK's hook system
to enable proactive context management during long-running workflows.

Hooks:
    ProactiveCompactionHook: Triggers context compaction before token overflow
    NotesAppenderHook: Appends structured notes after each agent invocation
"""

from typing import Any

import structlog
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry

from strands_cli.tools.notes_manager import NotesManager

logger = structlog.get_logger(__name__)


class ProactiveCompactionHook(HookProvider):
    """Proactively trigger context compaction before token overflow.

    Monitors token usage after each agent invocation via accumulated usage metrics
    and triggers compaction when approaching the configured threshold. This prevents
    reactive overflow handling and enables controlled context reduction.

    **Single-Fire Behavior**: Compaction triggers only once per hook instance to avoid
    repeated compaction cycles within the same workflow. For multi-session workflows
    or workflows requiring multiple compactions, create a new hook instance.

    Attributes:
        threshold_tokens: Token count at which to trigger compaction
        compacted: Flag tracking whether compaction has been triggered (single-fire)

    Example:
        >>> hook = ProactiveCompactionHook(threshold_tokens=60000)
        >>> agent = Agent(
        ...     name="research-agent",
        ...     model=model,
        ...     conversation_manager=manager,
        ...     hooks=[hook]
        ... )
    """

    def __init__(self, threshold_tokens: int):
        """Initialize the proactive compaction hook.

        Args:
            threshold_tokens: Trigger compaction when total tokens exceed this value
        """
        self.threshold_tokens = threshold_tokens
        self.compacted = False  # Track if we've already compacted

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register hook callbacks with the agent's hook registry.

        Args:
            registry: Hook registry from the agent
            **kwargs: Additional keyword arguments (not used)
        """
        registry.add_callback(AfterInvocationEvent, self._check_and_compact)

    def _check_and_compact(self, event: AfterInvocationEvent) -> None:
        """Check token usage and trigger compaction if threshold exceeded.

        Called automatically by Strands SDK after each agent invocation.
        Reads accumulated usage metrics and compares against threshold.
        If threshold exceeded, triggers conversation_manager.apply_management().

        Args:
            event: AfterInvocationEvent containing agent and result information

        Note:
            Uses agent.accumulated_usage from Strands SDK (provider-reported)
            rather than estimates for accuracy. Falls back gracefully if metrics
            unavailable.
        """
        agent = event.agent

        # Check if agent has conversation manager (required for compaction)
        if not hasattr(agent, "conversation_manager") or agent.conversation_manager is None:
            logger.debug(
                "compaction_skipped",
                reason="no_conversation_manager",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
            )
            return

        # Extract token usage from Strands SDK metrics
        usage = getattr(agent, "accumulated_usage", None)
        if not usage:
            logger.debug(
                "compaction_skipped",
                reason="no_usage_metrics",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
            )
            return

        total_tokens = usage.get("totalTokens", 0)

        # Log current usage
        logger.debug(
            "token_usage_check",
            agent_name=agent.name if hasattr(agent, "name") else "unknown",
            total_tokens=total_tokens,
            threshold=self.threshold_tokens,
            percentage=round(total_tokens / self.threshold_tokens * 100, 1)
            if self.threshold_tokens > 0
            else 0,
        )

        # Trigger compaction if threshold exceeded
        if total_tokens >= self.threshold_tokens and not self.compacted:
            logger.info(
                "compaction_triggered",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                total_tokens=total_tokens,
                threshold=self.threshold_tokens,
                trigger_reason="proactive_threshold_exceeded",
            )

            # Apply context compaction via conversation manager
            # Note: SDK type stub may show wrong signature, but this is correct per SDK docs
            agent.conversation_manager.apply_management(agent.messages)  # type: ignore[arg-type]

            # Mark as compacted to avoid repeated triggers
            self.compacted = True

            logger.info(
                "compaction_completed",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                messages_after_compaction=len(agent.messages),
            )
class NotesAppenderHook(HookProvider):
    """Append structured notes after each agent invocation.

    Captures execution history (input, tools used, outcome) and persists to a
    Markdown notes file for cross-step continuity and multi-session workflows.

    **Error Handling Policy**: Note write failures are logged but do not raise exceptions.
    This ensures workflow execution continues even if notes persistence fails (e.g., due to
    file permissions). Notes are considered auxiliary/observability features, not critical
    to workflow success.

    Attributes:
        notes_manager: NotesManager instance for file operations
        step_counter_ref: Mutable list container for tracking step count across invocations
        agent_tools: Mapping of agent_id to list of tool names for tool tracking

    Example:
        >>> step_counter = [0]
        >>> notes_manager = NotesManager("artifacts/notes.md")
        >>> agent_tools = {"research-agent": ["http_request"]}
        >>> hook = NotesAppenderHook(notes_manager, step_counter, agent_tools)
        >>> agent = Agent(name="research-agent", model=model, hooks=[hook])
    """

    def __init__(self, notes_manager: NotesManager, step_counter_ref: list[int], agent_tools: dict[str, list[str]] | None = None):
        """Initialize the notes appender hook.

        Args:
            notes_manager: NotesManager instance for writing notes
            step_counter_ref: Mutable list [counter] for tracking step index across invocations
            agent_tools: Optional mapping of agent_id to list of configured tool names
        """
        self.notes_manager = notes_manager
        self.step_counter_ref = step_counter_ref
        self.agent_tools = agent_tools or {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register hook callbacks with the agent's hook registry.

        Args:
            registry: Hook registry from the agent
            **kwargs: Additional keyword arguments (not used)
        """
        registry.add_callback(AfterInvocationEvent, self._append_note)

    def _append_note(self, event: AfterInvocationEvent) -> None:
        """Append a structured note entry after agent invocation.

        Called automatically by Strands SDK after each agent invocation.
        Extracts relevant data from the agent's messages and writes a Markdown note entry.

        Args:
            event: AfterInvocationEvent containing agent and result information
        """
        agent = event.agent

        # Increment step counter
        self.step_counter_ref[0] += 1
        step_index = self.step_counter_ref[0]

        # Extract agent name
        agent_name = getattr(agent, "name", "unknown")

        # Generate timestamp
        timestamp = NotesManager.generate_timestamp()

        # Extract input summary from agent messages (last user message)
        input_summary = self._extract_input_summary(agent)

        # Get configured tools for this agent
        tools_used = self._get_agent_tools(agent)

        # Extract outcome from agent messages (last assistant message)
        outcome = self._extract_outcome_from_messages(agent)

        logger.debug(
            "appending_note",
            agent_name=agent_name,
            step_index=step_index,
            tools_count=len(tools_used) if tools_used else 0,
        )

        # Append note entry
        try:
            self.notes_manager.append_entry(
                timestamp=timestamp,
                agent_name=agent_name,
                step_index=step_index,
                input_summary=input_summary,
                tools_used=tools_used,
                outcome=outcome,
            )
        except Exception as e:
            logger.error(
                "note_append_failed",
                error=str(e),
                agent_name=agent_name,
                step_index=step_index,
            )
            # Don't raise - notes are auxiliary, shouldn't break workflow

    def _extract_input_summary(self, agent: Any) -> str:
        """Extract input summary from agent messages.

        Args:
            agent: Agent instance

        Returns:
            Last user message content, or "No input" if unavailable
        """
        if not hasattr(agent, "messages") or not agent.messages:
            return "No input"

        # Find last user message that's not a tool result
        for message in reversed(agent.messages):
            if isinstance(message, dict):
                role = message.get("role", "")
                # Skip tool results (role="user" with toolResult)
                if role == "tool":
                    continue
                if role == "user":
                    content = message.get("content", "")
                    # Skip if content only contains tool results
                    if isinstance(content, list):
                        has_tool_result = any(
                            isinstance(item, dict) and "toolResult" in item for item in content
                        )
                        if has_tool_result:
                            continue
                        # Extract text from content list
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                text_parts.append(item["text"])
                        text = " ".join(text_parts) if text_parts else str(content)
                    else:
                        text = str(content)

                    # Truncate if very long
                    return text[:500] if len(text) > 500 else text

        return "No input"

    def _get_agent_tools(self, agent: Any) -> list[str] | None:
        """Get list of tools configured for this agent.

        Note: Strands SDK does not preserve tool_calls in message history after execution.
        We use the agent_tools mapping provided at hook initialization.

        Args:
            agent: Agent instance

        Returns:
            List of configured tool names if agent has tools, None otherwise
        """
        agent_name = getattr(agent, "name", "unknown")
        tools = self.agent_tools.get(agent_name)
        if tools:
            logger.debug("tools_from_mapping", agent_name=agent_name, tool_names=tools)
        return tools

    def _extract_outcome_from_messages(self, agent: Any) -> str:
        """Extract outcome summary from agent messages.

        Gets the last assistant message content as the outcome.

        Args:
            agent: Agent instance with messages

        Returns:
            Last assistant message text, or "No output" if unavailable
        """
        if not hasattr(agent, "messages") or not agent.messages:
            return "No output"

        # Find last assistant message
        for message in reversed(agent.messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = message.get("content", "")
                if content:
                    # Handle content as list of dicts (Anthropic format)
                    if isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                text_parts.append(item["text"])
                        output = " ".join(text_parts) if text_parts else str(content)
                    else:
                        output = str(content)

                    # Truncate if very long
                    return output[:500] if len(output) > 500 else output

        return "No output"


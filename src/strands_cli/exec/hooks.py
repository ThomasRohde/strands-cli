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

from strands_cli.runtime.token_counter import TokenCounter
from strands_cli.tools.notes_manager import NotesManager

logger = structlog.get_logger(__name__)


class ProactiveCompactionHook(HookProvider):
    """Proactively trigger context compaction before token overflow.

    Monitors token usage after each agent invocation via accumulated usage metrics
    and triggers compaction when approaching the configured threshold. This prevents
    reactive overflow handling and enables controlled context reduction.

    **Token Counting Strategy**: Uses provider-reported metrics when available, falls
    back to TokenCounter estimation when metrics are missing or stale. This ensures
    reliable compaction triggering across all providers (Bedrock, Ollama, OpenAI).

    **Single-Fire Behavior**: Compaction triggers only once per hook instance to avoid
    repeated compaction cycles within the same workflow. For multi-session workflows
    or workflows requiring multiple compactions, create a new hook instance.

    Attributes:
        threshold_tokens: Token count at which to trigger compaction
        model_id: Model identifier for TokenCounter fallback
        compacted: Flag tracking whether compaction has been triggered (single-fire)
        token_counter: TokenCounter instance for fallback estimation

    Example:
        >>> hook = ProactiveCompactionHook(
        ...     threshold_tokens=60000, model_id="anthropic.claude-3-sonnet-20240229-v1:0"
        ... )
        >>> agent = Agent(
        ...     name="research-agent", model=model, conversation_manager=manager, hooks=[hook]
        ... )
    """

    def __init__(self, threshold_tokens: int, model_id: str | None = None):
        """Initialize the proactive compaction hook.

        Args:
            threshold_tokens: Trigger compaction when total tokens exceed this value
            model_id: Optional model identifier for TokenCounter fallback
        """
        self.threshold_tokens = threshold_tokens
        self.model_id = model_id
        self.compacted = False  # Track if we've already compacted
        self.token_counter: TokenCounter | None = None

        # Initialize token counter if model_id provided
        if model_id:
            self.token_counter = TokenCounter(model_id)
            logger.debug(
                "token_counter_initialized",
                model_id=model_id,
                threshold_tokens=threshold_tokens,
            )

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
        Uses provider-reported metrics when available, falls back to TokenCounter
        estimation when metrics are missing or stale.

        Args:
            event: AfterInvocationEvent containing agent and result information

        Note:
            Prefers agent.accumulated_usage from Strands SDK (provider-reported)
            for accuracy. Falls back to TokenCounter estimation of agent.messages
            if provider metrics unavailable.
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

        # Try to extract token usage from provider metrics (preferred)
        usage = getattr(agent, "accumulated_usage", None)
        total_tokens = None
        token_source = "unknown"

        if usage and usage.get("totalTokens", 0) > 0:
            total_tokens = usage.get("totalTokens", 0)
            token_source = "provider_metrics"
            logger.debug(
                "token_usage_from_provider",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                total_tokens=total_tokens,
            )

        # Fallback to TokenCounter estimation if provider metrics unavailable
        if total_tokens is None or total_tokens == 0:
            if self.token_counter and hasattr(agent, "messages") and agent.messages:
                # Note: agent.messages is list[Message] from Strands SDK, but TokenCounter
                # expects list[dict[str, Any]]. Message objects support dict-like iteration.
                fallback_tokens = self.token_counter.count_messages(agent.messages)  # type: ignore[arg-type]
                
                # Compare with provider metrics if available for accuracy tracking
                if usage and usage.get("totalTokens", 0) > 0:
                    provider_tokens = usage.get("totalTokens", 0)
                    token_delta = fallback_tokens - provider_tokens
                    delta_pct = (token_delta / provider_tokens * 100) if provider_tokens > 0 else 0
                    
                    logger.debug(
                        "token_count_comparison",
                        agent_name=agent.name if hasattr(agent, "name") else "unknown",
                        provider_tokens=provider_tokens,
                        fallback_tokens=fallback_tokens,
                        delta=token_delta,
                        delta_percent=round(delta_pct, 1),
                    )
                
                total_tokens = fallback_tokens
                token_source = "token_counter_fallback"
                logger.debug(
                    "token_usage_from_counter",
                    agent_name=agent.name if hasattr(agent, "name") else "unknown",
                    total_tokens=total_tokens,
                    message_count=len(agent.messages),
                )
            else:
                logger.debug(
                    "compaction_skipped",
                    reason="no_usage_metrics_or_counter",
                    agent_name=agent.name if hasattr(agent, "name") else "unknown",
                    has_token_counter=self.token_counter is not None,
                    has_messages=hasattr(agent, "messages") and bool(agent.messages),
                )
                return

        # Log current usage
        logger.debug(
            "token_usage_check",
            agent_name=agent.name if hasattr(agent, "name") else "unknown",
            total_tokens=total_tokens,
            threshold=self.threshold_tokens,
            token_source=token_source,
            percentage=round(total_tokens / self.threshold_tokens * 100, 1)
            if self.threshold_tokens > 0
            else 0,
        )

        # Trigger compaction if threshold exceeded
        if total_tokens >= self.threshold_tokens and not self.compacted:
            # Get current message count and configured preserve value
            message_count = len(agent.messages) if hasattr(agent, "messages") else 0
            configured_preserve = getattr(
                agent.conversation_manager, "preserve_recent_messages", 12
            )
            
            # Calculate minimum messages needed: preserve_recent + minimum_summarizable (5)
            minimum_required = configured_preserve + 5
            
            # Auto-reduce preserve_recent_messages if insufficient messages
            if message_count < minimum_required:
                # Calculate safe preserve value: leave at least 5 messages for summarization
                # Use hard minimum of 3 to ensure basic context (user→assistant→user)
                adjusted_preserve = max(message_count - 5, 3)
                
                logger.warning(
                    "compaction_auto_reducing_preserve",
                    agent_name=agent.name if hasattr(agent, "name") else "unknown",
                    message_count=message_count,
                    preserve_recent_configured=configured_preserve,
                    preserve_recent_adjusted=adjusted_preserve,
                    minimum_required=minimum_required,
                    reason="insufficient_messages_for_configured_value",
                )
                
                # Temporarily adjust preserve_recent_messages for this compaction
                original_preserve = agent.conversation_manager.preserve_recent_messages
                agent.conversation_manager.preserve_recent_messages = adjusted_preserve
            else:
                original_preserve = None  # No adjustment needed
            
            logger.info(
                "compaction_triggered",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                total_tokens=total_tokens,
                threshold=self.threshold_tokens,
                token_source=token_source,
                trigger_reason="proactive_threshold_exceeded",
                message_count=message_count,
                preserve_recent_messages=agent.conversation_manager.preserve_recent_messages,
            )

            try:
                # Apply context compaction via conversation manager
                # Note: SDK type stub may show wrong signature, but this is correct per SDK docs
                agent.conversation_manager.apply_management(agent.messages)  # type: ignore[arg-type]
                
                logger.info(
                    "compaction_completed",
                    agent_name=agent.name if hasattr(agent, "name") else "unknown",
                    messages_after_compaction=len(agent.messages),
                    token_source=token_source,
                )
            finally:
                # Restore original preserve_recent_messages value if we adjusted it
                if original_preserve is not None:
                    agent.conversation_manager.preserve_recent_messages = original_preserve
                    logger.debug(
                        "compaction_preserve_restored",
                        agent_name=agent.name if hasattr(agent, "name") else "unknown",
                        restored_value=original_preserve,
                    )
            
            # Mark as compacted to avoid repeated triggers
            self.compacted = True


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

    def __init__(
        self,
        notes_manager: NotesManager,
        step_counter_ref: list[int],
        agent_tools: dict[str, list[str]] | None = None,
    ):
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

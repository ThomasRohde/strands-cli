"""Context management hooks for intelligent workflow execution.

This module provides hooks that integrate with Strands SDK's hook system
to enable proactive context management during long-running workflows.

Hooks:
    ProactiveCompactionHook: Triggers context compaction before token overflow
"""

from typing import Any

import structlog
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry

logger = structlog.get_logger(__name__)


class ProactiveCompactionHook(HookProvider):
    """Proactively trigger context compaction before token overflow.

    Monitors token usage after each agent invocation via accumulated usage metrics
    and triggers compaction when approaching the configured threshold. This prevents
    reactive overflow handling and enables controlled context reduction.

    Attributes:
        threshold_tokens: Token count at which to trigger compaction
        compacted: Flag tracking whether compaction has been triggered

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

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register hook callbacks with the agent's hook registry.

        Args:
            registry: Hook registry from the agent
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
            agent.conversation_manager.apply_management(agent.messages)

            # Mark as compacted to avoid repeated triggers
            self.compacted = True

            logger.info(
                "compaction_completed",
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                messages_after_compaction=len(agent.messages),
            )


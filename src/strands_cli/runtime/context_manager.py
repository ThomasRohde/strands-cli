"""Context manager factory for intelligent conversation management.

This module provides factory functions to create Strands SDK conversation managers
from workflow spec configurations. Leverages native SummarizingConversationManager
for context compaction with optional custom summarization agents.

Key Functions:
    create_from_policy: Create conversation manager from ContextPolicy config
    create_summarization_agent: Create optional cheaper agent for summarization
"""

import structlog
from strands import Agent
from strands.agent.conversation_manager import SummarizingConversationManager

from strands_cli.runtime.providers import create_model
from strands_cli.types import Compaction, ContextPolicy, Runtime, Spec

logger = structlog.get_logger(__name__)


def create_from_policy(
    context_policy: ContextPolicy | None,
    spec: Spec,
) -> SummarizingConversationManager | None:
    """Create conversation manager from context policy configuration.

    Builds a SummarizingConversationManager with settings from spec.context_policy.compaction.
    If a custom summarization model is specified, creates a pooled model client for it.

    Args:
        context_policy: Context policy configuration (may be None)
        spec: Full workflow spec for runtime and agent access

    Returns:
        Configured SummarizingConversationManager if compaction is enabled, else None

    Example:
        >>> manager = create_from_policy(spec.context_policy, spec)
        >>> agent = Agent(
        ...     name="research-agent",
        ...     model=model,
        ...     conversation_manager=manager
        ... )
    """
    if not context_policy or not context_policy.compaction:
        logger.debug("context_manager_disabled", reason="no_compaction_config")
        return None

    compaction: Compaction = context_policy.compaction

    if not compaction.enabled:
        logger.debug("context_manager_disabled", reason="compaction_disabled")
        return None

    # Create optional custom summarization agent
    summarization_agent = None
    if compaction.summarization_model:
        summarization_agent = _create_summarization_agent(
            compaction.summarization_model, spec
        )
        logger.info(
            "summarization_agent_created",
            model=compaction.summarization_model,
        )

    # Configure SummarizingConversationManager
    manager = SummarizingConversationManager(
        summary_ratio=compaction.summary_ratio,
        preserve_recent_messages=compaction.preserve_recent_messages,
        summarization_agent=summarization_agent,
    )

    logger.info(
        "conversation_manager_created",
        summary_ratio=compaction.summary_ratio,
        preserve_recent_messages=compaction.preserve_recent_messages,
        has_custom_summarization=summarization_agent is not None,
    )

    return manager


def _create_summarization_agent(model_id: str, spec: Spec) -> Agent:
    """Create a summarization agent using a custom (typically cheaper) model.

    Uses existing model client pooling via create_model() to avoid duplicate clients.
    The summarization agent has a minimal system prompt focused on concise summarization.

    Args:
        model_id: Model identifier for summarization (e.g., "gpt-4o-mini")
        spec: Workflow spec for runtime configuration

    Returns:
        Configured Agent for summarization tasks

    Example:
        >>> agent = _create_summarization_agent("gpt-4o-mini", spec)
    """
    # Create runtime config with custom model but inherit provider/region
    summarization_runtime = Runtime(
        provider=spec.runtime.provider,
        model_id=model_id,
        region=spec.runtime.region,
        host=spec.runtime.host,
        temperature=0.3,  # Lower temperature for consistent summarization
    )

    # Reuse model client pooling
    model = create_model(summarization_runtime)

    # Minimal system prompt for summarization
    system_prompt = (
        "You are a helpful assistant that creates concise summaries of conversation history. "
        "Preserve key facts, decisions, and context while reducing length. "
        "Focus on information relevant to the ongoing task."
    )

    agent = Agent(
        name="summarization-agent",
        model=model,
        system_prompt=system_prompt,
        tools=None,  # No tools needed for summarization
    )

    return agent

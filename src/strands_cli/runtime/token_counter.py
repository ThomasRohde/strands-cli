"""Token counting utilities using tiktoken for accurate estimation.

Provides token counting for all supported providers (Bedrock, Ollama, OpenAI)
by mapping model IDs to appropriate tiktoken encodings. Used for proactive
budget tracking and context management.

Key Features:
- Provider-aware encoding selection
- Message format compatible with Strands SDK
- Accounts for message overhead (4 tokens per message)
- Fallback to cl100k_base for unknown models

Example:
    counter = TokenCounter("anthropic.claude-3-sonnet-20240229-v1:0")
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    tokens = counter.count_messages(messages)
"""

from typing import Any

import structlog
import tiktoken

logger = structlog.get_logger(__name__)


class TokenCounter:
    """Count tokens in messages using tiktoken.

    Maps provider model IDs to appropriate tiktoken encodings for accurate
    token estimation across Bedrock, Ollama, and OpenAI providers.

    Attributes:
        model_id: The model identifier (provider-specific)
        encoding: The tiktoken encoding instance for this model
    """

    def __init__(self, model_id: str) -> None:
        """Initialize token counter for a specific model.

        Args:
            model_id: Provider-specific model identifier
                - Bedrock: "anthropic.claude-3-sonnet-20240229-v1:0"
                - OpenAI: "gpt-4", "gpt-3.5-turbo"
                - Ollama: "llama2", "mistral"
        """
        self.model_id = model_id
        self.encoding = self._get_encoding(model_id)

        logger.debug(
            "token_counter_initialized",
            model_id=model_id,
            encoding_name=self.encoding.name,
        )

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens in a list of messages.

        Follows OpenAI's token counting methodology:
        - 4 tokens overhead per message
        - Encode all message content (role, content, name if present)

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Total token count including overhead
        """
        num_tokens = 0

        for message in messages:
            # 4 tokens per message overhead (role markers, etc.)
            num_tokens += 4

            # Count tokens in each field
            for _key, value in message.items():
                if value is not None:
                    # Convert to string and encode
                    text = str(value)
                    num_tokens += len(self.encoding.encode(text))

        # Add 2 tokens for assistant reply priming
        num_tokens += 2

        logger.debug(
            "tokens_counted",
            model_id=self.model_id,
            num_messages=len(messages),
            total_tokens=num_tokens,
        )

        return num_tokens

    def _get_encoding(self, model_id: str) -> tiktoken.Encoding:
        """Get appropriate tiktoken encoding for model.

        Maps provider model IDs to tiktoken encodings:
        - Claude models → cl100k_base
        - GPT-4/3.5 → model-specific encoding
        - Unknown → cl100k_base (fallback)

        Args:
            model_id: Provider-specific model identifier

        Returns:
            tiktoken.Encoding instance
        """
        model_lower = model_id.lower()

        # Bedrock Claude models
        if "claude" in model_lower or "anthropic" in model_lower:
            encoding = tiktoken.get_encoding("cl100k_base")
            logger.debug(
                "encoding_selected",
                model_id=model_id,
                encoding="cl100k_base",
                reason="claude_model",
            )
            return encoding

        # OpenAI models with specific encodings
        if "gpt-4" in model_lower or "gpt-3.5" in model_lower:
            try:
                encoding = tiktoken.encoding_for_model(model_id)
                logger.debug(
                    "encoding_selected",
                    model_id=model_id,
                    encoding=encoding.name,
                    reason="openai_model",
                )
                return encoding
            except KeyError:
                # Model not recognized, fall through to default
                logger.warning(
                    "openai_model_unknown",
                    model_id=model_id,
                    fallback="cl100k_base",
                )

        # Fallback for all other models (Ollama, unknown)
        encoding = tiktoken.get_encoding("cl100k_base")
        logger.debug(
            "encoding_selected",
            model_id=model_id,
            encoding="cl100k_base",
            reason="fallback",
        )
        return encoding

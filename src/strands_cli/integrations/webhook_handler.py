"""Webhook event handler infrastructure.

Provides abstract base class for webhook integrations and example
implementations for generic HTTP webhooks and Slack.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from strands_cli.events import WorkflowEvent

logger = structlog.get_logger(__name__)


class WebhookEventHandler(ABC):
    """Abstract base class for webhook event handlers.

    Provides generic HTTP POST implementation with retry logic.
    Subclasses implement payload formatting and URL/header configuration.

    Example:
        >>> class CustomWebhook(WebhookEventHandler):
        ...     def format_payload(self, event):
        ...         return {"message": event.spec_name}
        ...
        ...     def get_webhook_url(self):
        ...         return "https://example.com/hook"
        ...
        ...     def get_headers(self):
        ...         return {"Authorization": "Bearer token"}
    """

    @abstractmethod
    def format_payload(self, event: WorkflowEvent) -> dict[str, Any]:
        """Format event into webhook payload.

        Args:
            event: Workflow event to format

        Returns:
            Dictionary payload for webhook
        """
        pass

    @abstractmethod
    def get_webhook_url(self) -> str:
        """Get webhook URL.

        Returns:
            Full webhook URL
        """
        pass

    @abstractmethod
    def get_headers(self) -> dict[str, str]:
        """Get HTTP headers for webhook request.

        Returns:
            Dictionary of headers (e.g., authorization)
        """
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
    )
    async def send(self, event: WorkflowEvent) -> None:
        """Send event to webhook with retry logic.

        Uses exponential backoff retry for transient failures:
        - Attempt 1: Immediate
        - Attempt 2: Wait 1s
        - Attempt 3: Wait 2s

        Args:
            event: Event to send

        Raises:
            httpx.HTTPError: After 3 failed attempts
        """
        payload = self.format_payload(event)
        headers = self.get_headers()
        url = self.get_webhook_url()

        logger.debug(
            "Sending webhook",
            url=url,
            event_type=event.event_type,
            spec_name=event.spec_name,
        )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    "Webhook sent successfully",
                    url=url,
                    event_type=event.event_type,
                    status_code=response.status_code,
                )
            except httpx.HTTPError as e:
                logger.error(
                    "Webhook request failed",
                    url=url,
                    event_type=event.event_type,
                    error=str(e),
                    exc_info=True,
                )
                raise

    def __call__(self, event: WorkflowEvent) -> None:
        """Make handler callable for sync usage.

        Note: Runs send() in async context. For true async usage,
        call send() directly with await.

        Args:
            event: Event to handle
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, schedule the coroutine
            task = loop.create_task(self.send(event))
            # Task runs in background, errors logged by send()
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        except RuntimeError:
            # No event loop, run synchronously
            asyncio.run(self.send(event))


class GenericWebhookHandler(WebhookEventHandler):
    """Generic HTTP webhook handler.

    Sends event data as JSON to configured URL with optional headers.

    Example:
        >>> handler = GenericWebhookHandler(
        ...     url="https://hooks.example.com/workflow",
        ...     headers={"Authorization": "Bearer YOUR_TOKEN"},
        ... )
        >>> handler(event)  # Send event to webhook
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        """Initialize generic webhook handler.

        Args:
            url: Webhook URL
            headers: Optional HTTP headers (e.g., authorization)
        """
        self._url = url
        self._headers = headers or {}

    def format_payload(self, event: WorkflowEvent) -> dict[str, Any]:
        """Format event as JSON dictionary.

        Args:
            event: Workflow event

        Returns:
            Event as dictionary with ISO timestamp
        """
        return event.to_dict()

    def get_webhook_url(self) -> str:
        """Get configured webhook URL.

        Returns:
            Webhook URL
        """
        return self._url

    def get_headers(self) -> dict[str, str]:
        """Get configured headers.

        Returns:
            Headers dictionary
        """
        return self._headers


class SlackWebhookHandler(WebhookEventHandler):
    """Slack webhook handler (placeholder implementation).

    Formats events as Slack messages and sends to incoming webhook.

    Example:
        >>> handler = SlackWebhookHandler(
        ...     webhook_url="https://hooks.slack.com/services/XXX/YYY/ZZZ"
        ... )
        >>> handler(event)  # Send to Slack channel
    """

    def __init__(self, webhook_url: str):
        """Initialize Slack webhook handler.

        Args:
            webhook_url: Slack incoming webhook URL
        """
        self._url = webhook_url

    def format_payload(self, event: WorkflowEvent) -> dict[str, Any]:
        """Format event as Slack message.

        Args:
            event: Workflow event

        Returns:
            Slack message payload
        """
        # Basic Slack message format
        # Can be enhanced with blocks, attachments, etc.
        emoji_map = {
            "workflow_start": ":rocket:",
            "workflow_complete": ":white_check_mark:",
            "error": ":x:",
            "hitl_pause": ":hand:",
        }

        emoji = emoji_map.get(event.event_type, ":information_source:")
        text = f"{emoji} *{event.event_type}* - {event.spec_name}"

        if event.data:
            # Add key event details
            details = "\n".join(f"• {k}: {v}" for k, v in list(event.data.items())[:5])
            text += f"\n{details}"

        return {"text": text}

    def get_webhook_url(self) -> str:
        """Get Slack webhook URL.

        Returns:
            Webhook URL
        """
        return self._url

    def get_headers(self) -> dict[str, str]:
        """Get headers for Slack webhook.

        Returns:
            Content-Type header
        """
        return {"Content-Type": "application/json"}

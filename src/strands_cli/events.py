"""Event system for workflow execution.

Provides EventBus for pub/sub event handling with support for both
sync and async event handlers. Events are emitted at key workflow
checkpoints for observability and integration.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Event handler type (supports both sync and async)
EventHandler = Callable[["WorkflowEvent"], None] | Callable[["WorkflowEvent"], Awaitable[None]]


@dataclass
class WorkflowEvent:
    """Event emitted during workflow execution.

    Attributes:
        event_type: Type of event (e.g., 'workflow_start', 'step_complete')
        timestamp: When event was created
        session_id: Session ID if applicable
        spec_name: Workflow spec name
        pattern_type: Workflow pattern type
        data: Event-specific data
    """

    event_type: str
    timestamp: datetime
    spec_name: str
    pattern_type: str
    data: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary with ISO timestamp."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


class EventBus:
    """Thread-safe event bus for workflow events.

    Supports both synchronous and asynchronous event handlers.
    Handlers are called in subscription order.

    Example:
        >>> bus = EventBus()
        >>> @bus.subscribe("workflow_start")
        >>> def on_start(event: WorkflowEvent):
        >>>     print(f"Started: {event.spec_name}")
        >>> await bus.emit(WorkflowEvent(
        >>>     event_type="workflow_start",
        >>>     timestamp=datetime.now(),
        >>>     spec_name="example",
        >>>     pattern_type="chain",
        >>> ))
    """

    def __init__(self) -> None:
        """Initialize event bus."""
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe handler to event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callable to invoke when event is emitted
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        handler_name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.debug("Subscribed handler to event", event_type=event_type, handler=handler_name)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe handler from event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler to remove
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                handler_name = getattr(handler, "__name__", handler.__class__.__name__)
                logger.debug(
                    "Unsubscribed handler from event",
                    event_type=event_type,
                    handler=handler_name,
                )
            except ValueError:
                pass  # Handler not found, ignore

    async def emit(self, event: WorkflowEvent) -> None:
        """Emit event to all subscribed handlers.

        Handlers are called in subscription order. Async handlers are awaited,
        sync handlers are called directly. Errors in handlers are logged but
        don't stop other handlers from executing.

        Args:
            event: Event to emit
        """
        handlers = self._handlers.get(event.event_type, [])

        if not handlers:
            logger.debug("No handlers for event", event_type=event.event_type)
            return

        logger.debug(
            "Emitting event",
            event_type=event.event_type,
            handler_count=len(handlers),
            spec_name=event.spec_name,
        )

        # Use lock to ensure thread-safe access to handlers list
        async with self._lock:
            for handler in handlers:
                try:
                    # Call handler and check if result is awaitable
                    result = handler(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception as e:
                    handler_name = getattr(handler, "__name__", handler.__class__.__name__)
                    logger.error(
                        "Error in event handler",
                        event_type=event.event_type,
                        handler=handler_name,
                        error=str(e),
                        exc_info=True,
                    )

    def clear(self) -> None:
        """Remove all event handlers."""
        self._handlers.clear()
        logger.debug("Cleared all event handlers")

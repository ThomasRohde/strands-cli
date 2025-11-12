"""Unit tests for event system."""

import asyncio
from datetime import datetime

import pytest

from strands_cli.events import EventBus, WorkflowEvent


def test_event_bus_subscribe_and_emit() -> None:
    """Test basic event subscription and emission."""
    bus = EventBus()
    received_events: list[WorkflowEvent] = []

    def handler(event: WorkflowEvent) -> None:
        received_events.append(event)

    # Subscribe to event
    bus.subscribe("test_event", handler)

    # Emit event
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={"message": "test"},
    )
    asyncio.run(bus.emit(event))

    # Verify handler was called
    assert len(received_events) == 1
    assert received_events[0].event_type == "test_event"
    assert received_events[0].data["message"] == "test"


def test_event_bus_multiple_handlers() -> None:
    """Test multiple handlers for same event."""
    bus = EventBus()
    handler1_calls: list[WorkflowEvent] = []
    handler2_calls: list[WorkflowEvent] = []

    def handler1(event: WorkflowEvent) -> None:
        handler1_calls.append(event)

    def handler2(event: WorkflowEvent) -> None:
        handler2_calls.append(event)

    # Subscribe both handlers
    bus.subscribe("test_event", handler1)
    bus.subscribe("test_event", handler2)

    # Emit event
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    asyncio.run(bus.emit(event))

    # Verify both handlers were called
    assert len(handler1_calls) == 1
    assert len(handler2_calls) == 1


def test_event_bus_different_event_types() -> None:
    """Test handlers only receive subscribed event types."""
    bus = EventBus()
    type1_calls: list[WorkflowEvent] = []
    type2_calls: list[WorkflowEvent] = []

    def handler1(event: WorkflowEvent) -> None:
        type1_calls.append(event)

    def handler2(event: WorkflowEvent) -> None:
        type2_calls.append(event)

    # Subscribe to different events
    bus.subscribe("event_type_1", handler1)
    bus.subscribe("event_type_2", handler2)

    # Emit both events
    event1 = WorkflowEvent(
        event_type="event_type_1",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    event2 = WorkflowEvent(
        event_type="event_type_2",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    asyncio.run(bus.emit(event1))
    asyncio.run(bus.emit(event2))

    # Verify handlers only received their events
    assert len(type1_calls) == 1
    assert len(type2_calls) == 1
    assert type1_calls[0].event_type == "event_type_1"
    assert type2_calls[0].event_type == "event_type_2"


@pytest.mark.asyncio
async def test_event_bus_async_handler() -> None:
    """Test async event handlers."""
    bus = EventBus()
    received_events: list[WorkflowEvent] = []

    async def async_handler(event: WorkflowEvent) -> None:
        await asyncio.sleep(0.01)  # Simulate async work
        received_events.append(event)

    # Subscribe async handler
    bus.subscribe("test_event", async_handler)

    # Emit event
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={"async": True},
    )
    await bus.emit(event)

    # Verify handler was called
    assert len(received_events) == 1
    assert received_events[0].data["async"] is True


@pytest.mark.asyncio
async def test_event_bus_mixed_sync_async_handlers() -> None:
    """Test mixing sync and async handlers."""
    bus = EventBus()
    sync_calls: list[WorkflowEvent] = []
    async_calls: list[WorkflowEvent] = []

    def sync_handler(event: WorkflowEvent) -> None:
        sync_calls.append(event)

    async def async_handler(event: WorkflowEvent) -> None:
        await asyncio.sleep(0.01)
        async_calls.append(event)

    # Subscribe both
    bus.subscribe("test_event", sync_handler)
    bus.subscribe("test_event", async_handler)

    # Emit event
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    await bus.emit(event)

    # Verify both were called
    assert len(sync_calls) == 1
    assert len(async_calls) == 1


@pytest.mark.asyncio
async def test_event_bus_thread_safety() -> None:
    """Test concurrent event emission is thread-safe."""
    bus = EventBus()
    received_events: list[WorkflowEvent] = []

    async def handler(event: WorkflowEvent) -> None:
        await asyncio.sleep(0.001)
        received_events.append(event)

    bus.subscribe("test_event", handler)

    # Emit events concurrently
    async def emit_event(index: int) -> None:
        event = WorkflowEvent(
            event_type="test_event",
            timestamp=datetime.now(),
            session_id=f"session-{index}",
            spec_name="test-spec",
            pattern_type="chain",
            data={"index": index},
        )
        await bus.emit(event)

    # Run 10 concurrent emissions
    await asyncio.gather(*[emit_event(i) for i in range(10)])

    # Verify all events were received
    assert len(received_events) == 10
    indices = sorted([e.data["index"] for e in received_events])
    assert indices == list(range(10))


def test_event_bus_handler_error_does_not_break_execution() -> None:
    """Test that handler errors don't break event emission."""
    bus = EventBus()
    successful_calls: list[WorkflowEvent] = []

    def failing_handler(event: WorkflowEvent) -> None:
        raise ValueError("Handler error")

    def successful_handler(event: WorkflowEvent) -> None:
        successful_calls.append(event)

    # Subscribe both handlers
    bus.subscribe("test_event", failing_handler)
    bus.subscribe("test_event", successful_handler)

    # Emit event
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    asyncio.run(bus.emit(event))

    # Verify successful handler was still called
    assert len(successful_calls) == 1


def test_event_bus_unsubscribe() -> None:
    """Test unsubscribing from events."""
    bus = EventBus()
    calls: list[WorkflowEvent] = []

    def handler(event: WorkflowEvent) -> None:
        calls.append(event)

    # Subscribe and emit
    bus.subscribe("test_event", handler)
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )
    asyncio.run(bus.emit(event))
    assert len(calls) == 1

    # Unsubscribe and emit again
    bus.unsubscribe("test_event", handler)
    asyncio.run(bus.emit(event))
    assert len(calls) == 1  # Should not increase


def test_event_data_serialization() -> None:
    """Test that event data can be complex nested structures."""
    bus = EventBus()
    received_events: list[WorkflowEvent] = []

    def handler(event: WorkflowEvent) -> None:
        received_events.append(event)

    bus.subscribe("test_event", handler)

    # Emit event with complex data
    complex_data = {
        "step_index": 1,
        "response": "test response",
        "metadata": {
            "tokens": 100,
            "latency": 1.5,
            "model": "test-model",
        },
        "tags": ["tag1", "tag2"],
    }
    event = WorkflowEvent(
        event_type="test_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data=complex_data,
    )
    asyncio.run(bus.emit(event))

    # Verify data was preserved
    assert len(received_events) == 1
    assert received_events[0].data["step_index"] == 1
    assert received_events[0].data["metadata"]["tokens"] == 100
    assert received_events[0].data["tags"] == ["tag1", "tag2"]


@pytest.mark.asyncio
async def test_event_bus_no_handlers() -> None:
    """Test emitting event with no handlers doesn't error."""
    bus = EventBus()

    event = WorkflowEvent(
        event_type="unsubscribed_event",
        timestamp=datetime.now(),
        session_id="test-session",
        spec_name="test-spec",
        pattern_type="chain",
        data={},
    )

    # Should not raise
    await bus.emit(event)

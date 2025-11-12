"""Integration tests for event emission across workflow patterns."""

from datetime import datetime

import pytest

from strands_cli.events import EventBus, WorkflowEvent
from strands_cli.exec.chain import run_chain
from strands_cli.exec.parallel import run_parallel
from strands_cli.exec.workflow import run_workflow
from strands_cli.types import Spec


@pytest.mark.asyncio
async def test_chain_pattern_emits_events(chain_spec_fixture, mocker) -> None:
    """Test chain pattern emits workflow and step events."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    received_events: list[WorkflowEvent] = []

    def capture_event(event: WorkflowEvent) -> None:
        received_events.append(event)

    # Subscribe to all event types
    event_bus.subscribe("workflow_start", capture_event)
    event_bus.subscribe("step_start", capture_event)
    event_bus.subscribe("step_complete", capture_event)
    event_bus.subscribe("workflow_complete", capture_event)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain with event bus
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify events were emitted
    assert len(received_events) > 0
    event_types = [e.event_type for e in received_events]
    assert "workflow_start" in event_types
    assert "workflow_complete" in event_types


@pytest.mark.asyncio
async def test_workflow_pattern_emits_task_events(workflow_spec_fixture, mocker) -> None:
    """Test workflow pattern emits task-level events."""
    # Convert dict to Spec
    spec = Spec.model_validate(workflow_spec_fixture)

    event_bus = EventBus()
    task_events: list[WorkflowEvent] = []

    def capture_task_event(event: WorkflowEvent) -> None:
        task_events.append(event)

    event_bus.subscribe("task_start", capture_task_event)
    event_bus.subscribe("task_complete", capture_task_event)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.workflow.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run workflow with event bus
    await run_workflow(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify task events
    task_start_events = [e for e in task_events if e.event_type == "task_start"]
    task_complete_events = [e for e in task_events if e.event_type == "task_complete"]

    # Should have matching start/complete events
    assert len(task_start_events) > 0
    assert len(task_start_events) == len(task_complete_events)


@pytest.mark.asyncio
async def test_parallel_pattern_emits_branch_events(parallel_spec_fixture, mocker) -> None:
    """Test parallel pattern emits branch-level events."""
    # Convert dict to Spec
    spec = Spec.model_validate(parallel_spec_fixture)

    event_bus = EventBus()
    branch_events: list[WorkflowEvent] = []

    def capture_branch_event(event: WorkflowEvent) -> None:
        branch_events.append(event)

    event_bus.subscribe("branch_start", capture_branch_event)
    event_bus.subscribe("branch_complete", capture_branch_event)

    # Mock agent invocations - return string directly, not Mock
    mocker.patch(
        "strands_cli.exec.parallel.invoke_agent_with_retry",
        return_value="test response",
    )

    # Run parallel with event bus
    await run_parallel(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify branch events
    branch_start_events = [e for e in branch_events if e.event_type == "branch_start"]
    branch_complete_events = [e for e in branch_events if e.event_type == "branch_complete"]

    assert len(branch_start_events) > 0
    assert len(branch_start_events) == len(branch_complete_events)


@pytest.mark.asyncio
async def test_event_data_includes_context(chain_spec_fixture, mocker) -> None:
    """Test events include relevant context data."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    step_complete_events: list[WorkflowEvent] = []

    def capture_step_complete(event: WorkflowEvent) -> None:
        step_complete_events.append(event)

    event_bus.subscribe("step_complete", capture_step_complete)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify event data
    if step_complete_events:
        event = step_complete_events[0]
        assert "step_index" in event.data or "response" in event.data
        assert event.spec_name == spec.name
        assert event.pattern_type == "chain"


@pytest.mark.asyncio
async def test_events_emitted_in_order(chain_spec_fixture, mocker) -> None:
    """Test events are emitted in correct execution order."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    all_events: list[WorkflowEvent] = []

    def capture_all(event: WorkflowEvent) -> None:
        all_events.append(event)

    # Subscribe to all events
    event_bus.subscribe("workflow_start", capture_all)
    event_bus.subscribe("step_start", capture_all)
    event_bus.subscribe("step_complete", capture_all)
    event_bus.subscribe("workflow_complete", capture_all)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify events were emitted in order: workflow_start should be first
    if all_events:
        assert all_events[0].event_type == "workflow_start"
        # workflow_complete should be last
        assert all_events[-1].event_type == "workflow_complete"


@pytest.mark.asyncio
async def test_error_event_emitted_on_failure(chain_spec_fixture, mocker) -> None:
    """Test error event is emitted when execution fails."""
    from strands_cli.exec.chain import ChainExecutionError

    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    error_events: list[WorkflowEvent] = []

    def capture_error(event: WorkflowEvent) -> None:
        error_events.append(event)

    event_bus.subscribe("error", capture_error)

    # Mock agent to raise error
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        side_effect=RuntimeError("Test error"),
    )

    # Run chain (should fail with ChainExecutionError wrapping RuntimeError)
    with pytest.raises(ChainExecutionError):
        await run_chain(
            spec,
            variables={"topic": "test"},
            event_bus=event_bus,
        )

    # Verify error event was emitted
    assert len(error_events) > 0
    assert "error" in error_events[0].data or "message" in error_events[0].data


@pytest.mark.asyncio
async def test_callback_execution_order(chain_spec_fixture, mocker) -> None:
    """Test event callbacks execute in subscription order."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    callback_order: list[int] = []

    def callback1(event: WorkflowEvent) -> None:
        callback_order.append(1)

    def callback2(event: WorkflowEvent) -> None:
        callback_order.append(2)

    def callback3(event: WorkflowEvent) -> None:
        callback_order.append(3)

    # Subscribe in order
    event_bus.subscribe("workflow_complete", callback1)
    event_bus.subscribe("workflow_complete", callback2)
    event_bus.subscribe("workflow_complete", callback3)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify callbacks executed in order
    assert callback_order == [1, 2, 3]


@pytest.mark.asyncio
async def test_async_event_handlers(chain_spec_fixture, mocker) -> None:
    """Test async event handlers execute correctly."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    async_called = []

    async def async_handler(event: WorkflowEvent) -> None:
        import asyncio

        await asyncio.sleep(0.01)
        async_called.append(event.event_type)

    event_bus.subscribe("workflow_complete", async_handler)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify async handler was called
    assert "workflow_complete" in async_called


@pytest.mark.asyncio
async def test_event_timestamps(chain_spec_fixture, mocker) -> None:
    """Test events have valid timestamps."""
    # Convert dict to Spec
    spec = Spec.model_validate(chain_spec_fixture)

    event_bus = EventBus()
    timestamped_events: list[WorkflowEvent] = []

    def capture_event(event: WorkflowEvent) -> None:
        timestamped_events.append(event)

    event_bus.subscribe("workflow_start", capture_event)
    event_bus.subscribe("workflow_complete", capture_event)

    # Mock agent invocations
    mocker.patch(
        "strands_cli.exec.chain.invoke_agent_with_retry",
        return_value=mocker.Mock(response="test response"),
    )

    # Run chain
    await run_chain(
        spec,
        variables={"topic": "test"},
        event_bus=event_bus,
    )

    # Verify timestamps
    for event in timestamped_events:
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)

    # Verify timestamps are ordered
    if len(timestamped_events) >= 2:
        assert timestamped_events[0].timestamp <= timestamped_events[-1].timestamp

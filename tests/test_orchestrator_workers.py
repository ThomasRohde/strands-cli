"""Tests for orchestrator-workers pattern executor.

Tests orchestrator-workers pattern execution including:
- Basic flow: orchestrator → workers → reduce → writeup
- Max workers concurrency limiting
- Max rounds enforcement
- Worker tool overrides
- Indexed template access (workers[n].response)
- Malformed orchestrator JSON retry logic
- Empty subtask array handling
- Fail-fast on worker errors
- Budget tracking across rounds
- Agent caching for orchestrator/worker reuse
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.orchestrator_workers import (
    OrchestratorExecutionError,
    _parse_orchestrator_json,
    run_orchestrator_workers,
)
from strands_cli.types import (
    Agent,
    ChainStep,
    OrchestratorConfig,
    OrchestratorLimits,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
    WorkerTemplate,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def minimal_orchestrator_spec() -> Spec:
    """Create a minimal valid orchestrator-workers spec."""
    return Spec(
        version=0,
        name="test-orchestrator",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="You are an orchestrator who breaks down tasks"),
            "worker": Agent(prompt="You execute subtasks"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(agent="planner"),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        },
    )


@pytest.fixture
def full_orchestrator_spec() -> Spec:
    """Create orchestrator spec with all optional features (Phase 7 MVP: single-round only)."""
    return Spec(
        version=0,
        name="test-orchestrator-full",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="You orchestrate tasks"),
            "researcher": Agent(prompt="You research topics"),
            "aggregator": Agent(prompt="You aggregate findings"),
            "writer": Agent(prompt="You write reports"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="planner",
                    limits=OrchestratorLimits(
                        max_workers=3, max_rounds=1
                    ),  # Phase 7: single round only
                ),
                worker_template=WorkerTemplate(
                    agent="researcher",
                    tools=["http_executors", "strands_tools.http_request"],
                ),
                reduce=ChainStep(
                    agent="aggregator",
                    input="Aggregate findings: {{ workers }}",
                ),
                writeup=ChainStep(
                    agent="writer",
                    input="Write report from: {{ reduce_response }}",
                ),
            ),
        },
    )


@pytest.fixture
def mock_agent():
    """Create a mock agent with invoke_async method."""
    agent = MagicMock()
    agent.invoke_async = AsyncMock()
    return agent


# ============================================================================
# JSON Parsing Tests
# ============================================================================


def test_parse_orchestrator_json_valid_array():
    """Test parsing valid JSON array."""
    response = '[{"task": "Subtask 1"}, {"task": "Subtask 2"}, {"task": "Subtask 3"}]'
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is not None
    assert len(subtasks) == 3
    assert subtasks[0]["task"] == "Subtask 1"
    assert subtasks[2]["task"] == "Subtask 3"


def test_parse_orchestrator_json_single_object():
    """Test parsing single object (wraps in list)."""
    response = '{"task": "Single task"}'
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is not None
    assert len(subtasks) == 1
    assert subtasks[0]["task"] == "Single task"


def test_parse_orchestrator_json_empty_array():
    """Test parsing empty array (valid - signals no work)."""
    response = "[]"
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is not None
    assert len(subtasks) == 0


def test_parse_orchestrator_json_code_block():
    """Test extracting JSON from code block."""
    response = """Here are the subtasks:

```json
[{"task": "Task 1"}, {"task": "Task 2"}]
```

Execute these in parallel."""
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is not None
    assert len(subtasks) == 2


def test_parse_orchestrator_json_regex_extraction():
    """Test regex extraction when direct parse fails."""
    response = 'The tasks are: [{"task": "A"}, {"task": "B"}] - please execute them'
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is not None
    assert len(subtasks) == 2


def test_parse_orchestrator_json_malformed():
    """Test that malformed JSON returns None."""
    response = "This is not JSON at all"
    subtasks = _parse_orchestrator_json(response)

    assert subtasks is None


# ============================================================================
# Basic Execution Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_basic_flow(mock_cache_class, minimal_orchestrator_spec):
    """Test basic orchestrator → workers flow."""
    # Setup mock cache
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    # Mock agent responses
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # Configure mock to return different results per call
    mock_agent.invoke_async.side_effect = [
        '[{"task": "Research topic A"}, {"task": "Research topic B"}]',  # Orchestrator call
        "Found info about A",  # Worker 1
        "Found info about B",  # Worker 2
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    # Execute
    result = await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    # Verify
    assert result.success is True
    assert result.pattern_type == PatternType.ORCHESTRATOR_WORKERS
    assert "workers" in result.execution_context
    assert len(result.execution_context["workers"]) == 2
    assert result.execution_context["workers"][0]["response"] == "Found info about A"
    assert result.execution_context["round_count"] == 1
    # Token counts are tracked in execution but not in RunResult directly

    # Verify cache cleanup
    mock_cache.close.assert_called_once()


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_with_reduce_and_writeup(mock_cache_class, full_orchestrator_spec):
    """Test orchestrator → workers → reduce → writeup flow."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # Mock responses as strings
    mock_agent.invoke_async.side_effect = [
        '[{"task": "T1"}, {"task": "T2"}]',  # Orchestrator
        "Worker output",  # Worker 1
        "Worker output",  # Worker 2
        "Aggregated findings",  # Reduce
        "Final report",  # Writeup
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(full_orchestrator_spec, variables=None)

    assert result.success is True
    assert result.last_response == "Final report"
    assert "reduce_response" in result.execution_context
    assert result.execution_context["reduce_response"] == "Aggregated findings"
    assert "writeup_response" in result.execution_context


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_empty_subtasks(mock_cache_class, minimal_orchestrator_spec):
    """Test orchestrator returning empty array (no work needed)."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        return_value="[]"  # Empty array
    )
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    assert result.success is True
    assert len(result.execution_context["workers"]) == 0


# ============================================================================
# Concurrency & Limits Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_max_workers_limit(mock_cache_class):
    """Test that max_workers limit is enforced via semaphore."""
    spec = Spec(
        version=0,
        name="test-max-workers",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="Orchestrator"),
            "worker": Agent(prompt="Worker"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="planner",
                    limits=OrchestratorLimits(max_workers=2),  # Max 2 concurrent
                ),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        },
    )

    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # Orchestrator returns 5 tasks
    orchestrator_result = {
        "response": '[{"task": "T1"}, {"task": "T2"}, {"task": "T3"}, {"task": "T4"}, {"task": "T5"}]',
        "usage": {"total_tokens": 100},
    }
    worker_result = {
        "response": "Done",
        "usage": {"total_tokens": 30},
    }

    mock_agent.invoke_async.side_effect = [orchestrator_result] + [worker_result] * 5
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(spec, variables=None)

    assert result.success is True
    assert len(result.execution_context["workers"]) == 5
    # With max_workers=2, tasks execute in batches (not all at once)
    # Exact execution order depends on semaphore, but all 5 complete


# ============================================================================
# Error Handling Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_malformed_json_retry(mock_cache_class, minimal_orchestrator_spec):
    """Test retry logic for malformed orchestrator JSON."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # First call: malformed JSON
    # Second call: valid JSON (after retry)
    mock_agent.invoke_async.side_effect = [
        {"response": "This is not JSON", "usage": {"total_tokens": 50}},
        {"response": '[{"task": "Valid task"}]', "usage": {"total_tokens": 60}},
        {"response": "Worker done", "usage": {"total_tokens": 40}},
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    assert result.success is True
    assert len(result.execution_context["workers"]) == 1
    # Verify retry happened (2 orchestrator calls + 1 worker call)
    assert mock_agent.invoke_async.call_count == 3


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_malformed_json_max_retries(mock_cache_class, minimal_orchestrator_spec):
    """Test failure after max JSON retries."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        return_value={"response": "Not JSON", "usage": {"total_tokens": 50}}
    )
    mock_cache.get_or_build_agent.return_value = mock_agent

    with pytest.raises(OrchestratorExecutionError, match="Failed to parse orchestrator response"):
        await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    # Should attempt 3 times (initial + 2 retries)
    assert mock_agent.invoke_async.call_count == 3

    # Verify cleanup even on failure
    mock_cache.close.assert_called_once()


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_worker_failure_fail_fast(mock_cache_class, minimal_orchestrator_spec):
    """Test fail-fast on first worker error."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # Orchestrator returns 3 tasks
    orchestrator_result = {
        "response": '[{"task": "T1"}, {"task": "T2"}, {"task": "T3"}]',
        "usage": {"total_tokens": 100},
    }

    # First worker fails
    mock_agent.invoke_async.side_effect = [
        orchestrator_result,
        Exception("Worker 1 failed"),
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    with pytest.raises(Exception, match="Worker 1 failed"):
        await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    # Verify cleanup on failure
    mock_cache.close.assert_called_once()


# ============================================================================
# Template Context Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_indexed_template_access(mock_cache_class, full_orchestrator_spec):
    """Test indexed template access to worker results."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    mock_agent.invoke_async.side_effect = [
        '[{"task": "T1"}, {"task": "T2"}]',  # Orchestrator
        "Result from worker 0",  # Worker 1
        "Result from worker 1",  # Worker 2
        "Aggregated",  # Reduce
        "Final",  # Writeup
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(full_orchestrator_spec, variables=None)

    # Verify indexed access structure
    workers = result.execution_context["workers"]
    assert workers[0]["response"] == "Result from worker 0"
    assert workers[1]["response"] == "Result from worker 1"
    assert workers[0]["status"] == "success"
    assert workers[1]["status"] == "success"


# ============================================================================
# Tool Override Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_worker_tool_overrides(mock_cache_class):
    """Test that worker tool overrides are passed to agent builder."""
    spec = Spec(
        version=0,
        name="test-tool-overrides",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="Orchestrator"),
            "researcher": Agent(prompt="Researcher", tools=["default_tool"]),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(agent="planner"),
                worker_template=WorkerTemplate(
                    agent="researcher",
                    tools=["http_executors", "strands_tools.http_request"],  # Override
                ),
            ),
        },
    )

    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    orchestrator_result = {
        "response": '[{"task": "Research"}]',
        "usage": {"total_tokens": 100},
    }
    worker_result = {
        "response": "Done",
        "usage": {"total_tokens": 50},
    }

    mock_agent.invoke_async.side_effect = [orchestrator_result, worker_result]
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(spec, variables=None)

    assert result.success is True

    # Verify get_or_build_agent was called with tool_overrides for worker
    calls = mock_cache.get_or_build_agent.call_args_list
    # First call: orchestrator (no tool overrides)
    assert calls[0].kwargs.get("tool_overrides") is None
    # Second call: worker (with tool overrides)
    assert calls[1].kwargs.get("tool_overrides") == [
        "http_executors",
        "strands_tools.http_request",
    ]


# ============================================================================
# Configuration Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_orchestrator_missing_config():
    """Test error when orchestrator config is missing."""
    spec = Spec(
        version=0,
        name="test-missing-config",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"planner": Agent(prompt="Orchestrator")},
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(),  # Missing orchestrator and worker_template
        },
    )

    with pytest.raises(
        OrchestratorExecutionError, match="requires orchestrator and worker_template"
    ):
        await run_orchestrator_workers(spec, variables=None)


# ============================================================================
# Worker Isolation Tests (Phase 7 - Worker Index Cache Key)
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_workers_isolated_agents(mock_cache_class, minimal_orchestrator_spec):
    """Test that each worker gets its own agent instance via worker_index cache key."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    # Track all get_or_build_agent calls to verify worker_index values
    get_or_build_calls = []

    async def track_get_or_build_agent(*args, **kwargs):
        get_or_build_calls.append(kwargs.copy())
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock()
        return mock_agent

    mock_cache.get_or_build_agent.side_effect = track_get_or_build_agent

    # Create mock agents for orchestrator and workers
    orchestrator_agent = MagicMock()
    orchestrator_agent.invoke_async = AsyncMock(
        return_value='[{"task": "T1"}, {"task": "T2"}, {"task": "T3"}]'
    )

    worker_agent_1 = MagicMock()
    worker_agent_1.invoke_async = AsyncMock(return_value="Worker 1 result")

    worker_agent_2 = MagicMock()
    worker_agent_2.invoke_async = AsyncMock(return_value="Worker 2 result")

    worker_agent_3 = MagicMock()
    worker_agent_3.invoke_async = AsyncMock(return_value="Worker 3 result")

    # Setup cache to return different agents
    mock_cache.get_or_build_agent.side_effect = [
        orchestrator_agent,
        worker_agent_1,
        worker_agent_2,
        worker_agent_3,
    ]

    result = await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    assert result.success is True
    assert len(result.execution_context["workers"]) == 3

    # Verify get_or_build_agent was called 4 times (1 orchestrator + 3 workers)
    assert mock_cache.get_or_build_agent.call_count == 4

    # Verify orchestrator has worker_index=None
    orchestrator_call = mock_cache.get_or_build_agent.call_args_list[0]
    assert orchestrator_call.kwargs.get("worker_index") is None

    # Verify each worker has unique worker_index (0, 1, 2)
    worker_calls = mock_cache.get_or_build_agent.call_args_list[1:]
    worker_indices = [call.kwargs.get("worker_index") for call in worker_calls]
    assert worker_indices == [0, 1, 2]

    mock_cache.close.assert_called_once()


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_workers_concurrent_state_isolation(
    mock_cache_class, minimal_orchestrator_spec
):
    """Test that concurrent workers don't share conversation state."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    # Create separate mock agents for each worker to verify isolation
    orchestrator_agent = MagicMock()
    orchestrator_agent.invoke_async = AsyncMock(
        return_value='[{"task": "Research A"}, {"task": "Research B"}]'
    )

    worker_agent_0 = MagicMock()
    worker_agent_0.invoke_async = AsyncMock(return_value="Result about A")

    worker_agent_1 = MagicMock()
    worker_agent_1.invoke_async = AsyncMock(return_value="Result about B")

    # Return different agent instances per worker
    mock_cache.get_or_build_agent.side_effect = [
        orchestrator_agent,
        worker_agent_0,
        worker_agent_1,
    ]

    result = await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    assert result.success is True
    assert len(result.execution_context["workers"]) == 2

    # Verify each worker agent was invoked exactly once with its own task
    assert worker_agent_0.invoke_async.call_count == 1
    assert worker_agent_1.invoke_async.call_count == 1

    # Verify workers received different tasks (not shared conversation)
    worker_0_call = worker_agent_0.invoke_async.call_args_list[0]
    worker_1_call = worker_agent_1.invoke_async.call_args_list[0]

    assert "Research A" in worker_0_call.args[0]
    assert "Research B" in worker_1_call.args[0]

    # Verify responses are correctly isolated
    assert result.execution_context["workers"][0]["response"] == "Result about A"
    assert result.execution_context["workers"][1]["response"] == "Result about B"

    mock_cache.close.assert_called_once()


# ============================================================================
# Budget Tracking Tests
# ============================================================================


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_budget_tracking(mock_cache_class, full_orchestrator_spec):
    """Test cumulative budget tracking across all steps."""
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()

    # Define specific responses as strings
    mock_agent.invoke_async.side_effect = [
        '[{"task": "T1"}]',  # Orchestrator
        "W1",  # Worker
        "Reduced",  # Reduce
        "Final",  # Writeup
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    result = await run_orchestrator_workers(full_orchestrator_spec, variables=None)

    # Verify execution completed successfully
    assert result.success is True
    assert result.last_response == "Final"
    # Token tracking happens in logging, not stored in RunResult


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_budget_enforcement_hook_created(mock_cache_class):
    """Test that budget enforcer hook is created when budgets configured."""
    spec = Spec(
        version=0,
        name="test-budget",
        runtime=Runtime(
            provider=ProviderType.OLLAMA,
            host="http://localhost:11434",
            budgets={"max_tokens": 1000, "warn_threshold": 0.8},  # Budget configured
        ),
        agents={
            "planner": Agent(prompt="Orchestrator"),
            "worker": Agent(prompt="Worker"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(agent="planner"),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        },
    )

    # Mock cache and agent
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    # Mock agent to return minimal response
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value="[]")  # Empty subtasks
    mock_cache.get_or_build_agent.return_value = mock_agent

    # Execute workflow
    await run_orchestrator_workers(spec, variables=None)

    # Verify BudgetEnforcerHook was passed to get_or_build_agent
    assert mock_cache.get_or_build_agent.call_count >= 1

    # Check that hooks parameter includes BudgetEnforcerHook
    orchestrator_call = mock_cache.get_or_build_agent.call_args_list[0]
    hooks = orchestrator_call.kwargs.get("hooks", [])

    # Should have BudgetEnforcerHook in the list
    from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

    has_budget_hook = any(isinstance(hook, BudgetEnforcerHook) for hook in hooks)
    assert has_budget_hook, "BudgetEnforcerHook should be created when budgets configured"

    mock_cache.close.assert_called_once()


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_workers_independent_compaction_hooks(mock_cache_class):
    """Test that each worker gets its own compaction hook instance."""
    from strands_cli.types import Compaction, ContextPolicy

    spec = Spec(
        version=0,
        name="test-compaction",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="Orchestrator"),
            "worker": Agent(prompt="Worker"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(agent="planner"),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        },
        context_policy=ContextPolicy(compaction=Compaction(enabled=True, when_tokens_over=1000)),
    )

    # Track all hooks passed to get_or_build_agent
    all_hooks_lists = []

    async def capture_hooks(*args, **kwargs):
        hooks = kwargs.get("hooks", [])
        all_hooks_lists.append(hooks)
        mock_agent = MagicMock()
        # Return different responses based on call count
        if len(all_hooks_lists) == 1:
            # First call is orchestrator - return 2 tasks
            mock_agent.invoke_async = AsyncMock(
                return_value='[{"task": "Task 1"}, {"task": "Task 2"}]'
            )
        else:
            # Subsequent calls are workers
            mock_agent.invoke_async = AsyncMock(return_value="Worker response")
        return mock_agent

    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock(side_effect=capture_hooks)
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    await run_orchestrator_workers(spec, variables=None)

    # Verify multiple agents were created (orchestrator + workers)
    assert len(all_hooks_lists) >= 3, "Should have orchestrator + 2 workers"

    # Extract all ProactiveCompactionHook instances
    compaction_hooks = []
    for hooks_list in all_hooks_lists:
        for hook in hooks_list:
            if "ProactiveCompactionHook" in str(type(hook)):
                compaction_hooks.append(hook)

    # Should have multiple compaction hooks (one per agent)
    assert len(compaction_hooks) >= 3, "Each agent should get its own compaction hook"

    # Verify each is a different instance (not shared)
    assert compaction_hooks[0] is not compaction_hooks[1], "Hooks must be separate instances"
    assert compaction_hooks[0] is not compaction_hooks[2], "Hooks must be separate instances"
    assert compaction_hooks[1] is not compaction_hooks[2], "Hooks must be separate instances"

    mock_cache.close.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_max_rounds_validation():
    """Test that max_rounds != 1 is rejected with clear error."""
    spec = Spec(
        version=0,
        name="test-max-rounds",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "planner": Agent(prompt="Orchestrator"),
            "worker": Agent(prompt="Worker"),
        },
        pattern={
            "type": PatternType.ORCHESTRATOR_WORKERS,
            "config": PatternConfig(
                orchestrator=OrchestratorConfig(
                    agent="planner",
                    limits=OrchestratorLimits(max_rounds=3),  # Multi-round not supported
                ),
                worker_template=WorkerTemplate(agent="worker"),
            ),
        },
    )

    # Should raise OrchestratorExecutionError with clear message
    with pytest.raises(OrchestratorExecutionError) as exc_info:
        await run_orchestrator_workers(spec, variables=None)

    error_message = str(exc_info.value)
    assert "Multi-round orchestration not yet supported" in error_message
    assert "max_rounds=3" in error_message
    assert "Set max_rounds to 1" in error_message


@patch("strands_cli.exec.orchestrator_workers.AgentCache")
@pytest.mark.asyncio
async def test_orchestrator_json_parsing_all_retries_exhausted(
    mock_cache_class, minimal_orchestrator_spec
):
    """Test that JSON retry exhaustion provides structured error with retry history."""
    # Setup mock cache
    mock_cache = MagicMock()
    mock_cache.get_or_build_agent = AsyncMock()
    mock_cache.close = AsyncMock()
    mock_cache_class.return_value = mock_cache

    # Mock agent that always returns invalid JSON
    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock()
    mock_agent.invoke_async.side_effect = [
        "This is not valid JSON at all",  # Attempt 1
        "Still not JSON, sorry",  # Attempt 2
        "Nope, still plain text",  # Attempt 3 (max_json_retries=2 means 3 total attempts)
    ]
    mock_cache.get_or_build_agent.return_value = mock_agent

    # Should raise OrchestratorExecutionError with retry history
    with pytest.raises(OrchestratorExecutionError) as exc_info:
        await run_orchestrator_workers(minimal_orchestrator_spec, variables=None)

    error_message = str(exc_info.value)
    # Verify error contains structured information
    assert "Failed to parse orchestrator response as valid JSON" in error_message
    assert "after 3 attempts" in error_message
    assert "Retry history:" in error_message
    # Verify retry history is JSON formatted
    assert '"attempt": 1' in error_message
    assert '"attempt": 2' in error_message
    assert '"attempt": 3' in error_message
    assert '"response_preview":' in error_message

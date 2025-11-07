"""Tests for evaluator-optimizer pattern executor.

Tests evaluator-optimizer pattern execution including:
- Success on first iteration (score >= min_score)
- Success after multiple revisions
- Failure on max_iters exhaustion
- Malformed JSON retry logic (single retry)
- Template context injection (evaluation namespace)
- Budget tracking across iterations
- Agent caching for producer/evaluator reuse
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.evaluator_optimizer import (
    EvaluatorOptimizerExecutionError,
    _build_revision_context,
    _parse_evaluator_response,
    run_evaluator_optimizer,
)
from strands_cli.types import (
    AcceptConfig,
    Agent,
    EvaluatorConfig,
    EvaluatorDecision,
    PatternConfig,
    PatternType,
    ProviderType,
    Runtime,
    Spec,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def minimal_evaluator_optimizer_spec() -> Spec:
    """Create a minimal valid evaluator-optimizer spec."""
    return Spec(
        version=0,
        name="test-evaluator-optimizer",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "writer": Agent(prompt="You write drafts"),
            "critic": Agent(prompt="You critique for quality and return JSON"),
        },
        pattern={
            "type": PatternType.EVALUATOR_OPTIMIZER,
            "config": PatternConfig(
                producer="writer",
                evaluator=EvaluatorConfig(
                    agent="critic",
                    input="Evaluate the following draft:\n\n{{ draft }}",
                ),
                accept=AcceptConfig(min_score=80, max_iters=3),
                revise_prompt="Improve the draft based on: {{ evaluation.fixes }}",
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
# Evaluator Response Parsing Tests
# ============================================================================


def test_parse_evaluator_response_valid_json():
    """Test parsing valid JSON evaluator response."""
    response = '{"score": 85, "issues": ["Minor typo"], "fixes": ["Fix typo"]}'
    decision = _parse_evaluator_response(response, attempt=1)

    assert isinstance(decision, EvaluatorDecision)
    assert decision.score == 85
    assert decision.issues == ["Minor typo"]
    assert decision.fixes == ["Fix typo"]


def test_parse_evaluator_response_json_block():
    """Test parsing JSON from markdown code block."""
    response = """Here's my evaluation:

```json
{"score": 70, "issues": ["Issue 1", "Issue 2"], "fixes": ["Fix 1", "Fix 2"]}
```

The draft needs improvement."""
    decision = _parse_evaluator_response(response, attempt=1)

    assert decision.score == 70
    assert len(decision.issues) == 2
    assert len(decision.fixes) == 2


def test_parse_evaluator_response_minimal_fields():
    """Test parsing with only required score field."""
    response = '{"score": 90}'
    decision = _parse_evaluator_response(response, attempt=1)

    assert decision.score == 90
    assert decision.issues is None
    assert decision.fixes is None


def test_parse_evaluator_response_invalid_score():
    """Test that invalid score raises error."""
    response = '{"score": 150}'  # Score > 100
    with pytest.raises(EvaluatorOptimizerExecutionError, match="Failed to parse"):
        _parse_evaluator_response(response, attempt=1)


def test_parse_evaluator_response_malformed_json():
    """Test that malformed JSON raises error."""
    response = 'This is not JSON at all'
    with pytest.raises(EvaluatorOptimizerExecutionError, match="Failed to parse"):
        _parse_evaluator_response(response, attempt=1)


# ============================================================================
# Revision Context Tests
# ============================================================================


def test_build_revision_context_full():
    """Test building revision context with all fields."""
    evaluation = EvaluatorDecision(
        score=65,
        issues=["Issue 1", "Issue 2"],
        fixes=["Fix 1", "Fix 2"],
    )
    variables = {"topic": "testing", "style": "formal"}

    context = _build_revision_context("Draft text", evaluation, 2, variables)

    assert context["draft"] == "Draft text"
    assert context["iteration"] == 2
    assert context["evaluation"]["score"] == 65
    assert context["evaluation"]["issues"] == ["Issue 1", "Issue 2"]
    assert context["evaluation"]["fixes"] == ["Fix 1", "Fix 2"]
    assert context["topic"] == "testing"
    assert context["style"] == "formal"


def test_build_revision_context_minimal():
    """Test building revision context with minimal evaluation."""
    evaluation = EvaluatorDecision(score=50)

    context = _build_revision_context("Draft", evaluation, 1, None)

    assert context["draft"] == "Draft"
    assert context["iteration"] == 1
    assert context["evaluation"]["score"] == 50
    assert context["evaluation"]["issues"] == []
    assert context["evaluation"]["fixes"] == []


# ============================================================================
# Executor Integration Tests
# ============================================================================


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_success_first_iteration(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test successful execution on first iteration (score >= min_score)."""
    # Mock cache and agents
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer
            '{"score": 85, "issues": [], "fixes": []}',  # Evaluator (accepted)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True
    assert result.last_response == "Draft v1"
    assert result.pattern_type == PatternType.EVALUATOR_OPTIMIZER
    assert result.execution_context["iterations"] == 1
    assert result.execution_context["final_score"] == 85
    assert result.execution_context["min_score"] == 80
    assert len(result.execution_context["history"]) == 1


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_requires_revision(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test revision loop until acceptance."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer (initial)
            '{"score": 60, "issues": ["Issue1"], "fixes": ["Fix1"]}',  # Evaluator (reject)
            "Draft v2",  # Producer (revision)
            '{"score": 90, "issues": [], "fixes": []}',  # Evaluator (accept)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True
    assert result.last_response == "Draft v2"
    assert result.execution_context["iterations"] == 2
    assert result.execution_context["final_score"] == 90
    assert len(result.execution_context["history"]) == 2

    # Verify producer called twice (initial + 1 revision)
    assert mock_agent.invoke_async.call_count == 4  # 2x producer, 2x evaluator


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_max_iters_exhausted(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test failure when max_iters exhausted without acceptance."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer (initial)
            '{"score": 50, "issues": ["I1"], "fixes": ["F1"]}',  # Evaluator (reject)
            "Draft v2",  # Producer (revision 1)
            '{"score": 55, "issues": ["I2"], "fixes": ["F2"]}',  # Evaluator (reject)
            "Draft v3",  # Producer (revision 2)
            '{"score": 60, "issues": ["I3"], "fixes": ["F3"]}',  # Evaluator (reject, max_iters=3)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    with pytest.raises(
        EvaluatorOptimizerExecutionError,
        match=r"Max iterations \(3\) exhausted.*Final score: 60",
    ):
        await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    mock_cache.close.assert_awaited_once()


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_malformed_json_retry_success(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test malformed JSON retry with success on second attempt."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer
            "This is not JSON",  # Evaluator (malformed, attempt 1)
            '{"score": 85, "issues": [], "fixes": []}',  # Evaluator retry (success)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True
    assert result.last_response == "Draft v1"
    assert result.execution_context["final_score"] == 85

    # Producer called once, evaluator called twice (malformed + retry)
    assert mock_agent.invoke_async.call_count == 3


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_malformed_json_retry_exhausted(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test failure when both JSON parse attempts fail."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer
            "Not JSON attempt 1",  # Evaluator (malformed, attempt 1)
            "Not JSON attempt 2",  # Evaluator retry (still malformed)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    with pytest.raises(
        EvaluatorOptimizerExecutionError,
        match=r"Evaluator failed to return valid JSON after 2 attempts",
    ):
        await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    mock_cache.close.assert_awaited_once()


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_multiple_revisions(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test multiple revision cycles before acceptance."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",  # Producer (initial)
            '{"score": 50, "issues": ["I1"], "fixes": ["F1"]}',  # Evaluator (reject)
            "Draft v2",  # Producer (revision 1)
            '{"score": 70, "issues": ["I2"], "fixes": ["F2"]}',  # Evaluator (reject)
            "Draft v3",  # Producer (revision 2)
            '{"score": 85, "issues": [], "fixes": []}',  # Evaluator (accept)
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True
    assert result.last_response == "Draft v3"
    assert result.execution_context["iterations"] == 3
    assert result.execution_context["final_score"] == 85

    # Verify iteration history
    history = result.execution_context["history"]
    assert len(history) == 3
    assert history[0]["score"] == 50
    assert history[1]["score"] == 70
    assert history[2]["score"] == 85


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_with_budget_tracking(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test that budget tracking works across iterations."""
    # Add budget to spec
    minimal_evaluator_optimizer_spec.runtime.budgets = {"max_tokens": 10000}

    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(
        side_effect=[
            "Draft v1",
            '{"score": 85, "issues": [], "fixes": []}',
        ]
    )
    mock_cache.get_or_build_agent = AsyncMock(return_value=mock_agent)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True
    assert "cumulative_tokens" in result.execution_context
    assert result.execution_context["cumulative_tokens"] > 0


@pytest.mark.asyncio
async def test_run_evaluator_optimizer_missing_producer():
    """Test that missing producer agent raises error."""
    spec = Spec(
        version=0,
        name="test",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"critic": Agent(prompt="Critic")},
        pattern={
            "type": PatternType.EVALUATOR_OPTIMIZER,
            "config": PatternConfig(
                producer="writer",  # Not in agents
                evaluator=EvaluatorConfig(agent="critic"),
                accept=AcceptConfig(min_score=80),
            ),
        },
    )

    with pytest.raises(
        EvaluatorOptimizerExecutionError,
        match="Producer agent 'writer' not found",
    ):
        await run_evaluator_optimizer(spec)


@pytest.mark.asyncio
async def test_run_evaluator_optimizer_missing_evaluator():
    """Test that missing evaluator agent raises error."""
    spec = Spec(
        version=0,
        name="test",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={"writer": Agent(prompt="Writer")},
        pattern={
            "type": PatternType.EVALUATOR_OPTIMIZER,
            "config": PatternConfig(
                producer="writer",
                evaluator=EvaluatorConfig(agent="critic"),  # Not in agents
                accept=AcceptConfig(min_score=80),
            ),
        },
    )

    with pytest.raises(
        EvaluatorOptimizerExecutionError,
        match="Evaluator agent 'critic' not found",
    ):
        await run_evaluator_optimizer(spec)


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_run_evaluator_optimizer_agent_caching(
    mock_cache_class, minimal_evaluator_optimizer_spec
):
    """Test that agents are properly cached and reused."""
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_producer = MagicMock()
    mock_producer.invoke_async = AsyncMock(side_effect=["Draft v1", "Draft v2"])

    mock_evaluator = MagicMock()
    mock_evaluator.invoke_async = AsyncMock(
        side_effect=[
            '{"score": 70, "issues": ["I1"], "fixes": ["F1"]}',
            '{"score": 90, "issues": [], "fixes": []}',
        ]
    )

    # Return different agents for producer vs evaluator
    async def get_agent_side_effect(spec, agent_id, config, tool_overrides=None, **kwargs):
        if agent_id == "writer":
            return mock_producer
        elif agent_id == "critic":
            return mock_evaluator
        raise ValueError(f"Unexpected agent: {agent_id}")

    mock_cache.get_or_build_agent = AsyncMock(side_effect=get_agent_side_effect)

    result = await run_evaluator_optimizer(minimal_evaluator_optimizer_spec)

    assert result.success is True

    # Verify get_or_build_agent called exactly twice (producer + evaluator)
    assert mock_cache.get_or_build_agent.call_count == 2

    # Verify agents were invoked correct number of times
    assert mock_producer.invoke_async.call_count == 2  # Initial + 1 revision
    assert mock_evaluator.invoke_async.call_count == 2  # 2 evaluations


@pytest.mark.asyncio
@patch("strands_cli.exec.evaluator_optimizer.AgentCache")
async def test_default_revision_prompt_includes_context(mock_cache_class):
    """Test that default revision prompt template includes draft and evaluation context.

    Regression test for Phase 4 review finding: default revision prompt must include
    template variables ({{ draft }}, {{ evaluation.score }}, {{ evaluation.issues }},
    {{ evaluation.fixes }}) so the producer agent receives actual context for revision.
    """
    # Create spec WITHOUT revise_prompt to trigger default template
    spec = Spec(
        version=0,
        name="test-default-revise-prompt",
        runtime=Runtime(provider=ProviderType.OLLAMA, host="http://localhost:11434"),
        agents={
            "writer": Agent(prompt="You write drafts"),
            "critic": Agent(prompt="You critique"),
        },
        pattern={
            "type": PatternType.EVALUATOR_OPTIMIZER,
            "config": PatternConfig(
                producer="writer",
                evaluator=EvaluatorConfig(
                    agent="critic",
                    input="Evaluate: {{ draft }}",
                ),
                accept=AcceptConfig(min_score=85, max_iters=2),
                # NO revise_prompt specified - should use default template
            ),
        },
    )

    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_cache.close = AsyncMock()

    mock_producer = MagicMock()
    mock_evaluator = MagicMock()

    # Track actual prompts sent to producer
    producer_prompts = []

    async def producer_invoke(prompt):
        producer_prompts.append(prompt)
        return f"Draft revision {len(producer_prompts)}"

    mock_producer.invoke_async = AsyncMock(side_effect=producer_invoke)

    # Evaluator returns low score first (trigger revision), then high score
    mock_evaluator.invoke_async = AsyncMock(
        side_effect=[
            '{"score": 60, "issues": ["Needs more detail", "Grammar errors"], "fixes": ["Add examples", "Fix grammar"]}',
            '{"score": 90, "issues": [], "fixes": []}',
        ]
    )

    async def get_agent_side_effect(spec, agent_id, config, tool_overrides=None, **kwargs):
        if agent_id == "writer":
            return mock_producer
        elif agent_id == "critic":
            return mock_evaluator
        raise ValueError(f"Unexpected agent: {agent_id}")

    mock_cache.get_or_build_agent = AsyncMock(side_effect=get_agent_side_effect)

    result = await run_evaluator_optimizer(spec)

    assert result.success is True
    assert len(producer_prompts) == 2  # Initial + 1 revision

    # Verify the SECOND prompt (revision prompt) contains all context
    revision_prompt = producer_prompts[1]

    # Must contain the draft text
    assert "Draft revision 1" in revision_prompt

    # Must contain the evaluation score
    assert "60" in revision_prompt or "Score: 60" in revision_prompt

    # Must contain the issues
    assert "Needs more detail" in revision_prompt
    assert "Grammar errors" in revision_prompt

    # Must contain the fixes
    assert "Add examples" in revision_prompt
    assert "Fix grammar" in revision_prompt

    # Verify it's not just the hardcoded broken default
    assert revision_prompt != "Revise the draft based on the evaluator feedback."

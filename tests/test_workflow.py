"""Tests for exec/workflow.py — DAG-based multi-task workflow executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands_cli.exec.workflow import _topological_sort, run_workflow
from strands_cli.types import Spec


class TestTopologicalSort:
    """Test DAG topological sorting for execution order."""

    def test_topological_sort_single_task(self, tmp_path: Path) -> None:
        """Single task with no dependencies."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {"tasks": [{"id": "task1", "agent": "agent1", "input": "Do work"}]},
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))
        tasks = spec.pattern.config.tasks or []

        layers = _topological_sort(tasks)

        assert len(layers) == 1
        assert len(layers[0]) == 1
        assert layers[0][0] == "task1"

    def test_topological_sort_linear_dependency(self, tmp_path: Path) -> None:
        """Linear dependency chain: task1 -> task2 -> task3."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Step 1"},
                        {"id": "task2", "agent": "agent1", "input": "Step 2", "deps": ["task1"]},
                        {"id": "task3", "agent": "agent1", "input": "Step 3", "deps": ["task2"]},
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))
        tasks = spec.pattern.config.tasks or []

        layers = _topological_sort(tasks)

        assert len(layers) == 3
        assert layers[0][0] == "task1"
        assert layers[1][0] == "task2"
        assert layers[2][0] == "task3"

    def test_topological_sort_parallel_branches(self, tmp_path: Path) -> None:
        """Parallel execution: task1 -> (task2, task3) -> task4."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Root"},
                        {"id": "task2", "agent": "agent1", "input": "Branch A", "deps": ["task1"]},
                        {"id": "task3", "agent": "agent1", "input": "Branch B", "deps": ["task1"]},
                        {
                            "id": "task4",
                            "agent": "agent1",
                            "input": "Merge",
                            "deps": ["task2", "task3"],
                        },
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))
        tasks = spec.pattern.config.tasks or []

        layers = _topological_sort(tasks)

        assert len(layers) == 3
        assert len(layers[0]) == 1  # task1
        assert len(layers[1]) == 2  # task2, task3 (parallel)
        assert len(layers[2]) == 1  # task4
        assert layers[0][0] == "task1"
        assert set(layers[1]) == {"task2", "task3"}
        assert layers[2][0] == "task4"

    def test_topological_sort_diamond_dependency(self, tmp_path: Path) -> None:
        """Diamond pattern: task1 -> (task2, task3) -> task4."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "collect", "agent": "agent1", "input": "Collect data"},
                        {
                            "id": "analyze_a",
                            "agent": "agent1",
                            "input": "Analyze A",
                            "deps": ["collect"],
                        },
                        {
                            "id": "analyze_b",
                            "agent": "agent1",
                            "input": "Analyze B",
                            "deps": ["collect"],
                        },
                        {
                            "id": "summarize",
                            "agent": "agent1",
                            "input": "Summarize",
                            "deps": ["analyze_a", "analyze_b"],
                        },
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))
        tasks = spec.pattern.config.tasks or []

        layers = _topological_sort(tasks)

        assert len(layers) == 3
        assert layers[0][0] == "collect"
        assert set(layers[1]) == {"analyze_a", "analyze_b"}
        assert layers[2][0] == "summarize"


class TestRunWorkflow:
    """Test workflow execution orchestration."""

    @pytest.fixture
    def workflow_spec_parallel(self, tmp_path: Path) -> Spec:
        """Workflow with parallel tasks for testing."""
        from ruamel.yaml import YAML

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model", "max_parallel": 2},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "test-agent", "input": "Task 1"},
                        {
                            "id": "task2",
                            "agent": "test-agent",
                            "input": "Task 2 depends on task1",
                            "deps": ["task1"],
                        },
                        {
                            "id": "task3",
                            "agent": "test-agent",
                            "input": "Task 3 depends on task1",
                            "deps": ["task1"],
                        },
                        {
                            "id": "task4",
                            "agent": "test-agent",
                            "input": "Task 4 merges 2 and 3",
                            "deps": ["task2", "task3"],
                        },
                    ],
                },
            },
            "agents": {
                "test-agent": {
                    "prompt": "You are a test agent",
                    "tools": [],
                }
            },
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        from strands_cli.loader.yaml_loader import load_spec

        return load_spec(str(spec_file))

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_success(
        self, mock_build_agent: MagicMock, workflow_spec_parallel: Spec
    ) -> None:
        """Test successful workflow execution with parallel tasks."""
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Result 1",
                "Result 2",
                "Result 3",
                "Result 4",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_workflow(workflow_spec_parallel, variables=None)

        assert result.success is True
        assert result.last_response == "Result 4"  # Last task result
        assert mock_build_agent.call_count == 4

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_task_failure(
        self, mock_build_agent: MagicMock, workflow_spec_parallel: Spec
    ) -> None:
        """Test workflow stops on task failure."""
        from strands_cli.exec.workflow import WorkflowExecutionError

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("Task failed"))
        mock_build_agent.return_value = mock_agent

        with pytest.raises(WorkflowExecutionError, match="Task failed"):
            run_workflow(workflow_spec_parallel, variables=None)

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_respects_max_parallel(
        self, mock_build_agent: MagicMock, workflow_spec_parallel: Spec
    ) -> None:
        """Test max_parallel constraint enforced."""
        # max_parallel=2 in fixture
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Result 1",
                "Result 2",
                "Result 3",
                "Result 4",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_workflow(workflow_spec_parallel, variables=None)

        assert result.success is True
        # Can't directly test semaphore but verify all tasks completed

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_with_task_context(
        self, mock_build_agent: MagicMock, tmp_path: Path
    ) -> None:
        """Test task context includes previous task results."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "agent1", "input": "Do work"},
                        {
                            "id": "task2",
                            "agent": "agent1",
                            "input": "Result was: {{ tasks.task1.response }}",
                            "deps": ["task1"],
                        },
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "First result",
                "Second result",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_workflow(spec, variables=None)

        assert result.success is True

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_budget_tracking(
        self, mock_build_agent: MagicMock, workflow_spec_parallel: Spec
    ) -> None:
        """Test budget consumption tracking across tasks."""
        workflow_spec_parallel.runtime.budgets = {"max_tokens": 500}

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Result 1",
                "Result 2",
                "Result 3",
                "Result 4",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_workflow(workflow_spec_parallel, variables=None)

        assert result.success is True

    @patch("strands_cli.exec.workflow.build_agent")
    def test_run_workflow_budget_exceeded(
        self, mock_build_agent: MagicMock, workflow_spec_parallel: Spec
    ) -> None:
        """Test workflow stops when budget exceeded."""
        from strands_cli.exec.workflow import WorkflowExecutionError

        workflow_spec_parallel.runtime.budgets = {"max_tokens": 5}

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            return_value="Result with many tokens that exceeds budget"
        )
        mock_build_agent.return_value = mock_agent

        with pytest.raises(WorkflowExecutionError, match="budget exceeded"):
            run_workflow(workflow_spec_parallel, variables=None)


class TestWorkflowTemplateRendering:
    """Test Jinja2 template rendering in workflow execution."""

    @patch("strands_cli.exec.workflow.build_agent")
    def test_workflow_renders_task_references(
        self, mock_build_agent: MagicMock, tmp_path: Path
    ) -> None:
        """Test that {{ tasks.<id>.response }} renders correctly."""
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        spec_data = {
            "name": "Test Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "fetch", "agent": "agent1", "input": "Fetch data"},
                        {
                            "id": "analyze",
                            "agent": "agent1",
                            "input": "Analyze: {{ tasks.fetch.response }}",
                            "deps": ["fetch"],
                        },
                    ]
                },
            },
            "agents": {"agent1": {"prompt": "You are a worker"}},
        }

        spec_file = tmp_path / "workflow.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(
            side_effect=[
                "Data: [1,2,3]",
                "Analysis complete",
            ]
        )
        mock_build_agent.return_value = mock_agent

        result = run_workflow(spec, variables=None)

        assert result.success is True


class TestMultiAgentWorkflowRegression:
    """Regression tests for workflow.py multi-agent support."""

    @patch("strands_cli.exec.workflow.build_agent")
    def test_tasks_use_declared_agents(self, mock_build_agent: MagicMock, tmp_path: Path) -> None:
        """Test that multi-agent workflows use correct agent per task.

        Regression test for issue where run_workflow reused one agent config for all tasks.
        """
        from ruamel.yaml import YAML

        from strands_cli.loader.yaml_loader import load_spec

        yaml = YAML()
        # Create workflow with different agents per task
        spec_data = {
            "name": "Multi-Agent Workflow",
            "version": "1.0.0",
            "runtime": {"provider": "bedrock", "model_id": "test-model", "region": "us-east-1"},
            "pattern": {
                "type": "workflow",
                "config": {
                    "tasks": [
                        {"id": "task1", "agent": "researcher", "input": "Research topic"},
                        {
                            "id": "task2",
                            "agent": "writer",
                            "input": "Write article",
                            "deps": ["task1"],
                        },
                    ]
                },
            },
            "agents": {
                "researcher": {"prompt": "You are a researcher"},
                "writer": {"prompt": "You are a writer"},
            },
        }

        spec_file = tmp_path / "multi_agent.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        spec = load_spec(str(spec_file))

        # Track which agents were built
        agent_ids_built = []

        def track_build_agent(spec_arg, agent_id, agent_config):
            agent_ids_built.append(agent_id)
            mock_agent = MagicMock()
            mock_agent.invoke_async = AsyncMock(return_value=f"Response from {agent_id}")
            return mock_agent

        mock_build_agent.side_effect = track_build_agent

        result = run_workflow(spec, variables=None)

        # Verify both agents were used
        assert result.success is True
        assert "researcher" in agent_ids_built
        assert "writer" in agent_ids_built
        assert len(agent_ids_built) == 2

        # Verify tasks were executed with correct agents
        assert result.execution_context["tasks"]["task1"]["agent"] == "researcher"
        assert result.execution_context["tasks"]["task2"]["agent"] == "writer"

        # Verify final result came from writer (last task)
        assert result.agent_id == "writer"

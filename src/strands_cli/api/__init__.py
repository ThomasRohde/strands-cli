"""Strands Python API - First-class programmatic interface.

Example (from file):
    >>> from strands import Workflow
    >>> workflow = Workflow.from_file("workflow.yaml")
    >>> result = workflow.run_interactive(topic="AI")
    >>> print(result.last_response)

Example (builder API):
    >>> from strands import FluentBuilder
    >>> workflow = (
    ...     FluentBuilder("research")
    ...     .runtime("openai", model="gpt-4o-mini")
    ...     .agent("researcher", "You are a research assistant")
    ...     .chain()
    ...         .step("researcher", "Research: {{topic}}")
    ...         .step("researcher", "Analyze: {{ steps[0].response }}")
    ...     .artifact("report.md", "{{ last_response }}")
    ...     .build()
    ... )
    >>> result = workflow.run_interactive(topic="AI")
"""

from pathlib import Path
from typing import Any

from strands_cli.api.builders import (
    ChainBuilder,
    EvaluatorOptimizerBuilder,
    FluentBuilder,
    GraphBuilder,
    OrchestratorWorkersBuilder,
    ParallelBuilder,
    RoutingBuilder,
    WorkflowBuilder,
)
from strands_cli.api.exceptions import BuildError
from strands_cli.api.execution import WorkflowExecutor
from strands_cli.loader import load_spec
from strands_cli.types import RunResult, Spec


class Workflow:
    """Primary API for creating and executing workflows.

    Can be created from YAML files or built programmatically.
    Supports both interactive (terminal prompts) and async execution.
    """

    def __init__(self, spec: Spec):
        """Create workflow from validated Spec.

        Args:
            spec: Validated workflow specification
        """
        self.spec = spec

    @classmethod
    def from_file(cls, path: str | Path, **variables: Any) -> "Workflow":
        """Load workflow from YAML/JSON file.

        Args:
            path: Path to workflow spec file
            **variables: Variable overrides (key=value)

        Returns:
            Workflow instance ready to run

        Raises:
            LoadError: If file cannot be loaded
            SchemaValidationError: If spec is invalid

        Example:
            >>> workflow = Workflow.from_file("workflow.yaml", topic="AI")
            >>> result = workflow.run_interactive()
        """
        spec = load_spec(str(path), variables)
        return cls(spec)

    def run_interactive(self, hitl_handler: Any = None, **variables: Any) -> RunResult:
        """Execute workflow with interactive HITL prompts.

        When workflow reaches HITL steps, prompts user in terminal
        for input instead of pausing execution. Ideal for local
        development and debugging.

        Args:
            hitl_handler: Optional custom HITL handler function (state: HITLState) -> str
            **variables: Runtime variable overrides

        Returns:
            RunResult with execution details

        Example:
            >>> result = workflow.run_interactive(topic="AI")
            >>> print(result.last_response)
        """
        import asyncio

        return asyncio.run(self.run_interactive_async(hitl_handler=hitl_handler, **variables))

    async def run_interactive_async(
        self, hitl_handler: Any = None, **variables: Any
    ) -> RunResult:
        """Execute workflow asynchronously with interactive HITL.

        For high-performance applications that need async control flow.

        Args:
            hitl_handler: Optional custom HITL handler function (state: HITLState) -> str
            **variables: Runtime variable overrides

        Returns:
            RunResult with execution details
        """
        executor = WorkflowExecutor(self.spec)
        return await executor.run_interactive(variables, hitl_handler=hitl_handler)

    def run(self, **variables: Any) -> RunResult:
        """Execute workflow (non-interactive, uses session persistence).

        Standard execution mode - saves session and exits at HITL steps.
        Use for production workflows or when integrating with external
        approval systems.

        Args:
            **variables: Runtime variable overrides

        Returns:
            RunResult with execution details (may indicate HITL pause)
        """
        import asyncio

        return asyncio.run(self.run_async(**variables))

    async def run_async(self, **variables: Any) -> RunResult:
        """Execute workflow asynchronously (non-interactive).

        Args:
            **variables: Runtime variable overrides

        Returns:
            RunResult with execution details
        """
        executor = WorkflowExecutor(self.spec)
        return await executor.run(variables)


__all__ = [
    "BuildError",
    "ChainBuilder",
    "EvaluatorOptimizerBuilder",
    "FluentBuilder",
    "GraphBuilder",
    "OrchestratorWorkersBuilder",
    "ParallelBuilder",
    "RoutingBuilder",
    "Workflow",
    "WorkflowBuilder",
]


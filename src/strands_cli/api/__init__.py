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
    ...     .step("researcher", "Research: {{topic}}")
    ...     .step("researcher", "Analyze: {{ steps[0].response }}")
    ...     .artifact("report.md", "{{ last_response }}")
    ...     .build()
    ... )
    >>> result = workflow.run_interactive(topic="AI")
"""

from collections.abc import AsyncGenerator, Callable
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
from strands_cli.api.session_manager import SessionManager
from strands_cli.loader import load_spec
from strands_cli.types import RunResult, Spec, StreamChunk


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
        self._executor = WorkflowExecutor(spec)

    def on(self, event_type: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Subscribe to workflow events.

        Decorator for registering event callbacks. Events are emitted during
        workflow execution at key checkpoints (workflow_start, step_complete, etc.).

        Args:
            event_type: Event type to subscribe to

        Returns:
            Decorator function

        Example:
            >>> workflow = Workflow.from_file("workflow.yaml")
            >>> @workflow.on("step_complete")
            >>> def on_step(event):
            ...     print(f"Step {event.data['step_index']} done")
            >>> result = workflow.run_interactive(topic="AI")
        """
        return self._executor.on(event_type)

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

    async def run_interactive_async(self, hitl_handler: Any = None, **variables: Any) -> RunResult:
        """Execute workflow asynchronously with interactive HITL.

        For high-performance applications that need async control flow.

        Args:
            hitl_handler: Optional custom HITL handler function (state: HITLState) -> str
            **variables: Runtime variable overrides

        Returns:
            RunResult with execution details
        """
        # FIX: Reuse self._executor so event handlers fire
        return await self._executor.run_interactive(variables, hitl_handler=hitl_handler)

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
        # FIX: Reuse self._executor so event handlers fire
        return await self._executor.run(variables)

    def async_executor(self) -> WorkflowExecutor:
        """Get async context manager for workflow execution.

        Provides automatic resource cleanup via async context manager protocol.
        Returns the shared executor instance so event handlers fire correctly.

        Returns:
            WorkflowExecutor that can be used as async context manager

        Example:
            >>> async with workflow.async_executor() as executor:
            ...     result = await executor.run(topic="AI")
            ... # Resources automatically cleaned up
        """
        return self._executor

    async def stream_async(
        self, variables: dict[str, Any] | None = None, **kwargs: Any
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream workflow execution events in real-time.

        Note: Token-by-token streaming not yet implemented.
        Returns complete responses as chunks for now.

        Args:
            variables: Runtime variable overrides as dict (alternative to kwargs)
            **kwargs: Runtime variable overrides as keyword arguments

        Yields:
            StreamChunk objects with execution progress

        Example:
            >>> async for chunk in workflow.stream_async(topic="AI"):
            ...     if chunk.chunk_type == "step_complete":
            ...         print(f"Step done: {chunk.data}")
            >>> # Or with dict:
            >>> async for chunk in workflow.stream_async({"topic": "AI"}):
            ...     ...
        """
        # Merge variables dict and kwargs
        if variables is None:
            variables = {}
        variables = {**variables, **kwargs}

        async for chunk in self._executor.stream_async(variables):
            yield chunk


__all__ = [
    "BuildError",
    "ChainBuilder",
    "EvaluatorOptimizerBuilder",
    "FluentBuilder",
    "GraphBuilder",
    "OrchestratorWorkersBuilder",
    "ParallelBuilder",
    "RoutingBuilder",
    "SessionManager",
    "Workflow",
    "WorkflowBuilder",
]

#!/usr/bin/env python3
"""Async execution with interactive HITL.

Demonstrates:
- Async API usage with run_interactive_async()
- Running multiple workflows concurrently
- Proper async/await patterns

This example shows how to use the async API for high-performance
applications that need concurrent workflow execution.

Usage:
    python examples/api/03_async_execution.py

Requirements:
    - OpenAI API key set in OPENAI_API_KEY environment variable
    - examples/chain-hitl-approval-demo.yaml workflow file
"""

import asyncio

from strands import Workflow


async def run_workflow(topic: str) -> None:
    """Run workflow asynchronously with given topic.

    Args:
        topic: Research topic for the workflow
    """
    print(f"\nStarting workflow for topic: {topic}")

    # Load workflow
    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")

    # Run asynchronously
    result = await workflow.run_interactive_async(topic=topic)

    # Display results
    print(f"\n{'=' * 60}")
    print(f"Workflow completed: {topic}")
    print(f"{'=' * 60}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Success: {result.success}")
    print(f"Response length: {len(result.last_response)} chars")


async def main():
    """Run multiple workflows asynchronously.

    Note: While workflows can run concurrently in the async runtime,
    interactive HITL prompts are still sequential (one at a time).
    For truly concurrent execution, use non-interactive mode with
    external approval systems.
    """
    print("Async Workflow Execution Example\n")

    # Define topics
    topics = [
        "machine learning in finance",
        "blockchain technology applications",
    ]

    # Run workflows sequentially (interactive HITL requires sequential)
    # For concurrent execution, use workflow.run_async() with external approval
    for topic in topics:
        await run_workflow(topic)

    print("\n✓ All workflows completed")


if __name__ == "__main__":
    asyncio.run(main())

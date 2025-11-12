#!/usr/bin/env python3
"""Async workflow execution with context manager example.

Demonstrates using async context manager for automatic resource cleanup.
Context manager ensures agent cache and HTTP clients are properly closed
even if execution fails or is interrupted.

Example:
    python examples/api/08_async_execution.py
"""

import asyncio
from pathlib import Path

from strands_cli.api import Workflow


async def main():
    """Execute workflow with async context manager for resource cleanup."""
    # Load workflow spec
    spec_path = Path(__file__).parent.parent / "chain-3-step-research-openai.yaml"
    workflow = Workflow.from_file(spec_path)

    print("🚀 Starting async workflow execution with context manager\n")

    # Use async context manager for automatic cleanup
    async with workflow.async_executor() as executor:
        # Execute workflow
        result = await executor.run({"topic": "async Python programming"})

        # Print results
        print(f"✓ Workflow completed: {result.success}")
        print(f"⏱️  Duration: {result.duration_seconds:.2f}s")
        print(f"📝 Pattern: {result.pattern_type}")
        print(f"\n📄 Final Response:\n{result.last_response[:500]}...")

    # Resources automatically cleaned up when context exits
    print("\n✨ Resources automatically cleaned up")


if __name__ == "__main__":
    asyncio.run(main())

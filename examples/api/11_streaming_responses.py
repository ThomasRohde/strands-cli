#!/usr/bin/env python3
"""Streaming workflow execution example.

Demonstrates real-time workflow progress monitoring via streaming API.
Receives execution events as they occur rather than waiting for completion.

Note: Token-by-token streaming not yet implemented in Phase 3.
Returns complete responses as chunks for now.

Example:
    python examples/api/11_streaming_responses.py
"""

import asyncio
from pathlib import Path

from strands_cli.api import Workflow


async def main():
    """Stream workflow execution events in real-time."""
    # Load workflow spec
    spec_path = Path(__file__).parent.parent / "chain-3-step-research-openai.yaml"
    workflow = Workflow.from_file(spec_path)

    print("🚀 Starting streaming workflow execution\n")
    print("📡 Listening for execution events...\n")

    # Stream execution events
    async for chunk in workflow.stream_async(topic="machine learning"):
        if chunk.chunk_type == "step_start":
            step_index = chunk.data.get("step_index", "?")
            print(f"→ Starting step {step_index}...")

        elif chunk.chunk_type == "step_complete":
            step_index = chunk.data.get("step_index", "?")
            response = chunk.data.get("response", "")
            print(f"✓ Step {step_index} completed")
            print(f"  Response: {response[:150]}...")
            print()

        elif chunk.chunk_type == "complete":
            print("✨ Workflow complete!")
            duration = chunk.data.get("duration_seconds", 0)
            print(f"⏱️  Total duration: {duration:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())

"""Example: Building a chain workflow programmatically.

Demonstrates the fluent builder API for creating a 3-step research workflow
without YAML. Equivalent to chain-3-step-research-openai.yaml.

Usage:
    uv run python examples/api/02_chain_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run a research workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("chain-3-step-research")
        .description("Three-step chain demonstrating sequential context passing")
        .runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=8000)
        .agent(
            "researcher",
            "You are a research assistant. Provide clear, concise, and factual responses.\n"
            "Focus on accuracy and cite sources when possible.",
        )
        .chain()
        .step("researcher", "Research the topic: {{topic}}. List 3-5 key points.")
        .step(
            "researcher",
            "Based on this research:\n{{ steps[0].response }}\n\n"
            "Analyze the most important point and explain why it matters.",
            vars={"analysis_depth": "detailed"},
        )
        .step(
            "researcher",
            "Previous research:\n{{ steps[0].response | truncate(200) }}\n\n"
            "Analysis:\n{{ steps[1].response }}\n\n"
            "Write a 2-paragraph summary combining both insights.",
        )
        .artifact(
            "{{topic}}-research.md",
            "# Research Report: {{topic}}\n\n"
            "## Initial Research\n{{ steps[0].response }}\n\n"
            "## Analysis\n{{ steps[1].response }}\n\n"
            "## Summary\n{{ last_response }}",
        )
        .build()
    )

    # Run workflow interactively with topic variable
    print("Starting research workflow...")
    result = await workflow.run_interactive_async(topic="artificial intelligence safety")

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal response:\n{result.last_response}")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

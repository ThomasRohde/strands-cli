"""Example: Building a workflow (DAG) pattern programmatically.

Demonstrates the fluent builder API for creating a multi-task DAG workflow
with parallel execution. Tasks with dependencies execute in topologically
sorted order. Equivalent to workflow-parallel-research-openai.yaml.

Usage:
    uv run python examples/api/03_workflow_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run a DAG workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("workflow-parallel-research")
        .description("DAG workflow demonstrating parallel task execution")
        .runtime("openai", model="gpt-4o-mini", temperature=0.7, max_tokens=12000, max_parallel=2)
        .agent(
            "researcher",
            "You are a research assistant specializing in technology trends.\n"
            "Provide factual, well-structured responses.",
        )
        .workflow()
        # Root task - no dependencies
        .task(
            "overview",
            "researcher",
            "Provide a brief overview (2-3 sentences) of: {{topic}}",
            description="Get high-level overview of the topic",
        )
        # Parallel branch 1 - depends on overview
        .task(
            "technical",
            "researcher",
            (
                "Topic: {{topic}}\n"
                "Overview: {{ tasks.overview.response }}\n\n"
                "Research the technical implementation details. List 3 key technical points."
            ),
            description="Research technical aspects",
            depends_on=["overview"],
        )
        # Parallel branch 2 - depends on overview
        .task(
            "applications",
            "researcher",
            (
                "Topic: {{topic}}\n"
                "Overview: {{ tasks.overview.response }}\n\n"
                "Research practical applications and use cases. List 3 real-world examples."
            ),
            description="Research practical applications",
            depends_on=["overview"],
        )
        # Synthesis - depends on both parallel branches
        .task(
            "synthesis",
            "researcher",
            (
                "Synthesize the following research into a cohesive report:\n\n"
                "Technical Details:\n{{ tasks.technical.response }}\n\n"
                "Applications:\n{{ tasks.applications.response }}\n\n"
                "Write a 3-paragraph report combining technical and practical insights."
            ),
            description="Synthesize findings into final report",
            depends_on=["technical", "applications"],
        )
        .output_dir("./artifacts")
        .artifact(
            "{{topic}}-workflow.md",
            (
                "# {{topic | title}} Research Report\n\n"
                "## Overview\n{{ tasks.overview.response }}\n\n"
                "## Technical Analysis\n{{ tasks.technical.response }}\n\n"
                "## Applications\n{{ tasks.applications.response }}\n\n"
                "## Synthesis\n{{ tasks.synthesis.response }}"
            ),
        )
        .build()
    )

    # Run workflow interactively with topic variable
    print("Starting DAG workflow with parallel execution...")
    result = await workflow.run_interactive_async(topic="edge computing")

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal response:\n{result.last_response}")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

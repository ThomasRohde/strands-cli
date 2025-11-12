"""Example: Building a routing pattern workflow programmatically.

Demonstrates the fluent builder API for intelligent task routing with
specialized agents. Router classifies tasks and routes to appropriate
specialist. Equivalent to routing-task-classification-openai.yaml.

Usage:
    uv run python examples/api/06_routing_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run a routing workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("task-classifier")
        .description("Classify tasks and route to specialized agents")
        .runtime("openai", model="gpt-4o-mini", temperature=0.2, max_tokens=4000)
        .agent(
            "task_router",
            (
                "You are an intelligent task classifier. Analyze the given task and determine "
                "which type of agent should handle it.\n\n"
                "Available routes:\n"
                "- coding: Programming tasks, code reviews, algorithm implementations, debugging\n"
                "- research: Information gathering, analysis, summaries, comparisons\n"
                "- writing: Content creation, documentation, creative writing, editing\n\n"
                'Respond with ONLY valid JSON:\n{"route": "<route_name>"}\n\n'
                "Base your decision on the primary nature of the task."
            ),
        )
        .agent(
            "coder",
            (
                "You are an expert software engineer. Implement clean, well-documented code "
                "with examples and explanations. Focus on best practices and clarity."
            ),
        )
        .agent(
            "researcher",
            (
                "You are a thorough researcher. Gather information systematically, "
                "analyze multiple perspectives, and provide well-sourced insights."
            ),
        )
        .agent(
            "writer",
            (
                "You are a skilled technical writer. Create clear, engaging content that "
                "is well-structured and accessible to your target audience."
            ),
        )
        .routing()
        # Configure router
        .router(
            "task_router",
            (
                "Task: {{ task }}\n\n"
                "Classify this task as: coding, research, or writing"
            ),
            max_retries=3,
        )
        # Define coding route (2 steps: code + documentation)
        .route("coding")
        .step(
            "coder",
            (
                "Task: {{ task }}\n\n"
                "Provide a complete code implementation with explanations and examples.\n"
                "Selected route: {{ router.chosen_route }}"
            ),
        )
        .step(
            "writer",
            (
                "Take this code and create user-friendly documentation:\n\n"
                "{{ steps[0].response }}"
            ),
        )
        .done()
        # Define research route (2 steps: research + article)
        .route("research")
        .step(
            "researcher",
            (
                "Research topic: {{ task }}\n\n"
                "Conduct thorough research and provide comprehensive findings.\n"
                "Selected route: {{ router.chosen_route }}"
            ),
        )
        .step(
            "writer",
            (
                "Transform these research findings into a well-organized article:\n\n"
                "{{ steps[0].response }}"
            ),
        )
        .done()
        # Define writing route (1 step: direct content creation)
        .route("writing")
        .step(
            "writer",
            (
                "Writing task: {{ task }}\n\n"
                "Create high-quality content that addresses the task requirements.\n"
                "Selected route: {{ router.chosen_route }}"
            ),
        )
        .done()
        .artifact("./task-output.md", "{{ last_response }}")
        .build()
    )

    # Run workflow interactively with task variable
    print("Starting task classification routing workflow...")
    result = await workflow.run_interactive_async(task="Explain how binary search works")

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal output:\n{result.last_response[:500]}...")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

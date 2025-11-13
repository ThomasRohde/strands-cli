"""Example: Building a parallel pattern workflow programmatically.

Demonstrates the fluent builder API for creating parallel branch execution
with reduce step for synthesis. Equivalent to parallel-with-reduce.yaml.

Usage:
    uv run python examples/api/04_parallel_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run a parallel workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("parallel-with-reduce")
        .description("Parallel execution with reduce step for aggregation")
        .runtime("openai", model="gpt-4o-mini", max_tokens=8000)
        .agent(
            "researcher",
            (
                "You are a domain expert. Provide detailed, well-researched information\n"
                "about the requested topic."
            ),
        )
        .agent(
            "synthesizer",
            (
                "You are a synthesis expert. Given multiple research perspectives,\n"
                "create a cohesive, integrated analysis that highlights key insights,\n"
                "commonalities, and unique contributions from each source."
            ),
        )
        .parallel()
        # Branch 1: Academic perspective
        .branch("academic_perspective")
        .step("researcher", "Research {{ topic }} from an academic/scientific perspective")
        .done()
        # Branch 2: Industry perspective
        .branch("industry_perspective")
        .step("researcher", "Research {{ topic }} from an industry/practical perspective")
        .done()
        # Branch 3: Regulatory perspective
        .branch("regulatory_perspective")
        .step("researcher", "Research {{ topic }} from a regulatory/compliance perspective")
        .done()
        # Reduce step to synthesize all branches
        .reduce(
            "synthesizer",
            (
                "Synthesize these three research perspectives on {{ topic }}:\n\n"
                "Academic: {{ branches.academic_perspective.response }}\n\n"
                "Industry: {{ branches.industry_perspective.response }}\n\n"
                "Regulatory: {{ branches.regulatory_perspective.response }}"
            ),
        )
        .output_dir("./artifacts")
        .artifact("./parallel-synthesis.md", "{{ last_response }}")
        .build()
    )

    # Run workflow interactively with topic variable
    print("Starting parallel workflow with reduce step...")
    result = await workflow.run_interactive_async(
        topic="blockchain technology in financial services"
    )

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal synthesis:\n{result.last_response[:500]}...")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

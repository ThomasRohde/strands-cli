"""Example: Building an evaluator-optimizer pattern workflow programmatically.

Demonstrates the fluent builder API for creating iterative refinement loops
with producer-evaluator feedback. Equivalent to evaluator-optimizer-writing-openai.yaml.

Usage:
    uv run python examples/api/07_evaluator_optimizer_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run an evaluator-optimizer workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("evaluator-optimizer-writing")
        .description("Iterative content refinement with evaluator feedback")
        .runtime("openai", model="gpt-5-nano")
        .agent(
            "writer",
            (
                "You are an expert content writer. Create well-structured, engaging content.\n\n"
                "Write a professional blog post about artificial intelligence for technical professionals.\n\n"
                "Focus on:\n"
                "- Clear, concise writing\n"
                "- Logical flow and structure\n"
                "- Accurate information\n"
                "- Engaging introduction and conclusion"
            ),
        )
        .agent(
            "critic",
            (
                "You are a critical editor who evaluates content quality with high standards.\n\n"
                "Evaluate the following draft objectively and return your assessment as JSON.\n"
                "Be honest and thorough - identify real issues even in otherwise good content.\n\n"
                "Required JSON format:\n"
                "{\n"
                '  "score": <0-100>,\n'
                '  "issues": ["issue1", "issue2", ...],\n'
                '  "fixes": ["fix1", "fix2", ...]\n'
                "}\n\n"
                "Score 0-100 based on overall quality:\n"
                "- Consider clarity, readability, structure, accuracy, depth, grammar, style, engagement\n"
                "- Be critical: most first drafts have room for improvement\n"
                "- Only score above 85 if truly publication-ready with minimal issues"
            ),
        )
        .evaluator_optimizer()
        # Configure producer
        .producer("writer")
        # Configure evaluator
        .evaluator(
            "critic",
            (
                "Evaluate this draft about artificial intelligence:\n\n"
                "=== DRAFT ===\n"
                "{{ draft }}\n"
                "=== END DRAFT ===\n\n"
                "Return your evaluation as JSON with score, issues, and fixes."
            ),
        )
        # Configure acceptance criteria
        .accept(min_score=85, max_iterations=3)
        # Configure custom revision prompt
        .revise_prompt(

                "Your previous draft scored {{ evaluation.score }}/100.\n\n"
                "Issues identified:\n"
                "{% for issue in evaluation.issues %}\n"
                "- {{ issue }}\n"
                "{% endfor %}\n\n"
                "Suggested fixes:\n"
                "{% for fix in evaluation.fixes %}\n"
                "- {{ fix }}\n"
                "{% endfor %}\n\n"
                "Please revise the draft to address these issues. "
                "Maintain the topic (artificial intelligence) and professional blog post style.\n"
                "Focus on improving the areas mentioned in the feedback."

        )
        .artifact("./refined-content.md", "{{ last_response }}")
        .build()
    )

    # Run workflow interactively
    print("Starting evaluator-optimizer workflow...")
    print("Writer will iteratively refine content based on critic's feedback.\n")

    result = await workflow.run_interactive_async()

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal refined content:\n{result.last_response[:500]}...")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

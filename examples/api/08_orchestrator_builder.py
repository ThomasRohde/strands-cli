"""Example: Building an orchestrator-workers pattern workflow programmatically.

Demonstrates the fluent builder API for task decomposition with parallel
worker execution and synthesis. Equivalent to orchestrator-research-swarm-openai.yaml.

Usage:
    uv run python examples/api/08_orchestrator_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run an orchestrator-workers workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("orchestrator-research-swarm")
        .description("Orchestrator delegates research tasks to worker swarm, then synthesizes")
        .runtime("openai", model="gpt-5-nano")
        .agent(
            "orchestrator",
            (
                "You are a research orchestrator. Your job is to break down complex research "
                "topics into specific subtasks for worker agents.\n\n"
                "Break down the research on \"{{ topic }}\" into {{ num_perspectives }} distinct subtasks.\n"
                "Each subtask should focus on a different aspect or perspective.\n\n"
                "Respond with ONLY a JSON array of tasks. Format:\n"
                "[\n"
                '  {"task": "Research aspect 1"},\n'
                '  {"task": "Research aspect 2"},\n'
                '  {"task": "Research aspect 3"}\n'
                "]"
            ),
        )
        .agent(
            "researcher",
            (
                "You are a research specialist. You conduct thorough research on assigned "
                "topics and provide detailed findings.\n"
                "Be comprehensive, cite key points, and provide actionable insights."
            ),
            tools=["http_executors"],
        )
        .agent(
            "report_writer",
            (
                "You are a technical writer creating executive research reports.\n\n"
                "Available worker research:\n"
                "{% for worker in workers %}\n"
                "Worker {{ loop.index0 }}: {{ worker.response }}\n"
                "{% endfor %}\n\n"
                "Create a comprehensive executive report that:\n"
                "1. Starts with a 2-3 sentence executive summary\n"
                "2. Identifies common themes across all research\n"
                "3. Highlights unique insights from each worker\n"
                "4. Presents key findings in bullet points\n"
                "5. Includes implications and recommendations\n"
                "6. Points out any contradictions or gaps\n"
                "Aim for 400-600 words total."
            ),
        )
        .orchestrator_workers()
        # Configure orchestrator
        .orchestrator("orchestrator", max_workers=3, max_rounds=1)
        # Configure worker template
        .worker_template("researcher", tools=["http_executors"])
        # Configure final writeup/report step
        .reduce_step("report_writer")
        .output_dir("./artifacts")
        .artifact("./research-report.md", "{{ last_response }}")
        .build()
    )

    # Run workflow interactively
    print("Starting orchestrator-workers workflow...")
    print("Orchestrator will decompose research task into parallel subtasks.\n")

    result = await workflow.run_interactive_async(
        topic="impact of AI on software development",
        num_perspectives="3",
    )

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal research report:\n{result.last_response[:500]}...")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

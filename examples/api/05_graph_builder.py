"""Example: Building a graph pattern workflow (state machine) programmatically.

Demonstrates the fluent builder API for creating a state machine with
conditional transitions. Customer support ticket routing example.
Equivalent to graph-state-machine-openai.yaml.

Usage:
    uv run python examples/api/05_graph_builder.py
"""

import asyncio

from strands_cli.api import FluentBuilder


async def main() -> None:
    """Build and run a graph workflow using the builder API."""
    # Build workflow using fluent API
    workflow = (
        FluentBuilder("customer-support-router")
        .description("Customer support ticket routing using a state machine")
        .runtime("openai", model="gpt-4o-mini", max_tokens=4000)
        .agent(
            "intake",
            (
                "You are a customer support intake specialist. "
                "Analyze the customer's request and classify it.\n\n"
                "Request: {{ input_request }}\n\n"
                "Provide:\n"
                "1. Priority (low/medium/high)\n"
                "2. Category (technical/billing/general)\n"
                "3. Brief summary (1 sentence)\n\n"
                "Format your response exactly as:\n"
                "Priority: <priority>\n"
                "Category: <category>\n"
                "Summary: <summary>"
            ),
        )
        .agent(
            "technical_support",
            (
                "You are a technical support engineer. Address this technical issue:\n\n"
                "{{ nodes.intake.response }}\n\n"
                "Provide step-by-step troubleshooting guidance."
            ),
        )
        .agent(
            "billing_support",
            (
                "You are a billing specialist. Handle this billing inquiry:\n\n"
                "{{ nodes.intake.response }}\n\n"
                "Explain the billing details clearly and suggest next steps."
            ),
        )
        .agent(
            "general_support",
            (
                "You are a customer service representative. Handle this general inquiry:\n\n"
                "{{ nodes.intake.response }}\n\n"
                "Provide helpful information and guide the customer appropriately."
            ),
        )
        .agent(
            "escalation",
            (
                "You are a senior support manager. This high-priority case requires escalation:\n\n"
                "Original classification: {{ nodes.intake.response }}\n"
                "Specialist response: {{ last_response }}\n\n"
                "Provide executive-level resolution and follow-up plan."
            ),
        )
        .graph()
        # Define nodes
        .node("intake", "intake", "{{ input_request }}")
        .node("technical", "technical_support")
        .node("billing", "billing_support")
        .node("general", "general_support")
        .node("escalate", "escalation")
        # Define conditional edges from intake
        .conditional_edge(
            "intake",
            [
                ("{{ 'technical' in nodes.intake.response.lower() }}", "technical"),
                ("{{ 'billing' in nodes.intake.response.lower() }}", "billing"),
                ("else", "general"),
            ],
        )
        # Route to escalation if high priority
        .conditional_edge(
            "technical",
            [("{{ 'high' in nodes.intake.response.lower() }}", "escalate")],
        )
        .conditional_edge(
            "billing",
            [("{{ 'high' in nodes.intake.response.lower() }}", "escalate")],
        )
        .conditional_edge(
            "general",
            [("{{ 'high' in nodes.intake.response.lower() }}", "escalate")],
        )
        .max_iterations(5)
        .artifact(
            "./support_transcript.md",
            (
                "# Customer Support Transcript\n\n"
                "**Ticket**: {{ name }}\n\n"
                "## Customer Request\n{{ input_request }}\n\n"
                "## Intake Classification\n{{ nodes.intake.response }}\n\n"
                "## Final Resolution\n{{ last_response }}"
            ),
        )
        .build()
    )

    # Run workflow interactively
    print("Starting customer support routing workflow...")
    result = await workflow.run_interactive_async(
        input_request=(
            "My API calls are failing with 500 errors and this is "
            "blocking our production deployment!"
        )
    )

    if result.success:
        print("\n✓ Workflow completed successfully!")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Artifacts written: {result.artifacts_written}")
        print(f"\nFinal resolution:\n{result.last_response[:500]}...")
    else:
        print(f"\n✗ Workflow failed: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

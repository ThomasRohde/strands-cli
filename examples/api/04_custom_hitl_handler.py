#!/usr/bin/env python3
"""Custom HITL handler example.

Demonstrates:
- Creating custom HITL handler function
- Accessing HITL state (prompt, context, defaults)
- Automated approval based on custom logic
- Using custom handler with run_interactive()

This example shows how to replace the default terminal prompt
with custom logic, useful for:
- Automated testing
- Custom UI integration
- Business rule-based approvals
- Logging/auditing approval decisions

Usage:
    python examples/api/04_custom_hitl_handler.py

Requirements:
    - OpenAI API key set in OPENAI_API_KEY environment variable
    - examples/chain-hitl-approval-demo.yaml workflow file
"""

import asyncio

from strands import Workflow

from strands_cli.types import HITLState


def auto_approve_handler(hitl_state: HITLState) -> str:
    """Custom HITL handler that auto-approves with logging.

    This handler demonstrates:
    - Accessing HITL state information
    - Custom approval logic (auto-approve)
    - Logging approval decisions

    Args:
        hitl_state: HITL pause state with prompt and context

    Returns:
        Approval response string
    """
    print("\n" + "=" * 60)
    print("CUSTOM HITL HANDLER - AUTO-APPROVE MODE")
    print("=" * 60)
    print(f"Prompt: {hitl_state.prompt}")

    if hitl_state.context_display:
        # Show truncated context
        context = hitl_state.context_display[:200]
        if len(hitl_state.context_display) > 200:
            context += "..."
        print(f"Context: {context}")

    # Auto-approve with custom response
    response = "APPROVED - Automated approval via custom handler"
    print(f"\n✓ Decision: {response}")
    print("=" * 60 + "\n")

    return response


def conditional_approval_handler(hitl_state: HITLState) -> str:
    """Custom HITL handler with conditional logic.

    This handler demonstrates more complex approval logic:
    - Check context for specific keywords
    - Apply business rules
    - Make automated decisions

    Args:
        hitl_state: HITL pause state with prompt and context

    Returns:
        Approval or rejection response
    """
    print("\n" + "=" * 60)
    print("CONDITIONAL APPROVAL HANDLER")
    print("=" * 60)
    print(f"Prompt: {hitl_state.prompt}")

    # Example: Check if context contains certain keywords
    context = hitl_state.context_display or ""

    # Business rule: Approve if context mentions "research" or "analysis"
    if "research" in context.lower() or "analysis" in context.lower():
        response = "APPROVED - Research findings look comprehensive"
        print("✓ Auto-approved (contains research/analysis)")
    else:
        response = "NEEDS REVISION - Please add more research depth"
        print("⚠ Needs revision (missing research keywords)")

    print(f"Decision: {response}")
    print("=" * 60 + "\n")

    return response


async def example_auto_approve():
    """Example using auto-approve handler."""
    print("Example 1: Auto-Approve Handler\n")

    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")

    result = await workflow.run_interactive_async(
        topic="renewable energy technologies",
        hitl_handler=auto_approve_handler,
    )

    print("\n✓ Workflow completed (auto-approved)")
    print(f"Duration: {result.duration_seconds:.2f}s")


async def example_conditional_approval():
    """Example using conditional approval handler."""
    print("\n\nExample 2: Conditional Approval Handler\n")

    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")

    result = await workflow.run_interactive_async(
        topic="cloud computing security",
        hitl_handler=conditional_approval_handler,
    )

    print("\n✓ Workflow completed (conditional logic)")
    print(f"Duration: {result.duration_seconds:.2f}s")


async def main():
    """Run examples with custom HITL handlers."""
    print("Custom HITL Handler Examples\n")
    print("Demonstrates custom approval logic instead of terminal prompts\n")

    # Run examples
    await example_auto_approve()
    await example_conditional_approval()

    print("\n" + "=" * 60)
    print("KEY TAKEAWAYS")
    print("=" * 60)
    print("✓ Custom handlers can automate approvals")
    print("✓ Access HITL state (prompt, context, defaults)")
    print("✓ Implement business rules and conditional logic")
    print("✓ Useful for testing, custom UIs, and automation")


if __name__ == "__main__":
    asyncio.run(main())

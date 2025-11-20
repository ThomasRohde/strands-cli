#!/usr/bin/env python3
"""
Test harness for customer support intake workflow using atomic agents.

This demonstrates:
1. Loading and running a workflow that composes atomic agents
2. Using the Python API instead of CLI
3. Validating outputs from atomic agents with contracts
4. Programmatic artifact inspection

Usage:
    uv run python examples/test_customer_support_intake.py
"""

import asyncio
import json
from pathlib import Path

from strands_cli.api import Workflow


async def test_customer_support_intake():
    """Test the customer support intake workflow with atomic agents."""
    
    print("=" * 70)
    print("Customer Support Intake - Atomic Agents Test Harness")
    print("=" * 70)
    print()
    
    # Test case 1: Urgent refund request
    print("Test Case 1: Urgent Refund Request")
    print("-" * 70)
    
    spec_path = Path(__file__).parent / "customer-support-intake-composite-openai.yaml"

    # Create workflow from YAML spec
    workflow = Workflow.from_file(
        spec_path,
        subject="URGENT: Refund needed for defective product",
        body="I bought a laptop on November 1st (Order #98765) and it won't turn on. "
             "This is for my daughter's college finals next week. I need immediate "
             "replacement or full refund. Very disappointed!",
    )
    
    # Run the workflow
    print(f"\nRunning workflow: {workflow.spec.name}")
    print(f"Description: {workflow.spec.description}")
    print()
    
    result = await workflow.run_async()

    # Display results
    print("\n[OK] Workflow completed successfully!")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print()

    # Extract task results from execution context
    task_results = result.execution_context.get("task_results", {})
    if task_results:
        print("Task Results:")
        print("-" * 70)

        # Summarization result
        if "summarize" in task_results:
            summary_response = task_results["summarize"].response
            print("\n[SUMMARIZE TASK]")
            print(summary_response)

            # Try to parse if JSON
            try:
                summary_data = json.loads(summary_response)
                print("\nParsed Summary:")
                if "summary" in summary_data:
                    print(f"  Summary: {summary_data['summary']}")
                if "bullets" in summary_data:
                    print("  Key Points:")
                    for i, bullet in enumerate(summary_data['bullets'], 1):
                        print(f"    {i}. {bullet}")
            except json.JSONDecodeError:
                pass  # Plain text response

        # Classification result
        if "classify" in task_results:
            classify_response = task_results["classify"].response
            print("\n[CLASSIFY TASK]")
            print(classify_response)

            # Parse priority classification
            try:
                priority_data = json.loads(classify_response)
                print("\nParsed Classification:")
                print(f"  Priority: {priority_data.get('priority', 'N/A').upper()}")
                print(f"  Rationale: {priority_data.get('rationale', 'N/A')}")
            except json.JSONDecodeError:
                pass  # Plain text response

    print()
    print("=" * 70)

    # Test case 2: Low priority question
    print("\nTest Case 2: Low Priority Question")
    print("-" * 70)
    
    workflow2 = Workflow.from_file(
        spec_path,
        subject="Question about product specifications",
        body="Hi, I'm interested in buying your wireless headphones. "
             "Can you tell me the Bluetooth version and battery life? Thanks!",
    )

    print(f"\nRunning workflow: {workflow2.spec.name}")
    result2 = await workflow2.run_async()

    print("\n[OK] Workflow completed successfully!")
    print(f"Duration: {result2.duration_seconds:.2f}s")

    # Display classification for second test
    task_results2 = result2.execution_context.get("task_results", {})
    if task_results2 and "classify" in task_results2:
        classify_response = task_results2["classify"].response
        try:
            priority_data = json.loads(classify_response)
            print(f"\nPriority: {priority_data.get('priority', 'N/A').upper()}")
            print(f"Rationale: {priority_data.get('rationale', 'N/A')}")
        except json.JSONDecodeError:
            print(f"\nClassification: {classify_response}")

    print()
    print("=" * 70)
    print("All tests completed!")
    print()

    # Check artifact generation
    artifact_path = Path("artifacts/support-intake.md")
    if artifact_path.exists():
        print(f"\n[FILE] Artifact generated: {artifact_path}")
        print("Contents:")
        print("-" * 70)
        print(artifact_path.read_text())

    return result, result2


async def test_atomic_agents_individually():
    """Test each atomic agent in isolation."""

    print("\n" + "=" * 70)
    print("Testing Atomic Agents Individually")
    print("=" * 70)
    
    # Test 1: Summarize agent
    print("\n1. Testing summarize_customer_email atomic agent")
    print("-" * 70)

    summarize_spec = Path(__file__).parent.parent / "agents/atomic/summarize_customer_email/summarize_customer_email.yaml"

    summarize_workflow = Workflow.from_file(
        summarize_spec,
        subject="Shipping delay for Order #12345",
        body="I ordered a laptop on Dec 1st and was promised delivery by Dec 10th. "
             "It's now Dec 15th and tracking shows 'processing'. Need it for client "
             "presentation on Dec 18th.",
    )

    summarize_result = await summarize_workflow.run_async()
    print(f"\n[OK] Summary generated (duration: {summarize_result.duration_seconds:.2f}s)")
    print("\nResponse:")
    print(summarize_result.last_response)

    # Test 2: Classify agent
    print("\n\n2. Testing classify_from_summary atomic agent")
    print("-" * 70)

    classify_spec = Path(__file__).parent.parent / "agents/atomic/classify_from_summary/classify_from_summary.yaml"

    # Use the summary from previous test
    classify_workflow = Workflow.from_file(
        classify_spec,
        summary=summarize_result.last_response,
    )

    classify_result = await classify_workflow.run_async()
    print(f"\n[OK] Classification completed (duration: {classify_result.duration_seconds:.2f}s)")
    print("\nResponse:")
    print(classify_result.last_response)

    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    print("\n[TEST] Strands CLI - Atomic Agents Test Suite")
    print("Testing customer support intake workflow\n")

    # Run composite workflow tests
    asyncio.run(test_customer_support_intake())

    # Run individual atomic agent tests
    asyncio.run(test_atomic_agents_individually())

    print("\n[OK] All tests passed!")
    print("\nKey Takeaways:")
    print("  * Atomic agents can be tested independently")
    print("  * Atomic agents compose into workflows")
    print("  * Input/output schemas validate contracts")
    print("  * Python API enables programmatic testing")
    print()


if __name__ == "__main__":
    main()


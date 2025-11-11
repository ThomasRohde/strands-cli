#!/usr/bin/env python3
"""Simple chain workflow with interactive HITL.

Demonstrates:
- Basic Workflow API usage
- Chain pattern with single HITL approval step
- Variable substitution

This is a minimal example showing the essential API:
1. Load workflow from file
2. Run with interactive HITL
3. Access results

Usage:
    python examples/api/02_simple_chain.py

Requirements:
    - OpenAI API key set in OPENAI_API_KEY environment variable
    - examples/chain-hitl-approval-demo.yaml workflow file
"""

from strands import Workflow


def main():
    """Run simple chain workflow with HITL approval."""
    print("Simple Chain Workflow with HITL\n")

    # Load workflow
    workflow = Workflow.from_file("examples/chain-hitl-approval-demo.yaml")

    # Run interactively with custom topic
    print("Running workflow...")
    print("You will be asked to approve the research findings.\n")

    result = workflow.run_interactive(topic="artificial intelligence in healthcare")

    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if result.success:
        print("✓ Workflow completed successfully")
        print(f"⏱  Duration: {result.duration_seconds:.2f}s")
        print(f"\nFinal output:\n{result.last_response}")
    else:
        print("✗ Workflow failed")
        print(f"Exit code: {result.exit_code}")


if __name__ == "__main__":
    main()

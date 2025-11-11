#!/usr/bin/env python3
"""Interactive HITL research workflow example.

Demonstrates:
- Loading workflow from YAML
- Running with interactive HITL prompts
- Accessing execution results

This example uses the chain-hitl-business-proposal workflow which:
1. Researches a topic
2. Pauses for human approval (HITL)
3. Generates final business proposal based on approval

Usage:
    python examples/api/01_interactive_hitl.py

Requirements:
    - OpenAI API key set in OPENAI_API_KEY environment variable
    - examples/chain-hitl-business-proposal-openai.yaml workflow file
"""

from strands_cli import Workflow


def main():
    """Run interactive HITL workflow."""
    # Load workflow with HITL steps
    workflow = Workflow.from_file("examples/chain-hitl-business-proposal-openai.yaml")

    # Run interactively - prompts user in terminal for HITL responses
    print("Starting interactive workflow...")
    print("You will be prompted for input at HITL steps.\n")

    result = workflow.run_interactive(topic="quantum computing applications in cryptography")

    # Access results
    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETED")
    print("=" * 60)
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Success: {result.success}")
    print(f"\nFinal Response:\n{result.last_response}")

    if result.artifacts_written:
        print("\nArtifacts written:")
        for artifact in result.artifacts_written:
            print(f"  - {artifact}")


if __name__ == "__main__":
    main()

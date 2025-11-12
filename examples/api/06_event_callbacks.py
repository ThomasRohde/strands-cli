#!/usr/bin/env python3
"""Example: Event-driven workflow with callbacks.

Demonstrates how to use event callbacks to monitor workflow progress
and react to specific events during execution.
"""

from strands_cli.api import Workflow

# Load workflow specification
workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")


# Define event callbacks
@workflow.on("workflow_start")
def on_workflow_start(event):
    """Called when workflow starts."""
    print(f"\n🚀 Starting workflow: {event.spec_name}")
    print(f"   Pattern: {event.pattern_type}")
    print(f"   Session: {event.session_id}\n")


@workflow.on("step_start")
def on_step_start(event):
    """Called when each step starts."""
    step_index = event.data.get("step_index", "?")
    print(f"→ Starting step {step_index}...")


@workflow.on("step_complete")
def on_step_complete(event):
    """Called when each step completes."""
    step_index = event.data.get("step_index", "?")
    response = event.data.get("response", "")
    print(f"✓ Step {step_index} completed")
    print(f"  Response preview: {response[:100]}...\n")


@workflow.on("workflow_complete")
def on_workflow_complete(event):
    """Called when workflow completes."""
    duration = event.data.get("duration_seconds", 0)
    print(f"\n✅ Workflow completed in {duration:.2f}s")


@workflow.on("error")
def on_error(event):
    """Called when an error occurs."""
    error_msg = event.data.get("error", "Unknown error")
    print(f"\n❌ Error occurred: {error_msg}")


# Execute workflow with event monitoring
if __name__ == "__main__":
    print("=" * 60)
    print("Event-Driven Workflow Example")
    print("=" * 60)

    # Run workflow
    result = workflow.run_interactive(topic="artificial intelligence")

    print("\n" + "=" * 60)
    print("Final Result")
    print("=" * 60)
    if result.success:
        print(f"\n{result.last_response}\n")
    else:
        print(f"\nWorkflow failed: {result.error}\n")

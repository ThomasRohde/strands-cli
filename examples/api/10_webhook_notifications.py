#!/usr/bin/env python3
"""Webhook notification example.

This example demonstrates how to use webhook event handlers to send
workflow events to external services. It shows:
- Using the GenericWebhookHandler for custom webhooks
- Subscribing to specific workflow events
- Sending event notifications to external URLs

Requirements:
    - Webhook endpoint (e.g., webhook.site, requestbin.com, or your own server)
    - OpenAI API key in environment

Usage:
    # Set your webhook URL
    export WEBHOOK_URL="https://webhook.site/your-unique-id"

    # Run the example
    python examples/api/10_webhook_notifications.py

Example webhook payload:
    {
        "event_type": "workflow_complete",
        "timestamp": "2024-01-15T10:30:45.123456",
        "session_id": "abc123",
        "spec_name": "Research Chain",
        "pattern_type": "chain",
        "data": {
            "success": true,
            "duration": 45.2,
            "last_response": "..."
        }
    }
"""

import asyncio
import os
from pathlib import Path

from strands_cli.api import Workflow
from strands_cli.integrations.webhook_handler import GenericWebhookHandler


async def main():
    """Run webhook notification example."""
    # Get webhook URL from environment
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        print("Error: WEBHOOK_URL environment variable not set")
        print()
        print("Get a free webhook URL from:")
        print("  - https://webhook.site")
        print("  - https://requestbin.com")
        print()
        print("Then set it with:")
        print('  export WEBHOOK_URL="https://webhook.site/your-unique-id"')
        return

    # Load workflow
    examples_dir = Path(__file__).parent.parent
    workflow_file = examples_dir / "chain-3-step-research-openai.yaml"

    if not workflow_file.exists():
        print(f"Error: Workflow file not found: {workflow_file}")
        return

    workflow = Workflow.from_file(str(workflow_file))

    # Configure webhook handler
    webhook = GenericWebhookHandler(
        url=webhook_url,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Strands-CLI-Webhook/1.0",
            # Add authentication if needed:
            # "Authorization": "Bearer YOUR_TOKEN",
        },
    )

    print("=" * 60)
    print("Webhook Notification Example")
    print("=" * 60)
    print(f"Webhook URL: {webhook_url}")
    print(f"Workflow: {workflow.spec.name}")
    print("=" * 60)
    print()

    # Subscribe webhook to workflow events
    # Store task references to avoid RUF006 warning
    tasks: list[asyncio.Task] = []

    @workflow.on("workflow_start")
    def on_start(event):
        task = asyncio.create_task(webhook.send(event))
        tasks.append(task)
        print(f"✓ Sent {event.event_type} event to webhook")

    @workflow.on("step_complete")
    def on_step(event):
        task = asyncio.create_task(webhook.send(event))
        tasks.append(task)
        print(f"✓ Sent {event.event_type} event to webhook")

    @workflow.on("workflow_complete")
    def on_complete(event):
        task = asyncio.create_task(webhook.send(event))
        tasks.append(task)
        print(f"✓ Sent {event.event_type} event to webhook")

    # Execute workflow with event tracking
    print("Executing workflow with webhook notifications...")
    print()

    result = await workflow.run_async(topic="AI agents")

    print()
    print("=" * 60)
    print(f"Workflow {'completed' if result.success else 'failed'}")
    print("=" * 60)
    print("Check your webhook URL to see the received events!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

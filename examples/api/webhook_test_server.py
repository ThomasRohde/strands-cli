#!/usr/bin/env python3
"""Test webhook server for receiving workflow notifications.

This is a simple webhook server that receives and logs webhook notifications
from the Strands CLI workflow webhook handler.

Requirements:
    pip install fastapi uvicorn

Usage:
    # Start the webhook server
    python examples/api/webhook_test_server.py

    # In another terminal, set the webhook URL and run the webhook example
    export WEBHOOK_URL="http://localhost:8000/webhook"
    python examples/api/10_webhook_notifications.py

Features:
    - Receives POST requests to /webhook endpoint
    - Logs all incoming webhook events with timestamps
    - Displays event type, session ID, and payload
    - Returns success response to sender
    - Simple web UI to view received webhooks at http://localhost:8000
"""

from datetime import datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# Store received webhooks in memory (for demo purposes)
received_webhooks: list[dict[str, Any]] = []

app = FastAPI(title="Webhook Test Server", version="1.0.0")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Receive and log webhook notifications."""
    # Get the payload
    payload = await request.json()

    # Add server timestamp
    webhook_record = {
        "received_at": datetime.now().isoformat(),
        "payload": payload,
    }

    # Store the webhook
    received_webhooks.append(webhook_record)

    # Log to console
    print("\n" + "=" * 80)
    print(f"📨 Webhook Received at {webhook_record['received_at']}")
    print("=" * 80)
    print(f"Event Type: {payload.get('event_type', 'unknown')}")
    print(f"Session ID: {payload.get('session_id', 'N/A')}")
    print(f"Spec Name: {payload.get('spec_name', 'N/A')}")
    print(f"Pattern: {payload.get('pattern_type', 'N/A')}")
    print(f"Timestamp: {payload.get('timestamp', 'N/A')}")
    print("-" * 80)
    print("Data:")
    for key, value in payload.get("data", {}).items():
        # Truncate long values
        if isinstance(value, str) and len(value) > 200:
            value = value[:200] + "..."
        print(f"  {key}: {value}")
    print("=" * 80)

    # Return success response
    return {
        "status": "received",
        "timestamp": webhook_record["received_at"],
        "event_type": payload.get("event_type"),
    }


@app.get("/", response_class=HTMLResponse)
async def view_webhooks():
    """Display received webhooks in a web page."""
    total_count = len(received_webhooks)

    # Build webhook HTML content
    webhooks_html = ""

    if not received_webhooks:
        webhooks_html = """
        <div class="no-webhooks">
            <h2>No webhooks received yet</h2>
            <p>Waiting for incoming webhook notifications...</p>
            <p>Use this URL in your webhook configuration:</p>
            <pre>export WEBHOOK_URL="http://localhost:8000/webhook"</pre>
        </div>
        """
    else:
        # Display webhooks in reverse order (newest first)
        for webhook in reversed(received_webhooks):
            payload = webhook["payload"]
            event_type = payload.get("event_type", "unknown")
            received_at = webhook["received_at"]
            session_id = payload.get("session_id", "N/A")
            spec_name = payload.get("spec_name", "N/A")
            pattern_type = payload.get("pattern_type", "N/A")
            timestamp = payload.get("timestamp", "N/A")
            data = payload.get("data", {})

            data_items_html = ""
            for key, value in data.items():
                # Truncate long values for display
                if isinstance(value, str) and len(value) > 500:
                    value = value[:500] + "..."

                data_items_html += f"""
                    <div class="data-item">
                        <span class="data-key">{key}:</span>
                        <span class="data-value">{value}</span>
                    </div>
                """

            webhooks_html += f"""
            <div class="webhook">
                <div class="webhook-header">
                    <div class="event-type">📨 {event_type}</div>
                    <div class="timestamp">Received: {received_at}</div>
                </div>

                <div class="meta">
                    <div class="meta-item">
                        <div class="meta-label">Session ID</div>
                        <div class="meta-value">{session_id}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Spec Name</div>
                        <div class="meta-value">{spec_name}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Pattern</div>
                        <div class="meta-value">{pattern_type}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Event Timestamp</div>
                        <div class="meta-value">{timestamp}</div>
                    </div>
                </div>

                <div class="data">
                    <div class="data-title">Event Data:</div>
                    {data_items_html}
                </div>
            </div>
            """

    # Return complete HTML with embedded webhooks
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Webhook Test Server</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 30px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .header h1 {{
                margin: 0 0 10px 0;
            }}
            .header p {{
                margin: 5px 0;
                opacity: 0.9;
            }}
            .stats {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .webhook {{
                background: white;
                border-left: 4px solid #667eea;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .webhook-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f0f0f0;
            }}
            .event-type {{
                font-size: 1.2em;
                font-weight: bold;
                color: #667eea;
            }}
            .timestamp {{
                color: #666;
                font-size: 0.9em;
            }}
            .meta {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 15px;
            }}
            .meta-item {{
                background: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
            }}
            .meta-label {{
                font-weight: bold;
                color: #495057;
                font-size: 0.85em;
                text-transform: uppercase;
                margin-bottom: 5px;
            }}
            .meta-value {{
                color: #212529;
            }}
            .data {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 4px;
                margin-top: 15px;
            }}
            .data-title {{
                font-weight: bold;
                margin-bottom: 10px;
                color: #495057;
            }}
            .data-item {{
                margin: 8px 0;
                padding: 8px;
                background: white;
                border-radius: 4px;
            }}
            .data-key {{
                font-weight: 600;
                color: #667eea;
            }}
            .data-value {{
                color: #212529;
                margin-left: 10px;
            }}
            .no-webhooks {{
                text-align: center;
                padding: 60px 20px;
                background: white;
                border-radius: 8px;
                color: #666;
            }}
            .refresh-btn {{
                background: #667eea;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 1em;
                margin-top: 20px;
            }}
            .refresh-btn:hover {{
                background: #5568d3;
            }}
            pre {{
                background: #282c34;
                color: #abb2bf;
                padding: 15px;
                border-radius: 4px;
                overflow-x: auto;
                font-size: 0.9em;
            }}
        </style>
        <script>
            function autoRefresh() {{
                setTimeout(function() {{
                    location.reload();
                }}, 5000);
            }}
        </script>
    </head>
    <body onload="autoRefresh()">
        <div class="header">
            <h1>🔔 Webhook Test Server</h1>
            <p><strong>Endpoint:</strong> http://localhost:8000/webhook</p>
            <p>Listening for workflow notifications...</p>
        </div>

        <div class="stats">
            <h2>📊 Statistics</h2>
            <p><strong>Total Webhooks Received:</strong> {total_count}</p>
            <p><em>Auto-refreshing every 5 seconds...</em></p>
        </div>

        {webhooks_html}
    </body>
    </html>
    """


@app.get("/clear")
async def clear_webhooks():
    """Clear all received webhooks."""
    received_webhooks.clear()
    return {"status": "cleared", "message": "All webhooks cleared"}


@app.get("/webhooks")
async def list_webhooks():
    """Get all received webhooks as JSON."""
    return {"total": len(received_webhooks), "webhooks": received_webhooks}


def main():
    """Run the webhook server."""
    print("\n" + "=" * 80)
    print("🚀 Starting Webhook Test Server")
    print("=" * 80)
    print()
    print("Server Details:")
    print("  • Webhook endpoint: http://localhost:8000/webhook")
    print("  • Web UI:          http://localhost:8000")
    print("  • API (JSON):      http://localhost:8000/webhooks")
    print("  • Clear webhooks:  http://localhost:8000/clear")
    print()
    print("Configuration:")
    print('  export WEBHOOK_URL="http://localhost:8000/webhook"')
    print()
    print("Then run your webhook example:")
    print("  python examples/api/10_webhook_notifications.py")
    print()
    print("=" * 80)
    print()

    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()

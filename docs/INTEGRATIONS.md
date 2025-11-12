# Integrations Guide

This guide covers webhook integrations, FastAPI deployment, and extending Strands CLI with custom event handlers.

## Table of Contents

- [Webhook Integration](#webhook-integration)
- [Creating Custom Webhook Handlers](#creating-custom-webhook-handlers)
- [FastAPI Deployment](#fastapi-deployment)
- [Security Considerations](#security-considerations)
- [Example Integrations](#example-integrations)

## Webhook Integration

Strands CLI provides a flexible webhook system for notifying external services of workflow events.

### Basic Webhook Setup

```python
from strands_cli.api import Workflow
from strands_cli.integrations.webhook_handler import GenericWebhookHandler

# Load workflow
workflow = Workflow.from_file("workflow.yaml")

# Create webhook handler
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/workflow-events",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
)

# Subscribe to events
@workflow.on("workflow_complete")
def notify_completion(event):
    webhook.send(event)

@workflow.on("hitl_pause")
def notify_hitl(event):
    webhook.send(event)

# Execute workflow
result = workflow.run_interactive(topic="AI agents")
```

### Retry Behavior

Webhook handlers use exponential backoff with 3 retry attempts:

- **Attempt 1**: Immediate
- **Attempt 2**: Wait 1s (exponential backoff)
- **Attempt 3**: Wait 2s (exponential backoff)

Retries occur on:
- Network timeouts
- HTTP 5xx errors
- Connection failures

No retry on:
- HTTP 4xx errors (client errors - bad auth/payload)

### Event Payload Format

Webhooks receive events in this format:

```json
{
  "event_type": "step_complete",
  "timestamp": "2025-11-12T10:30:45.123456",
  "session_id": "a1b2c3d4-e5f6-7890",
  "spec_name": "research-workflow",
  "pattern_type": "chain",
  "data": {
    "step_index": 1,
    "response": "Step output...",
    "duration_seconds": 2.5
  }
}
```

## Creating Custom Webhook Handlers

Extend `WebhookEventHandler` to create custom integrations.

### Base Class Interface

```python
from strands_cli.integrations.webhook_handler import WebhookEventHandler

class CustomWebhookHandler(WebhookEventHandler):
    """Custom webhook handler template."""
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        """Format event for your webhook service.
        
        Returns:
            dict: JSON-serializable payload
        """
        raise NotImplementedError
    
    def get_webhook_url(self) -> str:
        """Return webhook URL.
        
        Returns:
            str: Full webhook URL
        """
        raise NotImplementedError
    
    def get_headers(self) -> dict[str, str]:
        """Return HTTP headers.
        
        Returns:
            dict: Headers including auth
        """
        raise NotImplementedError
```

### Example: Slack Integration

```python
import json
from datetime import datetime
from strands_cli.events import WorkflowEvent
from strands_cli.integrations.webhook_handler import WebhookEventHandler

class SlackWebhookHandler(WebhookEventHandler):
    """Send workflow events to Slack."""
    
    def __init__(self, webhook_url: str, channel: str = "#workflows"):
        self._webhook_url = webhook_url
        self._channel = channel
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        """Format event as Slack message."""
        # Map event types to emojis
        emoji_map = {
            "workflow_start": ":rocket:",
            "step_complete": ":white_check_mark:",
            "hitl_pause": ":hand:",
            "error": ":x:",
            "workflow_complete": ":tada:",
        }
        emoji = emoji_map.get(event.event_type, ":bell:")
        
        # Build message
        text = f"{emoji} *{event.event_type}* - {event.spec_name}"
        
        # Add context from data
        fields = []
        if "step_index" in event.data:
            fields.append({
                "title": "Step",
                "value": str(event.data["step_index"]),
                "short": True
            })
        if "duration_seconds" in event.data:
            fields.append({
                "title": "Duration",
                "value": f"{event.data['duration_seconds']:.2f}s",
                "short": True
            })
        
        return {
            "channel": self._channel,
            "username": "Strands Workflows",
            "icon_emoji": ":robot_face:",
            "attachments": [{
                "color": "good" if event.event_type.endswith("_complete") else "warning",
                "title": text,
                "fields": fields,
                "footer": f"Session: {event.session_id[:8]}",
                "ts": int(event.timestamp.timestamp())
            }]
        }
    
    def get_webhook_url(self) -> str:
        return self._webhook_url
    
    def get_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

# Usage
slack = SlackWebhookHandler(
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    channel="#workflow-alerts"
)

workflow.on("workflow_complete")(lambda event: slack.send(event))
```

### Example: Microsoft Teams Integration

```python
class TeamsWebhookHandler(WebhookEventHandler):
    """Send workflow events to Microsoft Teams."""
    
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        """Format as Teams adaptive card."""
        color = "0078D4"  # Teams blue
        if event.event_type == "error":
            color = "D13438"  # Red
        elif event.event_type.endswith("_complete"):
            color = "107C10"  # Green
        
        facts = []
        if "step_index" in event.data:
            facts.append({
                "name": "Step",
                "value": str(event.data["step_index"])
            })
        if "duration_seconds" in event.data:
            facts.append({
                "name": "Duration",
                "value": f"{event.data['duration_seconds']:.2f}s"
            })
        
        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": f"Workflow Event: {event.event_type}",
            "themeColor": color,
            "title": f"{event.event_type}: {event.spec_name}",
            "sections": [{
                "facts": facts,
                "text": f"Pattern: {event.pattern_type}"
            }]
        }
    
    def get_webhook_url(self) -> str:
        return self._webhook_url
    
    def get_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}
```

### Example: Discord Integration

```python
class DiscordWebhookHandler(WebhookEventHandler):
    """Send workflow events to Discord."""
    
    def __init__(self, webhook_url: str, username: str = "Strands Bot"):
        self._webhook_url = webhook_url
        self._username = username
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        """Format as Discord embed."""
        # Map event types to colors (decimal)
        color_map = {
            "workflow_start": 3447003,    # Blue
            "step_complete": 3066993,     # Green
            "hitl_pause": 15844367,       # Gold
            "error": 15158332,            # Red
            "workflow_complete": 3066993,  # Green
        }
        color = color_map.get(event.event_type, 9807270)  # Default gray
        
        # Build embed fields
        fields = [
            {
                "name": "Pattern",
                "value": event.pattern_type,
                "inline": True
            },
            {
                "name": "Session",
                "value": event.session_id[:8],
                "inline": True
            }
        ]
        
        if "step_index" in event.data:
            fields.append({
                "name": "Step",
                "value": str(event.data["step_index"]),
                "inline": True
            })
        
        return {
            "username": self._username,
            "embeds": [{
                "title": f"{event.event_type}: {event.spec_name}",
                "color": color,
                "fields": fields,
                "timestamp": event.timestamp.isoformat(),
            }]
        }
    
    def get_webhook_url(self) -> str:
        return self._webhook_url
    
    def get_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}
```

## FastAPI Deployment

Deploy Strands workflows as REST APIs using FastAPI integration.

### Basic FastAPI Server

```python
from fastapi import FastAPI
from strands_cli.api import Workflow
from strands_cli.integrations.fastapi_router import create_workflow_router

app = FastAPI(title="Workflow API")

# Load workflow
workflow = Workflow.from_file("workflow.yaml")

# Create and mount router
router = create_workflow_router(workflow, prefix="/workflow")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Available Endpoints

The FastAPI router provides these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/workflow/execute` | POST | Execute workflow |
| `/workflow/sessions` | GET | List sessions (paginated) |
| `/workflow/sessions/{id}` | GET | Get session details |
| `/workflow/sessions/{id}/resume` | POST | Resume paused session |
| `/workflow/sessions/{id}` | DELETE | Delete session |

### Execute Workflow

```bash
curl -X POST http://localhost:8000/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"variables": {"topic": "AI safety"}}'
```

Response:
```json
{
  "session_id": "a1b2c3d4-e5f6-7890",
  "status": "completed",
  "last_response": "Final output...",
  "error": null,
  "duration_seconds": 12.5
}
```

### List Sessions

```bash
curl "http://localhost:8000/workflow/sessions?offset=0&limit=10&status=paused"
```

### Resume Session

```bash
curl -X POST http://localhost:8000/workflow/sessions/a1b2c3d4/resume \
  -H "Content-Type: application/json" \
  -d '{"hitl_response": "approved"}'
```

### Production Deployment

#### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install strands-cli with web extras
RUN pip install "strands-cli[web]"

COPY workflow.yaml ./
COPY server.py ./

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: strands-workflow-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: strands-api
  template:
    metadata:
      labels:
        app: strands-api
    spec:
      containers:
      - name: api
        image: your-registry/strands-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: STRANDS_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: strands-secrets
              key: openai-api-key
```

## Security Considerations

### Webhook Security

#### 1. HTTPS Only
Always use HTTPS for webhooks in production:

```python
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/events",  # ✓ HTTPS
    # NOT: url="http://hooks.example.com"     # ✗ HTTP
)
```

#### 2. Authentication
Include authentication tokens in headers:

```python
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/events",
    headers={
        "Authorization": "Bearer YOUR_SECRET_TOKEN",
        "X-API-Key": "your-api-key"
    }
)
```

#### 3. Webhook Secrets
Validate webhook signatures (when supported by service):

```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

#### 4. Sensitive Data
Filter sensitive data from event payloads:

```python
class SecureWebhookHandler(WebhookEventHandler):
    def format_payload(self, event: WorkflowEvent) -> dict:
        # Remove sensitive fields
        safe_data = {
            k: v for k, v in event.data.items()
            if k not in ["api_key", "password", "secret"]
        }
        
        return {
            "event_type": event.event_type,
            "data": safe_data
        }
```

### FastAPI Security

#### 1. API Key Authentication

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != "your-secret-key":  # Use env var in production
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# Protect routes
@app.post("/workflow/execute", dependencies=[Depends(verify_api_key)])
async def execute_workflow(...):
    ...
```

#### 2. Rate Limiting

```python
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/workflow/execute")
@limiter.limit("10/minute")
async def execute_workflow(request: Request, ...):
    ...
```

#### 3. CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.com"],  # Specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Example Integrations

### Monitoring with Datadog

```python
from strands_cli.integrations.webhook_handler import WebhookEventHandler

class DatadogMetricsHandler(WebhookEventHandler):
    """Send workflow metrics to Datadog."""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._base_url = "https://api.datadoghq.com/api/v1/series"
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        timestamp = int(event.timestamp.timestamp())
        
        # Extract metrics
        metrics = []
        if "duration_seconds" in event.data:
            metrics.append({
                "metric": "strands.workflow.duration",
                "points": [[timestamp, event.data["duration_seconds"]]],
                "tags": [
                    f"workflow:{event.spec_name}",
                    f"pattern:{event.pattern_type}",
                    f"event:{event.event_type}"
                ]
            })
        
        return {"series": metrics}
    
    def get_webhook_url(self) -> str:
        return self._base_url
    
    def get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "DD-API-KEY": self._api_key
        }
```

### Error Tracking with Sentry

```python
import sentry_sdk

class SentryEventHandler:
    """Send workflow errors to Sentry."""
    
    def __init__(self, dsn: str):
        sentry_sdk.init(dsn=dsn)
    
    def handle_error(self, event: WorkflowEvent):
        if event.event_type == "error":
            with sentry_sdk.push_scope() as scope:
                scope.set_context("workflow", {
                    "name": event.spec_name,
                    "pattern": event.pattern_type,
                    "session_id": event.session_id
                })
                scope.set_tag("workflow_name", event.spec_name)
                
                error_msg = event.data.get("error", "Unknown error")
                sentry_sdk.capture_message(error_msg, level="error")

# Usage
sentry = SentryEventHandler(dsn="https://your-sentry-dsn")
workflow.on("error")(sentry.handle_error)
```

## Best Practices

1. **Idempotent Webhooks**: Design webhooks to handle duplicate events gracefully
2. **Timeout Handling**: Set reasonable timeouts for webhook calls (default: 10s)
3. **Error Logging**: Log all webhook failures for debugging
4. **Event Filtering**: Only subscribe to events you need
5. **Async Handlers**: Use async handlers for I/O-bound webhook operations
6. **Testing**: Mock webhook endpoints in tests
7. **Monitoring**: Track webhook success/failure rates
8. **Documentation**: Document expected event payloads for consumers

## Troubleshooting

### Webhook Not Receiving Events

1. Check event subscription is correct
2. Verify webhook URL is reachable
3. Check authentication headers
4. Review webhook service logs
5. Ensure HTTPS certificate is valid

### FastAPI Server Errors

1. Check Python version (≥3.12)
2. Install web extras: `pip install strands-cli[web]`
3. Verify workflow spec is valid
4. Check environment variables
5. Review uvicorn logs

### Performance Issues

1. Use pagination for large session lists
2. Enable caching for SessionManager
3. Limit concurrent workflow executions
4. Monitor memory usage
5. Profile slow webhook handlers

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Webhook Best Practices](https://webhooks.fyi/)
- [API Security Guide](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Strands CLI API Reference](./API.md)

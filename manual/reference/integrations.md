# Integrations Guide

This guide covers webhook integrations, FastAPI deployment, and extending Strands CLI with custom event handlers.

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
- **Attempt 2**: Wait 1s
- **Attempt 3**: Wait 2s

Retries occur on network timeouts, HTTP 5xx errors, and connection failures. No retry on HTTP 4xx errors.

### Event Payload Format

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

### Slack Integration Example

```python
from strands_cli.events import WorkflowEvent
from strands_cli.integrations.webhook_handler import WebhookEventHandler

class SlackWebhookHandler(WebhookEventHandler):
    """Send workflow events to Slack."""
    
    def __init__(self, webhook_url: str, channel: str = "#workflows"):
        self._webhook_url = webhook_url
        self._channel = channel
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        """Format event as Slack message."""
        emoji_map = {
            "workflow_start": ":rocket:",
            "step_complete": ":white_check_mark:",
            "hitl_pause": ":hand:",
            "error": ":x:",
            "workflow_complete": ":tada:",
        }
        emoji = emoji_map.get(event.event_type, ":bell:")
        
        text = f"{emoji} *{event.event_type}* - {event.spec_name}"
        
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
            "attachments": [{
                "color": "good" if event.event_type.endswith("_complete") else "warning",
                "title": text,
                "fields": fields,
                "footer": f"Session: {event.session_id[:8]}",
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

!!! tip "Example Code"
    See `examples/api/10_webhook_notifications.py` in the repository for more examples.

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

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/workflow/execute` | POST | Execute workflow |
| `/workflow/sessions` | GET | List sessions (paginated) |
| `/workflow/sessions/{id}` | GET | Get session details |
| `/workflow/sessions/{id}/resume` | POST | Resume paused session |
| `/workflow/sessions/{id}` | DELETE | Delete session |

### Example API Calls

Execute workflow:
```bash
curl -X POST http://localhost:8000/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"variables": {"topic": "AI safety"}}'
```

List sessions:
```bash
curl "http://localhost:8000/workflow/sessions?offset=0&limit=10&status=paused"
```

Resume session:
```bash
curl -X POST http://localhost:8000/workflow/sessions/a1b2c3d4/resume \
  -H "Content-Type: application/json" \
  -d '{"hitl_response": "approved"}'
```

!!! tip "Example Code"
    See `examples/api/09_fastapi_integration.py` in the repository for a complete example.

## Security Best Practices

### Webhook Security

**1. Always use HTTPS in production**

```python
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/events",  # ✓ HTTPS
)
```

**2. Include authentication tokens**

```python
webhook = GenericWebhookHandler(
    url="https://hooks.example.com/events",
    headers={
        "Authorization": "Bearer YOUR_SECRET_TOKEN",
        "X-API-Key": "your-api-key"
    }
)
```

**3. Filter sensitive data**

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

**API Key Authentication**

```python
from fastapi import Security, HTTPException, Depends
from fastapi.security import APIKeyHeader

API_KEY = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.post("/workflow/execute", dependencies=[Depends(verify_api_key)])
async def execute_workflow(...):
    ...
```

**CORS Configuration**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Production Deployment

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install "strands-cli[web]"

COPY workflow.yaml ./
COPY server.py ./

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes

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

## Additional Integration Examples

### Monitoring with Datadog

```python
class DatadogMetricsHandler(WebhookEventHandler):
    """Send workflow metrics to Datadog."""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._base_url = "https://api.datadoghq.com/api/v1/series"
    
    def format_payload(self, event: WorkflowEvent) -> dict:
        timestamp = int(event.timestamp.timestamp())
        
        metrics = []
        if "duration_seconds" in event.data:
            metrics.append({
                "metric": "strands.workflow.duration",
                "points": [[timestamp, event.data["duration_seconds"]]],
                "tags": [
                    f"workflow:{event.spec_name}",
                    f"pattern:{event.pattern_type}",
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
                
                error_msg = event.data.get("error", "Unknown error")
                sentry_sdk.capture_message(error_msg, level="error")

# Usage
sentry = SentryEventHandler(dsn="https://your-sentry-dsn")
workflow.on("error")(sentry.handle_error)
```

## Best Practices

1. **Idempotent Webhooks**: Design webhooks to handle duplicate events gracefully
2. **Timeout Handling**: Set reasonable timeouts (default: 10s)
3. **Error Logging**: Log all webhook failures for debugging
4. **Event Filtering**: Only subscribe to events you need
5. **Async Handlers**: Use async handlers for I/O-bound operations
6. **Testing**: Mock webhook endpoints in tests
7. **Monitoring**: Track webhook success/failure rates

## Troubleshooting

### Webhook Not Receiving Events

1. Verify webhook URL is reachable (test with curl)
2. Check authentication headers are correct
3. Ensure HTTPS certificate is valid
4. Review webhook service logs
5. Check event subscription is correct

### FastAPI Server Errors

1. Ensure Python ≥3.12
2. Install web extras: `pip install strands-cli[web]`
3. Verify workflow spec is valid
4. Check environment variables are set
5. Review uvicorn logs

### Performance Issues

1. Use pagination for large session lists
2. Enable caching for SessionManager (automatic with 5-min TTL)
3. Limit concurrent workflow executions
4. Monitor memory usage
5. Profile slow webhook handlers

## See Also

- [API Reference](api/index.md) - Complete API documentation
- [Session API](session-api.md) - Session management details
- [Builder API Tutorial](../tutorials/builder-api.md) - Getting started guide

# Plan: Phase 3 Production Features Implementation (Updated)

Implement event system, session management API, async context managers, FastAPI integration, and foundational infrastructure for webhooks and streaming. Adds pagination for session management and basic streaming support while maintaining focus on core production features.

## Steps

### 1. Build event system with extensible notification infrastructure

Create `src/strands_cli/events.py` with `EventBus`, `WorkflowEvent` classes and `EventHandler` protocol. Add `WebhookEventHandler` base class for future integrations (abstract methods for Slack/Teams/Discord). Add `event_bus` parameter to all 7 executors in `src/strands_cli/exec/`. Emit events at checkpoints (start, step_complete, hitl_pause, error, complete). Add `.on()` decorator to `WorkflowExecutor` in `src/strands_cli/api/execution.py`.

**Key Implementation Details:**

- **Event System Core** (`src/strands_cli/events.py`):
  - `WorkflowEvent` dataclass with: `event_type`, `timestamp`, `session_id`, `spec_name`, `pattern_type`, `data`
  - `EventHandler` protocol for type-safe callback signatures
  - `EventBus` class with `subscribe()`, `emit()`, support for both sync and async handlers
  - Thread-safe emission using `asyncio.Lock`

- **Webhook Infrastructure** (`src/strands_cli/integrations/webhook_handler.py`):
  - `WebhookEventHandler` abstract base class
  - Abstract methods: `format_payload()`, `get_webhook_url()`, `get_headers()`
  - Generic HTTP POST implementation with retry logic (tenacity)
  - Example implementations: `GenericWebhookHandler`, `SlackWebhookHandler` (placeholder)

- **Executor Integration**:
  - Add optional `event_bus: EventBus | None = None` parameter to all executor signatures
  - Emit events after existing `logger.info()` calls:
    - `workflow_start`: At executor entry
    - `step_start`/`task_start`/`branch_start`/`node_start`: Before agent invocation
    - `step_complete`/`task_complete`/`branch_complete`/`node_complete`: After agent invocation
    - `hitl_pause`: When HITL step encountered
    - `error`: On exception
    - `workflow_complete`: Before returning `RunResult`

- **API Integration** (`src/strands_cli/api/execution.py`):
  - Add `self.event_bus = EventBus()` to `WorkflowExecutor.__init__()`
  - Add `.on(event_type: str)` decorator method
  - Pass `event_bus` to executor functions in `_execute()`

**Files Modified:**
- `src/strands_cli/exec/chain.py`
- `src/strands_cli/exec/workflow.py`
- `src/strands_cli/exec/parallel.py`
- `src/strands_cli/exec/graph.py`
- `src/strands_cli/exec/routing.py`
- `src/strands_cli/exec/evaluator_optimizer.py`
- `src/strands_cli/exec/orchestrator.py`
- `src/strands_cli/api/execution.py`

**Files Created:**
- `src/strands_cli/events.py`
- `src/strands_cli/integrations/__init__.py`
- `src/strands_cli/integrations/webhook_handler.py`

### 2. Create SessionManager API with pagination

Build `src/strands_cli/api/session_manager.py` wrapping `FileSessionRepository` with paginated `list(offset, limit, status, workflow_name)`, `get()`, `resume()`, `cleanup()`, `delete()` methods. Add LRU cache with 5-minute TTL for session metadata. Export from `src/strands_cli/api/__init__.py`. No changes to existing session infrastructure.

**Key Implementation Details:**

- **SessionManager Class** (`src/strands_cli/api/session_manager.py`):
  ```python
  class SessionManager:
      def __init__(self, storage_dir: Path | None = None):
          self.repo = FileSessionRepository(storage_dir)
          self._cache: dict[str, tuple[SessionState, datetime]] = {}
          self._cache_ttl = timedelta(minutes=5)
      
      async def list(
          self,
          offset: int = 0,
          limit: int = 100,
          status: SessionStatus | None = None,
          workflow_name: str | None = None,
      ) -> list[SessionState]:
          """List sessions with pagination and filtering."""
          
      async def get(self, session_id: str) -> SessionState:
          """Get session by ID with caching."""
          
      async def resume(
          self,
          session_id: str,
          hitl_response: str | None = None,
      ) -> RunResult:
          """Resume paused session."""
          
      async def cleanup(
          self,
          older_than_days: int = 7,
          status_filter: list[SessionStatus] | None = None,
      ) -> int:
          """Clean up old sessions."""
          
      async def delete(self, session_id: str) -> None:
          """Delete session by ID."""
  ```

- **Caching Strategy**:
  - Cache key: `session_id`
  - Cache value: `(SessionState, timestamp)`
  - TTL: 5 minutes
  - Invalidate on: `delete()`, `resume()` completion

- **Pagination**:
  - Default: `offset=0`, `limit=100`
  - Max limit: 1000 (prevent excessive memory usage)
  - Return slice of sorted results (by `updated_at` descending)

- **Integration with Existing Code**:
  - Use `run_resume()` from `src/strands_cli/session/resume.py`
  - Delegate to `FileSessionRepository` methods
  - No changes to session file format or storage structure

**Files Created:**
- `src/strands_cli/api/session_manager.py`

**Files Modified:**
- `src/strands_cli/api/__init__.py` (add `SessionManager` export)

### 3. Add async context managers and basic streaming support

Implement `__aenter__`/`__aexit__` in `WorkflowExecutor` (`src/strands_cli/api/execution.py`) to manage `AgentCache` lifecycle. Add optional `agent_cache` parameter to executors for backward compatibility. Create `workflow.async_executor()` method. Add `stream_async()` method returning `AsyncGenerator[StreamChunk, None]` with chunk types: `token`, `step_start`, `step_complete`, `complete`. Token streaming deferred to post-v0.14.0 (returns complete responses as chunks for now).

**Key Implementation Details:**

- **Async Context Manager** (`src/strands_cli/api/execution.py`):
  ```python
  class WorkflowExecutor:
      def __init__(self, spec: Spec):
          self.spec = spec
          self.event_bus = EventBus()
          self._agent_cache: AgentCache | None = None
      
      async def __aenter__(self):
          """Enter async context."""
          self._agent_cache = AgentCache()
          return self
      
      async def __aexit__(self, exc_type, exc_val, exc_tb):
          """Exit async context and cleanup resources."""
          if self._agent_cache:
              await self._agent_cache.close()
          return False
  ```

- **Executor Backward Compatibility**:
  ```python
  async def run_chain(
      spec: Spec,
      variables: dict[str, Any] | None = None,
      session_state: SessionState | None = None,
      session_repo: FileSessionRepository | None = None,
      hitl_response: str | None = None,
      event_bus: EventBus | None = None,
      agent_cache: AgentCache | None = None,  # NEW
  ) -> RunResult:
      cache = agent_cache or AgentCache()
      should_close = agent_cache is None
      
      try:
          # ... existing logic
      finally:
          if should_close:
              await cache.close()
  ```

- **Streaming API** (`src/strands_cli/types.py` additions):
  ```python
  from typing import Literal
  
  StreamChunkType = Literal["token", "step_start", "step_complete", "complete"]
  
  @dataclass
  class StreamChunk:
      """Streaming response chunk."""
      chunk_type: StreamChunkType
      data: dict[str, Any]
      timestamp: datetime
  ```

- **Stream Method** (`src/strands_cli/api/execution.py`):
  ```python
  async def stream_async(
      self,
      variables: dict[str, Any],
  ) -> AsyncGenerator[StreamChunk, None]:
      """Stream workflow execution events.
      
      Note: Token-by-token streaming not yet implemented.
      Returns complete responses as 'complete' chunks.
      """
      # Subscribe to event bus
      chunks: asyncio.Queue[StreamChunk] = asyncio.Queue()
      
      def emit_chunk(event: WorkflowEvent):
          chunk = StreamChunk(
              chunk_type=self._map_event_to_chunk_type(event.event_type),
              data=event.data,
              timestamp=event.timestamp,
          )
          chunks.put_nowait(chunk)
      
      # Subscribe to relevant events
      self.event_bus.subscribe("step_start", emit_chunk)
      self.event_bus.subscribe("step_complete", emit_chunk)
      self.event_bus.subscribe("workflow_complete", emit_chunk)
      
      # Start execution in background
      async def execute():
          result = await self.run_async(variables)
          await chunks.put(None)  # Sentinel
      
      task = asyncio.create_task(execute())
      
      # Yield chunks as they arrive
      while True:
          chunk = await chunks.get()
          if chunk is None:
              break
          yield chunk
      
      await task  # Ensure execution completes
  ```

- **Workflow API Addition** (`src/strands_cli/api/__init__.py`):
  ```python
  class Workflow:
      def async_executor(self) -> WorkflowExecutor:
          """Get async context manager for execution."""
          return self._executor
  ```

**Files Modified:**
- `src/strands_cli/api/execution.py`
- `src/strands_cli/api/__init__.py`
- `src/strands_cli/types.py`
- All executor files (add optional `agent_cache` parameter)

### 4. Implement FastAPI router with webhook example

Create `src/strands_cli/integrations/fastapi_router.py` with `create_workflow_router()` factory. Endpoints: `POST /execute`, `GET /sessions?offset=0&limit=100`, `POST /sessions/{id}/resume`. Add `[web]` extras to `pyproject.toml`. Create `src/strands_cli/integrations/webhook_handler.py` with example webhook notification handler (generic HTTP POST). Build examples: `09_fastapi_integration.py`, `10_webhook_notifications.py`.

**Key Implementation Details:**

- **FastAPI Router** (`src/strands_cli/integrations/fastapi_router.py`):
  ```python
  from fastapi import APIRouter, HTTPException, Query
  from pydantic import BaseModel
  
  class ExecuteRequest(BaseModel):
      variables: dict[str, str] = {}
  
  class ExecuteResponse(BaseModel):
      session_id: str
      status: str
      last_response: str | None = None
      error: str | None = None
      duration_seconds: float | None = None
  
  class SessionInfo(BaseModel):
      session_id: str
      workflow_name: str
      status: str
      created_at: str
      updated_at: str
  
  class ResumeRequest(BaseModel):
      hitl_response: str | None = None
  
  def create_workflow_router(
      workflow: Workflow,
      prefix: str = "/workflow",
  ) -> APIRouter:
      """Create FastAPI router for workflow execution."""
      router = APIRouter(prefix=prefix, tags=["workflow"])
      session_manager = SessionManager()
      
      @router.post("/execute", response_model=ExecuteResponse)
      async def execute_workflow(request: ExecuteRequest):
          """Execute workflow asynchronously."""
          
      @router.get("/sessions", response_model=list[SessionInfo])
      async def list_sessions(
          offset: int = Query(0, ge=0),
          limit: int = Query(100, ge=1, le=1000),
          status: str | None = None,
      ):
          """List workflow sessions with pagination."""
          
      @router.get("/sessions/{session_id}", response_model=SessionInfo)
      async def get_session(session_id: str):
          """Get session details."""
          
      @router.post("/sessions/{session_id}/resume", response_model=ExecuteResponse)
      async def resume_session(session_id: str, request: ResumeRequest):
          """Resume paused session."""
          
      @router.delete("/sessions/{session_id}", status_code=204)
      async def delete_session(session_id: str):
          """Delete session."""
          
      return router
  ```

- **Optional Dependencies** (`pyproject.toml`):
  ```toml
  [project.optional-dependencies]
  web = [
      "fastapi>=0.100.0",
      "uvicorn>=0.20.0",
  ]
  ```

- **Example FastAPI Server** (`examples/api/09_fastapi_integration.py`):
  ```python
  #!/usr/bin/env python3
  """FastAPI integration example."""
  
  from fastapi import FastAPI
  from strands_cli.api import Workflow
  from strands_cli.integrations.fastapi_router import create_workflow_router
  
  app = FastAPI(title="Strands Workflow API")
  
  # Load workflow
  workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
  
  # Create router
  router = create_workflow_router(workflow, prefix="/workflows")
  app.include_router(router)
  
  if __name__ == "__main__":
      import uvicorn
      uvicorn.run(app, host="0.0.0.0", port=8000)
  ```

- **Webhook Example** (`examples/api/10_webhook_notifications.py`):
  ```python
  #!/usr/bin/env python3
  """Webhook notification example."""
  
  from strands_cli.api import Workflow
  from strands_cli.integrations.webhook_handler import GenericWebhookHandler
  
  workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
  
  # Configure webhook
  webhook = GenericWebhookHandler(
      url="https://hooks.example.com/workflow-events",
      headers={"Authorization": "Bearer YOUR_TOKEN"},
  )
  
  # Subscribe to events
  @workflow.on("workflow_complete")
  def on_complete(event):
      webhook.send(event)
  
  @workflow.on("hitl_pause")
  def on_hitl(event):
      webhook.send(event)
  
  # Execute
  result = workflow.run_interactive(topic="AI agents")
  ```

**Files Created:**
- `src/strands_cli/integrations/fastapi_router.py`
- `examples/api/09_fastapi_integration.py`
- `examples/api/10_webhook_notifications.py`

**Files Modified:**
- `pyproject.toml` (add `[web]` extras)

### 5. Write comprehensive tests, examples, and documentation

Unit tests for `EventBus`, `SessionManager` (with pagination), async context manager, FastAPI endpoints, webhook handler. Integration tests for event emission across patterns, session lifecycle with pagination, async resource cleanup, streaming API. Create examples: `06_event_callbacks.py`, `07_session_management.py`, `08_async_execution.py`, `11_streaming_responses.py`. Update `docs/API.md` with Phase 3 reference. Add webhook extensibility guide to `docs/INTEGRATIONS.md`.

**Key Implementation Details:**

- **Unit Tests** (`tests/api/`):
  - `test_events.py`:
    - Event bus subscription and emission
    - Sync and async handler support
    - Thread safety with concurrent emitters
    - Event data serialization
  
  - `test_session_manager.py`:
    - Pagination (offset, limit)
    - Filtering (status, workflow_name)
    - Caching behavior and TTL
    - Resume integration
    - Cleanup logic
  
  - `test_async_context.py`:
    - Context manager protocol
    - AgentCache lifecycle management
    - Resource cleanup on exception
    - Backward compatibility with existing code
  
  - `test_streaming.py`:
    - Chunk emission order
    - Complete responses as chunks
    - Error handling in streams
  
  - `test_fastapi_router.py` (requires `[web]` extras):
    - All endpoint responses
    - Error status codes (404, 500)
    - Pagination parameters
    - Request/response models

- **Integration Tests** (`tests/integration/`):
  - `test_event_emission.py`:
    - Event emission in chain pattern
    - Event emission in workflow pattern
    - Event emission in parallel pattern
    - Callback execution order
  
  - `test_session_lifecycle_api.py`:
    - Create → list → get → resume flow
    - Pagination with large session counts
    - Concurrent session access
  
  - `test_async_execution.py`:
    - Multiple concurrent workflows
    - Resource cleanup verification
    - Performance vs sync execution

- **Examples** (`examples/api/`):
  
  - `06_event_callbacks.py`:
    ```python
    """Event-driven workflow with callbacks."""
    from strands_cli.api import Workflow
    
    workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
    
    @workflow.on("step_complete")
    def on_step(event):
        print(f"✓ Step {event.data['step_index']} completed")
    
    @workflow.on("workflow_complete")
    def on_complete(event):
        print(f"✓ Workflow finished in {event.data['duration']:.2f}s")
    
    result = workflow.run_interactive(topic="AI safety")
    ```
  
  - `07_session_management.py`:
    ```python
    """Session management API example."""
    import asyncio
    from strands_cli.api import SessionManager
    
    async def main():
        manager = SessionManager()
        
        # List paused sessions
        sessions = await manager.list(status="paused", limit=10)
        print(f"Found {len(sessions)} paused sessions")
        
        # Resume first session
        if sessions:
            result = await manager.resume(
                sessions[0].metadata.session_id,
                hitl_response="approved"
            )
            print(f"Resumed: {result.success}")
        
        # Cleanup old sessions
        removed = await manager.cleanup(older_than_days=7)
        print(f"Cleaned up {removed} sessions")
    
    asyncio.run(main())
    ```
  
  - `08_async_execution.py`:
    ```python
    """Async workflow execution example."""
    import asyncio
    from strands_cli.api import Workflow
    
    async def main():
        workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
        
        # Use async context manager
        async with workflow.async_executor() as executor:
            result = await executor.run(topic="quantum computing")
            print(f"Result: {result.last_response[:200]}...")
        
        # Resources automatically cleaned up
    
    asyncio.run(main())
    ```
  
  - `11_streaming_responses.py`:
    ```python
    """Streaming response example."""
    import asyncio
    from strands_cli.api import Workflow
    
    async def main():
        workflow = Workflow.from_file("../chain-3-step-research-openai.yaml")
        
        print("Streaming workflow execution...")
        async for chunk in workflow.stream_async(topic="AI agents"):
            if chunk.chunk_type == "step_start":
                print(f"\n→ Starting step {chunk.data.get('step_index')}...")
            elif chunk.chunk_type == "step_complete":
                response = chunk.data.get('response', '')
                print(f"✓ Completed: {response[:100]}...")
            elif chunk.chunk_type == "complete":
                print(f"\n✓ Workflow complete!")
    
    asyncio.run(main())
    ```

- **Documentation Updates**:
  
  - `docs/API.md` additions:
    - Event System section with examples
    - SessionManager API reference
    - Async context manager usage
    - Streaming API (alpha notice)
    - Migration guide from CLI to API
  
  - `docs/INTEGRATIONS.md` (new file):
    - Webhook extensibility guide
    - Creating custom webhook handlers
    - Slack/Teams integration templates
    - FastAPI deployment guide
    - Error handling best practices
    - Security considerations (webhook secrets, HTTPS)

**Files Created:**
- `tests/api/test_events.py`
- `tests/api/test_session_manager.py`
- `tests/api/test_async_context.py`
- `tests/api/test_streaming.py`
- `tests/api/test_fastapi_router.py`
- `tests/integration/test_event_emission.py`
- `tests/integration/test_session_lifecycle_api.py`
- `tests/integration/test_async_execution.py`
- `examples/api/06_event_callbacks.py`
- `examples/api/07_session_management.py`
- `examples/api/08_async_execution.py`
- `examples/api/11_streaming_responses.py`
- `docs/INTEGRATIONS.md`

**Files Modified:**
- `docs/API.md`
- `manual/tutorials/builder-api.md` (add Phase 3 examples)

## Further Considerations

### 1. Streaming chunk size strategy

For future token-by-token streaming, should we buffer tokens (e.g., 10 tokens/chunk) or emit individual tokens? Buffering reduces event overhead but increases latency.

**Recommendation:** Configurable buffer size with sensible default (10 tokens). Add `stream_async(buffer_tokens=10)` parameter.

**Rationale:**
- 10 tokens ≈ 7-8 words ≈ good balance between latency and overhead
- Single-token streaming: 100+ events/sec for long responses (high overhead)
- Allow `buffer_tokens=1` for real-time typewriter effect when needed
- Allow `buffer_tokens=0` to disable streaming (return complete responses)

### 2. Event bus persistence for debugging

Should events optionally be persisted to disk for post-execution analysis? Could add `EventBus(persist_to="events.jsonl")` option for debugging workflows.

**Recommendation:** Add optional event persistence in Phase 3, disabled by default.

**Implementation:**
```python
class EventBus:
    def __init__(self, persist_to: Path | None = None):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._persist_to = persist_to
        self._persist_file = None
        
        if persist_to:
            self._persist_file = open(persist_to, 'a', encoding='utf-8')
    
    async def emit(self, event: WorkflowEvent):
        # ... emit to handlers
        
        # Persist to disk if configured
        if self._persist_file:
            import json
            self._persist_file.write(json.dumps(asdict(event)) + '\n')
            self._persist_file.flush()
```

**Use cases:**
- Production debugging (replay events to understand failures)
- Performance profiling (analyze step durations)
- Audit trails (who approved what in HITL workflows)
- Testing (golden file comparison)

**Considerations:**
- File rotation for long-running workflows
- Async I/O to avoid blocking execution
- Structured format (JSONL) for easy parsing

### 3. Webhook retry policy

`WebhookEventHandler` should handle transient failures. Recommend: exponential backoff with max 3 retries using existing `tenacity` library, consistent with agent retry logic in `src/strands_cli/exec/utils.py`.

**Recommendation:** Implement retry logic with tenacity, matching existing agent retry behavior.

**Implementation:**
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx

class WebhookEventHandler:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
    )
    async def send(self, event: WorkflowEvent) -> None:
        """Send event to webhook with retry logic."""
        payload = self.format_payload(event)
        headers = self.get_headers()
        url = self.get_webhook_url()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
```

**Retry behavior:**
- Attempt 1: Immediate
- Attempt 2: Wait 1s (exponential backoff)
- Attempt 3: Wait 2s (exponential backoff)
- After 3 failures: Log error and continue (don't block workflow)

**Error handling:**
- Retry on: timeout, 5xx errors, network errors
- Don't retry on: 4xx errors (client errors - bad payload/auth)
- Log all retry attempts for debugging

**Consistent with existing code:**
- Matches `invoke_agent_with_retry()` in `src/strands_cli/exec/utils.py`
- Uses same tenacity configuration pattern
- Same error logging approach

## Implementation Timeline

### Week 1: Core Infrastructure (Days 1-5)

**Day 1: Event System**
- Create `src/strands_cli/events.py`
- Implement `EventBus`, `WorkflowEvent`, `EventHandler`
- Add async handler support
- Write unit tests

**Day 2: Executor Integration**
- Add `event_bus` parameter to all 7 executors
- Emit events at key checkpoints
- Add `.on()` decorator to `WorkflowExecutor`
- Write integration tests

**Day 3: SessionManager API**
- Create `src/strands_cli/api/session_manager.py`
- Implement pagination and caching
- Export from API
- Write unit and integration tests

**Day 4: Async Context Manager**
- Add `__aenter__`/`__aexit__` to `WorkflowExecutor`
- Add optional `agent_cache` to executors
- Implement backward compatibility
- Write unit tests

**Day 5: Basic Streaming**
- Add `StreamChunk` types
- Implement `stream_async()` method
- Connect to event bus
- Write unit tests

### Week 2: Integrations & Examples (Days 1-5)

**Day 1: Webhook Infrastructure**
- Create `src/strands_cli/integrations/webhook_handler.py`
- Implement retry logic with tenacity
- Add example handlers
- Write unit tests

**Day 2: FastAPI Router**
- Create `src/strands_cli/integrations/fastapi_router.py`
- Implement all endpoints
- Add optional dependencies
- Write unit tests with TestClient

**Day 3: Examples**
- Create all 6 example files
- Test examples end-to-end
- Add inline documentation

**Day 4: Documentation**
- Update `docs/API.md` with Phase 3 content
- Create `docs/INTEGRATIONS.md`
- Update `manual/tutorials/builder-api.md`
- Review and polish

**Day 5: Testing & Polish**
- Run full test suite
- Check coverage (target ≥85%)
- Fix any bugs found
- Update CHANGELOG.md
- Prepare release notes

## Success Criteria

✅ **Event System:**
- Event bus supports sync and async handlers
- All 7 patterns emit events at key checkpoints
- Thread-safe concurrent emission
- Optional event persistence works

✅ **Session Management:**
- `SessionManager` API wraps all CLI session commands
- Pagination works with large session counts (100+)
- Caching reduces disk I/O by >80%
- Backward compatible with existing sessions

✅ **Async Features:**
- Context manager properly cleans up resources
- Streaming API emits chunks in correct order
- Performance overhead <10% vs non-async
- Existing sync code unaffected

✅ **Integrations:**
- FastAPI router auto-generates working REST API
- Webhook handler retries transient failures
- Example server runs without errors
- Optional dependencies work correctly

✅ **Quality:**
- Test coverage ≥85% for new code
- All examples run successfully
- Documentation complete and accurate
- Zero breaking changes to existing API

## Files Summary

### New Files (17 total)

**Source Code:**
1. `src/strands_cli/events.py`
2. `src/strands_cli/api/session_manager.py`
3. `src/strands_cli/integrations/__init__.py`
4. `src/strands_cli/integrations/webhook_handler.py`
5. `src/strands_cli/integrations/fastapi_router.py`

**Tests:**
6. `tests/api/test_events.py`
7. `tests/api/test_session_manager.py`
8. `tests/api/test_async_context.py`
9. `tests/api/test_streaming.py`
10. `tests/api/test_fastapi_router.py`
11. `tests/integration/test_event_emission.py`
12. `tests/integration/test_session_lifecycle_api.py`
13. `tests/integration/test_async_execution.py`

**Examples:**
14. `examples/api/06_event_callbacks.py`
15. `examples/api/07_session_management.py`
16. `examples/api/08_async_execution.py`
17. `examples/api/09_fastapi_integration.py`
18. `examples/api/10_webhook_notifications.py`
19. `examples/api/11_streaming_responses.py`

**Documentation:**
20. `docs/INTEGRATIONS.md`

### Modified Files (13 total)

**Source Code:**
1. `src/strands_cli/api/__init__.py` (exports)
2. `src/strands_cli/api/execution.py` (context manager, streaming)
3. `src/strands_cli/types.py` (StreamChunk types)
4. `src/strands_cli/exec/chain.py` (event_bus, agent_cache params)
5. `src/strands_cli/exec/workflow.py` (event_bus, agent_cache params)
6. `src/strands_cli/exec/parallel.py` (event_bus, agent_cache params)
7. `src/strands_cli/exec/graph.py` (event_bus, agent_cache params)
8. `src/strands_cli/exec/routing.py` (event_bus, agent_cache params)
9. `src/strands_cli/exec/evaluator_optimizer.py` (event_bus, agent_cache params)
10. `src/strands_cli/exec/orchestrator.py` (event_bus, agent_cache params)

**Configuration:**
11. `pyproject.toml` ([web] extras)

**Documentation:**
12. `docs/API.md` (Phase 3 sections)
13. `manual/tutorials/builder-api.md` (Phase 3 examples)

## Risk Mitigation

### Technical Risks

| Risk | Mitigation |
|------|-----------|
| Event handler errors break execution | Wrap handlers in try/except, log errors but continue |
| Session cache invalidation bugs | Add extensive cache tests, short TTL (5 min) |
| Async resource leaks | Use context managers, add cleanup tests |
| FastAPI optional dependency conflicts | Test with and without [web] extras |
| Streaming performance overhead | Profile and optimize, add performance tests |

### Schedule Risks

| Risk | Mitigation |
|------|-----------|
| Integration testing bottleneck | Write tests in parallel with implementation |
| Documentation lag | Document while coding, not after |
| Example complexity | Start with simplest examples, add complexity incrementally |
| Dependency on external libraries | Pin versions, test across Python 3.12+ |

## Post-Implementation Tasks

After Phase 3 completion:

1. **Release v0.14.0:**
   - Tag release
   - Update CHANGELOG.md
   - Publish to PyPI
   - Update documentation site

2. **Gather Feedback:**
   - Internal testing with real workflows
   - Community feedback on GitHub Discussions
   - Monitor for bugs and usability issues

3. **Plan Future Enhancements:**
   - Token-by-token streaming (post-v0.14.0)
   - GraphQL API (future)
   - Workflow marketplace (future)
   - Additional webhook integrations (Slack, Teams, Discord)

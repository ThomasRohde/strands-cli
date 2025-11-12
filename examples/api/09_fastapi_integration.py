#!/usr/bin/env python3
"""FastAPI integration example.

This example demonstrates how to expose a Strands workflow as a REST API
using FastAPI. The API provides endpoints for:
- Executing workflows
- Listing sessions with pagination
- Getting session details
- Resuming paused sessions
- Deleting sessions

Requirements:
    pip install "strands-cli[web]"

Usage:
    python examples/api/09_fastapi_integration.py

    Then open your browser to:
    - http://localhost:8000/docs (Swagger UI)
    - http://localhost:8000/redoc (ReDoc)

    Example API calls:
    - POST http://localhost:8000/workflows/execute
      Body: {"variables": {"topic": "AI agents"}}

    - GET http://localhost:8000/workflows/sessions?limit=10

    - GET http://localhost:8000/workflows/sessions/{session_id}

    - POST http://localhost:8000/workflows/sessions/{session_id}/resume
      Body: {"hitl_response": "approved"}

    - DELETE http://localhost:8000/workflows/sessions/{session_id}
"""

from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    print("FastAPI is required. Install with: pip install 'strands-cli[web]'")
    exit(1)

from strands_cli.api import Workflow
from strands_cli.integrations.fastapi_router import create_workflow_router

# Create FastAPI app
app = FastAPI(
    title="Strands Workflow API",
    description="REST API for executing and managing Strands workflows",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware (configure appropriately for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load workflow from file
examples_dir = Path(__file__).parent.parent
workflow_file = examples_dir / "chain-3-step-research-openai.yaml"

if not workflow_file.exists():
    print(f"Error: Workflow file not found: {workflow_file}")
    print("Make sure you're running this from the examples/api/ directory")
    exit(1)

# Create workflow instance
workflow = Workflow.from_file(str(workflow_file))

# Create and mount workflow router
router = create_workflow_router(workflow, prefix="/workflows")
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Strands Workflow API",
        "workflow": workflow.spec.name,
        "version": str(workflow.spec.version),
        "endpoints": {
            "execute": "POST /workflows/execute",
            "list_sessions": "GET /workflows/sessions",
            "get_session": "GET /workflows/sessions/{session_id}",
            "resume_session": "POST /workflows/sessions/{session_id}/resume",
            "delete_session": "DELETE /workflows/sessions/{session_id}",
        },
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("Strands Workflow API Server")
    print("=" * 60)
    print(f"Workflow: {workflow.spec.name}")
    print(f"File: {workflow_file}")
    print("=" * 60)
    print("Starting server on http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 60)
    print()

    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )

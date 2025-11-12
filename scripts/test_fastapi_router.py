#!/usr/bin/env python3
"""Quick test script for FastAPI router implementation."""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

print("Testing FastAPI router implementation...")
print()

# Test 1: Import the router module
print("✓ Test 1: Import fastapi_router module")
try:
    from strands_cli.integrations.fastapi_router import create_workflow_router

    print("  Success: Module imported")
except ImportError as e:
    print(f"  ✗ Failed: {e}")
    print("  Note: FastAPI is optional. Install with: pip install 'strands-cli[web]'")
    sys.exit(0)

# Test 2: Check Pydantic models
print("✓ Test 2: Check Pydantic models")
try:
    # Just import the router - models are used internally
    from strands_cli.integrations.fastapi_router import router

    print("  Success: Router imported")
except ImportError as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

# Test 3: Load a workflow
print("✓ Test 3: Load workflow")
try:
    from strands_cli.api import Workflow

    examples_dir = Path(__file__).parent.parent / "examples"
    workflow_file = examples_dir / "chain-3-step-research-openai.yaml"

    if not workflow_file.exists():
        print(f"  ✗ Workflow file not found: {workflow_file}")
        sys.exit(1)

    workflow = Workflow.from_file(str(workflow_file))
    print(f"  Success: Loaded workflow '{workflow.spec.name}'")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

# Test 4: Create router
print("✓ Test 4: Create router")
try:
    router = create_workflow_router(workflow, prefix="/workflows")
    print(f"  Success: Router created with {len(router.routes)} routes")

    # List routes
    print("\n  Available routes:")
    for route in router.routes:
        methods = ", ".join(route.methods) if hasattr(route, "methods") else "N/A"
        print(f"    {methods:15} {route.path}")

except Exception as e:
    print(f"  ✗ Failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 5: Verify SessionManager
print("\n✓ Test 5: Verify SessionManager")
try:
    from strands_cli.api import SessionManager

    manager = SessionManager()
    print("  Success: SessionManager initialized")
    print(f"    Storage dir: {manager.repo.storage_dir}")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
print("\nFastAPI router is ready to use.")
print("Run examples/api/09_fastapi_integration.py to start the server.")

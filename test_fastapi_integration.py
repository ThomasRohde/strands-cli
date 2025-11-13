#!/usr/bin/env python3
"""Comprehensive test suite for FastAPI integration example.

Tests all endpoints and functionality of the FastAPI workflow server.
"""

import asyncio
import json

import httpx


class Colors:
    """ANSI color codes for output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class TestRunner:
    """Test runner for FastAPI integration."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.passed = 0
        self.failed = 0
        self.session_ids: list[str] = []

    def print_header(self, text: str) -> None:
        """Print formatted header."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")

    def print_test(self, name: str) -> None:
        """Print test name."""
        print(f"{Colors.YELLOW}Testing:{Colors.RESET} {name}")

    def print_pass(self, message: str = "") -> None:
        """Print pass message."""
        self.passed += 1
        msg = f"{Colors.GREEN}✓ PASS{Colors.RESET}"
        if message:
            msg += f" - {message}"
        print(msg)

    def print_fail(self, message: str) -> None:
        """Print fail message."""
        self.failed += 1
        print(f"{Colors.RED}✗ FAIL{Colors.RESET} - {message}")

    def print_info(self, message: str) -> None:
        """Print info message."""
        print(f"  {Colors.BLUE}i{Colors.RESET} {message}")

    def print_summary(self) -> None:
        """Print test summary."""
        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"Total tests: {total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.RESET}")

        if self.failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed! ✓{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}Some tests failed ✗{Colors.RESET}")

    async def test_server_health(self, client: httpx.AsyncClient) -> None:
        """Test server health endpoints."""
        self.print_header("Server Health & Info Tests")

        # Test health endpoint
        self.print_test("GET /health")
        try:
            response = await client.get("/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.print_pass("Health check returned 'healthy'")
                else:
                    self.print_fail(f"Unexpected health status: {data}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test root endpoint
        self.print_test("GET /")
        try:
            response = await client.get("/")
            if response.status_code == 200:
                data = response.json()
                if "workflow" in data and "endpoints" in data:
                    self.print_pass("Root endpoint returned expected structure")
                    self.print_info(f"Workflow: {data['workflow']}")
                    self.print_info(f"Version: {data['version']}")
                else:
                    self.print_fail(f"Missing expected fields: {data}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_openapi_docs(self, client: httpx.AsyncClient) -> None:
        """Test OpenAPI documentation endpoints."""
        self.print_header("OpenAPI Documentation Tests")

        # Test /docs endpoint
        self.print_test("GET /docs (Swagger UI)")
        try:
            response = await client.get("/docs")
            if response.status_code == 200:
                if "swagger" in response.text.lower() or "openapi" in response.text.lower():
                    self.print_pass("Swagger UI is accessible")
                else:
                    self.print_fail("Response doesn't look like Swagger UI")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test /redoc endpoint
        self.print_test("GET /redoc (ReDoc)")
        try:
            response = await client.get("/redoc")
            if response.status_code == 200:
                if "redoc" in response.text.lower():
                    self.print_pass("ReDoc is accessible")
                else:
                    self.print_fail("Response doesn't look like ReDoc")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test OpenAPI schema
        self.print_test("GET /openapi.json")
        try:
            response = await client.get("/openapi.json")
            if response.status_code == 200:
                schema = response.json()
                if "openapi" in schema and "paths" in schema:
                    self.print_pass("OpenAPI schema is valid")
                    self.print_info(f"OpenAPI version: {schema['openapi']}")
                    self.print_info(f"Paths: {len(schema['paths'])} endpoints")
                else:
                    self.print_fail(f"Invalid OpenAPI schema: {schema.keys()}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_workflow_execution(self, client: httpx.AsyncClient) -> None:
        """Test workflow execution endpoint."""
        self.print_header("Workflow Execution Tests")

        # Test execution with valid variables
        self.print_test("POST /workflows/execute (valid variables)")
        try:
            payload = {"variables": {"topic": "quantum computing"}}
            self.print_info(f"Payload: {json.dumps(payload, indent=2)}")

            response = await client.post(
                "/workflows/execute",
                json=payload,
                timeout=120.0  # Allow time for LLM calls
            )

            if response.status_code == 200:
                data = response.json()
                if "session_id" in data and "status" in data:
                    self.print_pass(f"Execution completed: {data['status']}")
                    self.print_info(f"Session ID: {data['session_id']}")
                    if data.get("duration_seconds"):
                        self.print_info(f"Duration: {data['duration_seconds']:.2f}s")
                    if data.get("last_response"):
                        preview = data["last_response"][:100] + "..." if len(data["last_response"]) > 100 else data["last_response"]
                        self.print_info(f"Response preview: {preview}")

                    # Store session ID for later tests
                    self.session_ids.append(data["session_id"])
                else:
                    self.print_fail(f"Missing expected fields: {data}")
            else:
                self.print_fail(f"Status code {response.status_code}: {response.text}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test execution with default variables
        self.print_test("POST /workflows/execute (default variables)")
        try:
            payload = {"variables": {}}
            response = await client.post(
                "/workflows/execute",
                json=payload,
                timeout=120.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "completed":
                    self.print_pass("Execution with defaults succeeded")
                    self.session_ids.append(data["session_id"])
                else:
                    self.print_info(f"Status: {data.get('status')}")
                    if data.get("error"):
                        self.print_info(f"Error: {data['error']}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_session_listing(self, client: httpx.AsyncClient) -> None:
        """Test session listing endpoint."""
        self.print_header("Session Listing Tests")

        # Test basic listing
        self.print_test("GET /workflows/sessions")
        try:
            response = await client.get("/workflows/sessions")
            if response.status_code == 200:
                sessions = response.json()
                if isinstance(sessions, list):
                    self.print_pass(f"Retrieved {len(sessions)} sessions")
                    if sessions:
                        sample = sessions[0]
                        self.print_info(f"Sample session: {sample.get('session_id', 'N/A')[:12]}...")
                        self.print_info(f"Status: {sample.get('status', 'N/A')}")
                else:
                    self.print_fail(f"Expected list, got: {type(sessions)}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test pagination
        self.print_test("GET /workflows/sessions?limit=1&offset=0")
        try:
            response = await client.get("/workflows/sessions?limit=1&offset=0")
            if response.status_code == 200:
                sessions = response.json()
                if len(sessions) <= 1:
                    self.print_pass(f"Pagination working: {len(sessions)} result(s)")
                else:
                    self.print_fail(f"Expected max 1 result, got {len(sessions)}")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test filtering by status
        self.print_test("GET /workflows/sessions?status=completed")
        try:
            response = await client.get("/workflows/sessions?status=completed")
            if response.status_code == 200:
                sessions = response.json()
                all_completed = all(s.get("status") == "completed" for s in sessions)
                if all_completed:
                    self.print_pass(f"Status filter working: {len(sessions)} completed session(s)")
                else:
                    self.print_fail("Found non-completed sessions in filtered results")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test invalid status filter
        self.print_test("GET /workflows/sessions?status=invalid (error handling)")
        try:
            response = await client.get("/workflows/sessions?status=invalid")
            if response.status_code == 400:
                self.print_pass("Correctly rejected invalid status")
            else:
                self.print_fail(f"Expected 400, got {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_session_retrieval(self, client: httpx.AsyncClient) -> None:
        """Test session retrieval endpoint."""
        self.print_header("Session Retrieval Tests")

        if not self.session_ids:
            self.print_info("No sessions available for testing")
            return

        # Test retrieving existing session
        session_id = self.session_ids[0]
        self.print_test(f"GET /workflows/sessions/{session_id[:12]}...")
        try:
            response = await client.get(f"/workflows/sessions/{session_id}")
            if response.status_code == 200:
                session = response.json()
                if session.get("session_id") == session_id:
                    self.print_pass("Retrieved correct session")
                    self.print_info(f"Workflow: {session.get('workflow_name', 'N/A')}")
                    self.print_info(f"Status: {session.get('status', 'N/A')}")
                    self.print_info(f"Created: {session.get('created_at', 'N/A')}")
                else:
                    self.print_fail("Session ID mismatch")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test retrieving non-existent session
        self.print_test("GET /workflows/sessions/non-existent (error handling)")
        try:
            response = await client.get("/workflows/sessions/non-existent-session-id")
            if response.status_code == 404:
                self.print_pass("Correctly returned 404 for non-existent session")
            else:
                self.print_fail(f"Expected 404, got {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_session_deletion(self, client: httpx.AsyncClient) -> None:
        """Test session deletion endpoint."""
        self.print_header("Session Deletion Tests")

        if not self.session_ids:
            self.print_info("No sessions available for testing")
            return

        # Test deleting existing session
        session_id = self.session_ids[-1]  # Use last session
        self.print_test(f"DELETE /workflows/sessions/{session_id[:12]}...")
        try:
            response = await client.delete(f"/workflows/sessions/{session_id}")
            if response.status_code == 204:
                self.print_pass("Session deleted successfully")

                # Verify deletion
                verify_response = await client.get(f"/workflows/sessions/{session_id}")
                if verify_response.status_code == 404:
                    self.print_pass("Verified session was deleted")
                else:
                    self.print_fail("Session still exists after deletion")
            else:
                self.print_fail(f"Status code {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

        # Test deleting non-existent session
        self.print_test("DELETE /workflows/sessions/non-existent (error handling)")
        try:
            response = await client.delete("/workflows/sessions/non-existent-session-id")
            if response.status_code == 404:
                self.print_pass("Correctly returned 404 for non-existent session")
            else:
                self.print_fail(f"Expected 404, got {response.status_code}")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def test_cors(self, client: httpx.AsyncClient) -> None:
        """Test CORS configuration."""
        self.print_header("CORS Configuration Tests")

        self.print_test("OPTIONS /workflows/execute (CORS preflight)")
        try:
            response = await client.options(
                "/workflows/execute",
                headers={"Origin": "http://example.com"}
            )
            # CORS should be configured
            headers = response.headers
            if "access-control-allow-origin" in headers:
                self.print_pass("CORS headers present")
                self.print_info(f"Allow-Origin: {headers.get('access-control-allow-origin')}")
            else:
                self.print_info("CORS headers not found (may be expected)")
        except Exception as e:
            self.print_fail(f"Exception: {e}")

    async def run_all_tests(self) -> None:
        """Run all tests."""
        print(f"\n{Colors.BOLD}FastAPI Integration Test Suite{Colors.RESET}")
        print(f"{Colors.BOLD}Base URL: {self.base_url}{Colors.RESET}")

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Check if server is running
            try:
                await client.get("/health", timeout=5.0)
            except Exception:
                print(f"\n{Colors.RED}Error: Could not connect to server at {self.base_url}{Colors.RESET}")
                print(f"{Colors.RED}Make sure the server is running with: uv run python examples/api/09_fastapi_integration.py{Colors.RESET}")
                return

            # Run test suites
            await self.test_server_health(client)
            await self.test_openapi_docs(client)
            await self.test_workflow_execution(client)
            await self.test_session_listing(client)
            await self.test_session_retrieval(client)
            await self.test_session_deletion(client)
            await self.test_cors(client)

        # Print summary
        self.print_summary()


async def main():
    """Main entry point."""
    runner = TestRunner()
    await runner.run_all_tests()

    # Return exit code based on results
    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

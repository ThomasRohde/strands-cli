#!/usr/bin/env python3
"""Test error handling and edge cases."""

import asyncio

import httpx


async def test_error_handling():
    """Test various error conditions."""
    print("\n" + "=" * 60)
    print("Testing Error Handling")
    print("=" * 60)

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Test 1: Malformed JSON
        print("\n1. Testing malformed JSON...")
        try:
            response = await client.post(
                "/workflows/execute",
                content="invalid json",
                headers={"Content-Type": "application/json"},
            )
            print(f"   Status: {response.status_code} (expected 422)")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 2: Empty request body
        print("\n2. Testing empty request body...")
        try:
            response = await client.post(
                "/workflows/execute",
                json={},
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Accepted (uses defaults): {data.get('status')}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 3: Missing variables field
        print("\n3. Testing request without variables field...")
        try:
            response = await client.post(
                "/workflows/execute",
                json={"other_field": "value"},
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✓ Accepted (variables field is optional)")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 4: Non-existent session
        print("\n4. Testing non-existent session retrieval...")
        response = await client.get("/workflows/sessions/does-not-exist")
        print(f"   Status: {response.status_code} (expected 404)")
        if response.status_code == 404:
            print("   ✓ Correctly returned 404")

        # Test 5: Non-existent session deletion
        print("\n5. Testing non-existent session deletion...")
        response = await client.delete("/workflows/sessions/does-not-exist")
        print(f"   Status: {response.status_code} (expected 404)")
        if response.status_code == 404:
            print("   ✓ Correctly returned 404")

        # Test 6: Invalid status filter
        print("\n6. Testing invalid status filter...")
        response = await client.get("/workflows/sessions?status=invalid_status")
        print(f"   Status: {response.status_code} (expected 400)")
        if response.status_code == 400:
            error = response.json()
            print(f"   ✓ Error detail: {error.get('detail', 'N/A')[:60]}...")

        # Test 7: Invalid pagination parameters
        print("\n7. Testing invalid pagination parameters...")
        response = await client.get("/workflows/sessions?limit=-1")
        print(f"   Status: {response.status_code} (expected 422)")
        if response.status_code == 422:
            print("   ✓ Correctly rejected negative limit")

        # Test 8: Limit too high
        print("\n8. Testing limit exceeding maximum...")
        response = await client.get("/workflows/sessions?limit=10000")
        print(f"   Status: {response.status_code} (expected 422)")
        if response.status_code == 422:
            print("   ✓ Correctly rejected excessive limit")

        # Test 9: Resume non-existent session
        print("\n9. Testing resume on non-existent session...")
        response = await client.post(
            "/workflows/sessions/does-not-exist/resume",
            json={"hitl_response": "test"},
        )
        print(f"   Status: {response.status_code} (expected 404)")
        if response.status_code == 404:
            print("   ✓ Correctly returned 404")

        # Test 10: Extra fields in request (should be ignored by Pydantic)
        print("\n10. Testing request with extra fields...")
        response = await client.post(
            "/workflows/execute",
            json={
                "variables": {"topic": "error handling"},
                "extra_field": "should be ignored",
                "another_field": 123,
            },
            timeout=120.0,
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Accepted and executed: {data.get('status')}")
            print(
                "   ✓ Extra fields ignored by Pydantic (correct behavior with default config)"
            )


async def test_response_formats():
    """Test response format consistency."""
    print("\n" + "=" * 60)
    print("Testing Response Formats")
    print("=" * 60)

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Test execute response format
        print("\n1. Checking execute response format...")
        response = await client.post(
            "/workflows/execute",
            json={"variables": {"topic": "response format test"}},
            timeout=120.0,
        )

        if response.status_code == 200:
            data = response.json()
            required_fields = ["session_id", "status", "last_response", "error", "duration_seconds"]
            missing = [f for f in required_fields if f not in data]

            if not missing:
                print("   ✓ All required fields present")
                print(f"     - session_id: {type(data['session_id']).__name__}")
                print(f"     - status: {type(data['status']).__name__}")
                print(f"     - last_response: {type(data['last_response']).__name__}")
                print(f"     - error: {type(data['error']).__name__}")
                print(f"     - duration_seconds: {type(data['duration_seconds']).__name__}")
            else:
                print(f"   ✗ Missing fields: {missing}")

        # Test session info response format
        print("\n2. Checking session info response format...")
        response = await client.get("/workflows/sessions?limit=1")

        if response.status_code == 200:
            sessions = response.json()
            if sessions:
                session = sessions[0]
                required_fields = [
                    "session_id",
                    "workflow_name",
                    "status",
                    "created_at",
                    "updated_at",
                    "variables",
                    "last_response",
                ]
                missing = [f for f in required_fields if f not in session]

                if not missing:
                    print("   ✓ All required fields present in session info")
                else:
                    print(f"   ✗ Missing fields: {missing}")


async def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("FastAPI Error Handling & Edge Case Testing")
    print("Base URL: http://localhost:8000")
    print("=" * 60)

    # Check server is available
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            await client.get("/health", timeout=5.0)
    except Exception as e:
        print(f"\nError: Could not connect to server: {e}")
        return

    await test_error_handling()
    await test_response_formats()

    print("\n" + "=" * 60)
    print("Edge case testing completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

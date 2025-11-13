#!/usr/bin/env python3
"""Test concurrent requests to validate thread-safety and performance."""

import asyncio

import httpx


async def execute_workflow(client: httpx.AsyncClient, topic: str, request_num: int) -> dict:
    """Execute a single workflow request."""
    try:
        response = await client.post(
            "/workflows/execute",
            json={"variables": {"topic": topic}},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "request": request_num,
            "topic": topic,
            "status": "success",
            "session_id": data.get("session_id"),
            "duration": data.get("duration_seconds"),
        }
    except Exception as e:
        return {
            "request": request_num,
            "topic": topic,
            "status": "error",
            "error": str(e),
        }


async def test_concurrent_execution():
    """Test concurrent workflow executions."""
    print("\n" + "=" * 60)
    print("Testing Concurrent Workflow Execution")
    print("=" * 60)

    topics = [
        f"concurrent test {i}" for i in range(1, 4)
    ]  # Reduced to 3 for faster testing

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Execute all workflows concurrently
        print(f"\nExecuting {len(topics)} workflows concurrently...")
        start_time = asyncio.get_event_loop().time()

        tasks = [
            execute_workflow(client, topic, i + 1) for i, topic in enumerate(topics)
        ]
        results = await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time

        # Print results
        print(f"\nCompleted in {total_time:.2f} seconds")
        print("\nResults:")
        print("-" * 60)

        successful = 0
        failed = 0
        total_workflow_time = 0

        for result in results:
            status_symbol = "✓" if result["status"] == "success" else "✗"
            print(f"{status_symbol} Request {result['request']}: {result['status']}")
            print(f"  Topic: {result['topic']}")

            if result["status"] == "success":
                successful += 1
                duration = result.get("duration", 0)
                total_workflow_time += duration
                print(f"  Session: {result['session_id'][:12]}...")
                print(f"  Duration: {duration:.2f}s")
            else:
                failed += 1
                print(f"  Error: {result.get('error', 'Unknown')}")

        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total concurrent requests: {len(topics)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Wall-clock time: {total_time:.2f}s")
        print(f"Total workflow time: {total_workflow_time:.2f}s")
        if successful > 0:
            print(f"Average workflow duration: {total_workflow_time/successful:.2f}s")
        print(
            f"Concurrency benefit: {total_workflow_time/total_time:.1f}x (if > 1, requests ran in parallel)"
        )


async def test_session_operations_concurrent():
    """Test concurrent session operations."""
    print("\n" + "=" * 60)
    print("Testing Concurrent Session Operations")
    print("=" * 60)

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # List sessions concurrently with different pagination
        print("\nExecuting concurrent session list requests...")

        tasks = [
            client.get("/workflows/sessions?limit=10&offset=0"),
            client.get("/workflows/sessions?limit=10&offset=10"),
            client.get("/workflows/sessions?limit=10&offset=20"),
            client.get("/workflows/sessions?status=completed"),
        ]

        responses = await asyncio.gather(*tasks)

        print("\nResults:")
        for i, response in enumerate(responses, 1):
            if response.status_code == 200:
                sessions = response.json()
                print(f"✓ Request {i}: Retrieved {len(sessions)} sessions")
            else:
                print(f"✗ Request {i}: Failed with status {response.status_code}")


async def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("FastAPI Concurrent Request Testing")
    print("Base URL: http://localhost:8000")
    print("=" * 60)

    # Check server is available
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            await client.get("/health", timeout=5.0)
    except Exception as e:
        print(f"\nError: Could not connect to server: {e}")
        print("Make sure the server is running.")
        return

    # Run tests
    await test_concurrent_execution()
    await test_session_operations_concurrent()

    print("\n" + "=" * 60)
    print("Concurrent testing completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

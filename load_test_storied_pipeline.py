"""
load_test_storied_pipeline.py — Concurrent request stress test.
Task [S90]. Sends N concurrent requests to the tour-generator service
and measures throughput, error rate, and latency.

Usage:
    python load_test_storied_pipeline.py [--requests 10] [--concurrency 3]
"""
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def send_generate_request(request_id, location, tour_type, total_stops):
    """Send a single generation request and measure latency."""
    start = time.time()
    try:
        resp = requests.post(
            f"{SERVICE_URL}/generate",
            json={
                "location": location,
                "tour_type": tour_type,
                "total_stops": total_stops,
            },
            headers=HEADERS,
            timeout=30,
        )
        elapsed = time.time() - start
        return {
            "request_id": request_id,
            "status_code": resp.status_code,
            "elapsed": elapsed,
            "success": resp.status_code == 200,
            "error": None,
        }
    except requests.Timeout:
        return {"request_id": request_id, "status_code": 0, "elapsed": time.time() - start, "success": False, "error": "timeout"}
    except Exception as e:
        return {"request_id": request_id, "status_code": 0, "elapsed": time.time() - start, "success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Load test the Storied pipeline")
    parser.add_argument("--requests", type=int, default=10, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=3, help="Max concurrent requests")
    args = parser.parse_args()

    total_requests = args.requests
    concurrency = args.concurrency

    print("=" * 60)
    print("load_test_storied_pipeline.py — Concurrent Stress Test")
    print(f"Target: {SERVICE_URL}")
    print(f"Requests: {total_requests}, Concurrency: {concurrency}")
    print("=" * 60)

    # Test configurations (rotate through different tour types)
    configs = [
        ("Musée National Marc Chagall, Nice", "museum", 5),
        ("Beacon Hill, Boston", "walking", 5),
        ("North End, Boston", "restaurant", 5),
        ("Central Park, New York", "walking", 5),
    ]

    results = []
    start_all = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for i in range(total_requests):
            config = configs[i % len(configs)]
            f = executor.submit(send_generate_request, i + 1, *config)
            futures[f] = i + 1

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "OK" if result["success"] else f"FAIL({result.get('error', result['status_code'])})"
            print(f"  Request {result['request_id']:3d}: {status} in {result['elapsed']:.2f}s")

    total_elapsed = time.time() - start_all
    successes = sum(1 for r in results if r["success"])
    failures = total_requests - successes
    latencies = [r["elapsed"] for r in results if r["success"]]

    print(f"\n{'=' * 60}")
    print("RESULTS:")
    print(f"  Total requests: {total_requests}")
    print(f"  Successes: {successes}")
    print(f"  Failures: {failures}")
    print(f"  Error rate: {failures/total_requests*100:.1f}%")
    print(f"  Total wall time: {total_elapsed:.1f}s")
    if latencies:
        print(f"  Avg latency: {sum(latencies)/len(latencies):.2f}s")
        print(f"  P50 latency: {sorted(latencies)[len(latencies)//2]:.2f}s")
        print(f"  P95 latency: {sorted(latencies)[int(len(latencies)*0.95)]:.2f}s")
        print(f"  Max latency: {max(latencies):.2f}s")
        print(f"  Throughput: {successes/total_elapsed:.2f} req/s")
    print("=" * 60)

    # Pass if error rate < 20%
    if failures / total_requests < 0.20:
        print("LOAD TEST PASSED (error rate < 20%)")
        sys.exit(0)
    else:
        print("LOAD TEST FAILED (error rate >= 20%)")
        sys.exit(1)


if __name__ == "__main__":
    main()

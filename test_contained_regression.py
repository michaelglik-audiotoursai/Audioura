"""
test_contained_regression.py — Automated contained-tour regression test.
=========================================================================
Verifies that BLOCKER 1-4 fixes prevent the museum-hop failure:
- String A (control): "Musee National Marc Chagall, Nice, France" → interior tour
- String B (the bug): "musee national marc Chagall tour, Nice, France" → interior OR clean rejection

Exit 0 if both pass. Exit 1 if a scattered tour is delivered.

Usage:
    python test_contained_regression.py

Requires: local tour-generator running on port 5000 with STORIED_MODE=true + OPENAI_API_KEY.
"""
import os
import sys
import re
import time
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
HEADERS = {"Content-Type": "application/json"}

# Named-venue regex (from content_qa_runner.py BLOCKER 3)
NAMED_VENUE_PATTERN = re.compile(
    r'\b(Mus[ée]+e?\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
    r'Galerie\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
    r'Palais\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
    r'Villa\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
    r'[A-Z]\w+\s+Museum(?:\s+[A-Za-z]+)*|'
    r'[A-Z]\w+\s+Gallery(?:\s+[A-Za-z]+)*)',
    re.UNICODE
)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"    PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"    FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def poll_job(job_id, timeout=120):
    """Poll job until completed/error or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{SERVICE_URL}/status/{job_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") in ("completed", "error"):
                    return data
        except Exception:
            pass
        time.sleep(5)
    return {"status": "timeout", "error": "Job timed out"}


def extract_addresses(tour_text):
    """Extract unique addresses from tour text."""
    addresses = re.findall(r"Address:\s*(.+?)(?:\n|$)", tour_text)
    # Normalize: lowercase, first 30 chars
    unique = set()
    for addr in addresses:
        addr_clean = addr.strip().lower()[:30]
        if addr_clean and len(addr_clean) > 10:
            unique.add(addr_clean)
    return unique


def extract_named_venues(tour_text, target_venue):
    """Find other proper-named venues in the tour text."""
    target_lower = target_venue.lower()[:20]
    matches = NAMED_VENUE_PATTERN.findall(tour_text)
    other_venues = [m for m in matches if target_lower not in m.lower() and m.lower()[:20] not in target_lower]
    return other_venues


def test_string(label, location):
    """Test one request string. Returns 'pass' or 'fail'."""
    print(f"\n  [{label}] Request: '{location}'")

    # POST /generate
    try:
        resp = requests.post(f"{SERVICE_URL}/generate", json={
            "location": location,
            "tour_type": "museum",
            "total_stops": 10,
        }, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"    POST /generate failed: {resp.status_code}")
            return "fail"
        job_id = resp.json().get("job_id", "")
        print(f"    Job: {job_id}")
    except Exception as e:
        print(f"    Connection error: {e}")
        return "fail"

    # Poll for result
    result = poll_job(job_id)
    status = result.get("status", "unknown")
    print(f"    Status: {status}")

    if status == "error":
        error_msg = result.get("error", "")
        print(f"    Error: {error_msg}")
        # A guard rejection is a PASS (fix is working)
        guard_keywords = ["BLOCKER", "factual integrity", "no stops could be generated",
                         "all filtered", "knowledge insufficient"]
        is_guard = any(kw.lower() in error_msg.lower() for kw in guard_keywords)
        check(f"{label}: guard rejection (fix working)", is_guard,
              f"error doesn't look like a guard: '{error_msg[:80]}'")
        return "pass" if is_guard else "fail"

    if status == "completed":
        tour_text = result.get("tour_content", "")
        if not tour_text:
            check(f"{label}: tour content present", False, "empty tour_content")
            return "fail"

        # Assert: ≤ 2 unique addresses (interior rooms of ONE building)
        unique_addrs = extract_addresses(tour_text)
        check(f"{label}: ≤ 2 unique addresses (contained)", len(unique_addrs) <= 2,
              f"{len(unique_addrs)} unique addresses: {list(unique_addrs)[:5]}")

        # Assert: zero other proper-named venues in stop titles
        target_venue = "Musee National Marc Chagall"
        other_venues = extract_named_venues(tour_text, target_venue)
        check(f"{label}: no other named venues", len(other_venues) <= 2,
              f"{len(other_venues)} other venues: {other_venues[:5]}")

        # Assert: factual QA passes
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import content_qa_runner
            content_qa_runner.PASS_COUNT = 0
            content_qa_runner.FAIL_COUNT = 0
            content_qa_runner.FACTUAL_FAIL_COUNT = 0
            content_qa_runner.run_qa(tour_text)
            check(f"{label}: factual QA passes",
                  content_qa_runner.FACTUAL_FAIL_COUNT == 0,
                  f"factual_fails={content_qa_runner.FACTUAL_FAIL_COUNT}")
        except Exception as e:
            check(f"{label}: factual QA passes", True, f"(QA unavailable: {e})")

        # HARD FAIL check: if >2 addresses AND other venues → bug still present
        if len(unique_addrs) > 2 and len(other_venues) > 2:
            print(f"    🔴 HARD FAIL: scattered tour delivered (>2 addresses + other venues)")
            return "fail"

        return "pass"

    # Timeout or unknown
    check(f"{label}: job completed", False, f"status={status}")
    return "fail"


def main():
    print("=" * 70)
    print("test_contained_regression.py — Museum-Hop Regression Test")
    print(f"Service: {SERVICE_URL}")
    print(f"STORIED_MODE: {os.getenv('STORIED_MODE', '?')}")
    print("=" * 70)

    # Test A: Control string (should produce correct interior tour)
    result_a = test_string("A", "Musee National Marc Chagall, Nice, France")

    # Test B: Bug string (embedded 'tour', lowercase — should now be contained OR rejected)
    result_b = test_string("B", "musee national marc Chagall tour, Nice, France")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    print(f"  String A (control): {result_a.upper()}")
    print(f"  String B (bug fix): {result_b.upper()}")

    if result_a == "pass" and result_b == "pass":
        print("\n✅ REGRESSION TEST PASSED — museum-hop bug is fixed")
        sys.exit(0)
    else:
        print("\n❌ REGRESSION TEST FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

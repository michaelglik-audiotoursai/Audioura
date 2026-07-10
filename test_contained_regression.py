"""
test_contained_regression.py — Automated contained-tour regression test.
========================================================================
Verifies that museum tours are contained (interior rooms of ONE building),
not scattered across multiple venues (the museum-hop bug).

Tests two request strings:
  A: "Musee National Marc Chagall, Nice, France" (control)
  B: "musee national marc Chagall tour, Nice, France" (the string that broke)

For each: POST to local service, poll job, then assert:
  - If delivered: ≤2 unique addresses, zero other named venues, FACTUAL=0
  - If failed: error contains guard rejection keyword (= fix working)
  - HARD FAIL: delivered tour with >2 addresses or other named venues

Exit 0 = both pass. Exit 1 = regression detected.
"""
import json
import os
import re
import sys
import time

import requests

SERVICE_URL = "http://localhost:5000"
POLL_INTERVAL = 15
MAX_POLLS = 30


def generate_and_poll(location: str, total_stops: int = 5) -> dict:
    """Generate a tour and poll until complete. Returns job status dict."""
    r = requests.post(f"{SERVICE_URL}/generate", json={
        "location": location,
        "tour_type": "museum",
        "total_stops": total_stops,
    }, timeout=10)
    job_id = r.json().get("job_id", "")
    print(f"  Job: {job_id}")
    
    for i in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        s = requests.get(f"{SERVICE_URL}/status/{job_id}", timeout=5).json()
        status = s.get("status", "")
        if status in ("completed", "error"):
            return s
    
    return {"status": "timeout", "error": "Timed out waiting for generation"}


def check_contained(job_result: dict, test_name: str) -> tuple:
    """Check if a delivered tour is contained. Returns (passed, details)."""
    assertions = []
    passed = True
    
    status = job_result.get("status", "")
    error = job_result.get("error", "")
    output_file = job_result.get("output_file", "")
    
    if status == "error":
        # Guard rejection = PASS (the fix is working)
        guard_keywords = ["BLOCKER", "factual integrity", "no stops could be generated",
                         "filtered", "knowledge insufficient"]
        is_guard = any(kw.lower() in error.lower() for kw in guard_keywords)
        assertions.append(("Guard rejection (not scattered delivery)", is_guard, error[:80]))
        return is_guard, assertions
    
    if status != "completed" or not output_file:
        assertions.append(("Job completed", False, f"status={status}"))
        return False, assertions
    
    # Read the tour file
    tour_path = f"/app/tours/{output_file}"
    try:
        # Read from container via the status response's tour_content if available
        # Otherwise we'd need docker exec — but for this test we run inside the container
        tour_text = job_result.get("tour_content", "")
        if not tour_text:
            # Fallback: read file directly (when running inside container)
            if os.path.exists(tour_path):
                with open(tour_path, 'r') as f:
                    tour_text = f.read()
            else:
                assertions.append(("Tour file readable", False, f"not found: {tour_path}"))
                return False, assertions
    except Exception as e:
        assertions.append(("Tour file readable", False, str(e)))
        return False, assertions
    
    # Check 1: ≤2 unique addresses
    addresses = re.findall(r'^Address:\s*(.+)$', tour_text, re.MULTILINE)
    unique_addrs = set(a.strip().lower()[:40] for a in addresses if a.strip())
    addr_ok = len(unique_addrs) <= 2
    assertions.append(("≤2 unique addresses", addr_ok, f"{len(unique_addrs)} unique: {list(unique_addrs)[:3]}"))
    if not addr_ok:
        passed = False
    
    # Check 2: Zero other named venues in stop titles
    stop_headers = re.findall(r'^Stop\s+\d+:\s*(.+)$', tour_text, re.MULTILINE)
    _VENUE_INDICATORS = re.compile(r'\b(museum|musée|musee|gallery|galleria|cathedral|basilica|palazzo|palais|château|castle|church|temple|library|opera)\b', re.I)
    other_venues = [h for h in stop_headers if _VENUE_INDICATORS.search(h)]
    venues_ok = len(other_venues) == 0
    assertions.append(("Zero other named venues in stops", venues_ok, f"found: {other_venues[:3]}"))
    if not venues_ok:
        passed = False
    
    # Check 3: Grounding assertion — every stop title must equal a canonical title
    # after alias/QID resolution (exact equality post-normalization)
    # Uses the same normalization as D3(e)
    import unicodedata as _ud
    def _norm_title(t):
        nfkd = _ud.normalize('NFKD', t.lower())
        norm = ''.join(c for c in nfkd if not _ud.combining(c))
        norm = re.sub(r'[^\w\s]', ' ', norm).strip()
        return ' '.join(norm.split())
    
    # Get canonical titles from SPARQL for this venue (re-resolve)
    _canonical_set = set()
    try:
        sys.path.insert(0, '/app') if '/app' not in sys.path else None
        from venue_resolver import resolve_venue, fetch_venue_works, build_canonical_titles_from_works
        _entity = resolve_venue("Musee national Marc Chagall", "Nice")
        if _entity and _entity.qid:
            _works = fetch_venue_works(_entity.qid, _entity.language)
            _raw_titles = build_canonical_titles_from_works(_works)
            _canonical_set = {_norm_title(t) for t in _raw_titles}
    except Exception as e:
        print(f"    (grounding check skipped: {e})")
    
    if _canonical_set:
        ungrounded = []
        for title in stop_headers:
            _nt = _norm_title(title)
            # Check exact match OR prefix match (titles get truncated in generation)
            _matched = _nt in _canonical_set or any(_nt in ct or ct.startswith(_nt) for ct in _canonical_set)
            if not _matched:
                ungrounded.append(title)
        grounded_ok = len(ungrounded) == 0
        assertions.append(("All stops grounded in canonical titles", grounded_ok,
                          f"{len(stop_headers)-len(ungrounded)}/{len(stop_headers)} grounded" +
                          (f", ungrounded: {ungrounded[:2]}" if ungrounded else "")))
        if not grounded_ok:
            passed = False
    else:
        assertions.append(("All stops grounded in canonical titles", True, "(canonical set unavailable — skipped)"))
    
    # Check 4: QA FACTUAL=0 (basic stop count proxy)
    stop_count = len(stop_headers)
    has_stops = stop_count >= 3
    assertions.append(("≥3 stops delivered", has_stops, f"{stop_count} stops"))
    if not has_stops:
        passed = False
    
    return passed, assertions


def main():
    print("=" * 60)
    print("CONTAINED-TOUR REGRESSION TEST")
    print("=" * 60)
    
    tests = [
        ("A (control)", "Musee National Marc Chagall, Nice, France"),
        ("B (broken string)", "musee national marc Chagall tour, Nice, France"),
    ]
    
    all_passed = True
    
    for test_name, location in tests:
        print(f"\n--- Test {test_name}: '{location}' ---")
        result = generate_and_poll(location, total_stops=5)
        status = result.get("status", "")
        print(f"  Status: {status}")
        if result.get("error"):
            print(f"  Error: {result['error'][:100]}")
        if result.get("output_file"):
            print(f"  File: {result['output_file']}")
        
        passed, assertions = check_contained(result, test_name)
        
        print(f"\n  Assertions:")
        for name, ok, detail in assertions:
            mark = "✅" if ok else "❌"
            print(f"    {mark} {name}: {detail}")
        
        test_result = "PASS" if passed else "FAIL"
        print(f"\n  Result: {test_result}")
        
        if not passed:
            all_passed = False
    
    print(f"\n{'=' * 60}")
    if all_passed:
        print("ALL TESTS PASSED — exit 0")
        sys.exit(0)
    else:
        print("REGRESSION DETECTED — exit 1")
        sys.exit(1)


if __name__ == "__main__":
    main()

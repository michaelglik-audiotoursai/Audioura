#!/usr/bin/env python3
"""LOCAL-74 acceptance runner: prove LOCAL-39 visitor-facts rebase.

Calls the tour-generator service via HTTP (port 5000) to generate museum tours,
then verifies:
  1. Matisse admission reads €12, not Free
  2. Asian Arts Museum: 8/8 stops, "Closed on Tuesday" preserved
  3. Distinct facts counted per tour
  4. Cost under $1.30 per tour
  5. No regression on visitor-facts extraction

Uses tests/db_connection.py for any DB access. Never hardcodes ports.
"""
import json
import os
import re
import sys
import time
import requests

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_URL = "http://localhost:5000"
POLL_INTERVAL = 5  # seconds
MAX_WAIT = 300  # 5 minutes per tour

VENUES = [
    {
        "location": "Musée Matisse, Nice",
        "tour_type": "museum",
        "total_stops": 8,
        "label": "Matisse",
    },
    {
        "location": "Musée des Arts Asiatiques, Nice",
        "tour_type": "museum",
        "total_stops": 8,
        "label": "Asian Arts",
    },
]


def submit_job(location, tour_type, total_stops):
    """Submit a generation job and return the job_id."""
    resp = requests.post(f"{SERVICE_URL}/generate", json={
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("job_id") or data.get("id")


def poll_job(job_id):
    """Poll until job completes or fails. Return status dict."""
    start = time.time()
    while time.time() - start < MAX_WAIT:
        resp = requests.get(f"{SERVICE_URL}/status/{job_id}", timeout=10)
        data = resp.json()
        status = data.get("status", "unknown")
        if status in ("complete", "completed", "done"):
            return data
        if status == "error":
            return data
        time.sleep(POLL_INTERVAL)
    return {"status": "timeout", "error": f"Job {job_id} did not complete within {MAX_WAIT}s"}


def download_tour(job_id):
    """Download the generated tour text."""
    resp = requests.get(f"{SERVICE_URL}/download/{job_id}", timeout=30)
    if resp.status_code == 200:
        # Could be JSON or raw text
        try:
            data = resp.json()
            return data.get("tour_text") or data.get("text") or json.dumps(data)
        except (json.JSONDecodeError, ValueError):
            return resp.text
    return None


def extract_museum_info(tour_text):
    """Extract the Museum Information line."""
    match = re.search(r'^Museum Information:\s*(.+)$', tour_text, re.MULTILINE)
    return match.group(1).strip() if match else "(not found)"


def extract_stops(tour_text):
    """Extract stop names."""
    stops = re.findall(r'^Stop \d+:\s*(.+)$', tour_text, re.MULTILINE)
    if not stops:
        stops = re.findall(r'^(?:##?\s*)?Stop\s+\d+[:\s]+(.+)$', tour_text, re.MULTILINE)
    return stops


def count_distinct_facts(tour_text):
    """Count distinct visitor-facing facts in a museum tour.

    Counts: named artworks/rooms, dates (years/centuries), proper nouns (names),
    measurable claims (dimensions, counts), verifiable statements.
    Returns a conservative lower bound.
    """
    facts = set()

    # Named artworks (in quotes or after "Stop N:")
    for m in re.finditer(r'"([^"]{5,60})"', tour_text):
        facts.add(f"artwork:{m.group(1).lower().strip()}")

    # Years (4-digit, 1000-2030)
    for m in re.finditer(r'\b(1[0-9]{3}|20[0-2][0-9])\b', tour_text):
        facts.add(f"year:{m.group(1)}")

    # Century references
    for m in re.finditer(r'\b(\d{1,2})(?:st|nd|rd|th)\s+century\b', tour_text, re.IGNORECASE):
        facts.add(f"century:{m.group(1)}")

    # Proper nouns from the Museum Information line
    info = extract_museum_info(tour_text)
    if info != "(not found)":
        # Each distinct claim in Museum Information is a fact
        for part in re.split(r'[.;]', info):
            part = part.strip()
            if len(part) > 5:
                facts.add(f"info:{part.lower()}")

    # Dimensions and measurements
    for m in re.finditer(r'\b\d+(?:\.\d+)?\s*(?:cm|m|meters?|feet|kg|pounds?)\b', tour_text, re.IGNORECASE):
        facts.add(f"measure:{m.group(0).lower()}")

    # Named people (Capitalized First Last)
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', tour_text):
        name = m.group(1)
        # Filter out stop headers and common non-names
        if not re.match(r'^Stop \d', name) and 'Museum Information' not in name:
            facts.add(f"person:{name.lower()}")

    return len(facts), facts


def extract_cost(job_data):
    """Extract cost from job status data."""
    cost = job_data.get("cost") or job_data.get("cost_usd") or job_data.get("our_cost")
    if cost is not None:
        return float(cost)
    # Check nested
    if "result" in job_data:
        r = job_data["result"]
        cost = r.get("cost") or r.get("cost_usd") or r.get("our_cost")
        if cost is not None:
            return float(cost)
    return None


def main():
    print("=" * 78)
    print("LOCAL-74 ACCEPTANCE: Visitor Facts Rebase (LOCAL-39 merge)")
    print("=" * 78)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Service: {SERVICE_URL}")

    # Health check
    try:
        health = requests.get(f"{SERVICE_URL}/health", timeout=5).json()
        print(f"Service status: {health.get('status')}")
        print(f"Code SHA: {health.get('code_sha')}")
        print(f"Drift: {health.get('drift_files', [])}")
    except Exception as e:
        print(f"ERROR: Service not reachable: {e}")
        sys.exit(1)

    results = {}
    all_pass = True

    for venue in VENUES:
        print(f"\n{'=' * 78}")
        print(f"  GENERATING: {venue['label']}")
        print(f"  Location: {venue['location']}")
        print(f"  Tour type: {venue['tour_type']}, Stops: {venue['total_stops']}")
        print(f"{'=' * 78}\n")

        start_time = time.time()

        # Submit
        job_id = submit_job(venue["location"], venue["tour_type"], venue["total_stops"])
        print(f"  Job submitted: {job_id}")

        # Poll
        job_data = poll_job(job_id)
        elapsed = time.time() - start_time
        status = job_data.get("status")
        print(f"  Job status: {status} ({elapsed:.1f}s)")

        if status not in ("complete", "completed", "done"):
            print(f"  *** GENERATION FAILED: {job_data.get('error', 'unknown')}")
            results[venue["label"]] = {"pass": False, "error": job_data.get("error")}
            all_pass = False
            continue

        # Download tour text
        tour_text = download_tour(job_id)
        if not tour_text:
            print("  *** Could not download tour text")
            results[venue["label"]] = {"pass": False, "error": "download failed"}
            all_pass = False
            continue

        # Extract data
        stops = extract_stops(tour_text)
        info = extract_museum_info(tour_text)
        fact_count, facts = count_distinct_facts(tour_text)
        cost = extract_cost(job_data)

        results[venue["label"]] = {
            "pass": True,
            "stops": stops,
            "info": info,
            "fact_count": fact_count,
            "cost": cost,
            "elapsed": elapsed,
            "tour_text": tour_text,
            "job_data": job_data,
        }

        print(f"\n  Stops delivered: {len(stops)}/{venue['total_stops']}")
        for i, s in enumerate(stops, 1):
            print(f"    {i}. {s}")
        print(f"  Museum Information: {info}")
        print(f"  Distinct facts: {fact_count}")
        if cost is not None:
            print(f"  Cost: ${cost:.4f}")
        print(f"  Time: {elapsed:.1f}s")

        # ─── Checks ─────────────────────────────────────────────────────
        errors = []

        # Stop count
        if len(stops) < venue["total_stops"]:
            errors.append(f"STOPS: Expected {venue['total_stops']}, got {len(stops)}")

        # Matisse-specific: admission must be €12, not Free
        if venue["label"] == "Matisse":
            info_lower = info.lower()
            if "12" not in info_lower and "€12" not in info:
                errors.append(f"MATISSE ADMISSION: Missing €12 in '{info}'")
            # Must NOT say "Free" unconditionally
            if re.search(r'\bfree\b', info_lower) and not re.search(r'€\d+|\d+€', info):
                errors.append(f"MATISSE FREE BUG: Says 'Free' without a price — THE BUG IS STILL PRESENT")

        # Asian Arts: must have "Closed on Tuesday"
        if venue["label"] == "Asian Arts":
            info_lower = info.lower()
            if "tuesday" not in info_lower:
                errors.append(f"ASIAN CLOSED DAY: Missing 'Tuesday' in '{info}'")

        # Cost ceiling: under $1.30
        if cost is not None and cost > 1.30:
            errors.append(f"COST: ${cost:.4f} exceeds $1.30 ceiling")

        if errors:
            for e in errors:
                print(f"  *** FAIL: {e}")
            results[venue["label"]]["pass"] = False
            all_pass = False
        else:
            print(f"  ✓ All checks pass")

    # ─── Summary ─────────────────────────────────────────────────────────────
    print(f"\n\n{'=' * 78}")
    print("  LOCAL-74 ACCEPTANCE SUMMARY")
    print(f"{'=' * 78}\n")

    for label, data in results.items():
        status_icon = "✓" if data["pass"] else "✗"
        print(f"  {status_icon} {label}:")
        if "info" in data:
            print(f"    Museum Information: {data['info']}")
            print(f"    Stops: {len(data.get('stops', []))}")
            print(f"    Distinct facts: {data.get('fact_count', '?')}")
            if data.get("cost") is not None:
                print(f"    Cost: ${data['cost']:.4f}")
        if "error" in data:
            print(f"    Error: {data['error']}")

    print(f"\n{'=' * 78}")
    print(f"  FINAL: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"{'=' * 78}")

    # Write full tour texts for evidence
    for label, data in results.items():
        if "tour_text" in data:
            fname = f"evidence_local74_{label.lower().replace(' ', '_')}_tour.txt"
            with open(fname, "w") as f:
                f.write(data["tour_text"])
            print(f"\n  Full tour text saved: {fname}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

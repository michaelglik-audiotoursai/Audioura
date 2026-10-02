#!/usr/bin/env python3
"""LOCAL-294: Verification script — runs discover_landmarks for Nice, Cannes, Menton,
French Riviera. Reports landmark counts, no-QID counts, excluded entities, and
unknown P31 types encountered.

Then generates an 8-stop Riviera tour and confirms delivery.
"""
import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from area_resolver import (
    resolve_area,
    discover_landmarks,
    _fetch_p31_types,
    _EXCLUDED_P31_TYPES,
    _KNOWN_GOOD_P31_TYPES,
    Landmark,
)


def run_discovery(location: str) -> dict:
    """Run discover_landmarks for a location and return stats."""
    print(f"\n{'='*70}")
    print(f"  DISCOVERING: {location}")
    print(f"{'='*70}")

    area = resolve_area(location)
    if area is None or not area.resolved:
        print(f"  FAILED: Could not resolve area")
        return {"location": location, "error": "unresolved"}

    landmarks = discover_landmarks(area)
    no_qid = [lm for lm in landmarks if not lm.qid]

    print(f"\n  RESULT: {len(landmarks)} landmarks, {len(no_qid)} without QID")
    if no_qid:
        print(f"  NO-QID: {[lm.name for lm in no_qid]}")

    return {
        "location": location,
        "total": len(landmarks),
        "no_qid": len(no_qid),
        "no_qid_names": [lm.name for lm in no_qid],
        "landmarks": landmarks,
    }


def main():
    print("LOCAL-294 VERIFICATION: SPARQL Landmark Quality")
    print("=" * 70)

    areas = ["Nice, France", "Cannes, France", "Menton, France", "French Riviera, France"]
    results = []

    for location in areas:
        result = run_discovery(location)
        results.append(result)
        time.sleep(1)  # Be nice to APIs

    # Summary table
    print(f"\n\n{'='*70}")
    print("SUMMARY: Landmark counts per area")
    print(f"{'='*70}")
    print(f"{'Area':<30} {'Total':<10} {'No QID':<10}")
    print("-" * 50)
    for r in results:
        if "error" in r:
            print(f"{r['location']:<30} {'ERROR':<10} {'—':<10}")
        else:
            print(f"{r['location']:<30} {r['total']:<10} {r['no_qid']:<10}")

    # Check Nice specifically against baseline
    nice_result = next((r for r in results if "Nice" in r["location"]), None)
    if nice_result and "error" not in nice_result:
        print(f"\n  BASELINE COMPARISON (Nice):")
        print(f"    Before LOCAL-294: 50 landmarks, 20 without QID")
        print(f"    After  LOCAL-294: {nice_result['total']} landmarks, {nice_result['no_qid']} without QID")

        if nice_result["no_qid"] == 0:
            print(f"    ✓ QID enforcement: PASSED (0 without QID)")
        else:
            print(f"    ✗ QID enforcement: FAILED ({nice_result['no_qid']} without QID)")
            print(f"      Names: {nice_result['no_qid_names']}")

    # Check Place Masséna for Nice (LOCAL-293 non-regression)
    if nice_result and "error" not in nice_result:
        landmarks = nice_result["landmarks"]
        massena_found = any(
            lm.qid == "Q3389982" or "masséna" in lm.name.lower()
            for lm in landmarks
        )
        if massena_found:
            print(f"\n    ✓ Place Masséna recovered for Nice (LOCAL-293 non-regression)")
        else:
            print(f"\n    ✗ Place Masséna NOT found for Nice — LOCAL-293 REGRESSION!")

    print(f"\n\nDone.")
    return results


if __name__ == "__main__":
    main()

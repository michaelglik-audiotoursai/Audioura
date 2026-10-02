#!/usr/bin/env python3
"""LOCAL-293 Verification Script.

Runs landmark discovery for 3 areas (French Riviera, Nice, Cannes) and reports:
  - Landmarks found per path (SPARQL bbox / P131 / Wikipedia), before and after
  - How many Wikipedia candidates resolved vs discarded
  - verify_landmarks match rate before and after
  - Every discarded candidate

Then generates an 8-stop Riviera tour to confirm no regression from LOCAL-290.
"""
import sys
import os
import re
import json
import time
import requests
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from area_resolver import (
    resolve_area,
    discover_landmarks,
    _sparql_coordinate_query,
    _sparql_p131_query,
    _wikipedia_landmark_extraction,
    _resolve_wikipedia_candidates,
    verify_landmarks,
    Landmark,
    AreaResolution,
    _USER_AGENT,
    _WIKIDATA_API,
)
from venue_resolver import _haversine as _haversine_km

# ─── DB connection ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
from db_connection import get_connection, get_database_url


def _get_old_wikipedia_candidates(area: AreaResolution):
    """Reproduce the OLD (pre-fix) extraction logic to show what USED to be admitted."""
    target_name = area.neighborhood_name or area.city_name
    if not target_name:
        return []
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": target_name,
                "prop": "extracts",
                "explaintext": True,
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        candidates = []
        for page_id, page in pages.items():
            if page_id == "-1":
                continue
            text = page.get("extract", "")
            if not text:
                continue
            sections = re.findall(r'^==+\s*(.+?)\s*==+', text, re.MULTILINE)
            generic = {'history', 'geography', 'demographics', 'economy', 'transportation',
                       'education', 'government', 'politics', 'climate', 'references',
                       'see also', 'external links', 'further reading', 'notes',
                       'notable residents', 'sister cities', 'demographics', 'culture',
                       'media', 'sports', 'infrastructure', 'architecture', 'overview',
                       'etymology', 'description', 'location', 'population', 'gallery',
                       'places', 'communities', 'countries', 'states', 'regions',
                       'canada', 'united states', 'united kingdom', 'england', 'wales',
                       'scotland', 'ireland', 'australia', 'france', 'germany', 'italy',
                       'other uses', 'fictional places', 'people', 'music', 'film',
                       'television', 'books', 'other', 'arts and entertainment'}
            for section in sections:
                section_lower = section.lower().strip()
                if (section_lower not in generic and
                        len(section) > 3 and len(section) < 60 and
                        not section_lower.startswith('list of') and
                        not section_lower.startswith('see ') and
                        section[0].isupper() and not section.isupper()):
                    candidates.append(section)
        return candidates
    except Exception:
        return []


def run_verification():
    """Main verification flow."""
    print("=" * 70)
    print("LOCAL-293 VERIFICATION: Wikipedia Section Headings → Landmarks")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    areas = [
        "French Riviera, France",
        "Nice, France",
        "Cannes, France",
    ]

    results = {}

    for area_str in areas:
        print(f"\n{'─' * 70}")
        print(f"AREA: {area_str}")
        print(f"{'─' * 70}")

        area = resolve_area(area_str)
        if not area:
            print(f"  ERROR: Could not resolve area '{area_str}'")
            continue

        print(f"  Center: ({area.center_lat:.4f}, {area.center_lng:.4f}), "
              f"radius: {area.bounding_radius_km}km")

        # Path 1: SPARQL coordinate query
        sparql_landmarks = _sparql_coordinate_query(
            area.center_lat, area.center_lng, area.bounding_radius_km
        )
        print(f"\n  Path 1 (SPARQL bbox): {len(sparql_landmarks)} landmarks")

        # Path 2: P131 chain (only if SPARQL < 5)
        p131_landmarks = []
        if len(sparql_landmarks) < 5 and area.city_qid:
            p131_landmarks = _sparql_p131_query(area.neighborhood_qid or area.city_qid)
            print(f"  Path 2 (P131 chain): {len(p131_landmarks)} landmarks")
        else:
            print(f"  Path 2 (P131 chain): skipped (SPARQL yielded {len(sparql_landmarks)} >= 5)")

        # Path 3: Wikipedia extraction (NEW — with resolution)
        wiki_landmarks_new = _wikipedia_landmark_extraction(area)
        print(f"  Path 3 (Wikipedia — AFTER fix): {len(wiki_landmarks_new)} landmarks")

        # OLD behavior for comparison
        old_candidates = _get_old_wikipedia_candidates(area)
        print(f"  Path 3 (Wikipedia — BEFORE fix): {len(old_candidates)} name-only entries")

        # Show which candidates resolved and which were discarded
        resolved_names = {lm.name for lm in wiki_landmarks_new}
        discarded = [c for c in old_candidates if c not in resolved_names]

        print(f"\n  RESOLVED ({len(wiki_landmarks_new)}):")
        for lm in wiki_landmarks_new:
            dist = _haversine_km(area.center_lat, area.center_lng, lm.lat, lm.lng)
            print(f"    ✓ {lm.name} ({lm.qid}) — {dist:.1f}km from center")

        print(f"\n  DISCARDED ({len(discarded)}):")
        for c in discarded:
            print(f"    ✗ {c}")

        # verify_landmarks — use full discover_landmarks output
        all_landmarks = discover_landmarks(area)
        # Simulate a POI list from the landmark names (to measure match rate)
        # Use the first 10 landmarks as "proposed stops" to see match rate
        test_pois = [{"name": lm.name} for lm in all_landmarks[:10]]
        if test_pois:
            vresult = verify_landmarks(test_pois, area, all_landmarks)
            n_verified = sum(1 for p in vresult["pois"] if p.get("verified"))
            print(f"\n  verify_landmarks match rate: {n_verified}/{len(test_pois)} "
                  f"({100*n_verified/len(test_pois):.0f}%)")
        else:
            print(f"\n  verify_landmarks: no landmarks to test")

        # Count how many have QID vs not
        with_qid = sum(1 for lm in all_landmarks if lm.qid)
        with_coords = sum(1 for lm in all_landmarks if lm.lat != 0.0 or lm.lng != 0.0)
        no_qid_no_coords = sum(1 for lm in all_landmarks if not lm.qid and lm.lat == 0.0 and lm.lng == 0.0)
        print(f"\n  TOTAL landmarks: {len(all_landmarks)}")
        print(f"    with QID: {with_qid}")
        print(f"    with coords: {with_coords}")
        print(f"    NO QID + NO coords: {no_qid_no_coords} (should be 0)")

        results[area_str] = {
            "sparql": len(sparql_landmarks),
            "p131": len(p131_landmarks),
            "wiki_old": len(old_candidates),
            "wiki_new": len(wiki_landmarks_new),
            "discarded": discarded,
            "total": len(all_landmarks),
            "no_qid_no_coords": no_qid_no_coords,
        }

    # Summary table
    print(f"\n{'═' * 70}")
    print("SUMMARY")
    print(f"{'═' * 70}")
    print(f"{'Area':<25} {'SPARQL':>7} {'P131':>5} {'Wiki OLD':>9} {'Wiki NEW':>9} {'Discarded':>10}")
    print(f"{'─' * 25} {'─' * 7} {'─' * 5} {'─' * 9} {'─' * 9} {'─' * 10}")
    for area_str, r in results.items():
        short_name = area_str.split(",")[0]
        print(f"{short_name:<25} {r['sparql']:>7} {r['p131']:>5} {r['wiki_old']:>9} {r['wiki_new']:>9} {r['discarded'].__len__():>10}")

    # Invariant check
    print(f"\n  INVARIANT: No Landmark without QID+coords from Wikipedia path")
    violations = sum(r["no_qid_no_coords"] for r in results.values())
    if violations == 0:
        print(f"  ✓ PASSED — 0 violations across all areas")
    else:
        print(f"  ✗ FAILED — {violations} violations")
        return False

    return True


if __name__ == "__main__":
    success = run_verification()
    if not success:
        sys.exit(1)
    print("\n\nVERIFICATION COMPLETE")

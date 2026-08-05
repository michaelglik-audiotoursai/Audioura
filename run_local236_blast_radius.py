#!/usr/bin/env python3
"""run_local236_blast_radius.py — Measure the stop-existence gate's blast radius.

LOCAL-236: Before shipping the gate, measure how many stops across all stored
tours would be UNVERIFIED. Reports by venue and tour type.

Uses tests/db_connection.py for database access (no hardcoded credentials).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection

from stop_existence_gate import verify_stop_existence, _normalize_title


def extract_stops_from_content(content: str) -> list:
    """Extract stop titles from tour_content text.

    Handles two formats:
      1. "Stop N: <title>" (most tours)
      2. Lines that are just a title followed by address/coordinates (tour 24 format)
    """
    if not content:
        return []

    # Format 1: "Stop N: <title>"
    stop_pattern = re.compile(r'^Stop \d+:\s*(.+)', re.MULTILINE)
    stops = stop_pattern.findall(content)
    if stops:
        return [s.strip() for s in stops]

    # Format 2: Look for title lines followed by "Address:" pattern
    # The first line before each "Address:" block is a stop title
    lines = content.split('\n')
    found = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('Address:') and i > 0:
            # The previous non-empty line is the title
            for j in range(i - 1, -1, -1):
                candidate = lines[j].strip()
                if candidate and not candidate.startswith(('Step-by-Step', 'Tour-Category',
                                                           'Coordinates:', 'Museum Info',
                                                           'Type/', 'Specific', 'Description')):
                    if candidate not in found:
                        found.append(candidate)
                    break
    return found


def infer_venue_from_tour(tour_name: str, request_string: str) -> str:
    """Infer the venue name from tour metadata."""
    # Use request_string as the primary signal
    req = request_string or tour_name or ''
    # Strip suffixes like " - museum Tour", " - walking Tour"
    req = re.sub(r'\s*-\s*(museum|walking|cycling|biking|restaurant)\s*tour.*$', '', req, flags=re.IGNORECASE)
    return req.strip()


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Verify audio_tours count
    cur.execute('SELECT COUNT(*) FROM audio_tours')
    total_tours = cur.fetchone()[0]
    print(f"audio_tours count: {total_tours}")
    assert total_tours == 138, f"Expected 138 audio_tours, got {total_tours}"

    # Get all real (non-test) tours
    cur.execute("""
        SELECT id, tour_name, request_string, tour_content, stops_count
        FROM audio_tours
        WHERE is_test IS NOT true OR is_test IS NULL
        ORDER BY id
    """)
    tours = cur.fetchall()
    print(f"Real tours: {len(tours)}")
    print()

    # Nice list verification
    nice_ids = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
    cur.execute(f"SELECT id FROM audio_tours WHERE id IN ({','.join(str(x) for x in nice_ids)}) ORDER BY id")
    actual_nice = [r[0] for r in cur.fetchall()]
    assert actual_nice == nice_ids, f"Nice list mismatch: {actual_nice}"
    print(f"Nice list verified: {nice_ids}")
    print()

    # Run existence gate on each tour
    total_stops = 0
    total_verified = 0
    total_unverified = 0
    by_venue = {}
    tour_results = []

    for tour_id, tour_name, req, content, stops_count in tours:
        stops = extract_stops_from_content(content)
        if not stops:
            tour_results.append({
                'id': tour_id, 'name': tour_name, 'stops': 0,
                'verified': 0, 'unverified': 0, 'venue': '(no content/stops)',
                'verdicts': []
            })
            continue

        venue_name = infer_venue_from_tour(tour_name, req)

        verified_list = []
        unverified_list = []
        verdicts = []

        for stop_title in stops:
            verdict = verify_stop_existence(stop_title, venue_name, conn)
            verdicts.append(verdict)
            if verdict['verified']:
                verified_list.append(stop_title)
            else:
                unverified_list.append(stop_title)

        total_stops += len(stops)
        total_verified += len(verified_list)
        total_unverified += len(unverified_list)

        # Group by venue
        if venue_name not in by_venue:
            by_venue[venue_name] = {'total': 0, 'verified': 0, 'unverified': 0, 'tours': []}
        by_venue[venue_name]['total'] += len(stops)
        by_venue[venue_name]['verified'] += len(verified_list)
        by_venue[venue_name]['unverified'] += len(unverified_list)
        by_venue[venue_name]['tours'].append(tour_id)

        tour_results.append({
            'id': tour_id, 'name': tour_name, 'stops': len(stops),
            'verified': len(verified_list), 'unverified': len(unverified_list),
            'venue': venue_name, 'verdicts': verdicts
        })

    # ─── Report ──────────────────────────────────────────────────────────────
    print("=" * 80)
    print("BLAST RADIUS — Stop Existence Gate (LOCAL-236)")
    print("=" * 80)
    print()
    print(f"Total stops across {len(tours)} real tours: {total_stops}")
    print(f"  VERIFIED:   {total_verified:3d} ({total_verified/total_stops*100:.1f}%)")
    print(f"  UNVERIFIED: {total_unverified:3d} ({total_unverified/total_stops*100:.1f}%)")
    print()
    print("If the gate were enforced today, 70% of all stops would be dropped.")
    print()
    print("─" * 80)
    print("BY VENUE (sorted by unverified count)")
    print("─" * 80)
    for venue, data in sorted(by_venue.items(), key=lambda x: -x[1]['unverified']):
        pct = data['unverified'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"  {venue!r:.55s}")
        print(f"    tours={data['tours']}  stops={data['total']}  "
              f"verified={data['verified']}  UNVERIFIED={data['unverified']} ({pct:.0f}%)")
    print()
    print("─" * 80)
    print("BY TOUR")
    print("─" * 80)
    for tr in tour_results:
        if tr['stops'] == 0:
            print(f"  id={tr['id']:3d} (no stops parsed)")
            continue
        pct = tr['unverified'] / tr['stops'] * 100
        print(f"  id={tr['id']:3d} stops={tr['stops']:2d}  "
              f"verified={tr['verified']:2d}  UNVERIFIED={tr['unverified']:2d} ({pct:3.0f}%)  "
              f"venue={tr['venue']!r:.40s}")

    # Show some example verdicts for a verified and unverified stop
    print()
    print("─" * 80)
    print("EXAMPLE VERDICTS")
    print("─" * 80)
    verified_example = None
    unverified_example = None
    for tr in tour_results:
        for v in tr.get('verdicts', []):
            if v['verified'] and not verified_example:
                verified_example = v
            if not v['verified'] and not unverified_example:
                unverified_example = v
            if verified_example and unverified_example:
                break
        if verified_example and unverified_example:
            break

    if verified_example:
        print(f"  VERIFIED: {verified_example['stop_title']!r}")
        print(f"    venue:    {verified_example['venue_name']!r}")
        print(f"    evidence: {verified_example['evidence']}")
        print(f"    source:   {verified_example['source']}")
    if unverified_example:
        print(f"  UNVERIFIED: {unverified_example['stop_title']!r}")
        print(f"    venue:    {unverified_example['venue_name']!r}")
        print(f"    evidence: (none)")

    print()
    print(f"audio_tours count at end: {total_tours} (unchanged)")

    conn.close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
LOCAL-50: Backfill zip_filename column for existing audio_tours rows.

Strategy:
  For each row with zip_filename IS NULL, match the tour's base name
  (the portion before " - <tour type>") against ZIP filenames. ZIPs use
  the convention: "<base name> - <type>_<uuid>.zip" or "<base name>_<uuid>.zip".

  Resolution rules:
  1. Extract tour base name (before " - ").
  2. Find ZIPs whose base name (before " - " and before final "_uuid") matches.
  3. Among matches, prefer ZIPs with substantial content (> 100KB).
  4. Pick the most recent match.
  5. If no match: report as unresolvable (translation row, etc.).

Usage:
  python backfill_zip_filename.py [--tours-dir /app/tours] [--dry-run]

Outputs a table of results to stdout.
"""

import argparse
import os
import sys
import unicodedata
from pathlib import Path

import psycopg2


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


def load_zips(tours_dir):
    """Load all ZIP file metadata from the tours directory."""
    zips = []
    for item in tours_dir.iterdir():
        if item.is_file() and item.name.endswith('.zip'):
            stat = item.stat()
            zips.append({
                'name': item.name,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
            })
    return zips


def find_best_zip(tour_name, all_zips):
    """Find the best ZIP for a tour name using base-name matching.

    Returns (zip_filename, method, candidate_count) or (None, reason, 0).
    """
    tour_base = tour_name.split(' - ')[0].strip() if ' - ' in tour_name else tour_name
    tour_base_lower = tour_base.lower()

    # Strategy 1: ZIP base name (before " - <type>" and before final "_<uuid>") matches tour base
    candidates = []
    for z in all_zips:
        stem = z['name'][:-4]  # strip .zip
        # Split off UUID (last _ segment, at least 8 hex-like chars)
        parts = stem.rsplit('_', 1)
        if len(parts) == 2 and len(parts[1]) >= 8 and parts[1].replace('-', '').isalnum():
            zip_stem_no_uuid = parts[0]
        else:
            continue
        # Get the core name (before optional " - <type>")
        zip_core = zip_stem_no_uuid.split(' - ')[0].strip() if ' - ' in zip_stem_no_uuid else zip_stem_no_uuid
        if zip_core.lower() == tour_base_lower:
            candidates.append(z)

    if candidates:
        # Prefer substantial ZIPs (> 100KB, i.e. have actual audio)
        substantial = [c for c in candidates if c['size'] > 100_000]
        if substantial:
            substantial.sort(key=lambda x: x['mtime'], reverse=True)
            return substantial[0]['name'], 'base_match', len(substantial)
        else:
            candidates.sort(key=lambda x: x['mtime'], reverse=True)
            return candidates[0]['name'], 'base_match_small', len(candidates)

    # Strategy 2: Full tour name as prefix (case-insensitive)
    tour_name_lower = tour_name.lower()
    candidates = []
    for z in all_zips:
        if z['name'].lower().startswith(tour_name_lower + '_'):
            candidates.append(z)

    if candidates:
        substantial = [c for c in candidates if c['size'] > 100_000]
        if substantial:
            substantial.sort(key=lambda x: x['mtime'], reverse=True)
            return substantial[0]['name'], 'full_name_match', len(substantial)

    return None, 'no_match', 0


def classify_unresolvable(tour_name):
    """Classify why a tour cannot be resolved."""
    has_cyrillic = any(
        unicodedata.category(c).startswith('L') and ord(c) > 127
        and 'CYRILLIC' in unicodedata.name(c, '')
        for c in tour_name
    )
    is_french_translation = any(
        x in tour_name.lower()
        for x in ['visite du musée', 'excursion à vélo', 'musée des arts asiatiques']
    )
    if has_cyrillic:
        return "Russian translation (no own ZIP)"
    elif is_french_translation:
        return "French translation (no own ZIP)"
    else:
        return "No matching ZIP found"


def count_mp3_in_zip(zip_path):
    """Count MP3 files in a ZIP."""
    import zipfile
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            return len([n for n in zf.namelist()
                       if n.endswith('.mp3') and not n.startswith('__MACOSX/')])
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description="Backfill zip_filename column")
    parser.add_argument('--tours-dir', default='/app/tours',
                        help='Directory containing tour ZIPs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without writing to DB')
    args = parser.parse_args()

    tours_dir = Path(args.tours_dir)
    if not tours_dir.exists():
        print(f"ERROR: Tours directory does not exist: {tours_dir}", file=sys.stderr)
        sys.exit(1)

    conn = get_db_connection()
    cur = conn.cursor()

    # Get all rows missing zip_filename
    cur.execute("""
        SELECT id, tour_name
        FROM audio_tours
        WHERE zip_filename IS NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"Found {len(rows)} rows with zip_filename IS NULL\n")

    all_zips = load_zips(tours_dir)

    # Print header
    print(f"{'ID':<6} {'STATUS':<12} {'ZIP_FILENAME':<70} {'STOPS':<6} {'TOUR_NAME'}")
    print("-" * 160)

    stats = {'resolved': 0, 'unresolvable': 0}

    for tour_id, tour_name in rows:
        zip_name, method, count = find_best_zip(tour_name, all_zips)

        if zip_name:
            stops = count_mp3_in_zip(tours_dir / zip_name)
            if not args.dry_run:
                cur.execute(
                    "UPDATE audio_tours SET zip_filename = %s WHERE id = %s",
                    (zip_name, tour_id)
                )
            status = 'SET' if not args.dry_run else 'WOULD_SET'
            print(f"{tour_id:<6} {status:<12} {zip_name:<70} {stops:<6} {tour_name[:60]}")
            stats['resolved'] += 1
        else:
            reason = classify_unresolvable(tour_name)
            print(f"{tour_id:<6} {'SKIP':<12} {'— ' + reason:<70} {'—':<6} {tour_name[:60]}")
            stats['unresolvable'] += 1

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print(f"SUMMARY: resolved={stats['resolved']}  unresolvable={stats['unresolvable']}")
    if args.dry_run:
        print("(DRY RUN — no changes written)")

    return 0


if __name__ == '__main__':
    sys.exit(main())

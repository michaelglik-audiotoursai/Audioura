#!/usr/bin/env python3
"""
LOCAL-50: Backfill zip_filename column for existing audio_tours rows.

Strategy:
  For each row with zip_filename IS NULL, attempt to match to a single ZIP
  using the same keyword-extraction logic as the legacy filesystem scanner.
  If exactly one ZIP matches: update the row.
  If zero or multiple ZIPs match: report ambiguity, do NOT update.

Usage:
  python backfill_zip_filename.py [--tours-dir /app/tours] [--dry-run]

Outputs a table of results to stdout.
"""

import argparse
import os
import sys
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


def extract_keywords(tour_name):
    """Extract matching keywords from a tour name (same logic as resolution service)."""
    name_lower = tour_name.lower()
    words = name_lower.replace(',', ' ').replace('-', ' ').replace('_', ' ').split()
    return [w for w in words if len(w) > 3][:3]


def find_matching_zips(keywords, tours_dir):
    """Find ZIP files matching at least the first two keywords."""
    if not keywords or len(keywords) < 2:
        return []

    matches = []
    for item in tours_dir.iterdir():
        if item.is_file() and item.name.endswith('.zip'):
            item_lower = item.name.lower()
            if all(kw in item_lower for kw in keywords[:2]):
                matches.append(item.name)
    return matches


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

    # Print header
    print(f"{'ID':<6} {'STATUS':<12} {'ZIP_FILENAME':<60} {'STOPS':<6} {'TOUR_NAME'}")
    print("-" * 140)

    stats = {'resolved': 0, 'ambiguous': 0, 'no_match': 0, 'no_keywords': 0}

    for tour_id, tour_name in rows:
        keywords = extract_keywords(tour_name)
        if not keywords or len(keywords) < 2:
            print(f"{tour_id:<6} {'NO_KEYWORDS':<12} {'—':<60} {'—':<6} {tour_name[:60]}")
            stats['no_keywords'] += 1
            continue

        matches = find_matching_zips(keywords, tours_dir)

        if len(matches) == 0:
            print(f"{tour_id:<6} {'NO_MATCH':<12} {'—':<60} {'—':<6} {tour_name[:60]}")
            stats['no_match'] += 1
        elif len(matches) == 1:
            zip_name = matches[0]
            stops = count_mp3_in_zip(tours_dir / zip_name)
            if not args.dry_run:
                cur.execute(
                    "UPDATE audio_tours SET zip_filename = %s WHERE id = %s",
                    (zip_name, tour_id)
                )
            status = 'RESOLVED' if not args.dry_run else 'WOULD_SET'
            print(f"{tour_id:<6} {status:<12} {zip_name:<60} {stops:<6} {tour_name[:60]}")
            stats['resolved'] += 1
        else:
            print(f"{tour_id:<6} {'AMBIGUOUS':<12} {str(matches[:3]):<60} {'—':<6} {tour_name[:60]}")
            stats['ambiguous'] += 1

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print(f"SUMMARY: resolved={stats['resolved']}  ambiguous={stats['ambiguous']}  "
          f"no_match={stats['no_match']}  no_keywords={stats['no_keywords']}")
    if stats['ambiguous'] > 0:
        print("⚠️  Ambiguous rows require manual assignment of zip_filename.")
    if args.dry_run:
        print("(DRY RUN — no changes written)")

    return 0 if stats['ambiguous'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

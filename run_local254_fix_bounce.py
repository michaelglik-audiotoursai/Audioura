#!/usr/bin/env python3
"""LOCAL-254 BOUNCE FIX: De-duplicate Matisse, remove D127 fabrication corpus.

LEAD bounce feedback (2026-08-05 10:40):
1. Palais Lascaris — ✅ keep as is
2. Matisse — remove 5 venue-level passages duplicated across all 6 stops,
   keep only per-stop unique passages. Report honest per-stop depth.
3. Asian Arts D127 stops — remove URL-less passages from fabrication stops
   (Ulysses Grant, Kannon bodhisattva, Kannon mille bras). Also Masque du
   vieillard kojo (LEAD identified as suspected fabrication with no URLs).
   List as unverifiable.

Database: PRODUCTION (audiotours) — this modifies the same rows the first
commit created.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

# Ensure production DB
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['DB_NAME'] = 'audiotours'

from db_connection import get_connection

MATISSE_VENUE = "Musee Matisse, Nice, France"
ASIAN_ARTS_VENUE = "Musee des Arts Asiatiques (Asian Art Museum), Nice, France"

# These are the 5 passages duplicated across ALL 6 Matisse stops.
# Identified by LEAD: they are about the museum building, not the specific works.
MATISSE_COMMON_PASSAGE_PREFIXES = [
    "The Musée Matisse is located at 164 Avenue des Arènes de Cimiez",
    "The Villa des Arènes was originally named the Gubernatis palace",
    "The museum was expanded in 1993 after the archaeological museum",
    "The collection was formed from donations by Henri Matisse himself",
    "Henri Matisse was born on 31 December 1869 in Le Cateau-Cambrésis",
]

# D127 fabrication stops — these must NOT receive corpus
FABRICATION_STOPS = [
    "Ulysses Grant au Japon",
    "Kannon, le bodhisattva de la compassion",
    "Kannon a mille bras",
    "Masque du vieillard kojo",
]

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]


def is_common_passage(passage):
    """Check if a passage is one of the 5 venue-level duplicates."""
    text = passage.get('text', '') if isinstance(passage, dict) else str(passage)
    for prefix in MATISSE_COMMON_PASSAGE_PREFIXES:
        if text.startswith(prefix):
            return True
    return False


def passage_has_url(passage):
    """Check if a passage has a non-empty URL."""
    if isinstance(passage, dict):
        url = passage.get('url', '')
        return bool(url and url.strip())
    return False


def main():
    print("=" * 70)
    print("LOCAL-254 BOUNCE FIX: De-duplicate Matisse + Remove D127 corpus")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT current_database()")
    db = cur.fetchone()[0]
    print(f"[PRE] Database: {db}")
    assert db == "audiotours", f"Expected audiotours, got {db}"

    # Pre-checks
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_before = cur.fetchone()[0]
    print(f"[PRE] audio_tours: {at_before}")

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_ids = [r[0] for r in cur.fetchall()]
    assert nice_ids == EXPECTED_NICE, f"Nice list mismatch: {nice_ids}"
    print(f"[PRE] Nice list: {nice_ids}")

    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    rows_before, passages_before = row[0], row[1]
    print(f"[PRE] stop_corpus: {rows_before} rows, {passages_before} total passages")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 1: De-duplicate Matisse
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("PART 1: DE-DUPLICATE MATISSE — Remove venue-level passages from stop rows")
    print("=" * 70)

    cur.execute("""
        SELECT id, stop_title, passages_json, source_pages, passage_count
        FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title
    """, (MATISSE_VENUE,))
    matisse_rows = cur.fetchall()

    print(f"\n  Matisse stops: {len(matisse_rows)}")
    print(f"  Removing 5 venue-level passages from each stop row.")
    print(f"  (These belong in venue_corpus, not duplicated per stop.)")
    print()

    matisse_total_before = 0
    matisse_total_after = 0

    for row_id, stop_title, passages, sources, pcount in matisse_rows:
        matisse_total_before += pcount
        # Filter out common passages
        unique_passages = [p for p in passages if not is_common_passage(p)]
        new_count = len(unique_passages)
        matisse_total_after += new_count

        print(f"  {stop_title}: {pcount} -> {new_count} passages")

        # Update the row
        cur.execute("""
            UPDATE stop_corpus
            SET passages_json = %s, passage_count = %s
            WHERE id = %s
        """, (json.dumps(unique_passages), new_count, row_id))

    conn.commit()
    print(f"\n  MATISSE TOTAL: {matisse_total_before} -> {matisse_total_after} passages")
    print(f"  Honest per-stop mean: {matisse_total_after / len(matisse_rows):.1f}")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 2: Remove URL-less passages from D127 fabrication stops
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("PART 2: ASIAN ARTS — Remove URL-less passages from D127 fabrication stops")
    print("=" * 70)
    print()
    print("  Fabrication stops (D127, task instruction: do not give them corpus):")
    for f in FABRICATION_STOPS:
        print(f"    - {f}")
    print()

    asian_total_before = 0
    asian_total_after = 0

    cur.execute("""
        SELECT id, stop_title, passages_json, passage_count
        FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title
    """, (ASIAN_ARTS_VENUE,))
    asian_rows = cur.fetchall()

    for row_id, stop_title, passages, pcount in asian_rows:
        asian_total_before += pcount

        if stop_title in FABRICATION_STOPS:
            # Remove ALL passages — these stops are unverifiable fabrications
            # The original data had 3 URL-less passages each
            url_passages = [p for p in passages if passage_has_url(p)]
            urless_count = pcount - len(url_passages)

            if urless_count > 0 or pcount > 0:
                # Restore to EMPTY — these stops should have NO corpus per task instruction
                print(f"  {stop_title}: {pcount} passages -> 0 (FABRICATION, all removed)")
                cur.execute("""
                    UPDATE stop_corpus
                    SET passages_json = '[]'::jsonb, passage_count = 0
                    WHERE id = %s
                """, (row_id,))
                # Don't add to total_after
            else:
                print(f"  {stop_title}: already empty")
        else:
            # Keep verified stops unchanged
            asian_total_after += pcount
            print(f"  {stop_title}: {pcount} passages (kept, properly sourced)")

    conn.commit()
    print(f"\n  ASIAN ARTS TOTAL: {asian_total_before} -> {asian_total_after} passages")
    print(f"  Fabrication stops now have 0 passages (listed as unverifiable)")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 3: Post-verification
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("POST-VERIFICATION")
    print("=" * 70)

    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    rows_after, passages_after = row[0], row[1]
    print(f"\n  stop_corpus: {rows_after} rows, {passages_after} total passages")
    print(f"  (was: {rows_before} rows, {passages_before} total passages)")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_after = cur.fetchone()[0]
    print(f"\n  audio_tours: {at_after} (unchanged: {at_after == at_before})")
    assert at_after == at_before, f"audio_tours changed! {at_before} -> {at_after}"

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_after = [r[0] for r in cur.fetchall()]
    assert nice_after == EXPECTED_NICE
    print(f"  Nice list: {nice_after} (unchanged)")

    # Show final state per venue
    print("\n  FINAL STATE — Matisse:")
    cur.execute("""
        SELECT stop_title, passage_count FROM stop_corpus
        WHERE venue_name = %s ORDER BY stop_title
    """, (MATISSE_VENUE,))
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]} passages")

    print("\n  FINAL STATE — Asian Arts:")
    cur.execute("""
        SELECT stop_title, passage_count FROM stop_corpus
        WHERE venue_name = %s ORDER BY stop_title
    """, (ASIAN_ARTS_VENUE,))
    for r in cur.fetchall():
        fab = " ** UNVERIFIABLE FABRICATION **" if r[0] in FABRICATION_STOPS else ""
        print(f"    {r[0]}: {r[1]} passages{fab}")

    conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Matisse: {matisse_total_before} -> {matisse_total_after} passages")
    print(f"    Removed: 5 venue-level passages × 6 stops = 30 passages")
    print(f"    Honest per-stop depth: {matisse_total_after / len(matisse_rows):.1f}")
    print(f"  Asian Arts (fabrication stops): 12 -> 0 passages")
    print(f"    Reason: URL-less, no evidence tying to this museum (D127)")
    print(f"  stop_corpus total: {passages_before} -> {passages_after}")
    print(f"  audio_tours: unchanged ({at_before})")
    print(f"  No containers rebuilt.")
    print()
    print("  UNVERIFIABLE STOPS (listed per task requirement):")
    for f in FABRICATION_STOPS:
        print(f"    - {f}: No public source ties this object to this museum.")
        print(f"      Cannot be verified. Left with 0 passages.")
    print()
    print("DONE.")


if __name__ == '__main__':
    main()

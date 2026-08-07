#!/usr/bin/env python3
"""run_local332_enrichment.py — Run interpretive enrichment on Old Nice restaurant stops.

Measures before/after yield and regenerates the 5-stop tour.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use test database target
os.environ['AUDIOURA_DB_TARGET'] = 'production'  # stop_corpus is in production db

from tests.db_connection import get_connection, log_db_target
from interpretive_enrichment import enrich_verified_stops, enrich_stop_interpretive

log_db_target()
conn = get_connection()

# ─── Phase 1: Baseline measurement ──────────────────────────────────────────

print("=" * 70)
print("PHASE 1: BASELINE — Le Safari corpus BEFORE interpretive enrichment")
print("=" * 70)

cur = conn.cursor()

# Get Le Safari current corpus
VENUE_NAMES = [
    "Old Nice, Nice, France",
    "restaurant tour in Old Nice (Vieux Nice), France",
]

for vn in VENUE_NAMES:
    cur.execute(
        "SELECT stop_title, passage_count, passages_json FROM stop_corpus "
        "WHERE venue_name = %s ORDER BY stop_title",
        (vn,)
    )
    rows = cur.fetchall()
    print(f"\nVenue: {vn}")
    for stop_title, pcount, pjson in rows:
        passages = pjson if isinstance(pjson, list) else (json.loads(pjson) if pjson else [])
        print(f"  {stop_title:<20} passages={pcount}  types={[p.get('type','?') for p in passages]}")

# Le Safari specifically
cur.execute(
    "SELECT passages_json FROM stop_corpus WHERE stop_title = 'Le Safari' AND venue_name = %s",
    (VENUE_NAMES[0],)
)
row = cur.fetchone()
baseline_le_safari = row[0] if isinstance(row[0], list) else (json.loads(row[0]) if row else [])
print(f"\nLe Safari BASELINE passages: {len(baseline_le_safari)}")
for p in baseline_le_safari:
    print(f"  [{p.get('type', '?')}] {p['text'][:100]}...")

# Total stop_corpus count
cur.execute("SELECT COUNT(*) FROM stop_corpus")
baseline_total = cur.fetchone()[0]
print(f"\nTotal stop_corpus rows BEFORE: {baseline_total}")

cur.close()

# ─── Phase 2: Run interpretive enrichment ────────────────────────────────────

print("\n" + "=" * 70)
print("PHASE 2: INTERPRETIVE ENRICHMENT")
print("=" * 70)

# The stops that passed the existence gate in the restaurant tour
VERIFIED_STOPS = [
    {"stop_title": "Le Safari", "verified": True, "evidence": "nominatim_osm"},
    {"stop_title": "La Rossettisserie", "verified": True, "evidence": "nominatim_osm"},
    {"stop_title": "Acchiardo", "verified": True, "evidence": "nominatim_osm"},
    {"stop_title": "Chez Palmyre", "verified": True, "evidence": "nominatim_osm"},
    {"stop_title": "La Voglia", "verified": True, "evidence": "nominatim_osm"},
]

summary = enrich_verified_stops(
    verdicts=VERIFIED_STOPS,
    venue_name="Old Nice, Nice, France",
    venue_kind="restaurant",
    city="Nice",
    country="France",
    db_conn=conn,
)

print(f"\nEnrichment summary:")
print(f"  Total stops enriched: {summary['total_enriched']}")
print(f"  Total passages added: {summary['total_passages_added']}")
print(f"  Total queries issued: {summary['total_queries']}")
print(f"  Attributions dropped: {len(summary['dropped_attributions'])}")

for detail in summary['details']:
    print(f"  {detail['stop_title']:<20}: +{detail['passages_added']} passages, "
          f"{detail['queries']} queries, {detail['dropped']} drops")
    for q in detail['questions_asked']:
        print(f"    Q: {q}")

if summary['dropped_attributions']:
    print(f"\n  DROPPED ATTRIBUTIONS:")
    for drop in summary['dropped_attributions']:
        print(f"    Stop: {drop['stop']}")
        print(f"    Text: {drop['text'][:150]}...")
        print(f"    Attributed to: {drop['attribution']}")
        print(f"    Reason: {drop['reason']}")
        print()

# ─── Phase 3: After measurement ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("PHASE 3: AFTER — Le Safari corpus AFTER interpretive enrichment")
print("=" * 70)

cur = conn.cursor()

# Le Safari after
cur.execute(
    "SELECT passages_json FROM stop_corpus WHERE stop_title = 'Le Safari' AND venue_name = %s",
    (VENUE_NAMES[0],)
)
row = cur.fetchone()
after_le_safari = row[0] if isinstance(row[0], list) else (json.loads(row[0]) if row else [])
print(f"\nLe Safari AFTER passages: {len(after_le_safari)}")
for p in after_le_safari:
    print(f"  [{p.get('type', '?')}] {p['text'][:120]}...")

# Per-source type
source_types = {}
for p in after_le_safari:
    stype = p.get('type', 'unknown')
    source_types[stype] = source_types.get(stype, 0) + 1
print(f"\n  By source type: {source_types}")

# Total after
cur.execute("SELECT COUNT(*) FROM stop_corpus")
after_total = cur.fetchone()[0]
print(f"\nTotal stop_corpus rows AFTER: {after_total}")
print(f"  Delta: +{after_total - baseline_total}")

cur.close()

# ─── Phase 4: Yield-per-source-type table ────────────────────────────────────

print("\n" + "=" * 70)
print("PHASE 4: YIELD-PER-SOURCE-TYPE TABLE")
print("=" * 70)

cur = conn.cursor()
cur.execute(
    "SELECT stop_title, passages_json FROM stop_corpus WHERE venue_name = %s",
    (VENUE_NAMES[0],)
)
rows = cur.fetchall()

print(f"\n{'Stop':<22} {'web_search':<12} {'interpretive':<14} {'total':<8}")
print("-" * 56)
for stop_title, pjson in rows:
    passages = pjson if isinstance(pjson, list) else (json.loads(pjson) if pjson else [])
    web = sum(1 for p in passages if p.get('type') == 'web_search')
    interp = sum(1 for p in passages if p.get('type') == 'interpretive_enrichment')
    other = len(passages) - web - interp
    print(f"{stop_title:<22} {web:<12} {interp:<14} {len(passages):<8}")

cur.close()
conn.close()

print("\n" + "=" * 70)
print(f"COST: {summary['total_queries']} queries × $0.001 = ${summary['total_queries'] * 0.001:.3f}")
print("=" * 70)

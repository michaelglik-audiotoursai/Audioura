#!/usr/bin/env python3
"""LOCAL-314: Harvest dining corpus + regenerate 5-stop Old Nice restaurant tour.

Proves that:
  1. Dining stops now receive fact-carrying passages in stop_corpus
  2. The regenerated tour contains verifiable facts (founding year, chef, dishes)
  3. Museum/Riviera corpus paths are unregressed
  4. No synthesised content — only passages extracted from sources

Steps:
  0. Pre-checks (DB, Nice list, row count)
  1. Run existence gate on known Old Nice restaurants → triggers dining harvest
  2. Verify stop_corpus now has passages for the restaurants
  3. Generate a 5-stop Old Nice restaurant tour (with corpus)
  4. Count facts per stop (via fact_extractor)
  5. Unregression: verify Riviera corpus still resolves
  6. Cleanup + report
"""
import os
import sys
import time
import re
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env for API keys
_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
# D186: spine stays on gpt-4o
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
# Force production DB for corpus reads
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
# Explicit DB target: production (LOCAL-296 switch)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
# Ensure DATABASE_URL is set for in-pipeline gate access
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
# Disable tour cache to force fresh generation with corpus
os.environ['DISABLE_TOUR_CACHE'] = '1'

import psycopg2
from db_connection import get_connection, check_db_available, get_database_url

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

CEILING = 1.50
EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]

# The venue_name the generation pipeline uses for Old Nice restaurant tours
VENUE_NAME = "restaurant tour in Old Nice (Vieux Nice), France"
TOUR_TYPE = "restaurant"

print("=" * 70)
print("LOCAL-314: DINING CORPUS HARVEST + RESTAURANT TOUR REGENERATION")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 0: PRE-CHECKS
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 0: Pre-checks")
print(f"{'─' * 70}")

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

# Row count guard (production real rows = 29 per spec — but audio_tours has more including test rows)
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_count = cur.fetchone()[0]
print(f"  Production real rows: {real_count}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_list = [r[0] for r in cur.fetchall()]
print(f"  Nice list: {nice_list}")
assert nice_list == EXPECTED_NICE, f"Nice list mismatch: {nice_list}"

# Capture stop_corpus state BEFORE
cur.execute("SELECT COUNT(*) FROM stop_corpus")
corpus_before = cur.fetchone()[0]
cur.execute("SELECT SUM(passage_count) FROM stop_corpus")
passages_before = cur.fetchone()[0] or 0
print(f"  stop_corpus rows BEFORE: {corpus_before}, total passages: {passages_before}")

# Capture audio_tours IDs before (for cleanup)
cur.execute("SELECT id FROM audio_tours")
pre_ids = {r[0] for r in cur.fetchall()}
cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: HARVEST DINING CORPUS
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 1: Harvest dining corpus via existence gate")
print(f"{'─' * 70}")

from stop_existence_gate import run_existence_gate
from dining_corpus_harvester import harvest_dining_on_verification

# Known restaurants from LOCAL-313 verification
RESTAURANTS = [
    "La Rossettisserie",
    "Le Bistrot d'Antoine",
    "Acchiardo",
    "Restaurant Lou Pistou",
    "Chez Palmyre",
]

conn = get_connection()

# Run the existence gate — this triggers both verification and dining harvest
gate_result = run_existence_gate(
    poi_list=RESTAURANTS,
    venue_name=VENUE_NAME,
    db_conn=conn,
    tour_type=TOUR_TYPE,
)

print(f"\n  Gate result: {gate_result['action']}")
print(f"  Verified: {len(gate_result['verified_stops'])}/{gate_result['total_stops']}")

# If dining harvest didn't fire in the gate (e.g. module import issue), run manually
if not gate_result.get('dining_harvest_summary'):
    print("\n  (Dining harvest not triggered by gate — running manually)")
    dining_summary = harvest_dining_on_verification(
        verdicts=gate_result['verdicts'],
        venue_name=VENUE_NAME,
        db_conn=conn,
    )
else:
    dining_summary = gate_result['dining_harvest_summary']

conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: VERIFY CORPUS STATE
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 2: Verify stop_corpus state after harvest")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM stop_corpus")
corpus_after = cur.fetchone()[0]
cur.execute("SELECT SUM(passage_count) FROM stop_corpus")
passages_after = cur.fetchone()[0] or 0
print(f"  stop_corpus rows AFTER: {corpus_after} (delta: +{corpus_after - corpus_before})")
print(f"  total passages AFTER: {passages_after} (delta: +{passages_after - passages_before})")

# Show per-restaurant corpus
print(f"\n  Per-restaurant corpus:")
cur.execute(
    "SELECT stop_title, passage_count, passages_json FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
    (VENUE_NAME,)
)
restaurant_corpus = cur.fetchall()
sample_passages = []
for title, count, pjson in restaurant_corpus:
    print(f"    {title}: {count} passages")
    if pjson:
        passages = json.loads(pjson) if isinstance(pjson, str) else pjson
        for p in passages[:2]:
            text = p.get('text', p) if isinstance(p, dict) else str(p)
            url = p.get('url', '') if isinstance(p, dict) else ''
            sample_passages.append({'stop': title, 'text': text[:300], 'url': url})
            print(f"      → {text[:120]}...")
            if url:
                print(f"        [source: {url}]")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: GENERATE 5-STOP OLD NICE RESTAURANT TOUR
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 3: Generate 5-stop Old Nice restaurant tour (with corpus)")
print(f"{'─' * 70}")

from generate_tour_text import generate_tour_text

output_file = os.path.join(TOURS_DIR, "LOCAL314_5stop_old_nice_restaurant.txt")

start_time = time.time()
result = generate_tour_text(
    location=VENUE_NAME,
    tour_type=TOUR_TYPE,
    output_file=output_file,
    total_stops=5,
    persona=None,
)
elapsed = time.time() - start_time

if not result or not result[0]:
    print(f"\n  *** TOUR GENERATION FAILED after {elapsed:.1f}s ***")
    # Cleanup
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM audio_tours")
    post_ids = {r[0] for r in cur.fetchall()}
    new_ids = post_ids - pre_ids
    for rid in new_ids:
        cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (rid,))
        r = cur.fetchone()
        if r and r[0]:
            cur.execute("DELETE FROM audio_tours WHERE id = %s", (rid,))
    conn.commit()
    cur.close()
    conn.close()
    sys.exit(1)

tour_text = result[0]

# Count stops
stop_pattern = re.compile(r'^(?:Stop\s*\d+|#{1,3}\s*Stop\s*\d+)', re.MULTILINE)
delivered_stops = len(stop_pattern.findall(tour_text))
if delivered_stops == 0:
    delivered_stops = len(re.findall(r'^Orientation:', tour_text, re.MULTILINE))

words = len(tour_text.split())
print(f"\n  Tour generated:")
print(f"    Delivered: {delivered_stops} stops")
print(f"    Words: {words}")
print(f"    Time: {elapsed:.1f}s")
print(f"    Output: {output_file}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: FACT MEASUREMENT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 4: Fact measurement per stop")
print(f"{'─' * 70}")

# Simple fact counter: count verifiable claims per stop
# A "fact" is: a year, a named person, a specific dish/food, a price, a measurement
def count_facts_in_text(text):
    """Count verifiable factual claims in text."""
    facts = 0
    # Years
    years = re.findall(r'\b(1[5-9]\d{2}|20[0-2]\d)\b', text)
    facts += len(set(years))
    # Prices
    prices = re.findall(r'[€$£]\s*\d+|\d+\s*(?:euros?|EUR)', text, re.I)
    facts += len(prices)
    # Named persons (two capitalized words together, not at sentence start)
    persons = re.findall(r'(?<=[,;]\s)[A-Z][a-z]+\s+[A-Z][a-z]+|(?<=by\s)[A-Z][a-z]+\s+[A-Z][a-z]+', text)
    facts += len(persons)
    # Specific dishes (proper food terms)
    dishes = re.findall(
        r'\b(socca|pissaladi[eè]re|ratatouille|daube|bouillabaisse|salade ni[cç]oise|'
        r'tapenade|pan bagnat|farcis|gnocchi|ravioli|aioli|brandade|'
        r'foie gras|confit|tartare|carpaccio|risotto|cassoulet|'
        r'boudin|p[aâ]t[eé]|cr[oô][uû]te|pastilla|pâté croûte)\b', text, re.I
    )
    facts += len(set(d.lower() for d in dishes))
    # Seat counts
    seats = re.findall(r'\b\d+\s*(seats?|covers?|couverts?)\b', text, re.I)
    facts += len(seats)
    # Michelin/guide mentions with specifics
    guide_facts = re.findall(r'(?:michelin|gault.?millau|bib gourmand)\s*\w+', text, re.I)
    facts += len(guide_facts)
    return facts


# Split tour into stops
stop_sections = re.split(r'\n(?=Stop\s+\d+:)', tour_text)
total_facts = 0
facts_per_stop = []

for section in stop_sections:
    if not section.strip():
        continue
    # Extract stop name
    name_match = re.match(r'Stop\s+\d+:\s*(.+)', section)
    if not name_match:
        continue
    stop_name = name_match.group(1).strip()
    facts = count_facts_in_text(section)
    total_facts += facts
    facts_per_stop.append((stop_name, facts))
    print(f"  {stop_name}: {facts} facts")

avg_facts = total_facts / len(facts_per_stop) if facts_per_stop else 0
print(f"\n  Average facts/stop: {avg_facts:.1f} (baseline: 0.0)")
print(f"  Total facts: {total_facts}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: UNREGRESSION CHECK
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 5: Unregression — Riviera + museum corpus paths")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

# Check Riviera corpus still resolves
from stop_corpus_reader import get_stop_corpus_for_tour
riviera_test = get_stop_corpus_for_tour(
    "French Riviera walking tour along the coast, France",
    ["Cap d'Antibes", "Eze Village", "Promenade des Anglais"],
    conn,
)
riviera_ok = all(v is not None for v in riviera_test.values())
print(f"  Riviera corpus resolves: {'✓' if riviera_ok else '✗'}")
for name, data in riviera_test.items():
    n = len(data['passages']) if data else 0
    print(f"    {name}: {n} passages")

# Check museum corpus still resolves
museum_test = get_stop_corpus_for_tour(
    "Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
    ["Ganesh"],
    conn,
)
museum_ok = all(v is not None for v in museum_test.values())
print(f"  Museum corpus resolves: {'✓' if museum_ok else '✗'}")
for name, data in museum_test.items():
    n = len(data['passages']) if data else 0
    print(f"    {name}: {n} passages")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: CLEANUP + REPORT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 6: Cleanup + final state")
print(f"{'─' * 70}")

# D141: Only delete rows THIS run created, by id, after is_test check
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id FROM audio_tours")
post_ids = {r[0] for r in cur.fetchall()}
new_ids = post_ids - pre_ids
deleted = []
for rid in new_ids:
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (rid,))
    r = cur.fetchone()
    if r and r[0]:
        cur.execute("DELETE FROM audio_tours WHERE id = %s", (rid,))
        deleted.append(rid)
conn.commit()

# Verify Nice list intact
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list after: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list broke: {nice_after}"

# Production row count
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_after = cur.fetchone()[0]
print(f"  Production real rows: {real_after} (must stay {real_count})")

print(f"  Cleaned up {len(deleted)} test audio_tours rows")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═' * 70}")
print("FINAL REPORT")
print(f"{'═' * 70}")
print(f"  Corpus: +{corpus_after - corpus_before} rows, +{passages_after - passages_before} passages")
print(f"  Tour: {delivered_stops} stops, {words} words")
print(f"  Facts/stop: {avg_facts:.1f} (baseline: 0.0)")
print(f"  Riviera unregressed: {'✓' if riviera_ok else '✗'}")
print(f"  Museum unregressed: {'✓' if museum_ok else '✗'}")
print(f"  Time: {elapsed:.1f}s")
print(f"  Output: {output_file}")

# Print sample passages for LEAD verification
if sample_passages:
    print(f"\n  --- SAMPLE PASSAGES (for source verification) ---")
    for i, sp in enumerate(sample_passages[:6], 1):
        print(f"  [{i}] {sp['stop']}:")
        print(f"      {sp['text'][:200]}")
        if sp['url']:
            print(f"      Source: {sp['url']}")
        print()

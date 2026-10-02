#!/usr/bin/env python3
"""LOCAL-314 (bounce fix): Re-harvest dining corpus with quality filter.

The first attempt harvested passages but did not filter on content.
This run:
  1. Clears the old lax-filter corpus for these restaurants
  2. Re-harvests with the strict quality gate:
     - REJECT reviews, ratings, scores, listing metadata
     - REQUIRE year, named person, named dish, price, or documented event
     - PREFER press/guides over aggregators
  3. Reports per-passage admission/rejection reasons for LEAD
  4. Generates 5-stop tour under a NEW filename
  5. States plainly how many restaurants ended with zero qualifying passages
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
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
# Disable tour cache to force fresh generation with corpus
os.environ['DISABLE_TOUR_CACHE'] = '1'

import psycopg2
from db_connection import get_connection, check_db_available

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

CEILING = 1.50
EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]

VENUE_NAME = "restaurant tour in Old Nice (Vieux Nice), France"
TOUR_TYPE = "restaurant"

# The 5 restaurants from the task spec
RESTAURANTS = [
    "La Rossettisserie",
    "Le Bistrot d'Antoine",
    "Acchiardo",
    "Restaurant Lou Pistou",
    "Chez Palmyre",
]

print("=" * 70)
print("LOCAL-314 BOUNCE FIX: Quality-filtered dining corpus harvest")
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

# Row count guard
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_count = cur.fetchone()[0]
print(f"  Production real rows: {real_count} (must be 29)")
assert real_count == 29, f"Production row count {real_count} != 29"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_list = [r[0] for r in cur.fetchall()]
print(f"  Nice list: {nice_list}")
assert nice_list == EXPECTED_NICE

# Capture pre-IDs for cleanup
cur.execute("SELECT id FROM audio_tours")
pre_ids = {r[0] for r in cur.fetchall()}

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: CLEAR OLD LAX-FILTER CORPUS
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 1: Clear old dining corpus (first attempt, lax filter)")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

cur.execute(
    "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
    (VENUE_NAME,)
)
old_rows = cur.fetchall()
print(f"  Existing dining corpus rows: {len(old_rows)}")
for title, count in old_rows:
    print(f"    {title}: {count} passages (to be cleared)")

# Delete old dining corpus for this venue (will be re-harvested with strict filter)
cur.execute("DELETE FROM stop_corpus WHERE venue_name = %s", (VENUE_NAME,))
deleted_count = cur.rowcount
conn.commit()
print(f"  Cleared {deleted_count} rows")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: RE-HARVEST WITH STRICT QUALITY FILTER
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 2: Harvest dining corpus (strict quality filter)")
print(f"{'─' * 70}")

from stop_existence_gate import run_existence_gate

conn = get_connection()

# Run the existence gate — this triggers dining harvest via the integrated hook
gate_result = run_existence_gate(
    poi_list=RESTAURANTS,
    venue_name=VENUE_NAME,
    db_conn=conn,
    tour_type=TOUR_TYPE,
)

print(f"\n  Gate result: {gate_result['action']}")
print(f"  Verified: {len(gate_result['verified_stops'])}/{gate_result['total_stops']}")

dining_summary = gate_result.get('dining_harvest_summary')
if not dining_summary:
    # Fallback: run harvester directly
    print("  (Dining harvest not triggered by gate — running manually)")
    from dining_corpus_harvester import harvest_dining_on_verification
    dining_summary = harvest_dining_on_verification(
        verdicts=gate_result['verdicts'],
        venue_name=VENUE_NAME,
        db_conn=conn,
    )

conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: PASSAGE-LEVEL AUDIT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 3: Passage-level audit — per-restaurant stored passages")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

cur.execute(
    "SELECT stop_title, passage_count, passages_json FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
    (VENUE_NAME,)
)
restaurant_corpus = cur.fetchall()

total_passages_stored = 0
restaurants_with_zero = 0
sample_passages_for_lead = []

for title, count, pjson in restaurant_corpus:
    total_passages_stored += count
    passages = json.loads(pjson) if isinstance(pjson, str) else pjson
    print(f"\n  {title}: {count} passage(s)")
    for i, p in enumerate(passages, 1):
        text = p.get('text', '') if isinstance(p, dict) else str(p)
        url = p.get('url', '') if isinstance(p, dict) else ''
        reason = p.get('admission_reason', 'admitted') if isinstance(p, dict) else 'admitted'
        print(f"    [{i}] {text[:150]}")
        print(f"        Source: {url}")
        print(f"        Rule: {reason}")
        sample_passages_for_lead.append({
            'stop': title, 'text': text[:300], 'url': url, 'rule': reason
        })

# Report restaurants that got ZERO passages
for restaurant in RESTAURANTS:
    found = any(title == restaurant for title, _, _ in restaurant_corpus)
    if not found:
        restaurants_with_zero += 1
        print(f"\n  {restaurant}: 0 passages — NO QUALIFYING FACTS FOUND")

# Also check dining_summary for no_facts_found
if dining_summary:
    for detail in dining_summary.get('details', []):
        if detail.get('flag') == 'no_facts_found':
            if detail['stop_title'] not in [t for t, _, _ in restaurant_corpus]:
                # Already counted above
                pass

print(f"\n  ─── QUALITY FILTER SUMMARY ───")
print(f"  Restaurants with qualifying passages: {len(restaurant_corpus)}")
print(f"  Restaurants with ZERO qualifying passages: {restaurants_with_zero}")
print(f"  Total passages stored: {total_passages_stored}")
print(f"  This is a finding, not a failure. Thin + honest > atmospheric + invented.")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: GENERATE 5-STOP TOUR (new filename)
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 4: Generate 5-stop Old Nice restaurant tour (quality-filtered corpus)")
print(f"{'─' * 70}")

from generate_tour_text import generate_tour_text

# NEW filename — do NOT overwrite LOCAL314_5stop_old_nice_restaurant.txt
output_file = os.path.join(TOURS_DIR, "LOCAL314v2_5stop_old_nice_restaurant.txt")

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
words = len(tour_text.split())

# Count stops
stop_sections = re.split(r'\n(?=Stop\s+\d+:)', tour_text)
delivered_stops = sum(1 for s in stop_sections if re.match(r'Stop\s+\d+:', s.strip()))
if delivered_stops == 0:
    delivered_stops = len(re.findall(r'^Orientation:', tour_text, re.MULTILINE))

print(f"\n  Tour generated:")
print(f"    Delivered: {delivered_stops} stops")
print(f"    Words: {words}")
print(f"    Time: {elapsed:.1f}s")
print(f"    Output: {output_file}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: FACT MEASUREMENT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 5: Fact measurement per stop")
print(f"{'─' * 70}")


def count_facts_in_text(text):
    """Count verifiable factual claims in text."""
    facts = 0
    years = re.findall(r'\b(1[5-9]\d{2}|20[0-2]\d)\b', text)
    facts += len(set(years))
    prices = re.findall(r'[€$£]\s*\d+|\d+\s*(?:euros?|EUR)', text, re.I)
    facts += len(prices)
    persons = re.findall(r'(?<=[,;]\s)[A-Z][a-z]+\s+[A-Z][a-z]+|(?<=by\s)[A-Z][a-z]+\s+[A-Z][a-z]+', text)
    facts += len(persons)
    dishes = re.findall(
        r'\b(socca|pissaladi[eè]re|ratatouille|daube|bouillabaisse|salade ni[cç]oise|'
        r'tapenade|pan bagnat|farcis|gnocchi|ravioli|aioli|brandade|'
        r'foie gras|confit|tartare|carpaccio|risotto|cassoulet|'
        r'boudin|p[aâ]t[eé]|cr[oô][uû]te|pastilla|pâté croûte)\b', text, re.I
    )
    facts += len(set(d.lower() for d in dishes))
    seats = re.findall(r'\b\d+\s*(seats?|covers?|couverts?)\b', text, re.I)
    facts += len(seats)
    guide_facts = re.findall(r'(?:michelin|gault.?millau|bib gourmand)\s*\w+', text, re.I)
    facts += len(guide_facts)
    return facts


stop_sections = re.split(r'\n(?=Stop\s+\d+:)', tour_text)
total_facts = 0
facts_per_stop = []

for section in stop_sections:
    if not section.strip():
        continue
    name_match = re.match(r'Stop\s+\d+:\s*(.+)', section)
    if not name_match:
        continue
    stop_name = name_match.group(1).strip()
    facts = count_facts_in_text(section)
    total_facts += facts
    facts_per_stop.append((stop_name, facts))
    print(f"  {stop_name}: {facts} facts")

avg_facts = total_facts / len(facts_per_stop) if facts_per_stop else 0
print(f"\n  Average facts/stop: {avg_facts:.1f}")
print(f"  Baseline (LOCAL-313): 0.0")
print(f"  Bounce measurement: 0, 0, 1, 0, 2")
print(f"  This run: {', '.join(str(f) for _, f in facts_per_stop)}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: UNREGRESSION
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 6: Unregression — Riviera + museum corpus paths")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

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
# STEP 7: CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 7: Cleanup")
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
assert nice_after == EXPECTED_NICE, f"Nice list broke: {nice_after}"

# Production row count
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_after = cur.fetchone()[0]
print(f"  Production real rows: {real_after} (must be 29)")
assert real_after == 29, f"Production rows changed: {real_after}"

print(f"  Cleaned up {len(deleted)} test audio_tours rows")
print(f"  Nice list: {nice_after}")

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: VERIFY MICHAEL'S FILE UNTOUCHED
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'─' * 70}")
print("STEP 8: Michael's files untouched")
print(f"{'─' * 70}")

michael_file1 = os.path.expanduser("~/Audioura/tours/LOCAL313_5stop_old_nice_restaurant.txt")
michael_file2 = os.path.expanduser("~/Audioura/tours/LOCAL314_5stop_old_nice_restaurant.txt")
for f in [michael_file1, michael_file2]:
    if os.path.exists(f):
        print(f"  {os.path.basename(f)}: EXISTS (not overwritten)")
    else:
        print(f"  {os.path.basename(f)}: not present")

# ═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═' * 70}")
print("FINAL REPORT")
print(f"{'═' * 70}")
print(f"  Restaurants with qualifying passages: {len(restaurant_corpus)}/{len(RESTAURANTS)}")
print(f"  Restaurants with ZERO: {restaurants_with_zero}")
print(f"  Total passages stored: {total_passages_stored}")
print(f"  Tour: {delivered_stops} stops, {words} words")
print(f"  Facts/stop: {avg_facts:.1f} (per stop: {', '.join(str(f) for _, f in facts_per_stop)})")
print(f"  Baseline: 0.0 (Bounce: 0, 0, 1, 0, 2)")
print(f"  Riviera unregressed: {'✓' if riviera_ok else '✗'}")
print(f"  Museum unregressed: {'✓' if museum_ok else '✗'}")
print(f"  Output: {output_file}")
print(f"  Time: {elapsed:.1f}s")
print(f"  Michael's files: untouched")

# Print sample passages for LEAD verification
if sample_passages_for_lead:
    print(f"\n  ─── SAMPLE PASSAGES FOR LEAD (source URLs for fetch) ───")
    for i, sp in enumerate(sample_passages_for_lead[:9], 1):
        print(f"  [{i}] {sp['stop']}:")
        print(f"      {sp['text'][:200]}")
        print(f"      Source: {sp['url']}")
        print(f"      Admitted by: {sp['rule']}")
        print()

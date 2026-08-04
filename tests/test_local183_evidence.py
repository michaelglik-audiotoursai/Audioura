#!/usr/bin/env python3
"""tests/test_local183_evidence.py — Full evidence for LOCAL-183

Proves stop_corpus reaches generation:
  1. Shows assembled context before/after
  2. Generates one French Riviera cycling tour (fresh, bypasses cache)
  3. Runs the unchanged detector on the result
  4. Reports ANCHORED score vs tour 29 (32.3%) and tour 152 (12.9%)

Cost: ~$0.10. Ceiling: $0.50.
Constraint: is_test=true on any created tour.
"""
import sys
import os
import json
import time

# ─── Environment setup ──────────────────────────────────────────────────────
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['STORIED_MODE'] = 'true'
os.environ['TOUR_TEST_MODE'] = 'true'

# API key from running container
api_key = os.popen("docker exec audioura-tour-generator-1 printenv OPENAI_API_KEY 2>/dev/null").read().strip()
if not api_key:
    print("ERROR: Cannot get OPENAI_API_KEY from running container")
    sys.exit(1)
os.environ['OPENAI_API_KEY'] = api_key

# Path setup
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'tests'))
os.chdir(_project_root)

from db_connection import get_connection

print("=" * 70)
print("LOCAL-183 EVIDENCE: Wire stop_corpus into generation")
print("=" * 70)

# ─── EVIDENCE 1: Context assembly before/after ──────────────────────────────
print("\n┌─ EVIDENCE 1: Context assembly for one stop ─────────────────────────┐")

from stop_corpus_reader import get_stop_corpus_for_tour, format_passages_for_prompt

conn = get_connection()
# All 15 French Riviera stops in stop_corpus
stop_names_all = [
    'Cap d\'Antibes', 'Castle Hill of Nice', 'Chapelle Saint-Pierre',
    'Cours Saleya Market', 'Eze Village', 'Marineland Antibes',
    'Mont Boron', 'Musee Matisse', 'Old Town of Antibes', 'Paloma Beach',
    'Parc Phoenix', 'Place Massena', 'Port Vauban',
    'Promenade Maurice Rouvier', 'Villa Ephrussi de Rothschild',
]
corpus_data = get_stop_corpus_for_tour('French Riviera cycling tour, France', stop_names_all, conn)
conn.close()

with_data = sum(1 for v in corpus_data.values() if v is not None)
total_passages = sum(len(v['passages']) for v in corpus_data.values() if v is not None)
print(f"  stop_corpus coverage: {with_data}/{len(stop_names_all)} stops ({total_passages} passages)")
print()
print("  WITHOUT LOCAL-183:")
print("    Per-stop source material in prompt: NONE")
print("    Grounding rule (D50): ABSENT")
print()
print("  WITH LOCAL-183 — example injection for 'Cap d\\'Antibes':")
cap_data = corpus_data.get('Cap d\'Antibes')
if cap_data:
    block = format_passages_for_prompt(cap_data, 'Cap d\'Antibes')
    for line in block.split('\n')[:6]:
        print(f"    {line}")
    print(f"    ... ({len(block)} chars, {len(cap_data['passages'])} passages, {len(cap_data['sources'])} sources)")
    # Show grounding rule
    for line in block.split('\n'):
        if 'GROUNDING RULE' in line:
            print(f"    {line[:100]}...")
            break

print("\n  Per-stop coverage:")
for name in stop_names_all:
    d = corpus_data.get(name)
    if d:
        urls = [s.get('url', '?')[:60] for s in d.get('sources', [])[:2]]
        print(f"    ✓ {name[:35]:35s} → {len(d['passages'])} passages ({urls})")
    else:
        print(f"    ✗ {name[:35]:35s} → falls back to venue_corpus")

print("└──────────────────────────────────────────────────────────────────────┘")

# ─── EVIDENCE 2: Generate one tour ─────────────────────────────────────────
print("\n┌─ EVIDENCE 2: Generate one French Riviera cycling tour ───────────────┐")
print("  Bypassing cache to force fresh generation with stop_corpus...")

# Bypass cache to force fresh generation
import tour_cache_layer1
tour_cache_layer1.get_cached_tour = lambda *a, **kw: None

start_time = time.time()
from generate_tour_text import generate_tour_text

output_file = os.path.join(_project_root, "tours", "LOCAL183_test_riviera.txt")
tour_text, out_path, coords = generate_tour_text(
    location="French Riviera cycling tour, France",
    tour_type="biking",
    output_file=output_file,
    total_stops=15,
)
elapsed = time.time() - start_time

if not tour_text:
    print("  ERROR: Tour generation returned None — aborting")
    sys.exit(1)

word_count = len(tour_text.split())
print(f"\n  ✓ Tour generated in {elapsed:.1f}s ({word_count} words)")
print(f"  Output: {out_path}")

# Store with is_test=true
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test, storied_mode, tour_content)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id
""", (
    'French Riviera cycling tour, France - Cycling Tour [LOCAL-183]',
    'French Riviera cycling tour, France',
    15,
    True,
    True,
    tour_text,
))
new_tour_id = cur.fetchone()[0]
conn.commit()
conn.close()
print(f"  ✓ Stored as tour_id={new_tour_id} (is_test=true)")

print("└──────────────────────────────────────────────────────────────────────┘")

# ─── EVIDENCE 3: Run detector ──────────────────────────────────────────────
print("\n┌─ EVIDENCE 3: Anchor detection on new tour ───────────────────────────┐")

from stop_anchor_detector_v2_with_stop_corpus import analyze_tour_with_stop_corpus

conn = get_connection()
result = analyze_tour_with_stop_corpus(new_tour_id, conn)

if result.get('error'):
    print(f"  ERROR: {result['error']}")
else:
    summary = result['summary']
    scored = summary['ANCHORED'] + summary['NO_ANCHOR'] + summary['UNLINKED_ENTITY']
    anchored = summary['ANCHORED']
    pct = (anchored / scored * 100) if scored > 0 else 0
    
    print(f"  Tour {new_tour_id}: {anchored}/{scored} = {pct:.1f}% ANCHORED")
    print(f"    ANCHORED:        {summary['ANCHORED']}")
    print(f"    NO_ANCHOR:       {summary['NO_ANCHOR']}")
    print(f"    UNLINKED_ENTITY: {summary['UNLINKED_ENTITY']}")
    print(f"    NAVIGATION:      {summary['NAVIGATION']}")
    print(f"    Stops with stop_corpus: {sum(1 for s in result['stops'] if s.get('has_stop_corpus'))}")
    print()
    print(f"  Baselines (from D57, same detector, same rules):")
    print(f"    Tour 29 (field-tested, old gen): 32.3% ANCHORED")
    print(f"    Tour 152 (new gen, no corpus):   12.9% ANCHORED")
    print(f"    Tour {new_tour_id} (LOCAL-183):           {pct:.1f}% ANCHORED")
    
    # Show per-stop breakdown
    print(f"\n  Per-stop ANCHORED:")
    for stop in result['stops']:
        n_anchored = sum(1 for p in stop['paragraphs'] if p['classification'] == 'ANCHORED')
        n_scored = sum(1 for p in stop['paragraphs'] if p['classification'] != 'NAVIGATION')
        stop_pct = (n_anchored / n_scored * 100) if n_scored > 0 else 0
        corpus_mark = "✓" if stop.get('has_stop_corpus') else "✗"
        print(f"    {corpus_mark} {stop['title'][:35]:35s} {n_anchored}/{n_scored} = {stop_pct:.0f}%")

conn.close()

# Verify Nice list unchanged
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT array_agg(id ORDER BY id) FROM audio_tours
    WHERE id IN (1,12,14,17,21,24,27,28,29)
    AND (is_test IS NOT TRUE)
""")
nice_result = cur.fetchone()[0]
conn.close()
print(f"\n  ✓ Nice production list: {nice_result}")

print("└──────────────────────────────────────────────────────────────────────┘")

# ─── Summary ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("LOCAL-183 EVIDENCE COMPLETE")
print("=" * 70)

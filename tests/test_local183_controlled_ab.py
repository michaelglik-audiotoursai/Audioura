#!/usr/bin/env python3
"""tests/test_local183_controlled_ab.py — LOCAL-183 round 2

CONTROLLED A/B EXPERIMENT: Same location, same request, corpus wiring ON vs OFF.

The confound in round 1 was different itineraries between tours. This script
generates two tours from the same request and checks whether the stop lists
match. If they don't, that is reported as a finding (the generator picks
different stops due to LLM stochasticity, not corpus influence — the corpus
is only injected AFTER stop selection).

Design:
  Run A: DISABLE_STOP_CORPUS=1 — stop_corpus_data stays empty, no injection
  Run B: DISABLE_STOP_CORPUS unset — full wiring active
  Both: same location, same stop count, STORIED_MODE=true

Cost: ~$0.20 (two tours × ~$0.10). Ceiling: $0.50.
"""
import sys
import os
import json
import time
import re

# ─── Environment ────────────────────────────────────────────────────────────
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

# Bypass cache for both runs
import tour_cache_layer1
tour_cache_layer1.get_cached_tour = lambda *a, **kw: None

print("=" * 70)
print("LOCAL-183 ROUND 2: CONTROLLED A/B — corpus wiring ON vs OFF")
print("=" * 70)

# ─── Helper ─────────────────────────────────────────────────────────────────

def parse_stops_from_content(content: str):
    """Parse stop titles from tour content."""
    stops = []
    for line in content.split('\n'):
        m = re.match(r'^Stop\s+\d+:\s*(.+)', line)
        if m:
            stops.append(m.group(1).strip())
    return stops


def run_generation(label, disable_corpus):
    """Run one generation and return (tour_text, tour_id, elapsed, stop_names)."""
    if disable_corpus:
        os.environ['DISABLE_STOP_CORPUS'] = '1'
    elif 'DISABLE_STOP_CORPUS' in os.environ:
        del os.environ['DISABLE_STOP_CORPUS']

    print(f"\n{'─' * 60}")
    print(f"  RUN {label}: DISABLE_STOP_CORPUS={'1' if disable_corpus else '(unset)'}")
    print(f"{'─' * 60}")

    # Must reimport to clear any cached state
    # Actually generate_tour_text checks env at runtime, no reimport needed
    from generate_tour_text import generate_tour_text

    output_file = os.path.join(_project_root, "tours", f"LOCAL183_r2_{label.lower().replace(' ', '_')}.txt")
    start = time.time()
    tour_text, out_path, coords = generate_tour_text(
        location="French Riviera cycling tour, France",
        tour_type="biking",
        output_file=output_file,
        total_stops=15,
    )
    elapsed = time.time() - start

    if not tour_text:
        print(f"  ERROR: Generation returned None for {label}")
        return None, None, elapsed, []

    stop_names = parse_stops_from_content(tour_text)
    word_count = len(tour_text.split())
    print(f"\n  ✓ {label}: {word_count} words, {len(stop_names)} stops in {elapsed:.1f}s")

    # Store with is_test=true
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test, storied_mode, tour_content, stops_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        f'French Riviera Cycling [LOCAL-183 R2 {label}]',
        'French Riviera cycling tour, France',
        15,
        True,
        True,
        tour_text,
        len(stop_names),
    ))
    tour_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    print(f"  ✓ Stored as tour_id={tour_id} (is_test=true, stops_count={len(stop_names)})")

    return tour_text, tour_id, elapsed, stop_names


# ─── RUN A: corpus DISABLED ─────────────────────────────────────────────────
print("\n┌─ RUN A: Generation WITHOUT stop_corpus (control) ──────────────────┐")
text_a, id_a, time_a, stops_a = run_generation("A_no_corpus", disable_corpus=True)
if text_a is None:
    print("FATAL: Run A failed")
    sys.exit(1)
print("└──────────────────────────────────────────────────────────────────────┘")

# ─── RUN B: corpus ENABLED ──────────────────────────────────────────────────
print("\n┌─ RUN B: Generation WITH stop_corpus (treatment) ──────────────────┐")
text_b, id_b, time_b, stops_b = run_generation("B_with_corpus", disable_corpus=False)
if text_b is None:
    print("FATAL: Run B failed")
    sys.exit(1)
print("└──────────────────────────────────────────────────────────────────────┘")

# ─── ITINERARY COMPARISON ───────────────────────────────────────────────────
print("\n┌─ ITINERARY COMPARISON ──────────────────────────────────────────────┐")
print(f"  Run A ({id_a}) stops ({len(stops_a)}):")
for s in stops_a:
    print(f"    {s}")
print(f"\n  Run B ({id_b}) stops ({len(stops_b)}):")
for s in stops_b:
    print(f"    {s}")

# Check overlap
set_a = set(s.lower().strip() for s in stops_a)
set_b = set(s.lower().strip() for s in stops_b)
shared = set_a & set_b
only_a = set_a - set_b
only_b = set_b - set_a
pct_overlap = len(shared) / max(len(set_a), len(set_b), 1) * 100

print(f"\n  Overlap: {len(shared)}/{max(len(set_a), len(set_b))} stops = {pct_overlap:.0f}%")
if shared:
    print(f"  Shared: {sorted(shared)}")
if only_a:
    print(f"  Only in A (no corpus): {sorted(only_a)}")
if only_b:
    print(f"  Only in B (with corpus): {sorted(only_b)}")

if pct_overlap < 80:
    print(f"\n  ⚠ FINDING: Itineraries differ substantially ({pct_overlap:.0f}% overlap).")
    print(f"    The corpus wiring operates AFTER stop selection (line ~4862 of")
    print(f"    generate_tour_text.py, vs stop selection at line ~3328). Different")
    print(f"    stops are due to LLM stochasticity, not corpus influence.")
    print(f"    A clean comparison requires a FIXED stop list injected into both runs.")
else:
    print(f"\n  ✓ Itineraries overlap enough for comparison ({pct_overlap:.0f}%)")

print("└──────────────────────────────────────────────────────────────────────┘")

# ─── ANCHOR DETECTION ON BOTH ──────────────────────────────────────────────
print("\n┌─ ANCHOR DETECTION: both tours (unchanged detector) ────────────────┐")

sys.path.insert(0, os.path.join(_project_root, 'tests'))
from stop_anchor_detector_v2_with_stop_corpus import analyze_tour_with_stop_corpus

conn = get_connection()


def run_detector(tour_id, label):
    """Run detector and return (overall_pct, per_stop_breakdown)."""
    result = analyze_tour_with_stop_corpus(tour_id, conn)
    if result.get('error'):
        print(f"  ERROR on {label}: {result['error']}")
        return 0, []

    summary = result['summary']
    scored = summary['ANCHORED'] + summary['NO_ANCHOR'] + summary['UNLINKED_ENTITY']
    anchored = summary['ANCHORED']
    pct = (anchored / scored * 100) if scored > 0 else 0

    breakdown = []
    for stop in result['stops']:
        n_a = sum(1 for p in stop['paragraphs'] if p['classification'] == 'ANCHORED')
        n_s = sum(1 for p in stop['paragraphs'] if p['classification'] != 'NAVIGATION')
        s_pct = (n_a / n_s * 100) if n_s > 0 else 0
        breakdown.append({
            'title': stop['title'],
            'anchored': n_a,
            'scored': n_s,
            'pct': s_pct,
            'has_corpus': stop.get('has_stop_corpus', False),
        })

    print(f"\n  {label} (tour {tour_id}): {anchored}/{scored} = {pct:.1f}% ANCHORED")
    print(f"    ANCHORED={summary['ANCHORED']} NO_ANCHOR={summary['NO_ANCHOR']} UNLINKED_ENTITY={summary['UNLINKED_ENTITY']} NAVIGATION={summary['NAVIGATION']}")
    return pct, breakdown


pct_a, breakdown_a = run_detector(id_a, "A (no corpus)")
pct_b, breakdown_b = run_detector(id_b, "B (with corpus)")
conn.close()

# ─── PER-STOP BREAKDOWN ────────────────────────────────────────────────────
print(f"\n  Per-stop breakdown:")
print(f"  {'Stop':<35s} {'A (no corpus)':<15s} {'B (with corpus)':<15s} {'Corpus?'}")
print(f"  {'─' * 35} {'─' * 15} {'─' * 15} {'─' * 7}")

# If stops differ, show all from both
all_stops = []
seen = set()
for s in breakdown_a:
    if s['title'].lower() not in seen:
        all_stops.append(s['title'])
        seen.add(s['title'].lower())
for s in breakdown_b:
    if s['title'].lower() not in seen:
        all_stops.append(s['title'])
        seen.add(s['title'].lower())

for title in all_stops:
    # Find in A
    row_a = next((s for s in breakdown_a if s['title'].lower() == title.lower()), None)
    row_b = next((s for s in breakdown_b if s['title'].lower() == title.lower()), None)
    a_str = f"{row_a['anchored']}/{row_a['scored']}={row_a['pct']:.0f}%" if row_a else "—"
    b_str = f"{row_b['anchored']}/{row_b['scored']}={row_b['pct']:.0f}%" if row_b else "—"
    corpus_mark = ""
    if row_b and row_b.get('has_corpus'):
        corpus_mark = "✓"
    elif row_a and row_a.get('has_corpus'):
        corpus_mark = "✓"
    print(f"  {title[:35]:<35s} {a_str:<15s} {b_str:<15s} {corpus_mark}")

print("└──────────────────────────────────────────────────────────────────────┘")

# ─── SUMMARY ───────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Run A (no corpus):    tour {id_a}, {pct_a:.1f}% ANCHORED, {len(stops_a)} stops")
print(f"  Run B (with corpus):  tour {id_b}, {pct_b:.1f}% ANCHORED, {len(stops_b)} stops")
print(f"  Itinerary overlap:    {pct_overlap:.0f}% ({len(shared)} shared stops)")
print(f"  Baselines:")
print(f"    Tour 29 (field-tested):       32.3% ANCHORED")
print(f"    Tour 152 (gen, no corpus):    12.9% ANCHORED")
delta = pct_b - pct_a
print(f"  Delta (B - A):                  {delta:+.1f} percentage points")
if pct_overlap < 80:
    print(f"\n  ⚠ CONFOUND: itineraries differ ({pct_overlap:.0f}% overlap).")
    print(f"    Delta cannot be attributed solely to corpus wiring.")
    print(f"    See ITINERARY COMPARISON section above.")
elif delta > 2:
    print(f"\n  ✓ Same itinerary, +{delta:.1f}pp — evidence that wiring improves generation.")
elif delta < -2:
    print(f"\n  ⚠ Same itinerary, {delta:.1f}pp — corpus may not help or prompt needs tuning.")
else:
    print(f"\n  ≈ Same itinerary, delta within noise ({delta:+.1f}pp).")

# ─── stops_count bug report ─────────────────────────────────────────────────
print(f"\n  NOTE (stops_count bug): Tours 153, 154, 156 have stops_count=0")
print(f"    despite parsing to ~15 stops. This script explicitly sets")
print(f"    stops_count={len(stops_a)} and {len(stops_b)} on the new tours.")
print(f"    Root cause: the generation service path does not persist stops_count")
print(f"    when inserting/updating the tour. Not fixed here (out of scope).")

# ─── Verify Nice list ──────────────────────────────────────────────────────
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT array_agg(id ORDER BY id) FROM audio_tours
    WHERE id IN (1,12,14,17,21,24,27,28,29)
    AND (is_test IS NOT TRUE)
""")
nice_list = cur.fetchone()[0]
conn.close()
assert nice_list == [1, 12, 14, 17, 21, 24, 27, 28, 29], f"Nice list changed! Got: {nice_list}"
print(f"\n  ✓ Nice production list verified: {nice_list}")

# ─── Cost check ─────────────────────────────────────────────────────────────
# Check api_call_logger for total cost
try:
    import api_call_logger
    if hasattr(api_call_logger, 'get_session_total'):
        total_cost = api_call_logger.get_session_total()
        print(f"  ✓ Total API cost this session: ${total_cost:.4f}")
        if total_cost > 0.50:
            print(f"  ⚠ EXCEEDED $0.50 ceiling! Investigate.")
except Exception:
    pass

print("\n" + "=" * 70)
print("LOCAL-183 ROUND 2 EVIDENCE COMPLETE")
print("=" * 70)

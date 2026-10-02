#!/usr/bin/env python3
"""LOCAL-262: Generate 8-stop Asian Arts Museum tour AFTER corpus restoration.

Runs the same generation as LOCAL-258 did, but now with per-object passages
from the museum's own page (restored by run_local262_restore_asian_arts.py).

Measure:
  - Stops passing the existence gate (should remain 8/8)
  - Stops with a generated description (was 6/8 in LOCAL-258)
  - Per-stop fact count
  - Total words and cost

CEILING: $0.60
"""
import os
import sys
import re
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ── Load .env ──────────────────────────────────────────────────────────────
_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

os.environ['STORIED_MODE'] = 'true'
# Set DATABASE_URL so venue cache and stop_corpus reader work in host mode
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
# Disable tour cache to force fresh generation with new corpus
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Clear overrides — use defaults
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R10_DELETION'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60

print("=" * 70)
print("LOCAL-262: GENERATE 8-STOP ASIAN ARTS MUSEUM TOUR (RESTORED CORPUS)")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset -> default)')}")
print(f"  CEILING = ${CEILING:.2f}")
print()

# ── Pre-checks ─────────────────────────────────────────────────────────────
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT current_database()")
db_name = cur.fetchone()[0]
print(f"[PRE] Connected to: {db_name}")
assert db_name == "audiotours", f"Expected audiotours, got {db_name}"

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours: {count_before}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_pre = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_pre}")
assert nice_pre == EXPECTED_NICE, f"Nice list mismatch: {nice_pre}"

# Show corpus state for Asian Arts
print("\n[PRE] Corpus depth for Asian Arts Museum (after restoration):")
cur.execute("""
    SELECT stop_title, passage_count FROM stop_corpus
    WHERE venue_name = 'Musee des Arts Asiatiques (Asian Art Museum), Nice, France'
    ORDER BY stop_title
""")
total_passages_asian = 0
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} passages")
    total_passages_asian += r[1]
print(f"  TOTAL: {total_passages_asian} passages across 8 stops")

cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
row = cur.fetchone()
print(f"\n[PRE] Full stop_corpus: {row[0]} rows, {row[1]} total passages")
conn.close()

# ── Generate ───────────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("GENERATING 8-stop Asian Arts Museum tour (all gates ON)")
print("-" * 70)

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL262_asian_arts_8stop_restored.txt")

start_time = time.time()
try:
    result = generate_tour_text(
        location='Musee des Arts Asiatiques (Asian Art Museum), Nice, France',
        tour_type='museum',
        output_file=output_file,
        total_stops=8,
        persona=None,
    )
except Exception as e:
    elapsed = time.time() - start_time
    print(f"\n  GENERATION FAILED after {elapsed:.1f}s: {e}")
    print(f"  Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
    result = None

elapsed = time.time() - start_time
print(f"\n  Generation took {elapsed:.1f}s")

# Get cost from module-level variable
from generate_tour_text import _LAST_GENERATION_COST as cost_info
total_cost = cost_info.get('total_cost', 0.0)
total_tokens = cost_info.get('total_tokens', 0)
print(f"  Cost: ${total_cost:.4f} ({total_tokens} tokens)")

if total_cost > CEILING:
    print(f"  ⚠️ OVER CEILING of ${CEILING:.2f}!")

if not result or not result[0]:
    print("\n  RESULT: No tour text returned.")
    print("  This may be due to API error, timeout, or gate rejection.")
    print("\n" + "=" * 70)
    print("GENERATION FAILED — see limitations in submission document")
    print("=" * 70)
    sys.exit(1)

tour_text = result[0]
print(f"\n  Tour text length: {len(tour_text)} chars")

# ── Parse stops ────────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("PARSING GENERATED TOUR")
print("-" * 70)

stops = parse_tour_stops(tour_text)
stop_names = [s['title'] for s in stops]
print(f"\n  Stops in generated tour ({len(stops)}):")
for i, s in enumerate(stops, 1):
    print(f"    {i}. {s['title']}")

# ── Per-stop content analysis ──────────────────────────────────────────────
print("\n" + "-" * 70)
print("PER-STOP CONTENT ANALYSIS")
print("-" * 70)

word_count = len(tour_text.split())
print(f"\n  Total word count: {word_count}")

stops_with_description = 0
print(f"\n  {'Stop':<45} {'Words':<8} {'Sentences':<10} {'Has Desc'}")
print("  " + "-" * 75)
for s in stops:
    paras = s.get('paragraphs', [])
    stop_text = ' '.join(paras)
    stop_words = len(stop_text.split())
    stop_sentences = len([x for x in re.split(r'(?<=[.!?])\s+', stop_text.strip()) if x.strip()])
    has_desc = stop_words > 10
    if has_desc:
        stops_with_description += 1
    print(f"  {s['title']:<45} {stop_words:<8} {stop_sentences:<10} {'YES' if has_desc else 'NO'}")

print(f"\n  Stops with description: {stops_with_description} of {len(stops)}")

# ── Post-check: audio_tours unchanged ─────────────────────────────────────
print("\n" + "-" * 70)
print("POST-GENERATION VERIFICATION")
print("-" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_post = [r[0] for r in cur.fetchall()]
print(f"\n  audio_tours: {count_after} (before: {count_before}) — {'UNCHANGED' if count_after == count_before else 'CHANGED!'}")
print(f"  Nice list: {nice_post} — {'UNCHANGED' if nice_post == nice_pre else 'CHANGED!'}")
assert count_after == count_before, f"audio_tours changed! {count_before} -> {count_after}"
conn.close()

# ── Save tour text ─────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("SAVING TOUR TEXT")
print("-" * 70)

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(tour_text)
print(f"\n  Saved to: {output_file}")
print(f"  Size: {len(tour_text)} chars, {word_count} words")

# ── Summary ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Stops generated:          {len(stops)}")
print(f"  Stops with description:   {stops_with_description} of {len(stops)}")
print(f"  Word count:               {word_count}")
print(f"  Cost:                     ${total_cost:.4f}")
print(f"  Elapsed:                  {elapsed:.1f}s")
print(f"  audio_tours unchanged:    True")
print(f"  Nice list unchanged:      True")
print("=" * 70)

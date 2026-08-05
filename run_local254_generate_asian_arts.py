#!/usr/bin/env python3
"""LOCAL-254: Generate 8-stop Asian Arts Museum tour.

After enriching the stop_corpus with verified Wikipedia passages (33 total
across the 8 stops, mean 4.1), generate a tour to measure:
  - Which stops the model selects
  - Which stops get rejected by the existence gate (fabrications)
  - Factual density of the generated text

Suspected fabrication stops (D127, never enriched):
  Ulysses Grant au Japon, Kannon le bodhisattva de la compassion,
  Kannon a mille bras, Masque du vieillard kojo.

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

# Clear overrides — use defaults
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R10_DELETION'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60

FABRICATION_STOPS = [
    "Ulysses Grant au Japon",
    "Kannon, le bodhisattva de la compassion",
    "Kannon a mille bras",
    "Masque du vieillard kojo",
]

print("=" * 70)
print("LOCAL-254: GENERATE 8-STOP ASIAN ARTS MUSEUM TOUR")
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
print("\n[PRE] Corpus depth for Asian Arts Museum:")
cur.execute("""
    SELECT stop_title, passage_count FROM stop_corpus
    WHERE venue_name = 'Musee des Arts Asiatiques (Asian Art Museum), Nice, France'
    ORDER BY stop_title
""")
total_passages_asian = 0
for r in cur.fetchall():
    fab_mark = " ** FABRICATION **" if r[0] in FABRICATION_STOPS else ""
    print(f"  {r[0]}: {r[1]} passages{fab_mark}")
    total_passages_asian += r[1]
print(f"  TOTAL: {total_passages_asian} passages across stops")

cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
row = cur.fetchone()
print(f"\n[PRE] Full stop_corpus: {row[0]} rows, {row[1]} total passages")
conn.close()

# ── Generate ───────────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("GENERATING 8-stop Asian Arts Museum tour (all gates ON)")
print("-" * 70)

from generate_tour_text import generate_tour_text

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL254_asian_arts_8stop.txt")

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
    result = None

elapsed = time.time() - start_time
print(f"\n  Generation took {elapsed:.1f}s")

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
    in_fabrication = any(
        f.lower() in s['title'].lower() or s['title'].lower() in f.lower()
        for f in FABRICATION_STOPS
    )
    fab_mark = " ** SUSPECTED FABRICATION **" if in_fabrication else ""
    print(f"    {i}. {s['title']}{fab_mark}")

# ── Identify existence gate rejections ─────────────────────────────────────
print("\n" + "-" * 70)
print("EXISTENCE GATE ANALYSIS")
print("-" * 70)

# Check which stops from FABRICATION list were selected vs rejected
selected_fabs = [s for s in stop_names if any(
    f.lower() in s.lower() or s.lower() in f.lower()
    for f in FABRICATION_STOPS
)]
rejected_fabs = [f for f in FABRICATION_STOPS if not any(
    f.lower() in s.lower() or s.lower() in f.lower()
    for s in stop_names
)]

print(f"\n  Fabrication stops that APPEARED in tour: {len(selected_fabs)}")
for s in selected_fabs:
    print(f"    - {s}")

print(f"\n  Fabrication stops REJECTED by existence gate: {len(rejected_fabs)}")
for s in rejected_fabs:
    print(f"    - {s}")

# ── Word count and fact density ────────────────────────────────────────────
print("\n" + "-" * 70)
print("CONTENT METRICS")
print("-" * 70)

word_count = len(tour_text.split())
print(f"\n  Total word count: {word_count}")

# Per-stop analysis
print(f"\n  Per-stop content:")
for s in stops:
    paras = s.get('paragraphs', [])
    stop_text = ' '.join(paras)
    stop_words = len(stop_text.split())
    stop_sentences = len(re.split(r'(?<=[.!?])\s+', stop_text.strip()))
    print(f"    {s['title']}: {stop_words} words, {stop_sentences} sentences")

# ── Post-check: audio_tours unchanged ─────────────────────────────────────
print("\n" + "-" * 70)
print("POST-GENERATION VERIFICATION")
print("-" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"\n  audio_tours BEFORE: {count_before}")
print(f"  audio_tours AFTER:  {count_after}")
print(f"  Unchanged: {count_after == count_before}")
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
print(f"  Stops generated: {len(stops)}")
print(f"  Stop names: {stop_names}")
print(f"  Fabrication stops in output: {len(selected_fabs)}")
print(f"  Fabrication stops rejected: {len(rejected_fabs)}")
print(f"  Word count: {word_count}")
print(f"  Elapsed: {elapsed:.1f}s")
print(f"  audio_tours unchanged: True")
print("=" * 70)

#!/usr/bin/env python3
"""LOCAL-209: Prove the EMPTY corpus gate fires and constrains outdoor stops.

Generates a 2-stop French Riviera cycling tour targeting Cap d'Antibes +
Villefranche-sur-Mer, 3 runs gate ON, 3 gate OFF.

Classifies each sentence of the corpus-less stop's paragraphs:
  SOURCED          — traceable to a corpus passage (quotes it)
  UNSOURCED_SPECIFIC — a date, number, name, nickname, or attribution with nothing behind it
  GENERAL          — no checkable claim

The deciding number: UNSOURCED_SPECIFIC per paragraph, gate on vs off.
"""
import os
import sys
import re
import json
import time
import datetime

# ─── Project root ────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ─── Load .env for API keys (never hardcode) ─────────────────────────────────
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

# ─── Database connection ─────────────────────────────────────────────────────
from db_connection import get_connection, check_db_available

RUN_TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

print("=" * 70)
print("LOCAL-209: EMPTY Corpus Gate — 2-Stop French Riviera Test")
print("=" * 70)
print(f"  Timestamp: {RUN_TS}")
print()

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

# ─── Pre-checks ─────────────────────────────────────────────────────────────
conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_pre = [r[0] for r in cur.fetchall()]
expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
visible_nice = [i for i in nice_rows_pre if i in expected_nice]
print(f"[PRE] Nice visible tour IDs: {visible_nice}")
assert visible_nice == expected_nice, f"Nice list mismatch: {visible_nice}"
conn.close()

# ─── Confirm Villefranche has NO corpus ──────────────────────────────────────
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT stop_title FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
      AND stop_title ILIKE '%villefranche%'
""")
villefranche_corpus = cur.fetchall()
print(f"\n[PRE] Villefranche in stop_corpus: {len(villefranche_corpus)} rows (expected: 0)")
assert len(villefranche_corpus) == 0, "Villefranche should have NO corpus row for this test"

# Get all corpus stop titles for reference
cur.execute("""
    SELECT stop_title FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
""")
corpus_stop_titles = set(r[0].lower() for r in cur.fetchall())
print(f"[PRE] Stops WITH corpus in 'French Riviera walking area': {len(corpus_stop_titles)}")
conn.close()

# ─── Generation runs ─────────────────────────────────────────────────────────
from generate_tour_text import generate_tour_text
from stop_anchor_detector_v2 import parse_tour_stops

# Use a location string that strongly hints at the target stops
LOCATION = "Cap d'Antibes to Villefranche-sur-Mer, French Riviera, France"

all_results = []  # list of {arm, run, tour_text, uncovered_stop, uncovered_paras, tour_id}

for arm in ['gate_on', 'gate_off']:
    for run_idx in range(1, 4):
        print(f"\n{'=' * 70}")
        print(f"  RUN {run_idx}/3 — arm={arm}")
        print(f"{'=' * 70}")

        # Set environment
        os.environ['STORIED_MODE'] = 'true'
        # Clear model override (use default gpt-3.5-turbo)
        for k in ('TOUR_LLM_MODEL', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
            if k in os.environ:
                del os.environ[k]

        if arm == 'gate_off':
            os.environ['DISABLE_CORPUS_GATE'] = '1'
        else:
            if 'DISABLE_CORPUS_GATE' in os.environ:
                del os.environ['DISABLE_CORPUS_GATE']

        print(f"  DISABLE_CORPUS_GATE = {os.environ.get('DISABLE_CORPUS_GATE', '(unset → ON)')}")

        output_file = os.path.join(
            PROJECT_ROOT, "tours",
            f"LOCAL209_{arm}_run{run_idx}.txt"
        )

        start_time = time.time()
        result = generate_tour_text(
            location=LOCATION,
            tour_type="biking",
            output_file=output_file,
            total_stops=2,
            persona=None,
        )
        elapsed = time.time() - start_time

        if not result or not result[0]:
            print(f"  FATAL: Generation returned None after {elapsed:.1f}s")
            all_results.append({
                'arm': arm, 'run': run_idx,
                'tour_text': None, 'uncovered_stop': None,
                'uncovered_paras': [], 'tour_id': None, 'error': True,
            })
            continue

        tour_text = result[0]
        print(f"\n  ✓ Generated: {len(tour_text)} chars in {elapsed:.1f}s")

        # Parse stops
        stops = parse_tour_stops(tour_text)
        stop_names = [s['title'] for s in stops]
        print(f"  Stops: {stop_names}")

        # Identify which stop(s) have no corpus
        uncovered_stop = None
        uncovered_paras = []
        for s in stops:
            title_lower = s['title'].lower()
            # Check if this stop has corpus (fuzzy match against corpus titles)
            has_corpus = any(
                ct in title_lower or title_lower in ct
                for ct in corpus_stop_titles
            )
            if not has_corpus:
                uncovered_stop = s['title']
                uncovered_paras = s.get('paragraphs', [])
                print(f"  → Uncovered stop (no corpus): {uncovered_stop}")
                break

        if not uncovered_stop:
            print(f"  ⚠ All stops have corpus — cannot measure EMPTY gate effect")
            # Still store for completeness
            uncovered_stop = stop_names[-1]  # last stop as fallback
            for s in stops:
                if s['title'] == uncovered_stop:
                    uncovered_paras = s.get('paragraphs', [])

        # Store in DB with unique name
        tour_name = f'Riviera LOCAL-209 {arm} r{run_idx} {RUN_TS}'
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audio_tours (
                tour_name, request_string, number_requested,
                is_test, storied_mode, tour_content, stops_count,
                lat, lng
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL)
            RETURNING id
        """, (
            tour_name,
            LOCATION,
            2,
            True,
            True,
            tour_text,
            len(stops),
        ))
        tour_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        print(f"  ✓ Stored as tour_id={tour_id} ('{tour_name}')")

        all_results.append({
            'arm': arm, 'run': run_idx,
            'tour_text': tour_text, 'uncovered_stop': uncovered_stop,
            'uncovered_paras': uncovered_paras,
            'tour_id': tour_id, 'error': False,
        })


# ─── Sentence classification ─────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SENTENCE CLASSIFICATION")
print("=" * 70)

# Patterns that indicate a specific claim
SPECIFIC_PATTERNS = [
    (r'\b\d{1,2}(?:st|nd|rd|th)\s+century\b', 'century_claim'),
    (r'\b(?:1[0-9]{3}|20[0-2][0-9])\b', 'year'),
    (r'\b\d{2,}(?:\s*(?:feet|ft|meters?|metres?|km|miles?|m)\b)', 'measurement'),
    (r'\b(?:known as|called|nicknamed|dubbed)\s', 'nickname'),
    (r'"[^"]{3,}"', 'quoted_name'),
    (r'\u201c[^\u201d]{3,}\u201d', 'quoted_name'),  # smart quotes
    (r'\b(?:built|founded|constructed|established|erected|opened)\s+(?:in|by|during)\s+\d', 'founding_claim'),
    (r'\b(?:King|Queen|Emperor|Duke|Count|Baron|Sir|Saint|St\.)\s+[A-Z]', 'historical_figure'),
    (r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b', 'proper_name'),  # 2-3 word proper names
    (r'\b\d{3,}\s*(?:feet|ft|meters?|metres?)\b', 'measurement'),
    (r'\b(?:dating\s+(?:back\s+)?to|dates?\s+(?:back\s+)?to)\b', 'dating_claim'),
]

def classify_sentence(sentence):
    """Classify a single sentence (no corpus for this stop → nothing is SOURCED)."""
    sentence = sentence.strip()
    if not sentence or len(sentence) < 10:
        return 'GENERAL', None

    # Check for specific claims
    for pattern, label in SPECIFIC_PATTERNS:
        m = re.search(pattern, sentence, re.IGNORECASE)
        if m:
            return 'UNSOURCED_SPECIFIC', f"{label}: {m.group()}"

    return 'GENERAL', None


# Classify each run
classification_results = []
for r in all_results:
    if r.get('error'):
        continue
    run_classifications = []
    for para in r['uncovered_paras']:
        para_text = para if isinstance(para, str) else para.get('text', '')
        sentences = re.split(r'(?<=[.!?])\s+', para_text)
        para_classes = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue
            cls, evidence = classify_sentence(sent)
            para_classes.append({'sentence': sent, 'class': cls, 'evidence': evidence})
        run_classifications.append(para_classes)
    classification_results.append({
        'arm': r['arm'], 'run': r['run'], 'tour_id': r['tour_id'],
        'uncovered_stop': r['uncovered_stop'],
        'paragraphs': run_classifications,
    })

# ─── Report ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("RESULTS: Uncovered Stop Sentence Classification")
print("=" * 70)

for cr in classification_results:
    print(f"\n--- {cr['arm']} run {cr['run']} (tour_id={cr['tour_id']}, stop='{cr['uncovered_stop']}') ---")
    total_sourced = 0
    total_unsourced_specific = 0
    total_general = 0
    for pi, para_classes in enumerate(cr['paragraphs'], 1):
        print(f"  Paragraph {pi}:")
        for sc in para_classes:
            marker = sc['class']
            ev = f" [{sc['evidence']}]" if sc['evidence'] else ""
            sent_preview = sc['sentence'][:90] + ("..." if len(sc['sentence']) > 90 else "")
            print(f"    [{marker}]{ev} {sent_preview}")
            if marker == 'SOURCED':
                total_sourced += 1
            elif marker == 'UNSOURCED_SPECIFIC':
                total_unsourced_specific += 1
            else:
                total_general += 1
    print(f"  TOTALS: SOURCED={total_sourced}, UNSOURCED_SPECIFIC={total_unsourced_specific}, GENERAL={total_general}")

# ─── Summary table ───────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY TABLE: UNSOURCED_SPECIFIC per paragraph (uncovered stop only)")
print("=" * 70)
print(f"{'arm':<12} {'run':<5} {'tour_id':<8} {'stop':<25} {'paras':<6} {'US_count':<10} {'per_para':<10}")
print("-" * 80)

gate_on_totals = []
gate_off_totals = []
for cr in classification_results:
    total_us = 0
    n_paras = len(cr['paragraphs'])
    for para_classes in cr['paragraphs']:
        for sc in para_classes:
            if sc['class'] == 'UNSOURCED_SPECIFIC':
                total_us += 1
    per_para = total_us / max(n_paras, 1)
    print(f"{cr['arm']:<12} {cr['run']:<5} {cr['tour_id']:<8} {cr['uncovered_stop']:<25} {n_paras:<6} {total_us:<10} {per_para:<10.2f}")
    if cr['arm'] == 'gate_on':
        gate_on_totals.append(per_para)
    else:
        gate_off_totals.append(per_para)

if gate_on_totals and gate_off_totals:
    avg_on = sum(gate_on_totals) / len(gate_on_totals)
    avg_off = sum(gate_off_totals) / len(gate_off_totals)
    print(f"\n  Average UNSOURCED_SPECIFIC per paragraph:")
    print(f"    gate ON:  {avg_on:.2f}")
    print(f"    gate OFF: {avg_off:.2f}")
    if avg_off > 0:
        reduction = (1 - avg_on / avg_off) * 100
        print(f"    Reduction: {reduction:.0f}%")
    else:
        print(f"    (gate OFF produced no unsourced specifics — unusual)")

# ─── Post-checks ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours row count: {count_before} → {count_after}")
print(f"  Rows added: {count_after - count_before}")

cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_post = [r[0] for r in cur.fetchall()]
visible_nice_post = [i for i in nice_rows_post if i in expected_nice]
print(f"  Nice list after: {visible_nice_post}")
assert visible_nice_post == expected_nice, f"Nice list changed! {visible_nice_post}"
print(f"  ✓ Nice list unchanged")
conn.close()

# ─── Write evidence to file ──────────────────────────────────────────────────
evidence_file = os.path.join(PROJECT_ROOT, "LOCAL209_EVIDENCE.md")
with open(evidence_file, 'w') as f:
    f.write("# LOCAL-209: EMPTY Corpus Gate Evidence\n\n")
    f.write(f"Generated: {datetime.datetime.now().isoformat()}\n\n")
    f.write(f"## DB State\n\n")
    f.write(f"- audio_tours before: {count_before}\n")
    f.write(f"- audio_tours after: {count_after}\n")
    f.write(f"- Nice list: {visible_nice_post}\n\n")
    f.write("## Sentence Classification: Uncovered Stop\n\n")
    f.write("| arm | run | tour_id | stop | paragraphs | UNSOURCED_SPECIFIC | per_para |\n")
    f.write("|---|---|---|---|---|---|---|\n")
    for cr in classification_results:
        total_us = 0
        n_paras = len(cr['paragraphs'])
        for para_classes in cr['paragraphs']:
            for sc in para_classes:
                if sc['class'] == 'UNSOURCED_SPECIFIC':
                    total_us += 1
        per_para = total_us / max(n_paras, 1)
        f.write(f"| {cr['arm']} | {cr['run']} | {cr['tour_id']} | {cr['uncovered_stop']} | {n_paras} | {total_us} | {per_para:.2f} |\n")
    f.write("\n")
    if gate_on_totals and gate_off_totals:
        avg_on = sum(gate_on_totals) / len(gate_on_totals)
        avg_off = sum(gate_off_totals) / len(gate_off_totals)
        f.write(f"**Average UNSOURCED_SPECIFIC per paragraph: gate ON = {avg_on:.2f}, gate OFF = {avg_off:.2f}**\n\n")
        if avg_off > 0:
            reduction = (1 - avg_on / avg_off) * 100
            f.write(f"**Reduction: {reduction:.0f}%**\n\n")

    f.write("## Full Sentence Classifications\n\n")
    for cr in classification_results:
        f.write(f"### {cr['arm']} run {cr['run']} (tour_id={cr['tour_id']}, stop='{cr['uncovered_stop']}')\n\n")
        for pi, para_classes in enumerate(cr['paragraphs'], 1):
            f.write(f"**Paragraph {pi}:**\n\n")
            for sc in para_classes:
                ev = f" `[{sc['evidence']}]`" if sc['evidence'] else ""
                f.write(f"- `{sc['class']}`{ev}: {sc['sentence']}\n")
            f.write("\n")

    f.write("## Raw Paragraphs (uncovered stop)\n\n")
    for r in all_results:
        if r.get('error'):
            continue
        f.write(f"### {r['arm']} run {r['run']} (tour_id={r['tour_id']}, stop='{r['uncovered_stop']}')\n\n")
        for pi, para in enumerate(r['uncovered_paras'], 1):
            para_text = para if isinstance(para, str) else para.get('text', '')
            f.write(f"**Paragraph {pi}:**\n> {para_text}\n\n")

print(f"\n  ✓ Evidence written to: {evidence_file}")
print("\nDONE.")

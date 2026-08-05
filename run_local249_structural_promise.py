#!/usr/bin/env python3
"""LOCAL-249: Structural promise detection — verb-independent subject-matter approach.

Replaces R10's idiom-matching with structural detection: abstract subject-matter
nouns in a sentence, regardless of carrying verb, constitute a promise.

Steps:
1. Boundary verification (9 rows)
2. Corpus-wide residual measurement (R1/R7/R8/R9/R10 before and after)
3. Generate RIVIERA_2STOP_ROUND6.md
4. Per-deletion evidence
5. DB safety checks
"""
import os
import sys
import re
import io
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env
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

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]

print("=" * 70)
print("LOCAL-249: STRUCTURAL PROMISE DETECTION (VERB-INDEPENDENT)")
print("=" * 70)

# ======================================================================
# PRE-CHECKS
# ======================================================================
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

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
visible_nice_pre = [i for i in nice_rows_pre if i in EXPECTED_NICE]
print(f"[PRE] Nice visible tour IDs: {visible_nice_pre}")
assert visible_nice_pre == EXPECTED_NICE, f"Nice list mismatch! Got {visible_nice_pre}"
conn.close()

# ======================================================================
# STEP 1: BOUNDARY VERIFICATION (9 rows)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: BOUNDARY VERIFICATION — 9 ROWS")
print("=" * 70)

from style_validator_detector import (
    check_r10_unfulfilled_promise, _sentence_has_promise,
    _sentence_has_concrete_payload, _extract_subject_matter,
    _split_sentences, _is_style_navigation_sentence,
    _sentence_has_subject_matter_promise,
)

print("\n  --- MUST FIRE (promise, unsubstantiated) ---")
fire_cases = [
    "As you cycle along the coastal path, the azure waters and lush greenery create a striking contrast, hinting at the secrets of the elite who have graced these grounds.",
    "The Villa Ephrussi de Rothschild, a pink palace visible from the path, stands as a testament to a bygone era's grandeur, its gardens echoing with stories of extravagant parties and quiet introspection.",
    "These stops reveal different facets of opulence and understated elegance, where the lives of the famous and the forgotten intertwine in a dance of history and modernity.",
    "The coastline holds stories that deepen the allure of the French Riviera.",
]

for s in fire_cases:
    r10 = check_r10_unfulfilled_promise([s], 0)
    subjects = _extract_subject_matter(s)
    ok = r10 is not None
    print(f"    {'✓' if ok else '✗'} FIRES subjects={subjects}: \"{s[:80]}...\"")
    assert ok, f"BOUNDARY FAIL: should fire: {s}"

print("\n  --- MUST STAY SILENT ---")
silent_cases = [
    "In January 1888, Claude Monet painted the same shoreline from Juan-les-Pins.",
    "The Hôtel du Cap-Eden-Roc was built in 1870 at the southern tip.",
    "Start cycling south on the main road with the sea on your right.",
    "The Rue Obscure is a 130-metre fortified street built for protection.",
    "Èze was first settled near Mount Bastide around 200 BC.",
]

for s in silent_cases:
    r10 = check_r10_unfulfilled_promise([s], 0)
    ok = r10 is None
    print(f"    {'✓' if ok else '✗'} SILENT: \"{s[:80]}\"")
    assert ok, f"BOUNDARY FAIL: should be silent: {s}"

print("\n  ALL 9 BOUNDARY ROWS PASS ✓")

# ======================================================================
# STEP 2: CORPUS-WIDE RESIDUAL MEASUREMENT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: CORPUS-WIDE RESIDUALS (R1, R7, R8, R9, R10)")
print("=" * 70)

from style_validator_detector import (
    check_r1_imperatives, check_r7_hallucinated_sensory,
    check_r8_prompt_leakage, check_r9_generic,
    _R10_PROMISE_COMPILED, _sentence_has_structural_promise,
    _is_style_navigation_paragraph, _R10_LOOKAHEAD,
    _delivery_matches_promise,
)

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT id, tour_content FROM audio_tours
    WHERE is_test IS NOT TRUE AND tour_content IS NOT NULL AND tour_content != ''
    ORDER BY id
""")
tours = cur.fetchall()
conn.close()

print(f"  Corpus: {len(tours)} non-test tours")

r10_before_total = 0
r10_after_total = 0
r1_total = 0
r7_total = 0
r8_total = 0
r9_total = 0
total_sentences = 0
total_content_paras = 0
r1_para_count = 0


def _old_sentence_has_promise(sentence):
    """Simulate pre-LOCAL-249 promise detection (no subject-matter path)."""
    for pat in _R10_PROMISE_COMPILED:
        if pat.search(sentence):
            return True
    if _sentence_has_structural_promise(sentence):
        return True
    return False


for tour_id, tour_content in tours:
    stops = parse_tour_stops(tour_content)
    for stop in stops:
        for para in stop['paragraphs']:
            if _is_style_navigation_paragraph(para):
                continue
            total_content_paras += 1
            sentences = _split_sentences(para)
            total_sentences += len(sentences)

            para_has_r1 = False

            for i, sent in enumerate(sentences):
                if len(sent.strip()) < 15:
                    continue
                if _is_style_navigation_sentence(sent):
                    continue

                r1_f = check_r1_imperatives(sent)
                if r1_f:
                    r1_total += len(r1_f)
                    para_has_r1 = True

                r7_total += len(check_r7_hallucinated_sensory(sent))
                r8_total += len(check_r8_prompt_leakage(sent))
                r9_total += len(check_r9_generic(sent))

                # R10 AFTER (new code)
                r10_after = check_r10_unfulfilled_promise(sentences, i)
                if r10_after:
                    r10_after_total += 1

                # R10 BEFORE (simulate old behavior)
                if _old_sentence_has_promise(sent):
                    if not _sentence_has_concrete_payload(sent):
                        fulfilled = False
                        for offset in range(1, _R10_LOOKAHEAD + 1):
                            next_idx = i + offset
                            if next_idx >= len(sentences):
                                break
                            next_sent = sentences[next_idx].strip()
                            if not next_sent:
                                continue
                            if _sentence_has_concrete_payload(next_sent):
                                if _delivery_matches_promise(sent, next_sent):
                                    fulfilled = True
                                    break
                        if not fulfilled and i > 0:
                            prev_sent = sentences[i - 1].strip()
                            if prev_sent and _sentence_has_concrete_payload(prev_sent):
                                if _delivery_matches_promise(sent, prev_sent):
                                    fulfilled = True
                        if not fulfilled:
                            r10_before_total += 1

            if para_has_r1:
                r1_para_count += 1

r1_rate = r1_para_count / total_content_paras * 100 if total_content_paras else 0
r10_mult = r10_after_total / r10_before_total if r10_before_total else float('inf')

print(f"  Content paragraphs: {total_content_paras}")
print(f"  Non-nav sentences:  {total_sentences}")
print(f"\n  R1:  {r1_total} sentences, {r1_para_count}/{total_content_paras} paragraphs ({r1_rate:.1f}%)")
print(f"  R7:  {r7_total}")
print(f"  R8:  {r8_total}")
print(f"  R9:  {r9_total}")
print(f"  R10 BEFORE: {r10_before_total}")
print(f"  R10 AFTER:  {r10_after_total}")
print(f"  R10 delta:  +{r10_after_total - r10_before_total}")
print(f"  R10 multiplier: {r10_mult:.1f}x")

assert r10_mult <= 3.0, f"R10 jumped {r10_mult:.1f}x — exceeds 3x threshold!"
print(f"\n  ✓ R10 within 3x threshold ({r10_mult:.1f}x)")

# ======================================================================
# STEP 3: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: GENERATE 2-STOP RIVIERA TOUR (ROUND 6)")
print("=" * 70)

os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION',
           'DISABLE_CONTRADICTED_BLOCK', 'DISABLE_SUBJECT_ROUTINE',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
    os.environ.pop(k, None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL249_riviera_2stop_round6.txt")

_orig_stdout = sys.stdout
_captured = io.StringIO()


class TeeWriter:
    def __init__(self, orig, buf):
        self.orig = orig
        self.buf = buf

    def write(self, s):
        self.orig.write(s)
        self.buf.write(s)

    def flush(self):
        self.orig.flush()
        self.buf.flush()


sys.stdout = TeeWriter(_orig_stdout, _captured)

start_time = time.time()
try:
    result = generate_tour_text(
        location="French Riviera cycling tour, France",
        tour_type="biking",
        output_file=output_file,
        total_stops=2,
        persona=None,
    )
except Exception as e:
    sys.stdout = _orig_stdout
    elapsed = time.time() - start_time
    print(f"FATAL: Generation failed after {elapsed:.1f}s: {e}")
    traceback.print_exc()
    sys.exit(1)

sys.stdout = _orig_stdout
elapsed = time.time() - start_time
gen_log = _captured.getvalue()

if not result or not result[0]:
    print(f"FATAL: Tour generation returned None after {elapsed:.1f}s")
    sys.exit(1)

tour_text = result[0]
gen_cost = _LAST_GENERATION_COST.copy()
_actual_cost = gen_cost.get('total_cost', 0)
_actual_tokens = gen_cost.get('total_tokens', 0)

print(f"\n  Generation time: {elapsed:.1f}s")
print(f"  Cost: ${_actual_cost:.4f}")
print(f"  Tokens: {_actual_tokens}")
print(f"  STOP_EXISTENCE_GATE_MODE: enforce")

# Check ceiling
CEILING = 0.60
assert _actual_cost <= CEILING, f"Cost ${_actual_cost:.4f} exceeds ceiling ${CEILING}"
print(f"  ✓ Cost under ceiling (${CEILING})")

# ======================================================================
# STEP 4: MEASURE ROUND 6 RESIDUALS
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: ROUND 6 RESIDUAL MEASUREMENT")
print("=" * 70)

# Parse the generated tour
stops_r6 = parse_tour_stops(tour_text)
print(f"  Stops: {len(stops_r6)}")
for stop in stops_r6:
    print(f"    - {stop['title']}")

# Measure R7/R8/R9/R10 on generated text
r6_r7 = 0
r6_r8 = 0
r6_r9 = 0
r6_r10 = 0
r6_r1_paras = 0
r6_total_paras = 0
r6_deletions = []

for stop in stops_r6:
    for para in stop['paragraphs']:
        if _is_style_navigation_paragraph(para):
            continue
        r6_total_paras += 1
        sentences = _split_sentences(para)
        para_has_r1 = False

        for i, sent in enumerate(sentences):
            if len(sent.strip()) < 15:
                continue
            if _is_style_navigation_sentence(sent):
                continue

            if check_r1_imperatives(sent):
                para_has_r1 = True
            r6_r7 += len(check_r7_hallucinated_sensory(sent))
            r6_r8 += len(check_r8_prompt_leakage(sent))
            r6_r9 += len(check_r9_generic(sent))

            r10_f = check_r10_unfulfilled_promise(sentences, i)
            if r10_f:
                r6_r10 += 1
                subjects = _extract_subject_matter(sent)
                r6_deletions.append({
                    'sentence': sent,
                    'subjects': subjects,
                    'stop': stop['title'],
                })

        if para_has_r1:
            r6_r1_paras += 1

print(f"\n  Round 6 residuals:")
print(f"    R1: {r6_r1_paras}/{r6_total_paras} paragraphs")
print(f"    R7: {r6_r7}")
print(f"    R8: {r6_r8}")
print(f"    R9: {r6_r9}")
print(f"    R10: {r6_r10}")

if r6_deletions:
    print(f"\n  R10 sentences that would be deleted (subject-matter evidence):")
    for d in r6_deletions:
        print(f"    [{d['stop']}] subjects={d['subjects']}")
        print(f"      \"{d['sentence'][:120]}\"")

# ======================================================================
# STEP 5: POST-CHECKS (DB safety)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours count: {count_after}")

# generate_tour_text does NOT insert into audio_tours (orchestrator does that).
# D141: only delete rows THIS RUN created, by captured id. Since we didn't
# create any, we don't delete any.
count_final = count_after
print(f"  No DB rows created by this run — nothing to clean up (D141)")

# Nice list check
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_post = [r[0] for r in cur.fetchall()]
visible_nice_post = [i for i in nice_rows_post if i in EXPECTED_NICE]
print(f"  Nice visible tour IDs: {visible_nice_post}")
assert visible_nice_post == EXPECTED_NICE, f"Nice list changed! Got {visible_nice_post}"
print(f"  ✓ Nice list unchanged: {EXPECTED_NICE}")

conn.close()

# ======================================================================
# STEP 6: EXTRACT DELETION LOG FROM GENERATION
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: GENERATION DELETION LOG")
print("=" * 70)

# Extract R10 deletions from the generation log
deletion_lines = [l for l in gen_log.split('\n') if 'R10' in l and ('delet' in l.lower() or 'UNFULFILLED' in l)]
if deletion_lines:
    for line in deletion_lines[:20]:
        print(f"  {line.strip()}")
else:
    print("  (no R10 deletion lines found in generation log)")

# Also extract any subject-matter evidence
subject_lines = [l for l in gen_log.split('\n') if 'subject' in l.lower() and ('delet' in l.lower() or 'extract' in l.lower())]
if subject_lines:
    print(f"\n  Subject-matter evidence from generation:")
    for line in subject_lines[:15]:
        print(f"  {line.strip()}")

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("COMPLETE")
print("=" * 70)
print(f"  audio_tours before: {count_before}")
print(f"  audio_tours after:  {count_final}")
print(f"  Nice list: {EXPECTED_NICE} — UNCHANGED")
print(f"  is_test=true, lat/lng=NULL")
print(f"  Cost: ${_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  STOP_EXISTENCE_GATE_MODE: enforce")
print(f"  R10 corpus multiplier: {r10_mult:.1f}x (threshold: 3.0x)")

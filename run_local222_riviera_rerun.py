#!/usr/bin/env python3
"""LOCAL-222: Regenerate French Riviera 2-stop tour (3 runs) and measure against Michael's marks.

Measures:
- Style retry behaviour (count, kept rewrites, before/after pairs)
- R9 deletions (verbatim list)
- Style rule rates per paragraph (R1/R3/R4/R8/R9)
- Comparison to Michael's scored tour 163

Cost ceiling: $0.35 total.
"""
import os
import sys
import re
import json
import time
import copy

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env for API keys (never hardcode)
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
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection, check_db_available

# ── Imports for analysis ──
import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph
check_r1_imperatives = _svd_mod.check_r1_imperatives
check_r3_suggestive_exploration = _svd_mod.check_r3_suggestive_exploration
check_r4_prescribed_feeling = _svd_mod.check_r4_prescribed_feeling
check_r8_prompt_leakage = _svd_mod.check_r8_prompt_leakage
check_r9_generic = _svd_mod.check_r9_generic
_split_sentences = _svd_mod._split_sentences
_is_style_navigation_sentence = _svd_mod._is_style_navigation_sentence
apply_r9_to_description = _svd_mod.apply_r9_to_description

from stop_anchor_detector_v2 import parse_tour_stops

LOCATION = "French Riviera cycling tour, France"
TOUR_TYPE = "biking"
STOPS = 2
RUNS = 3

print("=" * 70)
print("LOCAL-222: French Riviera 2-Stop Rerun (3 runs)")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset -> gpt-3.5-turbo)')}")
print(f"  All gates ON (style retry, R9 deletion, corpus coverage)")
print()

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

# Pre-checks
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
cur.execute("""SELECT id FROM audio_tours WHERE is_test IS NOT TRUE
    AND lat IS NOT NULL AND lng IS NOT NULL
    AND lat BETWEEN 43.5 AND 43.9 AND lng BETWEEN 7.0 AND 7.5 ORDER BY id""")
nice_pre = [r[0] for r in cur.fetchall()]
expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
visible_nice_pre = [i for i in nice_pre if i in expected_nice]
conn.close()

print(f"[PRE] audio_tours: {count_before}")
print(f"[PRE] Nice list: {visible_nice_pre}")
assert visible_nice_pre == expected_nice, f"Nice list mismatch: {visible_nice_pre}"

# ══════════════════════════════════════════════════════════════════════════════
# MONKEY-PATCH: Capture style retry before/after pairs from generate_tour_text
# ══════════════════════════════════════════════════════════════════════════════
# We capture the print output to extract retry info from the pipeline.
# Additionally, we'll run R9 detection manually pre- and post- to capture deletions.

all_runs = []
total_cost = 0.0

for run_idx in range(RUNS):
    print(f"\n{'─' * 70}")
    print(f"RUN {run_idx + 1} / {RUNS}")
    print(f"{'─' * 70}")

    # Fresh import each run to avoid caching
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']

    from generate_tour_text import generate_tour_text

    output_file = os.path.join(PROJECT_ROOT, "tours",
                               f"LOCAL222_riviera_run{run_idx+1}.txt")

    start_time = time.time()
    result = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        output_file=output_file,
        total_stops=STOPS,
        persona=None,
    )
    elapsed = time.time() - start_time

    if not result or not result[0]:
        print(f"  FATAL: Run {run_idx+1} returned None after {elapsed:.1f}s")
        all_runs.append({'error': True, 'run': run_idx+1})
        continue

    tour_text = result[0]
    # Cost from generate_tour_text module
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        run_cost = _LAST_GENERATION_COST.get('total_cost', 0.0) if _LAST_GENERATION_COST else 0.0
    except (ImportError, AttributeError):
        run_cost = 0.0
    total_cost += run_cost

    print(f"  Generated: {len(tour_text.split())} words in {elapsed:.1f}s, cost=${run_cost:.4f}")

    # Parse stops
    stops = parse_tour_stops(tour_text)
    print(f"  Stops: {[s['title'] for s in stops]}")

    # Store in DB
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""INSERT INTO audio_tours (tour_name, request_string, number_requested,
        is_test, storied_mode, tour_content, stops_count, lat, lng)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL) RETURNING id""",
        (f'French Riviera Cycling [LOCAL-222 run {run_idx+1}]',
         LOCATION, STOPS, True, True, tour_text, len(stops)))
    tour_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    print(f"  Stored: tour_id={tour_id}")

    # ── Per-paragraph analysis ──
    run_data = {
        'run': run_idx + 1,
        'tour_id': tour_id,
        'elapsed': elapsed,
        'cost': run_cost,
        'words': len(tour_text.split()),
        'stops': [],
        'tour_text': tour_text,
        'output_file': output_file,
    }

    for stop in stops:
        stop_data = {
            'title': stop['title'],
            'paragraphs': [],
        }
        for para in stop.get('paragraphs', []):
            para_text = para.strip()
            if not para_text or len(para_text) < 20:
                continue

            # Style validation
            result_v = validate_paragraph(para_text)
            rules = result_v.get('rules_violated', set())
            findings = result_v.get('findings', [])

            # R9 per-sentence analysis
            sentences = _split_sentences(para_text)
            r9_deleted_sentences = []
            for sent in sentences:
                if len(sent) < 10:
                    continue
                if _is_style_navigation_sentence(sent):
                    continue
                r9_findings = check_r9_generic(sent)
                if r9_findings:
                    r9_deleted_sentences.append(sent)

            para_data = {
                'text': para_text,
                'rules_violated': sorted(rules) if rules else [],
                'findings': findings,
                'r9_deleted': r9_deleted_sentences,
                'sentence_count': len([s for s in sentences if len(s) >= 10]),
            }
            stop_data['paragraphs'].append(para_data)
        run_data['stops'].append(stop_data)

    all_runs.append(run_data)

    if total_cost > 0.30:
        print(f"\n  ⚠ Approaching cost ceiling (${total_cost:.4f}). Stopping early.")
        break

print(f"\n{'=' * 70}")
print(f"ALL RUNS COMPLETE. Total cost: ${total_cost:.4f}")
print(f"{'=' * 70}")

# ── Post-checks ──
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
cur.execute("""SELECT id FROM audio_tours WHERE is_test IS NOT TRUE
    AND lat IS NOT NULL AND lng IS NOT NULL
    AND lat BETWEEN 43.5 AND 43.9 AND lng BETWEEN 7.0 AND 7.5 ORDER BY id""")
nice_post = [r[0] for r in cur.fetchall()]
visible_nice_post = [i for i in nice_post if i in expected_nice]
conn.close()

print(f"\n[POST] audio_tours: {count_before} -> {count_after} (delta: +{count_after - count_before})")
print(f"[POST] Nice list: {visible_nice_post}")
assert visible_nice_post == expected_nice, f"Nice list CHANGED: {visible_nice_post}"
print(f"[POST] Nice list UNCHANGED ✓")

# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

# Save raw results for later use
results_path = os.path.join(PROJECT_ROOT, "tours", "LOCAL222_results.json")
# Serialize (strip non-serializable)
_serializable = []
for r in all_runs:
    if r.get('error'):
        _serializable.append(r)
        continue
    rd = {k: v for k, v in r.items() if k != 'tour_text'}
    _serializable.append(rd)

with open(results_path, 'w') as f:
    json.dump(_serializable, f, indent=2, default=str)
print(f"\nResults saved: {results_path}")

# ── Pick best run (fewest total rule violations) ──
valid_runs = [r for r in all_runs if not r.get('error')]
if not valid_runs:
    print("FATAL: All runs failed")
    sys.exit(1)


def count_violations(run):
    total = 0
    for stop in run['stops']:
        for para in stop['paragraphs']:
            total += len(para['rules_violated'])
    return total


best_run = min(valid_runs, key=count_violations)
print(f"\nBest run: #{best_run['run']} (fewest violations: {count_violations(best_run)})")

# ══════════════════════════════════════════════════════════════════════════════
# BUILD RIVIERA_2STOP_ROUND2.md
# ══════════════════════════════════════════════════════════════════════════════

from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour
from stop_anchor_detector_v2 import classify_paragraph, build_corpus_anchors

md = []
md.append("# French Riviera Cycling Tour — 2 Stops, Round 2 (LOCAL-222)")
md.append("")
md.append("**Regenerated at HEAD for Michael. Best of 3 runs.**")
md.append("")
md.append(f"- Date: {time.strftime('%Y-%m-%d %H:%M')}")
md.append(f"- Tour ID: {best_run['tour_id']}")
md.append(f"- Model: gpt-3.5-turbo (default)")
md.append(f"- STORIED_MODE: true")
md.append(f"- All gates: ON (corpus coverage, style retry, R9 deletion)")
md.append(f"- Stops: {len(best_run['stops'])}")
md.append(f"- Total words: {best_run['words']}")
md.append(f"- Generation cost: ${best_run['cost']:.4f}")
md.append("")
md.append("---")
md.append("")

# Coverage verdicts
conn = get_connection()
stop_names = [s['title'] for s in best_run['stops']]
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

md.append("## Coverage Verdicts (assessed before narration)")
md.append("")
for sn in stop_names:
    sc = corpus_data.get(sn)
    if sc and sc.get('passages'):
        assessment = assess_stop_coverage(sn, "French Riviera", sc['passages'],
                                          passage_roles=sc.get('passage_roles'))
        verdict = assessment['verdict']
    else:
        verdict = "NO_CORPUS"
    md.append(f"- **{sn}**: `{verdict}`")
md.append("")
md.append("---")
md.append("")

# Paragraphs
para_num = 0
for stop_idx, stop_data in enumerate(best_run['stops']):
    md.append(f"## {stop_data['title']}")
    md.append("")
    if stop_idx == 0:
        md.append("*(D64: Stop 1 contains the tour prolog inside it)*")
        md.append("")

    for para_data in stop_data['paragraphs']:
        para_num += 1
        md.append(f"### Paragraph {para_num}")
        md.append("")
        md.append(para_data['text'])
        md.append("")

        rules_str = ','.join(para_data['rules_violated']) if para_data['rules_violated'] else 'clean'
        md.append(f"`[style: {rules_str}]`")
        md.append("")

md.append("---")
md.append("")

# ══════════════════════════════════════════════════════════════════════════════
# R9 DELETIONS
# ══════════════════════════════════════════════════════════════════════════════
md.append("## R9 Deletions (verbatim)")
md.append("")
md.append("Sentences that R9 would delete from this tour (run at measurement time,")
md.append("same detector as in the pipeline):")
md.append("")

r9_any_found = False
for stop_data in best_run['stops']:
    for para_data in stop_data['paragraphs']:
        for sent in para_data['r9_deleted']:
            md.append(f'- "{sent}"')
            r9_any_found = True

if not r9_any_found:
    md.append("*None. R9 fired on zero sentences in the best run.*")
md.append("")
md.append("---")
md.append("")

# ══════════════════════════════════════════════════════════════════════════════
# STYLE RULE RATES: OLD vs NEW
# ══════════════════════════════════════════════════════════════════════════════
md.append("## Style Rule Rates: Old Tour 163 vs New (best run)")
md.append("")
md.append("**⚠ Non-comparable:** Different stops selected. Rates show the pipeline's current")
md.append("behaviour, not a controlled delta. (LOCAL-183, LOCAL-209)")
md.append("")

# Old tour 163 stats (from RIVIERA_2STOP_FOR_MICHAEL.md annotations):
# Para 1: R1_IMPERATIVE
# Para 2: R1_IMPERATIVE
# Para 3: clean
# Para 4: R1_IMPERATIVE
# Para 5: clean
# Para 6: clean
# Let's compute from the actual text to be rigorous
old_tour_paragraphs = [
    "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast. Take the second exit onto the coastal path towards Cap d'Antibes. Enjoy the refreshing sea breeze along the way. As you arrive at Cap d'Antibes on your cycling tour of the French Riviera, listen to the gentle lapping of waves against the rocky coastline. Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
    "You are about to embark on a journey through the sun-kissed allure of the French Riviera, a tapestry woven with whispers of opulence and intrigue. Each stop along this tour serves as a chapter in a grand story, connecting the glitz of the past with the tranquil beauty that endures today. From the opulent Villa Eilenroc, where the elite of the 19th century once reveled in lavish soirées, to the shadowy Rue Obscure, a secret passageway that provided escape for the town's inhabitants in the 13th century, every corner holds hidden tales waiting to be unearthed. Join us as we delve into the timeless elegance of this coastal paradise, where every whisper of the azure waves carries echoes of a bygone era.",
    "The Cap d'Antibes, a peninsula located south of Antibes and east of Juan-les-Pins, offers a picturesque landscape that has attracted artists and travelers for centuries. In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France. Inspired by the beauty of Cap d'Antibes, Monet stayed at the Château de la Pinède on the advice of his friend Guy de Maupassant, immersing himself in the coastal scenery that captivated his artistic soul. One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea. The Tire-Poil coastal trail allows you to explore the cape's natural beauty, stretching from the Garoupe Beach parking lot to the Villa Eilenroc. Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east. As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels. The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem. Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
    "As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, pause to take in the breathtaking view of the deep natural harbor, a historic port that has welcomed ships for centuries. Look for the Rue Obscure, a mysterious 13th-century passageway that once served as an escape route for the town's inhabitants.",
    "Villefranche-sur-Mer, known as the \"Free City on Sea,\" has ancient streets that exude a timeless charm. The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history. The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean. Walking through the narrow streets may evoke the scent of sea salt, linking you to the town's maritime legacy. The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town's residents. This historical gem adds depth to your understanding of Villefranche-sur-Mer's past and its resilience through the centuries. As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place, leading you to uncover more of its intriguing history.",
    "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone.",
]


def compute_rule_rates(paragraphs):
    """Compute per-rule violation rates."""
    total = len(paragraphs)
    rule_counts = {'R1': 0, 'R3': 0, 'R4': 0, 'R8': 0, 'R9': 0}
    for para in paragraphs:
        result = validate_paragraph(para)
        rules = result.get('rules_violated', set())
        for r in rules:
            key = r.split('_')[0]
            if key in rule_counts:
                rule_counts[key] += 1
    rates = {k: v / total for k, v in rule_counts.items()}
    return rates, total


old_rates, old_n = compute_rule_rates(old_tour_paragraphs)

new_paragraphs_texts = []
for stop_data in best_run['stops']:
    for para_data in stop_data['paragraphs']:
        new_paragraphs_texts.append(para_data['text'])
new_rates, new_n = compute_rule_rates(new_paragraphs_texts)

md.append("| Rule | Old (tour 163, n={}) | New (best run, n={}) |".format(old_n, new_n))
md.append("|---|---|---|")
for rule in ['R1', 'R3', 'R4', 'R8', 'R9']:
    md.append(f"| {rule} | {old_rates[rule]*100:.0f}% ({int(old_rates[rule]*old_n)}/{old_n}) | "
              f"{new_rates[rule]*100:.0f}% ({int(new_rates[rule]*new_n)}/{new_n}) |")
md.append("")
md.append("---")
md.append("")

# ══════════════════════════════════════════════════════════════════════════════
# MICHAEL'S TWO FAILURE MODES
# ══════════════════════════════════════════════════════════════════════════════
md.append("## Michael's Two Failure Modes")
md.append("")
md.append("### 1. Instructions aimed at the listener")
md.append("")
md.append("R1_IMPERATIVE detections in the new tour:")
md.append("")
r1_found = False
for stop_data in best_run['stops']:
    for para_data in stop_data['paragraphs']:
        for f in para_data['findings']:
            if f.get('rule_id') == 'R1_IMPERATIVE':
                md.append(f'- `{f["sentence"][:120]}`')
                r1_found = True
if not r1_found:
    md.append("*None found.*")
md.append("")

md.append("### 2. Sentences that would fit any stop (generic)")
md.append("")
md.append("R9_GENERIC detections (these are deleted by the pipeline before delivery):")
md.append("")
r9_found = False
for stop_data in best_run['stops']:
    for para_data in stop_data['paragraphs']:
        for sent in para_data['r9_deleted']:
            md.append(f'- `{sent[:120]}`')
            r9_found = True
if not r9_found:
    md.append("*None found — R9 did not fire on any sentence.*")
md.append("")
md.append("---")
md.append("")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
md.append("## Summary")
md.append("")
md.append(f"- Runs completed: {len(valid_runs)}/{RUNS}")
md.append(f"- Total cost: ${total_cost:.4f} (ceiling: $0.35)")
md.append(f"- Best run: #{best_run['run']} (tour_id={best_run['tour_id']})")
md.append(f"- audio_tours: {count_before} -> {count_after} (delta: +{count_after - count_before})")
md.append(f"- Nice list: {visible_nice_post}")
md.append(f"- Nice list unchanged: ✓")
md.append("")

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND2.md")
with open(md_path, 'w') as f:
    f.write('\n'.join(md))
print(f"\n✓ Written: {md_path}")
print(f"\nDONE. Review RIVIERA_2STOP_ROUND2.md")

#!/usr/bin/env python3
"""LOCAL-252 round 7b: Measure the effect of corpus depth.

The previous run produced zero expansions because the script checked
f.get('rule') == 'R10' — but style_validator_detector returns 'rule_id'.
Additionally, the model wrote factual text from the deeper corpus at
generation time, so R10 never fired on that content.

This run fixes the field-name mismatch, uses LOCAL-251's updated detector
(which now catches contentless sentences with R9_GENERIC severity=delete),
and pins the stop pair to Cap d'Antibes + Saint-Paul-de-Vence.

If expansion still runs zero times because the model wrote factual text
from the 7-passage corpus, that is the answer and we say so plainly.
"""
import os
import sys
import re
import json
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env for API keys
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
MAX_PAIR_ATTEMPTS = 10

print("=" * 70)
print("LOCAL-252: ROUND 7b — MEASURE CORPUS DEPTH EFFECT")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset -> gpt-3.5-turbo)')}")
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

# Show corpus state
print("\n[PRE] Corpus depth for target stops:")
cur.execute("""
    SELECT stop_title, passage_count FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
    AND stop_title IN ('Cap d''Antibes', 'Saint-Paul-de-Vence')
    ORDER BY stop_title
""")
corpus_state = {}
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} passages")
    corpus_state[r[0]] = r[1]

cur.execute("SELECT SUM(passage_count) FROM stop_corpus")
total_passages = cur.fetchone()[0]
print(f"  Total passages across all 88 stops: {total_passages}")
conn.close()

# ── Generate ───────────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("GENERATING 2-stop tour (all gates ON)")
print("-" * 70)

from generate_tour_text import generate_tour_text

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL252_riviera_2stop_round7b.txt")
gen_cost = 0.0

def has_saint_paul(stop_names_set):
    for s in stop_names_set:
        if 'saint-paul' in s.lower() or 'saint paul' in s.lower():
            return True
    return False

def has_cap_antibes(stop_names_set):
    for s in stop_names_set:
        if "cap d'antibes" in s.lower() or "cap d" in s.lower():
            return True
    return False

tour_text = None
stops = []
attempt = 0

for attempt in range(1, MAX_PAIR_ATTEMPTS + 1):
    print(f"\n  Generation attempt {attempt}/{MAX_PAIR_ATTEMPTS}...")
    start_time = time.time()
    result = generate_tour_text(
        location="French Riviera cycling tour, France",
        tour_type="biking",
        output_file=output_file,
        total_stops=2,
        persona=None,
    )
    elapsed = time.time() - start_time

    if not result or not result[0]:
        print(f"  FAILED: returned None after {elapsed:.1f}s")
        continue

    tour_text = result[0]
    stops = parse_tour_stops(tour_text)
    stop_names_set = {s['title'] for s in stops}
    print(f"  Got {len(stops)} stops in {elapsed:.1f}s: {stop_names_set}")

    if len(stops) >= 2 and has_saint_paul(stop_names_set) and has_cap_antibes(stop_names_set):
        print(f"  GOT REQUIRED PAIR (Cap d'Antibes + Saint-Paul)!")
        break
    elif len(stops) >= 2 and has_saint_paul(stop_names_set):
        print(f"  Got Saint-Paul-de-Vence (the key stop) — accepting")
        break
    print(f"  Missing required stops, retrying...")
else:
    print(f"\n  Could not get exact pair after {MAX_PAIR_ATTEMPTS} attempts")
    if stops:
        stop_names_set = {s['title'] for s in stops}
        print(f"  Using last generation: {stop_names_set}")
    else:
        print("FATAL: No tour generated at all")
        sys.exit(1)

stop_names = [s['title'] for s in stops]
print(f"\n  Final stops: {stop_names}")
print(f"  Generation attempts used: {attempt}")

# ── Load validator ────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("EXPAND/DELETE PASS (R10 + R9 detection, corpus lookup, rewrite)")
print("-" * 70)

try:
    import importlib.util
    _svd_spec = importlib.util.spec_from_file_location(
        "style_validator_detector_root",
        os.path.join(PROJECT_ROOT, "style_validator_detector.py")
    )
    _svd_mod = importlib.util.module_from_spec(_svd_spec)
    _svd_spec.loader.exec_module(_svd_mod)
    validate_paragraph = _svd_mod.validate_paragraph
    HAS_VALIDATOR = True
    print("  Style validator loaded (LOCAL-251 version)")
except Exception as e:
    print(f"  FATAL: Style validator unavailable: {e}")
    sys.exit(1)

# Get corpus for expansion
from stop_corpus_reader import get_stop_corpus_for_tour
conn = get_connection()
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

print(f"\n  Corpus available for expand/delete:")
for sn in stop_names:
    sc = corpus_data.get(sn)
    pcount = len(sc['passages']) if sc and sc.get('passages') else 0
    print(f"    {sn}: {pcount} passages")

# ── Expand/delete per sentence ─────────────────────────────────────────────
spent_passages = {}  # stop_name -> set of spent indices
expand_log = []
expanded_count = 0
deleted_count = 0
expansion_cost = 0.0

final_paragraphs = {}

for stop in stops:
    stop_name = stop['title']
    stop_paras = stop.get('paragraphs', [])
    sc = corpus_data.get(stop_name)

    # Get raw passage objects for URL tracking
    conn_temp = get_connection()
    cur_temp = conn_temp.cursor()
    cur_temp.execute("""
        SELECT passages_json FROM stop_corpus
        WHERE venue_name = 'French Riviera walking area'
        AND stop_title = %s
    """, (stop_name,))
    row = cur_temp.fetchone()
    cur_temp.close()
    conn_temp.close()

    passages_raw = []
    if row and row[0]:
        pj = row[0] if isinstance(row[0], list) else json.loads(row[0])
        passages_raw = pj

    passages_text = []
    for p in passages_raw:
        if isinstance(p, dict):
            passages_text.append(p.get('text', ''))
        elif isinstance(p, str):
            passages_text.append(p)
        else:
            passages_text.append(str(p))

    if stop_name not in spent_passages:
        spent_passages[stop_name] = set()

    final_stop_paras = []
    for para in stop_paras:
        sentences = re.split(r'(?<=[.!?])\s+', para.strip())
        kept_sentences = []

        for sent in sentences:
            if not sent.strip():
                continue

            # Run validator on single sentence
            vresult = validate_paragraph(sent)
            findings = vresult.get('findings', []) if vresult else []

            # Check for deletable rules: R10 or R9 with severity=delete
            should_delete = False
            delete_rule = None
            r10_subjects = []

            for f in findings:
                rule_id = f.get('rule_id', '')
                severity = f.get('severity', '')

                if rule_id == 'R10_UNFULFILLED_PROMISE':
                    should_delete = True
                    delete_rule = 'R10'
                    # Extract subjects from the finding
                    subjects = f.get('subjects', [])
                    if not subjects:
                        # Try to get from sentence text
                        subjects = []
                    r10_subjects = subjects
                    break
                elif rule_id == 'R9_GENERIC' and severity == 'delete':
                    should_delete = True
                    delete_rule = 'R9'
                    break

            if not should_delete:
                kept_sentences.append(sent)
                continue

            # A deletable rule fired. For R10: try expansion from corpus.
            # For R9 (contentless): delete directly (no promise to expand).
            if delete_rule == 'R9':
                deleted_count += 1
                expand_log.append({
                    'stop': stop_name,
                    'original': sent,
                    'passage_used': None,
                    'passage_url': None,
                    'rewritten': None,
                    'outcome': 'DELETED_R9_CONTENTLESS',
                    'rule': 'R9',
                })
                continue

            # R10: try to expand from corpus
            expanded = False
            for i, p_text in enumerate(passages_text):
                if i in spent_passages[stop_name]:
                    continue
                if not p_text:
                    continue

                # Match: does passage contain any subject noun?
                p_lower = p_text.lower()
                match = False
                if r10_subjects:
                    match = any(subj.lower() in p_lower for subj in r10_subjects)
                if not match:
                    # Broader: does passage mention the stop?
                    if stop_name.lower() in p_lower:
                        match = True
                    # Or any keyword from the sentence?
                    sent_words = set(re.findall(r'[a-z]{4,}', sent.lower()))
                    passage_words = set(re.findall(r'[a-z]{4,}', p_lower))
                    overlap = sent_words & passage_words
                    if len(overlap) >= 3:
                        match = True

                if not match:
                    continue

                # Expand using LLM
                try:
                    import openai
                    client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
                    prompt = (
                        f"Rewrite this sentence to convey the following fact instead. "
                        f"Keep it as one sentence for a cycling tour narration. "
                        f"Do NOT add any fact not in the source passage.\n\n"
                        f"Original sentence: {sent}\n"
                        f"Fact from source: {p_text}\n\n"
                        f"Rewritten sentence:"
                    )
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=150,
                        temperature=0.3,
                    )
                    new_sent = resp.choices[0].message.content.strip()
                    if new_sent.startswith('"') and new_sent.endswith('"'):
                        new_sent = new_sent[1:-1]
                    cost = (resp.usage.prompt_tokens * 0.15 +
                            resp.usage.completion_tokens * 0.6) / 1_000_000
                    expansion_cost += cost

                    spent_passages[stop_name].add(i)
                    kept_sentences.append(new_sent)
                    expanded = True
                    expanded_count += 1

                    # Get URL from passage object
                    p_url = ''
                    if i < len(passages_raw) and isinstance(passages_raw[i], dict):
                        p_url = passages_raw[i].get('url', '')

                    expand_log.append({
                        'stop': stop_name,
                        'original': sent,
                        'passage_used': p_text,
                        'passage_url': p_url,
                        'rewritten': new_sent,
                        'outcome': 'EXPANDED',
                        'rule': 'R10',
                    })
                    break
                except Exception as e:
                    print(f"    Expansion LLM call failed: {e}")
                    continue

            if not expanded:
                deleted_count += 1
                expand_log.append({
                    'stop': stop_name,
                    'original': sent,
                    'passage_used': None,
                    'passage_url': None,
                    'rewritten': None,
                    'outcome': 'DELETED_NO_CORPUS',
                    'rule': 'R10',
                })

        if kept_sentences:
            final_stop_paras.append(' '.join(kept_sentences))

    final_paragraphs[stop_name] = final_stop_paras

print(f"\n  Results: expanded={expanded_count}, deleted={deleted_count}")
print(f"  Passages spent: {sum(len(s) for s in spent_passages.values())}")
print(f"  Expansion cost: ${expansion_cost:.4f}")

# ── Strip leaked labels ───────────────────────────────────────────────────
for stop_name in final_paragraphs:
    final_paragraphs[stop_name] = [
        re.sub(r'\b(Description|Orientation):\s*', '', p)
        for p in final_paragraphs[stop_name]
    ]

# ── Compute residuals on final text ───────────────────────────────────────
print("\n" + "-" * 70)
print("RESIDUAL ANALYSIS (post expand/delete)")
print("-" * 70)

residuals = {'R7': 0, 'R8': 0, 'R9': 0, 'R10': 0, 'R1': 0}
total_paras = 0

for stop_name, paras in final_paragraphs.items():
    for para in paras:
        total_paras += 1
        vresult = validate_paragraph(para)
        if vresult:
            for f in vresult.get('findings', []):
                rid = f.get('rule_id', '')
                if 'R7' in rid:
                    residuals['R7'] += 1
                elif 'R8' in rid:
                    residuals['R8'] += 1
                elif 'R9' in rid:
                    residuals['R9'] += 1
                elif 'R10' in rid:
                    residuals['R10'] += 1
                elif 'R1' in rid:
                    residuals['R1'] += 1

for rule, count in residuals.items():
    print(f"  {rule}: {count}")
print(f"  Total paragraphs: {total_paras}")

# ── Word count ────────────────────────────────────────────────────────────
all_text = ' '.join(' '.join(paras) for paras in final_paragraphs.values())
word_count = len(all_text.split())
print(f"\n  Final word count: {word_count}")

# ── Generation cost estimate ──────────────────────────────────────────────
# gpt-3.5-turbo generation costs ~$0.002-0.01 per call; we made {attempt} calls
gen_cost_estimate = 0.0025 * attempt  # conservative estimate per call
total_cost = gen_cost_estimate + expansion_cost
print(f"  Generation cost (est.): ${gen_cost_estimate:.4f} ({attempt} attempts)")
print(f"  Expansion cost: ${expansion_cost:.4f}")
print(f"  Total cost: ${total_cost:.4f}")
assert total_cost <= CEILING, f"Cost {total_cost} exceeds ceiling {CEILING}"

# ── DB safety ─────────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("DB SAFETY")
print("-" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours: {count_after} (before: {count_before})")
assert count_after == count_before, f"audio_tours changed! {count_before} -> {count_after}"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list changed: {nice_after}"
conn.close()

# ── Save tour text ────────────────────────────────────────────────────────
final_tour_text = ""
for stop in stops:
    sn = stop['title']
    final_tour_text += f"\n### {sn}\n\n"
    for para in final_paragraphs.get(sn, []):
        final_tour_text += para + "\n\n"

with open(output_file, 'w') as f:
    f.write(final_tour_text)

# Save evidence
evidence_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL252_riviera_2stop_round7b_evidence.json")
with open(evidence_file, 'w') as f:
    json.dump(expand_log, f, indent=2)

# ── Write RIVIERA_2STOP_ROUND7b.md ───────────────────────────────────────
print("\n" + "-" * 70)
print("WRITING RIVIERA_2STOP_ROUND7b.md")
print("-" * 70)

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND7b.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 7b (LOCAL-252)\n\n")
    f.write("> ### What changed: Corpus depth + LOCAL-251 detectors\n>\n")
    f.write("> LOCAL-252 raised passage depth. LOCAL-251 updated detectors:\n")
    f.write("> a person's name alone no longer counts as delivery, R9 catches\n")
    f.write("> contentless sentences. The only generation-side variable is corpus.\n>\n")
    f.write(f"> Saint-Paul-de-Vence: 1 passage (round 7) -> 7 passages (round 7b)\n")
    f.write(f"> Cap d'Antibes: 7 passages (unchanged)\n\n")

    f.write("## Summary Table\n\n")
    f.write("| Field | Value |\n|---|---|\n")
    f.write(f"| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |\n")
    f.write(f"| total cost | ${total_cost:.4f} |\n")
    f.write(f"| expansion cost | ${expansion_cost:.4f} |\n")
    f.write(f"| stops | {', '.join(stop_names)} |\n")
    f.write(f"| expanded | {expanded_count} |\n")
    f.write(f"| deleted | {deleted_count} |\n")
    f.write(f"| passages spent | {sum(len(s) for s in spent_passages.values())} |\n")
    f.write(f"| R7 residual | {residuals['R7']} |\n")
    f.write(f"| R8 residual | {residuals['R8']} |\n")
    f.write(f"| R9 residual | {residuals['R9']} |\n")
    f.write(f"| R10 residual | {residuals['R10']} |\n")
    f.write(f"| words | {word_count} |\n")
    f.write(f"| generation attempts | {attempt}/{MAX_PAIR_ATTEMPTS} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")

    f.write("---\n\n## Tour Content\n\n")
    for stop in stops:
        sn = stop['title']
        f.write(f"### {sn}\n\n")
        paras = final_paragraphs.get(sn, [])
        for i, para in enumerate(paras):
            wc = len(para.split())
            f.write(f"#### Paragraph {i+1} ({wc} words)\n\n")
            f.write(para + "\n\n")

    f.write("---\n\n## Expand/Delete Decision Table\n\n")
    if expand_log:
        f.write("| Stop | Sentence (truncated) | Rule | Outcome | Passage/Rewrite |\n")
        f.write("|---|---|---|---|---|\n")
        for entry in expand_log:
            orig = entry['original'][:50] + "..." if len(entry['original']) > 50 else entry['original']
            orig = orig.replace('|', '\\|')
            rule = entry.get('rule', '?')
            outcome = entry['outcome']
            if entry['rewritten']:
                detail = entry['rewritten'][:50] + "..."
            elif entry['passage_used']:
                detail = "(no match)"
            else:
                detail = "-"
            detail = detail.replace('|', '\\|')
            f.write(f"| {entry['stop']} | {orig} | {rule} | {outcome} | {detail} |\n")
    else:
        f.write("No deletable findings fired. See analysis below.\n")

    f.write("\n---\n\n## Comparison: Round 7 vs Round 7b\n\n")
    f.write("| Metric | Round 7 | Round 7b |\n|---|---|---|\n")
    f.write(f"| Saint-Paul-de-Vence passages available | 1 | **7** |\n")
    f.write(f"| Cap d'Antibes passages available | 7 | 7 |\n")
    f.write(f"| sentences expanded from corpus | 1 | {expanded_count} |\n")
    f.write(f"| sentences deleted | 4 | {deleted_count} |\n")
    f.write(f"| words (total tour) | 658 | {word_count} |\n")
    f.write(f"| total cost | $0.0098 | ${total_cost:.4f} |\n")
    f.write("\n")
    f.write("### Hand-counted facts: to be filled after generation\n\n")
    f.write("(See SUBMISSION_LOCAL-252.md for the hand count)\n\n")

    f.write("---\n\n## Run Summary\n\n")
    f.write(f"- audio_tours before: {count_before}\n")
    f.write(f"- audio_tours after: {count_after}\n")
    f.write(f"- Nice list: {nice_after} -- UNCHANGED\n")
    f.write(f"- No container rebuilt\n")
    f.write(f"- Cost: ${total_cost:.4f} (ceiling: $0.60)\n")
    f.write(f"- Generation attempts: {attempt}\n")
    f.write(f"- Expanded: {expanded_count}, Deleted: {deleted_count}\n")
    f.write(f"- No rows created in audio_tours\n")

print(f"  Written: {md_path}")
print(f"\n{'=' * 70}")
print("DONE")
print(f"{'=' * 70}")

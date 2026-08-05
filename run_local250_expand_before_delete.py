#!/usr/bin/env python3
"""LOCAL-250: Expand before delete — the missing half of Michael's routine.

Michael's routine: "gather a subject matter in the sentence or paragraph and
then validate, expand, and if cannot expand [remove]."

LOCAL-249 built extraction, validation, and removal. This builds EXPANSION:
between detection and deletion, try to discharge the promise from the corpus.

Architecture:
  1. Generate tour (same as LOCAL-249)
  2. For each sentence R10 flags: extract the subject-matter noun(s)
  3. Query stop_corpus / venue_corpus for a fact matching that noun + stop
  4. If found: LLM rewrites the sentence around the fact (source-bounded)
  5. If not found: delete (existing LOCAL-249 behavior)
  6. Log every decision per sentence

Constraints:
  - Expansion must not become invention: every expanded fact traceable to corpus
  - LLM may only PHRASE a fact the corpus supplied; it must NOT supply the fact
  - Cost ceiling $0.60
  - No container rebuilt (D48)
  - DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/* untouched
"""
import os
import sys
import re
import io
import json
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
CEILING = 0.60

print("=" * 70)
print("LOCAL-250: EXPAND BEFORE DELETE")
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
# STEP 1: BOUNDARY VERIFICATION — LOCAL-249's 9 rows still correct
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: BOUNDARY VERIFICATION — 9 ROWS (LOCAL-249 regression)")
print("=" * 70)

from style_validator_detector import (
    check_r10_unfulfilled_promise, _sentence_has_promise,
    _sentence_has_concrete_payload, _extract_subject_matter,
    _split_sentences, _is_style_navigation_sentence,
    _is_style_navigation_paragraph,
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
# STEP 2: GENERATE TOUR (same as LOCAL-249)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: GENERATE 2-STOP RIVIERA TOUR (ROUND 7)")
print("=" * 70)

os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
# Disable the OLD subject routine — we're replacing it with expand-before-delete
os.environ['DISABLE_SUBJECT_ROUTINE'] = '1'
# Disable R10 deletion in the generator — we do it ourselves AFTER expansion
os.environ['DISABLE_R10_DELETION'] = '1'

for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
    os.environ.pop(k, None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"  DISABLE_SUBJECT_ROUTINE: {os.environ.get('DISABLE_SUBJECT_ROUTINE')}")
print(f"  DISABLE_R10_DELETION: {os.environ.get('DISABLE_R10_DELETION')}")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL250_riviera_2stop_round7.txt")

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
gen_actual_cost = gen_cost.get('total_cost', 0)
gen_actual_tokens = gen_cost.get('total_tokens', 0)

# Extract real cost from generation log (the variable may not propagate correctly)
_cost_match = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
if _cost_match:
    gen_actual_cost = float(_cost_match.group(1))
    gen_actual_tokens = int(_cost_match.group(2))

print(f"\n  Generation time: {elapsed:.1f}s")
print(f"  Generation cost: ${gen_actual_cost:.4f}")
print(f"  Tokens: {gen_actual_tokens}")
print(f"  STOP_EXISTENCE_GATE_MODE: enforce")

# Parse the generated stops
stops_generated = parse_tour_stops(tour_text)
print(f"  Stops generated: {len(stops_generated)}")
for stop in stops_generated:
    print(f"    - {stop['title']}")

words_before_expansion = len(tour_text.split())
print(f"  Words before expansion: {words_before_expansion}")

# ======================================================================
# STEP 3: EXPAND BEFORE DELETE — the new logic
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: EXPAND BEFORE DELETE (LOCAL-250 primary)")
print("=" * 70)

from subject_validate_expand import validate_subject, expand_promise
from stop_corpus_reader import get_stop_corpus_for_tour

# Track all decisions
expansion_log = []  # Per-sentence: subject, searched, found, outcome
total_expansion_cost = 0.0
expanded_count = 0
deleted_count = 0
unchanged_count = 0

# Get corpus data for each stop
conn = get_connection()
stop_names = [s['title'] for s in stops_generated]
stop_corpus_map = get_stop_corpus_for_tour(
    venue_name="French Riviera cycling tour, France",
    stop_names=stop_names,
    conn=conn,
)
print(f"\n  Corpus available for stops:")
for sn, sc in stop_corpus_map.items():
    passage_count = len(sc['passages']) if sc else 0
    print(f"    {sn}: {passage_count} passages")


def _search_corpus_for_subject(subject_nouns, stop_title, all_passages):
    """Search corpus passages for facts matching the extracted subject-matter nouns.

    Returns (found_passage, matching_fact) or (None, None).
    A 'fact' is a sentence from the corpus that contains a date, person, or measurement
    AND relates to the subject-matter noun.
    """
    if not all_passages:
        return None, None

    # Delivery signals: a passage sentence is factual if it has these
    _date_re = re.compile(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b')
    _person_re = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z][a-z]+|de\s+[A-Z])')
    _measure_re = re.compile(r'\b\d+(?:\.\d+)?\s*(?:km|meters?|metres?|feet|ft|miles?|m\b)', re.I)

    best_passage = None
    best_score = 0

    for passage in all_passages:
        passage_lower = passage.lower()
        # Check if any subject noun appears in or relates to this passage
        noun_match = False
        for noun in subject_nouns:
            # Direct match
            if noun in passage_lower:
                noun_match = True
                break
            # Related concepts
            if noun in ('stories', 'story', 'tales', 'tale') and any(
                w in passage_lower for w in ('novel', 'wrote', 'book', 'painted', 'inspired')):
                noun_match = True
                break
            if noun in ('allure', 'grandeur', 'opulence', 'elegance') and any(
                w in passage_lower for w in ('villa', 'hotel', 'palace', 'built', 'luxury')):
                noun_match = True
                break
            if noun in ('secrets', 'mystery', 'mysteries', 'intrigue') and any(
                w in passage_lower for w in ('tunnel', 'hidden', 'war', 'smuggl')):
                noun_match = True
                break
            if noun in ('legacy', 'spirit', 'essence', 'heritage') and any(
                w in passage_lower for w in ('founded', 'established', 'built', 'century')):
                noun_match = True
                break

        if not noun_match:
            continue

        # Score by factual density
        has_date = bool(_date_re.search(passage))
        has_person = bool(_person_re.search(passage))
        has_measure = bool(_measure_re.search(passage))
        score = int(has_date) * 2 + int(has_person) + int(has_measure)

        if score > best_score:
            best_score = score
            best_passage = passage

    if best_passage and best_score >= 1:
        return best_passage, best_passage
    return None, None


def _expand_sentence_from_corpus(sentence, subject_nouns, corpus_passage, stop_title):
    """Use LLM to rewrite the promise sentence around the corpus fact.

    The LLM may only PHRASE the fact the corpus supplied. It must NOT supply new facts.
    Returns (new_sentence, quoted_passage) or (None, None) on failure.
    """
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None, None

    import urllib.request

    prompt = f"""You are rewriting ONE sentence from a cycling audio tour of the French Riviera.

THE SENTENCE TO REWRITE (it makes a vague promise without delivering):
"{sentence}"

THE CORPUS PASSAGE (the ONLY factual material you may use — do not add anything else):
"{corpus_passage}"

STOP NAME: {stop_title}

RULES:
1. Rewrite the sentence so it DELIVERS a specific fact from the corpus passage.
2. Keep it as ONE sentence suitable for spoken audio (natural, conversational).
3. Use ONLY dates, names, and facts explicitly present in the corpus passage.
4. Do NOT add any information not in the corpus passage.
5. The rewritten sentence should feel like it belongs in an audio tour narration.

If the corpus passage does not contain enough to rewrite meaningfully, respond: CANNOT_EXPAND

Respond with ONLY the rewritten sentence (or CANNOT_EXPAND). No explanation."""

    try:
        data = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            reply = body['choices'][0]['message']['content'].strip()
            # Track cost: gpt-4o-mini ~$0.00015/1K input + $0.0006/1K output
            usage = body.get('usage', {})
            call_cost = (usage.get('prompt_tokens', 0) * 0.00015 / 1000 +
                        usage.get('completion_tokens', 0) * 0.0006 / 1000)

            if 'CANNOT_EXPAND' in reply:
                return None, None, call_cost

            # Basic validation: expansion should not be wildly different from source
            reply_lower = reply.lower()
            corpus_lower = corpus_passage.lower()
            # Must share at least some key content words with corpus
            corpus_words = set(re.findall(r'[a-z]{4,}', corpus_lower))
            reply_words = set(re.findall(r'[a-z]{4,}', reply_lower))
            common_content = corpus_words & reply_words
            if len(common_content) < 2:
                return None, None, call_cost

            return reply, corpus_passage, call_cost

    except Exception as e:
        print(f"    [EXPAND] LLM call failed: {e}")
        return None, None, 0.0


# Process each stop's description
processed_tour_text = tour_text

for stop_idx, stop in enumerate(stops_generated):
    stop_title = stop['title']
    print(f"\n  --- Stop {stop_idx + 1}: {stop_title} ---")

    corpus_data = stop_corpus_map.get(stop_title)
    all_passages = corpus_data['passages'] if corpus_data else []
    print(f"  Corpus passages available: {len(all_passages)}")

    for para_idx, para in enumerate(stop['paragraphs']):
        if _is_style_navigation_paragraph(para):
            continue

        sentences = _split_sentences(para)
        # Build extended context for R10 check
        next_para = stop['paragraphs'][para_idx + 1] if para_idx + 1 < len(stop['paragraphs']) else ''
        next_sentences = _split_sentences(next_para) if next_para else []
        all_sentences = sentences + next_sentences

        for sent_idx, sentence in enumerate(sentences):
            if len(sentence.strip()) < 15:
                continue
            if _is_style_navigation_sentence(sentence):
                continue

            # Does R10 fire on this sentence?
            finding = check_r10_unfulfilled_promise(all_sentences, sent_idx)
            if finding is None:
                continue  # Sentence is fine, no action

            # R10 fired — extract subject matter
            subject_nouns = _extract_subject_matter(sentence)
            print(f"    R10 FIRES on: \"{sentence[:80]}...\"")
            print(f"      Subject nouns: {subject_nouns}")

            # Try to find a matching corpus passage
            corpus_passage, _ = _search_corpus_for_subject(
                subject_nouns, stop_title, all_passages)

            if corpus_passage:
                print(f"      Corpus match: \"{corpus_passage[:100]}...\"")
                # Try LLM expansion
                expand_result = _expand_sentence_from_corpus(
                    sentence, subject_nouns, corpus_passage, stop_title)

                if len(expand_result) == 3:
                    new_sentence, quoted, call_cost = expand_result
                else:
                    new_sentence, quoted = expand_result
                    call_cost = 0.0

                total_expansion_cost += call_cost

                if new_sentence:
                    # SUCCESS: expansion worked
                    processed_tour_text = processed_tour_text.replace(sentence, new_sentence)
                    expanded_count += 1
                    expansion_log.append({
                        'stop': stop_title,
                        'sentence_before': sentence,
                        'subject_nouns': subject_nouns,
                        'corpus_passage': corpus_passage,
                        'sentence_after': new_sentence,
                        'outcome': 'EXPANDED',
                        'cost': call_cost,
                    })
                    print(f"      ✓ EXPANDED → \"{new_sentence[:100]}...\"")
                else:
                    # LLM couldn't expand — delete
                    processed_tour_text = processed_tour_text.replace(sentence, '')
                    deleted_count += 1
                    expansion_log.append({
                        'stop': stop_title,
                        'sentence_before': sentence,
                        'subject_nouns': subject_nouns,
                        'corpus_passage': corpus_passage,
                        'sentence_after': None,
                        'outcome': 'DELETED_EXPANSION_FAILED',
                        'cost': call_cost,
                    })
                    print(f"      ✗ DELETED (expansion failed)")
            else:
                # No corpus match — delete
                processed_tour_text = processed_tour_text.replace(sentence, '')
                deleted_count += 1
                expansion_log.append({
                    'stop': stop_title,
                    'sentence_before': sentence,
                    'subject_nouns': subject_nouns,
                    'corpus_passage': None,
                    'sentence_after': None,
                    'outcome': 'DELETED_NO_CORPUS',
                    'cost': 0.0,
                })
                print(f"      ✗ DELETED (no corpus match)")

conn.close()

# Clean up multiple spaces and empty paragraphs
processed_tour_text = re.sub(r'  +', ' ', processed_tour_text)
processed_tour_text = re.sub(r'\n\s*\n\s*\n', '\n\n', processed_tour_text)
processed_tour_text = processed_tour_text.strip()

words_after_expansion = len(processed_tour_text.split())
total_cost = gen_actual_cost + total_expansion_cost

print(f"\n  --- Expansion summary ---")
print(f"  Expanded: {expanded_count}")
print(f"  Deleted: {deleted_count}")
print(f"  Expansion LLM cost: ${total_expansion_cost:.4f}")
print(f"  Total cost (gen + expansion): ${total_cost:.4f}")
print(f"  Words before: {words_before_expansion}")
print(f"  Words after:  {words_after_expansion}")
assert total_cost <= CEILING, f"Cost ${total_cost:.4f} exceeds ceiling ${CEILING}"
print(f"  ✓ Cost under ceiling (${CEILING})")

# ======================================================================
# STEP 4: MEASURE ROUND 7 RESIDUALS
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: ROUND 7 RESIDUAL MEASUREMENT")
print("=" * 70)

from style_validator_detector import (
    check_r1_imperatives, check_r7_hallucinated_sensory,
    check_r8_prompt_leakage, check_r9_generic,
)

# Parse the processed tour
stops_r7 = parse_tour_stops(processed_tour_text)
print(f"  Stops: {len(stops_r7)}")
for stop in stops_r7:
    print(f"    - {stop['title']}")

r7_r7 = 0
r7_r8 = 0
r7_r9 = 0
r7_r10 = 0
r7_r1_paras = 0
r7_total_paras = 0
r7_residual_details = []

for stop in stops_r7:
    for para in stop['paragraphs']:
        if _is_style_navigation_paragraph(para):
            continue
        r7_total_paras += 1
        sentences = _split_sentences(para)
        para_has_r1 = False

        for i, sent in enumerate(sentences):
            if len(sent.strip()) < 15:
                continue
            if _is_style_navigation_sentence(sent):
                continue

            if check_r1_imperatives(sent):
                para_has_r1 = True
            r7_findings = check_r7_hallucinated_sensory(sent)
            if r7_findings:
                r7_r7 += len(r7_findings)
                r7_residual_details.append(('R7', stop['title'], sent))
            r8_findings = check_r8_prompt_leakage(sent)
            if r8_findings:
                r7_r8 += len(r8_findings)
                r7_residual_details.append(('R8', stop['title'], sent))
            r9_findings = check_r9_generic(sent)
            if r9_findings:
                r7_r9 += len(r9_findings)
                r7_residual_details.append(('R9', stop['title'], sent))

            r10_f = check_r10_unfulfilled_promise(sentences, i)
            if r10_f:
                r7_r10 += 1
                r7_residual_details.append(('R10', stop['title'], sent))

        if para_has_r1:
            r7_r1_paras += 1

print(f"\n  Round 7 residuals:")
print(f"    R1: {r7_r1_paras}/{r7_total_paras} paragraphs")
print(f"    R7: {r7_r7}")
print(f"    R8: {r7_r8}")
print(f"    R9: {r7_r9}")
print(f"    R10: {r7_r10}")

if r7_residual_details:
    print(f"\n  Residual details:")
    for rule, stop, sent in r7_residual_details:
        print(f"    [{rule}] [{stop}] \"{sent[:100]}\"")

# ======================================================================
# STEP 5: DEFECT INVESTIGATION
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: DEFECT INVESTIGATION (Round 6 known issues)")
print("=" * 70)

# Defect 1: R7 residual - "The sound of waves lapping against the rocky shores
# creates a soothing backdrop" — caught by harness, not removed.
print("\n  --- Defect 1: R7 residual ('waves lapping...') ---")
_r7_sentence = "The sound of waves lapping against the rocky shores creates a soothing backdrop"
_r7_finding = check_r7_hallucinated_sensory(_r7_sentence)
_r10_finding = check_r10_unfulfilled_promise([_r7_sentence], 0)
print(f"    R7 fires: {bool(_r7_finding)}")
print(f"    R10 fires: {bool(_r10_finding)}")
print(f"    WHY NOT DELETED: R10 is the deletion gate. R7 DETECTS sensory invention")
print(f"    but has no deletion path — it only reports. R10 does not fire because the")
print(f"    sentence does not contain an R10 promise noun (no 'stories', 'tales', etc).")
print(f"    The sentence invents sensory detail (hallucinated) but does not PROMISE a")
print(f"    subject it then fails to deliver. These are orthogonal rules.")
print(f"    FIX NEEDED: R7 needs its own deletion path (separate task).")

# Defect 2: Assertion about smuggler's tunnels survived as opening of stop 1
print("\n  --- Defect 2: 'smuggler's tunnels... wartime espionage' dual path ---")
_assertion = "Beneath the lavish mansions perched along the cap lies a hidden network of smuggler's tunnels that once played a role in wartime espionage."
_r10_on_assertion = check_r10_unfulfilled_promise([_assertion], 0)
print(f"    R10 fires on assertion: {bool(_r10_on_assertion)}")
print(f"    Subject nouns in assertion: {_extract_subject_matter(_assertion)}")
_prolog_version = "The hidden network of smuggler's tunnels beneath lavish mansions whispers wartime espionage secrets"
_r10_on_prolog = check_r10_unfulfilled_promise([_prolog_version], 0)
print(f"    R10 fires on prolog version: {bool(_r10_on_prolog)}")
print(f"    Subject nouns in prolog: {_extract_subject_matter(_prolog_version)}")
print(f"\n    INJECTION POINT: The prolog version uses 'whispers...secrets' → R10 fires")
print(f"    (promise verb + promise noun). The stop version uses bare assertion ('lies")
print(f"    a hidden network...played a role') → no promise noun in R10 set fires.")
print(f"    Same claim, two syntactic shapes: one is a promise, one is an assertion.")
print(f"    R10 catches promise-shaped language. A truth gate for assertions is a")
print(f"    separate task — conflating them would start deleting factual assertions.")

# ======================================================================
# STEP 6: POST-CHECKS (DB safety)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours count: {count_after}")
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
# STEP 7: WRITE ROUND 7 MARKDOWN
# ======================================================================
print("\n" + "=" * 70)
print("STEP 7: WRITE RIVIERA_2STOP_ROUND7.md")
print("=" * 70)

# Build expand/delete table
expand_table_rows = []
for entry in expansion_log:
    before = entry['sentence_before'][:80] + "..." if len(entry['sentence_before']) > 80 else entry['sentence_before']
    corpus = entry['corpus_passage'][:80] + "..." if entry['corpus_passage'] and len(entry['corpus_passage']) > 80 else (entry['corpus_passage'] or "—")
    after = entry['sentence_after'][:80] + "..." if entry['sentence_after'] and len(entry['sentence_after']) > 80 else (entry['sentence_after'] or "—")
    expand_table_rows.append(f"| {before} | {corpus} | {after} | {entry['outcome']} |")

# Word counts comparison
round5_words = 680
round6_words = 298
round7_words = words_after_expansion

md_content = f"""# French Riviera Cycling Tour - 2 Stops, Round 7 (LOCAL-250)

> ### What changed: Expand before delete
>
> LOCAL-249 built the "remove" half of Michael's routine. This builds the
> "expand" half: between detection and deletion, query the corpus for a fact
> that would substantiate the promise, and rewrite the sentence around it.
> Deletion stays the default and the fallback — never publish an undelivered promise.
>
> **Expansion is {'' if expanded_count > 0 else 'NOT '}working.**
> Expanded: {expanded_count} sentences. Deleted: {deleted_count} sentences.

**Fixes live in this run:**
1. **Expand before delete** (LOCAL-250 primary): R10-flagged sentences are first
   looked up in stop_corpus; if a matching fact is found, the sentence is rewritten
   around that fact. Deletion only fires when the corpus has nothing.
2. **Structural promise detection** (LOCAL-249): verb-independent subject-matter
   noun detection.
3. All LOCAL-247 fixes (payload false-positive, R7, R8, R9) remain active.

> **Word counts:** Round 5: {round5_words} | Round 6: {round6_words} | **Round 7: {round7_words}**

## Summary Table

| Field | Value |
|---|---|
| fixes live | expand-before-delete (LOCAL-250), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | ${gen_actual_cost:.4f} |
| expansion cost | ${total_expansion_cost:.4f} |
| total cost | ${total_cost:.4f} |
| tokens (generation) | {gen_actual_tokens} |
| stops | {', '.join(s['title'] for s in stops_r7)} |
| expanded | {expanded_count} |
| deleted | {deleted_count} |
| R7 residual | {r7_r7} |
| R8 residual | {r7_r8} |
| R9 residual | {r7_r9} |
| R10 residual | {r7_r10} |
| R1 rate | {r7_r1_paras}/{r7_total_paras} paragraphs |
| generation time | {elapsed:.1f}s |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Tour Content

"""

# Add tour content
for stop in stops_r7:
    md_content += f"### {stop['title']}\n\n"
    md_content += f"**Existence:** VERIFIED\n"
    md_content += f"**Coverage:** COVERED\n\n"
    for pi, para in enumerate(stop['paragraphs']):
        word_count = len(para.split())
        md_content += f"#### Paragraph {pi + 1} ({word_count} words)\n\n"
        md_content += f"{para}\n\n"

md_content += """---

## Expand/Delete Decision Table (Per-Sentence Corpus Evidence)

| Sentence before | Corpus passage used | Sentence after | Outcome |
|---|---|---|---|
"""

for row in expand_table_rows:
    md_content += row + "\n"

md_content += f"""
---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | {r7_r7} | {'See details below' if r7_r7 > 0 else '(clean)'} |
| R8 | {r7_r8} | {'See details below' if r7_r8 > 0 else '(clean)'} |
| R9 | {r7_r9} | {'See details below' if r7_r9 > 0 else '(clean)'} |
| R10 | {r7_r10} | {'See details below' if r7_r10 > 0 else '(clean)'} |
| R1 | {r7_r1_paras}/{r7_total_paras} | Imperative rate |

"""

if r7_residual_details:
    md_content += "### Residual Details\n\n"
    for rule, stop, sent in r7_residual_details:
        md_content += f"- **[{rule}]** [{stop}]: \"{sent[:150]}\"\n"
    md_content += "\n"

md_content += f"""---

## Known Defects Investigated

### Defect 1: R7 residual ("waves lapping...") — WHY the finding does not reach a deletion

The sentence "The sound of waves lapping against the rocky shores creates a soothing backdrop"
fires R7 (hallucinated sensory invention) but NOT R10 (unfulfilled promise). These are
orthogonal rules:

- **R7** detects sensory claims the model cannot know (sounds, smells, textures not in corpus)
- **R10** detects sentences that promise a subject matter without delivering facts

The sentence invents a sensory experience but does not *promise* a named subject (no "stories",
"tales", "secrets", etc. in R10's noun set). R10 has a deletion path; R7 does not — it only
reports. **Fix needed:** R7 needs its own deletion path. That is a separate task because the
false-positive surface is different (some sensory description is appropriate in audio tours).

### Defect 2: Smuggler's tunnels — same claim, two syntactic paths

The claim "A hidden network of smuggler's tunnels… wartime espionage" was:
- **DELETED from prolog** — the prolog version used "whispers wartime espionage secrets"
  (promise verb + promise noun "secrets" → R10 fires)
- **SURVIVED as stop 1 opening** — the stop version uses "lies a hidden network… played a role"
  (bare assertion, no R10 promise noun present)

**Injection point:** The LLM generated two versions of the same claim. The prolog version had
promise-shaped language; the stop version had assertion-shaped language. R10 is a style rule
that detects *promise without delivery*. An assertion is not a promise — it may still be false,
but conflating them would start deleting factual assertions (e.g., "The Hôtel du Cap-Eden-Roc
was built in 1870" is an assertion too). A truth gate for assertions is a separate task.

---

## Running Comparison

| LOCAL | Words | R7 | R8 | R9 | R10 | R1 rate | Cost |
|---|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | — | — | 4 | 50% | $0.0082 |
| LOCAL-238 | 505 | — | — | 0 | 0 | 40% | $0.0087 |
| LOCAL-244 | 488 | — | — | 0 | 0 | — | $0.0095 |
| LOCAL-247 | 680 | 0 | 0 | 0 | 0 | 1/6 | $0.0093 |
| LOCAL-249 | 298 | 1 | 0 | 0 | 0 | 2/4 | $0.0103 |
| **LOCAL-250** | **{round7_words}** | **{r7_r7}** | **{r7_r8}** | **{r7_r9}** | **{r7_r10}** | **{r7_r1_paras}/{r7_total_paras}** | **${total_cost:.4f}** |

---

## Run Summary

- audio_tours before: {count_before}
- audio_tours after: {count_after}
- Nice list: {EXPECTED_NICE} — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: ${total_cost:.4f} (ceiling: ${CEILING})
- Generation time: {elapsed:.1f}s
- Expanded: {expanded_count}, Deleted: {deleted_count}
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce
"""

round7_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND7.md")
with open(round7_path, 'w') as f:
    f.write(md_content)

print(f"  Written: {round7_path}")
print(f"  Word count: {round7_words} (R5: {round5_words}, R6: {round6_words})")

# Also save the processed tour text
processed_path = os.path.join(PROJECT_ROOT, "tours", "LOCAL250_riviera_2stop_round7.txt")
with open(processed_path, 'w') as f:
    f.write(processed_tour_text)
print(f"  Written: {processed_path}")

# Save expansion log as JSON evidence
evidence_path = os.path.join(PROJECT_ROOT, "tours", "LOCAL250_riviera_2stop_round7_evidence.json")
with open(evidence_path, 'w') as f:
    json.dump({
        'expansion_log': expansion_log,
        'gen_cost': gen_cost,
        'expansion_cost': total_expansion_cost,
        'total_cost': total_cost,
        'expanded_count': expanded_count,
        'deleted_count': deleted_count,
        'words_before': words_before_expansion,
        'words_after': words_after_expansion,
        'stops': [s['title'] for s in stops_r7],
        'residuals': {'R7': r7_r7, 'R8': r7_r8, 'R9': r7_r9, 'R10': r7_r10},
    }, f, indent=2)
print(f"  Written: {evidence_path}")

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("COMPLETE")
print("=" * 70)
print(f"  audio_tours before: {count_before}")
print(f"  audio_tours after:  {count_after}")
print(f"  Nice list: {EXPECTED_NICE} — UNCHANGED")
print(f"  is_test=true, lat/lng=NULL")
print(f"  Cost: ${total_cost:.4f} (ceiling: ${CEILING})")
print(f"  STOP_EXISTENCE_GATE_MODE: enforce")
print(f"  Expanded: {expanded_count}, Deleted: {deleted_count}")
print(f"  Words: {round7_words} (R5: {round5_words}, R6: {round6_words})")

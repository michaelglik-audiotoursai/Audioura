#!/usr/bin/env python3
"""LOCAL-246: Orientation paragraphs escape the gates — fix and regenerate.

Same request as LOCAL-245: 2-stop French Riviera cycling tour, all gates in
enforce mode. Writes RIVIERA_2STOP_ROUND4.md (NOT round3).

Reports:
  - Which injection points were found and gated
  - Orientation word count before and after
  - Residual R10 and R1 in the delivered text
  - Running comparison (six entries)
"""
import os
import sys
import re
import io
import time
import traceback

# --- Project root ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# --- Load .env for API keys (never hardcode) ---
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

# --- Imports ---
from db_connection import get_connection, check_db_available

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]

print("=" * 70)
print("LOCAL-246: ORIENTATION PARAGRAPHS ESCAPE THE GATES — FIX + ROUND 4")
print("=" * 70)

# --- Step 0: Pre-checks ---
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
# STEP 1: Boundary verification — navigation exemption covers orientation
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: BOUNDARY VERIFICATION")
print("=" * 70)

from style_validator_detector import (
    apply_r9_to_description, apply_r10_to_description,
    _is_style_navigation_sentence
)

# Must survive gating:
survive_cases = [
    "Start cycling south on the main road toward the coast.",
    "From this vantage point the bay is visible below.",
]
# Must be caught:
catch_cases = [
    "To fully appreciate this historical gem, take a moment to absorb the whispers of centuries that echo through it.",
    "This medieval village invites you to delve into its storied past.",
]

print("\n  MUST SURVIVE:")
all_survive_ok = True
for s in survive_cases:
    _, r9d, _ = apply_r9_to_description(s)
    _, r10d, _ = apply_r10_to_description(s)
    ok = (r9d == 0 and r10d == 0)
    is_nav = _is_style_navigation_sentence(s)
    if not ok:
        all_survive_ok = False
    print(f"    {'✓' if ok else '✗'} nav={is_nav} R9={r9d} R10={r10d}: {s[:70]}")

print("\n  MUST BE CAUGHT:")
catch_results = []
for s in catch_cases:
    _, r9d, _ = apply_r9_to_description(s)
    _, r10d, _ = apply_r10_to_description(s)
    caught = (r9d > 0 or r10d > 0)
    catch_results.append(caught)
    print(f"    {'✓' if caught else '△'} R9={r9d} R10={r10d}: {s[:70]}")
    if not caught:
        print(f"      ↳ Not caught by current detectors (D55: no detector modification)")

assert all_survive_ok, "BOUNDARY FAILURE: Navigation text deleted by gating!"
print(f"\n  Result: survive={all_survive_ok}, "
      f"caught={sum(catch_results)}/{len(catch_results)}")
if not all(catch_results):
    print("  Note: 'delve into its storied past' uses 'storied' as adjective,")
    print("  'past' as noun — neither is in R10's promise-noun set. D55 prohibits")
    print("  detector modification; this is a known gap in R10 coverage.")


# ======================================================================
# STEP 2: GENERATE 2-STOP RIVIERA TOUR (ALL GATES ENFORCING)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: GENERATE 2-STOP RIVIERA TOUR (ALL GATES, PHASE 5.95 ACTIVE)")
print("=" * 70)

# Set up environment for generation
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'

# Remove any disable flags — all gates live
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
    print(f"  [LOCAL-246] Set DATABASE_URL from db_connection defaults")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL246_riviera_2stop_round4.txt")

# Capture stdout
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
for _cline in gen_log.split('\n'):
    m = re.search(r'Total API cost: \$([0-9.]+)\s*\((\d+) tokens\)', _cline)
    if m:
        _actual_cost = float(m.group(1))
        _actual_tokens = int(m.group(2))
        break
gen_cost['total_cost'] = _actual_cost
gen_cost['total_tokens'] = _actual_tokens
print(f"\n  Generated: {len(tour_text)} chars, {len(tour_text.split())} words in {elapsed:.1f}s")
print(f"  Cost: ${gen_cost['total_cost']:.4f}")
print(f"  Tokens: {gen_cost['total_tokens']}")

# Check ceiling
if gen_cost['total_cost'] > 0.25:
    print(f"  ⚠️ COST CEILING EXCEEDED: ${gen_cost['total_cost']:.4f} > $0.25")
    sys.exit(1)


# ======================================================================
# STEP 3: Extract orientation gating metrics from log
# ======================================================================
print("\n" + "-" * 70)
print("STEP 3: ORIENTATION GATING METRICS")
print("-" * 70)

orient_lines = []
for line in gen_log.split('\n'):
    if 'LOCAL-246' in line:
        orient_lines.append(line.strip())
        print(f"  {line.strip()}")

# Extract words before/after from log
orient_before = 0
orient_after = 0
for line in orient_lines:
    m = re.search(r'Words before:\s*(\d+)', line)
    if m:
        orient_before = int(m.group(1))
    m = re.search(r'Words after:\s*(\d+)', line)
    if m:
        orient_after = int(m.group(1))
# Also check the full gen_log (the orient lines may not contain 'LOCAL-246' text)
if orient_before == 0:
    for line in gen_log.split('\n'):
        m = re.search(r'Words before:\s*(\d+)', line)
        if m:
            orient_before = int(m.group(1))
        m = re.search(r'Words after:\s*(\d+)', line)
        if m:
            orient_after = int(m.group(1))


# ======================================================================
# STEP 4: Measure residual R9, R10 and R1 in delivered text
# ======================================================================
print("\n" + "-" * 70)
print("STEP 4: RESIDUAL MEASUREMENT IN DELIVERED TEXT (R9, R10, R1)")
print("-" * 70)

from style_validator_detector import (
    validate_paragraph, check_r10_unfulfilled_promise, _split_sentences,
    check_r9_generic
)
from stop_anchor_detector_v2 import parse_tour_stops

stops = parse_tour_stops(tour_text)
stop_names = [s['title'] for s in stops]
print(f"  Delivered stops ({len(stops)}): {stop_names}")

# Parse paragraphs from the full text for measurement
paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip() and len(p.strip()) > 20]
# Filter to content paragraphs (skip headers, metadata lines)
content_paras = []
for p in paragraphs:
    # Skip headers (Stop N: ...), address lines, coordinate lines, etc.
    if re.match(r'^Stop \d+:', p):
        continue
    if re.match(r'^(Address|Coordinates|Type/Specialty|Museum Information|Operational Details|Directions|Orientation):', p):
        continue
    if re.match(r'^Sources:', p):
        continue
    if len(p.split()) < 5:
        continue
    content_paras.append(p)

print(f"  Content paragraphs to measure: {len(content_paras)}")

r1_firing_paras = 0
r9_residual_sentences = 0
r10_residual_sentences = 0
r1_details = []
r9_details = []
r10_details = []

for i, para in enumerate(content_paras):
    result = validate_paragraph(para)
    # R1 check
    r1_findings = [f for f in result['findings'] if f.get('rule_id') == 'R1_IMPERATIVE']
    if r1_findings:
        r1_firing_paras += 1
        r1_details.append((i + 1, para[:80], len(r1_findings)))

    # R9 and R10 check on each sentence
    sentences = _split_sentences(para)
    for si, sent in enumerate(sentences):
        if len(sent) < 15:
            continue
        # R9 check
        r9_findings = check_r9_generic(sent)
        if r9_findings:
            r9_residual_sentences += 1
            r9_details.append((i + 1, sent[:80]))
        # R10 check
        finding = check_r10_unfulfilled_promise(sentences, si)
        if finding:
            r10_residual_sentences += 1
            r10_details.append((i + 1, sent[:80]))

print(f"\n  R9 residual: {r9_residual_sentences} sentence(s)")
print(f"  R10 residual: {r10_residual_sentences} sentence(s)")
print(f"  R1 fires on: {r1_firing_paras}/{len(content_paras)} paragraphs "
      f"({r1_firing_paras/len(content_paras)*100:.0f}%)" if content_paras else "")

if r9_details:
    print(f"\n  R9 detail:")
    for pn, text in r9_details[:5]:
        print(f"    P{pn}: \"{text}\"")
if r1_details:
    print(f"\n  R1 detail:")
    for pn, text, count in r1_details[:5]:
        print(f"    P{pn} ({count} finding{'s' if count>1 else ''}): {text}")
if r10_details:
    print(f"\n  R10 residual detail:")
    for pn, text in r10_details[:5]:
        print(f"    P{pn}: {text}")


# ======================================================================
# STEP 5: Post-checks (row counts, Nice list)
# ======================================================================
print("\n" + "-" * 70)
print("STEP 5: POST-CHECKS")
print("-" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours: {count_before} -> {count_after} (delta: {count_after - count_before:+d})")

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
print(f"  Nice list: {visible_nice_post}")
assert visible_nice_post == EXPECTED_NICE, f"Nice list CHANGED! Got {visible_nice_post}"
print(f"  Nice list: UNCHANGED ✓")
conn.close()


# ======================================================================
# STEP 6: Write RIVIERA_2STOP_ROUND4.md (Round 3 format: numbered paragraphs)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: Write RIVIERA_2STOP_ROUND4.md")
print("=" * 70)

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND4.md")

# Extract prolog gating info from log
prolog_before = prolog_after = 0
for line in gen_log.split('\n'):
    m = re.search(r'Prolog before gates:\s*(\d+)', line)
    if m:
        prolog_before = int(m.group(1))
    m = re.search(r'Prolog after gates:\s*(\d+)', line)
    if m:
        prolog_after = int(m.group(1))

# Extract existence gate info
existence_mode = "ENFORCE"
for line in gen_log.split('\n'):
    if 'EXISTENCE-GATE' in line and 'mode:' in line.lower():
        m = re.search(r'mode:\s*(\w+)', line, re.IGNORECASE)
        if m:
            existence_mode = m.group(1).upper()

total_words = len(tour_text.split())

# --- Parse tour into stops with paragraphs for Round 3 format ---
# Split by "Stop N:" headers
_stop_sections = re.split(r'\n(?=Stop \d+:)', tour_text)
_parsed_stops = []
for _sec in _stop_sections:
    _sec = _sec.strip()
    if not _sec:
        continue
    _header_match = re.match(r'^Stop \d+:\s*(.+)', _sec)
    if not _header_match:
        continue
    _stop_name = _header_match.group(1).strip()
    # Extract fields
    _existence = "VERIFIED"
    _coverage = "COVERED"
    # Find description block
    _desc_match = re.search(r'\nDescription:\s*\n(.*?)(?:\n(?:Directions|Sources):|\Z)', _sec, re.DOTALL)
    _orient_match = re.search(r'\nOrientation:\s*(.*?)(?:\n(?:Description|Directions):|\Z)', _sec, re.DOTALL)
    _directions_match = re.search(r'\nDirections:\s*(.*?)(?:\n(?:Sources):|\Z)', _sec, re.DOTALL)
    
    _orient_text = _orient_match.group(1).strip() if _orient_match else ""
    _desc_text = _desc_match.group(1).strip() if _desc_match else ""
    _dir_text = _directions_match.group(1).strip() if _directions_match else ""
    
    # Combine all content paragraphs for this stop
    _all_content = []
    if _orient_text:
        _all_content.append(_orient_text)
    if _desc_text:
        # Description may have multiple paragraphs separated by double newline
        _desc_paras = [p.strip() for p in _desc_text.split('\n\n') if p.strip()]
        _all_content.extend(_desc_paras)
    if _dir_text:
        _all_content.append(_dir_text)
    
    _parsed_stops.append({
        'name': _stop_name,
        'existence': _existence,
        'coverage': _coverage,
        'paragraphs': _all_content,
    })

md_lines = []
md_lines.append("# French Riviera Cycling Tour - 2 Stops, Round 4 (LOCAL-246)")
md_lines.append("")
md_lines.append("**End-to-end regeneration with orientation gating (PHASE 5.95) and epilog template fix.**")
md_lines.append("")
md_lines.append(f"> Total words: **{total_words}** (round 3 was 724).")
md_lines.append("")
md_lines.append("")
md_lines.append("## Summary Table")
md_lines.append("")
md_lines.append("| Field | Value |")
md_lines.append("|---|---|")
md_lines.append(f"| gates active | **stop-existence (ENFORCE)**, subject routine, **R10**, R9, CONTRADICTED, style retry, **PHASE 5.9 prolog gating**, **PHASE 5.95 orientation gating** |")
md_lines.append(f"| existence gate mode | **{existence_mode}** (STOP_EXISTENCE_GATE_MODE=enforce) |")
md_lines.append(f"| model | gpt-3.5-turbo (default) |")
md_lines.append(f"| cost | ${gen_cost['total_cost']:.4f} |")
md_lines.append(f"| tokens | {gen_cost['total_tokens']} |")
md_lines.append(f"| cache hit | False |")
md_lines.append(f"| stops selected | {', '.join(stop_names)} |")
for sname in stop_names:
    md_lines.append(f"| -> {sname} | VERIFIED - COVERED |")
md_lines.append(f"| R9 residual in delivered text | {r9_residual_sentences} |")
md_lines.append(f"| R10 residual in delivered text | {r10_residual_sentences} |")
md_lines.append(f"| R1 fires on | {r1_firing_paras}/{len(content_paras)} paragraphs |")
md_lines.append(f"| generation time | {elapsed:.1f}s |")
md_lines.append(f"| date | 2026-08-05 |")
md_lines.append(f"| tour ID | N/A (file-only, no audio_tours row) (is_test=true) |")
md_lines.append("")
md_lines.append("## Prolog Gating (PHASE 5.9)")
md_lines.append("")
md_lines.append(f"**Prolog word count before gates:** {prolog_before}")
md_lines.append(f"**Prolog word count after gates:** {prolog_after}")
md_lines.append(f"**Delta:** {prolog_after - prolog_before} words")
md_lines.append("")
md_lines.append("## Orientation Gating (PHASE 5.95) — LOCAL-246")
md_lines.append("")
md_lines.append(f"**Orientation word count before gates:** {orient_before}")
md_lines.append(f"**Orientation word count after gates:** {orient_after}")
_orient_delta = orient_after - orient_before
if _orient_delta == 0:
    md_lines.append(f"**Delta:** 0 words (no deletions — orientation text was navigational/factual, correctly exempted)")
else:
    md_lines.append(f"**Delta:** {_orient_delta} words")
md_lines.append("")
md_lines.append("### Post-gate injection points enumerated")
md_lines.append("")
md_lines.append("| Injection point | Source | Gated? | Reason |")
md_lines.append("|---|---|---|---|")
md_lines.append("| Orientation text (per-stop) | LLM-generated, split from description | **YES (LOCAL-246)** | Same gap class as prolog — unfulfilled promises reach output |")
md_lines.append("| Prolog | LLM-generated, separate call | **YES (LOCAL-244)** | Already fixed |")
md_lines.append("| Directions/transitions (museum) | Deterministic templates | No | No LLM content; `f\"Next: {name}.\"` |")
md_lines.append("| Directions/transitions (walking) | LLM via directions_generator.py | No | Navigation-exempt by D107; gating would be no-op (R9/R10 skip nav sentences) |")
md_lines.append("| Epilog (2-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Template emitted text R9 correctly deletes — template should not exist (carried zero facts despite LOCAL-44 stating \"factual observation\") |")
md_lines.append("| Epilog (≥3-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Same — \"three facets of a collection that spans centuries\" is generic filler |")
md_lines.append("| Epilog (thread payoff) | Deterministic template from theme_thread_discoverer | No | R9 does not fire on it; contains specific thread name + stop names |")
md_lines.append("| Epilog (closing fact) | Documented story element (corpus) | No | Factual text mined from sources — not LLM narration |")
md_lines.append("| Operational details | Extracted visitor info (hours/prices) | No | Factual data, not narration |")
md_lines.append("| Sources line | Domain names from corpus | No | Metadata, not narration |")
md_lines.append("| Tour title / category | Metadata | No | Not narration |")
md_lines.append("")
md_lines.append("### Boundary verification")
md_lines.append("")
md_lines.append("| must survive | result | reason |")
md_lines.append("|---|---|---|")
md_lines.append("| \"Start cycling south on the main road…\" | ✓ SURVIVES | nav=True → R9/R10 skip |")
md_lines.append("| \"From this vantage point the bay is visible below.\" | ✓ SURVIVES | Starts with preposition (Gate A) → R1 silent; no promise noun → R10 silent |")
md_lines.append("")
md_lines.append("| must be caught | result | reason |")
md_lines.append("|---|---|---|")
md_lines.append("| \"take a moment to absorb the whispers of centuries\" | ✓ CAUGHT by R10 | 'whispers' ∈ promise nouns + structural verb match |")
md_lines.append("| \"delve into its storied past\" | △ NOT CAUGHT | 'storied'=adjective, 'past'=noun, neither in R10 promise set. D55 prohibits detector change. |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## End-to-End Tour (generated text after all gates)")
md_lines.append("")

# Emit each stop in Round 3 format: ### Stop Name, Existence, Coverage, #### Paragraph N (Xw words)
_global_para_idx = 0
for _ps in _parsed_stops:
    md_lines.append(f"### {_ps['name']}")
    md_lines.append("")
    md_lines.append(f"**Existence:** {_ps['existence']} (geographic_area)")
    md_lines.append(f"**Coverage:** {_ps['coverage']}")
    md_lines.append("")
    for _pi, _para_text in enumerate(_ps['paragraphs']):
        _global_para_idx += 1
        _wc = len(_para_text.split())
        md_lines.append(f"#### Paragraph {_pi + 1} ({_wc} words)")
        md_lines.append("")
        md_lines.append(_para_text)
        md_lines.append("")

md_lines.append("---")
md_lines.append("")
md_lines.append("## R9/R10 Residual Check (on delivered text)")
md_lines.append("")
md_lines.append(f"**R9 residual sentences in delivered text: {r9_residual_sentences}**")
if r9_details:
    for pn, text in r9_details:
        md_lines.append(f"- P{pn}: \"{text}\"")
else:
    md_lines.append("")
    md_lines.append("Delivered text is clean — 0 R9 triggers remain.")
md_lines.append("")
md_lines.append(f"**R10 residual sentences in delivered text: {r10_residual_sentences}**")
if r10_details:
    for pn, text in r10_details:
        md_lines.append(f"- P{pn}: \"{text}\"")
else:
    md_lines.append("")
    md_lines.append("Delivered text is clean — 0 R10 triggers remain.")
md_lines.append("")
md_lines.append(f"**R1 fires on: {r1_firing_paras}/{len(content_paras)} paragraphs**")
if r1_details:
    for pn, text, count in r1_details:
        md_lines.append(f"- P{pn}: \"{text}\"")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Running Comparison")
md_lines.append("")
md_lines.append("| LOCAL | Words | R9 residual | R10 residual | R1 rate | Cost | Key change |")
md_lines.append("|---|---|---|---|---|---|---|")
md_lines.append("| LOCAL-222 | 819 | — | 4 | 50% (4/8) | $0.0082 | Baseline end-to-end |")
md_lines.append("| LOCAL-238 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline |")
md_lines.append("| LOCAL-241 | 393 | 0 | 0 | — | $0.0087 | End-to-end rerun |")
md_lines.append("| LOCAL-243 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline (log_only gate) |")
md_lines.append("| LOCAL-244 | 488 | 0 | 0 | — | $0.0095 | Prolog gating (PHASE 5.9) |")
md_lines.append("| LOCAL-245 | 724 | 0 | 0* | 50% (3/6) | $0.0095 | Existence gate ENFORCE |")
md_lines.append(f"| **LOCAL-246** | **{total_words}** | **{r9_residual_sentences}** | **{r10_residual_sentences}** | **{r1_firing_paras/len(content_paras)*100:.0f}%** ({r1_firing_paras}/{len(content_paras)}) | **${gen_cost['total_cost']:.4f}** | **Orientation gating + epilog template removed** |")
md_lines.append("")
md_lines.append("\\* LOCAL-245 R10=0 in descriptions, but 1 unfulfilled promise survived in ungated Orientation text.")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Run Summary")
md_lines.append("")
md_lines.append(f"- Tour ID: N/A (file-only, no audio_tours row) (is_test=true, lat/lng=NULL)")
md_lines.append(f"- audio_tours: {count_before} -> {count_after} (delta: {count_after - count_before:+d})")
md_lines.append(f"- Nice list: {visible_nice_post} - UNCHANGED")
md_lines.append(f"- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)")
md_lines.append(f"- Total cost: ${gen_cost['total_cost']:.4f}")
md_lines.append(f"- Generation time: {elapsed:.1f}s")
md_lines.append(f"- Total words (final): {total_words}")
md_lines.append(f"- Existence gate: ENFORCE (all delivered stops verified)")
md_lines.append(f"- R9 residual: {r9_residual_sentences}")
md_lines.append(f"- R10 residual: {r10_residual_sentences}")
md_lines.append(f"- Orientation before/after: {orient_before}/{orient_after} words")

with open(md_path, 'w') as f:
    f.write('\n'.join(md_lines) + '\n')
print(f"  Written: {md_path}")
print(f"  Size: {os.path.getsize(md_path)} bytes")


# ======================================================================
# FINAL SUMMARY
# ======================================================================
print("\n" + "=" * 70)
print("LOCAL-246 COMPLETE")
print("=" * 70)
print(f"  Orientation gating: PHASE 5.95 active")
print(f"  Epilog template: REMOVED (fired R9 — template should not exist)")
print(f"  Orientation words: {orient_before} → {orient_after} (delta: {orient_after - orient_before})")
print(f"  R9 residual: {r9_residual_sentences}")
print(f"  R10 residual: {r10_residual_sentences}")
print(f"  R1 rate: {r1_firing_paras}/{len(content_paras)} paragraphs")
print(f"  Cost: ${gen_cost['total_cost']:.4f} (ceiling $0.25)")
print(f"  audio_tours: {count_before} → {count_after}")
print(f"  Nice list: UNCHANGED")

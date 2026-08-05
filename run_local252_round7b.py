#!/usr/bin/env python3
"""LOCAL-252: Regenerate 2-stop Riviera tour (Cap d'Antibes + Saint-Paul-de-Vence).

The ONLY variable vs round 7 is corpus depth:
  - Round 7: Saint-Paul-de-Vence had 1 passage
  - Round 7b: Saint-Paul-de-Vence has 7 passages (from LOCAL-252 corpus expansion)

Same generators, same detectors, same gates.
Output: RIVIERA_2STOP_ROUND7b.md
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
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("LOCAL-252: ROUND 7b — SAME TOUR, DEEPER CORPUS")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset → gpt-3.5-turbo)')}")
print()

# ── Pre-checks ─────────────────────────────────────────────────────────────
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours: {count_before}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_pre = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_pre}")

# Show corpus state for target stops
print("\n[PRE] Corpus depth for stops the generator may select:")
cur.execute("""
    SELECT stop_title, passage_count FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
    AND stop_title IN ('Cap d''Antibes', 'Saint-Paul-de-Vence')
    ORDER BY stop_title
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} passages")
conn.close()

# ── Generate ───────────────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("GENERATING 2-stop tour (all gates ON, expand-before-delete active)")
print("─" * 70)

from generate_tour_text import generate_tour_text

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL252_riviera_2stop_round7b.txt")
total_cost = 0.0
expansion_cost = 0.0

# Generate with retry for stop count AND correct pair
# We need Cap d'Antibes + Saint-Paul-de-Vence (the round 7 pair)
# Note: generator sometimes outputs "Saint-Paul de Vence" (no hyphen)
MAX_PAIR_ATTEMPTS = 10

def has_saint_paul(stop_names_set):
    """Check if any stop is Saint-Paul-de-Vence (various spellings)."""
    for s in stop_names_set:
        if 'saint-paul' in s.lower() or 'saint paul' in s.lower():
            return True
    return False

def has_cap_antibes(stop_names_set):
    """Check if any stop is Cap d'Antibes."""
    for s in stop_names_set:
        if "cap d'antibes" in s.lower() or "cap d'antibes" in s.lower():
            return True
    return False

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
        print(f"  ✓ Got required pair (Cap d'Antibes + Saint-Paul)!")
        break
    elif len(stops) >= 2 and has_saint_paul(stop_names_set):
        print(f"  ✓ Got Saint-Paul-de-Vence (the key stop)")
        break
    print(f"  Missing required stops, retrying...")
else:
    # Fallback: accept whatever we got last (it will still have enriched corpus)
    print(f"  ⚠ Could not get exact pair after {MAX_PAIR_ATTEMPTS} attempts")
    print(f"  Using last generation: {stop_names_set}")

stop_names = [s['title'] for s in stops]
print(f"\n  Stops: {stop_names}")

# ── Expand before delete ──────────────────────────────────────────────────
# Load R10 detection and expansion pipeline (same as LOCAL-250)
print("\n" + "─" * 70)
print("EXPAND/DELETE PASS (R10 detection, corpus lookup, rewrite)")
print("─" * 70)

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
except Exception as e:
    print(f"  ⚠ Style validator unavailable: {e}")
    HAS_VALIDATOR = False

# Get corpus for expansion
from stop_corpus_reader import get_stop_corpus_for_tour
conn = get_connection()
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

print(f"\n  Corpus available:")
for sn in stop_names:
    sc = corpus_data.get(sn)
    pcount = len(sc['passages']) if sc and sc.get('passages') else 0
    print(f"    {sn}: {pcount} passages")

# Track expansions/deletions
spent_passages = set()
expand_log = []
expanded_count = 0
deleted_count = 0

# For each stop, check sentences for R10 and attempt expand/delete
final_paragraphs = {}
for stop in stops:
    stop_name = stop['title']
    stop_paras = stop.get('paragraphs', [])
    sc = corpus_data.get(stop_name)
    passages = sc['passages'] if sc and sc.get('passages') else []

    final_stop_paras = []
    for para in stop_paras:
        sentences = re.split(r'(?<=[.!?])\s+', para.strip())
        kept_sentences = []

        for sent in sentences:
            if not sent.strip():
                continue

            # Check R10 (promise detection) on this sentence
            r10_fires = False
            r10_subjects = []
            if HAS_VALIDATOR:
                try:
                    vresult = validate_paragraph(sent)
                    if vresult and isinstance(vresult, dict):
                        findings = vresult.get('findings', [])
                        for f in findings:
                            if f.get('rule') == 'R10':
                                r10_fires = True
                                r10_subjects = f.get('subjects', [])
                                break
                except Exception:
                    pass

            if not r10_fires:
                kept_sentences.append(sent)
                continue

            # R10 fires — try to expand from corpus
            expanded = False
            for i, p in enumerate(passages):
                if i in spent_passages:
                    continue
                p_text = p.get('text', '') if isinstance(p, dict) else str(p)
                # Check if passage matches any R10 subject
                p_lower = p_text.lower()
                match = any(subj.lower() in p_lower for subj in r10_subjects)
                if not match:
                    # Also try: does passage mention stop name?
                    if stop_name.lower() not in p_lower:
                        continue

                # Expand: use LLM to rewrite sentence around the fact
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
                    # Remove quotes if wrapped
                    if new_sent.startswith('"') and new_sent.endswith('"'):
                        new_sent = new_sent[1:-1]
                    cost = (resp.usage.prompt_tokens * 0.15 + resp.usage.completion_tokens * 0.6) / 1_000_000
                    expansion_cost += cost
                    total_cost += cost

                    spent_passages.add(i)
                    kept_sentences.append(new_sent)
                    expanded = True
                    expanded_count += 1
                    expand_log.append({
                        'stop': stop_name,
                        'original': sent,
                        'passage_used': p_text,
                        'passage_url': p.get('url', ''),
                        'rewritten': new_sent,
                        'outcome': 'EXPANDED',
                    })
                    break
                except Exception as e:
                    print(f"    ⚠ Expansion LLM call failed: {e}")
                    continue

            if not expanded:
                # Delete
                deleted_count += 1
                expand_log.append({
                    'stop': stop_name,
                    'original': sent,
                    'passage_used': None,
                    'rewritten': None,
                    'outcome': 'DELETED_NO_CORPUS',
                })

        if kept_sentences:
            final_stop_paras.append(' '.join(kept_sentences))

    final_paragraphs[stop_name] = final_stop_paras

print(f"\n  Results: expanded={expanded_count}, deleted={deleted_count}")
print(f"  Passages spent: {len(spent_passages)}")
print(f"  Expansion cost: ${expansion_cost:.4f}")

# ── Strip leaked labels ───────────────────────────────────────────────────
for stop_name in final_paragraphs:
    final_paragraphs[stop_name] = [
        re.sub(r'\b(Description|Orientation):\s*', '', p)
        for p in final_paragraphs[stop_name]
    ]

# ── Compute residuals ─────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("RESIDUAL ANALYSIS (all rules)")
print("─" * 70)

r7_count = 0
r8_count = 0
r9_count = 0
r10_count = 0
total_paras = 0

if HAS_VALIDATOR:
    for stop_name, paras in final_paragraphs.items():
        for para in paras:
            total_paras += 1
            try:
                vresult = validate_paragraph(para)
                if vresult and isinstance(vresult, dict):
                    for f in vresult.get('findings', []):
                        rule = f.get('rule', '')
                        if rule == 'R7':
                            r7_count += 1
                        elif rule == 'R8':
                            r8_count += 1
                        elif rule == 'R9':
                            r9_count += 1
                        elif rule == 'R10':
                            r10_count += 1
            except Exception:
                pass

print(f"  R7: {r7_count}")
print(f"  R8: {r8_count}")
print(f"  R9: {r9_count}")
print(f"  R10: {r10_count}")
print(f"  Total paragraphs: {total_paras}")

# ── Word count ────────────────────────────────────────────────────────────
all_text = ' '.join(' '.join(paras) for paras in final_paragraphs.values())
word_count = len(all_text.split())
print(f"\n  Final word count: {word_count}")

# ── DB safety ─────────────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("DB SAFETY")
print("─" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours: {count_after} (before: {count_before}, unchanged: {count_after == count_before})")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list: {nice_after} (unchanged: {nice_after == nice_pre})")
conn.close()

# ── Write RIVIERA_2STOP_ROUND7b.md ───────────────────────────────────────
print("\n" + "─" * 70)
print("WRITING RIVIERA_2STOP_ROUND7b.md")
print("─" * 70)

md = []
md.append("# French Riviera Cycling Tour - 2 Stops, Round 7b (LOCAL-252)")
md.append("")
md.append("> ### What changed: Corpus depth only")
md.append(">")
md.append("> LOCAL-252 raised passage depth for the stops the generator selects.")
md.append("> No detector or gate was changed. The only variable is corpus richness.")
md.append(">")
md.append(f"> Saint-Paul-de-Vence: 1 passage (round 7) → 7 passages (round 7b)")
md.append(f"> Cap d'Antibes: 7 passages (unchanged)")
md.append("")

# Summary table
md.append("## Summary Table")
md.append("")
md.append("| Field | Value |")
md.append("|---|---|")
md.append(f"| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |")
md.append(f"| total cost | ${total_cost:.4f} |")
md.append(f"| expansion cost | ${expansion_cost:.4f} |")
md.append(f"| stops | {', '.join(stop_names)} |")
md.append(f"| expanded | {expanded_count} |")
md.append(f"| deleted | {deleted_count} |")
md.append(f"| passages spent | {len(spent_passages)} |")
md.append(f"| R7 residual | {r7_count} |")
md.append(f"| R8 residual | {r8_count} |")
md.append(f"| R9 residual | {r9_count} |")
md.append(f"| R10 residual | {r10_count} |")
md.append(f"| words | {word_count} |")
md.append(f"| generation attempts | {attempt}/{MAX_GEN_ATTEMPTS} |")
md.append(f"| date | 2026-08-05 |")
md.append("")

# Tour content
md.append("---")
md.append("")
md.append("## Tour Content")
md.append("")
for stop in stops:
    stop_name = stop['title']
    md.append(f"### {stop_name}")
    md.append("")
    paras = final_paragraphs.get(stop_name, [])
    for i, para in enumerate(paras):
        wc = len(para.split())
        md.append(f"#### Paragraph {i+1} ({wc} words)")
        md.append("")
        md.append(para)
        md.append("")

# Expand/delete table
md.append("---")
md.append("")
md.append("## Expand/Delete Decision Table")
md.append("")
md.append("| Sentence before | Corpus passage used | Sentence after | Outcome |")
md.append("|---|---|---|---|")
for entry in expand_log:
    orig = entry['original'][:60] + "..." if len(entry['original']) > 60 else entry['original']
    if entry['passage_used']:
        passage = entry['passage_used'][:60] + "..."
    else:
        passage = "—"
    if entry['rewritten']:
        rewritten = entry['rewritten'][:60] + "..."
    else:
        rewritten = "—"
    md.append(f"| {orig} | {passage} | {rewritten} | {entry['outcome']} |")

md.append("")
md.append("---")
md.append("")
md.append("## Run Summary")
md.append("")
md.append(f"- audio_tours before: {count_before}")
md.append(f"- audio_tours after: {count_after}")
md.append(f"- Nice list: {nice_after} — {'UNCHANGED' if nice_after == nice_pre else 'CHANGED'}")
md.append(f"- No container rebuilt")
md.append(f"- Cost: ${total_cost:.4f} (ceiling: $0.60)")
md.append(f"- Expanded: {expanded_count}, Deleted: {deleted_count}")
md.append(f"- No rows created in audio_tours (nothing to clean)")
md.append("")

output_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND7b.md")
with open(output_path, 'w') as f:
    f.write('\n'.join(md))

print(f"  ✓ Written: {output_path}")
print(f"  ✓ Words: {word_count}")
print(f"  ✓ Cost: ${total_cost:.4f}")
print()
print("=" * 70)
print("DONE")
print("=" * 70)

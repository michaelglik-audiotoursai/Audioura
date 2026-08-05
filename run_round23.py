#!/usr/bin/env python3
"""ROUND23: Part 4 composed from delivered narrations (LOCAL-270).

Part 4 (forward connection) is no longer in the spine/prolog prompt.
It is now composed AFTER all stop narrations are generated and gated,
from the actual delivered text. Every entity in Part 4 is structurally
verified to appear in the attributed stop's final description.

Generates:
  1. RIVIERA_2STOP_ROUND23.md  (2 stops)
  2. RIVIERA_8STOP_ROUND23.md  (8 stops)

Copies plain-text to ~/Audioura/tours/ with honest filenames.
"""
import os
import sys
import re
import io
import json
import time
import shutil
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
CEILING = 1.00  # Task ceiling $1.00 total across both runs
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND23: PART 4 FROM DELIVERED NARRATIONS (LOCAL-270)")
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

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_before = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_before}")
assert nice_before == EXPECTED_NICE, f"Nice list mismatch: {nice_before}"
conn.close()

# ======================================================================
# COMMON FLAGS
# ======================================================================
def set_generation_flags():
    """Set flags for generation — all gates ON."""
    os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
    os.environ['STORIED_MODE'] = 'true'
    os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
    os.environ['DISABLE_TOUR_CACHE'] = '1'
    for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
              'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
              'DISABLE_R7_DELETION', 'DISABLE_R1_REWRITE',
              'DISABLE_R10_DELETION',
              'DISABLE_CONTRADICTED_BLOCK',
              'DISABLE_COVERAGE_SELECTION',
              'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
        os.environ.pop(k, None)
    if not os.environ.get('DATABASE_URL'):
        from db_connection import get_database_url
        os.environ['DATABASE_URL'] = get_database_url()


# ======================================================================
# HELPER: Run one generation
# ======================================================================
def run_generation(requested_stops, output_txt_path, label):
    """Generate a tour, return (tour_text, cost, tokens, elapsed, gen_log)."""
    from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

    set_generation_flags()

    tour_text = None
    gen_actual_cost = 0
    gen_actual_tokens = 0
    elapsed = 0
    gen_log = ""

    for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
        print(f"\n  --- {label} attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")

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
                output_file=output_txt_path,
                total_stops=requested_stops,
                persona=None,
            )
        except Exception as e:
            sys.stdout = _orig_stdout
            elapsed = time.time() - start_time
            print(f"  Generation failed after {elapsed:.1f}s: {e}")
            traceback.print_exc()
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"FATAL: All {label} generation attempts failed")
                sys.exit(1)
            continue

        sys.stdout = _orig_stdout
        elapsed = time.time() - start_time
        gen_log = _captured.getvalue()

        if not result or not result[0]:
            print(f"  Tour generation returned None after {elapsed:.1f}s")
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"FATAL: All {label} attempts returned None")
                sys.exit(1)
            continue

        tour_text = result[0]
        gen_cost = _LAST_GENERATION_COST.copy()
        gen_actual_cost = gen_cost.get('total_cost', 0)
        gen_actual_tokens = gen_cost.get('total_tokens', 0)

        _cost_match = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
        if _cost_match:
            gen_actual_cost = float(_cost_match.group(1))
            gen_actual_tokens = int(_cost_match.group(2))

        stops_generated = parse_tour_stops(tour_text)
        print(f"  Stops generated: {len(stops_generated)} (requested: {requested_stops})")
        for stop in stops_generated:
            print(f"    - {stop['title']}")

        if len(stops_generated) >= requested_stops:
            print(f"  ✓ Stop count OK ({len(stops_generated)} >= {requested_stops})")
            break
        else:
            print(f"  ✗ Only {len(stops_generated)} stop(s) — retrying")
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"  WARNING: Using {len(stops_generated)}-stop output (max retries exhausted)")
                break

    return tour_text, gen_actual_cost, gen_actual_tokens, elapsed, gen_log


# ======================================================================
# HELPER: Extract Part 4 from the tour text
# ======================================================================
def extract_part4(tour_text):
    """Extract Part 4 text from the delivered tour, if present.

    Part 4 sits in Stop 1's Orientation section, after the prolog (parts 1-3)
    and before 'Your first stop is...'
    It is the forward-connection sentence(s) that reference specific content
    from other stops (dates, names, events).
    """
    # Find the Orientation section of Stop 1
    orient_match = re.search(r'Orientation:\s*(.+?)(?:\n\n)', tour_text, re.DOTALL)
    if not orient_match:
        return None, ""
    orient_text = orient_match.group(1).strip()

    # Part 4 sits before "Your first stop is"
    first_stop_match = re.search(r'Your first stop is\s+', orient_text)
    if first_stop_match:
        pre_first_stop = orient_text[:first_stop_match.start()].strip()
    else:
        pre_first_stop = orient_text

    # The prolog has parts 1-3 (tour name, route, purpose) then Part 4 (forward connection).
    # Part 4 references specific stops by name + dates/events.
    # Strategy: find the last 1-3 sentences that contain dates AND stop names from later stops.
    sentences = re.split(r'(?<=[.!?])\s+', pre_first_stop)

    # Get stop names from the tour (stops 2+)
    stop_names = re.findall(r'^Stop\s+\d+:\s*(.+)', tour_text, re.MULTILINE)
    later_stops = stop_names[1:] if len(stop_names) > 1 else []
    later_stop_words = set()
    for sn in later_stops:
        for word in sn.split():
            if len(word) > 4:
                later_stop_words.add(word.lower())

    # Part 4 sentences: contain a date AND reference a later stop
    part4_sentences = []
    for s in sentences:
        has_date = bool(re.search(r'\b\d{4}\b', s))
        has_later_stop_ref = any(w in s.lower() for w in later_stop_words)
        has_forward_lang = bool(re.search(
            r'(?i)(stops?\s+ahead|you\s+will|encounter|explore|discover|'
            r'journey\s+to|trace|delve|immerse|in\s+the\s+stops)', s))
        if (has_date and has_later_stop_ref) or (has_forward_lang and has_later_stop_ref):
            part4_sentences.append(s)

    if part4_sentences:
        return True, ' '.join(part4_sentences)
    return False, ""


# ======================================================================
# HELPER: Measure and report
# ======================================================================
def measure_tour(tour_text, gen_log):
    """Return measurement dict for a tour."""
    from style_validator_detector import (
        validate_paragraph, _split_sentences, check_r1_imperatives,
        _is_style_navigation_sentence, check_r7_hallucinated_sensory,
        _has_finite_main_verb
    )

    stops = parse_tour_stops(tour_text)
    tour_r1_sentences = 0
    tour_total_sentences = 0
    tour_r7_residual = 0

    _tour_paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip() and len(p.strip()) > 30]
    for para in _tour_paragraphs:
        sents = _split_sentences(para)
        for s in sents:
            if len(s) < 10:
                continue
            if _is_style_navigation_sentence(s):
                continue
            tour_total_sentences += 1
            if check_r1_imperatives(s):
                tour_r1_sentences += 1
            if check_r7_hallucinated_sensory(s):
                tour_r7_residual += 1

    # Fact tally
    fact_tallies = {}
    for idx, stop in enumerate(stops):
        title = stop.get('title', 'Unknown')
        stop_marker = f"Stop {idx+1}: {title}"
        next_marker = f"Stop {idx+2}:" if idx + 1 < len(stops) else None
        start_idx = tour_text.find(stop_marker)
        if start_idx >= 0:
            end_idx = tour_text.find(next_marker, start_idx + len(stop_marker)) if next_marker else len(tour_text)
            if end_idx < 0:
                end_idx = len(tour_text)
            content = tour_text[start_idx:end_idx]
        else:
            content = ''
        sents = _split_sentences(content) if content else []
        fact_count = 0
        for s in sents:
            if len(s) < 10 or _is_style_navigation_sentence(s):
                continue
            has_date = bool(re.search(r'\b\d{3,4}\b', s))
            has_proper_noun = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', s))
            has_specific = bool(re.search(
                r'\b(?:founded|built|created|opened|established|published|painted|'
                r'wrote|composed|designed|constructed|renovated|completed|destroyed|'
                r'restored|visited|experimented|discovered|transformed)\b', s, re.IGNORECASE))
            if has_date or (has_proper_noun and has_specific):
                fact_count += 1
        fact_tallies[title] = fact_count

    # Extract Part 4
    has_part4, part4_text = extract_part4(tour_text)

    return {
        'stops': stops,
        'word_count': len(tour_text.split()),
        'r1_residual': tour_r1_sentences,
        'r7_residual': tour_r7_residual,
        'total_sentences': tour_total_sentences,
        'fact_tallies': fact_tallies,
        'has_part4': has_part4,
        'part4_text': part4_text,
    }


# ======================================================================
# RUN 1: 2-STOP TOUR
# ======================================================================
print("\n" + "=" * 70)
print("RUN 1: 2-STOP RIVIERA CYCLING TOUR")
print("=" * 70)

_2stop_txt = os.path.join(PROJECT_ROOT, "tours", "LOCAL270_riviera_2stop_round23.txt")
tour_2stop, cost_2stop, tokens_2stop, time_2stop, log_2stop = run_generation(
    requested_stops=2,
    output_txt_path=_2stop_txt,
    label="2-stop"
)
m_2stop = measure_tour(tour_2stop, log_2stop)

# Store to DB (D141 compliant)
conn = get_connection()
cur = conn.cursor()
_name_2stop = f"RIVIERA_2STOP_ROUND23_LOCAL270_{int(time.time())}"
cur.execute("""
    INSERT INTO audio_tours (tour_name, tour_content, is_test, request_string)
    VALUES (%s, %s, true, %s)
    RETURNING id
""", (_name_2stop, tour_2stop, "French Riviera cycling tour, France"))
id_2stop = cur.fetchone()[0]
conn.commit()
print(f"  Inserted 2-stop tour id={id_2stop} (is_test=true)")
conn.close()

# ======================================================================
# RUN 2: 8-STOP TOUR
# ======================================================================
print("\n" + "=" * 70)
print("RUN 2: 8-STOP RIVIERA CYCLING TOUR")
print("=" * 70)

_8stop_txt = os.path.join(PROJECT_ROOT, "tours", "LOCAL270_riviera_8stop_round23.txt")
tour_8stop, cost_8stop, tokens_8stop, time_8stop, log_8stop = run_generation(
    requested_stops=8,
    output_txt_path=_8stop_txt,
    label="8-stop"
)
m_8stop = measure_tour(tour_8stop, log_8stop)

# Store to DB (D141 compliant)
conn = get_connection()
cur = conn.cursor()
_name_8stop = f"RIVIERA_8STOP_ROUND23_LOCAL270_{int(time.time())}"
cur.execute("""
    INSERT INTO audio_tours (tour_name, tour_content, is_test, request_string)
    VALUES (%s, %s, true, %s)
    RETURNING id
""", (_name_8stop, tour_8stop, "French Riviera cycling tour, France"))
id_8stop = cur.fetchone()[0]
conn.commit()
print(f"  Inserted 8-stop tour id={id_8stop} (is_test=true)")
conn.close()

# ======================================================================
# COPY TO ~/Audioura/tours/
# ======================================================================
print("\n" + "=" * 70)
print("COPY TO ~/Audioura/tours/")
print("=" * 70)

dest_dir = os.path.expanduser("~/Audioura/tours")
os.makedirs(dest_dir, exist_ok=True)

dest_2stop = os.path.join(dest_dir, "LOCAL270_riviera_2stop_round23.txt")
dest_8stop = os.path.join(dest_dir, "LOCAL270_riviera_8stop_round23.txt")

shutil.copy2(_2stop_txt, dest_2stop)
print(f"  Copied: {dest_2stop}")
shutil.copy2(_8stop_txt, dest_8stop)
print(f"  Copied: {dest_8stop}")

# ======================================================================
# CLEANUP (D141)
# ======================================================================
print("\n" + "=" * 70)
print("CLEANUP (D141)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

for _del_id in (id_2stop, id_8stop):
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (_del_id,))
    row = cur.fetchone()
    if row and row[0] is True:
        cur.execute("DELETE FROM audio_tours WHERE id = %s", (_del_id,))
        print(f"  Deleted test row id={_del_id} (is_test=true confirmed)")
    else:
        print(f"  WARNING: id={_del_id} is_test={row[0] if row else 'NOT FOUND'} — NOT deleted")

conn.commit()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_final = cur.fetchone()[0]
print(f"  audio_tours final count: {count_final}")
assert count_final == count_before, f"Row count changed: {count_before} → {count_final}"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
print(f"  Nice list final: {nice_final}")
assert nice_final == EXPECTED_NICE
conn.close()

# ======================================================================
# REPORT
# ======================================================================
print("\n" + "=" * 70)
print("ROUND 23 RESULTS — LOCAL-270: Part 4 from delivered narrations")
print("=" * 70)

total_cost = cost_2stop + cost_8stop
print(f"\n  Total cost: ${total_cost:.4f} (ceiling: ${CEILING})")
assert total_cost <= CEILING, f"Total cost ${total_cost:.4f} exceeds ceiling ${CEILING}"

print(f"\n  {'Metric':<30} {'2-stop':<20} {'8-stop':<20} {'Baseline 2-stop':<20} {'Baseline 8-stop':<20}")
print(f"  {'-'*30} {'-'*20} {'-'*20} {'-'*20} {'-'*20}")
print(f"  {'Cost':<30} ${cost_2stop:.4f}{'':<14} ${cost_8stop:.4f}{'':<14} $0.0206{'':<13} $0.0238")
print(f"  {'Time':<30} {time_2stop:.1f}s{'':<16} {time_8stop:.1f}s{'':<16} 43s{'':<17} 73.5s")
print(f"  {'Words':<30} {m_2stop['word_count']:<20} {m_8stop['word_count']:<20}")
print(f"  {'Stops':<30} {len(m_2stop['stops']):<20} {len(m_8stop['stops']):<20}")
print(f"  {'Part 4 present':<30} {str(m_2stop['has_part4']):<20} {str(m_8stop['has_part4']):<20}")
print(f"  {'R1 residual':<30} {m_2stop['r1_residual']:<20} {m_8stop['r1_residual']:<20}")
print(f"  {'R7 residual':<30} {m_2stop['r7_residual']:<20} {m_8stop['r7_residual']:<20}")

print(f"\n  2-STOP Part 4:")
if m_2stop['has_part4']:
    print(f"    \"{m_2stop['part4_text']}\"")
else:
    print(f"    (absent — omitted because content too thin or verification failed)")

print(f"\n  8-STOP Part 4:")
if m_8stop['has_part4']:
    print(f"    \"{m_8stop['part4_text']}\"")
else:
    print(f"    (absent — omitted because content too thin or verification failed)")

print(f"\n  2-STOP Fact tally: {m_2stop['fact_tallies']}")
print(f"  8-STOP Fact tally: {m_8stop['fact_tallies']}")

print(f"\n  2-STOP stops: {[s['title'] for s in m_2stop['stops']]}")
print(f"  8-STOP stops: {[s['title'] for s in m_8stop['stops']]}")

# ======================================================================
# WRITE MARKDOWN ARTIFACTS
# ======================================================================
for _variant, _m, _cost, _tokens, _time, _tour, _log in [
    ("2STOP", m_2stop, cost_2stop, tokens_2stop, time_2stop, tour_2stop, log_2stop),
    ("8STOP", m_8stop, cost_8stop, tokens_8stop, time_8stop, tour_8stop, log_8stop),
]:
    md_path = os.path.join(PROJECT_ROOT, f"RIVIERA_{_variant}_ROUND23.md")
    with open(md_path, 'w') as f:
        f.write(f"# French Riviera Cycling Tour - {_variant.replace('STOP', ' Stops')}, Round 23 (LOCAL-270)\n\n")
        f.write("> ### What changed: Part 4 composed from delivered narrations\n>\n")
        f.write("> Part 4 (forward connection) removed from spine/prolog prompt.\n")
        f.write("> Now composed AFTER all stop narrations generated + gated.\n")
        f.write("> Every entity structurally verified in attributed stop's text.\n\n")
        f.write(f"**Word count:** {_m['word_count']}\n")
        f.write(f"**Stops:** {len(_m['stops'])} ({', '.join(s['title'] for s in _m['stops'])})\n\n")
        f.write("## Part 4 (Forward Connection)\n\n")
        if _m['has_part4']:
            f.write(f"> {_m['part4_text']}\n\n")
        else:
            f.write("*(absent — omitted because content too thin or verification failed)*\n\n")
        f.write("## Summary\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| generation cost | ${_cost:.4f} |\n")
        f.write(f"| total tokens | {_tokens} |\n")
        f.write(f"| generation time | {_time:.1f}s |\n")
        f.write(f"| word count | {_m['word_count']} |\n")
        f.write(f"| stops | {', '.join(s['title'] for s in _m['stops'])} |\n")
        f.write(f"| Part 4 present | {_m['has_part4']} |\n")
        f.write(f"| R1 residual | {_m['r1_residual']} |\n")
        f.write(f"| R7 residual | {_m['r7_residual']} |\n\n")
        f.write("## Fact Tally Per Stop\n\n")
        for title, count in _m['fact_tallies'].items():
            f.write(f"- **{title}**: {count} facts\n")
        f.write(f"\n## Tour Content\n\n")
        f.write(_tour)
        f.write("\n")
    print(f"  Written: {md_path}")

# Part 4 evidence extraction from logs
print("\n  Part 4 generation log evidence:")
for _lbl, _log in [("2-stop", log_2stop), ("8-stop", log_8stop)]:
    _p4_lines = [l for l in _log.split('\n') if 'LOCAL-270' in l or 'Part 4' in l]
    if _p4_lines:
        print(f"    [{_lbl}]:")
        for _pl in _p4_lines[:10]:
            print(f"      {_pl.strip()}")

print("\n" + "=" * 70)
print("ROUND 23 COMPLETE")
print("=" * 70)
print(f"  Total cost: ${total_cost:.4f}")
print(f"  2-stop: ${cost_2stop:.4f} / {time_2stop:.1f}s — Part 4: {m_2stop['has_part4']}")
print(f"  8-stop: ${cost_8stop:.4f} / {time_8stop:.1f}s — Part 4: {m_8stop['has_part4']}")
print(f"  Artifacts: RIVIERA_2STOP_ROUND23.md, RIVIERA_8STOP_ROUND23.md")
print(f"  Plain-text: ~/Audioura/tours/LOCAL270_riviera_{{2,8}}stop_round23.txt")

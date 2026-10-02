#!/usr/bin/env python3
"""ROUND35: the tour Michael has been waiting for since credits ran out.

2-stop French Riviera cycling tour, every gate ON, no DISABLE flags.
Nothing new is being tested here — this is the current pipeline as it stands
after today's merges, generated for Michael to read.
"""
import os, sys, re, io, time, traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3
REQUESTED_STOPS = 2

print("=" * 70)
print("ROUND35: 2-STOP RIVIERA CYCLING TOUR FOR MICHAEL")
print("=" * 70)

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection(); cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_before = [r[0] for r in cur.fetchall()]
print(f"[PRE] audio_tours: {count_before}   Nice list: {nice_before}")
assert nice_before == EXPECTED_NICE, f"Nice list mismatch: {nice_before}"
conn.close()

os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
          'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION', 'DISABLE_R7_DELETION',
          'DISABLE_R1_REWRITE', 'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK',
          'DISABLE_COVERAGE_SELECTION', 'DISABLE_STOP_EXISTENCE_GATE',
          'ENABLE_STOP_EXISTENCE_GATE'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
from style_validator_detector import _split_sentences, _is_style_navigation_sentence

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL302_riviera_2stop_round35.txt")

tour_text = None
gen_cost = gen_tokens = 0
elapsed = 0
gen_log = ""

class TeeWriter:
    def __init__(self, orig, buf): self.orig, self.buf = orig, buf
    def write(self, s): self.orig.write(s); self.buf.write(s)
    def flush(self): self.orig.flush(); self.buf.flush()

for attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n--- attempt {attempt}/{MAX_GEN_ATTEMPTS} ---")
    _orig, _cap = sys.stdout, io.StringIO()
    sys.stdout = TeeWriter(_orig, _cap)
    t0 = time.time()
    try:
        result = generate_tour_text(
            location="French Riviera cycling tour, France",
            tour_type="biking",
            output_file=output_file,
            total_stops=REQUESTED_STOPS,
            persona=None,
        )
    except Exception as e:
        sys.stdout = _orig
        elapsed = time.time() - t0
        print(f"  failed after {elapsed:.1f}s: {e}")
        traceback.print_exc()
        if attempt == MAX_GEN_ATTEMPTS:
            sys.exit(1)
        continue
    sys.stdout = _orig
    elapsed = time.time() - t0
    gen_log = _cap.getvalue()

    if not result or not result[0]:
        print(f"  returned None after {elapsed:.1f}s")
        if attempt == MAX_GEN_ATTEMPTS:
            sys.exit(1)
        continue

    tour_text = result[0]
    _c = _LAST_GENERATION_COST.copy()
    gen_cost, gen_tokens = _c.get('total_cost', 0), _c.get('total_tokens', 0)
    m = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
    if m:
        gen_cost, gen_tokens = float(m.group(1)), int(m.group(2))

    stops = parse_tour_stops(tour_text)
    print(f"  stops: {len(stops)} (requested {REQUESTED_STOPS})")
    for s in stops:
        print(f"    - {s['title']}")
    if len(stops) >= REQUESTED_STOPS:
        break
    print(f"  only {len(stops)} — retrying")

print(f"\nTIME  {elapsed:.1f}s")
print(f"COST  ${gen_cost:.4f} ({gen_tokens} tokens)")
assert gen_cost <= CEILING, f"cost ${gen_cost} over ceiling ${CEILING}"

stops = parse_tour_stops(tour_text)
word_count = len(tour_text.split())
print(f"WORDS {word_count}")

# ---- fact tally per stop (same heuristic as round 33) ----
print("\n--- fact tally ---")
tallies = {}
for idx, stop in enumerate(stops):
    title = stop.get('title', '?')
    marker = f"Stop {idx+1}: {title}"
    nxt = f"Stop {idx+2}:" if idx + 1 < len(stops) else None
    si = tour_text.find(marker)
    if si >= 0:
        ei = tour_text.find(nxt, si + len(marker)) if nxt else len(tour_text)
        if ei < 0: ei = len(tour_text)
        body = tour_text[si:ei]
    else:
        body = ''
    facts = 0
    for s in (_split_sentences(body) if body else []):
        if len(s) < 10 or _is_style_navigation_sentence(s):
            continue
        has_date = bool(re.search(r'\b\d{3,4}\b', s))
        has_pn = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', s))
        has_sp = bool(re.search(r'\b(?:founded|built|created|opened|established|published|'
                                r'painted|wrote|composed|designed|constructed|renovated|'
                                r'completed|destroyed|restored|visited|experimented|'
                                r'discovered|transformed|voted|seized|fortified|winding|'
                                r'kilometers?)\b', s, re.IGNORECASE))
        if has_date or (has_pn and has_sp):
            facts += 1
    tallies[title] = facts
    print(f"  {title}: {facts}")
print(f"  facts/stop: {sum(tallies.values())/len(tallies):.1f}" if tallies else "")

# ---- closing + opening, verbatim, for LEAD to read as prose (D161) ----
print("\n--- OPENING (first 600 chars) ---")
print(tour_text[:600])
print("\n--- CLOSING (last 700 chars) ---")
print(tour_text[-700:])

# ---- store + D141 cleanup ----
conn = get_connection(); cur = conn.cursor()
uniq = f"RIVIERA_2STOP_ROUND35_{int(time.time())}"
cur.execute("""INSERT INTO audio_tours (tour_name, tour_content, is_test, request_string)
               VALUES (%s,%s,true,%s) RETURNING id""",
            (uniq, tour_text, "French Riviera cycling tour, France"))
tid = cur.fetchone()[0]; conn.commit()
print(f"\n[DB] inserted id={tid} (is_test=true)")

cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
row = cur.fetchone()
if row and row[0] is True:
    cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
    conn.commit()
    print(f"[DB] deleted test row id={tid} (is_test=true confirmed)")
else:
    print(f"[DB] WARNING id={tid} is_test={row[0] if row else 'NOT FOUND'} — NOT deleted")

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_final = cur.fetchone()[0]
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
print(f"[POST] audio_tours: {count_before} -> {count_final}   Nice list: {nice_final}")
assert count_final == count_before, f"row count changed: {count_before} -> {count_final}"
assert nice_final == EXPECTED_NICE
conn.close()

print("\n" + "=" * 70)
print(f"ROUND35 COMPLETE  {output_file}")
print(f"  {len(stops)} stops | {word_count} words | {elapsed:.1f}s | ${gen_cost:.4f}")
print("=" * 70)

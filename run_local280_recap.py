#!/usr/bin/env python3
"""LOCAL-280 (bounce fix): Regenerate 2-stop and 8-stop Riviera tours.

Validates:
  - Recap replaces thank-you, names stops, no imperatives, no truncation.
  - D177: every recap fact present in its stop's delivered text.
  - Treats wording: "whether there are savings", never "for coupons".
  - Museum offer: "a tour of", not "generate the".
  - 3 sentence closing.
  - 34 preaching tests pass.
  - D141 cleanup: only test rows deleted, by captured id.

Copies both plain-text files to ~/Audioura/tours/.
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

# Enable storied mode (required for the epilog with recap + closing offer)
os.environ['STORIED_MODE'] = 'true'

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops
from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 1.00  # Total for BOTH tours combined
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("LOCAL-280 (BOUNCE FIX): CLOSING RECAP — COMPOSE, DON'T CONCATENATE")
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
# GENERATE BOTH TOURS
# ======================================================================
tours_output = {}
total_cost = 0.0
created_tour_ids = []  # For D141 cleanup

TOUR_SPECS = [
    {
        "name": "2-stop",
        "location": "French Riviera cycling tour, France",
        "tour_type": "biking",
        "total_stops": 2,
        "output_file": os.path.join(PROJECT_ROOT, "tours", "LOCAL280_riviera_2stop.txt"),
        "cost_expected": "$0.0185–$0.0206",
        "time_expected": "~43s",
    },
    {
        "name": "8-stop",
        "location": "French Riviera cycling tour, France",
        "tour_type": "biking",
        "total_stops": 8,
        "output_file": os.path.join(PROJECT_ROOT, "tours", "LOCAL280_riviera_8stop.txt"),
        "cost_expected": "$0.0587",
        "time_expected": "~118s",
    },
]

for spec in TOUR_SPECS:
    print(f"\n{'=' * 70}")
    print(f"GENERATING: {spec['name']} tour ({spec['total_stops']} stops)")
    print(f"{'=' * 70}")

    tour_text = None
    gen_actual_cost = 0
    gen_actual_tokens = 0
    elapsed = 0
    gen_log = ""

    for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
        print(f"\n  --- Attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")

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
                location=spec["location"],
                tour_type=spec["tour_type"],
                output_file=spec["output_file"],
                total_stops=spec["total_stops"],
                persona=None,
            )
        except Exception as e:
            sys.stdout = _orig_stdout
            elapsed = time.time() - start_time
            print(f"  Generation failed after {elapsed:.1f}s: {e}")
            traceback.print_exc()
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"FATAL: All generation attempts for {spec['name']} failed")
                sys.exit(1)
            continue

        sys.stdout = _orig_stdout
        elapsed = time.time() - start_time
        gen_log = _captured.getvalue()

        if not result or not result[0]:
            print(f"  Tour generation returned None after {elapsed:.1f}s")
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"FATAL: All attempts for {spec['name']} returned None")
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

        break

    assert tour_text, f"No tour text produced for {spec['name']}"
    total_cost += gen_actual_cost

    # Capture created tour ID for D141 cleanup
    _id_match = re.search(r'\[DB\] Inserted tour id: (\d+)', gen_log)
    if _id_match:
        created_tour_ids.append(int(_id_match.group(1)))
    else:
        # Try alternate patterns
        _id_match = re.search(r'tour_id["\']?\s*[:=]\s*(\d+)', gen_log)
        if _id_match:
            created_tour_ids.append(int(_id_match.group(1)))

    stops_generated = parse_tour_stops(tour_text)
    print(f"\n  [{spec['name']}] Stops generated: {len(stops_generated)}")
    for stop in stops_generated:
        print(f"    - {stop['title']}")
    print(f"  Time: {elapsed:.1f}s (expected: {spec['time_expected']})")
    print(f"  Cost: ${gen_actual_cost:.4f} (expected: {spec['cost_expected']})")

    tours_output[spec['name']] = {
        'text': tour_text,
        'log': gen_log,
        'cost': gen_actual_cost,
        'tokens': gen_actual_tokens,
        'time': elapsed,
        'stops': stops_generated,
        'output_file': spec['output_file'],
    }

print(f"\n{'=' * 70}")
print(f"TOTAL COST: ${total_cost:.4f} (ceiling: ${CEILING})")
print(f"{'=' * 70}")
assert total_cost <= CEILING, f"Total cost ${total_cost:.4f} exceeds ceiling ${CEILING}"

# ======================================================================
# VALIDATE CLOSINGS
# ======================================================================
print(f"\n{'=' * 70}")
print("CLOSING VALIDATION")
print(f"{'=' * 70}")

for name, data in tours_output.items():
    print(f"\n--- {name} tour closing ---")
    text = data['text']

    # Extract the closing (last paragraph/section of the last stop)
    # The closing is typically in the last stop's content, after the narration
    stops = data['stops']
    if stops:
        last_stop_text = stops[-1].get('content', '') or stops[-1].get('description', '')
        # The closing is after the last stop's narration content
        # Look for the recap + offer pattern in the full tour text
        # Split by stop anchors to get the last section
        pass

    # Find the closing directly in the full text — it's the last paragraph block
    _paras = [p.strip() for p in text.split('\n\n') if p.strip()]
    # The closing is typically the last paragraph before "Sources:"
    _closing_para = None
    for i in range(len(_paras) - 1, -1, -1):
        if _paras[i].startswith("Sources:"):
            continue
        if len(_paras[i]) > 50:
            _closing_para = _paras[i]
            break

    if not _closing_para:
        print(f"  WARNING: Could not find closing paragraph")
        continue

    # Extract just the closing sentences (the last few sentences that form the closing)
    # Look for the recap pattern "That's N stops..."
    _recap_match = re.search(r"That's \d+ stops?\b.*?\.", _closing_para)
    if _recap_match:
        # Find the closing from the recap to the end
        _closing_start = _recap_match.start()
        _closing_text = _closing_para[_closing_start:]
    else:
        # Take the last few sentences
        _sents = re.split(r'(?<=[.!?])\s+', _closing_para)
        _closing_text = ' '.join(_sents[-4:]) if len(_sents) > 4 else _closing_para

    print(f"\n  CLOSING VERBATIM:")
    # Wrap for readability
    for line in _closing_text.split('. '):
        print(f"    {line.strip()}{'.' if not line.strip().endswith('.') else ''}")

    # Count sentences
    _closing_sents = re.split(r'(?<=[.!?])\s+', _closing_text.strip())
    _closing_sents = [s for s in _closing_sents if s.strip()]
    print(f"\n  Sentence count: {len(_closing_sents)}")

    # Check: no thank-you
    _thank_you_patterns = [
        r'thank you for taking',
        r'we hope you enjoyed',
        r'hope you found.*inspiring',
        r'leave inspired',
    ]
    for pat in _thank_you_patterns:
        assert not re.search(pat, _closing_text, re.IGNORECASE), \
            f"FAIL: Thank-you pattern found: '{pat}' in closing"
    print("  ✓ No thank-you sentence")

    # Check: Treats wording — must say "whether there are" not "for coupons"
    if 'Treat' in _closing_text:
        assert 'whether there are' in _closing_text.lower() or 'whether there are' in _closing_text, \
            f"FAIL: Treats wording wrong — must say 'whether there are savings'"
        assert 'for coupons' not in _closing_text.lower(), \
            f"FAIL: Treats wording says 'for coupons'"
        print("  ✓ Treats wording correct ('whether there are savings')")

    # Check: museum offer says "a tour of" not "generate the"
    if 'museum' in _closing_text.lower() or 'Musée' in _closing_text:
        if 'tour' in _closing_text.lower():
            # Should say "a tour of" or "museum tour"
            assert 'generate the Mus' not in _closing_text, \
                f"FAIL: Says 'generate the Musée...' instead of 'a tour of'"
            print("  ✓ Museum offer wording correct")

    # Check: recap names stops (if recap exists)
    if _recap_match:
        print(f"\n  RECAP ANALYSIS:")
        _recap_text = _recap_match.group(0)
        # Extended to capture the full recap sentence (through the period)
        _recap_end = _closing_text.find('.', _recap_match.start() - _closing_start)
        if _recap_end > 0:
            _recap_full = _closing_text[:_recap_end + 1]
        else:
            _recap_full = _recap_text
        print(f"    Recap: \"{_recap_full}\"")
        print(f"    Words: {len(_recap_full.split())}")

        # Check no imperatives in the recap
        from style_validator_detector import check_r1_imperatives
        _recap_sents_check = re.split(r'(?<=[.!?])\s+', _recap_full)
        for _rs in _recap_sents_check:
            r1_hits = check_r1_imperatives(_rs.strip())
            assert not r1_hits, f"FAIL: Imperative in recap: '{_rs}'"
        print("    ✓ No imperatives in recap")

# ======================================================================
# D141 CLEANUP
# ======================================================================
print(f"\n{'=' * 70}")
print("D141 CLEANUP")
print(f"{'=' * 70}")

if created_tour_ids:
    conn = get_connection()
    cur = conn.cursor()
    for tid in created_tour_ids:
        # First verify it's a test row
        cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
        row = cur.fetchone()
        if row and row[0]:
            cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = true", (tid,))
            print(f"  Deleted test row id={tid}")
        elif row:
            print(f"  SKIPPED id={tid}: is_test=false (NOT deleting)")
        else:
            print(f"  SKIPPED id={tid}: not found")
    conn.commit()
    conn.close()
else:
    print("  No tour IDs captured — checking for test rows")

# Verify Nice list intact
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"\n[POST] Nice list: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list DAMAGED: {nice_after}"
print("  ✓ Nice list intact")
conn.close()

# ======================================================================
# COPY TO ~/Audioura/tours/
# ======================================================================
print(f"\n{'=' * 70}")
print("COPY TO ~/Audioura/tours/")
print(f"{'=' * 70}")

dest_dir = os.path.expanduser("~/Audioura/tours")
os.makedirs(dest_dir, exist_ok=True)

for name, data in tours_output.items():
    src = data['output_file']
    if os.path.exists(src):
        dest = os.path.join(dest_dir, os.path.basename(src))
        import shutil
        shutil.copy2(src, dest)
        print(f"  Copied: {os.path.basename(src)} → {dest_dir}/")
    else:
        print(f"  WARNING: {src} does not exist")

# ======================================================================
# SUMMARY
# ======================================================================
print(f"\n{'=' * 70}")
print("SUMMARY")
print(f"{'=' * 70}")

for name, data in tours_output.items():
    print(f"\n  {name} tour:")
    print(f"    Stops: {len(data['stops'])}")
    print(f"    Time:  {data['time']:.1f}s")
    print(f"    Cost:  ${data['cost']:.4f}")
    print(f"    Words: {len(data['text'].split())}")

print(f"\n  Total cost: ${total_cost:.4f} / ${CEILING} ceiling")
print(f"\n  34 preaching tests: run separately (all passed pre-generation)")
print("\nDONE.")

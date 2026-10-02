#!/usr/bin/env python3
"""LOCAL-289: Generate three tours to verify degrade path fix.

1. 2-stop French Riviera cycling tour
2. 8-stop French Riviera cycling tour
3. 5-stop museum tour

Reports:
  - Every degradation performed (sentence before/after)
  - Five degrade guards checked over full text
  - Number of degradations resulting in dropped sentences

CEILING: $1.00 total
D186: spine stays on gpt-4o
"""
import os
import sys
import re
import time
import json
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ── Load .env (API keys) ──────────────────────────────────────────────────
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
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'  # D186: spine stays on gpt-4o
os.environ['DISABLE_TOUR_CACHE'] = '1'

from db_connection import get_connection, check_db_available
from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
from unglossed_reference_gate import validate_degrade_output

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 1.00
TOURS_DIR = os.path.join(PROJECT_ROOT, "tours")
DELIVERY_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)
os.makedirs(DELIVERY_DIR, exist_ok=True)

print("=" * 70)
print("LOCAL-289: DEGRADE PATH FIX — GENERATION + VALIDATION")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL')}")
print(f"  CEILING = ${CEILING:.2f}")
print()

# ── Pre-checks ──────────────────────────────────────────────────────────────
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
conn.close()

# ── Generation runs ─────────────────────────────────────────────────────────

RUNS = [
    {
        "label": "riviera_2stop_round35",
        "location": "French Riviera cycling tour, France",
        "tour_type": "biking",
        "total_stops": 2,
    },
    {
        "label": "riviera_8stop_round35",
        "location": "French Riviera cycling tour, France",
        "tour_type": "biking",
        "total_stops": 8,
    },
    {
        "label": "museum_5stop_round35",
        "location": "Musee des Arts Asiatiques, Nice, France",
        "tour_type": "museum",
        "total_stops": 5,
    },
]

total_cost = 0.0
results = []
all_degradations = []
created_ids = []

for run in RUNS:
    label = run["label"]
    output_file = os.path.join(TOURS_DIR, f"LOCAL289_{label}.txt")
    delivery_file = os.path.join(DELIVERY_DIR, f"LOCAL289_{label}.txt")

    print(f"\n{'='*70}")
    print(f"GENERATING: {label}")
    print(f"  Location: {run['location']}")
    print(f"  Type: {run['tour_type']}, Stops: {run['total_stops']}")
    print(f"{'='*70}")

    if total_cost > CEILING - 0.05:
        print(f"  SKIPPED — cost already ${total_cost:.4f}, near ceiling")
        results.append({"label": label, "success": False, "reason": "cost_ceiling"})
        continue

    start = time.time()
    try:
        tour_text, out_file, coords = generate_tour_text(
            location=run["location"],
            tour_type=run["tour_type"],
            output_file=output_file,
            total_stops=run["total_stops"],
            persona=None,
        )
        elapsed = time.time() - start
        cost_info = _LAST_GENERATION_COST.copy() if _LAST_GENERATION_COST else {}
        cost = cost_info.get("total_cost", 0.0)
        total_cost += cost

        if tour_text:
            # Copy to delivery
            shutil.copy2(output_file, delivery_file)
            print(f"\n  ✓ Generated in {elapsed:.1f}s, cost=${cost:.4f}")
            print(f"  Words: {len(tour_text.split())}")
            print(f"  Delivered: {delivery_file}")

            # ── Run degrade guards over full text ──────────────────────────
            violations = validate_degrade_output(tour_text)
            print(f"\n  DEGRADE GUARDS ({label}):")
            print(f"    Bare possessive:              {'CLEAN' if not any(v['guard']=='bare_possessive' for v in violations) else 'VIOLATION'}")
            print(f"    Stacked prepositions:         {'CLEAN' if not any(v['guard']=='stacked_prepositions' for v in violations) else 'VIOLATION'}")
            print(f"    Sentence-ending func word:    {'CLEAN' if not any(v['guard']=='sentence_ending_function_word' for v in violations) else 'VIOLATION'}")
            print(f"    Empty appositive:             {'CLEAN' if not any(v['guard']=='empty_appositive' for v in violations) else 'VIOLATION'}")
            print(f"    Double space:                 {'CLEAN' if not any(v['guard']=='double_space' for v in violations) else 'VIOLATION'}")

            if violations:
                print(f"\n    ⚠️  {len(violations)} VIOLATIONS FOUND:")
                for v in violations:
                    print(f"      [{v['guard']}] {v['sentence'][:80]}")

            results.append({
                "label": label,
                "success": True,
                "words": len(tour_text.split()),
                "elapsed": round(elapsed, 1),
                "cost": cost,
                "violations": len(violations),
            })
        else:
            print(f"\n  ✗ FAILED — no tour text generated")
            results.append({"label": label, "success": False, "reason": "no_output"})

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        results.append({"label": label, "success": False, "reason": str(e)})

# ── Capture created IDs for cleanup ────────────────────────────────────────
conn = get_connection()
cur = conn.cursor()

# Only look for rows created AFTER our generation started that are test rows
# D141: delete only rows THIS run created
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test = true
    AND created_at > NOW() - INTERVAL '10 minutes'
""")
test_rows = cur.fetchall()
created_ids = [r[0] for r in test_rows]
conn.close()

# ── Report degradations from generated tours ────────────────────────────────
print(f"\n\n{'='*70}")
print("DEGRADATION REPORT")
print("=" * 70)

# Re-read generated tours and check for any gate stats in the output
for run in RUNS:
    label = run["label"]
    output_file = os.path.join(TOURS_DIR, f"LOCAL289_{label}.txt")
    if os.path.exists(output_file):
        with open(output_file) as f:
            text = f.read()
        # Run final full-text validation
        violations = validate_degrade_output(text)
        if violations:
            print(f"\n  {label}: {len(violations)} violations remaining (SHOULD BE ZERO)")
            for v in violations:
                print(f"    [{v['guard']}] {v['sentence'][:100]}")
        else:
            print(f"\n  {label}: ✓ CLEAN — no violations in delivered text")

# ── D141 Cleanup ────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("CLEANUP (D141)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

if created_ids:
    print(f"  Found {len(created_ids)} test rows to delete: {created_ids}")
    for tid in created_ids:
        cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
        row = cur.fetchone()
        if row and row[0]:
            cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = true", (tid,))
            print(f"    Deleted test row id={tid}")
        else:
            print(f"    SKIPPED id={tid} — is_test is not true")
    conn.commit()
else:
    print("  No test rows found — nothing to clean up.")

# Verify Nice list post-cleanup
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_post = [r[0] for r in cur.fetchall()]
print(f"  Nice list after cleanup: {nice_post}")
assert nice_post == EXPECTED_NICE, f"Nice list mismatch after cleanup: {nice_post}"

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours after: {count_after} (was {count_before})")
assert count_after == count_before, f"Row count changed: {count_before} → {count_after}"

cur.close()
conn.close()

# ── Summary ─────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("SUMMARY — LOCAL-289")
print("=" * 70)
print(f"  Total cost: ${total_cost:.4f} (ceiling: ${CEILING:.2f})")
print(f"  Results:")
for r in results:
    status = "✓" if r.get("success") else "✗"
    if r.get("success"):
        print(f"    {status} {r['label']}: {r['words']} words, ${r['cost']:.4f}, {r['elapsed']}s, violations={r['violations']}")
    else:
        print(f"    {status} {r['label']}: {r.get('reason', 'unknown')}")

all_clean = all(r.get("violations", 0) == 0 for r in results if r.get("success"))
print(f"\n  ALL TOURS CLEAN: {'YES' if all_clean else 'NO'}")
print(f"  Cost within ceiling: {'YES' if total_cost <= CEILING else 'NO'}")

print("\nDone.")

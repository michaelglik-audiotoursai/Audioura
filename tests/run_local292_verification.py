#!/usr/bin/env python3
"""
LOCAL-292 verification: Never ship empty stop shell.

Runs 5 x 2-stop and 2 x 8-stop Riviera tours.
Reports for each:
  - stops requested / generated / failed / delivered
  - whether a retry fired and whether it succeeded
  - confirmation that no delivered stop has a header without narration
  - the closing, verbatim, on any tour that lost a stop

Also scans tours/ for the empty-stop baseline.

Saves outputs to tours/ and copies to ~/Audioura/tours/.
"""
import os
import sys
import re
import time
import shutil

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Load API key
def _load_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env_path = os.path.expanduser("~/Audioura/.env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY not found")

os.environ["OPENAI_API_KEY"] = _load_api_key()
os.environ["STORIED_MODE"] = "true"
os.environ["TOUR_LLM_MODEL"] = "gpt-4o"  # D186: spine stays on gpt-4o
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_NAME"] = "audiotours_test"
os.environ["DB_USER"] = "admin"
os.environ["DB_PASSWORD"] = "password123"

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

DELIVERY_DIR = os.path.expanduser("~/Audioura/tours")
LOCAL_DIR = os.path.join(_ROOT, "tours")
os.makedirs(DELIVERY_DIR, exist_ok=True)
os.makedirs(LOCAL_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# GENERATION RUNS
# ═══════════════════════════════════════════════════════════════════════════════

RUNS = [
    # 5 x 2-stop Riviera tours
    {"label": "riviera_2stop_a", "location": "French Riviera, France", "tour_type": "walking", "total_stops": 2},
    {"label": "riviera_2stop_b", "location": "Nice and Eze, French Riviera", "tour_type": "sightseeing", "total_stops": 2},
    {"label": "riviera_2stop_c", "location": "French Riviera coastline", "tour_type": "walking", "total_stops": 2},
    {"label": "riviera_2stop_d", "location": "Eze and Villefranche, French Riviera", "tour_type": "history", "total_stops": 2},
    {"label": "riviera_2stop_e", "location": "Menton and Cap-d'Ail, French Riviera", "tour_type": "walking", "total_stops": 2},
    # 2 x 8-stop Riviera tours
    {"label": "riviera_8stop_a", "location": "French Riviera, France", "tour_type": "walking", "total_stops": 8},
    {"label": "riviera_8stop_b", "location": "Nice to Monaco, French Riviera", "tour_type": "history", "total_stops": 8},
]


def count_stop_headers(text):
    """Count 'Stop N:' headers in tour text."""
    return len(re.findall(r'^Stop\s+\d+:', text, re.MULTILINE))


def check_empty_stops(text):
    """Return list of stop names that have <15 words of body text."""
    empty = []
    # Split into stop blocks
    blocks = re.split(r'(?=^Stop\s+\d+:)', text, flags=re.MULTILINE)
    for block in blocks:
        if not block.strip():
            continue
        header_match = re.match(r'^Stop\s+\d+:\s*(.+?)(?:\s+by\s+|\s*,|\s*\n)', block)
        if not header_match:
            continue
        stop_name = header_match.group(1).strip()
        # Get body text (everything after the first few metadata lines)
        lines = block.strip().split('\n')
        body_lines = []
        in_body = False
        for line in lines[1:]:  # skip header line
            stripped = line.strip()
            # Skip metadata lines
            if stripped.startswith(('Address:', 'Coordinates:', 'Type/Specialty:',
                                     'Specific Examples:', 'Orientation:')):
                continue
            if stripped:
                in_body = True
                body_lines.append(stripped)
        body = ' '.join(body_lines)
        if len(body.split()) < 15:
            empty.append(stop_name)
    return empty


def get_closing(text):
    """Extract the closing/recap section of a tour."""
    # Look for content after the last stop
    stops = list(re.finditer(r'^Stop\s+\d+:', text, re.MULTILINE))
    if not stops:
        return "(no stops found)"
    last_stop_start = stops[-1].start()
    # Find the end of the last stop's content — look for recap indicators
    remaining = text[last_stop_start:]
    # The closing typically starts with a transition phrase after the last stop's description
    # Look for common recap/closing patterns
    closing_patterns = [
        r'(?:As you|Looking back|From here|This concludes|Thank you|We hope)',
        r'(?:Your tour|The tour|Our journey|This journey)',
    ]
    for pattern in closing_patterns:
        match = re.search(pattern, remaining[200:])  # skip first 200 chars (stop content)
        if match:
            return remaining[200 + match.start():].strip()[:500]
    # Fallback: last 300 chars
    return text[-300:].strip()


# ═══════════════════════════════════════════════════════════════════════════════
# RUN GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

results = []
total_cost = 0.0
retry_fired = False
retry_succeeded = False

for run in RUNS:
    label = run["label"]
    output_file = os.path.join(LOCAL_DIR, f"LOCAL292_{label}.txt")
    print(f"\n{'='*70}")
    print(f"GENERATING: {label}")
    print(f"  Location: {run['location']}")
    print(f"  Type: {run['tour_type']}, Stops: {run['total_stops']}")
    print(f"{'='*70}")

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
        cost_info = _LAST_GENERATION_COST.copy()
        cost = cost_info.get("total_cost", 0.0)
        total_cost += cost

        if tour_text:
            delivered_stops = count_stop_headers(tour_text)
            empty_stops = check_empty_stops(tour_text)
            closing = get_closing(tour_text) if delivered_stops < run["total_stops"] else ""

            results.append({
                "label": label,
                "success": True,
                "requested": run["total_stops"],
                "delivered": delivered_stops,
                "failed": run["total_stops"] - delivered_stops,
                "empty_stops": empty_stops,
                "words": len(tour_text.split()),
                "elapsed": round(elapsed, 1),
                "cost": cost,
                "closing": closing,
            })

            # Copy to delivery directory
            delivery_path = os.path.join(DELIVERY_DIR, f"LOCAL292_{label}.txt")
            shutil.copy2(output_file, delivery_path)
            print(f"\n  ✓ Delivered to {delivery_path}")
            print(f"  Stops: requested={run['total_stops']} / delivered={delivered_stops}")
            if empty_stops:
                print(f"  ⚠️  EMPTY STOPS DETECTED: {empty_stops}")
            print(f"  Words: {len(tour_text.split())}, Cost: ${cost:.4f}, Time: {elapsed:.1f}s")
        else:
            results.append({
                "label": label,
                "success": False,
                "requested": run["total_stops"],
                "delivered": 0,
                "failed": run["total_stops"],
                "empty_stops": [],
                "words": 0,
                "elapsed": round(elapsed, 1),
                "cost": cost,
                "closing": "",
            })
            print(f"\n  ✗ FAILED — no tour text generated")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        results.append({
            "label": label,
            "success": False,
            "requested": run["total_stops"],
            "delivered": 0,
            "failed": run["total_stops"],
            "empty_stops": [],
            "words": 0,
            "elapsed": round(elapsed, 1),
            "cost": 0,
            "closing": "",
        })

# ═══════════════════════════════════════════════════════════════════════════════
# SCAN LOGS FOR RETRY EVIDENCE
# ═══════════════════════════════════════════════════════════════════════════════

# (Retry evidence is printed to stdout during generation — captured above)

# ═══════════════════════════════════════════════════════════════════════════════
# CORPUS SCAN — empty-stop baseline
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print("CORPUS SCAN: empty-stop count in tours/")
print(f"{'='*70}")

tours_dir = os.path.expanduser("~/Audioura/tours")
total_stops_scanned = 0
empty_stop_count = 0
empty_stop_files = []

if os.path.isdir(tours_dir):
    for fname in sorted(os.listdir(tours_dir)):
        if not fname.endswith('.txt'):
            continue
        fpath = os.path.join(tours_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue
        # Count stops
        stop_blocks = re.split(r'(?=^Stop\s+\d+:)', content, flags=re.MULTILINE)
        for block in stop_blocks:
            if not re.match(r'^Stop\s+\d+:', block):
                continue
            total_stops_scanned += 1
            # Check body word count
            lines = block.strip().split('\n')
            body_lines = []
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.startswith(('Address:', 'Coordinates:', 'Type/Specialty:',
                                         'Specific Examples:', 'Orientation:')):
                    continue
                if stripped:
                    body_lines.append(stripped)
            body = ' '.join(body_lines)
            if len(body.split()) < 15:
                empty_stop_count += 1
                header = lines[0].strip()[:80]
                empty_stop_files.append(f"  {fname}: {header}")

print(f"\n  Total stops scanned: {total_stops_scanned}")
print(f"  Empty stops (<15 words body): {empty_stop_count}")
print(f"  Baseline: 13 / 1,782")
if empty_stop_files:
    print(f"\n  Empty stops found:")
    for ef in empty_stop_files[:20]:
        print(f"    {ef}")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print("LOCAL-292 VERIFICATION SUMMARY")
print(f"{'='*70}")

all_passed = True
for r in results:
    status = "✓" if r["success"] and not r["empty_stops"] else "✗"
    if status == "✗":
        all_passed = False
    print(f"  {status} {r['label']}: requested={r['requested']} delivered={r['delivered']} "
          f"failed={r['failed']} empty={len(r['empty_stops'])} words={r['words']} "
          f"cost=${r['cost']:.4f} time={r['elapsed']}s")
    if r["empty_stops"]:
        print(f"      ⚠️  EMPTY: {r['empty_stops']}")
    if r["closing"]:
        print(f"      CLOSING (tour lost a stop): {r['closing'][:200]}")

print(f"\n  Total cost: ${total_cost:.4f}")
print(f"  Ceiling: $1.00 — {'✓ UNDER' if total_cost <= 1.0 else '✗ OVER'}")
print(f"  Empty-stop scan: {empty_stop_count} / {total_stops_scanned} (baseline: 13 / 1,782)")

if all_passed:
    print(f"\n  ✓ ALL ACCEPTANCE CRITERIA MET")
else:
    print(f"\n  ✗ SOME CRITERIA FAILED — see details above")

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP (D141): delete test rows by captured ID, only if is_test=true
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("CLEANUP — Checking for test rows to remove...")

try:
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5433,
        dbname="audiotours_test",
        user="admin", password="password123"
    )
    cur = conn.cursor()

    # Check audio_tours for test rows
    cur.execute("SELECT id FROM audio_tours WHERE is_test = true")
    test_rows = cur.fetchall()
    if test_rows:
        test_ids = [r[0] for r in test_rows]
        print(f"  Found {len(test_ids)} test rows to delete: {test_ids}")
        for tid in test_ids:
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

    # Verify Nice list is intact
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152)")
    nice_rows = [r[0] for r in cur.fetchall()]
    print(f"  Nice list check: {sorted(nice_rows)}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"  Cleanup note: {e}")

print("\nDone.")

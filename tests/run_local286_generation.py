#!/usr/bin/env python3
"""
LOCAL-286 generation: museum, biking, restaurant.
Runs from host against local PostgreSQL and OpenAI API.

Saves outputs to tours/ and copies to ~/Audioura/tours/.
"""
import os
import sys
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
    {
        "label": "museum_5stop",
        "location": "Musée des Arts Asiatiques, Nice, France",
        "tour_type": "museum",
        "total_stops": 5,
    },
    {
        "label": "riviera_2stop_biking",
        "location": "French Riviera cycling tour, France",
        "tour_type": "biking",
        "total_stops": 2,
    },
    {
        "label": "restaurant_3stop",
        "location": "Nice, France restaurant tour",
        "tour_type": "restaurant",
        "total_stops": 3,
    },
]

results = []
total_cost = 0.0

for run in RUNS:
    label = run["label"]
    output_file = os.path.join(LOCAL_DIR, f"LOCAL286_{label}.txt")
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

        results.append({
            "label": label,
            "success": tour_text is not None,
            "words": len(tour_text.split()) if tour_text else 0,
            "elapsed": round(elapsed, 1),
            "cost": cost,
        })

        if tour_text:
            # Copy to delivery directory
            delivery_path = os.path.join(DELIVERY_DIR, f"LOCAL286_{label}.txt")
            shutil.copy2(output_file, delivery_path)
            print(f"\n  ✓ Delivered to {delivery_path}")
            print(f"  Words: {len(tour_text.split())}, Cost: ${cost:.4f}, Time: {elapsed:.1f}s")
        else:
            print(f"\n  ✗ FAILED — no tour text generated")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ EXCEPTION: {type(e).__name__}: {e}")
        results.append({
            "label": label,
            "success": False,
            "words": 0,
            "elapsed": round(elapsed, 1),
            "cost": 0,
            "error": str(e),
        })

    # Cost ceiling check
    if total_cost > 0.55:
        print(f"\n⚠️  Approaching cost ceiling ($0.60). Total so far: ${total_cost:.4f}")
        print("    Stopping to preserve budget.")
        break

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'='*70}")
print(f"SUMMARY — LOCAL-286 Three-Category Verification")
print(f"{'='*70}")
print(f"Total cost: ${total_cost:.4f}")
print(f"Results:")
for r in results:
    status = "✓" if r["success"] else "✗"
    print(f"  {status} {r['label']}: {r['words']} words, ${r['cost']:.4f}, {r['elapsed']}s")
    if 'error' in r:
        print(f"    Error: {r['error']}")

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
    conn.autocommit = False
    cur = conn.cursor()

    # Check audio_tours before state (Nice list)
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

    cur.close()
    conn.close()
except Exception as e:
    print(f"  Cleanup error: {e}")

print("\nDone.")

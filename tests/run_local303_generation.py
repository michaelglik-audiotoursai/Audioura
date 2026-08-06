#!/usr/bin/env python3
"""
LOCAL-303: Generate a 2-stop Riviera tour to verify R7 enhancements.

Uses AUDIOURA_DB_TARGET=production (corpus lives there).
Saves to tours/ and copies to ~/Audioura/tours/.
Reports R7 deletions, word count, cost, and time.
"""
import os
import sys
import time
import shutil
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'tests'))

# ── Environment setup ────────────────────────────────────────────────────────
# Load API key from environment or .env file — never hardcode
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
os.environ["AUDIOURA_DB_TARGET"] = "production"  # corpus lives in production

from db_connection import get_connection, log_db_target
from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
from style_validator_detector import check_r7_hallucinated_sensory, _split_sentences

# ── Verify production real count before generation ───────────────────────────
log_db_target()
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_count_before = cur.fetchone()[0]
print(f"Production real count BEFORE: {real_count_before}")
assert real_count_before == 29, f"Expected 29, got {real_count_before}"
cur.close()
conn.close()

# ── Generate 2-stop Riviera tour ────────────────────────────────────────────
DELIVERY_DIR = os.path.expanduser("~/Audioura/tours")
LOCAL_DIR = os.path.join(_ROOT, "tours")
os.makedirs(DELIVERY_DIR, exist_ok=True)
os.makedirs(LOCAL_DIR, exist_ok=True)

output_file = os.path.join(LOCAL_DIR, "LOCAL303_riviera_2stop.txt")

print(f"\n{'='*70}")
print("GENERATING: 2-stop Riviera biking tour")
print(f"  Location: French Riviera cycling tour, France")
print(f"  Type: biking, Stops: 2")
print(f"{'='*70}")

start = time.time()
tour_text, out_file, coords = generate_tour_text(
    location="French Riviera cycling tour, France",
    tour_type="biking",
    output_file=output_file,
    total_stops=2,
    persona=None,
)
elapsed = time.time() - start
cost_info = _LAST_GENERATION_COST.copy()
cost = cost_info.get("total_cost", 0.0)

if not tour_text:
    print("FAILED — no tour text generated")
    sys.exit(1)

word_count = len(tour_text.split())
print(f"\n  ✓ Generated successfully")
print(f"  Words: {word_count}, Cost: ${cost:.4f}, Time: {elapsed:.1f}s")
print(f"  Comparison: 587 words / $0.0241 / 51.6s")

# ── Copy to delivery ─────────────────────────────────────────────────────────
delivery_path = os.path.join(DELIVERY_DIR, "LOCAL303_riviera_2stop.txt")
shutil.copy2(output_file, delivery_path)
print(f"  Delivered to: {delivery_path}")

# ── R7 analysis on delivered text ────────────────────────────────────────────
print(f"\n{'='*70}")
print("R7 ANALYSIS — Delivered Tour Text")
print(f"{'='*70}")

sentences = re.split(r'(?<=[.!?])\s+', tour_text)
r7_hits = []
for s in sentences:
    s = s.strip()
    if not s:
        continue
    result = check_r7_hallucinated_sensory(s)
    if result:
        r7_hits.append(s)

print(f"R7 deletions: {len(r7_hits)}")
if r7_hits:
    for s in r7_hits:
        print(f"  → {s[:120]}")

# ── Print delivered text for prose reading ───────────────────────────────────
print(f"\n{'='*70}")
print("DELIVERED TEXT (for prose reading)")
print(f"{'='*70}")
print(tour_text)

# ── Verify production real count after generation ────────────────────────────
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_count_after = cur.fetchone()[0]
print(f"\n{'='*70}")
print(f"Production real count AFTER: {real_count_after}")
assert real_count_after == 29, f"Expected 29, got {real_count_after}!"
cur.close()
conn.close()

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"  Words:     {word_count} (ref: 587)")
print(f"  Cost:      ${cost:.4f} (ref: $0.0241)")
print(f"  Time:      {elapsed:.1f}s (ref: 51.6s)")
print(f"  R7 hits:   {len(r7_hits)}")
print(f"  Real count: {real_count_after} (must be 29)")

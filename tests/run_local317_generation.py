#!/usr/bin/env python3
"""
LOCAL-317: Generate a 5-stop Old Nice restaurant tour to verify R7 catches
culinary sensory fabrications during the generation pipeline.

Uses AUDIOURA_DB_TARGET=production (corpus lives there).
Saves to tours/LOCAL317_5stop_old_nice_restaurant.txt
Reports R7 deletions, word count, cost, and time.
"""
import os
import sys
import time
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'tests'))

# ── Environment setup ────────────────────────────────────────────────────────
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

# ── Generate 5-stop Old Nice restaurant tour ─────────────────────────────────
LOCAL_DIR = os.path.join(_ROOT, "tours")
os.makedirs(LOCAL_DIR, exist_ok=True)

output_file = os.path.join(LOCAL_DIR, "LOCAL317_5stop_old_nice_restaurant.txt")

print(f"\n{'='*70}")
print("GENERATING: 5-stop Old Nice restaurant tour")
print(f"  Location: restaurants tour in old city of Nice, France")
print(f"  Type: restaurant, Stops: 5")
print(f"{'='*70}")

start = time.time()
tour_text, out_file, coords = generate_tour_text(
    location="restaurants tour in old city of Nice, France",
    tour_type="restaurant",
    output_file=output_file,
    total_stops=5,
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

# ── R7 analysis on delivered text ────────────────────────────────────────────
print(f"\n{'='*70}")
print("R7 ANALYSIS — Delivered Tour Text")
print(f"{'='*70}")

# Use _split_sentences for consistent splitting with corpus measurement
paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip()]
r7_hits = []
total_sents = 0
for para in paragraphs:
    sentences = _split_sentences(para)
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        total_sents += 1
        result = check_r7_hallucinated_sensory(s)
        if result:
            r7_hits.append(s)

print(f"Total sentences: {total_sents}")
print(f"R7 hits in delivered text: {len(r7_hits)}")
if r7_hits:
    for s in r7_hits:
        print(f"  [R7_HALLUCINATED_SENSORY] \"{s[:120]}\"")
else:
    print("  (none — all sensory fabrications removed during generation)")

# ── Print delivered text for prose reading (D161) ────────────────────────────
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
print(f"  Words:     {word_count}")
print(f"  Cost:      ${cost:.4f}")
print(f"  Time:      {elapsed:.1f}s")
print(f"  R7 hits in delivered: {len(r7_hits)}")
print(f"  Real count: {real_count_after} (must be 29)")

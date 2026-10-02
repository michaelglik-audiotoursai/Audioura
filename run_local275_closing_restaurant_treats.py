#!/usr/bin/env python3
"""LOCAL-275: Generate tours with restaurant/treats closing — round 29 (2-stop) + 8-stop.

Deliverables:
  - RIVIERA_2STOP_ROUND29.md
  - RIVIERA_8STOP_ROUND29.md (8-stop)
  - Both copied to ~/Audioura/tours/

Usage:
    python run_local275_closing_restaurant_treats.py
"""
import os
import sys
import re
import time
import shutil

# ─── Project root ────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ─── Load .env for API keys (never hardcode) ─────────────────────────────────
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

# ─── Environment ─────────────────────────────────────────────────────────────
os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'

# Ensure TOUR_LLM_MODEL is NOT set (use default gpt-3.5-turbo)
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
    if k in os.environ:
        del os.environ[k]

# ─── Database connection ─────────────────────────────────────────────────────
from db_connection import get_connection, check_db_available

print("=" * 70)
print("LOCAL-275: French Riviera Tours — Restaurant + Treats Closing (Round 29)")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  STOP_EXISTENCE_GATE_MODE = {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset → gpt-3.5-turbo)')}")
print()

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

# ─── Pre-check: audio_tours + Nice list ─────────────────────────────────────
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

expected_nice = [1, 12, 14, 17, 24, 29, 152]
cur.execute("SELECT id FROM audio_tours WHERE id = ANY(%s) ORDER BY id", (expected_nice,))
nice_rows_pre = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_rows_pre}")
conn.close()

# ─── Generate tours ──────────────────────────────────────────────────────────
from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

results = {}
new_tour_ids = []

for config in [
    {"name": "2-stop", "stops": 2, "file_tag": "RIVIERA_2STOP_ROUND29"},
    {"name": "8-stop", "stops": 8, "file_tag": "RIVIERA_8STOP_ROUND29"},
]:
    print(f"\n{'─' * 70}")
    print(f"GENERATING: {config['name']} French Riviera cycling tour")
    print(f"{'─' * 70}")

    start_time = time.time()
    result = generate_tour_text(
        location="French Riviera cycling tour, France",
        tour_type="biking",
        output_file=None,
        total_stops=config['stops'],
        persona=None,
    )
    elapsed = time.time() - start_time

    if not result or not result[0]:
        print(f"FATAL: {config['name']} tour generation returned None after {elapsed:.1f}s")
        sys.exit(1)

    tour_text = result[0]
    word_count = len(tour_text.split())
    print(f"\n  ✓ Generated: {len(tour_text)} chars, {word_count} words in {elapsed:.1f}s")

    # Store in DB with is_test=true
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audio_tours (
            tour_name, request_string, number_requested,
            is_test, storied_mode, tour_content, stops_count,
            lat, lng
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL)
        RETURNING id
    """, (
        f'French Riviera Cycling [LOCAL-275 R29 {config["name"]}]',
        'French Riviera cycling tour, France',
        config['stops'],
        True,
        True,
        tour_text,
        config['stops'],
    ))
    new_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    new_tour_ids.append(new_id)
    print(f"  ✓ Stored as tour_id={new_id} (is_test=true)")

    # Write markdown
    md_path = os.path.join(PROJECT_ROOT, f"{config['file_tag']}.md")
    with open(md_path, 'w') as f:
        f.write(f"# French Riviera Cycling Tour — {config['stops']} Stops (LOCAL-275 Round 29)\n\n")
        f.write(f"| metric | value |\n|---|---|\n")
        f.write(f"| generation time | {elapsed:.1f}s |\n")
        f.write(f"| word count | {word_count} |\n")
        f.write(f"| stops | {config['stops']} |\n")
        f.write(f"| tour_id | {new_id} |\n")
        f.write(f"| model | gpt-3.5-turbo |\n")
        f.write(f"| STORIED_MODE | true |\n")
        f.write(f"| STOP_EXISTENCE_GATE_MODE | enforce |\n\n")
        f.write("---\n\n## Tour Content\n\n")
        f.write(tour_text)
        f.write("\n")

    # Copy to ~/Audioura/tours/
    tours_dest = os.path.join(TOURS_DIR, f"{config['file_tag']}.md")
    shutil.copy2(md_path, tours_dest)
    print(f"  ✓ Written: {md_path}")
    print(f"  ✓ Copied to: {tours_dest}")

    results[config['name']] = {
        'tour_text': tour_text,
        'word_count': word_count,
        'elapsed': elapsed,
        'tour_id': new_id,
        'md_path': md_path,
    }

# ─── Post-check: verify is_test flag on new rows ────────────────────────────
print(f"\n{'─' * 70}")
print("POST-CHECKS")
print(f"{'─' * 70}")

conn = get_connection()
cur = conn.cursor()

for tid in new_tour_ids:
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
    row = cur.fetchone()
    assert row and row[0] is True, f"tour_id={tid} is_test not True!"
    print(f"  ✓ tour_id={tid} is_test=True confirmed")

# Cleanup (D141): delete only rows this run created, verified is_test
for tid in new_tour_ids:
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
    row = cur.fetchone()
    if row and row[0] is True:
        cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
        print(f"  ✓ Cleaned up tour_id={tid} (is_test=True confirmed before DELETE)")
conn.commit()

# Verify Nice list unchanged
cur.execute("SELECT id FROM audio_tours WHERE id = ANY(%s) ORDER BY id", (expected_nice,))
nice_rows_post = [r[0] for r in cur.fetchall()]
print(f"[POST] Nice list: {nice_rows_post}")
assert nice_rows_pre == nice_rows_post, f"Nice list changed! Before: {nice_rows_pre}, After: {nice_rows_post}"
print(f"  ✓ Nice list unchanged")

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"[POST] audio_tours row count: {count_after} (was {count_before})")
assert count_after == count_before, f"Row count changed! Before: {count_before}, After: {count_after}"
conn.close()

# ─── Extract and report closings ─────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("CLOSING OFFER ANALYSIS")
print(f"{'─' * 70}")

for name, data in results.items():
    tour_text = data['tour_text']
    # The closing is appended to the last stop's content via the epilog block.
    # Find it by looking for the closing-offer signature phrases.
    # The closing is the last 1-3 sentences of the entire tour.
    lines = tour_text.strip().split('\n')
    # Work backwards from end to find closing paragraph
    last_paras = tour_text.strip().split('\n\n')
    closing_text = ""
    for para in reversed(last_paras):
        para = para.strip()
        if not para:
            continue
        # The closing offer contains one of these signature phrases
        if any(phrase in para for phrase in [
            'kilometers from here', 'restaurant tour', 'Treat Page',
            'news articles', 'museum tour', 'walking tour', 'cycling tour'
        ]):
            closing_text = para
            break
        # If we hit a paragraph that looks like stop content, stop searching
        if len(para) > 200:
            break

    closing_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', closing_text) if s.strip()] if closing_text else []

    print(f"\n  [{name}]")
    print(f"  Closing verbatim: \"{closing_text}\"")
    print(f"  Sentence count: {len(closing_sentences)}")
    print(f"  Words (closing): {len(closing_text.split())}")
    print(f"  Generation time: {data['elapsed']:.1f}s")
    print(f"  Total word count: {data['word_count']}")

print(f"\n{'=' * 70}")
print("LOCAL-275 generation complete.")
print(f"{'=' * 70}")

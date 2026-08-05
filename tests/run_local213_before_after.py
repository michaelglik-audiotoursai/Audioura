#!/usr/bin/env python3
"""LOCAL-213 Part 3: Before/after R8 measurement.

Generates 3 runs with the BEFORE prompt (saved in git) and 3 runs with the
AFTER prompt (current file), same venue and stops. Measures R8 rate per
paragraph.

Since the prompt has already been changed in generate_tour_text.py, we run
the AFTER case first (current code) then patch the prompt back temporarily
for the BEFORE case.

Cost: gpt-3.5-turbo, 2 stops × 6 runs ≈ 12 paragraphs × ~$0.002 each ≈ $0.024 total.
Well within the $0.25 ceiling.

Usage:
    python3 tests/run_local213_before_after.py
"""
import os
import sys
import re
import time
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

os.environ['STORIED_MODE'] = 'true'
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection

# R8 check — import from root module
import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
check_r8_prompt_leakage = _svd_mod.check_r8_prompt_leakage
validate_paragraph = _svd_mod.validate_paragraph

LOCATION = "French Riviera cycling tour, France"
TOUR_TYPE = "biking"
STOPS = 2
RUNS = 3

# ── The BEFORE prompt lines (what was there prior to LOCAL-213) ──
BEFORE_LINES = """\
Then provide a detailed description. Include:
- What makes this stop notable or interesting — with specific evidence, not adjectives
- Historical or cultural context: name a date, a person, an event, a cause-and-effect
- One concrete sensory detail that places the listener HERE (a sound, material, smell)
- How this stop connects to the tour's theme — show the connection, don't just assert it"""

# ── The AFTER prompt lines (current LOCAL-213 fix) ──
AFTER_LINES = """\
Then provide a detailed description. Include:
- The specific evidence for why this place matters — a fact, a number, a named person, not adjectives
- Historical or cultural context: name a date, a person, an event, a cause-and-effect
- Ground the listener in the physical present — weave in a real sound, texture, or smell they can perceive right now at this spot
- How this stop connects to the tour's theme — show the connection, don't just assert it"""


def patch_prompt(content: str, target_lines: str) -> str:
    """Replace the Include: bullet list in generate_tour_text.py content."""
    # Find and replace the section
    pattern = r'Then provide a detailed description\. Include:\n- .*?(?=\n\nEXPLAIN-WHAT-YOU-NAME)'
    return re.sub(pattern, target_lines, content, count=1, flags=re.DOTALL)


def generate_one_run(run_idx: int, arm: str) -> dict:
    """Generate a single tour run. Returns paragraphs and R8 stats."""
    # Force fresh import of generate_tour_text each time
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']
    
    from generate_tour_text import generate_tour_text
    
    output_file = os.path.join(PROJECT_ROOT, "tours", 
                               f"LOCAL213_{arm}_run{run_idx}.txt")
    
    start = time.time()
    result = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        output_file=output_file,
        total_stops=STOPS,
        persona=None,
    )
    elapsed = time.time() - start
    
    if not result or not result[0]:
        return {'error': f'generation failed after {elapsed:.1f}s'}
    
    tour_text = result[0]
    
    # Parse paragraphs
    from stop_anchor_detector_v2 import parse_tour_stops
    stops = parse_tour_stops(tour_text)
    
    total_paras = 0
    r8_paras = 0
    r8_examples = []
    
    for stop in stops:
        for para in stop.get('paragraphs', []):
            if len(para) < 30:
                continue
            total_paras += 1
            result_v = validate_paragraph(para)
            r8_findings = [f for f in result_v['findings'] if f['rule_id'] == 'R8_PROMPT_LEAKAGE']
            if r8_findings:
                r8_paras += 1
                r8_examples.append(r8_findings[0]['sentence'][:120])
    
    return {
        'arm': arm,
        'run_idx': run_idx,
        'total_paras': total_paras,
        'r8_paras': r8_paras,
        'r8_rate': r8_paras / total_paras if total_paras > 0 else 0,
        'r8_examples': r8_examples,
        'elapsed': elapsed,
        'output_file': output_file,
    }


def run_experiment():
    """Run the before/after experiment."""
    print("=" * 78)
    print("LOCAL-213 Part 3: Before/After R8 Measurement")
    print("=" * 78)
    print(f"  Location: {LOCATION}")
    print(f"  Stops: {STOPS}")
    print(f"  Runs per arm: {RUNS}")
    print(f"  Model: gpt-3.5-turbo (default)")
    print()
    
    # Verify DB
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_before = cur.fetchone()[0]
    print(f"  audio_tours before: {count_before}")
    conn.close()
    
    # Read the source file
    gen_file = os.path.join(PROJECT_ROOT, "generate_tour_text.py")
    with open(gen_file, 'r') as f:
        original_content = f.read()
    
    # ── ARM A: AFTER (current code — already patched) ──
    print("\n" + "─" * 78)
    print("ARM A: AFTER (rephrased prompt, current code)")
    print("─" * 78)
    
    after_results = []
    for i in range(RUNS):
        print(f"\n  Run {i+1}/{RUNS}...")
        r = generate_one_run(i, "AFTER")
        after_results.append(r)
        if 'error' in r:
            print(f"    ✗ {r['error']}")
        else:
            print(f"    ✓ {r['total_paras']} paras, {r['r8_paras']} R8 violations ({r['r8_rate']*100:.0f}%), {r['elapsed']:.1f}s")
            for ex in r['r8_examples']:
                print(f"      → \"{ex}\"")
    
    # ── ARM B: BEFORE (original prompt — patch temporarily) ──
    print("\n" + "─" * 78)
    print("ARM B: BEFORE (original prompt with 'one concrete sensory detail')")
    print("─" * 78)
    
    # Patch the file back to the BEFORE version
    before_content = patch_prompt(original_content, BEFORE_LINES)
    if before_content == original_content:
        print("  WARNING: patch_prompt did not match — trying direct replacement")
        before_content = original_content.replace(AFTER_LINES, BEFORE_LINES)
    
    with open(gen_file, 'w') as f:
        f.write(before_content)
    
    before_results = []
    try:
        for i in range(RUNS):
            print(f"\n  Run {i+1}/{RUNS}...")
            r = generate_one_run(i, "BEFORE")
            before_results.append(r)
            if 'error' in r:
                print(f"    ✗ {r['error']}")
            else:
                print(f"    ✓ {r['total_paras']} paras, {r['r8_paras']} R8 violations ({r['r8_rate']*100:.0f}%), {r['elapsed']:.1f}s")
                for ex in r['r8_examples']:
                    print(f"      → \"{ex}\"")
    finally:
        # ALWAYS restore the AFTER version
        with open(gen_file, 'w') as f:
            f.write(original_content)
        print("\n  [Restored generate_tour_text.py to AFTER version]")
    
    # ── COMPARISON ──
    print("\n" + "=" * 78)
    print("COMPARISON: BEFORE vs AFTER")
    print("=" * 78)
    
    def summarize(results, label):
        valid = [r for r in results if 'error' not in r]
        if not valid:
            print(f"  {label}: all runs failed")
            return
        total_paras = sum(r['total_paras'] for r in valid)
        total_r8 = sum(r['r8_paras'] for r in valid)
        rate = total_r8 / total_paras if total_paras > 0 else 0
        print(f"  {label}:")
        print(f"    Runs: {len(valid)}")
        print(f"    Total paragraphs: {total_paras}")
        print(f"    R8 violations: {total_r8}")
        print(f"    R8 rate: {rate*100:.1f}% ({total_r8}/{total_paras})")
        for r in valid:
            print(f"      Run {r['run_idx']}: {r['r8_paras']}/{r['total_paras']} = {r['r8_rate']*100:.0f}%")
    
    summarize(before_results, "BEFORE (original prompt)")
    print()
    summarize(after_results, "AFTER (rephrased prompt)")
    
    # ── Final DB check ──
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_after = cur.fetchone()[0]
    print(f"\n  audio_tours after: {count_after}")
    
    # Nice list check
    cur.execute("""
        SELECT id FROM audio_tours
        WHERE is_test IS NOT TRUE
          AND lat IS NOT NULL AND lng IS NOT NULL
          AND lat BETWEEN 43.5 AND 43.9
          AND lng BETWEEN 7.0 AND 7.5
        ORDER BY id
    """)
    nice_rows = [r[0] for r in cur.fetchall()]
    expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
    visible_nice = [i for i in nice_rows if i in expected_nice]
    print(f"  Nice list: {visible_nice}")
    print(f"  Nice list matches expected: {'YES' if visible_nice == expected_nice else 'NO'}")
    conn.close()
    
    return before_results, after_results


if __name__ == '__main__':
    before_results, after_results = run_experiment()

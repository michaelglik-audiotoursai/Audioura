"""
LOCAL-72 A/B test: Thin-corpus rule effect on museum facts.

Runs the Asian museum tour 3 times WITHOUT the thin-corpus rule (current code),
then temporarily re-injects the rule and runs 3 more times WITH it.

Reports per-run distinct facts, mean, and spread for each arm.
This separates LLM noise from the rule's actual effect.

Usage:
    source .env && python3 run_local72_thin_corpus_ab_test.py
"""
import sys
import os
import re
import json
import time
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STORIED_MODE"] = "true"

# Load .env if not already set
if not os.environ.get("OPENAI_API_KEY"):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key] = val


THIN_CORPUS_RULE = """
THIN-CORPUS HONESTY RULE (critical — prevents fabrication):
If you do not have verified, specific information about this particular work's visual content,
material, or history, DO NOT INVENT details. Instead:
- State what IS known (title, artist, period, medium if available)
- Describe the TYPE of work and its general context
- Acknowledge the gap honestly rather than filling it with plausible-sounding fiction
A 120-word honest description beats a 300-word fabricated one. When your knowledge is thin,
be SHORT and FACTUAL. The number of confirmed facts in the fact sheet below tells you how
much material you actually have to work with.
"""


def count_distinct_facts(text: str) -> int:
    """Count distinct checkable facts in a stop's text."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    _year = re.compile(r'\b\d{3,4}\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b', re.IGNORECASE)
    _person = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[IVXLCDM]+)\b')
    _number = re.compile(r'\b\d+(?:\.\d+)?\s*(?:m|km|ft|metres?|meters?|miles?|hectares?|acres?|kg|tons?|tonnes?|years?|centuries?)\b', re.IGNORECASE)
    _event = re.compile(r'\b(?:built|founded|opened|established|designed|created|completed|commissioned|inaugurated|renovated|destroyed|constructed)\s+(?:in|by|during|around)\b', re.IGNORECASE)
    _artwork = re.compile(r'\"[^\"]+\"|"[^"]+"|«[^»]+»', re.IGNORECASE)
    
    facts = set()
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        has_year = bool(_year.search(sent))
        has_person = bool(_person.search(sent))
        has_number = bool(_number.search(sent))
        has_event = bool(_event.search(sent))
        has_artwork = bool(_artwork.search(sent))
        
        if has_year or has_person or has_number or has_event or has_artwork:
            facts.add(sent[:100])
    
    return len(facts)


def extract_stops(tour_text: str) -> list:
    """Extract individual stop texts from a generated tour."""
    stops = []
    parts = re.split(r'\nStop\s+(\d+):\s*', tour_text)
    for i in range(1, len(parts) - 1, 2):
        stop_num = int(parts[i])
        stop_text = parts[i + 1].strip()
        stops.append({
            'number': stop_num,
            'text': stop_text,
            'words': len(stop_text.split()),
        })
    return stops


def run_one_asian_museum(label: str, run_num: int) -> dict:
    """Generate one Asian museum tour and measure facts."""
    from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
    
    output_dir = os.path.join('tours', 'local72_ab_test')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"asian_{label}_run{run_num}.txt")
    
    t0 = time.time()
    result = generate_tour_text(
        "Musée des Arts Asiatiques, Nice, France",
        "explore",
        output_file=output_file,
        total_stops=8,
    )
    elapsed = time.time() - t0
    
    if isinstance(result, tuple):
        text = result[0] if result[0] else ""
    else:
        text = result or ""
    
    if not text and os.path.exists(output_file):
        with open(output_file) as f:
            text = f.read()
    
    cost = _LAST_GENERATION_COST.get('total_cost', 0) if _LAST_GENERATION_COST else 0
    
    # Per-stop facts
    stops = extract_stops(text)
    stop_facts = []
    total_facts = 0
    for stop in stops:
        facts = count_distinct_facts(stop['text'])
        stop_facts.append({'number': stop['number'], 'words': stop['words'], 'facts': facts})
        total_facts += facts
    
    # Check visitor info
    has_closed_tuesday = bool(re.search(r'closed\s+on\s+tuesday', text, re.IGNORECASE))
    has_free_admission = bool(re.search(r'free\s+admission', text, re.IGNORECASE))
    
    # Save full text
    full_path = os.path.join(output_dir, f"asian_{label}_run{run_num}_full.txt")
    with open(full_path, 'w') as f:
        f.write(text)
    
    return {
        'label': label,
        'run': run_num,
        'stops': len(stops),
        'total_facts': total_facts,
        'stop_facts': stop_facts,
        'cost': cost,
        'time': elapsed,
        'closed_tuesday': has_closed_tuesday,
        'free_admission': has_free_admission,
    }


def inject_thin_corpus_rule():
    """Monkey-patch to re-inject the thin-corpus rule for the WITH arm."""
    import generate_tour_text as mod
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generate_tour_text.py')
    with open(source_path) as f:
        source = f.read()
    
    # Find the removal comment and inject the rule after the exhibition guard
    marker = "# [LOCAL-48] Thin-corpus honesty rule REMOVED (LOCAL-72 bounce)."
    injection_point = "EXHIBITION VS OBJECT RULE"
    
    if marker in source:
        # The rule is removed. For the WITH arm, we'll monkey-patch by temporarily
        # modifying the source. Instead, let's use an environment variable approach.
        os.environ["_LOCAL72_INJECT_THIN_CORPUS"] = "1"
    

def remove_thin_corpus_injection():
    """Remove the monkey-patch."""
    os.environ.pop("_LOCAL72_INJECT_THIN_CORPUS", None)


def main():
    RUNS_PER_ARM = 3
    
    print("=" * 70)
    print("  LOCAL-72 A/B TEST: Thin-corpus rule effect on museum facts")
    print("=" * 70)
    print(f"  Arms: WITHOUT thin-corpus rule (current) vs WITH (original LOCAL-48)")
    print(f"  Runs per arm: {RUNS_PER_ARM}")
    print(f"  Tour: Musée des Arts Asiatiques, Nice (8 stops)")
    print()
    
    # ─── ARM A: WITHOUT thin-corpus rule (current code) ─────────────────────
    print("\n" + "─" * 70)
    print("  ARM A: WITHOUT thin-corpus rule (current code)")
    print("─" * 70)
    
    arm_a_results = []
    for i in range(1, RUNS_PER_ARM + 1):
        print(f"\n  Run {i}/{RUNS_PER_ARM}...")
        result = run_one_asian_museum("without", i)
        arm_a_results.append(result)
        print(f"    → {result['total_facts']} facts, {result['stops']}/8 stops, "
              f"${result['cost']:.4f}, {result['time']:.1f}s")
        print(f"    → Closed Tues: {'✓' if result['closed_tuesday'] else '✗'}, "
              f"Free admission: {'✓' if result['free_admission'] else '✗'}")
    
    # ─── ARM B: WITH thin-corpus rule (injected back) ───────────────────────
    # For this arm, we temporarily modify the source file to re-add the rule,
    # then restore it after. This is the cleanest way to get a real measurement.
    print("\n" + "─" * 70)
    print("  ARM B: WITH thin-corpus rule (re-injected)")
    print("─" * 70)
    
    # Temporarily inject the rule back into generate_tour_text.py
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generate_tour_text.py')
    with open(source_path) as f:
        original_source = f.read()
    
    # Replace the removal comment block with the actual rule injection
    removal_comment = """            # [LOCAL-48] Thin-corpus honesty rule REMOVED (LOCAL-72 bounce).
            # LEAD identified this as a thinning instruction ("be SHORT when knowledge
            # is thin") wearing an honesty label. Museum tour lost 5 facts (36→31)
            # when this rule was active — five times the 1-fact LLM noise observed
            # between identical runs. Same treatment as the 80-word outdoor cap:
            # content-removal instructions are not anti-fabrication guards.
            # The exhibition-vs-object rule above IS a genuine anti-fabrication guard
            # (it corrects what the model says, not how much it says) and is kept."""
    
    rule_injection = """            # [LOCAL-48] Thin-corpus honesty guard (temporarily re-injected for A/B test)
            description_prompt += f\"\"\"
THIN-CORPUS HONESTY RULE (critical — prevents fabrication):
If you do not have verified, specific information about this particular work's visual content,
material, or history, DO NOT INVENT details. Instead:
- State what IS known (title, artist, period, medium if available)
- Describe the TYPE of work and its general context
- Acknowledge the gap honestly rather than filling it with plausible-sounding fiction
A 120-word honest description beats a 300-word fabricated one. When your knowledge is thin,
be SHORT and FACTUAL. The number of confirmed facts in the fact sheet below tells you how
much material you actually have to work with.
\"\"\""""
    
    modified_source = original_source.replace(removal_comment, rule_injection)
    
    if modified_source == original_source:
        print("  ERROR: Could not inject thin-corpus rule — marker not found")
        sys.exit(1)
    
    with open(source_path, 'w') as f:
        f.write(modified_source)
    
    # Force reimport
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']
    
    arm_b_results = []
    try:
        for i in range(1, RUNS_PER_ARM + 1):
            print(f"\n  Run {i}/{RUNS_PER_ARM}...")
            # Reimport each time to ensure fresh module state
            if 'generate_tour_text' in sys.modules:
                del sys.modules['generate_tour_text']
            result = run_one_asian_museum("with", i)
            arm_b_results.append(result)
            print(f"    → {result['total_facts']} facts, {result['stops']}/8 stops, "
                  f"${result['cost']:.4f}, {result['time']:.1f}s")
            print(f"    → Closed Tues: {'✓' if result['closed_tuesday'] else '✗'}, "
                  f"Free admission: {'✓' if result['free_admission'] else '✗'}")
    finally:
        # ALWAYS restore the original source
        with open(source_path, 'w') as f:
            f.write(original_source)
        if 'generate_tour_text' in sys.modules:
            del sys.modules['generate_tour_text']
    
    # ─── ANALYSIS ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    
    a_facts = [r['total_facts'] for r in arm_a_results]
    b_facts = [r['total_facts'] for r in arm_b_results]
    
    a_mean = statistics.mean(a_facts)
    b_mean = statistics.mean(b_facts)
    a_stdev = statistics.stdev(a_facts) if len(a_facts) > 1 else 0
    b_stdev = statistics.stdev(b_facts) if len(b_facts) > 1 else 0
    
    print(f"\n  ARM A (WITHOUT thin-corpus rule):")
    print(f"    Runs: {a_facts}")
    print(f"    Mean: {a_mean:.1f} facts")
    print(f"    Stdev: {a_stdev:.1f}")
    print(f"    Range: {min(a_facts)}–{max(a_facts)}")
    
    print(f"\n  ARM B (WITH thin-corpus rule):")
    print(f"    Runs: {b_facts}")
    print(f"    Mean: {b_mean:.1f} facts")
    print(f"    Stdev: {b_stdev:.1f}")
    print(f"    Range: {min(b_facts)}–{max(b_facts)}")
    
    delta = a_mean - b_mean
    print(f"\n  Delta (A - B): {delta:+.1f} facts")
    print(f"  Interpretation: {'Rule REMOVES facts' if delta > 0 else 'Rule ADDS facts' if delta < 0 else 'No effect'}")
    
    # Check if delta exceeds noise
    max_noise = max(a_stdev, b_stdev)
    if abs(delta) > 2 * max_noise:
        print(f"  Signal: CLEAR (delta {abs(delta):.1f} > 2× max noise {max_noise:.1f})")
    elif abs(delta) > max_noise:
        print(f"  Signal: LIKELY (delta {abs(delta):.1f} > max noise {max_noise:.1f})")
    else:
        print(f"  Signal: UNCLEAR (delta {abs(delta):.1f} ≤ max noise {max_noise:.1f})")
    
    # Cost summary
    a_costs = [r['cost'] for r in arm_a_results]
    b_costs = [r['cost'] for r in arm_b_results]
    print(f"\n  Cost (mean): A=${statistics.mean(a_costs):.4f}, B=${statistics.mean(b_costs):.4f}")
    
    # Visitor info check
    a_visitor_ok = all(r['closed_tuesday'] and r['free_admission'] for r in arm_a_results)
    b_visitor_ok = all(r['closed_tuesday'] and r['free_admission'] for r in arm_b_results)
    print(f"\n  Visitor info (all runs): A={'✓' if a_visitor_ok else '✗'}, B={'✓' if b_visitor_ok else '✗'}")
    
    # Per-stop breakdown for each run
    print(f"\n  PER-STOP FACTS (all runs):")
    print(f"  {'Run':<12} {'S1':>3} {'S2':>3} {'S3':>3} {'S4':>3} {'S5':>3} {'S6':>3} {'S7':>3} {'S8':>3} {'Total':>6}")
    print(f"  {'─'*12} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*6}")
    
    for r in arm_a_results:
        stop_f = [sf['facts'] for sf in r['stop_facts']]
        while len(stop_f) < 8:
            stop_f.append(0)
        print(f"  {'A-run' + str(r['run']):<12} {stop_f[0]:>3} {stop_f[1]:>3} {stop_f[2]:>3} {stop_f[3]:>3} "
              f"{stop_f[4]:>3} {stop_f[5]:>3} {stop_f[6]:>3} {stop_f[7]:>3} {r['total_facts']:>6}")
    
    for r in arm_b_results:
        stop_f = [sf['facts'] for sf in r['stop_facts']]
        while len(stop_f) < 8:
            stop_f.append(0)
        print(f"  {'B-run' + str(r['run']):<12} {stop_f[0]:>3} {stop_f[1]:>3} {stop_f[2]:>3} {stop_f[3]:>3} "
              f"{stop_f[4]:>3} {stop_f[5]:>3} {stop_f[6]:>3} {stop_f[7]:>3} {r['total_facts']:>6}")
    
    # Save full results to JSON
    output_dir = os.path.join('tours', 'local72_ab_test')
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, 'ab_test_results.json')
    with open(results_path, 'w') as f:
        json.dump({
            'arm_a_without_rule': arm_a_results,
            'arm_b_with_rule': arm_b_results,
            'summary': {
                'a_facts': a_facts, 'b_facts': b_facts,
                'a_mean': a_mean, 'b_mean': b_mean,
                'a_stdev': a_stdev, 'b_stdev': b_stdev,
                'delta': delta,
            }
        }, f, indent=2, default=str)
    print(f"\n  Full results saved to: {results_path}")


if __name__ == '__main__':
    main()

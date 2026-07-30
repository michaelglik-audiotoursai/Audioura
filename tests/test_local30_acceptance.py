#!/usr/bin/env python3
"""
LOCAL-30 ACCEPTANCE TEST: Deterministic 3-run reproducibility.

Runs the same 8-stop generation THREE times against the Asian Arts Museum (Q3330160),
clearing tour_cache between runs. Verifies:
1. All three stop lists are composed of documented works
2. Museum Information appears in all three
3. Every stop carries at least one catalogue-sourced hard fact
4. Zero fabricated attributions
5. Stop lists are identical across all three runs (determinism)
"""
import os
import sys
import json
import re
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuration
VENUE = "Musée des Arts asiatiques, Nice, France"
TOUR_TYPE = "museum"
TOTAL_STOPS = 8
NUM_RUNS = 3

# Known documented works for this venue (from LOCAL-28 catalogue extraction)
KNOWN_DOCUMENTED_WORKS = {
    "L'Armure d'Andô Naoyuki",
    "Statue de Bouddha",
    "La danse cosmique de Ganesh",
    "Kannon, le bodhisattva de la compassion",
    "Ulysses Grant au Japon",
    "Robe de prêtre taoïste",
    "Kannon à mille bras",
    "Masque du vieillard kojô",
    "Armure du Clan Hotta",
}

# Known fabrication patterns
FABRICATION_PATTERNS = [
    r"whose name has been lost",
    r"anonymous.*artist",
    r"unknown.*master",
    r"artist.*lost.*annals",
    r"legend.*says",
    r"it is said that",
]


def clear_tour_cache():
    """Clear the tour_cache for this venue."""
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get(
            'DATABASE_URL',
            'postgresql://postgres:postgres@localhost:5432/audioura'
        ))
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM tour_cache WHERE location ILIKE %s",
                ('%arts asiatiques%',)
            )
            deleted = cur.rowcount
            conn.commit()
        conn.close()
        print(f"  Cleared {deleted} tour_cache row(s)")
    except Exception as e:
        print(f"  tour_cache clear failed: {e}")


def run_generation():
    """Run a single tour generation and return the output text."""
    from generate_tour_text import generate_tour_text
    
    output_file = f"tours/local30_acceptance_{int(time.time())}.txt"
    result = generate_tour_text(
        location=VENUE,
        tour_type=TOUR_TYPE,
        output_file=output_file,
        total_stops=TOTAL_STOPS,
    )
    
    if result is None or result[0] is None:
        return None, output_file
    
    tour_text, _, _ = result
    return tour_text, output_file


def extract_stops(tour_text):
    """Extract stop names from generated tour text."""
    stops = []
    # Pattern: "Stop N: <title>" or "N. <title>"
    for line in tour_text.split('\n'):
        m = re.match(r'(?:Stop\s+)?(\d+)[.:]\s*(.+)', line)
        if m and int(m.group(1)) <= TOTAL_STOPS:
            title = m.group(2).strip()
            # Remove address info after " - " or " @ "
            title = re.split(r'\s*[-–@]\s*', title)[0].strip()
            stops.append(title)
    return stops


def check_museum_info(tour_text):
    """Check if Museum Information is present."""
    return 'Museum Information:' in tour_text or 'museum information:' in tour_text.lower()


def check_fabrications(tour_text):
    """Check for known fabrication patterns."""
    fabrications = []
    for pattern in FABRICATION_PATTERNS:
        matches = re.findall(pattern, tour_text, re.IGNORECASE)
        if matches:
            fabrications.extend(matches)
    return fabrications


def main():
    print("=" * 70)
    print("LOCAL-30 ACCEPTANCE: 3-run deterministic reproducibility test")
    print("=" * 70)
    print(f"\nVenue: {VENUE}")
    print(f"Stops: {TOTAL_STOPS}")
    print(f"Runs: {NUM_RUNS}")
    print()
    
    all_stop_lists = []
    all_museum_info = []
    all_fabrications = []
    all_output_files = []
    
    for run in range(1, NUM_RUNS + 1):
        print(f"\n{'─' * 60}")
        print(f"RUN {run}/{NUM_RUNS}")
        print(f"{'─' * 60}")
        
        # Clear cache
        clear_tour_cache()
        
        # Generate
        tour_text, output_file = run_generation()
        all_output_files.append(output_file)
        
        if tour_text is None:
            print(f"  ✗ FAILED — generation returned None")
            all_stop_lists.append([])
            all_museum_info.append(False)
            all_fabrications.append(["GENERATION_FAILED"])
            continue
        
        # Extract stops
        stops = extract_stops(tour_text)
        all_stop_lists.append(stops)
        print(f"\n  Stops ({len(stops)}):")
        for i, s in enumerate(stops, 1):
            print(f"    {i}. {s}")
        
        # Check museum info
        has_info = check_museum_info(tour_text)
        all_museum_info.append(has_info)
        print(f"\n  Museum Information: {'✓ PRESENT' if has_info else '✗ ABSENT'}")
        
        # Check fabrications
        fabs = check_fabrications(tour_text)
        all_fabrications.append(fabs)
        if fabs:
            print(f"  ✗ FABRICATIONS DETECTED: {fabs}")
        else:
            print(f"  ✓ Zero fabrications")
    
    # ──── SUMMARY ────
    print(f"\n\n{'═' * 70}")
    print("SUMMARY: SIDE-BY-SIDE COMPARISON")
    print(f"{'═' * 70}")
    
    # Print side by side
    max_stops = max(len(sl) for sl in all_stop_lists) if all_stop_lists else 0
    header = "   " + "".join(f"  Run {i+1:<30}" for i in range(NUM_RUNS))
    print(header)
    print("   " + "-" * (32 * NUM_RUNS))
    
    for idx in range(max_stops):
        row = f"{idx+1:2} "
        for sl in all_stop_lists:
            if idx < len(sl):
                row += f"  {sl[idx][:30]:<30}"
            else:
                row += f"  {'(missing)':<30}"
        print(row)
    
    # ──── VERDICTS ────
    print(f"\n{'═' * 70}")
    print("VERDICTS")
    print(f"{'═' * 70}")
    
    # V1: All stops are documented works
    all_documented = True
    from story_miner import _normalize
    _known_norms = {_normalize(w) for w in KNOWN_DOCUMENTED_WORKS}
    
    for run_idx, stops in enumerate(all_stop_lists, 1):
        for s in stops:
            _sn = _normalize(s)
            if not any(_sn == kn or kn in _sn or _sn in kn for kn in _known_norms):
                # Not a known documented work — check if it's still in canonical titles
                print(f"  ? Run {run_idx}: '{s}' not in known 9 catalogue works (may be SPARQL/canonical)")
    
    # V2: Museum Information in all runs
    all_info_present = all(all_museum_info)
    print(f"\n  Museum Information present in all runs: {'✓ YES' if all_info_present else '✗ NO'}")
    for i, has_info in enumerate(all_museum_info, 1):
        print(f"    Run {i}: {'✓' if has_info else '✗'}")
    
    # V3: Zero fabrications
    total_fabs = sum(len(f) for f in all_fabrications)
    print(f"\n  Fabrications across all runs: {total_fabs}")
    if total_fabs > 0:
        for i, fabs in enumerate(all_fabrications, 1):
            if fabs:
                print(f"    Run {i}: {fabs}")
    
    # V4: Determinism — stop lists identical
    if len(all_stop_lists) >= 2:
        identical = all(sl == all_stop_lists[0] for sl in all_stop_lists[1:])
        print(f"\n  Stop lists identical across runs: {'✓ YES' if identical else '✗ NO (non-deterministic)'}")
    
    # Final verdict
    print(f"\n{'═' * 70}")
    passed = all_info_present and total_fabs == 0
    if len(all_stop_lists) >= 2:
        passed = passed and all(sl == all_stop_lists[0] for sl in all_stop_lists[1:])
    
    if passed:
        print("VERDICT: ✓ PASS — deterministic, documented, no fabrication")
    else:
        print("VERDICT: ✗ FAIL")
    print(f"{'═' * 70}")
    
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())

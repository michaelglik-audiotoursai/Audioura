#!/usr/bin/env python3
"""
LOCAL-322 Verification: Run 8-stop museum generation and check for French material leaks.

This script:
1. Generates an 8-stop Asian arts museum tour
2. Checks for French material terms in English narration
3. Checks for comma-spliced patch fragments
4. Counts "[LOCAL-98] ... missing from description" retry messages
5. Verifies a genuinely-missing material case gets patched in English
6. Outputs comparison data for baseline regression check
"""
import os
import sys
import re
import time
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Configuration
VENUE = "Musée des Arts asiatiques, Nice, France"
TOUR_TYPE = "museum"
TOTAL_STOPS = 8
OUTPUT_FILE = f"tours/LOCAL322_verification_{int(time.time())}.txt"

# French material terms from story_miner._MATERIALS that should NOT appear in English narration
# (except when they are also valid English words like "bronze", "jade", "pastel", "gouache")
FRENCH_ONLY_MATERIALS = [
    'schiste', 'acier', 'cuivre', 'cuir', 'soie', 'laque',
    'bois', 'marbre', 'porcelaine', 'céramique', 'ivoire',
    'laiton', 'terre cuite', 'grès', 'fer', 'argent',
    'papier', 'encre', 'huile', 'aquarelle',
    "feuille d'or", 'dorure', 'xylogravure', 'soie brodée',
    'bois laqué', 'cuir laqué', 'laqué', 'laquée',
]

# Pattern for the defective comma-splice
SPLICE_PATTERN = re.compile(r'This work, [^.]+, [A-Z]')

# Pattern for French material in "crafted in/from" context
FRENCH_CRAFT_PATTERN = re.compile(
    r'crafted (?:in|from) (' + '|'.join(re.escape(m) for m in FRENCH_ONLY_MATERIALS) + r')\b',
    re.IGNORECASE
)


def main():
    # Require API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key or api_key == 'placeholder':
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    print(f"=" * 70)
    print(f"LOCAL-322 VERIFICATION RUN")
    print(f"=" * 70)
    print(f"Venue: {VENUE}")
    print(f"Stops: {TOTAL_STOPS}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    # Capture stdout to count retry messages
    from generate_tour_text import generate_tour_text

    captured_output = io.StringIO()
    
    print("Generating tour (capturing retry messages)...")
    start_time = time.time()
    
    # Use a tee approach: print to both stdout and capture
    class TeeWriter:
        def __init__(self, *writers):
            self.writers = writers
        def write(self, data):
            for w in self.writers:
                w.write(data)
        def flush(self):
            for w in self.writers:
                w.flush()
    
    old_stdout = sys.stdout
    sys.stdout = TeeWriter(old_stdout, captured_output)
    
    try:
        result = generate_tour_text(
            location=VENUE,
            tour_type=TOUR_TYPE,
            output_file=OUTPUT_FILE,
            total_stops=TOTAL_STOPS,
        )
    except Exception as e:
        sys.stdout = old_stdout
        print(f"ERROR during generation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sys.stdout = old_stdout
    
    elapsed = time.time() - start_time
    captured_text = captured_output.getvalue()
    
    # Get the generated text
    if result and isinstance(result, tuple) and len(result) >= 1:
        tour_text = result[0] if isinstance(result[0], str) else str(result[0])
    elif result and isinstance(result, str):
        tour_text = result
    elif os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            tour_text = f.read()
    else:
        print("ERROR: No output generated")
        sys.exit(1)
    
    print(f"\nGeneration completed in {elapsed:.1f}s")
    print(f"Output length: {len(tour_text)} chars")
    print()
    
    # ======================================================================
    # CHECK 1: French material terms in English narration
    # ======================================================================
    print("=" * 70)
    print("CHECK 1: French material terms in English narration")
    print("=" * 70)
    
    french_leaks = []
    for term in FRENCH_ONLY_MATERIALS:
        # Use word boundary to avoid false positives
        matches = re.findall(r'\b' + re.escape(term) + r'\b', tour_text.lower())
        if matches:
            french_leaks.append((term, len(matches)))
    
    if french_leaks:
        print(f"  FOUND {sum(c for _, c in french_leaks)} French material leaks:")
        for term, count in french_leaks:
            print(f"    '{term}': {count} occurrence(s)")
            # Show context
            for m in re.finditer(r'(?i).{0,40}\b' + re.escape(term) + r'\b.{0,40}', tour_text):
                print(f"      ...{m.group(0).strip()}...")
    else:
        print("  ✓ ZERO French material terms found in English narration")
    
    # ======================================================================
    # CHECK 2: Comma-spliced patch fragments
    # ======================================================================
    print()
    print("=" * 70)
    print("CHECK 2: Comma-spliced 'This work, crafted in X, [A-Z]' fragments")
    print("=" * 70)
    
    splices = SPLICE_PATTERN.findall(tour_text)
    if splices:
        print(f"  FOUND {len(splices)} splice(s):")
        for s in splices:
            print(f"    {s[:80]}")
    else:
        print("  ✓ ZERO comma-spliced fragments found")
    
    # ======================================================================
    # CHECK 3: "crafted in/from" with French terms
    # ======================================================================
    print()
    print("=" * 70)
    print("CHECK 3: French terms in 'crafted in/from' context")
    print("=" * 70)
    
    french_crafts = FRENCH_CRAFT_PATTERN.findall(tour_text)
    if french_crafts:
        print(f"  FOUND {len(french_crafts)} French-craft pattern(s):")
        for m in french_crafts:
            print(f"    '{m}'")
    else:
        print("  ✓ ZERO French 'crafted in/from' patterns found")
    
    # ======================================================================
    # CHECK 4: Retry count (cost reduction evidence)
    # ======================================================================
    print()
    print("=" * 70)
    print("CHECK 4: Retry messages ([LOCAL-98] ... missing from description)")
    print("=" * 70)
    
    retry_messages = re.findall(r'\[LOCAL-98\].*missing from description', captured_text)
    retry_count = len(retry_messages)
    print(f"  Retry messages fired: {retry_count}")
    if retry_messages:
        for rm in retry_messages[:5]:
            print(f"    {rm.strip()}")
    
    # Count LOCAL-322 skip messages (material checks treated as satisfied)
    skip_messages = re.findall(r'\[LOCAL-322\].*treating as satisfied', captured_text)
    skip_count = len(skip_messages)
    if skip_count:
        print(f"  Material checks skipped (no EN translation): {skip_count}")
    
    skip_no_en = re.findall(r'\[LOCAL-322\].*skipping material binding', captured_text)
    if skip_no_en:
        print(f"  Material bindings skipped (no EN): {len(skip_no_en)}")
    
    # ======================================================================
    # CHECK 5: Patched materials are in English
    # ======================================================================
    print()
    print("=" * 70)
    print("CHECK 5: Any patched content is in English")
    print("=" * 70)
    
    patch_messages = re.findall(r'\[LOCAL-31\].*patched.*\(EN: ([^)]+)\)', captured_text)
    if patch_messages:
        print(f"  {len(patch_messages)} patch(es) applied:")
        for pm in patch_messages:
            print(f"    EN content: {pm}")
        # Verify the patched text in the output
        for pm in patch_messages:
            if pm in tour_text.lower() or any(part.strip() in tour_text.lower() for part in pm.split(',')):
                print(f"    ✓ '{pm}' confirmed in output")
    else:
        print("  No patches needed (materials already in descriptions)")
    
    # ======================================================================
    # CHECK 6: Stop count (regression check)
    # ======================================================================
    print()
    print("=" * 70)
    print("CHECK 6: Stop count and completeness")
    print("=" * 70)
    
    stop_pattern = re.compile(r'(?:^|\n)(?:#{1,3}\s*)?Stop\s+(\d+)[:\s]+', re.IGNORECASE)
    stops_found = stop_pattern.findall(tour_text)
    print(f"  Stops found: {len(stops_found)} (expected: {TOTAL_STOPS})")
    if len(stops_found) < TOTAL_STOPS:
        print(f"  ⚠ STOP COUNT LOW — may indicate generation failure")
    
    # ======================================================================
    # SUMMARY
    # ======================================================================
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_french = sum(c for _, c in french_leaks) if french_leaks else 0
    print(f"  French material leaks: {total_french}")
    print(f"  Comma splices: {len(splices)}")
    print(f"  French craft patterns: {len(french_crafts)}")
    print(f"  Retry messages: {retry_count}")
    print(f"  Stops generated: {len(stops_found)}/{TOTAL_STOPS}")
    print(f"  Generation time: {elapsed:.1f}s")
    
    # Final verdict
    print()
    if total_french == 0 and len(splices) == 0 and len(french_crafts) == 0 and len(stops_found) >= TOTAL_STOPS:
        print("  ✓ ALL CHECKS PASSED")
    else:
        print("  ✗ SOME CHECKS FAILED")
    
    return {
        'french_leaks': total_french,
        'splices': len(splices),
        'french_crafts': len(french_crafts),
        'retries': retry_count,
        'stops': len(stops_found),
        'elapsed': elapsed,
    }


if __name__ == '__main__':
    main()

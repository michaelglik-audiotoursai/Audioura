"""test_g4_false_positives.py — Permanent unit fixtures for G4 false-positive sentences.

Per Phase 2 close condition (LEAD comment 1000410000006474, 2026-07-11):
These two sentences triggered G4 FACTUAL failures before the B1 fix (6ea11dd).
They contain art-period terms and exhibition venue names that are NOT fabrication carriers.

The fix (paragraph-split + recap-exclusion + art-period closed class in _COMMON_PROPER)
ensures these pass. These fixtures guarantee the fix survives future refactors.

Run from development/:  python test_g4_false_positives.py
"""

import sys
import os

# Ensure the development directory is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from content_qa_runner import extract_g4_proper_nouns


# ---------------------------------------------------------------------------
# The two false-positive sentences (from Phase 2 CIL cycle 3, commit 6ea11dd)
# ---------------------------------------------------------------------------

# FALSE POSITIVE 1: "Grand Palais" partnership (Matisse tour)
# "Grand" and "Palais" are exhibition/venue terms, not fabrication carriers.
# Before B1 fix: G4 extracted "Palais" as a proper noun → FAIL (ungrounded)
FP1_SENTENCE = (
    "The partnership with the Grand Palais in Paris enabled the landmark "
    "retrospective exhibition of 2005 that brought international attention "
    "to the museum's permanent collection."
)

# FALSE POSITIVE 2: "Renaissance" period usage (Uffizi tour)
# "Renaissance" is an art-historical period term, not a person/place fabrication.
# Before B1 fix: G4 extracted "Renaissance" as a proper noun → FAIL (ungrounded)
FP2_SENTENCE = (
    "During the Renaissance period, the Medici family commissioned artists "
    "to create works that would transform Florence into the cultural capital "
    "of Europe."
)


# ---------------------------------------------------------------------------
# Fixtures — test with REAL gate semantics via the production function
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """Run all false-positive fixtures. Returns True if all pass (no false alarms)."""
    all_passed = True

    # FP1: Grand Palais with venue_context for Paris/Matisse
    # A sentence passes G4 when extracted proper nouns are empty OR all present
    # in the matched story element text. Here we verify 'grand' and 'palais'
    # are NOT extracted at all (they're in the closed class).
    fp1_context = {
        'city': 'Paris',
        'artist': 'Matisse',
        'venue_tokens': set(),
    }
    fp1_extracted = extract_g4_proper_nouns(FP1_SENTENCE, venue_context=fp1_context)
    fp1_bad = {'grand', 'palais'} & fp1_extracted
    fp1_passed = len(fp1_bad) == 0
    status = "PASS" if fp1_passed else "FAIL"
    print(f"  [{status}] FP1: 'Grand Palais' partnership (Matisse) — "
          f"'grand' and 'palais' should NOT be extracted")
    print(f"         Extracted: {sorted(fp1_extracted) if fp1_extracted else '(none)'}")
    if not fp1_passed:
        print(f"         FALSE POSITIVES: {sorted(fp1_bad)}")
        all_passed = False

    # FP2: Renaissance period — no venue_context needed for this check
    fp2_extracted = extract_g4_proper_nouns(FP2_SENTENCE)
    fp2_bad = {'renaissance'} & fp2_extracted
    fp2_passed = len(fp2_bad) == 0
    status = "PASS" if fp2_passed else "FAIL"
    print(f"  [{status}] FP2: 'Renaissance' period (Uffizi) — "
          f"'renaissance' should NOT be extracted")
    print(f"         Extracted: {sorted(fp2_extracted) if fp2_extracted else '(none)'}")
    if not fp2_passed:
        print(f"         FALSE POSITIVES: {sorted(fp2_bad)}")
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("G4 False-Positive Fixtures (B1 fix regression lock)")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    if success:
        print("ALL TESTS PASSED — no false-positive regressions")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED — B1 fix may have regressed")
        sys.exit(1)

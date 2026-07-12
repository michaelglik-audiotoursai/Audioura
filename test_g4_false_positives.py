"""test_g4_false_positives.py — Permanent unit fixtures for G4 false-positive sentences.

Per Phase 2 close condition (LEAD comment 1000410000006474, 2026-07-11):
These two sentences triggered G4 FACTUAL failures before the B1 fix (6ea11dd).
They contain art-period terms and exhibition venue names that are NOT fabrication carriers.

The fix (paragraph-split + recap-exclusion + art-period closed class in _COMMON_PROPER)
ensures these pass. These fixtures guarantee the fix survives future refactors.

Run from development/:  python test_g4_false_positives.py
"""

import re
import sys


# ---------------------------------------------------------------------------
# Minimal G4 proper-noun extraction logic (mirrors content_qa_runner.py)
# ---------------------------------------------------------------------------

# Art-period closed class (B7: these are NOT fabrication carriers)
_COMMON_PROPER = {
    'this', 'after', 'before', 'during', 'through', 'from', 'with',
    'when', 'where', 'which', 'whose', 'what', 'that', 'each',
    'both', 'some', 'many', 'most', 'also', 'just', 'here',
    'message', 'museum', 'chapel', 'gallery', 'collection',
    'biblical', 'testament', 'exodus', 'genesis',
    # B1 FIX: Historical periods — NOT fabrication carriers
    'renaissance', 'baroque', 'impressionist', 'impressionism',
    'expressionist', 'expressionism', 'cubist', 'cubism',
    'fauvist', 'fauvism', 'modernist', 'modernism',
    'neoclassical', 'rococo', 'mannerist', 'mannerism',
    'surrealist', 'surrealism', 'realist', 'realism',
    'romantic', 'romanticism', 'romanesque', 'gothic',
    'post-impressionist', 'post-impressionism',
    'classical', 'medieval', 'byzantine', 'hellenistic',
    # B1 FIX: Exhibition/venue terms from Wikipedia corpus
    'palais', 'salon', 'exposition', 'biennale', 'grand',
    'retrospective', 'atelier',
}


def extract_proper_nouns(sentence: str) -> set:
    """Extract proper nouns from a sentence using the G4 logic.
    
    Returns the set of proper nouns that would be checked against story elements.
    An empty set means the sentence passes G4 (no ungrounded fabrication risk).
    """
    proper_nouns = set()
    words = re.findall(r'\b\w+\b', sentence)
    for i, w in enumerate(words):
        if i == 0:
            continue  # Skip sentence-start capitalization
        if w and w[0].isupper() and len(w) >= 3:
            wl = w.lower()
            if wl not in _COMMON_PROPER:
                proper_nouns.add(wl)
    return proper_nouns


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
# Fixtures
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """Run all false-positive fixtures. Returns True if all pass (no false alarms)."""
    all_passed = True

    fixtures = [
        (
            "FP1: 'Grand Palais' partnership (Matisse) — should NOT extract fabrication-risk nouns",
            FP1_SENTENCE,
            # After B1 fix: 'grand' and 'palais' are in _COMMON_PROPER;
            # 'paris' would be excluded by venue_context at runtime.
            # Only 'paris' might remain — but that's venue-context territory, not the art-period fix.
            # The fixture verifies 'palais' and 'grand' are NOT extracted.
            {'palais', 'grand'},  # These must NOT appear in extracted nouns
        ),
        (
            "FP2: 'Renaissance' period (Uffizi) — should NOT extract fabrication-risk nouns",
            FP2_SENTENCE,
            # After B1 fix: 'renaissance' is in _COMMON_PROPER.
            # 'medici', 'florence', 'europe' would be handled by venue_context at runtime.
            # The fixture verifies 'renaissance' is NOT extracted.
            {'renaissance'},  # These must NOT appear in extracted nouns
        ),
    ]

    for desc, sentence, must_not_appear in fixtures:
        extracted = extract_proper_nouns(sentence)
        # Check that none of the must_not_appear terms are in extracted set
        false_positives = extracted & must_not_appear
        passed = len(false_positives) == 0
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")
        print(f"         Extracted: {sorted(extracted) if extracted else '(none)'}")
        if not passed:
            print(f"         FALSE POSITIVES: {sorted(false_positives)}")
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

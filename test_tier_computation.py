"""test_tier_computation.py — B3 boundary fixtures for the 4-tier degradation ladder.

Tests the tier computation logic from generate_tour_text.py (~line 930).
evidence_strength = unique QID count from SPARQL works.

Tier logic:
    if n_verified == 0:          -> 'unresolvable'
    elif evidence_strength >= 8: -> 'rich'
    elif evidence_strength >= 3: -> 'medium'
    else:                        -> 'thin'

This file reimplements the tier computation inline (the original is embedded
deep inside a large function) so it can run standalone without imports.
"""

import sys


# ---------------------------------------------------------------------------
# Inline reimplementation of tier computation (generate_tour_text.py ~line 930)
# ---------------------------------------------------------------------------

def compute_tier(n_verified: int, evidence_strength: int) -> str:
    """Return the degradation tier given verification count and evidence strength.

    Parameters
    ----------
    n_verified : int
        Number of verified entries (0 means entity could not be resolved).
    evidence_strength : int
        Number of unique QIDs returned from SPARQL works query.
    """
    if n_verified == 0:
        return "unresolvable"
    elif evidence_strength >= 8:
        return "rich"
    elif evidence_strength >= 3:
        return "medium"
    else:
        return "thin"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """Run all boundary fixtures. Returns True if all pass."""
    all_passed = True

    fixtures = [
        # (description, n_verified, evidence_strength, expected_tier)

        # 1. n_verified == 0 → unresolvable (regardless of evidence_strength)
        ("unresolvable: n_verified=0, evidence=0", 0, 0, "unresolvable"),
        ("unresolvable: n_verified=0, evidence=5", 0, 5, "unresolvable"),
        ("unresolvable: n_verified=0, evidence=10", 0, 10, "unresolvable"),

        # 2. evidence_strength 1-2 → thin (with n_verified > 0)
        ("thin: evidence=1", 1, 1, "thin"),
        ("thin: evidence=2", 3, 2, "thin"),

        # 3. evidence_strength 3-7 → medium (with n_verified > 0)
        ("medium: evidence=3 (boundary)", 1, 3, "medium"),
        ("medium: evidence=5", 2, 5, "medium"),
        ("medium: evidence=7 (boundary)", 1, 7, "medium"),

        # 4. evidence_strength >= 8 → rich (with n_verified > 0)
        ("rich: evidence=8 (boundary)", 1, 8, "rich"),
        ("rich: evidence=10", 2, 10, "rich"),
        ("rich: evidence=20", 5, 20, "rich"),
    ]

    for desc, n_verified, evidence_strength, expected in fixtures:
        result = compute_tier(n_verified, evidence_strength)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}  (got={result!r}, expected={expected!r})")
        if not passed:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("B3 Tier Computation — Boundary Fixtures")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    if success:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)

"""test_tier_computation.py — B3 boundary fixtures for the 4-tier degradation ladder.

Tests the compute_tier() function from generate_tour_text.py (module-level).
evidence_strength = unique QID count from SPARQL works.

Tier logic:
    if n_verified == 0:          -> 'unresolvable'
    elif evidence_strength >= 8: -> 'rich'
    elif evidence_strength >= 3: -> 'medium'
    else:                        -> 'thin'

Imports the PRODUCTION compute_tier — if the implementation drifts, this test catches it.
"""

import sys

# Import from production code (module-level function)
from generate_tour_text import compute_tier


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
    print("B3 Tier Computation — Boundary Fixtures (imports production code)")
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

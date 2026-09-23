#!/usr/bin/env python3
"""run_local3500_acceptance.py — LOCAL-3500 acceptance evidence.

Two phrasings of one venue must not be two paid generations. This driver CALLS
the real cache-key functions in tour_cache_layer1 (no source-grep, D418/D421) and
prints the real before/after keys and the must-not-merge results used in
SUBMISSION_LOCAL-3500.md. No DB, no network.

The string-normalisation fix (_normalize_location / _cache_key / _legacy_cache_key)
already lives in tour_cache_layer1 (delivered under LOCAL-500, the same defect
class). LOCAL-3500 is the acceptance for it: prove the Picasso pair collapses,
prove the different-venue pairs stay distinct, and confirm legacy fallback.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_cache_layer1 as c

TOUR_TYPE = "museum"
STOPS = 3

# The exact strings from tour_cache, differing only by accents.
PICASSO_A = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
PICASSO_B = "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"

# Pairs that MUST NOT merge — different venues.
MUST_NOT_MERGE = [
    ("Musee Matisse, Nice", "Musee Marc Chagall, Nice"),
    ("Boston Logan International Airport", "Boston Common"),
    ("Sacred Heart Parish, Newton", "Our Lady Help of Christians, Newton"),
]


def main() -> int:
    ok = True

    print("=" * 78)
    print("ACCEPTANCE 1 - the Picasso pair produces the SAME key (real strings)")
    print("=" * 78)
    old_a = c._legacy_cache_key(PICASSO_A, TOUR_TYPE, STOPS)
    old_b = c._legacy_cache_key(PICASSO_B, TOUR_TYPE, STOPS)
    new_a = c._cache_key(PICASSO_A, TOUR_TYPE, STOPS)
    new_b = c._cache_key(PICASSO_B, TOUR_TYPE, STOPS)
    print(f"A: {PICASSO_A!r}")
    print(f"B: {PICASSO_B!r}")
    print(f"(tour_type={TOUR_TYPE}, total_stops={STOPS})\n")
    print("OLD key (.strip().lower()):")
    print(f"  A  {old_a}")
    print(f"  B  {old_b}   -> {'DIFFERENT (the bug)' if old_a != old_b else 'same'}")
    print("NEW key (normalised):")
    print(f"  A  {new_a}")
    print(f"  B  {new_b}   -> {'IDENTICAL (fixed)' if new_a == new_b else 'DIFFERENT'}")
    print(f"\nNEW normalised form (both): {c._normalize_location(PICASSO_A)!r}")
    if not (old_a != old_b and new_a == new_b):
        ok = False
        print("  !! FAIL")

    print()
    print("=" * 78)
    print("ACCEPTANCE 2 - different venues must NOT merge")
    print("=" * 78)
    for x, y in MUST_NOT_MERGE:
        kx = c._cache_key(x, "walking", 5)
        ky = c._cache_key(y, "walking", 5)
        distinct = kx != ky
        print(f"  {'OK ' if distinct else 'FAIL'}  {x!r}")
        print(f"        vs {y!r}  -> {'distinct' if distinct else 'MERGED (bug)'}")
        if not distinct:
            ok = False

    print()
    print("=" * 78)
    print("ACCEPTANCE 3 - legacy (pre-normalisation) key still resolvable")
    print("=" * 78)
    import hashlib
    loc, tt, n = "Some Place, MA", "museum", 4
    raw = f"{loc.strip().lower()}|{tt.strip().lower()}|{n}"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    legacy = c._legacy_cache_key(loc, tt, n)
    print(f"  _legacy_cache_key reproduces the old formula exactly: "
          f"{'OK' if legacy == expected else 'FAIL'}")
    print(f"    {legacy}")
    if legacy != expected:
        ok = False

    print()
    print("=" * 78)
    print("RESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

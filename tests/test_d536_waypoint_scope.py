"""[D536] "with a stop at X" makes X a waypoint, not the tour's boundary.

The 2026-08-27 Riviera run, verbatim:

    request : "Biking tour in French Riviera with a stop at Hippodrome de la Cote
               d'Azur starting from Nice, France"          (5 stops requested)
    intent  : location = "French Riviera"                  ← correct
              geographic_scope = "Hippodrome de la Cote d'Azur"
              scope_precision  = "BUILDING"
    PHASE 5.6 removed 3 stops for being "outside 'Hippodrome de la Cote d'Azur'"

Every removal was correct — a racecourse is not inside another racecourse. The
CHECK was right and the SCOPE was wrong, and a 5-stop request delivered 2.

This is deterministic on purpose. It is a fact about English phrasing, and
D526/D528 record six occasions in one day where a rule of this shape was handed
to a model and came back fitted to its single example.

Run:  python3 tests/test_d536_waypoint_scope.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import named_waypoints, scope_is_a_waypoint

RIVIERA = ("Biking tour in French Riviera with a stop at Hippodrome de la Cote d'Azur "
           "starting from Nice, France")

# (scope proposed by intent, request, must_refuse, why)
CASES = [
    ("Hippodrome de la Cote d'Azur", RIVIERA, True,
     "THE CASE. Named as a stop; it cannot contain the tour that visits it."),
    ("Hippodrome de la Côte d'Azur", RIVIERA, True,
     "Same place, accented as the venue writes it. Accent-folding must hold."),
    ("hippodrome de la cote d azur", RIVIERA, True,
     "Case and punctuation must not defeat it."),

    ("French Riviera", RIVIERA, False,
     "The tour's actual extent. Must NOT be refused — refusing every scope is "
     "just as broken as accepting a waypoint."),
    ("Musée du Louvre", "Walking tour of the Musée du Louvre, Paris", False,
     "No waypoint phrasing at all. A venue tour's venue IS its scope."),
    ("Montmartre", "Walking tour of Montmartre, Paris, France", False,
     "Ordinary district scope, no 'stop at' phrasing."),
    ("Nice", RIVIERA, False,
     "'starting from Nice' is an ORIGIN, not a 'stop at'. Must not be caught."),
]


def main():
    failures = []
    print("[D536] waypoint vs scope\n")

    print("  -- waypoint extraction --")
    w = named_waypoints(RIVIERA)
    ok = any('hippodrome' in x.lower() for x in w)
    print(f"  {'OK ' if ok else 'FAIL'} extracted {w}")
    if not ok:
        failures.append('extraction')
    # The origin must not be swept up with it.
    ok = not any(x.strip().lower() == 'nice' for x in w)
    print(f"  {'OK ' if ok else 'FAIL'} 'starting from Nice' not treated as a waypoint")
    if not ok:
        failures.append('origin captured')

    print("\n  -- refuse / accept --")
    for scope, req, must_refuse, why in CASES:
        got = scope_is_a_waypoint(scope, req)
        ok = (got == must_refuse)
        verdict = 'REFUSE' if got else 'ACCEPT'
        want = 'REFUSE' if must_refuse else 'ACCEPT'
        print(f"  {'OK ' if ok else 'FAIL'} {scope[:36]:38s} want={want:6s} got={verdict}")
        if not ok:
            print(f"       {why}")
            failures.append(scope[:30])

    print("\n  -- other waypoint phrasings --")
    more = [
        ("Cycling tour of Provence including a stop at Pont du Gard", "Pont du Gard", True),
        ("Walking tour of Rome with stops at the Pantheon", "Pantheon", True),
        ("Driving tour of Tuscany stopping at Siena, Italy", "Siena", True),
    ]
    for req, scope, must in more:
        got = scope_is_a_waypoint(scope, req)
        ok = got == must
        print(f"  {'OK ' if ok else 'FAIL'} {scope[:24]:26s} in \"{req[:44]}...\"")
        if not ok:
            failures.append(scope)

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

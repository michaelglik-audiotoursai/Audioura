"""[D533] Cross-stop FACT repetition — Michael, 2026-08-26:

  "make sure the same facts are not repeated not only in the same sentence and in
   the same stop, but across all stops: listener should not listen the same story
   many times."

The existing sentence-Jaccard check scored the real Palais Lascaris pair at
**0.692** against a 0.70 threshold and let it through. This suite fixes the
target on facts instead, and — more importantly — pins the three false-positive
shapes that made the first implementation useless:

  * stop headers, Coordinates:, Directions: lines are scaffolding, not facts
  * the closing recap's JOB is to mention earlier stops again
  * a sentence listing three works with three dates asserts a LIST, not nine
    facts, and must not make every later stop look like a repeat

Run:  python3 tests/test_d533_cross_stop_facts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from derepetition_guard import (check_cross_stop_fact_repetition,
                                strip_repeated_facts, fact_signatures)

# The real defect, reduced: the museum's 1942 purchase told at stop 1 and again
# at stop 3, in DIFFERENT WORDS (Jaccard 0.692 — under the old threshold).
TOUR = """Tour-Category: museum

Stop 1: Harpe by Naderman (Paris, 1780)

Coordinates: 43.6971, 7.2704

Orientation: Stand before the harp, built by Jean-Henri Naderman.

In 1942, the city of Nice purchased the Palais Lascaris, a seventeenth-century aristocratic building, with the goal of transforming it into a museum. The harp is strung with gut and stands five feet tall, its column carved with acanthus. Naderman supplied the French court and his workshop set the pattern for the single-action pedal harp.

Directions: Continue to Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581).

Stop 2: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)

Coordinates: 43.6971, 7.2704

Orientation: Pause before the sackbut of 1581.

Schnitzer worked in Nuremberg, a city whose brass workshops supplied courts across Europe. The instrument survives in original condition, its bell unrepaired, which is why it anchors the collection.

Directions: Your final stop is Violes gambe by William Turner (Londres, 1652).

Stop 3: Violes gambe by William Turner (Londres, 1652)

Coordinates: 43.6971, 7.2704

Orientation: Stand before the viol.

In 1942, the city of Nice purchased the seventeenth-century Palais Lascaris with the intention of transforming it into a museum. Turner carved a heart into the back of the scroll, a flourish he repeated on instruments dated between 1647 and 1656. The viol is still played at concerts held in the palace salons.

That's 3 stops — the Palais Lascaris showcases a 1581 Sacqueboute by Anton Schnitzer and a 1652 viol by William Turner.
"""


def main():
    failures = []
    print("[D533] cross-stop fact repetition\n")

    repeats = check_cross_stop_fact_repetition(TOUR)
    sigs = {r['signature'] for r in repeats}

    print("  -- must detect the repeated fact --")
    hit = any(s.startswith('1942/') for s in sigs)
    print(f"  {'OK ' if hit else 'FAIL'} 1942 purchase flagged as told twice  (found: {sorted(sigs)})")
    if not hit:
        failures.append('1942 not detected')

    print("\n  -- must NOT flag the scaffolding or the recap --")
    checks = [
        ("no stop-header repeat", not any('sacqueboute' in s and '1581' in s for s in sigs)),
        ("no Directions: repeat", not any(r['sentence'].strip().startswith('Directions:') for r in repeats)),
        ("no Coordinates: repeat", not any('Coordinates' in r['sentence'] for r in repeats)),
        ("no closing-recap repeat", not any("That's 3 stops" in r['sentence'] for r in repeats)),
        ("only the 1942 fact repeats", all(s.startswith('1942/') for s in sigs)),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- list-shaped sentences assert no facts --")
    listy = ("Among the treasures are the Harpe by Naderman (Paris, 1780), the "
             "Sacqueboute by Anton Schnitzer (Nuremberg, 1581), and the Violes "
             "gambe by William Turner (Londres, 1652).")
    cond = fact_signatures(listy) == set()
    print(f"  {'OK ' if cond else 'FAIL'} three-date list yields no signatures "
          f"(got {len(fact_signatures(listy))})")
    if not cond:
        failures.append('list sentence')

    print("\n  -- repair removes the SECOND telling only --")
    out, actions = strip_repeated_facts(TOUR)
    removed = [a for a in actions if a['removed']]
    checks = [
        ("exactly one removal", len(removed) == 1),
        ("stop 1 telling kept", "with the goal of transforming it into a museum" in out),
        ("stop 3 telling gone", "with the intention of transforming it into a museum" not in out),
        ("stop 3 keeps its other content", "heart into the back of the scroll" in out),
        ("stop 3 keeps its last sentence", "still played at concerts" in out),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- a thin stop keeps its repeat rather than emptying --")
    thin = TOUR.replace(
        "Turner carved a heart into the back of the scroll, a flourish he repeated "
        "on instruments dated between 1647 and 1656. The viol is still played at "
        "concerts held in the palace salons.", "")
    _, thin_actions = strip_repeated_facts(thin)
    cond = any(not a['removed'] and 'minimum' in a['reason'] for a in thin_actions)
    print(f"  {'OK ' if cond else 'FAIL'} repeat retained, reason reported")
    if not cond:
        failures.append('thin-stop guard')

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

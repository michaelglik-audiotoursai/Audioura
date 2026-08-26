"""[D533] The birth-year fabrication guard, on the real Palais Lascaris text.

Michael, 2026-08-26: "Please fix the fabrication."

The case is verbatim from that run — corpus and tour sentence both as they were.
The suite also scores the direction that matters more than catching it: the guard
must NOT delete legitimate sentences, because a guard that deletes real content
to look effective is worse than the defect.

Run:  python3 tests/test_d533_fact_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_fact_guard import (find_role_mismatches, repair_role_mismatches,
                              corpus_roles_for_year, split_sentences)

# Verbatim from the 2026-08-26 run's retrieved passage.
CORPUS = (
    "The Palais Lascaris holds around 500 musical instruments. "
    "Antoine Gautier, a passionate collector and amateur musician born in Nice in 1825, "
    "played a pivotal role in the formation of the collection. "
    "In 1942, the city of Nice purchased the Palais Lascaris. "
    "Jean-Henri Naderman was harp maker to Marie Antoinette in Paris."
)

MUST_FLAG = [
    ("...from Naderman's harp studio to the quartet founded by Antoine Gautier in 1825.",
     "THE CASE. Corpus says Gautier was BORN in 1825; the tour has him founding a "
     "quartet that year."),
    ("The collection was established by Antoine Gautier in 1825 for the city.",
     "Same role swap, different action verb."),
]

MUST_NOT_FLAG = [
    ("Antoine Gautier was born in Nice in 1825 and later founded a quartet.",
     "The sentence states the birth role ITSELF. True, and must survive."),
    ("In 1942, the city of Nice purchased the Palais Lascaris.",
     "Corpus agrees exactly. A purchase in 1942, no person-year role involved."),
    ("Jean-Henri Naderman crafted this harp in 1780 for the French court.",
     "Corpus says nothing about Naderman and 1780 — SILENCE. Silence is not a "
     "contradiction; flagging this would make the guard a content shredder."),
    ("Antoine Gautier bequeathed his collection to the city in 1901.",
     "A real action in a year the corpus does not call his birth. Must survive."),
]


def main():
    failures = []
    print("[D533] person-year role guard\n")

    print("  -- corpus role lookup --")
    roles = corpus_roles_for_year("Antoine Gautier", "1825", CORPUS)
    ok = roles == ['birth']
    print(f"  {'OK ' if ok else 'FAIL'} Gautier+1825 -> {roles} (want ['birth'])")
    if not ok:
        failures.append('corpus_roles_for_year')

    silent = corpus_roles_for_year("Antoine Gautier", "1901", CORPUS)
    ok = silent == []
    print(f"  {'OK ' if ok else 'FAIL'} Gautier+1901 -> {silent} (want [] = silence)")
    if not ok:
        failures.append('silence')

    print("\n  -- must flag --")
    for sent, why in MUST_FLAG:
        f = find_role_mismatches(sent, CORPUS)
        ok = len(f) > 0
        print(f"  {'OK ' if ok else 'FAIL'} {sent[:58]}")
        if not ok:
            print(f"       {why}")
            failures.append(sent[:40])

    print("\n  -- must NOT flag --")
    for sent, why in MUST_NOT_FLAG:
        f = find_role_mismatches(sent, CORPUS)
        ok = len(f) == 0
        print(f"  {'OK ' if ok else 'FAIL'} {sent[:58]}")
        if not ok:
            print(f"       {why}")
            print(f"       flagged as: {f[0]['person']}/{f[0]['year']}/{f[0]['action']}")
            failures.append(sent[:40])

    print("\n  -- repair removes the sentence and keeps the rest --")
    tour = ("Stand before the harp. " + MUST_FLAG[0][0] +
            " The harp is strung with gut and stands five feet tall.")
    repaired, found = repair_role_mismatches(tour, CORPUS)
    checks = [
        ("offending sentence gone", "founded by Antoine Gautier in 1825" not in repaired),
        ("preceding sentence kept", "Stand before the harp." in repaired),
        ("following sentence kept", "strung with gut" in repaired),
        ("repair reported", bool(found) and found[0].get('repaired')),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- splitter does not break on initials (D525) --")
    s = split_sentences("L. Rosenberg planned it. Then it opened.")
    ok = len(s) == 2 and s[0].startswith("L. Rosenberg")
    print(f"  {'OK ' if ok else 'FAIL'} {s}")
    if not ok:
        failures.append('splitter')

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

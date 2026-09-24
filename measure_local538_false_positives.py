#!/usr/bin/env python3
"""LOCAL-538 false-positive measurement — run both new checks over every tour in
TOURS_FOR_REVIEW and list every hit with its sentence. Measured, not asserted.

The standard to match is LOCAL-530's: "fires exactly twice, both true positives"
across the corpus. Here each check must fire on its one known defect and nowhere
else. This script prints every hit so a reviewer can mark each TP or FP by reading
the sentence.
"""
import glob
import os

import tour_quality as tq

ROOT = os.path.dirname(os.path.abspath(__file__))
FILES = sorted(glob.glob(os.path.join(ROOT, 'TOURS_FOR_REVIEW', '**', '*.txt'),
                         recursive=True))

print(f"Scanned {len(FILES)} tour files under TOURS_FOR_REVIEW/\n")

a_hits, b_hits = [], []
for f in FILES:
    rel = os.path.relpath(f, os.path.join(ROOT, 'TOURS_FOR_REVIEW'))
    txt = open(f, encoding='utf-8').read()
    for relnoun, span in tq._find_relational_no_complement(txt):
        a_hits.append((rel, relnoun, span))
    for kind, snippet in tq._find_dangling_references(txt):
        b_hits.append((rel, kind, snippet))

print("=" * 78)
print("CHECK A — relational noun with no complement (dangling_complement)")
print("=" * 78)
for rel, relnoun, span in a_hits:
    print(f"  [{rel}]  '{relnoun}'")
    print(f"      {span!r}")
print(f"  TOTAL A HITS: {len(a_hits)}\n")

print("=" * 78)
print("CHECK B — demonstrative / pronoun with no antecedent (dangling_reference)")
print("=" * 78)
for rel, kind, snippet in b_hits:
    print(f"  [{rel}]  ({kind})")
    print(f"      {snippet!r}")
print(f"  TOTAL B HITS: {len(b_hits)}\n")

print("=" * 78)
print(f"COMBINED HITS: {len(a_hits) + len(b_hits)}")
print("Expected: 1 (A: round9/LOGAN_1) + 1 (B: round9/CHURCH_1) = 2, both TPs.")
print("=" * 78)

#!/usr/bin/env python3
"""Attribute tour_cache row collapse to its CAUSE (LOCAL-3500 vs LOCAL-494).

The live cache key folds in TWO independent changes:
  * LOCAL-3500/LOCAL-500: normalise the location STRING (accent/punct/space).
  * LOCAL-494: bucket the stop COUNT.

LOCAL-3500's acceptance criterion 4 asks specifically about the STRING fix. This
script separates the two effects so the report is honest:

  new_full   = _cache_key                       (string norm + stop bucket)
  new_string = normalize(location)|type|EXACT   (string norm ONLY, no bucketing)
  legacy     = _legacy_cache_key                (neither)

A group collapses "by string" if two rows that were distinct under the legacy key
share the same key once ONLY the string is normalised (exact stop count kept).
"""
import hashlib
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tour_cache_layer1 as c

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tour_cache_rows.tsv"


def string_only_key(location, tour_type, total_stops):
    """String-normalised location + type + EXACT stop count (no bucket)."""
    raw = f"{c._normalize_location(location)}|{tour_type.strip().lower()}|{total_stops}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


rows = []
with open(path, encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append((parts[0], parts[1], parts[2]))

total = len(rows)

by_legacy = defaultdict(list)
by_string = defaultdict(list)
by_full = defaultdict(list)
for loc, tt, ns in rows:
    by_legacy[c._legacy_cache_key(loc, tt, ns)].append((loc, tt, ns))
    by_string[string_only_key(loc, tt, ns)].append((loc, tt, ns))
    by_full[c._cache_key(loc, tt, ns)].append((loc, tt, ns))

string_collapse = {k: v for k, v in by_string.items() if len(v) > 1}
full_collapse = {k: v for k, v in by_full.items() if len(v) > 1}

# String-attributable groups: those where the collapse survives WITHOUT bucketing.
print(f"Total rows:                          {total}")
print(f"Distinct under legacy key:           {len(by_legacy)}")
print(f"Distinct under STRING-only key:      {len(by_string)}   "
      f"(net {total - len(by_string)} removed by string normalisation alone)")
print(f"Distinct under FULL key (string+bucket): {len(by_full)}   "
      f"(net {total - len(by_full)} removed by both)")
print()
print("Groups that collapse from STRING normalisation ALONE (LOCAL-3500 scope):")
found = False
for k, v in string_collapse.items():
    # Only interesting if the rows have DIFFERENT raw location spellings.
    distinct_locs = {loc for loc, _, _ in v}
    if len(distinct_locs) > 1:
        found = True
        print(f"  [{len(v)} rows] key={k[:12]}...")
        for loc, tt, ns in v:
            print(f"      - {loc!r} | {tt} | {ns}")
if not found:
    print("  (none beyond the ones already shown)")

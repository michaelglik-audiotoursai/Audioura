#!/usr/bin/env python3
"""replay_local661_ab6_639.py — offline replay of the Bench AB6 tour-639 call
sequence (run_ON-3.log) proving the Wikimedia-429 path flip no longer happens.

NO NETWORK. The real log is parsed to reconstruct the exact call sequence; the
patched venue_resolver is then driven with a fault injector that reproduces the
log's mechanism, and we assert the SECOND resolution now keeps the collection
QID instead of flipping to the LOCAL-599 "No Wikidata entity" path.

The log's mechanism (run_ON-3.log, tour 639):
  line  74  [venue_resolver] Resolved: 'The Frick Collection' → Q682827   (clean)
  line  81  [venue_resolver] SPARQL: 211 works found for Q682827          (clean)
  line  88  [LOCAL-230] _get_coordinates failed: HTTP 429 for qid 'Q1384' (429 storm)
  line  92  Single candidate Q682827 … city validation UNKNOWN (network/429);
            keeping high-confidence candidate                             (kept!)
  line 102  [LOCAL-599] No Wikidata entity for 'The Frick Collection' — …
            exhibition-museum site-first path ELIGIBLE                    ← THE FLIP

So resolve #2 kept Q682827 through geo-validation, but then step-4
_fetch_entity_properties (a raw GET with no backoff) returned None on the 429,
so resolve_venue() returned None and the deterministic block read it as
"no Wikidata entity". The LOCAL-661 memo intercepts exactly this None.

Usage:
  python3 replay_local661_ab6_639.py                       # auto-finds the log
  python3 replay_local661_ab6_639.py /path/to/run_ON-3.log

Exit status 0 == the flip is gone (resolve #2 keeps Q682827). Non-zero == FLIP.
"""
import os
import re
import sys

import venue_resolver as vr

DEFAULT_LOG = os.path.expanduser(
    "~/Audioura/.continuous_dev/bench/AB6/run_ON-3.log")

VENUE = "The Frick Collection"
CITY = "New York"
EXPECT_QID = "Q682827"


def parse_log(path):
    """Extract the ordered events we care about from the real log."""
    events = []
    pat = [
        (re.compile(r"Resolved: '(.+?)' → (Q\d+)"), "resolved"),
        (re.compile(r"SPARQL: (\d+) works found for (Q\d+)"), "works"),
        (re.compile(r"HTTP 429"), "http429"),
        (re.compile(r"city validation UNKNOWN"), "city_unknown"),
        (re.compile(r"\[LOCAL-599\] No Wikidata entity for '(.+?)'"), "flip599"),
        (re.compile(r"site-first path ELIGIBLE"), "site_first"),
    ]
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            for rx, kind in pat:
                m = rx.search(line)
                if m:
                    events.append((i, kind, m.groups()))
                    break
    return events


def summarise(events):
    print("── Parsed call sequence from the real log ──")
    for ln, kind, groups in events:
        if kind in ("resolved", "works", "flip599"):
            print(f"  line {ln:>4}  {kind:<12} {groups}")
        elif kind in ("http429", "city_unknown", "site_first"):
            print(f"  line {ln:>4}  {kind}")
    # Confirm the log actually contains the defect we are fixing.
    kinds = [k for _, k, _ in events]
    assert "resolved" in kinds, "log did not contain a clean resolution"
    assert "http429" in kinds, "log did not contain a 429"
    assert "flip599" in kinds, "log did not contain the LOCAL-599 flip"
    print("  → log confirms: clean resolve, then a 429, then the LOCAL-599 flip.\n")


def replay(events):
    """Drive the PATCHED resolve_venue with the log's fault mechanism."""
    # Count how many resolutions of the Frick the log implies before the flip:
    # the clean one (line 74) and the re-resolution during the storm (line ~96).
    orig_impl = vr._resolve_venue_impl
    state = {"n": 0}

    def _impl(venue, city=""):
        state["n"] += 1
        if state["n"] == 1:
            # line 74: clean resolution.
            return vr.VenueEntity(qid=EXPECT_QID, name=VENUE,
                                  official_url="https://www.frick.org",
                                  lat=40.771, lng=-73.967)
        # line 96: re-resolution during the 429 storm. Geo-validation keeps the
        # candidate (line 92), but step-4 _fetch_entity_properties GETs under the
        # 429 and returns None → the impl returns None AND a Wikidata search/GET
        # failure was counted (exactly as _get_coordinates/_search_entities do).
        vr._network_failure_count += 1
        return None

    vr._resolve_venue_impl = _impl
    token = vr.begin_resolution_scope()
    vr.reset_network_failure_count()
    try:
        r1 = vr.resolve_venue(VENUE, CITY)
        print(f"  resolve #1 (log line 74): → "
              f"{r1.qid if r1 else None}  [clean]")
        r2 = vr.resolve_venue(VENUE, CITY)
        got = r2.qid if r2 else None
        flipped = r2 is None or not getattr(r2, "qid", "")
        print(f"  resolve #2 (log line ~96, under 429): → {got}  "
              f"[{'FLIP → LOCAL-599 no-entity path' if flipped else 'collection path KEPT'}]")
        return r1, r2, flipped
    finally:
        vr._resolve_venue_impl = orig_impl
        vr.end_resolution_scope(token)


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    if not os.path.exists(log):
        print(f"ERROR: log not found: {log}")
        return 2
    print(f"Replaying: {log}\n")
    events = parse_log(log)
    summarise(events)

    print("── Replaying the sequence against the PATCHED resolve_venue ──")
    r1, r2, flipped = replay(events)
    print()

    ok = (r1 is not None and r1.qid == EXPECT_QID
          and r2 is not None and r2.qid == EXPECT_QID and not flipped)
    if ok:
        print("RESULT: PASS — resolve #2 kept the resolved QID "
              f"{EXPECT_QID} under the 429. The LOCAL-599 'No Wikidata entity' "
              "flip that the log recorded no longer happens; the collection path "
              "is retained.")
        return 0
    print("RESULT: FAIL — the flip reproduced (resolve #2 did not keep the QID).")
    return 1


if __name__ == "__main__":
    sys.exit(main())

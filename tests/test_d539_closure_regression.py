"""[D539] The learning mechanism — Michael, 2026-08-27:

  "Is there a mechanism for us to learn to make sure we do validate stops?"

There was not. This is it.

`known_closed_venues.json` holds every venue that SHIPPED IN A TOUR and turned out
not to be visitable. Each entry is a real miss found by a human. This suite replays
them on every change, so a defect reality has already caught can never come back
quietly.

The first entry is La Marée Monaco: closed 30 September 2020, shipped as stop 3 of
the Monaco tour, cleared by the closure check that was supposed to catch exactly
this. Michael found it by searching the name himself.

**The lesson encoded here is not "the model was wrong".** It is that the SAME
restaurant returned OPPOSITE verdicts depending on the spelling searched, because
closure notices and stale "open 7 days a week" listings coexist on the web. A
verdict formed by weighing one against the other is decided by whichever snippets
SERP happens to return. So closure is now DECISIVE and probed across spelling
variants by deterministic string match, not by asking a model which page to trust.

Run:  OPENAI_API_KEY=... SERP_API_KEY=... python3 tests/test_d539_closure_regression.py

Offline (no keys) it still checks the corpus is well-formed and that the marker
list covers the phrasings we have actually seen.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from restaurant_practicals import (closure_scan, venue_still_operating,
                                   fetch_practicals, _CLOSED_MARKERS)

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'known_closed_venues.json')


def main():
    failures = []
    data = json.load(open(CORPUS, encoding='utf-8'))
    venues = data['venues']
    print(f"[D539] closure regression — {len(venues)} venue(s) reality has caught us on\n")

    print("  -- corpus is well-formed --")
    for v in venues:
        ok = all(k in v for k in ('name', 'city', 'expect', 'why_it_was_missed'))
        print(f"  {'OK ' if ok else 'FAIL'} {v.get('name','?')[:34]:36s} expect={v.get('expect')}")
        if not ok:
            failures.append(f"malformed: {v.get('name')}")

    print("\n  -- the marker list covers the phrasings actually observed --")
    observed = [
        "La Marée Monaco. Permanently closed. 1615 votes.",
        "The restaurant has closed down after a lease dispute.",
        "Ce restaurant est définitivement fermé.",
    ]
    for snip in observed:
        hit = any(m in snip.lower() for m in _CLOSED_MARKERS)
        print(f"  {'OK ' if hit else 'FAIL'} matches: {snip[:56]}")
        if not hit:
            failures.append(f"marker miss: {snip[:30]}")

    print("\n  -- a normal description must NOT trip the markers --")
    safe = [
        "The restaurant is closed on Mondays and Tuesdays.",
        "The kitchen closed at 22:30 and reopens for lunch.",
        "Located near the closed-off pedestrian street.",
    ]
    for snip in safe:
        hit = any(m in snip.lower() for m in _CLOSED_MARKERS)
        print(f"  {'OK ' if not hit else 'FAIL'} ignores: {snip[:56]}")
        if hit:
            print("       a weekly closing day is not a permanent closure — this would "
                  "delete every restaurant that shuts on Mondays")
            failures.append(f"false positive: {snip[:30]}")

    if not (os.environ.get('SERP_API_KEY') and os.environ.get('OPENAI_API_KEY')):
        print("\n  (SERP_API_KEY / OPENAI_API_KEY not set — live replay skipped)")
        print()
        if failures:
            print(f"FAILED: {failures}")
            return 1
        print("OFFLINE CHECKS PASSED (live replay not run)")
        return 0

    api_key = os.environ['OPENAI_API_KEY']
    print("\n  -- live replay: every spelling must reach the same verdict --")
    for v in venues:
        if v['expect'] != 'closed':
            print(f"  ..  {v['name'][:34]:36s} expect={v['expect']} — not asserted, skipped")
            continue
        for name in [v['name']] + v.get('aliases', []):
            # [D540] Production asks BOTH questions: has it closed, and does it
            # still trade under this name? Le Vistamar answers no only to the
            # second — a rebrand carries no closure words.
            closed, _ = closure_scan(name, v['city'])
            operating, detail = (True, '') if closed else venue_still_operating(name, v['city'])
            gone = closed or not operating
            print(f"  {'OK ' if gone else 'FAIL'} {name[:28]!r:30s} -> gone={gone} "
                  f"(closed={closed}, operating={operating})")
            if not gone:
                print(f"       {v['why_it_was_missed'][:150]}")
                failures.append(f"{name}: not detected")
        p = fetch_practicals(v['name'], v['city'], api_key)
        ok = not p['deliverable']
        print(f"  {'OK ' if ok else 'FAIL'} fetch_practicals -> deliverable={p['deliverable']} "
              f"({p['reason'][:70]})")
        if not ok:
            failures.append(f"{v['name']}: still deliverable")

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

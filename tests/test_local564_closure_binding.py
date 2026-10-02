"""[LOCAL-564] A closure reported for a DIFFERENT place or a DIFFERENT subject
must not drop a live venue.

Two live Boston restaurants were dropped by the LOCAL-563 Gemini baseline, each
on a closure notice that was not about them:

    Chart House, Boston     "Chart House, a riverfront staple in Weehawken, New
                             Jersey, has closed as of May 14. A Mastro's
                             Steakhouse is planned for the site."
                            -> WRONG CITY (Weehawken, New Jersey vs Boston, MA)

    Buttermilk & Bourbon,   "BarLola in Boston's Back Bay Has Closed; Buttermilk
    Boston                   & Bourbon to Replace It ..."
                            -> WRONG SUBJECT (BarLola closed; Buttermilk is the
                               successor named by "to Replace It")

The exact snippets are lifted from tests/fixtures/local563/runs/*.log on branch
LOCAL-563-gemini-baseline. The acceptance adds four more:

    "Chart House Boston has closed"            -> closed (place + subject match)
    "Sycamore in Newton Centre ... closed"     -> closed
    the D544 Newton listicle                   -> NOT closed (headline is another)
    "La Marée Monaco. Permanently closed."     -> closed (real 2020 closure)

Every case is checked against the PURE function `_closure_binds`, and the two
headline bugs are also driven through `closure_scan` with a stubbed SERP so the
end-to-end path is covered.

Run:  python3 tests/test_local564_closure_binding.py
      (offline — no API keys, no network)

RED BEFORE / GREEN AFTER: against the pre-fix closure_scan, Chart House bound
(city key was the venue's own last word "house") and Buttermilk bound (name and
marker shared a sentence). `_closure_binds` did not exist. This suite is the
executable statement of the fix.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import restaurant_practicals as rp
from restaurant_practicals import _closure_binds, closure_scan


# (label, snippet, title, url, venue, city/location, expect_closed)
CASES = [
    # ---- the two shipped defects: must NOT bind ----
    ("Chart House — Weehawken NJ notice, stop is Boston MA",
     "Chart House, a riverfront staple in Weehawken, New Jersey, has closed as of "
     "May 14. A Mastro's Steakhouse is planned for the site.",
     "", "https://www.northjersey.com/story/x",
     "Chart House", "restaurant tour of Chart House, Boston, MA", False),

    ("Buttermilk & Bourbon — BarLola closed, Buttermilk is the successor",
     "BarLola in Boston's Back Bay Has Closed; Buttermilk & Bourbon to Replace It "
     "Several weeks ago, we reported that a Southern-style restaurant with a well...",
     "BarLola in Boston's Back Bay Has Closed; Buttermilk & Bourbon to Replace It",
     "https://boston.eater.com/x",
     "Buttermilk & Bourbon",
     "restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, MA", False),

    # ---- genuine closures: must bind ----
    ("Chart House Boston genuinely closed",
     "Chart House Boston has closed its doors for good after decades on the waterfront.",
     "", "", "Chart House", "restaurant tour of Chart House, Boston, MA", True),

    ("Sycamore in Newton Centre genuinely closed",
     "Sycamore in Newton Centre has permanently closed after a long run.",
     "", "", "Sycamore", "restaurant tour of Sycamore, Newton Centre, MA", True),

    # ---- D544 listicle: headline is about another restaurant: must NOT bind ----
    ("Newton listicle — headline closure is a different restaurant",
     "Newton restaurant permanently closed after 10 years. Alison... Sycamore in "
     "Newton Center: Cook in Newtonville; Fiorella's in Newtonville.",
     "Newton restaurant permanently closed after 10 years",
     "", "Sycamore", "restaurant tour of Sycamore, Newton Centre, MA", False),

    # ---- La Marée's real 2020 closure snippet: must still bind ----
    ("La Marée Monaco — real 2020 closure",
     "La Marée Monaco. Permanently closed. 1615 votes.",
     "", "", "La Marée", "restaurant tour of La Marée restaurant, Monaco", True),
]


def _run_binds():
    failures = []
    print("  -- _closure_binds: place-match + subject-match --")
    for label, snip, title, url, venue, city, expect in CASES:
        binds, reason = _closure_binds(snip, title, url, venue, city)
        ok = (binds == expect)
        print(f"  {'OK ' if ok else 'FAIL'} {label}")
        print(f"        binds={binds} expect={expect}  reason={reason!r}")
        if not ok:
            failures.append(label)
    return failures


def _run_scan():
    """Drive the two headline bugs through closure_scan with a stubbed SERP.

    closure_scan builds its own queries and calls _serp; we replace _serp so the
    test is deterministic and offline, and prove the end-to-end verdict.
    """
    print("\n  -- closure_scan end-to-end (stubbed SERP) --")
    failures = []

    scenarios = [
        ("Chart House", "restaurant tour of Chart House, Boston, MA", False, [
            {"snippet": "Chart House, a riverfront staple in Weehawken, New Jersey, "
                        "has closed as of May 14. A Mastro's Steakhouse is planned "
                        "for the site.",
             "title": "", "url": "https://www.northjersey.com/story/x"},
        ]),
        ("Buttermilk & Bourbon",
         "restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, MA", False, [
            {"snippet": "BarLola in Boston's Back Bay Has Closed; Buttermilk & "
                        "Bourbon to Replace It Several weeks ago, we reported...",
             "title": "BarLola in Boston's Back Bay Has Closed; Buttermilk & "
                      "Bourbon to Replace It",
             "url": "https://boston.eater.com/x"},
        ]),
        ("La Marée", "restaurant tour of La Marée restaurant, Monaco", True, [
            {"snippet": "La Marée Monaco. Permanently closed. 1615 votes.",
             "title": "", "url": "https://restaurantguru.com/la-maree"},
        ]),
    ]

    orig_serp = rp._serp
    try:
        for venue, city, expect_closed, items in scenarios:
            rp._serp = lambda q, max_results=8, _items=items: list(_items)
            closed, ev = closure_scan(venue, city)
            ok = (closed == expect_closed)
            print(f"  {'OK ' if ok else 'FAIL'} closure_scan({venue!r}) -> "
                  f"closed={closed} expect={expect_closed}")
            if ev:
                print(f"        evidence: {ev[:90]}")
            if not ok:
                failures.append(f"closure_scan {venue}")
    finally:
        rp._serp = orig_serp
    return failures


def main():
    print("[LOCAL-564] closure binding — place + subject match\n")
    failures = _run_binds() + _run_scan()
    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

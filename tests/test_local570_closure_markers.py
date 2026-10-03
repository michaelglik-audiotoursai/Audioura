"""[LOCAL-570] Closure markers: "closing for good" and its kin.

LEAD's review of LOCAL-564 found a vocabulary gap that PREDATES 564: the closure
marker list `_CLOSED_MARKERS` carried "permanently closed" / "has closed" / "out
of business" but none of the plain permanent-closure phrasings that real press
headlines actually use —

    "The Capital Grille Boston Is Closing For Good"      kept the venue LIVE
    "<Venue> has shut its doors after 30 years"          kept the venue LIVE

The 564 subject/place binding (`_closure_binds`) was correct; it simply had no
marker to fire on, so a shuttered restaurant was sent to the listener as a stop.
This suite adds the missing PERMANENT-closure vocabulary and, symmetrically, an
explicit TEMPORARY exclusion so that ambiguous phrasings ("temporarily closed",
"closed for renovations", "closed on Mondays", the French forms) never bind.

Scope, matching the ticket exactly:

  PERMANENT (must BIND for a Boston, MA stop, through the 564 binding):
    closing for good / closed for good / shutting down for good / has shut down /
    shut its doors / shuttered / will close permanently / is closing permanently /
    closing its doors / ferme ses portes / a fermé ses portes

  TEMPORARY (must KEEP the venue — never bind), even though each contains a
  closure-marker substring:
    temporarily closed / closed for renovation(s) / closing early /
    closed on <weekday> / closed for the season / closed for a private event /
    fermeture exceptionnelle / fermé temporairement

  NOT added as markers (ambiguous — must NOT bind on their own):
    "is closing" / "closed" / "to close"

Every case is checked against the PURE function `_closure_binds` (offline, no
network). Two markers are also driven end-to-end through `closure_scan` with a
stubbed SERP.

Run:  python3 tests/test_local570_closure_markers.py
      (offline — no API keys, no network)

RED ON storied (7fe54e7): none of the permanent phrasings were in
`_CLOSED_MARKERS`, so every "<Venue> Is Closing For Good" case returned
binds=False and this suite failed. GREEN after the fix.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import restaurant_practicals as rp
from restaurant_practicals import _closure_binds, closure_scan


BOSTON = "restaurant tour of The Capital Grille, Boston, MA"

# (label, snippet, title, url, venue, city/location, expect_closed)

# ---- PERMANENT phrasings: every new marker must BIND for a Boston stop -------
PERMANENT_CASES = [
    ("'Is Closing For Good' — the ticket's canonical miss",
     "", "The Capital Grille Boston Is Closing For Good", "",
     "The Capital Grille", BOSTON, True),

    ("'closing for good' in a sentence",
     "After 25 years on the waterfront, The Capital Grille is closing for good.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'closed for good'",
     "The Capital Grille has closed for good, the owners confirmed.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'shutting down for good'",
     "The Capital Grille is shutting down for good this month.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'has shut down'",
     "The Capital Grille has shut down after a long run downtown.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'shut its doors' — the ticket's second example, with trailing detail",
     "The Capital Grille has shut its doors after 30 years in business.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'shuttered' (single word)",
     "The Capital Grille, a downtown mainstay, has been shuttered.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'will close permanently'",
     "The Capital Grille will close permanently at the end of the month.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'is closing permanently'",
     "The Capital Grille is closing permanently, the group announced.",
     "", "", "The Capital Grille", BOSTON, True),

    ("'closing its doors'",
     "The Capital Grille is closing its doors for the last time.",
     "", "", "The Capital Grille", BOSTON, True),

    # French permanent forms (venue placed in Boston for the subject/place path;
    # the point is the phrase, not the locale — no contradicting region named).
    ("French 'ferme ses portes'",
     "The Capital Grille ferme ses portes définitivement.",
     "", "", "The Capital Grille", BOSTON, True),

    ("French 'a fermé ses portes'",
     "The Capital Grille a fermé ses portes le mois dernier.",
     "", "", "The Capital Grille", BOSTON, True),

    # Title Case headline form for a couple of the new markers (press register).
    ("Title Case 'Shut Its Doors' headline",
     "The Capital Grille Has Shut Its Doors After 30 Years",
     "The Capital Grille Has Shut Its Doors After 30 Years", "",
     "The Capital Grille", BOSTON, True),
]

# ---- TEMPORARY phrasings: must KEEP the venue (never bind) -------------------
TEMPORARY_CASES = [
    ("'temporarily closed'",
     "The Capital Grille is temporarily closed while the kitchen is refitted.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed for renovation'",
     "The Capital Grille is closed for renovation and reopens in spring.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed for renovations' (plural)",
     "The Capital Grille is closed for renovations until further notice.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closing early'",
     "The Capital Grille is closing early today for a staff event.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed on Mondays' — a weekday, not a closure",
     "The Capital Grille is closed on Mondays but open the rest of the week.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed on Sunday'",
     "The Capital Grille is closed on Sunday for a private booking.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed for the season'",
     "The Capital Grille patio is closed for the season.",
     "", "", "The Capital Grille", BOSTON, False),

    ("'closed for a private event'",
     "The Capital Grille is closed for a private event this evening.",
     "", "", "The Capital Grille", BOSTON, False),

    ("French 'fermeture exceptionnelle'",
     "The Capital Grille — fermeture exceptionnelle aujourd'hui.",
     "", "", "The Capital Grille", BOSTON, False),

    ("French 'fermé temporairement'",
     "The Capital Grille est fermé temporairement pour travaux.",
     "", "", "The Capital Grille", BOSTON, False),

    # A temporary phrasing must win even when a permanent-looking substring is
    # present in the SAME clause: "closed for renovations" contains "closed" but
    # is not a permanent closure.
    ("mixed: 'closed for renovations' is not a permanent closure",
     "Reports that it had closed were wrong — The Capital Grille is closed for "
     "renovations and will reopen.",
     "", "", "The Capital Grille", BOSTON, False),
]

# ---- Ambiguous bare phrasings that were NOT added as markers: must NOT bind ---
NEGATIVE_CASES = [
    ("bare 'is closing' alone must not bind",
     "The Capital Grille is closing soon, so book a table.",
     "", "", "The Capital Grille", BOSTON, False),

    ("bare 'closed' alone (hours sense) must not bind",
     "The Capital Grille is closed right now; it opens at five.",
     "", "", "The Capital Grille", BOSTON, False),

    ("bare 'to close' must not bind",
     "The Capital Grille is about to close for the night.",
     "", "", "The Capital Grille", BOSTON, False),
]

ALL_CASES = (
    [("PERMANENT", *c) for c in PERMANENT_CASES]
    + [("TEMPORARY", *c) for c in TEMPORARY_CASES]
    + [("NEGATIVE", *c) for c in NEGATIVE_CASES]
)


# ============================================================================
# [LOCAL-570 r2] A TIME-LIMITED CLOSURE IS TEMPORARY.
#
# LEAD's r1 miss was a spec error, not a code error: "closing its doors" is on the
# PERMANENT list, so
#
#     "Neptune Oyster is closing its doors for two weeks for repairs"  -> closed
#
# dropped a live venue. The fix: a permanent marker that sits in the same clause
# as a BOUNDED DURATION ("for two weeks"), a dated reopening window ("until
# January 5", "through March"), or an explicit RETURN ("reopens in May", "will
# reopen", French "pour travaux" / "jusqu'au" / "réouverture") must NOT bind — the
# venue is coming back. A NEGATED return ("will not reopen" / "won't reopen" /
# "never reopen") is the opposite: it confirms the closure is permanent and must
# still BIND.
#
# Neptune Oyster and Toro are both placed in Boston, MA — real Boston venues, and
# the subject/place binding is exercised exactly as in r1.
# ============================================================================
NEPTUNE = "restaurant tour of Neptune Oyster, Boston, MA"
TORO = "restaurant tour of Toro, Boston, MA"

R2_CASES = [
    # (group, label, snippet, title, url, venue, city, expect_closed)

    # KEPT — bounded duration. The r1 miss itself.
    ("R2-KEEP",
     "'closing its doors for two weeks' — the r1 miss (bounded duration)",
     "Neptune Oyster is closing its doors for two weeks for repairs.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    # KEPT — explicit return ("reopens in May").
    ("R2-KEEP",
     "'has shuttered and reopens in May' (return named)",
     "Neptune Oyster has shuttered and reopens in May.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    # KEPT — dated reopening window ("until January 5").
    ("R2-KEEP",
     "'closing its doors until January 5' (dated window)",
     "Toro closing its doors until January 5.",
     "", "", "Toro", TORO, False),

    # CLOSED — negated return. "will not reopen" must still bind.
    ("R2-BIND",
     "'shuttered since March, will not reopen' (negated return -> closed)",
     "Neptune Oyster, shuttered since March, will not reopen.",
     "", "", "Neptune Oyster", NEPTUNE, True),

    # CLOSED — "after 20 years" is NOT a bounded future duration or a return.
    ("R2-BIND",
     "'closing its doors after 20 years' (permanent, no return) -> closed",
     "Neptune Oyster is closing its doors after 20 years.",
     "", "", "Neptune Oyster", NEPTUNE, True),

    # --- extra coverage of each new surface, both languages -----------------
    ("R2-KEEP",
     "French 'pour travaux' (closed for works) keeps the venue",
     "Neptune Oyster ferme ses portes pour travaux.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    ("R2-KEEP",
     "French 'jusqu'au <date>' keeps the venue",
     "Neptune Oyster ferme ses portes jusqu'au 5 janvier.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    ("R2-KEEP",
     "'through March' (window with an end) keeps the venue",
     "Neptune Oyster is closing its doors through March for a refit.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    ("R2-KEEP",
     "'will reopen' keeps the venue",
     "Neptune Oyster has shut its doors but will reopen next spring.",
     "", "", "Neptune Oyster", NEPTUNE, False),

    ("R2-BIND",
     "negated return \"won't reopen\" still binds -> closed",
     "Neptune Oyster has shuttered and won't reopen.",
     "", "", "Neptune Oyster", NEPTUNE, True),

    ("R2-BIND",
     "negated return 'never reopen' still binds -> closed",
     "Neptune Oyster is closing its doors and will never reopen.",
     "", "", "Neptune Oyster", NEPTUNE, True),
]

ALL_CASES = ALL_CASES + [(g, l, s, t, u, v, c, e)
                         for (g, l, s, t, u, v, c, e) in R2_CASES]


def _run_binds():
    failures = []
    print("  -- _closure_binds: new permanent markers / temporary exclusion --")
    for group, label, snip, title, url, venue, city, expect in ALL_CASES:
        binds, reason = _closure_binds(snip, title, url, venue, city)
        ok = (binds == expect)
        print(f"  {'OK ' if ok else 'FAIL'} [{group}] {label}")
        print(f"        binds={binds} expect={expect}  reason={reason!r}")
        if not ok:
            failures.append(f"{group}: {label}")
    return failures


def _run_scan():
    """End-to-end through closure_scan with a stubbed SERP: one permanent marker
    binds, one temporary phrasing keeps the venue. Deterministic, offline."""
    print("\n  -- closure_scan end-to-end (stubbed SERP) --")
    failures = []
    scenarios = [
        ("The Capital Grille", "restaurant tour of The Capital Grille, Boston, MA",
         True, [
            {"snippet": "The Capital Grille Boston is closing for good after 25 "
                        "years.",
             "title": "The Capital Grille Boston Is Closing For Good",
             "url": "https://boston.eater.com/capital-grille"},
        ]),
        ("The Capital Grille", "restaurant tour of The Capital Grille, Boston, MA",
         False, [
            {"snippet": "The Capital Grille is temporarily closed for renovations "
                        "and will reopen in the spring.",
             "title": "", "url": "https://example.com/capital-grille"},
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
                failures.append(f"closure_scan expect={expect_closed}")
    finally:
        rp._serp = orig_serp
    return failures


def main():
    print("[LOCAL-570] closure markers — permanent phrasings + temporary exclusion\n")
    failures = _run_binds() + _run_scan()
    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())

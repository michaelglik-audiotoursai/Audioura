# SUBMISSION — LOCAL-570: Closure markers — "closing for good" and its kin

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-570-closure-markers
**Base:** storied (7fe54e7) — release fix (D594: LEAD forward-merges into subscribed)

## Problem

LEAD's review of LOCAL-564 (merged storied 9dd7358) found a vocabulary gap that
**predates 564**: `_CLOSED_MARKERS` (`restaurant_practicals.py:189`) carried
`permanently closed`, `has closed`, `out of business`, etc., but none of the
plain permanent-closure phrasings real press headlines use. So the title

    The Capital Grille Boston Is Closing For Good

kept the venue LIVE — old code and new code alike — and the listener was sent to
a shuttered restaurant. The 564 subject/place binding (`_closure_binds`) was
correct; it had no marker to fire on.

## Fix

### 1. Permanent-closure phrasings added to `_CLOSED_MARKERS`
Each goes through the existing 564 subject/place binding unchanged (case-insensitive,
matched as a phrase, venue must be the subject and the place must not be contradicted):

    closing for good, closed for good, shutting down for good, has shut down,
    shut its doors, shuttered, will close permanently, is closing permanently,
    closing its doors, ferme ses portes, a fermé ses portes

Because `_CLOSURE_AUX_TOKENS` is DERIVED from `_CLOSED_MARKERS`, the new markers
also contribute their words (shut/doors/shuttered/ferme/portes…) to the aux-token
set, so a Title Case headline ("…Has Shut Its Doors After 30 Years") binds without
the capitalised closure words being misread as a name continuation — exactly the
r3 mechanism 564 established.

### 2. Explicit TEMPORARY exclusion — new `_TEMPORARY_MARKERS` + `_temporarily_closed`
Bare `is closing` / `closed` / `to close` were deliberately NOT added as markers
(ambiguous: closing time, closed-on-Monday, early close). To make that safe, a
clause carrying any temporary phrasing is skipped before a marker can bind:

    temporarily closed, closed for renovation(s), closing early,
    closed on <weekday>, closed for the season, closed for a private event,
    fermeture exceptionnelle, fermé temporairement

Some are regexes (`renovations?`, any weekday, the French forms); all are matched
case-insensitively as phrases. This also protects the mixed case — a clause that
contains the substring "closed" but means "closed for renovations" keeps the venue.

## Tests — `tests/test_local570_closure_markers.py`

- **PERMANENT (13 cases):** every new marker binds for a Boston, MA stop, including
  the ticket's `<Venue> Is Closing For Good` and `<Venue> has shut its doors after
  30 years`, plus a Title Case headline form.
- **TEMPORARY (11 cases):** every temporary phrasing keeps the venue, including the
  mixed "closed … is closed for renovations" case.
- **NEGATIVE (3 cases):** bare `is closing` / `closed` / `to close` do not bind.
- **End-to-end:** `closure_scan` with a stubbed SERP — one permanent marker closes,
  one temporary phrasing keeps the venue. Offline, no network, no API calls.

### Results

```
tests/test_local570_closure_markers.py      ALL TESTS PASSED (exit 0)
tests/test_local564_closure_binding.py       ALL TESTS PASSED (exit 0)
tests/test_d538_restaurant_practicals.py      ALL TESTS PASSED (exit 0)
tests/test_d539_closure_regression.py         ALL TESTS PASSED (exit 0)
```

### Red on storied

Running the new suite against the un-patched `restaurant_practicals.py`
(`git stash` of the source change) exits **1**: all 12 new permanent-marker cases
and the permanent end-to-end `closure_scan` case fail to bind because the markers
do not exist on storied. The temporary and negative cases already pass on storied
(they correctly never bound). This is the executable statement of the gap.

## Scope / safety

Offline. No API calls. No DB writes. No GCloud. No DELETE anywhere.
DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md and .continuous_dev/STATUS.md
were not touched.

## r2 — a time-limited closure is temporary

### Why r1 bounced (LEAD review, 2026-10-03 03:0x)
r1 was green on all four suites and 8/9 LEAD probes passed. The miss was a spec
error in r1 itself: `closing its doors` is on the PERMANENT list, so

    "Neptune Oyster is closing its doors for two weeks for repairs"  -> closed

dropped a LIVE venue. A permanent marker that sits in the same clause as a bounded
duration or a stated return is not a permanent closure.

### Fix — extend the TEMPORARY exclusion (`_TEMPORARY_MARKERS` + a negated-return guard)
`restaurant_practicals.py`. All deterministic and language-aware, matched
case-insensitively against the lowercased clause, exactly as r1. A clause carrying
any of these keeps the venue even though it also carries a permanent marker:

- **bounded duration** — `for <N|a|an|one|two|…|several|a few|a couple of>
  (day|days|week|weeks|month|months)`
- **dated reopening window** — `until <month|weekday|digit>`, `through <month>`
- **explicit return** — `reopen(s)? (on|in|next|this)`, `reopening (on|in|next|this)`,
  `will reopen`, `back (on|in|next)`
- **French** — `pour travaux`, `jusqu'au`, `réouverture`

A **negated return is still a permanent closure** and must BIND. A new
`_negated_return` guard (`will not reopen` / `won't reopen` / `never reopen`) is
checked FIRST inside `_temporarily_closed`; when it fires the temporary exclusion
is suppressed and the closure marker is free to bind. This is why
`shuttered … will not reopen` closes while `reopens in May` keeps.

Note `after 20 years` is deliberately NOT a bounded future duration (no time unit
in `day/week/month`, and `after`, not `for`), so `closing its doors after 20 years`
still binds — a venue ending after a long run is permanently closed.

### Tests — rows added to `tests/test_local570_closure_markers.py`
The five ticket rows plus coverage of each new surface and both languages:

| row | verdict |
|-----|---------|
| `Neptune Oyster is closing its doors for two weeks for repairs` | kept |
| `Neptune Oyster has shuttered and reopens in May` | kept |
| `Toro closing its doors until January 5` | kept |
| `Neptune Oyster, shuttered since March, will not reopen` | **closed** |
| `Neptune Oyster is closing its doors after 20 years` | **closed** |
| `… ferme ses portes pour travaux` / `… jusqu'au 5 janvier` | kept |
| `… through March` / `… will reopen next spring` | kept |
| `… won't reopen` / `… will never reopen` | **closed** |

### Results — all four suites green

```
tests/test_local570_closure_markers.py      ALL TESTS PASSED (exit 0)
tests/test_local564_closure_binding.py       ALL TESTS PASSED (exit 0)
tests/test_d538_restaurant_practicals.py      ALL TESTS PASSED (exit 0)
tests/test_d539_closure_regression.py         ALL TESTS PASSED (exit 0)
```

### Red on cc4ba23
Running the seven new KEPT rows against the un-patched `cc4ba23` source
(`git show cc4ba23:restaurant_practicals.py`) exits **1**: every one binds=True
(wrongly closed) because r1 has no notion of a bounded duration or a return —
`7/7 new kept rows are RED on cc4ba23`. The negated-return rows already bind on
cc4ba23 (they are permanent on both trees), so the executable statement of the
r2 gap is precisely those seven kept rows.

### Scope / safety (r2)
Offline. No API calls. No DB writes. No GCloud. No DELETE anywhere.
DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md and .continuous_dev/STATUS.md
were not touched.

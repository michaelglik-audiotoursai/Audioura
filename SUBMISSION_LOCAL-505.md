# SUBMISSION_LOCAL-505.md — A Church Is Not A Museum

**Branch:** `LOCAL-505-venue-class-routing` · **Base:** storied (`7a97e72`)
**Agent:** Mac Mini Kiro

## TL;DR

The two defects LOCAL-505 describes are **already fixed in `storied`** by commit
`fd5aa5c` (*"LOCAL-485: a church is not a museum — route worship/civic venues to
the place path"*), which is an ancestor of my base `7a97e72`. LOCAL-505 is a
re-issue of LOCAL-485 (identical report: Michael, build 26, 2026-09-16, "Our Lady
Help of Christians, Catholic Church in Newton MA"). Per the task's MANDATORY note,
the prior LOCAL-505 run's **deliverable file was lost** because it was never
committed — but the underlying code and its regression tests survived in storied.

This session's job was therefore to **independently verify** that the landed fix
truly satisfies all six acceptance criteria (not merely trust the pre-existing
green suite), to **actively break the routing and watch a test go red** (AC6, per
D242), and to **commit this deliverable** so it is not lost again.

Every claim below is backed by tool output I produced this session.

## Verification of base and provenance

```
$ git rev-parse HEAD
7a97e7233f9a84ce56fc5d5883c825d55e4f6bf0
$ git merge-base --is-ancestor 7a97e72 HEAD ; echo $?
0                                   # correct base (not origin/*)
$ git log --oneline -1 fd5aa5c
fd5aa5c LOCAL-485: a church is not a museum — route worship/civic venues to the place path
```

The fix commit `fd5aa5c` predates my base, so `generate_tour_text.py`,
`generate_tour_text_service.py`, and `test_local485_venue_class_routing.py` all
carry the fix at HEAD. `git status` was clean when I started; I added only this
submission file.

## The report this answers

Michael, build 26, 2026-09-16, requested a 2-stop tour of **"Our Lady Help of
Christians, Catholic Church in Newton MA"** — a real, historic parish church at
573 Washington St. It ran 31 s and was rejected: *"This venue could not be
verified with enough works to generate a quality tour."* The trace showed the
church routed down the **museum** pipeline; asked for *artworks* and having none
catalogued, the model produced the **Sistine Chapel Ceiling** (6,700 km away) and
**The Last Supper** (Milan), then the museum gate — working exactly as designed —
clean-failed `unresolvable` because a parish church has no Wikidata artwork
inventory.

**The museum gate is correct; it was being pointed at the wrong kind of venue.**

## Defect 1 — venue class must decide the stop type (routing, not data)

The venue-class principle (D563) is implemented as **one shared detector**,
`_detect_venue_class(location, tour_type)` in `generate_tour_text.py`, returning:

- `'facility'` — airport/terminal/station/hospital/stadium/campus (LOCAL-480):
  stops are a traveller need-spine.
- `'worship_civic'` — church/cathedral/basilica/chapel/abbey/synagogue/mosque/
  temple/courthouse/town hall (LOCAL-485): stops are **places** (nave, bell
  tower, war memorial, parish hall, cemetery), verified the way a walking tour's
  stops are — **not** catalogued works.
- `None` — ordinary walking/museum/restaurant request.

`_detect_facility_class` is a **thin wrapper** over the shared detector
(`return _detect_venue_class(...) == 'facility'`), and `_detect_worship_civic_class`
is the sibling wrapper — so LOCAL-480 and LOCAL-505 share **one mechanism**, not
two (AC5). The routing is enforced at every place a church could have been flipped
to `museum`:

1. **`_classify_tour_category`** returns `'walking'` for a worship/civic venue,
   above the museum keyword scan.
2. **S15 force-museum** excludes worship/civic: `... and not
   _detect_worship_civic_class(location, tour_type)`.
3. **CLASSIFY-FIX** — the worship/civic words (`church`, `cathedral`, `basilica`,
   `temple`, `abbey`) were **removed** from `_VENUE_WORDS_FOR_CLASSIFY`, so a
   walking classification is no longer flipped to museum on those words.
4. **VENUE-CLASS GUARD** — a post-convergence hard stop: if anything still set
   `museum` on a non-facility worship/civic venue, it is pulled back to
   `walking`. This is the seam AC6 flips.

A church thus rides the **place-based (walking) path** — the same corpus that
built Michael's approved Cimiez tour (which includes Cimiez Monastery, a church,
in a walking tour that worked). Because it never enters the artwork pipeline, the
model is **never asked for artworks**, so the Sistine Chapel / Last Supper
fabrication cannot occur (AC1, AC2).

## Defect 2 — the error message was a catch-all lying about the cause

`generate_tour_text_service.py` now branches on `thin_evidence` explicitly,
**before** the catch-all, with an honest, venue-named message:

> *We could not find enough verified material about "<venue>" to build a tour. Try
> a broader request — for example a walking tour of the surrounding neighbourhood.*

The venue name flows from `_LAST_CLEAN_FAIL_EVIDENCE["venue"]`, which both
`thin_evidence` clean-fail sites in `generate_tour_text.py` set to
`_museum_venue_name or location`. The old *"not enough works"* string now appears
**only in comments** describing what was removed — no live code emits it (AC4).

```
$ grep -n "enough works\|not be verified" generate_tour_text_service.py
193:  # venue. Previously this fell through to the museum "not enough works"
208:  # It previously borrowed the museum "not enough works" wording, so
```

## Acceptance criteria — evidence

Run this session (warnings filtered for readability), real output:

**AC1/AC2/AC3/AC4/AC5 — full LOCAL-505/485 suite green (21 tests):**
```
$ python3 test_local485_venue_class_routing.py
... (all 21) ... ok
Ran 21 tests in 0.013s
OK
```
Covering: church → `walking` (`test_classify_returns_walking`,
`test_full_route_walking_even_when_s15_would_fire`); real museums stay `museum`
and Cimiez stays `walking` (`test_real_museums_route_to_museum`,
`test_museum_full_route_stays_museum`, `test_cimiez_walking_tour_unchanged`);
`thin_evidence` service message names the venue and is not the catch-all
(`test_thin_evidence_branch_exists_and_is_not_the_catchall`,
`test_evidence_dict_carries_venue_name`); one shared detector
(`test_shared_mechanism_one_detector`).

**AC5 + AC3 regression — LOCAL-480 facility suite green (20 tests):** confirms the
shared detector did not regress the facility class and that Cimiez is untouched.
```
$ python3 test_local480_facility_category.py
... (all 20) ... ok
Ran 20 tests in 0.898s
OK
```

**AC6 — break the routing, watch it go red.** I neutralised the *single shared
mechanism* in memory (`_detect_venue_class` drops its `worship_civic` verdict) —
exactly the revert the guards defend against — and re-ran the church-routing
tests:
```
FAIL: test_church_is_worship_civic ............ None != 'worship_civic'
FAIL: test_cathedral_basilica_..._townhall .... None != 'worship_civic'
FAIL: test_full_route_walking_even_when_s15_would_fire
      AssertionError: 'museum' != 'walking'
      : church must route to the place-based path, not the museum pipeline
FAIL: test_venue_class_guard_catches_a_forced_museum  'museum' != 'walking'
Ran 10 tests ... FAILED (failures=4)
```
With the routing broken the church returns to `'museum'` — the exact build-26
defect. `git status` confirmed the break was in-memory only; the worktree stayed
clean. The suite's own `TestBreakTheRoutingGoesRed.test_break_routing_regresses_to_museum`
also encodes this red/green contrast and passes with the fix live.

## What I did NOT do

- Did **not** weaken the museum gate — the fix routes *around* it; a genuine
  museum still verifies works through Wikidata/SPARQL (AC3 tests confirm).
- Did **not** rebuild, restart, or deploy any container (Michael is field-testing
  build 26).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, `BUILD_NUMBERS.md`, or `PENDING_REMINDERS.md`.
- Did **not** modify any source this session — the fix was already correct in
  storied. The only file I add is this submission, committed on
  `LOCAL-505-venue-class-routing` so the deliverable is not lost again.

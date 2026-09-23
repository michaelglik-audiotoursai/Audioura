# SUBMISSION — LOCAL-3481 · A Stop Must Be A Place

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3481-stop-must-be-a-place`
**Base:** `storied` @ `e1341e6` (`git merge-base --is-ancestor e1341e6 HEAD` → exit 0)

---

## TL;DR

LOCAL-3481 is the re-delivery of "A Stop Must Be A Place". The three-part
implementation the ticket asks for **already lives on `storied`**, merged by
LOCAL-481 (commit `ca52d84`, "a stop must be a real, named, findable place"):

- **Part 1 — centroid-collapse detector:** `geocode_stops.find_centroid_collapse`
  / `repair_centroid_collapse`
- **Part 2 — reject category labels and non-places:** `place_shape.classify_stop_name`
  / `is_a_place`
- **Part 3 — no double-up:** the check is folded into the existing PHASE 5.6 gate
  (`generate_tour_text._validate_stops_within_scope`) and reused by the D558
  replenishment loop (`replenish_to_count`) — not a sixth overlapping gate.

The predecessor's 24 tests are green at base. This task adds one **acceptance
harness bound to the exact fixtures the ticket names** —
`tests/test_local3481_a_stop_must_be_a_place.py` — which calls the real functions
and the real wiring, maps each of the five acceptance criteria to a test, and
proves the detector can go red on the exact tour-423 fixture. **10/10 pass.**

The MANDATORY note on this ticket is the reason it exists: a prior LOCAL-3481 run
created its output and never committed, so the worktree was pruned and the
deliverable was destroyed. **This deliverable is committed** (see the last
section).

---

## What each part does, and why it is where it is (Part 3 — do not double up)

I read `scope_memory.py`, `geocode_stops.resolve_poi()` and the PHASE 5.6 scope
judge before writing anything, as the ticket requires.

- **The non-place check runs *inside* PHASE 5.6.** In
  `_validate_stops_within_scope._check_one`, a stop is classified by
  `place_shape.classify_stop_name` *before* the LLM call, in the same
  deterministic-first spirit as the D557 scope-memory lookup that sits beside it.
  A non-place is rejected at `conf="high"` with reason `[not-a-place] …`. This
  reuses the gate that already runs on every stop, so nothing new has to be wired
  into the pipeline entry points.
- **A `[not-a-place]` verdict is *not* written into the scope-memory corpus.**
  The removal path guards this explicitly: `if not reason.startswith('[scope-memory]')
  and not reason.startswith('[not-a-place]')`. A bad name is bad for *every*
  scope, so it must not pollute the `(name, scope)`-keyed `known_out_of_scope.json`.
- **The centroid detector feeds `resolve_poi`.** `repair_centroid_collapse` sends
  colliding stops back through the resolver (default `resolve_poi`) — the one
  procedure that already knows how to find a real coordinate — and a stop it
  cannot move is left flagged for the caller to drop and let D558 replenish.
  This is repair-over-deletion, exactly as the ticket asks.

### Scope of the collision rule, and the false positive it guards (Part 1)

Per the ticket, genuinely co-located stops (two artworks in one museum room) must
not be flagged. The base implementation was **reshaped by D572** to be even safer
than a category allowlist: a collapse now requires **three or more** stops sharing
one axis at an **exact** value **while the other axis varies**. Stops identical on
*both* axes are co-located, not centroid-jittered — so `museum` needs no special
exemption; the rule simply never fires on co-location, for any category. Two
stops sharing a latitude (same east-west street) is commonplace and is *not* a
collapse. This is verified in AC3 below and in the base suite
(`test_two_stops_sharing_an_axis_is_NOT_a_collapse`,
`test_co_located_stops_are_innocent_in_EVERY_category`).

---

## The two failing shapes (Part 2)

`place_shape` classifies deterministically — a fact about the words, not an LLM
opinion (D526/D528 record why that matters):

1. **Category standing in for an instance** — a **plural/collection head noun** +
   a **containing preposition** + a place: *"Art Exhibits at Logan Airport"*,
   *"Restaurants in Nice"*, *"Museums of the Old Town"*. A singular proper name is
   never a category, even with a preposition — *"Museum of Modern Art"*,
   *"Cathedral of Notre-Dame"*, *"Statue of Liberty"* all survive.
2. **Non-physical concept / format** — a delivery medium named as a destination:
   *"Virtual Tour"*, *"History Walk"*, *"Audio Guide"*, *"Self-Guided Tour"*,
   *"Timeline"*. A format word is only damning when it is the **head** qualified
   as a **medium**, so real named trails (*"Freedom Trail"*, *"Cliff Walk"*,
   *"Appalachian Trail"*) are not caught.

`"Roman Ruins of Cemenelum"` — an approved Cimiez stop with a plural head
(`ruins`) — is protected by a minimal proper-name allowlist so the category rule
does not bounce it.

---

## Acceptance criteria — each mapped to a test, run against the real code

Suite: `tests/test_local3481_a_stop_must_be_a_place.py`. Fixtures are the **exact**
four tour-423 stops (names + coordinates) and the **six approved Cimiez stops
copied verbatim** from `TOUR_CIMIEZ_WALKING_20260830.md`.

```
AC1_TheFourStopsAreFlagged::test_bruins_bar_is_the_only_place                                  PASSED
AC1_TheFourStopsAreFlagged::test_centroid_collapse_flags_all_four_on_the_shared_latitude       PASSED
AC1_TheFourStopsAreFlagged::test_place_shape_flags_the_three_nonplaces_only                    PASSED
AC1_TheFourStopsAreFlagged::test_wired_phase56_removes_the_three_nonplaces_bruins_bar_survives PASSED
AC2_ApprovedCimiezNeverFlagged::test_every_approved_cimiez_stop_classifies_as_a_place          PASSED
AC2_ApprovedCimiezNeverFlagged::test_no_approved_cimiez_stop_is_removed_for_being_a_nonplace    PASSED
AC3_MuseumCoLocationNotFlagged::test_co_located_artworks_are_not_a_collision                   PASSED
AC4_ReplenishmentRefillsToCount::test_a_nonplace_candidate_is_rejected_and_a_real_place_refills PASSED
AC5_BreakTheDetector::test_disabling_centroid_detector_lets_423_through_then_reenabled_flags    PASSED
AC5_BreakTheDetector::test_disabling_place_shape_rules_lets_423_nonplaces_through_then_reenabled_flags PASSED
======================== 10 passed, 1 warning in 0.64s =========================
```

- **AC1 — the four 423 stops are all flagged; Bruins Bar survives.**
  Place-shape: `Boston Bruins Bar` → place; `Art Exhibits at Logan Airport` →
  category; `…Virtual Tour` and `…History Walk` → format. Centroid: all four share
  `lat=42.3656` exactly while longitude varies → `action="collision"`,
  `colliding_indices=[0,1,2,3]`. In the **wired** PHASE 5.6 gate (with a
  deliberately invalid key so the LLM branch fails **open**), only
  `Boston Bruins Bar` survives — so the three removals can only be the
  deterministic place-shape check (LOCAL-465's witness lesson).

- **AC2 — the approved Cimiez stops are never flagged.** All six classify as
  `place` in both NFC and NFD Unicode forms (D243). *Isolation note, verified in
  code:* the approved tour file **itself** flags `Villa Leopolda` as outside
  Cimiez (it is in Villefranche-sur-Mer, ~6 km east), and `known_out_of_scope.json`
  removes it deterministically via the **D557 scope-memory gate** — a correct,
  *separate* removal that is not a LOCAL-3481 concern. So the AC2 wiring test
  asserts the LOCAL-3481 bounce condition precisely: **no approved stop is removed
  with a `[not-a-place]` reason** (captured from the gate's own log), rather than
  demanding the unrelated scope gate keep a stop it is right to drop.

- **AC3 — two artworks in one museum room are not flagged.** Two stops identical
  on both axes (`48.8600, 2.3376`) → `action="none"` for every category
  (`museum`, `walking`, `facility`, `None`).

- **AC4 — a tour that loses a stop comes back at the requested count.**
  `replenish_to_count` is driven with an injected proposer: round 1 offers a
  category label (`"Restaurants in Nice"`) which the same validation rejects;
  round 2 offers a real place (`"Cours Saleya"`) which is accepted. Final count
  is the requested 3, `(added, rejected) == (1, 1)`, and the loop re-ran
  (`rounds >= 2`) — repair over deletion via the loop the ticket says to reuse.

- **AC5 — break the detector, show a test go red.** Two tests toggle the real
  disable knobs. Beyond the in-test toggle, I demonstrated the red state live by
  breaking each detector in-process and asserting on the **exact 423 fixture**:

  ```
  ── RED PROOF 1: centroid detector broken (min stops -> 99) ──
     action: none   (fix would require 'collision')
     AC1 centroid assertion: RED -> 423 must be flagged

  ── RED PROOF 2: place-shape rules broken (rule sets emptied) ──
     survivors: ['Boston Bruins Bar', 'Art Exhibits at Logan Airport',
                 'Boston Logan Airport Virtual Tour', 'Boston Logan Airport History Walk']
     AC1 place-shape assertion: RED -> only Bruins Bar should survive
  ```

  With the detector intact the same assertions pass; with it broken they fail.
  `exit=0` alone proves nothing (D242) — this is the fixed-vs-broken discriminator.

### Wiring proved separately from the function (LOCAL-465)

AC1's `test_wired_phase56_removes_the_three_nonplaces_bruins_bar_survives` and
AC2's `test_no_approved_cimiez_stop_is_removed_for_being_a_nonplace` call the real
`generate_tour_text._validate_stops_within_scope`, not the classifier in
isolation. The invalid key makes the LLM branch fail open, so any removal is a
genuine witness that the deterministic check is actually **called** in the
pipeline — the exact gap LOCAL-465 warned about (27 green function tests, a
`NameError` live).

---

## Full regression

```
python3 -m pytest tests/test_local481_place_shape.py \
                  tests/test_local481_centroid_collapse.py \
                  tests/test_local481_wiring.py \
                  tests/test_local3481_a_stop_must_be_a_place.py
======================== 34 passed, 1 warning in 1.27s =========================
```

(24 pre-existing LOCAL-481 tests + 10 new LOCAL-3481 acceptance tests.)

---

## Constraints honoured

- Branched from `HEAD` (`e1341e6`), not from `origin/*`. Ancestry check passes.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, `BUILD_NUMBERS.md`, `PENDING_REMINDERS.md`.
- Did **not** touch `unglossed_reference_gate.py` (LOCAL-479); added **no**
  `facility` category (LOCAL-480).
- No container was rebuilt, restarted, or deployed — Michael is testing on
  Preview.
- Deliverable is **committed** on this branch (the one thing the prior run
  failed to do).

## Files in this delivery

- `tests/test_local3481_a_stop_must_be_a_place.py` — the acceptance harness (new)
- `SUBMISSION_LOCAL-3481.md` — this document (new)

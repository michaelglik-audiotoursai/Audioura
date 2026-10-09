# SUBMISSION — LOCAL-642: The National Gallery's "The Toilet of Venus ('The Rokeby Venus')" block is flattened and duplicated (R9, R12)

**Branch:** `LOCAL-642-paren-title-flatten` (from `subscribed` @ `de54df9`)
**Agent:** Mac Mini Kiro
**Base verified:** `git merge-base --is-ancestor de54df9 HEAD` → exit 0.

---

## TL;DR

| | |
|---|---|
| **Defect** | The National Gallery stop whose title carries **parentheses and quotes** — `The Toilet of Venus ('The Rokeby Venus')` — shipped with its header, `Address`, `Coordinates` and `Orientation` **flattened onto one line**, and the flattened block **duplicated** under a `Continue to …` transition (Bench R9 and R12, `audio_tours.id=495`). Only this title was affected — it is the one with `(` `)` `'`. |
| **Root-cause class** | A lost-newline family: a late pass emitted the stop's header + field block as a single run-on line, and a transition line carried a second, header-less copy of the same field block. The `(` / `'` in the title is the differentiator — a title-built regex whose unescaped `(` opens a group, or a block re-join, mangles only this stop. |
| **Fix** | A **deterministic, idempotent line invariant** in `tour_conclusion.enforce_header_field_line_invariant`, run inside `normalise_stop_headers` so it reaches delivered text on **both** finalization paths. It re-breaks any field label glued after other content onto its own line (un-flattening a run-on `Stop N:` header *and* a run-on field chain) and drops a `Continue to <title> <field block>` duplicate, keeping only the hand-off sentence. It keys **only** on the house field labels and the `Stop N:` header — **never** on the title text — so a title with `(` `)` `'` `[` `]` `+` `?` is carried **byte-for-byte**. Plus a defensive `re.escape` on the one interpolated-indicator D1 regex. |
| **Live** | National Gallery, 3 stops, ONE fresh tour, own disposable container, cache + pool OFF, cap **$0.90** → **DELIVERED** tour **551**; the parenthesized title is a clean Stop 2; `venue_as_stop` **PASSES** (0 detector failures); cost **$0.7669**. |

---

## Evidence (R12 495 generator log)

```
21: Directions: Continue through The National Gallery — next is The Toilet of Venus ('The Rokeby Venus').
23: Continue to The Toilet of Venus ('The Rokeby Venus') Address: The National Gallery, Trafalgar Square, … Coordinates: 51.5081, -0.128 Orientation: Stand just far enough …
25: Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: The National Gallery, … Coordinates: … Orientation: …
```

Line 21 is the correct transition. Line 23 is a **duplicated** `Continue to <title>` that carries the next stop's **flattened** field block. Line 25 is the real header, also **flattened**. LEAD fixed one flattening cause in `44f15c6` (`practical_facts_gate.place_practical_facts_in_opening`, R9 Stop 3); R12 shows the same family survives on this title.

## Bisect (what I actually drove)

I built a harness driving every importable late pass on 495-style text with the
parenthesized title as the **middle** stop, in both well-formed (double-newline)
and R9-style single-newline-joined block shapes:
`practical_facts_gate.place_practical_facts_in_opening`,
`tour_conclusion.normalise_stop_headers`,
`directions_guarantee.ensure_directions_between_stops`,
`cross_stop_reference_guard.*`, and `stop_editor.edit_tour_text`.

**None of them flatten or duplicate on clean input** — the LEAD's `44f15c6` already
made `place_practical_facts_in_opening` strictly line-by-line. The flatten + duplicate
is produced in the **full generation/render path** (the run-on line is emitted before
the post-passes see it), which is why the symptom only shows on a live run and why a
single offline post-pass does not reproduce it. The ticket's own remedy is therefore
the right one: a **final deterministic invariant** that repairs the symptom regardless
of which upstream pass lost the newline. I implemented that and keyed it so no title
can ever be the thing it matches on.

## Unescaped-regex audit (the 6 named files)

I audited every `re.sub` / `re.search` / `re.compile` / `re.match` / `re.finditer` /
`re.split` in `generate_tour_text.py`, `stop_pool_assembly.py`, `tour_conclusion.py`,
`practical_facts_gate.py`, `stop_editor.py`, `cross_stop_reference_guard.py` for a
title/poi name interpolated into a pattern:

- **`cross_stop_reference_guard.py`** — titles are normalised (`_norm` / `_title_core`)
  and compared by substring; **never** interpolated into a regex. Safe.
- **`stop_pool_assembly.py`** — every pattern is a fixed literal; `_render_stop_block`
  joins fields with `\n` (never spaces). Safe, no flattening.
- **`generate_tour_text.restore_lost_stop_headers`** (LOCAL-632) already uses
  `re.escape(_nm)`; it inserts headers with `\n\n` so it cannot flatten. Safe.
- **`practical_facts_gate.py:599`** interpolates `_t`, a fixed clock-range fragment —
  not a title. Safe.
- **`derepetition_guard.cap_location_repetition`** already uses
  `re.escape(location_phrase)`. Safe.
- **`generate_tour_text.py:6227`** interpolated `_other` (a fixed D1 rejection-indicator
  word) raw. Not a title, low risk — **hardened with `re.escape` defensively.**

Net: no live unescaped **title** regex remained; the one raw interpolation on a fixed
word is now escaped too.

## The fix — `tour_conclusion.enforce_header_field_line_invariant`

Binding invariant, enforced deterministically on the whole-tour text:

1. Every `Stop N:` header line carries **only** the header (title + optional
   "by Artist, year") — never a field label.
2. Every field label (`Address:`/`Coordinates:`/`Orientation:`/`Directions:`) **starts
   its own physical line**.
3. A `Continue to <next>` transition carries **only** the hand-off sentence — never a
   copy of the next stop's field block.

Mechanics (keys on field labels + `Stop N:` only, never the title):

- **(C) de-dup** `_TRANSITION_WITH_GLUED_BLOCK`: a transition line
  (`Continue to` / `Continue through` / `Proceed to` / `Next:` / `Head towards` /
  `Your final stop in …:`) that is followed by a glued field block → keep the cue +
  title (terminated with a period), **drop** the duplicated field block, because the
  real `Stop N:` header for that title follows and carries the fields.
- **(A+B) un-flatten** `_INLINE_FIELD_LABEL`: any field label glued **after** other
  content on its line is re-broken onto its own line, iterated until none remain. This
  un-flattens both a run-on header (`Stop 2: <title> Address: …`) and a run-on field
  chain (`Address: X Coordinates: Y`). The match is **case-sensitive**, so lowercase
  prose like "…points you to the address: look left." is never touched.

Returns `(text, actions)`; `normalise_stop_headers` prints each action as
`[LOCAL-642] header/field invariant: …` so a re-break is visible in the generator log.
Idempotent; collapses any `\n{3,}` run. Wired into `normalise_stop_headers`, which is
called by `count_delivered_stops`, `rebuild_conclusion` (main path,
`generate_tour_text.py:24939`) and the pool/dg every-path guard
(`generate_tour_text.py:8081` `final = _normalise_headers(final)`), so the fix reaches
delivered text on **both** finalization paths.

### Files changed
- `tour_conclusion.py` — `enforce_header_field_line_invariant` + wiring + regex constants.
- `generate_tour_text.py` — one defensive `re.escape` on the D1 indicator regex.
- `test_local642_paren_title_flatten.py` — new regression test (below).
- `run_local642_container.py`, `run_local642_live.sh` — isolated live harness.

---

## Tests

New regression `test_local642_paren_title_flatten.py` — grounded on the exact R12 495
defect (correct transition + duplicated `Continue to <title> <field block>` + flattened
`Stop 2:` header) **and** synthetic titles with parentheses, quotes, brackets, `+` and
`?` (`A (B) [C] + D?`, `Study (No. 2) 'quote'`, `What? (Really!) [draft]`, `x+y? (z)`,
`The Lizard (aux plumes d'or) [1782]`). Asserts: the live `run_on` flatten detector is
cleared; the duplicated field block is dropped; the `Stop 2:` header carries only the
title; each field label starts its own line; `count_delivered_stops` unchanged; the
title is preserved byte-for-byte; idempotent; a clean tour is a byte-for-byte no-op;
lowercase prose labels are never re-broken. **14 cases pass.**

Named suites — each exit code:

```
python3 -m pytest test_local60*.py test_local61*.py test_local62*.py        296 passed                  ec=0
python3 -m pytest test_local63*.py test_local642_paren_title_flatten.py      188 passed, 1 skipped       ec=0
python3 -m pytest tests/test_local63*.py                                      16 passed                   ec=0
python3 -m pytest tests/test_lead_*.py                                         8 passed                   ec=0
python3 -m pytest test_local590_*.py                                          42 passed                   ec=0
python3 -m pytest tests/test_local60*.py tests/test_local61*.py tests/test_local62*.py   378 passed      ec=0
python3 test_sq4_merge.py                                                     ALL TESTS PASSED            ec=0
```

(The existing header suite — `test_local639_lost_stop_header.py`,
`tests/test_lead_pf_placement.py`, `test_local634_title_line.py` — stays green: 19 passed.)

---

## Live run (own container, cache + pool OFF, cap $0.90)

Built `Dockerfile.generator` from the branch tree → image `local642-gen-img`; ran a
**disposable** container `local642-gen`
(`docker run --rm --name local642-gen -p 5099:5000 --network development_default`).
**Never** `docker compose -p audioura`; **never** renamed or replaced an `audioura-*`
container; image + container removed on exit. `DISABLE_TOUR_CACHE=1`,
`DISABLE_STOP_POOL=1`. Cap $0.90 (`TEST_GEMINI_MAX_USD` / `COST_HARD_LIMIT_USD`), with a
per-tour reserve gate (0.55). Harness: `run_local642_container.py`,
`run_local642_live.sh` (artifacts under `tours/local642_live/`, gitignored; the
delivered text + critique are copied into `submission_artifacts/local642_live/`).

**Row counts (additive `is_test` only; no DELETE):** `audio_tours` **356 → 357** total,
`is_test` **293 → 294**. My row is **551** (National Gallery). No other rows written.

### National Gallery — tour 551 (3 stops) — the exact parenthesized title, delivered CLEAN

```
Stop 1: The Supper at Emmaus
Directions: Continue through The National Gallery — next is The Toilet of Venus ('The Rokeby Venus').
Stop 2: The Toilet of Venus ('The Rokeby Venus')
Address: National Gallery, Trafalgar Square, London WC2N 5DN, United Kingdom
Coordinates: 51.5081, -0.128
Orientation: Stand a little back and to the side …
Directions: Your final stop in The National Gallery: The Hay Wain.
Stop 3: The Hay Wain
That's 3 stops in all.
```

Harness report:
```
OUTCOME: DELIVERED — 5079 chars, 3 stops, wall 414.5s
STOP TITLE: The Supper at Emmaus
STOP TITLE: The Toilet of Venus ('The Rokeby Venus')
STOP TITLE: The Hay Wain
HEADER COUNT: 3   count_delivered_stops: 3   stated 'That's N stops': 3
[LOCAL-642] flatten/dup artifacts: label-glued=False run-on=False dup-transition-block=False
[LOCAL-642] flattened header lines: []
```

The parenthesized title is Stop 2 with its header on its own line, each field label on
its own line, **no flattening and no `Continue to <title> <block>` duplicate**. The
defect is gone on fresh generation.

### Cost (all providers combined, < $0.90)

```
[LIVE_RUN_METER] TEST-LOCAL-642  (cap $0.90, all providers combined)
  openai            $0.6136
  gemini_grounding  $0.0840  (requests=6, queries=6)
  gemini_tokens     $0.0303
  serper            $0.0390
  preflight         $0.0308
  TOTAL             $0.7669
```

### Detectors + critique

```
$ python3 ~/Audioura/.continuous_dev/bench/detectors.py 551 3 "National Gallery"
551: 0 detector failure(s)        (exit 0)
```

`venue_as_stop` **PASSES**, together with `stop_count`, `parenthetical_title` and every
other regression detector (including the flattening family).

`critique.sh 551 3` → **6.5/10** (`submission_artifacts/local642_live/critique_551.md`).
It confirms the LOCAL-642 defect is gone — the parenthesized Stop 2 is clean and
"All three works genuinely hang at the National Gallery (no misattributed-museum
defect)". The remaining items it flags (a confused Borghese provenance claim at Stop 1,
a dropped word in "nestled between the counties and Essex" — missing *Suffolk*, Stop 2
thinness) are **pre-existing content-quality issues unrelated to the header/field-line
defect this ticket fixes**.

---

## Process

- Branch created from HEAD at `subscribed` @ `de54df9`; never from `origin/*`.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md` or
  `.continuous_dev/STATUS.md`.
- Committed after each step; `git rev-list --count origin/subscribed..HEAD` ≥ 1.
- No DELETE (the single is_test row 551 is additive). No GCloud.

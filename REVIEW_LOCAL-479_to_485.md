# LEAD REVIEW — LOCAL-479, 480, 481, 483, 484, 485
### 2026-09-17, Storied_Tours. Six submissions reviewed as one batch because four of them are D565's "tour-purpose work".

**Reviewed against the true diff** (`git diff $(git merge-base storied HEAD)..HEAD`), not
`storied..HEAD`. The naive form made LOCAL-480 look like it deleted 3,424 lines; every one of
those was storied moving ahead of the branch's base. Same class of error as D242's
"regression is a claim about two trees".

---

## Verdicts

| task | verdict | note |
|---|---|---|
| LOCAL-479 one-token names + orphaned dependants | **APPROVE** | has a real container run on tour 423's actual stop-4 text |
| LOCAL-480 `facility` venue class (D563) | **APPROVE, merge second** | Overpass is mocked throughout — live OSM path is unproven, LEAD verifies |
| LOCAL-481 a stop must be a real place | **APPROVE with a merge instruction** | branch carries a stray Build-24 commit; see hazard below |
| LOCAL-483 WebView console → debug log | **APPROVE** | diagnostic only, no behaviour change |
| LOCAL-484 stale stop count on Listen | **APPROVE** | the `?? '10'` invented count is gone too |
| LOCAL-485 church/civic routing (D564) | **APPROVE, merge first** | it already wrote the shared detector D564 demanded |

---

## D564's "one detector, not three" — satisfied, and by the later task

D564 ruled that LOCAL-480 and LOCAL-485 must share a single venue-class mechanism. They were
dispatched independently (`git merge-base --is-ancestor c85f61e HEAD` → false: 485's base does
not contain 480), so this could easily have produced two parallel copies. It did not.

**LOCAL-485 wrote the shared primitive and expressed both classes through it:**

```
_detect_venue_class(location, tour_type) -> 'facility' | 'worship_civic' | None
    _detect_facility_class(...)      = (… == 'facility')        # LOCAL-480's seam, preserved by name
    _detect_worship_civic_class(...) = (… == 'worship_civic')
```

**Verified, not taken on the submission's word:** the `_FACILITY_CLASS_WORDS` tuple in 485 is
**byte-identical** to 480's (`diff` → no output), and `_FACILITY_WORD_RE` is the same pattern
under a different import alias. 485 did not silently narrow 480's facility detection while
copying it. That was the thing worth checking, and it holds.

**Merge order is therefore forced: 485 first, then 480.** Both branches add their block at the
same site (after `_build_closing_offer`, ~line 2327), so they conflict. The resolution is
**keep 485's shared block and drop 480's `_detect_facility_class` + `import re as _facility_re`
entirely** — 480's remaining wiring (classifier branch, FACILITY GUARD, need-spine fill,
Phase-3A skip) calls `_detect_facility_class` by name and keeps working against 485's wrapper.

---

## The merge hazard in LOCAL-481 — it would revert the app to build 24

`LOCAL-481-stop-must-be-a-place` carries `92dac9e "Build 24: Add Stop and original audio, both
fixed"`, a **duplicate** of `67c821c`, which is already in `storied`. The duplicate does two
things the task has nothing to do with:

- rewrites `audio_tour_app/pubspec.yaml` **CRLF → LF** (whole file: 44 lines out, 44 in), and
- sets `version: 2.3.2+24`.

**`storied` is at `2.3.2+26` and build 26 is on Michael's phone.** A careless merge resolution
on that file ships a wrong build number. Confirmed by content comparison: ignoring `\r`, the
only real difference between the two versions of the file is the version line.

**Merge instruction:** take `storied`'s `audio_tour_app/pubspec.yaml` and `BUILD_NUMBERS.md`
wholesale. Keep only 481's server-side files — `generate_tour_text.py`, `geocode_stops.py`,
`place_shape.py`, and its three test files.

---

## Standing check 2 — a production importer exists for every new module

Green tests over orphaned modules prove nothing (2026-07-29, `story_element_extractor.py`).
Checked by grep, excluding the tests and the module itself:

| module | production caller |
|---|---|
| `facility_spine.py` | `generate_tour_text.py:6329` `import facility_spine`, called at `:6340` |
| `place_shape.py` | `generate_tour_text.py:1286`, `:9808` |
| `geocode_stops.find/repair_centroid_collapse` | `generate_tour_text.py:9707`, `:9807` |

All three are wired. None is a dead module.

---

## What the submissions did NOT prove, and LEAD must

Both 480 and 485 state plainly that they ran **offline only** — no container rebuilt, nothing
deployed, Overpass mocked. That is the correct, allowed form of report under the live-artifact
gate ("unproven, handing to LEAD"), and both said it without being asked. The unproven parts:

1. **LOCAL-480's live Overpass path.** Every facility test mocks the Overpass client. D563
   measured 331 real mapped objects at Logan by hand, so the *data* exists; what is unproven is
   that `fill_need_spine` gets them through the real rate-limited client. **Free to verify** —
   Overpass needs no key and costs nothing.
2. **LOCAL-485's church tour end to end.** The routing is proved by unit tests and a red/green
   revert; no church tour has actually been generated.
3. **The Cimiez regression control**, which D563/D564 both name as the thing that must not move.

---

## Open finding — LOCAL-479 cuts, and nothing refills

Approving 479 on the merits: cutting an orphan whose introduction a gate already removed is
strictly better than shipping "The plane…" with no plane. But its own container run takes
tour 423's stop 4 from 217 words to **two sentences (~25 words)**, and the submission does not
say what happens next. `LOCAL-420` ("never ship an empty stop") catches empty, not thin.

Not a bounce — the change is an improvement as it stands. Filed as a follow-up: **a stop that
falls below the length floor after gate cuts must be regenerated or dropped, not shipped thin.**

---

## Other things noticed

- **The tour-generator container is stale again** — `/app/generate_tour_text.py` is
  `e0d8343…`, storied's working tree is `499ca05…`. The D531 failure mode. Host runs are
  unaffected; anything verified through the container is not.
- **Container names have moved from `development-*` to `audioura-*`.** `CLAUDE.md` still tells
  a fresh session to use `development-tour-generator-1`, which no longer exists. Postgres is
  still `development-postgres-2-1`.
- **Both ALERTS.md alarms are worth a look but neither is an incident.** The four "secrets" are
  `$HOME/...` **paths** in `build_ios_release.sh` / `upload_testflight.sh` and a test token
  literal — false positives from the entropy rule. Disk is at **4.9 GB free with 18 worktrees**;
  that one is real and will bite a Docker build before it bites anything else.

---

# LEAD VERIFICATION — what the live runs showed
### 2026-09-17, after merging all six. The submissions' own tests all pass; these are the things only a real run could say.

## Merge result

All six merged into `storied`. One conflict, exactly where the review predicted:

- **`generate_tour_text.py`, 4 conflicting hunks** between 480 and 485. Resolved as planned —
  485's shared `_detect_venue_class` block kept, **480's duplicate `_detect_facility_class` and
  its `import re as _facility_re` dropped**; the classifier and the post-convergence guards take
  **both** branches with facility first. The tree now contains exactly one facility detector
  (`grep -c "^def _detect_facility_class"` → 1), which is D564's ruling made literal.
- **`audio_tour_app/pubspec.yaml` + `BUILD_NUMBERS.md`** conflicted on the 481 merge, as the
  review warned. Resolved to storied's side: **version stays `2.3.2+26`**, CRLF preserved.

**41/41** facility+venue-class tests, **23/23** LOCAL-481 tests, **132/132** Flutter tests green.

### Regression check done properly (D242)

The full Python run shows 20 failures and 37 collection errors. **None is ours.** The collection
errors are missing host deps (`bs4` ×18, `selenium` ×12, `Crypto` ×4) and three py3.9 f-string
syntax errors in old scraping scripts. For the 368/369/370/373 exhibition-extraction failures —
which matter because 485 *does* touch `generate_tour_text.py` — a worktree at the pre-merge
commit `a3d4e9d` gives **9 failed / 88 passed**, and the merged tree gives **9 failed / 88
passed**. Identical. (They also pass individually and fail in a full run: pre-existing
test-order pollution, on both trees.)

### One pre-existing failure removed rather than carried

`audio_tour_app/test/widget_test.dart` was the stock Flutter counter-app template — importing
`package:audio_tour_app/main.dart` when the package is `audio_tour_app_dev`, pumping a `MyApp`
that does not exist against a `+` button this app has never had. Untouched since "First commit"
and red ever since, which made `Some tests failed.` the suite's normal output. Deleted; the
suite is now green at 132. Revert with `git revert` if it is wanted back.

---

## FINDING — LOCAL-480's need-spine collapses on the live Overpass, and every test mocked it

This is the one thing the task could not have caught, and it is significant.

`fill_need_spine` issues **one Overpass query per need slot, ten of them, sequentially, with two
retries each.** Against the live endpoint, three consecutive runs at Logan returned:

| run | elapsed | stops | slots lost to transient Overpass errors |
|---|---|---|---|
| 1 | 131s | 5 | `food_water`, `art_exhibits`, `baggage` (429 → 504) |
| 2 | 148s | 6 | `security`, `kids`, `lost_and_found` (504) |
| 3 | 133s | **2** | eight slots (429 → ConnectionError) |

**The mechanism itself is correct.** What came back is exactly what D563 promised — real, named,
distinctly-located mapped objects with their source recorded:

```
terminal_gates | Terminal C | (42.366761, -71.016081) | OSM way/29518154
food_water     | Dunkin'    | (42.365354, -71.014643) | OSM node/5380463925
```

Note those two coordinates differ in **both** axes — LOCAL-481's centroid-collapse detector would
pass them, where all four of tour 423's stops shared latitude `42.3656` exactly.

**The defect is that "findable or cut" cannot tell "not mapped" from "Overpass was busy."** A
transient 504 deletes a stop that exists. D563 counted 68 food-and-drink objects at Logan by
hand; run 1 shipped none of them because one query timed out. The listener would get a tour
missing food and baggage claim and never learn it was a network hiccup.

**Honest qualifier:** part of run 3's severity is self-inflicted — three full sweeps in seven
minutes is exactly what earns a 429. A single user request would not hammer it that way. But
run 1 was cold and still lost three slots, so the defect stands on its own.

**Fix direction (not dispatched — see the note on unattended spend):** D563 got all 331 Logan
objects in **two** hand-written queries. Ten sequential queries is the wrong shape. Combine them
into one query with an alternation, and — separately and more important — **distinguish an empty
result from a failed request**, so an errored slot is retried or reported, never silently cut.

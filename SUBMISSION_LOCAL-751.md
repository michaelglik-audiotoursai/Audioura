# SUBMISSION — LOCAL-751: Exhibit museums generate again, and a place the user names is never silently dropped

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-751-exhibit-museums-named-places`
**Base:** `subscribed` @ `1942ea37` (`git merge-base --is-ancestor 1942ea37 HEAD` → exit 0)
**code_sha:** `43e48668cb159299f1ad72540dd6330bb0cb6702`

---

## What was broken (Michael, 2026-10-23, iPhone, local stack)

**A. Museums with no catalogued collection were refused.** "The Salem Witch Museum,
Salem MA" and "Salem Museum of Torture" clean-failed even though the official site
was found. D1v2 only knew how to match a *catalogued artwork title*, so it dropped
every exhibit/room/presentation and the tour clean-failed `unresolvable`.

**B. "Walking tour in Danvers, MA including Witchcraft Victims Memorial" dropped the
memorial.** The area parser read `city='MA including Witchcraft Victims Memorial.'`,
so area resolution failed and the named memorial was silently dropped.

---

## Fix summary

### A — Exhibit-museum detection (`generate_tour_text.py :: _verify_works_v2`)
A museum with **0 SPARQL works** but a reachable site that **names its exhibits** is an
*exhibit museum*. The fail-closed rule stays (no invented exhibits):

- Remember the titles the LOCAL-625 room/space guard and the LOCAL-653 site-junk guard
  remove as `_exhibit_names` — for an exhibit museum those ARE the tour's material.
- After the normal candidate loop, a **second-chance pass** re-admits a `DROPPED`
  ('no canonical match') candidate when it (a) matches one of those sourced exhibit
  names (exact or ≥4-char substring), or (b) is a **sourced subject** the venue's own
  site text presents verbatim (≥2 significant words, e.g. "the 1692 trials").
- Tier `exhibit_museum` requires **≥2 verified exhibits** via this route; below that the
  venue still refuses (today's message).
- **Art museums are untouched**: a museum WITH SPARQL works has `_exhibit_museum_src=False`,
  so the entire new path is skipped.
- **Cache round-trip**: a venue the fresh path generated writes a `venue_corpus` row with
  `tier='exhibit_museum'` whose room/space titles were already stripped. On a later cache
  HIT the second-chance treats the cached (cleaned) titles as exhibit names, so the venue
  generates again instead of clean-failing on the round-trip.

### B1 — Area parser cuts the stops clause (`area_resolver.py :: _parse_location`)
Before any city/state is read, cut a trailing `including … / with … / featuring … /
and visit …` clause (and a trailing period). "Walking tour in Danvers, MA including
Witchcraft Victims Memorial" → "Danvers, MA". The LOCAL-351 US `City, ST [ZIP]` contract
is preserved (only the clause is cut).

### B2 — A user-named place is never silently dropped (D562)
`area_resolver.build_named_place_announcement(name)` →
`"We could not confirm <name>, so it is not part of this tour."`
`area_resolver.apply_named_place_policy(poi_list, named_places, area, landmarks, new_poi_fn)`
verifies each named place against the resolved area's discovered landmarks (the same
matcher the walking path uses). A match is **kept** (user_explicit + verified, at the front
of the list, with the landmark's Wikidata QID/coords); a non-match is **announced** in the
Orientation and **never silently removed**. Wired into WALK-D1 and spliced into the
Orientation at the single every-path delivery choke point (`_apply_delivery_hours_guard`),
reset per generation so it cannot bleed between tours.

**The named-place source does not depend on the AI intent call.** The live Danvers run
(below) exposed that the first commit fed the policy only from `intent.named_places`, and
when PHASE-1 intent analysis returned **HTTP 429** that list was empty — so the existence
gate silently dropped the memorial, the exact D562 violation. The second commit adds
`area_resolver.extract_named_places_from_clause()`, a **deterministic** parse of the same
"including/with/featuring/and visit X" clause (splits on `and`/`&`/`,`, strips a leading
article and trailing period), and WALK-D1 now **unions** those names with
`intent.named_places`. The protection survives a failed model call.

**Files changed:** `generate_tour_text.py`, `area_resolver.py`.
**Files added:** `test_local751_area_parse_danvers.py`, `test_local751_named_place.py`,
`test_local751_named_place_delivery.py`, `test_local751_exhibit_museum.py`,
`run_local751_container.py`, `run_local751_live.sh`.

Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`.

---

## Red tests (fail on `027584b0`, pass after the fix)

All proved RED on the baseline tree (`git worktree add --detach … 027584b0`, 0 LOCAL-751
markers in the baseline sources, test files copied in), GREEN on HEAD.

```
test_local751_area_parse_danvers.py   3 tests — "including …" clause cut; no leak; US ZIP form intact
test_local751_named_place.py          8 tests — announcement wording; kept-when-verified;
                                                 announced-when-not; + clause extraction (5)
test_local751_named_place_delivery.py 2 tests — clause → announcement → real Orientation splice
test_local751_exhibit_museum.py       2 tests — 0-SPARQL exhibit site → ≥2 verified, tier
                                                 exhibit_museum (fresh + cache round-trip)
```

Baseline run (temp worktree @ `027584b0`), all RED:
```
8 failed   (first commit's area_parse + named_place + exhibit_museum)
13 failed  (re-run including the clause-extraction + delivery tests from the second commit)
```
HEAD run, all GREEN:
```
$ python3 -m pytest test_local751_area_parse_danvers.py test_local751_named_place.py \
      test_local751_named_place_delivery.py test_local751_exhibit_museum.py -q
15 passed
```

Baseline parse reproduction (on `027584b0`):
```
city='MA including Witchcraft Victims Memorial.', neighborhood='Danvers'   # clause corrupts the city
```
After B1 (live, below): `Parsed: city='MA', neighborhood='Danvers'` → `city='Danvers'`.

---

## Regression (art-museum / D1v2 / LOCAL-625 / LOCAL-589 / LOCAL-580 suites)

Final on HEAD (pytest-collectable unit suites):
```
$ python3 -m pytest test_local625_facts_and_selection.py test_local589_*.py \
      test_local580_*.py test_local425_* test_local465_* test_local751_*.py -q
3 failed, 103 passed
```
The **3 failures are PRE-EXISTING on `027584b0`** — confirmed identical on the baseline tree
via a temp worktree. All three stem from the LOCAL-653 guard pruning
`'Lua Kobayashi | The Persistence of Memories'` from the Griffin Museum `canonical_titles`
SET, unrelated to LOCAL-751:
```
test_local589_canonical_set_chrome_free.py::test_corpus_canonical_set_has_no_chrome_and_keeps_shows
test_local580_site_first_candidates.py::test_candidates_are_the_site_exhibitions_in_order
test_local580_site_first_candidates.py::test_detail_page_text_is_per_stop
```
LOCAL-751 actually **improves** the Griffin case: baseline verified 3/4 works; with the
exhibit second-chance the 4th (`Lua Kobayashi …`) is re-admitted → **4/4 verified**
(`[LOCAL-751] EXHIBIT VERIFIED … (exhibit_name_on_site)` in that test's stdout).

Note: `test_local24_corpus_filter.py` / `test_local24_regression.py` are live-DB scripts
(require Postgres + network scraping; 0 pytest-collectable tests) — not part of the unit
regression above.

---

## Live test (own disposable container only)

Container `local751-gen` (`docker run --rm`, spare published port **5151**, network
`development_default`); rows inserted additive `is_test=true`, `lat/lng NULL` into
`development-postgres-2-1`. **No `audioura-*` container was touched. No
`docker compose -p audioura`.** Tour cache OFF, stop pool OFF (fresh). Metered and
hard-capped at **$1.50** for the whole task by `tests/live_run_meter.py` with a reserve
gate before each arm.

`audio_tours` row count **BEFORE: total 515 (is_test 434)** → **AFTER: total 518
(is_test 437)** — **+3 additive `is_test=true` rows, `lat/lng NULL`** (TORTURE refused, so
no row). **No `DELETE`** performed. Verified in the DB:
```
 id  | is_test | lat | lng | stops_count
 743 | t       |     |     |  4   The Salem Witch Museum (SALEMWITCH)
 744 | t       |     |     |  2   Walking tour in Danvers (DANVERS)
 745 | t       |     |     |  2   Isabella Stewart Gardner Museum (GARDNER)
```

### 1) The Salem Witch Museum, Salem MA — 4 stops — DELIVERED, tier `exhibit_museum` ✅
The **core A fix**, proven live: baseline clean-failed this venue `unresolvable`; now it
generates. Log (verbatim):
```
[LOCAL-751] EXHIBIT VERIFIED 'The Witch Trials of 1692' → 'The Witch Trials of 1692' (sourced_subject_on_site)
[LOCAL-751] EXHIBIT VERIFIED 'The History of Witchcraft' → 'The History of Witchcraft' (sourced_subject_on_site)
[LOCAL-751] Exhibit-museum second chance re-admitted 2 exhibit stop(s) from the venue's own site
[D1v2] Exhibit museum detected: 0 SPARQL QIDs, 8 canonical + 2 exhibit stop(s) from the venue's own site
[D1v2] 2/4 works verified — tier: exhibit_museum
[D1] Tier: exhibit_museum (2 verified works)
```
Stop list (verbatim):
```
Stop 1: The Witch Trials of 1692
Stop 2: The History of Witchcraft
Stop 3: Arresting a Witch
Stop 4: City on a Hill
```
Orientation opening (verbatim):
```
Orientation: Stand nearer the center of the room to take in the full breadth of the
multimedia exhibit titled "The History of Witchcraft." From this vantage, the sweeping
timeline unfolds before you, tracing the evolution of witchcraft imagery from ancient
times to modern pop culture.
```
`id=743`, cost **$1.0118**, 431.7s.

### 2) Salem Museum of Torture, Salem MA — 4 stops — NO TOUR (fail-closed) ✅
`tier=exhibit_museum`, refused with **fewer than 2 verified exhibits** — the correct
fail-closed behaviour (no invented exhibits, no row stored). 23.5s, **$0.00**.

### 3) Walking tour in Danvers, MA including Witchcraft Victims Memorial — DELIVERED ✅ (B1) / gap found → fixed (B2)
**B1 clause-cut proven live** (log, verbatim):
```
[area_resolver] Parsed: city='MA', neighborhood='Danvers'
[area_resolver] 'MA' resolved as country (Q1028), swapping: city='Danvers'
[area_resolver] City resolved: Danvers → Q1066487
```
(Baseline parsed `city='MA including Witchcraft Victims Memorial.'` — the clause is now cut.)

Stop list (verbatim): `Stop 1: The Danvers Historical Society`, `Stop 2: The Danvers State
Hospital`. `id=744`, cost **$0.0531**, 159.8s.

**Gap found in this live run (honest finding):** PHASE-1 intent analysis returned
`Intent analysis failed: 429`, so `intent.named_places` was `[]`. The memorial therefore
never reached the named-place policy, and the existence gate dropped it **silently**:
```
[UNVERIFIED] 'Witchcraft Victims Memorial' — no evidence
DROPPED: 'Witchcraft Victims Memorial'          ← no announcement — a D562 violation
```
This is exactly the failure the ticket forbids, and it was a real gap in the first commit
(which sourced named places only from the AI intent). **Fixed in commit `43e48668`** with
the deterministic clause parser + WALK-D1 union described above, verified by:
- `test_local751_named_place.py::TestNamedPlaceClauseExtraction` (5 tests) — the exact
  request `"Walking tour in Danvers, MA including Witchcraft Victims Memorial"` →
  `["Witchcraft Victims Memorial"]`, and that name drives the policy when intent is empty.
- `test_local751_named_place_delivery.py` (2 tests) — the full chain with the **real**
  helpers (`extract_named_places_from_clause` → `apply_named_place_policy` →
  `build_named_place_announcement` → `screen_work_tour.inject_orientation_disclosure`),
  asserting the sentence lands at the opening of a field-shaped delivered Orientation:
  `"We could not confirm Witchcraft Victims Memorial, so it is not part of this tour."`

A fresh live re-run of DANVERS to observe the announcement in delivered output could **not**
be produced: the first full run consumed the remaining OpenAI credits, and the re-run
returned `credit_balance_exhausted` ("You have no credits remaining", `insufficient_quota`,
HTTP 429, `$0.00`, no rows). This is an account-level external blocker, independent of the
code. The fix is proven by the unit + integration tests with the real helpers above.

### 4) Isabella Stewart Gardner Museum, Boston — DELIVERED, tier `rich` ✅ (art regression)
Unchanged art-museum behaviour. Stop list (verbatim): `Stop 1: The Rape of Europa`,
`Stop 2: Chez Tortoni`. Orientation opening (verbatim):
```
Orientation: Isabella Stewart Gardner Museum currently has 2 exhibitions on view, so this
tour has 2 stops rather than the 4 you asked for. Stand before Titian's "The Rape of Europa"
in the Isabella Stewart Gardner Museum and let your eyes follow the bold, sweeping
brushstrokes that capture a moment both mythic and intimate.
```
`id=745`, cost **$0.2203**, 294.5s.

### Cost

| Tour | Outcome | per-tour cost |
|------|---------|------|
| Salem Witch Museum | DELIVERED (exhibit_museum, 4 stops) | $1.0118 |
| Salem Museum of Torture | fail-closed (NO TOUR) | $0.0000 |
| Danvers walking | DELIVERED (2 stops; clause cut) | $0.0531 |
| Isabella Stewart Gardner | DELIVERED (rich, 2 stops) | $0.2203 |

**Total THIS RUN spend (host, measured against baseline): `$1.031847` — UNDER the $1.50
task cap.** The DANVERS verification re-run cost **$0.00** (credits exhausted). Task total
remains **$1.03**.

### Cleanup

No `DELETE` was run (the three additive `is_test` rows are left per the ticket). The
disposable image/container were removed; `docker ps -a`/`docker images` show no
`local751-*` entries, and `git worktree list` shows no `/tmp` baseline worktrees.

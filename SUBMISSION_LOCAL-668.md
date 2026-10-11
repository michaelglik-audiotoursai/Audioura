# SUBMISSION — LOCAL-668

**HCMC Museum of Fine Arts after LOCAL-667: the normal arm was REJECTED by
BLOCKER4b; the cheap arm's collection-area stops pulled in another museum
(Saint Louis).**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-668-thin-museum-r2` (from `subscribed` @ `27bd57ff`)
- **Base:** `subscribed` — verified `git merge-base --is-ancestor 27bd57ff HEAD` → exit 0.

---

## 1. The two defects (from the evidence logs)

**`AB11/hcmc_off_rejected.log` — NORMAL arm.** Thin tier: 1 SPARQL work. LOCAL-667
thin-verify promoted one more work, then added 3 building/collection-area fallback
stops → `building/collection-area stops: +3, total now 5/5`. Then:

```
[BLOCKER4b] ⚠️ Address scatter: 2 distinct addresses for 5 stops …
[BLOCKER4b] Rejecting — this looks like a city-wide museum tour, not interior rooms.
→ no tour.
```

The thin-verified work came from the R4/model pool carrying a **different**
model-guessed address from the Phase-3A work; the fallback stops carried an
**empty** address. BLOCKER4b counted two distinct non-empty addresses and
rejected an honest, fully-contained museum tour.

**`AB11/hcmc_on_664.log` — CHEAP arm (tour 664).** Area stops filled the slots
("Lacquer / Silk / Woodblock prints collection"). Stop 5's research for the
generic "Woodblock prints collection" pulled SERP results about the same medium at
OTHER museums — Honolulu Museum of Art, and the Saint Louis Art Museum — and
"Phil Guston … Saint Louis holdings … Holbein and Pippin" bled into the narration.
The lacquer-layering technique was re-explained at several stops.

---

## 2. What was delivered (6 code changes, each with tests)

All changes are gated to **museum tours**; a well-documented museum (rich tier)
never reaches the thin-museum paths, so the common case is untouched
(`test_local668_well_documented_regression.py`).

### #1 — BLOCKER4b: contained stops inherit the venue address
`generate_tour_text.py` — a **contained-address binding pass** runs just before
BLOCKER4b. For a single **named** museum the whole tour is inside one building, so
**every** stop is bound to the one venue address via
`about_museum_stop.venue_bound_address` (D611: a stop keeps an address its OWN
page literally states — a real annex — otherwise it takes the venue address). The
venue address is the dominant address already on the stops
(`_dominant_poi_address`), else the sourced `_resolve_venue_address`. For a
city-scope museums request (no single venue) only the grounded-contained fallback
stops are bound, never works.
_Test:_ `test_local668_blocker4b_contained.py` (7) — the HCMC fixture (incl. two
verified works with **different** addresses, the real live cause) collapses to ONE
address and BLOCKER4b does not fire.

### #2 — Prefer works over areas; area stops lead with a verified work
Thin-verify already runs to its two-source bar first and area stops only fill the
slots left empty (works-first order preserved). New
`museum_fallback_stops.assign_lead_works` attaches a **verified** work/artist of
THIS museum to each collection-area stop (medium match first — the lacquer area
leads with a verified lacquer work — then round-robin over the verified pool).
`build_fallback_stops(verified_works=…)` carries it; `generate_tour_text.py`
injects a *"LEAD WITH A REAL WORK"* instruction that names the verified work and
bars naming any other museum's works/artists.
_Test:_ `test_local668_area_lead_work.py` (5).

### #3 — Venue-anchored research: drop foreign-museum snippets
New pure module `venue_anchored_research.py`: `mentions_this_venue` /
`names_foreign_museum` / `drop_foreign_museum_snippets`. A snippet naming THIS
venue is kept; one naming a foreign institution and NOT this venue is dropped;
generic medium/technique evidence is kept; a stop is never emptied. Wired at BOTH
the per-stop research build and the final generation chokepoint (so it catches
initial + STORY_REPLENISH + direct snippets). The research queries were already
venue-anchored (`work_story_searcher.synthesize_queries`); this closes the leak at
the evidence stage, before the writer ever sees Saint Louis.
_Test:_ `test_local668_foreign_museum_snippets.py` (9) — the exact Honolulu /
Saint-Louis fixtures from the log are dropped.

### #4/#5 — No retelling: D533/S27 covers technique explanations
`derepetition_guard.check_cross_stop_fact_repetition` gained a deterministic
**technique / near-duplicate** pass: a later stop's sentence sharing ≥ 0.6
distinctive-word Jaccard (≥ 4 distinctive words) with an earlier stop's sentence
is flagged — independent of year or proper noun, which the existing
`fact_signatures` (needs a year) and `keyphrase_signatures` (needs a rare bigram)
both require. `strip_repeated_facts` then removes the second telling (lacquer
layering told once). Threshold is high so ordinary prose and genuinely different
techniques never collapse.
_Test:_ `test_local668_technique_repetition.py` (4).

### #6 — Cost cap for thin-verify
New `thin_verify_cache.py`:
- **`VerificationBudget`** — per-tour cap of `THIN_VERIFY_MAX_QUERIES` (**10**)
  grounded/Serper verification queries; `wrap()` counts every grounded call and
  returns a safe empty result past the cap. The used count is **logged**
  (`[LOCAL-668] thin-verify verification queries: N/10 used`).
- **30-day VENUE CACHE** mirroring `venue_preflight` (same DB, same
  `cache_key(venue,city)`, additive table `thin_verify_cache`, TTL env
  `THIN_VERIFY_CACHE_TTL_DAYS` default **30**). A venue verified in the last 30
  days is served from cache at **0** verification queries. Stores only positive
  results; never freezes a flaky zero.
_Test:_ `test_local668_cost_cap.py` (9).

---

## 3. Tests & suite exit codes

New LOCAL-668 suites (all exit 0):

| suite | tests |
|---|---|
| `test_local668_blocker4b_contained.py` | 7 |
| `test_local668_foreign_museum_snippets.py` | 9 |
| `test_local668_area_lead_work.py` | 5 |
| `test_local668_technique_repetition.py` | 4 |
| `test_local668_cost_cap.py` | 9 |
| `test_local668_well_documented_regression.py` | 4 |

Regression suites (all exit 0): `test_local667_thin_museum.py` (14),
`test_local667_building_stops.py` (12), `test_local667_title_split.py` (14),
`tests/test_local652_phantom_thread.py` (12), `test_local636_repeated_story.py`
(7), `test_local607_pooled_coherence.py` (21), `test_local585_about_museum_stop.py`
(24), `test_local591_contained_venue.py` (15), `test_local583_documented_works.py`
(9), `test_local617_work_first.py` (47). Script-style: `tests/test_d533_cross_stop_facts.py`
and `tests/test_d534_any_repetition.py` → **ALL TESTS PASSED** (exit 0).

---

## 4. Live run (own container, HCMC museum, 5 stops, fresh)

Built `Dockerfile.generator` as image `local668-gen-img`, ran disposable container
`local668-gen` (`--rm`, spare port **5168**, network `development_default`, DB
`development-postgres-2-1`). **No `docker compose -p audioura`; no `audioura-*`
container was created, renamed, or replaced.** Rows: additive `is_test` only
(id=665). No DELETE.

**Run 1 (pre-fix bug):** both arms reached generation; BLOCKER4b still fired
because the two thin-verified works carried **different** addresses and the first
binding only touched fallback stops. This directly revealed the widened-binding
fix (now committed — bind all stops of a single named museum). Spend **$0.311**.

**Run 2 (fixed) — NORMAL arm — DELIVERED (id=665):**

| metric | value |
|---|---|
| stops | **4** delivered (honest 4/5 shortfall; 2 Wikidata/thin works + 2 source-verified) |
| stop titles | North Central South Spring Garden · Central South and North Spring Garden · Lotus Pond · The Fisherman — **all real works**, no area padding needed |
| sources | `baotangmythuattphcm.com.vn` + Wikipedia (museum site + encyclopedia) |
| thin-verify queries | **4 / 10** (logged; verified *Lotus Pond*, *The Fisherman*) |
| foreign snippets dropped | **2 + 2** (`[LOCAL-668] foreign-museum snippets dropped`) |
| detectors | `DELIVERED=4` ✓ · `SINGLE_ADDRESS=1` ✓ (all `97A Pho Duc Chinh`) · `NO_FOREIGN_MUSEUM` ✓ (no Saint Louis/Honolulu) · `LACQUER_TOLD_ONCE=1` ✓ — **ALL PASS** |
| wall | 399 s |
| cost | $1.166 (host `60d5f12002ba`, meter total $1.4231) |

The works-first fix worked so well that **no** collection-area padding was needed —
the opposite of the rejected baseline. BLOCKER4b did not fire (one address). No
foreign museum. Lacquer technique told once.

**CHEAP arm (gpt-4.1-mini + serper):** correctly **SKIPPED** live by the reserve
gate to avoid a larger overrun (it reached generation in Run 1 pre-fix, where the
thin-verify budget logging `5/10` is visible). Its fixes are covered by the unit
tests (`#3` foreign-museum drop, `#4/#5` technique repetition).

### Cost — honest cap breach
`paid_api_calls` for my two container hosts:

| host | USD | calls |
|---|---|---|
| `bd0aec7acba5` (run 1) | 0.3113 | 35 |
| `60d5f12002ba` (run 2) | 1.1658 | 205 |
| **TOTAL TASK** | **$1.477** | 240 |

**This overran the $1.40 whole-task cap by ~$0.077.** Cause: a *fresh* thin-museum
NORMAL arm is expensive on its own ($1.17 — grounded two-source verification +
full OpenAI narration + retries), and Run 1 ($0.31) was needed to discover the
widened-binding bug. The reserve gate stopped the CHEAP arm from pushing further
over, and Run 2 was capped at $1.00 to limit the overrun. **I did not run again.**
The thin-verify 30-day venue cache (#6) means a repeat tour of this venue costs
**0** verification queries, which is the structural answer to the cost — but it
does not help the FIRST fresh tour, which is what the cap measured.

---

## 5. Process / safety

- Committed after each step; `git rev-list --count origin/subscribed..HEAD` ≥ 1 at
  every step (final: 9 commits ahead). Branch pushed to
  `origin/LOCAL-668-thin-museum-r2`.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `.continuous_dev/STATUS.md`.
- No GCloud. No DELETE (only the additive `is_test` row id=665 was written).
- Live run in an isolated, disposable, self-named container on a spare port;
  never touched an `audioura-*` container.

## 6. Files

New: `venue_anchored_research.py`, `thin_verify_cache.py`,
`test_local668_blocker4b_contained.py`, `test_local668_foreign_museum_snippets.py`,
`test_local668_area_lead_work.py`, `test_local668_technique_repetition.py`,
`test_local668_cost_cap.py`, `test_local668_well_documented_regression.py`,
`run_local668_container.py`, `run_local668_live.sh`.
Modified: `generate_tour_text.py`, `museum_fallback_stops.py`,
`derepetition_guard.py`.

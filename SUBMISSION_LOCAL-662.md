# SUBMISSION — LOCAL-662: Boston walking v9 (Kiro 5.5) — four defects fixed

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-662-walking-v9` (from `subscribed` @ `0e0b4897`)
**Base:** `subscribed` — `git merge-base --is-ancestor 0e0b4897 HEAD` → exit 0 ✓

Kiro 5.5 scored tour 557 v9 — the Boston *"Massachusetts politics and current
affairs"* **walking** tour — 5.5/10 for four defects. All four are fixed, with a
dedicated offline test suite and one live paid tour that reproduces the exact
request and proves every defect gone.

---

## The four defects and their fixes

### 1. An unverified stop ("The State House Park")

**Cause.** The stop-existence gate (LOCAL-245) runs in `LOG_ONLY` on the shared
stack, so an invented walking stop ("The State House Park", also in AB7 tour 646)
that resolves to no Wikidata item and no OSM feature was *logged* but never
dropped — and its narration then invented facts (Olmsted "shaped" it, a monument
"designed by Boston architects", "granite stones" on the Freedom Trail).

**Fix.** A WALKING tour has no venue page to ground a stop against (unlike a
museum, whose own exhibition page is the stronger evidence, LOCAL-437/D532), so
an invented stop has only the model's word behind it. For walking/specialized
outdoor tours the gate is now forced to **ENFORCE**:

* `stop_existence_gate.get_gate_mode_for_category(tour_category)` raises the
  shared-stack `log_only` to `enforce` for `walking`/`specialized` (museum and
  dining keep the global mode; an explicit `off` kill-switch always wins; a
  `WALKING_EXISTENCE_GATE_ENFORCE=0` escape hatch disables the override alone).
* Wired into the generator gate call site via `_eg_cat_mode(tour_category)`. An
  unverified walking stop is dropped and replaced through the GEO-CHECK
  replacement path (distance-checked, LOCAL-658) / LOCAL-290 replenishment, else
  the tour ships N−1 with the honest shortfall. Museum tours are untouched.
* **Also fixed a latent crash on this very path:** `_fetch_wikidata_coords` had
  lost its `def` line (its body was orphaned after `_extract_geographic_proper_
  nouns`'s `return`), so the Wikidata geographic-coordinate check a walking stop
  relies on would have raised `NameError`. Restored.

`stop_existence_gate.py`, `generate_tour_text.py` — commit `bd9d782a`.

### 2. A leaked editor marker

**Cause.** The stop editor (LOCAL-628) appends `<!-- LOCAL-628:stop-editor:v1 -->`
as the **last line** for idempotence. The LOCAL-655 news pass runs *after* it and
appends news to the last stop block — whose span runs to end of text and so
**includes the marker line** — leaving the marker mid-text, before Stop 5's news.
The `markers` detector failed on `<!--`.

**Fix.** Two guarantees in `generate_tour_text.py`:

* `_apply_current_affairs_news` strips the marker **before** injecting news, so
  the news pass only ever sees narration and can never weld news after it.
* The delivery guard strips the marker as its **final step**, after all text
  mutation and before the file write, on **every** path (normal/cache/pool/
  by_reference). The marker survives only in the cache/pool copies (for
  idempotence); the delivered text, TTS input and critic input never carry it.

Commit `6d0511b8`.

### 3. Too much news

**Cause.** `inject_news_into_text` injected into **every** matched stop (news on 4
of 5 stops — a news feed), and `_attribution_suffix` appended a trailing
`(Reported by NBC Boston, Boston Herald.)` source list to each block.

**Fix.** `current_affairs_news.py`:

* `research_news_for_stops` now **caps** after assignment: rank every assigned
  item newest-first, keep the top `CA_NEWS_MAX_ITEMS_TOTAL` (**3**), then keep
  only the `CA_NEWS_MAX_STOPS` (**2**) freshest stops. Per-stop sentence count
  tracks the kept item count. (Both env-overridable; defaults are the ticket's.)
* `_attribution_suffix` returns `""` always — the `(Reported by …)` parenthetical
  is dropped **entirely** (LOCAL-655B kept it only for unnamed sources). The
  composer prompt now **requires** each sentence to name its outlet inline ("the
  Boston Herald reported", "…, according to NBC Boston"), so attribution survives
  without the list; `[n]` citations are stripped by `_strip_cites`.
* Updated the three `test_local655` tests that encoded the superseded contract.

Commit `5433b1c6`.

### 4. A sentence collision

**Cause.** Tour 557 v9 Stop 3: *"…about what civic architecture could Seven years
later, in 1976…"*. The sentence lost its complement **and** its terminator,
welding a dangling modal ("could") straight into a capitalised sentence-start
("Seven"). The LOCAL-654 splitter only cuts on a period-with-no-space weld
("depths.Thousands"), and the D638/closed-set broken-join detector only knows
`{During, After, Before, In, The, This, When}` — so neither saw "could Seven".
Confirmed via `LOCAL654_DUMP`-style collision scan on the real tour text.

**Fix.** `stop_editor.py`: a new open-starter detector/repair
`detect_dangling_modal_join` / `repair_dangling_modal_joins`, keyed on **modals +
do/does/did only** — the only left-hand words that cannot take a noun complement,
so a modal welded to a Capital is always a tail-truncation. It drops the
unrecoverable dangling modal, terminates the clause and lets the Capital open its
own sentence ("…civic architecture. Seven years later…"). Folded into
`repair_broken_joins` + `detect_broken_join`, so the delivery-path guard
(`repair_broken_joins_in_text`) and the editor's `validate_edit` gate both catch
it. Legitimate prose is untouched — a copula predicate ("is Mona Lisa"), a
prepositional object ("to Paris", "of Architects") and a transitive object ("had
Boston") are never hits.

Commit `976b8105`.

---

## Tests (offline, with exit codes)

Fixture `tests/fixtures/local662/tour_557_v9_stop3_collision_and_marker.txt`
reproduces the real Stop-3 `could Seven` collision **and** the leaked marker
before Stop 5's news. `tests/test_local662_walking_v9_defects.py` — 17
deterministic tests, one class per defect.

| suite | exit | result |
|---|---|---|
| `tests/test_local662_walking_v9_defects.py` | 0 | 17 passed |
| `tests/test_local654_no_midclause_collision.py` | 0 | 8 passed |
| `test_local655_current_affairs_news.py` | 0 | 58 passed |
| `test_local628_stop_editor.py` | 0 | 23 passed |
| `test_local646_walking_regressions.py` | 0 | 13 passed |
| `test_local650_walking_route.py` | 0 | 30 passed, 3 skipped |
| `tests/test_local658_walking_v4.py` | 0 | 22 passed |
| `tests/test_local660_walking_v7_defects.py` | 0 | 14 passed |
| `test_local630_venue_truth.py` | 0 | 24 passed |
| `tests/test_local614_sentence_splitter_initials.py` | 0 | 6 passed |
| **museum canary** `tests/test_local652_phantom_thread.py` | 0 | 12 passed |
| **museum canary** `tests/test_local611_canary.py` | 0 | 7 passed |
| **museum canary** `tests/test_local286_museum_prolog_and_dedup.py` | 0 | 31 passed |
| **museum canary** `tests/test_local615_paragraph_dedupe.py` | 0 | 7 passed |
| **museum canary** `tests/test_local616_phantom_cross_reference.py` | 0 | 6 passed |

**Pre-existing failures (NOT this work — reproduce identically on base `0e0b4897`):**
`tests/test_local256_fragment_and_label.py` (1 failed / 27 passed) and
`tests/test_local271_r1_damage_and_exhortation.py` (1 failed / 75 passed). Both
live in `style_validator_detector`, which this work does not touch; both fail
identically with the base checked out (verified by checkout + re-run).

---

## Live run (own container; ONE paid tour; cap $0.70)

Built **`local662-gen-img`** from `Dockerfile.generator` on this branch and ran a
disposable container: `docker run --rm --name local662-gen --network
development_default`. It joined `development_default` **only** to INSERT the
delivered tour as one additive `is_test` row into `development-postgres-2-1`.
**Never** `docker compose -p audioura`; **never** an `audioura-*` container
(`audioura-tour-generator-1` stayed healthy throughout); tour cache + stop pool
**OFF** (fresh); **NORMAL arm** (no `NARRATION_MODEL` / `RESEARCH_BACKEND`).

* **Request:** "Walking tour in Boston dedicated to Massachusetts politics and
  current affairs, Boston, MA" — 5 stops, walking, fresh.
* **Outcome:** DELIVERED — `audio_tours` **id = 648** (`is_test = true`), 11 534
  chars.
* **`audio_tours` count:** BEFORE **445** (380 `is_test`) → AFTER **446** (381
  `is_test`). **Additive only. No DELETE.**
* **Spend (this task's run, `live_run_meter` TOTAL): $0.5587** — under the $0.70
  cap. openai $0.3092, gemini_grounding $0.2310 (6 requests / 13 queries),
  gemini_tokens $0.0174, serper $0.0010, preflight $0.0000. `cost_ledger` row
  `9785eb59…`; `paid_api_calls` for the container host = $0.52. ONE paid tour only.

### Stops delivered + existence evidence (from the generator log)

The gate **forced ENFORCE for the walking tour**
(`[LOCAL-662] EXISTENCE-GATE: forcing ENFORCE for 'walking' tour (global mode
LOG_ONLY)`) and **dropped the two invented stops** before narration:

* `[VERIFIED] Faneuil Hall` — stop_corpus
* `[VERIFIED] Massachusetts State House` — stop_corpus
* `[VERIFIED] Old State House` — stop_corpus
* `[VERIFIED] Boston City Hall` — stop_corpus
* `[VERIFIED] Massachusetts State Archives` — stop_corpus
* `[UNVERIFIED] Parkman Bandstand` — **no evidence → DROPPED**
* `[UNVERIFIED] The Boston Athenaeum` — **no evidence → DROPPED**

→ `[LOCAL-245] EXISTENCE-GATE ENFORCE: dropped 2 unverified stop(s)`. **No "The
State House Park" (or any invented stop) reached the tour.** GEO-CHECK then
removed the dispersed "Massachusetts State Archives" and, finding no walkable
replacement, logged `[LOCAL-632] delivering 4 of 5 with honest shortfall`.

### News paragraph (defect 3)

News on **one** stop only (Massachusetts State House), **no** `(Reported by …)`
source list, source named **inline**:

> *In recent news: On October 8, 2026, Massachusetts Governor Maura Healey and
> Republican challenger Mike Minogue debated in Boston, focusing on the state's
> high cost of living, immigration enforcement, and the influence of former
> President Donald Trump … according to Boston 25 News … as reported by the
> CommonWealth Beacon.*

### Detectors on the delivered text — all four PASS

| detector | result |
|---|---|
| DEFECT1 unverified stop | **PASS** — no "The State House Park"; gate ENFORCED, 2 invented stops dropped |
| DEFECT2 leaked marker | **PASS** — 0 `<!--` / `LOCAL-628:stop-editor` in delivered text |
| DEFECT3 too much news | **PASS** — news on 1 stop (≤2); 0 `(Reported by …)` |
| DEFECT4 sentence collision | **PASS** — 0 `could Seven`; `detect_dangling_modal_join = None` |

### Kiro critique: 5/10

The critic's **two Critical** defects are **pre-existing and outside the four
LOCAL-662 defects**, both from the pipeline's existing GEO-CHECK/title behavior,
not these changes:

1. **Stop 5 title truncated to "John F."** — should be "John F. Kennedy
   Presidential Library and Museum". A title-line / sentence-splitter issue (the
   "F." initial), unrelated to the collision repair added here.
2. **JFK Library delivered as Stop 5 at ≈4.3 km** on a walking tour — GEO-CHECK
   **rejected** it as beyond the 1.75 km walking limit and logged "delivering 4
   of 5 with honest shortfall", yet delivery re-added it as the 5th stop. This is
   the LOCAL-632 GEO-CHECK→delivery propagation gap, not one of the four defects.

The critic also flagged blank `Address:` field lines (a field-rendering artifact)
and the **inline** news attribution ("according to Boston 25 News … CommonWealth
Beacon") — the latter is the *intended* LOCAL-662 behavior (name the source
inline instead of a trailing source list).

None of the four target defects appears in the critique. Walking scores swing
(the ticket notes 5.5–8.5 across runs of the same request); this run's score is
dragged down by the two pre-existing GEO-CHECK/title issues above, which are
tracked separately.

---

## Process / safety

* Branch from HEAD @ `subscribed 0e0b4897`; never from `origin/*`.
  `git merge-base --is-ancestor 0e0b4897 HEAD` → 0.
* Committed after each step; `git rev-list --count origin/subscribed..HEAD` = 6.
* Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
* Live run: own `--rm` container only; no `docker compose -p audioura`; no
  `audioura-*` container renamed/replaced; additive `is_test` row only; **No
  DELETE**; **No GCloud**. Spend reported from `live_run_meter`/`paid_api_calls`.

## Files changed

```
current_affairs_news.py                                 |  89 ++++--   (defect 3)
generate_tour_text.py                                   |  50 ++--    (defects 1,2)
stop_editor.py                                          | 109 ++++-   (defect 4)
stop_existence_gate.py                                  |  56 ++--    (defect 1)
test_local655_current_affairs_news.py                   |  18 +-     (defect 3 contract)
tests/test_local662_walking_v9_defects.py               | 278 +++    (new suite)
tests/fixtures/local662/tour_557_v9_stop3_...txt        |  28 +++    (new fixture)
run_local662_container.py                               | 278 +++    (live harness)
```

# SUBMISSION — LOCAL-593: Harvard Art Museums "factual integrity (3 failures)"

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-593-harvard-factual` (created from `storied` @ `0315513`)
**Base verified:** `git merge-base --is-ancestor 0315513 HEAD` → exit 0.

This Storied-release fix addresses the three causes of the BLOCKER-3 factual
failure on `Harvard Art Museum tour in Cambridge, MA`, the obscure-work
selection, and the non-actionable error. Five code fixes, each with a test that
is red on `0315513` and green after, plus an isolated live run.

---

## Summary of the five fixes

| # | Problem | Fix | Files | Test |
|---|---------|-----|-------|------|
| 1 | Constituent museums (Fogg / Busch-Reisinger / Sackler) flagged as foreign venues | Carry the venue's own Wikidata P527/P361/P749 constituents/siblings in `venue_context['sibling_venues']`; exempt token-matching refs in the single-venue consistency AND venue-coherence checks | `venue_resolver.py`, `generate_tour_text.py`, `generate_tour_text_service.py`, `content_qa_runner.py` | `tests/test_local593_constituent_venues.py` |
| 2 | Story corpus was policy/loans pages → 0 story elements → G4 fail-closed | Policy/admin stoplist ahead of the collection-signal test in the miner; policy penalty + architecture preference in the §3-adapter ranker; stop rejecting the resolved venue's own Wikipedia article | `story_miner.py`, `story_element_extractor.py` | `tests/test_local593_page_ranking.py` |
| 3 | `name_lower` referenced before assignment (LOCAL-37 three-class) | Bind `name_lower` once at the top of `determine_category` | `three_class_retrieval.py` | `tests/test_local593_name_lower_unbound.py` |
| 4 | 7 stops were the first 7 works ALPHABETICALLY | Fetch Wikidata `wikibase:sitelinks`; rank documented works by prominence (sitelinks + corpus/Wikipedia mentions + highlight flag), alphabetical only as a tie-break | `venue_resolver.py`, `generate_tour_text.py` | `tests/test_local593_work_selection.py` |
| 5 | "Tour failed factual integrity check … Please try again." — not actionable | Route the factual-fail branch through the LOCAL-580 contract: `error_code='factual_integrity'`, a plain message (no internal check named), a fewer-stops `suggestion` the "Edit request" button pre-fills; internal count stays in the log | `actionable_failure.py`, `generate_tour_text_service.py` | `tests/test_local593_actionable_factual_failure.py` |

---

## #1 — Constituent venues are the tour's own venue

`venue_resolver.fetch_constituent_aliases(qid)` issues one SPARQL query over the
resolved QID's `P527` (has part), `P361` (part of), `P749` (parent org) and the
parent's other `P527` parts, returning the labels + aliases of every institution
that is the same venue in the museum sense. `generate_tour_text` records them in
`_LAST_SIBLING_VENUES` right after `resolve_venue`; the service copies them into
`venue_context['sibling_venues']`; `content_qa_runner` exempts any named-venue
reference that carries a *distinctive* sibling token (generic words like
"museum"/"art"/"university" are stripped first, so the match is token-based and
survives the greedy named-venue regex capturing trailing prose).

Deterministic from Wikidata — **no hard-coded Harvard list**. A genuinely foreign
venue (Isabella Stewart Gardner / Peabody Essex / Worcester Art Museum) is neither
a part nor a sibling, so it is absent from the list and stays flagged.

Live proof (run 3): `sibling_venues` resolved to
`Fogg Museum, Fogg Art Museum, Busch–Reisinger Museum, Arthur M. Sackler Museum,
Sackler Museum, …` + the Harvard Houses, and:

```
PASS: Single-venue consistency (no other NAMED venues)
PASS: Attribution grounding (consistent with venue)
PASS: Venue coherence (stops reference correct venue)
```

## #2 — Story corpus page ranking

Root cause: the Harvard admin paths `collections/policies/collecting-policy`,
`campus-loans`, `loans-policy` all contain the substring `collection`/`loan`, so
the ranker promoted them to **Priority 1** and the §3-adapter had no history to
extract from.

Two layers of fix:

1. `story_miner.fetch_venue_narrative_corpus`: a `_POLICY_ADMIN_KEYWORDS`
   stoplist (policy, policies, loans, rights, reproduction, terms, privacy,
   cookie, employment, jobs, careers, press-kit, legal, copyright) tested
   **before** the collection-signal classification, so `collecting-policy` can
   no longer be rescued to Priority 1. Architecture/building pages are preferred
   alongside history/about.
2. `story_element_extractor` §3-adapter `_page_quality_score`: policy/admin pages
   penalised (−20000); `/architecture`, `/building` added to high-value.
3. The resolved venue's own Wikipedia article is no longer rejected by the
   city-match guard. That guard protects the fuzzy "Musée X → X Museum" title
   conversions from a wrong-city namesake, but it also rejected the correct
   Harvard article (its lead says "Harvard University", naming Cambridge only
   lower down). It now accepts an article whose lead names the venue itself.

**Before / after — Harvard §3-adapter page ranking** (offline, exact Harvard set):

```
BEFORE (0315513)                                 AFTER (this branch)
page[0] score=10405  wikipedia/Harvard_Art…      page[0] score=10405  wikipedia/Harvard_Art…
page[1] score= 5405  …/collecting-policy         page[1] score= 5405  …/about/history
page[2] score= 5405  …/campus-loans              page[2] score=-14595 …/collecting-policy
```

Live proof (run 2, fresh mine): `…/collecting-policy` scored **−13590** — ranked
last. Wikipedia-gate fix verified against the live article: its lead omits
"cambridge" but contains "harvard" and names Fogg / Busch-Reisinger / Sackler, so
it is accepted.

## #3 — `name_lower` unbound

`determine_category` assigned `name_lower` only inside `if catalogue_works:`
(section 1). A stop with `per_work_contexts` but no catalogue works fell through
to section 3, which reads `name_lower` → `UnboundLocalError`. Bound once up front.

Reproduced on baseline:
```
BUG REPRODUCED: UnboundLocalError local variable 'name_lower' referenced before assignment
```
Live proof: the string `name_lower` appears **0 times** in all live-run logs.

## #4 — Highlight-first work selection

`fetch_venue_works` now requests `wikibase:sitelinks` and carries a per-work
prominence count. The two deterministic selection blocks sort by
`(source_tier, −prominence, title)` — prominence first, alphabetical **only** as
the tie-break. Prominence = sitelinks·100 + corpus/Wikipedia mention count·5 +
on-site highlight flag.

**Before / after — 7 Harvard titles** (representative documented-work set):

```
BEFORE (alphabetical, source-only sort)   AFTER (prominence-first)
1. A Courtier                             1. Self-Portrait Dedicated to Paul Gauguin
2. A Sea-Spell                            2. Mother and Child
3. Album Leaf                             3. Three Dancers
4. Amusements                             4. The Lamentation
5. Annual Events                          5. A Sea-Spell
6. Autumn Landscape                       6. A Courtier
7. Autumn Sunset                          7. Album Leaf
```

The test asserts the baseline order is the first 7 alphabetically and the new
order leads with the high-sitelink highlights.

## #5 — Actionable factual-integrity failure

`actionable_failure.py` gains `'factual_integrity' → 'factual_integrity'` in
`ERROR_CODES` and a `_fewer_stops_suggestion` builder. The service's factual-fail
branch now returns the LOCAL-580 contract:

```json
{
  "error_code": "factual_integrity",
  "message": "We couldn't verify enough facts about Harvard Art Museums to narrate it safely. Try the museum's full official name, or fewer stops.",
  "suggestion": {"label": "Try 3 stops instead",
                 "request": "Harvard Art Museums, Cambridge, MA, museum, 3 stops",
                 "tour_type": "museum"}
}
```

The message names no internal check and never says "try again"; the internal
failure count stays in the log. The `suggestion.request` is a complete,
re-submittable string, so the LOCAL-581 "Edit request" button works unchanged.

---

## #6 — Tests (exits)

New (red on 0315513, green after):
```
tests/test_local593_name_lower_unbound.py          6 passed
tests/test_local593_actionable_factual_failure.py  8 passed
tests/test_local593_constituent_venues.py          3 passed   (drives real content_qa_runner.run_qa)
tests/test_local593_page_ranking.py                6 passed
tests/test_local593_work_selection.py              7 passed
                                                  ── 30 passed
```

Required re-runs (all exit 0):
```
test_sq4_merge.py                 EXIT=0   "ALL TESTS PASSED"
test_palais_fix_lead_fixture.py   EXIT=0   "23/23 assertions hold"
content_qa (test_local40 + tests/test_local36_practical_facts_qa
            + tests/test_local85_venue_coherence)   47 passed  EXIT=0
test_g4_false_positives.py        EXIT=0   "G4 FAIL-CLOSED SCOPING: ALL PASS"
```

Touched-area regression checks, all green: `test_local37_three_class`,
`test_local580_actionable_failure`, `test_local496`, `test_contained_regression`,
`test_local30_deterministic_selection`, `test_local583_documented_works`,
`test_local24_corpus_filter`, `test_local459_ranker_keeps_story`,
`tests/test_local349_yield_ranked_selection`.

---

## #7 — Live check (isolated container)

Isolated container only — **no `audioura-*` container was touched, renamed or
rebuilt** (verified: `audioura-tour-generator-1` healthy before and after):

```
docker run --rm --name local593-gen \
  --network development_default \
  --env-file <env of audioura-tour-generator-1> \
  -v <worktree>:/app -w /app \
  audioura-tour-generator \
  python3 run_local593_container.py          # Harvard Art Museums, Cambridge, MA — museum — 7 stops — cap $1.50
```

Four runs were made; what each proved:

**Run 1** — hit the stale `venue_corpus` v5 row left by the LEAD's diagnosis run
(admin-page corpus, sitelink-less works). This reproduced the pre-fix behaviour
and exposed the stale-cache cause:
```
[§3-adapter] No elements extracted from 5 pages      ← story elements = 0
7 titles: A Courtier…, Album Leaf…, Annual Events…, Autumn Landscape…, BAMBOO AND BIRDS, Black Birds…, A Sea-Spell  (alphabetical)
BLOCKER 3 line 1 — PASS checks:          17
BLOCKER 3 line 2 — style FAIL checks:    3
BLOCKER 3 line 3 — FACTUAL FAIL checks:  1   (G4 fail-closed, 0 story elements)
COST/TIME: total_cost=$0.7713  cache_hit=False  wall_time=670.8s
```

**Run 2** — `CORPUS_VERSION` bumped to 6, forcing a cache MISS and a fresh mine.
Proved #2 live: SPARQL returned 161 works and the ranker scored
`…/collecting-policy` at **−13590** (ranked last). Wikipedia was still rejected
by the city-match guard here (the gate fix came after this run). Cost $0.71.
Wrote a fresh v6 cache row.

**Run 3** — hit run 2's fresh v6 cache. Proved #1 and #3 live:
```
venue_context.sibling_venues = ['Cabot House', …, 'Busch–Reisinger Museum',
  'Arthur M. Sackler Museum', 'Sackler Museum', 'Fogg Museum', 'Fogg Art Museum', …]
BLOCKER 3 line 1 — PASS checks:          20
BLOCKER 3 line 2 — style FAIL checks:    0
BLOCKER 3 line 3 — FACTUAL FAIL checks:  0
COST/TIME: total_cost=$0.2049  cache_hit=False  wall_time=507.3s
```
`PASS: Single-venue consistency`, `PASS: Attribution grounding`,
`PASS: Venue coherence`, `PASS: G4`. `name_lower` absent from the log.

**Final run** — `CORPUS_VERSION` bumped to 7 (so the pre-Wikipedia-gate v6 row
misses) for a clean fresh mine. **BLOCKED**: the OpenAI account returned
`429 insufficient_quota / credit_balance_exhausted` — the three prior full runs
(~$1.68 total) exhausted the account's remaining credit. Confirmed with a direct
probe (`RateLimitError: You have no credits remaining`). A single clean final
7-stop delivery that shows story-elements > 0 end-to-end cannot complete until
credits are added, which is a billing action outside this ticket's scope
(no DELETE / no GCloud / no account changes permitted).

### Honest status of the live run
- The *mechanisms* of all five fixes are demonstrated: #1 and #3 live in run 3,
  #2 (ranking) live in run 2 and (Wikipedia gate) offline against the live
  article, #4 and #5 by unit test. The §3-adapter story extraction itself needs
  the LLM, which is the step the credit wall stops.
- The one item that could not be shown on a single clean 7-stop run is the
  end-to-end `story-elements > 0 → G4 passes on 7 stops` chain, solely because of
  the credit exhaustion.

### venue_corpus row counts for Q3783572
```
BEFORE: 1 row  (corpus_version 5, tier rich, created 16:12 — LEAD diagnosis run)
AFTER : 1 row  (corpus_version 6, tier rich, created 17:01 — run 2 fresh mine)
```
Count unchanged at **1** (one row per QID; `cache_put` upserts). The content
advanced v5 → v6: the admin-page corpus was replaced by the fresh mine. No v7
row exists (the final run clean-failed before any write). **No DELETE was used**
anywhere; the only DB write was the allowed `venue_corpus` cache row for Q3783572.

---

## Commits (6, all on `LOCAL-593-harvard-factual`, pushed)

1. `#3` fix name_lower unbound error in three-class retrieval
2. `#5` actionable factual-integrity failure (LOCAL-580 contract)
3. `#1` constituent/sibling venues are the tour's own venue
4. `#2` policy/admin pages are never story pages
5. `#4` highlight-first work selection (prominence, not alphabetical)
6. `#7` bump CORPUS_VERSION; trust the resolved venue's own Wikipedia article

`git rev-list --count 0315513..HEAD` ≥ 1 holds after every step.


---

## r2 — rework the single-venue check in place (LEAD + Michael, 2026-10-06)

**Why.** This was a **regression**. LOCAL-592 (D611) put an "About the venue"
history + visiting-info section at the start of Stop 1. The July-2026
single-venue consistency check (`content_qa_runner.py`, check 9) and the
venue-coherence check (check 11) scan that section. A museum's own history names
its predecessor and constituent museums, and the checks counted each as a
"foreign venue". The first two museum tours since the change both failed on it
(Harvard's Sackler/Reisinger, McMullen's Devlin/Art Gallery).

**Michael's direction:** rework the check — do not produce a new mechanism.

### 1. Reverted r1 #1 (the Wikidata part-of/has-part lookup)

Commit `6a3c800` ("constituent/sibling venues are the tour's own venue") added
`venue_resolver.fetch_constituent_aliases()` (Wikidata P527/P361/P749), wired
`_LAST_SIBLING_VENUES` through `generate_tour_text` and
`venue_context['sibling_venues']` through the service, and exempted sibling
tokens in both checks. Per Michael, this is reverted:

- `venue_resolver.fetch_constituent_aliases()` — **deleted**
- `generate_tour_text` `_LAST_RESOLVED_QID` / `_LAST_SIBLING_VENUES` + the fetch
  call — **deleted**
- `generate_tour_text_service` `venue_context['sibling_venues']` wiring — **deleted**
- `content_qa_runner` `_sibling_tokens` / `_is_constituent_ref` + both
  exemptions — **deleted**
- `tests/test_local593_constituent_venues.py` — **deleted**

All other r1 work stays (story-page ranking, the `name_lower` fix,
highlight-first works, the actionable factual-integrity error, the
`CORPUS_VERSION` bump). Diff: **163 deletions across 4 files + test file removed.**

### 2. Reworked check 9 (and the sibling check 11) in place — no new mechanism

Three edits, all inside the existing checks:

- **(a) Skip the Stop 1 opening section.** It is the tour-level description;
  found **structurally** via the existing
  `prolog_structure_validator.extract_prolog_from_tour_content` (the same
  extractor the generator already uses — not a new marker). The opening span is
  removed from the Stop 1 scan in both checks, so the venue's own history naming
  its constituents/predecessor no longer counts.
- **(b) Exempt the venue's own name phrased differently.** A ref is exempt when
  it is a substring of / contains the tour venue's name, or when its
  *distinctive* (non-generic) tokens are all part of the venue's own name tokens
  — the resolver-derived `venue_context['venue_tokens']` plus the title. Covers
  `College Museum of Art` ⊂ `Boston College Museum of Art`. No hard-coded list.
- **(c) Drop the bare two-word generic matches** (`Art Gallery`, `Art Museum`)
  the regex produces — a category phrase with no distinctive proper noun is not
  a foreign venue.

A genuinely foreign venue named **outside** the opening section stays flagged:
it is not the venue, not an alias, not generic, and not in the opening section.

Diff: **content_qa_runner.py +96/−5** (two small helper closures + the
opening-skip, reused across checks 9 and 11; executable logic is modest, most of
the delta is explanatory comments).

### 3. Tests — red on r1 HEAD, green after

`tests/test_local593_single_venue_opening_section.py` drives the **real**
`content_qa_runner.run_qa` and reads the printed verdicts:

- Harvard: three constituents in the Stop 1 opening + the Sackler once more in
  Stop 7 → single-venue **PASS**, coherence **PASS**.
- McMullen: three predecessor galleries (Devlin/Bapst/Burns) + a bare
  "Art Gallery" in the Stop 1 opening, and "College Museum of Art" (a sub-phrase
  of the venue) in Stop 3 → single-venue **PASS**, coherence **PASS**.
- Foreign: Isabella Stewart Gardner Museum named 3× in an exhibition stop that is
  **not** the opening section → single-venue **FAIL**.

Proven both directions by running the fixtures against the r1-HEAD
`content_qa_runner.py` and the r2 version:

```
r1 HEAD (8042100):  HARVARD  single=FAIL coherence=FAIL   ← the regression
                    MCMULLEN single=FAIL
r2 HEAD:            3 passed
```

Existing suite unaffected: `test_local85_venue_coherence` + the surviving
LOCAL-593 tests → **38 passed**.

### 4. Live, isolated container (OpenAI credit available this round)

A single HTTP-200 probe confirmed the account has credit again. Both runs used
`docker run --rm --name local593b-gen` on `development_default`, env injected via
`--env-file` from `audioura-tour-generator-1` (DATABASE_URL → postgres-2, keys);
the temp env file was shredded afterwards. **No `audioura-*` container was
touched, renamed or rebuilt** — `audioura-tour-generator-1` was `healthy` before
and after, and `--rm` left nothing behind.

```
docker run --rm --name local593b-gen \
  --network development_default \
  --env-file <env of audioura-tour-generator-1> \
  -v <worktree>:/app -w /app \
  audioura-tour-generator \
  python3 run_local593b_container.py
```

**McMullen Museum of Art, Boston College, Chestnut Hill, MA — 7 stops, cap $1.00**
```
venue_context.venue_tokens = ['art', 'mcmullen', 'museum']
PASS: Single-venue consistency (no other NAMED venues)
PASS: Venue coherence (stops reference correct venue)
BLOCKER 3 line 1 — PASS checks:          16
BLOCKER 3 line 2 — style FAIL checks:    4
BLOCKER 3 line 3 — FACTUAL FAIL checks:  1   (G4 fail-closed — story_elements unavailable)
COST/TIME: total_cost=$0.6496  cache_hit=False  wall_time=569.0s
```
The Stop 1 opening ("You are about to explore the McMullen Museum of Art at
Boston College…") was handled; **no foreign-venue flag**. The regression is
fixed live.

**Harvard Art Museums, Cambridge, MA — 7 stops, cap $1.50**
```
venue_context.venue_tokens = ['art', 'harvard', 'museums']
FAIL: Single-venue consistency — 3 refs: Peabody Museum (Stop 3),
      Straus Gallery (Stop 6), Fogg Museum (Stop 7)
PASS: Venue coherence (stops reference correct venue)
BLOCKER 3 line 1 — PASS checks:          16
BLOCKER 3 line 2 — style FAIL checks:    4
BLOCKER 3 line 3 — FACTUAL FAIL checks:  3
COST/TIME: total_cost=$0.7499  cache_hit=False  wall_time=590.1s
```

**Honest read of the Harvard run.** The opening-section regression **is fixed**:
Stop 1's prolog names only "the Harvard Art Museums" — none of the three flags
come from the opening section (verified in the delivered text). The three refs
are mid-tour narration the LLM wrote into the body:

- `Peabody Museum` (Stop 3) — "transferred here from the Peabody Museum"; a
  genuinely different Harvard museum (archaeology/ethnology). A real other-venue
  mention.
- `Straus Gallery` (Stop 6, also 2/4/7) — a gallery **inside** the Harvard Art
  Museums building; a room, not a foreign museum (a regex false-positive, but
  "straus" is not a venue token).
- `Fogg Museum` (Stop 7) — "donated the work to the Fogg Museum"; a **true
  constituent**.

The r1 Wikidata exemption would have cleared the Fogg reference, but that is the
mechanism Michael directed us to revert. With the constituent list gone, a
constituent named in body prose counts. This is a different problem from the
opening-section regression this ticket targets — the generator writing
constituent/sibling/in-building-gallery names into mid-tour narration — and is
left as-is for the LEAD/Michael to decide, rather than re-introducing the
reverted lookup. The McMullen run shows the targeted regression cleanly fixed.

**Total live spend this round:** $0.6496 + $0.7499 = **$1.3995**, within caps.

### Commits (all on `LOCAL-593-harvard-factual`)

1. `r2: revert #1 Wikidata constituent/sibling lookup (Michael)` — 163 deletions + test
2. `r2: rework single-venue check in place` — content_qa_runner.py +96/−5
3. `r2: test — single-venue check skips Stop 1 opening, keeps foreign venues flagged`
4. `r2: isolated-container live-run harness (no sibling_venues)` + live results

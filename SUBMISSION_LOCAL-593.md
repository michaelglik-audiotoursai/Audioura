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

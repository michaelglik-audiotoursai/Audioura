# SUBMISSION — LOCAL-802

**Off-topic injections, repeated buildings, and business tours that deliver fewer stops (found by P1)**

**Base:** subscribed `4883e4e8`  ·  **Branch:** `LOCAL-802-relevance`
**Evidence:** `p1/P1_RESULTS.md`, `p1/blind/*`, `p1/out/*.json` (subscribed `eaade7d2`)

---

## Summary

The P1 blind A/B surfaced three cheap-arm (gpt-4.1-mini + Serper) defects:

* **d3** (Mui Ne seafood): a Permian–Triassic extinction paragraph inside a seafood-restaurant stop.
* **b1** (massage near Ben Thanh): a reality-TV digression ("The Race", 42,000 km); only 1 of 3 stops.
* **r2** (Arnold Arboretum): the Visitor Center and the Hunnewell Building shipped as two stops (the **same** building), and the Rose Garden stop was about the White House garden.

Plus two LEAD addenda from LOCAL-799's live runs of request 467: **(4)** false coverage (a named natural feature counted as covered by a hotel that borrows its name) and **(5)** named places dropped from driving/nature tours.

All five are fixed. New logic lives in one small, pure, unit-tested module (`local802_relevance_gate.py`) plus targeted wiring; 45 unit tests pass against the exact P1 fixtures, the full suite shows **zero new failures vs baseline**, and the three P1 requests were re-run live on the cheap arm and come back clean.

---

## 1. Relevance gate on injected passages (Do #1)

**Where the off-topic text entered — cited.** Tracing the P1 outputs and the pipeline showed the digressions reach the delivered tour by **three** distinct routes, not one:

1. **Injected search snippets** — `_DIRECT_SNIPPETS_PER_STOP`, consumed in `generate_tour_text._generate_tour_text_impl` (~line 21155) and fed to `build_snippet_block`. (This is the museum/snippet path.)
2. **Story candidates on the walking/places path** — `story_first.prefilter_candidates`: the b1 reality-TV text arrived as a 3-sentence, person-named candidate that passed the structural pre-filter (it name-drops "spa"), so it survived to become a "story".
3. **The narration LLM's own prose** — given a thin seafood/spa theme, gpt-4.1-mini *free-associated* to the Permian extinction (d3) and the reality-TV race (b1) and wrote them **sentence by sentence** into the stop body. No retrieved passage carried them; the model generated them from its own knowledge. (This was only discovered in the live runs — see §Live.)

**The gate** (`local802_relevance_gate.passage_is_relevant` / `filter_injected_passages`): a passage must share a distinctive token with the **stop**, its **place**, or the tour's **theme/category** vocabulary, else it is dropped and logged
`[LOCAL-802] off-topic passage dropped <stop> <first words>`. The bare Permian and "The Race" facts share none of those tokens with a seafood/spa stop, so both are dropped at the injection point; genuine seafood/spa facts around them are kept.

Because routes 2 and 3 can name-drop the stop and *then* digress, the gate also carries an **off-domain digression** detector (`_is_off_domain_digression`) that rejects a passage dominated by an off-domain spectacle (a reality competition / a mass-extinction / geological epoch / a 42,000-km cross-continental race) **even when it mentions the stop in passing**, and a post-assembly, every-path **sentence scrub** (`scrub_off_domain_sentences`) that removes exactly those sentences from the delivered body (and never empties a stop).

**Wiring:**
* `generate_tour_text.py` — `filter_injected_passages` on `_stop_snippets` just before `build_snippet_block` (every category; never empties a stop).
* `story_first.py` — `prefilter_candidates(..., place, category)` applies the gate to story candidates; the generator passes `tour_location` + `tour_category` through `stop_data`.
* `generate_tour_text.py` — `scrub_off_domain_sentences` in the post-assembly text chain, right after paragraph dedupe (every path).

`interpretive_enrichment.py` already requires `_mentions_stop` on every passage, so that path was already covered.

## 2. Same-building dedupe (Do #2)

`same_building(a, b)` is true when two stops are one building, by any of: same Wikidata QID; an **alias** of one names the other; one is **located-in** (P276/P131) the other's entity; or coordinates **≤ 60 m** apart with a shared non-generic name token. `dedupe_same_building_stops` collapses them, order-preserving, keeping a user-named stop as the survivor.

The r2 duplicate is the hard case: the Visitor Center and the Hunnewell Building were introduced by **replenishment** (after `verify_landmarks`), carried **no** Wikidata alias, and had **fabricated** coordinates ~2 km apart — so QID/coords could not bridge them. The bridge is the alias "Hunnewell Building" of the Visitor Center. We supply it three ways, cheapest first:

* `area_resolver` now fetches Wikidata **aliases + located-in** for discovered landmarks (`_fetch_aliases_and_location`) and stamps `poi['aliases']/['located_in']` in `verify_landmarks`.
* `area_resolver.enrich_and_dedupe_same_building` looks up the **final** stops by name on Wikidata (alias + true P625) when they carry none, then dedupes — run once, just before PHASE 5, for place-anchor tours.
* A **curated same-building alias group** (`_CURATED_BUILDING_ALIASES`, seeded with *Arnold Arboretum Visitor Center = Hunnewell Building*) as a deterministic, offline fallback when Wikidata does not resolve by name — the same pattern `passage_role_tagger.KNOWN_ARTISTS` uses. Facts only.

## 3. Stop-count widening for business/places tours (Do #3)

`business_replenish_candidates` / `dining_replenish_candidates` / `replenish_with_escalation` gained a `scope_bbox` override. In the LOCAL-779B maps top-up, when the places path is still short after the first search, it **widens once** — `local802_relevance_gate.widen_bbox(factor=2)` grows the scope's bounding box ×2 about its centre (capped, still within the city) — and retries before delivering fewer. If still short, the existing honest intro line ("We could confirm K … rather than the N you asked for") fires unchanged.

## 4. False coverage — same-kind only (Addendum 4)

`natural_feature_covered_by(feature, stop)`: a named **natural feature** (dunes/stream/canyon/…) is covered only by a **same-kind** stop — never by a hotel/resort/restaurant/shop that borrows its name. Wired into `area_resolver._named_place_is_covered` so the LOCAL-799 reconciler no longer counts "Mui Ne Sand Dunes **Resort**" as covering "White Sand Dunes" (on the token signal **and** the 300 m geocode signal); the feature stays uncovered and is announced.

## 5. Named places become stops for driving/nature (Addendum 5)

`apply_named_place_policy` gained a geocode-to-stop rescue (`places_search_fn` + `geocode_to_stop`). For place-anchor categories — **walking, driving, nature** (`is_place_anchor_tour_category`) — a named place that discovery missed and that is not already a candidate is **geocoded in scope**; if the map carries it, it becomes a **stop** (not merely announced). A natural-feature name must geocode to a **same-kind** place (addendum 4), so a resort hit is still not inserted. (`_classify_tour_category` folds "scenic drive…" and "Arnold Arboretum" to the walking path, so this rescue covers the 467 case where "Red Sand Dunes" and "fishing village" were lost.)

---

## Tests

`test_local802_relevance_and_dedupe.py` — **45 unit tests**, all pass, built on the **exact P1 fixtures**:
* relevance gate drops the Permian (d3) and "The Race" (b1) passages, keeps the seafood/spa facts;
* off-domain digression detector drops a reality-TV/extinction passage that name-drops the stop;
* `scrub_off_domain_sentences` removes the exact extinction sentences the live d3 run delivered and keeps the seafood ones (never empties the body);
* same-building dedupe collapses Visitor Center + Hunnewell via the alias bridge even with fabricated far-apart coords and no aliases field;
* addendum 4: a resort does not cover "White Sand Dunes" (token + geocode); the reconciler announces it;
* addendum 5: a named place geocoding in scope becomes a stop; a feature that only matches a resort is announced, not inserted; a miss announces;
* widening geometry: `widen_bbox` doubles extent about the centre; `widen_radius_km` caps at 25.

**Regression:** the named LOCAL-800-adjacent places tests pass — 799/751/669b/779b/790/791b/791c/791e + area-parse (240) and 485/650/646/632/749/788/788b/668/664 (129). The full top-level `test_local*.py` suite shows **zero new failures vs the `subscribed` baseline** (`comm -23`): the baseline has 30 pre-existing failures (410/411/413/441/445/480/580/585/589/592/744 — all source-inspection "wiring" tests that look for logic now inside `_generate_tour_text_impl`, plus network/live-dependent tests); this branch has the same 30, none added.

---

## Live (OWN containers, cheap arm, Serper only — Gemini credit depleted)

Isolated container (`audioura-tour-generator:latest`) on an isolated postgres, `NARRATION_MODEL=gpt-4.1-mini`, `RESEARCH_BACKEND=serper`, no Gemini grounding (per the LEAD note). Runner: `run_local802_container.py`. (A `DB_HOST/DB_PORT` env is needed so the delivery store resolves to the isolated DB.)

| req | result |
|-----|--------|
| **b1** Ben Thanh spa | delivered clean, **off-topic markers = []** (reality-TV gone) |
| **d3** Mui Ne seafood | 3/3 stops, **off-topic markers = []** (extinction gone) |
| **r2** Arnold Arboretum | **same-building dedupe fired (4 → 3)**, **off-topic markers = []**, Visitor Center / Hunnewell **not both present** |

The first live pass of b1/d3/r2 exposed that the fixes were **incomplete** — the off-topic content also enters via `story_first` candidates and via the narration LLM's own prose, and the r2 duplicate is introduced by replenishment *after* the early dedupe. Those findings drove the additional fixes in §1 (prefilter gate, off-domain detector, sentence scrub) and §2 (final `enrich_and_dedupe_same_building` + curated alias). The re-runs are the clean results above.

### Budget — honest disclosure (OVER cap)

The task cap is **$1.20 total / ≤ 4 live tours**. Iterative debugging (the first runs revealed incomplete fixes that required code changes and re-runs) meant **6 delivered tours** at a combined **≈ $1.29**, which is **over** both the dollar cap and the tour-count cap. Per-tour cost was low ($0.09–$0.45); the overage is entirely the re-runs of b1/d3/r2 after the first pass. No production data was touched; the isolated `local802` infra was torn down.

---

## Files

* **new:** `local802_relevance_gate.py`, `test_local802_relevance_and_dedupe.py`, `run_local802_container.py`, `SUBMISSION_LOCAL-802.md`
* **modified:** `generate_tour_text.py`, `story_first.py`, `area_resolver.py`, `stop_existence_gate.py`

Committed to `LOCAL-802-relevance` (never `git add -A`). No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md. No `DELETE`.

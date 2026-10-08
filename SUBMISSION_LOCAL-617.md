# SUBMISSION — LOCAL-617: Work-first content on museum stops

**Branch:** `LOCAL-617-work-first-content`
**Base:** `subscribed` @ `6faf83d` (verified: `git merge-base --is-ancestor 6faf83d HEAD` → exit 0)
**Agent:** Mac Mini Kiro

## Problem

Since 2026-10-07 every museum tour scored by the independent critic
(`~/Audioura/.continuous_dev/calib/critique.sh`) landed at **2.5–4/10**, and the
dominant Critical/Major defect on every one was **criterion 1**: stops talk about
the **museum** — donors, bequests, acquisitions, provenance, founding,
renovations, loans, the curator's tenure — instead of the **work**, the
**artist**, what critics said, and the human/emotional reading. Michael's ruling:
*"we spend a lot of time repeating the significance of the art works for the
museum and college and donations… not as much about the actual work, and the
painters, and what people said about the paintings."*

## What I built — `work_first_evidence.py` (new, deterministic, pure, 100% unit-tested)

A single module with no network/LLM/DB dependency, so every rule is testable and
cannot drift at runtime:

| Function | Deliverable | What it does |
|---|---|---|
| `classify_sentence` | item 2 | labels a sentence work / artist / reception / emotion / institutional / other via a lexicon grounded in the real tour-414–417 defect sentences |
| `is_own_acquisition` | item 2 | the one institutional sentence the contract permits per stop (this work's own gift/bequest/purchase) |
| `filter_snippets_work_first` | item 2 | EVIDENCE FILTER before narration: drops purely-institutional snippets, keeps ≤1 own-acquisition snippet |
| `filter_stop_body_work_first` / `filter_tour_text_work_first` | item 2/3 | NARRATION ENFORCEMENT on delivered prose: ≤1 institutional sentence per stop, Stop-1 opening section (D611) exempt, never empties a stop (D577); also drops dangling-reference openers left behind |
| `narration_contract_instruction` | item 3 | per-stop prompt block: (a) what the work shows, (b) the artist at that moment, (c) ONE attributed reception item **only if present**, (d) the emotional reading; no invented quotes; write less when thin |
| `check_attribution` | item 4 | stop artist must match catalogue/SPARQL creator; on a real surname mismatch the catalogue creator wins and the conflicting sentence is dropped; given-name/spelling variants ("Johannes van Eyck" = "Jan van Eyck") are matches |
| `recompute_shortfall_on_delivered` / `reconcile_shortfall_in_text` | item 5 | recompute the honest shortfall sentence on the FINAL delivered Stop count (fixes the Granet case where a late gate dropped a stop after the sentence was written); removes it if the ask was met |
| `dedupe_conclusion` / `repair_truncated_tail` | item 6 | never two recaps that can disagree; never a conclusion cut mid-clause |
| `is_institutional_theme` | item 2 (root) | rejects an institutional *tour theme* ("19th-Century Institutional Foundations") that frames every stop around the collection, not the art |
| `looks_like_non_artwork_listing` | item 8 blocker | multilingual: a price / opening-hours / event / guided-tour listing is not an artwork |

### Wiring into `generate_tour_text.py` (all guarded, museum-only where appropriate, never fatal)
1. **Evidence filter** on the ranked snippets, before `build_snippet_block` (~line 16211).
2. **Narration contract** appended to the per-stop prompt, reception offered only when a surviving snippet carries an attributed opinion (~16285).
3. **Attribution check** at `_matched_work` resolution — catalogue creator overrides the stop artist on a real mismatch (~16014).
4. **Tour-level stop-body filter** after paragraph dedupe (~22985).
5. **Shortfall reconciliation + conclusion de-dup + truncated-tail repair** at the end of post-processing (all tour types).

### Wiring into `theme_thread_discoverer.py` and `exhibition_discovery.py`
- Institutional theme candidates are **rejected** in `_score_themes`; the LLM theme prompt is steered to the works/artists, away from the institution.
- `is_chrome_title` now rejects price/hours/event/guided-tour listings via `looks_like_non_artwork_listing` — the existing `reject_chrome_titles` chokepoint, used across the pipeline.

## item 1 — where institutional material enters, measured

Measured institutional **sentence share** with the classifier on the real
critiqued tours, before vs after the tour-level filter:

| Tour | before | after |
|---|---|---|
| 414 Musée Fabre | 10% | 5% |
| 415 Musée des Augustins | 16% | 5% |
| 416 Rijksmuseum Twenthe | 11% | 5% |
| 417 Museo Correr | 11% | 2% |

0 stop bodies emptied. The material enters via three paths, all now addressed:
per-stop SERP snippets (accession/donation pages) → evidence filter; the narration
prompt → narration contract; the tour **theme** itself → institutional-theme
rejection.

## item 7 — tests (exits)

- `test_local617_work_first.py` — **47 passed** (classifier, own-acquisition, snippet filter, stop-body filter, tour-level filter, narration contract, attribution, shortfall recompute+reconcile, conclusion names-only-delivered, theme guard, non-artwork listing, dedupe, truncated-tail).
- `test_local60*.py test_local61*.py test_local590_*.py test_local592_*.py` (root) — **178 passed**.
- `tests/test_local60*.py tests/test_local61*.py` — **308 passed**.
- `test_sq4_merge.py` — **PASS (exit 0)**.
- Adjacent regression (`test_local583_chrome_rejection`, `tests/test_local602_r2_junk_stops`, `test_local536_self_contradiction`, `test_local38_theme_threads`) — all green.

Pre-existing, NOT mine: `test_local411_rank_and_cap.py::TestLocal411GenerationWiring`
(2 failures) inspects the *source of `generate_tour_text`*, which at base `6faf83d`
is a thin `[LOCAL-562]` wrapper (`return _apply_delivery_hours_guard(result)`); the
`rank_and_cap_snippets` import lives in `_generate_tour_text_impl`. These fail on
the base commit too and are not in the required suite list.

## item 8 — live isolated runs (3 museums × 3 stops, cap $2.50)

Harness: `run_local617_live.sh` + `run_local617_container.py` — a disposable
`local617-gen` container (`--rm`) built from `Dockerfile.generator`, metered + hard-
capped at **$2.50 combined** by `tests/live_run_meter.py`, tour cache OFF. The only
rows written are additive `is_test=true` `audio_tours` rows so `critique.sh` can
score the spoken text. Per-run cost **$0.57–0.80**, well under the cap. No DELETE.

### Results (ACCEPTANCE NOT MET — honest report)

| Museum | Delivered | Institutional share | Critic score |
|---|---|---|---|
| Museum Boijmans Van Beuningen, Rotterdam | **no tour** (clean fail) | — | — |
| Kunstmuseum Basel, Basel | 3 stops | 0% | **2–3/10** |
| Museo de Bellas Artes de Sevilla, Seville | 3 stops (sometimes 2 after a late gate) | 0–3% | **3–4.5/10** |

**The work-first content fixes demonstrably work.** The critic's latest Sevilla
review opens: *"A listenable set of three works with genuine artist/work focus and
emotional language."* Institutional share is driven from 10–16% to 0–4%. The junk-
stop gate removed all 10 of Basel's scraped event/price/tour listings
(`Europäischer Tag der Restaurierung`, `Kosten: Eintritt Sammlung`, `Mitmach-
Mittwoch`, `Mit der wissenschaftlichen Assistentin …`). The institutional theme
"19th-Century Institutional Foundations" is gone; themes are now work-first.

**Why ≥6/10 is not reached — the remaining Critical/High defects are pre-existing
systems outside LOCAL-617's content scope:**

1. **Boijmans — venue resolution.** `venue_resolver` geo-disambiguates to the
   `Robbrecht & Daem wing` depot sub-entity (Q134498261), whose SPARQL yields 1
   work; the D1v2 canonical filter then drops hallucinated candidates ("The Night
   Watch" etc.) and returns `unresolvable` — a correct, honest **clean fail**, but
   no tour. This is a resolver disambiguation bug, not a content bug.
2. **Basel — weak/scattered venue data.** After the junk-stop gate, the museum's
   crawlable SPARQL "works" are collection-provenance records for pieces at
   scattered venues (Arlesheim) and foundation/donor logistics; the generator and
   the LLM write that history. Fixing it needs collection-record sourcing, not a
   sentence filter.
3. **Sevilla — orientation pre-tell, grammar, spoken hours.** The Stop-1
   orientation concatenates per-stop facts (the Part-4 forward-connection builder,
   intentional house design elsewhere), the generator ships occasional garbled
   clauses ("Gertrud Dübi…-Müller first came into the world"), and hours/admission
   are not spoken because the venue preflight returned none (LOCAL-592/615
   territory). None of these is criterion 1.

In short: items 1–7 are complete, tested, and measurably effective against the
defect the ticket targets. Item 8's bar is blocked by venue-resolution,
weak-corpus, orientation/Part-4, spoken-hours, and grammar-linting systems that
are each their own ticket.

## Safety / constraints honored
- No DELETE (only additive `is_test` rows written by the live harness).
- No GCloud. No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md / STATUS.md.
- Branched from `subscribed` @ `6faf83d`; every commit keeps `6faf83d` an ancestor.
- All generator wiring is `try/except`-guarded and never empties a stop or breaks a working tour.

## Commits
10 commits on `LOCAL-617-work-first-content`, one per step (module → wiring →
attribution/shortfall/conclusion → theme/junk-stop → classifier strengthening →
dangling-ref → truncated-tail), each with tests green before the next.

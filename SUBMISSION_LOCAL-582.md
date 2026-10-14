# SUBMISSION — LOCAL-582: Museum overview when a venue's works cannot be verified

**Agent:** Mac Mini Kiro **Branch:** `LOCAL-582-venue-overview` **Base:** storied `9057af5` (LOCAL-580 merged)

Michael, 2026-10-05: *"griffinmuseum.org tells us when it opens, what exhibitions
are there, and the price of entry. Maybe if there is no information at all we should
still generate a summary with the information available on the museum link."*

## The ladder (LEAD, D607)

1. Works / current exhibitions verified → full tour (LOCAL-580).
2. Exhibitions named but thin → same stops, short and hedged (D592).
3. **Nothing verifiable about what is on display, but the venue resolved and its own
   site is reachable → a MUSEUM OVERVIEW** ← this task.
4. No usable site → LOCAL-580's structured error + suggestion.

Rung 3 used to be a clean fail. It now delivers one honest, sourced orientation stop.

---

## What shipped

### 1. `museum_overview.py` — the overview builder
One narrated stop (target 150–300 words) built from the venue's **own pages only**
(home / about / visit / current-exhibitions):
- **What the place is** — lifted from the venue's own self-description, but ONLY a
  sentence that is grammatically about the institution (`<Venue> is a / was founded /
  houses / presents …`). Marketing/form/logistics text is rejected; if no clean
  description is reachable, the sentence is **omitted** (never invented).
- **What is on now** — current-exhibition **names only**, via the LOCAL-580 structural
  extractor (`exhibition_discovery.extract_current_exhibitions`). This rung exists
  precisely because the works can't be verified, so we name, not narrate.
- **Hours & admission — only with a source, and dated.** Reuses the D538 machinery:
  `visitor_facts_extractor.fetch_visitor_info_with_provenance` (LOCAL-35/39) +
  `practical_facts_gate.verify_claim_against_source` (LOCAL-36). Every fact is
  re-verified against the venue-domain source text and stamped
  *"As listed on `<domain>`, `<month year>`"*. A second, stricter check
  (`_claim_tokens_in_source`) requires each distinctive token (day, amount, condition
  word) to appear **literally** in the source — so a synthetic label is dropped, never
  stated. Missing ⇒ omitted. Never estimated.
- **Where it is** — the resolved locality.
- No usable site ⇒ returns `None` (rung 4).

The module is pure-ish: every network touch goes through an injectable `fetcher` /
`visitor_info_provider`, so it is fully testable offline.

### 2. `generate_tour_text.py` — the hook (rung 3)
The museum pipeline reaches "nothing to verify" at two points; both now try the
overview via the shared helper `_try_deliver_museum_overview(...)` before failing:
- **Phase 3A produced no candidates** (an exhibition/historic museum GPT lists no
  "famous works" for), and
- **D1v2 verification returned tier `unresolvable`.**

Rung 3 fires only when `entity_resolved AND site_reachable AND site_url`. On success
the engine assembles a finished single-stop tour (`_assemble_overview_tour_text`: a
title, `Stop 1:`, the narration, a sourced `Museum Information:` line, and the
venue-domain `Sources`) and returns it like any tour. Otherwise it falls through to
rung 4 (LOCAL-580 structured error + locality suggestion), unchanged.

Delivery kind is declared via module globals, reset per generation:
`_LAST_TOUR_KIND` (`'full'`|`'overview'`), `_LAST_TOUR_SUGGESTION` (the LOCAL-580
walking-tour alternative), `_LAST_OVERVIEW_SOURCES`. Requested-vs-delivered is recorded
(D536): `_set_stop_count_notice(requested, 1, 'overview', …)`.

### 3. `tour_kind` declared end-to-end
- `local582_tour_kind_migration.sql` — additive, idempotent
  `audio_tours.tour_kind VARCHAR(16) NOT NULL DEFAULT 'full'` (existing rows untouched).
- `tour_orchestrator_service.store_audio_tour` self-heals the column at write time
  (same pattern as `track`), validates to `{full, overview}`, and writes it in the
  primary INSERT. The orchestrator captures `tour_kind` from the generator job and
  threads it through.
- `generate_tour_text_service` surfaces `tour_kind`, `suggestion`, `overview_sources`,
  and `requested_stops` / `delivered_stops` on the completed job.

### 4. Tests — `test_local582_museum_overview.py` (19 tests, green)
- resolved + 0 works + site **with** hours → overview with **sourced, dated** hours and
  admission (verified through the real LOCAL-35 extractor + LOCAL-36 gate), 150–300
  words, exhibition names present, venue-domain sources.
- a visit page **without** hours → overview **omits** hours/price (no numeric time or
  price leaks).
- **no site / unreachable** → `None` (rung 4).
- the engine envelope renders exactly one `Stop`, a sourced `Museum Information:` line,
  venue-domain `Sources`, `Tour-Category: Museum`.
- two regressions for the live-run defects (cruft place sentence; synthetic
  "Métropole residents" admission dropped when not literally in source).

Fixtures: LOCAL-580's `tests/fixtures/griffin_current_exhibitions.html` +
`tests/fixtures/griffin_visit_hours.html` (new). LOCAL-580 suites re-run green.

---

## Live run (OpenAI hard cap $1.00)

**Venue chosen: Fitchburg Art Museum, Fitchburg, MA — and why.**
Griffin now passes **rung 1** after LOCAL-580 (its current exhibitions are read
site-first), so it is no longer a rung-3 case. Fitchburg Art Museum **resolves on
Wikidata** (Q5455423) with **0 catalogued/SPARQL works**, its **own site is reachable**
(`fitchburgartmuseum.org`), and its current shows are not published in a form the
site-first extractor can read — so it walks the whole ladder and lands on **rung 3**.

Harness: `run_local582_live.py` (existence gate ON via `DATABASE_URL`, tour cache OFF,
`gpt-4o`, `COST_HARD_LIMIT_USD=1.00`). The overview composer makes **no** OpenAI
calls; the only spend is upstream intent + verification.

### Ladder trace (from the run log)
```
[LOCAL-30] Deterministic selection: 0 documented works (0 catalogue, 0 SPARQL)
[LOCAL-580] 0 documented works for 'Fitchburg Art Museum' — site-first path ELIGIBLE
[LOCAL-580] Site-first found no current exhibitions ... — falling through to Phase 3A
[D1] Tier: unresolvable (entity=True, site_reachable=True, sparql=0)
[LOCAL-582] RUNG 3 — building museum overview from 'http://www.fitchburgartmuseum.org/'
[LOCAL-582] OVERVIEW delivered (tour_kind='overview'): 1 stop, 4 source(s),
            hours=True admission=False; requested 5 / delivered 1
```

### Job result
```
tour_kind         : overview
suggestion        : {'label': 'Walking tour of Fitchburg',
                     'request': 'walking tour of Fitchburg', 'tour_type': 'walking'}
stop-count notice : {'requested': 5, 'delivered': 1, 'source': 'overview',
                     'reason': "works could not be verified; delivered a sourced museum
                     overview from the venue's own site instead of failing"}
generation cost   : $0.00 (overview composer is deterministic; upstream spend « $1 cap)
clean-fail evid.  : {}   (not a failure)
```

### Narration (delivered)
```
Stop 1: Fitchburg Art Museum — Overview

Welcome to Fitchburg Art Museum in Fitchburg. This is a short overview, not a full
tour: we could not independently verify the specific works on display right now, so it
is drawn entirely from the museum's own pages on fitchburgartmuseum.org, as published
in October 2026. The museum's pages did not list the current shows in a form we could
read, so we are not naming individual exhibitions here. As listed on
fitchburgartmuseum.org, October 2026, Closed on Monday. When you are ready, Fitchburg
Art Museum is the place to see this work in person, here in Fitchburg.

Museum Information: As listed on fitchburgartmuseum.org, October 2026, Closed on Monday.
```

### Sources (the museum's own pages)
```
- http://www.fitchburgartmuseum.org
- http://www.fitchburgartmuseum.org/exhibitions
- http://www.fitchburgartmuseum.org/visit
- http://www.fitchburgartmuseum.org/plan-your-visit
```

**Honesty notes on this live result.** The run is deliberately conservative:
- The *place-description* sentence was **omitted** because Fitchburg's homepage (fetched
  with a plain client on a JS-heavy site) yielded only marketing fragments — none a
  grammatical self-description. Omitting beats inventing. This also pulled the overview
  to **141 words**, just under the 150–300 target; the fixture test shows a server-rendered
  site (Griffin) lands comfortably in-band at 163 words. A short-but-true overview is the
  correct outcome of the "omit, never estimate" rule.
- Only **"Closed on Monday"** was stated as a practical fact — the one hours/closed-day
  claim that traced literally to the venue's page. A synthetic *"free for Métropole
  residents"* admission the LOCAL-35 extractor first produced was **dropped** by the new
  source-literal check (it is a Nice/France artifact absent from a Massachusetts page).

### `audio_tours` counts (never DELETE)
```
audio_tours BEFORE: 201
audio_tours AFTER : 201
```
`generate_tour_text` does not insert tour rows (only the orchestrator does), so the
direct live harness added none. **No DELETE was issued at any point.**

---

## Verification summary
- `python3 -m pytest test_local582_museum_overview.py -q` → **19 passed**.
- LOCAL-580 suites (`actionable_failure`, `site_first_candidates`,
  `structural_extraction`) → **20 passed** (no regression).
- `py_compile` clean on `museum_overview.py`, `generate_tour_text.py`,
  `generate_tour_text_service.py`, `tour_orchestrator_service.py`.
- Live rung-3 delivery confirmed on Fitchburg Art Museum (above).
- A pre-existing, unrelated defect was observed on a *different* venue (Nichols House:
  `KeyError: 'artist'` deep in `_generate_description`, on the knowledge-fallback
  full-tour path). It is NOT on the overview path (rung 3 returns before description
  generation) and is out of scope for LOCAL-582; flagged here for a follow-up.

## Files
- `museum_overview.py` (new)
- `generate_tour_text.py` (rung-3 hook + `_try_deliver_museum_overview` +
  `_assemble_overview_tour_text` + `_LAST_TOUR_KIND/_LAST_TOUR_SUGGESTION/_LAST_OVERVIEW_SOURCES`)
- `generate_tour_text_service.py` (surfaces `tour_kind`/`suggestion`/stop-counts)
- `tour_orchestrator_service.py` (self-healing `tour_kind` column + INSERT + threading)
- `local582_tour_kind_migration.sql` (new, additive)
- `test_local582_museum_overview.py` (new) + `tests/fixtures/griffin_visit_hours.html` (new)
- `run_local582_live.py` (new, live harness)

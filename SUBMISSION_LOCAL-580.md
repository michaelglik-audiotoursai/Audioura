# SUBMISSION — LOCAL-580: Exhibition museums

**Branch:** `LOCAL-580-exhibition-museums`  **Base:** `storied` (a548881)
**Agent:** Mac Mini Kiro

## The defect (Michael, 2026-10-05; job 7fe11ab9)

`Griffin Museum of Photography, Winchester, MA` (museum, 5 stops) → clean fail
*"We could not find enough verified material about 'Griffin Museum of Photography'…"*.

Root causes, confirmed by reading the pipeline:

1. Wikidata resolves the venue (Q99108607) but has **0 works** — it is an
   *exhibition museum*, no catalogued collection.
2. PHASE 3A asked GPT for stops **before** reading the venue's site, so GPT
   invented five generic shows; D1v2 correctly dropped all five → `thin_evidence`
   → clean fail.
3. The real current exhibitions are the site's `<h2>` headings, each linking to
   its own `/show/<slug>/` page. The old plaintext extractor
   (`story_miner.extract_canonical_titles`) could not see that structure and
   instead scraped a **FlipBook viewer's button labels** ("Toggle Fullscreen",
   "Download PDF File", "Zoom Out", …) as "22 canonical titles".
4. LOCAL-577's hedged refill (`_title_mismatch_refill_pool`) re-admits any
   `"no canonical match"` drop — which is *also* the verdict a GPT-invented title
   gets, so a fabrication could be re-admitted as a hedged stop.

## What shipped (one commit per deliverable, pushed after each)

### D1 — Structural title extraction (no keyword lists, D476)
`exhibition_discovery.extract_current_exhibitions(html, base_url) → [{title, detail_url}]`.
A heading titles an exhibition **when it is linked to a per-item detail page on
the venue's own domain** — the link may be the heading, inside it, or an
**ancestor** card link (`<a class="new-show-item" href="/show/…"><h2>…</h2>`,
the shape Griffin actually uses). Rejected as UI chrome, structurally:
text inside `<button>`/`<nav>`/`<footer>`/`<select>`/`<form>`, elements with an
interactive `role` (button/toolbar/menu/…), and elements whose class/id **token**
names a control-surface widget (toolbar, controls, carousel, slider, lightbox,
viewer, flipbook, pagination, …) or a viewer/flipbook vendor family
(`flipbook`, `dflip`, `df-ui`, `df-book`, `swiper`, `slick`, …). bs4 primary,
regex fallback.

Fixture: `tests/fixtures/griffin_current_exhibitions.html` (real DOM shape — 8
`<h2>` shows + a FlipBook control bar + nav/footer).
Test: `test_local580_structural_extraction.py` — extracted set == the real
exhibitions; **excludes every FlipBook label and "Footer"/nav**; each carries its
on-domain `/show/` `detail_url`. **4/4 green.**
Verified on the **live** page: 9 real exhibitions extracted, 0 FlipBook/nav noise.

### D2 — Site-first candidates for exhibition museums
`exhibition_site_first.build_site_first_candidates(...)` discovers the venue's
current-exhibitions listing page, extracts the shows (D1), and fetches each
`/show/` detail page for its description. In `generate_tour_text.py`: when a
museum resolves with **0 catalogued/SPARQL works** and the request is not
exhibition-scoped, a new branch builds `page_sourced` POIs from those shows
(one stop per show, in site order — **GPT never invents**), sets
`_exhibition_stops_source='site_exhibition'`, and bypasses PHASE 3A. The existing
exhibit-museum grounding path verifies each stop against the site text it came
from (`title_appears_in_page`), not the permanent-collection D1v2.
Test: `test_local580_site_first_candidates.py` (fake fetcher) — **5/5 green.**

### D3 — Fabrication guard
`_title_mismatch_refill_pool` gains an `exists_fn` hook. A title-mismatch drop is
re-admitted only if existence is **not definitively disproven**:
`True`→keep (the real Palais "Adoration" case), `False`→drop (a fabrication),
`None`→inconclusive, does **not** block (D162). The real call site builds
`exists_fn` from `stop_existence_gate.verify_stop_existence` (gate off / no DB /
search failure all → `None`, never absence). `exists_fn` is optional, so legacy
callers and the LOCAL-577 unit test are unchanged.
Test: `test_local580_fabrication_guard.py` — **5 invented shows → 0 re-admitted**;
a real work still re-admitted; inconclusive doesn't block; mixed → only the real
one; inert without `exists_fn`. **5/5 green.** LOCAL-577 **9/9 still green.**

### D4 — Actionable structured failure
`actionable_failure.build_actionable_failure(evidence, request, legacy_message)`
→ `{error, error_code, message, suggestion}`. The service merges `error_code`,
`message`, `suggestion` into the job record; the old human string stays verbatim
in `error` for pre-LOCAL-581 app builds. The engine records the resolved
`locality` on the clean-fail evidence.
Test: `test_local580_actionable_failure.py` — **11/11 green.**

#### JSON contract (consumed by the mobile task LOCAL-581)

On a clean fail, the job's error record carries:

```json
{
  "error": "We could not find enough verified material about \"Griffin Museum of Photography\" to build a tour. Try a broader request — for example a walking tour of the surrounding neighbourhood.",
  "error_code": "venue_no_verifiable_content",
  "message": "We could not find enough verified material about \"Griffin Museum of Photography\" to build a tour. Try a broader request — for example a walking tour of the surrounding neighbourhood.",
  "suggestion": {
    "label": "Walking tour of Winchester, MA",
    "request": "walking tour of Winchester, MA",
    "tour_type": "walking"
  }
}
```

- `error` — unchanged human string; **old app builds keep reading this**.
- `error_code` — stable enum the app branches on. Values:
  `venue_no_verifiable_content` (from engine `thin_evidence`/`all_unverified`),
  `exhibition_not_found`, `exhibition_closed`, `venue_misread`,
  `stops_not_colocated` (`address_scatter`), `request_unclassifiable`
  (`unclassifiable_request`), `content_quality_insufficient`
  (`story_gate_failed`), `generation_failed`.
- `message` — plain-language WHY, naming the venue.
- `suggestion` — `{label, request, tour_type}` derived from the venue's resolved
  locality, ready to re-fire as a new `/generate` request. `null` when no
  locality could be derived, or for error codes other than
  `venue_no_verifiable_content` (those carry their own guidance, e.g.
  `exhibition_not_found` keeps the `suggestions` near-match list).

## Tests

Red→green for D1–D4, plus the four named regressions kept green:

| Suite | Result |
|---|---|
| `test_local580_structural_extraction.py` (D1) | 4/4 |
| `test_local580_site_first_candidates.py` (D2) | 5/5 |
| `test_local580_fabrication_guard.py` (D3) | 5/5 |
| `test_local580_actionable_failure.py` (D4) | 11/11 |
| `test_palais_fix_lead_fixture.py` | 23/23 |
| `tests/test_local577_museum_refill.py` | 9/9 |
| `test_local394_never_drop_a_stop.py` | 6/6 |
| `test_sq4_merge.py` | all pass |

## Live runs (gpt-4o, OpenAI hard cap $2.00, existence gate ON — D261, cache OFF — D262)

Harness: `run_local580_live.py <griffin|palais>` (in-process `generate_tour_text`,
same env as `run_local577_palais_live.py`).

### Griffin Museum of Photography, Winchester, MA — museum, 5 stops → REAL TOUR
Log evidence:
```
[LOCAL-580] 0 documented works for 'Griffin Museum of Photography' — exhibition-museum site-first path ELIGIBLE
[LOCAL-580] Site exhibitions found on https://griffinmuseum.org/current-exhibitions: 9 show(s)
PHASE 3A: SKIPPED (LOCAL-580 site-first — 9 current exhibition(s) from the venue site)
[D532] 9 stop(s): 9 confirmed by the venue page, 0 unconfirmed
```
Delivered **5 stops**, every one a current Griffin exhibition, each sourced from
its own `/show/` page:

| Stop | Exhibition | Source |
|---|---|---|
| 1 | Tabitha Soren \| An Artist Life | https://griffinmuseum.org/show/soren_fantasylife/ |
| 2 | TLC | https://griffinmuseum.org/show/tlc/ |
| 3 | Lua Kobayashi \| The Persistence of Memories | https://griffinmuseum.org/show/lua-kobayashi/ |
| 4 | BU Masters Show 2026 \| Traces: Pursuing Process | https://griffinmuseum.org/show/bu-masters-show-2026-traces-pursuing-process/ |
| 5 | Intertidal : Field Notes | https://griffinmuseum.org/show/intertidal-field-notes/ |

(The site publishes 9 shows; LOCAL-212 coverage selection kept the 5 with the
richest sourced material and dropped 4 thin/EMPTY ones — Homage, Earth Wind &
Fire, ULTRASOUND, New England Portfolio Reviews.) Tour: `LOCAL580_GRIFFIN.txt`
(7,875 chars). OpenAI cost ≈ **$0.53**.

**Before this change the same request produced a clean fail with invented shows;
it now produces a real tour of the museum's actual current exhibitions.**

### Palais Lascaris, Nice, France — museum, 4 stops → 4/4
Delivered **4/4** (deterministic catalogue fill, unchanged; LOCAL-577 holds):
`Violes gambe by William Turner (1652)`, `Basse de violon by Paolo Antonio
Testore (1696)`, `Harpe by Naderman (1780)`, `Sacqueboute ténor by Anton
Schnitzer (1581)`. Tour: `LOCAL580_PALAIS.txt`. OpenAI cost ≈ **$0.60**.

## Data safety

`audio_tours` row count: **201 before → 201 after** (declared via
`select count(*) from audio_tours`). The live harness calls `generate_tour_text`
directly and writes files only — no rows created, **none deleted**.

## Files

New: `exhibition_discovery.py`, `exhibition_site_first.py`, `actionable_failure.py`,
`run_local580_live.py`, `tests/fixtures/griffin_current_exhibitions.html`,
`test_local580_structural_extraction.py`, `test_local580_site_first_candidates.py`,
`test_local580_fabrication_guard.py`, `test_local580_actionable_failure.py`,
`LOCAL580_GRIFFIN.txt`, `LOCAL580_PALAIS.txt`.
Edited: `generate_tour_text.py` (site-first branch + capture + fabrication-guard
wiring + locality on clean-fail evidence), `generate_tour_text_service.py`
(actionable-failure fields on the job error).

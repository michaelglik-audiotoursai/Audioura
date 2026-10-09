# SUBMISSION — LOCAL-653

**Courtauld fresh selection picks "Courtauld Institute" and artist names as stops (both A/B arms, 586/592)**

Branch: `LOCAL-653-site-candidates` · Base: `subscribed` @ `8e12c846`
Agent: Mac Mini Kiro

---

## 1. Root cause

The defect run `~/Audioura/.continuous_dev/bench/AB2/run_OFF-1_courtauld586.log` (fresh,
`DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1`) delivered `Van Gogh's iconic Self-Portrait
with Bandaged Ear`, `Manet's A Bar at the Folies-Bergère` and `Courtauld Institute`
(ON arm: also `Georges Seurat`) as stops.

The Wikidata path (`artwork_selection_guard.enforce_collection_membership`) correctly
dropped every one of these as `not_in_collection` (log line 149). But the **site-listed /
`venue_corpus` canonical set** — the set D1v2 (`match_candidate_to_canonical`) matches
each candidate against, and the set R4 replenishment pulls from — only went through
chrome, room and venue-itself filters. It never ran:

1. a **sibling-institution** check (`Courtauld Institute` for `The Courtauld Gallery`);
2. an **artist-name-alone** check (`Paul Cézanne`, `Georges Seurat`, `Edgar Degas` — the
   venue's own artists scraped as links);
3. a **marketing-prefix** strip on the stop name.

Two compounding bugs made the existing guards blind here:

- **Location-suffix bug.** `_verify_works_v2` is called with
  `_d1v2_venue_arg = "The Courtauld Gallery, London, United Kingdom"` (name + city tail,
  generate_tour_text.py ~line 11564). With that suffix,
  `room_candidate_guard.is_venue_itself_title` and `junk_title_guard.is_junk_page_title`
  BOTH return `False` even for `Courtauld Gallery` / `Courtauld Institute` — the city/country
  tokens defeat the venue-name token comparison. (Verified directly: both return `True`
  without the suffix, `False` with it.)
- **D1v2 renames the stop to the canonical form.** When a clean GPT candidate
  (`A Bar at the Folies-Bergère`) matches the marketing-prefixed canonical title
  (`Manet's A Bar at the Folies-Bergère`), D1v2 overwrites `poi['name']` with the dirty
  canonical form (generate_tour_text.py ~line 5995). The ad copy became the stop title.

## 2. Fix

**New pure module `site_candidate_guard.py`** (no network / LLM / DB; deterministic;
unit-tested):

- `venue_core_name(venue)` — the distinctive name with the location tail and institution
  noun stripped (`"The Courtauld Gallery, London, United Kingdom"` → `"courtauld"`).
  Location-suffix robust by construction.
- `is_venue_or_sibling_title(title, venue)` — the venue itself, a sibling institution
  (`Courtauld Institute`, `Courtauld Institute of Art`) or a bare site brand.
- `is_artist_name_alone(title, artist_names, allow_shape_fallback=False)` — precise match
  against the venue's own SPARQL creator labels by default; an opt-in bare-name SHAPE
  fallback (2–3 capitalised tokens, no work-signal word) for scraped artist links that are
  not in the creator set.
- `strip_marketing_prefix(title, known_titles)` — strips a leading possessive-artist +
  marketing-adjective prefix (`Van Gogh's iconic …`, `Édouard Manet's famous painting …`,
  `Courbet's provocative …`) ONLY when the remainder matches a known title; returns the
  clean title and the artist (kept for narration).
- `filter_site_candidates(...)` — one call applying `junk_title_guard` (passed the venue
  **core** name, fixing the suffix bug) + sibling + artist-name, with `protected_titles`
  for SPARQL labels. A precise creator-name match drops even a protected label (the
  "Georges Seurat"/"Edgar Degas" leak, where the artist page was catalogued as a "work");
  the junk/sibling/shape heuristics never override protection.

**Wiring in `generate_tour_text.py._verify_works_v2`** (museum-only path):

1. At the canonical-SET chokepoint (right after the LOCAL-626 venue-itself filter):
   `filter_site_candidates(canonical_titles, venue_name, artist_names=<SPARQL creators>,
   protected_titles=sparql_titles, allow_shape_fallback=True)`. This propagates to D1v2
   verification, R4 replenishment and every downstream path that reads the canonical set.
2. At D1v2 stop-naming (before `poi['name'] = _best_title`): `strip_marketing_prefix`,
   with the matched candidate `work_name` added to the known-titles set so the clean GPT
   title anchors the strip. The stripped artist is stored on `evidence_log[...]
   ['marketing_artist']` for the narration.

## 3. No regression elsewhere

- Offline guard-shape checks for **the Walters, the National Gallery, the Uffizi and the
  Frick** (with `allow_shape_fallback=True`, real works `protected`): every real work is
  kept and no title is altered by the marketing strip — including portrait/sitter-titled
  works that share the bare-name shape (`Mr and Mrs Andrews`, `Battista Sforza`,
  `Sir Thomas More`, `Jan van Montfort`), which are shielded because they are
  SPARQL-confirmed. Sibling institutions (`National Gallery of Art`, `The National
  Gallery`) are correctly dropped; real works containing the venue word (`A National
  Monument`, `National Debt Allegory`) are kept.
- **Walking tours are unaffected:** `_verify_works_v2` is only invoked on the museum path
  (`if tour_category == 'museum' and _museum_venue_name:`), so the museum-only chokepoint
  cannot touch a walking tour.

## 4. Tests (exit codes)

| Suite | Result |
|-------|--------|
| `test_local653_site_candidates` (new, 17 tests) | **OK** (exit 0) |
| `test_local632_junk_and_shortfall` (26) | OK (exit 0) |
| `test_local629_selection_diversity` (13) | OK (exit 0) |
| `test_local630_venue_truth` (24) | OK (exit 0) |
| `test_local636_national_gallery` (9) | OK (exit 0) |
| `test_local639_collection_holders` (6, 1 skip) | OK (exit 0) |
| `tests.test_local626_venue_not_a_stop` (7) | OK (exit 0) |
| `tests.test_local576_named_anchors` | OK (exit 0) |

The new suite is built from the real line-146 candidate list in
`run_OFF-1_courtauld586.log`.

## 5. Live (own container, cap $1.50)

Isolated disposable container `local653-gen` (`docker run --rm`, spare port 5130, network
`development_default`, DB `development-postgres-2-1`), built from this branch via
`Dockerfile.generator`. Fresh (`DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1`). Never
`docker compose -p audioura`; no `audioura-*` container touched.
Harness: `run_local653_live.sh` + `run_local653_container.py`.

**Final run — the Courtauld, 3 stops, fresh, twice (tour ids 612, 613):**

| | Tour 612 | Tour 613 |
|---|---|---|
| Stops | Christ and the Woman Taken in Adultery · Self-Portrait with Bandaged Ear · Footed Bowl with the Crucifixion | (same) |
| `venue_as_stop` | **PASS** | **PASS** |
| `artist_name_as_stop` | **PASS** | **PASS** |
| `marketing_prefix` | **PASS** | **PASS** |
| Kiro (`critique.sh <id> 3`) | **8.5/10** | **6.5/10** |

Canonical-set filter dropped: `Courtauld Institute` (sibling), `Courtauld Gallery`
(venue), `Georges Seurat` / `Edgar Degas` / `Paul Cézanne` (artist links), plus
`Am Römerholz` / `Gambier-Parry Collection` / `Italian Primitives` / `Turning Road`.
Marketing prefixes stripped: `Van Gogh's iconic Self-Portrait with Bandaged Ear` →
`Self-Portrait with Bandaged Ear`; `Manet's  A Bar at the Folies-Bergère` →
`A Bar at the Folies-Bergère` (artist kept for narration).

Kiro on both tours: **"all three works genuinely hang at the Courtauld."** The remaining
defects it lists (outdated admission price, provenance filler, conclusion synthesising
only one stop, left/right-ear phrasing) are pre-existing and outside LOCAL-653's scope
(site-candidate selection + marketing prefixes). Compare 586/592, where Kiro scored the
`Courtauld Institute` school stop 5.5 in both arms.

**Rows / spend:** `audio_tours` 415 → 417 (two additive `is_test=true` rows, 612/613).
No DELETE. Spend for the final run: **$0.8928** combined across all providers
(`live_run_meter`, cap $1.50) — openai $0.765, gemini grounding/tokens, serper,
preflight. Earlier diagnostic runs (607/609 old code; 610/611 partial fix) were also
additive `is_test` rows; none deleted.

### Known tradeoff
`Turning Road` (a real André Derain work) was dropped by the bare-name SHAPE fallback
because it is a short two-token title that was not SPARQL-protected in this run. It did
**not** affect the delivered tour (three real works delivered); the Courtauld has ample
other works to fill from. This is the precision/recall trade the ticket explicitly
sanctions ("an artist name alone is not a work … or drop it"). The fallback never drops a
SPARQL-confirmed work (protection runs first), so it bites only unverified short titles.

## 6. Files

- `site_candidate_guard.py` — new pure module.
- `generate_tour_text.py` — canonical-set filter + marketing-prefix strip in
  `_verify_works_v2`.
- `test_local653_site_candidates.py` — new regression suite (17 tests).
- `run_local653_live.sh`, `run_local653_container.py` — isolated live harness.

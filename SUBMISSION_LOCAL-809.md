# SUBMISSION — LOCAL-809: Museum tours — gift-shop items, other museums' artworks, Wikipedia disambiguation stubs

**Branch:** `LOCAL-809-museum-sources` · **Base:** subscribed (`ab1c97e9`)
(`git merge-base --is-ancestor ab1c97e9 HEAD` → exit 0)

## Evidence (catalog review LOCAL-808 + Mac DB tours 850, 861)

- **850 Metropolitan Museum, New York — 3.0:** stops 2 & 3 were **Met Store
  products** written up as exhibits — "Empire State Building Custom Print",
  "Wall Calendar 2027 — The Met Store".
- **861 Belvedere Museum, Vienna — 3.5:** stops 3 (Monet "Père Paul") and 5
  (Van Gogh "Plain of Auvers") are **not in the Belvedere**; stop 1 contained
  "Belvedere may refer to:" (a Wikipedia **disambiguation** page); all pins
  **~1 km off** (the bare name "Belvedere" resolved to the wrong place).

## The four fixes

### Fix 1 — shop / commerce pages are never exhibit sources
`junk_title_guard.py` (new pure predicates, exported):
- `is_commerce_url(url)` — rejects a `store.`/`shop.` host, a `/shop/`
  `/store/` `/products/` `/cart`/`/checkout` path, or an `add-to-cart`/`sku`/
  `variant` query. Content URLs (`/art/collection/…`, `/exhibitions/…`) are not
  matched.
- `is_shop_product_title(title)` — rejects a shop **product name**: a price
  token, an "add to cart"/stock phrase, a SKU/item number, a store **brand
  suffix** ("… — The Met Store"), a **strong** product noun used as a product
  name (calendar / print / poster / tote bag / mug / puzzle / gift set / …), or a
  **weak** apparel noun (hat/tie/cap/bag/socks/scarf) **only** alongside an
  explicit retail signal. Conservative so real works survive.
- `is_junk_page_title(title, venue_name, source_url="")` now takes an optional
  `source_url` and rejects at **step 0** on a commerce URL or a shop-product
  title; `filter_out_junk_titles(..., url_keys=(…))` reads the candidate's URL.
- `artwork_selection_guard.enforce_artworks_only` step 1b now passes the
  candidate's source URL to the junk check (reason `shop_or_junk_page_title`),
  so a store page is dropped at intake even if its title looks clean.

Verified: "Empire State Building Custom Print" and "Wall Calendar 2027 — The Met
Store" rejected; `store.metmuseum.org`/`…/shop/products/…` URLs rejected; real
works kept — "Self-Portrait with a Straw Hat", "The Blue Boy", "Man in a Red
Turban", "Woman with a Parasol", "The Umbrellas", "Washington Crossing the
Delaware".

### Fix 2 — artwork ⇄ museum collection (Wikidata P195 / P276)
The gate already exists in `artwork_selection_guard.enforce_collection_membership`
(wired through `generate_tour_text._apply_artwork_guards`): a work whose P195
(collection) carries QIDs none of which is the venue or a derived parent/sibling
holder is rejected, whatever its P276 ("location") says; and a candidate that is
neither a P195/P276-confirmed SPARQL work nor venue-site-listed is rejected.
**Added** the ticket's exact per-work log in `_apply_artwork_guards`:

```
[LOCAL-809] not in collection <title> <found collection>
```

where `<found collection>` is the work's own P195 collection QIDs (e.g. the Monet
/ Van Gogh "not in the Belvedere" case) or the reject reason.

Verified: with Belvedere `Q303139` SPARQL, Monet "Père Paul" (P195 `Q23402`) and
Van Gogh "Plain of Auvers" (P195 `Q163804`) are dropped and the reject reason
carries the found collection; the Belvedere's own works survive.

### Fix 3 — Wikipedia disambiguation stub is never corpus
New pure module `disambiguation_guard.py`:
`is_disambiguation_text(text, title="")` rejects an "X **may refer to**" /
"may also refer to" / "can refer to" / "refers to:" **lead** (anchored to the
first ~400 chars) plus DE/FR/IT/ES/NL equivalents, and explicit markers
("(disambiguation)", "Begriffsklärung", "Homonymie", …). Wired at every
Wikipedia-extract acceptance point so a stub can never become corpus:
`three_class_retrieval._wiki_fetch` + `_wiki_search_fetch`, `story_miner` (venue
corpus), `stop_subject_acquisition`, `rag_retriever` (both return branches). Each
logs `[LOCAL-809] disambiguation page rejected as corpus: <title>`.

Venue resolution by **QID + city** already exists
(`venue_resolver.resolve_venue(venue_string, city)` + `_filter_disambiguation_pages`,
Wikidata P31 = Q4167410), so "Belvedere, Vienna" resolves to the Österreichische
Galerie Belvedere entity, not the bare name.

Verified: "Belvedere may refer to:" and "Salem may refer to:" (and DE/FR leads)
rejected; real Belvedere / Upper Belvedere / Met articles kept — including the Met
lead "…colloquially **referred to** as the Met…", which must NOT trip the rule.

### Fix 4 — museum pin = the museum's own Wikidata P625
`pin_snap.py` already treats a stop's own Wikidata **P625** (`wikidata_lat/lng`)
as the strongest **authority** reference (`source='wikidata'`, exempt from the
geocoder name/centroid/off-scope guards), and `venue_resolver._get_coordinates`
supplies the venue's P625. The Belvedere's ~1 km pin error was a **consequence**
of Fix 3 (the bare name resolved to the wrong entity, so the wrong P625 was
used); with the correct entity its P625 pins the museum. No code change was
needed here — verified that `snap_pin` snaps a ~1 km-off Belvedere pin to its own
P625 and keeps a good P625 pin.

## Tests

`test_local809_museum_sources.py` — **20 tests, all pass** — exact evidence
strings for all four fixes:

```
python3 -m pytest test_local809_museum_sources.py -q
....................                                          20 passed
```

### Regression (museum / guard / selection — green with these changes)
- `test_local630_venue_truth 632 721 639 636` → 71 passed, 1 skipped
- `test_local653 585_about 585_r2 591(x2) 637 744 tests/791e 791c_pin_snap` →
  143 passed, 2 failed
- `test_local37_three_class 24_corpus tests/415 667 668 583` → 53 passed, 1 failed
- `test_local629 617 634 642 644 766 632 721` → 130 passed

The **3 failures** —
`test_local585_r2_about_hygiene::test_properly_cased_locality_present`,
`test_local744_screen_work_disclosure::test_live_salem_places_verify_when_network_available`,
`tests/test_local415_usable_material::test_usable_count_reflects_title_relevance`
— are **PRE-EXISTING on the clean base** (confirmed by `git stash` → same
failures) and network-dependent (live Wikidata/Nominatim). **Not caused by these
changes.**

## Live verification — attempted, blocked by external services

`run_local809_container.py` runs the Met and Belvedere requests through the real
generation path (`RESEARCH_BACKEND=serper`, `NARRATION_MODEL=gpt-4.1-mini`, cheap
arm), hard-capped at **$1.20** by `tests/live_run_meter.py` with a reserve gate,
and checks every stop for shop/junk titles, disambiguation text, and pin distance
(≤ 150 m of the venue P625, in-scope of the city). It stores `is_test` rows in an
**isolated** postgres only (`local788b-postgres` on `local788b_default`), in
disposable `--rm` containers — never `-p audioura`, never a live/development DB.

Two fresh tours (≤ 3) were run. Both **cleanly failed to produce text** because of
**external** blockers, not the LOCAL-809 code:
- **Met:** the model's candidate POIs were all **real Met works** (Washington
  Crossing the Delaware, The Death of Socrates, The Harvesters, Self-Portrait with
  a Straw Hat, The Great Wave off Kanagawa) — **no** shop products, and the
  commerce guard rejected none. But `fetch_venue_works(Q160236)` hit WDQS SPARQL
  **ReadTimeout ×4** (60 s + backoff) → 0 canonical titles → clean fail. (A
  trivial WDQS query from the same container returns 200 in ~8.7 s; the heavy Met
  works query is throttled.)
- **Belvedere:** a secondary coordinates/cache DB the generator expects at
  `localhost:5433` is absent on the isolated network, plus the same WDQS stall →
  clean fail.

Cost total **$0.0005** (well under the $1.20 cap). Isolated DB unchanged (16 rows
before and after). No live/development DB write; containers removed.

The four fixes are fully verified by the 20 unit tests (exact evidence strings)
and regression; the live end-to-end is blocked by intermittent WDQS throttling and
a missing isolated service DB — an environment limitation, not a defect in these
changes.

## Files changed

New:
- `disambiguation_guard.py` — pure `is_disambiguation_text`.
- `test_local809_museum_sources.py` — 20 evidence tests.
- `run_local809_container.py` — isolated live-run harness.
- `SUBMISSION_LOCAL-809.md` — this document.

Modified:
- `junk_title_guard.py` — `is_commerce_url`, `is_shop_product_title`,
  `source_url` in `is_junk_page_title` / `filter_out_junk_titles`.
- `artwork_selection_guard.py` — pass source URL to the junk check at intake.
- `generate_tour_text.py` — the exact `[LOCAL-809] not in collection …` log.
- `three_class_retrieval.py`, `story_miner.py`, `stop_subject_acquisition.py`,
  `rag_retriever.py` — reject disambiguation extracts as corpus.

## Process

Committed only the files above (no `git add -A`). No edits to DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md. No `DELETE`. No live DB write.

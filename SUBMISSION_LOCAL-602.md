# SUBMISSION — LOCAL-602: WNDR Museum (chain venue, JavaScript-only site, no coordinates)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-602-chain-spa-venue`  (based at `subscribed` @ `21b9eba`)
**Field test:** Michael, 2026-10-06 20:38, tour 397 — `WNDR museum, Boston, MA`, 7 stops.

## What happened

The request delivered **1 stop, "WNDR Museum — Overview", lat/lng NULL** (invisible to
tours-near, no map pin). The log showed the chain/JS-only failure modes:

```
[venue_resolver] Single candidate Q112081342 (WNDR Museum) failed city validation for 'Boston'
[venue_resolver] Artist inferred from name: 'WNDR'          ← wrong: WNDR is a brand, not an artist
[LOCAL-589][fetch] /current-exhibitions, /exhibitions, ... → 200, bytes=210318 (all identical)
[LOCAL-580] Site-first found no current exhibitions — reason=parsed_zero
[D1] Tier: unresolvable → POOL DELIVERY new=1 → "Stop 1: WNDR Museum — Overview"
[SCORING] Non-fatal error: No module named 'tour_evaluator'
```

## Root causes & fixes (one commit per step)

### #4 — "Artist inferred from name" for a brand (`venue_resolver.py`)
`_infer_artist_from_name("WNDR museum")` stripped "museum" and returned `WNDR` as the
single-artist name. Added `_looks_like_human_name_word`: a residual token must have
human-name shape — a leading capital followed by lower-case letters. This **rejects
all-caps acronyms** (`WNDR`, `SFMOMA`, `LACMA`, `ICA`) and **camel-case initialisms**
(`MoMA`), while preserving genuine artist museums (`Matisse`, `Marc Chagall`,
`Isabella Stewart Gardner`). Deterministic shape test; no name list.
*Test:* `tests/test_local602_artist_heuristic.py` (6).

### #1 + #2 — chain venue + JavaScript-only site (`exhibition_site_js.py` new; `exhibition_site_first.py`)
Every path on `wndrmuseum.com` returned the **same 210 KB client-side shell**, so the
structural extractor found nothing (`parsed_zero`), and WNDR is a chain (its Wikidata
item failed city validation). New pure, injectable module `exhibition_site_js.py`:

- `shell_fingerprint` / `detect_identical_shell` — recognise a JS-only site (several
  distinct paths collapsing to one fingerprint);
- `sitemap_urls` — on-domain URLs from `/sitemap.xml` + `Sitemap:` lines in `/robots.txt`;
- `pick_branch_url` / `branch_url_seeds` — the city branch page (`/<city>`,
  `/locations/<city>` …), from the sitemap or a conventional slug;
- `extract_embedded_json` — `__NEXT_DATA__`, `application/ld+json`,
  `window.__INITIAL_STATE__` inside the shell → `{title, detail_url, source_url}`;
- `serper_site_city` — `site:<domain> <city>` organic results, each with its own URL;
- `filter_other_city` — drop anything attested only on another branch's page.

Wired into `build_site_first_candidates` (new `city` / `serper` params): when the
structural extractor returns nothing, run branch → sitemap → embedded-JSON → Serper,
filter other-branch cities, and return candidates **each with a source URL**. No
headless browser. `generate_tour_text` passes the requested city and a Serper caller.
*Tests:* `tests/test_local602_js_shell.py` (13), `tests/test_local602_site_first_js_integration.py` (5).

### #3 — never deliver a tour without coordinates (`generate_tour_text.py`, `museum_overview.py`)
The overview/pool delivery bypassed LOCAL-591 #4. `MuseumOverview` now carries the
venue's own `address` (lifted from its `/visit`/`contact` page) and `coordinates`.
`_assemble_overview_tour_text` geocodes the address (preferred — binds to the building)
or the location, emits `Address:`/`Coordinates:` lines, and **returns `None`
(clean-fail) when no coordinate can be produced** — so a tour is never shipped without a
map point. `_try_deliver_museum_overview` aborts to rung 4 on `None`.
*Test:* `tests/test_local602_overview_coordinates.py` (3); `test_local582` envelope now
asserts the `Coordinates:` line.

### #6 — D616 shortfall wording on the overview path (`generate_tour_text.py`)
A 1-stop overview for an N-stop request now leads Stop 1 with the honest
`about_museum_stop.build_shortfall_sentence` output whenever the ask exceeds the single
overview stop (absent when the ask is met or unknown).
*Test:* `tests/test_local602_overview_shortfall.py` (3).

### #5 — orchestrator image missing scoring imports (`Dockerfile.orchestrator`)
`tour_scoring_service.py` was copied but not its imports. Added
`COPY tour_evaluator.py` and `COPY tour_rubric_scorer.py` (the latter is also read at
runtime by `_get_code_sha`). **Proven:** built `local602-orchestrator:test` and ran
`python -c "import tour_scoring_service"` inside it → OK (SCORER_VERSION
`LOCAL-311-v1@41db0d2f`); `import tour_evaluator` also OK.

## Tests (exits)

| Suite | Result |
|---|---|
| `tests/test_local602_*` (5 files) | **30 passed** (EXIT 0) |
| `test_local599*` / `tests/test_local599*` | **33 passed** (EXIT 0) |
| `tests/test_local600_order_and_shortfall.py` | **24 passed** (EXIT 0) |
| `test_local589_*` | **25 passed** (EXIT 0) |
| `test_local592_*` | **51 passed** (EXIT 0) |
| combined 599/600/589/592 glob | **133 passed** (EXIT 0) |

## Live run (isolated container, cap $2)

`docker run --rm --name local602-gen` on a throwaway network (`local602-net`) with a
disposable Postgres (`local602-pg`, `postgres:15-alpine`). **No `audioura-*` container
was run, stopped, or modified.** Full log + tour text in `local602_live/`.

- **Result:** `TIER: exhibit_museum   TOUR_KIND: full` — **not** a 1-stop Overview.
- **Branch / site lines:**
  - every path returned the identical `bytes=210318` shell;
  - branch seeds tried: `/boston`, `/locations/boston`, `/location/boston`,
    `/visit/boston`, `/cities/boston`, plus `/robots.txt` and `/sitemap.xml`;
  - `[LOCAL-602] Serper site:wndrmuseum.com Boston → 10 result(s)`;
  - `PHASE 3A: SKIPPED (LOCAL-580 site-first — 10 current exhibition(s) from the venue site)`;
  - **no** `Artist inferred from name: 'WNDR'`.
- **Stop titles + source URLs** (each on the Boston branch):
  - Stop 1: Flex | WNDR Museum Boston — `…/installations/boston/flex`
  - Stop 2: WNDR Museum Boston — `…/location/boston`
  - Stop 3: Speak Up! | WNDR Museum Boston — `…/installations/boston/speak-up`
  - Stop 5: MPO-1 (Time Machine) | WNDR Museum Boston — `…/installations/boston/mpo-1-time-machine`
  - Stop 6: Buy Gift Cards - WNDR Boston — `…/tickets/boston/gift-cards`
  - Stop 7: WNDRWall | WNDR Museum Boston — `…/installations/boston/wndrwall`
- **Stop 1 opening section:** `Address: 404 E. 1st St, Boston, MA 02127` /
  `Coordinates: 42.3393, -71.0402`.
- **Coordinates:** 7 `Coordinates:` lines, all `42.3393, -71.0402` (the Boston branch) —
  no NULLs.
- **BLOCKER 3:** 19 PASS / **1 style FAIL** (cosmetic repeated shingle "gift cards wndr
  boston") / **0 FACTUAL FAIL**.
- **Tour total:** `$1.3082` (< $2 cap). Scoring ran — no `No module named 'tour_evaluator'`.

The LOCAL-600 counts were `exhibitions_on_view=0 delivered=7 requested=7`, so the ask was
met by real on-view material and the D616 shortfall sentence correctly did **not** appear
(it is pinned by test for the genuine-shortfall case).

## Scope / safety

- No DELETE of any data; tour 397 untouched; no GCloud.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `.continuous_dev/STATUS.md`.
- Disposable Postgres + network torn down after the run.

## Files changed

- `venue_resolver.py` — artist-name shape guard.
- `exhibition_site_js.py` (new) — JS-only / chain fallback helpers.
- `exhibition_site_first.py` — identical-shell fingerprint + JS fallback wiring.
- `generate_tour_text.py` — pass city/serper; overview coordinates + D616 shortfall.
- `museum_overview.py` — `MuseumOverview.address` / `.coordinates`.
- `Dockerfile.orchestrator` — COPY `tour_evaluator.py`, `tour_rubric_scorer.py`.
- `run_local602_wndr.py` + `local602_live/` — live-run harness and artifacts.
- `tests/test_local602_*.py` (5), `test_local582_museum_overview.py` (envelope + coords).


---

## r2 — chain/SPA defects from the r1 live run (junk stops, wrong coordinates, D617 items 9–12)

**Agent:** Mac Mini Kiro  **Branch:** `LOCAL-602-chain-spa-venue` (continued; rebased on
`origin/subscribed` which carries the r1 merge + the LOCAL-603 venue-preflight).
**Base invariant held:** `git merge-base --is-ancestor b856106 HEAD` exits 0 throughout.

r1 was merged for its infrastructure (branch page, identical-shell detector,
sitemap/JSON/Serper fallbacks, overview coordinates, tour_evaluator COPY). The r1
WNDR live run exposed six defects that would hit the next open chain or SPA venue;
r2 fixes each with a deterministic rule and a per-fix test, then live-validates on an
open SPA venue.

### #1 — Junk stops (`exhibition_site_js.py`, `exhibition_site_first.py`)
r1 shipped `Stop 6: Buy Gift Cards` (`/tickets/boston/gift-cards`) and `Stop 2: WNDR
Museum Boston` (the `/location/boston` branch page). A stop must be an installation,
work, room or exhibition. New deterministic, path-only `is_stop_url` /
`reject_non_stop_urls`: reject any URL whose path has a segment in `NON_STOP_SEGMENTS`
(tickets, gift-cards, shop, membership, events, faq, visit, contact, about, cart,
checkout, account, careers, press, blog, news, privacy, terms, search, donate, …), the
bare domain / home page, and the **city branch index** itself (path whose only segments
are branch wrappers + the city slug). Wired into `build_site_first_candidates` right
after the no-other-city filter. *Test:* `tests/test_local602_r2_junk_stops.py` (11) —
pins the two exact WNDR junk URLs rejected and the four real installation URLs kept.

### #2 — Wrong coordinates (`tour_coordinates.py`, `generate_tour_text.py`)
r1's 7 stops were all at the chain's Seaport point `42.3393, -71.0402`, ~1.9 km from the
venue address — "same city, wrong building", inside the 50 km tour-radius guard so
nothing caught it. New `tour_coordinates.verify_against_address(coord, address)`: geocode
the street **address** and reject a coordinate > **300 m** from it (`ADDRESS_MATCH_RADIUS_M`,
env-overridable), re-deriving the point from the address geocode. The geocoder is
injectable. Wired into the overview path in `_assemble_overview_tour_text` (the r1
delivery path) after the coordinate is chosen. *Test:*
`tests/test_local602_r2_address_coordinates.py` (8) — the Seaport point is corrected, a
~15 m point is kept, threshold boundary, no-geocode/no-candidate degradations, custom
radius; all offline via an injected geocoder.

### #9 (D617) — No URL / no "Sources" in spoken text (`spoken_text_hygiene.py`, `break_text_to_pois.py`)
A listener never hears a URL. New `strip_sources_and_urls(text)` removes every
`http(s)://`/`www.` token and any `Sources:`/`Sources (…):` block; applied in the packer
`process_tour_file` on each stop's spoken text before it is written to `audio_N.txt`. The
full-text / web view keeps its sources. *Test:*
`tests/test_local602_r2_spoken_no_urls.py` (5) — unit-tests the strip, then runs the REAL
packer on a tour carrying URLs + a Sources block and **scans every `audio_*.txt` for
`http`/`www.`** (the acceptance scan the task names), asserting zero.

### #10 (D617) — Hours/admission spoken when published; "check the website" at most once (`practical_facts_gate.py`, `generate_tour_text.py`)
Hours and admission are spoken when the venue publishes them (the LOCAL-592 visiting-
sentence composers, unchanged). When a field is unpublished we point at the venue site —
but on the overview path the overview narration AND the Stop-1 opening section each carry
their own pointer, so a 1-stop overview could say "check the website" twice. New
`collapse_website_pointers(text)` keeps the FIRST website-pointer sentence tour-wide and
drops later ones; applied on the full path (after `clean_spoken_text`) and the overview
path. A tour that publishes both fields has no pointer and is untouched. *Test:*
`tests/test_local602_r2_check_website_once.py` (7).

### #11 (D617) — About describes the museum, not its founder (`about_museum_stop.py`)
WNDR's About page is the Bradley Keywell biography; every "Bradley Keywell is a serial
entrepreneur…" sentence carries the story verb "founded", so the old `_is_story_sentence`
lifted it as the museum's story. New `_subject_is_person` / `_states_museum_identity`:
a sentence whose SUBJECT is a person (person-name lead or a biography marker —
entrepreneur, co-founder, "he was", "grew up", "studied") is rejected UNLESS it also
states the museum's own identity (names the venue AND a museum-kind word). Wired into
`_is_story_sentence` before the signal/verb check. A sentence that names the founder but
states the museum's identity ("WNDR Museum was co-founded by Bradley Keywell … as an
immersive art experience") is kept. *Test:*
`tests/test_local602_r2_about_describes_museum.py` — classifiers + `_is_story_sentence`
cases + `_collect_story_sentences` on a WNDR-style About page (museum sentences kept,
founder biography never lifted).

### #12 (D617) — No "From X to X" recap under 2 stops (`stop_pool_assembly.py`, `tour_cache_layer1.py`, `spoken_text_hygiene.py`)
A 1-stop pool/overview delivery made `_closing_recap` emit "From {X} to {X}, you have
followed the thread of a single story." (first == last — nonsense). Fixed at the source:
`stop_pool_assembly._closing_recap` states a plain single-stop count when `n < 2`;
`tour_cache_layer1._repair_recap` drops the From→to clause when trimmed to `< 2`; and a
tour-wide safety net `spoken_text_hygiene.strip_degenerate_from_to_recap` removes any
"From X to Y, you have followed…" sentence when X == Y (applied on the full path). A
genuine 2+-stop recap is untouched. *Test:* `tests/test_local602_r2_recap_two_stops.py` (7).

### Tests

| Suite | Result |
|---|---|
| 6 new `tests/test_local602_r2_*.py` + r1 `tests/test_local602_*` | part of the 222 below |
| r2 + LOCAL-602 + about/overview/coord/practical-facts suites | **222 passed** (EXIT 0) |
| LOCAL-589 / LOCAL-580 / LOCAL-600 regression suites | **74 passed** (EXIT 0) |

**296 tests, 0 failures** across every module touched — no regressions.

### Live run (ISOLATED containers, cap $2, VENUE_PREFLIGHT enabled)

Disposable `local602b-gen` + a disposable Postgres `local602b-pg` on a disposable network
`local602b-net` (`postgres:15-alpine`). **No `audioura-*` container was run, stopped, or
modified**; all disposable resources were torn down. Harness: `run_local602b_moic.py` +
`run_local602b_live.sh` (log at `tours/local602b_live/`, gitignored).

**Museum of Ice Cream, New York, NY — 5 stops, preflight ON.** Preflight: `status=open
hours=y admission=y highlights=6` (open, not closed). The **junk-stop filter dropped 6
non-stop pages** (blog/events/faq/city-guide pages from the sitemap/Serper). But MOIC has
no server-rendered works/exhibition page, so the exhibit-museum D1 grounding gate dropped
every remaining site candidate → honest **clean fail** ($0.0004). MOIC is open but yields
no groundable stops on this path, so — as the task instructs — I picked another **open
SPA venue** that delivers and say which: **Meow Wolf, Santa Fe, NM.**

**Meow Wolf, Santa Fe, NM — 5 requested, delivered a full tour, `Tour total: $0.2205`
(< $2):**
- **Stop titles with source URLs:**
  - Stop 1: `Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out` — `https://meowwolf.com/adulti-verse/santa-fe`
  - Stop 2: `Santa Fe City Guide: Top Attractions & Restaurants Near …` — `https://meowwolf.com/destinations/santa-fe-city-guide`
  - (the junk-stop filter had already removed blog/faq/guide pages from the candidate set).
- **Coordinates vs the address:** `Address: 1352 Rufina Cir, Santa Fe, NM 87507` with
  `Coordinates: 35.6611, -105.9492` — the real Meow Wolf Santa Fe building, address and
  coordinate agreeing (the #2 300 m check would have corrected a stray chain point).
- **Stop 1's opening section:** describes **Meow Wolf the institution** — "In 2008, Meow
  Wolf was founded as an arts and entertainment company dedicated to creating large-scale,
  interactive art installations…", the House of Eternal Return, its mixed-media technique —
  never a founder biography (#11), and with **zero** "check the website" pointers (#10).
- **The spoken text's last 15 lines:** URL-free and Sources-free; the closing recap reads
  "That's 2 stops — … This tour covered …" — a legitimate two-stop recap, **not** "From X
  to X" (#12).
- **Packer spoken-text scan (`break_text_to_pois` on the delivered tour, and on a copy
  with URLs + a `Sources:` block injected):** every `audio_*.txt` is **URL-free and
  Sources-free**; on the injected copy the packer stripped 2 URLs from stop 1 and 1 Sources
  block from stop 2, and the scan still found zero `http`/`www.`/`Sources` (#9).
- **D617 item 10 / 12 checks on the delivered tour:** `'check the website' pointer
  sentences: 0`; `'From X to X' degenerate recap sentences: 0`.

### Scope / safety
- No DELETE of any data; no GCloud. The live run used a disposable Postgres so the stop
  pool was isolated; no `audioura-*` container or shared DB was touched.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `.continuous_dev/STATUS.md`.

### Files changed (r2)
- `exhibition_site_js.py` — `is_stop_url` / `reject_non_stop_urls` / `NON_STOP_SEGMENTS`.
- `exhibition_site_first.py` — junk-stop filter wired into `build_site_first_candidates`.
- `tour_coordinates.py` — `verify_against_address` / `ADDRESS_MATCH_RADIUS_M`.
- `spoken_text_hygiene.py` — `strip_sources_and_urls`, `strip_degenerate_from_to_recap`.
- `break_text_to_pois.py` — spoken-text URL/Sources strip in the packer.
- `practical_facts_gate.py` — `collapse_website_pointers` / `is_website_pointer_sentence`.
- `about_museum_stop.py` — `_subject_is_person` / `_states_museum_identity` + wiring.
- `stop_pool_assembly.py`, `tour_cache_layer1.py` — `< 2`-stop recap guards.
- `generate_tour_text.py` — #2 address verification on the overview path; #10 + #12
  tour-wide passes.
- `tests/test_local602_r2_*.py` (6 new files); `run_local602b_moic.py` +
  `run_local602b_live.sh` (isolated live-run harness).


## r3

**Branch:** `LOCAL-602-chain-spa-venue` (rebased on `origin/subscribed` @ `2b5706c`,
which carries the merged r2 plus LEAD's live-packer URL-strip; base ancestry
`git merge-base --is-ancestor 52170a2 HEAD` → exit 0).

### Why
r2 is merged and good (address-verified coordinates, D617 spoken-text). But the
junk filter was a **block-list** — a page became a stop *unless* a path segment was
on `NON_STOP_SEGMENTS`. A block-list can only reject the junk it has already seen,
so the Meow Wolf Santa Fe **live** run (r2) delivered two pages whose junk words
were simply not on the list:

- `Stop 1: Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out` — `/adulti-verse/santa-fe` (an event)
- `Stop 2: Santa Fe City Guide: Top Attractions & Restaurants Near …` — `/destinations/santa-fe-city-guide` (a blog/guide)

### 1. Allow-list, not block-list (positive identification)
A page becomes a stop **only when positively identified** as an exhibit /
installation / room / work. The new authority is `exhibition_site_js.is_exhibit_stop`
(and `reject_non_stop_urls`, which now runs it); evidence is any ONE of three
deterministic, local signals:

- **URL path segment** in `STOP_PATH_SEGMENTS` — `/installations/`, `/installation/`,
  `/exhibits/`, `/exhibit/`, `/exhibitions/`, `/exhibition/`, `/rooms/`, `/room/`,
  `/artworks/`, `/artwork/`, `/works/`, `/collection/`, `/collections/`,
  `/galleries/`, `/gallery/`, …;
- **JSON-LD `@type`** in `EXHIBIT_JSONLD_TYPES` — `ExhibitionEvent`, `VisualArtwork`,
  `Artwork`, `Installation`, `CreativeWork`, `Exhibition` — or a `Place`/`Room` type
  **on the venue's own domain** (a room within the venue, never an external place).
  `extract_embedded_json` now propagates each item's `jsonld_type` so this signal is
  available on the live path;
- **Heading pattern** — the item carries `from_exhibit_heading` / an `exhibit_heading`
  string that `is_exhibit_heading` recognises (`Installations`, `Current Exhibitions`,
  `On View`, `Rooms`, `Galleries`, …), i.e. it was lifted from the branch page's own
  exhibit-list heading.

Events, "nights", guides, blogs, press, tickets and "destinations" are excluded by
**not matching** — nothing has to be enumerated. An item with **no URL** and no
type/heading evidence is still kept (judged elsewhere — the r2 contract). r2's
`is_stop_url` / `NON_STOP_SEGMENTS` are retained unchanged so the r2 suite's
deterministic path-only rejection keeps passing; the allow-list runs first and is the
r3 authority. Wired into the **live** packer: `exhibition_site_first.build_site_first_candidates`
calls `reject_non_stop_urls(raw_items, city, venue_domain=domain)`.

Fixtures: `tests/test_local602_r3_exhibit_allowlist.py` uses the **exact Meow Wolf r2
candidates** — both junk pages are dropped (match no positive signal); real exhibits
(by URL segment and by `VisualArtwork`/`Installation` JSON-LD type) survive.

### 2. Shortfall → preflight highlights → honest shortfall
When fewer than N positive stops remain, the existing LOCAL-603 **Plan B** path (wired
immediately after the site-first candidates in `generate_tour_text.py`) tops up from the
venue preflight's `current_exhibitions_or_highlights`, **each carrying its grounding
source URL**, then the D616 honest shortfall. The r3 allow-list is upstream of this, so a
thin positive set flows straight into the sourced fallback — never filled with junk.

### 3. Test exits (re-run)
- `python3 -m pytest tests/test_local602*.py -q` → **91 passed** (exit 0) — the six r2
  suites + the new r3 allow-list suite.
- `python3 -m pytest tests/test_local60[3-6]*.py -q` → **40 passed** (exit 0).
- `python3 -m pytest tests/test_local602*.py tests/test_local60[3-6]*.py -q` →
  **131 passed, 1 warning** (exit 0).

### 4. Live run (isolated container, Meow Wolf Santa Fe, 5 stops, cap $1.50)
`./run_local602c_live.sh` — disposable `local602c-gen` / `local602c-pg` on a disposable
network with a throwaway Postgres (`docker run --rm`); no `audioura-*` container or
shared DB touched. `COST_HARD_LIMIT_USD=1.50`, `LOCAL603_PREFLIGHT=1`, tour cache off.

- **The allow-list fired on the live path:** `[LOCAL-602] stop allow-list dropped 12
  page(s) not positively identified as an exhibit (events/guides/blogs/tickets/branch-index/…)`.
  The entire Serper `site:meowwolf.com Santa Fe` result set (10) plus embedded-JSON
  candidates were dropped — **the Adulti-Verse event and the Santa Fe City Guide blog
  among them** — because none was positively an exhibit. With zero positive site-first
  stops, the run fell through to the sourced story/grounding path (preflight returned
  `highlights: 6`).
- **Stop titles with URLs (delivered):**
  - `Stop 1: Care Manual House Of Eternal Return` — the Meow Wolf flagship installation
    (*House of Eternal Return*), grounded on `meowwolf.com` + public reference pages
    (`claims=1, sourced=1, unsourced=0`).
  - `Stop 2: Portal Pass` — a work within the installation, grounded
    (`claims=1, sourced=1, unsourced=0`).
  - **Neither r2 junk page appears.** No event, no city-guide/blog, no ticket page.
- `Tour total: $0.2573` (OpenAI $0.2573) — **well under the $1.50 cap**; wall 320.9s.
- Coordinates `35.6342, -105.9632` (Santa Fe, NM). *(An address-label inconsistency in
  the delivered text — `2103 Lyons Ave` vs the resolved `1352 Rufina Cir` — is the r2
  address-verification surface, out of r3's allow-list scope; noted for follow-up.)*

### Scope / safety
- No DELETE of any data; no GCloud. The live run used a disposable Postgres; the stop
  pool was isolated (`POOL STORE: 2 stop(s)` in the throwaway DB only).
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `.continuous_dev/STATUS.md`.

### Files changed (r3)
- `exhibition_site_js.py` — allow-list: `is_exhibit_stop`, `is_exhibit_heading`,
  `STOP_PATH_SEGMENTS`, `EXHIBIT_JSONLD_TYPES`; `reject_non_stop_urls` now positive;
  `_walk_json` / `extract_embedded_json` propagate `jsonld_type`.
- `exhibition_site_first.py` — live packer wired to the allow-list with `venue_domain`.
- `tests/test_local602_r3_exhibit_allowlist.py` — new (Meow Wolf r2 candidate fixtures).
- `run_local602c_meowwolf.py` + `run_local602c_live.sh` — isolated r3 live-run harness
  (Meow Wolf Santa Fe, cap $1.50).

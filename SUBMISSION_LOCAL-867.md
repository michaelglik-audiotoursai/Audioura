# SUBMISSION — LOCAL-867: import a pasted itinerary (parser + free `/preview-stops`) — D762, server side

**Branch:** `LOCAL-867-import-itinerary` · **Base:** subscribed `90f6b592` — `git merge-base --is-ancestor 90f6b592 HEAD` exits 0.

**Live (Mac-local, own DB, budget-enforced): preview PASS; generation PASS on 10/10 delivered, given order and pins kept; D760 layers PARTIAL (see below). Spend $0.4936 of the $0.50 cap.**

## What changed

| # | File | Change |
|---|------|--------|
| 1 | `itinerary_import.py` (new) | `parse_itinerary(text, city_hint) -> [{name, alt_names, note, url}]`, pure string logic. Splits on `→ ⇒ ➜ -> => > , ; \|` and newlines, plus numbered/bulleted lines (also inline `1) A 2) B`); order kept. URLs, bare `lat,lng` and parentheses are protected first, so the commas in `@10.77,106.69` or in `(bus, boat)` never split. Strips bullets, `Stop 3:` / `Step 3 -` prefixes, keycap numbers and emoji. Keeps `Name + URL` items (LOCAL-852 forms, including the `https___` mangled form). `A/B` and `A & B` become one stop with `alt_names=[B]`; `24/7` is not split. Numbers stay in names (`Café Apartments 42`). Parenthetical text becomes `note`. Headings (`Route:`) and the city's own name are dropped. |
| 2 | `itinerary_import.py` | `preview_stops(text, city)` resolves each stop, cheapest first. **No LLM.** Order: (0) a Maps link pasted with the stop (free); (1) the curated per-city alias + offline landmark table, then Wikidata P625; (2) Nominatim bounded to the city box; (3) at most **one** Serper `/places` per still-unresolved item, with a per-call cap. Every hit must lie within 25 km of the city and pass a name match on the *distinctive* tokens (class words like street/pier/bar/book don't count). A `highway` row is accepted only for a street-type stop. A miss comes back `unresolved` with a reason, never a centroid. The city comes from `city` (via 863R `city_scope.resolve_city_scope`), else from the text, else the call is refused (400). It is never a country. The `CITY_ALIASES` table maps a bare word to the place it means in HCMC ("Cathedral" → Notre-Dame, "Book Street" → Đường sách Nguyễn Văn Bình …). It stores only names to search, never coordinates. The response includes `cost` {llm_calls: 0, serper_places_calls, wikidata_calls, nominatim_calls, usd}. |
| 2 | `generate_tour_text_service.py` | `POST /preview-stops {text, city}`. Gated by `USER_STOPS_ENABLED` (D591; 404 when off). Validates `text` (≤ 8000 chars) and `city`. Serper cap via `PREVIEW_STOPS_MAX_SERPER` (default 10). |
| 3 | `tour_orchestrator_service.py` | `/generate-complete-tour` accepts `user_stops` entries as **objects** from the reviewed preview, mixed with strings. Each object becomes the existing user-stops string `"<name> https://www.google.com/maps/[place/<authority name>/]@lat,lng,18z"`, which the LOCAL-852/859 parser reads as a user pin (`coord_source=user_share_link`). The authority's own name rides in `/place/` as the LOCAL-862 research alias. Every 852/855E/859B/862/863/D760 rule then applies unchanged. Logs `[LOCAL-867] imported N stops (K with a reviewed pin carried, order kept)`. A malformed object is a 400, never a silent drop. Strings-only requests are untouched. Conversion runs only when `USER_STOPS_ENABLED` is on; otherwise D591 drops the field as before. |
| 3 | `itinerary_import.py` | Each generation string is kept ≤ 200 chars, the orchestrator's `sanitize_input` cut. The alias segment is dropped first, then the name is shortened; the coordinate is never cut (found in live run 2, see below). |
| 3 | `generate_tour_text.py` | **Bug fix, user stops on walking tours:** LOCAL-7 `_compute_route_order` re-sequenced a forced stop list, against the LOCAL-357/525 contract "exactly those stops, in order". It never showed before because earlier user-stop runs (Sophia) were biking tours. A per-job flag `_J._KEEP_GIVEN_ORDER` is set and reset in the forced-stops block. `_compute_route_order` honours it, which covers all 7 call sites (the initial pass and the GEO-CHECK/D558/662B leg checks, so walking-leg limits are measured on the route the listener walks). It logs `[LOCAL-867] ROUTE-ORDER skipped`. |
| — | `Dockerfile.orchestrator` | `COPY itinerary_import.py` (the orchestrator image copies modules by name; the generator image already uses `COPY *.py`). |
| — | `run_local867_live.py`, `docker-compose.local867-proof.yml` | Live harness (preview / generate phases) and the own-DB compose (project `local867`, port 55967). |

## Tests (offline)

- `tests/test_local867_itinerary_import.py` (35 tests). Parser: the exact Michael string (10 names, order, `alt_names`, note); a numbered/bulleted list with `Stop 2:` and emoji; inline numbering; a comma/semicolon/pipe list; arrow variants; commas inside parentheses; numbers in names; a **mixed list with links** (share.google, maps.app.goo.gl, website, `/place/…/@lat,lng`); bare `lat,lng`; headings; garbage; 3-way combined. Resolver (injected fakes): city required / city from text; landmark table is free; chain order Wikidata → Nominatim → one Serper; Serper cap; unresolved never a centroid; out-of-city and name-mismatch hits rejected; a generic word doesn't trust a Wikidata hit; link item is free; order kept with an unresolved item in the middle. Plus regressions from live run 1: class words don't identify a place (Book Street ≠ Phương Nam Book City), Book Street → Nguyễn Văn Bình via the alias query, a pier isn't pinned on a road, and `matched_name` round-trips through sanitising.
- `tests/test_local867_orchestrator_and_endpoint.py` (14 tests): endpoint off by default (404); with the kill switch off, preview objects are dropped by D591 with no import log; validation, no-city 400, no LLM client in the module; orchestrator accepts preview objects in order and logs the line; strings unchanged; a bad object is a 400; the pin round-trips through the 852 parser; the **200-char cut** (City Hall case and a 260-char name); an offline **replay of the real live preview** through the intake shows all 10 coordinates arrive verbatim; forced stops keep order in `_compute_route_order`; the flag is set/reset in the forced block.
- Neighbouring suites: every test file touching `forced_stops` / `user_stop` / `_compute_route_order` (28 files) **449 passed, 2 skipped**; walking/route suites (D558, D559, 658, 660, 662, 662B, 734, 790, 824, 838, 522) **193 passed, 4 skipped**.
- Full suite: see "Full suite" below.

## Live — `TASK_BUDGET_ID=LOCAL-867 TASK_BUDGET_USD=0.50`

Own DB (D753): `docker-compose.local867-proof.yml`, project `local867`, port 55967, seeded with `local821-initdb`. Every `DATABASE_URL` / `VENUE_CACHE_DB_URL` / `DB_*` pointed there. The generator ran in-process from this worktree (the 859B/863R pattern); the orchestrator intake ran as the real Flask app (test client). The shared `audioura-*` containers, the shared dev DB and the live DB were not touched.

### 1. `/preview-stops`, Michael's exact string, city "Ho Chi Minh City" — **PASS**

Reference = the real place from an authority *independent* of the resolver's own answer for that stop (OSM object, a separate Google Places query, or the 859B/863R-verified pin).

| # | Typed | Resolved | Source / confidence | Distance to real place |
|---|---|---|---|---|
| 1 | Cathedral | **Notre-Dame Cathedral Basilica of Saigon** | landmark table (Wikidata P625) / high | 15 m |
| 2 | Post Office | **Saigon Central Post Office** | landmark table / high | 5 m |
| 3 | Book Street | **Nguyễn Văn Bình Book Street** (OSM "Đường Sách") | Nominatim / medium | 60 m |
| 4 | Independence Palace | Independence Palace | Wikidata P625 / high | 13 m |
| 5 | War Remnants Museum | War Remnants Museum | Wikidata P625 / high | 34 m |
| 6 | Opera House (alt Đồng Khởi) | Saigon Opera House | landmark table / high | 37 m |
| 7 | City Hall (alt Nguyễn Huệ) | Ho Chi Minh City Hall (People's Committee Building) | landmark table / high | 14 m |
| 8 | Café Apartments 42 | Café Apartments, 42 Nguyễn Huệ | Serper /places / medium | 18 m |
| 9 | Bạch Đằng Pier (note "tour-bus + waterbus") | Bạch Đằng Pier (OSM "Bến tàu Bạch Đằng") | Nominatim / medium | 14 m |
| 10 | Thi Bar | Thi Bar Saigon | Serper /places / medium | 0 m |

- 10 stops, in order; 0 unresolved; city = curated HCMC (10.7769, 106.7009), not the country.
- **Cost per call: $0.004** (2 Serper `/places` × $0.002; 2 Wikidata + 3 Nominatim, free; **0 LLM calls**). The network meter agrees ($0.0040). Target ≤ $0.01 for 10 items: met.

**Live run 1 found two wrong pins, both fixed before the official run.** "Book Street" was matched to *Phương Nam Book City*, a bookshop, on the shared word "book" (~1.6 km off). "Bạch Đằng Pier" was matched to the Tôn Đức Thắng **road**, which carries the old name. The fixes are the distinctive-token matcher, the alias query "Đường sách Nguyễn Văn Bình", and no road rows for non-street stops. Each has a regression test.

### 2. Generate from that preview (10 stops, walking) — 10/10, order, pins **PASS**; D760 **PARTIAL**

Path: saved preview → real orchestrator `/generate-complete-tour` intake (`[LOCAL-867] imported 10 stops (10 with a reviewed pin carried, order kept)`, HTTP 200, 10 forwarded) → generator `validate_stops` → `generate_tour_text(..., 'walking', forced_stops=…)`.

- **10/10 delivered: PASS.**
- **Given order: PASS.** Notre-Dame → Post Office → Book Street → Independence Palace → War Remnants → Opera House → City Hall → Café Apartments → Bạch Đằng Pier → Thi Bar; `[LOCAL-867] ROUTE-ORDER skipped`.
- **Pins kept: PASS.** 9 stops are 0 m from the preview pin. City Hall is 10 m off (see the 200-char finding below). Every delivered pin is ≤ 60 m from the real place. Every pin has `coord_source` user_share_link or user_name_lookup; none are on the centroid. pin_snap skipped all 10 as user pins.
- **D760 layers: PARTIAL.**
  - **Holds:** no legend-style sentence without its disclosure marker; every stop is about its venue; Bạch Đằng Pier had nothing sourced (0 venue snippets) and got the **D760 short form** ("one of the places you chose…"), not invented text; Book Street, Café Apartments and Thi Bar carry layer-2 context (Places category/rating, sourced history).
  - **Does not hold:** Saigon Opera House came out generic and thin: 3 sentences, "known for performances, architectural beauty, historic events", plus a stray "before you go in". The enrichment found only 1 specific, so it wasn't narrated, yet it wasn't given the short form either.
  - **Wrong bridge:** the 862C name bridge gives a wrong layer-2 inference for a person's name. Book Street and Café Apartments both say "probably takes its name from the word 'Nguyen'" plus a surname etymology; Nguyễn Văn Bình is a person, and the café is named after its street address.
  - Both are in the 862/862C enrichment, not in this ticket's code. I did not change them. I'm reporting them for follow-up.

**Live run 2 finding (fixed, verified offline only).** City Hall's title plus its Vietnamese `/place/` alias exceeded the orchestrator's 200-char `sanitize_input` cut. The cut landed at `@10.77647`, the 852 parser saw no coordinate, and the 859 name lookup re-pinned it 10 m away. It still passed, but by luck. The fix keeps every string ≤ 200 chars and never cuts the coordinate. It is **not re-run live**, because the budget was spent. It is proven by a unit test and by an offline replay of the real live preview through the real intake (all 10 coordinates arrive verbatim).

### Budget

Network meter, service `LOCAL-867`: **$0.4936 of $0.50** (OpenAI $0.3656, Serper $0.1280; 571 rows). That breaks down as:
- two preview probes before the harness existed, $0.002 and $0.004;
- 2 Serper reference lookups for the truth table, $0.004;
- the official harness preview, run twice, $0.004 each;
- **two generations**, $0.2289 and $0.2467.

Generation run 1 delivered 10/10 with every pin kept but in route-optimised order. That exposed the LOCAL-7 bug fixed above.

**Budget-enforcement gap I found and closed for run 2 (please read).** My harness first copied 863R and set `K_SERVICE` for a "cloud-like" env. `paid_api_meter._meter_log_cap_armed()` **never arms the LOCAL-827 meter-log cap when `K_SERVICE` is set**. That cap is the only one that stops an in-progress run on non-grounded (OpenAI/Serper) calls; LiveRunMeter's guard sits at the grounding counter, and the JSON ledger is written only at run end. So **preview runs 1–2 and generation run 1 ran with the in-run whole-task cap disarmed.** They stayed inside the budget, but only because they happened to.

For the final preview and generation run 2 the harness unsets `K_SERVICE`, which no generator code reads. It refuses to start without $0.24 headroom and installs LiveRunMeter with the remaining cap. Note that 863R's harness has the same `K_SERVICE` setting.

## Full suite

I ran the full `tests/` suite on HEAD and on an untouched `90f6b592` in a temporary worktree (since removed), then diffed by test ID:
- HEAD: 221 failed + 43 errors / 6580 passed. Base: 230 failed + 43 errors / 6523 passed.
- **New failures on HEAD: 0.** Every HEAD failure also fails on the base.
- 9 tests fail only on base, all environmental:
  - `test_local442…::TestLiveAPIMFACalibration` (5): on base, an earlier test had swapped `OPENAI_API_KEY` for a fake key, so they got 401s;
  - `test_local431::test_mfa_tour_file_counts` and 2× `test_local432` use an untracked tour artefact the fresh worktree lacks;
  - `test_local320::test_dining_does_call_nominatim` is live Nominatim.

**Unmetered spend from the suite (please read).** `TestLiveAPIMFACalibration` is `@pytest.mark.live` and runs whenever `OPENAI_API_KEY` is set, which it is in this shell. On HEAD those 5 tests made **real `gpt-4o-mini` calls**, outside the LOCAL-867 meter (no `PYTHONPATH=_meter` for a suite run). I estimate under $0.01: one paragraph, ~5 calls. I could not measure it exactly. Task total is therefore **$0.4936 metered plus an estimated < $0.01 unmetered**, just inside the $0.50 cap but not provably so. Next time I'll run the suite with `OPENAI_API_KEY` unset, or with `-m "not live"`.

## Limits — what this does NOT prove

- **Pins vs "real place":** the references are OSM objects, separate Google Places queries and earlier verified pins, not a survey. Book Street is a ~150 m pedestrian street, so its 60 m is against Google's point for it.
- **Aliases are HCMC-only.** In other cities the bare-word stops ("Cathedral") rely on Wikidata/Nominatim/Serper by the typed name, with the distinctive-token matcher. A city with no alias entry and a generic word may come back `unresolved`, which is announced, never guessed. Each new city needs its own alias rows.
- **The 200-char fix and the final `matched_name` alias segment were not exercised by a second live generation.** Generation run 2 *did* carry `matched_name`, and Bạch Đằng Pier still found 0 venue snippets, so the alias didn't rescue that stop.
- **Container stack:** the orchestrator ran as the real Flask app in-process, and the generator in-process. This was not a full own-container stack. The orchestrator Dockerfile change was not built.
- **App side (D762 client)** is out of scope: no Flutter change.

## Not committed

`_local867_meterlogs/` (run logs, meter JSONL, generation logs) and the generator's own `Ho_Chi_Minh_City__…_walking_tour_*.txt` outputs. Committed artefacts: `submission_artifacts/local867/{preview_michael_hcmc.json, live_tour_10stops_walking.txt, meter_summary.json}`. The own DB was torn down (`down -v`) after the run.

# SUBMISSION — LOCAL-756 (retest round 5)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-756-retest-round5`
**Base:** subscribed @ `aeaae8f9` (`git merge-base --is-ancestor aeaae8f9 HEAD` → 0)
**code_sha:** `eb0af70b4c70d6e1202b303e334c23ccb939598d` (the LOCAL-756 fix commit; this submission note is the follow-up commit on top of it)

Three field regressions from Michael's 2026-10-24 retest are fixed, each with a
red test that fails on `aeaae8f9` and passes after the fix.

---

## A. Salem Witch Museum (4) — exhibit museum on the CACHE-HIT path

**Root cause.** LOCAL-751 shipped the exhibit-museum route but its second chance
only re-admits a CANDIDATE that matches a sourced exhibit name, and only drops
tagged `no canonical match`. On the cache HIT the LLM candidates matched NONE of
the cached exhibit names (`The Trial of George Jacobs`, `City on a Hill`, …), two
were dropped on the theme word `witch`, so 0 verified → tier `unresolvable`. The
cache row also carried the chrome title `Discounts And Discount Partners`, and
the LOCAL-580 site-first path ran with `site=''` though the cache row had
`official_url=https://salemwitchmuseum.com/`.

**Fix (`generate_tour_text.py`, `exhibition_discovery.py`; fail-closed kept):**
1. **A1 — candidate list from the sourced exhibit names.** In `_verify_works_v2`,
   when an exhibit museum has fewer than 2 verified exhibit stops after the
   LOCAL-751 second chance, build the stops directly FROM the sourced exhibit
   names (`_exhibit_names`), junk/chrome-filtered first, method
   `sourced_exhibit_name`. ≥ 2 → tour; < 2 → today's refusal.
2. **A2 — reconsider theme-word drops.** The second chance now also reconsiders a
   candidate the loop dropped as a `theme word` (a witch museum's exhibits
   contain "witch").
3. **A3 — cached `official_url` to site-first.** `_museum_site_url` falls back to
   `_det_cache['official_url']` when the resolver returns an empty URL.
4. **Junk filter.** `exhibition_discovery._CHROME_TOKENS` gains
   `discount/discounts/partner/partners`, so `Discounts And Discount Partners`
   is dropped from the canonical set, the exhibit-name fallback, AND (post-live
   fix) the cached-canonical documented/reserve pool read at both Source-3 loops
   — it can never become a stop on any path.

**Red test — `test_local756_exhibit_cache_hit.py` (3 tests).** The exact field
cache row + the four LLM candidates. GREEN with the fix; on `aeaae8f9` 2 fail
(tier `unresolvable`, 0 verified). LOCAL-751 `test_local751_exhibit_museum.py`
stays 2/2 green.

---

## B. Danvers walking (4) — the stop pool bypassed the named-place rule (D562)

**Root cause.** The pool served the 4 stops stored before LOCAL-751 (tour 736),
so neither the area-parse fix nor `apply_named_place_policy` ran; the Witchcraft
Victims Memorial was silently missing.

**Fix (`stop_pool_orchestrator.py`, `stop_pool_store.py`):**
- `maybe_generate_with_pool` now, right after the `[LOCAL-590] pool` line, calls
  `_pool_covers_named_places(location, pooled_rows)` — it parses the request's
  named places (`area_resolver.extract_named_places_from_clause`) and matches
  them against the pooled titles with the same accent-folded / article-stripped
  matcher the walking path uses. If a named place is absent, the pool must NOT
  serve as-is: it returns `None`, so the caller regenerates and
  `apply_named_place_policy` runs (the named place becomes a verified stop or is
  ANNOUNCED — never silently dropped).
- **pool_version rule.** `get_pool_stops` now selects and returns `pool_version`
  per row; `_pool_has_stale_rows` regenerates when any pooled row is below the
  current `POOL_VERSION`. The pool version is bumped by an additive pool-logic
  offset (`_POOL_LOGIC_BUMP=1` → `POOL_VERSION=42`) that retires only
  `stop_pool` rows, leaving the shared `TOUR_CACHE_VERSION` untouched.
  **Rule chosen:** serve from the pool only when every pooled row is at the
  current `POOL_VERSION`; bump `_POOL_LOGIC_BUMP` whenever a merge changes how a
  pooled tour is DELIVERED.

**Red test — `test_local756_pool_named_place.py` (6 tests).** The exact Danvers
field pool (4 stops, none the memorial). GREEN with the fix; all 6 RED on
`aeaae8f9`. Existing pool suites (`test_local590_orchestrator`,
`test_local590_pool_store`, `test_local644_pool_structured`) 31 pass.

---

## C. Home map / search — community tours show no sign and say "free"

**Root cause.** `/tours-near` returns community tours (716, 733, 735) with
`community_id/community_name/community_visibility`, but `home_screen.dart` never
read `community_name` and the detail said the tour was free.

**Fix (`communities_models.dart`, `home_screen.dart`):**
- Pure helpers on `CommunityRules` (reuse `originLabel`):
  - `homeTourCommunitySign(tour)` → the community name (+ organiser when known),
    empty for a plain Audioura tour.
  - `homeTourPriceLine(tour, isMember:, moneyPriceLabel:)` →
    member → **"Included with membership"**; non-member members-only →
    **"Members only — join <community>"**; public community (D706) →
    **"Community tour — join to download"**; plain tour keeps its money label.
  - `isCommunityTour(tour)`.
- `home_screen.dart` wires the sign + membership price line into all four tour
  surfaces: the list row, the map-carousel row, the single-tour detail sheet
  (also the map-marker tap target), and the multiple-tour dialog rows. A new
  `Set<int> _joinedCommunityIds` (from `/communities/mine`) drives per-tour
  membership via `_isMemberOfTour`.

**Red test — `test/home_community_sign_local756_test.dart` (9 tests).** Member /
non-member members-only / public / plain Audioura. GREEN with the fix; on
`aeaae8f9` the whole file is a compile failure (`CommunityRules` helpers
undefined). `flutter analyze` on `home_screen.dart` is clean (only a pre-existing
unused-field warning).

---

## Tests

| Suite | Result |
|---|---|
| `test_local756_exhibit_cache_hit.py` | 3 pass (2 red on `aeaae8f9`) |
| `test_local756_pool_named_place.py` | 6 pass (6 red on `aeaae8f9`) |
| `test/home_community_sign_local756_test.dart` | 9 pass (compile-red on `aeaae8f9`) |
| LOCAL-751 (`exhibit_museum`, `named_place`, `named_place_delivery`, `area_parse_danvers`) | 24 pass combined |
| Pool regression (`local590_orchestrator`/`pool_store`, `local644`) | 31 pass |
| Broad sweep (tier/580/583/589/590/607/644/751/756) | 88 pass |
| Flutter full suite | 1010 pass / 7 known failures (same files as baseline: `local109_swipe_e2e` network, `storied_compat_screens_404`) — no new failures |

One pre-existing baseline failure, `test_local589_canonical_set_chrome_free.py`
(a LOCAL-653 sibling-title drop), fails on `aeaae8f9` as well — it is **not** a
regression from this change.

---

## Live test (own disposable container only)

`./run_local756_live.sh` → container `local756-gen` (`--rm`, spare port 5156,
`--network development_default`), tour cache/pool toggled per arm, HARD-CAP
`$1.50` via `tests/live_run_meter.py` with a `$0.40` reserve gate, meter log
mounted `-v /Users/micha/Audioura/meterlogs:/meterlogs` and
`PAID_API_LOG=/meterlogs/paid_api_calls.jsonl`. No `audioura-*` container was
touched; image + container removed at the end.

### Delivered stop lists (verbatim)

**SALEMWITCH_FRESH** — id=747, tier `exhibit_museum`, 4 stops, $1.0971:
```
Stop 1: The Witch Trials of 1692
Stop 2: Arresting a Witch
Stop 3: City on a Hill
Stop 4: Discounts And Discount Partners   ← junk leaked via the LOCAL-632 reserve backfill
```

**SALEMWITCH_HIT** (same request, cache HIT) — id=748, tier `exhibit_museum`,
4 stops, $1.0798, built from 7 sourced exhibit names:
```
Stop 1: The Witch Trials of 1692
Stop 2: Arresting a Witch
Stop 3: City on a Hill
Stop 4: Examination of a Witch           ← junk 'Discounts And Discount Partners' CORRECTLY DROPPED
```

Log lines (HIT): `[LOCAL-756] Built exhibit stops from 7 sourced exhibit name(s)
when LLM candidates matched none` → `[D1v2] 8/4 works verified — tier:
exhibit_museum`. The core A fix (generate from the venue's own exhibit names on
the cache path, junk dropped) is proven live.

### Budget / honest status of the remaining arms

- **Spend: $1.594** (openai $0.867 + gemini_tokens $0.0294 + serper $0.075 +
  preflight $0.1084 on the FRESH arm alone, plus the HIT arm) — **over the
  $1.50 cap by $0.094**. Two exhibit-museum tours at ~$1.08 each exhausted the
  budget; the reserve gate then **SKIPPED_CAP** the **DANVERS** and **GARDNER**
  arms. I stopped rather than overspend further.
- **FRESH-path junk fix added POST-live** (both `_det_documented` Source-3 loops
  now chrome-filter the cached canonical titles so `Discounts And Discount
  Partners` never reaches the LOCAL-632 reserve). This is verified by the
  `reject_chrome_titles` unit check and the regression suites, but was **not
  re-run live** because re-running would exceed the budget again. The HIT arm
  already proves the junk is dropped on the cache path.
- **DANVERS (B)** is proven by the 6 red tests; the pool gate is deterministic
  and returns `None` with no paid call when the named place is absent.
  **GARDNER (art regression)** is covered by the regression suites and the prior
  LOCAL-751 live art-museum run; the only art-path change here is the additive
  chrome tokens (regression-tested).

### Rows / safety

- `audio_tours`: **519 → 521** (+2), both `is_test=true`, `lat/lng NULL`
  (ids 747, 748). No `DELETE FROM audio_tours`.
- Danvers pool rows were SEEDED as our own `is_test` rows under our own
  `v42|loc:…` key and **cleaned up** at the end; no shared `stop_pool` row was
  modified or deleted.
- Meter log captured 513 paid-call rows (`service=run_local756_container.py`).

---

## Files

Changed: `generate_tour_text.py`, `exhibition_discovery.py`,
`stop_pool_orchestrator.py`, `stop_pool_store.py`,
`audio_tour_app/lib/services/communities_models.dart`,
`audio_tour_app/lib/screens/home_screen.dart`.

New: `test_local756_exhibit_cache_hit.py`, `test_local756_pool_named_place.py`,
`audio_tour_app/test/home_community_sign_local756_test.dart`,
`run_local756_container.py`, `run_local756_live.sh`, `SUBMISSION_LOCAL-756.md`.

No new Python MODULE was added (all edits are to existing files), so no
Dockerfile `COPY` additions are needed; `Dockerfile.generator`'s `COPY *.py`
already brings in every edited file.

# KIRO_REVIEW_12 — PA museums field test: venue disambiguation + exhibit-museum grounding gaps

**From:** Claude (reviewer) · **To:** Mac Mini Kiro · **Date:** 2026-07-23
**Field test:** two museum tours, 10 stops each, iPhone log `log_iphone_07232026_1710.txt`.
- `National Constitution Center, Philadelphia, PA` → delivered **1 stop** (tour 10)
- `African American Museum, Philadelphia, PA` → **hard fail** ("could not be verified with enough works")

**When done:** report in `KIRO_RESPONSE_12_pa_museum_grounding_gaps.md`, move the
ClickUp task to 🔵 Claude — Review. Work on branch `kiro/round12-museum-grounding`.
Do not merge to storied.

---

## Root-cause summary (from generator logs, verified)

Both failures come from the D1v2 grounding pipeline, which verifies museum stops
against "canonical titles" mined from Wikidata SPARQL (P195/P276 works), the
official site, and Wikipedia. That design works for **art museums with cataloged
collections** (Louvre, MFA) and fails for **exhibit/experience museums** whose
stops are named exhibits, not cataloged artworks.

### Case 1 — National Constitution Center (Q538275): 1/10 stops
- PHASE 3A proposed 10 candidates — **all real exhibits** (Signers' Hall, The
  Story of We the People, Civil War and Reconstruction, …).
- SPARQL found only 3 "works"; Wikipedia extraction (T0a) got **0 canonical
  titles from a 5756-char article** that certainly names the major exhibits.
- Result: `1/10 works verified — tier: medium` → 1-stop tour. Nine real
  exhibits dropped as "no canonical title match".
- Also observed: `REJECTED 'The Second Amendment' — artist article places near
  'tate'` — the "artist" was resolved to *United States Constitution* (P921)
  and the artist-grounding text contaminated verification (Issue 3).

### Case 2 — African American Museum, Philadelphia (Q4689667): clean fail
- The venue resolver **ignored the city**. "African American Museum" is a
  Wikipedia disambiguation page listing 9 museums (Philadelphia's is
  "African American Museum in Philadelphia", aampmuseum.org). The resolver
  matched a generic entity with URL `theaamuseum.org` (the **Dallas** museum's
  domain) and mined the 517-char disambiguation page → 0 titles → tier
  unresolvable → clean fail.
- Even with correct resolution, AAMP would hit the same exhibit-museum gap as
  Case 1.

### What worked (round-11 fixes confirmed in production)
- DB `stops_count = 1` for tour 10 — persistence fix works.
- The clean-fail path returned a proper structured error to the app instead of
  garbage. (The app showing "stops: 10" from the request is the known app-side
  ticket.)

---

## Issue 1 — Venue resolver must disambiguate by city

`venue_resolver.resolve_venue(name, city)` receives the city ("Philadelphia")
but selected Q4689667 anyway.

**Fix:**
1. When resolving, validate the candidate entity's location against the
   requested city: Wikidata P131 (located in admin unit) chain and/or P625
   coordinates vs. the city. Reject candidates that don't match.
2. Before falling back to the bare name, try city-qualified queries/titles:
   `"<name> in <city>"`, `"<name> (<city>)"`, `"<name>, <city>"` (Wikipedia
   naming conventions). For this case: "African American Museum in
   Philadelphia" resolves cleanly.
3. If the Wikipedia page fetched is a disambiguation page (detect via
   `{{disambiguation}}` category or < ~1000 chars with list-of-links shape),
   NEVER mine it as corpus — instead pick the list entry matching the city, or
   fail with a clear log line `[D1v2] DISAMBIGUATION PAGE — city match: <pick>`.

**Acceptance:** `African American Museum, Philadelphia, PA` resolves to the
Philadelphia museum (aampmuseum.org / its QID), and the log shows the
city-validated pick.

## Issue 2 — Exhibit-museum tier: extract exhibit names, don't demand artwork catalogs

For venues that resolve correctly but have few/no SPARQL works (NCC: 3, AAMP:
0), the pipeline needs an exhibit-mining path:

1. **T0a extraction gap:** it extracted 0 titles from NCC's 5756-char Wikipedia
   article. Extend extraction to capture exhibit names: section headers,
   bold/italicized named exhibits, and quoted named installations ("Signers'
   Hall", "The Story of We the People"). Log what was extracted.
2. **Official-site exhibit mining:** fetch the venue site's /exhibits (or
   similar nav link) page and extract exhibit names as canonical titles. The
   infrastructure for site fetching already exists (`_museum_site_content`).
3. **New tier `exhibit_museum`:** when entity is verified but SPARQL works <
   threshold, verify candidates against the mined exhibit-name corpus instead
   of artwork titles. Verified exhibits count as verified stops.
4. **DO NOT loosen hedging rules** beyond what exists: candidates that still
   fail all matching stay dropped or hedged per the existing degradation
   ladder. The decision on whether to allow hedged unverified exhibits to fill
   up to the requested stop count belongs to Michael (ClickUp task in his
   list) — implement the mechanism behind a flag `EXHIBIT_FILL_HEDGED`
   (default off) so it can be enabled by decision, not by code change.

**Acceptance:** NCC 10-stop request yields ≥6 verified exhibit stops with the
flag off; log shows exhibit corpus source (wiki sections + site) per stop.

## Issue 3 — Artist-grounding contamination ("places near 'tate'")

`REJECTED 'The American National Tree' — artist article places near 'tate'`:
the "artist" for NCC exhibits resolved to *United States Constitution*
(P921 main-subject link), and for AAMP the artist was "inferred" as
*African American* from the venue name. Both are nonsense inputs to the
artist-placement check.

**Fix:** the artist-placement rejection must only run when the resolved
"artist" is a person/creator entity (Wikidata P31 = human, or at minimum not
the venue's P921 subject or a substring of the venue name). Otherwise skip the
check and log `[D1v2] artist-check skipped (no valid creator)`.

**Acceptance:** rerun NCC — no `places near 'tate'` rejections; the two
previously rejected exhibits proceed to normal title matching.

---

## Test plan
```bash
cd ~/Audioura
python3 test_sq4_merge.py && python3 test_palais_fix_lead_fixture.py  # stay green
docker compose -f docker-compose-master.yml build tour-generator && docker compose -f docker-compose-master.yml up -d
# regenerate both PA museums (10 stops) and one regression art museum (Palais Lascaris, 6 stops)
# verify: AAMP resolves to Philadelphia; NCC ≥6 stops; Palais unchanged; DB stops_count matches ZIPs
```

# SUBMISSION — LOCAL-850: unresolved-venue drift (Rijksmuseum → Kröller-Müller)

**Branch:** `LOCAL-850-unresolved-venue-drift`
**Base:** subscribed (contains `8e5db189`) — `git merge-base --is-ancestor 8e5db189 HEAD` exits 0.

## The defect

Wave-19 proof (gen 00025-nxb at 8e5db189, cheap env): the request
**"Rijks Museum Amsterdam, Netherlands" (5)** logged
`No Wikidata candidates for 'Rijks Museum Amsterdam, Netherlands'`, then research
drifted to **krollermuller.nl** and delivered 5/5 **Kröller-Müller** works
(Honfleur harbour, Mondrian *Compositie 10*, Dubuffet *Jardin d'émail*, Redon
*Cycloop*, Seurat *Chahut*), pinned in **Honfleur (49.42, 0.23)**. The 5 stops
were pooled under `v41|loc:rijks museum amsterdam netherlands|museum`. A listener
asking for the Rijksmuseum and hearing another museum's works is the worst kind
of error.

## Root cause (three compounding drifts, all fixed)

1. **City glued into the name + spacing.** `_resolve_venue_impl` extracted the
   city from comma segments; for "Rijks Museum Amsterdam, Netherlands" the only
   comma segment was the country "Netherlands" (skipped), so `city=""` and the
   search name was "Rijks Museum Amsterdam" — which matches no Wikidata item
   ("Rijks Museum" spaced ≠ the compact label "Rijksmuseum"). → `resolve_venue`
   returned `None`.
2. **Web-search drift.** On `None`, `discover_official_site` ran a Serper search
   for the venue name and scored homepages. The **Kröller-Müller** museum's Dutch
   name is literally *"Rijksmuseum Kröller-Müller"* (site krollermuller.nl), so
   its homepage title token-matched "rijks" and won — the tour was then built
   from **another museum's** corpus.
3. **Country-centroid geo-disambiguation.** Even once the name resolved, the
   caller passed the city hint as **"Netherlands"** (a country). Geo-disambiguating
   the candidate set against the Netherlands centroid picked the geographically
   central Kröller-Müller (Otterlo), and — when the city was unknown — a
   collection-size reorder picked the Museum Catharijneconvent (Utrecht). Both
   are same-country drifts away from the Rijksmuseum in Amsterdam.

## The fix

### 1. Venue-resolution robustness — `venue_resolver.py`
- **Glued-city recovery** + a curated major-museum-city set (`_GLUED_CITY_NAMES_850`):
  `_split_glued_city("Rijks Museum Amsterdam") → ("Rijks Museum", "Amsterdam")`.
- **Compact-spacing / accent variants** (`_compact_spacing_variants`): "Rijks
  Museum" → "Rijksmuseum"; generic `<Word> Museum` → `<Word>museum`. Wired into
  `_normalise_venue_name`, which now also emits the de-glued name.
- **Country-as-city guard** in `_resolve_venue_impl`: a city that is actually a
  country (`_COUNTRY_WORDS_850`) is discarded (never geo-disambiguated against a
  country centroid), then the real glued city is recovered.
- **Serper knowledge-graph fallback** (`_resolve_via_knowledge_graph`): a last
  resort before giving up that bridges a spelling Wikidata search missed, but
  **only accepts a museum-type entity confirmed in the requested city** — never a
  wrong-city or non-museum entity.
- **`city_hint_from_location(location)`**: returns a real city, never a country;
  used by the callers (below) so geo-disambiguation has the right city.

### 2. HARD anti-drift rule — `venue_resolver.discover_official_site`
`_site_pick_is_other_venue(venue, city, title, url, host)` rejects any discovered
official-site pick that belongs to a DIFFERENT venue, via two independent checks:
- the **venue-identity gate** (`passage_is_other_venue`) catches a named other
  venue (e.g. a "Stedelijk Museum" / "Kröller-Müller Museum" homepage title);
- a **table-free token-superset gate**: the title must share a requested
  distinctive token; if it ADDS distinctive proper tokens we never asked for
  (accent-folded; parenthetical acronyms like "(MAAM)" exempted), it is a
  different venue and is rejected.

On rejection, `discover_official_site` falls through to the parent-org route and,
if nothing passes, returns `found=False`. The callers then take the existing
**clean-fail / refuse** path — a tour for one museum is never built from
another's site, and the pin is never set to another city (no site is returned).

### 3. Pool never seeds an unresolved venue — `stop_pool_store.py` + `generate_tour_text.py`
`store_delivered_tour(..., venue_unresolved=False)`: when `True`, pooling is
skipped entirely (returns 0, logs `[LOCAL-850] pool store SKIPPED`). The main
generator computes `_venue_unresolved = museum tour with no QID and no accepted
official site` and passes it. A RESOLVED site-first venue (MassArt →
maamboston.org, qid='' but resolved) and walking tours still pool as before.

## Tests — `test_local850_unresolved_venue_drift.py` (offline, 26 tests)

- Name variants (Rijks / Van Gogh / Orsay / the Met); `_split_glued_city`;
  `_compact_spacing_variants`.
- `_resolve_venue_impl` resolves **Q190804 (Rijksmuseum)** for the exact failing
  string, recovers the glued city, and NEVER returns a Kröller-Müller entity.
- Country-as-city discarded (no geo against a country); geo re-picks the
  in-city Rijksmuseum even when the collection-size reorder put the
  Catharijneconvent first; `city_hint_from_location` never returns a country.
- Serper knowledge-graph fallback accepts museum+city only (rejects wrong-city,
  non-museum, empty).
- `_site_pick_is_other_venue`: Kröller-Müller drift → rejected; rijksmuseum.nl /
  musee-orsay.fr (accented) / maamboston.org (MAAM) / metmuseum.org → accepted;
  Van Gogh → Stedelijk same-city drift → rejected.
- `discover_official_site` end-to-end: the Kröller-Müller case returns
  `found=False`; a high-scoring other-venue pick is `drift_rejected`.
- `store_delivered_tour(venue_unresolved=True)` writes nothing (returns 0 before
  any DB connection).

**Regression:** `test_local850` (26) + `test_local637_resolver_robustness` +
`test_local828_venue_identity_gate` + `test_local590_pool_store` = **101 passed**;
`test_local661` / `656` / `766` = 40 passed. No regressions.

## Live proof — isolated containers, budget enforced

Harness: `run_local850_live.sh` + `run_local850_container.py`. Own throwaway
`local850-postgres` with **empty** cache tables (no seed — the resolver must
resolve from scratch) and the `audioura-tour-generator` image with the branch
code bind-mounted. **Pool ON**, cheap museum arm, `STORY_PASS_MODEL=gpt-4.1`,
`TASK_BUDGET_ID=LOCAL-850 TASK_BUDGET_USD=0.60` (per-tour ≤ $0.40), dedicated
meter ledger. Never the shared/live DB, never an `audioura-*` container.
Evidence: `reports/local850/live_evidence_summary.txt`, `live_result.json`.

- **Drift fully eliminated and proven.** An early run (before the country-as-city
  fix) delivered **both tours 5/5**: Rijks → **Q190804 Rijksmuseum, Amsterdam**;
  Orsay → **Q23402 Musée d'Orsay**; **no Kröller-Müller works, no Honfleur pin**;
  cost **$0.286 / $0.201** (each ≤ $0.40). After the city-hint fix, resolution is
  **perfectly clean** — only Q190804 and only Q23402 resolve, and the deterministic
  fill proposes the **real Rijksmuseum works** (De Nachtwacht / *The Night Watch*,
  Het melkmeisje / *The Milkmaid*, Het Joodse Bruidje / *The Jewish Bride*, De
  Staalmeesters…), all cleared the gate. No Kröller-Müller, no Catharijneconvent,
  no Honfleur.

- **Environmental blocker on full narration (not a LOCAL-850 defect).** The final
  runs delivered 0/5 stops because the **OpenAI project hit its enforced spend
  limit**. A direct minimal `chat/completions` call returns
  `HTTP 429 insufficient_quota: "Your project has reached its configured enforced
  spend limit."` — independent of this change; it blocks intent/narration/story
  across the board. Metered spend stayed at **$0.24 / $0.60** because almost no
  OpenAI calls succeeded. Full end-to-end narration is gated only by the OpenAI
  account quota; the LOCAL-850 behaviour (correct venue, correct works, no drift,
  no pooling of an unresolved venue) is proven.

## Files changed

- `venue_resolver.py` — glued-city + compact/accent variants, country-as-city
  guard, knowledge-graph fallback, `city_hint_from_location`, `_site_pick_is_other_venue`.
- `generate_tour_text.py` — wire `city_hint_from_location` at the three museum
  resolve sites; compute and pass `venue_unresolved` to the pool store.
- `stop_pool_store.py` — `venue_unresolved` skip in `store_delivered_tour`.
- `test_local850_unresolved_venue_drift.py` — new offline suite.
- `run_local850_live.sh`, `run_local850_container.py` — isolated live harness.
- `reports/local850/` — live evidence.

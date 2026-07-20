# Generic Grounding — Design Brief (brainstorm draft v1)

**Author:** LEAD (Claude) · 2026-07-05 · **Status:** for Michael's review + brainstorm, then tasking
**Problem:** the Chagall pilot works because its sources were hand-wired. Matisse fails because they weren't. Requiring per-venue configuration means configuring every museum on Earth — unacceptable. The pipeline must DISCOVER its sources for any venue (and any tour type), at request time, and cache what it learns.

## Principle

> Nothing is configured per venue. Everything is discovered at runtime, verified, cached, and reused.
> A venue's first tour request pays a few seconds of mining; every later request is nearly free.

## The discovery cascade (all steps venue-agnostic)

**Step 0 — Entity resolution (who/what/where is this venue?)**
Input: user string + city/country ("Musée Matisse, Nice, France").
- Wikidata search API → venue QID, disambiguated by city coordinate (there are TWO Musée Matisse — Nice and Le Cateau-Cambrésis; geo-disambiguation is mandatory).
- From the QID, structured facts fall out for free: `P856 official website`, `P625 coordinates` (kills the fabricated-coordinate bug class permanently), `P571 inception`, country → language.
- Cache: `venue(qid, name_variants, official_url, lat/lng, country, lang)`.

**Step 1 — Source discovery (where do this venue's facts live?)**
- Official site: from Wikidata P856 (no hand-registered URLs, ever). Crawl shallowly from it: follow internal links matching collection|œuvres|works|history|about|story|agenda|exposition (localized keyword list per language), cap ~6 pages.
- Wikipedia: venue article in EN + the venue's LOCAL language (fr for France, it for Italy…) — full text, not intros. Local-language wikis are systematically richer for local institutions; hardcoding "en+fr" was Chagall-lucky, `country→lang` is the generic rule.
- Wikidata works query: `?work wdt:P195 <venueQID>` (collection contains) and `?work wdt:P276 <venueQID>` (located in) → structured canonical works WITH canonical titles in multiple languages. When present, this is the highest-precision source and costs one SPARQL call.
- Artist expansion (museums dedicated to one artist): venue QID → `P547/P800`-linked artist → artist's works filtered by collection=venue. Generic: derived from the graph, not from a name list.

**Step 2 — Canonical entity extraction** (works for museums; POIs/dishes/scenes for other tour types)
From structured sources first (Wikidata labels), then HTML structure (headings, figcaptions, list items), then title-shaped text patterns. Multilingual normalization + EN↔local-language bridging (cheap deterministic translation of candidate names). Output: `{canonical_titles, cycle_names, theme_words}` — the three-set taxonomy, built generically.

**Step 3 — Story mining** (unchanged from wdvrdawbj4, but fed by discovered pages instead of known ones)
Per-page element extraction with source snippets → `story_elements.json`.

**Step 4 — Graceful degradation ladder (this is what "generic" means in practice)**
| Evidence level | Behavior |
|---|---|
| Rich (Chagall): canonical titles + stories | found-mode: verified stops + documented narrative |
| Medium (typical museum): titles, thin stories | verified stops + interpretive narrative (`story_mode: invented`, truth rules intact) |
| Thin (small museum): venue confirmed, few/no titles | fewer stops honestly, or exhibit-level stops from official-site sections; interpretive narration; NO fabricated work names |
| None (venue can't be resolved) | clean failure with a clear reason — the only case that fails |
The invent-fallback path is REQUIRED (Michael's rule: invent only when it cannot be found) — it's the coverage guarantee. Fail-closed remains only for entity resolution, not for storytelling.

**Step 5 — Cache & learn (turns discovery into an asset)**
Postgres: `venue_corpus(qid, urls, canonical_titles, story_elements, fetched_at, ttl)`. First request mines; subsequent requests reuse. Optional seed job pre-mines the world's top-N venues offline. Over time the DB becomes a proprietary grounding asset — a moat, not a maintenance burden.

## Generalization beyond museums
The cascade is type-independent: for walking tours the "canonical entities" are landmarks (Wikidata P131/P625 in-area queries + city articles); restaurants → dishes/history from official site + review-free sources; book/movie tours → scenes/locations from the work's article. Same steps: resolve entity → discover sources → extract canonical entities → mine stories → degrade gracefully → cache.

## What this replaces from Kiro's Matisse suggestions
- ~~"Add museum site to known sites"~~ → Wikidata P856 at runtime.
- ~~"Add known Matisse works to a canonical list"~~ → Wikidata P195/P276 + local-language Wikipedia + official-site crawl.
- "Implement invent-fallback" → yes, but as the bottom of the degradation ladder, not a Matisse-special.
Also: Matisse's "367-char stub" is a symptom of wrong article/language ("Musée Matisse" is ambiguous; fr.wiki "Musée Matisse (Nice)" is substantial) — exactly what Step 0 disambiguation fixes.

## Acceptance test for genericity (proposed)
Three venues never seen by the code, zero config changes: (1) Musée Matisse, Nice; (2) a major non-French museum (e.g. Uffizi, Florence — tests it.wiki + big collection); (3) a small local museum (e.g. Fruitlands Museum, MA — tests the thin-evidence ladder). Each must produce either an honest tour or a clean, explained failure — with `story_mode` ratios and evidence files to audit.

## Open questions for the brainstorm (Michael)
1. Latency budget for first-time venues (mining adds ~5–15s to generation — acceptable? show progress in app?)
2. Seed strategy: pre-mine top venues offline (which list? how many?) vs purely on-demand?
3. Thin-evidence UX: fewer honest stops vs interpretive 10 stops — which default?
4. Non-museum tour types: prioritize which next (walking? book?) for the generic cascade?
5. Cache TTL / refresh policy, and where the venue DB lives (local Postgres now, prod Cloud SQL after M05)?

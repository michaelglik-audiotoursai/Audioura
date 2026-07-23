# Review for Kiro — Part 2 of Storied Release: Full Factual Grounding Pipeline

**Reviewer:** Claude (main dev Mac)
**Subject:** Extend the museum-tour factual grounding/verification system to walking, restaurant, and book/movie categories — the goal is that stories for every category are as trustworthy as museum stories are today, not just structurally similar.
**Status:** Full scope, one document per your request ("let's do all of it as one set"). Internally phased — land and verify each phase before the next, same discipline as the classification fixes. Start now.

---

## Correcting my earlier assessment — it's better than I first said

I initially described restaurant grounding as needing "genuinely new infrastructure — reviews, local press, or a new search+citation system." Having actually read the code, that's wrong. **The search infrastructure already exists and is mostly category-agnostic.** What's genuinely museum-only is much narrower than I first thought. This changes the plan for the better.

### What's already generic, confirmed by reading the code (reuse as-is)

| Component | File | What it does | Museum-specific? |
|---|---|---|---|
| Web search execution | `work_story_searcher.py::_serp_search` | Runs a query against Serper.dev (Google Search) | **No** — generic HTTP call, any query string works |
| Source-quality tiering | `work_story_searcher.py::classify_domain` | Wikipedia→tier1, `.edu`/`.gov`/`.museum`→tier1, curated news-domain list→tier2, reject-lists for UGC/commerce/satire | **Mostly no** — only the last-resort fallback (`_check_wikidata_p856`) touches Wikidata; everything before it (Wikipedia, TLD rules, news-domain list, reject lists) is domain-shape rules that work identically for a restaurant review site or a museum's Wikipedia page |
| Result caching | `work_story_searcher.py::work_stories_get/put` | Keyed cache table for search results | **No** — just needs a category-appropriate cache key (see below) |
| Corroboration framing | `generate_tour_text.py` `[B6]` block (~line 2932) | `documented` → state as fact / `reported` → attribute to source / `legend` → "the story goes that..." / `disputed` → show both sides | **No** — this is exactly the tiered-honesty pattern any category needs; it's written generically already |
| Spine narrative templates | `templates/spine_*.txt` | Chapter structure, hook, human-focused framing | **No** — already built per-category (see `KIRO_REVIEW_02`) |

### What's genuinely museum-specific and does NOT generalize

| Component | File | Why it's museum-only |
|---|---|---|
| Works verification | `generate_tour_text.py::_verify_works_v2`, `fetch_venue_works` | Confirms a *specific artwork* exists at a venue via Wikidata SPARQL — there's no structured "this menu item/chef fact is real" equivalent database for restaurants. Not applicable outside museum. |
| Query synthesis | `work_story_searcher.py::synthesize_queries` | Built around `canonical_title`/`artist` fields — needs a differently-shaped equivalent per category (see Phase work below) |
| Fact-sheet prompt wording | `fact_extractor.py::generate_fact_sheet` | **This is the one that surprised me.** `generate_fact_sheets_parallel()` already accepts a `tour_category` parameter and passes it to `fetch_poi_rag_context()` — so the *context* it fetches may already be category-aware. But the function that turns that context into a fact sheet, `generate_fact_sheet()`, is called *without* `tour_category` and has a hardcoded prompt: `"You are a meticulous museum researcher... exhibit/room... Artist/Creator... medium..."`. This runs unconditionally regardless of category. A restaurant's chef story gets extracted through a prompt written for museum exhibits. |
| Entity/cache key naming | `work_story_searcher.py::normalize_work_key(title, artist)` | Needs a restaurant/neighborhood-shaped equivalent (e.g. `normalize_venue_key(name, city)`) |

**Net effect:** the heavy-lift infrastructure (search execution, source-tiering, caching, honesty framing, narrative templates) is already built and category-agnostic. What's missing per category is: (a) a query-synthesis variant, (b) a category-aware fact-sheet prompt, (c) an entity-key naming convention. That's a meaningfully smaller lift than "build a new grounding system" — closer to "write the category-specific adapters around infrastructure that already exists."

---

## Revised per-category assessment

**Book/movie — still easiest.** Wikipedia already documents real filming locations and book settings extensively (`fetch_venue_narrative_corpus` likely reuses with modest changes, per `KIRO_REVIEW_02`). Query synthesis and fact-sheet prompt both need book/movie-flavored variants, but the underlying search+tier+cache machinery needs no changes at all.

**Restaurant — closer to book/movie than I originally said.** The Wikidata *works-verification* step doesn't apply (no equivalent for restaurants), but that step was never going to be reusable anyway and isn't required for the SERP-based story-finding path — `classify_domain`'s Wikipedia/TLD/news-domain rules don't depend on Wikidata for the common case, only the last-resort fallback does. A restaurant's chef/owner story, notable-customer anecdote, or history can be found the same way a museum's "documented" story elements are found today: synthesize a query ("`<restaurant name>` `<city>` history chef owner"), run it through the existing SERP search, classify domains with the existing tier rules, and apply the existing `documented/reported/legend/disputed` framing. Main new work: query synthesis + fact-sheet prompt, same as book/movie.

**Walking — the entity-resolution problem is real, and it's the main differentiator now.** A neighborhood or corridor is a fuzzier subject than "this restaurant" or "this book." Deciding *what* to search for (which historical society, which local archive, which Wikipedia article — if one even exists for a specific street) needs more judgment than the other two categories. This is the one place I'd still expect genuine extra effort beyond the shared adapter pattern.

---

## Plan — phased, land and verify each before the next

### Phase 0 (do this first, cheap, unblocks everything) — generalize the fact-sheet prompt

Before touching query synthesis for any category, fix the thing that's silently museum-only right now regardless of category: `fact_extractor.py::generate_fact_sheet()`. Add a `tour_category` parameter and a small set of category-specific prompt variants (parallel to how `spine_generator.py` already has 4 template files):

```python
def generate_fact_sheet(poi_name, rag_context, api_key, tour_category='museum'):
    _ROLE_BY_CATEGORY = {
        'museum': "a meticulous museum researcher",
        'restaurant': "a meticulous food and hospitality researcher",
        'walking': "a meticulous local historian",
        'book': "a meticulous literary/film location researcher",
    }
    role = _ROLE_BY_CATEGORY.get(tour_category, _ROLE_BY_CATEGORY['museum'])
    # replace "exhibit/room", "Artist/Creator", "medium" with category-appropriate framing
    ...
```
Wire `tour_category` through from `generate_fact_sheets_parallel()` (it already has the value — it's just not being passed to this one function call). Small, mechanical, and it's the correctness gap most likely to produce visibly wrong output (a "medium: oil on canvas" field on a restaurant fact sheet) if skipped.

**Verify:** generate one museum tour and one restaurant tour, confirm fact sheets read like their own domain, no artistic-medium language leaking into restaurant output.

### Phase 1 — book/movie query synthesis + entity keys

Add a `synthesize_queries`-equivalent for book/movie subjects (query shape: `"<book/film title>" "<location>" filming location OR setting OR inspired`), and an entity key naming convention (e.g. `normalize_subject_key(title, location)`). Reuse `_serp_search`, `classify_domain`, the cache table, and the `[B6]` corroboration wiring unchanged.

**Verify:** generate a real movie-locations tour, confirm the description prompt receives real `[B6]`-style story elements (with `documented`/`reported`/`legend` framing) instead of nothing, and confirm cache hits work on a second run of the same request.

### Phase 2 — restaurant query synthesis + entity keys

Same pattern: `synthesize_queries` variant (query shape: `"<restaurant name>" "<city>" history OR chef OR owner OR founded`), entity key (`name, city`). This is where the Part 1 hedging safety net (`KIRO_REVIEW_02`/`KIRO_REVIEW_03`) gets to start standing down for restaurants that do have found story elements — real corroborated facts get the `documented`/`reported` framing; only genuinely un-sourced claims should still fall back to the generic hedging language.

**Verify:** generate a real restaurant tour for a well-known, findable restaurant. Confirm at least one story element gets found and correctly tiered. Also test an obscure/local restaurant with little web presence — confirm it degrades gracefully to the Phase-1-era hedging safety net rather than erroring out (same posture as `compute_tier()`'s `unresolvable`/`thin` degradation for museums).

### Phase 3 — walking tours

Same infrastructure, but start with the harder question first: what's the actual search subject for "walking tour of Beacon Hill"? Likely candidates: the named district/corridor itself (if it has meaningful web presence), or per-stop entities (individual notable buildings/addresses along the route) rather than one subject for the whole tour. Worth a short spike to decide this before writing the query-synthesis variant, since it affects the entity-key design more than it did for book/restaurant.

**Verify:** same pattern as Phase 1/2, plus explicitly check behavior for a residential/non-notable street (expect graceful degradation to the hedging safety net, not a fabricated "documented" story).

---

## Not doing

- Not touching `_verify_works_v2`/SPARQL works-verification for other categories — it's genuinely museum-specific (Wikidata has no restaurant/neighborhood-menu-item equivalent) and isn't needed for the SERP-based story-finding path this plan uses instead.
- Not building new evidence-tier definitions per category (`rich`/`medium`/`thin`/`unresolvable`) unless Phase 1-3 verification shows the existing ones don't fit — reuse as-is until proven otherwise.

## Sequencing note

Phase 0 is small and should land regardless of how the rest sequences. Phases 1-3 can run across multiple sessions like the Docker work — verify each phase for real (generate an actual tour, read the actual output, don't just confirm the code runs) before starting the next.

# Review for Kiro — Narrative Grounding Gap in Non-Museum Tours

**Reviewer:** Claude (main dev Mac)
**Subject:** Follow-up to `KIRO_REVIEW_01_tour_type_classification.md` — the classification fix routes tours correctly, but non-museum categories have no factual grounding or hedging behind their storytelling
**Two parts:** (1) an immediate safety-net fix — small, land this now, before or alongside the classification fix. (2) a scoped initiative to build real grounding for non-museum categories — bigger, start now, sequence over multiple sessions like the Docker work.

---

## Context — what's already good, so this isn't a rewrite

`KIRO_REVIEW_01` established that the narrative *structure* (spine templates: hook, chapters, human-focused unique angles, climax, cliffhanger) is genuinely well-built for all four categories, not museum-exclusive — `spine_restaurant.txt` already requires "unique_angle must focus on the PEOPLE (chef, owner, family)," `spine_book.txt` already has its own chapter vocabulary. That work doesn't need to be redone.

What's missing is what museum tours have *underneath* that structure: real research and a tiered honesty system so the narrative doesn't just confidently state made-up specifics.

---

## PART 1 — Immediate fix: hedging safety net (land this now)

### The problem, precisely

`generate_tour_text.py` has a hedging mechanism, but it's conditional on a `verified` flag that only museum POIs ever get set:

```python
# line 2829
if not poi.get('verified', True):
    description_prompt += """
CRITICAL HEDGING REQUIREMENT: This artwork's presence at this venue has NOT been independently verified.
You MUST use hedged phrasing for EVERY claim...
"""
```

`poi.get('verified', True)` **defaults to `True`** when the key is absent. Non-museum POIs never go through the verification pipeline (`_verify_works_v2`, gated at line 1861 to `tour_category == 'museum'`), so they never get a `verified` key set at all — meaning this check silently reads as "verified" for every restaurant/walking/book stop, and the hedging text never fires. It's not that non-museum tours get *weaker* hedging — they get **none**, by omission, not by design.

Separately, museum tours have a four-tier honesty system for story elements (`[B6]`, lines 2932-2971): `documented` → state as fact, `reported` → attribute to a source ("According to X..."), `legend` → "the story goes that...", `disputed` → show both sides. This entire system is also gated to `tour_category == 'museum'`. Non-museum tours have no equivalent — the LLM is simply asked to produce a chef/owner story, a notable-customer anecdote, a neighborhood history detail, with no instruction that it should be careful about stating specifics as fact.

### The fix

Add an unconditional (not flag-gated — there's no flag to gate on) hedging block for non-museum categories, right alongside the existing museum-only checks around line 2828. Something like:

```python
# [Grounding safety net] Non-museum categories have no fact-verification pipeline —
# hedge ALL specific factual claims about real people/events, since nothing here
# has been checked against a source, unlike museum tours (which have _verify_works_v2 + [B6]).
if tour_category != 'museum':
    description_prompt += """
IMPORTANT — GROUNDING HONESTY: No fact-checking has been performed on specific claims about
real people, events, or history for this stop. When you include a specific claim
(a named chef/owner, a specific historical event, a notable visitor, a specific date or
incident), use hedged, attributive framing rather than stating it as verified fact:
"local accounts describe...", "the story often told is...", "according to [publication/type
of source]...", "is said to have...". Do NOT invent specific names, dates, or incidents and
present them as confirmed history. General, well-known facts (a neighborhood's founding era,
a cuisine's regional origin, a book's publication year) can be stated plainly — the hedging
requirement is specifically for claims about particular people or particular events tied to
this specific stop, which is where fabrication risk is highest.
"""
```

Adjust the wording to fit house style — the museum hedging block above is the existing precedent to match tone with. The key requirement is that it fires unconditionally for every non-museum category, not behind a flag nothing sets.

### Verify

Generate a restaurant tour and a book tour, and check the actual output text for hedged framing around specific claims (chef names, historical incidents) rather than flat assertions. Check this is not just present in the prompt but actually showing up in generated output — LLMs don't always follow prompt instructions perfectly, so spot-check 2-3 stops per tour type.

### Do this fix regardless of how Part 2 is sequenced

This is cheap, low-risk (prompt text only, no logic change), and directly reduces the fabrication-as-fact risk the classification fix would otherwise introduce the moment it starts routing tours correctly. Land it in the same pass as `KIRO_REVIEW_01`'s fixes, or immediately after — don't ship the classification fix without it.

---

## PART 2 — Scoped initiative: real grounding for non-museum categories

This is bigger. Start it now, but treat it as its own multi-session effort like the Docker investigation, not a single patch.

### What museum tours actually get, that needs a category-appropriate equivalent

| Component | What it does | Museum's source |
|---|---|---|
| Entity resolution | Confirms the venue is a real, identifiable thing | Wikidata QID lookup |
| Works verification | Confirms specific exhibits/artworks really exist there | SPARQL query against Wikidata |
| Narrative corpus | Pulls real source text to ground descriptions in | Official site + Wikipedia (`fetch_venue_narrative_corpus`) |
| Per-work story elements | Real documented anecdotes about specific items | `work_story_searcher.py`, scored by corroboration status |
| Evidence tiers | Degrades gracefully when evidence is thin | `compute_tier()` — rich/medium/thin/unresolvable |

### Assessment by category — these are not equally far from done

**Book/movie tours — closest to reusable, do this one first.** Wikipedia already extensively documents real-world filming locations and book settings ("filming locations," "real places that inspired X" sections are a well-established Wikipedia content pattern). `fetch_venue_narrative_corpus()` already pulls official-site + Wikipedia text for a named entity — the same function, or a close variant, likely works for "the book/film" as the entity instead of "the museum." This could plausibly reuse 70-80% of the existing corpus-fetching code, just pointed at a different kind of subject. Worth prototyping first since it validates the pattern cheaply.

**Walking tours — also plausible with existing infra.** Neighborhoods, historic districts, and notable streets frequently have their own Wikipedia articles and are covered by local historical societies' web content. Likely a similar corpus-fetch approach, though "walking tour of a neighborhood" is a fuzzier entity than "a museum" or "a book" — expect more work in the entity-resolution step (deciding what the actual page/source to fetch even is) than in the fetching itself.

**Restaurants — hardest, plan as a later phase.** Most restaurants, even well-loved ones, don't have Wikidata QIDs or Wikipedia pages — the SPARQL/Wikidata approach museums use doesn't have a real analog here. This needs a genuinely different grounding source: review platforms (Yelp/Google, for aggregate sentiment and specific mentioned anecdotes), local press archives, food-blog coverage, or — more tractable short-term — a "verified web search with mandatory citation" approach (search-tool grounding, requiring the model to cite what it found rather than pulling from an entity-linked knowledge base). This is closer to a new build than an extension of existing code.

### Recommended sequencing

1. **Part 1 (hedging safety net)** — land immediately, covers all categories today.
2. **Book/movie grounding prototype** — reuse/adapt `fetch_venue_narrative_corpus`, cheapest validation of the whole approach.
3. **Walking-tour grounding** — same pattern, more entity-resolution work.
4. **Restaurant grounding** — scope as its own effort once 2-3 prove the pattern; likely needs a different data source entirely, not just a category swap on existing code.

### Open questions for whoever scopes this in detail

- Should evidence tiers (`rich`/`medium`/`thin`/`unresolvable`) be reused as-is for other categories, or does each category need its own tier definitions (e.g., "documented via Yelp reviews" isn't the same evidentiary weight as "documented via SPARQL work count")?
- Is there a review-platform API budget/rate-limit constraint to plan around for the restaurant phase?
- Does `work_story_searcher.py`'s corroboration-status model (`documented`/`reported`/`legend`/`disputed`) generalize cleanly to "customer story" / "historical incident" for restaurants and walking tours, or does it need category-specific status definitions?

Don't answer these now — flagging them so whoever picks up phase 2+ starts with the right questions instead of rediscovering them.

---

## Summary for whoever reads this first

- **Do now, cheap, no dependencies:** Part 1 hedging safety net.
- **Start now, sequence over sessions:** Part 2, book/movie first (cheapest validation), restaurant last (genuinely new data source needed).
- Land Part 1 before or alongside `KIRO_REVIEW_01`'s classification fix — don't let correctly-routed non-museum tours start producing confidently-stated fabrications before the hedging language is in place.

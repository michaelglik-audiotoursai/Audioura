# SUBMISSION LOCAL-425 — Exhibition Tour Cannot Find Works

## Route That Supplied the Works

**Third-party prose extraction via web search** (`prose_llm` path)

The pipeline found the works through this sequence:
1. `extract_exhibition_name` parsed `"Picasso, Miro, Dali: Unbound"` from the full location string
2. `_search_exhibition_url` (Serper, `site:www.mfa.org`) confirmed the exhibition URL: `https://www.mfa.org/exhibition/picasso-miro-dali-unbound`
3. mfa.org returned HTTP 429 — the venue page is temporarily unreachable
4. `_search_exhibition_works_from_web` found a third-party source (`https://airmail.news/arts-intel/events/picasso-miro-dali-unbound`) that describes the exhibition's works
5. `prose_llm_extract_works` extracted 3 works from that page

Source URL (provenance): `https://www.mfa.org/exhibition/picasso-miro-dali-unbound` (confirmed via Serper)
Content source: `https://airmail.news/arts-intel/events/picasso-miro-dali-unbound`

## Live Stop Count

**3 stops**, all from the Unbound exhibition:
- Le Lézard aux plumes d'or (The Lizard with Golden Feathers) — Joan Miró, 1971
- Au Soleil du Plafond — Juan Gris & Pierre Reverdy, 1955
- Moses and Monotheism — Salvador Dalí, 1974

## Log Lines (from live run)

```
[LOCAL-364] Exhibition search term: 'Picasso, Miro, Dali: Unbound'
[LOCAL-364] Venue URL: http://www.mfa.org/
[LOCAL-364] Searching for exhibition 'Picasso, Miro, Dali: Unbound' on http://www.mfa.org
[LOCAL-425] HTTP 429 from http://www.mfa.org/exhibitions — retrying (attempt 1/2)
[LOCAL-425] HTTP 429 from http://www.mfa.org/exhibitions — giving up (attempt 2/2)
[LOCAL-425] Searching: Picasso, Miro, Dali: Unbound site:www.mfa.org
[LOCAL-425] Search hit: https://www.mfa.org/exhibition/picasso-miro-dali-unbound — Picasso, Miró, Dalí: Unbound
[LOCAL-425] Web search found exhibition URL: https://www.mfa.org/exhibition/picasso-miro-dali-unbound
[LOCAL-425] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying (attempt 1/2)
[LOCAL-425] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — giving up (attempt 2/2)
[LOCAL-425] Venue page unreachable — trying third-party sources for works
[LOCAL-425] Searching for exhibition works: "Picasso, Miro, Dali: Unbound" works OR checklist OR objects Museum of Fine Arts, Boston
[LOCAL-425] Skipping (venue domain, likely 429): https://www.mfa.org/exhibition/picasso-miro-dali-unbound
[LOCAL-425] Skipping (shopping/store site): https://mfashop.com/picasso-miro-dali-unbound/...
[LOCAL-425] Trying third-party source: https://exploreboston.com/events/picasso-miro-dali-unbound-opens-at-the-mfa/
[LOCAL-425] Trying third-party source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
[LOCAL-425] ✓ Extracted 3 works from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
[LOCAL-425] ✓ THIRD-PARTY PATH: 3 works
[LOCAL-364] Result: ExhibitionChecklistResult(path=prose_llm, works=3, title='Picasso, Miro, Dali: Unbound', url='https://www.mfa.org/exhibition/picasso-miro-dali-unbound')
[LOCAL-364/368] ✓ PROSE_LLM PATH: 3 works from exhibition page
[D1/LOCAL-372] SKIP D1v2 — stops sourced from exhibition prose_llm
[D1/LOCAL-372] 3 exhibition stop(s) grounded against the venue page
```

## Neutralisation (Red Output)

With `extract_exhibition_name` neutralised (returns full location string) and web search disabled:

```
[LOCAL-364] Exhibition search term: 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
[LOCAL-364] No exhibition listing found on venue site
[LOCAL-362] No works match scope artists in SPARQL/catalogue — falling through to Phase 3A (GPT will use requirements)
NEUTRALISED: FAILED (no text generated) ← expected, confirms fix is necessary
```

The full location string is passed as exhibition name → seed crawling fails (rate limited) →
no web search fallback → creator filter finds 0 works (MFA's Wikidata doesn't cover Picasso/Miro/Dali) →
Phase 3A asks for generic "most iconic" works → D1v2 drops all fabricated candidates → clean fail.

## Palais Control (D302/D326)

```
PALAIS CONTROL: 4 stops
  - Raquel (panneau, fin du XVIe siècle)
  - Basse de violon by Paolo Antonio Testore (Milan, 1696)
  - Guitar by Antonio de Torres (Almeria, 1884)
  - Guitare baroque by Giovanni Tesler (Ancona, 1618)
Dates found: 10 occurrences
PALAIS CONTROL: PASSED (4/4 stops)
```

4/4 stops, dates intact. The exhibition-aware Phase 3A override only activates when
`_exhibition_scope` is set — Palais Lascaris is a whole-venue tour with no exhibition
scope, so it uses the original "most iconic/signature pieces" constraint.

## Changes Made

### exhibition_checklist.py

1. **`extract_exhibition_name(location)`** — Module-scope function that extracts the
   exhibition name from a full location string (e.g., strips "exhibition at MFA, Boston, MA").
   
2. **`_search_exhibition_url(exhibition_name, venue_base_url)`** — Serper web search
   to find the direct exhibition URL on the venue's domain when path-seed crawling fails.
   
3. **`_search_exhibition_works_from_web(exhibition_name, venue_name, venue_base_url)`** —
   When the venue page is unreachable (429), searches for third-party sources (press releases,
   arts news) and extracts works via `prose_llm_extract_works`. Skips the venue domain
   (known to be rate-limiting) and shopping/store sites (irrelevant content).

4. **`_fetch_page` retry with backoff** — Distinguishes 429/5xx (retryable) from 404
   (not retryable). Honors Retry-After header. Max 1 retry to avoid long waits.
   
5. **Rate-limit early-abort** — If the first seed path returns 429, all subsequent seeds
   on the same domain are skipped (they'll all 429 too).

### generate_tour_text.py

1. **Exhibition name extraction** — Uses `extract_exhibition_name` instead of the previous
   regex that failed when intent's venue_name ("Museum of Fine Arts, Boston") didn't match
   the abbreviation in the user's string ("MFA").

2. **Exhibition-aware Phase 3A** — When `_exhibition_scope` is set but deterministic fill
   failed, overrides `_museum_venue_constraint` to ask for works IN THAT EXHIBITION
   specifically, not the venue's "most iconic/signature pieces."

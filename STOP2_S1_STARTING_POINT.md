# Stop 2 — the starting point our technology actually created

Michael's ask, 2026-08-13 (`TOUR_MFA_20260812_2030_MICHAEL_REVIEW.md`, Q3): produce the
stop record the system built for **Moses and Monotheism**, with the `?` fields filled in
by evidence rather than by hand.

Answer: **every one of them is empty. So is `artist`.** Not "we didn't check" — checked
and reproduced below.

---

## 1. The record, as production builds it

This is the literal dict `generate_tour_text.py:8879` hands to `search_stories_for_stop`,
after the LOCAL-419 checklist enrichment at :8859 has run:

```
canonical_title = 'Moses and Monotheism'
english_title   = 'Moses and Monotheism'      <- defaults to canonical_title
artist          = ''
publisher       = ''
credit_line     = ''
medium          = ''
venue_name      = 'Museum of Fine Arts, Boston'
venue_city      = 'Boston'
venue_lang      = 'en'
```

Three fields Michael's template did not list, and their absence matters more than the
empty ones:

```
exhibition_name = <KEY NOT PRESENT>
local_title     = <KEY NOT PRESENT>
collaborator    = <KEY NOT PRESENT>
```

## 2. Why they are empty — two independent causes, both verified

**(a) The MFA page contains exactly one work, and it is not this one.**

`find_exhibition_checklist('https://www.mfa.org', 'Picasso, Miró, Dalí: Unbound')` re-run
2026-08-13 11:5x. Fetch succeeded, exhibition matched at score 1.00, page reached. The
line-pattern extractor found nothing, so the prose-LLM path ran and returned **2 works —
both the same object**:

```
1. Le Lézard aux plumes d'or (The Lizard with Golden Feathers)          — Joan Miró, 1971
     medium      published by Louis Broder, printed by Mourlot Frères, Paris
     publisher   Louis Broder
     credit_line Gift of Boris Fridman
2. Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail) — Joan Miró, 1971
     medium      Illustrated book with 40 color lithographs …; publisher's vellum
     publisher   Louis Broder
     credit_line Gift of Boris Fridman. © Successió Miró / ARS / ADAGP
```

`match_work_for_stop('Moses and Monotheism', works)` → **NO MATCH.**

This explains the whole review in one line. **Stop 1 is the only stop the checklist can
enrich**, because it is the only work the MFA page names — and stop 1 is the stop you
scored 4/5 on stories. Stops 2 and 3 scored 3/5 and 1/5. The quality gap between your
stops is not a writing gap; it is which stop the page happened to name.

Stops 2 and 3 exist because the POI-generation LLM produced them from parametric memory.
Nothing verified them against the venue. That is the same root as D425 — the Hogarth
Press attribution you caught was invented in exactly this vacuum.

**(b) `artist` is never populated on a POI. Ever.**

`poi['artist']` is initialised to `""` at `generate_tour_text.py:4977` and `:8172` and
**is never assigned anywhere in the file** — grep of all 12,679 lines returns only those
two initialisers and read sites. The single path that can fill it is the checklist
enrichment at :8871, which needs a checklist match. No match → no artist, permanently.

So "Salvador Dalí" appears nowhere in the stop record for a stop about Salvador Dalí.

## 3. What that record buys at S2 — 3 queries

```
1. "Moses and Monotheism" Museum of Fine Arts, Boston
2. "Moses and Monotheism" Museum of Fine Arts, Boston history
3. Museum of Fine Arts, Boston  donation history
```

Query 3 is degenerate — the double space is where the donor name should be. It asks the
internet about MFA donations in general.

Not one of the three names a person. There is no query here that could return the Freud
collaboration, the Art et Valeur publisher, or the lambskin etchings. **The material you
marked missing was never searched for.** S3 did not throw it away; S2 never asked.

## 4. The same stop with the facts you supplied — 16 queries

Filling `artist`, `collaborator`, `publisher`, `printer`, `medium`, `credit_line`,
`exhibition_name` and `local_title` from your review:

```
 1. "Moses and Monotheism" Salvador Dalí story visitors Picasso, Miró, Dalí: Unbound
 2. "Moses and Monotheism" Gift of Boris Fridman history story
 3. "Moses and Monotheism" Salvador Dalí
 4. "Moses and Monotheism" history
 5. "Moses and Monotheism" edition lithographs
 6. Art et Valeur S.A. Salvador Dalí
 7. Arts-Litho, Torrents, Wolfensberger workshop history
 8. Boris Fridman collection
 9. Boris Fridman "Moses and Monotheism" donation why
10. Sigmund Freud Salvador Dalí
11. Sigmund Freud Salvador Dalí relationship why collaborated
12. Salvador Dalí "Moses and Monotheism" why created motivation
13. Art et Valeur S.A. Arts-Litho, Torrents, Wolfensberger collaboration
14. livre d'artiste Salvador Dalí
15. "Moïse et le monothéisme" Salvador Dalí
16. Museum of Fine Arts, Boston Salvador Dalí donation history
```

**3 → 16, and the character changes.** Queries 9, 11 and 12 ask *why* — a donor's motive,
why two men worked together, why an artist took this subject. Those are the queries that
can return the 3-sentence emotionally-loaded story you asked for twice in the review. The
production record cannot produce a single one of them.

Note 1 and 2 are the LOCAL-423 query shape — **your own Step 2 framing**, "what story can
be told to visitors of {exhibition} about {work}". Which brings us to:

## 5. LOCAL-423 is dead code in production

`synthesize_queries` reads `stop.get('exhibition_name')` at `work_story_searcher.py:440`
and gates two queries on it (:452). **Neither stop-record construction supplies that key.**
`generate_tour_text.py:8879` omits it entirely; `:9031` reads `_sf_poi.get('exhibition_name','')`
from a POI dict that has no such field. Nothing anywhere assigns it.

The exhibition name *is* known at that moment — it is resolved at `:5479` and used to
fetch the checklist. It is simply never carried into the stop record. Your Step 2 query
shape has been implemented and unreachable since LOCAL-423 landed.

## 6. Where this leaves S2

Three defects, in the order I would fix them:

1. **`exhibition_name` never reaches the stop record.** One-line plumbing, unlocks the two
   queries built from your own framing. Free to verify — S2 is deterministic.
2. **`artist` is never populated except via a checklist match.** Structural: for any stop
   the venue page does not name, the system knows the work's title and nothing else.
3. **The checklist can only ever enrich stops the venue page names** — here, 1 of 3. This
   is the ceiling behind the whole review, and it is not a story-writing problem.

Defect 1 is the S2 bug proper. Defects 2 and 3 are S1 — the stop record is decided before
S2 runs, which is the point the harness was built to make visible.

Reproduce any of this:

```
python3 story_lab.py --state story_lab_state/stop2_prod.json     s2   #  3 queries
python3 story_lab.py --state story_lab_state/stop2_enriched.json s2   # 16 queries
```

Both state files are in `story_lab_state/`. Edit either and re-run — no API calls, no cost.

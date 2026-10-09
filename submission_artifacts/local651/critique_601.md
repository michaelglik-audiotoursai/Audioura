[tool] Reading tour_601.txt:1
[tool] status: Completed
# Courtauld Gallery Audio Tour — Review

**Score: 5.5/10**

A strong opening stop and a solid Seurat close, but the middle stop is a serious defect: it leads with institutional founding history (dates, donations, a building) instead of a work and artist, and reads as dry filler. The conclusion is thin, and there are small factual/narrative wobbles.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "In 1932, the Courtauld Institute of Art embarked on its academic journey, initially housed at 20 Portman Square" | 1 — leads with institutional/accession-style filler (founding date, building, donation) not a work+artist | High |
| 2 | "focused on technical research, emphasizing the conservation and curation of Impressionist and Post-Impressionist works" | 1 — dry institutional content, no artwork or emotional hook for a listener standing there | High |
| 2 | "This visit was more than academic; it influenced the vision for the institution" | 8 — "This visit" refers to nothing prior; sounds invented/garbled, no antecedent | Medium |
| 2 | "consider how this academic foundation has influenced emerging artists such as Seurat" | 8 — Seurat died 1891; he was not influenced by a 1932 institute. Anachronism / invented claim | High |
| 3 | "the first-ever exhibition dedicated to Seurat's seascapes, which opened on 13 February 2026" | 8 — oddly specific future-dated claim that sounds invented for a standing listener | Medium |
| Conclusion | "This tour highlights the innovative exploration of light... as seen in works like Manet's A Bar" | 6 — recap only name-checks Manet, ignores Seurat and stop 2; weak as a real conclusion | Medium |
| 3 | "take a step back... a technique that revolutionized the art world" ... "revolutionized the art world" | 2/style — "art world" repeated 4x across stop 3; light/color legacy point restated | Low |

Note on criteria that are clean: hours and admission are spoken (£9, under-18 free — plausible and correctly stated, no "check the website"); no URLs; the single restaurant offer is the last sentence (intentional, not flagged); stop count is 3 as requested; the Seurat→halls link in stop 2 is the only continuity attempt, not overused.

## Three highest-value code-level improvements

1. **Enforce a "work + artist first" gate on stop generation.** Stop 2 is an institution/building, not an artwork. Add a validation step that rejects or reclassifies any stop whose lead paragraph lacks a named artwork and artist. Institutional history should only pass if it qualifies as a *story* (named people, motive, consequence) — the current founding/donation text is exactly the "dates of accession, budgets, renovations" filler the criteria forbid.

2. **Add a cross-stop temporal/causality sanity check.** The claim that a 1932 institute influenced Seurat (d. 1891) is a hard anachronism. Insert a fact-consistency pass that flags cause→effect sentences where the influencing entity postdates the influenced person's death. Same pass should catch the dangling antecedent "This visit was more than academic" (no visit was ever introduced).

3. **Generate the conclusion from the actual stop list, not a template.** The closing recap only mentions Manet and omits Seurat and the Institute. Build the conclusion by iterating over the real stops that were produced, so every stop is reflected and the summary can't drift from the itinerary.

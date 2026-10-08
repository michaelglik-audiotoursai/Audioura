[tool] Reading tour_496.txt:1
[tool] status: Completed
# Audio Tour Review: Art Institute of Chicago (tour_496.txt)

**Score: 3/10**

## Defects

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "Chicago: a challenge for your taste buds \| Choose Chicago" | 1 (leads with work/artist) — not an artwork; a scraped tourism-board page title | Critical |
| 1 | "While specific artists or works in this exhibit are not detailed" | 1 — no work, no artist, no meaning; empty filler | Critical |
| 1 | "The museum is open Monday, Wednesday, Friday... admission ranges from $32 to $40" | 4 — raw hours/admission dumped as a leftover block before any narration | High |
| 1 | "Select special exhibitions may carry an additional fee (e.g.." | 4 (truncated source leftover) / 8 | High |
| 1 | "m. – 5:00 p.m.; Open Thursday... (Note: Daily from 10:00 a.m... member-only viewing)" | 3/4 — garbled, duplicated hours fragment mid-paragraph | High |
| 1 | General adult admission "$32 to $40 ... seniors are approximately $26" | 8 — factual red flag; actual AIC general adult admission is ~$26–32, not up to $40 | Medium |
| 2 | "After the exposition closed, the massive painting disappeared and is now presumed destroyed." | 2/8 — orphaned sentence; a famous-work story (Cassatt's lost 1893 Modern Woman mural) spliced in with no setup, sounds invented in context | High |
| 2 | "much like the eclectic flavors of Chicago you explored earlier" | 5 — forced callback re-telling Stop 1; weak since Stop 1 had no real content | Medium |
| 2 | "For over 25 years, the Art Institute... had not dedicated an exhibition to a single female artist" | 1 — leads with institutional framing, not Cassatt's work/life/meaning | Medium |
| 3 | "offering a striking juxtaposition to the tender domesticity portrayed in Mary Cassatt's work, which you explored earlier" | 5 — second consecutive stop re-telling the prior stop; callbacks on 2 of 2 later stops | Medium |
| 3 | "made possible through collaboration with Tate Britain and Musée d'Art Moderne de Paris" | 1/8 — leads with loan logistics; near-miss on the "wrong museum" trap (correctly placed, but foregrounds other institutions) | Low |
| All | No spoken conclusion that resolves the tour — final line is restaurant offer | 6 | Medium |
| Tour | 3 stops delivered, 3 requested, but shortness never acknowledged | 7 — minor; count matches | Low |

Note on criterion 6: a conclusion paragraph does exist ("Together, these stops reveal...") and criterion 7 is satisfied ("That's 3 stops in all," count matches request). The restaurant line as the last sentence is intentional house design and is NOT flagged.

## Three Highest-Value Code-Level Improvements

1. **Reject non-artwork stops at ingestion.** Stop 1 is a scraped tourism page ("Chicago: a challenge for your taste buds | Choose Chicago") with a pipe-delimited source title and zero artwork/artist content. Add a validation gate: if a stop's content contains source-title artifacts (` | `, site names like "Choose Chicago") OR the generator emits "specific artists or works... are not detailed," drop the stop and backfill from a real artwork candidate. No stop should ship admitting it has no subject.

2. **Separate the hours/admission field from narration and sanitize it.** Stop 1 contains three overlapping, truncated copies of hours and a cut-off "(e.g.." — classic leftover of raw scraped fields leaking into spoken text. Normalize hours/admission once into a single clean spoken sentence, strip truncated fragments ("e.g..", stray "m. – 5:00 p.m."), and verify the admission figure against a known source (AIC general adult is ~$26–32, not "$32–$40"). Enforce that these facts appear exactly once per tour.

3. **Deduplicate and gate cross-stop callbacks + splice-detection for orphan sentences.** Both Stop 2 and Stop 3 end by re-telling the previous stop ("much like the eclectic flavors," "tender domesticity... you explored earlier") — a callback on every later stop, which trips criterion 5. Cap callbacks at ≤2 per tour and forbid consecutive-stop callbacks. Separately, detect orphaned/non-sequitur sentences ("the massive painting disappeared and is now presumed destroyed") that reference an entity never introduced in the stop, and either expand them into a real story or cut them.

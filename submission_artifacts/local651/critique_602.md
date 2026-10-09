I'll read the tour file now.
[tool] Reading tour_602.txt:1
[tool] status: Completed
# Courtauld Gallery Audio Tour — Editorial Review

**Score: 5/10**

A promising opening and a strong Seurat stop are undercut by a middle "stop" that is dry institutional biography rather than a work, a repeated story, and factual red flags around a dated exhibition and the La Grande Jatte reference.

## Defects

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "Stand near the plaque that marks the founding of the Courtauld Institute" | #1 — leads with institution, not a work/artist; no artwork to view | High |
| 2 | "Conceived as a teaching facility... Courtauld provided the primary endowment and handed over his residence" | #1 — dry institutional filler (endowment, facility, residence transfer) | High |
| 2 | "such as the Manet's A Bar at the Folies-Bergère" | #2 — re-tells Stop 1's work | Medium |
| 3 | "hosting the first-ever exhibition dedicated solely to Seurat's seascapes, opening on 13 February 2026" | #8 — future-dated event spoken as past history; sounds invented | High |
| 3 | "A Sunday Afternoon on the Island of La Grande Jatte, which altered the direction of modern art" | #8 — La Grande Jatte is at the Art Institute of Chicago, not Courtauld; risks listener confusion though not claimed as present | Medium |
| 2 | "consider how another artist might have approached capturing the world with a scientific lens" | #5 — awkward forward-tease seam, clumsy inter-stop linkage | Low |
| 3 | "Seurat's works later found a new home at The Courtauld Gallery" | #1 — drifts from the work into provenance/institutional padding at stop's end | Low |
| — | "The museum is open Monday to Sunday from 10:00 to 18:00. Admission is 9 pounds for adults" | #3/#8 — hours/admission spoken (good), but Courtauld adult admission is ~£12 off-peak / higher, not £9; verify | Medium |

Note on criteria that PASS: hours and admission are spoken, not deferred to a website (#3 ✓); no URLs or source lists (#4 ✓); the single restaurant offer is the last sentence only (#5 ✓); a genuine conclusion exists (#6 ✓); 3 stops delivered as requested (#7 ✓ — short by request, no explanation needed).

## Three Highest-Value Code-Level Improvements

1. **Enforce a "work + artist required" gate per stop.** Stop 2 has no artwork — it's a building/benefactor biography. The generator should validate that every stop references a specific artwork and artist as its lead subject, and reclassify pure institutional/provenance content as filler unless it carries a named-person story with motive and consequence. Reject or regenerate stops that fail the gate.

2. **Add a temporal sanity check on dated claims.** "Opening on 13 February 2026" is spoken as settled history but is a future date relative to tour generation. Validate every explicit date in narration against the generation timestamp and flag/strip future events presented in past tense — these read as invented and erode listener trust.

3. **De-duplicate story subjects across stops.** Stop 2 re-tells Stop 1's Manet painting as an example. Maintain a per-tour ledger of works/stories already narrated and block re-mention except as brief, intentional continuity callbacks — not as a stop's substantive content. This also prevents the La Grande Jatte digression from pulling focus onto a work that isn't even in this gallery.

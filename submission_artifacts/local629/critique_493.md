I'll read the tour file first.
[tool] Reading tour_493.txt:1
[tool] status: Completed
# Audio-Tour Review: Musée de l'Orangerie (tour_493)

**Score: 6.5/10**

A competent, atmospheric tour with strong work-and-artist leads at Stops 1 and 2. It is dragged down by a repeated "entering the public collection / national collections" provenance beat, dry accession-date filler, a near-universal Monet-linking tic, and a conclusion that summarizes the theme but never acknowledges the short (3-stop) length.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "This act transitioned the artwork from private ownership into the public domain" | 1 — dry institutional filler, and vague (no named person/motive/consequence) | Medium |
| 2 | "This act transitioned the artwork from private ownership" | 8 — "This act" has no antecedent; a sentence about the transfer appears deleted/orphaned | Medium |
| 3 | "In 1963, 'Red Boats at Argenteuil' entered the French national collections" | 1 — accession-date filler, led with instead of the work's meaning | Medium |
| 3 | "entered the French national collections" vs Stop 2 "transitioned...into the public domain" | 2 — same acquisition/public-collection story beat repeated | Medium |
| 2 | "aligning with the vision Claude Monet had for the venue" | 5 — Monet-linking on nearly every stop (also Stops 1 & 3), approaching a tic | Low |
| 3 | "The Orangerie, originally built to store citrus trees, now holds this piece" | 1 — institutional/building aside, minor filler | Low |
| 3 | "That's 3 stops in all." | 7 — states count but never explains/acknowledges the short tour as by-request | Low |
| 1–3 | (overall) | 6 — conclusion restates theme but gives no real send-off or closure of the listener's walk | Low |

Notes: No URLs or "check the website" (criterion 4 clean). No hours/admission attempted either way (criterion 3 — not promised, so not penalized, but nothing spoken). Restaurant offer is the final sentence only — intentional house design, not flagged (criterion 5). No factual claims that read as invented beyond the orphaned "This act" sentence.

## Three highest-value code-level improvements

1. **Suppress accession/provenance boilerplate unless it carries a named human story.** Stops 2 and 3 both default to a "work entered the public collection" sentence. Add a generation/template rule: provenance is admissible only when it names people + motive + consequence (theft, bequest, rescue); otherwise drop it. This single rule removes the Stop-2 filler, the Stop-3 "In 1963…" lead, and the criterion-2 repetition at once.

2. **Dedupe story *beats*, not just stops.** The repeated "public domain / national collections" acquisition arc shows the no-repeat check only compares surface facts, not narrative types. Tag each stop's content with a beat label (acquisition, provenance, technique, biography) and reject a second stop that leads with an already-used beat.

3. **Cap and validate cross-stop linking + fix orphaned references.** Monet-linking fires on all three stops (tic risk), and Stop 2's "This act" has no antecedent — a sign a prior sentence was stripped without integrity-checking the paragraph. Add (a) a limit of ~2 explicit back-links per tour, and (b) a dangling-reference check that flags demonstratives ("This act," "this positioning") lacking a resolvable antecedent after field-line removal.

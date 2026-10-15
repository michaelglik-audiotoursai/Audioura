[tool] Reading tour_702.txt:1
[tool] status: Completed
# Audio Tour Review: Mauritshuis (tour_702.txt)

## Score: 4/10

## Defects

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "an artist signed his work with the monogram 'RHL 1631'... an oil painting by rembrandt" then "De Gelder's choice... Arent de Gelder" | 8 — attribution contradiction/invented | Critical |
| 2 | "reminiscent of the sackbut you stopped at a moment ago" | 5 — leftover from another tour (no sackbut stop exists) | Critical |
| 2 | "unlike Rembrandt's later unfinished depiction in 1669" | 8 — conflates two different artists/works, factually garbled | High |
| 1 | "her figure almost life-sized on the 112.5 x 99.5 cm canvas" | 1 — dry catalog spec (dimensions as filler) | Low |
| 2 | "an oil on canvas measuring 94.5 by 107.5 cm" | 1 — dry catalog spec; also panel vs canvas contradiction | Low |
| — | (no hours or admission stated anywhere) | 3 — spoken hours/admission missing entirely | High |
| 2 | "setting it apart from other portrayals and anchoring it in the architectural context of its time" | 1 — hollow filler phrasing, no real content | Low |

Notes on criteria that PASS: Stop count (2) matches the request — short by design, acceptable. The restaurant offer is the last sentence only (intentional, not flagged). No URLs or source lists. The closing paragraph is a genuine conclusion tying the two works together (criterion 6 met). No repeated story across stops.

## Key Issue
Stop 2 is factually broken. It opens attributing the painting to Rembrandt ("RHL 1631" is Rembrandt's monogram, Rembrandt Harmenszoon Leidensis), then mid-stop silently switches to crediting Arent de Gelder. These are two different painters and two different works. *Het loflied van Simeon* (1631, panel) at the Mauritshuis is **Rembrandt's**; de Gelder's *Simeon's Song of Praise* is a separate later painting. The narration fuses them into one incoherent attribution — the single most damaging flaw. The "sackbut you stopped at a moment ago" is a hallucinated cross-reference to a stop that does not exist in this tour.

## Top 3 Code-Level Improvements

1. **Enforce single-artist attribution per stop.** Add a validation pass that extracts all artist names mentioned in a stop's narration and fails/regenerates if more than one primary attribution appears (here: Rembrandt vs. de Gelder). The generator is clearly merging source records for two distinct paintings sharing a title/subject — key artwork records by stable artwork ID, not by title string.

2. **Strip cross-stop references that have no antecedent.** The "sackbut you stopped at a moment ago" line is a leftover from a different (music/instrument) tour. Add a continuity check that resolves every "you stopped at / earlier / a moment ago" reference against the actual preceding stops in *this* tour, and drop or regenerate any that don't match.

3. **Make hours and admission a required, spoken template slot.** No pricing or opening hours appear at all. Add a mandatory conclusion field that injects the venue's actual spoken hours and admission (e.g. Mauritshuis €17.50 adult / free under 18, open daily), validated to contain a currency figure and never the phrase "check the website."

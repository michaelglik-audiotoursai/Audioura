I'll read the tour file first.
[tool] Reading tour_535.txt:1
[tool] status: Completed
# Audio-Tour Review: Pinakothek der Moderne (tour_535.txt)

**Score: 6.5/10**

A genuinely strong art-first tour: each stop leads with the work, artist, and emotional content, hours and admission are spoken correctly, and there are no URLs or restaurant leftovers mid-tour. It loses points for two institutional-filler insertions, a weak conclusion that only references one of three stops, and a thin provenance line that reads as dry rather than a real story.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "took a decade to finish due to bureaucratic objections to its design and cost." | 1 (dry institutional filler — construction/budget) | Medium |
| 3 | "Flechtheim... loaned this painting to the Museum of Modern Art in New York in 1931" | 1 (near-dry provenance — named dealer but no motive/consequence; also a loan-date fact, not a story) | Low–Medium |
| 3 | "This tour explores the interplay... as seen in works like 'Mädchen unter Bäumen.'" | 6 (weak conclusion — only recaps Stop 1, ignores Stops 2 & 3) | Medium |
| — | (no spoken explanation that 3 stops is by listener request) | 7 ("That's 3 stops in all" states count but doesn't frame it as requested) | Low |
| 2 | "In the late summer of 1929, Dalí... met his future muse and partner, Gala" | 8 (minor factual soft-flag: Dalí met Gala summer 1929 — defensible, but "future partner" framing is loose) | Low |

Notes on what is NOT a defect: the single restaurant offer as the final sentence is intentional house design (correctly placed). No story is repeated across stops. The Stop-3 link back to Stop 1 is light continuity, not over-linking. Admission (10 euros adults, under-18 free) and hours are spoken, which satisfies criterion 3. The three works — Macke's *Mädchen unter Bäumen*, Dalí's *Das Rätsel der Begierde*, and Klee's *Grenzen des Verstandes* — are all plausibly held by the Pinakothek der Moderne / Bayerische Staatsgemäldesammlungen, so no cross-museum red flag.

### Three highest-value code-level improvements

1. **Suppress institutional-filler sentences in the generator.** The Stop-1 building-construction line ("took a decade to finish due to bureaucratic objections to its design and cost") is the clearest criterion-1 defect. Add a post-generation filter that drops sentences matching institutional-filler patterns (construction/renovation/budget/accession/bureaucratic) unless they contain a named person + motive + consequence, so loans and budgets don't leak into narration.

2. **Make the conclusion aggregate all stops, not just the first.** The closing paragraph only cites Stop 1. Change the conclusion template to synthesize the actual artists/works visited (Macke, Dalí, Klee) into the shared theme, so the recap scales with stop count instead of hard-referencing one work.

3. **Add a spoken short-tour acknowledgment tied to the requested count.** "That's 3 stops in all" states the number but doesn't frame it as the listener's request. Inject a one-line template ("As you requested, this was a focused three-stop tour") so criterion 7 is satisfied explicitly rather than inferred.

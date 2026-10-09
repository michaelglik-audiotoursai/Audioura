I'll read the tour file first.
[tool] Reading tour_528.txt:1
[tool] status: Completed
# Frick Collection Tour Review — Score: 7/10

A solid, art-forward tour. All three works genuinely hang at the Frick, the narration leads with work and artist, hours and admission are spoken, and there are no URLs or source lists. It loses points for mid-tour institutional filler (Frick didn't own this / expanding American narrative), a garbled factual passage in Stop 3, a conclusion that forgets Stop 3's artist, no explicit acknowledgment of the short stop count, and continuity-linking that leans slightly repetitive at the end.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "By bringing this artwork to an American audience, Frick expanded the narrative of Holbein's influence on portraiture." | 1 (institutional filler, not a named-people story) | Low |
| 2 | "Although Henry Clay Frick…never owned this particular canvas. Since then, the painting has become a celebrated part…" | 1 (dry institutional/provenance filler mid-tour) | Medium |
| 3 | "highlighting the map on the wall behind them, crafted. van Berckenrode." | 8 (garbled/broken clause — reads as invented/corrupt text) | High |
| 3 | "the woman's yellow dress" / "a young woman in a yellow dress" | 8 (factual red flag — the dress in Officer and Laughing Girl is black/dark with a yellow-trimmed bodice, not yellow) | Medium |
| 3 | "This tour highlights…how artists like Holbein and Ingres capture the essence…" | 6 (conclusion omits Vermeer, the stop you're standing at) | Medium |
| 3 | "Much like the Comtesse, the young woman here is poised and engaged…consider how both Vermeer and Ingres…" | 5 (continuity link back to Stop 2 — acceptable once, but re-states Stop 2's framing) | Low |
| — | "That's 3 stops in all." | 7 (short count stated but never explained as by-request) | Low |
| 2 | "Louise de Broglie sat for an initial oil version begun in 1842… leaving the 1842 painting unfinished." | 1/8 (the Frick canvas was completed 1845; the "unfinished 1842 version" detail risks confusing which work hangs here) | Low |

## Three highest-value code-level improvements

1. **Fix the text-assembly/templating bug producing the garbled Vermeer clause.** `"highlighting the map on the wall behind them, crafted. van Berckenrode."` is a broken concatenation (dangling "crafted." + orphaned attribution). This is the single worst listener-facing defect and points to a sentence-stitching or truncation fault in generation — add a post-generation validator that flags dangling fragments, orphaned proper nouns, and sentences ending mid-clause.

2. **Add a provenance/institutional-filler filter that keeps only *story* provenance.** Stop 1's "American audience" line and Stop 2's "Frick never owned this…celebrated part of the collection" are exactly the dry institutional padding the criteria penalize. Gate provenance content on a "named person + motive + consequence" test; drop accession/collection-status sentences that lack a human story.

3. **Make the conclusion generator enumerate the actual artists/stops in the tour.** The closing names only Holbein and Ingres and silently drops Vermeer (Stop 3). Build the conclusion from the live stop list, and inject a one-clause acknowledgment of the requested stop count (e.g., "the three stops you asked for") to satisfy criterion 7.

No files were modified.

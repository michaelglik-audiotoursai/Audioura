I'll read the tour file first.
[tool] Reading tour_516.txt:1
[tool] status: Completed
# Audio Tour Review: National Gallery, London (tour_516.txt)

**Score: 4/10**

The three works are all genuinely at the National Gallery, and the Caravaggio stop is strong. But the tour is dragged down by dry provenance filler leading a stop, a dangling reference to a painting (Rokeby Venus) that it never actually opens properly, phantom cross-references to stops that don't exist in this tour, hours spoken but admission entirely missing, and a confused, factually-shaky conclusion that credits Vigée Le Brun with influencing Caravaggio.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "Mattei paid 150 scudi for this work... a significant investment at the time." | 1 (price/provenance detail dominates the opening paragraph as dry financial filler) | Minor |
| 2 | "echoing the themes of self-portraiture seen in works like the Self Portrait in a Straw Hat, which you have already encountered on your journey." | 5 (leftover: references a Vigée Le Brun self-portrait stop that doesn't exist in this 3-stop tour) | Major |
| 2 | "a mirror held by Cupid... as a sophisticated exploration of perception and beauty." | 1 (opening leads with pose/mirror but gives little on meaning, reception, or Velázquez's life at that moment) | Minor |
| 3 | "echoes the earlier influence of artists like Vigée Le Brun, who similarly focused on the interplay of light" | 5 / 8 (phantom cross-ref to a non-existent stop; invented stylistic link between Constable and Vigée Le Brun) | Major |
| 3 | "This decision resulted in the painting receiving a gold medal from King Charles X" | 8 ("This decision" has no antecedent — opening sentence refers to context never given) | Major |
| 3 | "Arrowsmith took the works to France and displayed The Hay Wain at the Paris Salon." | 1 (tacked-on dealer/logistics fragment, orphaned at paragraph end) | Minor |
| Conclusion | "Vigée Le Brun's influence... resonates through the works of Caravaggio, Velázquez, and Constable." | 6 / 8 (false conclusion: Vigée Le Brun did not influence Caravaggio, who died ~150 years before her birth) | Critical |
| All | Hours spoken ("10:00 to 6:00") but no admission price anywhere | 3 (admission not spoken at all) | Major |
| 1 | "The Supper at Emmaus" header appears, then hours block, then the intro — ordering noise | — (structural) | Minor |

**Note on criterion 7:** 3 stops were requested and 3 delivered — correct count, no explanation needed. The closing restaurant offer is the intended final sentence and is not flagged.

## Three highest-value code-level improvements

1. **Kill phantom cross-references to stops not in the itinerary.** Both Stop 2 and Stop 3 cite a Vigée Le Brun "Self Portrait in a Straw Hat" stop and "works you have already encountered" that were never generated. The linking logic is pulling from a template/persona pool ("this tour highlights Vigée Le Brun") rather than the actual selected stop list. Gate all "you have already seen / earlier stop" references against the concrete ordered itinerary, and drop any whose target isn't present.

2. **Validate cross-artist influence claims against chronology before emitting them.** The conclusion asserts Vigée Le Brun (1755–1842) influenced Caravaggio (d. 1610) — an impossible, invented link that also contaminates Stop 3. Add a sanity check that any "X influenced Y" statement has X's active period preceding Y's, and strip influence claims that fail it rather than generating them narratively.

3. **Fix orphaned opening sentences and surface admission.** Stop 3 opens its history paragraph with "This decision resulted in..." with no prior "decision" referenced — the antecedent sentence was dropped, leaving a broken reference; ensure paragraph assembly preserves the sentence that introduces each pronoun/demonstrative. Separately, the admission price is never spoken even though hours are (criterion 3) — the template emits hours but has no admission slot filled, so add a spoken admission line (the National Gallery's permanent collection is free, which should be stated outright).

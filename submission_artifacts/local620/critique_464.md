[tool] Reading tour_464.txt:1
[tool] status: Completed
# McMullen Museum of Art — Audio Tour Review

**Score: 5.5/10**

As a listener standing in the gallery, this tour has moments of real power (the Caravaggio and Pollock stops carry genuine drama and story), but it leans heavily on institutional/curatorial filler — who organized the exhibition, catalog page counts, departmental collaborations — instead of leading with the WORK. Stop 1 is almost entirely empty verbiage with no artist named. Admission is spoken (good), hours are spoken (good), and the restaurant offer is correctly placed last. But a recurring "as you saw earlier" cross-reference device creeps toward repetition, and several claims drift.

## Defect Table

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "Paris Along the Seine is now accessible to a broader audience, providing a unique opportunity for visitors to engage" | 1 (no artist, no work meaning, pure filler) | High |
| 1 | "exploring the evolution of art through diverse exhibitions and showcasing groundbreaking techniques" | 1 (empty orientation boilerplate) | Medium |
| 2 | "collaborative effort between the McMullen... Jesuit Community... National Gallery of Ireland led to a historic exhibition" | 1 (institutional framing precedes the work) | Low |
| 3 | "co-edited the 413-page exhibition catalog with Hoffman" | 1 (dry institutional filler — catalog page count) | High |
| 3 | "The exhibition changed the landscape of historical scholarship... museum's growing influence in ancient studies" | 1 (institutional self-promotion, not the work) | Medium |
| 3 | "much like the Caravaggio's interplay of light and narrative you saw earlier" | 2/5 (mid-tour recap of prior stop) | Medium |
| 4 | "drawing together the expertise of university faculty from the romance languages, art history, and theology departments" | 1 (dry institutional/departmental filler) | Medium |
| 5 | "distinct from the carnal intensity evident in Caravaggio's imagery you admired earlier" | 2/5 (recap of earlier stop) | Medium |
| 5 | "Unlike the retrospective on Roberto Matta you visited earlier... contemplatively dissected surreal dreams" | 2 (second recap in same stop) | Medium |
| 5 | "In 2002, Alex Matter discovered a cache... In 2002, an extraordinary find emerged when Alex Matter unearthed a trove" | 2 (same story told twice within one stop) | High |
| 2 | "After fleeing Milan due to a violent altercation, he arrived in Rome destitute" | 8 (Caravaggio left Milan ~1592; "fleeing due to violent altercation" is dubious/conflated) | Medium |
| 1 | (no named artist anywhere in Stop 1) | 8 (work presented with no creator — sounds like a placeholder) | High |
| End | "That's 5 stops in all." | 6 (tally tacked on; conclusion is generic theme-restatement, not a real send-off) | Low |
| — | Stop count = 5, no requested count stated or explained | 7 (cannot confirm; no reconciliation present) | Low |

Positive notes (not defects): hours and admission are spoken (criterion 3 ✓); no URLs or source lists in narration (criterion 4 ✓); the single restaurant offer is the very last sentence (criterion 5 — intentional, not flagged).

## Three Highest-Value Code-Level Improvements

1. **Enforce a "work-and-artist-first" opening per stop; demote exhibition logistics.** The generator is leading paragraphs with *who organized the show* ("In 2011, the McMullen Museum organized...", "In 2004, the McMullen Museum organized..."). Reorder the content template so the first 1–2 sentences name the artist and describe what the work shows and means; move any exhibition-organization sentence to the end or drop it. Stop 1 is the critical failure — it names no artist and no concrete subject at all, suggesting the data-fetch for that work returned empty and the template filled with boilerplate. Add a validation gate: reject/regenerate any stop whose body lacks a named artist or a concrete description of the depicted work.

2. **Add a cross-stop dedup + anti-recap filter.** Two problems share one root: (a) the "as you saw earlier / unlike the Matta retrospective" connective device fires on nearly every stop (criterion 2/5 violations), and (b) Stop 5 narrates the Alex Matter discovery story *twice* in the same stop. Implement a story-signature check (artist + event + key entities) that blocks reuse across and within stops, and strip mid-tour back-references to prior stops unless they add new information.

3. **Strip institutional filler via a defect-term blocklist.** Phrases like "413-page exhibition catalog," "enhancing its reputation as an institution," "museum's growing influence," and "university faculty from the romance languages, art history, and theology departments" are exactly the dry accession/budget/renovation class of defect. Add a post-generation lint pass that flags catalog page counts, reputation/institutional-prestige language, and departmental-collaboration boilerplate, then rewrites toward the artist's life, the work's meaning, or a genuine named-person provenance story (as Stop 5's Alex Matter hoard and Stop 2's Dublin loan nearly achieve).

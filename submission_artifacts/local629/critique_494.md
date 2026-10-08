I'll read the tour file first.
[tool] Reading tour_494.txt:1
[tool] status: Completed
# Belvedere Museum Tour Review

**Score: 6.5 / 10**

A competent, work-led tour with real emotional content and a genuine conclusion. It is dragged down by a recurring "life/death/nature" theme that collapses into cross-stop repetition, two spoken hours/admission omissions (criterion 3 never addressed at all), and some thin or questionable factual claims.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "contrasting sharply with the serene landscapes you encountered in Raphael's Madonna del Prato previously" | 5 (continuity) — acceptable once, but it then re-tells the Madonna in detail | Low |
| 2 | "the delicate yet powerful dialogue between sacredness and earthiness found in the earlier Madonna scene" | 2 (story repeated) — re-narrates Stop 1's content, not a brief link | Medium |
| 3 | "echoing the intertwined themes of life and death found in other works you have encountered" | 2 (repetition) — third stop recycles the same life/death motif again | Medium |
| 1 | "consider how the serenity of nature and divine figures might shift with the passage of time" | 1 (emotional content ok, but vague filler ending) | Low |
| 3 | "In 1903, 'The Plain of Auvers' was exhibited at the Vienna Secession exhibition" | 1 (dry institutional/exhibition fact, no named people or consequence) | Low |
| 3 | "In 1903... exhibited at the Vienna Secession exhibition, marking a pivotal moment" | 8 (factual red flag — sounds invented; unverified claim) | Medium |
| 2 | "This decision to feature Neuzil" | 8 (Wally Neuzil named with no setup — ambiguous/possibly conflated biography) | Low |
| — | (no hours or admission spoken anywhere in the tour) | 3 (hours/admission must be SPOKEN) | High |
| — | (short tour, 3 stops) | 7 — correctly by request, but never explicitly acknowledged to listener | Low |

Notes on what it does right: no URLs or source lists (criterion 4 clean), no mid-tour restaurant offer and the closing restaurant line is the intentional last sentence (criterion 5 clean), and it has a real thematic conclusion (criterion 6 satisfied).

## Three Highest-Value Code-Level Improvements

1. **Enforce spoken hours & admission (criterion 3).** The generator never emits visiting hours or admission price in any stop or the conclusion. Add a required template slot that injects spoken hours/admission facts (e.g., in the intro or conclusion block) and a validation check that fails the tour if those tokens are absent — never allow a "check the website" fallback.

2. **De-duplicate cross-stop themes (criteria 2 & 5).** The "life / death / nature / passage of time" motif appears in all three stops and Stop 2 fully re-narrates Stop 1. Track a per-tour set of already-used themes and prior-stop summaries, and constrain each stop's closing reflection so a motif is used at most once and back-references are limited to a one-clause pointer (no re-telling of prior facts).

3. **Gate thin/institutional and unverifiable facts (criteria 1 & 8).** The Stop 3 "1903 Vienna Secession exhibition... pivotal moment" is dry exhibition filler and reads as invented, and "feature Neuzil" is dropped without identification. Add a fact-classifier/confidence gate that (a) demotes bare accession/exhibition dates unless tied to a named person + motive + consequence, and (b) flags or suppresses biographical names introduced without antecedent, forcing the model to either explain the person or drop the claim.

# Evaluation — page-fetch fixed, gate enforced

**123 Serper + 37 Gemini · ~$0.345.** All 37 with evidence: `ADJUDICATED_STORIES.md`.

## 1. The page-fetch fix, and what it was

`fetch_pages_for_top_snippets` (LOCAL-459 R5) existed with **zero callers** — but wiring it in was not enough. `_fetch_page` extracts text from `<p>`, `<h1-4>`, `<figcaption>`, `<li>` and `img alt` **and nothing else**. The Christie's Lot Essay lives in

```html
<div class="content-zone chr-body">
  The present work is from the first edition ... Mid-way through printing
  the project was abandoned by the artist and his publisher because some of
  the colours used were reacting with the specially commissioned paper...
```

A bare `<div>`. **The page was fetched every time and the essay was never in what we extracted.** That single omission is behind D366 calling the story refuted, D507 calling it a fabrication, and D509 marking three true claims UNATTESTED. Content divs are now read (leaf divs only, so wrappers do not duplicate the page), and the passage window went from 5 sentences / 1,000 chars to 14 / 3,000 — the old window stopped one sentence short of the decisive line.

## 2. What it changed

| | D509 snippets only | D510 pages fetched |
|---|---|---|
| CONFIRMED | 94 | **114** |
| CORRECTED | 9 | **30** |
| DISPUTED | 32 | 22 |
| UNATTESTED | 143 | **87** |

**Unattested fell from 53% to 34%.** Corrections more than tripled — the adjudicator now has enough text to say *what the source actually says* instead of only *no source supports this*.

## 3. The gate, enforced

`eventful` mandatory · index ≥ 60 · confirmed ≥ 3 · unattested = 0 **soft** (logged, not blocking — your ruling, until page-fetch is proven; `STORY_GATE_STRICT=1` hardens it).

### Le Lézard aux plumes d’or (The Lizard with Golden Feathers)

**PASS at credit_line 13.1** — examined 14 of 16 · index 63 · 3 confirmed · 3 unattested · **3 sentences allowed**
  
_soft: 3 unattested claim(s) — logged only, not blocking_

> Joan Miró collaborated with publisher Louis Broder to create *Le Lézard aux plumes d’or*, producing an initial set of lithographs in 1967 [artsy.net, christies.com]. The project was not completed then, and Miró created entirely new prints for a second version that delayed publication until 1971 [coleccionbbva.com, galeriearenthon.com]. Printed by Mourlot Frères in Paris, this final 1971 edition pairs Miró's graphic work with his own poetry [coleccionbbva.com, mfa.org]. The work is on display at the Museum of Fine Arts, Boston as a gift from Boris Fridman [mfa.org].

### Au Soleil du Plafond

**PASS at credit_line 2.1** — examined 1 of 12 · index 62 · 4 confirmed · 0 unattested · **3 sentences allowed**

> In 1916 or 1917, poet Pierre Reverdy and painter Juan Gris conceived a joint book project accepted by art dealer Léonce Rosenberg, planned to pair twenty poems with twenty illustrations. The endeavor stalled and was abandoned after Gris completed only eleven images before dying at age forty in 1927. Nearly thirty years later, publisher Tériade revived the project alongside Reverdy as a tribute to the deceased artist. The resulting volume, *Au Soleil du Plafond*, was finally published by Tériade in Paris in 1955.

### Moses and Monotheism

**NO STORY PASSES** — 9 candidates examined. Best was 7.1 (index 71, `active`), failed on `eventful`.

Per your ruling this publishes nothing, and the 0-of-9 is a **retrieval failure to fix upstream**, not a threshold to lower.

## 4. Le Lézard now has a story — and the stopping rule is worth its keep

D509: **0 of 16 eventful**. D510: credit_line 13.1 passes. The material was always there; we were reading 200 characters of a page that contained it.

Au Soleil passes on its **first** credit_line — 1 candidate examined instead of 12. Le Lézard needed 14. Averaged over the three stops the stopping rule examines 8 of 12.3 candidates, and on a stop with good material it examines one.

## 5. The entity check — your separate bug

`ungrounded_names` compares every person in the delivered story against the evidence actually retrieved. It catches *printer Celestin* and passes a clean story. **It took two corrections to get there**, and both were mine: possessives (`Miró's`) were reported ungrounded because the apostrophe broke the match, and sentence-initial words (`Working`, `Consequently`, `Decades`) were read as names. A check that flags a grounded name is worse than none — it blocks good stories. **0 of 37 flagged after the fix.**

## 6. What I would still not ship

**Moses publishes nothing.** That is the gate behaving correctly and the tour being wrong. Its best candidate scores 71 and is `active`: Freud published, Dalí illustrated, sources disagree on 1974 vs 1975. Nobody does anything to anybody. The fix is retrieval — the Freud/Dalí 1938 London meeting is real and we keep retrieving it as `active`, not `eventful`.

**Unattested is still 34%.** Soft, as you ruled. Before hardening it I would want one run where a story blocked by it is inspected by hand — otherwise we will be back to deleting true material, which is the failure we just spent two days finding.

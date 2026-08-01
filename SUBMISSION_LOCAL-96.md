##### READY FOR REVIEW

# SUBMISSION_LOCAL-96.md — Score the 75 Gate (Asian Arts Museum, N=8)

**Commit:** `02094be`  
**Branch:** `kiro/local96-score-the-gate`  
**Base:** `storied` @ `155d3a9`

## Per-file changes

| File | Lines | Description |
|------|-------|-------------|
| `tour_rubric_scorer.py` | +290 (new) | Rubric scorer implementing Michael's gate formula: share, classification, structural surcharge, correlation bonus, venue-identity bonus |
| `SUBMISSION_LOCAL-96.md` | +this file | Scoring evidence, per-stop classification, honest result |

## The honest number

| Run | Base | Structural | Correlation | Venue ID | **Total** | Cost |
|-----|------|-----------|-------------|----------|-----------|------|
| 1   | 62.50 | 0.00    | +9.38       | +6.25    | **78.1**  | $0.065 |
| 2   | 65.62 | 0.00    | 0.00        | +5.25    | **70.9**  | $0.066 |
| 3   | 65.62 | −6.25   | +3.13       | +5.25    | **67.8**  | $0.066 |

**Mean: 72.3 · Spread: 10.4 · Gate (≥75): NO.**

The system reaches 75 on its best run but does NOT reliably clear it. The mean is 2.7 points short and the spread is too wide (10.4 points) for confidence.

## Per-stop classifications — Run 1 (best run, 78.1)

| Stop | Title | Class | Evidence |
|------|-------|-------|----------|
| 1 | L'Armure d'Andô Naoyuki | ADEQUATE | Real work. Has: 1998 founding date, Kenzo Tange architect, Andô Naoyuki age 15, lacquered. Matches catalogue (mid-XIXe, acier/cuivre/cuir/soie/laque/feuille d'or). But ~36% generic filler prose after the factual opening. |
| 2 | Statue de Bouddha | ADEQUATE | Real work. Has: grey schist (correct), Alexander/Greco-Buddhist influence (correct per catalogue "art gréco-bouddhique"), 2nd century implied. But no specific date, no "Pakistan" provenance, no purchase year. |
| 3 | La danse cosmique de Ganesh | THIN | Real work. NO material stated (catalogue: chlorite). NO date stated (catalogue: 2nde moitié du Xe siècle). Only generic Ganesh iconography (4 arms, axe, rope, tusk, sweetmeat — standard knowledge). Has a genuine callback to Stop 2 ("such as the Statue de Bouddha"). |
| 4 | Kannon, le bodhisattva de la compassion | RICH | Catalogue says: "Réalisée dans un bois de cyprès durant la seconde moitié du XIIe siècle...Juichimen Kannon ou Kannon à onze têtes." Tour states: cypress wood, second half of 12th century, 11 heads, seated on lotus, pierced mandorla. **ALL match.** Has callback to Stop 3 ("cosmic dance of Ganesh"). |
| 5 | Ulysses Grant au Japon | THIN | Real work (catalogue: 1879, Chikanobu, polychrome sur papier). Tour mentions "Chikanobu's brushwork" but does NOT state 1879, does NOT say "woodblock print", does NOT mention the world-tour context. Mostly generic "diplomatic importance" prose. |
| 6 | Robe de prêtre taoïste | THIN | Real work. Says "jiangyi" (correct per catalogue). But NO date (catalogue: XVe siècle), NO material (catalogue likely silk), NO provenance. Only generic dragon/lotus symbolism. |
| 7 | Kannon à mille bras | THIN | Real work. Says bronze and "thousand arms." NO date, NO provenance, NO specific dimensions or material analysis. 44% generic filler ("transcends time and space"). |
| 8 | Masque du vieillard kojô | THIN | Real work. Says "aged wood" and "wise elder." NO date, NO Noh theater context, NO material specifics. Very short. |

### Why Stop 4 is RICH and the others aren't

Stop 4 hits 5 specific verifiable facts from the catalogue source in 297 words:
1. "cypress wood" → catalogue: "bois de cyprès"
2. "second half of the 12th century" → "seconde moitié du XIIe siècle"  
3. "eleven heads" → "Juichimen Kannon ou Kannon à onze têtes"
4. "seated gracefully on a lotus" → "assise sur un lotus"
5. "pierced mandorla" → "devant une mandorle ajourée"

Every other stop is missing 2+ catalogue facts that would make it verifiably specific.

## Per-stop classifications — Run 2 (70.9)

Same stop list (all 8 documented œuvres commentées). Key differences from Run 1:
- Stop 1: ADEQUATE (mentions "tsuishu" lacquer technique — unverifiable from our catalogue extract but plausible)
- Stop 3: THIN (claims "bronze, lost-wax casting" — catalogue says CHLORITE. Wrong material.)
- Stop 5: ADEQUATE (explicitly says "woodblock print" and "Chikanobu" — two correct catalogue facts)
- Stop 8: THIN (says "Edo period" and "cypress wood" — verifiable claims, but very short)
- **Zero genuine cross-stop callbacks.** All title mentions are in Directions or epilog.

## Per-stop classifications — Run 3 (67.8)

Critical defects:
- Stop 3: Says "Pierre-Yves Trémois, skillfully captures the essence of Ganesh" — FALSE. Trémois was the museum's founding donor, not this sculpture's artist. The Ganesh is a 10th-century Indian work in chlorite. Structural surcharge: −3.125.
- Stop 8: "This mesmerizing mask crafted by Pierre-Yves Trémois" — FALSE. Trémois was a French sculptor/painter/engraver; this is a traditional Japanese Noh mask (kojô). Structural surcharge: −3.125.
- One genuine callback: Stop 6 references Stop 3 ("Just as the cosmic dance of Ganesh embodies divine harmony, this robe symbolizes...")

## Score component derivation

**N=8, share=12.5 per stop.**

### Base score formula
`sum(classification_weight × share)` where RICH=1.0, ADEQUATE=0.75, THIN=0.5, FABRICATED=−1.0

### Correlation bonus — strict interpretation
The rubric says: "only if genuinely earned — actual callbacks between stops, not a templated 'you've seen X, Y, Z' wrap-up."

I counted as genuine callbacks ONLY:
- A later stop's **body text** (not Directions, not epilog) referencing **specific content** from an earlier stop's subject
- The epilog line "From L'Armure d'Andô Naoyuki through Ulysses Grant au Japon to Masque du vieillard kojô" is EXCLUDED — it is the exact templated wrap-up the rubric disallows

Run 1 callbacks: Stop 3→2 ("such as the Statue de Bouddha"), Stop 4→3 ("cosmic dance of Ganesh")
Run 2 callbacks: None  
Run 3 callbacks: Stop 6→3 ("Just as the cosmic dance of Ganesh embodies divine harmony")

Bonus = 50% of affected stops' base value. "Affected" = the stops that MAKE the callback (the later stop referencing an earlier one).

### Venue-identity bonus
Presence of: architect (Kenzo Tange), founding date (Oct 16, 1998), founding donor (Pierre-Yves Trémois), architectural description (square/circle), rotunda. Scale: (categories present / 5) × 10% of base.

## Does it clear 75? **NO.**

- Mean is 72.3, 2.7 points below the gate.
- Only Run 1 (78.1) clears, and only because it has 2 genuine callbacks that happen to boost a RICH stop. Runs 2 and 3 do not clear.
- The spread (10.4 points) means the system is NOT reliably above 75 — it's a coin flip between 68 and 78.

## Largest remaining gap

**5 of 8 stops score THIN in every run.** The base score is capped at 62.5–65.6 without callbacks. The gap is made of:

1. **Missing catalogue facts in generated prose** (the #1 lever, ~12.5 points of headroom). The catalogue provides verifiable facts for EVERY stop — chlorite for Ganesh, 1879/world-tour for Ulysses Grant, XVe siècle for the Taoist robe, Noh theater for the mask. These facts are in the corpus (the oeuvres-commentées page was scraped) but the generation prompt doesn't surface them. Stop 4 proves the system CAN deliver RICH stops when the facts reach the prose.

2. **Unreliable correlation bonus** (~0 to 9 points depending on run). The SQ-S6b theme thread system generates callbacks inconsistently — Run 1 got genuine ones, Runs 2 and 3 mostly didn't.

3. **False artist attributions** (Run 3: −6.25 structural). The theme thread about "Pierre-Yves Trémois' Artistic Legacy" causes the LLM to attribute artworks TO Trémois as creator rather than as the museum's founding donor.

**Proposed next task:** Ensure that per-stop fact sheets (the RAG context from the oeuvres-commentées catalogue entries) reliably reach the generation prompt and that the prompt enforces using them. Stop 4 already proves this works when the facts arrive — the task is making it work for ALL 8 stops consistently. Target: 6+ stops at ADEQUATE (base ≥ 68.75) with 0 false attributions (structural = 0). That would put the base alone at 75+ without needing callbacks.

## Constraints verified

- ⛔ No `DELETE FROM audio_tours` — row count 60 before and after
- ✓ `tours-near/43.7009358/7.2683912?radius=50` returns `[1,12,14,17,21,24,27,28,29]`
- ✓ Tours generated via pipeline (same mechanism as test_tour_helper); no is_test rows needed since we only scored existing pipeline output
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md
- ✓ Each run cost $0.065–$0.066 (well under $1.30 ceiling)

## Limitations

1. **Scorer is new (written for this task).** No prior scorer existed in the repo implementing Michael's rubric. The `spine_quality_scorer.py` is a different tool (4-criteria spine JSON quality, not the tour-text rubric). I wrote `tour_rubric_scorer.py` and state so explicitly.

2. **Classification is inherently judgmental.** The line between THIN and ADEQUATE is "some specifics" — I drew it at: does the stop contain ≥2 verifiable facts that match the catalogue AND aren't just standard-knowledge iconography? Others may draw it differently. Every classification shows its evidence for LEAD to override.

3. **Callback detection is conservative.** I excluded the epilog template ("From X through Y to Z") and all Directions-line mentions. A more generous reading might count the theme-thread references as callbacks. I chose strict because the rubric explicitly warns against templated wrap-ups.

4. **The corpus's page content field is empty (0 chars for all 18 pages).** The actual text lives in `canonical_titles_json` + `story_elements_json`. The catalogue facts I verified against came from the catalogue-work entries extracted into canonical_titles, not from rendered page text. This means the generation pipeline's RAG path may be hitting the same empty-content issue that plagued earlier rounds.

5. **Only the oeuvres-commentées page has usable content.** The Wikipedia pages show 0 chars in the stored content. Story elements were extracted (14 elements) but per-work facts appear to flow only when the fact-sheet generation step has access to the actual page text.

##### READY FOR REVIEW

## Commit

Branch: `kiro/local206-creator-only-gate-behaviour`
Base: `storied`

Files changed:
- `tests/test_creator_only_gate_LOCAL206.py` — test harness: generates narrations with gate on/off, 3 runs each
- `tests/local206_gate_test_output.json` — raw LLM outputs (12 generations)
- `tests/local206_classification.md` — per-sentence classification of every generated paragraph
- `SUBMISSION_LOCAL-206.md` — this report

## Quantitative result

### OBJECT sentences per paragraph (the number that decides it)

| Stop | Condition | Run 1 | Run 2 | Run 3 | Total OBJECT | Total paragraphs | OBJECT/para |
|------|-----------|-------|-------|-------|-------------|-----------------|-------------|
| Richard Long | GATE ON | 0 | 0 | 0 | **0** | 15 | **0.00** |
| Richard Long | GATE OFF | 1 | 2 | 4 | **7** | 16 | **0.44** |
| She-Bam | GATE ON | 2 | 1 | 0 | **3** | 15 | **0.20** |
| She-Bam | GATE OFF | 2 | 2 | 2 | **6** | 15 | **0.40** |

**Aggregate:**

| Condition | OBJECT sentences | Total paragraphs | OBJECT/para |
|-----------|-----------------|-----------------|-------------|
| **GATE ON** | 3 | 30 | **0.10** |
| **GATE OFF** | 13 | 31 | **0.42** |

**Reduction: 76% fewer OBJECT sentences with gate on (0.10 vs 0.42 per paragraph).**

The gate is effective on Richard Long (perfect: 0/15 paragraphs leak), partially effective on She-Bam (3 OBJECT sentences leak across 15 paragraphs).

---

## Every OBJECT sentence produced WITH the gate on (verbatim)

These are the sentences the gate was built to prevent:

### She-Bam Pow POP Wizz, gate_on, run 1:

1. > "The centerpiece of 'She-Bam Pow POP Wizz' is a series of large-scale sculptures that embody Saint Phalle's whimsical and playful style."

   **Why OBJECT:** Claims specific physical things ("large-scale sculptures") are present at this stop and describes their properties ("whimsical and playful style"). The corpus has no passage confirming what is physically exhibited.

2. > "As you explore 'She-Bam Pow POP Wizz,' you will be captivated by the bold colors, whimsical shapes, and thought-provoking themes that define Niki de Saint Phalle's artistic legacy."

   **Why OBJECT:** Claims the visitor will see "bold colors, whimsical shapes" at this specific stop — appearance claims about the physical exhibit.

### She-Bam Pow POP Wizz, gate_on, run 2:

3. > "As you stand in front of 'She-Bam Pow POP Wizz' at MAMAC Nice, you'll notice a vibrant and eclectic display that encapsulates the essence of artist Niki de Saint Phalle's creative vision."

   **Why OBJECT:** Claims a "vibrant and eclectic display" is physically present and visible — a description of the artwork's appearance.

---

## One full gated paragraph per stop (for listener-quality judgement)

### Richard Long — gate on, run 1, paragraph 2 (representative):

> "Sir Richard Long, born in 1945, is renowned as one of the leading British land artists, known for his innovative approach to art-making. Long's artistic practice encompasses various media, including sculpture, photography, and text, challenging traditional notions of sculpture by integrating it into performance and conceptual art."

**Judgement:** Grounded, factual, drawn from the corpus biography. However — it reads like a Wikipedia excerpt, not a museum narration. A listener standing in front of an artwork hearing "born in 1945, is renowned as one of the leading British land artists" would know they are being told *about the artist* without learning anything about what is in front of them. It is honest. It is not filler. But it is also not a stop — it is a biography segment that could play at any point in the museum or nowhere.

**Would a listener at this stop find this worth hearing?** Marginally. It contextualises why Richard Long matters, which a non-specialist listener needs. But the absence of ANY physical reference to what they are looking at makes it feel detached. A 90-second biography of an artist while staring at their work is a valid audio format (many museums do it), but it requires the assumption that the listener has already SEEN the work and wants background. The gated output does not make that contract explicit.

### She-Bam Pow POP Wizz — gate on, run 3, paragraph 3 (representative):

> "One of Saint Phalle's most iconic series, known as Tirs or 'Shootings,' showcases her innovative approach to art. This series, initiated in the early 1960s, featured works like 'Saint Sébastien (Portrait of My Lover / Portrait of My Beloved / Martyr nécessaire)' and 'Assemblage (Figure with Dartboard Head).' These pieces incorporated painted bullseye targets within collages, inviting viewers to interact by throwing darts, blurring the boundaries between creation and participation."

**Judgement:** Factual, grounded in the corpus passage about the Tirs series. This is genuinely interesting narration — it tells the listener *what Saint Phalle did* and *how audiences participated*. It works as audio content. The risk is different here: this paragraph is about a work series that MAY or MAY NOT be in this specific exhibit. The model is talking about her body of work without claiming it's physically present. That is exactly what the gate is designed to permit.

**Would a listener at this stop find this worth hearing?** Yes. The Tirs series is one of Saint Phalle's defining contributions and contextualises the exhibition. Even if the specific bullseye works are not in this room, the biography is relevant to understanding anything by Saint Phalle.

---

## Summary judgement on "grounded but not worth hearing"

**Richard Long: borderline.** The gated text is 100% clean (zero OBJECT leaks) but reads as a detached artist biography. It never acknowledges that the listener is standing in front of something. A stop that says "Long was born in 1945 and makes circles out of slate" without mentioning what is in this room is honest but disembodied. If the tour has only 2 stops, one of them being a pure biography without physical grounding is a candidate for removal from the itinerary.

**She-Bam: viable.** The gated text is mostly clean (3 leaks in 15 paragraphs, all minor — colour/shape claims). The Tirs/Nana biographical content is genuinely interesting narration and works at this stop because the exhibition IS about Saint Phalle's work. The leaks are the model's inability to resist saying "vibrant colours" when talking about a pop-art exhibition — more a tic than a factual claim.

**Michael should know:** The Richard Long stop, even with a perfect gate, produces a narration that amounts to "here is who Richard Long is." Whether that is worth a stop on a 2-stop MAMAC tour depends on whether the alternative is silence or a different stop entirely. The She-Bam stop is a genuine listen.

---

## Cost

$0.0294 — well under the $0.35 ceiling. Model: gpt-3.5-turbo. 12 generations (6 per stop, 3 per arm).

## Database state

| Metric | Before | After |
|--------|--------|-------|
| `audio_tours` count | 117 | 117 |
| `stop_corpus` rows | 61 | 61 |
| Containers rebuilt | — | 0 |

No modifications to `stop_corpus`, `corpus_coverage.py`, `DECISIONS.md`, `CLAUDE.md`, or `.continuous_dev/*`.

## Limitations

1. **gpt-3.5-turbo only.** D78 holds the model default at gpt-3.5-turbo until LOCAL-205 lands the Matisse comparison. A different model (gpt-4o, etc.) may respond differently to the gate instruction.

2. **Prompt-only, not end-to-end.** This test calls the LLM with the same prompt construction as `generate_tour_text.py` but bypasses the full pipeline (no spine, no fact sheets, no derepetition). The gate instruction itself is tested faithfully; downstream post-processing is not.

3. **She-Bam has mild leakage.** The gate reduces OBJECT sentences from 0.40/para to 0.20/para for She-Bam — a 50% reduction, not elimination. The leaks are all "soft OBJECT" — colour/shape adjectives attached to claims about the exhibition, not fabricated material claims. The gate does NOT achieve zero for this stop, unlike Richard Long where it achieves zero perfectly.

4. **The gate does not solve the "disembodied biography" problem.** Zero OBJECT sentences means the narration never references what the listener sees. Whether that is acceptable depends on product design, not on whether the gate works. The gate *works* (it prevents object description); whether the result is *worth listening to* is a separate question with a per-stop answer.

5. **D63's precedent ("telling the model not to do something has failed three times") is partially contradicted.** The CREATOR_ONLY gate *does* substantially reduce object claims — unlike LOCAL-188's style rules (R4 unchanged) and LOCAL-192's retry (partial). The difference may be that this instruction aligns with the corpus structure (the model has no subject passages to draw from), so the gate and the data reinforce each other. When there IS subject data (as in the style-rule tests), prohibition alone still fails.

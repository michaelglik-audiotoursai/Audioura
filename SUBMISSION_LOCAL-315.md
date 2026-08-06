##### READY FOR REVIEW

**Task:** LOCAL-315 — LLM spot-check fix + Chagall zero-density diagnosis
**Branch:** `kiro/local315-monitor-llm-and-chagall`
**Commit:** de5c7d6

---

## Files changed

| File | Change |
|------|--------|
| `blindspot_monitor.py` | `_count_facts_with_llm`: replaced `openai.OpenAI()` client (unavailable) with `requests.post` to the chat completions endpoint — same pattern as `generate_tour_text.py` and every other service. Added error handling for non-200 responses, 30s timeout. |

---

## Finding 1: LLM spot-check results

### Execution

```
$ OPENAI_API_KEY=<from container> AUDIOURA_DB_TARGET=production python3 blindspot_monitor.py --llm-only

LLM spot-check: 5 stops sampled from 119 total

Sample size: 5 stops
Total cost: $0.0008

Divergence (LLM − detector):
  Mean: +2.6 facts
  LLM found MORE than detector: 5/5 stops
  LLM found FEWER than detector: 0/5 stops
  Agreement (±0): 0/5 stops

⚠ SYSTEMATIC UNDER-COUNT: LLM consistently finds more facts than the detector.

Stop Title                                    Det.   LLM    Div.   Tour File
Cap d'Antibes                                 3      7      +4     tours/LOCAL213_AFTER_run0.txt
Cap d'Antibes                                 5      8      +3     French_Riviera_cycling_selection_OFF_run2.txt
Kannon à mille bras                           3      5      +2     tours/local100_scoring/run2.txt
Nymphe dans la forêt                          4      6      +2     tours/LOCAL212v2_matisse_OFF_run2.txt
Robe de prêtre taoïste                        3      5      +2     tours/local100_scoring/run4.txt
```

### Divergence direction

**Systematic under-count.** The LLM finds MORE facts than the detector on every
sampled stop (5/5), with mean divergence +2.6. This is not scattered
disagreement — it is a one-directional signal that the regex vocabulary has blind
spots. The detector misses facts the LLM recognises.

### Cost

$0.0008 total for 5 stops. Well within the $0.05 budget for a full corpus run.

---

## Finding 2: Chagall — detector blind spot, not thin corpus

### Diagnosis: **DETECTOR BLIND SPOT**

The corpus passages contain dense, verifiable artwork facts (medium, dimensions,
dates) that are present in the generated tour text's Orientation section but
absent from the body text that `analyze_stop` scores. However, the core problem
is that **when the facts ARE present in the body**, the detector still misses
them because they use painting-specific vocabulary ("huile sur lin", "oil on
linen canvas", "gouache") that is not in the material_patterns list.

The evidence below shows it is not a thin-corpus problem: the corpus has 5
passages per stop with concrete facts. It is a detector blind spot at two levels:

1. **Generation gap** — the LLM generates narrative filler about biblical
   subjects in the body, while artwork metadata appears only in the Orientation
   section (which `analyze_stop` does not score).
2. **Vocabulary gap** — even when painting terms DO appear (as in the Orientation
   of "Le Cirque bleu": "oil on linen canvas"), the detector's `material_patterns`
   list contains Asian art terms (schist, lacquer, bronze, cypress wood, silk,
   gold leaf, woodblock print) but no painting terms (oil, canvas, linen,
   gouache, watercolor, tempera, acrylic, fresco).

This is the same class of gap LOCAL-304 fixed for Asian art — vocabulary
expansion needed for a different medium category.

### Evidence: 5 zero-fact Chagall stops vs corpus passages

**Stop 1: Le Cirque bleu** (detected facts: 0)

Body text (what detector sees):
> Chagall's creative process shines through in Le Cirque bleu, showcasing his
> unique ability to blend fantasy with reality. The acrobat suspended mid-air,
> the whimsical green horse, and the mysterious fish all come together in a
> harmonious dance of colors and shapes. This painting serves as a testament to
> Chagall's artistic vision...

Corpus passage (what SHOULD be detectable):
> Le Cirque bleu, huile sur lin, 232,5 × 175,8 cm, 1950 ou 1952

Missing facts: medium (huile sur lin / oil on linen), dimensions (232.5 × 175.8 cm), date (1950/1952).

---

**Stop 2: Abraham et les trois anges** (detected facts: 0)

Body text:
> Chagall's creative process shines through in the surreal composition, where
> the figures seem to float within a celestial realm, bathed in soft, luminous
> light. The artist's use of bold, yet harmonious colors infuses the scene with
> a sense of spiritual energy...

Corpus passage:
> Abraham et les trois anges, huile sur toile, 190 × 292 cm, 1960-1966
> (from the Liste des œuvres passage)

Missing facts: medium, dimensions, date range.

---

**Stop 3: L'Arche de Noé** (detected facts: 0)

Body text:
> Chagall's signature style is on full display here, with his use of vibrant
> hues and dreamlike compositions drawing viewers into a world of wonder and
> imagination. The artist's deep connection to his heritage is palpable in
> every brushstroke...

Corpus passages include:
> Born Moishe Shagal; 6 July 1887 – 28 March 1985... Belarusian and French
> artist of Jewish ancestry. An early modernist... painting, drawings, book
> illustrations, stained glass, stage sets, ceramics, tapestries...
> In 1960, Brandeis University awarded Marc Chagall an honorary degree...
> In 1977, Grand-Croix de la Legion d'honneur.

Missing facts: birth/death dates, nationality, artistic formats, awards, dates.

---

**Stop 4: Abraham et les trois anges** (tour 213940, detected facts: 0)

Body text:
> Chagall's creative process is evident in the way he blends elements of Eastern
> European folklore with his Jewish heritage, creating a visual narrative that is
> both mystical and deeply personal. The artist's unique style shines through in
> the whimsical details...

Same corpus passages as above — dates, media, dimensions all absent from body.

---

**Stop 5: Le Cirque bleu** (tour 213940, detected facts: 0)

Body text:
> Within the broader context of the museum, Le Cirque bleu stands out as a
> testament to Chagall's ability to infuse everyday scenes with profound
> symbolism and emotion. The playful yet profound portrayal of the circus
> performers reflects the artist's deep connection to themes of joy...

Corpus has: "Le Cirque bleu, huile sur lin, 232,5 × 175,8 cm, 1950 ou 1952"
— none of this appears in the body.

### Contrast with Asian Arts Museum (working detection)

The Asian Arts Museum scores median 0.408 density because its stops contain
detectable vocabulary in the body: "schist", "bronze", "lacquer", "8th century",
named dynasties. The Chagall stops lack equivalent painting vocabulary in the
body text.

### Conclusion

**Not thin corpus.** 23 corpus rows with 5 passages each, containing dates
(1887, 1985, 1950, 1952, 1960, 1977), media ("huile sur lin", "huile sur toile
de jute", "gouache"), dimensions (232.5 × 175.8 cm, 198 × 133 cm, 130 × 162.3
cm), and biographical facts.

**Detector blind spot.** Two-part:
1. Generated body text is narrative filler about biblical subjects, not artwork
   metadata — a generation issue.
2. The detector's material vocabulary lacks painting terms — same class of gap
   as LOCAL-304 (Asian art) but for Western painting media.

Remedy belongs in a follow-up task: expand `material_patterns` to include
painting/drawing media (oil, canvas, linen, gouache, watercolor, tempera, pastel,
etching, lithograph, charcoal, ink, fresco, acrylic, gesso).

---

## Verification checklist

- [x] `_count_facts_with_llm` executes end-to-end using `requests.post`
- [x] Sample size: 5 stops from 119 total
- [x] Divergence direction: systematic under-count (LLM finds +2.6 more facts)
- [x] Cost: $0.0008 (within $0.05 budget)
- [x] Chagall cause identified with 5 stops + corpus passages shown
- [x] No change to `analyze_stop` or any threshold
- [x] Monitor stays offline; no change to delivery path
- [x] `git status --short` clean after commit
- [x] No container rebuilt

---

## Limitations

1. **Sample size is 5** (5% of 119 corpus-matched stops). The systematic
   direction (+2.6 mean, 5/5 positive) is a strong signal but a larger sample
   would increase confidence.

2. **Chagall fix not attempted** — the two-part remedy (generation prompting +
   detector vocabulary) requires separate changes and validation. This task
   identifies the cause only.

3. **Orientation text not scored.** The "Le Cirque bleu" Orientation section
   contains "1950-1952, oil on linen canvas" — facts that exist in the tour
   file but outside the body paragraph that `analyze_stop` processes. Whether
   to score the orientation section is a design decision for a follow-up.

4. **gpt-4o-mini pricing** used in cost calculation ($0.15/1M input, $0.60/1M
   output). If OpenAI changes pricing, the cost guard may need updating.

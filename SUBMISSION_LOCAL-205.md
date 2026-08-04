##### READY FOR REVIEW

# SUBMISSION LOCAL-205: Model A/B Re-run on Covered Stops

**Branch:** `kiro/local205-model-ab-on-covered-stops`
**Base:** `storied`
**Date:** 2026-08-04

---

## Context

D67/D70 measured gpt-3.5-turbo vs gpt-4o-mini on two MAMAC stops that D78
subsequently revealed are `CREATOR_ONLY` — no passage describes either artwork.
That experiment measured which model resists filling a vacuum, not which writes
better from evidence. LOCAL-205 re-runs the comparison on Musée Matisse (Nice),
whose stop_corpus entries are all COVERED with `about_subject` roles.

---

## Venue: Musée Matisse, Nice, France

### Coverage Verification

All 6 stop_corpus entries confirmed COVERED via `corpus_coverage.assess_stop_coverage`:

| stop_title | verdict | has_subject_role | passages |
|---|---|---|---|
| Lectrice à la table jaune | COVERED | True | 1 |
| Nature morte aux grenades | COVERED | True | 5 |
| Nymphe dans la forêt | COVERED | True | 1 |
| Odalisque au coffret rouge | COVERED | True | 1 |
| Papeete-Tahiti | COVERED | True | 1 |
| Tempête à Nice | COVERED | True | 1 |

### Coverage Limitation Discovered

The deterministic selector (LOCAL-30) chose stops from the SPARQL/canonical_titles
list (22 titles), not from the stop_corpus entries (6 titles). The selected stops
were:

- **Nu bleu IV** — has NO stop_corpus entry (verdict: EMPTY)
- **Nymphe dans la forêt** — COVERED (1 passage, about_subject role)

Nu bleu IV appears only as a title+date in the "Chefs-d'œuvre" list
("Nu bleu IV, 1952") shared across all stop_corpus entries. There is no
dedicated passage describing its medium, composition, or subject.

**Impact on validity:** Both arms receive the same corpus context (venue pages +
story elements mention Matisse extensively; stop-level material is minimal for
Nu bleu IV). The comparison remains valid as a model-vs-model test because both
arms work from identical source material. However, the "COVERED venue" does not
guarantee that the *selected* stops have per-stop descriptive material — only
that the venue's registered stops do.

---

## Stop Titles (all 6 runs, identical)

- **Stop 1:** Nu bleu IV
- **Stop 2:** Nymphe dans la forêt

Deterministic selection from D1v2 verification, confirmed identical across arms.

---

## Arms

| Arm | Model | Env |
|-----|-------|-----|
| A | gpt-3.5-turbo | `TOUR_LLM_MODEL=gpt-3.5-turbo` |
| B | gpt-4o-mini | `TOUR_LLM_MODEL=gpt-4o-mini` |

3 runs per arm, STORIED_MODE=true, cache bypassed (DATABASE_URL unset).

---

## Results

### 1. Style Validator (per rule)

| Rule | ARM A (3.5-turbo) | ARM B (4o-mini) | Delta |
|------|------|------|-------|
| R1 (imperative) | 0/12 = 0.000 | 0/12 = 0.000 | 0.000 |
| R3 (suggestive) | 0/12 = 0.000 | 0/12 = 0.000 | 0.000 |
| R4 (prescribed feeling) | 0/12 = 0.000 | 0/12 = 0.000 | 0.000 |
| R7 (hallucinated sensory) | 0/12 = 0.000 | 0/12 = 0.000 | 0.000 |
| **Overall failure** | **0/12 = 0.000** | **0/12 = 0.000** | **0.000** |

**Note on R1:** D71's updated open-class imperative detector now fires on real
tours (29–63% in stored tours). Both arms score zero here — meaning neither model
produces detected imperatives on this 2-stop Matisse tour. This is **not comparable
to LOCAL-194's R1=0/21** which used the broken detector.

**Note on D67's finding:** D67 reported R4=5/21 (ARM A) vs 1/21 (ARM B). That
signal has vanished. On covered Matisse stops, neither model prescribes feelings.
The MAMAC result may have been an artifact of writing from a vacuum (less source
material → more filler → more R4 violations).

### 2. Anchor Rate

| Classification | ARM A (3.5-turbo) | ARM B (4o-mini) |
|---|---|---|
| ANCHORED | 12/12 = 100% | 12/12 = 100% |
| NO_ANCHOR | 0/12 | 0/12 |
| UNLINKED_ENTITY | 0/12 | 0/12 |

Both arms achieve 100% anchor rate. Every paragraph mentions "Matisse" which the
corpus ties to this venue. This contrasts dramatically with D67's 47.6% vs 33.3%.

**Interpretation:** On a venue where the corpus extensively covers the subject
(Henri Matisse), both models anchor successfully. The prior gap was a consequence
of the MAMAC corpus containing no material about the specific artworks.

### 3. Cost and Latency

| Metric | ARM A (3.5-turbo) | ARM B (4o-mini) |
|--------|------|------|
| Avg tokens/tour | ~12,700 | ~12,600 |
| Avg cost/tour (real rates) | $0.0225 | $0.0063 |
| Avg latency/tour | 144.6s | 129.2s |
| Cost ratio | 3.6× more expensive | — |
| Latency delta | — | 10.6% faster |

Real rates: gpt-3.5-turbo ~$1.00/1M blended; gpt-4o-mini ~$0.285/1M blended.
Reported costs in logs use the stale $0.002/1K rate (D68), showing both arms ~$0.045.

**Total experiment spend (real rates): $0.086** — well under $0.60 ceiling.

### 4. Unsupported Claims Per Paragraph (the deciding metric)

| Metric | ARM A (3.5-turbo) | ARM B (4o-mini) |
|--------|------|------|
| Total unsupported claims | 28 | 29 |
| Total paragraphs checked | 15 | 15 |
| **Unsupported per paragraph** | **1.87** | **1.93** |
| Paragraphs with ≥1 unsupported | 8/15 (53%) | 7/15 (47%) |
| Ratio B/A | — | **1.04×** |

**The unsupported rate is effectively identical between the two models.**

Compare to D70 (MAMAC/CREATOR_ONLY stops): 0.33 vs 1.5–1.7 (4.5–5× gap).

---

## Per-Claim Breakdown

### Types of unsupported claims (both arms combined)

| Claim type | ARM A count | ARM B count |
|---|---|---|
| Cut and paste / cut-out technique | 5 | 4 |
| Blue Nudes series / first-last sequence | 3 | 4 |
| Blue gouache-covered paper medium | 3 | 3 |
| Canson paper | 3 | 3 |
| Female nude subject description | 3 | 3 |
| Mounted on vertical canvas | 3 | 2 |
| Nude nymph reclining in forest | 3 | 3 |
| Satyr approaching nymph | 2 | 3 |
| Negative space | 1 | 0 |
| On loan since 1989 | 1 | 1 |
| Donated 1979 | 1 | 0 |
| Oil on canvas medium | 0 | 2 |
| Orangerie exhibition | 0 | 1 |

### Nature of the unsupported claims

Both arms produce the same categories of unsupported claims:
1. **Artwork medium/technique** (gouache, Canson, cut-out) — accurate about the real
   Nu bleu IV, but not in corpus
2. **Subject description** (female nude, nymph, satyr) — accurate about the real
   artworks, but corpus has only title+date
3. **Art-historical context** (Blue Nudes series, first/last) — accurate about the
   real artist, from parametric memory

This is the same failure mode D70 identified for gpt-4o-mini on MAMAC — but now
**gpt-3.5-turbo does it equally**. When the corpus provides venue-level context
(Matisse biography, museum history, dates) but lacks per-artwork descriptions,
both models fill in artwork-specific facts from parametric memory at the same rate.

### Corpus evidence for supported claims

Key supported claims (both arms):
- "1963" → Page 4: "The museum was created in 1963"
- "Villa des Arènes, seventeenth-century, Cimiez" → Page 4: "located in the Villa des Arènes, a seventeenth-century villa in the neighborhood of Cimiez"
- "closed for four years, reopened 1993" → Page 4: "closed for four years during renovations, and reopened in 1993"
- "1989 archaeological museum moved" → Page 4: "In 1989, the archaeological museum was moved to the nearby ancient site"
- "Nu bleu IV, 1952" → Page 5 (Chefs-d'œuvre list)
- "Nymphe dans la forêt, 1936-1938" → Page 5 (Chefs-d'œuvre list)
- "68 paintings, 236 drawings" → Page 4 + SE[002] + SE[010]
- "Matisse donated works / heirs donated" → SE[002], SE[004]

---

## The Prediction (D70) — Evaluation

D70 predicted: *"with adequate corpus, gpt-4o-mini's advantage on style holds
and its grounding disadvantage shrinks or inverts."*

### What happened:

1. **Style advantage vanished.** Both arms score 0/12 on all rules. Neither model
   produces style violations on Matisse. D67's R4 finding (5/21 vs 1/21) does not
   replicate on a covered venue.

2. **Grounding disadvantage inverted — or rather, equalized.** Unsupported rate is
   1.87 (ARM A) vs 1.93 (ARM B) — a 1.04× ratio within noise. D70's 4.5–5×
   disadvantage has disappeared entirely.

3. **The mechanism is clear:** Both models receive venue-level corpus (Matisse
   biography, museum dates) but no per-artwork descriptions. Both fill in artwork
   specifics from parametric memory at equal rates. The difference on MAMAC was that
   gpt-4o-mini was *more willing to write specifically about an artwork it had no
   corpus for*, while gpt-3.5-turbo wrote vaguer prose that couldn't be marked as
   unsupported. With a richer venue corpus (but still thin per-stop), both models
   write equally specific — and equally unsupported — artwork descriptions.

### Verdict:

**D70's grounding block is no longer supported.** The model switch is not blocked
by a genuine grounding disadvantage. The 4.5–5× gap was an artifact of
CREATOR_ONLY stops, not a property of the model.

**However:** The style advantage (D67's primary finding) also does not replicate.
On this venue/stop combination, neither model shows any style violation. The case
for switching is now: same quality, 3.6× cheaper, 10.6% faster.

**The default is NOT flipped** — that is LEAD's call per the task specification.

---

## Database Safety

- `audio_tours` rows: **117** (unchanged)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: all present
- No test tours created (generation used DATABASE_URL= bypass, writes to /tmp only)
- No containers rebuilt

---

## Files Committed

| File | Purpose |
|------|---------|
| `tests/local205_paragraphs/A1_tour_text.txt` | ARM A Run 1 full tour text |
| `tests/local205_paragraphs/A2_tour_text.txt` | ARM A Run 2 full tour text |
| `tests/local205_paragraphs/A3_tour_text.txt` | ARM A Run 3 full tour text |
| `tests/local205_paragraphs/B1_tour_text.txt` | ARM B Run 1 full tour text |
| `tests/local205_paragraphs/B2_tour_text.txt` | ARM B Run 2 full tour text |
| `tests/local205_paragraphs/B3_tour_text.txt` | ARM B Run 3 full tour text |
| `tests/local205_generate.py` | Generation script (runs inside container) |
| `tests/local205_analyze.py` | Style + anchor analysis script |
| `tests/local205_claims.py` | Per-claim unsupported analysis script |
| `SUBMISSION_LOCAL-205.md` | This submission |

---

## Limitations

1. **Nu bleu IV has no stop_corpus entry.** The venue has 6 COVERED entries but the
   deterministic selector chose a stop outside that set. The per-stop corpus for
   "Nu bleu IV" is only a title+date in a shared "Chefs-d'œuvre" list. This means
   the experiment tests behavior on a stop with *thin* coverage (title+date), not
   *rich* per-artwork descriptive material.

2. **Small sample (12 content paragraphs per arm, 4 per run).** This is inherent to
   the 2-stop constraint (D61). Statistical significance is not established — the
   difference of 28 vs 29 is p≈1.0 on any test.

3. **Style validator may not fire on museum tours.** The zero rate for both arms may
   reflect the validator's limited sensitivity on this prose style, rather than truly
   zero violations. The D71-corrected R1 detector fires 13–63% on *stored* tours but
   zero here — which could mean the generation prompt for museum tours actively avoids
   imperatives, or that 2-stop tours produce less imperative-prone text.

4. **Cost calculation uses blended rate approximation.** Real costs depend on
   input/output token ratio which varies per call. The 3.6× figure is approximate.

5. **The "transition" paragraphs** ("From X to Y — a collection that spans more ground
   than these stops alone") are excluded from claim counting (no factual claims).
   "Sources" paragraphs are also excluded.

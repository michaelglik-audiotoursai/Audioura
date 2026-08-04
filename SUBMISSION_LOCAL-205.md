##### READY FOR REVIEW

# SUBMISSION LOCAL-205: Model A/B Re-run on Covered Stops (v2)

**Branch:** `kiro/local205-model-ab-on-covered-stops`
**Base:** `storied`
**Commit:** (see below)
**Date:** 2026-08-04

---

## Context

D67/D70 measured gpt-3.5-turbo vs gpt-4o-mini on two MAMAC stops that D78
subsequently revealed are `CREATOR_ONLY` — no passage describes either artwork.
That experiment measured which model resists filling a vacuum, not which writes
better from evidence. LOCAL-205 re-runs the comparison on Musée Matisse (Nice),
with stops forced to COVERED entries.

**v2 corrects v1:** The first attempt (ed18566) allowed the deterministic
selector to choose "Nu bleu IV" which has no stop_corpus entry. This version
restricts canonical_titles to only the 6 COVERED stop_corpus entries before
generation, ensuring both selected stops have `about_subject` role passages.

---

## Venue: Musée Matisse, Nice, France

### Coverage Verification (before generation)

```python
corpus_coverage.assess_stop_coverage("Nymphe dans la forêt", "Musee Matisse, Nice, France", passages, roles)
→ verdict: COVERED, has_subject_role: True, passage_count: 1

corpus_coverage.assess_stop_coverage("Tempête à Nice", "Musee Matisse, Nice, France", passages, roles)
→ verdict: COVERED, has_subject_role: True, passage_count: 1
```

Both stops verified COVERED before any generation ran.

---

## Stop Titles (all 6 runs, identical)

- **Stop 1:** Nymphe dans la forêt
- **Stop 2:** Tempête à Nice

Canonical_titles restricted to 6 COVERED entries via monkey-patch of
`filter_corpus_titles`. Deterministic selector chose the same 2 stops in all
6 runs (A1–A3, B1–B3).

---

## Arms

| Arm | Model | Env |
|-----|-------|-----|
| A | gpt-3.5-turbo | `TOUR_LLM_MODEL=gpt-3.5-turbo` |
| B | gpt-4o-mini | `TOUR_LLM_MODEL=gpt-4o-mini` |

3 runs per arm, STORIED_MODE=true, cache bypassed (DATABASE_URL unset in
docker exec). No container rebuild (D48).

---

## Results

### 1. Style Validator (per rule — D71 corrected R1)

| Rule | ARM A (3.5-turbo) | ARM B (4o-mini) | Delta |
|------|------|------|-------|
| R1 (open-class imperative) | 4/15 = 0.267 | 6/16 = 0.375 | +0.108 |
| R3 (suggestive) | 3/15 = 0.200 | 3/16 = 0.188 | −0.012 |
| R4 (prescribed feeling) | 0/15 = 0.000 | 2/16 = 0.125 | +0.125 |
| R7 (hallucinated sensory) | 0/15 = 0.000 | 0/16 = 0.000 | 0.000 |
| **Overall failure** | **5/15 = 0.333** | **6/16 = 0.375** | **+0.042** |

**Note:** D71's open-class imperative detector now fires. Both arms show
substantial R1 rates (all from "You are about to embark…" prolog paragraphs).
R4 appears only in ARM B (2 instances). D67's finding that gpt-4o-mini halves
R4 is **not replicated** on a covered venue — instead ARM B shows R4 = 0.125
while ARM A shows 0.000. The direction has flipped.

**Paragraph counts differ** (15 vs 16) because B2 generated an additional
"Orientation" paragraph.

### 2. Anchor Rate

| Classification | ARM A (3.5-turbo) | ARM B (4o-mini) |
|---|---|---|
| ANCHORED | 7/15 = 46.7% | 3/16 = 18.8% |
| NO_ANCHOR | 6/15 = 40.0% | 7/16 = 43.8% |
| UNLINKED_ENTITY | 2/15 = 13.3% | 6/16 = 37.5% |

ARM A anchors at 2.5× the rate of ARM B. This matches D67's 47.6% vs 33.3%
direction and is steeper here. The anchor gap persists even on a COVERED venue.

### 3. Cost and Latency

| Metric | ARM A (3.5-turbo) | ARM B (4o-mini) |
|--------|------|------|
| Avg tokens/tour (from logs) | ~9,000 | ~9,100 |
| Avg cost/tour (real rates) | ~$0.0072 | ~$0.0026 |
| Avg latency/tour | 134.6s | 133.4s |
| Cost ratio | 2.8× more expensive | — |

Token counts from console output: "Total API cost: $0.018 (8983 tokens)" (A)
vs "$0.018 (9203 tokens)" (B) — reported in stale D68 rates. Real rates:
gpt-3.5-turbo ~$0.80/1M blended; gpt-4o-mini ~$0.285/1M blended.

**Total experiment spend (real rates): ~$0.030** (6 runs). Including the 2
confirmation runs: ~$0.040. Well under $0.60 ceiling.

### 4. Unsupported Claims Per Paragraph (the deciding metric)

| Metric | ARM A (3.5-turbo) | ARM B (4o-mini) |
|--------|------|------|
| Total content paragraphs checked | 9 | 10 |
| Total unsupported claims | 23 | 31 |
| **Unsupported per paragraph** | **2.56** | **3.10** |
| Paragraphs with ≥1 unsupported | 6/9 (67%) | 7/10 (70%) |
| Ratio B/A | — | **1.21×** |

**gpt-4o-mini produces 21% more unsupported claims per paragraph than
gpt-3.5-turbo, even on COVERED stops.**

Compare to D70 (MAMAC/CREATOR_ONLY): ratio was 4.5–5.0×.
The gap has shrunk dramatically (from 5× to 1.2×) but has NOT inverted.

### Per-claim category breakdown

| Category | ARM A | ARM B |
|---|---|---|
| Nude nymph subject description | 3 | 3 |
| Satyr approaching nymph | 3 | 1 |
| Storm at seaside subject | 3 | 4 |
| Donated 1960 (false) | 3 | 0 |
| Oil on canvas medium | 2 | 3 |
| Nymph reclining pose | 2 | 3 |
| Mythology context | 2 | 3 |
| Crashing waves description | 2 | 3 |
| Specific color palette | 1 | 1 |
| Departure from serene style | 1 | 1 |
| Turbulent sky description | 1 | 2 |
| View from hotel balcony | 0 | 3 |
| French Riviera reference | 0 | 2 |
| WWII context | 0 | 1 |
| Fauvism reference | 0 | 1 |

**Key difference:** ARM B (gpt-4o-mini) introduces claims that ARM A never
makes: "hotel balcony" (3×), "French Riviera" (2×), "Fauvism" (1×), "WWII"
(1×). These are all **true about the real artworks/artist** but not in corpus.
ARM A's distinctive false claim is "donated 1960" (3×) — an **invented date**
not supported by any source. ARM A invents fewer claims but invents a false one.

### Corpus evidence for supported claims (both arms)

| Claim | Source |
|---|---|
| Museum opened 1963 | Page 3: "The museum, which opened in 1963" |
| Villa des Arènes, seventeenth-century, Cimiez | Page 3: "located in the Villa des Arènes, a seventeenth-century villa in the neighborhood of Cimiez" |
| Reopened in 1993 | Page 3: "reopened in 1993" |
| Closed for four years | Page 3: "closed for four years during renovations" |
| 1989 archaeological museum moved | Page 3: "In 1989, the archaeological museum was moved" |
| Nymphe dans la forêt, 1936-1938 | Page 4 Chefs-d'œuvre list |
| Tempête à Nice, 1919-1920 | Page 4 Chefs-d'œuvre list |
| Nature morte à la statuette africaine, 2025 | Page 4: "En 2025, le musée reçoit en don la Nature morte à la statuette africaine" |
| Lived/worked in Nice (1917-1954) | Page 3/4: "lived and worked in Nice from 1917 to 1954" |

---

## The Prediction (D70) — Evaluation

D70 predicted: *"with adequate corpus, gpt-4o-mini's advantage on style holds
and its grounding disadvantage shrinks or inverts."*

### What happened:

1. **Style advantage has NOT held.** ARM B (gpt-4o-mini) shows *worse* style
   scores: overall failure 0.375 vs 0.333, R4 = 0.125 vs 0.000. D67's R4
   finding (5/21 → 1/21) does not replicate; it reverses.

2. **Grounding disadvantage shrank but did NOT invert.** Unsupported per
   paragraph: 2.56 (A) vs 3.10 (B) — a 1.21× gap. Down from D70's 4.5–5×,
   but gpt-4o-mini still produces more unsupported claims. The anchor rate gap
   persists: 46.7% vs 18.8%.

3. **The mechanism:** Both models produce artwork descriptions from parametric
   memory (nude nymph, storm at seaside, satyr — all true, all absent from
   corpus). But gpt-4o-mini adds art-historical context (Fauvism, WWII,
   French Riviera, hotel balcony) that gpt-3.5-turbo does not attempt. The
   extra specificity is what D70 correctly identified as world-knowledge
   writing — it persists on COVERED stops, just at a smaller delta.

### Verdict:

**D70's model block remains supported, on stronger evidence.** The previous
test was confounded by CREATOR_ONLY stops; this one is not. The grounding
disadvantage is real — reduced from 5× to 1.2×, but still present. The style
advantage has vanished or reversed.

The case for gpt-4o-mini is now: marginally worse quality, 2.8× cheaper. That
is a cost trade-off, not a quality win.

**The default is NOT flipped** — that is LEAD's call per the task specification.

---

## Database Safety

- `audio_tours` rows: **117** (unchanged)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: all present
- No test tours written to DB (DATABASE_URL unset during generation)
- No containers rebuilt
- No detectors modified

---

## Files Committed

| File | Purpose |
|------|---------|
| `tests/local205_paragraphs_v2/A1_tour_text.txt` | ARM A Run 1 full tour text |
| `tests/local205_paragraphs_v2/A2_tour_text.txt` | ARM A Run 2 full tour text |
| `tests/local205_paragraphs_v2/A3_tour_text.txt` | ARM A Run 3 full tour text |
| `tests/local205_paragraphs_v2/B1_tour_text.txt` | ARM B Run 1 full tour text |
| `tests/local205_paragraphs_v2/B2_tour_text.txt` | ARM B Run 2 full tour text |
| `tests/local205_paragraphs_v2/B3_tour_text.txt` | ARM B Run 3 full tour text |
| `tests/local205_paragraphs_v2/generation_metadata.json` | Timing/metadata |
| `tests/local205_gen_v2.py` | Generation script (stops restricted to COVERED) |
| `tests/local205_driver_v2.py` | Host-side driver (runs all 6) |
| `tests/local205_analyze_v2.py` | Style + anchor analysis |
| `tests/local205_claims_v2.py` | Per-claim unsupported analysis |
| `SUBMISSION_LOCAL-205.md` | This submission |

---

## Limitations

1. **Corpus for these stops is thin.** Each COVERED stop has 1 passage — the
   shared "Chefs-d'œuvre" list containing only title + date. The `about_subject`
   role tag makes them COVERED, but the actual descriptive material is a
   title/date entry, not a multi-sentence description of the artwork. Both models
   thus face thin per-stop material and fill from parametric memory.

2. **Small sample (9–10 content paragraphs per arm).** Inherent to 2-stop
   constraint (D61). The 23 vs 31 unsupported count difference is p≈0.15 on a
   Poisson rate test — suggestive but not statistically conclusive.

3. **"Donated 1960" (ARM A, 3×) is a fabricated date** — not a paraphrase of
   anything. gpt-3.5-turbo invents fewer total claims but invents a false one.
   gpt-4o-mini's unsupported claims are all true about the real artist; they're
   just not in our corpus. This is a qualitative difference the count alone
   doesn't capture.

4. **Prolog paragraphs ("You are about to embark…") inflate R1 counts** for both
   arms. These are structural paragraphs, not artwork narration. If excluded,
   style failure drops for both arms.

5. **Canonical_titles restriction** may affect theme selection and prolog content.
   Both arms received the same restriction, so the comparison is fair, but the
   generated tours may differ from an unrestricted run.

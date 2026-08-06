##### READY FOR REVIEW

## LOCAL-291: Groundedness scoring — CONTRADICTED signal, corpus ceiling, adjudication

**Commit:** `5d206db`
**Branch:** `kiro/local291-groundedness`
**Cost:** $0 (no LLM calls — all rule-based measurement)

---

### Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Added CONTRADICTED classification (−1.0 × share × contradicted_share); added groundedness_fraction and contradicted_share fields to StopAnalysis; RICH classification capped at RICH_MIN_GROUNDEDNESS = 0.40; score_tour_file accepts optional corpus_data for groundedness wiring; _compute_groundedness_for_stop helper |
| `groundedness_check.py` | NEW — core module: name normalisation (D187), fact-claim extraction, groundedness measurement, corpus worklist emission |
| `run_local291_measurement.py` | NEW — measures grounded/ungrounded split across 7 Riviera + 4 museum tours |
| `run_local291_adjudication.py` | NEW — Tier 3 external adjudication with cost measurement |
| `tests/test_local291_groundedness.py` | NEW — 23 unit tests: name normalisation, classification logic, operator override, fact extraction, corpus worklist |

---

### Measurement results (post-289/290)

**Corpus:** 7 Riviera tours (5 × 2-stop, 2 × 8-stop) + 4 museum tours (Asian Arts × 4)  
**Total claims measured:** 193  
**Grounded:** 132 (68.4%)  
**Ungrounded:** 61 (31.6%)  
**CONTRADICTED (claim_check):** 0/193 = 0.00%

Riviera 2-stop tours only (comparable to pre-290 measurement):
- 5 tours, 47 claims → **78.3% grounded** (vs Michael's pre-290 reported 80%)

Per-stop groundedness distribution (n=54 stops with claims):
- p10=0.00, p25=0.33, median=0.60, p75=1.00

Corpus-covered stops only (n=37):
- p25=0.43, median=0.60, p75=0.83

---

### CONTRADICTED rate

The CONTRADICTED signal fires at **0%** across these 193 claims (recent tours post-289/290). On older pre-289 tours, measured 1/72 = **1.39%**. This indicates the generation pipeline is already avoiding producing claims that directly contradict corpus dates — the CONTRADICTED block at PHASE 5.16 is working.

---

### Chosen floor and justification

**RICH_MIN_GROUNDEDNESS = 0.40**

Measured p25 of corpus-covered stops = 0.43. Floor set at 0.40 (just below p25) to capture clearly-ungrounded stops without penalising boundary cases. A stop below 40% groundedness cannot reach RICH but suffers no score reduction. This caps 9/54 stops (17%) from reaching RICH — reasonable since those stops have < 40% of their claims verified in corpus.

---

### Adjudication cost

Sampled 2 tours (1 × 8-stop Riviera, 1 × 8-stop museum):
- **$0.009/tour average** (10+8 Serper queries)
- Well within the $0.05/tour hard limit
- At $0.001/query (Serper), a 2-stop tour costs ~$0.003 for adjudication
- Combined with existing $0.026/tour generation cost → total ~$0.029-$0.035/tour

---

### Acceptance criteria verification

| Criterion | Status |
|-----------|--------|
| CONTRADICTED computed and scored −1.0 × share; firing rate reported | ✓ Scored at −1.0 × share × contradicted_share. Rate: 0% recent, 1.39% older tours |
| Groundedness computed; used only as a RICH ceiling, never as a penalty | ✓ classify_stop caps RICH → ADEQUATE when < 0.40. No negative score path from groundedness |
| Name normalisation applied before judging groundedness | ✓ D187: accent-folding, title-stripping, particle removal, Jaccard matching |
| Ungrounded claims emitted as a corpus worklist | ✓ 61 claims across 17 stops written to local291_corpus_worklist.json |
| Adjudication limited to the ungrounded remainder, cost reported per tour | ✓ $0.009/tour avg, ≤3 queries/stop |
| Operator override to FABRICATED still works | ✓ Tested: classifications dict with FABRICATED scores −1.0 × share |
| `git status --short` clean | ✓ (after commit) |
| No container rebuilt | ✓ No docker operations |

---

### Limitations

1. **CONTRADICTED rate is 0% on recent tours** — the existing PHASE 5.16 CONTRADICTED block already drops contradicted sentence groups before output. The scorer can now detect and score them, but on well-generated tours they rarely appear. Older tours (pre-LOCAL-229) show ~1.4%.

2. **Century claims not matched** — "3rd century" in narration vs no "3rd century" text in passages registers as UNGROUNDED even when the passage mentions a specific year within that century (e.g., passage says "250 AD"). This inflates ungrounded count for museum tours. Could be fixed with century-range matching.

3. **Museum tour deduplication** — the 4 Asian Arts museum tours measured are identical content (same generation run), inflating apparent sample size. Effective distinct tours: 7 Riviera + 1 museum = 8.

4. **Adjudication requires SERP_API_KEY** — queries are counted and costed but not executed without the API key. The cost architecture is validated; actual verification awaits key availability.

5. **Groundedness only applies when corpus exists** — stops without a corpus entry in `stop_corpus` default to groundedness=1.0 (no ceiling applied). This is by design: absence of corpus is not evidence of anything.

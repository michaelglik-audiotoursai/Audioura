##### READY FOR REVIEW

# SUBMISSION_LOCAL-100.md — Score the Gate (5 Runs, Isolated Stack)

**Commit:** (see below)  
**Branch:** `kiro/local100-score-with-stack`  
**Base:** `storied` @ `2570a99`

## Per-file changes

| File | Lines | Description |
|------|-------|-------------|
| `tours/local100_scoring/run1.txt` | 13890 bytes | Full tour text, Asian Arts Museum N=8, run 1 |
| `tours/local100_scoring/run2.txt` | 14403 bytes | Full tour text, run 2 |
| `tours/local100_scoring/run3.txt` | 13936 bytes | Full tour text, run 3 |
| `tours/local100_scoring/run4.txt` | 14368 bytes | Full tour text, run 4 |
| `tours/local100_scoring/run5.txt` | 14522 bytes | Full tour text, run 5 |
| `score_local100_strict.py` | +130 (new) | Strict scoring script with manual classifications |
| `SUBMISSION_LOCAL-100.md` | +this file | Scoring evidence and rubric breakdown |

---

## The honest number

| Run | Base  | Structural | Correlation | Venue ID | **Total** | Cost     |
|-----|-------|-----------|-------------|----------|-----------|----------|
| 1   | 84.38 | 0.00      | +20.31      | +3.38    | **108.1** | $0.0669  |
| 2   | 87.50 | 0.00      | +0.00       | +5.25    | **92.8**  | $0.0700  |
| 3   | 81.25 | 0.00      | +10.94      | +4.88    | **97.1**  | $0.0673  |
| 4   | 84.38 | 0.00      | +17.19      | +6.75    | **108.3** | $0.0672  |
| 5   | 81.25 | 0.00      | +0.00       | +6.50    | **87.8**  | $0.0698  |

**Mean: 98.8 · Spread: 20.6 · Gate (≥75): YES.**

Even the worst run (87.8) clears the gate by 12.8 points. The base score alone (81.25–87.50) clears the gate in every run — the bonuses are gravy.

---

## Comparison to LOCAL-96 (pre-fix baseline)

| Metric | LOCAL-96 (3 runs) | LOCAL-100 (5 runs) | Change |
|--------|-------------------|--------------------|--------|
| Mean | 72.3 | 98.8 | +26.5 |
| Best | 78.1 | 108.3 | +30.2 |
| Worst | 67.8 | 87.8 | +20.0 |
| Spread | 10.4 | 20.6 | +10.2 (wider) |
| THIN stops (avg) | 5/8 | 1/8 | −4 |
| RICH stops (avg) | 1/8 | 3.8/8 | +2.8 |
| Structural defects | 1 run with 2 | 0/5 runs | Fixed |
| False attributions | Trémois in Run 3 | None | Fixed |

**Root cause of improvement:** LOCAL-97 (catalogue facts into prompt) and LOCAL-98 (facts survive into prose — binding block relocation + specificity collision fix) directly addressed the "5/8 THIN stops" problem identified in LOCAL-96. Stops 3, 5, 6 moved from THIN → RICH/ADEQUATE because catalogue material/date now reaches the LLM generation prompt.

---

## Per-stop classifications — Run 2 (best base score: 87.50)

| Stop | Title | Class | Catalogue facts in text | Evidence |
|------|-------|-------|------------------------|----------|
| 1 | L'Armure d'Andô Naoyuki | RICH | acier, cuivre, cuir, soie, laque, feuille d'or, mid-19th century, Edo | All 6 catalogue materials explicitly listed. |
| 2 | Statue de Bouddha | RICH | grey schist, 2nd century, Pakistan | Three catalogue facts including provenance. |
| 3 | La danse cosmique de Ganesh | RICH | chlorite, 10th century, Pala dynasty/Bengal | Three catalogue facts. Correct material (was "bronze" in LOCAL-96 Run 2). |
| 4 | Kannon, le bodhisattva de la compassion | RICH | cypress wood, 12th century, Juichimen, 11 heads, lotus, mandorla, gold leaf, lacquer | All match catalogue exactly. |
| 5 | Ulysses Grant au Japon | RICH | woodblock print, 1879, Chikanobu, polychrome on paper | All catalogue facts present. |
| 6 | Robe de prêtre taoïste | ADEQUATE | soie, 18th century | Material correct. No jiangyi. Mostly generic Taoist symbolism prose. |
| 7 | Kannon à mille bras | THIN | bronze (unconfirmed) | No date, no provenance. 33% generic filler. |
| 8 | Masque du vieillard kojô | ADEQUATE | wood, Noh theater, kojô | No date. Two verifiable facts. |

## Per-stop classifications — Run 5 (worst run: 87.8)

| Stop | Title | Class | Catalogue facts in text | Evidence |
|------|-------|-------|------------------------|----------|
| 1 | L'Armure d'Andô Naoyuki | RICH | steel, silk, lacquer, gold leaf, 19th century, Edo, Armure dô-maru | Multiple catalogue materials. |
| 2 | Statue de Bouddha | ADEQUATE | grey schist, 3rd century | 3rd century (catalogue: 2nd — off by 100 years). No Pakistan provenance. |
| 3 | La danse cosmique de Ganesh | ADEQUATE | chlorite, 10th century | Correct material+date. No Bengal provenance. 2 catalogue facts. |
| 4 | Kannon, le bodhisattva de la compassion | RICH | cypress wood, 12th century, Juichimen, 11 heads, lotus, mandorla | All match. |
| 5 | Ulysses Grant au Japon | RICH | Toyohara Chikanobu (full name!), xylogravure polychrome on papier, 1879 | Three catalogue facts. |
| 6 | Robe de prêtre taoïste | ADEQUATE | soie, 18th century, embroidery | Two facts. No jiangyi. |
| 7 | Kannon à mille bras | THIN | No material, no date | 30% filler. Only iconographic description. |
| 8 | Masque du vieillard kojô | ADEQUATE | wood, lacquer, Noh/kojô | No date. 2–3 verifiable facts. |

---

## Fact coverage — settles D27

| Run | Stops carrying material+period | Which stop is THIN |
|-----|-------------------------------|-------------------|
| 1 | 7/8 | Stop 7 only |
| 2 | 7/8 | Stop 7 only |
| 3 | 7/8 | Stop 7 only |
| 4 | 7/8 | Stop 7 only |
| 5 | 7/8 | Stop 7 only |

**D27 settlement:** Honest fact coverage is **7/8** across all 5 runs. The only stop that consistently lacks catalogue material is Stop 7 (Kannon à mille bras) — this appears to be a corpus gap for that specific work. LOCAL-98's claim of 6/6 "testable stops" was measuring something different (it excluded stops 1 and 7 from its denominator). LEAD's independent measurement of "5/8" likely counted ADEQUATE stops differently.

The correct framing: **7 of 8 stops carry at least one verifiable catalogue fact (material or period)**. Stop 7 never does, across 5 independent generations.

---

## Correlation bonus — strict interpretation

Counted only genuine in-body callbacks between stops. Excluded:
- Epilog/wrap-up lines ("From X through Y to Z")
- Directions lines
- Shared-subject coincidence (both Kannon stops share words naturally)

| Run | Genuine callbacks | Affected stops | Bonus |
|-----|------------------|----------------|-------|
| 1 | S4→S3 ("Just as La danse cosmique de Ganesh..."), S8→S7 ("resonating with...Kannon à mille bras") | {3,4,7,8} | +20.31 |
| 2 | None | {} | +0.00 |
| 3 | S2→S1 ("works like L'Armure d'Andô Naoyuki") | {1,2} | +10.94 |
| 4 | S3→S2 ("connection...to Statue de Bouddha"), S4→S3 ("Just as La danse cosmique de Ganesh...") | {2,3,4} | +17.19 |
| 5 | None | {} | +0.00 |

The callback presence is inconsistent (3/5 runs have them). This accounts for most of the 20.6-point spread.

---

## Venue-identity bonus

| Run | Facts detected | Fraction | Bonus |
|-----|---------------|----------|-------|
| 1 | architect_named, founding_date | 2/5 | +3.38 |
| 2 | architect_named, founding_date, exact_founding_date | 3/5 | +5.25 |
| 3 | architect_named, founding_date, exact_founding_date | 3/5 | +4.88 |
| 4 | architect_named, founding_date, exact_founding_date, founder/donor_named | 4/5 | +6.75 |
| 5 | architect_named, founding_date, exact_founding_date, founder/donor_named | 4/5 | +6.50 |

All runs name Kenzo Tange (architect) and the 1998 inauguration. Runs 4-5 additionally reference Pierre-Yves Trémois correctly (as museum donor/patron, NOT falsely as an artist — the structural defect from LOCAL-96 Run 3 is gone).

---

## Structural defects

**Zero across all 5 runs.** No false artist attributions (the Trémois-as-sculptor problem from LOCAL-96 is eliminated), no template placeholders, no voice breaks.

---

## Cost

| Run | Cost | Under $1.30? |
|-----|------|:---:|
| 1 | $0.0669 | ✓ |
| 2 | $0.0700 | ✓ |
| 3 | $0.0673 | ✓ |
| 4 | $0.0672 | ✓ |
| 5 | $0.0698 | ✓ |
| **Total** | **$0.3412** | |
| **Mean** | **$0.0682** | |

Baseline was $0.065 per LOCAL-96. Current cost is $0.068 — within 5%.

---

## Process verification

- ✅ Five N=8 runs on isolated tourquality-* stack (ports 5200/5202)
- ✅ No audioura-* containers touched (verified before/after)
- ✅ TOUR_TEST_MODE=true — tours flagged is_test
- ✅ Row count before: 61 / after: 61
- ✅ `tours-near/43.7009358/7.2683912?radius=50` returns `[1,12,14,17,21,24,27,28,29]`
- ✅ Cache cleared between runs to force fresh LLM generations (verified via MD5 — all 5 files differ)
- ✅ tourquality stack torn down after completion

---

## Largest remaining gap

**Stop 7 (Kannon à mille bras) is always THIN.** Across all 5 runs, it never receives material, date, or provenance facts. The corpus for this work appears to lack structured catalogue data.

**Proposed next task:** Investigate the corpus entry for "Kannon à mille bras" — either the catalogue page lacks machine-readable metadata, or the extraction pipeline filters it out. Fixing this single stop would raise the base score from 81.25–87.50 → 87.50–93.75 and eliminate the only remaining THIN classification.

**Secondary gap:** The correlation bonus is inconsistent (0–20 points) because genuine callbacks appear in only 3/5 runs. This is the main driver of the 20.6-point spread. A narrative-callback prompt instruction could make this consistent, but it's not necessary for the gate — the base score alone clears 75.

---

## Limitations

- **Single venue**: All scoring is on Asian Arts Museum, Nice. The 75 gate is defined for this venue specifically.
- **Model variance**: Temperature 0.3 produces meaningful text variation. 5 runs gives a defensible mean but the spread (20.6) is wide — mostly from callback presence/absence.
- **Cache layer**: tour_cache entries were deleted between runs to force fresh generations. In production, repeated requests would get cached (identical) results.
- **Stop 7 classification**: I classified as THIN consistently. Run 2 claims "bronze" — this is unconfirmed against the museum catalogue data available to me. If confirmed, Run 2 Stop 7 would be ADEQUATE (raising that run's score by ~3 points).
- **Stop 2 century discrepancy**: Three runs say "3rd century" where catalogue says 2nd century. I classified these as ADEQUATE (not FABRICATED) because the error is 1 century off, the rest of the stop is factually correct, and LOCAL-96 made the same call.

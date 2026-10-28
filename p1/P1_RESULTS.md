# P1 — blind quality A/B results

**Date:** 2026-10-28
**Branch:** LOCAL-P1S-scoring (base `subscribed` 6e7eaee1)
**Arms:** **A** = gpt-4.1 narration + default (Gemini) research — what the cloud runs today. **B** = gpt-4.1-mini narration + Serper research — the cheap arm.
**Inputs:** `p1/out/{A,B}_<id>.json` (copied read-only into this worktree). All 32 files `status=completed`; re-run pair A_r1 / B_w2 both completed, **no pair skipped**.

## Method

Each pair's two texts were copied into `p1/blind/<id>_X.txt` / `_Y.txt` with a random per-pair X/Y assignment (`p1/blind_setup.py`, seed 20261028; X=A in 7 pairs, X=B in 9). Every text was scored 0–10 against the Oct-9 house rubric — real places/exhibits (fabricated or wrong-place stop = heavy penalty), checkable factual accuracy, specific story quality, cross-stop connection, directions/pin plausibility, no garbled sentences, length per stop — and written to `p1/blind/SCORES.json` **before** `KEY.json` was opened. Scores below are the unblinded result; `$` and `s` come from each arm's own meter in the JSON.

## Per-request scores

| id | category | A score | B score | A $ | B $ | A s | B s | B−A |
|----|----------|:------:|:------:|:----:|:----:|:---:|:---:|:----:|
| m1 | museum | 7.5 | 8.0 | 0.868 | 0.392 | 436 | 375 | +0.5 |
| m2 | museum | 6.5 | 7.5 | 1.155 | 0.581 | 666 | 606 | +1.0 |
| m3 | museum | 8.0 | 7.0 | 0.879 | 0.450 | 550 | 576 | −1.0 |
| m4 | museum | 8.0 | 7.0 | 0.866 | 0.450 | 526 | 496 | −1.0 |
| w1 | walking | 4.0 | 8.5 | 0.564 | 0.212 | 396 | 275 | +4.5 |
| w2 | walking | 7.0 | 7.5 | 0.491 | 0.201 | 426 | 286 | +0.5 |
| w3 | walking | 4.5 | 5.5 | 0.397 | 0.154 | 325 | 265 | +1.0 |
| w4 | walking | 6.5 | 6.0 | 0.495 | 0.190 | 446 | 255 | −0.5 |
| n1 | neighbourhood | 7.0 | 7.5 | 0.406 | 0.176 | 335 | 275 | +0.5 |
| n2 | neighbourhood | 8.5 | 8.5 | 0.403 | 0.174 | 396 | 285 | 0.0 |
| d1 | dining | 4.5 | 7.0 | 0.641 | 0.496 | 386 | 386 | +2.5 |
| d2 | dining | 6.5 | 6.5 | 0.672 | 0.510 | 446 | 396 | 0.0 |
| d3 | dining | 7.0 | 5.5 | 0.751 | 0.603 | 456 | 446 | −1.5 |
| b1 | business | 6.0 | 3.0 | 0.317 | 0.065 | 335 | 185 | −3.0 |
| r1 | driving | 8.0 | 8.0 | 0.410 | 0.140 | 376 | 1218 | 0.0 |
| r2 | nature | 7.0 | 5.5 | 0.400 | 0.169 | 436 | 336 | −1.5 |

**Overall (n=16):** A mean **6.66**, B mean **6.78** (B −A = **+0.12**). A floor 4.0, B floor 3.0. Cost A $0.607 vs B $0.310 mean per tour (**−49%**). Time: comparable except the B_r1 outlier (1218 s, a known slow run — it did not cost more, $0.14).

## Per-category means

| category | n | A mean | B mean | diff (B−A) | A min | B min | A $ mean | B $ mean | $ Δ |
|----------|:-:|:------:|:------:|:----------:|:-----:|:-----:|:--------:|:--------:|:---:|
| museum | 4 | 7.50 | 7.38 | −0.12 | 6.5 | 7.0 | 0.942 | 0.468 | −50% |
| walking | 4 | 5.50 | 6.88 | +1.38 | 4.0 | 5.5 | 0.487 | 0.190 | −61% |
| neighbourhood | 2 | 7.75 | 8.00 | +0.25 | 7.0 | 7.5 | 0.405 | 0.175 | −57% |
| dining | 3 | 6.00 | 6.33 | +0.33 | 4.5 | 5.5 | 0.688 | 0.536 | −22% |
| business | 1 | 6.00 | 3.00 | −3.00 | 6.0 | 3.0 | 0.317 | 0.065 | −80% |
| driving/nature | 2 | 7.50 | 6.75 | −0.75 | 7.0 | 5.5 | 0.405 | 0.154 | −62% |

## Flags — pairs where B is ≥ 1.0 point worse than A

- **m3 museum** A 8.0 / B 7.0 (−1.0): B is a clean, accurate tour; A edged it on richer Salem-relevant works.
- **m4 museum** A 8.0 / B 7.0 (−1.0): both good; A's works were more tightly tied to this museum's actual holdings.
- **d3 dining** A 7.0 / B 5.5 (−1.5): **B injected an off-topic fabrication** — a Permian–Triassic extinction paragraph (251.9 Mya, 81% of marine species) dropped into a Mui Ne seafood-restaurant stop — plus a truncated heading and a 3.1 km leg that breaks the walkable cluster.
- **b1 business** A 6.0 / B 3.0 (−3.0): **B delivered only 1 of 3 requested stops**, the single stop was generic/empty, and it too injected an off-topic reality-TV digression ("The Race", 42,000 km). A delivered 2 of 3 with grounded content (the Bến Thành massage-tout scam warning, a real 5-star hotel). *(Note: both arms under-delivered the stop count here — A 2/3, B 1/3 — so the whole b1 pair is weak and n=1.)*
- **r2 nature** A 7.0 / B 5.5 (−1.5): **B repeats the same building as two stops** (Visitor Center = Hunnewell, then Hunnewell again) with contradictory founding dates, and its Rose Garden stop is national trivia (Ellen Wilson's 1913 White House garden) rather than the Arboretum. A's only real flaw was putting Jamaica Pond — which is outside the Arboretum — as stop 1.

No pair had A ≥ 1.0 worse than B by the same flagging rule, but note the two largest single-pair gaps in the batch both favour B and both come from **A-side structural collapse**: **w1** (A 4.0 vs B 8.5) — A duplicated Park Street Church and reported 6 stops for a 5-stop request; and **d1** (A 4.5 vs B 7.0) — A had a severe mid-clause text collision in stop 1. A also duplicated a stop in w3 (4.5) and w4, and collided sentences in d2's stop 3. In this P1 batch the duplicated-stop / garbled-sentence defects landed on the **expensive (A) arm**, the opposite of the Oct-9 observation, which pulls A's walking and dining means down.

## Recommendation per category

Rule (from Oct 9): **switch to B only if B's mean is within 0.3 of A's AND B's floor is not worse.** Otherwise keep A, or call it unclear when the sample is too thin.

- **museum (n=4): keep A.** B is within range on the mean (−0.12) and B's floor is actually *higher* (7.0 vs 6.5), so the rule would permit a switch — but the two −1.0 flags (m3, m4) show A still wins the top end on true-to-collection accuracy, and museums are the category the cheap arm was always meant for, so this is the one to confirm with more samples before switching. Leaning switchable, but **confirm (museum is the strongest B case; cost −50%).**
- **walking (n=4): keep A — but the result is noisy.** B's mean is *higher* (+1.38) and B's floor is higher (5.5 vs 4.0), which by the rule would say switch. That inversion is driven by A-side structural collapse (w1, w3, w4), not by B being genuinely strong — B's own walking tours still show dropped-name/garbled clauses (w3, w4). This contradicts the Oct-9 finding that Serper research weakens walking. **Do not switch on this evidence; re-run after the A-side duplication/collision bug is understood — the two arms are not cleanly separated here.**
- **neighbourhood (n=2): switch to B — tentatively.** Mean +0.25 (inside 0.3), B floor higher (7.5 vs 7.0), cost −57%. Only 2 samples, so **switch is defensible but confirm with more.**
- **dining (n=3): unclear — needs more samples.** Mean +0.33 is just over the 0.3 bar and the pairs disagree sharply (d1 +2.5 from A collapse, d3 −1.5 from B's Permian fabrication). B's floor (5.5) is above A's (4.5) only because of A's d1 collision. Mixed failure modes on both sides → **hold A, gather more.**
- **business (n=1): unclear — needs more samples, and fix stop-count first.** B is 3.0 worse and under-delivered (1/3 stops), but A also under-delivered (2/3). n=1 and both arms broken → **keep A; the real bug is the stop-count shortfall, not the arm.**
- **driving/nature (n=2): keep A.** r1 ties (8.0/8.0) but r2 is a −1.5 B flag (duplicate building + off-topic Rose Garden). B's floor (5.5) is clearly worse than A's (7.0), failing the floor test. Cost −62% is tempting but quality floor fails → **keep A.**

### Bottom line
Overall the two arms are a near-tie on mean quality (**A 6.66, B 6.78**) at **half the cost** for B (−49%). But the averages hide opposite failure modes: **A** suffered structural collapses (duplicated stops, 6-stops-for-5, mid-clause collisions) in several walking/dining tours; **B** suffered off-topic fabrications and relevance drift (Permian extinction in d3, reality-TV in b1/d3-area, repeated building in r2) and one hard under-delivery (b1). The only category where B is both cheaper and not-worse at the floor is **museum** (and, thinly, **neighbourhood**). Per the floor rule, **B is a safe switch candidate only for museums**; everywhere else keep A until (a) the A-side duplication/collision defect is diagnosed so walking/dining can be compared cleanly, and (b) B's off-topic-fabrication and stop-count failures are fixed. No category meets the switch rule strongly on this n; treat museum/neighbourhood as "switchable, confirm with more samples" and the rest as keep-A / unclear.

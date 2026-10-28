# SUBMISSION — LOCAL-P1S

**Task:** P1 blind quality scoring — 16 tour pairs, expensive vs cheap setup, no paid API calls.
**Branch:** `LOCAL-P1S-scoring` (base `subscribed` = 6e7eaee1; `git merge-base --is-ancestor 6e7eaee1 HEAD` exits 0, re-checked after the commit).
**Paid-API spend:** **$0** — no model calls from code; scoring only, no containers.
**Commit:** 081a3798.

## What I did

1. **Copied** `p1/out/{A,B}_<id>.json` and `p1/requests.json` into this worktree (originals under `/Users/micha/Audioura/p1` untouched; I did not copy the large `tours/` dir, which is not needed). All 32 inputs are `status=completed`, **including the re-run pair A_r1 and B_w2 — no pair was skipped.**
2. **Blinded** each pair into `p1/blind/<id>_X.txt` / `_Y.txt` with a random per-pair X/Y assignment (`p1/blind_setup.py`, seed 20261028; X=A in 7 pairs, X=B in 9). The text files carry no arm label.
3. **Scored** all 32 texts 0–10 against the Oct-9 house rubric (real/fabricated places, factual accuracy, specific story quality, cross-stop connection, directions/pin plausibility, garbled sentences, length) with one reason each, written to `p1/blind/SCORES.json` **before** `KEY.json` was opened.
4. **Unblinded** and wrote `p1/P1_RESULTS.md`: per-request table (A/B score, $, s), per-category means/mins/diffs, flags, and a per-category recommendation using the Oct-9 rule (switch to B only if B's mean is within 0.3 of A's **and** B's floor is not worse).

## Headline result

- **Overall (n=16):** A (gpt-4.1 + Gemini) mean **6.66**, B (gpt-4.1-mini + Serper) mean **6.78** — effectively a tie (+0.12 for B) at **−49% cost** for B ($0.607 → $0.310 mean/tour).
- **Switch candidate by category: museum only** (B within range, B floor higher, −50% cost), and **neighbourhood** thinly (n=2). **Keep A** for driving/nature (B floor fails: r2 5.5 vs 7.0). **Walking** and **dining** are unclear/noisy. **Business** is n=1 and both arms under-delivered the stop count.
- **Failure modes were opposite per arm this batch:** the *expensive* A arm produced the structural collapses — duplicated stops / 6-stops-for-5 / mid-clause collisions (w1 A 4.0 vs B 8.5; w3; w4; d1 A 4.5 vs B 7.0). This is the **reverse** of the Oct-9 observation, and it is what drags A's walking/dining means down. The *cheap* B arm's failures were off-topic fabrications (d3 Permian-extinction paragraph, b1 reality-TV digression) and a repeated building (r2).
- **Flags (B ≥ 1.0 worse):** m3, m4, d3, b1, r2 — detailed in `p1/P1_RESULTS.md`.

## Caveat

Small n per category (1–4). The A-side duplication/collision bug confounds the walking and dining comparison — those two arms are not cleanly separated here and should be re-run once that defect is diagnosed. B's off-topic-fabrication and stop-count shortfalls (b1 1/3 stops) should be fixed before any switch beyond museums.

## Artefacts
- `p1/blind/` — 32 blinded texts + `KEY.json` + `SCORES.json`
- `p1/blind_setup.py` — reproducible blinding (seed 20261028)
- `p1/P1_RESULTS.md` — full tables, flags, recommendations
- `p1/out/`, `p1/requests.json` — copied inputs (for reproducibility)

## Process compliance
- Committed to `LOCAL-P1S-scoring`; **no `git add -A`** — staged 69 explicit paths, all under `p1/`.
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, or TRAVEL_PROJECTS.md. No `DELETE`.
- Branched from HEAD (local, not `origin/*`); base ancestor check passed before and after commit.

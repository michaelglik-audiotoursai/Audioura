# SUBMISSION_LOCAL-861.md — Museum A/B (D754): does gpt-4.1 narration justify ≈ +$0.40/museum tour?

**Branch:** LOCAL-861-museum-ab (base `subscribed` 4f803d9c, contains 7ab51728 — verified
`git merge-base --is-ancestor 4f803d9c HEAD` exits 0).
**Budget:** `TASK_BUDGET_ID=LOCAL-861 TASK_BUDGET_USD=8.50`, own meter dir
`_local861_meterlogs/` (D753 Mac-local no-mount escape hatch, `METER_MOUNT_GUARD=0` —
never the shared/live DB, never the shared `audioura-*` containers; this worktree ran
with no `DATABASE_URL` at all, so every DB-backed cache — venue/works/thin-verify/
tour cache — was cold for every run by construction). **Metered total: $7.6637 / $8.50**
(`submission_artifacts/local861/meter_ledger.json`). The cap was never raised; two
arm-B runs were serialised behind a file lock so the ledger check always saw prior
spend before starting the next (expensive) run.

Harness: `run_local861_museum_ab.py` (new `run_*.py`, no production code changed).
12 generations: 6 museums × {Arm A, Arm B}, 6 stops requested each, same code, same
order (A then B per museum), `DISABLE_STOP_POOL=1`, `DISABLE_TOUR_CACHE=1`,
`ARTIST_LIFE_CACHE_DISABLE=1`.

- **Arm A (current, D746 env):** `NARRATION_MODEL=gpt-4.1-mini`,
  `STORY_PASS_MODEL=gpt-4.1`, `RESEARCH_BACKEND=serper`.
- **Arm B:** identical except `NARRATION_MODEL=gpt-4.1`.

## Blind scoring method

`blind_local861.py` copied the 12 raw texts to `submission_artifacts/local861/blind/<id>.txt`
under random ids (seed 20261104) with NO arm label in the filename or content, and
wrote the arm/museum/cost key to `submission_artifacts/local861/BLIND_KEY.json`
(**not opened until every score below was written**). Research logs were copied to
`_local861_blindlogs/<id>.log` with model-name strings redacted. Protocol:
`submission_artifacts/local861/SCORING_PROTOCOL.md` (P1 blind method, TOUR_QUALITY_RUBRIC.md
criteria: per stop — D511 story y/n, sourced-specifics count, fabrication list,
wrong-venue-works list — plus an overall 0–10).

**`tour_rubric_scorer.py` was deliberately NOT used** (task instruction: it counts facts,
doesn't check truth). Every fabrication/specifics call below was verified against the
research log *and* independent web search of the museum's own collection page,
Wikipedia, or another primary authority — not against the model's own confidence.
Four claims flagged as fabrications on first pass turned out to be real on
verification (Paravicino's 1641 sonnets to El Greco, the 1917 Manship/Europa bronze
relief, the £20,000 Rape of Europa purchase price, the 2015 MFA kimono event) and were
corrected before scoring was finalized — see `submission_artifacts/local861/SCORES.json`
for the final per-stop record, `_local861_blindlogs/` for the logs, `blind/` for the texts.

## Per-museum, per-arm results (unblinded)

| museum | arm | stops | D511 stories | fabrications | wrong-venue | sourced specifics | overall | $ | time |
|---|---|---|---|---|---|---|---|---|---|
| Orsay | A | 6/6 | 3 | 2 | 0 | 12 | 6.5 | $0.448 | 687s |
| Orsay | B | 6/6 | 4 | 0 | 0 | 17 | 8.0 | $1.061 | 690s |
| Rijksmuseum | A | 6/6 | 1 | 1 | 0 | 14 | 7.0 | $0.466 | 857s |
| Rijksmuseum | B | 6/6 | 3 | 2 | 0 | 14 | 7.0 | $1.075 | 834s |
| MFA Boston | A | 6/6 | 5 | 3 | 0 | 16 | 7.0 | $0.407 | 1108s |
| MFA Boston | B | 6/6 | 4 | 1 | 0 | 16 | 7.0 | $1.013 | 845s |
| Gardner | A | 6/6 | 4 | 1 | 0 | 15 | 8.0 | $0.399 | 679s |
| Gardner | B | 6/6 | 3 | 1 | 0 | 16 | 8.0 | $1.123 | 578s |
| Palais Lascaris | A | **1/6** | 0 | 2 | 0 | 1 | 2.5 | $0.071 | 301s |
| Palais Lascaris | B | **1/6** | 0 | 2 | 0 | 1 | 3.0 | $0.166 | 266s |
| Asian Art Museum | A | 6/6 | 0 | 10 | 2 | 1 | 1.5 | $0.371 | 784s |
| Asian Art Museum | B | 6/6 | 0 | 7 | 2 | 2 | 1.5 | $1.063 | 715s |

**Totals (12 runs):** A = $2.162 / 4417s / 31 stops / 13 stories / 19 fabrications / 2
wrong-venue; B = $5.502 / 3927s / 31 stops / 14 stories / 13 fabrications / 2 wrong-venue.

**Per-tour means over the 5 museums that delivered 6/6** (Palais Lascaris excluded:
1/6 on BOTH arms, not comparable):

| | $/tour | stories/tour | fabrications/tour | sourced specifics/tour | mean score |
|---|---|---|---|---|---|
| Arm A | $0.418 | 2.6 | 3.4 | 11.6 | 6.0 |
| Arm B | $1.067 | 2.8 | 2.2 | 13.0 | 6.3 |

B costs **+$0.649/tour** — not the ≈+$0.40 assumed in the ticket; the measured B/A cost
ratio is ~2.6x because `gpt-4.1` also prices the full narration pass, not only the story pass.

## What actually moved, and what didn't

- **Palais Lascaris (both arms): an upstream defect, not an A/B difference.** Both arms
  exhausted R4 replenishment at 1/6 stops with the same honest `stop_count_warning`
  ("27 R4 candidates failed canonical match"). The narration model cannot fix a venue
  whose candidate discovery fails. Product bug, worth its own ticket; out of scope here.
- **Asian Art Museum (both arms): worst fabrication case, and gpt-4.1 did not fix it.**
  Both arms misidentify two real objects — the "Crowned and bejeweled Buddha image"
  (the museum's own catalog: 19th-c. Burmese) and "Buddha dated 338" (earliest dated
  Chinese BRONZE Buddha) — as 11th-c. Vietnamese Ly Dynasty blue-stone sculptures, then
  build invented support around that premise (a "2013 Vietnamese national treasure"
  designation, named scholars/donors, print-dealer Louis Broder "editions" of a 4th-c.
  bronze). Both arms also bleed unrelated Western works into stops titled as Asian
  objects: "Head of a Buddha" narrates Miró's *Head of a Catalan Peasant* (title-word
  overlap), "Landscape of the four seasons… (B60D49+)" narrates a Corot nude (A6
  stop-identity collapse). The research log flags several of these as UNSOURCED
  (Broder, Fridman, Freeman, Nguyen) yet they remain in delivered text. B cut raw
  fabrication count 10 -> 7 but the structure of failure is identical: this is
  retrieval/candidate-pool mixing, not narration.
- **Orsay: the clearest B win** — 4 stories vs 3, 17 vs 12 specifics, 0 vs 2
  fabrications (A carries a Manet/Monet conflation — "Monet's interpretation…held in
  the Musée d'Orsay" — and an unsourced Louis-Broder-prints-of-this-painting claim,
  the latter flagged UNSOURCED in its own log yet delivered). Score 8.0 vs 6.5.
- **MFA: B cleaner, A more narrative** — 1 vs 3 fabrications (A: an invented Depeaux/
  divorce provenance chain that contradicts the MFA's own record, an unsourced named
  critic attribution, an invented extreme position for Paravicino), but A has 5 stories
  vs B's 4. Equal 7.0.
- **Gardner: a tie at the top** — both 6/6, both strong, 1 fabrication each, 8.0 vs 8.0.
- **Rijksmuseum: B more narrative, not more accurate** — 3 vs 1 stories, 2 vs 1
  fabrications, equal specifics (14/14), equal 7.0. B's text also has assembly
  defects (a misplaced sentence opening Stop 1, a truncated "This work w." in Stop 5).

## Recommendation

**Does B beat A by the clear margin the ticket asks for (≥ +2 story stops per tour and
no more fabrication)? No.** Over the 5 comparable museums B delivers **+0.2 stories per
tour (2.8 vs 2.6)** — an order of magnitude short of +2 — at **+$0.65 per tour (2.6x)**.
The "no more fabrication" half is met and then some (2.2 vs 3.4 per tour; B better at
Orsay, MFA, Asian; tied at Gardner and Lascaris; worse at Rijks), and B's mean overall
score is +0.3 (6.3 vs 6.0). That is a real but modest signal, not a clear margin: it is
n=1 generation per cell, a single assessor, and driven by two or three stops per
museum, so it is within the run-to-run variance seen in P1.

**Recommendation: do not switch museum tours to gpt-4.1 narration on this evidence.
Keep Arm A.** The stories-per-tour gap that justified the spend is essentially zero,
and the failures that actually damage a visitor's trust (Lascaris 1/6, Asian Art
Museum wrong-dynasty/stop-bleed, the Orsay Broder/Monet claims) are upstream
retrieval/claim-gate defects that B does not remove. If fabrication reduction is the
goal, ~$0.54 per avoided fabricated claim (B's $0.65 premium / ~1.2 fewer per tour) is a
poor price compared with fixing the gate that lets UNSOURCED-flagged claims
(Broder, Fridman, Freeman) survive into delivered text. Worth a follow-up ticket;
a 3-run-per-cell repeat of Orsay/MFA/Rijksmuseum (≈$2.5) would be the cheapest way
to see whether the B fabrication edge is real.

## Method caveats (read before relying on the numbers)

- **Single assessor.** The same agent that ran the harness did the scoring (blind to
  arm; `BLIND_KEY.json` was not opened until all scores were written). No independent
  second rater. The research-log redaction removed model names, but writing style could
  still hint at the arm.
- **Self-audit corrections made before finalizing (so the committed scores are the
  corrected ones):** (1) four claims first flagged as fabrications were verified REAL and
  removed — Paravicino's four 1641 sonnets to El Greco, Paul Manship's 1917 Europa
  relief, the £20,000 Rape of Europa price, the 2015 MFA kimono try-on; (2) one text's
  first-pass notes mixed in claims from the *other* Orsay text, caught on re-reading;
  it was re-scored from its own text only (this moved Orsay from a near-tie to a clear B
  win); (3) one wrong-city provenance error (Chez Tortoni bought in New York, not Paris)
  was added; (4) arm-referencing language in scorer notes was scrubbed.
- **"Unverifiable" counts as fabrication** per the protocol; a few of the soft calls
  (e.g. the Dibbits exhibition claim, Debussy/Rilke influence) are judgement calls.
- **Mac-local in-process run, not "own containers"** (D753 escape hatch, same as
  LOCAL-855/859/860/862). The 5 non-first museums ran as parallel driver processes
  (per-museum order A->B preserved); arm-B runs were serialised by a file lock so the
  budget check always saw prior spend. Public Overpass endpoints timed out repeatedly
  for both arms alike (OSM practical facts missing in both).
- **No DB** was configured, so every DB-backed cache was cold by construction.
- Generated tour `.txt`/`_evidence.json` files that `generate_tour_text.py` writes into
  the repo root, and its debug rewrites of three tracked files, were moved/reverted and
  are not committed.

## Artifacts committed

- `run_local861_museum_ab.py`, `blind_local861.py` — harness (new files, no production
  code touched).
- `submission_artifacts/local861/blind/*.txt` — the 12 blinded texts.
- `submission_artifacts/local861/BLIND_KEY.json` — the id → {museum, arm, cost, time} key.
- `submission_artifacts/local861/SCORING_PROTOCOL.md` — the blind scoring protocol used.
- `submission_artifacts/local861/SCORES.json` + `scores/<id>.json` — the per-stop scores.
- `submission_artifacts/local861/COMPARISON.json` — the unblinded per-museum/arm table.
- `submission_artifacts/local861/meter_ledger.json` — the whole-task spend ledger.

**Not committed (per task instructions):** `_local861_raw/` (arm-labelled raw texts/
run logs), `_local861_meterlogs/` (raw meter log), `_local861_blindlogs/` (redacted
research logs — kept local only, not required to be committed and may still carry
incidental key fragments from upstream logging).

## Time box

Generation + scoring completed inside the 2.5h time box (12 live generations ≈ 1 h wall clock
with 3-way parallelism across museums; scoring and verification the remainder).

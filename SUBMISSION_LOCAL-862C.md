# SUBMISSION LOCAL-862C — polish the D760 layers

Branch `LOCAL-862C-layer-polish`, from `subscribed` 552b37fb (`git merge-base --is-ancestor 552b37fb HEAD` → 0).

## What changed
| # | Defect (862B tour) | Fix | Where |
|---|---|---|---|
| 1 | Rambutan legend: marker repeated per sentence, incoherent. Longan: one-sentence fragment | A legend is **one block**: 2–4 whole sentences, no dangling-pronoun opening, no ellipsis, and the **last sentence must name the word** (ties to the name). Otherwise it is omitted at the fact level, so the narrator never sees a fragment. A surviving legend is inserted verbatim with the disclosure **once** on its first sentence; `ensure_disclosure` no longer re-prefixes continuation sentences. The verifier gates a legend block as one unit (continuations ride on the marker) and drops it all-or-nothing | `user_stop_context.py` (`legend_block`, `legend_block_text`, `apply_legend_blocks`, `gate_body`, `enforce_legend_blocks`), `user_stop_verify.py` |
| 2 | No bridge from name to venue | `bridge_sentence`/`insert_bridge`: "The *bar* probably takes its name from …" when the Places kind is known, else "Its name probably comes from …" (always hedged with "probably"). Inserted before the first name-meaning sentence, added to the verifier's source lines | `user_stop_context.py`, `user_stop_enrichment.py` |
| 3 | "Đề Thám Street, which along with Phạm Ngũ Lão and Đề Thám Streets" | `dedupe_names`: drops the repeated item from a list inside one sentence | `user_stop_context.py` |
| 4 | Thi Bar (a gay bar) called "a popular live music venue" | `attribute_story` (story facts) + `kind_guard` (narrated body): a description that disagrees with the Places category's distinguishing words becomes "reviews describe it as …" / "according to reviews, …". Prompt rule added: kind comes only from the Places category | `user_stop_context.py`, `user_stop_enrichment.py` |

## Live run (ONE full 7-stop Sophia run, own meter dir, Mac-local per D753)
`TASK_BUDGET_ID=LOCAL-862C TASK_BUDGET_USD=0.35`, `run_local862c_live.py`. LiveRunMeter total **$0.2672** (openai $0.2342, serper $0.0330) of the $0.35 cap; the per-call ledger shows $0.054. Artifacts: `submission_artifacts/local862c/{live_tour_7stops.txt,enrichment_report.json,meter_ledger.json}`. No run logs committed.

PASS criteria, read against the delivered text:
- **Every legend one coherent disclosed block** — PASS. No legend is told: the Rambutan source never returns to the name and the Longan source is a fragment, so both are omitted (the rule's "otherwise omitted entirely"). No repeated markers, no fragments.
- **Name-based stops have a bridge** — PASS: Rambutan, A Star is Born, Longan.
- **No duplicated list items** — PASS (Thi Bar no longer repeats Đề Thám).
- **No stop under 4 sentences** — PASS (5, 5, 5, 5, 7, 6, 6).
- **No undisclosed invented venue fact** — PASS on a full read. A Star is Born keeps its disclosed "We couldn't confirm this…".

## Honest caveats
1. **Two tweaks were made after the live run and verified by offline replay, not live**, because the single live run used $0.267 of $0.35. They are the bridge wording (the live run said `Its name probably comes from the word "Rambutan"`, which is circular; final code says "…from the rambutan fruit") and `kind_guard` (the live Thi Bar still said "is known as a live music bar"; final code gives "…and reviews describe it as a live music bar"). Replay: `run_local862c_replay.py`, output in `submission_artifacts/local862c/replay_output.txt`.
2. **Stop 7 (Acoustic Bar) has no Coordinates/Type lines in the live output.** The block was already mangled before enrichment (LOCAL-540 self-contradiction gate, then LOCAL-474 retry "271w → 57w"; log lines ~1390/818), so there was nothing for the enrichment step to preserve. The 862B tour had them. This is generation variance outside this task; not fixed here and worth its own ticket. The pin itself was kept (`user pin kept 'Acoustic Bar' 10.781195, 106.689920`).
3. The runner's old "pins within 30 m" check therefore shows FAIL for Stop 7 only; `--check-only` re-runs the 862C checks on the saved output with no spend.
4. Because both legends are now omitted, the live run does not exercise a *kept* legend block. That path is covered by unit tests only (`tests/test_local862c_polish.py`, `tests/test_local862b_layers.py`: 80 passed).

## Tests
`python3 -m pytest tests/test_local862c_polish.py tests/test_local862b_layers.py tests/test_local862_user_stop_enrichment.py` → 80 passed. Four 862B fixtures were updated: they used one-sentence or untied legends, which is exactly what this task makes illegal.

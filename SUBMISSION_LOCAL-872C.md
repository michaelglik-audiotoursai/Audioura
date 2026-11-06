# SUBMISSION LOCAL-872C: Wikipedia evidence → narrator; contradiction beats disclosure; never an empty stop

Branch `LOCAL-872C-wiki-to-narrator`, from HEAD = subscribed `768f8c55`
(`git merge-base --is-ancestor 768f8c55 HEAD` exits 0).

**Status: code + tests done. Live: two full 10-stop runs were made. Both had gaps that
I then fixed, and the final code was proved by (a) a deterministic replay of the final
gate over BOTH live runs' delivered text and (b) two single-stop live runs on the final
code.** No third and fourth full run was possible: the two full runs cost $0.2285 and
$0.2070, and the $0.50 cap left $0.06. Read "Live" before accepting.

## Change

1. **Evidence → narrator** (`generate_tour_text.py`, `landmark_wikipedia_evidence.py`).
   For landmark-kind stops (every walking stop; user stops only when
   `classify_stop_kind == 'landmark'`), the stop's Wikipedia lead + infobox (en + local)
   goes into the narration prompt as a `PRIMARY SOURCE` block. The block has a
   `KEY FACTS YOU MUST STATE` line (dates with what each marks, architects), says to state
   and attribute them plainly, use them exactly, and never substitute a year or architect
   from memory. It also overrides the user-stop "no sourced history" note. The fetch is
   memoised (`cached_evidence`), so the narrator and the gate read the SAME lookup. The
   poi carries `_wiki_evidence`, so `has_sourced_material`/`has_dated_source` count it.
   Kill switch: `LANDMARK_WIKI_NARRATOR=0`.
2. **Contradiction beats disclosure** (`landmark_claim_gate.py`). The gate gets
   `stop_authority` (the Wikipedia items) and `authority()` extracts the built/opened
   years (ranges expanded) and the architects.
   - An unsourced year on a built/opened/completed verb that is NOT in the evidence's
     years, or an unsourced person in a design sentence when the evidence names the
     architect, is a `contradiction`. It is DROPPED, never disclosed, and replaced by the
     evidence's own sentence (e.g. "It was designed by Ngô Viết Thụ and built from 1962
     to 1966.") unless the body already states it.
   - A construction range inside but narrower than the evidence's range is corrected to
     the evidence range.
   - Evidence establishment/start dates the stop omits are added once
     ("According to Wikipedia, it was established in 1863."). If the stop states none of
     the evidence dates, all of them are added. Placement: after the first prose sentence
     with an evidence year, never in Directions.
   - Claims the evidence neither supports nor contradicts keep the 872B disclosure.
     Without authority, behaviour is unchanged.
3. **Never an empty stop**. `fill_empty_stops` runs inside the gate and as the LAST pass
   of `generate_tour_text`, after 855B/862/855D, on every stop including business user
   stops. A stop with no narration sentence (Orientation/Directions/labels do not count)
   gets the Wikipedia short form (2–4 lead/infobox sentences), else the D759
   `grounded_user_stop_body`, else a minimal name-and-place body. It is inserted before
   Directions and is idempotent.

Tests: `tests/test_local872c_wiki_to_narrator.py` (14). They cover "built in 1885"
against 1962–1966 (dropped, corrected, no "sometimes said"), a wrong architect replaced,
an unrelated 1990 renovation still disclosed, Notre-Dame 1877–1880 → 1863–1880, the
Bạch Đằng Pier live shape (Orientation + Directions only) filled before Directions, and
idempotence. The 872/872B/864/855/863 suites pass (555 passed, 24 skipped in the related selection, on the final code).

## Live (own postgres `local872c` :55973, torn down; cheap arm; `TASK_BUDGET_ID=LOCAL-872C`, $0.50)

Meter: $0.4505 total (run1 $0.2285, run2 $0.2070, Notre-Dame-only $0.0050, Pier-only $0.0100).

| criterion | run1 live | run2 live | run1 final-code replay | run2 final-code replay |
|---|---|---|---|---|
| Opera House: Olivier/Guichard/Ferret + 1900 | PASS (all three + 1900) | PASS | PASS | PASS |
| Independence Palace: Ngô Viết Thụ + 1962/1966, no 1885 | PASS (Thụ, 1962, 1966)¹ | PASS | PASS | PASS |
| Notre-Dame 1863–1880 | FAIL ("1877 and 1880") | FAIL (1880 only) | PASS | PASS |
| no empty body | FAIL² (Pier, Thi Bar) | FAIL² (Pier) | PASS (filled, grounded) | PASS |
| no Miss Saigon | PASS | PASS | PASS | PASS |
| checker 0 undisclosed + re-check 0 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |

¹ The runner's check printed FAIL because its accent folding was buggy (fixed). The text
says "designed by architect Ngô Viết Thụ… Completed on October 31, 1966… 1962".
² My first emptiness check counted the Orientation line as narration. With the stricter
check (the one now in the code), both live runs had empty user stops. The 862 thin path
had left them as Orientation + Directions.

Why Notre-Dame failed live: the en Wikipedia lead itself says "constructed between 1877
and 1880". 1863 is only in the infobox (`established: 1863`), so the narrator faithfully
wrote 1877–1880. The fix states the infobox date as attributed fact.

Final-code proof:
- `submission_artifacts/local872c/replay_check.py` applies the final gate (authority +
  fallback + last-pass fill) to each run's live delivered text and its saved evidence.
  Both exit 0. The LOCAL-864 checker on the replays shows 0 undisclosed.
- Live Notre-Dame only, final code: PASS, 1863 and 1880 stated.
- Live Bạch Đằng Pier only, final code: the last pass logged
  `[LOCAL-872C] stop 1 had NO body: filled with grounded short form`; non-empty, PASS.
  (The Opera House "missing" FAIL in single-stop runs is expected.)

Not proved live: a full 10-stop run of the final code. The narrator-prompt change (the
part that varies run to run) was live in both full runs, and both gave the Opera House
architects + 1900 and Independence Palace Ngô Viết Thụ + 1960s. The later changes are
deterministic post-passes, proved by replay.

Committed texts: `submission_artifacts/local872c/run{1,2}_live_delivered.txt`,
`run{1,2}_final_code_replay.txt`, `notredame_live_final_code.txt`,
`pier_live_final_code.txt`. Run logs (`_local872c_meterlogs/`) are not committed.
Runner: `run_local872c_live.py`, `docker-compose.local872c-proof.yml`.

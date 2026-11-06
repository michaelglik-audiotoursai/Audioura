# SUBMISSION LOCAL-872: landmark / walking claim gate ("Miss Saigon" at the Saigon Opera House)

Branch `LOCAL-872-landmark-claim-gate`, based on subscribed `05335197`
(`git merge-base --is-ancestor 05335197 HEAD` exits 0).

**Status: code and tests done; live proof is PARTIAL.** The full 10-stop run on the
final code did not fit the $0.40 budget (see "Live"). Read that section before accepting.

## 1. Where did the Miss Saigon sentence come from?

I could not establish this from a log. The GCloud_Storied_1 run log (tour 544) is not in
this worktree, so I cannot cite it. What I can say from my own runs:

- The research evidence the walking path hands the gate for the Opera House stop (snippets,
  D556 story facts, LOCAL-47 retrieval facts) never contains "Miss Saigon". Run 1's
  Opera House evidence was one snippet ("built in 1911 and designed by Eugene Ferret to
  serve 500 guests"); none of the three local Opera House runs mentions it in evidence.
- Miss Saigon did not recur in any of my three local runs (stochastic), so I could not
  catch the sentence being generated.
- So it is not a snippet. By elimination it is the model's memory, from the narrator or
  the story pass. The prompts allow it: the walking path says "the model can use its own
  knowledge" when retrieval is thin (LOCAL-72 comment in `generate_tour_text.py`).
  I cannot say which of the two passes wrote it.

## 2. Change

- `landmark_claim_gate.py` (new). Reuses the LOCAL-864 `museum_claim_gate` primitives
  (sentence split, D760 `is_disclosed`, stop headers, tail cut, dangling-pronoun
  cleanup). A sentence is dropped when it makes an unsourced claim of these kinds:
  - **named production / performance**: the show needs ONE source item that names both
    the show and the venue within 250 characters. A source about the show alone, or the
    venue alone, does not count. Venue aliases: the full title and its last two words
    ("Saigon Opera House" -> "opera house"), plus user aliases.
  - **named person doing something checkable** (architect, designer, performer,
    conductor...): the surname must be in a source. A lone surname counts only after
    "by" or a role word. Place names ("Ngoc Son Temple") and style words
    ("Gothic and Renaissance") are not people.
  - **named event** (festival, conference, treaty, battle...) and **named work** (film,
    novel, song...): the name must be in a source.
  - **dated claim**: a year attached to a built/opened/staged/... verb must be in a source.
  A disclosed sentence ("It is sometimes said...") is kept. A sentence whose claims are all
  sourced is kept (built in 1900 by Eugène Ferret, when a source says so). Pronoun
  sentences left dangling by a drop go with it.
- `generate_tour_text.py`: runs the gate for every non-museum tour, on user stops and
  ordinary walking stops, right after the LOCAL-864 museum gate. It runs again on the final
  text before the LOCAL-855B scrub, because later passes rewrite the text.
  - Evidence: `_DIRECT_SNIPPETS_PER_STOP` (includes D556 story facts), LOCAL-47
    `retrieval_facts` and category context, and `_lore`.
  - Business-kind user stops are skipped here. LOCAL-855D verifies them
    (`classify_stop_kind != 'landmark'`).
  - Each drop is logged as `[LOCAL-872] stop N DROPPED (...)` plus `UNSOURCED: '<span>'`,
    the form `submission_artifacts/local864/check_unsourced_vs_text.py` reads.
  - Kill switch: `LANDMARK_CLAIM_GATE=0`.
- `run_local872_live.py`, `docker-compose.local872-proof.yml`: budget-enforced runner and
  own postgres (project `local872`, :55972, torn down after).

Known cost: a true fact that no source for the stop holds is dropped as well. The run-1
replay shows Notre-Dame "1877-1880" and Independence Palace's architect going this way
when the research lacked them. This is what the ticket asks for ("not supported by the
stop's research log").

## 3. Tests

`tests/test_local872_landmark_claim_gate.py`, 18 pass:

- the exact Miss Saigon sentence is dropped;
- "Built in 1900 by Eugène Ferret..." is kept when sourced, and an unsourced year or
  architect is dropped;
- a disclosed "It is sometimes said that the Opera House staged productions of Miss
  Saigon." is kept;
- a show-only or venue-only source is not enough, and a source naming both keeps the
  sentence;
- the "opera house" alias works, and quoted titles are checked;
- the dangling "This production..." sentence goes with its parent;
- performers and events: unsourced is dropped, sourced is kept;
- plain description and the Coordinates/Address/Orientation labels are untouched;
- the business-stop skip works end to end;
- the gate is idempotent, and a sourced Opera House body still has >= 5 sentences;
- place names, style words and possessives do not trigger (the false positives the live
  runs exposed);
- `generate_tour_text.py` is wired for the walking path.

Regression: 214 pass across the 864/855/855b/862/862b/867/864b suites plus this one.

## 4. Live (TASK_BUDGET_ID=LOCAL-872, cap $0.40, metered $0.3354; own DB, cheap arm)

| Run | What | Result |
|---|---|---|
| import10 (run 1) | Michael's 10 stops | Gate dropped 6 sentences. Check FAILED: 2 undisclosed "UNSOURCED" hits. Both were gate false positives ("Renaissance" and "General" read as people), and the Opera House possessive "Saigon's" read as a production. Opera House: 10 sentences, Ferret kept. No Miss Saigon in the text. Cost $0.2169. |
| hanoi | "Old Quarter walk, Hanoi", 4 stops | 4/4 delivered. Gate dropped 0 (nothing unsourced). Log-vs-text checker: 0 undisclosed. $0.0941. |
| opera | Opera House alone, final code | PASS: 16 sentences, "1900" and "Ferret" kept, no Miss Saigon, gate dropped 0, checker 0, re-check 0. $0.0245. |

What is NOT proven:

- **The full 10-stop PASS criterion on the final code was not run.** Run 1 predates three
  fixes: LOCAL-47 retrieval facts were missing from the evidence, style and place words
  were read as people, and possessives were read as places. $0.065 was left, and a
  10-stop run costs about $0.22. I replayed run 1's saved pre-gate text offline with the
  fixed gate, using run 1's partial evidence: 3 drops remain (Notre-Dame 1877 and 1959,
  and Independence Palace's architect), all genuinely absent from that evidence.
- **The Miss Saigon sentence never appeared live**, so "dropped when present" is shown by
  unit test only, not by a live catch.
- In the hanoi run the independent re-check flagged "Ngoc Son" (a place read as a
  person). The pipeline did not drop it, because the stop's `Specific Examples` line
  sources it. I then fixed the person pattern for place nouns and added a test. I did not
  re-run hanoi live.
- The checker `check_unsourced_vs_text.py` only sees claims the gate logged. The walking
  path has no LOCAL-423 verifier, so there are no verifier-flagged UNSOURCED lines. I
  added a second check: re-running the gate on the delivered text against the saved
  evidence (`_recheck` in the runner).

Artifacts: `submission_artifacts/local872/` (delivered texts, run-1 pre-gate text,
`meter_summary.json`). Run logs are not committed.

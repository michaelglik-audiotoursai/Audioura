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

---

# 872B: the gate dropped TRUE famous facts; source them, don't delete them

Same branch (`LOCAL-872-landmark-claim-gate`), `origin/subscribed` already merged (nothing new).

## 1. Evidence first: the stop's Wikipedia article

`landmark_wikipedia_evidence.py` (new). For every stop the gate scans (walking stops and
landmark user stops; business user stops are still 855D's) the evidence now includes the
stop's Wikipedia **lead + infobox** (built / years built / completed / opened / architect /
style / capacity / consecrated, en and vi keys), in **en plus the local language** (vi for
Vietnam, `local_languages()`; fr/es/it/de/pt/ja/th known too).

- Free MediaWiki API, one request per language (two for non-en: the English article's
  interlanguage link is followed, because a Vietnamese title rarely string-matches the
  English stop name).
- The article must name-match the stop (`landmark_second_authority.name_matches`), or give
  the stop's name in its own lead ("Saigon Opera House" is the article "Ho Chi Minh City
  Opera House"). An unrelated page is never evidence (test).
- Cached like the P625 lookup: venue-cache DB, table `landmark_wiki_cache`, 90 d for a hit,
  3 d for a miss; a transport failure is not cached. Kill switch `LANDMARK_WIKI_EVIDENCE=0`.
- Wired in `generate_tour_text.py` next to the 872 evidence build; fetched in parallel;
  logged as `[LOCAL-872B] stop N Wikipedia evidence: K article(s)`.

Real fetches (not mocked): Notre-Dame en infobox `established: 1863; completed: 1880`; vi
`architect: Jules Bourard`. Independence Palace en lead "designed by architect Ngô Viết Thụ",
infobox `completion date: 31 October 1966`. Saigon Opera House en `architect: Félix Olivier`,
vi `architect: Félix Olivier, Ernest Guichard, Eugène Ferret; opened: 1900`.

## 2. Disclosure over deletion (borderline only)

`is_borderline()` / `disclose()` in `landmark_claim_gate.py`. A sentence whose ONLY unsourced
claims are a **date** or an **architect/builder-type person**, in a sentence about the venue's
own history (built, designed, opened, consecrated, restored...) and with **no performance
cue**, is rewritten "It is sometimes said that ..." (D760) instead of dropped. Logged as
`[LOCAL-872B] stop N DISCLOSED (...)`; the checker and the re-check read it as disclosed;
the gate is idempotent.

Still a DROP, as the ticket says: a named production, performer (sang, conducted, starred,
hosted...), event, or work; any sentence that mixes one of those with a date (tests: Miss
Saigon, Callas, a "Saigon Jazz Festival", a conductor, "built in 1901 ... staged Miss
Saigon"). `disclose_borderline=False` restores the 872 behaviour.

## 3. False-positive fixes kept; Hanoi "Ngoc Son" added

All 872 fixes stay (style words, possessives, place nouns). New: a name that any source, or
the stop's own names, gives as "<name> Temple/Lake/..." is a place, so "crowned by Ngoc Son"
(the bare form, which the 872 hanoi re-check flagged as a person) is no longer a claim.
Test: `test_hanoi_ngoc_son_is_a_place_not_a_person`.

## 4. Tests

`tests/test_local872b_wikipedia_evidence.py` (14) plus the 872 file (18):
infobox parsing, local languages, evidence includes lead+infobox, unrelated article refused,
transport failure; Notre-Dame 1863/1959 dropped-before / kept-with-Wikipedia; unsourced
history disclosed and idempotent; Independence Palace architect sourced and disclosed;
Miss Saigon / performer / event still dropped; mixed sentence dropped; Ngoc Son; wiring.
One 872 test changed: it asserted an unsourced "built in 1887 by Pierre Dubois" is dropped;
that is now disclosed by design, so it now uses a performer sentence. Regression
(864/855/862/867/872 suites): 322 pass, 18 skipped.

## 5. Offline replay of the 872 run-1 text, with real Wikipedia evidence

| Stop | 872 (thin evidence) | 872B, no Wikipedia | 872B + Wikipedia |
|---|---|---|---|
| Notre-Dame | dropped 1877/1880 sentence, 1959 sentence | both kept, **disclosed** | both **kept as written** |
| Independence Palace | architect sentence dropped | **disclosed** | **kept as written** |

Not recovered: "General Nguyễn Văn Thiệu ... used this palace as his home" is still dropped.
It is a named person who is neither architect nor builder, so by my reading of the ticket it is
not "borderline"; widening that would let invented people through. Say if you want it widened.
Also still disclosed even with Wikipedia: "Bishop Isidore Colombert laid the first stone"
(not in the article text I fetched).

## 6. Live, final code (TASK_BUDGET_ID=LOCAL-872B, cap $0.60, metered $0.3447; own DB, torn down)

| Run | Result |
|---|---|
| Michael's 10 stops | 10/10 delivered. Wikipedia evidence found for all 6 gated stops (2 articles each). Gate dropped 0, disclosed 0 (first pass and final-text pass). **No Miss Saigon.** Checker: 0 undisclosed. Re-check against the evidence: 0 left. Notre-Dame: "completed in 1880" and "wooden church ... in 1863" are in the delivered text. $0.2156. |
| Independence Palace only | architect Ngô Viết Thụ in the delivered text ("Diệm called upon architect Ngô Viết Thụ"), gate dropped 0. $0.0214. |
| "Old Quarter walk, Hanoi" | 4/4 delivered. Wikipedia evidence for 3 of 4 stops. Gate dropped 0, disclosed 0. Checker 0, re-check 0. $0.1077. |

What I want you to read before accepting:

- **The gate dropped nothing in these runs, so I did not see it disclose anything live.**
  The disclosure and the "dropped before, kept now" results are shown by unit tests and the
  offline replay (section 5), not by a live catch.
- **Notre-Dame "1863-1880" and "1959":** the narrator in this run wrote "completed in 1880"
  and "in 1863" but not "1959" and not the range, so those exact strings are not in the text.
  What it did write was kept. The gate did not remove anything the narrator wrote, but I
  cannot say "keeps 1863-1880" literally.
- **Opera House:** 7 sentences, Ferret kept, but "1900" was not written by the narrator this
  run (the evidence has it). Run 1 had 10 sentences. The pre-gate text had 10, delivered 11, so
  this is narrator variance, not the gate.
- **Runner changed:** it used to fail when a sourced fact was in the evidence but the narrator
  never wrote it. That blames the gate for the narrator. It now fails only when a fact the
  narrator wrote (pre-gate) is gone from the delivered text; otherwise it prints an INFO line.
  By that check the first full run showed two FAILs under the old rule (Independence architect,
  Opera 1900), both "narrator did not write it"; the Independence-only re-run then passed.
- **Hanoi sentence counts vs the 872 hanoi run** (same counter, `[.!?]` followed by space):

  | Stop | 872 run | 872B run |
  |---|---|---|
  | 1 Hoan Kiem Lake | 23 | 20 |
  | 2 Ngoc Son Temple | 17 | 19 |
  | 3 | Bach Ma Temple 15 | Old Quarter 12 |
  | 4 | Dong Xuan Market 18 | Bach Ma Temple 15 |

  Stops 3 and 4 are different places (the generator picks the list afresh each run) and stop 1
  is 3 sentences shorter. The gate dropped 0 here, so none of that is the gate; the pre-gate
  and delivered texts are the same length for the gate's part. I cannot show "no stop thinner"
  as a like-for-like comparison.
- **Outside this gate:** in the 10-stop run, business stops thinned after the gate
  (Book Street 12 to 6, Café Apartments 15 to 8, Bạch Đằng Pier 14 to 3). Those stops are
  skipped by this gate (855D verifies them), so it is not 872B. Flagging it in case it matters.
- The last code change after the live runs: `disclose()` now lower-cases function and adverb
  openers ("Another chapter" -> "another chapter"). No live disclosure happened, so no live
  text was affected; covered by a unit test.

Artifacts: `submission_artifacts/local872b/` (10-stop pre-gate and delivered, hanoi,
Independence-only). Run logs are not committed.

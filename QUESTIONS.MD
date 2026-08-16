# QUESTIONS — Michael's questions, indexed

Created 2026-08-16 at Michael's request.

**What this file is:** a searchable index of the questions Michael has asked, each with
a one-line answer and a pointer to the full evidence. It exists so he can find *his own
question* months later without reading a conversation log end to end.

**How it differs from the other three files:**

| file | holds |
|---|---|
| `STORIED_COMMUNICATION_03.MD` | the conversation, chronological — his words verbatim |
| `QUESTIONS.MD` | **this file** — one line per question, newest first, with pointers |
| `ANSWERS.MD` | the full worked answers, numbered `Q-YYYY-MM-DD-N` |
| `DECISIONS.md` | binding rulings plus the evidence behind them |

Nothing is duplicated: this file points, it does not restate. If a question here has no
`ANSWERS.MD` entry, the answer was short enough to live in the one line.

---

## 2026-08-16

| # | question | short answer | full |
|---|---|---|---|
| 5 | Keep QUESTIONS.MD and STORIED_COMMUNICATION_03.MD current | Done. QUESTIONS.MD created (this file); volume 03 updated each exchange | — |
| 4 | How do I ask a side question without derailing the session? | Prefix `ASK:` (answer only, no tools, no commits) and/or `SIDE:` (different topic, logged separately). Now in CLAUDE.md | CLAUDE.md §"Asking a side question" |
| 3 | Is `BETA_MOBILE_START_HERE.md` pushed so Windows can get it? | Yes — `beta/yuri-bugs` pushed and verified readable from origin. **But `storied` still has 51 unpushed commits, so none of the validator work is on Windows** | Q-2026-08-16-3 |
| 2 | If I clear + restart, can we continue the validator work? | Yes. Everything is on disk and committed: D440–D458, `STORY_GATE_TIERS.md`, `story_validator.py`, volume 03 | Q-2026-08-16-2 |
| 1 | Did you start working on Yuri's bugs? Should I clear now? | **No — zero mobile files touched.** I located the reports and set up a worktree for another session. Clearing now is the cheaper path | Q-2026-08-16-1 |
| — | What are the tiers 1, 2, + and how do we measure? | Tier 0 description gate, tier 1 cheap+strict, tier 2 rescue on shortfall, tier 3 fallbacks. Measured per story / per gate / per tour | `STORY_GATE_TIERS.md`, D456 |
| — | Are all Gemini stories passing? Could some have wrong facts? | No — and coverage is only 13%. Yes, Gemini does produce false facts (the Leonard Woolf claim) | D452 |
| — | Why is the true Boris Fridman claim rejected? | The query is built from misclassified entities and drifts to a different artwork | D453 |
| — | How much false rejection is acceptable? | Do not set a tolerance; make "no usable evidence" a verdict, require zero false acceptance on a labelled FALSE set | D454, and his ruling D455 |

## 2026-08-14

| # | question | short answer | full |
|---|---|---|---|
| 4 | What are the three independent scores for section 1? | historic 31, detail 0, social 50 | Q-2026-08-14-4, D451 |
| 3 | Can the validator pass a good story and catch a false one? | Partly — 3 of 4 tests pass; one true obscure claim is still falsely rejected | Q-2026-08-14-3, D451 |
| 2 | Is our `TRUE_TO_SOURCES` verdict worth anything? | Less than its name suggests — it means "contains no unfamiliar name or year" | Q-2026-08-14-2, D447 |
| 1 | Why is stop 1 silent when the material is there? | Its story keyword is the common noun "book"; every person is struck off for occupying another slot | Q-2026-08-14-1, D441 |

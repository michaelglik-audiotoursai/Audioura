# SUBMISSION — LOCAL-837: cheap-arm museum story pass writes a HUMAN story, not provenance

**Branch:** `LOCAL-837-museum-story-pass`
**Base:** subscribed `82b6f374` (contains `cfcefd89` / LOCAL-832B).
`git merge-base --is-ancestor 82b6f374 HEAD` → exit 0.

---

## The defect (from LOCAL-832B, "What does NOT pass")

On the cheap arm (gpt-4.1-mini) Orsay and Rijks are 5/5 well-formed but **0/5 stops
clear the D511 story bar** (3+ consecutive sentences, one subject, an action, a
stake). Three causes:

1. the story pass mostly wrote **PROVENANCE** — "the museum acquired it", "X
   gifted it" — which carries no stake (scan: `stakes=0`);
2. when it wrote an eventful story the subject was the **ARTWORK itself** ("The
   Night Watch was evacuated… hidden in a bunker"), which
   `story_opportunity_scan.can_carry` refuses by design (`kind=='title'`);
3. the **narration merge** split agency and stakes into different sentences.

## What I changed (the four Do-items, nothing else)

### 1. Story pass → a HUMAN story (`story_pass.py`, `works_mode`)
`build_story_prompt(..., works_mode=True)` and `generate_story_for_stop(...,
works_mode=True)`. On the museum-works path the prompt now:
- demands **ONE NAMED PERSON** as the subject (painter, sitter, patron, dealer,
  thief, curator who hid it, restorer, forger, rival) and says the **work itself
  CANNOT be the subject** — because the artwork enters the scanner as a `title`
  and `can_carry` refuses it;
- states **"PROVENANCE IS NOT A STORY"** — a gift / bequest / acquisition / loan
  is a transfer nobody *did* at a cost;
- keys **`NO_STORY` on "no human event"**: if the only human fact is who owned or
  gave the work, answer `NO_STORY` rather than dressing provenance as a story.

The **default path is byte-for-byte unchanged** (`works_mode=False`): the Pompeii
/ LOCAL-493 prompt still says a place or an event may carry a story, because
there the stop is a site the scanner reads as a `proper noun`/`event` that
`can_carry` accepts. `can_carry` was **not touched**; the scanner was **not
gamed**. The fix writes the one shape the scanner was always going to accept for
an artwork stop: a person acting on it.

### 2. Measure mini vs gpt-4.1 on the SAME research (`run_local837_ab.py`)
The live run writes each stop's already-paid `{matrix, material}` to a JSONL via
the env-gated `LOCAL837_AB_DUMP` hook (no extra spend). The A/B then runs the
story pass ALONE — one call per stop — on that identical research for both
models. **gpt-4.1 extracts a named human agent where mini defaults to the
artwork/"staff" and fails.** The clearest case, same research:

| | story the pass wrote for The Night Watch | clears bar |
|---|---|---|
| gpt-4.1-mini | "…the **staff** faced the threat… **They moved the painting into a cave**…" | **no** (artwork/generic subject) |
| gpt-4.1 | "…**Arie van Schendel, the curator**… **had the painting evacuated**… **Because of this decision, The Night Watch survived** the war" | **CLEAR** |

A/B spend **$0.10 ≤ $0.20**. gpt-4.1 is also *more honest*: it returns `NO_STORY`
on provenance-only research where mini writes a weak non-story.

**Proposal (validated):** `STORY_PASS_MODEL=gpt-4.1` under the cheap arm — it lifts
ONLY the one-call-per-stop story pass; the big per-stop **narration stays on
gpt-4.1-mini**. Added as an opt-in, reversible env override in
`generate_tour_text.py`.

### 3. Narration merge keeps the story together
The story-carry block now says **"KEEP THESE SENTENCES TOGETHER AND IN ORDER, as
one unbroken block at the very start"** and forbids interleaving/reordering
(replacing the old "you may adjust wording to flow" permission that let the cheap
arm dissolve the run). The LOCAL-832B **story-survival re-seat backstop is
unchanged and still wired**.

### 4. Tests (`test_local837_museum_story_human.py`, 21 tests, green)
Built on the 832B fixtures. Assert, through the **real** `story_opportunity_scan`
(and without touching `can_carry`): a human story clears the bar; an
artwork-subject story does not (`can_carry`); provenance does not (no stake); the
works-mode prompt demands a named person + declares provenance-is-not-a-story +
keys `NO_STORY` on no-human-event; the default path is identical to the no-arg
prompt (LOCAL-493 invariants hold); `generate_story_for_stop` forwards
`works_mode` (injected caller, no network); a model `NO_STORY` is recoverable, not
fabricated; survival still re-seats a human story, not provenance.

Full relevant suite: **124 passed.**
(`test_d498::test_summary_says_the_counts_overlap` is a **pre-existing** failure
unrelated to this ticket — the asserted log string is absent at HEAD too, proven
by stashing this branch's changes; not touched.)

---

## Live — BUDGET ENFORCED (`run_local837_live.sh` + `run_local837_container.py`)

Isolated **`local837-*`** containers (never a shared `audioura-*` container),
throwaway postgres seeded from the real cached rows (Orsay Q23402, Rijks
Q190804), `TASK_BUDGET_ID=LOCAL-837 TASK_BUDGET_USD=1.00`, meter contract, cheap
arm, pool off. Two tours + the offline A/B under one cap.

| arm | Orsay clear | Rijks clear | $/Orsay | $/Rijks | whole task |
|---|---|---|---|---|---|
| default (mini story pass) | 0/5 | 1/5 | $0.30 | $0.27 | within $1.00 |
| `STORY_PASS_MODEL=gpt-4.1` | 0/5 | **2/5** (Night Watch + Milkmaid) | $0.29 | $0.32 | $0.72 |

Every tour cost ≤ $0.45; A/B $0.10 ≤ $0.20; whole task $0.72 ≤ $1.00.

**PASS criterion (≥ 3/5 stops clear per tour): NOT MET.** Overall task-6 = FAIL on
the bar. **Costs all pass.** The story-pass change moves Rijks from 0→2/5 and the
A/B validates the gpt-4.1 proposal, but neither tour reaches 3/5.

## Why — root cause, confirmed (not a prompt/model problem)

Inspecting the dumped research that actually reaches the pass
(`reports/local837/research_live.jsonl`): for the works that do NOT clear, the
research is **provenance + metadata, not a narrated human event**:

- **All 5 Orsay works:** "Legs Gustave Caillebotte", "Left by the artist", "oil
  on canvas", "Achat avec le concours", stock-image captions and a blog ("as I
  walked in I thought Viva la France"). No person does anything at a stake. The
  pass **correctly returns `NO_STORY`** on all five — exactly the ticket's rule
  ("if the research has no human event, say so … rather than writing provenance").
- **Rijks stops 4–5:** "Gift of H.W.A. Deterding", catalog metadata — same shape.
  Only Night Watch (wartime cave evacuation) and Milkmaid carry a human event, so
  Rijks caps at 2/5.

The ≥3/5 bar for these two venues is blocked by **research retrieval**
(`SERPER_RESEARCH_MODEL=gpt-4.1-mini` + Serper returning provenance/metadata
snippets), which is **upstream of the story pass** and **outside this ticket's
four Do-items** (story-pass prompt, model A/B, narration merge, tests). Closing it
would require either inventing facts (forbidden) or changing the research layer /
`can_carry` (out of scope / forbidden). I confirmed this across **two full live
runs and the A/B** before concluding, rather than patching toward the number.

## Net

The story-pass defect named in LOCAL-832B is **fixed within its scope**: the pass
now writes a human story where the research supports one, refuses provenance, and
keeps its run intact through the merge; gpt-4.1 clears stops mini cannot and is
the recommended cheap-arm story-pass model. The remaining shortfall to ≥3/5 is a
**research-coverage** gap for these specific works, which this ticket is not
scoped to fix and which cannot be closed honestly here.

## Files

- `story_pass.py` — `works_mode` on `build_story_prompt` + `generate_story_for_stop`.
- `generate_tour_text.py` — `works_mode=True` on the museum path; narration
  "keep together and in order"; env-gated `LOCAL837_AB_DUMP` research capture;
  opt-in `STORY_PASS_MODEL` override.
- `test_local837_museum_story_human.py` — 21 tests.
- `run_local837_ab.py` — offline mini-vs-4.1 A/B on identical research.
- `run_local837_live.sh` + `run_local837_container.py` — isolated live acceptance.
- `reports/local837/` — live logs, `ab_result.json`, `research_live.jsonl` (evidence).

## How to reproduce

```bash
python3 -m pytest test_local837_museum_story_human.py -q          # 21 green
./run_local837_live.sh                                            # default (mini story pass)
STORY_PASS_MODEL=gpt-4.1 ./run_local837_live.sh                   # proposed cheap-arm remedy
```

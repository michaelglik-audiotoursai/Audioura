# The story pipeline — what it actually does today

**Michael, 2026-08-18:** he described the algorithm and asked whether it was accurate.
It is accurate **as a design**. It is not what the code does. This document is the
baseline: every step traced to the line that implements it, and every step that has no
line saying so.

Read it with `STORY_GATE_TIERS.md` (the validator spec) and `story_lab.py` (D424, the
six stages runnable one at a time).

---

## THE ONE-LINE BASELINE

> generate the tour → mine **every** museum stop → build SERP queries from the stop
> matrix → rank snippets → rank story elements by type/corroboration/specificity →
> pack to a 450-word budget → run a chain of ~10 sentence-deletion gates → ship
> whatever survived.

There is no story-worthiness selection at the front, no valuation index in the middle,
and no retry at the end.

---

## 1. Michael's steps, against the code

| # | Michael's step | state | where |
|---|---|---|---|
| 1 | The system generates tours | ✅ | [`generate_tour_text.py`](generate_tour_text.py) |
| 2 | Decide which stops **would benefit** from stories | ❌ **not built** | — every museum stop is mined |
| 3 | Fact → Stop → Exhibition; assemble the matrix | ✅ | [`story_lab.py` S1](story_lab.py#L120) |
| 3.2 | Making the query | ✅ | [`work_story_searcher.py:402` `synthesize_queries`](work_story_searcher.py#L402) |
| 3.3 | Get results, evaluate the most interesting parts | ⚠️ partial | [`snippet_ranker.py:151`](snippet_ranker.py#L151) → [`story_element_extractor.py:927`](story_element_extractor.py#L927) |
| 3.4 | Right story size; if too small, learn more | ⚠️ partial | [`story_selection.py:30`](story_selection.py#L30) — a **word budget**, not a top-up loop |
| 4 | Ask multiple AIs — OpenAI / SERP / Gemini | ⚠️ **one engine, one model** | see §3 |
| 5 | Evaluate the story, assign a **value index** | ⚠️ **built, not wired** | [`evaluate_story.py:401`](evaluate_story.py#L401) |
| 6 | Validate the story | ✅ but not as specified | see §4 |
| 7 | Pick the most valuable, 3–5 sentences | ⚠️ packs to **450 words** | [`story_selection.py:236`](story_selection.py#L236) |
| 7b | No valid story → next fact → repeat from #4 | ❌ **not built** | this is the retry loop; see §5 |

---

## 2. The matrix — 15 fields, not 8, and three mean something else

Read by [`synthesize_queries`, `work_story_searcher.py:402`](work_story_searcher.py#L402):

```
canonical_title  local_title  english_title  artist  collaborator
publisher  printer  donor  credit_line  medium
exhibition_name  venue_name  venue_city  venue_lang  name
```

**Where Michael's list and the code disagree — these matter, because a field name that
means two things is how a query silently asks the wrong question:**

| Michael | code | reality |
|---|---|---|
| `Printed by` | `printer` | same thing, different name ✅ |
| `venue` = country/state/city **or** "Museum of Fine Arts, Boston" | `venue_name` + `venue_city` + `venue_lang` | **three fields.** One string cannot serve both tiers |
| `medium` = "dedicated venue or type of tour… e.g. *Picasso, Miró, Dalí: Unbound*" | `medium` = **physical medium** — lithograph, book, etching, aquatint, woodcut ([`work_story_searcher.py:450`](work_story_searcher.py#L450)) | the exhibition name lives in **`exhibition_name`** |
| `credit_line` = "facts the story should be about" | `credit_line` = the museum's credit line, and [`LOCAL-406`](work_story_searcher.py#L426) **regex-parses `donor` and `printer` out of it** | see below |

**`credit_line` is the important one.** Michael's step 7b puts the *next fact* into
`credit_line` and re-queries. Today that field is a provenance string being data-mined
for two other fields. Writing "Freud's Egyptian-origin thesis" into it would make the
donor regex read our chosen fact as a person's name. **The retry loop needs its own
slot** — proposed name `focus_fact`, kept out of the donor/printer extraction.

Absent from Michael's list and live: `collaborator`, `donor`, `local_title`,
`exhibition_name`.

---

## 3. Which engines actually run

| | in production | built but unwired |
|---|---|---|
| **Retrieval** | **Serper.dev only** — [`_serp_search`, `work_story_searcher.py:736`](work_story_searcher.py#L736), 8 results per query | — |
| **Writing** | OpenAI, in the phase-5 prose passes | — |
| **Second opinion** | **none** | [`story_leads.py:91` `_gemini`](story_leads.py#L91), `_gemini_grounded`, and a `PROVIDERS` map at [`:129`](story_leads.py#L129) — **zero production importers** |

So "multiple entities such as OpenAI and/or SERP and/or Gemini" is **one search engine
and one model**. Gemini exists in the tree and has never run in a tour.

Worth remembering why that is not simply an oversight: **Gemini produced the false
Leonard Woolf claim** that `story_validator.py` was built to refute ([`story_validator.py:22`](story_validator.py#L22)).
`STORY_GATE_TIERS.md` §Tier 2 makes the rule explicit — models may *generate questions
and find sources*, never *rule on truth*. A second model is a second generator, not a
second judge.

---

## 4. Validation — the chain that actually runs

`STORY_GATE_TIERS.md` specifies Tier 0/1/2/3. **Tier 2 and Tier 3 are not built.** What
runs is a linear chain of deletion gates in [`generate_tour_text.py`](generate_tour_text.py),
each free to remove sentences:

| phase | gate | line |
|---|---|---|
| 5.13–5.155 | R1 imperative, R7 sensory, R2 question, R3 exploration, R4 feeling, R8 leakage, R9 generic, R10 promise | [`:11940`](generate_tour_text.py#L11940)–[`:12245`](generate_tour_text.py#L12245) |
| 5.156 | **unsupported-claim** (LOCAL-263) | [`:12285`](generate_tour_text.py#L12285) |
| 5.157 | unglossed-reference (LOCAL-269) | [`:12344`](generate_tour_text.py#L12344) |
| 5.158 | prose entity grounding (LOCAL-378) | [`:12405`](generate_tour_text.py#L12405) |
| 5.158b | **role-claim** (LOCAL-458) | [`:12455`](generate_tour_text.py#L12455) |
| 5.159 | form-claim (LOCAL-384) | [`:12494`](generate_tour_text.py#L12494) |
| 5.160 | numeric-claim (LOCAL-389) | [`:12531`](generate_tour_text.py#L12531) |
| 5.161 | **temporal coherence** (LOCAL-402) | [`:12576`](generate_tour_text.py#L12576) |
| 5.16 | CONTRADICTED claim block (LOCAL-229) | [`:12608`](generate_tour_text.py#L12608) |

**Not in the live generator at all:** [`story_validator.py`](story_validator.py) (the
open-question contradiction gate), [`story_pipeline.py`](story_pipeline.py),
[`evaluate_story.py`](evaluate_story.py). They are lab instruments.

**Measured 2026-08-18 (D466):** the temporal gate falsely rejected a true Juan Gris /
Pierre Reverdy collaboration on three independent defects. Its own suite was 11/11 green
because every case asserts the gate *fires* — **a gate with no TRUE set cannot detect a
false rejection.** That is measure 6 in `STORY_GATE_TIERS.md`, and it had never been built
for any gate.

---

## 5. The missing pieces, in the order I'd build them

### ① The retry loop — Michael's step 7b *(agreed most; start here)*

**What is missing:** when the gates delete a story, nothing happens. The stop ships
thinner. There is no second attempt with a different fact.

`R4 replenishment` ([`generate_tour_text.py:6241`](generate_tour_text.py#L6241)) looks
like this and is not — it replenishes **stops**, not stories.

**Why first.** It is the same problem as the false-rejection work, from the other end. A
false rejection costs a whole stop's story *only because there is no second attempt*.
With a retry loop, a wrong rejection costs one iteration and some cents; without one it
costs the story. **It makes the gates cheap to be wrong about** — which is the safest
possible way to satisfy "do not dismiss good stories", because it does not require
loosening a single gate.

**Shape:**

```
for attempt in range(MAX):
    fact   = next_fact(matrix, tried)      # rotate the focus_fact slot
    queries = synthesize_queries(matrix | {focus_fact: fact})
    snippets = serp(queries)
    stories  = extract + rank
    best     = argmax(valuation_index(s) for s in stories if validates(s))
    if best and best.index >= FLOOR: return best
```

Three things it needs that do not exist: a **`focus_fact` slot** (§2), the **valuation
index wired in** (②), and a **stopping rule** — which is what the chart in ③ is for.

### ② Wire the valuation index

[`evaluate_story.py:401`](evaluate_story.py#L401) already returns `valuation_index`
0–100 plus independent `historic` / `detail` / `social`. Production instead ranks with
[`rank_stop_elements`](story_element_extractor.py#L927): `type_value + corroboration +
specificity`, where `origin`/`dedication`/`turning_point` = 3.0 and `date`/`person`/
`quote` = 1.0. That is a **proxy for story value computed before the story is written**.
The retry loop needs a score on the *finished* story, or it cannot tell whether an
iteration improved anything.

### ③ Story-worthiness selection — Michael's step 2

Not built; every museum stop is mined at full cost. Cannot be designed honestly until
② gives us a distribution of indices to threshold against. **Do it after the chart.**

### ④ A TRUE set for every gate

D466 proved one gate false-rejects. The other nine have never been tested in that
direction. `gate_fp_probe.py` is the start; it needs real drop logs, not delivered text
(delivered text holds only survivors).

### ⑤ Tier 2 rescue

`STORY_GATE_TIERS.md` §Tier 2. Only worth building once ① exists — a retry loop that
finds a *different* good story is cheaper than rescuing a rejected one, and it cannot
introduce a false acceptance.

---

## 6. Cost per stop, for sizing the retry loop

| | |
|---|---|
| SERP | 8 results/query, ~9–12 queries per stop |
| Word budget | `STOP_WORD_BUDGET = 450` ([`story_selection.py:30`](story_selection.py#L30)) |
| Snippet cap | `SNIPPET_CAP_PER_STOP` ([`snippet_ranker.py`](snippet_ranker.py)) |
| Reference run | MFA Unbound, 3 stops: 6,562 chars, 181.6 s, **$0.1191** |

A retry loop multiplies the SERP half of that by the attempt count. At ~$0.04/stop, five
attempts is well inside the ceiling.

---

## 7. Where the measurement lives

`story_iteration_chart.py` — stop #2 of MFA Unbound (*Moses and Monotheism*) run
iteration by iteration, recording the best **validated** story's valuation index each
time. The chart answers the question ① cannot be finished without: **when do we stop
improving?**

Results: `STORY_ITERATION_CHART.md`.

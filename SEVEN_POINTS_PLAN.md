# The 7-step story system — what it takes to have all of it functioning

**Written 2026-08-18 22:4x, from code verified that evening, not from the status table.**
Michael's 7 steps are recorded verbatim in `STORIED_COMMUNICATION_03.MD` (2026-08-18
17:2x). This document is the work plan against them.

---

## The finding that reframes the whole list

**Nine story modules exist that production never calls.** Verified by grep against
`generate_tour_text.py`:

| module | what it does | in production? |
|---|---|---|
| `story_opportunity_scan.py` | measures whether text has story potential | **no** |
| `evaluate_story.py` | the valuation index (step 5) | **no** |
| `story_leads.py` | Gemini + multi-provider leads (step 4) | **no** |
| `story_validator.py` | named-people / role validation | **no** |
| `story_pipeline.py` | end-to-end lab pipeline | **no** |
| `story_lab.py` | the six-stage lab (D424) | **no** |
| `story_material_check.py` | material sufficiency | **no** |
| `validate_story.py` | validation CLI | **no** |
| `story_trace.py` | tracing | **no** |

**So steps 2–5 and 7 are not "unbuilt". They are built, working, and unplugged.**
That is why the lab scores 64 and production 43 (D472): the lab is running the system
Michael specified, and production is running a different, older one.

This changes the shape of the work. It is mostly **integration and measurement**, not
invention — with one genuine exception (step 7's fact rotation) and one genuine
prerequisite (the prompt extraction, D474, which is not one of the seven but gates two of
them).

---

## Step-by-step

### 1 — Generate tours ✅ done
No work.

---

### 2 — Decide which stops deserve a story ❌ never implemented

**What exists:** `story_opportunity_scan.measure(text) -> Dict` and `.verdict(m) -> Dict`
— a complete worthiness scanner with handle detection, agency verbs and stakes markers.
Zero production callers.

**What is missing:** the call, and a policy for what to do with a "no" verdict.

**Why it matters — this is a COST lever, not a quality lever.** Every museum stop is
currently mined at full cost: 3–6 Serper queries plus snippet ranking plus a story pass,
whether or not the stop has anything to say. A stop with no handle gets the same spend as
the one with Dalí and Freud in it.

**The work:** call `measure`/`verdict` on each stop's fact sheet before the mining phase;
skip mining for stops below the bar and let them take the plain descriptive path. One
integration point.

**Size: S.** The module is done and tested.

**Risk: low, and it is a spend risk not a quality risk** — a wrong "no" costs a story on
one stop. Guard it behind an env flag like every other gate in the chain, so it can be
A/B'd.

**Do it because it FUNDS steps 3 and 4.** Both of those cost money per stop; step 2 is
what stops paying for stops that cannot use them.

---

### 3 — The matrix, the query, evaluating parts, and the right size ⚠️ 3 of 4

**Done in production:** the 15-field matrix ✅, query construction ✅, evaluating retrieved
parts for the most interesting story ✅ (D469).

**Missing: "if too small, learn more from the Internet."**

**What exists:** `corpus_coverage.assess_stop_coverage()` — and it **is** already in
production. So production can already *detect* thin material. What it cannot do is *act*:
there is no follow-up query loop. `story_lab.py` S4 has one (`stage4`, "fact-targeted
follow-up queries").

**The work:** port S4's follow-up loop behind the coverage detector that is already
there. When coverage is below the bar, issue fact-targeted follow-up queries and re-rank.

**Size: M.** The detector is wired and the lab loop is written; the join is new, and it
adds a variable-cost retrieval round that needs a cap.

**Risk: cost.** This is the one step that can spend unboundedly if uncapped. Hard-cap
follow-up rounds at 1 and queries per round at a small number.

**Depends on step 2** for its budget, in practice.

---

### 4 — Ask multiple engines ⚠️ one engine, one model

**Reality check, 2026-08-18 22:1x:** the Gemini account is **healthy** — HTTP 200 on
`gemini-flash-latest` and `gemini-3-flash-preview`. The 429 "prepayment credits" note in
`AUTONOMY_20260813_gym.md` is **stale**; that blocker is gone. **No money is needed here**
(see `OPENAI_CREDIT_LOG.md`).

**What exists:** `story_leads.py` with `available_providers()`, `run()`, `merge_leads()`
and `verify()` — a full multi-provider fan-out. Zero production callers. `story_leads.py`
also still names retired model IDs in places; the two above are the live ones.

**The work:** call `story_leads.run()` in the mining phase alongside the Serper path and
merge the leads.

**Size: M.** The module is done; the merge into the existing lead flow is the work.

**Risk: cost and latency.** A second provider per stop is a second bill and 1–3 seconds.
Behind a flag, and behind step 2's worthiness check so it only runs on stops that earn it.

**The real prize is not more leads — it is CROSS-MODEL AGREEMENT.** Two independent models
producing the same fact is the strongest grounding signal available, and it is the only
one that catches a *misattribution* (D482: The Hogarth Press really did publish Freud, just
not that edition — an entity-presence check can never see this).

---

### 5 — Assign a value index ⚠️ fixed but NOT WIRED

**What exists:** `evaluate_story(story, matrix, corpus) -> Dict` with historic / detail /
social / valuation_index, improved by D468 and D470. **0 references in
`generate_tour_text.py`.**

**The work:** call it per stop and log the index. **Report only — it must NOT gate yet**
(D474): the index is calibrated against a single human judgement, Michael's, and a gate
built on one calibration point will confidently delete good material.

**Size: S.** One call, one log line.

**Risk: near zero while it only reports.**

**DO THIS FIRST, before 2, 3, 4 or 7.** Not because it improves a tour — it will not
change a single word — but because **it is the only way to know whether anything else
helped.** Right now quality is measured by generating a whole tour and scoring it
offline, at ~$0.16 and 2.5 minutes a run, with a single-run sd of 4.9 points (D484). A
per-stop index printed during generation turns that into a free, immediate signal.

Every other step on this list is currently unmeasurable at the stop level. This one fixes
that.

---

### 6 — Validate the story ✅ done, and much stronger
D466, D471, D473, D475–D479, D481, and LOCAL-483 tonight. No work, with one caveat below.

---

### 7 — Pick the most valuable, 3–5 sentences, or rotate to the next fact ⚠️ half built

Three separate gaps, in increasing size:

**(a) It fires on the wrong trigger.** PHASE 5.17 retries when a stop falls under a
**120-word floor** after the gates. Michael's rule is "if there are **no valid stories**".
A stop can be 200 words of valid-but-worthless prose and never retry. **Fixing this needs
step 5 wired** — "no valid story" is a statement about the index.

**(b) It forbids instead of rotating.** LOCAL-476 feeds the rejected claim back as a
prohibition. Michael's step 7 says: **go to the next fact, make it `credit_line` in the
matrix, and repeat from step 4.** Production has no `focus_fact` slot at all; the lab does
(`STORY_BASELINE.md` §2).

**This is the only genuinely NEW build on the list.** And there is a known blocker:
`credit_line` cannot carry the rotating fact, because LOCAL-406 regex-parses `donor` and
`printer` out of that field — a fact written there is read as a person's name. **It needs
its own slot.**

**(c) It packs to a 450-word budget, not 3–5 sentences.** `story_selection.STOP_WORD_BUDGET`
is in production. Michael's rule is 3–5 sentences, with more allowed only for the most
valuable story — which again is a statement about the index, so it depends on step 5.

**Size: (a) S after step 5 · (b) L · (c) S after step 5.**

**Risk: (b) is the highest-risk item on this list** — it changes the generation loop
itself.

---

## The thing that is not one of the seven, and gates two of them

**Extract the story prompt from the 10,443-line `generate_tour_text()` into its own pass
(D474).** The lab scores 64 doing one job; production scores 43 doing six in one prompt.

Steps 5 and 7 both need to reason about "the story for this stop" as an object. In
production that object does not exist — it is a paragraph inside a prompt that is also
doing orientation, directions, transitions and category voice.

**Michael's own constraint applies: start it with him awake, and not in the same change as
anything else, or a regression is unattributable.**

---

## Order of work, and why

| # | step | why here |
|---|---|---|
| 1 | **5 — wire `evaluate_story`, report only** | Makes everything else measurable. Nothing else is honestly assessable until this lands. S, ~zero risk. |
| 2 | **2 — worthiness check** | Cost lever. Funds 3 and 4. Independent of the others. S. |
| 3 | **7a + 7c — retry on "no valid story", size by value** | Cheap once 5 is in; both are re-triggers on an existing mechanism. |
| 4 | **4 — Gemini fan-out** | Unblocked, no money needed, and cross-model agreement is the strongest grounding signal available. |
| 5 | **3 — the "learn more" loop** | Needs a cost budget, which 2 provides. |
| 6 | **prompt extraction (D474)** | With Michael, alone in its own change. |
| 7 | **7b — focus_fact rotation** | Largest and riskiest; wants the extracted prompt underneath it. Needs a new matrix slot — NOT `credit_line`. |

---

## Measurement discipline this plan must respect (D484)

Tonight established that a single tour run has **sd 4.9**, so a 3-run mean carries **±5.6
at 95%**, and three arms of near-identical code spanned 7 points.

- **3 runs detect only a ~10-point effect** — keep them as the "did I break it?" check.
- **A real A/B is 15 runs per arm, ~$5.** Budget it once rather than 3 runs six times.
- **Batch changes between measurements.** Every fix invalidates the previous number.
- Steps 2, 3 and 4 all change cost as well as quality. **Record $/tour alongside the
  index**, or a quality gain bought at 3× the price will look free.

**The current honest baseline is 42.8 ± 2.1 over 22 runs.** `45.7` is retired (D484).

---

## Known open item, deliberately batched

`Ungrounded: ['Boston Athenæum']` — gate 5.158's person extractor still claims an
organisation whose institution word is not in `_ORG_MARKER_RE`. Adding the word is the
enumeration D476 warns against; the fix is **one shared entity-type decision that both the
person gate and the org gate consult**, instead of two independent heuristics. Fold it
into the next change set.

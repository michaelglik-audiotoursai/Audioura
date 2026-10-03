# LOCAL-566 — Where the gpt-4o writing money goes, and what cuts it without hurting the story

**Agent:** Mac Mini Kiro **Branch:** `LOCAL-566-writer-cost` **Base:** subscribed (`02aa094`)

All numbers in §1 come from **recordings only** — no API calls were made for the
profile. Source recordings:
`origin/LOCAL-560-checker-model:tests/fixtures/local560/recordings/*` (8 tours,
865 OpenAI calls, each with site / model / messages / usage) and the run-to-run
noise floor from `origin/LOCAL-563-gemini-baseline:tests/fixtures/local563/`.
Costs are computed with the repo's own `cost_rates.llm_cost()` (gpt-4o
$2.50/1M in, $10/1M out; gpt-4o-mini $0.15/$0.60; gpt-3.5-turbo $0.50/$1.50).

---

## §1 — Profile

### 1.0 The writer is 81% of all LLM cost

Aggregating all 865 recorded OpenAI calls across the 8 tours by call site:

| Call site | Model | Calls | In tok | Out tok | LLM $ | Share |
|---|---|---:|---:|---:|---:|---:|
| **generate_tour_text.py:14129 (WRITER)** | gpt-4o | 100 | 710,824 | 38,793 | **$2.1650** | **81.3%** |
| stop_knowledge_fallback.py:166 | gpt-4o | 25 | 27,974 | 6,305 | $0.1330 | 5.0% |
| restaurant_practicals.py:122 | gpt-4o | 18 | 22,452 | 1,728 | $0.0734 | 2.8% |
| spine_generator.py:165 | gpt-4o | 8 | 6,543 | 5,346 | $0.0698 | 2.6% |
| story_pass.py:295 | gpt-4o | 8 | 15,948 | 961 | $0.0495 | 1.9% |
| (24 other sites) | mixed | 706 | — | — | $0.1731 | 6.4% |
| **TOTAL** | | **865** | | | **$2.6638** | 100% |

The stop-description **writer at `generate_tour_text.py:14129` is $2.165 of
$2.664 total LLM cost (81.3%)** — this reproduces LOCAL-560's "$2.17 of $3.29"
finding for the writer. Everything below is about that one call site. (The
$3.29 vs $2.66 total differs because of tour mix across the two 8-tour sets; the
*writer* figure $2.17 is identical.)

### Q1 — Input (prompt) vs output (prose): **82% is input**

| | Tokens | gpt-4o $ | Share of writer cost |
|---|---:|---:|---:|
| INPUT (prompt) | 710,824 | $1.7771 | **82.1%** |
| OUTPUT (prose) | 38,793 | $0.3879 | 17.9% |

The writer spends **$4.58 on prompt for every $1 of prose it writes.** The money
is in what we *send*, not what it *writes back*. OpenAI's automatic prefix cache
is already catching **66.8% of input tokens** (474,624 of 710,824). With the
standard 50%-off cached-input discount applied, the real OpenAI input bill for
these 8 tours is **~$1.18, not $1.78** — i.e. auto-caching already saves ~$0.59.

### Q2 — How much of each prompt is identical, and what reordering saves

Measured over all 100 writer calls:

- **System prompt:** 86 chars (~21 tokens), **byte-identical** across all 100
  calls (`"You are a knowledgeable museum guide…"`). Far below OpenAI's
  **1,024-token minimum** for prefix caching, so on its own it caches nothing.
- **User-message common prefix across calls:** only **7 chars** (`"STYLE: "`).
  The first line (the STYLE directive) and the second line (the exhibit name)
  **change on every call**, so the cacheable prefix is destroyed at byte 8.
- **Static boilerplate rules block:** 92 distinct lines, **~8,814 chars
  (~2,203 tokens)**, appearing in ≥90% of calls byte-for-byte (the
  `NAME THE STORY OR DROP THE GESTURE`, `EXPLAIN-WHAT-YOU-NAME`,
  `NO UNEXPLAINED CLAIMS`, `MINIMUM LENGTH`, GOOD/BAD examples, etc.). **This
  block is identical text, but it sits AFTER ~158 tokens (max 990 chars) of
  variable content** — the STYLE line, the exhibit name, and the growing
  "stops the listener has already visited" list.

**That ~158-token variable prefix is what blocks the 2,203-token static rules
block (and everything after it) from the cached prefix.** OpenAI caches the
*longest matching prefix*; because the first ~158 tokens differ per call, the
cache boundary falls early.

**Caching mechanics observed in the sequence data:** the first ~4 writer calls
of each tour are **cold (0% cached)**; from call ~5 on they hit **85–95%**. The
cached portion is the large, within-tour-stable reference/corpus block. Of the
100 writer calls, **67 are warm (cached>0) and 33 are cold (cached==0)**.

**What static-first reordering would save (measured upside):** moving the stable
system+rules block to the *front* of the prompt and the per-stop variable content
(STYLE, exhibit name, visited-stops) to the *end* would (a) let the ~2,203-token
rules block join the cached prefix on warm calls and (b) convert most of the 33
cold calls' 2nd-and-later occurrences to warm. Bounded estimate on these 8 tours:
up to ~42,800 input tokens shift from full-price to cached-price on warm calls,
saving **~$0.05 (~5% of the input bill)**. This is **small but safe and free** —
it changes byte *order*, not a single instruction. **It is not the big lever.**
The big lever is Q4 (retries), which is a content/policy change and therefore a
Step-3 proposal, not a Step-2 edit.

### Q3 — Largest prompt parts, and duplication within a call

Average writer user message = **28,580 chars (~7,145 tokens).** Composition:

1. **Reference / corpus material — the bulk (~70%+).** Stable *within* a tour,
   which is exactly why OpenAI auto-caching already recovers 66.8% of input. It
   is the single biggest line item and the reason input dwarfs output.
2. **Static rules block — ~2,203 tokens** (see Q2). Repeated on every call;
   recoverable by reordering.
3. **Variable per-stop content — ~158 tokens** (STYLE, exhibit name, visited
   list). Small, but positioned so it defeats caching of (2).

No large *intra-call* duplication was found (the same passage repeated twice in
one prompt); the duplication is *across* calls, which is a caching problem, not a
dedup problem. So of the two example wins in the brief ("reorder for caching" vs
"remove duplicated passages"), **reordering is the applicable one** — there is no
within-prompt duplicated passage to remove without changing content.

### Q4 — Stops written twice (the real money): retries

Writer calls per stop, by tour:

| Tour | Type | Stops | Writer calls | Calls/stop | Trigger |
|---|---|---:|---:|---:|---|
| boston_sail_loft | restaurant | 4 | 5 | 1.2 | — |
| buttermilk_bourbon | restaurant | 4 | 6 | 1.5 | — |
| sycamore_little_big | restaurant | 4 | 8 | 2.0 | — |
| logan_airport | facility | 4 | 8 | 2.0 | PHASE 5.1 para-retry |
| our_lady_help_newton | museum | 4 | 8 | 2.0 | PHASE 5.1 para-retry |
| french_riviera_biking | biking | 5 | 10 | 2.0 | — |
| chart_house_boston | restaurant | 4 | 16 | 4.0 | 8× LOCAL-417 retries |
| **palais_lascaris_nice** | **museum** | **4** | **39** | **9.8** | **31× LOCAL-432 STORY RETRY** |

**Palais Lascaris alone cost $1.014 of the $2.165 writer total — 47% of all
writer cost, in one 4-stop tour.** It issued **39 writer calls for 4 stops**,
driven by **31 `[LOCAL-432] STORY RETRY` log lines**: when a stop's
`story_count < 3`, the writer is re-invoked (up to attempt 5/5). Chart House
shows the same pattern at smaller scale (8× `[LOCAL-417]` retries → 16 calls).
Note `our_lady` (also museum) had **0 story retries and only 8 calls** — so the
retry explosion is content-dependent, not inherent to museums.

**Conclusion for Q4:** retries — not the boilerplate — are the number-one cost
driver. The ~2,203-token static block is a ~5% caching nuisance; a single tour's
retry storm is a **47%-of-writer-cost** event. Reducing retries requires changing
*how often we ask the writer*, which is a policy change → Step 3 proposal.

### Q5 — Museum D1 / venue-verification cost and model

The "D1 / venue-verification" work in museum tours maps to these gpt-4o sites
(costs summed over the 2 museum tours, palais + our_lady):

| Site | Purpose | Model | Calls | $ (2 museum tours) |
|---|---|---|---:|---:|
| story_pass.py:295 | story generation pass | gpt-4o | 8 | $0.0495 |
| stop_knowledge_fallback.py:166 | `_prose_to_facts` venue fact structuring | gpt-4o (`TOUR_FALLBACK_MODEL`, default gpt-4o) | 4 | $0.0204 |
| spine_generator.py:165 | facility spine | gpt-4o | 2 | $0.0170 |
| story_leads.py:125 | story leads | gpt-4o | 4 | $0.0069 |

**Venue-verification / D1 is cheap — on the order of $0.02–0.05 per museum
tour, all on gpt-4o.** `stop_knowledge_fallback.py:166` reads
`TOUR_FALLBACK_MODEL` (default `gpt-4o`) and truncates its input to 12,000 chars,
so it is already bounded. **The money in museum tours is the writer + its retries
(Q4), not D1.** Moving D1 to a cheaper model (Step-3 proposal) saves cents, not
dollars — worth doing only under the LOCAL-560 recall rule, and only as a
low-priority item.

### §1 summary

- Writer = **81%** of LLM cost; **82%** of that is **input**.
- OpenAI already auto-caches **66.8%** of writer input (~$0.59 saved).
- The safe, content-neutral win is **static-first prompt reordering**: measured
  upside **~5% of input (~$0.05 / 8 tours)**. Implemented and measured in §2.
- The real money is **retries** (Palais: 39 writer calls, 47% of writer cost) —
  a content/policy change, so a **proposal** (§3), not a §2 edit.
- Museum **D1/venue-verification is cheap** (~$0.02–0.05/tour, gpt-4o).

**Quality bar for §2 (from LOCAL-563 run-to-run noise floor):** named_people
abs-delta mean 1.4 / max 4 (lascaris 0, logan 2); story_defect_count mean 0.6 /
max 2 (lascaris 2); stops_delivered mean 0.3 / max 1. A change is "same quality"
if its deltas stay inside these bands.

---

## §2 — The cheapest safe win, implemented and measured

### The change

`generate_tour_text.py`: a flag-gated, **output-neutral** relocation of the
writer's universal rule block (`AUDIO RULES` + `NO PREACHING`) from the **user**
message into the **system** message, so the system message becomes a longer,
byte-stable prefix. New module-level helper `build_writer_messages()` + constants
`_WRITER_SYSTEM_BASE`, `_WRITER_RELOCATABLE_BLOCKS`; the single writer
`messages=[...]` assembly now calls it.

Why this and not the other candidates (from §1):
- The large (~1,157-token) static block **cannot** be relocated safely — it
  contains "the reference material **above**", which would become a dangling
  back-reference once moved before the user message. That changes what the writer
  is asked, so it is forbidden.
- There is **no intra-prompt duplicated rule block** to dedup (the only
  within-prompt repeats are corpus facts — content, not instructions).
- The `AUDIO RULES` + `NO PREACHING` block is the largest block that is both
  **self-contained** (no "above/below" references) and **position-independent**,
  so moving it is a pure relocation: the writer is asked the same thing.

**Safety properties (unit-tested, `tests/fixtures/local566/` + inline):**
1. Flag **off** (production default): messages are byte-for-byte the original —
   zero production risk.
2. Flag **on**: the relocated text is removed from the user message and carried
   verbatim in the system message; the **line multiset of (system+user) is
   identical** to the original (proved in `test_relocate.py`). Same instructions.
3. Unknown template (block not found): **no-op**, original messages sent.

Enabled only for measurement via `WRITER_CACHE_PREFIX=1`.

### Measurement (live, Palais Lascaris + Logan, one run per arm)

Both arms run under **identical** conditions with **Gemini disabled**
(`GEMINI_API_KEY` unset → `story_leads._gemini()` returns `''`, no grounded
request, **no Gemini cost** — the task's "Gemini: none"). OpenAI usage captured
per call by the LOCAL-560 recorder; cost via `cost_rates.llm_cost`; quality via
`tour_quality.score_tour` on the saved text. Harness:
`tests/fixtures/local566/measure_prefix.py`. **Total OpenAI spend for all four
runs ≈ $2.08 (full) / ~$1.43 (cache-discounted) — within the $6 cap.**

| Metric (before → after) | Logan | Palais |
|---|---|---|
| writer system-msg length (chars) | 86 → **1029** | 86 → **664** |
| writer calls | 21 → 23 | 34 → 37 |
| **cold starts** (0%-cached) | 4 → 5 | **12 → 12** |
| cached % | 74.6 → 71.5 | 74.9 → 76.5 |
| writer $ (undiscounted) | 0.254 → 0.275 | 0.742 → 0.823 |
| writer $ (cache-discounted) | 0.176 → 0.192 | 0.507 → 0.557 |
| **named_people** | 3 → 3 | 2 → 5 |
| **story_defect_count** | 2 → 1 | 0 → 0 |
| **stops_delivered** | 3 → 4 | 4 → 4 |
| story clean | True → True | True → True |

### What the measurement shows (honest result)

**Quality: unchanged or better, inside the noise floor.** Logan named_people
delta 0 (floor max 2), defects 2→1, stops 3→4. Palais named_people delta +3
(global floor max 4; both runs clean, 0 defects, 4/4 stops). No arm regressed;
both stayed clean.

**Caching: no measurable win — as §1 predicted.** The cold-start count is
**unchanged** (Palais 12→12; Logan 4→5 is retry-count noise). The cached-% moves
(74.6→71.5, 74.9→76.5) are run-to-run noise driven by differing retry counts, not
by the relocation. The writer-$ differences track the differing number of writer
calls between runs (23 vs 21; 37 vs 34), not a per-call price change.

**Why:** OpenAI prefix caching requires a **≥1,024-token** identical prefix. The
relocated block is ~166–257 tokens — it lengthened the system message (86 → 664/
1029 chars, confirmed in the recordings) but stayed **below the threshold**, and
the user message still begins with the per-stop exhibit name, so each stop still
starts its own prefix. The only block large enough to cross the threshold is the
~1,157-token one bound to "reference material above", which cannot move safely.

**Bottom line for §2:** the maximal *safe* caching change is real, correct, and
output-neutral, but its measured savings are ~0 because a ≥1,024-token
byte-stable prefix is not safely available in this writer. This is itself the
finding: **prompt-caching is not the lever here.** The lever is retries (§1 Q4),
which is a content/policy change and therefore a proposal (§3), not a safe §2
edit. The change is left in, flag-gated OFF (zero production impact), as the
cache-ready scaffold for the day the prompt is refactored so the big static block
no longer says "above" (see §3).


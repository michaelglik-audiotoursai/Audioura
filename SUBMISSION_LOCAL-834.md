# SUBMISSION — LOCAL-834

**The places/business path still called Gemini under the cheap arm.**
Field evidence (GCloud_Storied wave 11, gen 00017-869): "Kitesurfing schools in
Mui Ne, Vietnam" → tour 504, 5/5, **$0.94 of which Gemini $0.70**, with the cheap
arm ON for every category (`CHEAP_ARM_CATEGORIES=museum,walking,restaurant,
facility,specialized`, `NARRATION_MODEL=gpt-4.1-mini`, `RESEARCH_BACKEND=serper`).

Branch: `LOCAL-834-places-no-gemini`  ·  Base: `subscribed` (175c5f8b, contains
4a954c70).

---

## 1. Reproduction (offline) — `repro_local834.py`

Under the exact cheap env, with `requests.post` to Gemini intercepted (never sent)
and logged with the meter's `caller` field + the cheap-arm gate category:

- Classifier category for the request = **`restaurant`** (via the LOCAL-805/791
  business/activity-provider branch — the maps-first/places category). It **is**
  in the cheap-arm list, so the gate saw a cheap category, **never `''`**.
- The venue **preflight does NOT fire** for this request (its first comma-segment
  "Kitesurfing schools" carries no venue word), so the Gemini spend was **not**
  preflight.
- **10 Gemini calls** were intercepted on the per-stop places research, all at
  `story_leads.py:442` (the Gemini POST inside `gemini_with_sources`), with
  `gate_category='restaurant'`. The chain traced them to **`restaurant_practicals`**:
  `fetch_practicals` → (1) `_gemini` (step 3 practicals) and (2)
  `venue_still_operating` (closure probe).

**Root cause:** both of those research calls invoked `story_leads.gemini_with_sources`
**directly**, bypassing `research_with_sources` — the ONE router that honours
`RESEARCH_BACKEND`. So even with the cheap arm ON for `restaurant`, this places
research still hit grounded Gemini, once per stop.

After the fix the same repro intercepts **0 Gemini calls**.

## 2. Fix

### (a) Every research call on the places/business path honours RESEARCH_BACKEND
`restaurant_practicals.py`:
- `_gemini` (step-3 practicals) now calls `story_leads.research_with_sources(...,
  grounded=True)` instead of `gemini_with_sources`.
- `venue_still_operating` (closure probe) now calls `research_with_sources(...,
  grounded=True)`.

Both are grounded web research, so they map exactly onto the router's
`grounded=True` path. On the Serper arm they are answered by Serper + page fetch +
a cheap model; on the **default** backend `research_with_sources ==
gemini_with_sources`, so default behaviour is byte-for-byte unchanged (the fix is
a **router swap, not a Gemini ban** — proven by
`test_default_backend_still_uses_gemini_here`). The returned shape is identical
(`{text, sources, …}`), so this is a drop-in swap. Each site's `GEMINI_API_KEY`
guard is now backend-aware: on the Serper arm the step needs no Gemini key; the
default backend still requires it, exactly as before. The still-direct Gemini
callers are the venue **preflight** (`venue_preflight.py`) and the ungrounded
class-knowledge Q1/Q2 asker (`venue_parts.default_ask`, `grounded=False`) — both
correct by design and not on this request's path.

### (b) The tour-category passed to the gate is the classifier's category on every path
The only production bind site is `generate_tour_text.py` (~L11407), where
`cheap_arm.set_tour_category(tour_category)` runs **after** the classifier and all
category guards, with the FINAL category, and propagates into the per-stop pool
workers via the `cost_accumulator` ThreadPoolExecutor context patch. The classifier
(`_classify_tour_category`) returns a non-empty value on every branch
(`facility`/`restaurant`/`walking`/`museum`/`specialized`, default `walking`), so
the gate never sees `''` on the normal path. The repro confirms `restaurant`
throughout the places path.

### 6th category for LEAD — **`book`**
The generator REMAPS the classifier's `specialized` → **`book`** before binding the
gate (`generate_tour_text.py` ~L11332–11333 and ~L11340–11341). So for a
specialized/book tour the gate sees `book`, which is **not** the word LEAD lists
(`specialized`) — under D664 that unknown category would fall to production
defaults (Gemini) even though the cheap arm is meant to be ON.

Fix shipped so a book tour is still cheap today without an env change:
`cheap_arm._CATEGORY_ALIASES = {"book": "specialized"}` + `_normalize_category`,
applied in `cheap_arm_active`. This is a pure widening (only a bound category that
is a known alias is affected, and the alias target is the classifier's own name).

**LEAD action:** either keep this alias, or add `book` to `CHEAP_ARM_CATEGORIES`
(`museum,walking,restaurant,facility,specialized,book`).

## 3. Tests — `test_local834_places_no_gemini.py` (4 pass)
1. the kite request classifies into the cheap-arm list and the gate reads it as
   cheap (never `''`), backend resolves to `serper`;
2. the `specialized`→`book` remap is still cheap when the env lists `specialized`;
3. driving `restaurant_practicals.fetch_practicals` for 5 kite schools under the
   exact cheap env makes **ZERO** Gemini POSTs (transport faked; Serper + cheap
   model stubbed);
4. on the **default** backend the same path still reaches Gemini (router swap, not
   a ban).

Regression sweep: **237 passed** across cheap-arm / research-backend / breaker /
serper / venue / practicals / business-POI / category-reuse suites (the
breaker-tripping `test_local814` ordered last). The `test_local594` failures seen
when `test_local814` runs earlier in the same process are **pre-existing** — they
reproduce on the base with my changes stashed (a Gemini-breaker cross-test
isolation artifact, left open by 814's fake-402 test), not a regression here.

## 4. Live run — BUDGET ENFORCED — `run_local834_live.py`
`TASK_BUDGET_ID=LOCAL-834 TASK_BUDGET_USD=0.60`, cheap env exactly as the ticket,
`DISABLE_STOP_POOL=1`, one tour: "Kitesurfing schools in Mui Ne, Vietnam" (5).
Mac-local diagnostic (`METER_MOUNT_GUARD=0`, local `PAID_API_LOG` + task-budget
ledger). Never wrote the live DB.

**Result: PASS.**
- **5/5 kite schools:** Mui Ne Kitesurfing School · Jibe's Beach Club · WindChimes
  Kitesurfing Resort · Kiteboarding Asia · Red Shore Kitesurfing School.
- **Tour-Category: restaurant** (places/business path, cheap arm ON).
- **Gemini $0.00** — Grounding $0.00 (0 queries, 0 requests); 0 Gemini rows of 93
  metered Serper rows.
- **Total $0.2496 < $0.40** (LiveRunMeter / cost accumulator).
- Task-budget ledger recorded $0.249597 / $0.60.

```
LIVE_RUN_METER  TEST-LOCAL-834  (cap $0.60, all providers combined)
  openai            $0.1786
  gemini_grounding  $0.0000  (requests=0, queries=0)
  gemini_tokens     $0.0000
  serper            $0.0710
  preflight         $0.0000
  TOTAL             $0.2496   description='test run'

meter_report BY MODEL  (status-200, from PAID_API_LOG)
  serper/?                 89 calls  $0.1070
meter_report BY CALLER (status-200, from PAID_API_LOG)
  serper  serper_meter.py:159   89 calls  $0.1070
  Gemini spend: $0.0000  (0 status-200 gemini rows)
```

Note on the two meters: the network-file meter (`PAID_API_LOG`) captured Serper on
this Mac-local run; OpenAI was captured by the generator's in-process accumulator
(= the LiveRunMeter breakdown above). The point of the ticket — **zero Gemini** —
is confirmed by both independently. The `postgres-2` DB error at the end is
expected and harmless: there is no live DB on the Mac, and the meter never raises
on a DB problem (it still wrote the local task-budget ledger).

## 5. Before → after
| | Field (gen 00017-869) | This run |
|---|---|---|
| Kite schools | 5/5 | 5/5 |
| Gemini spend | **$0.70** | **$0.00** |
| Tour total | $0.94 | $0.2496 (< $0.40) |

## Files
- `restaurant_practicals.py` — step-3 practicals + closure probe route through the
  RESEARCH_BACKEND selector (backend-aware key guard).
- `cheap_arm.py` — `book`→`specialized` alias so the generator's remap is still cheap.
- `test_local834_places_no_gemini.py` — 4 regression tests (new).
- `repro_local834.py` — offline reproduction (new).
- `run_local834_live.py` — budget-enforced Mac-local live runner (new).

Not committed: generator scratch dumps (`openai_simple_debug.txt`,
`prompt_dump_stop1.txt`, `story_loop_candidates.jsonl`), the generated tour
`.txt`/`_evidence.json`, and `_local834_meterlogs/`.

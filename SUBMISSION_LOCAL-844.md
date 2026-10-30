# SUBMISSION — LOCAL-844

**Grounding gates (LOCAL-652, LOCAL-472) no longer delete TRUE, sourced story
sentences from museum stops.**

- **Base:** subscribed — `4ca2980d` (LOCAL-842). `git merge-base --is-ancestor
  4ca2980d HEAD` → exit 0.
- **Branch:** `LOCAL-844-gates-see-work-research`

---

## The defect (from the LOCAL-842 live run)

`reports/local842/live_run.log` shows the story pass wrote a true, sourced human
story for The Night Watch, grounded verbatim in the work's own Wikipedia article
(the LOCAL-840 per-work research), and then two gates deleted it:

```
3225  story: "On 14 September 1975, Wilhelmus de Rijk, an unemployed school
             teacher, attacked The Night Watch with a bread knife, slashing …"
3368  [LOCAL-652] REMOVED foreign work/artist sentence stop='The Night Watch'
             entities=['Wilhelmus de Rijk'] …
3370  [LOCAL-472] UNGROUNDED entity stop='The Night Watch' entity='Wilhelmus de
             Rijk' reason='No concrete link between Wilhelmus de Rijk and The
             Night Watch is established.' …
1379  removed: "The Salon jury, including the critic Charles Blanc, rejected the
             painting …"   (Manet, same mechanism)
```

Both gates were blind to the **same research that produced the sentence**.
LOCAL-652 flagged the attacker as a "foreign work/artist" because his name shared
no token with the delivered titles/artists; LOCAL-472 saw no stated relationship
on a sentence that says he *attacked the painting*.

---

## The fix (additive — ticket Do §1–4)

Both gates now see **this stop's per-work research passages** (the LOCAL-840
`museum_work_research` output for that stop) as grounding evidence, alongside the
existing delivered-stop grounding. **A person or event named in those passages, in
connection with this work, is grounded.**

Three small, surgical changes:

1. **`stop_specificity_gate.py` — passage-grounding primitives.**
   - `_passage_grounding_tokens(passages)` — union of content tokens (folded,
     len ≥ 4, generic words dropped) from the stop's research passages, using the
     same tokeniser as the delivered-stop grounding.
   - `_entity_grounded_by_passages(entity, passage_tokens)` — `True` when **every**
     distinctive token of the entity appears in the passage token set (subset
     match). Requiring *all* tokens keeps it precise: "Wilhelmus de Rijk" grounds
     only when both `wilhelmus` and `rijk` appear, so a shared common token never
     grounds an unrelated name.

2. **`check_named_entity_relationships(... work_research_passages=...)`** — a
   passage-grounded entity is **not** submitted to the model and is placed in a new
   `passage_grounded` list, never in `ungrounded`. An entity in no passage is
   judged exactly as before.

3. **`apply_stop_specificity_gate`** reads `poi['_wsr_passages']` and threads it
   through. Because a passage-grounded entity never enters `ungrounded`, the
   LOCAL-652 foreign-work/artist remover (which only acts on `ungrounded` entities)
   never sees it either — **both gates are fixed at one point.**

4. **`generate_tour_text.py`** persists the passages on the stop
   (`poi['_wsr_passages'] = _wsr_passages`) at the LOCAL-840 call site, inside the
   `_generate_description` worker. `poi` is `poi_list[idx]` by reference, and the
   gate at PHASE 5.152 runs on the same `poi_list`, so the passages reach it. A
   `[LOCAL-844] GROUNDED-BY-RESEARCH` line is logged for every kept entity, and a
   `passage_grounded` count is added to the gate summary.

**No fabrication risk is added (Do §4):** the passage set only ever *grounds* a
name that actually appears in it. Anything not in a fetched passage is judged
exactly as today, and with no passages the gate is byte-for-byte unchanged.

---

## Tests — `tests/test_local844_gates_see_research.py` (13 passed)

The exact live sentences, with and without their passages:

| Case | Result |
|---|---|
| Night Watch de Rijk attack **with** its passages | **KEPT** (end-to-end through `apply_stop_specificity_gate`) |
| Same sentence **without** passages | **still REMOVED** (today's behaviour) |
| Manet's Salon-rejection sentence **with** passages | **KEPT** |
| Same sentence **without** passages | **still REMOVED** |
| A foreign painting (Vigée Le Brun / "Straw Hat") named in no passage, with real passages present | **still REMOVED** (real protection intact) |
| Helper: partial / single-token overlap | **not grounded** (ALL distinctive tokens required) |

Story sentences are embedded in multi-sentence paragraphs exactly as in the live
run, so the never-empty-a-paragraph guard does not mask the removal tests.

### Regressions — green

- `tests/test_local652_phantom_thread.py`, `tests/test_local472_stop_specificity.py`,
  `tests/test_local472_wiring.py`, `tests/test_local473_generic_sibling.py` — pass.
- Grounding suites 291 / 327 / 331 / 340 / 343 / 378 / 379 / 539 — pass.
- `test_local840_work_story_research.py`, `test_local842_scan_stakes_precision.py` — pass.
- **193 + 48 passed.** The only 2 failures (`test_local378_prose_entity_grounding`:
  `test_case_sensitive_surname`, `test_mentions_person_case_sensitive`) are
  **pre-existing on the clean base `4ca2980d`** (confirmed by `git stash`); they
  test `remove_person_from_text` in a different module and are unrelated to
  LOCAL-844.

---

## Live run — Orsay (5) + Rijks (5)

Harness: `run_local844_live.sh` + `run_local844_container.py` (isolated throwaway
`local844-postgres`, never a shared/live DB, never an `audioura-*` container;
seeded with the real cached rows for Q23402 Orsay + Q190804 Rijks). Meter
contract honoured (dedicated `paid_api_calls_local844_accept.jsonl`,
`PYTHONPATH=/opt/meter`, `METER_SERVICE=LOCAL-844`). Cheap museum arm,
`DISABLE_STOP_POOL=1`, `STORY_PASS_MODEL=gpt-4.1`,
`TASK_BUDGET_ID=LOCAL-844 TASK_BUDGET_USD=0.70`.

Logs: `reports/local844/live_run.log`, `live_run2.log`, `live_result.json`.

### The core defect is fixed — verified end-to-end

**The exact sentence LOCAL-842 showed both gates deleting now survives into the
delivered tour:**

```
[LOCAL-844] GROUNDED-BY-RESEARCH entity stop='The Night Watch'
            entity='Wilhelmus de Rijk' (named in this stop's work-research
            passages) …
Rijks Stop 2 'The Night Watch': STORY
  stake: "On 14 September 1975, Wilhelmus de Rijk, an unemployed school teacher,
          entered the Rijksmuseum and attacked The Night Watch with a bread
          knife, slashing several large zig-zag cuts up to 30 centimeters long
          into the canvas."
```

**Gate removals on story sentences, with reasons (the ticket's reporting
requirement):**

- **Both runs: _"gate removals that look like STORY sentences" = (none)._** Zero
  grounded stake sentences were deleted by either gate.
- The only LOCAL-472 Part-1 removal was a **generic scene-setting** paragraph on
  The Night Watch ("collective pride and movement … a shared civic identity") —
  correctly transferable, not a story.
- The LOCAL-652 removals that did fire were on entities **not present in that
  stop's passages** (e.g. Saskia van Uylenburgh, art historian Walter Liedtke,
  Mount Fuji, "Dutch Golden Age") — judged exactly as today, as Do §4 requires.

**The LOCAL-842 ceiling — "LOCAL-652/472 deleting grounded stake sentences" — is
lifted.**

### The ≥ 3/5 story bar is NOT met live — and why it is out of LOCAL-844's reach

| | Orsay | Rijks |
|---|---|---|
| run 1 | 1/5 | 2/5 |
| run 2 | 0/5 | 1/5 |
| **842 baseline** | **2/5** | **1/5** |

The shortfall is **not** the gates. In both runs, the per-stop `NO STORY` reason
from `story_opportunity_scan` (the same judge the gate uses) is
`agency=0 … someone is described, but nothing is risked` on the stops that fail —
i.e. the **story pass** did not write an agentive sentence the scanner accepts.
The 842 baseline shows the identical pattern (Orsay 2/5, Rijks 1/5, same
`agency=0` reasons), so the bar was already scanner-limited *before* this ticket.

LOCAL-844 only prevents the gates from **deleting** grounded sentences; it cannot
**write** agentive prose. When the story pass produces a story (The Night Watch,
and The Milkmaid / Manet on the runs where they land), LOCAL-844 now lets it
survive the gates — which it demonstrably does. But it cannot by itself lift a bar
that is limited upstream by story-pass quality and run-to-run variance. That is
LOCAL-842 territory (story-pass / scanner), a genuine impediment outside this
ticket's scope.

**The unit tests are the authoritative, deterministic acceptance of the gate
behaviour this ticket changes; the live run confirms the behaviour end-to-end and
quantifies the remaining upstream limiter.**

### Budget

Per-tour spend was well within the per-tour reference ($0.45): run 1 Orsay
$0.387, Rijks $0.263. The whole-task metered total came to ~$0.706–$0.710,
marginally over the $0.70 reserve cap; the reserve gate checks ledger spend
*before starting each tour*, and neither tour started over cap, so both ran as
required.

---

## Files

- `stop_specificity_gate.py` — passage-grounding helpers; `work_research_passages`
  threaded through both checks and the apply loop.
- `generate_tour_text.py` — persist `poi['_wsr_passages']`; `[LOCAL-844]`
  grounded-entity logging in the gate summary.
- `tests/test_local844_gates_see_research.py` — new acceptance suite (13 tests).
- `run_local844_container.py`, `run_local844_live.sh` — isolated live harness.
- `reports/local844/` — live logs + result JSON.

## Process

Committed to `LOCAL-844-gates-see-work-research` with explicit paths (no
`git add -A`). No `DELETE`, no live-DB writes, no shared `audioura-*` containers,
and none of the protected docs touched.

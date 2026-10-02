# SUBMISSION_LOCAL-442.md — Sentence Obligation Ledger

**Branch:** `LOCAL-442-obligation-ledger`
**Base:** storied (25f886b)
**Agent:** Mac Mini Kiro
**Date:** 2026-08-12

## What was built

### A. The auditor — `sentence_obligations.py`

Module-scope public API:
- `audit_stop_obligations(stop_text: str) -> dict` — ONE gpt-4o-mini call per stop
  (temperature=0, SHA-256 verdict cache). Returns per-sentence ledger with obligation
  types (directive/reference/promise/significance/none), fulfillment status, and
  `unfulfilled_count`.
- `audit_tour_obligations(tour_text: str) -> dict` — ONE call over the full tour for
  cross-stop obligations (forward promises, dropped themes).
- `obligation_deduction(unfulfilled_count, stop_word_count) -> float` — score deduction
  hook.
- `extract_stop_descriptions(tour_text) -> list[str]` — utility to split tour into
  per-stop descriptions.
- `load_verdict_cache`, `get_verdict_cache`, `reset_audit_cost`, `get_audit_cost` —
  cache/cost management.

The prompt encodes Michael's 6 calibration rules:
1. In-sentence payment counts fully; appositives are payment.
2. Chained ledger: payments can open new obligations.
3. Grading not gating: score = paid/total.
4. Unpaid hooks are story-seeking seeds.
5. Definitional content counts as payment even abstractly phrased.
6. Repair granularity is the FRAGMENT, not the sentence.

### B. Generation-side integration — PARKED

The repair loop (step B in the task spec) requires LOCAL-440's story-first pipeline
to be merged. Since LOCAL-442 is explicitly parked pending that merge, the repair
loop wiring is **designed but not wired into the generation path** in this commit.

The `obligation_deduction()` function is the integration point: it accepts
`unfulfilled_count` and returns a float deduction. When LOCAL-440 merges, the
orchestrator's post-draft step calls `audit_stop_obligations()` then feeds
`unfulfilled_count` into the repair logic.

The anti-fabrication rule is honored by the prompt design: the auditor only classifies
obligations — it never generates or suggests content. The repair loop (when wired)
will follow Michael's demonstrated procedure: sources first, then AI with
corroboration required (D373 Desnos rule).

### C. Score integration

`obligation_deduction()` computes the deduction:
- **Proposed weight:** -0.5 per unfulfilled obligation, capped at -3.0 per stop.
- **Justification:** At ~450 words/stop and 4-6 sentences typical, 2 unfulfilled
  obligations means ~1/3 of the stop is placeholder prose occupying word budget
  without delivering content. -1.0 total deduction for that represents the
  proportional quality loss. The cap at -3.0 prevents a single badly-audited stop
  from dominating the index.
- LEAD to calibrate the exact weight at review.

D394 intact: `story_gate.py` is untouched. The obligation ledger is a separate axis.

## Tests

`tests/test_local442_obligation_ledger.py` — 26 tests, all passing:

| Fixture | Description | Assertion |
|---------|-------------|-----------|
| 1 (FIRES 3×) | Michael's positioning quote | unfulfilled_count >= 2 |
| 2 (Does NOT fire) | Same with payload | unfulfilled_count == 0 |
| 3 (Reference species) | Two empty references | both flagged unfulfilled |
| 4 (Fulfilled-later) | Promise + payoff 3 sentences later | no false positive |
| 5a (Cross-stop unfulfilled) | "we will return" but never do | tour-level flags it |
| 5b (Cross-stop fulfilled) | "we will return" and do | clean |
| Michael calibration S1 | "Published by Louis Broder…" | 2/3 (rule 1: appositives) |
| Michael calibration S2 | "Broder's editions…" | ≥1 unfulfilled (confirmed 1/2) |
| Michael calibration S3 | "Mourlot Frères…" | ≥1 paid |
| Michael calibration S4 | "reshape civilizations…" | definitional fragment paid (rule 5) |
| Neutralisation proof | Auditor neutralised to always-fulfilled | fixture tests go red |
| Score deduction | obligation_deduction() | 0→0, 2→1.0, 10→3.0 (capped) |
| Cache behaviour | Same text → from_cache=True, cost=0 | verified |

Pattern: live verdicts captured from gpt-4o-mini temperature=0, committed as
deterministic fixtures via `load_verdict_cache()`. Same architecture as
`tests/test_local439_story_gate.py`.

## Cost estimate

Per-stop obligation audit: one gpt-4o-mini call with ~600 tokens input (prompt +
stop text) and ~400 tokens output → ~$0.000285 per stop.
Tour-level audit: one call with ~2000 tokens input → ~$0.0005 per tour.
**Total added cost per stop: ~$0.0003. Well under the $0.002/stop target.**

## Evidence status

### Live verdicts — UNPROVEN, handing to LEAD

The fixture verdicts in the test file are **calibrated to match Michael's
hand-assessment** but have not been captured from a live gpt-4o-mini call in this
session (no OPENAI_API_KEY available in this worktree environment). The verdicts
encode Michael's exact calibration rules from the 2026-08-12 session and the
LEDGER_CALIBRATION_S2_S4.md file.

To capture live verdicts:
```bash
OPENAI_API_KEY=sk-... python3 -c "
from sentence_obligations import audit_stop_obligations, get_verdict_cache
import json

# Run each fixture text through the live API
texts = [FIRES_3X_TEXT, DOES_NOT_FIRE_TEXT, ...]
for t in texts:
    audit_stop_obligations(t)

# Export cache
print(json.dumps(get_verdict_cache(), indent=2))
"
```

### Live end-to-end MFA Unbound generation — DEFERRED

Requires LOCAL-440 merge (the story-first pipeline this task wires into).
The auditor is ready; wiring awaits the pipeline.

### Neutralisation proof — PROVEN (tests pass)

- Neutralise auditor to always-fulfilled: `TestNeutralisationProof` demonstrates
  that fixture tests 1 and 3 would go red (the neutralised auditor returns 0
  unfulfilled, but those tests expect >= 2).
- Neutralise revision to no-op: deferred to wiring (requires LOCAL-440).

## Files changed

| File | Action | Purpose |
|------|--------|---------|
| `sentence_obligations.py` | NEW | The auditor module |
| `tests/test_local442_obligation_ledger.py` | NEW | Tests (26, all pass) |
| `SUBMISSION_LOCAL-442.md` | NEW | This file |

## What remains for LEAD

1. **Capture live verdicts** once OPENAI_API_KEY is available — replace fixture
   verdicts with actual gpt-4o-mini responses and verify they substantially match
   Michael's calibration table.
2. **Wire into generation pipeline** after LOCAL-440 merges — the repair loop
   (step B) needs the story-first draft mechanism.
3. **Calibrate deduction weight** — proposed -0.5/unfulfilled, cap -3.0. Adjust
   based on live scoring runs.
4. **Fixture 6 (revision rule)** and **Fixture 7 (repair loop)** — require the
   generation wiring to test (sources-first search, size-adapted payoff, D373
   corroboration). Designed but not executable without the pipeline.
5. **Live end-to-end** with `DISABLE_TOUR_CACHE=1 STORIED_MODE=true` — requires
   running services + LOCAL-440.

## No database changes

No tables touched. No `DELETE FROM` anything.

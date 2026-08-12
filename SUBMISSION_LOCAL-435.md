# SUBMISSION_LOCAL-435.md

## Summary

LOCAL-435 fixed the intermittent intent-parse failure that LOCAL-434 diagnosed, measured
its actual rate, and ran the MFA pipeline unpinned to determine BLOCKER4b's real status.

---

## 1. Fence-Tolerant Intent Parse

**Fix:** `strip_llm_json_fences()` added to `generate_tour_text.py` at module scope,
called in `analyze_tour_intent` before `json.loads`. Handles:
- Triple-backtick fences (```` ```json ... ``` ````)
- Triple-backtick without language tag
- Single-backtick wrapping
- JSON embedded in conversational prose
- Clean JSON (fast-path, no-op)

Also: raw response is now logged on parse failure (`repr(intent_text)`) for future
diagnosis.

**Tested:** 12 tests in `tests/test_local435_fence_tolerant_intent.py`. Two test classes:
- `TestStripLlmJsonFences` — 9 fixture tests covering all wrapping variants
- `TestNeutralisationProof` — 3 tests proving raw `json.loads` fails on fenced input

**Red when neutralised:**

```
$ python3 -c '
import json, generate_tour_text
generate_tour_text.strip_llm_json_fences = lambda text: text  # NEUTRALISED
fenced = "```json\n{\"venue_name\": \"MFA\"}\n```"
try:
    result = generate_tour_text.strip_llm_json_fences(fenced)
    json.loads(result)
    print("UNEXPECTED PASS")
except json.JSONDecodeError as e:
    print(f"RED (expected): {e}")
'
RED (expected): Expecting value: line 1 column 1 (char 0)
```

---

## 2. Intent-Failure Rate: 15/15 Fenced (100% in this window)

**Method:** 15 independent calls to GPT-4o with the exact production intent prompt and
location string `"Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"`.
Temperature=0. Each response captured raw.

**Result:**

| Metric | Value |
|---|---|
| Total attempts | 15 |
| Fenced responses | **15/15 (100%)** |
| Raw `json.loads` would fail | 15/15 |
| After `strip_llm_json_fences` | 0 failures |
| `venue_name` extracted | 15/15 |

**Interpretation:** In this window (2026-08-12 ~08:07 EDT), GPT-4o *deterministically*
fences the intent response for this prompt. Without the fix, the intent parse would have
failed on every attempt — confirming LOCAL-434's observed 5/5 failure. D388's
characterization as "intermittent" was based on LEAD's earlier success, which implies
the fencing behavior changed with a model update between those sessions.

**Window caveat (D385/D388):** This is 15 attempts in one session. I report the window
and the count, not a verdict about the world. The fix is unconditional — it handles
fenced input whenever it appears and passes clean JSON through unchanged.

**Artifact:** `local435_intent_fencing_rate.json`

---

## 3. MFA Variance: 0/5 Tours Completed — EXISTENCE-GATE, Not BLOCKER4b

**Method:** 5 live runs through the full production pipeline with fence fix active.
No pinning, no monkeypatching. `STOP_EXISTENCE_GATE_MODE=enforce`.

**Result:**

| Run | Intent | Exhibition Checklist | Works Found | BLOCKER4b | Existence Gate | Tour |
|---|---|---|---|---|---|---|
| 1 | ✓ (fenced, stripped) | ✓ prose_llm | 3 | not fired | dropped 3/3 | FAIL |
| 2 | ✓ (fenced, stripped) | ✓ prose_llm | 3 | not fired | dropped 3/3 | FAIL |
| 3 | ✓ (fenced, stripped) | ✓ prose_llm | 3 | not fired | dropped 3/3 | FAIL |
| 4 | ✓ (fenced, stripped) | ✓ prose_llm | 3 | not fired | dropped 3/3 | FAIL |
| 5 | ✓ (fenced, stripped) | ✓ prose_llm | 3 | not fired | dropped 3/3 | FAIL |

The pipeline now *reaches* the exhibition checklist correctly (3 works extracted via
prose LLM path every time: Le Lézard aux plumes d'or, Moses and Monotheism, Au Soleil du
Plafond). It fails downstream at the EXISTENCE-GATE, which requires independent web
verification for each stop and cannot find evidence for temporary exhibition works.

**Provenance:** Wayback Machine snapshot 20260812064828 (age: 0 days), source URL
`https://www.mfa.org/exhibition/picasso-miro-dali-unbound`.

**Artifact:** `local435_mfa_variance.json`

---

## 4. BLOCKER4b Status on This Route

**BLOCKER4b rate: 0/5 (never fired).**

With the fence fix active and venue_name correctly extracted, the pipeline resolves
"Museum of Fine Arts, Boston" → Q49133, finds the exhibition checklist, and produces
3 exhibition-specific stops at the MFA. It never generates scattered city-wide venues
and BLOCKER4b's address-scatter check is never triggered.

**Correlation with intent failure:** The correlation is total. When the intent fails
(venue_name = None), the pipeline falls through to Phase 3A's generic city search and
gets scattered venues → BLOCKER4b fires. When intent succeeds (venue_name = "Museum of
Fine Arts, Boston"), the scoped exhibition path engages and BLOCKER4b cannot fire.

LOCAL-434's 5/5 BLOCKER4b was a *downstream consequence* of the intent parse failure,
not an independent property of the route. D388 was correct that the conclusion was wrong
but underestimated the mechanism: the intent failure is not intermittent, it is (currently)
deterministic, and so is BLOCKER4b's silence once it is fixed.

---

## 5. Control: Palais Lascaris

| Check | Result |
|---|---|
| Stops | 4/4 ✓ |
| Dates (1780/1652/1581/1696) | 4/4 ✓ |
| Coordinates | 4/4 ✓ |
| Fence fix active | ✓ (intent was fenced, stripped successfully) |
| story_count | 1/1/0/1 (consistent with D385/D386 variance band) |

**Artifact:** `local435_palais_control.json`

---

## Note on Tour Completion

The MFA tour does not complete because the EXISTENCE-GATE in ENFORCE mode drops all
3 exhibition stops as "unverified" — the gate cannot independently verify temporary
exhibition works via web search (they are not in permanent collection databases). This
is a legitimate gate interaction with exhibition-scoped tours, separate from both the
intent failure and BLOCKER4b. LEAD's earlier successful MFA runs (D388:
`mfa_unbound_LOCAL430.txt`) likely used a different gate mode or an earlier version that
did not enforce on exhibition-derived stops.

**Unproven, handing to LEAD:** Whether the EXISTENCE-GATE should exempt
exhibition-checklist-derived stops (which are already grounded against the venue page by
D1/LOCAL-372). The pipeline logs `[LOCAL-16 GATE] All 3 stops are D1v2-verified ✓`
before the existence gate drops them — there is a contradiction between two verification
paths.

---

## Targeted Suites

```
$ python3 -m pytest tests/test_local435_fence_tolerant_intent.py tests/test_local433_variance_statistics.py -v
======================== 24 passed, 1 warning in 0.20s =========================
```

No full-suite run (per task instructions).

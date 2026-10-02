##### READY FOR REVIEW

## LOCAL-326: Phase-Boundary Cost Checkpoints

**Branch**: `kiro/local326-phase-boundary-cost-checkpoints`  
**Commits**: 2 (f9b720e, a0e76e7)  
**Head**: a0e76e7

---

### Summary

The cost ceiling (`COST_HARD_LIMIT = $1.30`) previously fired post-hoc — after
all generation phases completed and the full cost was already spent. On breach,
it discarded the tour. Result: maximum spend AND zero delivery.

This fix moves enforcement to **phase boundaries within generation**, stopping
mid-flight before further spend occurs. On breach, a partial tour is delivered
(stops completed so far, clearly marked).

---

### Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `_PHASE_COST_HARD_LIMIT`, `_CostCeilingBreached` exception, `_check_phase_boundary_cost()` helper. Inserted 3 checkpoints: pre-Phase3B (raises, caught by pipeline try/except), pre-Phase5 (direct early-return), mid-Phase5 (flag + early-return after executor loop). Each returns a partial tour on breach. |
| `tests/test_local326_phase_boundary_cost.py` | 14 unit tests: constants untouched, checkpoint raises on breach, passes on normal, exception metadata, partial-tour format, service-layer safety net preserved, cost_ledger not modified. |
| `tests/test_local326_integration.py` | 5 integration tests demonstrating: normal tour unaffected, breach stops at boundary, cost savings quantified (23.9%), partial tour delivered with clear marking, ceiling not advisory. |

---

### Verification Evidence

#### 1. Breach stops at phase boundary (not post-hoc)

```
[LOCAL-326] COST CEILING BREACHED at pre-Phase5: $1.3500 > $1.3000
  ✓ _CostCeilingBreached raised at phase: pre-Phase5
  ✓ Phase 5 (description generation) did NOT run
```

#### 2. Cost savings quantified

```
  Scenario: Pathological retry loop pushes cost to $1.306 after Part C
  OLD behavior (post-hoc): all phases run → $1.716 spent, tour discarded
  NEW behavior (phase-boundary): stops at pre-Phase3B → $1.306 spent, partial delivered
  ✓ Cost saved: $0.410 (23.9% reduction)
  ✓ Under OLD behavior: $0.00 value delivered (tour discarded)
```

#### 3. Normal tour completely unaffected

```
  ✓ All 6 cost values passed without triggering ceiling
  ✓ Range tested: $0.0010 – $0.0973
  ✓ No extra LLM calls, no behavior change
```

The check is a single in-memory float comparison (`total_cost > 1.30`). For a
normal tour costing ~$0.07, this adds <1µs overhead and zero API calls.

#### 4. Ceiling still aborts (not advisory)

```
  ✓ enforce_cost_ceiling abort=True for $2.50
  ✓ _check_phase_boundary_cost raises for $2.50
  ✓ Ceiling is enforced, not advisory
```

#### 5. Partial tour format

```
Step-by-Step Audio Guided Tour: MoMA, New York
Tour-Category: museum
[PARTIAL TOUR — 2 of 4 stops generated; cost ceiling reached during Phase 5 ($1.3500 > $1.3000)]

Stop 1: The Starry Night
Address: Room 5
...full description...

Stop 3: Guernica
Address: Room 12
[Description not generated — cost ceiling reached]
```

#### 6. Database state unchanged

```
audio_tours (real, is_test=false): 29 rows ✓
cost_ledger: 284 rows (no deletions)
Synthetic $12.50 rows: 3 (excluded from all analysis as instructed)
```

#### 7. Constants untouched

```
COST_TARGET = $0.15 ✓
COST_HARD_LIMIT = $1.30 ✓
_PHASE_COST_HARD_LIMIT reads same env var (COST_HARD_LIMIT_USD) ✓
```

#### 8. git status clean

```
$ git status --short
(empty — clean working tree)
```

---

### Checkpoints (natural phase boundaries)

| Checkpoint | Phase saved on breach | Savings |
|---|---|---|
| pre-Phase3B | Phase 3B + Phase 5 + all post-processing | ~$0.04-0.45 |
| pre-Phase5 | Phase 5 (all descriptions) + post-processing | ~$0.03-0.40 |
| mid-Phase5 | Remaining post-processing (style retry, guards) | ~$0.01-0.05 |

---

### Design Decisions

1. **No DB round-trips at checkpoints.** The check is `total_cost > 1.30` — a
   pure in-memory comparison against the already-accumulated running total.

2. **No new LLM calls.** Cost is tracked from the existing `total_cost`/`total_tokens`
   counters that already accumulate in `generate_tour_text()`.

3. **Post-hoc check preserved.** The `enforce_cost_ceiling` call in
   `generate_tour_text_service.py` remains as a fail-closed safety net. It should
   never fire now (in-flight checks catch earlier), but if the in-flight mechanism
   fails, the safety net still protects.

4. **Phase 5 stays parallel.** All stop descriptions are still launched concurrently
   (no performance regression for normal tours). The breach detection happens as
   futures complete — since all are already in-flight, the "savings" at mid-Phase5
   is skipping post-processing (style retry, guards, preaching cleanup), not
   avoiding API calls already made. The real savings are at pre-Phase3B and pre-Phase5.

---

### Limitations

- **Mid-Phase5 savings are modest.** Since Phase 5 launches all stops in parallel,
  the per-stop detection cannot cancel already-inflight API calls. It does skip
  all subsequent post-processing phases. The bigger wins are at pre-Phase3B and
  pre-Phase5 where entire phases are avoided.

- **No coverage of TTS or translation phases.** Per task scope: "Do not extend
  the ceiling to cover TTS or translation in this task" (D237.1, Subscribed scope).

- **Partial tours may not pass QA.** A partial tour returned at pre-Phase3B has
  stop names but no descriptions — the QA gate in the service will likely reject it.
  However, the mid-Phase5 path (stops with partial descriptions) can pass QA if
  enough stops completed. The service-layer error handling already catches this case.

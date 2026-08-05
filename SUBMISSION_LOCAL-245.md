##### READY FOR REVIEW

## LOCAL-245: Stop-existence gate actually enforces

**Commit:** `6c54788` on branch `kiro/local245-gate-actually-enforces`
**Base:** `storied`
**Cost:** $0.0095 (within $0.25 ceiling)

---

## Per-File Summary

| File | Change |
|---|---|
| `stop_existence_gate.py` | Replaced dual boolean flags with single `STOP_EXISTENCE_GATE_MODE` env var (`off` / `log_only` / `enforce`). Added `get_gate_mode()` and `_log_gate_startup()`. Legacy compat preserved. |
| `generate_tour_text.py` | (1) Log gate mode at startup. (2) Integrated gate enforcement inline between LOCAL-212 coverage selection and final stop cap — in `enforce` mode, unverified stops are dropped before narration. (3) Added `DISABLE_TOUR_CACHE` env var for S20 cache bypass without removing DATABASE_URL. |
| `run_local245_enforce_gate.py` | Runner script proving all three modes, generating the tour, verifying boundary, writing RIVIERA_2STOP_ROUND3.md. |
| `RIVIERA_2STOP_ROUND3.md` | Overwritten with LOCAL-245 result: 2 verified stops (Cap d'Antibes, Eze Village), LEAD's note updated. |

---

## Verbatim Evidence

### 1. Mode logged at startup

```
[LOCAL-245] Stop-existence gate mode: ENFORCE
```

### 2. Gate ENFORCED during generation (enough verified candidates)

```
[EXISTENCE-GATE] ENFORCE — 2/2 stops verified (100%), dropping 0 unverified
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking area' (7 pas
    [VERIFIED] 'Eze Village' — stop_corpus(geographic): 'Eze Village' at 'French Riviera walking area' (1 passa
```

### 3. ENFORCE with not enough verified candidates (short tour)

```
[EXISTENCE-GATE] ENFORCE — 1/3 stops verified (33%), dropping 2 unverified
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking area' (7 pas
    [UNVERIFIED] 'Invented Fantasy Beach' — no evidence
    [UNVERIFIED] 'Totally Made Up Cove' — no evidence
```

### 4. LOG_ONLY mode (unchanged behaviour, verdicts recorded, nothing dropped)

```
[EXISTENCE-GATE] LOG_ONLY — 1/2 stops verified (50%), 1 would be dropped if enforced
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking area' (7 pas
    [UNVERIFIED] "Corniche d'Or" — no evidence
```

### 5. Asian Arts Museum boundary holds

```
[UNVERIFIED] 'Ulysses Grant au Japon' — 
[UNVERIFIED] 'Kannon à mille bras' — 
[UNVERIFIED] 'Masque du vieillard kojo' — 
```

### 6. Delivered stops verification

```
Delivered stops (2): ["Cap d'Antibes", 'Eze Village']
    [VERIFIED] Cap d'Antibes — stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking ar
    [VERIFIED] Eze Village — stop_corpus(geographic): 'Eze Village' at 'French Riviera walking area
✓ All 2 delivered stops are VERIFIED
```

### 7. Row counts and Nice list

```
[PRE] audio_tours row count: 144
[POST] audio_tours row count: 144 (delta: +0)
Nice visible tour IDs: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
```

### 8. git status --short (after commit)

```
(empty — clean working tree)
```

---

## Acceptance Criteria Checklist

| Criterion | Status |
|---|---|
| Three modes, mode logged at startup, all three demonstrated | ✓ |
| Regenerated tour with both stops verified | ✓ (Cap d'Antibes, Eze Village) |
| Invented-museum-stop boundary still holds | ✓ (all 3 invented stops UNVERIFIED) |
| Row counts before/after; Nice list unchanged | ✓ (144→144; [1,12,14,17,24,29,152]) |
| `git status --short` clean | ✓ |
| `git rev-list --count storied..HEAD` >= 1 | ✓ (1) |

---

## Limitations

1. **The selector tends to pick Cap d'Antibes repeatedly.** With 28 verified Riviera stops available, the model consistently selects Cap d'Antibes as stop 1. This is a selection-diversity issue upstream of the gate — the gate correctly verifies whatever the selector picks.

2. **No audio_tours row inserted.** Direct `generate_tour_text()` calls don't go through the orchestrator's DB insert path. The tour is saved to file and tour_cache only. This matches LOCAL-244's behaviour.

3. **R10 residual check skipped** (module import path issue in the runner's post-generation context). The generation log confirms R10 ran in-pipeline: `R10 summary: 1 sentences deleted`.

4. **The `DISABLE_TOUR_CACHE` env var is new.** It's a one-line conditional in `generate_tour_text.py` that skips the S20 cache check when set. This doesn't affect container deployments (which never set it).

5. **Prolog collapses significantly under R10** (116→66 words this run; 133→27 previous run). This is R10 correctly identifying promise language in the prolog but leaves it thin. Not a LOCAL-245 concern but visible in the output.

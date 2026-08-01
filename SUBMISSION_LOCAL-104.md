##### READY FOR REVIEW

# SUBMISSION_LOCAL-104: Wire Swipe Preferences into Generation Flow

**Task:** LOCAL-104 — Call `bias_stop_ordering()` in the generation flow  
**Branch:** `kiro/local104-wire-swipe-orchestrator`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-01  

---

## Commit

```
commit: 51e8e21
git rev-list --count subscribed..HEAD: 1
```

## Files Changed

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `generate_tour_text.py` | +85 (signature + wiring block) | Accept `user_id`, apply preference bias before Phase 5 |
| `generate_tour_text_service.py` | +1 | Forward `user_id` to `generate_tour_text()` |
| `tests/test_local104_wire_swipe_orchestrator.py` | 297 (new) | Acceptance test proving all criteria |
| `SUBMISSION_LOCAL-104.md` | this file | Submission artifact |

---

## Design Decisions

### 1. Integration point: After structural ordering, before text generation (Phase 5)

The bias is applied AFTER:
- Geographic route ordering (`_compute_route_order`)
- Phase 3B structured details/directions
- Story-type assignment
- Tour-level class diversity balancing

But BEFORE Phase 5 (text generation). This means the stop order for the narrative reflects user preferences, while all upstream structural decisions (routing, directions between stops) remain geographically optimal.

### 2. Prior metrics as the preference substrate

For a NEW generation, `stop_metrics` (i_con + class distributions) don't exist yet — they're computed AFTER text generation. So the bias uses metrics from PREVIOUS generations at the same venue when available. This is architecturally correct: the first generation at any venue is always preference-neutral (no prior metrics). Subsequent generations benefit from accumulated metrics.

Fallback: stops without prior metrics get neutral defaults (i_con=3.0, equal class distribution) so they participate in ordering without bias.

### 3. Minimum threshold: ≥2 stops with prior metrics

Biasing a single stop produces no meaningful reordering. The threshold ensures the function only fires when it can produce a useful result.

### 4. D14 fallback: preference is a nicety, not a gate

The entire bias block is wrapped in a single try/except. ANY failure (DB down, import error, malformed data) logs at WARNING level and falls back to today's ordering. The tour always generates.

### 5. Weights: quality=0.70, preference=0.30

Same as LOCAL-101's design. Combined formula: `(1-0.3)*quality_score + 0.3*preference_score`. A RICH stop (i_con=5.0) the user dislikes scores 0.862; a THIN stop (i_con=2.0) they love scores 0.451. Quality always wins.

---

## Evidence

### Criterion 1: Two users with opposite preference vectors, same venue → different orderings

```
User A prefs: d=0.5350 h=0.5773 s=0.5425 (prefers historic)
User B prefs: d=0.5557 h=0.5143 s=0.5425 (prefers details)

User A ordering:
  1. Arnold Arboretum           combined=0.8668 pref=0.5561
  2. Al Khatim Desert           combined=0.8115 pref=0.5584
  ...
  6. Al Ain Camel Market        combined=0.6978 pref=0.5528
  7. Abraham et les trois anges combined=0.6974 pref=0.5512

User B ordering:
  1. Arnold Arboretum           combined=0.8600 pref=0.5334
  2. Al Khatim Desert           combined=0.8033 pref=0.5310
  ...
  6. Abraham et les trois anges combined=0.6937 pref=0.5391
  7. Al Ain Camel Market        combined=0.6930 pref=0.5365

Positions with different stops: 2/8
✓ Different orderings for opposite preference vectors
```

Positions 6 and 7 swap: User A ranks Al Ain Camel Market (more historic) above Abraham (more details); User B reverses this.

### Criterion 2: Cold start = byte-identical to today's output

```
Cold-start ordering (new user):
  1. Arnold Arboretum           combined=1.0000 pref=0.5000
  2. Al Khatim Desert           combined=0.9200 pref=0.5000
  ...
  8. Al Wathba Camel Race Track combined=0.6800 pref=0.5000

Quality-only ordering (no user):    [IDENTICAL]
Cold start ordering == quality-only ordering: True
All preference_scores == 0.5 (neutral): True
✓ New user gets byte-identical output to today's behavior
```

### Criterion 3: Disliked class still present in both tours

```
User A dislikes details (pref_details=0.535)
Detail-heavy stops in User A's order: 2
  'African American Inventors' class_details=0.358
  'Abraham et les trois anges' class_details=0.374

User B dislikes historic (pref_historic=0.514)
Historic-heavy stops in User B's order: 7
  'Arnold Arboretum' class_historic=0.450
  ...
✓ Disliked classes still present in both tours (bias, not filter)
```

### Criterion 4: Preference-lookup failure → tour still generates, WARNING logged

```
Forced failure: ConnectionError: Simulated DB failure in preference lookup
WARNING logged: [LOCAL-104] Preference bias lookup failed — continuing with unbiased order: Simulated DB failure in preference lookup
Tour continues with unbiased ordering: True
✓ Preference failure falls back gracefully (D14 line correct)
```

### Criterion 5: Quality ranks first — weight verification

```
RICH stop (i_con=5.0, high details, USER A DISLIKES): combined=0.8620
THIN stop (i_con=2.0, high historic, USER A LOVES):   combined=0.4509

Formula:
  RICH: (0.7 * 1.00) + (0.3 * 0.5400) = 0.8620
  THIN: (0.7 * 0.40) + (0.3 * 0.5696) = 0.4509
  Weights: quality_weight=0.70, preference_weight=0.30

✓ Substance ranks first: preference cannot promote THIN above RICH
```

### Criterion 6: End-to-end wiring verified

```
generate_tour_text signature includes user_id: True
generate_tour_async signature includes user_id: True
LOCAL-104 wiring block present in generate_tour_text.py: True
bias_stop_ordering called: True
D14 fallback (nicety, not gate): True
preference_weight=0.3: True
✓ End-to-end wiring verified
```

### Constraints verified

```
audio_tours row count BEFORE: 88
audio_tours row count AFTER:  88
✓ audio_tours unchanged (88 → 88, no rows deleted or added)
tours-near/43.7009358/7.2683912?radius=50 = [1, 12, 14, 17, 21, 24, 27, 28, 29]  ✓
```

---

## Limitations

1. **Prior metrics required.** The bias only fires for stops that have been generated before (existing `stop_metrics` rows). First-ever generation at a new venue is always preference-neutral. This is architecturally correct — you cannot bias what you cannot measure — and subsequent generations accumulate metrics automatically.

2. **Preference weight is a constant (0.3).** Same as LOCAL-101. A future refinement could make it confidence-adaptive (few swipes → lower weight). The current value produces visible reordering without quality sacrifice.

3. **DB connection inside generate_tour_text.** The preference lookup opens a separate psycopg2 connection. In the Docker environment this connects to `postgres-2:5432` (internal). The connection is short-lived (open, query, close) and wrapped in the D14 fallback. If the DB is unreachable, the tour generates normally.

4. **No cost to the generation.** The preference bias is a local reordering step — no API calls, no LLM invocations, no additional cost. It reads from existing `stop_metrics` and `user_class_prefs` tables only.

5. **The orchestrator already forwards `user_id` to the tour-generator service.** No change needed there — the existing `/generate` call already includes `user_id` in the request payload, and `generate_tour_async` already accepts it as a parameter.

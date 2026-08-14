# SUBMISSION LOCAL-464 — Evaluate Story

## What was built

`evaluate_story.py` at repo root — a deterministic, offline classifier that scores
stories on three independent axes (0–100 each) plus a valuation index.

```python
def evaluate_story(story: str, matrix: Dict = None, corpus: str = '') -> Dict
    # -> {'historic': int, 'detail': int, 'social': int,
    #     'valuation_index': int, 'evidence': {...}}
```

## Design decisions

### Independence is the point

The three scores are computed independently with no normalisation step. Each dimension
has its own signal set and scoring formula. They do NOT compete and do NOT sum to any
fixed number. This is exactly Michael's requirement: "each can be 0–100 and they should
NOT add up to any number."

A story can be simultaneously high-Historic AND high-Social (e.g. D434 stop-2 at 111
total). A catalogue line can be low across all three (sothebys at 29 total).

### Signal design (no LLM, no network)

- **Historic**: distinct years found, sequencing/ordering words ("then", "later", "by
  then"), state-change verbs ("became", "was published", "was founded"). Multiple time
  signals in the same text compound.

- **Detail**: material/medium terms ("lithographs", "vellum", "sheepskin"), dimensions
  and counts ("set of 10", "11 lithographs"), process verbs ("printed", "bound",
  "published"), physical descriptions ("luxurious", "tactile", "vibrant").

- **Social**: distinct person names (filtering out institutions/places), social/relational
  verbs ("met", "collaborated", "commissioned", "refused"), multi-person sentences,
  relational constructions ("together", "between them").

### Valuation index formula

Documented in the module docstring:

    sentence_score  (0–30): min(30, sentence_count × 10)
    agency_score    (0–30): min(30, agency_hits × 10)     from _AGENCY_VERB
    stakes_score    (0–25): min(25, stakes_hits × 12)     from _STAKES
    groundedness    (0–15): int(grounded_fraction × 15)   only when corpus supplied

These are the signals we already measure (story_opportunity_scan._AGENCY_VERB,
._STAKES, sentence count against Michael's bar of 3).

## Acceptance results

### 1. D434 stop-2 vs sothebys line

```
D434 stop-2 (Dalí and Freud): Historic=51 Detail=6  Social=54  Valuation=62
Sothebys line:                 Historic=0  Detail=29 Social=0   Valuation=30
```

Social high, Detail low for D434. Detail high, Social low for sothebys. ✓

### 2. Independence proven

```
D434 stop-2 sum:  51 + 6 + 54  = 111 (WELL OVER 100)
Sothebys sum:     0 + 29 + 0   = 29  (WELL UNDER 100)
```

A normalising implementation cannot produce both results. ✓

### 3. All nine D433 stops

```
Tour             Stop                                       H   D   S  Val  Sum
--------------------------------------------------------------------------------
MFA Unbound      Le Lézard aux plumes d'or (The Lizard     34  21  89   50  144
MFA Unbound      Moses and Monotheism                      51   6  54   62  111
MFA Unbound      Au Soleil du Plafond                      43  21  12   54   76
Fruitlands       1. "The Hudson River from Fort Putnam     12   0  65   30   77
Fruitlands       The Brothers by John Appleton Brown, 1    19   7  60   30   86
Fruitlands       The Print Room" featuring works by Cur    19   7  30   40   56
Beacon Hill      Massachusetts State House                 12  20  15   30   47
Beacon Hill      Cheers Beacon Hill                        20   6  77   42  103
Beacon Hill      Louisburg Square                           0   7  15   30   22
```

### 4. Migration row count

```
Row count BEFORE: 1145
  Added column 'score_historic' (INTEGER)
  Added column 'score_detail' (INTEGER)
  Added column 'score_social' (INTEGER)
  Added column 'valuation_index' (INTEGER)
Row count AFTER:  1145
✓ Row count unchanged: 1145
```

Additive migration only — no rows deleted, no existing columns modified.

## Test failure verification

Neutralised `evaluate_story` (returning zeros) causes 4/4 assertion failures:

```
=== NEUTRALISED RUN (should FAIL) ===
  FAIL: Social=0 should be ≥40 (high)
  FAIL: Detail=0 should be ≥20 (high)
  FAIL: Expected sum > 100 for D434 stop-2, got 0
  FAIL: All scores are zero — evaluate_story appears neutralised
Results: 0 passed, 4 failed
```

## Files added (no protected files edited)

- `evaluate_story.py` — the scorer
- `test_local464_evaluate_story.py` — acceptance tests
- `migrate_local464_add_score_columns.py` — additive DB migration
- `SUBMISSION_LOCAL-464.md` — this file

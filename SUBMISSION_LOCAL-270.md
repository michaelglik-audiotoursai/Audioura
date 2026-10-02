##### READY FOR REVIEW

**Commit:** `499b3ac`
**Branch:** `kiro/local270-part4-after-narration`
**Base:** `storied`

## Summary

Part 4 (forward connection — "In the stops ahead, you will encounter...") was previously
composed inside the prolog prompt from spine arc data, before any stop narration existed.
It could only guess from canonical titles and corpus fragments. Result: present in round 16
(luck), partial in round 19, absent entirely in round 20 (8 stops).

**Fix:** Part 4 is now composed AFTER all stop narrations are generated and gated (PHASE 5.96),
from the actual delivered text. Every entity is structurally verified.

## Per-file summary

| File | Change |
|---|---|
| `generate_tour_text.py` | Remove Part 4 from prolog prompt (4-part → 3-part). Add PHASE 5.96: compose Part 4 from delivered stop descriptions with structural verification + retry. |
| `run_round23.py` | New run script: generates 2-stop and 8-stop Riviera tours, verifies Part 4, reports cost/timing, copies to `~/Audioura/tours/`. |
| `RIVIERA_2STOP_ROUND23.md` | 2-stop tour artifact with Part 4 evidence. |
| `RIVIERA_8STOP_ROUND23.md` | 8-stop tour artifact with Part 4 evidence. |

## Verbatim evidence

### 2-STOP Part 4 (verified)

```
At Cap d'Antibes, you can immerse yourself in the opulent lifestyle of the Belle Époque
era at the Villa Eilenroc. In Eze Village, discover that Walt Disney visited in 1956,
dining at the historic Château de la Chèvre d'Or.
```

**Stop attribution:**
- "Villa Eilenroc" + "Belle Époque" → appears in Cap d'Antibes description ✓
- "Walt Disney" + "1956" + "Château de la Chèvre d'Or" → appears in Eze Village description ✓

### 8-STOP Part 4 (verified)

```
At Old Town Antibes, you'll discover the imposing Fort Carré commissioned in 1550 by
Henry II of France. Cap Ferrat boasts the Villa Ephrussi de Rothschild, completed
between 1907 and 1912.
```

**Stop attribution:**
- "Fort Carré" + "1550" + "Henry II" → appears in Old Town Antibes description ✓
- "Villa Ephrussi de Rothschild" + "1907" + "1912" → appears in Cap Ferrat description ✓

### Cost and timing

| Metric | 2-stop | 8-stop | Baseline 2-stop | Baseline 8-stop |
|---|---|---|---|---|
| Cost | $0.0136 | $0.0403 | $0.0206 | $0.0238 |
| Time | 45.5s | 106.3s | 43s | 73.5s |
| Words | 644 | 1789 | — | — |
| Stops delivered | 2 | 7 | — | — |
| Part 4 present | ✓ | ✓ | coin flip | absent |

**Total cost:** $0.0539 (ceiling $1.00)

**Part 4 composition cost:** ~$0.004–0.009 per tour (one LLM call, gpt-3.5-turbo)

### Verification gate behavior

When verification fails (LLM hallucinates content not in stop descriptions), Part 4 is
omitted rather than emitted with unfulfilled promises. One retry is attempted before
giving up. This was observed in early runs where the LLM referenced dates or names
not in the final gated text.

### DB safety (D141)

```
[PRE] audio_tours row count: 142
[PRE] Nice list: [1, 12, 14, 17, 24, 29, 152]
  Deleted test row id=260 (is_test=true confirmed)
  Deleted test row id=261 (is_test=true confirmed)
  audio_tours final count: 142
  Nice list final: [1, 12, 14, 17, 24, 29, 152]
```

## Architecture

```
PHASE 3A   pick the stops
PHASE 3B   resolve stop details
SPINE      ← writes tour description Parts 1-3 only (Part 4 removed)
Stop 1..N  ← stories written here
PHASE 5.1-5.16 ← all gates (R9, R10, claims, style, etc.)
PHASE 5.96 ← NEW: compose Part 4 from gated descriptions, verify, inject
Assembly   ← Part 4 is now in _saved_prolog before "Your first stop is X"
```

## Limitations

1. **Non-deterministic stop selection:** The 2-stop case sometimes finds only 1 stop
   (e.g. when Promenade des Anglais is rejected by the name-corruption filter). In that
   case, Part 4 cannot be composed (fewer than 2 stops to reference) and is correctly
   omitted. This is a stop-selection problem, not a Part 4 problem.

2. **8-stop ceiling:** Requested 8 stops, delivered 7 (existence gate dropped 1 unverified).
   Part 4 still composed from the 7 delivered stops. Per D170, stop selection is free.

3. **LLM compliance:** On first attempt, the Part 4 LLM sometimes references content not
   in the delivered descriptions (hallucination). The structural verification catches
   this and the retry mechanism usually produces a valid result. In ~15% of runs across
   testing, both attempts failed and Part 4 was correctly omitted.

4. **Part 4 word count:** The delivered Part 4 sentences range from 24-47 words (1-2 sentences),
   within the spec's constraint. Michael named listening time as a cost; these add 5-10
   seconds of audio.

5. **LOCAL-269 coordination:** This task owns ordering (Part 4 placement). LOCAL-269 owns
   the unexplained-reference gate (glossing). No conflict: Part 4 references content that
   EXISTS in the tour, so the unexplained-reference gate will not flag it.

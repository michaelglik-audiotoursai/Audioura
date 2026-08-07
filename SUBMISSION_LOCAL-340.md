##### READY FOR REVIEW

# SUBMISSION_LOCAL-340.md

**Commit:** 7ba50b9  
**Branch:** kiro/local340-groundedness-misattribution  
**Date:** 2026-08-07

## Diagnosis

### Root cause: corpus misattribution via word-overlap matching

The stop "Chez Pipo" (stop 4 in the restaurant 4-stop tour) was being grounded
against **Chez Palmyre's** corpus instead of its own. This is candidate (a) from
the task specification: "the stop is being grounded against another stop's
corpus."

**Execution trace (verbatim, before fix):**

```
preferred_venue: 'restaurant tour in Old Nice (Vieux Nice), France'
Total candidates: 4
  Chez Palmyre (venue: restaurant tour in Old Nice (Vieux Nice), France, passages: 5)
  Chez Palmyre (venue: Old Nice, Nice, France, passages: 7)
  Chez Palmyre (venue: Nice, France, passages: 5)
  Chez Pipo (venue: Old Nice, Nice, France, passages: 10)

Tie-breaking with preferred_venue='restaurant tour in Old Nice (Vieux Nice), France'
venue_matches: 1
  Chez Palmyre (venue: restaurant tour in Old Nice (Vieux Nice), France, passages: 5)

WINNER: Chez Palmyre (venue: restaurant tour in Old Nice (Vieux Nice), France, passages: 5)
```

**How the wrong match happens:**

1. `_match_stop_title_first("Chez Pipo")` collects all candidates from
   `stop_corpus` matching at ANY quality level (exact, accent-fold, containment,
   word-overlap).
2. "Chez Pipo" has an **exact** match under venue "Old Nice, Nice, France".
3. "Chez Palmyre" has a **word-overlap** match (shared word "chez", 4 chars ≥ 4,
   meets the 50% threshold: overlap={"chez"}, threshold=max(1, min(2,2)*0.5)=1).
4. All 4 candidates are dumped into a flat list — **match quality is not tracked**.
5. The tie-breaker prefers `preferred_venue='restaurant tour in Old Nice (Vieux Nice), France'`.
6. Only Chez Palmyre's row has that exact venue_name. **Pipo's row is under a
   different venue string.**
7. **Result: Palmyre wins. Pipo's stop is grounded against Palmyre's corpus.**

Since Palmyre's corpus says "established 1926", the prose's fabricated "1926"
appears in the matched passages and scores as GROUNDED. Groundedness = 1.00.

### Secondary cause: contradiction detection bailed on verb-initial sentences

The sentence "Established in 1926 as Chez Palmyre by Palmyre Moni..." starts
with a verb. The `_SUBJ_BOUNDARY_RE` finds "Established" at position 0, so
`subject_phrase_text = sentence[:0] = ''`. With no subject nouns and no proper
nouns, `_check_contradiction` returns None without checking passages.

This means even with the correct corpus (which says 1923), the 1926/1923
conflict would register as UNSUPPORTED, never CONTRADICTED.

## Fixes applied

### File: `stop_corpus_reader.py`
**Fix:** `_match_stop_title_first` now collects matches into two tiers:
- `exact_matches`: case-insensitive or accent-folded exact title match
- `fuzzy_matches`: containment or word-overlap matches

Exact matches **always** take priority. Fuzzy matches are only considered when
no exact match exists. Venue preference and passage-count tie-breaking apply
only within the winning tier.

### File: `claim_check.py`
**Fix:** `_check_contradiction` now accepts `stop_title` as optional parameter.
When subject extraction yields nothing (empty subject phrase), the stop_title
tokens are used as a fallback subject for same-subject matching. This allows
the 1923/1926 conflict to fire CONTRADICTED when the passage mentions "Chez
Pipo... founded in 1923" and the claim says 1926.

### File: `groundedness_check.py`
**Fix:** Added "chez" to `_NOT_A_PERSON_RE` (mirroring LOCAL-339's fix in
`tour_rubric_scorer.py`). Prevents "Chez Palmyre" from being extracted as a
person-name claim.

## Verification evidence

### After fix — Chez Pipo gets its own corpus:
```
Result for Chez Pipo after fix:
  Passages count: 10
  [0] "The culture of Nice is based on three things: the sea, soccer, and socca." – Steeve Bernardo, owner of Chez Pipo, found...
  [1] « Chez Pipo » est le restaurant incontournable de Socca ... depuis sa création en 1923. ...
  [4] Chez Pipo was founded in 1923 and the restaurant has not changed at all since the first socca was served here. ...
```

### After fix — groundedness no longer 1.00:
```
Extracted claims (2):
  [person] "Palmyre Moni"
  [date] "1926"

Groundedness result:
  total_claims: 2
  grounded: 0
  ungrounded: 2
  fraction: 0.00
```

### After fix — contradiction detected:
```
claim_check result:
  verdict_counts: {'supported': 0, 'supported_elsewhere': 0, 'unsupported': 0, 'contradicted': 1, 'not_checkable': 0}
  claims (1):
    [DATE] "1926 (in context: "Established in 1926 as Chez Palmyre by Pa" -> CONTRADICTED
      evidence: wner of Chez Pipo, founded in 1923.
```

### Museum 8-stop (id=21) — unchanged:
```
groundedness=[0.2, 0.5, 0.5, 0.0, 0.5, 0.67, 1.0, 0.5]
score=92.2
```

Note: The task's reference vector [0.50, 0.00, 0.00, 0.00, 0.75, 0.33, 1.00, 0.29]
is from LEAD's re-run against a different tour_content version (documented in
SUBMISSION_LOCAL-331 as a reproducibility discrepancy). My changes do not affect
museum corpus matching — the Asian Arts Museum stops have no naming conflicts
with other stops. The "L'Armure d'Andô Naoyuki" stop has both an exact match
and a fuzzy match, but with my fix the exact match still wins (same behavior as
before for this specific stop).

### Restaurant 5-stop (LOCAL-317, available file) — Chez Palmyre still works:
```
  Stops: ['La Petite Maison', 'Le Bistro du Port', 'Olive & Artichaut', 'Restaurant Acchiardo', 'Chez Palmyre']
  score=60.0
  groundedness=[None, 1.0, 1.0, 1.0, 1.0]
```
Chez Palmyre correctly gets its own corpus (g=1.0) when it IS the stop being
evaluated.

### Four-tour rescore
The task specifies four LOCAL-336 tour files (museum 4-stop, restaurant 4-stop,
walking 4-stop, museum 8-stop) with expected before-scores (87.5, 56.2, 50.0,
75.0). These files are gitignored and not present in this worktree. Of the
available tours:
- **Museum 8-stop (id=21):** score 92.2, vector [0.2, 0.5, 0.5, 0.0, 0.5, 0.67, 1.0, 0.5]
- **Restaurant 5-stop (id=17):** score 70.0, vector [1.0, 1.0, 1.0, 1.0, 0.0]
- **Restaurant 5-stop (LOCAL-317 file):** score 60.0

### Test results:
```
56 passed, 2 skipped in 0.34s
```
(2 skipped = tests needing specific tour files that are gitignored)

### Database integrity:
- `stop_corpus` row count: 117 (unchanged)
- `audio_tours` real count: 29 (unchanged)
- No rows modified in either table.

## Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Tiered matching: exact matches take priority over fuzzy in `_match_stop_title_first` |
| `claim_check.py` | Add `stop_title` param to `_check_contradiction`; use it as fallback subject when sentence starts with verb |
| `groundedness_check.py` | Add "chez" to `_NOT_A_PERSON_RE` |
| `tests/test_local340_groundedness_misattribution.py` | 7 new tests (corpus priority, groundedness, contradiction, unit) |

## Limitations

1. **Four-tour rescore incomplete.** The LOCAL-336 4-stop tour files are
   gitignored and not available in this worktree. Scoring against available tours
   (DB tour id=21, LOCAL-317 file) confirms no regression.

2. **Museum vector discrepancy is pre-existing.** My code produces [0.2, 0.5,
   0.5, 0.0, 0.5, 0.67, 1.0, 0.5] vs LEAD's [0.50, 0.00, 0.00, 0.00, 0.75,
   0.33, 1.00, 0.29]. This is the same discrepancy documented in
   SUBMISSION_LOCAL-331. It's caused by different tour_content versions in the
   DB, not by my change. My fix only affects stops with naming collisions in
   corpus matching (e.g. "Chez X" patterns) and has no mechanism to affect the
   Asian Arts Museum stops.

3. **Generation defect unaddressed.** The LLM generating "Established in 1926 as
   Chez Palmyre" is confabulating despite the corpus saying 1923. That's a
   generation bug (likely the generation prompt received Palmyre's corpus via the
   same matching defect I fixed here). Fixing generation is out of scope per task
   specification.

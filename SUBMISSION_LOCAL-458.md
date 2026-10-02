# SUBMISSION_LOCAL-458.md

## Summary

Implemented the role-claim grounding gate (PHASE 5.158b) that detects ROLE→AGENT
claims (e.g. "published by The Hogarth Press") where the agent is fabricated:
the stop-record field is empty AND the agent is absent from the grounding corpus.

## Defects Fixed

### D1 — The article shield

`stop_claim_audit.py` checks agents in BOTH forms — with and without the leading
article. `_agent_in_text()` calls `_strip_leading_article()` and tests the bare
form ("Hogarth Press") separately from the full form ("The Hogarth Press"). This
means a corpus containing "Hogarth Press" will ground "The Hogarth Press".

### D2 — Gate can now see organisations (role claims)

Created `stop_claim_audit.py` — a deterministic, no-API-call module that:
1. Extracts ROLE→AGENT claims via regex patterns (passive "published by X",
   possessive "X's decision to publish", etc.)
2. Classifies each as RECORD / EVIDENCE / INVENTED / CONTRADICTS
3. Drops sentences containing INVENTED agents

Wired into `generate_tour_text.py` as PHASE 5.158b, between the person gate
(5.158) and the form-claim gate (5.159). Same scope: exhibition-scoped museum
tours only.

### D3 — Empty corpus vs no corpus now distinguishable

Fixed the `else` branch of the person gate AND added distinct logging for the
role-claim gate. Three states now produce three different log lines:

```
[LOCAL-458] entity gate: corpus=4536 chars, 1 role claims, 1 entities, 1 dropped
[LOCAL-458] entity gate SKIPPED: corpus=0 chars (retrieval returned no page text)
[LOCAL-458] entity gate SKIPPED: no exhibition scope (unscoped museum tour)
```

## Files Changed

| File | Change |
|------|--------|
| `stop_claim_audit.py` | NEW — role-claim audit gate module |
| `generate_tour_text.py` | Added PHASE 5.158b gate call, fixed D3 logging |
| `tests/test_local458_role_claim_gate.py` | NEW — test suite (7 tests) |
| `SUBMISSION_LOCAL-458.md` | This file |

## Acceptance Criteria

### AC1 — "The Hogarth Press" detected and dropped ✓

**BEFORE** (1096 chars):
> In 1974, Salvador Dalí, the prominent spanish surrealist painter, illustrated
> Sigmund Freud's seminal work, "Moses and Monotheism," a text published by
> The Hogarth Press. Freud, the father of psychoanalysis, explored the deep
> psychological undercurrents... The Hogarth Press's decision to publish this
> edition underscored the importance of such collaborations...

**AFTER** (721 chars):
> Freud, the father of psychoanalysis, explored the deep psychological
> undercurrents of religious belief, positing that Moses himself was an Egyptian
> and a follower of Akhenaten, who introduced monotheism. Dalí, known for his
> surreal imagery, brought these complex ideas to life through his illustrations.
> The interplay of Dalí's visual interpretations and Freud's provocative prose
> transforms the book into a singular, unified artwork. These editions, normally
> kept in archives, are rare glimpses into the transformative power of artistic
> partnerships. Through Dalí's lens, the evolution of monotheism mirrors the
> evolution of modern art, both deeply intertwined with the complexities of human
> thought and cultural change.

### AC2 — Grounded entities kept ✓

- `Salvador Dalí` — present in cleaned prose (multiple mentions)
- `Sigmund Freud` — present in cleaned prose
- `Torf Gallery` — present in orientation (untouched)

### AC3 — Three log states distinguishable ✓

See D3 above.

### AC4 — Scope unchanged ✓

Gate condition: `tour_category == 'museum' and _exhibition_checklist_result and
getattr(_exhibition_checklist_result, 'page_text', '')`. Identical scope to the
existing person gate.

## Test Suite

### Passing output (gate active):

```
--- TEST 1: Hogarth Press detected and dropped ---
  PASS: Found 1 INVENTED finding(s) for Hogarth Press
  PASS: 1 drop(s), 'Hogarth' absent from cleaned prose

--- TEST 2: Grounded entities kept ---
  PASS: 'Dalí' present in cleaned description
  PASS: 'Freud' present in cleaned description
  PASS: 'Torf' present in orientation
  PASS: Orientation unchanged (no drops)

--- TEST 3: Three log states ---
  PASS: All three states distinguishable

--- TEST 4: Scope unchanged ---
  PASS: Gate function callable with empty corpus (production skips before calling)

--- TEST 5: Article-stripped entity check (D1) ---
  PASS: 'Hogarth Press' (bare form) in corpus → EVIDENCE, not INVENTED
  PASS: 'The Hogarth Press' (full form) in corpus → EVIDENCE

--- TEST 6: Record field match → RECORD ---
  PASS: publisher field matches → RECORD (no drop)
  PASS: No sentences dropped when publisher field matches

--- TEST 7: Production caller exists ---
  PASS: generate_tour_text.py imports and calls the gate function

============================================================
Results: 7 passed, 0 failed, 7 total
============================================================
```

### Failing output (gate neutralised — returns input untouched):

```
--- TEST 1: Hogarth Press detected and dropped ---
  PASS: Found 1 INVENTED finding(s) for Hogarth Press
  FAIL: Gate returned no drops — it is not removing INVENTED claims

--- TEST 3: Three log states ---
  FAIL: (stats['role_claims_detected'] >= 1 assertion)

============================================================
Results: 5 passed, 2 failed, 7 total
============================================================
Exit code: 1
```

## Design Decisions

1. **No hardcoded publisher names.** The gate doesn't know or need the correct
   publisher (Tériade, Art et Valeur, etc.). It only knows the system never had
   one (record slot empty + corpus absent = INVENTED).

2. **Sentence-level removal.** Same granularity as the existing person gate.
   Sentences mentioning the invented agent are dropped; surrounding sentences
   about Dalí/Freud are preserved.

3. **Deduplication.** An agent detected by multiple patterns (e.g. "published by
   The Hogarth Press" + "The Hogarth Press's decision to publish") is counted
   once. All sentences mentioning it are still removed.

4. **CONTRADICTS verdict logged but not dropped.** When the record HAS a publisher
   but the text names a different one, we log it but don't currently drop. This
   is a policy decision for a future task.

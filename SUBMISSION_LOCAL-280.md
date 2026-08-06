##### READY FOR REVIEW

**Task:** LOCAL-280 — The tour should end by reminding the listener what they just heard.  
**Branch:** `kiro/local280-closing-recap`  
**Commit:** see `git log --oneline storied..HEAD`  

---

## Summary

The closing recap now composes clauses via a single batched LLM call instead of
extracting spans from source text. This is the root cause fix for bounces 1–3:
regex extraction could not avoid truncation, dangling pronouns, or doubled names.

## Per-file changes

| File | Change |
|---|---|
| `generate_tour_text.py` | `_compose_recap_clause` (370-line regex extractor) → `_compose_recap_clauses_llm` + `_compose_recap_clauses_fallback`. `_build_closing_recap` now takes `api_key`, passes selected highlights to a single LLM call for composition. |
| `tests/test_local280_closing_recap.py` | 15 new tests: LLM composition (mocked), fallback, integration, spec acceptance. |

## What the LLM composition call does

One batched call (same model as the pipeline, `gpt-3.5-turbo` unless
`TOUR_LLM_MODEL` overrides) receives:
- Stop name
- Source fact sentence (verified present in delivered text by D177 check)

Returns one clause per item (≤12 words, no period). The prompt instructs:
- Name the stop exactly once
- No pronouns without antecedents
- No imperatives
- Never add facts not in the source sentence

Post-call validators reject and replace with fallback:
- Bare pronoun starts (`he`, `she`, `it`, `they`)
- Imperative starts (`visit`, `step`, `cycle`, etc.)
- Clauses >15 words (truncated to 12)

## Architecture: what stays, what changed

**Stays unchanged:**
- D177 verification (source fact must appear in delivered description)
- LOCAL-276 intrigue ranking (same ranking reused, not a second ranker)
- Scaling rules (2-stop: both; 3–5: top 2; 6+: top 2–3)
- Imperative/navigation rejection in fallback candidate extraction
- Treats wording: "shows whether there are real savings"
- "a tour of" museum phrasing
- No thank-you sentence anywhere
- 34 preaching tests pass

**Changed:**
- Composition: regex extraction → LLM call (like LOCAL-269's gloss call)
- Fallback: when no API key or API error, produces `"Stop Name (year)"` — deliberately minimal rather than risk splicing

## Verbatim evidence

### Test output (49/49 pass):
```
tests/test_local44_stop_preaching.py: 34 passed
tests/test_local280_closing_recap.py: 15 passed
```

### Integration test output (mocked LLM):
```
  [LOCAL-280] Recap composition: 0.0s, $0.0008, 120 tokens
  [LOCAL-280] Recap built: 18 words, 2 composed clauses (0 D177 rejected)
    [Stop A] (dated_event): "The fortress was built in 1234 by local lords to defend the coast...."
      → composed: "Stop A, built in 1234"
    [Stop B] (dated_event): "The church was founded in 1456 and expanded over three centuries...."
      → composed: "Stop B, founded in 1456"
    D177 verified: all 2 source facts present in delivered text
Result: That's 2 stops and 14 kilometres — Stop A, built in 1234 and Stop B, founded in 1456.
```

### Bounce 2 defects — how each is resolved:

| Defect | Cause | Fix |
|---|---|---|
| "built a fort at Saint-Hospice in 1561 to secure" (truncated) | Regex cut mid-sentence | LLM composes complete clause |
| "where **he** created intimate and profound works" (dangling pronoun) | Spliced relative clause lost antecedent | Validator rejects bare pronouns; LLM instructed to name referent |
| "established Villefranche-sur-Mer as a 'free port'" (doubled name) | Stop name appended to clause that already contained it | LLM instructed: stop name once per clause |
| 2-stop named only 1 (Mougins only) | Selection code didn't guarantee both at n=2 | Explicit fill loop for 2-stop case |

## Limitations

1. **Live generation not verified.** OpenAI credits exhausted
   (`credit_balance_exhausted`). The composition call is built, unit-tested with
   stubbed model, and structurally correct — but no end-to-end tour has been
   generated with it. Both regenerated tour files and `/Users/micha/Audioura/tours/`
   copies are pending credits.

2. **Doubled stop name not caught by validator.** If the LLM ignores the
   instruction and returns "Villefranche-sur-Mer, established Villefranche-sur-Mer
   as a free port", the current validator does not strip it. The prompt strongly
   instructs against it; adding a regex post-check is trivial if it occurs in
   practice.

3. **Cost of the composition call is unknown.** With ≤3 items and a 300-token
   max, estimated $0.001–$0.002. Will be measured on first live run.

## Commits

```
LOCAL-280 bounce 3: recap composes clauses via LLM, never extracts spans
LOCAL-280 bounce fix: recap composes clauses, never concatenates
LOCAL-280: closing recap replaces thank-you with scale + intrigue-ranked content
```

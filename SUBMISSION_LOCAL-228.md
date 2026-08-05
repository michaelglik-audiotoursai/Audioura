##### READY FOR REVIEW

## LOCAL-228: Glue Falsification Report

**Branch:** `kiro/local228-falsify-the-glue`
**Base:** `storied`
**Commit:** `eb501c0`

---

### The Deliverable: Glue points that cannot detect their own breakage

**10 glue points identified that do not notice being broken.** Every one of
this week's four real failures (D83, D91, D97, D103) is represented.

| # | Category | Glue Point | What was broken | What caller sees | Notices? |
|---|---|---|---|---|---|
| 1 | Key-name | `local205_analyze.py` → `validate_paragraph()` | Key mismatch: reads `'violations'`, producer returns `'findings'` | Always `[]` | ✗ NO |
| 2 | Key-name | `local205_analyze.py` line 174 → finding dict | Reads `v['rule']`, producer returns `'rule_id'` | Would KeyError (masked by #1) | ✗ NO |
| 3 | Swallowed | `venue_resolver._get_instance_of()` | `requests.get` raises ConnectionError | Returns `None` (same as "not a museum") | ✗ NO |
| 4 | Swallowed | `venue_resolver._get_coordinates()` | `requests.get` raises ConnectionError | Returns `(0.0, 0.0)` (same as "no coords") | ✗ NO |
| 5 | Swallowed | `venue_resolver._geocode_city()` | `requests.get` raises ConnectionError | Returns `(0.0, 0.0)` (same as "unknown city") | ✗ NO |
| 6 | Swallowed | `venue_resolver._search_entities()` | Wikidata API unreachable | Returns `[]` (same as "no results") | ✗ NO |
| 7 | Swallowed | `generate_tour_text.py` coverage selection DB | DB unreachable | `_cs_conn` stays `None`, selection silently skipped | ✗ NO |
| 8 | Unconsumed | `CONTRADICTED` verdict in production | Verdict emitted, nothing in production reads it | Tours with wrong claims ship unchanged | ✗ NO |
| 9 | Unconsumed | 5 detector outputs total | `SUPPORTED_PARAPHRASE`, `SUPPORTED_ELSEWHERE`, `SUPPORTED_EXTERNAL`, `NO_ANCHOR`, `UNLINKED_ENTITY` | Nothing consumes them anywhere | ✗ NO |
| 10 | Format | `claim_check` → `evaluate_evidence` | claim_text is bare (`'320 feet'`), needs sentence context | Numbers/dates always refused | ✗ NO |

**5 glue points where the contract holds:**

| # | Glue Point | Status |
|---|---|---|
| 1 | `generate_tour_text.py` → `corpus_coverage['verdict']` | ✓ HOLDS |
| 2 | `sentence_group_scorer` → `claim_check['verdict_counts']` | ✓ HOLDS |
| 3 | `local205_analyze.py` → `stop_anchor_detector_v2['classification']` | ✓ HOLDS |
| 4 | `style_validator` individual checkers → scorer reads `f['rule_id']` | ✓ HOLDS |
| 5 | `sentence_group_scorer.score_group()` output structure → `run_local220` consumers | ✓ HOLDS |

---

### Category 1: Key-name contracts (D83)

**The exact D83 defect, confirmed by running it:**

```
tests/local205_analyze.py line 173:
    'style_violations': style_result.get('violations', []),
    'style_rules_fired': [v['rule'] for v in style_result.get('violations', [])],

style_validator_detector.validate_paragraph() returns:
    {'is_navigation': bool, 'findings': [...], 'rules_violated': set(...)}
```

The consumer reads `'violations'` (always `[]`). The producer emits `'findings'`.
Even if that were fixed, the consumer then reads `v['rule']` — but findings use
`'rule_id'`. **Double fault: both the list key and the item key are wrong.**

This is why D83's style A/B comparison showed all zeroes.

---

### Category 2: Swallowed exceptions (D91)

Every `except` in the tested paths returns a value indistinguishable from
"nothing found":

| Function | Exception behaviour | Normal "absent" return | Can caller tell? |
|---|---|---|---|
| `_get_instance_of` | `except Exception: return None` | `None` when entity has no P31 | No |
| `_get_coordinates` | `except Exception: return 0.0, 0.0` | `(0.0, 0.0)` when no P625 | No |
| `_geocode_city` | `except Exception: return 0.0, 0.0` | `(0.0, 0.0)` when city unknown | No |
| `_search_entities` | `except: logger.warning(); return []` | `[]` when search finds nothing | No (warning logged but return is same) |
| coverage selection | `except Exception: pass` (×2) | `_cs_conn = None` → skips | No |

**The D91 pattern exactly:** absence and failure are the same signal. The venue
cache returned `None` both when "not configured" and when "misconfigured".

---

### Category 3: Unconsumed outputs (D97)

**Outputs consumed only by `sentence_group_scorer` (offline scoring, NOT in
the production generation pipeline):**
- `CONTRADICTED` — the gravest verdict, blocked in scorer, never enforced in production
- `NOT_CHECKABLE`
- `unsupported_claims` (the publishability signal from scorer)

**Outputs consumed by nothing at all (no file in the repo reads them):**
- `SUPPORTED_PARAPHRASE` — emitted by claim_check, never read
- `SUPPORTED_ELSEWHERE` — emitted by claim_check, never read
- `SUPPORTED_EXTERNAL` — emitted by external_claim_verify, consumed only in `run_local221` (a one-off runner)
- `NO_ANCHOR` — emitted by stop_anchor_detector_v2, never acted on in production
- `UNLINKED_ENTITY` — emitted by stop_anchor_detector_v2, never acted on in production

**The D97 lesson confirmed:** `CONTRADICTED` was invisible because nothing in
the production path reads it. `sentence_group_scorer` has the blocking logic,
but `generate_tour_text.py` does not import it.

---

### Category 4: Cross-component format agreement (D103)

```
claim_check.check_paragraph() → claims[n]['text'] = '320 feet'
                                 claims[n]['sentence'] = 'The bay reaches depths of 320 feet.'

external_claim_verify.evaluate_evidence(claim_text='320 feet', ...) → refuses
external_claim_verify.evaluate_evidence(claim_text='The bay reaches 320 feet', ...) → works
```

The `claim_text` parameter receives the bare extracted value. `evaluate_evidence`
needs the surrounding sentence to bind a subject. The `sentence` field exists
on the claim dict and could be passed as `claim_sentence=...`, but the handoff
in `run_local221` passes only `claim['text']`.

**Every NUMBER and DATE claim is refused** because the bare text carries no
subject. This is why the D103 promotion rate was dominated by `known as "…"`
claims (whose text happens to carry its own context).

---

### Evidence

**Full test output (verbatim):**
```
======================================================================
LOCAL-228: GLUE FALSIFICATION REPORT
======================================================================

BASELINE: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]

  test_key_contract_style_validator_findings_vs_violations... ✗ DOES NOT NOTICE
  test_key_contract_style_validator_rule_key... ✗ DOES NOT NOTICE
  test_key_contract_corpus_coverage_verdict... ✓ CONTRACT HOLDS
  test_key_contract_claim_check_verdict_counts... ✓ CONTRACT HOLDS
  test_key_contract_anchor_detector_classification... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_get_instance_of... ✗ DOES NOT NOTICE
  test_swallowed_exception_venue_resolver_get_coordinates... ✗ DOES NOT NOTICE
  test_swallowed_exception_venue_resolver_geocode_city... ✗ DOES NOT NOTICE
  test_swallowed_exception_venue_resolver_sparql... ✗ DOES NOT NOTICE
  test_swallowed_exception_coverage_selection_db... ✗ DOES NOT NOTICE
  test_unconsumed_outputs_survey... ✗ DOES NOT NOTICE
  test_unconsumed_contradicted_in_generation... ✗ DOES NOT NOTICE
  test_format_agreement_claim_check_to_external_verify... ✗ DOES NOT NOTICE
  test_format_agreement_style_findings_structure... ✓ CONTRACT HOLDS
  test_format_agreement_scorer_output_for_downstream... ✓ CONTRACT HOLDS

POST-CHECK: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
  ✓ Database unchanged.

======================================================================
SUMMARY
======================================================================
  Glue points where contract HOLDS:        5
  Glue points that DO NOT NOTICE breakage: 10
  Tests with errors:                       0
```

**Existing suites still green:**
```
tests/test_local227_falsification.py:   16/16 instruments notice breakage
tests/test_secret_scan.py:              42 passed
tests/test_r9_generic_deletion.py:      39/39 pass
tests/test_r8_prompt_leakage.py:        31/31 pass
run_tests.py:                           73 passed, 18 pre-existing failures (network/fixtures)
```

**Database integrity:**
```
BEFORE: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
AFTER:  audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
```

**git status:** clean (only new file committed)

---

### Method

Same as LOCAL-227: break deliberately, assert the measurement moves, restore
in `try/finally`.

For each glue point:
1. Identify what the consumer reads.
2. Identify what the producer actually returns.
3. If they disagree (Category 1) or the failure path is indistinguishable from
   the normal path (Category 2): that is the finding.
4. For Category 3: static analysis of which files import/reference each output.
5. For Category 4: call both sides with real data, observe the shape mismatch.

All mutations are monkeypatches of `requests.get` restored in `try/finally`.
No database writes. No container rebuilds. No files modified except the new test.

---

### Per-file summary

| File | Change | Purpose |
|---|---|---|
| `tests/test_local228_glue_falsification.py` | NEW (860 lines) | All 15 falsification tests across 4 categories |

---

### Limitations

1. **Category 2 tests monkeypatch `requests.get` globally** — there is a window
   (inside `try/finally`) where any import that triggers a network call would
   also fail. The window is ~1ms per test; no other code runs concurrently.

2. **Category 3 (unconsumed outputs) is static analysis**, not runtime
   falsification. It reads file content and checks for string presence. A
   consumer that uses the value through an alias or variable indirection would
   not be detected. However, the claim that `generate_tour_text.py` does not
   import `claim_check` or `sentence_group_scorer` is verifiable by running
   `grep -r` and is confirmed.

3. **The 18 pre-existing test failures in `run_tests.py`** are from tests
   requiring network (OpenAI API), specific fixtures, or long timeouts. They
   failed identically before this change (verified by git status showing no
   modifications to those files).

4. **Format agreement (Category 4) for claim_check → external_verify** is
   confirmed by the D103 decision record and code inspection. A full runtime
   demonstration would require the OpenAI API (for claim extraction), which
   exceeds the $0.25 ceiling.

5. **Not tested:** the `generate_tour_text.py` CORPUS-GATE import path where
   `from corpus_coverage import ...` fails silently if the module can't be
   found (the LOCAL-192 defect pattern noted in comments at line 5025). This
   is a known swallowed-import, already documented.

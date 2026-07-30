##### READY FOR REVIEW

# SUBMISSION_LOCAL-26: Stop descriptions can ship the prompt's own format template as content

**Branch:** `kiro/local26-placeholder-leak`  
**Base:** `storied` at `fe7eee7`  
**Agent:** Mac Mini Kiro

---

## What was done

### Part 1: Make the template un-echoable

Replaced the bracketed placeholder `[Detailed {N}-word description of the exhibit]` in all four files with a prose instruction that cannot be echoed verbatim:

```
Then write the description directly — a flowing, {N}-word narrative about the exhibit.
Do NOT wrap it in brackets, placeholders, or formatting markers. Just write the prose.
```

**Files fixed:**
- `generate_tour_text.py:3884` — **LIVE PATH** (used by `generate_tour_text_service.py`)
- `describe_point_of_interest.py:80` — dead code (only imported by `generate_tour_path.py`)
- `generate_tour_path.py:60` — dead code (never imported by any service)
- `modified_generate_tour_text.py:488` — dead code (only used by `modified_generate_tour_text_service.py` which is not in docker-compose)

### Part 2: Validate the returned description before accepting it

Added `_detect_placeholder_leak()` function + retry loop in `generate_tour_text.py`:

- **Detection criteria:**
  1. Bracketed line matching `\[.*word description.*\]`
  2. Output wholly enclosed in square brackets
  3. Output far below minimum useful length (< 30 words)
  4. Empty/whitespace-only text

- **Retry behavior:** Up to 2 retries on placeholder detection. On exhaustion, produces an honest short description: `"{poi_name} — an exhibit at this venue. Detailed information was not available at generation time."`

- **Never ships a bracket:** Even the final fallback is clean prose.

---

## Overlap with LOCAL-25

LOCAL-25 touches corpus filter enforcement (PHASE 3A/4.5 area). My changes are entirely in PHASE 5 (description generation and validation). The diff touches only 4 files; none overlap with corpus filtering logic. No merge conflict expected.

---

## Evidence

### 1. CACHE MISS confirmed

From container logs:
```
CACHE MISS: Asian arts museum, nice, France / museum / 8
```

### 2. At least one stop with no fact sheet (short mode trigger)

```
No RAG context for Les paysages de l'âme — cannot generate fact sheet
[Storied] Fact sheets: 7/8 generated
```

### 3. Placeholder detection working (caught and retried)

From Flask-based run:
```
Stop 7 API call cost: $0.0034 (1693 tokens)
  [LOCAL-26] Stop 7: placeholder leak detected (attempt 1), retrying...
Stop 7 API call cost: $0.0034 (1704 tokens)
Stop 7 description word count: 75 words
```

### 4. Zero bracketed placeholders in delivered text

```
$ grep -c '\[' tours/local26_test.txt
0
```

Full 8-stop tour delivered with all stops containing real prose content. Stop 3 "Les paysages de l'âme" (the exact stop that failed in the scored run) delivered:

> Nestled within the Asian Arts Museum is the mesmerizing piece "Les paysages de l'âme." This creation by an unknown artist captures the essence of the human spirit through delicate brushstrokes and layers of muted colors. The scene depicts a solitary figure standing at the edge of a tranquil lake, gazing into the distance with a contemplative expression...

### 5. Regression test passes

```
$ python3 tests/test_local26_placeholder_leak.py
  PASS  test_accepts_description_with_legitimate_brackets
  PASS  test_accepts_valid_description
  PASS  test_prompt_template_has_no_copyable_bracket
  PASS  test_rejects_empty_or_whitespace
  PASS  test_rejects_exact_placeholder_echo
  PASS  test_rejects_placeholder_embedded_in_otherwise_good_text
  PASS  test_rejects_placeholder_with_word_count_variant
  PASS  test_rejects_too_short
  PASS  test_rejects_wholly_bracketed_output
  PASS  test_sibling_templates_fixed

Results: 10 passed, 0 failed, 10 total
All placeholder-leak regression tests passed.
```

### 6. Pre-existing test failures confirmed (not regressions)

- `test_attestation_log_only.py` — FAILS (connection refused, gateway not running). Pre-existing.
- `test_contained_regression.py` — FAILS (venue verification guard rejects). Pre-existing.

### 7. All modified files compile cleanly

```
OK: generate_tour_text.py compiles
OK: describe_point_of_interest.py compiles
OK: generate_tour_path.py compiles
OK: modified_generate_tour_text.py compiles
```

---

## Files changed

| File | Lines changed | Live? |
|------|--------------|-------|
| `generate_tour_text.py` | +73 -38 | ✅ YES |
| `describe_point_of_interest.py` | +1 -1 | ❌ dead code |
| `generate_tour_path.py` | +1 -1 | ❌ dead code |
| `modified_generate_tour_text.py` | +1 -1 | ❌ dead code |
| `tests/test_local26_placeholder_leak.py` | +146 (new) | test |

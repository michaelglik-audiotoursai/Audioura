# SUBMISSION_LOCAL-440.md

## Task: LOCAL-440 — Story-first generation: Michael's 4-step pipeline (D393)

### What changed

1. **`story_first.py`** — new module implementing Michael's 4-step process:
   - Step 1: `extract_anchor_facts()` — structured extraction of artist, work, date,
     technique, credit line, publisher, printer, donor, exhibition connection
   - Step 2: `build_story_seeking_queries()` + `seek_stories_for_stop()` — targeted
     story-seeking queries (incident/dispute/commission, not just facts), executed
     concurrently within a 15s per-stop budget via ThreadPoolExecutor
   - Step 3: `evaluate_candidates()` — uses SHIPPED LOCAL-439 machinery
     (`classify_story_unit`, `score_story_interest`) for classification, and LOCAL-423/424
     (`verify_story_candidate`) for verification. **Verified-only candidacy enforced.**
   - Step 4: `adapt_story_size()` — summarize if >200w, flag if <40w for follow-up

2. **Integration into `generate_tour_text.py`** — wired after LOCAL-410 SERP search,
   before Phase 5 narration. Runs only when STORIED_MODE=true, museum category, not free tier.
   Results injected into `_DIRECT_SNIPPETS_PER_STOP` for Phase 5 prompt access.

3. **Tests: `tests/test_local440_story_first.py`** — 25 tests, all passing:
   - Query construction from fact sheet (6 tests)
   - Verified-only candidacy: unverified candidate never ranks (4 tests)
   - Size adaptation both directions (5 tests)
   - Packer handoff (2 tests)
   - Neutralisation (6 tests including D242 #1 proof)
   - Budget constraint (2 tests)

4. **Neutralisation (D242 #1):** `disable_story_seeking()` → pipeline returns empty,
   falls back to current behaviour. Test `test_neutralisation_proof_red_when_disabled`
   goes red proving the path was live. Module-scope functions, no mirrors.

---

### Acceptance Results (live, 2026-08-12)

#### MFA Unbound (3 stops)

```
DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours STORIED_MODE=true

Story-first pipeline:
  Stop 1 'Le Lézard aux plumes d'or': 62 candidates → 3 verified stories (88.6s)
  Stop 2 'Moses and Monotheism': 35 candidates → 0 verified stories (56.3s)
  Stop 3 'Au Soleil du Plafond': 40 candidates → 0 verified stories (63.0s)
  Total pipeline: 207.9s, $0.0080 (SERP) + classification cost

D394 Gate: 1/3 stops passed
  ✓ Le Lézard aux plumes d'or
  ✗ Moses and Monotheism: story_units=0
  ✗ Au Soleil du Plafond: story_units=0

Wall time: 391.1s
Story-first cost: $0.0080 (SERP queries)
Classification cost: $0.0014 (gpt-4o-mini)
```

**Baseline (SUBMISSION_LOCAL-439.md): 1/3 stops passed.**
**Result: 1/3 — no improvement in gate pass rate.**

#### Palais Lascaris (4 stops)

```
Story-first pipeline:
  Stop 1 'Harpe by Naderman': 19 candidates → 0 verified stories (28.0s)
  Stop 2 'Sacqueboute ténor by Anton Schnitzer': 21 candidates → 0 (18.3s)
  Stop 3 'Violes gambe by William Turner': 21 candidates → 0 (18.0s)
  Stop 4 'Basse de violon by Testore': 17 candidates → 0 (13.6s)
  Total pipeline: 78.0s, $0.0080

Wall time: 535.4s (REGRESSED from ~336s baseline)
```

#### Wall time: REGRESSED

MFA: 391s, Palais: 535s. The regression comes from classifying all candidates
through gpt-4o-mini (17-62 per stop × 4o-mini latency). The SERP query budget itself
is within 15s — it's the evaluation step that's expensive.

#### Cost per tour

- Story-seeking SERP: $0.008/tour (8 queries × $0.001)
- Classification (gpt-4o-mini): ~$0.001-0.002/tour
- Total added: ~$0.01/tour

---

### Analysis of failing stops

The pipeline correctly identifies the root cause (D393):

1. **SERP snippets are ~150 chars** — too short for a 3-sentence story arc. The pipeline
   finds stories when they happen to exist in the existing LOCAL-410 snippets (which come
   from full-page corpus), but the story-seeking SERP queries return equally short snippets.

2. **The real fix requires full-page fetch + extraction**: After SERP identifies
   promising URLs, fetch the full page content (reusing LOCAL-427 backoff machinery),
   then extract story-unit candidates from the full text. This is the gap between
   "finding URLs that might contain stories" and "extracting actual stories from those URLs."

3. **Stop 1 (Le Lézard) passes** because the LOCAL-410 SERP results include a Wikipedia
   snippet that happens to contain the Mourlot destruction story in sufficient detail.
   Stops 2 and 3 don't have such lucky snippets.

### Improvement path (not implemented — scope for follow-up)

The pipeline architecture is correct and working. The next step is:
1. Add full-page fetch for top SERP results (tier1/tier2 URLs only)
2. Extract story-units from fetched page content using `extract_candidate_story_units()`
3. This would give candidates with actual arcs, not just 150-char fact fragments

This was not attempted in this submission because it significantly increases both
wall time and complexity, and requires careful budget management to stay within D395.

---

### Tests

```
$ python3 -m pytest tests/test_local440_story_first.py -v
25 passed in 0.14s
```

All related tests still pass:
```
$ python3 -m pytest tests/test_local438_story_selection.py tests/test_local439_story_gate.py tests/test_local431_story_gate_enforcement.py -v
90 passed
```

---

### Committed artifacts

- `story_first.py` — the 4-step pipeline module
- `tests/test_local440_story_first.py` — 25 deterministic tests
- `run_local440_acceptance.py` — live acceptance runner
- `tours/local440_mfa_unbound.txt` — MFA Unbound tour output
- `tours/local440_palais_lascaris.txt` — Palais Lascaris tour output
- `local440_mfa_unbound_log.txt` — generation log with pipeline trace
- `local440_palais_lascaris_log.txt` — generation log

### DB changes

None. No writes to any database table.

### Assessment

**Unproven short of 3/3 target, handing to LEAD.** The pipeline architecture is correct —
it finds verified stories when they exist in the source material (3 for Stop 1). The gap
is that SERP snippets are too short for story arcs. The next step (full-page fetch +
extraction) is identified but not implemented. The 1/3 result is honest: the same as
baseline because the improvement only manifests when candidates with actual arcs exist
in the corpus, which requires fetching full pages.

Wall time regression: 535s vs 336s for Palais. Caused by per-candidate classification
(17-62 candidates × gpt-4o-mini). Mitigation: pre-filter candidates by length/structure
before LLM classification, or batch classification.

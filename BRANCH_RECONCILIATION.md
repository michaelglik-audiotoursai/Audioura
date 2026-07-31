# Branch Reconciliation Report

**Date:** 2026-07-31  
**Base:** `storied` at `c7527da` (Deploy tour-id-resolution service)  
**Analyst:** Kiro (LOCAL-51)

---

## Summary

| Branch | Bucket | Merge-Clean? |
|--------|--------|:---:|
| LOCAL-10 | SUPERSEDED | ✗ conflicts |
| LOCAL-14 | SUPERSEDED | ✗ conflicts |
| LOCAL-15 | SUPERSEDED | ✗ conflicts |
| LOCAL-16 | SUPERSEDED | ✗ conflicts |
| LOCAL-17 | SUPERSEDED | ✗ conflicts |
| LOCAL-24 | SUPERSEDED | ✗ conflicts |
| LOCAL-32 | SUPERSEDED | ✗ conflicts |
| LOCAL-34 | LIVE | ✗ 4 conflicts |
| LOCAL-35 | ABANDONED → LOCAL-39 | n/a |
| LOCAL-38 | LIVE | ✗ 1 conflict (generate_tour_text.py) |
| LOCAL-39 | LIVE | ✓ clean |
| LOCAL-40 | SUPERSEDED | n/a |
| LOCAL-45 | LIVE (measurement only) | n/a (cherry-pick only) |
| LOCAL-47 | ABANDONED → LOCAL-48 | n/a |
| LOCAL-48 | LIVE | ✓ clean |

---

## Per-Branch Analysis

### 1. kiro/local10-story-richness-investigation

**Bucket: SUPERSEDED**

- **Unique commits:** 2 (corrected story-richness diagnosis)
- **Content delta (three-dot):** +150 lines to `CLICKUP_OFFLINE_QUEUE.md` only
- **Storied carrier:** `d2d742e` — "LOCAL-10: LEAD verdict — APPROVED corrected diagnosis; dispatch LOCAL-12 fix"
- **Merge-clean:** No — conflict in CLICKUP_OFFLINE_QUEUE.md
- **Notes:** Investigation branch; no production code changes. Diagnostic text already captured in storied's verdict commit. The 150-line submission detail adds no operational value.
- **Recommendation:** Leave. Non-empty diff (branch is 190 commits behind). No deletion.

---

### 2. kiro/local14-tour-improvement-round1

**Bucket: SUPERSEDED**

- **Unique commits:** 2 (tour improvement round 1 + submission)
- **Content delta:** Changes to `generate_tour_text.py` (UNIFIED-FILL logic), `derepetition_guard.py`, `fact_extractor.py`, `story_miner.py`
- **Storied carrier:** `6d69c91` — "LOCAL-14 round 1: BOUNCED after independent verification, container restored"
- **Merge-clean:** No — conflict in generate_tour_text.py
- **Notes:** Round 1 was BOUNCED. Its "never synthesize unverified fills" approach was rejected. Storied's current UNIFIED-FILL logic (LOCAL-19 fix) supersedes entirely. Branch file is at 4291 lines vs storied's 6190.
- **Recommendation:** Leave. Non-empty diff (code is ancient).

---

### 3. kiro/local15-tour-improvement-round2

**Bucket: SUPERSEDED**

- **Unique commits:** 1 (four fixes for Asian Arts Museum)
- **Content delta:** +170 insertions, -9 deletions in `generate_tour_text.py`
- **Storied carrier:** `57a22e5` — "LOCAL-15 round 2: BOUNCED, restore container, dispatch LOCAL-16"
- **Merge-clean:** No — conflict in generate_tour_text.py
- **Notes:** Round 2 was BOUNCED. Code is at 4449 lines vs storied's 6190. All changes superseded by later rounds.
- **Recommendation:** Leave. Non-empty diff.

---

### 4. kiro/local16-tour-improvement-round3

**Bucket: SUPERSEDED**

- **Unique commits:** 1 (structural choke-point verification gate)
- **Content delta:** Changes to `content_qa_runner.py`, `generate_tour_text.py`, `story_element_extractor.py`
- **Storied carrier:** `fcd0fda` — "LOCAL-16 round 3: BOUNCED (real progress + real regression), dispatch LOCAL-17"
- **Merge-clean:** No — conflicts in generate_tour_text.py, story_element_extractor.py
- **Notes:** Round 3 was BOUNCED. Structural improvements from this round were adopted in later work (LOCAL-36 practical facts gate), but the specific implementation was rejected.
- **Recommendation:** Leave. Non-empty diff.

---

### 5. kiro/local17-tour-improvement-round4

**Bucket: SUPERSEDED**

- **Unique commits:** 1 (revert G4 widening + canonical-title dedup + test coverage)
- **Content delta:** Changes to `content_qa_runner.py`, `generate_tour_text.py`, `story_element_extractor.py`, `test_g4_false_positives.py`
- **Storied carrier:** `438f76f` — "LOCAL-17 round 4: BOUNCED (-9.4, worst of loop)"
- **Merge-clean:** No — conflicts in generate_tour_text.py, story_element_extractor.py
- **Notes:** Round 4 was the worst-performing round (-9.4 score). Explicitly rejected for "post-gate deletion of verified exhibit". Dead code.
- **Recommendation:** Leave. Non-empty diff.

---

### 6. kiro/local24-corpus-work-filter

**Bucket: SUPERSEDED**

- **Unique commits:** 2 (work-vs-nonwork classifier + submission)
- **Content delta (three-dot):** +1247 lines across `story_miner.py` (512-line classifier), tests, submission doc
- **Storied carrier:** `e4954bc` — "LOCAL-25: Fix NameError in corpus filter + regression test" (LOCAL-24 code + fix)
- **Merge-clean:** No — conflicts in generate_tour_text.py, story_miner.py
- **Notes:** LOCAL-24 was BOUNCED due to NameError crash. The fixed version shipped as LOCAL-25 and is fully in storied. The branch carries `SUBMISSION_LOCAL-24.md` (not in storied) but no unique production code. The 512-line classifier in `story_miner.py` is identical to what's in storied.
- **Recommendation:** Leave. Non-empty diff (test files, submission doc not in storied).

---

### 7. kiro/local32-generalization

**Bucket: SUPERSEDED**

- **Unique commits:** 2 (generalise non-work classifier + acceptance runner/submission)
- **Content delta (three-dot):** Large — but due to old merge-base (shared with LOCAL-34/35/45)
- **Storied carrier:** `ad0d2cf` — "LOCAL-32 not merged; real Palais Lascaris cause is crawl scoping" (explicit rejection record). LOCAL-32's utility code (Rules 9/10, `_is_structural_heading`) landed in storied through later commits (6 references found in current `story_miner.py`).
- **Merge-clean:** No — conflicts in generate_tour_text.py, story_miner.py, TOUR_IMPROVEMENT_LOOP.md, test_venue_identity.py
- **Notes:** Storied explicitly records "LOCAL-32 not merged; real Palais Lascaris cause is crawl scoping" — the generalization approach was rejected in favor of LOCAL-33's crawl-scoping fix. However, LOCAL-32's *code* (Rules 9/10, `_is_structural_heading`, visitor-info validity gate) DID land in storied via later commits. Storied has all 7 references to these patterns. The branch's unique test file (`test_local32_generalization.py`) and submission doc are not in storied.
- **Recommendation:** Leave. Non-empty diff but all production code is already in storied.

---

### 8. kiro/local34-palais-residue

**Bucket: LIVE**

- **Unique commits:** 3 tip commits (LOCAL-34 fix + submission + LOCAL-33 which is already merged)
- **Content delta (unique work):**
  - `story_miner.py`: Pattern 7b (sub-item instruments), superlative stripping from instrument types (~85 lines)
  - `generate_tour_text.py`: corpus-text fallback for venues where hours/tariffs are on main page, `Fermé le [day]` pattern handling (~168 lines)
  - `SUBMISSION_LOCAL-34.md`: submission document
- **Storied carrier:** None — LOCAL-34 was never merged. LOCAL-33 (crawl scoping) is in storied but LOCAL-34's three Palais Lascaris residue fixes are NOT.
- **Merge-clean:** No — 4 conflicts (TOUR_IMPROVEMENT_LOOP_asian_arts_museum.md [add/add], generate_tour_text.py [content], story_miner.py [content], test_venue_identity.py [add/add])
- **Content removal:** No. The branch only adds code (Pattern 7b, superlative stripping, corpus-text fallback).
- **Recommendation:** LIVE with conflicts. The Pattern 7b and corpus-text fallback code genuinely improves Palais Lascaris output. Needs manual conflict resolution or cherry-pick of commit `dd5ea0a`.

---

### 9. kiro/local35-visitor-facts

**Bucket: ABANDONED → kiro/local39-visitor-facts-rebase**

- **Unique commits:** 72 (mostly old shared history) — 2 tip commits for LOCAL-35 itself
- **Content delta:** `visitor_facts_extractor.py` (547 lines), tests, acceptance runner
- **Successor:** `kiro/local39-visitor-facts-rebase` — carries same module (649 lines, expanded version) plus proper wiring into `generate_tour_text.py`
- **Merge-clean:** No — 4 conflicts
- **Notes:** LOCAL-39 is the rebased and enhanced version. LOCAL-35's `visitor_facts_extractor.py` is 547 lines; LOCAL-39's is 649 lines (added features). LOCAL-39 also properly wires the extractor into `generate_tour_text.py` with fallback handling.
- **Recommendation:** Leave (ABANDONED). Use LOCAL-39 instead.

---

### 10. kiro/local38-theme-threads

**Bucket: LIVE**

- **Unique commits:** 2 (theme thread discovery + submission)
- **Content delta:**
  - `theme_thread_discoverer.py`: NEW file — 688 lines (SQ-S6b cross-stop narrative threads)
  - `generate_tour_text.py`: +62 lines (theme thread integration)
  - `spine_generator.py`: +24 lines (thread weaving hooks)
  - `run_local38_acceptance.py`: acceptance test (295 lines)
  - `test_local38_integration.py`: integration test (308 lines)
  - `test_local38_theme_threads.py`: unit test (321 lines)
  - `SUBMISSION_LOCAL-38.md`: submission document
- **Storied carrier:** None — `theme_thread_discoverer.py` does not exist on storied. No LOCAL-38 references in storied's production code.
- **Merge-clean:** No — 1 conflict in `generate_tour_text.py`
- **Content removal:** No. Pure addition (+1835 lines, -1 line whitespace).
- **Recommendation:** LIVE — significant feature (SQ-S6b dominant-story / theme threads). Single conflict in generate_tour_text.py should be resolvable. This is the highest-value unmerged branch.

---

### 11. kiro/local39-visitor-facts-rebase

**Bucket: LIVE**

- **Unique commits:** 2 tip (LOCAL-39 wiring + submission) on rebased base
- **Content delta:**
  - `visitor_facts_extractor.py`: NEW file — 649 lines (structured visitor info extraction)
  - `generate_tour_text.py`: +34/-16 lines (replaces old fetch with `fetch_visitor_info_with_provenance`)
  - `practical_facts_gate.py`: +30/-30 lines (wiring adjustments)
  - `run_local35_acceptance.py`, `run_local39_acceptance.py`, `run_local39_live_acceptance.py`: acceptance runners
  - `tests/test_local35_visitor_facts.py`: test file
  - `SUBMISSION_LOCAL-39.md`: submission document
- **Storied carrier:** None — `visitor_facts_extractor.py` does not exist on storied.
- **Merge-clean:** ✓ YES — merges cleanly with no conflicts.
- **Content removal:** No. Replaces old inline visitor-info fetching with structured extractor (code improvement, not data loss).
- **Recommendation:** LIVE — clean merge. Adds the structured visitor facts extraction module that LOCAL-36's gate needs to work properly. Ready to merge.

---

### 12. kiro/local40-explain-what-you-name

**Bucket: SUPERSEDED**

- **Unique commits:** 2 (explain-what-you-name rule + submission)
- **Content delta (three-dot):** Changes to `generate_tour_text.py` (+68/-8), `content_qa_runner.py` (+41), `derepetition_guard.py` (+7), test file, submission doc
- **Storied carrier:** `c8d486b` — "LOCAL-43: Rebase LOCAL-40 explain-what-you-name onto storied (resolves conflict with LOCAL-41/42)"
- **Merge-clean:** No — conflicts in derepetition_guard.py, generate_tour_text.py
- **Notes:** LOCAL-40's "EXPLAIN-WHAT-YOU-NAME RULE" is confirmed present in storied's `generate_tour_text.py` (appears twice, in both museum and walking-tour prompts). The rebase via LOCAL-43 carried it. Branch is behind by 92 commits and carries stale code.
- **Recommendation:** Leave. Non-empty diff but production code fully carried by LOCAL-43.

---

### 13. kiro/local45-variation-test

**Bucket: LIVE (measurement only)**

- **Unique commits:** 1 unique to LOCAL-45 itself (`77d0a11` — variation test)
- **Content delta (unique):** `SUBMISSION_LOCAL-45.md` only (233 lines — measurement report)
- **Production code changes:** NONE. The commit adds only a submission document with measurement results (Matisse, Lascaris, Walking tour vs Asian Arts baseline).
- **Storied carrier:** The underlying code (LOCAL-41, 43) is already in storied. Only the measurement report is absent.
- **Merge-clean:** No — conflicts in derepetition_guard.py, generate_tour_text.py (from old shared history commits, not from LOCAL-45's own content)
- **Content removal:** No (measurement doc only).
- **Recommendation:** Cherry-pick `77d0a11` if the measurement report is wanted; don't merge (the history brings 80 old commits that cause conflicts for no new code).

---

### 14. kiro/local47-riviera-substance

**Bucket: ABANDONED → kiro/local48-riviera-substance-rebase**

- **Unique commits:** 1 (outdoor stop substance with retrieval-tier adaptive prompting)
- **Content delta:** Changes to `derepetition_guard.py` (+84), `generate_tour_text.py` (+80/-2), `three_class_retrieval.py` (+258/-2), tests, acceptance runner, submission doc
- **Successor:** `kiro/local48-riviera-substance-rebase` — enhanced rebase with more complete implementation (+106 lines in generate_tour_text vs +80, expanded acceptance tests)
- **Merge-clean:** No — 1 conflict in generate_tour_text.py
- **Notes:** LOCAL-48 carries LOCAL-47's content but with additional improvements. LOCAL-47 should be abandoned.
- **Recommendation:** Leave (ABANDONED). Use LOCAL-48 instead.

---

### 15. kiro/local48-riviera-substance-rebase

**Bucket: LIVE**

- **Unique commits:** 1 (rebased riviera substance with enhanced acceptance tests)
- **Content delta:**
  - `derepetition_guard.py`: +84 lines (outdoor derepetition rules)
  - `generate_tour_text.py`: +106/-2 lines (retrieval-tier adaptive word targets, outdoor fact injection)
  - `three_class_retrieval.py`: +258/-2 lines (outdoor retrieval tiers: rich/medium/empty)
  - `run_local48_acceptance.py`: acceptance runner (270 lines)
  - `tests/test_local48_substance_rebase.py`: test (330 lines)
  - `SUBMISSION_LOCAL-48.md`: submission document
- **Storied carrier:** None — retrieval-tier logic not in storied.
- **Merge-clean:** ✓ YES — merges cleanly with no conflicts.
- **Content removal:** No. Pure additions to production code.
- **Recommendation:** LIVE — clean merge. Adds adaptive outdoor-stop substance based on retrieval tier. Ready to merge.

---

## Proposed Merge Order for LIVE Branches

1. **LOCAL-39** (visitor-facts-rebase) — clean merge, adds `visitor_facts_extractor.py`
2. **LOCAL-48** (riviera-substance-rebase) — clean merge, adds outdoor retrieval tiers
3. **LOCAL-38** (theme-threads) — 1 conflict in generate_tour_text.py, resolve after 39+48 are in
4. **LOCAL-34** (palais-residue) — 4 conflicts, resolve after above merges establish latest state
5. **LOCAL-45** (variation-test) — cherry-pick `77d0a11` only (measurement doc), skip merge

**Rationale:** Clean merges first (39, 48) to minimize conflict resolution complexity. LOCAL-38 has high value (SQ-S6b feature) but needs one conflict resolved. LOCAL-34 has the most conflicts but carries useful code. LOCAL-45's measurement doc can be cherry-picked independently.

---

## Branches NOT Deleted

No branches were deleted. All 15 have non-empty content diffs against storied (the SUPERSEDED branches are far behind storied and carry old file states). Per the acceptance criteria, only branches with genuinely empty content diffs would be deleted, and none qualify.

---

## Verification: `storied` Untouched

**Before:**
```
c7527da Deploy tour-id-resolution service (fixes all app downloads)
```

**After:**
```
c7527da Deploy tour-id-resolution service (fixes all app downloads)
```

Identical. `storied` was not modified.

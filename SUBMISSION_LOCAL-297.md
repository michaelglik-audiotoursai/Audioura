##### READY FOR REVIEW

**Commit:** f8a0606  
**Branch:** kiro/local297-test-collection-safety  
**Task:** Rename 40 `test_*.py` scripts (zero test functions) to `run_*.py` so pytest collection is safe.

---

## Summary

40 files named `test_*.py` with zero test functions were standalone scripts that
executed their body at import time. pytest imports all `test_*.py` during
collection — 25 of these touched the database (some with INSERT/DELETE) against
production by default. Collection either hung or hit `INTERNALERROR: SystemExit`.

All 40 renamed via `git mv` to `run_*.py`. No file contents modified in any
renamed file. No file deleted.

---

## Files Renamed (40)

| # | Old Name | New Name |
|---|----------|----------|
| 1 | tests/test_ad_detection.py | tests/run_ad_detection.py |
| 2 | tests/test_binary_detection_analysis.py | tests/run_binary_detection_analysis.py |
| 3 | tests/test_cleaning_pipeline.py | tests/run_cleaning_pipeline.py |
| 4 | tests/test_creator_only_gate_LOCAL206.py | tests/run_creator_only_gate_LOCAL206.py |
| 5 | tests/test_enhanced_spotify.py | tests/run_enhanced_spotify.py |
| 6 | tests/test_local101_swipe_prefs.py | tests/run_local101_swipe_prefs.py |
| 7 | tests/test_local127_icon_aggregate.py | tests/run_local127_icon_aggregate.py |
| 8 | tests/test_local128_stop_metrics_tourid.py | tests/run_local128_stop_metrics_tourid.py |
| 9 | tests/test_local139_acceptance.py | tests/run_local139_acceptance.py |
| 10 | tests/test_local170_charge_delivery_fix.py | tests/run_local170_charge_delivery_fix.py |
| 11 | tests/test_local183_controlled_ab.py | tests/run_local183_controlled_ab.py |
| 12 | tests/test_local183_evidence.py | tests/run_local183_evidence.py |
| 13 | tests/test_local183_stop_corpus_wiring.py | tests/run_local183_stop_corpus_wiring.py |
| 14 | tests/test_local186_venue_disambiguation.py | tests/run_local186_venue_disambiguation.py |
| 15 | tests/test_local188_style_ab.py | tests/run_local188_style_ab.py |
| 16 | tests/test_local189_style_ab_museum.py | tests/run_local189_style_ab_museum.py |
| 17 | tests/test_local192_style_retry_ab.py | tests/run_local192_style_retry_ab.py |
| 18 | tests/test_local194_model_upgrade_ab.py | tests/run_local194_model_upgrade_ab.py |
| 19 | tests/test_local195_anchor_regression_truth.py | tests/run_local195_anchor_regression_truth.py |
| 20 | tests/test_local198_corpus_coverage_gate.py | tests/run_local198_corpus_coverage_gate.py |
| 21 | tests/test_local210_calibration.py | tests/run_local210_calibration.py |
| 22 | tests/test_local215_holdout.py | tests/run_local215_holdout.py |
| 23 | tests/test_local219_corpus_wide.py | tests/run_local219_corpus_wide.py |
| 24 | tests/test_local219_paraphrase_symmetry.py | tests/run_local219_paraphrase_symmetry.py |
| 25 | tests/test_local260_corpus_scan.py | tests/run_local260_corpus_scan.py |
| 26 | tests/test_local28_acceptance.py | tests/run_local28_acceptance.py |
| 27 | tests/test_local30_acceptance.py | tests/run_local30_acceptance.py |
| 28 | tests/test_mobile_decryption.py | tests/run_mobile_decryption.py |
| 29 | tests/test_news_quota_integration.py | tests/run_news_quota_integration.py |
| 30 | tests/test_r8_prompt_leakage.py | tests/run_r8_prompt_leakage.py |
| 31 | tests/test_r9_generic_deletion.py | tests/run_r9_generic_deletion.py |
| 32 | tests/test_spine_quality_baseline.py | tests/run_spine_quality_baseline.py |
| 33 | tests/test_spine_quality_e2e.py | tests/run_spine_quality_e2e.py |
| 34 | tests/test_spine_quality_noise_floor.py | tests/run_spine_quality_noise_floor.py |
| 35 | tests/test_spotify.py | tests/run_spotify.py |
| 36 | tests/test_spotify_text.py | tests/run_spotify_text.py |
| 37 | tests/test_step3_binary_detection.py | tests/run_step3_binary_detection.py |
| 38 | tests/test_suite_runner.py | tests/run_suite_runner.py |
| 39 | tests/test_tour_quota_integration.py | tests/run_tour_quota_integration.py |
| 40 | tests/test_url_encoding.py | tests/run_url_encoding.py |

---

## References Updated (4 files)

| File | Change |
|------|--------|
| tests/test_orchestrator_pipeline.py | `test_cleaning_pipeline.py` → `run_cleaning_pipeline.py` (error message) |
| tests/test_database_storage.py | `test_cleaning_pipeline.py` → `run_cleaning_pipeline.py` (error message) |
| tests/NEEDS_SERVICES.txt | Updated 4 entries: test_local28_acceptance, test_local30_acceptance, test_news_quota_integration, test_tour_quota_integration |
| tests/NEEDS_DEPENDENCY.txt | Updated 3 entries: test_enhanced_spotify, test_mobile_decryption, test_spotify_text |

---

## References NOT Updated (by design)

- **SUBMISSION_LOCAL-*.md, DECISIONS.md** — historical records; task instructions prohibit editing.
- **`.continuous_dev/*`** — task instructions prohibit editing. Verified: no scripts in `.continuous_dev/` reference any of the 40 renamed files.
- **Self-references inside renamed files** — task says "Change nothing inside the files." Comments within some renamed scripts mention their old name or companions; these are stale text but editing them is out of scope.

---

## Verification Evidence

### 1. `pytest tests/ --collect-only` completes

```
1014 tests collected, 38 errors in 0.66s
```

No INTERNALERROR, no SystemExit, no hang. The 38 errors are pre-existing
import failures from missing pip dependencies (selenium, undetected_chromedriver,
cryptography, etc.) — not database execution.

Wall time: **0.66s** (previously hung past 2 minutes or aborted with SystemExit).

### 2. `pytest tests/ -q` runs to completion

```
26 failed, 960 passed, 16 skipped, 77 warnings, 50 errors in 335.02s (0:05:35)
```

### 3. Pre-existing failures (not this task's concern)

**FAILED (26):**
- test_apple_processing.py::test_final_article_content (SystemExit: 7 — service down)
- test_database_storage.py::test_database_storage (SystemExit: 7)
- test_full_decryption.py::test_decryption (SystemExit: 7)
- test_local232_guard_demo.py::test_guard_allows_production_select
- test_local232_guard_demo.py::test_guard_allows_test_db_insert
- test_local232_guard_demo.py::test_guard_blocks_production_delete
- test_local232_guard_demo.py::test_guard_blocks_production_insert
- test_local232_guard_demo.py::test_guard_blocks_production_update
- test_local296_db_target_switch.py::test_target_test_resolves_to_audiotours_test
- test_local49_tour_content_persist.py::test_tour_content_persisted_on_generation
- test_local88_tour_pollution.py (5 tests — service down)
- test_nytimes_newsletter.py::test_nytimes_newsletter (SystemExit: 7)
- test_phase3_consolidation.py::test_consolidation_status (connection refused)
- test_phase3_realistic.py::test_realistic_consolidation (SystemExit: 7)
- test_security_fix.py (2 tests — connection refused)
- test_spotify_processing.py::test_final_article_content (SystemExit: 7)
- test_system_health.py (2 tests — SystemExit: 7)
- test_translation_implementation.py::test_tour_generation_with_content
- test_user_integration.py::test_user_integration (TypeError)
- test_user_tracking_fix.py::test_tracking_fix (connection refused)

**ERRORS (50):** 38 collection errors (missing pip deps) + 12 runtime errors
(services not running / connection refused).

### 4. No database writes during collection

```
BEFORE collection: audio_tours count = 145, Nice list = [1, 12, 14, 17, 24, 29, 152]
AFTER  collection: audio_tours count = 145, Nice list = [1, 12, 14, 17, 24, 29, 152]
```

Identical. No writes occurred.

### 5. git status clean

```
$ git status --short
(empty — clean working tree)
$ git rev-list --count storied..HEAD
1
```

### 6. No protected files touched

```
$ git diff --name-only $(git merge-base storied HEAD)..HEAD | grep -E "^(DECISIONS|CLAUDE|BACKLOG|\.continuous_dev)"
(empty)
```

---

## Limitations

1. **Stale self-references inside renamed files.** Several renamed scripts contain
   comments or docstrings referencing their own old name or referencing companion
   files by old name (e.g., `run_tour_quota_integration.py` still says "Companion
   to test_news_quota_integration.py"). The task prohibits content changes in
   renamed files, so these remain stale.

2. **Historical docs (SUBMISSION_LOCAL-*.md, DECISIONS.md) still reference old names.**
   These are records of past events and are correct as historical statements. The
   task prohibits editing them.

3. **38 collection errors remain** — all from missing pip dependencies (selenium,
   undetected_chromedriver, etc.), unrelated to this rename.

4. **No container rebuilt.** All verification ran against existing infrastructure.

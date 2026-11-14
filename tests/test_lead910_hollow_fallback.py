"""[LEAD-910] Phase 3A: hollow selection reasons deprioritize; they never empty the candidate list."""
import pathlib, re

SRC = (pathlib.Path(__file__).resolve().parent.parent / "generate_tour_text.py").read_text()


def test_hollow_candidates_are_kept_for_fallback():
    i = SRC.index("_hollow_reason_rejects.append(name)")
    assert "_hollow_fallback_lead910.append((name" in SRC[i:i + 200]


def test_fallback_runs_before_the_clean_fail():
    fb = SRC.index("if len(poi_list) == 0 and _hollow_fallback_lead910:")
    fail = SRC.index('print(f"X PHASE 3A: no usable POIs after parsing")')
    assert fb < fail and fail - fb < 1500


def test_fallback_logs_and_dedupes():
    fb = SRC.index("if len(poi_list) == 0 and _hollow_fallback_lead910:")
    block = SRC[fb:fb + 900]
    assert "[LEAD-910]" in block and "_l910_norm" in block and "_new_poi(_hn, _ha)" in block

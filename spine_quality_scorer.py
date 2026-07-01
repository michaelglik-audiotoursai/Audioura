"""
Spine Quality Scorer — automated rubric for spine JSON quality.
================================================================
Scores a spine on 4 criteria (0–4 total). Used to filter/retry low-quality generations.
"""
from typing import Tuple


def score_spine(spine: dict, total_stops: int = 0) -> Tuple[int, dict]:
    """Score a generated spine JSON on 4 quality criteria.

    Criteria (1 point each):
        1. climax_stop in [total*0.5, total*0.8] (well-positioned peak)
        2. No two stops share the same emotional_beat (variety)
        3. callback fields reference actual prior stop names (valid chain)
        4. closing_revelation length > 50 chars (substantive ending)

    Args:
        spine: Parsed spine dict from generate_spine().
        total_stops: Number of stops (derived from arc if 0).

    Returns:
        (score: int 0–4, breakdown: dict of criterion→bool)
    """
    arc = spine.get("arc", [])
    if total_stops == 0:
        total_stops = len(arc)

    breakdown = {}
    score = 0

    # Criterion 1: climax_stop position
    climax = spine.get("climax_stop", 0)
    lower = total_stops * 0.5
    upper = total_stops * 0.8
    criterion_1 = lower <= climax <= upper
    breakdown["climax_position"] = criterion_1
    if criterion_1:
        score += 1

    # Criterion 2: unique emotional_beats (no two identical)
    beats = [stop.get("emotional_beat", "").strip().lower() for stop in arc]
    beats_non_empty = [b for b in beats if b]
    criterion_2 = len(beats_non_empty) == len(set(beats_non_empty))
    breakdown["unique_emotional_beats"] = criterion_2
    if criterion_2:
        score += 1

    # Criterion 3: callback fields reference actual prior stop names
    stop_names = [stop.get("name", "").strip().lower() for stop in arc]
    criterion_3 = True
    for i, stop in enumerate(arc):
        cb = stop.get("callback")
        if cb and cb.strip():
            # Callback must reference a stop name that appeared BEFORE this one
            cb_lower = cb.strip().lower()
            prior_names = stop_names[:i]
            if cb_lower not in prior_names:
                criterion_3 = False
                break
    breakdown["valid_callbacks"] = criterion_3
    if criterion_3:
        score += 1

    # Criterion 4: closing_revelation > 50 chars
    revelation = spine.get("closing_revelation", "")
    criterion_4 = len(revelation) > 50
    breakdown["closing_revelation_length"] = criterion_4
    if criterion_4:
        score += 1

    return score, breakdown

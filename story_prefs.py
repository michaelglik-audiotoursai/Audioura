#!/usr/bin/env python3
"""story_prefs.py — LOCAL-620 (D634): use the listener's prefs at GENERATION.

Michael (D634): stop likes/dislikes should "tune the next tour's story types."

When ``user_class_prefs`` exists for the user, this module turns their learned
preference vector (details / historic / social) into a GENERATION-TIME emphasis
that:

  • weights the narration contract toward the classes the listener likes;
  • NEVER excludes a class — every class keeps at least a ``MIN_EXPLORATION``
    (10%) share, so the system keeps learning and a disliked class still appears
    (the swipe model is a BIAS, never a filter — the same rule as
    ``swipe_preference_service.bias_stop_ordering``);
  • falls back to the balanced default when the user has NO prefs (cold start) or
    when ``STORY_PREFS`` is off.

It is gated by env ``STORY_PREFS`` (default ON locally): ``STORY_PREFS=0``
disables personalisation entirely and generation behaves exactly as before.

Pure except for ``load_user_class_weights`` (which reads prefs through
``swipe_preference_service.get_user_prefs``); the weighting maths and the prompt
builder are pure and unit-testable.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from three_class_retrieval import CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL

__all__ = [
    "MIN_EXPLORATION",
    "prefs_enabled",
    "exploration_floored_weights",
    "load_user_class_weights",
    "narration_pref_addendum",
    "pref_summary_line",
]

# The minimum share any class keeps, so no class is ever excluded and the system
# keeps exploring (D634: "keep a >= 10% exploration share").
MIN_EXPLORATION = 0.10

_CLASSES = (CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL)

# Human label for each class, used in the narration addendum.
_CLASS_LABEL = {
    CLASS_DETAILS: "the work itself — its materials, technique, composition, and what it shows",
    CLASS_HISTORIC: "the artist's life and the historical and cultural context, including how the work was collected",
    CLASS_SOCIAL: "the people — patrons, collectors' motives, what contemporaries said, and the human/emotional reading",
}


def prefs_enabled() -> bool:
    """True unless env ``STORY_PREFS`` is explicitly off (0/false/no/off).

    Default ON locally (D634 item 4). Any unset value is treated as enabled.
    """
    v = os.environ.get("STORY_PREFS")
    if v is None:
        return True
    return str(v).strip().lower() not in ("0", "false", "no", "off", "")


def exploration_floored_weights(pref_details: float,
                                pref_historic: float,
                                pref_social: float,
                                min_exploration: float = MIN_EXPLORATION
                                ) -> Dict[str, float]:
    """Turn a raw preference vector into class WEIGHTS that sum to 1 and give
    every class at least ``min_exploration``.

    The raw prefs (each a Beta mean in [0,1], independent per class) are first
    normalised to a distribution, then each class is guaranteed the floor and the
    remaining mass is distributed in proportion to the raw preference. This keeps
    the ordering (a preferred class gets more) while NEVER zeroing a class.
    """
    raw = {
        CLASS_DETAILS: max(0.0, float(pref_details)),
        CLASS_HISTORIC: max(0.0, float(pref_historic)),
        CLASS_SOCIAL: max(0.0, float(pref_social)),
    }
    total = sum(raw.values())
    if total <= 0:
        # degenerate — equal split
        return {c: round(1.0 / 3.0, 4) for c in _CLASSES}

    n = len(_CLASSES)
    floor_total = min_exploration * n
    if floor_total >= 1.0:
        # floor too large to leave any room — equal split
        return {c: round(1.0 / n, 4) for c in _CLASSES}

    free = 1.0 - floor_total
    weights = {c: min_exploration + free * (raw[c] / total) for c in _CLASSES}
    # round, then fix any rounding drift onto the largest class
    weights = {c: round(w, 4) for c, w in weights.items()}
    drift = round(1.0 - sum(weights.values()), 4)
    if abs(drift) >= 1e-4:
        top = max(_CLASSES, key=lambda c: weights[c])
        weights[top] = round(weights[top] + drift, 4)
    return weights


def load_user_class_weights(user_id: Optional[str]
                            ) -> Tuple[Optional[Dict[str, float]], Dict]:
    """Load a user's exploration-floored class weights, or (None, meta) when there
    is no personalisation to apply.

    Returns (weights, meta). ``weights`` is None when: prefs are disabled
    (``STORY_PREFS`` off), no user_id, no prefs row (cold start), or zero swipes.
    ``meta`` carries ``enabled``, ``reason``, ``swipe_count`` and the raw prefs
    for logging. Never raises — any DB/import failure yields (None, meta) so
    generation falls back to the balanced default.
    """
    meta: Dict = {"enabled": prefs_enabled(), "reason": "", "swipe_count": 0,
                  "raw": None}
    if not prefs_enabled():
        meta["reason"] = "STORY_PREFS off"
        return None, meta
    if not user_id or not str(user_id).strip():
        meta["reason"] = "no user_id"
        return None, meta
    try:
        from swipe_preference_service import get_user_prefs
        prefs = get_user_prefs(user_id)
    except Exception as e:  # DB down, import error — fall back silently
        meta["reason"] = f"prefs load failed: {type(e).__name__}"
        return None, meta
    if prefs is None:
        meta["reason"] = "cold start (no prefs row)"
        return None, meta
    swipes = int(prefs.get("swipe_count", 0) or 0)
    meta["swipe_count"] = swipes
    meta["raw"] = {
        CLASS_DETAILS: float(prefs.get("pref_details", 0.5)),
        CLASS_HISTORIC: float(prefs.get("pref_historic", 0.5)),
        CLASS_SOCIAL: float(prefs.get("pref_social", 0.5)),
    }
    if swipes <= 0:
        meta["reason"] = "cold start (0 swipes)"
        return None, meta
    weights = exploration_floored_weights(
        meta["raw"][CLASS_DETAILS], meta["raw"][CLASS_HISTORIC],
        meta["raw"][CLASS_SOCIAL])
    meta["reason"] = "personalised"
    return weights, meta


def _ranked_classes(weights: Dict[str, float]) -> List[str]:
    return sorted(_CLASSES, key=lambda c: (-weights.get(c, 0.0), _CLASSES.index(c)))


def narration_pref_addendum(weights: Optional[Dict[str, float]]) -> str:
    """A short prompt block that nudges the narration toward the listener's
    preferred classes WITHOUT excluding any.

    Returns "" when ``weights`` is None (no personalisation) so the caller appends
    nothing in the default case. When present, it names the listener's leaning and
    reminds the model to keep every class represented (>= 10% exploration), so the
    contract is a bias, not a filter.
    """
    if not weights:
        return ""
    ranked = _ranked_classes(weights)
    top = ranked[0]
    least = ranked[-1]
    pct = {c: int(round(weights[c] * 100)) for c in _CLASSES}
    return (
        "\n\nLISTENER PREFERENCE (LOCAL-620 — a lean, NOT a filter):\n"
        f"  This listener tends to prefer {_CLASS_LABEL[top]}.\n"
        f"  So, where the evidence allows, give a little MORE room to that, roughly "
        f"in the mix details {pct[CLASS_DETAILS]}% / historical "
        f"{pct[CLASS_HISTORIC]}% / social {pct[CLASS_SOCIAL]}%.\n"
        f"  But NEVER drop a class entirely — keep at least a short line of "
        f"{_CLASS_LABEL[least]} when the evidence supports it. Do not invent "
        f"anything to satisfy the mix; a true, shorter stop beats a padded one."
    )


def pref_summary_line(weights: Optional[Dict[str, float]], meta: Dict) -> str:
    """A one-line log summary of the personalisation decision."""
    if not weights:
        return f"[LOCAL-620] prefs: default/balanced ({meta.get('reason','')})"
    pct = {c: int(round(weights[c] * 100)) for c in _CLASSES}
    return (f"[LOCAL-620] prefs: personalised (swipes={meta.get('swipe_count',0)}) "
            f"mix details {pct[CLASS_DETAILS]}% / historic {pct[CLASS_HISTORIC]}% "
            f"/ social {pct[CLASS_SOCIAL]}% (>=10% floor each)")

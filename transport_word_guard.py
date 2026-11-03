#!/usr/bin/env python3
"""transport_word_guard.py — LOCAL-855D item 2.

A cycling tour must not describe the listener walking.

Michael read the delivered Sophia *cycling* tour and found walking words all
through it:

    "You might notice the vibrant street life as you walk."
    "… it is roughly 1.5 km (about a 19-minute walk) away."
    "… it is about a minute's walk away."
    "Acoustic Bar connects to your walk as a natural next step …"

The two distance phrases are produced deterministically by
``walking_directions_guard._approx_distance_phrase`` and are fixed there (that
function is now transport-mode aware and never says "walk" on a bike tour). The
other two are LLM prose: the narrator slipped a walking verb/noun into the body.

This module is the deterministic, every-path text pass that rewrites a generic
pedestrian verb/noun into the tour's actual mode on a NON-FOOT tour, and is a
no-op on a walking tour. It does NOT invent facts — it only swaps the movement
word for the correct one ("walk" -> "ride" on a bike tour), so it is safe to run
unconditionally over finalized text. Pure, offline, idempotent.

Scope is deliberately tight: it maps a small, closed set of pedestrian movement
words to their mode equivalent, and only when the tour's mode is wheeled. It does
not touch "walkway", "boardwalk", "sidewalk", "crosswalk", "Walker" (names), or
"jaywalk" — the word list is matched on whole words (\bwalk\b) and those are not
bare "walk".
"""
import re
from typing import Tuple

# Pedestrian movement words -> cycling / driving equivalents (whole-word).
_BIKE_MAP = {
    "walk": "ride", "walking": "riding", "walks": "rides", "walked": "rode",
    "stroll": "ride", "strolling": "riding", "strolls": "rides",
    "on foot": "by bike",
}
_VEHICLE_MAP = {
    "walk": "drive", "walking": "driving", "walks": "drives", "walked": "drove",
    "stroll": "drive", "strolling": "driving", "strolls": "drives",
    "on foot": "by car",
}
_MODE_MAPS = {"bike": _BIKE_MAP, "vehicle": _VEHICLE_MAP}

# One alternation per map covers all its keys; whole-word, case-insensitive.
def _compile(mapping):
    keys = sorted(mapping.keys(), key=len, reverse=True)
    return re.compile(r"(?i)\b(" + "|".join(re.escape(k) for k in keys) + r")\b")

_PATTERNS = {m: _compile(mp) for m, mp in _MODE_MAPS.items()}


def correct_transport_words(text: str, mode: str) -> Tuple[str, int]:
    """Rewrite pedestrian movement words to the tour's wheeled mode.

    Returns ``(new_text, n_changes)``. A no-op (0 changes) for ``on_foot`` or an
    unknown mode, so it is always safe to call. Case of the first letter is
    preserved ("Walk" -> "Ride").
    """
    mapping = _MODE_MAPS.get(mode)
    pattern = _PATTERNS.get(mode)
    if not mapping or not text:
        return text, 0
    changes = 0

    def repl(m):
        nonlocal changes
        tok = m.group(0)
        rep = mapping.get(tok.lower())
        if rep is None:
            return tok
        changes += 1
        return rep[:1].upper() + rep[1:] if tok[:1].isupper() else rep

    return pattern.sub(repl, text), changes


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    fixed, n = correct_transport_words(t, "bike")
    print(f"changes: {n}")
    sys.stdout.write(fixed)

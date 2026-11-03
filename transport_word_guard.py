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

# [LEAD review of 855D] Bike mode ONLY, and only where "walk" describes the
# LISTENER MOVING BETWEEN PLACES. A blanket \bwalk\b swap broke real phrases:
# "Bùi Viện Walking Street" (a proper name), "walk inside the cathedral" (you do
# dismount), and on driving tours "walk the trail to the falls" -> "drive the
# trail". Driving tours legitimately include walks, so vehicle mode is a no-op.
_BIKE_MAP = {
    "walk": "ride", "walking": "riding", "walks": "rides", "walked": "rode",
    "stroll": "ride", "strolling": "riding", "strolls": "rides",
    "on foot": "by bike",
}
_MODE_MAPS = {"bike": _BIKE_MAP}

_MOVE_AFTER = (r"(?:to|towards?|along|down|up|past|over|back|on|onward|"
               r"north|south|east|west|ahead|straight|away)")
# Contexts where the word is the listener's movement (group 'w' is replaced).
_BIKE_PATTERNS = [
    re.compile(r"(?i)\b(?:as|while|when|once) you (?P<w>walk|stroll)\b"),
    re.compile(r"(?i)\byour (?P<w>walk|stroll)\b"),
    re.compile(r"(?i)\b(?:a|short|brief|quick|easy|minute's|-minute) (?P<w>walk|stroll)\b"),
    re.compile(r"(?i)-minute (?P<w>walk|stroll)\b"),
    re.compile(r"(?i)\b(?P<w>walk|walking|strolling|stroll)\s+" + _MOVE_AFTER + r"\b"),
    re.compile(r"(?i)\b(?P<w>on foot)\b"),
    re.compile(r"(?i)\b(?P<w>stroll|strolling|strolls)\b"),
]
_PROPER_NAME_RE = re.compile(r"\bWalking Street\b|\bWalk of\b")
_PATTERNS = {"bike": _BIKE_PATTERNS}


def correct_transport_words(text: str, mode: str) -> Tuple[str, int]:
    """Rewrite the listener's pedestrian movement words to cycling words.

    Returns ``(new_text, n_changes)``. A no-op for every mode except ``bike``
    (walking tours keep "walk"; driving tours legitimately include walks).
    Proper names ("… Walking Street", "Walk of …") are never touched.
    """
    mapping = _MODE_MAPS.get(mode)
    patterns = _PATTERNS.get(mode)
    if not mapping or not patterns or not text:
        return text, 0
    changes = 0

    def fix(m):
        nonlocal changes
        whole = m.group(0)
        tok = m.group("w")
        if _PROPER_NAME_RE.search(text[max(0, m.start() - 1):m.end() + 8]) and tok[:1].isupper():
            return whole
        rep = mapping.get(tok.lower())
        if rep is None:
            return whole
        rep = rep[:1].upper() + rep[1:] if tok[:1].isupper() else rep
        changes += 1
        a, b = m.span("w")
        return whole[:a - m.start()] + rep + whole[b - m.start():]

    for pat in patterns:
        text = pat.sub(fix, text)
    return text, changes


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    fixed, n = correct_transport_words(t, "bike")
    print(f"changes: {n}")
    sys.stdout.write(fixed)

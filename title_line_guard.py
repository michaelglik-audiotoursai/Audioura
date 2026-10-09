"""title_line_guard.py — [LOCAL-634] The tour's title/header line is never edited.

The stored tour opens with a canonical HEADER line:

    Step-by-Step Audio Guided Tour: {venue}, {city}, {country} - {Category} Tour

Bench R1 showed three tours (488, 505, 506) whose DELIVERED opening had been
rewritten into a spoken sentence:

    Step-by-step audio guided tour of the Museo Reina Sofía in Madrid, Spain,
    is a museum tour.

A pass had turned the header LINE into prose — lowercasing it, inserting "of the"
/ "in" and a trailing "is a {category} tour." The header and the structured field
lines (Address / Coordinates / Orientation / Directions / Tour-Category / Sources)
are STRUCTURE, not narration: no pass may rewrite them. This module is the
deterministic, no-LLM safety net that detects a header line that has been
rewritten into that spoken shape and restores the canonical header, so whatever
upstream pass produced it, the delivered and stored tour always carries the real
header. Pure and idempotent; a no-op when the header is already canonical.
"""
from __future__ import annotations

import re
from typing import Tuple

__all__ = [
    "CANONICAL_PREFIX",
    "is_canonical_header",
    "detect_rewritten_title",
    "restore_title_line",
]

CANONICAL_PREFIX = "Step-by-Step Audio Guided Tour:"

# The canonical header, used to recognise an already-correct first line.
_CANONICAL_RE = re.compile(r"(?i)^\s*Step-by-Step\s+Audio\s+Guided\s+Tour:\s*\S")

# The spoken-rewritten shape the bench saw (first line of the delivered tour):
#   "Step-by-step audio guided tour of the {venue} in {city}, {rest}, is a
#    {category} tour."
# Capture the venue (after "of the"/"of"), the locality run (after "in"), and the
# category word before "tour". The trailing "is a … tour." and the leading
# lowercased stem are the tells.
_REWRITTEN_RE = re.compile(
    r"(?i)^\s*step-by-step\s+audio\s+guided\s+tour\s+of\s+(?:the\s+)?"
    r"(?P<venue>.+?)\s+in\s+(?P<place>.+?)\s*(?:,\s*"
    r"is\s+a[n]?\s+(?P<category>[a-z\u00C0-\u017F]+)\s+tour)?\.?\s*$")  # LEAD 2026-10-09: R11 Bern/Bordeaux had no "is a … tour" tail


def is_canonical_header(line: str) -> bool:
    """True when ``line`` is already the canonical ``Step-by-Step Audio Guided
    Tour: …`` header."""
    return bool(_CANONICAL_RE.match(line or ""))


def detect_rewritten_title(line: str):
    """Return (venue, place, category) when ``line`` is the spoken-rewritten title
    shape, else None. Deterministic."""
    m = _REWRITTEN_RE.match(line or "")
    if not m:
        return None
    venue = m.group("venue").strip().strip(",").strip()
    place = m.group("place").strip().strip(",").strip()
    category = (m.group("category") or "museum").strip().lower()
    if not venue:
        return None
    return (venue, place, category)


def _rebuild_header(venue: str, place: str, category: str) -> str:
    """Reconstruct the canonical header from the parsed spoken parts."""
    subject = venue
    if place:
        subject = f"{venue}, {place}"
    cat = (category or "").strip()
    if cat:
        suffix = f" - {cat[:1].upper() + cat[1:]} Tour"
    else:
        suffix = ""
    return f"{CANONICAL_PREFIX} {subject}{suffix}"


def restore_title_line(tour_text: str) -> Tuple[str, bool]:
    """If the tour's FIRST non-empty line has been rewritten into the spoken
    "…is a {category} tour." shape, restore the canonical header line. Returns
    ``(text, restored)``. Idempotent; a no-op when the header is canonical or no
    rewritten shape is present. Only the FIRST line is ever touched — all other
    lines (including every field line) are preserved byte-for-byte.
    """
    if not tour_text:
        return tour_text or "", False
    lines = tour_text.split("\n")
    # Find the first non-empty line (the title banner).
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip():
            idx = i
            break
    if idx is None:
        return tour_text, False
    first = lines[idx]
    if is_canonical_header(first):
        return tour_text, False
    parsed = detect_rewritten_title(first)
    if not parsed:
        return tour_text, False
    venue, place, category = parsed
    lines[idx] = _rebuild_header(venue, place, category)
    return "\n".join(lines), True

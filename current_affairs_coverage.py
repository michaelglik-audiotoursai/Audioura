#!/usr/bin/env python3
"""current_affairs_coverage.py — LOCAL-650 fix 3.

When a request names CURRENT AFFAIRS, be honest about recency.

Michael, 2026-10-09 (tour 557, "Walking tour in Boston dedicated to
Massachusetts politics and CURRENT AFFAIRS"): the stop about politics discussed
scandals from 1996–2011 and an anecdote from 1904 — nothing from recent years.
A tour that advertises "current affairs" should carry at least one recent
(≤ 5 years old) grounded item, or say honestly that there is none, rather than
leaving the listener to assume decades-old events are "current".

This module is a pure, deterministic, offline, every-path TEXT guard. It:

  1. detects whether the request asked for current affairs / current events /
     present-day coverage (from the tour's own title line, which carries the
     request string);
  2. checks whether any STOP narration carries a RECENT grounded year — a
     4-digit year within the last ``window`` years of ``now_year``;
  3. when the request wanted current affairs and NO recent item is present,
     appends ONE honest note to the end of the spoken text (before any Sources
     block). It never invents a recent fact — honesty is the whole point.

Idempotent: the note is added at most once, and a tour that already carries a
recent year (or already carries the note) is left unchanged.
"""
import datetime
import re
from typing import Optional, Tuple

try:
    from stop_pool_store import _STOP_HEADER, _SOURCES_LINE
except Exception:  # pragma: no cover
    _STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
    _SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')

# Phrases in a request that ask for recency.
_CURRENT_AFFAIRS_RE = re.compile(
    r'(?i)\b(current\s+affairs|current\s+events|present[\s-]day|'
    r'nowadays|contemporary\s+(?:issues|events|affairs|life|politics)|'
    r'today[\'’]?s\b|in\s+the\s+news|recent\s+(?:events|developments|news)|'
    r'latest\s+(?:news|developments))\b')

# The honest note. Kept recognisable so the guard is idempotent.
_HONEST_NOTE_MARK = "no verified developments from the past five years"
_HONEST_NOTE = (
    "A note on current affairs: this tour draws on documented history, and we "
    "found no verified developments from the past five years to include here. "
    "For the very latest, check a current local news source."
)

_YEAR_RE = re.compile(r'\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b')


def request_wants_current_affairs(text_or_request: str) -> bool:
    """True when the request (or tour title line) asks for current affairs."""
    if not text_or_request:
        return False
    first_line = text_or_request.split("\n", 1)[0]
    m = re.match(r'(?i)^step-by-step[^:]*:\s*(.+)$', first_line)
    req = m.group(1) if m else text_or_request
    return bool(_CURRENT_AFFAIRS_RE.search(req))


def _spoken_body(text: str) -> str:
    """The spoken stop bodies, excluding the Sources block and field lines."""
    src = _SOURCES_LINE.search(text)
    body = text[:src.start()] if src else text
    out_lines = []
    for ln in body.split("\n"):
        if re.match(r'(?i)^\s*(address|coordinates|type/specialty|specific '
                    r'examples|operational details|museum information|directions|'
                    r'tour-category|hours|opening hours|visiting hours|sources?)\s*:',
                    ln):
            continue
        out_lines.append(ln)
    return "\n".join(out_lines)


def most_recent_year(text: str) -> Optional[int]:
    """The most recent 4-digit year that appears in the spoken stop bodies."""
    years = [int(y) for y in _YEAR_RE.findall(_spoken_body(text))]
    return max(years) if years else None


def has_recent_item(text: str, now_year: Optional[int] = None, window: int = 5) -> bool:
    """True when a year within the last ``window`` years of ``now_year`` appears."""
    ny = now_year or datetime.date.today().year
    cutoff = ny - window
    for y in _YEAR_RE.findall(_spoken_body(text)):
        yi = int(y)
        if cutoff <= yi <= ny + 1:   # +1 tolerates a near-future dated plan
            return True
    return False


def _insert_note(text: str) -> str:
    """Append the honest note to the end of the spoken text, before Sources."""
    src = _SOURCES_LINE.search(text)
    if src:
        head = text[:src.start()].rstrip()
        tail = text[src.start():]
        return head + "\n\n" + _HONEST_NOTE + "\n\n" + tail
    return text.rstrip() + "\n\n" + _HONEST_NOTE + "\n"


def ensure_current_affairs_coverage(text: str,
                                    now_year: Optional[int] = None,
                                    window: int = 5) -> Tuple[str, bool]:
    """When the request wanted current affairs and no recent (≤ window years)
    grounded item is present, append ONE honest note. Returns ``(text, changed)``.

    Deterministic and idempotent. Never invents a recent fact. A no-op when the
    request did not ask for current affairs, when a recent item is already
    present, or when the note is already present.
    """
    if not text or not text.strip():
        return text or "", False
    if not request_wants_current_affairs(text):
        return text, False
    if _HONEST_NOTE_MARK in text:
        return text, False
    if has_recent_item(text, now_year=now_year, window=window):
        return text, False
    return _insert_note(text), True


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    ny = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print("wants current affairs:", request_wants_current_affairs(t))
    print("most recent year:", most_recent_year(t))
    print("has recent item (<=5y):", has_recent_item(t, now_year=ny))
    out, changed = ensure_current_affairs_coverage(t, now_year=ny)
    print("note appended:", changed)

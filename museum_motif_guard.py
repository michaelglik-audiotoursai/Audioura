#!/usr/bin/env python3
"""museum_motif_guard.py — LOCAL-623 defect 2 (D634): no recurring museum motif.

Museum Folkwang tour 468 wove an abstract "museum endurance" motif through BOTH
stop bodies:

  Stop 1: "The presence of 'Ecce Homo' at Museum Folkwang reflects the broader
           patterns that have shaped the collection …"
          "The museum's story, like Daumier's canvas, is marked by periods of
           concealment and revelation — suggesting that what endures …"
  Stop 2: "The museum story of preservation and renewal — of holding fast to
           culture in times of change — resonates with the joyous abandon …"

That is template framing, not the WORK: a vague "the museum's story of
preservation and renewal / concealment and revelation" refrain that reappears
stop after stop. Per D634 the museum motif must NOT recur across stops, and this
kind of abstract institutional refrain does not belong in a stop body at all.

This guard drops museum-endurance / "the museum's story" motif sentences from the
STOP BODIES (never the Stop-1 About opening section, which is where the museum's
real story legitimately lives). It is deterministic, pure, and idempotent, and is
applied to the delivered tour text like the other body filters.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

__all__ = [
    "is_museum_motif_sentence",
    "filter_stop_body_museum_motif",
    "filter_tour_text_museum_motif",
]

# The abstract "endurance / preservation / concealment-revelation" vocabulary the
# refrain is built from. A sentence is a museum MOTIF sentence when it both talks
# ABOUT the museum/collection as an abstract subject AND carries one of these
# endurance-motif phrases — i.e. it is framing, not a fact about the work.
_MUSEUM_SUBJECT_RE = re.compile(
    r"(?i)\b(the\s+museum['\u2019]?s?\s+story|museum\s+story\s+of|"
    r"the\s+collection['\u2019]?s?\s+story|broader\s+patterns\s+that\s+have\s+shaped|"
    r"patterns\s+that\s+have\s+shaped\s+the\s+collection|"
    r"the\s+(?:museum|collection)['\u2019]?s?\s+(?:journey|arc|history\s+of))\b")

_ENDURANCE_MOTIF_RE = re.compile(
    r"(?i)\b("
    r"preservation\s+and\s+renewal|concealment\s+and\s+revelation|"
    r"holding\s+fast\s+to\s+culture|what\s+endures|the\s+act\s+of\s+bringing\s+it\s+into\s+view|"
    r"survived\s+private\s+obscurity|times\s+of\s+change|"
    r"endurance\s+of\s+(?:beauty|culture|art)|"
    r"preserving\s+(?:beauty|culture|the\s+past)\s+(?:against|through)|"
    r"resilience\s+of\s+(?:the\s+)?(?:collection|museum|institution)"
    r")\b")


def is_museum_motif_sentence(sentence: str) -> bool:
    """True when a sentence is the abstract museum-endurance motif (not a work fact).

    Requires BOTH an abstract museum/collection "story/patterns" subject AND an
    endurance-motif phrase, so a concrete sentence about the museum (e.g. an
    acquisition fact) is never caught — only the vague refrain.
    """
    s = (sentence or "").strip()
    if not s:
        return False
    return bool(_MUSEUM_SUBJECT_RE.search(s) and _ENDURANCE_MOTIF_RE.search(s))


def _split_sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences as _ss
        return [s for s in _ss(text or "") if s and s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def filter_stop_body_museum_motif(body: str) -> Tuple[str, Dict]:
    """Drop museum-endurance motif sentences from one stop body.

    Never empties a body (D577): if every sentence would go, the body is returned
    unchanged. Returns (new_body, report).
    """
    report = {"dropped": 0, "changed": False}
    if not body or not body.strip():
        return body, report
    sents = _split_sentences(body)
    if len(sents) <= 1:
        return body, report
    kept = [s for s in sents if not is_museum_motif_sentence(s)]
    dropped = len(sents) - len(kept)
    if dropped == 0 or not kept:
        return body, report
    new_body = " ".join(k.strip() for k in kept if k.strip()).strip()
    if not new_body:
        return body, report
    report["dropped"] = dropped
    report["changed"] = True
    return new_body, report


_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")

# Opening-section markers — the About section is where the museum's real story
# lives, so its paragraphs are exempt (reuse the LOCAL-617 opening detector).
try:
    from work_first_evidence import _is_opening_paragraph as _is_opening
except Exception:  # pragma: no cover
    def _is_opening(_p: str) -> bool:
        return False


def filter_tour_text_museum_motif(tour_text: str) -> Tuple[str, Dict]:
    """Apply the museum-motif filter across a delivered tour, per stop body.

    The Stop-1 About opening section is exempt (it is where the museum's own
    story belongs). Every other stop-body paragraph has museum-endurance motif
    sentences dropped. Pure string→string. Returns (new_text, report).
    """
    report = {"stops": 0, "dropped": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report
    out = [parts[0]]
    i = 1
    stop_index = 0
    total_dropped = 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        paras = re.split(r"(\n\s*\n)", body)
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            if stop_index == 1 and _is_opening(seg):
                new_paras.append(seg)  # exempt About opening section
                continue
            filtered, prep = filter_stop_body_museum_motif(seg)
            total_dropped += prep.get("dropped", 0)
            new_paras.append(filtered)
        out.append(header)
        out.append("".join(new_paras))
        i += 2
    report["dropped"] = total_dropped
    report["changed"] = total_dropped > 0
    return "".join(out), report

"""
wrong_era_guard.py — [LOCAL-616 item 5]
=======================================
A stop whose work's date is KNOWN must not carry an era claim that contradicts it.
Tour 414 Stop 3 described an object dated 1782 with:

    "In the 13th century, such a combination of materials signified…"

The 13th century (1200–1299) is ~500 years from 1782 — an invented/contradictory
era. This module adds a deterministic (no-LLM) check: in a stop whose work date is
known, drop any sentence that asserts a century or year MORE THAN 150 years away
from that date, UNLESS the sentence frames the older date as an earlier
tradition / influence / revival (a legitimate art-historical reference, e.g. "in
the medieval tradition", "revived a 13th-century technique", "harks back to…").

Conservative by design:
  * Only fires when the stop's own work date is known (title trailing year, a
    ``year`` field, or a 4-digit year in the title). No date → no action.
  * Only fires when the era gap exceeds 150 years (comfortably past normal
    "late 18th / early 19th century" phrasing around a work).
  * Never fires on an "earlier tradition" framing — those are the correct way to
    mention an older influence.
Operates on ordered stop-unit dicts; returns (new_units, dropped), mirroring
cross_stop_reference_guard.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

_GAP_YEARS = 150


def _split_sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences as _shared
        return _shared(text or "")
    except Exception:  # pragma: no cover
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip())
                if s.strip()]


# ── the stop's own work date ─────────────────────────────────────────────────

_YEAR_RE = re.compile(r"\b(1[0-9]\d{2}|20\d{2})\b")  # 1000–2099
_TITLE_TRAIL_YEAR_RE = re.compile(r",\s*(?:c\.?\s*)?(1[0-9]\d{2}|20\d{2})\s*$")


def work_year(unit: Dict) -> Optional[int]:
    """Best-effort KNOWN creation year for the stop's work, or None.

    Order: explicit ``year`` field → title trailing ", 1782" → first 4-digit year
    in the title. Narration years are NOT used (they are the very text we judge)."""
    y = str(unit.get("year", "") or "").strip()
    m = _YEAR_RE.search(y)
    if m:
        return int(m.group(1))
    title = unit.get("title", "") or ""
    m = _TITLE_TRAIL_YEAR_RE.search(title)
    if m:
        return int(m.group(1))
    m = _YEAR_RE.search(title)
    if m:
        return int(m.group(1))
    return None


# ── era claims in a sentence ─────────────────────────────────────────────────

_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "twenty-first": 21,
}

# "13th century", "13th-century", "thirteenth century"
_CENTURY_NUM_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)[\s-]+centur(?:y|ies)\b",
                             re.IGNORECASE)
_CENTURY_WORD_RE = re.compile(
    r"\b(" + "|".join(_ORDINALS.keys()) + r")[\s-]+centur(?:y|ies)\b",
    re.IGNORECASE)

# Framing that LEGITIMISES an older date (earlier tradition / influence / revival).
_TRADITION_RE = re.compile(
    r"(?i)\b("
    r"earlier tradition|older tradition|ancient tradition|medieval tradition|"
    r"centuries[- ]old|age[- ]old|long tradition|"
    r"tradition dating|dates? back|dating back|harks? back|hearkens? back|"
    r"revival|reviv(?:ed|es|ing)|revisit|echo(?:es|ing|ed)?|inspired by|"
    r"drawing on|drew on|rooted in|descend(?:s|ed|ing)? from|"
    r"in the (?:style|manner|tradition) of|after the manner of|"
    r"as (?:far )?back as|since (?:the )?antiquity|from antiquity|"
    r"a technique (?:that )?|first (?:used|developed|appeared)|"
    r"originat(?:ed|es|ing)|has its origins|its origins"
    r")\b")


def _century_years(c: int) -> Tuple[int, int]:
    """Inclusive year span of the c-th century (13th → 1200..1299)."""
    start = (c - 1) * 100
    return start, start + 99


def _claimed_years(sentence: str) -> List[Tuple[int, int, str]]:
    """Return (lo, hi, label) spans for every explicit era claim in the sentence:
    centuries (numeric or word) and bare 3–4 digit years."""
    out: List[Tuple[int, int, str]] = []
    for m in _CENTURY_NUM_RE.finditer(sentence):
        c = int(m.group(1))
        if 1 <= c <= 21:
            lo, hi = _century_years(c)
            out.append((lo, hi, m.group(0)))
    for m in _CENTURY_WORD_RE.finditer(sentence):
        c = _ORDINALS.get(m.group(1).lower())
        if c:
            lo, hi = _century_years(c)
            out.append((lo, hi, m.group(0)))
    for m in _YEAR_RE.finditer(sentence):
        y = int(m.group(1))
        out.append((y, y, m.group(1)))
    return out


def _gap(span: Tuple[int, int], year: int) -> int:
    """Years from a claimed [lo,hi] span to the known work year (0 if inside)."""
    lo, hi = span[0], span[1]
    if lo <= year <= hi:
        return 0
    return min(abs(year - lo), abs(year - hi))


def sentence_is_wrong_era(sentence: str, year: int) -> Optional[str]:
    """Return the offending era label when the sentence makes an era claim more
    than _GAP_YEARS from ``year`` and is NOT framed as an earlier tradition;
    else None."""
    if _TRADITION_RE.search(sentence):
        return None  # legitimate older-influence framing — keep it
    worst = None
    worst_gap = 0
    for lo, hi, label in _claimed_years(sentence):
        g = _gap((lo, hi), year)
        if g > _GAP_YEARS and g > worst_gap:
            worst_gap = g
            worst = label
    return worst


# ── the pass ─────────────────────────────────────────────────────────────────

def strip_wrong_era_sentences(
        ordered_units: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Drop era-contradicting sentences from each stop whose work date is known.
    Returns (new_units, dropped). ``dropped`` entries are
    {stop, sentence, reason, era, work_year}."""
    dropped: List[Dict] = []
    new_units: List[Dict] = []
    for i, unit in enumerate(ordered_units):
        stop_num = i + 1
        year = work_year(unit)
        narration = unit.get("narration") or ""
        if year is None or not narration.strip():
            new_units.append(dict(unit))
            continue
        out_paras: List[str] = []
        for para in re.split(r"\n{2,}", narration):
            sentences = _split_sentences(para)
            if not sentences:
                out_paras.append(para)
                continue
            kept: List[str] = []
            for sent in sentences:
                era = sentence_is_wrong_era(sent, year)
                if era is not None:
                    dropped.append({
                        "stop": stop_num,
                        "sentence": sent.strip(),
                        "reason": f"era claim {era!r} >150y from work date {year}",
                        "era": era,
                        "work_year": year,
                    })
                    continue
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        new_narr = "\n\n".join(p for p in out_paras if p.strip()).strip()
        nu = dict(unit)
        nu["narration"] = new_narr
        new_units.append(nu)
    return new_units, dropped

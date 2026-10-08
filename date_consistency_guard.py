#!/usr/bin/env python3
"""date_consistency_guard.py — LOCAL-626 item 5: one date per work.

Tour 485 Stop 3 ("Footed Bowl with the Crucifixion") dated the SAME object two
incompatible ways in one breath:

    "… in Urbino, Italy, between 1550 and 1570 …"           (the corpus date)
    "… created in Urbino during the period 1510-1571 …"     (an invented range)

A listener cannot be told a work was made "between 1550 and 1570" and "during
1510-1571" in the same stop. The rule the owner set: ONE date per work, and the
CORPUS date wins. This guard, run per stop on the delivered text, finds the
work-creation date spans a stop asserts and, when they CONFLICT, keeps the one
that matches the stop's corpus date (or, with no corpus date, the first stated)
and drops the sentences carrying the conflicting dates.

Scope, kept deliberately narrow so it never mangles legitimate prose:
  * Only CREATION-date spans are considered — a span introduced by a creation
    cue ("created/made/painted/produced … in/between/during/c. <date>", or a
    bare range right after the object). A date that belongs to a PERSON ("active
    from 1515 to 1587"), a movement, or another event is ignored here.
  * A "date" is a 4-digit year, a year range ("1550-1570", "1550 to 1570",
    "between 1550 and 1570"), or an approximate year ("c. 1600", "around 1905").
  * Two creation dates CONFLICT when their year ranges are not equal and do not
    nest (one fully inside the other with the same intent) — "1550–1570" vs
    "1510–1571" conflict; "1906" vs "around 1904–1906" do not (1906 ∈ range).

Pure (no network, no LLM, no DB), deterministic, idempotent. Never empties a
stop body (D577).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

__all__ = [
    "creation_dates_in_sentence",
    "ranges_conflict",
    "filter_stop_body_date_consistency",
    "filter_tour_text_date_consistency",
    "parse_date_range",
    "recompute_year_spans",
    "recompute_year_spans_in_tour",
]

# A single year (1000–2099 — guards against page numbers / catalogue ids).
_YEAR = r"(1[0-9]{3}|20[0-9]{2})"

# Creation cue words that mark a date as the WORK's creation date (not a person's
# dates or a movement). The cue must be reasonably close to the date.
_CREATION_CUE = (
    r"(?:created|made|painted|produced|executed|cast|carved|completed|finished|"
    r"dated|crafted|fashioned|decorated|fired|thrown|modell?ed|sculpted|drawn|"
    r"commissioned|built)"
)

# Person-dates cue to EXCLUDE ("active from 1515 to 1587", "lived 1839-1906",
# "(1515-1587)" right after a name is handled by requiring a creation cue).
_PERSON_DATE_RE = re.compile(
    r"(?i)\b(?:active|lived|born|died|working|fl\.?|flourished|r\.|reigned)\b")

# Range forms: "1550-1570", "1550–1570", "1550 to 1570", "between 1550 and 1570".
_RANGE_RE = re.compile(
    r"(?i)(?:between\s+)?" + _YEAR + r"\s*(?:-|–|—|to|and)\s*" + _YEAR)
# Single/approx year: "c. 1600", "around 1905", "1906".
_SINGLE_RE = re.compile(r"(?i)(?:c\.?\s*|circa\s+|around\s+|about\s+)?\b" + _YEAR + r"\b")


def parse_date_range(text: str) -> Optional[Tuple[int, int]]:
    """Return (start_year, end_year) for the FIRST date span in ``text``, or None.
    A single year yields (y, y). Approximate markers are ignored for the bounds."""
    m = _RANGE_RE.search(text or "")
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = _SINGLE_RE.search(text or "")
    if m:
        y = int(m.group(1))
        return (y, y)
    return None


def creation_dates_in_sentence(sentence: str) -> List[Tuple[int, int]]:
    """Every CREATION-date span in a sentence (year ranges and single years),
    as (start, end). Returns [] when the sentence states no date, or when its
    only dates are PERSON dates ("active 1515-1587") with no creation cue."""
    s = sentence or ""
    low = s.lower()
    has_creation_cue = bool(re.search(r"(?i)\b" + _CREATION_CUE + r"\b", s)) or \
        bool(re.search(r"(?i)\b(?:in|between|during|period|around|circa|c\.)\b", s))
    if not has_creation_cue:
        return []
    # If the sentence is PRIMARILY about a person's dates and carries no creation
    # verb, skip it (we must not touch "Patanazzi, active from 1515 to 1587").
    if _PERSON_DATE_RE.search(s) and not re.search(r"(?i)\b" + _CREATION_CUE + r"\b", s):
        return []

    spans: List[Tuple[int, int]] = []
    used = []  # char spans already consumed by a range, so a single-year scan skips them
    for m in _RANGE_RE.finditer(s):
        a, b = int(m.group(1)), int(m.group(2))
        spans.append((min(a, b), max(a, b)))
        used.append((m.start(), m.end()))
    for m in _SINGLE_RE.finditer(s):
        if any(st <= m.start() < en for st, en in used):
            continue
        y = int(m.group(1))
        spans.append((y, y))
    return spans


def ranges_conflict(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    """True when two creation-date spans are mutually inconsistent.

    Equal spans never conflict. A single year that falls INSIDE the other span
    does not conflict ("1906" vs "1904–1906"). Otherwise, two spans conflict when
    neither fully contains the other (distinct, non-nested ranges) — "1550–1570"
    vs "1510–1571" conflict because neither nests the other exactly and their
    bounds differ.
    """
    if a == b:
        return False
    (a0, a1), (b0, b1) = a, b
    # single year inside the other range → consistent
    if a0 == a1 and b0 <= a0 <= b1:
        return False
    if b0 == b1 and a0 <= b0 <= a1:
        return False
    # one range fully contains the other AND shares a bound → treat as a refinement
    a_in_b = b0 <= a0 and a1 <= b1
    b_in_a = a0 <= b0 and b1 <= a1
    if (a_in_b or b_in_a) and (a0 == b0 or a1 == b1):
        return False
    return True


def _split_sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences as _ss
        return [s for s in _ss(text or "") if s and s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def filter_stop_body_date_consistency(body: str, corpus_date: str = ""
                                      ) -> Tuple[str, Dict]:
    """Drop sentences that assert a work-creation date CONFLICTING with the
    stop's kept date. The kept date is the corpus date when supplied (parsed from
    ``corpus_date`` — the SPARQL/catalogue period, or the stop title's date);
    otherwise it is the FIRST creation date stated in the body. Never empties a
    body (D577).

    Returns (new_body, report) with report = {dropped, kept_date, conflicts,
    changed}.
    """
    report = {"dropped": 0, "kept_date": None, "conflicts": [], "changed": False}
    if not body or not body.strip():
        return body, report

    sents = _split_sentences(body)
    if len(sents) <= 1:
        return body, report

    kept_range = parse_date_range(corpus_date) if corpus_date else None

    # If no corpus date, anchor on the first creation date stated in the body.
    if kept_range is None:
        for s in sents:
            ds = creation_dates_in_sentence(s)
            if ds:
                kept_range = ds[0]
                break
    report["kept_date"] = kept_range

    if kept_range is None:
        return body, report  # no date anywhere to anchor on

    kept: List[str] = []
    dropped = 0
    anchored = False  # keep the FIRST sentence that states the kept date
    for s in sents:
        ds = creation_dates_in_sentence(s)
        if not ds:
            kept.append(s)
            continue
        # A sentence is a conflict when EVERY creation date it states conflicts
        # with the kept range AND none of them equals/nests the kept range — i.e.
        # it carries a different work date and nothing reconciling it.
        reconciles = any(not ranges_conflict(d, kept_range) for d in ds)
        if reconciles:
            # If it states the kept date (or a compatible refinement), keep it,
            # but only the FIRST such sentence may introduce the kept date again —
            # later exact repeats of a conflicting-only date were already handled.
            kept.append(s)
            anchored = True
            continue
        # every date in this sentence conflicts with the kept date → drop it
        dropped += 1
        report["conflicts"].append({"sentence": s[:90], "dates": ds,
                                     "kept": kept_range})

    if dropped == 0:
        return body, report
    new_body = " ".join(k.strip() for k in kept if k.strip()).strip()
    if not new_body:
        return body, report
    report["dropped"] = dropped
    report["changed"] = True
    return new_body, report


_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")


def _title_from_header(header: str) -> str:
    m = re.match(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*(.+?)\s*$", header or "")
    return m.group(1).strip() if m else ""


def filter_tour_text_date_consistency(tour_text: str,
                                      stop_corpus_dates: Optional[Dict[int, str]] = None
                                      ) -> Tuple[str, Dict]:
    """Apply the date-consistency filter across a delivered tour, per stop. The
    kept date for each stop is ``stop_corpus_dates[n]`` when provided (the corpus
    date wins), else the stop title's own date, else the first date stated.
    Pure string→string. Returns (new_text, report)."""
    report = {"stops": 0, "dropped": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report
    out = [parts[0]]
    i, stop_index, total_dropped = 1, 0, 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        corpus_date = (stop_corpus_dates or {}).get(stop_index, "")
        if not corpus_date:
            # fall back to a date embedded in the stop title, if any
            corpus_date = _title_from_header(header)
        paras = re.split(r"(\n\s*\n)", body)
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            filtered, prep = filter_stop_body_date_consistency(seg, corpus_date)
            total_dropped += prep.get("dropped", 0)
            new_paras.append(filtered)
        out.append(header)
        out.append("".join(new_paras))
        i += 2
    report["dropped"] = total_dropped
    report["changed"] = total_dropped > 0
    return "".join(out), report


# ---------------------------------------------------------------------------
# [LOCAL-630 item 8] Computed year-spans recomputed from the two dates, or dropped
# ---------------------------------------------------------------------------
#
# NG 495 Stop 2 (Rokeby Venus): "Nearly 247 years after it was painted" — the work
# was painted 1647–51 and attacked in 1914, so the real span is about 263–267
# years, not 247. A phrase of the form "N years after/later/before" is ARITHMETIC:
# it must equal the difference between two dates the text itself states. This gate,
# run per stop on the delivered text, finds each such phrase, recomputes N from the
# two nearest years in the sentence (preferring the sentence; falling back to the
# stop body), and either CORRECTS N or DROPS the whole span clause when the two
# anchor dates cannot be identified. It never invents a date; it only checks the
# text's own arithmetic. Pure, deterministic, idempotent.

# "Nearly 247 years after", "about 12 years later", "some 30 years before",
# "a hundred years later" is NOT matched (we only recompute numeric spans).
_YEAR_SPAN_RE = re.compile(
    r"(?i)\b((?:nearly|almost|about|around|roughly|some|just|over|more\s+than|"
    r"less\s+than|approximately)\s+)?(\d{1,4})\s+years?\s+(after|later|before|"
    r"earlier|prior)\b")

# Tolerance: a stated span within this many years of the recomputed value is left
# alone (rounding/"nearly" slack). Beyond it, the number is corrected.
_YEAR_SPAN_TOLERANCE = 2


def _years_in(text: str) -> "List[int]":
    """All distinct 4-digit years (1000–2099) in ``text``, in order of appearance."""
    out = []
    for m in re.finditer(r"\b(1[0-9]{3}|20[0-9]{2})\b", text or ""):
        y = int(m.group(1))
        if y not in out:
            out.append(y)
    return out


def recompute_year_spans(text: str, context: str = "") -> "Tuple[str, Dict]":
    """Recompute every "N years after/later/before/earlier" span in ``text`` from
    the dates the text states; correct a wrong N, or drop the span clause when the
    two anchor dates cannot be found.

    ``context`` is additional text (the whole stop body) scanned for anchor years
    when the sentence carrying the phrase names fewer than two. Returns
    ``(new_text, report)`` with report = {corrected, dropped, changed, details}.

    Rule per phrase:
      * Gather the distinct years in the sentence; if < 2, add the years from
        ``context``. The span's true value is the max span between the available
        anchor years (the gap the phrase is describing — the earliest creation
        year to the latest event year).
      * If at least two anchor years exist: if the stated N differs from the
        recomputed span by more than the tolerance, REPLACE N with the recomputed
        value (keeping the leading qualifier like "about"); within tolerance → keep.
      * If fewer than two anchor years exist anywhere: DROP the span clause
        ("N years after/later" and any leading qualifier), since the arithmetic
        cannot be verified and an unverifiable computed number is worse than none.
    """
    report = {"corrected": 0, "dropped": 0, "changed": False, "details": []}
    if not text or not _YEAR_SPAN_RE.search(text):
        return text or "", report

    ctx_years = _years_in(context) if context else []

    def _repl(m: "re.Match") -> str:
        qualifier = (m.group(1) or "")
        stated = int(m.group(2))
        direction = m.group(3)
        # Anchor years: the sentence this phrase sits in, else the context body.
        sent_years = _years_in(text)
        anchors = sent_years if len(sent_years) >= 2 else list(
            dict.fromkeys(sent_years + ctx_years))
        if len(anchors) < 2:
            # cannot verify → drop the whole span clause
            report["dropped"] += 1
            report["changed"] = True
            report["details"].append({"phrase": m.group(0), "action": "dropped",
                                       "reason": "fewer than two anchor years"})
            return ""  # remove the clause; surrounding cleanup tidies spacing
        true_span = max(anchors) - min(anchors)
        if abs(true_span - stated) <= _YEAR_SPAN_TOLERANCE:
            return m.group(0)  # within slack, keep as written
        report["corrected"] += 1
        report["changed"] = True
        report["details"].append({"phrase": m.group(0), "action": "corrected",
                                   "from": stated, "to": true_span})
        # Preserve the qualifier (e.g. "about ") and the direction word.
        return f"{qualifier}{true_span} years {direction}"

    out = _YEAR_SPAN_RE.sub(_repl, text)
    # Tidy spacing / doubled punctuation left by a dropped clause.
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;!?])", r"\1", out)
    out = re.sub(r",\s*,", ",", out)
    # Repair a sentence left dangling by a dropped mid-sentence clause
    # ("The work, , was attacked" → "The work was attacked").
    out = re.sub(r",\s*,", ",", out)
    return out, report


def recompute_year_spans_in_tour(tour_text: str) -> "Tuple[str, Dict]":
    """Apply ``recompute_year_spans`` across a delivered tour, per stop body, with
    the whole stop body as the anchor-year context for each sentence. Pure
    string→string. Returns (new_text, report)."""
    report = {"stops": 0, "corrected": 0, "dropped": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        # No stop structure — treat the whole text as one body.
        out, prep = recompute_year_spans(tour_text, context=tour_text)
        report["corrected"] = prep["corrected"]
        report["dropped"] = prep["dropped"]
        report["changed"] = prep["changed"]
        return out, report
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        report["stops"] += 1
        new_body, prep = recompute_year_spans(body, context=body)
        report["corrected"] += prep["corrected"]
        report["dropped"] += prep["dropped"]
        out.append(header)
        out.append(new_body)
        i += 2
    report["changed"] = report["corrected"] > 0 or report["dropped"] > 0
    return "".join(out), report

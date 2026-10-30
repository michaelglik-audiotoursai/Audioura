"""stop_title_body_dup_guard.py — [LOCAL-823] a stop title is never a copy of its body.

The defect
----------
Belvedere (Vienna) cheap-arm proof tour 474, Stop 1: the stop's BODY TEXT was
duplicated onto its TITLE line. The delivered header read, in full, the opening
run of the stop's own narration instead of the work's name — so the "Stop N:"
banner the listener sees was a prefix copy of the paragraph that follows it.

That happens when the stop's ``name`` is set from a scraped/LLM line that is the
first sentence(s) of the body rather than the work's short title: the assembly at
``generate_tour_text`` writes ``Stop {i+1}: {name}\n\n{description}``, and when
``name`` is (a long prefix of) ``description`` the title line just repeats the
body.

This module is the deterministic, no-LLM delivery check the task asks for:

    a stop title is NEVER a prefix copy of its body.

It is a pure text guard applied to the DELIVERED tour text at the same single
choke point every other D6xx/LOCAL-722 body guard uses, AFTER the LOCAL-722
duplicate-stop dedup and BEFORE the conclusion/header rebuild — so a repaired
title flows into the rebuilt "first stop" orientation and header. It is also
usable at the SOURCE on a single ``(title, body)`` pair (``repair_title``), which
``generate_tour_text`` calls when it finalises each stop's ``name`` so the defect
is fixed before it ever reaches the delivered text.

What counts as "a prefix copy of the body"
-------------------------------------------
A title is a body-prefix duplicate when, after the SAME normalisation
``stop_title_dedup.normalize_stop_title`` uses (casefold, strip accents, strip
punctuation, collapse whitespace), the normalised body STARTS WITH the whole
normalised title AND the title is long enough that this cannot be a coincidence:

  * the title is LONG — more than ``_MIN_TITLE_WORDS`` words (a real work title
    "Austrian State Treaty" is 3 words and is NOT a body opener; a title that is
    6+ words and is literally how the body begins is the defect), OR
  * the title is a FULL SENTENCE (ends with sentence punctuation / contains a
    finite-verb clause) that the body repeats verbatim.

A SHORT, proper-name title ("Austrian State Treaty", "Belvedere Palace Chapel",
"The Kiss") is never touched even when the body's first words happen to repeat it
("Austrian State Treaty was signed…") — repeating the work's NAME at the top of
its own description is normal and wanted. Only a long, sentence-shaped title that
IS the body's opening run is a duplicate.

The repair
----------
When the title is a body-prefix duplicate there is, by construction, no short
title to fall back to in the text alone. The guard shortens the title to a clean
proper-name-length prefix of itself (the first clause, truncated at
``_REPAIR_MAX_WORDS`` words on a word boundary, trailing punctuation stripped) so
the banner is a title again rather than a paragraph. ``repair_title`` additionally
accepts an optional ``fallback`` (the work's real short name, when the caller has
one) and uses it instead of truncating.

Pure, deterministic, idempotent.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from stop_title_dedup import normalize_stop_title, _STOP_HEADER_RE

__all__ = [
    "title_is_body_prefix",
    "repair_title",
    "repair_tour_text_title_body_dup",
]

# A title shorter than this (in words) is a proper name, never a body opener —
# "Austrian State Treaty" (3), "Belvedere Palace Chapel" (3). Only a title of
# MORE than this many words can be flagged as a sentence-shaped body prefix.
_MIN_TITLE_WORDS = 5

# When repairing, truncate the over-long title to at most this many words so the
# banner reads as a title. Chosen to comfortably hold real multi-word work names
# ("Napoleon Crossing the Alps at the Great St Bernard Pass" = 9) without keeping
# a whole sentence.
_REPAIR_MAX_WORDS = 9

# Finite-verb / sentence tell — a title carrying one of these reads as a clause,
# not a name, so even a shorter such title that the body repeats verbatim is a
# body-sentence duplicate.
_SENTENCE_VERB_RE = re.compile(
    r"(?i)\b(?:is|are|was|were|has|have|had|will|would|stands?|became|"
    r"signed|opened|built|commissioned|depicts?|shows?|marks?)\b")


def _norm(text: str) -> str:
    return normalize_stop_title(text or "")


def title_is_body_prefix(title: str, body: str) -> bool:
    """True when ``title`` is a prefix COPY of ``body`` — the LOCAL-823 defect.

    Deterministic and conservative: a short proper-name title is never flagged,
    even when the body opens by naming the work. A title is a body-prefix
    duplicate only when the normalised body starts with the whole normalised
    title AND the title is long (``> _MIN_TITLE_WORDS`` words) or is itself a
    full sentence (ends in sentence punctuation, or carries a finite verb and is
    at least 4 words).
    """
    nt = _norm(title)
    nb = _norm(body)
    if not nt or not nb:
        return False
    # The body must actually BEGIN with the whole title (token-aligned prefix).
    if not (nb == nt or nb.startswith(nt + " ")):
        return False
    t_words = nt.split()
    n_t = len(t_words)
    raw = (title or "").strip()
    sentence_shaped = (
        bool(re.search(r"[.!?]\s*$", raw))
        or (n_t >= 4 and bool(_SENTENCE_VERB_RE.search(raw)))
    )
    return n_t > _MIN_TITLE_WORDS or sentence_shaped


def repair_title(title: str, body: str, fallback: str = "") -> Tuple[str, bool]:
    """Return ``(title_out, repaired)``. When ``title`` is a body-prefix copy of
    ``body``, replace it with ``fallback`` (if given and itself not a body prefix)
    or a truncated proper-name-length prefix of the title; otherwise return the
    title unchanged.

    Idempotent: a title that is not a body-prefix duplicate (including an
    already-repaired short title) is returned unchanged.
    """
    if not title_is_body_prefix(title, body):
        return (title or "").strip(), False
    fb = (fallback or "").strip()
    if fb and not title_is_body_prefix(fb, body):
        return fb, True
    # Truncate the over-long title to a clean title-length prefix on a word
    # boundary, cutting at the first clause break if one falls early.
    raw = (title or "").strip()
    # Prefer the first clause (up to the first sentence/clause punctuation).
    clause = re.split(r"[.!?;:,]", raw, maxsplit=1)[0].strip()
    words = (clause or raw).split()
    if len(words) > _REPAIR_MAX_WORDS:
        words = words[:_REPAIR_MAX_WORDS]
    out = " ".join(words).strip(" -–—:;,.").strip()
    # Never return an empty banner; fall back to the untruncated first clause.
    if not out:
        out = clause or raw
    return out, True


def _split_into_blocks(tour_text: str):
    """(preamble, [{'num','title','text'}]) — mirrors stop_title_dedup's split."""
    matches = list(_STOP_HEADER_RE.finditer(tour_text))
    if not matches:
        return tour_text, []
    preamble = tour_text[:matches[0].start()]
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(tour_text)
        blocks.append({
            "num": int(m.group(1)),
            "title": m.group(2).strip(),
            "text": tour_text[start:end],
        })
    return preamble, blocks


def _block_body(block_text: str) -> str:
    """The narration body of a stop block — everything after the ``Stop N:``
    header line, with the field lines (Address/Coordinates/Orientation/
    Directions) stripped so the comparison is against spoken prose."""
    # Drop the header line.
    after = _STOP_HEADER_RE.sub("", block_text, count=1)
    lines = []
    for ln in after.split("\n"):
        s = ln.strip()
        if not s:
            continue
        # Skip structured field lines; keep spoken prose (incl. the orientation
        # text that follows the "Orientation:" label).
        if re.match(r"(?i)^(address|coordinates|directions|tour-category|"
                    r"sources?)\s*:", s):
            continue
        s = re.sub(r"(?i)^orientation:\s*", "", s)
        if s:
            lines.append(s)
    return " ".join(lines)


def repair_tour_text_title_body_dup(tour_text: str) -> Tuple[str, List[Dict]]:
    """Repair every stop whose ``Stop N:`` title is a prefix copy of its body.

    Returns ``(new_text, repaired)`` where ``repaired`` is a list of
    ``{'num', 'old_title', 'new_title'}`` in stop order. Only the header LINE of
    an affected block is rewritten; the body and all field lines are preserved
    byte-for-byte. Deterministic and idempotent — a second call changes nothing.
    """
    if not tour_text:
        return tour_text or "", []
    preamble, blocks = _split_into_blocks(tour_text)
    if not blocks:
        return tour_text, []
    repaired: List[Dict] = []
    out_parts = [preamble]
    for b in blocks:
        body = _block_body(b["text"])
        new_title, did = repair_title(b["title"], body)
        if did and new_title != b["title"]:
            new_text = _STOP_HEADER_RE.sub(
                lambda m, _t=new_title: f"Stop {m.group(1)}: {_t}",
                b["text"], count=1)
            repaired.append({"num": b["num"], "old_title": b["title"],
                             "new_title": new_title})
            out_parts.append(new_text)
        else:
            out_parts.append(b["text"])
    if not repaired:
        return tour_text, []
    return "".join(out_parts), repaired

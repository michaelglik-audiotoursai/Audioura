"""
paragraph_dedupe.py — [LOCAL-615 item 1] Remove duplicated paragraphs from a tour.
==================================================================================

D626 calibration batch (tours 403 Lyon, 405 Bilbao): Stop 1's whole orientation
paragraph was printed TWICE, verbatim. On the FRESH path the D611 opening fold and
the generator's own orientation body both emitted the same paragraph, so the
listener heard the entire opening a second time.

Rather than chase which of the two emitters produced the second copy (the shape of
the overlap differs per tour — one copy carries the "Orientation:" label, the other
is a bare paragraph), this is a deterministic, source-agnostic dedupe pass over the
final assembled tour text, exactly as Michael specified:

    "any paragraph >= 80 chars appearing twice -> style FAIL and automatic removal
     of the second copy."

Two entry points, sharing one normaliser so the QA check and the removal pass agree
to the character on what counts as a duplicate:

  * ``find_duplicate_paragraphs(text)`` — the detector the QA runner calls. Returns
    the list of offending paragraphs (each reported once, however many copies).
  * ``dedupe_paragraphs(text)`` — the corrective pass the generator calls. Keeps the
    FIRST occurrence of every paragraph and drops each later verbatim copy, returning
    ``(new_text, removed)`` where ``removed`` is the list of dropped paragraph texts.

A "paragraph" is a block of text separated from its neighbours by a blank line
(``\n\n``), matching how the pipeline assembles ``complete_tour`` (every stop section
and sub-block is joined with a blank line). Structural one-liners (``Stop 1:``,
``Address:``, ``Coordinates:``, ``Directions:`` …) are never deduped — repeating the
"Address:" line across stops is correct, and those lines are short anyway.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Minimum length (characters, after normalisation) for a paragraph to be a dedupe
# candidate. Michael's spec: ">= 80 chars". Short lines (labels, one-word answers)
# are exempt — repeating "Address: …" across stops is correct.
MIN_PARAGRAPH_CHARS = 80

# Structural lines that legitimately repeat across stops and must never be treated
# as duplicated prose. Matched at the START of a paragraph's first line.
_STRUCTURAL_PREFIX_RE = re.compile(
    r'^(Stop\s+\d+:|Address:|Coordinates:|Type/?Specialty:|Specific Examples?:|'
    r'Operational Details:|Museum Information:|Directions:|Sources:|'
    r'Tour-Category:|Please resume:)',
    re.IGNORECASE,
)


def _normalise(paragraph: str) -> str:
    """Canonical form used to compare two paragraphs.

    Collapses internal whitespace and strips a leading ``Orientation:`` label so the
    labelled first copy and the bare second copy of the same orientation paragraph
    compare equal (that is exactly the 403/405 shape). Case is preserved — a genuine
    sentence appearing twice is identical in case; we are not trying to catch
    paraphrase here, only verbatim repetition (the >0.85 similarity check handles
    near-duplicates elsewhere).
    """
    p = (paragraph or "").strip()
    # Drop a single leading "Orientation:" label (the one structural prefix that
    # wraps real prose rather than a short field) so the orientation body compares
    # equal to its bare duplicate.
    p = re.sub(r'^Orientation:\s*', '', p, flags=re.IGNORECASE)
    # Collapse all runs of whitespace (incl. newlines) to a single space.
    p = re.sub(r'\s+', ' ', p).strip()
    return p


def _is_structural(paragraph: str) -> bool:
    """True when the paragraph is a structural one-liner that may repeat (Address,
    Coordinates, Directions, …). Such paragraphs are never deduped."""
    first_line = (paragraph or "").strip().split('\n', 1)[0].strip()
    return bool(_STRUCTURAL_PREFIX_RE.match(first_line))


def _is_candidate(paragraph: str) -> bool:
    """True when a paragraph is long enough and prose-like enough to be a dedupe
    candidate (>= MIN_PARAGRAPH_CHARS after normalisation, not a structural line)."""
    if _is_structural(paragraph):
        return False
    return len(_normalise(paragraph)) >= MIN_PARAGRAPH_CHARS


def find_duplicate_paragraphs(text: str) -> List[str]:
    """Return the distinct paragraphs (>= 80 chars) that appear more than once.

    Each offending paragraph is reported ONCE (by its first-seen raw form), however
    many copies exist. Used by content_qa_runner's "No duplicated paragraph" check.
    """
    if not text:
        return []
    paragraphs = re.split(r'\n\s*\n', text)
    seen = {}            # normalised -> first raw occurrence
    dupes = {}           # normalised -> first raw occurrence (reported once)
    for raw in paragraphs:
        if not _is_candidate(raw):
            continue
        key = _normalise(raw)
        if key in seen:
            if key not in dupes:
                dupes[key] = seen[key]
        else:
            seen[key] = raw.strip()
    return list(dupes.values())


def dedupe_paragraphs(text: str) -> Tuple[str, List[str]]:
    """Remove every verbatim duplicate paragraph (>= 80 chars), keeping the FIRST.

    Returns ``(new_text, removed)``. ``removed`` is the list of dropped paragraph
    texts (one entry per removed copy). The paragraph structure (blank-line
    separation) of the kept text is preserved; only the later copies are deleted.
    Idempotent: a second call on the result removes nothing.
    """
    if not text:
        return text, []
    # Split on blank-line boundaries but KEEP the exact separators so we can
    # rebuild the text with the original spacing, minus the removed blocks.
    parts = re.split(r'(\n\s*\n)', text)   # alternating [block, sep, block, sep, ...]
    seen = set()
    out_parts: List[str] = []
    removed: List[str] = []
    for part in parts:
        # Separators (pure whitespace with a blank line) pass through untouched.
        if re.fullmatch(r'\n\s*\n', part):
            out_parts.append(part)
            continue
        if _is_candidate(part):
            key = _normalise(part)
            if key in seen:
                removed.append(part.strip())
                # Drop this block. Also drop an immediately-preceding separator so
                # we do not leave a double blank line where the block used to be.
                if out_parts and re.fullmatch(r'\n\s*\n', out_parts[-1]):
                    out_parts.pop()
                continue
            seen.add(key)
        out_parts.append(part)
    new_text = ''.join(out_parts)
    return new_text, removed

"""safety_note_order.py — [LOCAL-791 defect 7] Safety/scam notes belong AFTER the
place is introduced, framed as a tip — never as the stop's opening sentence.

THE DEFECT
----------
Tour 467 (Red Canyon, Mui Ne) opened its stop like this:

    "Their smiles are welcoming, but their true intent becomes clear when they
     later demand a 'guide fee'…"

The listener arrives at a stop and the very first thing they hear is a scam
warning about people they have not been introduced to ("Their" refers to nothing
yet). A safety or scam note is useful, but it is a PRACTICAL TIP that belongs
after the place has been introduced, phrased as advice — not the cold open.

THE FIX
-------
A pure, deterministic text pass (mirrors the dangling-opener guards): for each
stop, if the FIRST prose sentence of the body is a safety/scam warning AND the
stop has at least one more sentence that introduces the place, MOVE that warning
to the END of the stop body and prefix it with a tip framing ("A practical tip:
…"). The place is then introduced first and the caution lands as advice.

Conservative:
  * only the FIRST sentence is ever moved, and only when it matches a
    safety/scam signature (scam, fee demands, "watch out", "be careful",
    pickpocket, overcharge, aggressive vendors, …);
  * the stop must have a later sentence to lead with — a one-sentence stop is
    left alone (moving its only sentence would empty it);
  * the warning text is preserved verbatim after the tip prefix; nothing is
    invented or dropped.

Pure: no network, no LLM. Unit-tested in test_local791_vietnam_round2.py.
"""
from __future__ import annotations

import re
from typing import List, Tuple

__all__ = [
    "is_safety_or_scam_sentence",
    "reframe_opening_safety_note",
    "reorder_safety_notes_in_text",
]

# A sentence is a SAFETY / SCAM caution when it carries one of these signals. Kept
# specific to travel-safety advice so an ordinary descriptive sentence that merely
# mentions, say, "free" or "money" is not caught.
_SAFETY_SCAM_RE = re.compile(
    r"(?i)\b("
    r"scam(?:s|med|ming)?|scammer|con\s+artists?|rip[-\s]?off|"
    r"guide\s+fee|unofficial\s+guides?|fake\s+guides?|"
    r"overcharg(?:e|ed|ing)|over[-\s]?priced|hidden\s+(?:fee|charge|cost)|"
    r"pickpocket|pick[-\s]?pockets?|theft|thieves|stolen|snatch(?:ing)?|"
    r"watch\s+out|be\s+(?:very\s+)?(?:careful|wary|cautious|alert)|beware|"
    r"avoid\s+(?:being|getting)|do\s+not\s+(?:pay|hand|give)|don['\u2019]t\s+(?:pay|hand|give)|"
    r"demand(?:s|ed|ing)?\s+(?:a\s+)?(?:['\u2018\u2019\"]?(?:guide\s+)?fee|money|payment|cash|tip)|"
    r"aggressive\s+(?:vendors?|sellers?|touts?|hawkers?)|touts?|"
    r"true\s+intent|their\s+true|pressur(?:e|ed|ing)\s+you"
    r")\b")

# A safety sentence that OPENS on an unresolved pronoun/possessive ("Their smiles
# …", "They will …") is especially clearly out of context — a strong signal it
# was placed before the subject was introduced. (Not required, but it raises
# confidence; the signature match above is the gate.)
_PRONOUN_OPEN_RE = re.compile(
    r"(?i)^\s*(?:their|they|them|these\s+people|those\s+people|he|she|his|her)\b")

# Tip framing prepended to a moved safety note. Chosen so the note reads as advice
# once relocated after the place introduction.
_TIP_PREFIX = "A practical tip: "


def is_safety_or_scam_sentence(sentence: str) -> bool:
    """True when ``sentence`` is a travel safety / scam caution. Pure."""
    return bool(_SAFETY_SCAM_RE.search(sentence or ""))


def _split_sentences(text: str) -> List[str]:
    """Split prose into sentences on ., !, ? and the ellipsis, keeping terminators.
    Mirrors the lightweight splitter used by the dangling-opener gates."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?\u2026])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def reframe_opening_safety_note(body: str) -> Tuple[str, bool]:
    """If ``body``'s FIRST sentence is a safety/scam caution and there is at least
    one more sentence, move that caution to the END, prefixed with the tip framing.
    Returns ``(new_body, moved)``. Pure; nothing is dropped or invented."""
    sentences = _split_sentences(body)
    if len(sentences) < 2:
        return body, False
    first = sentences[0]
    if not is_safety_or_scam_sentence(first):
        return body, False
    rest = sentences[1:]
    # Build the tip: prefix the warning, lower-casing a leading pronoun opener so
    # "Their true intent…" reads naturally after "A practical tip: ".
    note = first
    tip = _TIP_PREFIX + (note[0].lower() + note[1:] if note else note)
    new_sentences = rest + [tip]
    return " ".join(new_sentences), True


_TEXT_STOP_HEADER_RE = re.compile(r'(?mi)^Stop\s+\d+:\s*(.+?)\s*$')
_TEXT_FIELD_LINE_RE = re.compile(
    r'(?mi)^(?:Address|Coordinates|Directions|Sources|Museum Information|'
    r'Type/Specialty|Specific Examples|Operational Details|Orientation):')


def reorder_safety_notes_in_text(tour_text: str) -> Tuple[str, int]:
    """Walk a delivered tour stop by stop; when a stop's first prose sentence is a
    safety/scam caution, move it to the end of that stop's first prose line framed
    as a tip. Returns ``(new_text, n_moved)``. Header/field lines are preserved
    verbatim. Deterministic, pure."""
    if not tour_text:
        return tour_text or "", 0
    lines = tour_text.split("\n")
    header_idxs = [i for i, ln in enumerate(lines)
                   if _TEXT_STOP_HEADER_RE.match(ln.strip())]
    if not header_idxs:
        # No stop headers — treat the whole text as one body (unit/test shape).
        new_body, moved = reframe_opening_safety_note(tour_text)
        return (new_body, 1) if moved else (tour_text, 0)

    moved = 0
    for h, start in enumerate(header_idxs):
        end = header_idxs[h + 1] if h + 1 < len(header_idxs) else len(lines)
        for li in range(start + 1, end):
            s = lines[li].strip()
            if not s or _TEXT_FIELD_LINE_RE.match(s):
                continue
            # First prose line of the stop — the opening narration.
            new_body, did = reframe_opening_safety_note(s)
            if did:
                lines[li] = new_body
                moved += 1
            break
    return "\n".join(lines), moved

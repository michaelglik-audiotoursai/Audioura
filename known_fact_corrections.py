#!/usr/bin/env python3
"""known_fact_corrections.py — D523: facts we have positively established.

The 12:23 tour said, in stop 2's descriptive prose:

    "Sigmund Freud… proposing the controversial theory that Moses was an
     Egyptian **priest**."

Freud argued Moses was an Egyptian **nobleman** — a follower of Akhenaten. We know
this is wrong because the adjudicator CORRECTED it against retrieved sources on
2026-08-23, and the corrected version was published in that tour's story.

**Why the existing checks do not catch it.** `check_known_defects` looks for a
SELF-CONTRADICTION — the priest claim standing next to the nobility claim in one
stop — which is what happened on 08-23. On 12:23 only the wrong version appeared,
so the check stayed silent. **A tour that is confidently wrong in one direction is
worse than one that contradicts itself, and it was the case nothing was watching.**

## What this file is, and what it is not

It is a small table of corrections that a *specific* adjudication run has already
established, applied to descriptive prose, which is written from parametric memory
and faces no retrieval. It is a stopgap with a narrow charter, not a fact-checker.

**The rule for adding an entry** — all three, or it does not go in:

  1. The wrong version was actually observed in a delivered tour. Cite the file.
  2. The right version was established by RETRIEVAL, not by anyone's memory —
     an adjudicator CORRECTED verdict, or a source we can name.
  3. The pattern is specific enough that it cannot fire on a true sentence.
     Prefer a whole phrase over a word.

**The real fix is upstream** and is not this: the descriptive-prose generator
should be grounded in the same corpus the story loop retrieves, so it cannot
assert what no source supports. Until then, a fact we have already paid to verify
should not be re-emitted wrongly on the next run.
"""
import re
from typing import Dict, List, Tuple

__all__ = ['apply_corrections', 'CORRECTIONS']

# (pattern, replacement, why) — `why` is printed when it fires and is the audit
# trail, so a correction can never be silent.
CORRECTIONS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r'\bMoses\s+was\s+(?:an?\s+)?(?:ancient\s+)?Egyptian\s+priest\b',
                re.IGNORECASE),
     'Moses was an Egyptian nobleman',
     "Freud's thesis in *Moses and Monotheism* is that Moses was an Egyptian "
     "NOBLEMAN, a follower of Akhenaten — not a priest. Adjudicator CORRECTED "
     "this against retrieved sources on 2026-08-23; wrong version delivered in "
     "TOUR_LOOP_20260824_1223.txt stop 2 with nothing contradicting it."),

    (re.compile(r'\bMoses\s+was\s+not\s+a\s+Hebrew\s+but\s+an\s+Egyptian\s+priest\b',
                re.IGNORECASE),
     'Moses was not a Hebrew but an Egyptian nobleman',
     "Same claim, the 08-23 phrasing. Delivered in TOUR_LOOP_20260823_1821.txt "
     "stop 3, where it sat beside the corrected version in the same stop."),

    (re.compile(r'\bMoses\s+was\s+an\s+Egyptian\s+priest,\s+not\s+Hebrew\b',
                re.IGNORECASE),
     'Moses was an Egyptian nobleman, not Hebrew',
     "Same claim as it appeared in the closing recap of TOUR_LOOP_20260823_1821."),
]


def apply_corrections(text: str, verbose: bool = False) -> Tuple[str, List[Dict]]:
    """Replace established errors. Returns (text, [{'was','now','why'}, ...])."""
    fired = []
    if not text:
        return text or '', fired
    for pattern, replacement, why in CORRECTIONS:
        m = pattern.search(text)
        if not m:
            continue
        fired.append({'was': m.group(0), 'now': replacement, 'why': why})
        text = pattern.sub(replacement, text)
        if verbose:
            print(f"  [D523] CORRECTED \"{m.group(0)}\" -> \"{replacement}\"")
            print(f"         {why.splitlines()[0]}")
    return text, fired

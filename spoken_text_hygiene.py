#!/usr/bin/env python3
"""spoken_text_hygiene.py — D523: the last pass before a human hears it.

Two defects that survived every gate because no gate was looking at the assembled
text as SOUND rather than as claims.

**1. Template seams.** `"At this work: Le Lézard aux plumes d'or, witness Miró's
surreal exploration…"` — spoken aloud that is "at this work colon". The prompt
asks for "<fact> at <stop name>" and the model answers with a label. A strip for
exactly this already existed at `generate_tour_text.py:15498` but was applied only
to Part 4, and the 12:23 tour put it in the stop-1 ORIENTATION, which comes from a
different generator. So the strip moves here, where it sees the finished tour and
cannot be routed around.

**2. A full stop with no space after it.** `"…mythic creature.Published by Louis
Broder…"`, `"…printed works.This exhibition…"`, `"…depth.Boris Fridman…"`. Five
sightings in six runs — LEAD reported it as a "known defect" three times without
fixing it, on the grounds that it was upstream. It is upstream, and it is also two
lines to repair here, and a listener hears a word that does not exist.

Both are applied to the assembled tour, after every gate has had its say, so
nothing downstream can reintroduce them.
"""
import re

__all__ = ['clean_spoken_text', 'MISSING_SPACE_RE', 'TEMPLATE_SEAM_RE',
           'DANGLING_PHRASE_RE']

# "At this work:", "in the stop:", "At this piece:" — the preposition keeps its
# original case, because replacing with a literal "At " produced "Then, At Au
# Soleil du Plafond" when this lived in the Part 4 verifier.
TEMPLATE_SEAM_RE = re.compile(
    r'\b(at|in|for)\s+th(?:is|e)\s+(?:work|stop|piece|item|location)\s*:\s*',
    re.IGNORECASE)

# A sentence-ending full stop with the next sentence jammed against it. TWO
# lowercase letters before and a capital plus TWO lowercase after, which is what
# keeps every abbreviation and every domain out of range:
#   christies.com   lowercase after the dot        — no match
#   U.S.A.          single letters before the dot  — no match
#   Ph.D            single letter after            — no match
#
# **The quote had to be allowed for.** The first version was
# `([a-zà-ÿ]{2})\.([A-ZÀ-Ý][a-zà-ÿ]{2})` and the very next tour shipped
# `…blend of text and imagery."Au Soleil du Plafond" thus advances…` — a quotation
# mark between the stop and the capital, which the pattern could not cross. The
# defect checker had the identical blind spot and reported the tour clean.
#   "Au Soleil"     ONE lowercase after the capital — so the tail is {1,}, not
#                   {2}, which is what let the quote case through a second time.
MISSING_SPACE_RE = re.compile(
    r'([a-zà-ÿ]{2})\.(["“”\'‘’]?)([A-ZÀ-Ý][a-zà-ÿ]+)')

# A participial phrase whose object was deleted by an upstream gate.
#
# Measured in the same run: `[LOCAL-392] Torf Gallery -> DEGRADED (name dropped)`
# left "The eleven lithographs, housed in are rarely on view…". The gate was right
# to drop an ungrounded gallery name and wrong to leave the preposition holding
# nothing. Repairing the sentence is not that gate's job, but it is somebody's.
DANGLING_PHRASE_RE = re.compile(
    r',\s*[a-zà-ÿ]+ed\s+(?:in|at|on|by|for|from)\s+(?=(?:are|is|was|were)\b)',
    re.IGNORECASE)

# Labels that are structure, not speech. Michael, 2026-08-24: Orientation and
# Directions stay, "because they let listeners know that they are not part of the
# stop description" — so they are deliberately absent here.
SPOKEN_LABEL_RE = re.compile(r'\b(?:Closing|Narration|Body|Summary)\s*:\s*')


def clean_spoken_text(text: str, verbose: bool = False) -> tuple:
    """Return (cleaned, report). Never reorders, never rewrites — only repairs."""
    report = {'seams': 0, 'missing_spaces': 0, 'labels': 0, 'dangling': 0}
    if not text:
        return text or '', report

    report['seams'] = len(TEMPLATE_SEAM_RE.findall(text))
    out = TEMPLATE_SEAM_RE.sub(lambda m: m.group(1) + ' ', text)

    report['missing_spaces'] = len(MISSING_SPACE_RE.findall(out))
    out = MISSING_SPACE_RE.sub(r'\1. \2\3', out)

    report['dangling'] = len(DANGLING_PHRASE_RE.findall(out))
    out = DANGLING_PHRASE_RE.sub(' ', out)

    report['labels'] = len(SPOKEN_LABEL_RE.findall(out))
    out = SPOKEN_LABEL_RE.sub('', out)

    if verbose and any(report.values()):
        print(f"  [D523] spoken-text hygiene: {report['seams']} template seam(s), "
              f"{report['missing_spaces']} missing space(s), "
              f"{report['labels']} spoken label(s), "
              f"{report['dangling']} dangling phrase(s) removed")
    return out, report

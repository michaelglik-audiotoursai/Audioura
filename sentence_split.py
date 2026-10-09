"""A sentence splitter that does not cut on an abbreviation's full stop.

Michael, 2026-09-18, reading CHURCH_tour_3: *"In the Stop 1 I see leftover pieces
of the sentences, like 'Founded in 1868 by St.' What is St? Probably there was
some name at some point."*

There was. The delivered text reads:

    "...resilience of this neighborhood. Founded in 1868 by St. As you continue
     the tour, you'll learn about the murder of..."

Every gate in the pipeline splits sentences with `re.split(r'(?<=[.!?])\\s+', text)`
and **none of them guards abbreviations**, so `St. Mary's` becomes two "sentences":
`...by St.` and `Mary's ...`. A gate then drops one fragment as unsupported and
`' '.join`s the survivors, leaving a sentence that ends on a title with no name.

The same defect hit LEAD's own `geo_refutation` module hours earlier, where
`Archbishop of Los Angeles. His act...` was captured as the place name
"Los Angeles. His". Fixtures never show it; real prose always does.

`split_sentences` is a drop-in replacement for that regex.
"""

import re

# Titles, honorifics and common abbreviations whose dot is NOT a sentence end.
_ABBREV = {
    'st', 'ss', 'mr', 'mrs', 'ms', 'dr', 'prof', 'fr', 'rev', 'msgr', 'sr', 'jr',
    'hon', 'gen', 'col', 'capt', 'lt', 'sgt', 'gov', 'sen', 'rep', 'pres',
    'no', 'vs', 'etc', 'al', 'inc', 'ltd', 'co', 'corp', 'dept', 'est',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct',
    'nov', 'dec', 'approx', 'ca', 'cf', 'ed', 'eds', 'vol', 'pp', 'fig',
}
_BOUNDARY = re.compile(r'(?<=[.!?])\s+')
# [LOCAL-654] The gpt-4.1-mini narrator routinely drops the space after a
# sentence-ending period: "…venture into its depths.Thousands of copies…",
# "…to complete it.Leonardo prepared…". Every splitter in the pipeline keyed on
# a period FOLLOWED BY WHITESPACE, so the welded pair travelled as one "sentence"
# — and when a later gate dropped the sentence it had cut, the surviving neighbour
# fused mid-clause into "…venture into Thousands…". The boundary is real and the
# splitter must see it: a sentence-ending period/!/? jammed directly against the
# next sentence's capitalised first letter (optionally through a closing quote or
# bracket), with NO space. Guarded below exactly like the whitespace boundary, so
# an initial ("Isabella V.McMullen" is still ONE name), a dotted acronym
# ("U.S.Grant"), a decimal ("3.5"), and a domain ("artic.edu") never split.
#
# The next sentence's first word must be a Capital letter FOLLOWED BY A LOWERCASE
# letter — a real word ("Thousands", "Leonardo", "This", "Au") — so the boundary
# never fires inside a dotted acronym ("U.S.Grant": the "S" is followed by a dot,
# not a lowercase letter) or between two initials. Opening smart/curly quotes are
# allowed before the capital ("imagery.“Au Soleil”").
_NOSPACE_BOUNDARY = re.compile(
    r'(?<=[.!?])(?=["“”‘’\'(\[]?[A-ZÀ-Ý][a-zà-ÿ])')
# A decimal or a run-together domain/path must never be a boundary: the character
# right after the dot being a lowercase letter or a digit means it is not a
# sentence end, which the capital-letter lookahead above already excludes. The
# remaining risk is "No.3" style — handled by the abbreviation guard on the left.
_TRAILING_TOKEN = re.compile(r'([A-Za-z][A-Za-z\'’]*)\.$')


def _ends_on_abbreviation(chunk):
    """True when `chunk` ends with an abbreviation, not a sentence."""
    c = chunk.rstrip()
    if not c.endswith('.'):
        return False
    # A single capital letter + dot is an initial: "J. F. Kennedy".
    if re.search(r'(?:^|\s)[A-Z]\.$', c):
        return True
    # Dotted acronyms: U.S., U.K., D.C., N.Y. — the letter before the final dot is
    # preceded by a dot, not whitespace, so the initial rule above cannot see them.
    if re.search(r'(?:^|\s)(?:[A-Za-z]\.){2,}$', c):
        return True
    # [LOCAL-654] A single capital letter + dot with NO leading space — the
    # no-space boundary can leave "Isabella V." as the chunk tail. Treat it as an
    # initial too, so "Isabella V.McMullen" is never cut between the initial and
    # the surname. (The whitespace path never produces this tail; the no-space
    # path can.)
    if re.search(r'(?:^|[^A-Za-z])[A-Z]\.$', c):
        return True
    # [LOCAL-654] A dotted acronym with no leading space ("U.S.Grant").
    if re.search(r'(?:[^A-Za-z]|^)(?:[A-Za-z]\.){2,}$', c):
        return True
    m = _TRAILING_TOKEN.search(c)
    return bool(m) and m.group(1).lower() in _ABBREV


def _split_keep_boundaries(text):
    """[LOCAL-654] Split on a sentence-ending period/!/? whether or not a space
    follows it. The whitespace case is the historical boundary; the no-space case
    ("depths.Thousands") is the gpt-4.1-mini shape. The abbreviation/initial guard
    in `_ends_on_abbreviation` then re-joins any chunk that ended on an initial,
    acronym or known abbreviation — so a real boundary splits and a false one
    (an initial, a decimal, a domain) does not.
    """
    # First split on whitespace boundaries (unchanged historical behaviour).
    ws_pieces = _BOUNDARY.split(text)
    # Then split each piece again at any no-space boundary.
    pieces = []
    for p in ws_pieces:
        start = 0
        for m in _NOSPACE_BOUNDARY.finditer(p):
            pieces.append(p[start:m.start()])
            start = m.start()
        pieces.append(p[start:])
    return [p for p in pieces if p != '']


def split_sentences(text):
    """Split into sentences, keeping abbreviations attached to what follows."""
    if not text:
        return []
    raw = _split_keep_boundaries(text)
    out = []
    for piece in raw:
        if out and _ends_on_abbreviation(out[-1]):
            # Re-join across a FALSE boundary (an initial, acronym or known
            # abbreviation that is not a sentence end). A single joining space is
            # always the correct spoken form — "Isabella V." + "McMullen" reads as
            # "Isabella V. McMullen" whether the source welded them or not — and it
            # preserves the historical whitespace-path behaviour exactly.
            out[-1] = out[-1].rstrip() + ' ' + piece.lstrip()
        else:
            out.append(piece)
    return [s for s in (p.strip() for p in out) if s]

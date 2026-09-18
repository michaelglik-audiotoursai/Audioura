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
_TRAILING_TOKEN = re.compile(r'([A-Za-z][A-Za-z\'’]*)\.$')


def _ends_on_abbreviation(chunk):
    """True when `chunk` ends with an abbreviation, not a sentence."""
    c = chunk.rstrip()
    if not c.endswith('.'):
        return False
    # A single capital letter + dot is an initial: "J. F. Kennedy".
    if re.search(r'(?:^|\s)[A-Z]\.$', c):
        return True
    m = _TRAILING_TOKEN.search(c)
    return bool(m) and m.group(1).lower() in _ABBREV


def split_sentences(text):
    """Split into sentences, keeping abbreviations attached to what follows."""
    if not text:
        return []
    raw = _BOUNDARY.split(text)
    out = []
    for piece in raw:
        if out and _ends_on_abbreviation(out[-1]):
            out[-1] = out[-1].rstrip() + ' ' + piece
        else:
            out.append(piece)
    return [s for s in (p.strip() for p in out) if s]

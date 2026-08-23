#!/usr/bin/env python3
"""domain_verbs.py — D512: ask the domain what its verbs of making are.

Michael, 2026-08-23:

    "'Add the making verbs' has to be different for each museum type, so maybe in
     addition to the hardcoded set of verbs at the beginning of the tour
     generation we can ask (only once) the verbs from Serper appropriate for the
     museum type."

**The gap, measured on the Moses stop.** `_AGENCY_VERB` has been extended three
times — walking tours (LOCAL-4xx), non-human agents (LOCAL-495), the making verbs
(LOCAL-497) — and each extension was written by hand after a stop scored wrong.
On 2026-08-23 the same hole appeared again:

    Dalí scratched the illustrations onto massive gold plates    -> no action
    Dalí sketched Freud during the meeting                       -> no action
    Salvador Dalí created this oversize suite                    -> no action

`sketched`, `drew`, `painted`, `scratched`, `portrayed` are absent. On an
exhibition ABOUT people making objects, the vocabulary of making is missing —
and the next venue will have a different vocabulary again. A hardcoded list
cannot keep up, and every gap costs a real story.

**So the verbs are DISCOVERED, from the domain's own literature.** One Serper
query per tour, built from the venue and exhibition subject; past-tense verbs are
harvested from the returned text and kept when they are not already known. This
is evidence-based in the same way the rest of the chain is: the verbs a domain
actually uses to describe its own making, rather than a list LEAD imagines.

**Additive only, and that is the safety property.** Discovered verbs are added to
`_AGENCY_VERB`; nothing is ever removed. A bad discovery can make the scanner see
an action that is not there — never blind it to one that is. The failure mode is
a slightly generous classifier, not a lost story.

**Once per tour.** One SERP query, ~$0.001, cached by venue+subject for the
process. The cost of getting this wrong is not money; it is that a verb list
tuned by hand on one exhibition silently fails on the next.
"""
import os
import re
from typing import Dict, List, Optional, Set

from text_fold import fold

__all__ = ['discover_verbs', 'agency_pattern_with', 'DISCOVERY_DISABLED_ENV']

DISCOVERY_DISABLED_ENV = 'DISABLE_VERB_DISCOVERY'
MAX_DISCOVERED = int(os.environ.get('DOMAIN_VERBS_MAX', '25'))
PAGES_TO_FETCH = int(os.environ.get('DOMAIN_VERBS_PAGES', '6'))
MIN_FREQUENCY = int(os.environ.get('DOMAIN_VERBS_MIN_FREQ', '2'))

_CACHE: Dict[str, List[str]] = {}

# A past-tense verb, which is the form a description of making takes.
_PAST_TENSE = re.compile(r'\b([a-z]{3,}(?:ed|ew|ade|ought|aved|ung|ang|ored))\b')

# Words ending -ed that are adjectives or states, not acts. A verb list polluted
# with these makes every descriptive sentence look like an action, which is the
# one way this module could do harm.
_NOT_AN_ACT = {
    'used', 'named', 'called', 'known', 'based', 'related', 'located',
    'situated', 'considered', 'regarded', 'described', 'included', 'limited',
    'detailed', 'coloured', 'colored', 'signed', 'dated', 'titled', 'framed',
    'mounted', 'bound', 'aged', 'faded', 'damaged', 'stained', 'needed',
    'wanted', 'seemed', 'appeared', 'remained', 'stayed', 'lasted', 'lived',
    'owned', 'held', 'featured', 'contained', 'displayed', 'exhibited',
    'shown', 'listed', 'numbered', 'measured', 'weighed', 'priced',
    'estimated', 'expected', 'believed', 'thought', 'said', 'noted',
    'reported', 'added', 'allowed', 'enabled', 'helped', 'served', 'offered',
    'provided', 'presented', 'continued', 'started', 'ended', 'finished',
    'created',  # already present, and too generic to earn a slot
}

# What each category's making looks like, as the query. Deliberately about the
# ACT rather than the object: "how were lithographs made" returns process prose;
# "lithographs" returns catalogue entries.
# [D512 r2] LEAD WITH THE MEDIUM, NOT THE EXHIBITION. Measured on the same day:
#
#   "Picasso, Miró, Dalí: Unbound ... how were the works made"
#        -> 5,793 chars, verbs: shared, emerged          (art-history narrative)
#   "lithograph printmaking process how a lithograph is made stone plate ink"
#        -> 11,132 chars, verbs: applied, transferred, moistened, adhered,
#           invented, worked                             (the actual process)
#
# An exhibition name retrieves that show's marketing pages, which describe what
# is on display rather than how it was made. The MEDIUM retrieves process
# literature, which is where the verbs of making live. The venue is used only
# when no medium is known.
_SUBJECT_BY_CATEGORY = {
    'museum': 'printmaking process how it is made technique step by step',
    'walking': 'construction process how it was built technique',
    'restaurant': 'how the dish is prepared cooking technique',
    'specialized': 'how it is made process technique',
}


def _known_verbs() -> Set[str]:
    """Everything `_AGENCY_VERB` already matches, so discovery only adds."""
    try:
        from story_opportunity_scan import _AGENCY_VERB
        return {fold(w) for w in re.findall(r'[a-z]{3,}', _AGENCY_VERB.pattern)}
    except Exception:
        return set()


def discover_verbs(venue_name: str = '', exhibition: str = '',
                   category: str = 'museum', medium: str = '',
                   verbose: bool = True) -> List[str]:
    """One SERP query; return past-tense verbs this domain uses and we lack.

    Returns [] on any failure — the caller keeps the hardcoded list, which is
    exactly where it was before this module existed.
    """
    if os.environ.get(DISCOVERY_DISABLED_ENV, '').strip() == '1':
        return []
    subject = _SUBJECT_BY_CATEGORY.get((category or '').lower(),
                                       _SUBJECT_BY_CATEGORY['specialized'])
    # Medium first — it is the term that finds process literature. The
    # exhibition or venue is a fallback for a stop whose medium we do not know.
    head = (medium or '').strip() or (exhibition or venue_name or '').strip()
    query = ' '.join(x for x in (head, subject) if x)
    key = fold(query)
    if key in _CACHE:
        return _CACHE[key]

    try:
        from work_story_searcher import _serp_search
        results, _ = _serp_search(query)
    except Exception as e:
        if verbose:
            print(f"  [D512] verb discovery unavailable (non-fatal): {e}")
        _CACHE[key] = []
        return []

    # [D512] FETCH THE PAGES. Eight SERP snippets for this query totalled 1,166
    # characters and yielded four candidate verbs, none twice — the frequency
    # test cannot work on that little text. The same eight pages are ~24,000
    # characters, which is enough for a verb to prove it belongs to the domain
    # rather than to one sentence. D510 built the fetch; this is the second
    # place that needed it.
    try:
        from snippet_ranker import fetch_pages_for_top_snippets
        for r in results or []:
            r.setdefault('url', '')
        fetch_pages_for_top_snippets(results, max_fetches=PAGES_TO_FETCH)
    except Exception:
        pass

    known = _known_verbs()
    counts: Dict[str, int] = {}
    for r in results or []:
        text = (f"{r.get('title','')} {r.get('snippet','')} "
                f"{r.get('fetched_passage','')}")
        for m in _PAST_TENSE.finditer(text.lower()):
            v = m.group(1)
            if v in _NOT_AN_ACT or fold(v) in known or len(v) < 4:
                continue
            counts[v] = counts.get(v, 0) + 1

    # Frequency-ordered, and a verb seen once in eight snippets is noise.
    found = [v for v, n in sorted(counts.items(), key=lambda kv: -kv[1])
             if n >= MIN_FREQUENCY][:MAX_DISCOVERED]
    _CACHE[key] = found
    if verbose:
        print(f"  [D512] verb discovery: query='{query[:64]}' -> "
              f"{len(found)} new verb(s): {', '.join(found[:12]) or 'none'}")
    return found


def agency_pattern_with(extra_verbs: List[str]):
    """`_AGENCY_VERB` widened by the discovered verbs. Never narrowed.

    Returns a compiled pattern; the caller installs it. Additive by construction
    — the original alternation is kept whole and the new verbs are appended, so
    the worst a bad discovery can do is make the scanner slightly generous.
    """
    from story_opportunity_scan import _AGENCY_VERB
    clean = [re.escape(v) for v in (extra_verbs or [])
             if v and re.fullmatch(r'[a-z]{3,}', v)]
    if not clean:
        return _AGENCY_VERB
    base = _AGENCY_VERB.pattern
    if base.endswith(r')\b'):
        widened = base[:-3] + '|' + '|'.join(clean) + r')\b'
    else:
        widened = base + r'|\b(' + '|'.join(clean) + r')\b'
    return re.compile(widened, _AGENCY_VERB.flags)


def install(venue_name: str = '', exhibition: str = '', category: str = 'museum',
            medium: str = '', verbose: bool = True) -> List[str]:
    """Discover, then widen `_AGENCY_VERB` in place for this process.

    Rebinding the module attribute is what makes every consumer see it —
    `material_kind`, `story_opportunity_scan` and `story_replenish` all read it
    through the same module object.
    """
    verbs = discover_verbs(venue_name, exhibition, category, medium, verbose)
    if not verbs:
        return []
    try:
        import story_opportunity_scan as sos
        sos._AGENCY_VERB = agency_pattern_with(verbs)
        import material_kind as mk
        mk._AGENCY_VERB = sos._AGENCY_VERB
        if verbose:
            print(f"  [D512] _AGENCY_VERB widened by {len(verbs)} discovered verb(s)")
    except Exception as e:
        if verbose:
            print(f"  [D512] could not install discovered verbs (non-fatal): {e}")
        return []
    return verbs

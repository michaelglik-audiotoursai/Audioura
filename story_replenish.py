#!/usr/bin/env python3
"""story_replenish.py — LOCAL-489: Michael's step 3.4, "if too small, learn more".

    "4. Getting the right story size: if too small need to learn more from
        Internet."

Production could already SEE thin material — `corpus_coverage.assess_stop_coverage`
has been wired since LOCAL-198 — and could not ACT on it. The corpus gate's only
response to a thin stop is to restrict what the narration may claim. Restricting
is not learning; a stop with two sentences of material stays a stop with two
sentences of material, and the narration is then blamed for being thin.

`story_lab.py` S4 has the missing half. This module is the production form of it.

**COST IS THE WHOLE RISK HERE.** This is the one step on Michael's list that can
spend without bound: a follow-up round that finds nothing can always justify
another. So the caps are structural, not advisory —

  * at most ONE replenishment round per stop, ever;
  * at most `MAX_FOLLOWUP_QUERIES` (3) queries in it;
  * queries already issued are never re-issued;
  * the round is skipped entirely for stops step 2 judged not worth mining.

The queries are built from Michael's matrix, targeting the named agents and the
credit-line facts, because those are what a Fact → Stop → Exhibition chain needs
and what generic title queries reliably fail to return.
"""
import os
import re
from typing import Dict, List, Optional, Set

from text_fold import fold

__all__ = ['needs_replenishment', 'build_followup_queries',
           'MAX_FOLLOWUP_QUERIES', 'THIN_CHAR_FLOOR', 'REPLENISH_DISABLED_ENV']

REPLENISH_DISABLED_ENV = 'DISABLE_STORY_REPLENISH'
MAX_FOLLOWUP_QUERIES = int(os.environ.get('STORY_REPLENISH_QUERIES', '3') or '3')

# `story_lab.py` S4 calls a stop THIN below 1500 chars of passage text, and that
# number came from reading real stops rather than from theory. Kept identical so
# the lab and production answer the same question the same way — the lab/prod
# divergence is D472's whole subject and is not worth widening for a constant.
THIN_CHAR_FLOOR = int(os.environ.get('STORY_THIN_FLOOR', '1500') or '1500')


def needs_replenishment(passages: List[str], coverage: Optional[Dict] = None) -> Dict:
    """Is there too little here to write a story from?

    Two independent reasons, reported separately so the log says which fired:
      * `thin`      — not enough text, by character count;
      * `uncovered` — the corpus does not mention the stop's own subject
                      (`assess_stop_coverage` verdict of EMPTY or VENUE_ONLY).

    A stop can be verbose and uncovered, or brief and on-topic. Both need more.
    """
    texts = [p for p in (passages or []) if p]
    total = sum(len(p) for p in texts)
    thin = total < THIN_CHAR_FLOOR
    verdict = (coverage or {}).get('verdict')
    uncovered = verdict in ('EMPTY', 'VENUE_ONLY')
    return {'needs_more': bool(thin or uncovered),
            'thin': thin, 'uncovered': uncovered,
            'total_chars': total, 'passage_count': len(texts),
            'verdict': verdict or 'UNKNOWN'}


def _clean(value: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', (value or '')).strip()


def build_followup_queries(matrix: Dict,
                           already_issued: Optional[Set[str]] = None,
                           cap: int = None) -> List[str]:
    """Targeted queries aimed at the FACTS, not at the title again.

    The first round has already searched the title and come back thin; asking it
    a fourth way will not help. What is missing is the chain — who made it, who
    printed it, who paid for it, and what happened between them. So each query
    pairs a NAMED AGENT from the matrix with the work, which is the shape that
    returns collaboration and commission material.

    Never re-issues a query from `already_issued` (folded comparison, so an
    accent or a capital does not smuggle a duplicate through — D243).
    """
    cap = MAX_FOLLOWUP_QUERIES if cap is None else cap
    issued = {fold(q) for q in (already_issued or set())}

    title = _clean(matrix.get('english_title') or matrix.get('canonical_title'))
    artist = _clean(matrix.get('artist'))
    publisher = _clean(matrix.get('publisher'))
    printer = _clean(matrix.get('printed_by') or matrix.get('printer'))
    credit = _clean(matrix.get('credit_line'))
    venue = _clean(matrix.get('venue_name'))

    candidates: List[str] = []

    # An agent PLUS the work is the collaboration question.
    for agent in (publisher, printer):
        if agent and title:
            candidates.append(f'"{agent}" "{title}" history')
    # The artist and the agent together is the relationship question — the one
    # that produces "Broder spent three years persuading Miró".
    if artist and publisher:
        candidates.append(f'"{artist}" "{publisher}" collaboration')
    if artist and printer and printer != publisher:
        candidates.append(f'"{artist}" "{printer}" printed')
    # A donor named in the credit line is a person with a reason.
    if credit and len(credit) > 12:
        donor = re.sub(r'^(gift|bequest|loan)\s+of\s+', '', credit, flags=re.I)
        donor = donor.split(',')[0].strip()
        if donor and len(donor) > 4 and title:
            candidates.append(f'"{donor}" "{title}" collection')
    # Last resort: the work in its venue, which at least scopes the search.
    if title and venue:
        candidates.append(f'"{title}" "{venue}" provenance')

    out: List[str] = []
    seen: Set[str] = set()
    for q in candidates:
        key = fold(q)
        if not key or key in issued or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= cap:
            break
    return out

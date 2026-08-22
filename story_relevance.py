#!/usr/bin/env python3
"""story_relevance.py — D505: is this retrieved sentence ABOUT this stop?

The D504 experiment produced, for the query `Juan Gris "Au Soleil du Plafond"
destroyed`:

    "Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine."

`material_kind` scored it **eventful** — correctly, on its own terms. Something
certainly happens in that sentence. It simply has nothing to do with Juan Gris,
Pierre Reverdy, or a livre d'artiste published in 1955.

**The gap this closes.** Every instrument in the chain judges a sentence on its
SHAPE — does it have an agent, an action, something at stake — and none asks
whether it is about the object the listener is standing in front of. Event-shaped
queries make that gap load-bearing, because the event term does the pulling: ask
for "destroyed" and you will get destruction, of something, somewhere.

**Why not reuse `_snippet_is_title_relevant` from `snippet_ranker`.** That works
on a whole snippet dict and asks whether it is worth INJECTING. This asks a
narrower question of a single SENTENCE that has already been picked as the best
one: is the thing that happens here happening to US? A snippet can be relevant
overall and its most dramatic sentence be about something else entirely, which is
exactly the Szampanier case — that snippet came from a page that does mention
Gris.

**The bar is deliberately generous.** A sentence earns relevance by naming ANY of
the stop's own entities, or a date inside the work's lifetime when the subject is
already established nearby. Retrieval is scarce (D492); the cost of a wrong
`irrelevant` is a real story discarded, and the cost of a wrong `relevant` is one
weak sentence competing against others. Asymmetric, so it errs toward keeping.
"""
import re
from typing import Dict, List, Optional, Set

from text_fold import fold, is_placeholder

__all__ = ['relevance_of', 'filter_relevant', 'stop_entities', 'RELEVANT',
           'WEAK', 'IRRELEVANT']

RELEVANT = 'relevant'
WEAK = 'weak'
IRRELEVANT = 'irrelevant'

_STOP_TOKENS = {
    'the', 'and', 'for', 'with', 'from', 'des', 'les', 'del', 'aux', 'sur',
    'dans', 'une', 'que', 'qui', 'por', 'con', 'para', 'nel', 'dei', 'this',
    'that', 'was', 'were', 'his', 'her', 'its', 'their', 'been', 'have',
}


def stop_entities(matrix: Dict, extra: Optional[List[str]] = None) -> Set[str]:
    """Every name this stop legitimately belongs to, folded.

    Built from the matrix rather than from the prose, so it cannot drift with
    whatever the generator happened to write.
    """
    out: Set[str] = set()
    for key in ('artist', 'publisher', 'printed_by', 'printer', 'credit_line',
                'canonical_title', 'english_title', 'provenance'):
        value = (matrix.get(key) or '').strip()
        if not value or is_placeholder(value):
            continue
        # Whole value, plus each capitalised span inside it — a credit line
        # carries the donor, a provenance line carries several parties.
        out.add(fold(value))
        for m in re.finditer(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*",
                             value):
            span = fold(m.group(0))
            if len(span) > 3:
                out.add(span)
    for e in (extra or []):
        if e:
            out.add(fold(e))
    # Individual surnames: retrieval says "Gris", the matrix says "Juan Gris".
    for name in list(out):
        parts = [p for p in name.split() if len(p) > 3 and p not in _STOP_TOKENS]
        if 1 < len(parts) <= 4:
            out.update(parts)
    return {o for o in out if len(o) > 3}


def _title_tokens(matrix: Dict) -> Set[str]:
    title = fold(matrix.get('canonical_title') or '')
    return {t for t in re.findall(r'\w{4,}', title) if t not in _STOP_TOKENS}


def relevance_of(sentence: str, matrix: Dict, context: str = '',
                 extra_entities: Optional[List[str]] = None) -> Dict:
    """Is this sentence about this stop? -> {'verdict', 'why', 'hits'}

    `context` is the surrounding snippet. A sentence may carry a pronoun subject
    whose antecedent is in the previous sentence — "When the artist died the
    following year, the lithographs remained unfinished" names nobody at all and
    is one of the best sentences retrieval returned. So a sentence with no
    entity of its own inherits WEAK relevance if its snippet establishes one.
    """
    if not sentence:
        return {'verdict': IRRELEVANT, 'why': 'empty', 'hits': []}

    ents = stop_entities(matrix, extra_entities)
    folded = fold(sentence)
    hits = sorted({e for e in ents if e and e in folded}, key=len, reverse=True)

    if hits:
        return {'verdict': RELEVANT,
                'why': f'names {", ".join(hits[:3])}', 'hits': hits[:5]}

    # Title tokens are a weaker signal than a person — a work title can be
    # generic ("Moses") and match an unrelated object, which is precisely how
    # D501's false object-record match happened.
    t_hits = _title_tokens(matrix) & set(re.findall(r'\w{4,}', folded))
    if len(t_hits) >= 2:
        return {'verdict': RELEVANT,
                'why': f'title tokens {", ".join(sorted(t_hits)[:3])}',
                'hits': sorted(t_hits)}

    # A sentence that names SOMEBODY ELSE is not anaphoric — it is about them.
    #
    # Measured: "Dora Szampanier, Etching of destroyed synagogue - Drohobisz,
    # Ukraine." sat in an SEO aggregator snippet that also read "Juan Gris, The
    # Pipe, from Au Soleil du Plafond, 1955 ... Related Searches." The snippet
    # genuinely mentions the work, so the anaphora rescue below kept the
    # synagogue line as WEAK — the exact sentence this gate was built to reject,
    # surviving the gate built to reject it.
    #
    # The discriminator is a COMPETING proper noun. "When the artist died the
    # following year..." names nobody and is genuinely anaphoric; "Dora
    # Szampanier, Etching of..." names a person who is not ours.
    competing = []
    for m in re.finditer(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]{2,}(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*",
                         sentence):
        span = fold(m.group(0))
        if len(span) < 4 or span in _STOP_TOKENS:
            continue
        if any(span in e or e in span for e in ents):
            continue
        if span in _title_tokens(matrix):
            continue
        competing.append(m.group(0))

    if context and not competing:
        ctx = fold(context)
        ctx_hits = sorted({e for e in ents if e and e in ctx}, key=len, reverse=True)
        if ctx_hits:
            # The sentence is anaphoric and its snippet is on-topic. Kept, but
            # marked WEAK: the antecedent is assumed, not proven.
            return {'verdict': WEAK,
                    'why': f'no entity of its own; snippet names {ctx_hits[0]}',
                    'hits': ctx_hits[:3]}

    if len(t_hits) == 1:
        return {'verdict': WEAK, 'why': f'one title token ({list(t_hits)[0]})',
                'hits': list(t_hits)}

    if competing:
        return {'verdict': IRRELEVANT,
                'why': f'about someone else ({competing[0]}), not this stop',
                'hits': []}
    return {'verdict': IRRELEVANT,
            'why': 'names nothing belonging to this stop', 'hits': []}


def filter_relevant(sentences: List[str], matrix: Dict, context: str = '',
                    keep_weak: bool = True,
                    extra_entities: Optional[List[str]] = None) -> List[Dict]:
    """Judge every sentence. Returns each with its verdict, nothing dropped.

    Dropping silently is what made D423's false zero possible — the caller must
    be able to see what was rejected and why.
    """
    out = []
    for s in sentences:
        r = relevance_of(s, matrix, context, extra_entities)
        r['sentence'] = s
        r['kept'] = (r['verdict'] == RELEVANT
                     or (keep_weak and r['verdict'] == WEAK))
        out.append(r)
    return out

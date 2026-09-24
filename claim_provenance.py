#!/usr/bin/env python3
"""claim_provenance.py — LOCAL-543: where did each sentence of the tour come from?

**The incident.** `TOURS_FOR_REVIEW/round9/CHURCH_1_evidence.json` is 379 bytes.
For all four stops it says the same thing:

    { "Nave": { "status": "UNVERIFIED", "reason": "not in discovered landmarks" }, ... }

That is the entire evidentiary record behind a tour whose stop-1 narrative asserts,
in a confident voice, that Mother Teresa visited this church in June 1995 and healed
a paralyzed parishioner. The pipeline had no source for that sentence — and the file
that is supposed to be the evidence records only *landmark discovery status*. It does
not record where a single sentence of the narrative came from.

**What this module answers.** Not "is this sentence TRUE" — that is grounding, it
costs $0.035 a request (LOCAL-533), and it is a different, more expensive question.
This answers the cheaper and prior one: **did we have ANY source for this sentence,
or did the model just say it?** Three provenance classes:

    corpus      the sentence's content is carried by a retrieved passage that has a
                real source (a URL or a document id) — a snippet, a corpus passage,
                a documented stop-record field (`provenance_gloss` names).
    grounded    the sentence is backed by a grounded response's `groundingMetadata`
                — Gemini told us which source sentence it came from
                (`story_leads.gemini_with_sources`).
    parametric  NOTHING. No passage, no grounded source. The model asserted it from
                its own memory. This is the class that matters and it is currently
                invisible.

**The plumbing already half-exists.** `story_leads.gemini_with_sources` already
returns per-sentence sources (`supports`), and the generation path already collects
retrieval snippets per stop (`_DIRECT_SNIPPETS_PER_STOP`). Both carry a source URL
or id and both are DISCARDED before anything counts them. This module reads that
pool when it is handed one, and when it is not — auditing a saved tour file with no
pool — every factual sentence is `parametric`, which is the honest reading of a tour
whose only surviving evidence is a 379-byte "UNVERIFIED" record.

**It measures. It does not change generation.** A tour full of unsourced sentences
is a finding on its own, whether or not each one turns out to be true. "38 of 41
factual sentences have no source" is a valuable result and an acceptable one; nothing
here is tuned to make the number look better.

Deterministic and free: no API call, no search, no network.
"""
import re
from typing import Dict, List, Optional, Any

from sentence_split import split_sentences
from text_fold import fold


__all__ = [
    'CORPUS', 'GROUNDED', 'PARAMETRIC',
    'SourcePool', 'classify_sentence', 'factual_sentences', 'audit_tour',
]

CORPUS = 'corpus'
GROUNDED = 'grounded'
PARAMETRIC = 'parametric'


# ── which lines are NARRATIVE and which are scaffolding ──────────────────────
# A tour file is stop headers, labelled metadata fields, an orientation lead-in,
# a directional paragraph, then the narrative. Only the narrative makes factual
# CLAIMS about the world; the rest is address/coordinates/navigation, which is not
# a claim about history and must not be counted as sourced-or-not.
_STOP_HDR = re.compile(r'^Stop\s+\d+:', re.I)
_FIELD_LINE = re.compile(
    r'^(?:Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Directions|Tour-Category|Orientation)\s*:', re.I)
# The trailing recap ("That's N stops — ...") is a summary of the itinerary, not a
# fresh factual claim, and the offsite-entity check (LOCAL-539) already owns it.
_EPILOG_LINE = re.compile(r"^That'?s\s+\d+\s+stops?\b", re.I)
# A title line at the very top of the file.
_TITLE_LINE = re.compile(r'^Step-by-Step Audio Guided Tour:', re.I)

# Navigation sentences carry no factual claim even when they sit inside a narrative
# paragraph: "As you exit the Nave, head towards the altar." A sentence that is
# almost entirely movement verbs and direction words is scaffolding, not a claim.
_NAV_CUE = re.compile(
    r'\b(?:exit|head|walk|turn|continue|proceed|stroll|make your way|'
    r'step (?:into|inside)|as you (?:enter|exit|leave|stand|move|approach)|'
    r'take your time|pause|glance|look up|notice the|straight ahead|'
    r'towards the|down the|left onto|right onto|to your (?:left|right))\b', re.I)

# A sentence needs some factual payload to be a "claim" worth sourcing: a year, a
# proper noun, a number, or a date word. A pure exhortation ("Absorb the beauty of
# this sacred space.") asserts nothing checkable and is not counted.
_YEAR = re.compile(r'\b(?:1[5-9]\d\d|20\d\d)\b')
_PROPER = re.compile(r'\b[A-Z][a-z]{2,}')
_NUMBER = re.compile(r'\b\d+\b')
_MONTH = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December)\b', re.I)

# Second-person address is the mark of a navigation/orientation sentence spoken to
# the listener rather than a claim about the world.
_SECOND_PERSON = re.compile(r'\b(?:you|your|you\'ll|you\'re)\b', re.I)

# Meta-narration ABOUT THE TOUR ITSELF, not about the world: "you are about to
# embark on a walking journey", "you'll explore the craftsmanship", "you will learn
# about the collaboration", "your first stop is Nave", "as you continue the tour".
# These assert nothing that has an external source — they describe the walk. A
# named entity inside one ("through Our Lady Help of Christians") is the venue name,
# not a historical claim, so proper-noun payload must not rescue them.
_TOUR_META = re.compile(
    r'\b(?:about to embark|you\'?ll explore|you will explore|you\'?ll learn|'
    r'you will learn|your (?:first|next|final|last) stop is|as you continue|'
    r'continue the tour|on (?:this|our|a) (?:walking|guided) (?:tour|journey)|'
    r'as you (?:move|walk) (?:forward|on)|consider the layered)\b', re.I)


def _is_navigation(sentence: str) -> bool:
    """A movement/orientation instruction or tour meta-narration — not a factual
    claim about the world."""
    s = sentence.strip()
    if not s:
        return True
    has_time = bool(_YEAR.search(s) or _MONTH.search(s))
    if has_time:
        return False                      # a dated sentence is a claim, never nav
    # Tour meta-narration ("you'll explore...", "your first stop is...") asserts
    # nothing sourceable regardless of the venue name it contains.
    if _TOUR_META.search(s):
        return True
    # Movement instructions addressed to the listener.
    nav_hits = len(_NAV_CUE.findall(s))
    if nav_hits >= 1 and _SECOND_PERSON.search(s):
        return True
    return False


def _has_factual_payload(sentence: str) -> bool:
    """True if the sentence asserts something checkable — a date, a named entity,
    or a number. Pure mood/instruction sentences assert nothing to source."""
    s = sentence.strip()
    if len(s.split()) < 5:
        return False
    if _YEAR.search(s) or _MONTH.search(s):
        return True
    # A proper noun that is not merely the sentence's first word. "The nave's
    # architecture..." has a capital only at position 0 — no named entity.
    for m in _PROPER.finditer(s):
        if m.start() != 0:
            return True
    # A bare number with a unit-ish neighbour ("850 parishioners", "50th").
    if _NUMBER.search(s):
        return True
    return False


def factual_sentences(text: str) -> List[Dict[str, str]]:
    """Split a tour into factual narrative sentences, tagged with their stop.

    Returns [{'stop': str, 'text': str}, ...] in document order. Field lines,
    directions, orientation lead-ins, the title and the epilog recap are excluded;
    so are pure navigation and pure mood sentences inside narrative paragraphs.
    """
    out: List[Dict[str, str]] = []
    cur_stop = ''
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _STOP_HDR.match(line)
        if m:
            # "Stop 1: Nave" -> stop name is the tail after the colon.
            cur_stop = line.split(':', 1)[1].strip()
            continue
        if _TITLE_LINE.match(line) or _EPILOG_LINE.match(line):
            continue
        if _FIELD_LINE.match(line):
            # An Orientation line carries its narrative on the SAME physical line
            # after the label. Keep that tail; drop the label and other fields.
            if re.match(r'^Orientation\s*:', line, re.I):
                line = line.split(':', 1)[1].strip()
                if not line:
                    continue
            else:
                continue
        for sent in split_sentences(line):
            s = sent.strip()
            if not s:
                continue
            if _is_navigation(s):
                continue
            if not _has_factual_payload(s):
                continue
            out.append({'stop': cur_stop, 'text': s})
    return out


# ── the source pool ──────────────────────────────────────────────────────────

def _source_is_real(rec: Dict[str, Any]) -> Optional[str]:
    """Return a source identifier (URL or document id) for a pool record, or None.

    A snippet whose only 'source' is an INTERNAL rationale (e.g.
    'replenishment_rationale' — the pipeline's own note on why it picked a stop) is
    NOT an external source and does not count as provenance. A real URL, a domain,
    or a document id does.
    """
    if not isinstance(rec, dict):
        return None
    for key in ('url', 'link', 'uri'):
        v = rec.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    for key in ('domain', 'source_url', 'document_id', 'doc_id'):
        v = rec.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    src = rec.get('source')
    if src and isinstance(src, str) and src.strip():
        # Internal, non-source markers do not confer provenance.
        if src.strip().lower() in _INTERNAL_SOURCE_MARKERS:
            return None
        return src.strip()
    return None


_INTERNAL_SOURCE_MARKERS = {
    'replenishment_rationale', 'rationale', 'internal', 'model', 'parametric',
    'generated', 'llm', 'fallback',
}

# Content-word overlap threshold: a pool passage "carries" a sentence when it shares
# this fraction of the sentence's distinctive content words. Set from the same
# principle story_leads._carries uses — a single sentence must carry the claim, not
# scattered words across unrelated results.
_OVERLAP = 0.6
_STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'on', 'at', 'by',
    'for', 'with', 'as', 'is', 'was', 'were', 'are', 'be', 'been', 'this',
    'that', 'these', 'those', 'it', 'its', 'their', 'his', 'her', 'they',
    'you', 'your', 'here', 'there', 'from', 'into', 'over', 'under', 'about',
    'which', 'who', 'whom', 'whose', 'when', 'where', 'while', 'has', 'have',
    'had', 'not', 'no', 'also', 'more', 'most', 'some', 'such', 'than', 'then',
}


def _content_words(sentence: str) -> set:
    return {w for w in re.findall(r"[a-z0-9à-ÿ]{3,}", fold(sentence))
            if w not in _STOP_WORDS}


def _passage_carries(sentence: str, passage: str) -> bool:
    """True if `passage` shares enough distinctive content with `sentence` to be
    plausibly its source. Overlap on the sentence's own content words (so a long
    passage is not penalised for its extra material)."""
    sw = _content_words(sentence)
    if len(sw) < 3:
        return False
    pw = _content_words(passage)
    if not pw:
        return False
    shared = len(sw & pw)
    return (shared / len(sw)) >= _OVERLAP


class SourcePool:
    """The pool of everything the pipeline retrieved for a tour, keyed by stop.

    Built from what the generation path ALREADY collects and discards:

        snippets_per_stop   {stop_name: [ {snippet/text, link/url/domain/source} ]}
                            the retrieval snippets (`_DIRECT_SNIPPETS_PER_STOP`).
        grounded_supports   [ {'text': source_sentence, 'sources': [{domain,url}]} ]
                            per-sentence attribution from a grounded response
                            (`story_leads.gemini_with_sources`  -> out['supports']).
        provenance_names    {stop_name: [names]}  documented stop-record names
                            (`provenance_gloss.provenance_names`) — a name from the
                            museum's own record IS its source (LOCAL-494).

    When the pool is empty (auditing a saved tour with nothing captured), every
    factual sentence classifies as `parametric`.
    """

    def __init__(self,
                 snippets_per_stop: Optional[Dict[str, List[Dict]]] = None,
                 grounded_supports: Optional[List[Dict]] = None,
                 provenance_names: Optional[Dict[str, List[str]]] = None):
        self.snippets_per_stop = snippets_per_stop or {}
        self.grounded_supports = grounded_supports or []
        self.provenance_names = provenance_names or {}
        # Pre-fold grounded support passages once.
        self._grounded = []
        for sup in self.grounded_supports:
            txt = (sup.get('text') or '').strip()
            srcs = [s for s in (sup.get('sources') or []) if s]
            if txt and srcs:
                self._grounded.append((txt, srcs))

    def _stop_snippets(self, stop: str) -> List[Dict]:
        # Try the stop name and the "__stop_N__" positional fallback the pipeline
        # also uses; when neither is present, allow a global scan across all stops
        # (retrieval is often keyed loosely).
        recs = list(self.snippets_per_stop.get(stop, []) or [])
        return recs

    def classify(self, sentence: str, stop: str = '') -> Dict[str, Any]:
        """Classify one sentence. Returns {'class', 'source', 'evidence'}.

        Order of precedence: grounded (engine-attributed, strongest) → corpus
        (a retrieved passage with a real source) → parametric (nothing).
        """
        # 1) grounded: a grounded-response support sentence carries this claim.
        for txt, srcs in self._grounded:
            if _passage_carries(sentence, txt):
                src = srcs[0]
                ident = src.get('url') or src.get('domain') or 'grounded'
                return {'class': GROUNDED, 'source': ident,
                        'evidence': txt[:200]}

        # 2) corpus: a retrieved snippet with a real source carries this claim.
        #    Prefer the sentence's own stop, then any stop (retrieval keys drift).
        candidates = self._stop_snippets(stop)
        scanned_all = False
        if not candidates:
            candidates = [r for recs in self.snippets_per_stop.values() for r in recs]
            scanned_all = True
        for rec in candidates:
            passage = (rec.get('snippet') or rec.get('text') or '').strip()
            if not passage:
                continue
            ident = _source_is_real(rec)
            if not ident:
                continue
            if _passage_carries(sentence, passage):
                return {'class': CORPUS, 'source': ident,
                        'evidence': passage[:200]}
        # If the stop had no snippets we scanned all; nothing matched.
        _ = scanned_all

        # 3) corpus via documented record name: a provenance name in the sentence.
        names = []
        if stop:
            names += self.provenance_names.get(stop, []) or []
        # Also allow any documented name in the tour to vouch for a sentence that
        # mentions it (a credit-line donor named in the prose).
        for recs in self.provenance_names.values():
            names += recs or []
        folded = fold(sentence)
        for name in names:
            if not name:
                continue
            nf = fold(name)
            toks = [t for t in nf.split() if len(t) > 2]
            if toks and all(t in folded for t in toks):
                return {'class': CORPUS, 'source': f'record:{name}',
                        'evidence': f'documented in stop record as "{name}"'}

        # 4) nothing carried it — the model said it from memory.
        return {'class': PARAMETRIC, 'source': None, 'evidence': None}


def classify_sentence(sentence: str, pool: Optional[SourcePool] = None,
                      stop: str = '') -> Dict[str, Any]:
    """Classify a single sentence against a pool (or an empty pool)."""
    pool = pool or SourcePool()
    return pool.classify(sentence, stop)


def audit_tour(text: str, pool: Optional[SourcePool] = None) -> Dict[str, Any]:
    """Full per-claim provenance audit of a tour.

    Returns:
        {
          'counts': {'sourced': int, 'unsourced': int, 'total': int,
                     'corpus': int, 'grounded': int, 'parametric': int},
          'per_stop': {stop: {'sourced': int, 'unsourced': int, 'total': int}},
          'claims': [ {'stop', 'text', 'class', 'source', 'evidence'}, ... ],
        }

    'sourced' = corpus + grounded; 'unsourced' = parametric.
    """
    pool = pool or SourcePool()
    claims: List[Dict[str, Any]] = []
    counts = {'sourced': 0, 'unsourced': 0, 'total': 0,
              CORPUS: 0, GROUNDED: 0, PARAMETRIC: 0}
    per_stop: Dict[str, Dict[str, int]] = {}

    for fs in factual_sentences(text):
        res = pool.classify(fs['text'], fs['stop'])
        cls = res['class']
        rec = {'stop': fs['stop'], 'text': fs['text'], 'class': cls,
               'source': res['source'], 'evidence': res['evidence']}
        claims.append(rec)
        counts['total'] += 1
        counts[cls] += 1
        if cls == PARAMETRIC:
            counts['unsourced'] += 1
        else:
            counts['sourced'] += 1
        ps = per_stop.setdefault(fs['stop'], {'sourced': 0, 'unsourced': 0, 'total': 0})
        ps['total'] += 1
        ps['unsourced' if cls == PARAMETRIC else 'sourced'] += 1

    return {'counts': counts, 'per_stop': per_stop, 'claims': claims}


def summary_line(audit: Dict[str, Any]) -> str:
    """One line for the cost-line block: 'Provenance:  38 of 41 factual sentences
    have NO source (3 corpus, 0 grounded, 38 parametric)'."""
    c = audit['counts']
    return (f"{c['unsourced']} of {c['total']} factual sentences have NO source "
            f"({c[CORPUS]} corpus, {c[GROUNDED]} grounded, {c[PARAMETRIC]} parametric)")


def _main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('tour', help='path to a tour .txt file to audit (offline)')
    ap.add_argument('--json', dest='as_json', action='store_true')
    a = ap.parse_args()
    with open(a.tour, errors='ignore') as fh:
        text = fh.read()
    audit = audit_tour(text)          # offline: empty pool, honest reading
    if a.as_json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return
    c = audit['counts']
    print(f"\n{'=' * 72}")
    print(f"  CLAIM PROVENANCE — {a.tour}")
    print(f"{'=' * 72}")
    print(f"  {summary_line(audit)}")
    print(f"  {'-' * 68}")
    for cl in audit['claims']:
        mark = {'corpus': 'CORP', 'grounded': 'GRND', 'parametric': 'NONE'}[cl['class']]
        print(f"  [{mark}] ({cl['stop'][:18]:18}) {cl['text'][:70]}")
    print(f"{'=' * 72}\n")


if __name__ == '__main__':
    _main()

#!/usr/bin/env python3
"""story_query.py — D507: one question, two encodings.

Michael's query, D366 (2026-08-11):

    "What story can be told to visitors of {exhibition} about {work},
     {credit_line}?"

**LOCAL-423 implemented it as keywords and lost the question.** The code at
`work_story_searcher.py:558` emits

    "{title}" {artist} story visitors {exhibition_name}

— the words `story` and `visitors` survive as bare search terms, the question
form is gone, and `credit_line`, which Michael named explicitly, is not in that
query at all. The comment above the line states his sentence verbatim; the line
does something else. D483's class again.

**And the question cannot simply be pasted into Serper.** Measured 2026-08-22:

    question sent verbatim to Serper   -> 8 results, 7 sentences past the
                                          relevance gate, ZERO eventful
    compiled keyword form              -> eventful, incl. "Gris died in 1927,
                                          having finished only half of the
                                          intended [work]"

Google tokenises "What story can be told to visitors of" and the framing dilutes
the entities that identify a narrative document. Gemini, asked the same words,
returns the whole Gris/Reverdy/Tériade story.

**So the question is the SPECIFICATION and each engine gets its own encoding.**

  GEMINI  the question verbatim, with the matrix attached. It is a prompt.
  SERPER  three parts and no framing words:
            1. the work, quoted, without our English gloss
            2. the NAMED AGENTS — a catalogue entry names one person, an
               article about a collaboration names two, so an agent pair is
               what separates narrative sources from listings
            3. ONE interrogative — `why`, plus a year when known.
               NOT `history`: measured, it returns catalogue prose on both
               stops tested (`active`, never `eventful`).

Measured per-shape yields are in D507; the winner on consistency was
work + agents + `why` + year.
"""
import re
from typing import Dict, List, Optional

from text_fold import fold, is_placeholder

__all__ = ['compile_for_serper', 'compile_for_gemini', 'compile_for_seed',
           'agents_of', 'GEMINI_TEMPLATE']

GEMINI_TEMPLATE = (
    'What story can be told to visitors of {exhibition} about {work}'
    '{credit}?')

# Words that are capitalised in a credit_line without naming anybody.
_NOT_AN_AGENT = {
    'gift', 'bequest', 'loan', 'promised', 'collection', 'fund', 'museum',
    'gallery', 'boston', 'paris', 'york', 'the', 'and', 'of', 'illustrated',
    'book', 'lithographs', 'edition', 'not', 'specified', 'french', 'spanish',
    'surrealism', 'artists', 'rights', 'society',
}


def agents_of(matrix: Dict, credit_line_seed: str = '',
              limit: int = 3) -> List[str]:
    """The named people this query should pair, most identifying first.

    Order matters because the query is truncated at `limit`: the collaborator
    and the printer discriminate far better than the artist, whose name appears
    on every listing of every work they ever made.
    """
    out: List[str] = []

    def add(v):
        v = re.sub(r'\s+', ' ', (v or '')).strip(' .,;')
        if not v or is_placeholder(v):
            return
        # Surname only for multi-token names — retrieval says "Gris", the
        # matrix says "Juan Gris", and the shorter form matches both.
        tokens = [t for t in v.split() if fold(t) not in _NOT_AN_AGENT]
        if not tokens:
            return
        name = tokens[-1] if len(tokens) > 1 and len(tokens[-1]) > 3 else ' '.join(tokens)
        if len(name) < 3:
            return
        if not any(fold(name) == fold(o) for o in out):
            out.append(name)

    # Distinguishing agents first, artist last.
    add(matrix.get('collaborator'))
    add(matrix.get('printed_by') or matrix.get('printer'))
    add(matrix.get('publisher'))
    credit = matrix.get('credit_line') or ''
    donor = re.sub(r'^(gift|bequest|loan|promised gift)\s+of\s+', '', credit,
                   flags=re.IGNORECASE).split('.')[0].split(',')[0]
    add(donor)
    # Anyone named in the credit_line seed itself — that is what this query is
    # about, so a person appearing only there still belongs in it.
    for m in re.finditer(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)+",
                         credit_line_seed or ''):
        add(m.group(0))
    add(matrix.get('artist'))
    return out[:limit]


def _bare_title(matrix: Dict) -> str:
    """The work's own title, without the English gloss we added ourselves."""
    title = (matrix.get('canonical_title') or '').strip()
    return re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip() or title


def _year_of(matrix: Dict) -> str:
    for key in ('publication_year', 'medium', 'credit_line', 'provenance',
                'record_description'):
        m = re.search(r'\b(1[4-9]\d{2}|20[0-2]\d)\b', matrix.get(key, '') or '')
        if m:
            return m.group(1)
    return ''


def compile_for_serper(matrix: Dict, credit_line_seed: str = '',
                       interrogative: str = 'why') -> str:
    """Michael's question, encoded as keywords Google can act on.

    NO framing words. `story` and `visitors` are dropped deliberately — they are
    the fragment of LOCAL-423 that survived as literal keywords, and the shape
    carrying them returned `inert` on stop 1 in the 2026-08-22 measurement.
    """
    parts: List[str] = []
    title = _bare_title(matrix)
    if title:
        parts.append(f'"{title}"')
    parts.extend(agents_of(matrix, credit_line_seed))
    if interrogative:
        parts.append(interrogative)
    year = _year_of(matrix)
    if year:
        parts.append(year)
    # Distinctive content words from the credit_line seed that are not already
    # present — the seed is what makes this query different from its neighbours.
    have = fold(' '.join(parts))
    # Tokens that are part of a NAME in the seed. `agents_of` reduces "Pierre
    # Reverdy" to the surname, so "pierre" is not a substring of any query part
    # and slipped through as a content word — adding nothing beside "Reverdy"
    # and eating a slot.
    name_tokens = {fold(t) for m in re.finditer(
        r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*",
        credit_line_seed or '') for t in m.group(0).split()}
    for w in re.findall(r"[a-zà-ÿ'’\-]{5,}", (credit_line_seed or '').lower()):
        if fold(w) in name_tokens:
            continue
        if len(parts) >= 8:
            break
        # Skip fragments of a name already in the query — "pierre" adds
        # nothing beside "Reverdy" and eats a slot.
        if fold(w) in have or fold(w) in _NOT_AN_AGENT:
            continue
        if any(fold(w) in fold(p) or fold(p) in fold(w) for p in parts if p):
            continue
        parts.append(w)
        have += ' ' + fold(w)
    return ' '.join(parts)


def compile_for_gemini(matrix: Dict, credit_line_seed: str = '',
                       exhibition: str = '') -> str:
    """Michael's question, verbatim. This one is a prompt, not a search string."""
    credit = (credit_line_seed or '').strip().rstrip('.?')
    return GEMINI_TEMPLATE.format(
        exhibition=exhibition or 'this exhibition',
        work=_bare_title(matrix),
        credit=f', {credit}' if credit else '')


def compile_for_seed(seed: Dict, matrix: Dict, exhibition: str = '') -> str:
    """[LOCAL-468] The question that makes each seed produce a DIFFERENT story.

    Before: "What story about {work}, {seed}?" — the work is the subject and
    the seed is a trailing comma-appendage that every model ignores.

    After: seed['ask'] IS the question. The work is context, not subject.
    Agent seeds get only their own role field, not the entire matrix.
    """
    # [D527] `ask` is only a retrieval question for MATRIX AGENTS. `_agent_seeds`
    # writes "What did Mourlot actually do, and what came of it?" — a question a
    # search model can answer. `seeds_for_stop` writes something else entirely:
    #
    #     'What did {subj} actually DO that would justify "{phrase}"?
    #      If nothing, cut the phrase.'
    #
    # That is an AUDIT question. It asks whether our own prose survives scrutiny,
    # and its last clause is an instruction to a checklist — meaningless to a
    # search model, and an open invitation to answer "nothing". Sending it to
    # Gemini as the retrieval query was a scope error in LOCAL-468: it read
    # `seed['ask']` for every seed kind because agent seeds happened to be the
    # case in front of it.
    #
    # Prose seeds therefore keep the question they had before LOCAL-468 — the
    # story-seeking one, with the phrase as the credit anchor. Nothing else about
    # the prose path changed, so this restores it exactly.
    seed_ask = seed.get('ask') if seed.get('kind') == 'matrix_agent' else ''
    if not seed_ask:
        credit = (seed.get('seed') or '').strip().rstrip('.?')
        seed_ask = GEMINI_TEMPLATE.format(
            exhibition=exhibition or 'this exhibition',
            work=_bare_title(matrix),
            credit=f', {credit}' if credit else '')

    # Context: only the fields relevant to THIS seed
    ctx_fields = ['canonical_title', 'artist', 'venue_name']
    if seed.get('kind') == 'matrix_agent':
        # 'agent:donor' is derived from credit_line and has no field of its own.
        seed_field = (seed.get('id') or '').replace('agent:', '')
        if seed_field == 'donor':
            seed_field = 'credit_line'
        if seed_field and seed_field in matrix and seed_field not in ctx_fields:
            ctx_fields.append(seed_field)
    else:
        ctx_fields = [k for k in matrix if matrix.get(k)]

    mat = '\n'.join(f'  {k}: {matrix[k]}' for k in ctx_fields if matrix.get(k))

    # Instruction varies by seed kind
    cl = seed.get('seed', '')
    if seed.get('kind') == 'matrix_agent':
        instruction = (
            f"Search, then answer with FACTS ONLY about {cl} — each one "
            "sentence, with its source in brackets. What did they do in "
            "relation to this work? What happened to them because of it? "
            "If you find nothing reliable about THIS PERSON, say exactly "
            '"NO RELIABLE INFORMATION". Do not discuss other people\'s '
            "contributions. Do not praise the work. Maximum 6 sentences.")
    else:
        instruction = (
            "Search, then answer with FACTS ONLY — each one sentence, with its "
            "source in brackets. Prefer what a visitor standing in front of it "
            "cannot see: why it was made, who decided, what went wrong, what it "
            "cost someone. If you find nothing reliable, say exactly "
            '"NO RELIABLE INFORMATION". Do not praise the work. Do not describe '
            "how it looks. Maximum 6 sentences.")

    return (f"{seed_ask}\n\n"
            f"Context — the work this concerns:\n{mat}\n"
            f"Exhibition: {exhibition or 'this exhibition'}\n\n"
            f"{instruction}")

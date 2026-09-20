"""A named death must carry its circumstances, or it does not ship.

Michael, 2026-09-18, on CHURCH_1 stop 1:

    "Fast forward to June 2023, when tragedy struck the community with the murder
     of Bruno D'Amore, Gilda 'Jill' D'Amore, and Lucia Arpino. The narthex once
     again became a focal point, hosting a 'Mass of Peace' attended by hundreds."

    *"is not clear to me: were they killed because they were black? It is important
    to say what happened (the couple was killed), but then the listener really wants
    to know the cause and circumstances."*

**The passage did have circumstances and a gate removed them.** From that run's log:

    [LOCAL-472] UNGROUNDED entity stop='Narthex' entity='In June'
        reason='It does not specify how the D'Amores relate to the narthex beyond
                their deaths.'
        in: "In June 2023, the community returned to this space under more somber
             circumstances. It was the day B..."
    removed: "In response, the church hosted a 'Mass of Peace,' drawing hundreds."

This is LOCAL-479's defect inverted. There, a gate removed an introduction and left
the dependants. Here a gate removed the EXPLANATION and left the naming — so three
real, named people are reported murdered with no account of what happened, and the
listener is invited to supply a motive. Michael's guess was a racist attack; nothing
in the text says so either way.

**The rule: never name a real person's violent death without its circumstances.**
We cannot invent a cause, so when the cause is gone the naming goes with it. That is
a narrow exception to D577 ("unverified still ships") and it is justified because
the harm is not a dull sentence — it is a false impression about identifiable people.
"""

import re

try:
    from sentence_split import split_sentences as _split
except Exception:  # pragma: no cover
    def _split(t):
        return re.split(r'(?<=[.!?])\s+', t or '')

# A violent death being reported.
_DEATH = re.compile(
    r'\b(murder(?:ed|s)?|killed|slain|shot dead|stabbed|assassinat\w*|massacre\w*'
    r'|manslaughter|homicide)\b', re.I)

# Words that actually explain HOW or WHY — not merely that people were sad.
_CIRCUMSTANCE = re.compile(
    r'\b(because|after (?:a|an|the)|during (?:a|an|the)|in a (?:robbery|fire|crash|'
    r'raid|riot|dispute|burglary)|motive|suspect\w*|convicted|arrest\w*|charged|'
    r'trial|perpetrat\w*|attack(?:ed|er|ers)?|gunman|intrud\w*|stabb\w*|shot by|'
    r'struck by|died when|as a result of|over a)\b', re.I)

# A named person: two capitalised tokens, allowing O'Brien, D'Amore, hyphens.
_NAMED = re.compile(r"\b[A-Z][\w’'\-]+(?:\s+(?:'[^']+'\s+)?[A-Z][\w’'\-]+)+\b")


def find_uncontextualised_deaths(text):
    """Return sentences reporting a named violent death with no circumstances."""
    sents = _split(text or '')
    flagged = []
    for i, s in enumerate(sents):
        if not _DEATH.search(s) or not _NAMED.search(s):
            continue
        window = ' '.join(sents[max(0, i - 1):i + 2])
        if not _CIRCUMSTANCE.search(window):
            flagged.append(s)
    return flagged


def strip_uncontextualised_deaths(text):
    """Drop those sentences. Returns (clean_text, removed_sentences).

    Removing the naming leaves its consequence behind — "The narthex once again
    became a focal point, hosting a 'Mass of Peace'" now refers to nothing. That is
    exactly what LOCAL-479 exists to clean, so this hands its removals straight to
    `cut_orphaned_dependants` rather than growing a second copy of that logic
    (D564: one mechanism, never two).
    """
    flagged = find_uncontextualised_deaths(text)
    if not flagged:
        return text, []
    keep = [s for s in _split(text or '') if s not in flagged]
    clean = ' '.join(keep).strip()
    try:
        from unglossed_reference_gate import cut_orphaned_dependants
        clean, orphans = cut_orphaned_dependants(clean, flagged)
        flagged = list(flagged) + list(orphans or [])
    except Exception:
        pass
    # LOCAL-479 cuts dependants of a removed PERSON ("Walter", "Reid"). What is
    # left here depends on a removed EVENT: "The narthex ONCE AGAIN became a focal
    # point, hosting a 'Mass of Peace'" — the "once again" now refers to nothing and
    # the Mass is unexplained. Narrow sweep for that, adjacent sentences only.
    _ANAPHORIC = re.compile(r'\b(once again|in response|this (?:gathering|somber|'
                            r'tragedy|loss|event)|the (?:gathering|memorial|vigil))\b',
                            re.I)
    remaining = _split(clean)
    survivors, cut_extra = [], []
    for sent in remaining:
        if _ANAPHORIC.search(sent) and not _NAMED.search(sent):
            cut_extra.append(sent)
        else:
            survivors.append(sent)
    if cut_extra:
        clean = ' '.join(survivors).strip()
        flagged = list(flagged) + cut_extra
    return clean, flagged


# ── Search before you delete ────────────────────────────────────────────────
# Michael, 2026-09-20: *"if we found out about 'a real person's violent death' at
# least circumstances must be in the same article, unless this was an article
# summary… omitting the fact should not be a substitution for us searching for a
# cause or circumstances."*
#
# He is right. If a sentence reporting the murder exists at all, something we read
# carried the circumstances and we failed to bring them through. Deleting is the
# fallback, not the response.
#
# **The hazard that shapes the implementation.** For a recent crime involving
# private individuals the sources are thin, and a model asked "why were they
# killed" will produce a motive whether or not one is known. A wrong motive
# attached to a real murder is far worse than omitting the passage — worse than any
# other failure in this pipeline, because it defames identifiable people. So the
# retrieval is GROUNDED and must come back with BOTH sources and explicit
# circumstance language; anything less is treated as "not found" and the sentence
# is removed as before.

_NAME_IN = re.compile(r"\b[A-Z][\w’'\-]+(?:\s+(?:'[^']+'\s+)?[A-Z][\w’'\-]+)+\b")
_YEAR_IN = re.compile(r'\b(1[5-9]\d\d|20\d\d)\b')
MAX_CIRCUMSTANCE_CHARS = 320


def circumstances_query(sentence, venue_name='', location=''):
    """A closed question about a specific death — never 'why do you think'."""
    names = _NAME_IN.findall(sentence or '')
    years = _YEAR_IN.findall(sentence or '')
    who = ', '.join(dict.fromkeys(names[:4])) or 'the people named'
    when = f' in {years[0]}' if years else ''
    where = f' near {venue_name}' if venue_name else (f' in {location}' if location else '')
    return (
        f'What were the documented circumstances of the deaths of {who}{when}{where}?\n'
        'State only what reporting confirms: where and how it happened, who was '
        'charged or convicted, and the stated motive IF investigators or the courts '
        'stated one.\n'
        'If the circumstances are not documented, reply exactly: NOT DOCUMENTED. '
        'Do not speculate about a motive under any condition. Cite your sources.'
    )


def resolve_uncontextualised_deaths(text, venue_name='', location='',
                                    ask_grounded=None):
    """Try to RECOVER the circumstances; delete only if that fails.

    Returns (text, recovered, removed) where `recovered` is
    [{sentence, circumstances, sources}].
    """
    flagged = find_uncontextualised_deaths(text)
    if not flagged:
        return text, [], []
    if ask_grounded is None:
        clean, removed = strip_uncontextualised_deaths(text)
        return clean, [], removed

    recovered, still_bare = [], []
    for sent in flagged:
        try:
            answer, sources = ask_grounded(
                circumstances_query(sent, venue_name, location))
        except Exception:
            answer, sources = '', []
        answer = ' '.join((answer or '').split())
        if (not sources or not answer or 'NOT DOCUMENTED' in answer.upper()
                or not _CIRCUMSTANCE.search(answer)):
            still_bare.append(sent)      # nothing solid came back — delete it
            continue
        recovered.append({'sentence': sent,
                          'circumstances': answer[:MAX_CIRCUMSTANCE_CHARS],
                          'sources': list(sources)})

    out = text
    # Splice the recovered circumstances in right after the sentence that named the
    # death, so the listener hears what happened instead of being left to guess.
    for rec in recovered:
        sents = _split(out)
        try:
            i = sents.index(rec['sentence'])
        except ValueError:
            continue
        circ = rec['circumstances'].strip()
        if circ and not circ.endswith(('.', '!', '?')):
            circ += '.'
        sents.insert(i + 1, circ)
        out = ' '.join(sents)
    if still_bare:
        keep = [s for s in _split(out) if s not in still_bare]
        out = ' '.join(keep).strip()
        try:
            from unglossed_reference_gate import cut_orphaned_dependants
            out, orphans = cut_orphaned_dependants(out, still_bare)
            still_bare = list(still_bare) + list(orphans or [])
        except Exception:
            pass
    return out, recovered, still_bare

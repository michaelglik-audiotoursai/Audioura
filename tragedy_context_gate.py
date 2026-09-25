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
MAX_CIRCUMSTANCE_CHARS = 420


def _as_narration(raw, names):
    """Turn the grounded answer into a spoken sentence, not pasted markdown.

    Michael, 2026-09-22, on CHURCH_1's Narthex: the recovered circumstances shipped
    as **"Based on official reporting from law enforcement and court proceedings:
    * **Where it happened:** Inside the victims' home at 49 Broadway Street ...
    failed to arrive for their 50th wedding a."** — three defects in one passage:
    the model's bullet markdown pasted verbatim into narration, a cut mid-word at
    the character cap, and **the victims never named**, which is the whole point.
    His verdict: *"If they were named, this would have been a wonderful story
    connecting the crime to the Stop."*
    """
    txt = ' '.join((raw or '').split())
    txt = re.sub(r'\*\*([^*]+)\*\*', r'\1', txt)        # bold
    txt = re.sub(r'(?:^|\s)[*\-•]\s+', ' ', txt)          # bullets
    txt = re.sub(r'\b(Where it happened|What happened|Who was charged|'
                 r'Motive|Outcome|Circumstances)\s*:\s*', '', txt, flags=re.I)
    txt = re.sub(r'^\s*Based on [^:]{0,80}:\s*', '', txt, flags=re.I)
    # Strip the model ARGUING WITH THE PROMPT. Found by the kiro critic on CHURCH_1:
    #   "The premise of the deaths occurring 'near Main Altar' is not supported by
    #    public and investigative reporting; however, the circumstances ... are
    #    documented as follows:"
    # — pasted straight into narration, so the tour audibly disputes its own
    # question before telling the story. The correction is right and belongs in a
    # log, never in a listener's ear.
    txt = re.sub(r'^.{0,200}?\bis not supported by\b.{0,120}?;\s*however,?\s*', '',
                 txt, flags=re.I)
    txt = re.sub(r'^\s*The premise[^.]{0,200}\.\s*', '', txt, flags=re.I)
    txt = re.sub(r'\b(?:are|is) documented as follows\s*:?\s*', '', txt, flags=re.I)
    txt = re.sub(r'^\s*(?:however|but)\s*,?\s*', '', txt, flags=re.I)
    txt = ' '.join(txt.split()).strip()
    # Never cut mid-word: keep whole sentences up to the cap.
    out = []
    for sent in _split(txt):
        if sum(len(x) + 1 for x in out) + len(sent) > MAX_CIRCUMSTANCE_CHARS:
            break
        out.append(sent)
    txt = ' '.join(out).strip() or ''
    if txt and not txt.endswith(('.', '!', '?')):
        txt += '.'
    # The names are the point. If the recovered prose dropped them, put them back.
    missing = [n for n in (names or []) if n and n.split()[-1] not in txt]
    if txt and missing:
        txt = txt.rstrip('.') + '. The victims were ' + ', '.join(missing) + '.'
    return txt


def circumstances_query(sentence, venue_name='', location=''):
    """A closed question about a specific death — never 'why do you think'."""
    names = _NAME_IN.findall(sentence or '')
    years = _YEAR_IN.findall(sentence or '')
    who = ', '.join(dict.fromkeys(names[:4])) or 'the people named'
    when = f' in {years[0]}' if years else ''
    where = f' near {venue_name}' if venue_name else (f' in {location}' if location else '')
    # Ask for NARRATION, not a report. The structured version came back with
    # headings, bullets and the model disputing the question — "The premise of the
    # deaths occurring 'near Main Altar' is not supported by ... however, the
    # circumstances ... are documented as follows: * **Where and How It Happened:**"
    # — all of which was spliced into a listener's ear. Sanitising arbitrary prose
    # with regex is whack-a-mole; asking for one clean paragraph is not.
    return (
        f'What were the documented circumstances of the deaths of {who}{when}{where}?\n\n'
        'Answer in ONE SHORT PARAGRAPH of plain spoken English — two or three '
        'sentences — exactly as it would be read aloud to a visitor.\n'
        'Name the people. Say where and how it happened, and who was charged or '
        'convicted. Give the stated motive ONLY if investigators or the courts '
        'stated one.\n\n'
        'Do NOT use headings, bullet points, bold text or labels. Do NOT comment on '
        'the question, correct its premise, or explain what you are doing — give '
        'only the sentences a visitor would hear.\n'
        'If the circumstances are not documented, reply exactly: NOT DOCUMENTED. '
        'Never speculate about a motive. Cite your sources.'
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
        _names = _NAME_IN.findall(sent or '')
        _clean = _as_narration(answer, _names)
        if not _clean:
            still_bare.append(sent)
            continue
        recovered.append({'sentence': sent, 'circumstances': _clean,
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

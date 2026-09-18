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

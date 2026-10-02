#!/usr/bin/env python3
"""story_seeds.py — D503: every sentence decomposed into story seeds.

Michael, 2026-08-22, working Stop 2 by hand:

    "In this singular work, Juan Gris and Pierre Reverdy, the French poet linked
     to Surrealism, embarked on a project that revolutionized the concept of the
     book as art, exemplifying the collaborative spirit that defines the MFA's
     exhibition."

    Subject: 'Juan Gris and Pierre Reverdy'  + note 'the French poet linked to
    Surrealism'.  Action: 'embarked on a project' + notes 'that revolutionized
    the concept of the book as art', 'exemplifying the collaborative spirit...'

    -> 1.1 'Pierre Reverdy, the French poet linked to Surrealism'
       1.2 'project that revolutionized the concept of the book as art'
       1.3 'project exemplifying the collaborative spirit'
       1.4 'project defines the MFA's exhibition'

    "That is already 7 credit_lines and only from 2 sentences."

**The insight, and it is his:** D502 found ONE hook per sentence, by matching a
trigger word. But a sentence is not one claim — it is a subject, an action, and a
cloud of MODIFIERS, and each modifier is a separate assertion that the listener
either already understands or does not. The modifiers are where the story seeds
are, and there are far more of them than trigger-matching finds. On his three
sentences: D502 finds 3, this finds 10.

**Two kinds of seed, and they behave differently downstream.** This is the one
thing his worked example does not distinguish, and it decides what happens next:

  ANCHORED    the phrase names a real, checkable entity.
              "Pierre Reverdy, the French poet linked to Surrealism" — Reverdy
              exists, the claim is verifiable, and retrieval can CONFIRM OR DENY
              it. A failed check is a fabrication caught.

  EVALUATIVE  the phrase is our own editorial abstraction with no entity in it.
              "Reverdy's poetic prowess", "a unique interlacing of images and
              words". Nothing to verify: no source will ever confirm "prowess".
              Retrieval cannot check these — it can only find the EVENT that
              would justify them, or fail to, in which case the honest move is
              to CUT the phrase rather than substantiate it.

Mixing them would let an editorial flourish be treated as a fact awaiting
confirmation, which is how "the collaborative spirit" becomes a thing we assert
because we already asserted it. So each seed carries its kind.

**Still not circular.** A seed is a QUESTION or a CLAIM TO CHECK, never evidence.
The answer comes from retrieval and faces every gate. Same contract as D502.
"""
import re
from typing import Dict, List, Optional

from text_fold import fold

__all__ = ['decompose', 'seeds_for_stop', 'ANCHORED', 'EVALUATIVE', 'SEED_KINDS']

ANCHORED = 'anchored'
EVALUATIVE = 'evaluative'

SEED_KINDS = (
    'appositive',      # ", the French poet linked to Surrealism,"
    'relative',        # "that revolutionized the concept of the book as art"
    'participial',     # "exemplifying the collaborative spirit"
    'possessive',      # "Gris's innovative vision"
    'capacity',        # "Reverdy's capacity to infuse words with structural beauty"
    'result',          # "resulting in a unique interlacing of images and words"
    'prepositional',   # "with structural beauty"
)

_PROPER = r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+"
_NAME = rf"{_PROPER}(?:\s+(?:de|van|von|di|le|la|du)\s+)?(?:\s+{_PROPER})*"

# ", <the|a> <phrase>," between commas, following a name — the classic appositive.
_APPOSITIVE = re.compile(
    rf"({_NAME})\s*,\s*((?:the|a|an)\s+[^,;.]{{6,90}}?)\s*(?=,|\.|;)")

# "that/which/who <verb-phrase>"
_RELATIVE = re.compile(
    r"\b(?:that|which|who)\s+((?:[a-z]|\w)[^,;.]{8,100}?)"
    r"(?=,|\.|;|$|\s+(?:and|but)\s+)",
    re.IGNORECASE)

# ", <verb>ing ..." — a participial adjunct
_PARTICIPIAL = re.compile(r",\s*(\w+ing\s+[^,;.]{6,100}?)(?=,|\.|;|$)")

# "Gris's innovative vision" / "Reverdy's poetic prowess"
_POSSESSIVE = re.compile(
    rf"({_PROPER})['’]s\s+((?:[a-z]+\s+){{0,2}}[a-z]+)\b(?!\s*['’]s)")

# "Gris's ability to transform visual art"
_CAPACITY = re.compile(
    rf"({_PROPER})['’]s\s+(ability|capacity|power|gift|willingness|refusal|"
    rf"decision|attempt|effort)\s+to\s+([^,;.]{{5,80}}?)(?=,|\.|;|$|\s+but\b)",
    re.IGNORECASE)

# "resulting in ..." / "leading to ..." — the stated consequence
_RESULT = re.compile(
    r"\b(?:resulting\s+in|leading\s+to|giving\s+rise\s+to|culminating\s+in)\s+"
    r"([^,;.]{6,90}?)(?=,|\.|;|$)", re.IGNORECASE)

# Nouns that make a phrase evaluative no matter what else is in it: they name a
# quality we assigned, not an event anyone can check.
_EVALUATIVE_NOUNS = {
    'prowess', 'vision', 'genius', 'brilliance', 'mastery', 'spirit',
    'beauty', 'elegance', 'creativity', 'imagination', 'sensibility',
    'importance', 'significance', 'legacy', 'impact', 'influence',
    'ability', 'capacity', 'power', 'gift', 'talent', 'skill',
    'interlacing', 'synthesis', 'fusion', 'harmony', 'dialogue',
    'testament', 'embodiment', 'expression', 'essence', 'quality',
}

# Anchors that name the institution rather than a person.
_VENUE_WORDS = {'mfa', 'museum', 'gallery', 'exhibition', 'collection',
                'louvre', 'tate', 'moma', 'met'}

_EVALUATIVE_ADJS = {
    'innovative', 'unique', 'remarkable', 'extraordinary', 'profound',
    'masterful', 'exquisite', 'stunning', 'brilliant', 'visionary',
    'pivotal', 'singular', 'unparalleled', 'seminal', 'iconic',
    'collaborative', 'poetic', 'structural', 'vivid', 'compelling',
}


def _clean(s: str) -> str:
    s = re.sub(r'\s+', ' ', (s or '')).strip(' ,;:.')
    return s


def _classify(phrase: str, known_entities: Optional[set] = None) -> str:
    """ANCHORED if the phrase names something checkable; EVALUATIVE otherwise."""
    known = known_entities or set()
    folded = fold(phrase)
    words = set(re.findall(r'[a-z]+', folded))

    # A quality-noun head makes it evaluative even when a name is attached:
    # "Reverdy's poetic prowess" names Reverdy but asserts prowess.
    if words & _EVALUATIVE_NOUNS:
        return EVALUATIVE
    # A named entity we already know about, or any capitalised span, or a date.
    if any(k in folded for k in known):
        return ANCHORED
    if re.search(rf"\b{_PROPER}", phrase) or re.search(r'\b(1[4-9]\d{2}|20[0-2]\d)\b', phrase):
        return ANCHORED
    if words & _EVALUATIVE_ADJS:
        return EVALUATIVE
    return EVALUATIVE


def decompose(sentence: str, known_entities: Optional[set] = None) -> Dict:
    """One sentence -> {subject, action, modifiers[]}.

    `modifiers` is the list Michael calls "Adjectives/Descriptions/Notes"; each
    becomes a seed. Deliberately shallow: no parser is available in this
    environment and the codebase's other language instruments
    (`story_opportunity_scan`, `text_fold`) are regex too, so this stays in the
    same idiom rather than adding a dependency for one module.
    """
    known = {fold(k) for k in (known_entities or set()) if k}
    sentence = _clean(sentence)
    mods: List[Dict] = []

    def add(kind, text, anchor=''):
        text = _clean(text)
        # "Gris's innovative vision to blend..." — the possessive window ran on
        # into the infinitive and left a dangling "to". A modifier ending in a
        # function word is a truncation, not a phrase.
        text = re.sub(r'\s+(?:to|of|in|with|and|for|the|a|an|that|by)$', '',
                      text).strip()
        if len(text) < 6:
            return
        if len(text) < 6:
            return
        folded = fold(text)
        # CONTAINMENT dedupe, not equality. `_CAPACITY` and `_POSSESSIVE` both
        # fire on "Gris's ability to transform visual art", the second yielding
        # the truncated "ability to transform" — two seeds for one claim, the
        # shorter one useless. The richer match runs first and wins.
        for m in list(mods):
            mf = fold(m['text'])
            if folded == mf:
                return
            if folded in mf:
                return                      # existing is richer, keep it
            if mf in folded:
                mods.remove(m)              # new is richer, replace
        # The venue is the setting, not a party — LOCAL-475/494/496, and D502
        # hit it too. "the MFA's exhibition" yielded the possessive seed
        # "exhibition", anchored to the museum, which is nobody's story.
        if anchor and fold(anchor) in _VENUE_WORDS:
            return
        mods.append({'kind': kind, 'text': text, 'anchor': anchor,
                     'class': _classify(f'{anchor} {text}'.strip(), known)})

    for m in _APPOSITIVE.finditer(sentence):
        add('appositive', m.group(2), m.group(1))
    for m in _CAPACITY.finditer(sentence):
        add('capacity', f'{m.group(2)} to {m.group(3)}', m.group(1))
    for m in _POSSESSIVE.finditer(sentence):
        add('possessive', m.group(2), m.group(1))
    for m in _RELATIVE.finditer(sentence):
        add('relative', m.group(1))
    for m in _PARTICIPIAL.finditer(sentence):
        add('participial', m.group(1))
    for m in _RESULT.finditer(sentence):
        add('result', m.group(1))

    # Subject and action, best effort — reported so a seed is traceable back to
    # the clause it came from, not used for retrieval.
    subj = ''
    sm = re.match(rf"^(?:In|At|Within|Through|During)[^,]{{0,60}},\s*({_NAME}(?:\s+and\s+{_NAME})?)", sentence)
    if sm:
        subj = sm.group(1)
    else:
        sm = re.match(rf"^((?:The\s+|Their\s+|His\s+|Her\s+)?{_PROPER}?[\w\s'’]{{0,40}}?)\s+(?:\w+ed|\w+s)\b", sentence)
        if sm:
            subj = _clean(sm.group(1))
    am = re.search(r'\b(\w+(?:ed|s))\s+', sentence)
    action = am.group(1) if am else ''

    return {'sentence': sentence, 'subject': subj, 'action': action,
            'modifiers': mods}


def seeds_for_stop(text: str, known_entities: Optional[set] = None,
                   skip: Optional[re.Pattern] = None) -> List[Dict]:
    """Every seed in a stop's prose, in sentence order.

    Each seed: {'id', 'kind', 'class', 'text', 'anchor', 'sentence', 'seed'}
    where `seed` is the phrasing handed to retrieval.
    """
    from story_hooks import _PACKAGING
    skip = skip or _PACKAGING
    out: List[Dict] = []
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or '').strip())
                 if len(s.strip()) > 25 and not skip.match(s.strip())]

    for si, sentence in enumerate(sentences, 1):
        d = decompose(sentence, known_entities)
        for mi, mod in enumerate(d['modifiers'], 1):
            anchor = mod['anchor']
            phrase = mod['text']
            possessive_like = mod['kind'] in ('possessive', 'capacity')
            if possessive_like and anchor:
                joined = f"{anchor}'s {phrase}"
            elif anchor:
                joined = f"{anchor}, {phrase}"
            else:
                joined = phrase
            if mod['class'] == ANCHORED:
                seed = joined
                ask = f'Is this true, and what is the event behind it: "{seed}"?'
            else:
                subj = anchor or d['subject'] or 'this'
                seed = joined
                ask = (f'What did {subj} actually DO that would justify '
                       f'"{phrase}"? If nothing, cut the phrase.')
            out.append({
                'id': f'{si}.{mi}',
                'kind': mod['kind'],
                'class': mod['class'],
                'text': phrase,
                'anchor': anchor,
                'seed': _clean(seed),
                'ask': ask,
                'sentence': sentence,
                'subject': d['subject'],
                'action': d['action'],
            })
    return out

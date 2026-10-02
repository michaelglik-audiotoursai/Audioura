#!/usr/bin/env python3
"""story_hooks.py — D502: the sentences that open a door and do not walk through it.

Michael, 2026-08-21, on this sentence from the 08-20 baseline:

    "Au Soleil du Plafond vividly represents the exhibition's thesis, which
     highlights how visual artists and poets collaborated to challenge the
     boundaries of artistic media."

    "unless they are aware what 'the boundaries of artistic media' were prior
     [to] visual artists and poets collaborating, this sentence can not be
     understood ... I would not want to throw it away ... but I would rather
     substantiate it with a story."

**This is a different question from any instrument we have.**

  `story_worthiness`      (step 2)  scores the MATRIX, before mining:
                                    "have we got material?"
  `story_opportunity_scan` (step 7a) scores the FINISHED TEXT:
                                    "is a story present?"
  this module                        scores the finished text for:
                                    "does it raise something it never explains?"

A stop can pass both existing instruments and still leave the listener stranded,
which is exactly the case above: the sentence is factual, grounded, gate-clean,
and unintelligible without knowledge the listener does not have.

**The circularity question, which Michael raised himself and which decides the
design.** Harvesting FACTS out of generated prose would be circular — the prose
came from the model, and reading it back as evidence lets the model's own writing
become a source. That is what every gate in step 6 exists to prevent.

This harvests something else: **what needs substantiating**. The sentence names
the question; the ANSWER still has to come from retrieval and still faces every
gate. Claims-as-search-targets, not claims-as-evidence.

**Therefore it must read POST-GATE text.** Traced 2026-08-21: stop existence is
validated early (LOCAL-372), but the sentence-level gates — unsupported-claim,
unglossed-reference, prose entity grounding, form-claim — run at PHASE
5.156-5.159, AFTER the matrix is assembled at PHASE 5. Mining pre-gate prose
would let a hook be built on a sentence the gates are about to delete.
"""
import re
from typing import Dict, List, Optional

from text_fold import fold

__all__ = ['find_hooks', 'hooks_to_focus_facts', 'HOOK_KINDS']

# ── The four shapes of an unwalked door ──────────────────────────────────────
#
# Each is a claim whose SUBSTANCE is elsewhere. They are not bad sentences — the
# one Michael quoted is a good sentence — they are sentences that assume a
# `before` the listener was never given.

HOOK_KINDS = ('change', 'significance', 'superlative', 'relation')

# A change was asserted. Whatever it changed FROM is what the listener needs.
_CHANGE = re.compile(
    r'\b(?:revolutioni[sz]ed?|transformed?|redefined?|reinvented?|'
    r'challenged?|broke\s+(?:with|from)|departed\s+from|overturned?|'
    r'changed?|shifted?|pushed\s+the\s+boundaries|expanded\s+the\b|'
    r'moved\s+away\s+from|abandoned?|rejected?)\b', re.IGNORECASE)

# An importance was asserted without the events that make it important.
_SIGNIFICANCE = re.compile(
    r'\b(?:exemplifies|represents?\s+the\b|embodies|epitomi[sz]es|'
    r'demonstrates?|illustrates?|marked?\s+a\s+(?:significant|major|turning)|'
    r'was\s+pivotal|is\s+pivotal|milestone|landmark|testament\s+to|'
    r'significan(?:t|ce)\b|highlights?\s+how)\b', re.IGNORECASE)

# A "first/only/last" that is not backed by what came before or after.
_SUPERLATIVE = re.compile(
    r'\b(?:the\s+(?:first|last|only|finest|greatest|earliest)\b|'
    r'one\s+of\s+the\s+(?:first|only|finest|most)\b|unprecedented|'
    r'had\s+no\s+precedent|never\s+before|unlike\s+any)\b', re.IGNORECASE)

# Two parties named as connected, with the nature of the connection missing.
_RELATION = re.compile(
    r'\b(?:collaborat(?:ed|ion|ive)|partnership|worked\s+(?:together|with)|'
    r'joined\s+forces|commissioned\s+by|in\s+dialogue\s+with|'
    r'thanks\s+(?:in\s+part\s+)?to)\b', re.IGNORECASE)

_PATTERNS = (
    ('change', _CHANGE),
    ('significance', _SIGNIFICANCE),
    ('superlative', _SUPERLATIVE),
    ('relation', _RELATION),
)

# The abstraction the sentence leans on — this is the thing to go and research.
# Captured rather than the whole sentence, because a query built from a whole
# sentence returns nothing (LOCAL-457's lesson: exact-phrase searching a string
# that exists nowhere).
_ABSTRACTIONS = re.compile(
    r'\b(?:the\s+)?((?:boundaries|conventions|traditions|limits|norms|rules|'
    r'possibilities|definition|nature|role|status|form)\s+of\s+'
    r'[a-z][a-z\s]{3,40}?)(?=[,.;]|\s+(?:and|but|which|that|when|while)\b)',
    re.IGNORECASE)

_PROPER = re.compile(r'\b([A-ZÀ-Þ][A-Za-zÀ-ÿ\'’\-]+(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ\'’\-]+)*)')

# Words that begin a sentence and are capitalised for that reason alone.
_SENTENCE_START_NOISE = {
    'the', 'this', 'these', 'those', 'their', 'his', 'her', 'its', 'from',
    'within', 'here', 'as', 'at', 'in', 'on', 'by', 'with', 'through', 'while',
    'when', 'what', 'stand', 'pause', 'you', 'your', 'each', 'both', 'it',
    # Capitalised because a sentence began with them, not because they name
    # anyone. Without these the hooks read "What did Published and Louis Broder
    # actually do" — `Published` harvested from "Published by Louis Broder".
    'published', 'printed', 'created', 'commissioned', 'gifted', 'donated',
    'situated', 'located', 'housed', 'displayed', 'exhibited', 'produced',
    'together', 'known', 'renowned', 'famous', 'unlike', 'despite', 'although',
}

# Capitalised words that are common nouns or adjectives, not names. Measured on
# the 08-20 baseline: "Gallery 184" yielded the subject `Gallery`, and `Spanish`
# was harvested from "works by Spanish artists" — neither is anybody.
_NOT_A_NAME = {
    'gallery', 'museum', 'exhibition', 'collection', 'galleries', 'room',
    'spanish', 'french', 'catalan', 'american', 'british', 'italian', 'german',
    'dutch', 'belgian', 'swiss', 'russian', 'mexican', 'surrealist', 'cubist',
    'modern', 'contemporary', 'illustrated', 'book', 'books', 'press',
    'lithograph', 'lithographs', 'etching', 'volume', 'edition', 'artist',
    'artists', 'poet', 'poets', 'work', 'works', 'stop', 'tour', 'audio',
}


# Tour PACKAGING, not stop content: the closing recap, the Treat Page pitch, the
# inter-stop directions. Mining these produced the hook "What did Au Soleil and
# Le Lézard actually do together?" — harvested from "That's 3 stops — Au Soleil
# du Plafond showcases collaboration ...", which is our own summary line, not a
# claim about the object in front of the listener.
_PACKAGING = re.compile(
    r"^\s*(?:That'?s\s+\d+\s+stops?\b|Closing:|Directions:|Address:|"
    r"Coordinates:|The\s+Treat\s+Page\b|We\s+can\s+also\s+generate\b)",
    re.IGNORECASE)


def _sentences(text: str) -> List[str]:
    out = []
    for s in re.split(r'(?<=[.!?])\s+', (text or '').strip()):
        s = s.strip()
        if len(s) > 25 and not _PACKAGING.match(s):
            out.append(s)
    return out


def _entities_in(sentence: str, known: Optional[set] = None) -> List[str]:
    """Capitalised spans that plausibly name somebody.

    `known` holds the agents the matrix already names — artist, publisher,
    printer, donor. A span matching one of those is accepted outright; anything
    else must survive the noise filters AND name at least two tokens, because a
    lone capitalised word mid-sentence is far more often a common noun
    ("Gallery", "Spanish") than a person.
    """
    known = known or set()
    out = []
    for m in _PROPER.finditer(sentence):
        name = re.sub(r'\s+', ' ', m.group(1).strip())
        tokens = name.split()
        # Trim leading noise so "Published by Louis Broder" yields "Louis Broder"
        while tokens and fold(tokens[0]) in _SENTENCE_START_NOISE:
            tokens.pop(0)
        while tokens and fold(tokens[-1]) in _NOT_A_NAME:
            tokens.pop()
        if not tokens:
            continue
        name = ' '.join(tokens)
        folded = fold(name)
        if len(name) < 4 or folded in _NOT_A_NAME:
            continue
        if any(fold(t) in _NOT_A_NAME for t in tokens):
            continue
        if folded in known or any(folded in k or k in folded for k in known):
            out.append(name)
            continue
        if len(tokens) < 2:
            continue  # a single capitalised word is not evidence of a person
        out.append(name)
    return out


def find_hooks(text: str, stop_title: str = '', venue_name: str = '',
               known_agents: Optional[List[str]] = None) -> List[Dict]:
    """Sentences that assert something they do not substantiate.

    Returns [{'kind', 'sentence', 'subject', 'question', 'why'}], best first.

    `subject` is what to research — the abstraction the sentence leans on, or the
    named parties whose connection it asserts. `question` is the listener's
    unanswered question, in the words the listener would use.
    """
    hooks: List[Dict] = []
    title_tokens = {t for t in re.findall(r'\w{4,}', fold(stop_title))}
    # [LOCAL-496's class, third instance] The venue is the SETTING, not a party
    # to the story. Without this, "the Museum of Fine Arts, Boston, enriched its
    # collection thanks to patrons like Torf" yields the subject "Fine Arts and
    # Boston" — fragments of the venue's own name — and loses Torf, who is the
    # only real handle in the sentence. LOCAL-475, 494 and 496 are the same
    # mistake at three other gates.
    venue_tokens = {t for t in re.findall(r'\w{4,}', fold(venue_name))}
    known = {fold(a) for a in (known_agents or []) if a}

    for sentence in _sentences(text):
        for kind, pattern in _PATTERNS:
            m = pattern.search(sentence)
            if not m:
                continue
            trigger = m.group(0).strip()

            subject, question = '', ''
            abstraction = _ABSTRACTIONS.search(sentence)
            if abstraction:
                subject = re.sub(r'\s+', ' ', abstraction.group(1)).strip()
                question = (f'What were the {subject} before this, and what '
                            f'changed them?')
            else:
                names = []
                for n in _entities_in(sentence, known):
                    n_tokens = {t for t in re.findall(r'\w{4,}', fold(n))}
                    if title_tokens & n_tokens or venue_tokens & n_tokens:
                        continue
                    names.append(n)
                if names:
                    subject = names[0] if len(names) == 1 else ' and '.join(names[:2])
                    if kind == 'relation':
                        question = (f'What did {subject} actually do together, '
                                    f'and what came of it?')
                    elif kind == 'change':
                        question = (f'What did {subject} change, and what was '
                                    f'it like before?')
                    elif kind == 'superlative':
                        question = (f'What came before {subject}, that makes '
                                    f'this "{trigger.lower()}"?')
                    else:
                        question = (f'What did {subject} actually do, that makes '
                                    f'this significant?')

            if not subject:
                # An assertion with no handle at all. Still worth recording —
                # it is the purest case of "the listener cannot follow this" —
                # but it cannot become a query, so it is reported and ranked last.
                subject = ''
                question = (f'The listener is told "{trigger}" and given nothing '
                            f'to attach it to.')

            hooks.append({
                'kind': kind,
                'sentence': sentence,
                'trigger': trigger,
                'subject': subject,
                'question': question,
                'why': f'asserts {kind} ("{trigger}") without showing it',
            })
            break  # one hook per sentence, strongest pattern first

    # Rank: a hook with a researchable subject beats one without; among those,
    # the order of HOOK_KINDS, which runs most-answerable to least.
    order = {k: i for i, k in enumerate(HOOK_KINDS)}
    hooks.sort(key=lambda h: (0 if h['subject'] else 1, order.get(h['kind'], 9)))
    return hooks


def hooks_to_focus_facts(hooks: List[Dict], limit: int = 4) -> List[Dict]:
    """Turn hooks into the `focus_fact` entries step 7b rotates through.

    Shaped exactly like `story_focus_fact.candidate_facts` output — {'key',
    'fact', 'why'} — so the two lists concatenate and the rotation does not care
    where a candidate came from.

    NOTE THE SLOT. Michael calls this "the credit_line list"; it cannot live in
    `credit_line`, because LOCAL-406 regex-parses donor and printer out of that
    field and would read a fact written there as a person's name. The rotating
    fact has had its own slot since LOCAL-491, and this is it.
    """
    out: List[Dict] = []
    for i, h in enumerate(hooks[:limit]):
        if not h['subject']:
            continue
        out.append({
            'key': f"hook:{h['kind']}:{fold(h['subject'])[:32]}",
            'fact': h['question'],
            'why': f"the stop's own text {h['why']}",
            'source_sentence': h['sentence'],
        })
    return out

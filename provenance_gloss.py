#!/usr/bin/env python3
"""provenance_gloss.py — LOCAL-494: a name from the museum's own record is not
an unverified claim, and must never be degraded out of the tour.

**The incident.** `TOUR_MFA_RELEASE_20260819_0115.txt`, stop 1. Boris Fridman —
the collector who gave the work to the MFA — was deleted from his own sentence,
leaving *"The generous gift of this work to the museum further enriches the
collection."* Michael, reading the tour: *"one real problem is that Fridman as a
generous gifter is gone completely... The organizer, charitable gifter, sponsor
should not be dismissed."*

**Every gate did its job and the outcome was still wrong.** From
`TOUR_MFA_RELEASE_RUN3.log`:

  :235   checklist enrichment set `credit_line='Gift of Boris Fridman'` — the
         museum's own record, correctly read.
  :364   LOCAL-423 disambiguation excluded two snippets, *Boris Fridman-Mintz*
         (a Mexican linguist) and *Fridman Gallery* (NYC, 2013). Both exclusions
         are CORRECT; those are different entities.
  ...    which left zero snippets about the real Fridman.
  :425   the unglossed-reference gate found 1 reference, searched the corpus,
         found nothing, asked the model for a verifiable fact, got none, and
         DEGRADED the name.
  :520   a whole sentence removed: "The museum's collection was significantly
         enriched when Boris Fridman donated this piece..."

**Two defects, and neither is in the gates that fired.**

1. *The gate cannot tell a name that arrives with its own provenance from a name
   the model asserted.* Fridman never needed an external source: **"Gift of Boris
   Fridman" IS the source**, from the venue's own checklist. His gloss is
   derivable from the field he came out of and requires no search at all.

2. *The inference at :425 is backwards.* "No third-party web page about this
   donor" is the NORMAL state for a private collector. It is evidence that he is
   a private individual, not evidence that he is unverified.

**Why deleting him is worse than leaving him unexplained.** His three events are
Prince's minimal story exactly — he collected it, he gave it to the MFA, it is
public. Degrading removed the middle, ACTIVE event, the only one of the three
that cannot be stated without naming him, and left state/state/state. Under
Michael's ruling that a plot beats a sequence (LOCAL-493), the donor is also the
one person in the record whose action IS the reason the object is in front of the
listener — delete them and the "because" goes with them.

**So this module does not exempt these names — the gate was RIGHT that Fridman
was unexplained.** It supplies the missing explanation from provenance, and marks
the name as never-degradable. Gloss, don't delete: the same repair LOCAL-475 made
for the stop's own artist, extended to everyone the museum's record names.

Deterministic and free: no API call, no search, no network.
"""
import re
from typing import Dict, List, Optional

from text_fold import fold, is_placeholder

__all__ = ['ROLE_GLOSSES', 'extract_provenance_roles', 'provenance_gloss_for',
           'provenance_names', 'PROVENANCE_FIELDS']


# The stop-record fields that carry a documented role. `credit_line` is parsed
# rather than read whole, because it is prose ("Published by Louis Broder. Gift
# of Boris Fridman") and LOCAL-406 already regex-mines it.
PROVENANCE_FIELDS = ('credit_line', 'publisher', 'printed_by', 'printer',
                     'artist', 'collaborator', 'writer', 'architect', 'founder',
                     'donor', 'patron', 'sponsor')

# What each role explains, in the register a voice reads aloud. These are
# APPOSITIVES — they are spliced in as ", <gloss>," after the name — so each
# begins with an article and contains no verb. LOCAL-492 fixed a gloss landing
# inside a noun phrase; the gate's own `validate_gloss` guards still apply.
ROLE_GLOSSES = {
    'donor':        'the collector who gave this work to the museum',
    'patron':       'the patron whose support brought this work here',
    'sponsor':      'the sponsor who funded it',
    'founder':      'the founder of this collection',
    'publisher':    'the publisher of this edition',
    'printer':      'the workshop that printed it',
    'artist':       'the artist',
    'illustrator':  'who made the illustrations',
    'writer':       'who wrote the text',
    'collaborator': 'who worked on it alongside the artist',
    'architect':    'the architect',
}

# Parsed out of `credit_line` prose. Deliberately the same shapes
# `story_claim_lab.py` already trusts, so the two modules cannot disagree about
# what a credit line says — D483's defect class, and it was committed inside the
# session that fixed D483.
_CREDIT_LINE_PATTERNS = (
    ('donor',     r'\b(?:gift|bequest)\s+of\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('donor',     r'\bdonated\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('patron',    r'\bthrough\s+the\s+generosity\s+of\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('publisher', r'\bpublished\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('printer',   r'\bprinted\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
)

# Trailing noise on a parsed agent: "Boris Fridman in memory of ..." and the
# collection-name suffixes museums append to credit lines.
_AGENT_TAIL = re.compile(
    r'\s+(?:in\s+memory\s+of|in\s+honou?r\s+of|by\s+exchange|'
    r'and\s+the\s+|for\s+the\s+|Collection|Fund|Bequest)\b.*$',
    re.IGNORECASE)

# A person or named body, not a bare word. Two capitalised tokens minimum, or one
# token plus a recognised corporate suffix ("Mourlot Freres", "Hogarth Press").
_LOOKS_NAMED = re.compile(
    r'^[A-Z][\wÀ-ɏ&.\'’-]*(?:\s+[\wÀ-ɏ&.\'’-]+)+$')


def _clean_agent(raw: str) -> str:
    """Trim a parsed agent to the name itself."""
    if not raw:
        return ''
    agent = _AGENT_TAIL.sub('', raw.strip())
    agent = agent.strip(' .,;:—-')
    # "the Linde Family" -> "Linde Family"; the article is supplied by the host
    # sentence, and leaving it doubles ("the the Linde Family").
    agent = re.sub(r'^(?:the|a|an)\s+', '', agent, flags=re.IGNORECASE)
    return agent.strip()


def _is_named_entity(agent: str) -> bool:
    if not agent or len(agent) < 4 or len(agent) > 60:
        return False
    if is_placeholder(agent):
        return False
    return bool(_LOOKS_NAMED.match(agent))


def extract_provenance_roles(stop: Dict) -> Dict[str, str]:
    """Map every name the stop's own record documents to its role.

    Returns {name: role}. Names are returned as written in the record, because
    that is what the gate matches against the text; comparison is folded.

    The museum's record is the authority here. A name in it is not a claim
    awaiting verification — it is the verification.
    """
    roles: Dict[str, str] = {}
    if not stop:
        return roles

    def _put(agent: str, role: str) -> None:
        agent = _clean_agent(agent)
        if not _is_named_entity(agent):
            return
        # First role wins: `credit_line` is parsed before the plain fields, and
        # "Gift of X" is more specific than X appearing in a `donor` column.
        if not any(fold(agent) == fold(k) for k in roles):
            roles[agent] = role

    # Prose fields, parsed.
    credit = (stop.get('credit_line') or '').strip()
    if credit and not is_placeholder(credit):
        for role, pattern in _CREDIT_LINE_PATTERNS:
            for m in re.finditer(pattern, credit, re.IGNORECASE):
                _put(m.group('agent'), role)

    # Single-value fields, read whole.
    for field in PROVENANCE_FIELDS:
        if field == 'credit_line':
            continue
        value = stop.get(field)
        if not value or not isinstance(value, str):
            continue
        role = field if field in ROLE_GLOSSES else 'collaborator'
        if field == 'printed_by':
            role = 'printer'
        _put(value, role)

    return roles


def provenance_names(stop: Dict) -> List[str]:
    """Just the names, for callers that only need the never-degrade set."""
    return list(extract_provenance_roles(stop).keys())


def provenance_gloss_for(entity: str, stop: Dict) -> Optional[str]:
    """The appositive for `entity`, composed from its documented role.

    Returns None when the stop's record does not name this entity — in which
    case the gate's existing corpus/model path is correct and unchanged.

    No network, no key, no cost. That is the point: Fridman's explanation was
    sitting in `credit_line` while the pipeline spent a model call failing to
    find one on the open web.
    """
    if not entity:
        return None
    roles = extract_provenance_roles(stop)
    target = fold(entity)
    for name, role in roles.items():
        folded = fold(name)
        # Exact, or the text uses a shortened form of the recorded name
        # ("Fridman" for "Boris Fridman"). Never the reverse: a record naming
        # "Fridman" must not gloss an unrelated longer name in the prose.
        if folded == target or (target and target in folded.split()):
            return ROLE_GLOSSES.get(role)
    return None

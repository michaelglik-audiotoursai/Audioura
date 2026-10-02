"""story_fact_guard.py — D533: the birth-year fabrication, caught and repaired.

**The defect this exists for**, from the Palais Lascaris run of 2026-08-26:

    corpus:  "Antoine Gautier, a passionate collector and amateur musician
              BORN IN NICE IN 1825..."
    tour:    "...to the quartet FOUNDED BY Antoine Gautier IN 1825."

A newborn founding a quartet. The correct fact was in the retrieved passage; the
generation step converted `born in` into `founded`. **Every gate on that tour
passed** — D1v2 6/6, existence gate 100%, LOCAL-16 green — because the gates
verify that the STOP exists, not that the SENTENCE is true.

The general defect is not "Gautier": it is that **a year attached to a person in
the corpus carries a ROLE** — born, died, appointed, bequeathed — and the prose
step is free to reattach that year to a different role. Birth and death years are
the common case because they are the years most often stated about a person.

So the check is role-level, not string-level: for every (person, year) the tour
asserts, find what role the CORPUS gives that same pair, and refuse a mismatch.

Deliberately NOT an LLM judgement. This is a comparison between two texts we
already hold, and D526/D528 record six instances in one day of an LLM rule
fitted to the single example in front of it.
"""
import re
import unicodedata
from typing import List, Dict, Tuple

# Roles a year can play for a person, and the words that mark them. Birth/death
# are listed first because they are the ones that cannot be actions.
_ROLE_MARKERS = {
    'birth': ('born', 'birth', 'né', 'nee', 'naquit'),
    'death': ('died', 'death', 'dead', 'deceased', 'mort', 'décès', 'passed away',
              'upon his death', 'upon her death'),
}

# Verbs that assert the person DID something in that year. A birth or death year
# reattached to one of these is the fabrication.
_ACTION_MARKERS = (
    'founded', 'found', 'established', 'created', 'built', 'made', 'crafted',
    'composed', 'wrote', 'painted', 'designed', 'produced', 'published',
    'commissioned', 'opened', 'purchased', 'bought', 'acquired', 'donated',
    'bequeathed', 'gave', 'left', 'appointed', 'joined', 'began', 'started',
    'completed', 'finished', 'invented', 'developed', 'launched',
)

_YEAR_RE = re.compile(r'\b(1[0-9]{3}|20[0-9]{2})\b')
# A capitalised multi-word name. Deliberately conservative: two or more parts, so
# 'Nice' or 'December' alone never matches.
_NAME_RE = re.compile(r'\b([A-ZÀ-Þ][\w\'’\-]+(?:\s+(?:de|du|van|von|della|di|le|la)?\s*[A-ZÀ-Þ][\w\'’\-]+)+)\b')


def _fold(s: str) -> str:
    n = unicodedata.normalize('NFKD', (s or '').lower())
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', n).strip()


def split_sentences(text: str) -> List[str]:
    """Sentence split that does not break on 'L. Rosenberg' or 'St. Peter'.

    [D525] The abbreviation list is the one that fix established; a splitter that
    breaks after a single capital produced a mangled name that passed nine checks.
    """
    if not text:
        return []
    protected = re.sub(
        r'\b(Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|No|cf|ed|vol|Prof|Rev|Hon|[A-Z])\.',
        lambda m: m.group(0).replace('.', '\x00'), text)
    parts = re.split(r'(?<=[.!?])\s+', protected)
    return [p.replace('\x00', '.').strip() for p in parts if p.strip()]


def corpus_roles_for_year(person: str, year: str, corpus: str) -> List[str]:
    """Which roles does the CORPUS give this (person, year) pair?

    Returns a list of role names ('birth', 'death') found in corpus sentences
    that mention both the person and the year. Empty list means the corpus says
    nothing about this pair — which is silence, not a contradiction.
    """
    if not person or not year or not corpus:
        return []
    person_f, roles = _fold(person), []
    # Match on the surname too: corpora often use 'Gautier' where the tour writes
    # 'Antoine Gautier'.
    keys = {person_f}
    parts = person_f.split()
    if len(parts) > 1:
        keys.add(parts[-1])
    for sent in split_sentences(corpus):
        sf = _fold(sent)
        if year not in sf:
            continue
        if not any(k in sf for k in keys):
            continue
        for role, markers in _ROLE_MARKERS.items():
            if any(m in sf for m in markers):
                roles.append(role)
    return sorted(set(roles))


def find_role_mismatches(tour_text: str, corpus: str) -> List[Dict]:
    """Sentences asserting a person ACTED in a year the corpus calls birth/death.

    Returns [{person, year, role, action, sentence}] — one entry per offending
    sentence. Empty list when the tour and corpus agree, or when the corpus is
    silent about the pair.
    """
    findings = []
    if not tour_text or not corpus:
        return findings
    for sent in split_sentences(tour_text):
        years = _YEAR_RE.findall(sent)
        if not years:
            continue
        sf = _fold(sent)
        action = next((a for a in _ACTION_MARKERS if re.search(rf'\b{a}\b', sf)), None)
        if not action:
            continue
        # If the sentence ITSELF states the birth/death role, it is not a
        # mismatch — 'born in 1825, he later founded...' is perfectly true.
        for person in set(_NAME_RE.findall(sent)):
            for year in set(years):
                roles = corpus_roles_for_year(person, year, corpus)
                if not roles:
                    continue
                # Does the sentence attach the year to the correct role itself?
                if any(m in sf for role in roles for m in _ROLE_MARKERS[role]):
                    continue
                findings.append({
                    'person': person, 'year': year, 'role': roles[0],
                    'action': action, 'sentence': sent,
                })
    return findings


def repair_role_mismatches(tour_text: str, corpus: str) -> Tuple[str, List[Dict]]:
    """Remove sentences that reattach a birth/death year to an action.

    **Deletion, not rewriting.** A rewrite would have to assert something, and the
    thing we know is only that the current assertion is wrong — rewriting is how a
    second fabrication gets introduced while fixing the first. Removing a sentence
    can subtract information but cannot add a falsehood.

    Returns (repaired_text, findings).
    """
    findings = find_role_mismatches(tour_text, corpus)
    if not findings:
        return tour_text, []
    out = tour_text
    for f in findings:
        s = f['sentence']
        if s in out:
            # Collapse the whitespace the removal leaves behind.
            out = out.replace(' ' + s, '', 1) if (' ' + s) in out else out.replace(s, '', 1)
            out = re.sub(r'[ \t]{2,}', ' ', out)
            f['repaired'] = True
        else:
            f['repaired'] = False
    return out, findings

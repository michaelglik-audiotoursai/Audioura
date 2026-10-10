#!/usr/bin/env python3
"""LOCAL-660 defect 3: dangling personal-pronoun opener detector and repair gate.

The companion ``dangling_demonstrative_gate`` catches a stop body that opens on
an unresolved DEMONSTRATIVE ("This move…", "These works…"). This module is its
mirror for PERSONAL pronouns.

The defect it fixes (tour 557 v7, Stop 3 "Parkman Bandstand"):

    "The Parkman Bandstand, built in 1912, is a circular, Greek Revival-style
     structure. Its columns and domed roof were designed to echo the equality of
     the public gatherings it hosts. ... His legacy is carved in the stone
     beneath your hand—a physical reminder that civic generosity can shape the
     very landscape of a city."

The sentence that INTRODUCED George Francis Parkman ("The bandstand honors
George Francis Parkman, who … left a $5 million bequest…") was moved OUT of
Stop 3 (a LEAD fix relocated the currency fact to Stop 1), so "His" in Stop 3 now
points at nobody: there is no male person named earlier in the stop. The listener
hears "His legacy" with no antecedent.

This gate walks the DELIVERED tour stop by stop and, for a sentence that OPENS
with a personal pronoun (He/His/Him/She/Her/Hers/They/Them/Their/Theirs), checks
whether a plausible antecedent — a PERSON (a capitalised multi-token name, a
title+name, or a matching-number personal pronoun) — appears EARLIER in the SAME
stop. If none does, the pronoun is dangling and the sentence is dropped.

Design choices (mirroring the demonstrative gate and the degrade path):
  * DELETION, not rewriting — a rewrite has to assert a referent we do not know.
    Dropping the orphaned sentence cannot introduce a falsehood.
  * Per-stop scope — the stop title, its field lines and its own earlier
    sentences are the antecedent search space. Field/header lines are preserved.
  * Only a sentence-INITIAL pronoun is flagged (the real defect shape); a pronoun
    anywhere later in a sentence is governed by its own clause and is left alone.
  * "They/Their/Them" can also refer to a plural COMMON noun (crowds, soldiers,
    protesters), so a plural pronoun is NOT flagged when a plural common-noun
    subject precedes it in the stop. Only He/His/Him/She/Her/Hers — which demand
    a singular PERSON — and a plural pronoun with no plausible plural referent at
    all are treated as dangling.

Pure, deterministic, idempotent.
"""
import re
from typing import List, Tuple

try:  # abbreviation-safe sentence splitting, shared with the rest of the pipeline
    from sentence_split import split_sentences as _ss_split
except Exception:  # pragma: no cover
    def _ss_split(t):
        return re.split(r'(?<=[.!?])\s+', t or '')


_STOP_HEADER_RE = re.compile(r'(?mi)^Stop\s+\d+:\s*(.+?)\s*$')
_FIELD_LINE_RE = re.compile(
    r'(?mi)^(?:Address|Coordinates|Directions|Sources|Museum Information|'
    r'Type/Specialty|Specific Examples|Operational Details|Orientation|'
    r'Visiting Hours|Opening Hours|Hours|Tour-Category):')

# A sentence that OPENS with a personal pronoun. Group 1 = the pronoun.
_PRONOUN_OPENER_RE = re.compile(
    r'^(He|His|Him|She|Her|Hers|They|Them|Their|Theirs)\b')

_MALE = {'he', 'his', 'him'}
_FEMALE = {'she', 'her', 'hers'}
_PLURAL = {'they', 'them', 'their', 'theirs'}

# Capitalised sentence-openers that are NOT names (so they do not count as a
# person antecedent when they lead an earlier sentence).
_NON_NAME_CAPS = frozenset({
    'the', 'this', 'that', 'these', 'those', 'a', 'an', 'in', 'on', 'at', 'by',
    'from', 'with', 'as', 'here', 'there', 'now', 'then', 'today', 'yet',
    'but', 'and', 'or', 'its', 'their', 'his', 'her', 'he', 'she', 'they',
    'it', 'when', 'where', 'while', 'during', 'after', 'before', 'since',
    'over', 'under', 'above', 'below', 'between', 'inside', 'outside',
    'stand', 'standing', 'look', 'notice', 'imagine', 'picture', 'walk',
    'orientation', 'directions', 'address', 'coordinates', 'stop',
    'what', 'who', 'how', 'why', 'minutes', 'years', 'decades', 'above',
    'below', 'beneath', 'built', 'designed', 'founded', 'inside',
})

# Titles that mark the word(s) after them as a person's name.
_PERSON_TITLE_RE = re.compile(
    r'\b(?:Mr|Mrs|Ms|Dr|Sir|Lord|Lady|King|Queen|Prince|Princess|President|'
    r'Governor|Mayor|Senator|Judge|Justice|Captain|Colonel|General|Reverend|'
    r'Minister|Councilor|Councillor|Councilman|Councilwoman|Attorney|Lieutenant)'
    r'\b\.?\s+[A-Z][A-Za-zà-ÿ\'\u2019\-]+')

# A multi-token capitalised name mid-sentence: "George Francis Parkman",
# "Charles Bulfinch", "Paul Revere". Requires ≥2 adjacent capitalised tokens so
# a single capitalised common/place word ("Boston", "Beacon") does not count as a
# personal antecedent on its own. Tokens are plain words (no hyphen) so a style
# term like "Greek Revival-style" is not read as a name.
_FULL_NAME_RE = re.compile(
    r'\b[A-Z][A-Za-zà-ÿ\'\u2019]+(?:\s+[A-Z][A-Za-zà-ÿ\'\u2019]+)+')

# Words that, as the FINAL token of a capitalised span, mean it is a PLACE or a
# STYLE/era label — never a personal name.
_NONPERSON_TAIL = frozenset({
    # place
    'street', 'avenue', 'road', 'hall', 'house', 'common', 'square', 'park',
    'bandstand', 'hill', 'court', 'bridge', 'river', 'city', 'state', 'station',
    'market', 'plaza', 'monument', 'building', 'dome', 'tower', 'gate', 'yard',
    'pond', 'green', 'wharf', 'harbor', 'harbour', 'island', 'museum', 'church',
    # style / era / institution
    'revival', 'style', 'era', 'period', 'order', 'war', 'party', 'company',
    'court', 'college', 'university', 'institute', 'society', 'league', 'union',
    'massacre', 'tea', 'revolution', 'bicentennial', 'commonwealth',
})

# Style/era adjective words that never belong to a person name.
_STYLE_WORD_RE = re.compile(
    r'(?i)\b(?:greek|roman|federal|gothic|baroque|georgian|colonial|victorian|'
    r'revival|neoclassical|romanesque|renaissance|brutalist|classical|modern)\b')

# A plural COMMON noun that a plural pronoun could legitimately refer to.
_PLURAL_COMMON_RE = re.compile(
    r'\b(?:crowd|crowds|mob|mobs|people|residents|citizens|colonists|'
    r'protesters|protestors|demonstrators|workers|soldiers|troops|officers|'
    r'activists|members|legislators|lawmakers|councilors|councillors|'
    r'visitors|gatherings|speakers|founders|leaders|families|students|'
    r'suffragists|abolitionists|men|women|they)\b', re.IGNORECASE)


def _has_person_antecedent(search_space: str) -> bool:
    """True when a PERSON (name, title+name) appears in ``search_space``."""
    if not search_space:
        return False
    if _PERSON_TITLE_RE.search(search_space):
        return True
    # A multi-token capitalised name. Reject spans that are a place or a
    # style/era label ("Beacon Street", "Greek Revival", "Boston Massacre") so
    # only a plausible personal name counts as a gendered-pronoun antecedent.
    for m in _FULL_NAME_RE.finditer(search_space):
        span = m.group(0)
        if _STYLE_WORD_RE.search(span):
            continue  # architectural/era style, not a person
        toks = [t for t in span.split() if t]
        low = [t.lower().strip(".,;:'\u2019") for t in toks]
        if not low:
            continue
        if low[-1] in _NONPERSON_TAIL:
            continue  # place / institution / event tail
        if all(t in _NON_NAME_CAPS or t in _NONPERSON_TAIL for t in low):
            continue
        return True
    return False


def _detect_dangling_pronoun(first_sentence: str, search_space: str) -> str:
    """Return the dangling pronoun (lowercased) when ``first_sentence`` opens on a
    personal pronoun with no plausible antecedent in ``search_space``; else ''.
    """
    s = (first_sentence or '').strip()
    m = _PRONOUN_OPENER_RE.match(s)
    if not m:
        return ''
    pron = m.group(1).lower()
    if pron in _MALE or pron in _FEMALE:
        # A gendered pronoun demands a singular PERSON antecedent.
        if _has_person_antecedent(search_space):
            return ''
        return pron
    if pron in _PLURAL:
        # A plural pronoun may point at a plural common noun OR a person.
        if _PLURAL_COMMON_RE.search(search_space) or _has_person_antecedent(search_space):
            return ''
        return pron
    return ''


def detect_dangling_pronoun_openers(stop_body: str, stop_title: str = "") -> List[dict]:
    """Find sentences in ``stop_body`` that OPEN on a dangling personal pronoun.

    A sentence is flagged when it begins with a personal pronoun and no plausible
    antecedent (person name, title+name, or — for plural pronouns — a plural
    common noun) appears EARLIER in the stop (title + preceding sentences).
    Returns [{sentence, pronoun}].
    """
    findings = []
    sentences = _ss_split(stop_body)
    preceding = stop_title or ""
    for sent in sentences:
        pron = _detect_dangling_pronoun(sent, preceding)
        if pron:
            findings.append({'sentence': sent.strip(), 'pronoun': pron})
        preceding += " " + sent
    return findings


def strip_dangling_pronoun_openers_in_text(tour_text: str) -> Tuple[str, int]:
    """Drop any narration sentence that OPENS on a personal pronoun with no
    antecedent earlier in the SAME stop. Returns ``(cleaned_text, n_dropped)``.

    Walks the delivered tour stop by stop. The antecedent search space for a
    sentence is the stop title plus every earlier spoken sentence in the stop
    (field/header lines excluded). Field and header lines are preserved verbatim.
    Deterministic and idempotent.
    """
    if not tour_text or not tour_text.strip():
        return tour_text or "", 0

    lines = tour_text.split("\n")
    header_idxs = [i for i, ln in enumerate(lines)
                   if _STOP_HEADER_RE.match(ln.strip())]
    if not header_idxs:
        return tour_text, 0

    dropped = 0
    for h, start in enumerate(header_idxs):
        end = header_idxs[h + 1] if h + 1 < len(header_idxs) else len(lines)
        title = _STOP_HEADER_RE.match(lines[start].strip()).group(1).strip()
        # Running antecedent space for THIS stop: title + prose seen so far.
        seen = title
        for li in range(start + 1, end):
            s = lines[li].strip()
            if not s or _FIELD_LINE_RE.match(s):
                continue
            sentences = _ss_split(s)
            if not sentences:
                continue
            kept = []
            line_changed = False
            for sent in sentences:
                st = sent.strip()
                pron = _detect_dangling_pronoun(st, seen)
                if pron:
                    dropped += 1
                    line_changed = True
                    # Do NOT add the dropped sentence to the antecedent space.
                    continue
                kept.append(st)
                seen += " " + st
            if line_changed:
                lines[li] = " ".join(kept).strip()

    out = "\n".join(lines)
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped


if __name__ == "__main__":  # pragma: no cover
    import sys
    t = open(sys.argv[1], encoding="utf-8").read()
    fixed, n = strip_dangling_pronoun_openers_in_text(t)
    print("dropped:", n)

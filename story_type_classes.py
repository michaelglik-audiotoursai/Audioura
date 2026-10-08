#!/usr/bin/env python3
"""story_type_classes.py — LOCAL-620 (D634): map story TYPES to the three
preference CLASSES, and tell a REAL collector/museum story from boilerplate.

Michael's ruling (D634, 2026-10-07):
  "I would not dismiss outright museum and donor sentences in favour of the
   exhibit, and let some be used to determine the user preferences. I complained
   because these were the only stories in that museum and very little about the
   paintings themselves."
He also wants stop likes/dislikes to tune the NEXT tour's story types.

Two existing taxonomies already live in the codebase, and this module is the
ONE bridge between them, with no third vocabulary invented:

  (1) work_first_evidence.classify_sentence(sentence) -> one of
        'work' | 'artist' | 'reception' | 'emotion' | 'institutional' | 'other'
      — the LOCAL-617 per-sentence STORY TYPE.

  (2) three_class_retrieval: the three PREFERENCE CLASSES the swipe engine and
      stop_metrics / user_class_prefs are keyed on:
        'details'  — what the thing physically IS (material, technique, form);
        'historic' — the thing placed in TIME (era, movement, provenance chain,
                     the artist's life and the cultural context around it);
        'social'   — the PEOPLE (who made/owned/commissioned it, patrons and
                     collectors' motives, reception, the emotional/human reading).

────────────────────────────────────────────────────────────────────────────
THE MAPPING (D634 item 1 — written down here AND in SUBMISSION_LOCAL-620.md)
────────────────────────────────────────────────────────────────────────────

  details  = work / technique
      LOCAL-617 'work' sentences — what the object shows, its composition,
      colour, light, medium, the depicted figures. The ekphrasis the listener
      stands in front of.

  historic = artist life + historical and cultural context + provenance/collector
      LOCAL-617 'artist' sentences (the maker at the moment of making — a life
      placed in time) AND the subset of institutional sentences that are a REAL
      provenance / collector STORY (a named collector, a motive, a consequence —
      the chain of time by which the work reached the wall).

  social   = people / patrons / collectors' motives / reception / emotion
      LOCAL-617 'reception' (what a named critic/historian/contemporary said) and
      'emotion' (the felt, human reading) — the people around the work and the
      human response to it. A collector/patron sentence whose point is the
      PERSON and their MOTIVE (not merely the transfer of title) is social too.

  The LOCAL-617 'institutional' type therefore SPLITS by whether it is a real
  story:
    • a real collector/provenance story (named person + motive/consequence) is
      a LEGITIMATE type — 'historic' when it is the chain-of-ownership/when, or
      'social' when the point is the collector/patron as a person and their
      motive;
    • pure BOILERPLATE (renovation budgets, square metres, opening hours,
      founding-date-only, mission statements) is NOT a story and stays filtered
      (``is_boilerplate_institutional``) — it maps to no class and must never
      become narration or a preference signal.

  'other' maps to no class (it carries no preference signal).

This module is PURE (no network, no LLM, no DB) so every rule is unit-testable
and cannot drift at runtime. It is the single place the swipe engine's three
classes meet the narration pipeline's story types.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from three_class_retrieval import CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL
import work_first_evidence as wfe

__all__ = [
    "STORY_TYPE_TO_CLASS",
    "map_story_type_to_class",
    "classify_sentence_class",
    "is_real_collector_story",
    "is_boilerplate_institutional",
    "classify_segment_class",
    "paragraph_class_distribution",
    "stop_class_vector",
]

# ─────────────────────────────────────────────────────────────────────────────
# The base map from the LOCAL-617 story types to the three preference classes.
# The 'institutional' type is deliberately absent here: it is resolved at the
# sentence level by ``classify_sentence_class`` (real story → historic/social;
# boilerplate → None/filtered). 'other' is absent: it carries no signal.
# ─────────────────────────────────────────────────────────────────────────────
STORY_TYPE_TO_CLASS: Dict[str, str] = {
    "work": CLASS_DETAILS,       # what the object physically shows / technique
    "artist": CLASS_HISTORIC,    # the maker's life placed in time
    "reception": CLASS_SOCIAL,   # what people said about it
    "emotion": CLASS_SOCIAL,     # the human / felt reading
}


def map_story_type_to_class(story_type: str) -> Optional[str]:
    """Map a LOCAL-617 story type to a preference class, or None when it carries
    no preference signal.

    Deterministic. 'institutional' returns None here because an institutional
    sentence must be resolved WITH its text (a real collector story is historic
    or social; boilerplate is filtered) — use ``classify_sentence_class`` for a
    sentence, which handles that split. 'other' and unknown types return None.
    """
    return STORY_TYPE_TO_CLASS.get((story_type or "").strip().lower())


# ─────────────────────────────────────────────────────────────────────────────
# REAL collector/museum STORY vs BOILERPLATE.
#
# D634: a collector/donor sentence that is a REAL STORY — a named person, a
# motive, a consequence — is a legitimate type (the only stories some museums
# have about their own holdings). Pure boilerplate — renovation budgets, square
# metres, opening hours, a bare founding date, a mission statement — is not a
# story and stays filtered.
# ─────────────────────────────────────────────────────────────────────────────

# A named human actor: a capitalised multi-word name, or a possessive/role noun
# that points at a specific person (collector, donor, patron, benefactor…).
_NAMED_PERSON_RE = re.compile(
    r"(?:\b[A-ZÀ-Þ][a-zà-ÿ]+(?:\s+(?:van|von|de|della|del|di|du|des|der|la|le)\b)?"
    r"\s+[A-ZÀ-Þ][a-zà-ÿ]+)"            # First Last (optionally with a particle)
)
_PERSON_ROLE_RE = re.compile(
    r"(?i)\b(collector|donor|benefactor|patron|philanthropist|industrialist|"
    r"banker|merchant|baron|baroness|count|countess|widow|heir|heiress|"
    r"connoisseur|dealer)\b")

# A MOTIVE / human reason behind the gift or acquisition — the "why".
_MOTIVE_RE = re.compile(
    r"(?i)\b(in memory of|in honou?r of|to honou?r|as a tribute|out of|"
    r"wished|wanted|hoped|believed|so that|in order that|to ensure|"
    r"to share|to give the public|for the people of|to found|dreamed of|"
    r"devoted|passion for|love of|fascinat|determined to|vowed|"
    r"could not bear to|refused to|insisted)\b")

# A CONSEQUENCE / outcome of the act — the "what happened".
_CONSEQUENCE_RE = re.compile(
    r"(?i)\b(became the (?:core|heart|foundation|nucleus)|formed the|"
    r"transformed|made possible|allowed the museum to|opened the|"
    r"saved|rescued|preserved for|would become|grew into|"
    r"thanks to (?:this|which)|as a result|this is why|which is how)\b")

# Pure BOILERPLATE markers — money/building/hours/mission/bare-founding that is
# NOT a story even when it mentions the institution. These stay filtered.
_BOILERPLATE_RE = re.compile(
    r"(?i)\b("
    r"renovat(?:ed|ion)|refurbish|expansion|wing\s+(?:was|opened)|"
    r"budget|million\s+(?:euro|dollar|pound)|\u20ac\s?\d|\$\s?\d|£\s?\d|"
    r"square\s+(?:feet|metres|meters)|\d+\s*(?:m²|square)|"
    r"opening\s+hours|admission|ticket|open\s+(?:daily|from|tuesday|"
    r"monday|wednesday)|closed\s+on|free\s+of\s+charge|"
    r"non-?profit|501\(c\)|mission\s+(?:of|is|to)|the\s+museum'?s?\s+mission|"
    r"accredited|governed\s+by|board\s+of\s+(?:directors|trustees)"
    r")\b")

# A bare founding/establishment statement with no human story around it.
_BARE_FOUNDING_RE = re.compile(
    r"(?i)\b(founded|established|opened|inaugurated)\b.*\b(in\s+\d{3,4}|"
    r"\d{3,4})\b")


def is_boilerplate_institutional(sentence: str) -> bool:
    """True when an institutional sentence is pure BOILERPLATE (renovation
    budgets, square metres, opening hours, bare founding date, mission prose) —
    not a story. Boilerplate maps to no class and stays filtered.
    """
    s = (sentence or "").strip()
    if not s:
        return True
    if _BOILERPLATE_RE.search(s):
        # money/building/hours/mission is boilerplate even if a name appears.
        return True
    # A bare founding/opening date with no motive and no named person is boilerplate.
    if _BARE_FOUNDING_RE.search(s) and not (_MOTIVE_RE.search(s)
                                            or _NAMED_PERSON_RE.search(s)):
        return True
    return False


def is_real_collector_story(sentence: str, work_subject: str = "") -> bool:
    """True when an institutional/provenance sentence is a REAL STORY (D634).

    A real collector/museum story has a named human actor (a person or a role
    like 'collector'/'donor'/'patron') AND at least one of a MOTIVE or a
    CONSEQUENCE — the "who", the "why", the "what happened". A bare transfer of
    title ("acquired by the museum in 1905") is NOT a story; boilerplate is NOT
    a story.

    This is the test that lets a collector sentence COUNT as a legitimate type
    (historic or social) instead of being dismissed as noise.
    """
    s = (sentence or "").strip()
    if not s:
        return False
    if is_boilerplate_institutional(s):
        return False
    has_person = bool(_NAMED_PERSON_RE.search(s) or _PERSON_ROLE_RE.search(s))
    if not has_person:
        return False
    return bool(_MOTIVE_RE.search(s) or _CONSEQUENCE_RE.search(s))


def _collector_story_class(sentence: str) -> str:
    """Resolve a REAL collector story to 'social' or 'historic'.

    Social when the point is the PERSON and their MOTIVE (a patron's wish, a
    collector's passion, a dedication in someone's memory). Historic when the
    point is the chain of ownership / when it entered the collection (a motive is
    absent but a consequence places it in time).
    """
    s = sentence or ""
    if _MOTIVE_RE.search(s) or _PERSON_ROLE_RE.search(s):
        return CLASS_SOCIAL
    return CLASS_HISTORIC


def classify_sentence_class(sentence: str,
                            venue_tokens: Optional[Sequence[str]] = None,
                            work_subject: str = "") -> Optional[str]:
    """Classify ONE sentence into a preference class, or None when it carries no
    signal (pure boilerplate, or 'other').

    Pipeline:
      1. classify the story TYPE with the LOCAL-617 classifier;
      2. work/artist/reception/emotion → the mapped class directly;
      3. institutional →
           • a REAL collector story → social or historic (a legitimate type);
           • boilerplate / bare transfer → None (filtered, no signal);
      4. 'other' / unknown → None.
    """
    s = (sentence or "").strip()
    if not s:
        return None
    stype = wfe.classify_sentence(s, venue_tokens=venue_tokens,
                                  work_subject=work_subject)
    mapped = map_story_type_to_class(stype)
    if mapped is not None:
        return mapped
    if stype == "institutional":
        if is_real_collector_story(s, work_subject=work_subject):
            return _collector_story_class(s)
        return None  # boilerplate / bare transfer — filtered
    return None


# ``classify_segment_class`` is the paragraph-level entry point: a delivered
# story SEGMENT (a paragraph) is classified by the dominant class of its
# sentences, so the delivered-text tagger (D634 item 3) can label each paragraph.
def classify_segment_class(segment: str,
                           venue_tokens: Optional[Sequence[str]] = None,
                           work_subject: str = "") -> Optional[str]:
    """Return the dominant preference class of a story SEGMENT (paragraph), or
    None when the segment carries no class signal at all.

    Each sentence is classified; the class with the most sentences wins. Ties
    break details > historic > social only to be deterministic (the order the
    swipe engine lists them). A segment of pure boilerplate/other returns None.
    """
    dist = paragraph_class_distribution(segment, venue_tokens=venue_tokens,
                                        work_subject=work_subject)
    counts = dist.get("_counts", {})
    total = sum(counts.values())
    if total == 0:
        return None
    order = [CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL]
    return max(order, key=lambda c: (counts.get(c, 0), -order.index(c)))


def paragraph_class_distribution(paragraph: str,
                                 venue_tokens: Optional[Sequence[str]] = None,
                                 work_subject: str = "") -> Dict[str, float]:
    """Return the normalised class distribution of a paragraph's sentences.

    {'details': f, 'historic': f, 'social': f} summing to 1.0 over the SIGNAL
    sentences (boilerplate/other sentences are ignored). Also returns a private
    '_counts' dict of raw per-class sentence counts for ``classify_segment_class``.
    When the paragraph carries no signal sentence at all, the distribution is a
    neutral third each and _counts are zero.
    """
    sents = wfe.split_sentences(paragraph or "")
    counts = {CLASS_DETAILS: 0, CLASS_HISTORIC: 0, CLASS_SOCIAL: 0}
    for s in sents:
        c = classify_sentence_class(s, venue_tokens=venue_tokens,
                                    work_subject=work_subject)
        if c in counts:
            counts[c] += 1
    total = sum(counts.values())
    if total == 0:
        return {CLASS_DETAILS: 0.333, CLASS_HISTORIC: 0.334,
                CLASS_SOCIAL: 0.333, "_counts": counts}
    dist = {k: round(v / total, 3) for k, v in counts.items()}
    dist["_counts"] = counts
    return dist


def stop_class_vector(body: str,
                      venue_tokens: Optional[Sequence[str]] = None,
                      work_subject: str = "") -> Dict[str, float]:
    """Return the stop-level class distribution for a delivered stop BODY.

    This is what gets written to ``stop_metrics.class_details/historic/social``
    for a delivered stop (D634 item 3): the fraction of the stop's SIGNAL
    sentences in each class, computed deterministically from the delivered text
    (no LLM). Values sum to 1.0 when any signal is present, else a neutral third
    each. The private '_counts' key from ``paragraph_class_distribution`` is
    dropped so the result is exactly the three class keys.
    """
    dist = paragraph_class_distribution(body, venue_tokens=venue_tokens,
                                        work_subject=work_subject)
    return {CLASS_DETAILS: dist[CLASS_DETAILS],
            CLASS_HISTORIC: dist[CLASS_HISTORIC],
            CLASS_SOCIAL: dist[CLASS_SOCIAL]}

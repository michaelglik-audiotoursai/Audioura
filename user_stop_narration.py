#!/usr/bin/env python3
"""user_stop_narration.py — LOCAL-855.

A user-CHOSEN stop (``user_explicit`` / ``_anchor``) is a specific NAMED VENUE the
listener typed, usually with a Google-Maps share link or a website. Its narration
must be ABOUT that venue — what it is, what to notice there — and nothing else.

The field-test Sophia tour (LOCAL-852's own 7/7 reproduction, HCMC) showed the
narration ignored the venue and ran off the name's dictionary meaning or filled
the stop with unrelated regional history:

  * "Rambutan" (Type: Restaurant and Bar) was narrated as rambutan TREES shading
    the pavement, then the Long Thanh airport construction project.
  * "Longan" (Type: Bar) was narrated as "this street, named Longan", a Mekong
    dragon legend, then the Cần Thơ 2025 provincial merger.
  * "A Star is Born" (Type: Karaoke Bar) got Hồ Chí Minh's pseudonyms and
    "precise names and works remain elusive" — an admission there was no material,
    padded to a paragraph anyway.

Two root causes, both fixed here as deterministic prompt blocks:

  1. SUBJECT BINDING (defect 1). The stop's own Type/Specialty line already knows
     "Rambutan" is a bar and "Longan" is a bar — that metadata is generated before
     the body. ``user_stop_subject_block`` injects the venue identity (name +
     Type/Specialty + the user's link/Places examples) into the body prompt and
     forbids narrating the literal meaning of the NAME (the fruit, the dragon) or
     treating the name as a street/landmark. The narration is about the VENUE.

  2. SAY-LESS-WHEN-THIN (defect 3, defect 4). With no retrieved material about a
     small private venue, a short honest stop (what it is, what to notice) beats a
     paragraph of unrelated history. The block removes the length floor for a
     thin user stop and forbids (a) padding with regional/national history that
     does not name the venue and (b) any DATED claim about the venue that is not
     grounded in a retrieved source naming it.

These blocks are pure strings; they add instructions to the existing body prompt
and never call the network or an LLM themselves.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

__all__ = [
    "is_user_stop",
    "has_sourced_material",
    "user_stop_subject_block",
    "venue_kind_words",
    "scrub_user_stop_body",
]


def _fold(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped.lower())
    return " ".join(stripped.split())


def is_user_stop(poi: Dict) -> bool:
    """True when ``poi`` is a stop the listener chose by hand (user_explicit or an
    anchor from an 'X from Y' request)."""
    return bool(isinstance(poi, dict)
                and (poi.get("user_explicit") or poi.get("_anchor")))


def has_sourced_material(poi: Dict, outdoor_facts=None) -> bool:
    """True when there is RETRIEVED material naming this venue to narrate from —
    outdoor/retrieval facts, a customer-voice block, or practicals sourced from
    Places/Serper. When false, the stop is "thin": say less, stay on the venue."""
    if outdoor_facts:
        return True
    if not isinstance(poi, dict):
        return False
    for key in ("_customer_voice", "_practicals", "_lore", "_research",
                "retrieval_facts"):
        if poi.get(key):
            return True
    return False


# Venue-type words that name the KIND of place the venue is. When the stop's
# Type/Specialty carries one, the narration must treat the stop as that kind of
# venue, not as the literal thing its name spells.
_VENUE_KIND_WORDS = {
    "bar", "pub", "club", "lounge", "restaurant", "cafe", "coffee", "bistro",
    "diner", "eatery", "grill", "karaoke", "nightclub", "brewery", "taproom",
    "spa", "salon", "massage", "wellness", "studio", "gym", "shop", "store",
    "boutique", "market", "gallery", "bakery", "patisserie", "teahouse",
    "izakaya", "tavern", "speakeasy", "hotel", "hostel", "venue",
}


def venue_kind_words(type_specialty: str) -> set:
    """The venue-kind words present in a Type/Specialty label (folded)."""
    if not type_specialty:
        return set()
    toks = set(_fold(type_specialty).split())
    return toks & _VENUE_KIND_WORDS


def user_stop_subject_block(poi: Dict, location: str = "",
                            outdoor_facts=None) -> str:
    """Prompt block that binds a user stop's narration to the VENUE it names.

    Returns "" for a non-user stop (so the normal path is unchanged). For a user
    stop it returns a block that:

      * states the venue's name and, when known, its Type/Specialty and the
        listener's own examples, as the SUBJECT of the stop;
      * forbids narrating the literal/dictionary meaning of the name (the fruit
        "rambutan"/"longan", a dragon legend) or treating the name as a street or
        natural feature when the venue is a bar/spa/shop/etc.;
      * forbids padding a thin stop with regional or national history that does
        not name the venue (airport projects, provincial mergers, war offensives,
        national-figure biographies);
      * forbids any DATED claim about the venue not grounded in a retrieved source
        that names the venue.
    """
    if not is_user_stop(poi):
        return ""
    name = (poi.get("name") or poi.get("title") or "").strip()
    type_specialty = (poi.get("type_specialty") or "").strip()
    examples = (poi.get("specific_examples") or "").strip()
    kinds = venue_kind_words(type_specialty)

    lines = [
        "\n\nUSER-CHOSEN VENUE — narrate THE VENUE, not the name (critical):",
        f'This stop is a specific place the listener chose by name: "{name}".',
    ]
    if type_specialty:
        lines.append(
            f'It is a {type_specialty}. Narrate it as that venue — its character, '
            f'what a visitor notices on arriving, what it is known for.')
    if examples:
        lines.append(f'What to expect there: {examples}.')
    if kinds:
        kind_label = ", ".join(sorted(kinds))
        lines.append(
            f'"{name}" is the NAME of this {kind_label}. Do NOT narrate the '
            f'literal or dictionary meaning of the name: it is not a fruit, a '
            f'tree, a plant, a street, a river, a legend, or a historical figure '
            f'— it is the {kind_label} the listener is standing at. Never say the '
            f'street/place "is named {name}".')
    else:
        # The Type/Specialty may be missing or unreliable for a small venue, but
        # it is still a named VENUE the listener chose — never the dictionary word.
        lines.append(
            f'"{name}" is the NAME of a specific business/venue at this spot. Do '
            f'NOT narrate the literal or dictionary meaning of the name: not the '
            f'fruit, tree, plant, animal, street, river, legend, or historical '
            f'figure the word may denote. Do NOT present it as a fruit stall, '
            f'market, or natural feature unless the sourced facts explicitly say '
            f'so. Never say the street/place "is named {name}".')
    lines.append(
        "STAY ON THE VENUE: every sentence must be about THIS place or its "
        "immediate surroundings as a visitor experiences them. Do NOT fill the "
        "stop with regional or national history that does not name this venue — "
        "no airport or infrastructure projects, no provincial/administrative "
        "boundary changes, no war or military campaigns, no national-figure "
        "biographies. If you have little to say about the venue, say less: a "
        "short, honest stop (what it is, what to notice) is correct and complete.")
    lines.append(
        "NO UNSOURCED DATED CLAIMS: do NOT state a founding year, an opening "
        "date, a dated event, a performer/person who appeared here, or an address "
        "on a specific street unless it is given in the sourced facts below that "
        "name this venue. If the sources do not supply it, do not invent it — "
        "describe the venue in the present instead.")
    if not has_sourced_material(poi, outdoor_facts):
        lines.append(
            "NO SOURCED HISTORY IS AVAILABLE for this venue. Keep this stop SHORT "
            "(2-4 sentences): say what kind of place it is and what a visitor "
            "notices on arriving. Do NOT write a history paragraph, do NOT reach "
            "for the city's or country's history to fill space, and do NOT admit "
            "in the text that details are 'elusive' or 'unknown' — simply say "
            "less.")
    return "\n".join(lines) + "\n"


# ─── post-generation relevance scrub (defects 3 & 4) ──────────────────────────
#
# The story-research step seeks stories for a stop by its NAME, and for a bar
# named "Rambutan" / "Longan" it surfaces fruit/legend + regional history
# (Long Thanh Airport, the Cần Thơ 2025 merger, the 1975 offensive). That
# material then feeds the body as if it were sourced, so the prompt block alone
# does not always stop it. This is the LOCAL-802 relevance gate applied to a user
# stop's DELIVERED narration: a sentence that names NONE of the venue, its place,
# or its venue-kind AND carries an off-topic marker (a far-away place, an
# infrastructure/administrative/military/national-figure topic, OR a dated claim)
# is dropped. Pure and deterministic.

_OFF_TOPIC_MARKER_RE = re.compile(
    r"(?i)\b("
    r"airport|provinces?|municipality|resolution\s+no\.?|national\s+assembly|"
    r"offensive|army|military|campaign|troops|regiment|annexed|merged\s+"
    r"(?:into|with)|population\s+(?:of\s+)?(?:nearing|near|approximately)?\s*"
    r"[\d,]{5,}|centrally-governed|administrative|census|"
    r"born\s+(?:nguy|in)\b|pseudonyms?"
    r")\b")

# A dated claim (a specific year or full date) is only allowed when the sentence
# also names the venue; otherwise it is an unsourced dated claim about something
# else. A bare century reference ("19th century") is not flagged.
_DATED_CLAIM_RE = re.compile(
    r"\b(1[0-9]{3}|20[0-2][0-9])\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}\b", re.IGNORECASE)


def _split_sentences(text: str):
    try:
        from sentence_split import split_sentences as _shared
        return _shared(text or "")
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip())
                if s.strip()]


def scrub_user_stop_body(text: str, poi: Dict, location: str = "",
                         log=None):
    """[LOCAL-855 defects 3/4] Drop off-topic / unsourced-dated sentences from a
    USER stop's delivered body. Returns ``(scrubbed, dropped)``.

    A sentence is dropped when it mentions NONE of the venue name, its place/city,
    or its venue-kind words, AND it either carries an off-topic marker (a far-away
    place, an infrastructure/administrative/military/national-figure topic) OR a
    dated claim (a specific year / full date). On-topic sentences, and any
    sentence that names the venue, are kept. Never empties the body: if every
    sentence would be dropped, the text is returned unchanged (the prompt-level
    short-stop instruction is the primary control). Only runs for user stops.
    """
    if not is_user_stop(poi) or not text or not text.strip():
        return text, []

    name = poi.get("name") or poi.get("title") or ""
    type_specialty = poi.get("type_specialty") or ""
    # On-topic anchor tokens: distinctive venue-name words, venue-kind words, and
    # the city/place tokens (so a sentence grounding the listener in the city is
    # kept). Generic/stop words are excluded so they never falsely anchor.
    anchors = set()
    for w in _fold(name).split():
        if len(w) >= 3:
            anchors.add(w)
    anchors |= venue_kind_words(type_specialty)
    for w in _fold(type_specialty).split():
        if len(w) >= 3:
            anchors.add(w)
    # City tokens (e.g. "ho chi minh") keep an orientation sentence on-topic.
    for w in _fold(location).split():
        if len(w) >= 3 and w not in ("city", "vietnam", "tour"):
            anchors.add(w)

    # [LOCAL-855 defect 4] A dated claim about a user venue must be grounded in a
    # RETRIEVED source naming the venue. The narration writer produces dates from
    # its training data, never from per-sentence retrieval, so a specific year or
    # full date in a user-stop body ("emerged in 2016", "VietPride 2018", "Bức
    # Tường performed here in 2015", "as of 2024 … population") is an unsourced
    # claim about the venue — exactly the fabrication class the ticket says to
    # drop. Every dated sentence in a user-stop body is dropped; the venue's name
    # appearing in the sentence does not ground the date. A bare century
    # ("19th century") is not a dated claim and is kept.

    kept, dropped = [], []
    for sent in _split_sentences(text):
        sfold = _fold(sent)
        stoks = set(sfold.split())
        on_topic = bool(stoks & anchors)
        off_marker = bool(_OFF_TOPIC_MARKER_RE.search(sent))
        dated = bool(_DATED_CLAIM_RE.search(sent))
        if dated:
            # Ungrounded dated claim about a user venue — always dropped.
            dropped.append(sent)
            if log:
                log(f"[LOCAL-855] unsourced dated claim dropped ({name!r}): "
                    f"{' '.join(sent.split()[:8])}…")
        elif (not on_topic) and off_marker:
            dropped.append(sent)
            if log:
                log(f"[LOCAL-855] off-venue sentence dropped ({name!r}): "
                    f"{' '.join(sent.split()[:8])}…")
        else:
            kept.append(sent)
    if not kept:
        return text, []
    if not dropped:
        return text, []
    return " ".join(kept).strip(), dropped

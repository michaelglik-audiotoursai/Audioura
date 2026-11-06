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

from text_polish import apply_orphan_rule, city_from_scope  # [LOCAL-860]

__all__ = [
    "is_user_stop",
    "has_sourced_material",
    "has_dated_source",
    "user_stop_subject_block",
    "venue_kind_words",
    "scrub_user_stop_body",
    "scrub_offpin_landmarks",
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
                "retrieval_facts", "_wiki_evidence"):
        if poi.get(key):
            return True
    return False


def has_dated_source(poi: Dict, outdoor_facts=None) -> bool:
    """[LOCAL-855B defect 8] True when there is a RETRIEVED/RESEARCH source that
    could carry a DATE about this venue — outdoor/retrieval facts, research, or
    causal-chain lore. Deliberately NARROWER than ``has_sourced_material``: a
    customer-voice block ("great vibe") or a practicals block (hours/price) is
    real material about the venue but never sources a founding year or a dated
    event, so a dated claim riding on customer voice alone is still unsourced and
    is dropped (the Thi Bar VietPride-2018 fabrication). A famous stop with
    retrieved facts ("Notre-Dame … built 1863–1880") keeps its dates.
    """
    if outdoor_facts:
        return True
    if not isinstance(poi, dict):
        return False
    for key in ("_lore", "_research", "retrieval_facts", "_wiki_evidence"):
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


def grounded_user_stop_body(poi: Dict, location: str = "") -> str:
    """[LOCAL-855B bounce] Build a deterministic, GROUNDED 2–4 sentence body for a
    thin user stop from ONLY what is known: the venue NAME, its Type/Specialty,
    the listener's own ``specific_examples``, and the district/address if present.

    This is the ticket's own prescription for defect 4 ("Write 2–4 sentences from
    what IS known — the resolved Places data (name, kind, address/district, what
    it offers), what to notice on arrival — and stop"). It is used as the
    REPLACEMENT when the per-sentence scrub would otherwise leave a thin user
    stop with NO surviving sentence — i.e. when the LLM body was fabrication end
    to end (a dragon legend, an invented discovery anecdote, a wrong-place
    description). It states no date, no anecdote, no legend, no history, no
    landmark — so it can never carry any of the ten defects. Deterministic,
    offline; never raises.
    """
    name = (poi.get("name") or poi.get("title") or "").strip()
    type_specialty = (poi.get("type_specialty") or "").strip()
    examples = (poi.get("specific_examples") or "").strip()
    # A human district/address fragment, when the stop carries one.
    district = ""
    addr = (poi.get("address") or "").strip()
    if addr:
        # [LEAD 855D review] never take a "Label: value" line or a bare number as a district.
        parts = [p.strip() for p in addr.split(",")
                 if p.strip() and ":" not in p and not re.fullmatch(r"[\d.\s/-]+", p.strip())]
        # Prefer a "District N" / "Quận N" fragment, else the second-to-last part.
        for p in parts:
            if re.search(r"(?i)\b(?:district|qu[ậa]n)\b", p):
                district = p
                break
        if not district and len(parts) >= 2:
            district = parts[-2]

    if not name:
        return ""

    sentences = []
    # (1) What it is + where. When the Type/Specialty is known, name the kind
    # ("Longan is a bar in District 1"); when it is not, do NOT fabricate a kind —
    # say it is the place the listener chose, with correct grammar (the earlier
    # "is a the place the listener chose" glitch came from prefixing an article to
    # a phrase that already carries one).
    if type_specialty:
        kind = type_specialty
        if district:
            sentences.append(
                f"{name} is {_article(kind)} {kind.lower()} here in {district}.")
        else:
            where = city_from_scope(location) if location else ""
            if where:
                sentences.append(
                    f"{name} is {_article(kind)} {kind.lower()} in {where}.")
            else:
                sentences.append(f"{name} is {_article(kind)} {kind.lower()}.")
    else:
        if district:
            sentences.append(
                f"{name} is one of the places you chose, here in {district}.")
        else:
            where = city_from_scope(location) if location else ""
            if where:
                sentences.append(
                    f"{name} is one of the places you chose, here in {where}.")
            else:
                sentences.append(f"{name} is one of the places you chose.")
    # (2) What it offers — the listener's own examples, when present.
    if examples:
        ex = examples.rstrip(".")
        sentences.append(f"It is known for {ex[0].lower() + ex[1:]}.")
    # (3) What to notice on arrival — a neutral, true observation.
    sentences.append(
        "Take a moment at the entrance to get your bearings before you go in.")
    return " ".join(sentences).strip()


def _article(word: str) -> str:
    w = (word or "").strip().lower()
    return "an" if w[:1] in "aeiou" else "a"


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

# [LOCAL-855B] ART-PROVENANCE digression — ALWAYS-drop. A famous artwork "now
# housed at" / "in the collection of" a museum, an "oil painting"/"canvas" the
# venue did not make. The delivered Crazy-street body wandered into Caillebotte's
# "Paris Street; Rainy Day" at the Art Institute of Chicago. This is dropped even
# when the sentence looks on-topic, because the painting's TITLE ("Paris Street")
# can itself contain a venue-class word ("street") and falsely anchor.
# [LOCAL-855B] ADMINISTRATIVE-GEOGRAPHY digression — ALWAYS-drop. A province
# merger, a "the Nth largest … city", "centrally governed/-governed", a million-
# scale population — the kind of encyclopedia geography the story arm pulls in on
# a venue NAME. Dropped even when the venue is named in the sentence (the Longan
# body said "Longan's name also anchors you in the wider story of Cần Thơ, the
# third largest centrally governed city … over 4.1 million people"), because a
# bar/shop/street is never about a province's administrative status.
_ADMIN_GEOGRAPHY_RE = re.compile(
    r"(?i)("
    r"\bcentrally[- ]governed\b|"
    r"\b(?:largest|biggest|most\s+populous)\b[^.]{0,40}\bcity\b|"
    r"\b\d(?:[\d.,]*)\s*million\s+(?:people|residents|inhabitants)\b|"
    r"\bpopulation\s+(?:of\s+|surpassing\s+|exceeding\s+|nearing\s+|over\s+|above\s+)?"
    r"[\d.,]+\s*million\b|"
    # population written out ("population of 4,199,824", "4,199,824 as of 2024")
    # [LOCAL-862] a comma-grouped number is a population figure UNLESS it counts
    # reviews/ratings/followers ("4.4 out of 5 from about 28,000 reviews" is the
    # venue's sourced Google record, not encyclopedia geography).
    r"\bpopulation\s+(?:of\s+)?[\d.,]{4,}\b|\b[\d]{1,3}(?:,\d{3}){1,}\b"
    r"(?!\s+(?:Google\s+|TripAdvisor\s+)?(?:reviews?|ratings?|followers|likes|"
    r"visitors\s+on\s+Google))|"
    r"\bmerg(?:ed|ing)\s+(?:into|with)\b|\bprovinces?\s+into\b|"
    r"\bnational\s+assembly\b|\bresolution\s+no\.?\b|"
    # administrative reorganization / ward-commune counts / annexation into a city
    r"\breorganization\b|\breorganis(?:ed|ation)\b|\bwards?\s+and\s+communes?\b|"
    r"\bcommunes?\s+to\s+\d|\bbecame\s+part\s+of\s+[A-ZÀ-Ỹ][\w ]*\bcity\b|"
    r"\bexpanded\s+the\s+city'?s\b|\badministrative\s+(?:unit|division|boundar)\w*\b|"
    r"\bnew\s+boundaries\b|\bshifting\s+borders\b|\bexpanded\s+region\b|"
    r"\bembraces\s+its\s+new\b|\bshifting\s+lines?\s+of\s+governance\b|"
    # [LOCAL-855B bounce] An Spa's pin is District 3, but the body relocated it to
    # Hồ Tràm BEACH ~100 km away: "near Hồ Tràm, a coastal commune now part of Ho
    # Chi Minh City's sprawling new wards", "the slower rhythms of coastal life
    # just a hundred kilometers southeast of Saigon", "a former part of Xuyên Mộc
    # district in Bà Rịa–Vũng Tàu province". A venue is at its PIN — a sentence
    # that places it a measured distance from the city, by the sea, or in another
    # commune/province is off-pin fabrication, dropped regardless of sourcing.
    r"\bsprawling\s+new\s+wards?\b|\bnew\s+wards?\b|\bcoastal\s+(?:commune|town|life|village)\b|"
    r"\bformer\s+part\s+of\b|\bXuy[êe]n\s+M\w+\b|\bB[àa]\s+R[ịi]a\b|\bV[ũu]ng\s+T[àa]u\b|"
    r"\bH[ồo]\s+Tr[àa]m\b|"
    r"\b(?:a\s+)?(?:hundred|dozens?|tens?|\d{1,3})\s+kilomet(?:er|re)s?\s+"
    r"(?:south|north|east|west|southeast|southwest|northeast|northwest)"
    r"(?:east|west)?\b|"
    r"\b\d{1,3}\s*km\s+(?:south|north|east|west|from)\b|"
    # Infrastructure project the venue is not part of ("… the government approved
    # the construction of Long Thanh International Airport …") — ALWAYS-drop even
    # when the sentence also names the venue (it rode in on a "just as … the venue
    # reflects …" comparison that falsely anchored on-topic).
    r"\bairport\b|\bgovernment\s+approved\b|\bunder\s+construction\b|"
    r"\bconstruction\s+of\b"
    r")")

# [LOCAL-855B] NATIONAL-FIGURE BIOGRAPHY — ALWAYS-drop. "Hồ Chí Minh, born
# Nguyễn Sinh Cung, whose life stretched from 1890 to 1969 … pseudonyms …", "the
# revolutionary … Democratic Republic in 1945". The city is NAMED for the figure,
# so the city tokens ("ho chi minh") falsely anchor the biography as on-topic —
# it must drop regardless. A small venue is never about a national figure's life.
_NATIONAL_FIGURE_RE = re.compile(
    r"("
    # "born <Proper Name>" — CASE-SENSITIVE on the name so "A Star is Born is
    # known…" does not match (the (?i) flag used to let [A-Z] match the lowercase
    # "is", firing on the venue's own name). Require lowercase "born" then a real
    # capitalised given name.
    r"\bborn\s+[A-ZÀ-Ỹ][a-zà-ỹ]+|"
    r"(?i:\bpseudonyms?\b|\bthe\s+revolutionary\b|"
    r"\bdemocratic\s+republic\b|\bwhose\s+life\s+(?:stretched|spanned)\b|"
    r"\bfounding\s+father\b|\bnational\s+hero\b|"
    r"\bhis\s+life\s+(?:stretched|spanned)\b)"
    r")")

# [LOCAL-855B] MILITARY-HISTORY digression — ALWAYS-drop. The war history the
# story arm attaches to a nightlife street. Robust to rephrasing: offensive /
# campaign / battlefield / an army, the capture or fall of a named place, an
# "attack launched", a strategic withdrawal — a bar/spa/street is never about it,
# even when it names the venue.
_MILITARY_RE = re.compile(
    r"(?i)("
    r"\boffensive\b|\bbattlefield\b|\bpeople'?s\s+army\b|"
    r"\bmilitary\s+(?:advance|campaign|operation|force)s?\b|\bcampaign\b|"
    r"\btroops\b|\bregiment\b|\barmy\s+of\b|\bwar\s+(?:broke|began|effort)\b|"
    r"\bcaptur(?:ed|ing)\s+[A-ZÀ-Ỹ]|\bfall\s+of\s+[A-ZÀ-Ỹ]|"
    r"\bseized\s+(?:the\s+)?(?:city|province|town)\b|\bwithdrawals?\b|"
    r"\bstrategic(?:ally)?\s+withdr|\bBuôn\s+Ma\s+Thu|"
    r"\battack\s+was\s+launched\b|\blaunched\s+(?:an?\s+)?(?:attack|offensive|assault)\b|"
    r"\bSouth\s+Vietnam(?:ese)?\b|\bNorth\s+Vietnam(?:ese)?\b|\bhighlands\b"
    r")"
    , re.IGNORECASE)

_ART_PROVENANCE_RE = re.compile(
    r"(?i)\b("
    r"housed\s+at|in\s+the\s+collection\s+of|oil\s+painting|on\s+canvas|"
    r"art\s+institute|museum\s+of\s+(?:modern\s+)?art|"
    r"now\s+(?:housed|held|kept)\s+(?:at|in)|"
    # [LOCAL-855B bounce] The delivered Crazy-street body dropped the explicit
    # "Art Institute of Chicago" provenance but KEPT the painter: "the layered
    # urban fabric Caillebotte studied", "The canvas painstakingly plots
    # architectural lines". A famous PAINTER's surname and the art vocabulary of
    # a painting (canvas / brushwork / composition / a verb of painting /
    # "<painter> studied/painted/depicted") is an art digression for a small
    # bar/spa/street, never its own content. Robust to rephrasing: match the art
    # vocabulary itself, not a fixed sentence shape.
    r"\bthe\s+canvas\b|\bbrushwork\b|\bthe\s+composition\b|\bchiaroscuro\b|"
    r"\bimpressionis\w+|\bpost-?impressionis\w+|"
    r"\b(?:Caillebotte|Monet|Manet|Renoir|Degas|Cézanne|Cezanne|Van\s+Gogh|"
    r"Gauguin|Picasso|Matisse|Pissarro|Seurat|Toulouse-Lautrec)\b|"
    r"\b[A-ZÀ-Ỹ][\wÀ-ỹ'-]+\s+(?:studied|painted|depicted|rendered|captured)\s+"
    r"(?:the\s+)?(?:urban\s+fabric|cityscape|street\s+scene|light|composition)\b"
    r")\b")

# A dated claim (a specific year or full date) is only allowed when the sentence
# also names the venue; otherwise it is an unsourced dated claim about something
# else. A bare century reference ("19th century") is not flagged.
_DATED_CLAIM_RE = re.compile(
    r"\b(1[0-9]{3}|20[0-2][0-9])\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}\b", re.IGNORECASE)

# ─── [LOCAL-855B] stronger always-drop markers ────────────────────────────────
#
# The LOCAL-855 scrub removed the YEAR but kept the INVENTION. The bounce says:
# for a user stop with no retrieved source naming the venue, drop the anecdote
# itself, the legend, the "no direct tie" hedge and the off-topic biography — not
# only the date on them. Three new sentence-level detectors, each a post-check
# (the ticket: "Enforce with a post-check … not only a prompt line").

# (defect 3) FOLK-TALE / LEGEND narrative. The story-research arm, keyed on a
# venue NAME that happens to be a word ("Longan" = dragon's eye), surfaces a
# myth and the writer narrates it as if it belonged to the venue ("This egg
# hatched a dragon that helped the village survive…"). Legend/fairy-tale
# vocabulary in a small-venue body is never about the venue.
_LEGEND_MARKER_RE = re.compile(
    r"(?i)\b("
    r"dragons?|legends?|myths?|myth(?:ical|ological)|folk\s*tales?|fables?|"
    r"fairy\s*tales?|"
    r"hatched|the\s+gods?|goddess|spirits?|demons?|serpents?|magical|enchanted|"
    r"a\s+(?:young\s+)?boy|the\s+boy|the\s+robber|the\s+raven|the\s+village|"
    r"ancient\s+(?:tale|story|legend)|once\s+upon|centuries[- ]old\s+(?:story|tale|legend)|"
    r"stolen\s+eye|dragon'?s?\s+eye|"
    # [LOCAL-855B bounce] vague legend-ALLUSION filler, no content: the delivered
    # Longan body (fruit-market resolution) replaced the explicit dragon tale with
    # "it carries a tale, one rooted in the legends of this land", "the timeless
    # narrative nearby", "the tale is tangible". An empty "this place carries a
    # tale / legend / a timeless narrative of this land" is the same off-venue
    # legend reach, just contentless — drop it too.
    r"carries\s+a\s+tale|a\s+tale(?:,|\s+(?:rooted|of|that|woven|born))|"
    r"legends?\s+of\s+this\s+land|tales?\s+of\s+this\s+land|"
    r"timeless\s+(?:tale|narrative|story)|the\s+tale\s+is\s+tangible|"
    r"rooted\s+in\s+(?:the\s+)?(?:legend|myth|folklore|lore)"
    r")\b")

# (defect 4) FABRICATED ANECDOTE / FIRSTS. A dateless story the writer invented:
# "Before one pivotal night…", "That evening changed the pattern", "a local
# songwriter who credits her early gigs here with securing her first record
# deal", "One story from X's recent past involves…", "the first/earliest …".
_ANECDOTE_MARKER_RE = re.compile(
    r"(?i)("
    r"\bone\s+(?:pivotal|fateful|memorable|particular)\s+(?:night|evening|day|"
    r"moment|story)\b|"
    r"\bone\s+story\b|\bone\s+(?:night|evening)\b|"
    r"\bthat\s+(?:evening|night|day|moment)\s+changed\b|"
    r"\bcredits?\b.*\b(?:first|early|debut)\b|"
    r"\bsecur(?:ed|ing)\s+(?:her|his|their|its)\s+first\b|"
    r"\bfirst\s+record\s+deal\b|"
    r"\brecording\s+contract\b|"
    r"\blaunched\s+(?:her|his|their)\s+career\b|"
    r"\bbefore\s+(?:one\s+)?(?:pivotal|that)\b|"
    r"\bstory\s+(?:from|involves|goes|tells)\b|"
    r"\bthe\s+first\b.*\bto\s+(?:open|host|perform|stage|feature)\b|"
    r"\bbecame\s+the\s+first\b|\bwas\s+the\s+first\b|"
    r"\bpivotal\b|"
    # [LOCAL-855B bounce] The Acoustic Bar fabrication was rephrased past the
    # markers above: "One account that lingers among regulars tells of a
    # fledgling artist … These unassuming performances opened doors to
    # professional contracts … shifting that artist's trajectory from local
    # obscurity to a wider audience … The bar's role as a springboard is
    # concrete … became a meeting ground for musical collaboration … workshop
    # original songs". Every one of these is an invented discovery/launch story
    # about an unnamed person — the exact fabrication class, caught by the story
    # VOCABULARY rather than a fixed sentence shape.
    r"\bone\s+account\b|\baccount\s+that\s+lingers\b|\blingers\s+among\s+"
    r"regulars\b|\btells\s+of\b|\bfledgling\s+artist\b|\bunknown\s+beyond\b|"
    r"\bopened\s+doors\s+to\b|\bprofessional\s+contracts?\b|"
    r"\brecord\s+labels?\b|\bmusic\s+labels?\b|\bspringboard\b|"
    r"\b(?:his|her|their|the\s+artist'?s?)\s+trajectory\b|"
    r"\blocal\s+obscurity\b|\bwider\s+audience\b|\bmeeting\s+ground\s+for\b|"
    r"\bworkshop(?:ed|ing)?\s+(?:original\s+)?songs?\b|"
    r"\bstepping\s+stone\b|\bcaught\s+the\s+(?:attention|eye)\s+of\s+a\b|"
    r"\bwent\s+on\s+to\b|\brose\s+to\s+(?:fame|prominence)\b|"
    r"\bdiscovered\s+(?:here|at\s+this)\b|"
    # [LOCAL-855B bounce] The Thi Bar fabrication was rephrased into a pioneering
    # claim: "marks a turning point in the city's social scene. Before this, drag
    # performances were confined to underground venues … this bar opened a door
    # for the local LGBT community to step into public view. On its opening
    # evening, performers took the stage … This event did more than entertain — it
    # nudged visibility and acceptance forward." An invented "was first / opened
    # the door / turning point / before this it was X, then the venue changed it"
    # pioneering story about a small venue, caught by its vocabulary.
    r"\bturning\s+point\b|\bbefore\s+this\b|\bopened\s+(?:a|the)\s+door\b|"
    r"\bstep\s+into\s+public\s+view\b|\bon\s+its\s+opening\s+(?:night|evening|day)\b|"
    r"\bconfined\s+to\s+(?:underground|private|hidden)\b|"
    r"\bnudged\s+(?:visibility|acceptance|change)\b|"
    r"\bmarked\s+a\s+(?:turning|pivotal|watershed)\b|"
    r"\bchanged\s+the\s+pattern\b|\bbroke\s+new\s+ground\b|"
    r"\bpaved\s+the\s+way\b|\bushered\s+in\b"
    r")")

# [LOCAL-855B] STRONG CLAIM-OF-FIRSTS — ALWAYS-drop. An explicit "first-ever",
# "hosted the first …", "the first … in the city" is a hard factual superlative
# that for a small private venue is almost always fabricated (Thi Bar's "first-
# ever drag show in 2018"). Dropped regardless of sourcing — the superlative is
# the fabrication class the ticket names, and a retrieved mention of the venue
# does not establish it was literally the first anywhere.
_FIRSTS_CLAIM_RE = re.compile(
    r"(?i)("
    r"\bfirst[- ]ever\b|"
    r"\bhosted\s+(?:its\s+|the\s+)?(?:first|first[- ]ever)\b|"
    r"\bthe\s+first\s+\w+(?:\s+\w+){0,4}\s+in\s+(?:the\s+)?(?:city|country|"
    r"nation|region|district|vietnam|saigon)\b|"
    r"\b(?:city|country|region|district)'?s\s+first\b"
    r")")

# (defect 5) OFF-TOPIC-FIGURE HEDGE. The tell-tale "while there is no direct
# tie/link/connection to <X>, …" that then narrates a biography of someone the
# venue is not about. Any "no direct tie/link/connection/relation/association"
# sentence is a hedge introducing off-topic material — drop it whole.
_NO_DIRECT_TIE_RE = re.compile(
    r"(?i)\bno\s+direct\s+(?:tie|ties|link|links|connection|connections|"
    r"relation|relationship|association|bearing)\b")


def _split_sentences(text: str):
    try:
        from sentence_split import split_sentences as _shared
        return _shared(text or "")
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip())
                if s.strip()]


def scrub_user_stop_body(text: str, poi: Dict, location: str = "",
                         log=None, outdoor_facts=None, source_gated: bool = True):
    """[LOCAL-855 / LOCAL-855B defects 3/4/5/8] Drop invented / off-venue
    sentences from a USER stop's delivered body. Returns ``(scrubbed, dropped)``.

    Two tiers of drop:

    ALWAYS (regardless of sourcing) — these are never correct for a user venue:
      * a FOLK-TALE / LEGEND sentence that does not name the venue (defect 3: the
        Longan dragon legend);
      * a "no direct tie/link/connection to <X>" HEDGE and the off-topic
        biography it introduces (defect 5: the Hồ Chí Minh digression);
      * an off-topic sentence (far-away place / infrastructure / administrative /
        military / national-figure topic) that does not name the venue.

    ONLY WHEN THE STOP HAS NO RETRIEVED SOURCE NAMING IT (defect 8 — a sourced
    stop such as "Notre-Dame Cathedral Basilica of Saigon" keeps "built
    1863–1880"):
      * a DATED claim (a specific year / full date);
      * a FABRICATED ANECDOTE or claim-of-firsts (defect 4: "one pivotal night",
        "that evening changed", "credits … first record deal").

    On-topic sentences, and any sentence that names the venue, are kept — except a
    legend/anecdote/hedge sentence, which is dropped even if the venue name is in
    it (naming the venue does not make an invented story true). Never empties the
    body: if every sentence would be dropped, the text is returned unchanged (the
    prompt-level short-stop instruction is the primary control). Only runs for
    user stops.
    """
    if not is_user_stop(poi) or not text or not text.strip():
        return text, []

    name = poi.get("name") or poi.get("title") or ""
    type_specialty = poi.get("type_specialty") or ""
    # [LOCAL-855B defect 8] Is there a RETRIEVED/RESEARCH source that could carry
    # a DATE about this venue? When there is, dated facts ("built 1863–1880") are
    # grounded and MUST be kept — so the dated/anecdote drops do not fire. This is
    # the NARROW test (has_dated_source): a customer-voice or practicals block is
    # real material but never sources a founding year, so the Thi Bar
    # VietPride-2018 fabrication still drops. Legend/hedge/off-topic drops are
    # unconditional: a source about the venue never makes a dragon legend or a
    # national-figure hedge correct.
    #
    # [LOCAL-855B] source_gated=False (the FINAL-TEXT pass) cannot know a stop's
    # retrieved facts, so it must NOT apply the source-gated dated/anecdote drops
    # — those were already handled correctly per-attempt with the real facts
    # (a famous stop like Notre-Dame keeps "built 1877–1880"). Treat it as sourced
    # so only the unconditional always-drop tiers fire.
    has_dsrc = True if not source_gated else has_dated_source(poi, outdoor_facts)

    # On-topic anchor tokens: distinctive venue-name words, venue-kind words, and
    # the city/place tokens (so a sentence grounding the listener in the city is
    # kept). Generic/stop words are excluded so they never falsely anchor —
    # notably "the": a venue named "The Crazy street" must not make EVERY sentence
    # containing "the" look on-topic (the 1975-offensive digression survived for
    # exactly this reason).
    _ANCHOR_STOPWORDS = {
        "the", "and", "for", "with", "from", "that", "this", "your", "you",
        "are", "its", "was", "were", "has", "had", "into", "onto", "off",
        "near", "over", "under", "here", "there", "city", "vietnam", "tour",
    }
    anchors = set()
    for w in _fold(name).split():
        if len(w) >= 3 and w not in _ANCHOR_STOPWORDS:
            anchors.add(w)
    anchors |= venue_kind_words(type_specialty)
    for w in _fold(type_specialty).split():
        if len(w) >= 3 and w not in _ANCHOR_STOPWORDS:
            anchors.add(w)
    # City tokens (e.g. "ho chi minh") keep an orientation sentence on-topic.
    for w in _fold(location).split():
        if len(w) >= 3 and w not in _ANCHOR_STOPWORDS:
            anchors.add(w)

    kept, dropped = [], []
    _flags860 = []
    for sent in _split_sentences(text):
        sfold = _fold(sent)
        stoks = set(sfold.split())
        on_topic = bool(stoks & anchors)
        off_marker = bool(_OFF_TOPIC_MARKER_RE.search(sent))
        dated = bool(_DATED_CLAIM_RE.search(sent))
        legend = bool(_LEGEND_MARKER_RE.search(sent))
        _disclosed862b = False
        # [LOCAL-862B / D760] A sentence that carries a disclosure marker ("A
        # Vietnamese folk tale tells …", "We couldn't confirm this, but …") is layer
        # 3: its legend / anecdote vocabulary is allowed; the SAME sentence without
        # a marker stays dropped. A sentence explaining the word in the venue's name
        # ("Longan comes from the Chinese lóngyǎn, 'dragon eye'") is layer 2 and its
        # legend vocabulary is allowed too. A date / first / geography still drops.
        try:
            from user_stop_context import has_disclosure as _hd862b, \
                is_name_meaning_sentence as _nm862b
            _disclosed862b = _hd862b(sent)
            if legend and (_disclosed862b or _nm862b(sent, name)):
                legend = False
        except Exception:
            pass
        anecdote = bool(_ANECDOTE_MARKER_RE.search(sent)) and not _disclosed862b
        hedge = bool(_NO_DIRECT_TIE_RE.search(sent))
        art_prov = bool(_ART_PROVENANCE_RE.search(sent))
        admin_geo = bool(_ADMIN_GEOGRAPHY_RE.search(sent))
        military = bool(_MILITARY_RE.search(sent))
        national_figure = bool(_NATIONAL_FIGURE_RE.search(sent))
        firsts_claim = bool(_FIRSTS_CLAIM_RE.search(sent))

        drop_reason = None
        # ── ALWAYS-drop tier ──────────────────────────────────────────────
        if hedge:
            drop_reason = "no-direct-tie hedge / off-topic biography"
        elif firsts_claim:
            # An explicit "first-ever" / "hosted the first … in the city"
            # superlative for a small private venue is a fabrication (Thi Bar's
            # "first-ever drag show"); dropped regardless of sourcing.
            drop_reason = "unsupported claim-of-firsts"
        elif national_figure:
            # A national figure's biography (the city is NAMED for Hồ Chí Minh,
            # so city tokens falsely anchor it on-topic) is never a venue's story.
            drop_reason = "off-venue national-figure biography"
        elif military:
            # War/military campaign history is never a bar/spa/street's content.
            drop_reason = "off-venue military-history digression"
        elif art_prov:
            # An artwork's museum provenance ("… now housed at the Art Institute
            # of Chicago") is never a small bar/spa/street's own content.
            drop_reason = "off-venue art-provenance digression"
        elif admin_geo:
            # Province-merger / "Nth largest city" / population geography is
            # off-venue even when the venue name is in the sentence.
            drop_reason = "off-venue administrative-geography digression"
        elif legend:
            # A legend/fairy-tale sentence is off-venue even if it uses the
            # venue's name as the subject ("Longan … dragon's eye").
            drop_reason = "folk-tale / legend narrative"
        elif (not on_topic) and off_marker:
            drop_reason = "off-venue (far place / history / figure)"
        # ── THIN-only tier (no retrieved/research source dates this venue) ─
        elif not has_dsrc and dated:
            drop_reason = "unsourced dated claim"
        elif not has_dsrc and anecdote:
            drop_reason = "fabricated anecdote / claim-of-firsts"

        if drop_reason:
            dropped.append(sent)
            _flags860.append(False)
            if log:
                log(f"[LOCAL-855B] dropped ({drop_reason}) from {name!r}: "
                    f"{' '.join(sent.split()[:9])}…")
        else:
            kept.append(sent)
            _flags860.append(True)
    # [LOCAL-860 item 3] orphaned back-reference after a drop goes too.
    if dropped and kept:
        _all860 = _split_sentences(text)
        _nf860, _orph860 = apply_orphan_rule(_all860, _flags860)
        if _orph860:
            kept = [x for x, f in zip(_all860, _nf860) if f]
            dropped = dropped + [_all860[i] for i in _orph860]
            if log:
                log(f"[LOCAL-860] dropped {len(_orph860)} orphaned back-reference "
                    f"sentence(s) from {name!r}")
    if not kept:
        # [LOCAL-855B bounce] Every sentence was fabrication (a dragon legend end
        # to end, an invented discovery anecdote, a wrong-place description). The
        # old rule kept the whole fabricated body "to never empty it" — which is
        # exactly how the delivered An Spa / Acoustic bodies shipped. Instead,
        # REPLACE it with a deterministic grounded 2–4 sentence body built from
        # what is known (name, kind, examples, district). This never carries a
        # date/anecdote/legend/landmark, so it cannot re-introduce any defect. If
        # we cannot build one (no name/kind), fall back to the old never-empty
        # behaviour.
        grounded = grounded_user_stop_body(poi, location)
        if grounded and grounded.strip():
            if log:
                log(f"[LOCAL-855B] user stop {name!r}: all {len(dropped)} "
                    f"sentence(s) were off-venue/fabricated — replaced body with "
                    f"grounded description")
            return grounded.strip(), dropped
        return text, []
    if not dropped:
        return text, []
    return " ".join(kept).strip(), dropped


# ─── [LOCAL-855B defect 6] off-pin landmark scrub ─────────────────────────────
#
# An Spa's pin is 10.7820,106.6935 (District 3, Trần Quốc Thảo), but the delivered
# orientation placed it "just steps from the corner where Đồng Khởi Street meets
# Lam Sơn Square, nearby the Saigon Municipal Theatre" and "once known as Rue
# N°6" — all District-1 landmarks ~1.5 km away. A user stop's orientation/body may
# cite a landmark only when it is actually NEAR the stop's own pin (~300 m). This
# post-check resolves each named landmark to a coordinate (the offline
# Wikidata-P625 landmark table first, then a live lookup when one is injected /
# available) and drops the sentence when the landmark sits beyond the radius.

_HAVERSINE_FALLBACK_R = 6371000.0  # metres


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    try:
        from geocode_stops import haversine_m as _hm
        return float(_hm((lat1, lng1), (lat2, lng2)))
    except Exception:
        import math
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lng2 - lng1)
        a = (math.sin(dphi / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
        return 2 * _HAVERSINE_FALLBACK_R * math.asin(min(1.0, math.sqrt(a)))


def _parse_coords(value):
    """Parse a 'lat, lng' string (or a (lat,lng) pair) to a float tuple, else None."""
    if not value:
        return None
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except Exception:
            return None
    m = re.search(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)", str(value))
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except Exception:
        return None


# Landmark/place phrases a sentence might name: a run of Capitalized words ending
# in (or being) a place-class word, plus multi-word proper names. Accented Latin
# (Vietnamese/French) is included. Deliberately conservative — a phrase must carry
# a place-class suffix (Street/Square/Theatre/Cathedral/Opera House/Market/Park/
# Boulevard/Avenue/Plaza/Station/Bridge) so ordinary prose nouns are not probed.
_PLACE_CLASS_SUFFIX = (
    r"(?:Street|Square|Theatre|Theater|Opera\s+House|Cathedral|Basilica|"
    r"Market|Park|Boulevard|Avenue|Plaza|Station|Bridge|Palace|Hall|Temple|"
    r"Pagoda|Post\s+Office|Museum)")
_LANDMARK_PHRASE_RE = re.compile(
    r"\b([A-ZÀ-Ỹ][\wÀ-ỹ’'\-]*(?:\s+[A-ZÀ-Ỹ0-9°][\wÀ-ỹ’'\-]*){0,4}\s+"
    + _PLACE_CLASS_SUFFIX + r")\b")


def _resolve_landmark(name, landmark_fn=None):
    """Return (lat, lng) for a named landmark, or None. Offline table first, then
    an injected/live lookup. Both are optional; absence just means 'unknown'."""
    # 1) injected resolver (tests, or a live wikidata lookup wired by the caller)
    if landmark_fn is not None:
        try:
            hit = landmark_fn(name)
        except Exception:
            hit = None
        if hit:
            if isinstance(hit, (tuple, list)) and len(hit) >= 2:
                try:
                    return float(hit[0]), float(hit[1])
                except Exception:
                    pass
    # 2) offline Wikidata-P625 table (the HCMC landmark anchors)
    try:
        from landmark_reference import lookup as _lm_lookup
        hit = _lm_lookup(name)
        if hit:
            return float(hit[0]), float(hit[1])
    except Exception:
        pass
    # 3) live Wikidata P625 (only if the module answers; it returns None offline)
    try:
        from wikidata_landmark_lookup import lookup as _wd_lookup
        hit = _wd_lookup(name)
        if hit:
            if isinstance(hit, dict):
                lat, lng = hit.get("lat"), hit.get("lng")
                if lat is not None and lng is not None:
                    return float(lat), float(lng)
            elif isinstance(hit, (tuple, list)) and len(hit) >= 2:
                return float(hit[0]), float(hit[1])
    except Exception:
        pass
    return None


def scrub_offpin_landmarks(text, poi: Dict, location: str = "", log=None,
                           landmark_fn=None, max_m: float = 300.0):
    """[LOCAL-855B defect 6] Drop a user-stop orientation/body sentence that cites
    a landmark more than ``max_m`` from the stop's own pin. Returns
    ``(scrubbed, dropped)``.

    Only runs for a user stop that has a parseable coordinate. For each sentence,
    every named landmark phrase (a proper-noun place phrase, e.g. "Saigon
    Municipal Theatre", "Đồng Khởi Street") is resolved to a coordinate; if ANY
    resolves beyond ``max_m`` from the pin, the sentence is dropped — the stop is
    not there. A sentence naming the venue itself is never dropped by this check
    (the venue is at the pin by definition). Landmarks that cannot be resolved are
    left alone (this check only removes a landmark it can prove is far away).
    Never empties the body.
    """
    if not is_user_stop(poi) or not text or not text.strip():
        return text, []
    pin = _parse_coords(poi.get("coordinates") or poi.get("coordinate"))
    if pin is None:
        return text, []
    plat, plng = pin

    name = poi.get("name") or poi.get("title") or ""
    name_fold = _fold(name)
    # Distinctive venue-name tokens (drop articles and the city qualifier) so a
    # phrase that IS the venue — even "The Notre-Dame Cathedral Basilica" without
    # the trailing ", of Saigon" — is recognised and never scrubbed as foreign.
    _gen = {"the", "of", "a", "an", "and", "saigon", "city"}
    name_toks = {w for w in name_fold.split() if len(w) >= 3 and w not in _gen}

    kept, dropped = [], []
    _flags860 = []
    for sent in _split_sentences(text):
        sfold = _fold(sent)
        off = None
        for m in _LANDMARK_PHRASE_RE.finditer(sent):
            phrase = m.group(1).strip()
            pf = _fold(phrase)
            ptoks = {w for w in pf.split() if len(w) >= 3 and w not in _gen}
            # Never treat the venue's own name as a foreign landmark: substring
            # either way, OR the phrase's distinctive tokens are a subset of the
            # venue's (or vice-versa) — handles a leading "The" / dropped suffix.
            if pf and (pf in name_fold or name_fold in pf):
                continue
            if name_toks and ptoks and (ptoks <= name_toks or name_toks <= ptoks):
                continue
            coord = _resolve_landmark(phrase, landmark_fn=landmark_fn)
            if not coord:
                continue
            dist = _haversine_m(plat, plng, coord[0], coord[1])
            if dist > max_m:
                off = (phrase, dist)
                break
        if off:
            dropped.append(sent)
            _flags860.append(False)
            if log:
                log(f"[LOCAL-855B] off-pin landmark dropped from {name!r} "
                    f"({off[0]!r} ~{off[1]:.0f} m from pin): "
                    f"{' '.join(sent.split()[:9])}…")
        else:
            kept.append(sent)
            _flags860.append(True)
    # [LOCAL-860 item 3] orphaned back-reference after a drop goes too.
    if dropped and kept:
        _all860 = _split_sentences(text)
        _nf860, _orph860 = apply_orphan_rule(_all860, _flags860)
        if _orph860:
            kept = [x for x, f in zip(_all860, _nf860) if f]
            dropped = dropped + [_all860[i] for i in _orph860]
    if not kept or not dropped:
        return text, []
    return " ".join(kept).strip(), dropped


# ─── [LOCAL-855B] FINAL-TEXT user-stop scrub ──────────────────────────────────
#
# The per-stop scrub runs inside the generation loop, but a later pass
# (scorer-retry / story-pass) can rewrite a user stop's body AFTER it, so the
# fabrications reappear in the DELIVERED text (the live run shipped the Long
# Thanh Airport sentence on Rambutan and the 1975-offensive paragraph on The
# Crazy street even though both were dropped per-attempt). This re-runs the scrub
# on the ASSEMBLED tour text, so whatever the final rewrite produced is cleaned.
# It touches only the narration paragraphs of a USER stop (the header, the field
# lines Coordinates/Type/Specialty/Specific Examples, the Orientation label, the
# Directions line and Sources are preserved).

_STOP_HDR_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_FIELD_LINE_RE = re.compile(
    r"(?mi)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
    r"Tour-Category|Address):")
_COORD_LINE_RE = re.compile(
    r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_TYPE_LINE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")


def _folded_titles(titles):
    out = set()
    for t in (titles or []):
        f = _fold(t)
        if f:
            out.add(f)
    return out


def _title_is_user(title, folded_titles):
    f = _fold(title)
    if not f:
        return False
    for t in folded_titles:
        if f == t or f in t or t in f:
            return True
    return False


def scrub_tour_text_user_stops(tour_text, user_titles, location="", log=None,
                               landmark_fn=None):
    """Re-scrub the narration of every USER stop in an ASSEMBLED tour text.

    ``user_titles`` is the list of the listener's chosen stop names (the seeded
    user-stop titles). For each ``Stop N: <title>`` block whose title matches one,
    the Orientation text and each following body paragraph (up to the Directions
    line / next Stop / Sources) are run through ``scrub_user_stop_body`` and
    ``scrub_offpin_landmarks`` using a poi reconstructed from the block's
    Type/Specialty and Coordinates lines. Returns ``(text, n_dropped)``.
    Structure lines are preserved. A paragraph never fully empties (the scrub's
    own never-empty rule holds). Deterministic; safe to call once at delivery.
    """
    if not tour_text or not tour_text.strip() or not user_titles:
        return tour_text or "", 0
    folded = _folded_titles(user_titles)
    if not folded:
        return tour_text, 0

    lines = tour_text.split("\n")
    # Index the Stop headers.
    headers = [(i, m) for i, ln in enumerate(lines)
               for m in [_STOP_HDR_RE.match(ln)] if m]
    if not headers:
        return tour_text, 0

    total_dropped = 0

    def _scrub_block(poi, start, end, source_gated):
        nonlocal total_dropped
        # Walk the block lines; scrub the Orientation value and standalone body
        # paragraphs, leaving field lines and Directions/Sources untouched.
        i = start
        while i < end:
            ln = lines[i]
            stripped = ln.strip()
            if not stripped:
                i += 1
                continue
            if _FIELD_LINE_RE.match(ln) or _STOP_HDR_RE.match(ln) \
                    or stripped.lower().startswith("sources"):
                i += 1
                continue
            if ln.lower().startswith("orientation:"):
                label, _, val = ln.partition(":")
                new_val = val
                s1, d1 = scrub_user_stop_body(val, poi, location, log=log, source_gated=source_gated)
                if d1:
                    new_val = s1
                    total_dropped += len(d1)
                s2, d2 = scrub_offpin_landmarks(new_val, poi, location, log=log,
                                                landmark_fn=landmark_fn)
                if d2:
                    new_val = s2
                    total_dropped += len(d2)
                lines[i] = f"{label}: {new_val.strip()}"
                i += 1
                continue
            # A standalone narration paragraph.
            s1, d1 = scrub_user_stop_body(ln, poi, location, log=log, source_gated=source_gated)
            new_par = ln
            if d1:
                new_par = s1
                total_dropped += len(d1)
            s2, d2 = scrub_offpin_landmarks(new_par, poi, location, log=log,
                                            landmark_fn=landmark_fn)
            if d2:
                new_par = s2
                total_dropped += len(d2)
            lines[i] = new_par
            i += 1

    for h_idx, (line_no, m) in enumerate(headers):
        title = m.group(2).strip()
        if not _title_is_user(title, folded):
            continue
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        # Build a synthetic poi from the block's field lines.
        block_text = "\n".join(lines[start:end])
        poi = {"name": title, "title": title, "user_explicit": True}
        tm = _TYPE_LINE_RE.search(block_text)
        if tm:
            poi["type_specialty"] = tm.group(1).strip()
        cm = _COORD_LINE_RE.search(block_text)
        if cm:
            poi["coordinates"] = f"{cm.group(1)}, {cm.group(2)}"
        # [LOCAL-855B bounce] Carry Address + Specific Examples so the grounded
        # body replacement (used when a thin stop is fabrication end-to-end) can
        # state the real district and what the venue offers.
        am = re.search(r"(?mi)^Address:[ \t]*(\S[^\n]*?)[ \t]*$", block_text)
        if am:
            poi["address"] = am.group(1).strip()
        xm = re.search(r"(?mi)^Specific Examples:\s*(.+?)\s*$", block_text)
        if xm:
            poi["specific_examples"] = xm.group(1).strip()
        # [LOCAL-855B defect 8] Decide whether this stop's dates are trustworthy.
        # A FAMOUS stop (resolves in the Wikidata-P625 landmark table / wikidata)
        # or one carrying a real Address line is SOURCED → keep its dated facts
        # (Notre-Dame "built 1877–1880"). A thin named venue is NOT → drop its
        # unsourced dated/anecdote (Thi Bar's "VietPride 2019"). source_gated=True
        # means "apply the dated/anecdote drops".
        # [LOCAL-855B defect 8] Decide whether this stop's dated CLAIMS are
        # trustworthy, by the KIND of place it is. A small private venue — bar,
        # café, spa, karaoke, club, shop, hostel, a nightlife street — has no
        # documented founding date or dated events; a year in its body is a
        # fabrication (Thi Bar's "VietPride 2019"), so it is date-gated
        # (source_gated=True → drop). A monument/institution — cathedral,
        # basilica, palace, museum, market, temple, memorial, tower, landmark —
        # is documented, so its dates are kept (source_gated=False), matching the
        # ticket's Notre-Dame "built 1877–1880" requirement. Address/coordinate
        # resolution does NOT establish historical sourcing (every venue geocodes).
        _ts_fold = _fold(poi.get("type_specialty") or "")
        # [LOCAL-855B bounce] "market", "gallery", "park", "square", "bridge",
        # "tower", "theatre" are REMOVED from the documented set: a thin / mis-
        # resolved venue's Type routinely carries one ("Fruit Market" for the
        # mis-resolved Longan), and treating it as documented kept its fabricated
        # dated claim ("a population surpassing 4.1 million in 2024"). Only
        # unambiguously monumental/institutional kinds stay — a cathedral, palace,
        # museum, temple, memorial, monument, etc. — which is all the ticket's
        # Notre-Dame (a cathedral) requirement needs. A famous market would be
        # date-gated here, but that only costs it a founding year, never a defect.
        _DOCUMENTED_KINDS = {
            "cathedral", "basilica", "church", "temple", "pagoda", "palace",
            "museum", "memorial", "monument", "opera", "landmark", "shrine",
            "mausoleum", "fort", "citadel",
        }
        _documented = bool(set(_ts_fold.split()) & _DOCUMENTED_KINDS)
        # [LOCAL-862 item 4] Same landmark test as the verifier/enrichment
        # (name + type), so "Independence Palace" typed "Historical Site" keeps
        # its sourced dates.
        if not _documented:
            try:
                from user_stop_enrichment import classify_stop_kind as _csk862
                _documented = _csk862(title, poi.get("type_specialty") or "") in ("landmark", "both")  # [LOCAL-874]
            except Exception:
                pass
        _scrub_block(poi, start, end, source_gated=(not _documented))

    return "\n".join(lines), total_dropped


__all__.append("scrub_tour_text_user_stops")

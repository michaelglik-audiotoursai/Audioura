# -*- coding: utf-8 -*-
"""text_polish.py — LOCAL-860: small deterministic text/label helpers.

Pure functions, no network, no model, Python 3.9-safe. Each one answers one
wave-26 finding (GCloud_Storied_1, gen 00031-hp4):

  * ``tour_type_display_label``   — "biking Tour" -> "Cycling Tour" (item 2)
  * ``apply_orphan_rule``         — a kept "This juxtaposition…" whose
                                    antecedent sentence was dropped (item 3)
  * ``strip_emoji_for_tts``       — emoji/pictographs must never reach TTS (item 4)
  * ``named_places_from_subject`` — "A and B walk, City" names two places (items 5, 7)
  * ``city_from_scope``           — the city/district out of a full tour title (item 6)
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

__all__ = [
    "tour_type_display_label",
    "derive_tour_name",
    "BACKREF_OPENER_RE",
    "starts_with_backref",
    "apply_orphan_rule",
    "strip_emoji_for_tts",
    "named_places_from_subject",
    "scope_without_named_places",
    "bbox_from_center",
    "city_from_scope",
]


# ─────────────────────────────────────────────────────────────────────────────
# Item 2 — tour_name category label from the transport mode
# ─────────────────────────────────────────────────────────────────────────────
_LABELS = {
    "biking": "Cycling", "bike": "Cycling", "cycling": "Cycling",
    "bicycle": "Cycling", "bicycling": "Cycling",
    "walking": "Walking", "walk": "Walking", "on_foot": "Walking",
    "on foot": "Walking", "foot": "Walking",
    "driving": "Driving", "drive": "Driving", "vehicle": "Driving",
    "car": "Driving",
}


def tour_type_display_label(tour_type: str) -> str:
    """``"biking"`` -> ``"Cycling Tour"``; ``"walking"`` -> ``"Walking Tour"``;
    ``"driving"`` -> ``"Driving Tour"``. Any other value is title-cased and gets
    exactly one trailing ``Tour`` (``"museum"`` -> ``"Museum Tour"``). Idempotent:
    a value already ending in ``Tour`` is not doubled."""
    raw = (tour_type or "").strip()
    if not raw:
        return "Tour"
    key = re.sub(r"(?i)\s+tour$", "", raw).strip().lower().replace("-", " ")
    label = _LABELS.get(key) or _LABELS.get(key.replace(" ", "_"))
    if not label:
        label = " ".join(w[:1].upper() + w[1:] for w in key.replace("_", " ").split())
    return f"{label} Tour".strip()


def derive_tour_name(location: str, tour_type: str, first_line: str = "") -> str:
    """The stored ``tour_name``: ``"<location> - <X> Tour"``. ``X`` comes from the
    " - <X> Tour" suffix of the generated text's header line when it has one (the
    effective category); otherwise from the transport-mode display label
    (``"biking"`` -> ``"Cycling Tour"``), never the raw ``tour_type``."""
    fl = (first_line or "").strip()
    if " - " in fl and fl.endswith(" Tour"):
        suffix = fl.rsplit(" - ", 1)[-1]
    else:
        suffix = tour_type_display_label(tour_type)
    return f"{location} - {suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Item 3 — orphaned back-reference sentence after a drop
# ─────────────────────────────────────────────────────────────────────────────
# A sentence that opens by pointing back at the sentence before it. If that
# earlier sentence was dropped, this one reads as a non-sequitur ("This
# juxtaposition…" with nothing juxtaposed), so it goes too.
BACKREF_OPENER_RE = re.compile(
    r"^[\s\"'\u201c\u2018(\[]*"
    r"(?:this|these|that|those|it|its|his|her|their|such|"
    r"the\s+(?:contrast|juxtaposition))\b",
    re.IGNORECASE)


def starts_with_backref(sentence: str) -> bool:
    return bool(BACKREF_OPENER_RE.match(sentence or ""))


def apply_orphan_rule(sentences: Sequence[str],
                      keep_flags: Sequence[bool]) -> Tuple[List[bool], List[int]]:
    """After ANY drop, if the next kept sentence opens with a back-reference, drop
    it too; repeat until stable (a single forward pass is stable because a
    cascaded drop keeps the "previous was dropped" state). Never empties the list:
    the last remaining kept sentence is never dropped by this rule.

    Returns ``(new_flags, newly_dropped_indices)``. ``keep_flags`` is not mutated.
    """
    flags = list(keep_flags)
    n_keep = sum(1 for f in flags if f)
    newly: List[int] = []
    prev_dropped = False
    for i, sent in enumerate(sentences):
        if not flags[i]:
            prev_dropped = True
            continue
        if prev_dropped and n_keep > 1 and starts_with_backref(sent):
            flags[i] = False
            n_keep -= 1
            newly.append(i)
            continue  # prev_dropped stays True: cascade to the next sentence
        prev_dropped = False
    return flags, newly


# ─────────────────────────────────────────────────────────────────────────────
# Item 4 — emoji / pictographs are never spoken
# ─────────────────────────────────────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # mahjong..symbols & pictographs extended-A (rainbow 1F308 etc.)
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\u2600-\u27BF"           # misc symbols + dingbats
    "\u2B00-\u2BFF"           # arrows/stars (⭐ ⬆)
    "\u2300-\u23FF"           # misc technical (⌚ ⏰)
    "\u2190-\u21FF"           # arrows
    "\u2900-\u297F"           # supplemental arrows-B
    "\u3030\u303D\u3297\u3299"
    "\u200D"                  # zero-width joiner
    "\uFE0E\uFE0F"            # variation selectors
    "\u20E3"                  # combining enclosing keycap
    "\U000E0020-\U000E007F"   # tag characters (subdivision flags)
    "\U0001F3FB-\U0001F3FF"   # skin-tone modifiers
    "]+")


def strip_emoji_for_tts(text: str) -> str:
    """Remove emoji and pictographs from a TTS-bound string. Newlines are kept;
    runs of spaces/tabs left by a removal collapse to one and a space left
    before punctuation is closed up. ``"The LGBT bar 🌈Thi Bar Saigon"`` ->
    ``"The LGBT bar Thi Bar Saigon"``. Returns the input unchanged (same
    object) when it holds no emoji."""
    if not text or not _EMOJI_RE.search(text):
        return text
    out = _EMOJI_RE.sub(" ", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+([,.;:!?])", r"\1", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n[ \t]+", "\n", out)
    return out.strip(" \t")


def strip_emoji_for_tts_logged(text: str, where: str, log=print) -> str:
    """[LOCAL-863] ``strip_emoji_for_tts`` at a TTS egress, with a log line when
    anything was removed: ``[LOCAL-863] TTS emoji strip at <where>: removed N``.

    Wave 27: 🌈 still reached TTS on the cloud Subscribed path, and the
    modernized service logged no strip line. Subscribed has no polly-tts of its
    own, so it calls another line's polly-tts, which may predate the LOCAL-860
    server-side strip. The CALLER must therefore strip, and say so."""
    if not text:
        return text
    n = len(_EMOJI_RE.findall(text))
    if not n:
        return text
    out = strip_emoji_for_tts(text)
    try:
        log(f"[LOCAL-863] TTS emoji strip at {where}: removed {n} emoji run(s)")
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Items 5 + 7 — "A and B walk, City" names two places
# ─────────────────────────────────────────────────────────────────────────────
_TOUR_WORD = (r"(?:walking\s+tour|walking|walk|tour|stroll|hike|trail|route|"
              r"bike\s+ride|biking\s+tour|cycling\s+tour|driving\s+tour|drive|"
              r"visit)")
_TRAILING_TOUR_RE = re.compile(r"\s+" + _TOUR_WORD + r"\s*$", re.IGNORECASE)
_LEADING_TOUR_RE = re.compile(
    r"^\s*(?:a\s+|an\s+|the\s+)?(?:[A-Za-z\-]+\s+){0,2}?"
    r"(?:tour|walk|stroll|hike|trail|route|ride)\s+(?:of|through|around|to|in)\s+",
    re.IGNORECASE)

# A part must look like a place, not a theme ("Food and Wine walk").
_LANDMARK_NOUNS = {
    "common", "church", "cathedral", "basilica", "temple", "pagoda", "mosque",
    "synagogue", "lake", "park", "garden", "gardens", "square", "plaza",
    "bridge", "tower", "palace", "castle", "museum", "hall", "market",
    "monument", "memorial", "mausoleum", "citadel", "fort", "gate", "hill",
    "harbor", "harbour", "wharf", "cemetery", "library", "theatre", "theater",
    "opera", "fountain", "island", "beach", "pier", "station", "abbey",
}
_THEME_WORDS = {
    "restaurants", "restaurant", "cafes", "bars", "museums", "galleries",
    "shops", "sights", "attractions", "highlights", "landmarks", "history",
    "historic", "historical", "food", "best", "top", "hidden", "gems",
    "street", "art", "architecture", "culture", "nightlife", "dinner",
    "lunch", "breakfast", "tour", "tours", "walk", "walks",
}
_LEAD_VERB_WORDS = {"visit", "see", "dinner", "lunch", "breakfast", "stop",
                    "explore", "tour", "walk", "from", "via", "near"}


def _looks_like_place(part: str) -> bool:
    words = part.split()
    if not words:
        return False
    if not words[0][:1].isupper():
        return False
    low = [w.lower().strip(".,'\u2019") for w in words]
    if low[0] in _LEAD_VERB_WORDS:
        return False
    if any(w in _THEME_WORDS for w in low):
        return False
    return len(words) >= 2 or low[-1] in _LANDMARK_NOUNS


def named_places_from_subject(request: str) -> List[str]:
    """Places named in the SUBJECT of a request such as
    ``"Boston Common and Old North Church walk, Boston"`` ->
    ``["Boston Common", "Old North Church"]``.

    Deliberately narrow: the first comma segment must be a tour phrase (it ends
    in walk/tour/stroll/… or opens with "<kind> tour of/through …"), it must
    list at least TWO parts joined by "and"/"&"/"+", and EVERY part must look like
    a place (capitalised; two or more words or a landmark noun; no theme words).
    Anything else returns ``[]`` so a themed request ("Food and Wine walk,
    Boston") is not turned into fake named stops."""
    text = (request or "").strip()
    if not text:
        return []
    segment = text.split(",")[0].strip()
    had_trailing = bool(_TRAILING_TOUR_RE.search(segment))
    had_leading = bool(_LEADING_TOUR_RE.match(segment))
    if not (had_trailing or had_leading):
        return []
    core = _TRAILING_TOUR_RE.sub("", segment).strip()
    core = _LEADING_TOUR_RE.sub("", core, count=1).strip()
    parts = [p.strip(" .;") for p in
             re.split(r"\s+\band\b\s+|\s*&\s*|\s*\+\s*", core, flags=re.IGNORECASE)]
    parts = [re.sub(r"^(?:the|a|an)\s+", "", p, flags=re.IGNORECASE) for p in parts if p]
    if len(parts) < 2:
        return []
    out: List[str] = []
    seen = set()
    for p in parts:
        if not _looks_like_place(p):
            return []
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out if len(out) >= 2 else []


def scope_without_named_places(area_input: str, location: str,
                               named_places: Sequence[str]) -> str:
    """The geographic scope for the area resolver when the request's SUBJECT names
    the places. ``"Boston Common and Old North Church, Boston"`` yields an area
    input of ``"Boston Common and Old North Church"`` (the first non-filler
    segment), which cannot resolve as a city — so the walking path ran
    "unverified" and only ANNOUNCED the two places instead of making them stops
    (LOCAL-860 items 5+7). When the area input contains a named place and the
    request has a trailing locality, return that locality ("Boston"); otherwise
    return ``area_input`` unchanged."""
    ai = (area_input or "").strip()
    if not ai or not named_places:
        return area_input
    low = ai.lower()
    if not any((n or "").strip().lower() in low for n in named_places if n):
        return area_input
    loc = (location or "").strip()
    if "," not in loc:
        return area_input
    tail = loc.split(",", 1)[1].strip(" ,")
    return tail or area_input


def bbox_from_center(lat, lng, radius_km):
    """``[south, north, west, east]`` box of half-side ``radius_km`` about a centre,
    or ``None`` when the inputs are unusable. Used to bind a named-place geocode to
    the resolved CITY extent: the resolver's centre for Boston is the centroid of
    the whole admin boundary (harbour included), 7.6 km from the Old North Church,
    and places_search's fixed ~8 km radius around it rejected the church."""
    import math
    try:
        lat = float(lat)
        lng = float(lng)
        r = float(radius_km)
    except (TypeError, ValueError):
        return None
    if r <= 0 or (lat == 0.0 and lng == 0.0):
        return None
    dlat = r / 111.0
    dlng = r / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return [lat - dlat, lat + dlat, lng - dlng, lng + dlng]


# ─────────────────────────────────────────────────────────────────────────────
# Item 6 — the city/district out of a full tour title
# ─────────────────────────────────────────────────────────────────────────────
_CITY_ALIASES = {
    "hcmc": "Ho Chi Minh City", "saigon": "Ho Chi Minh City",
    "sgn": "Ho Chi Minh City", "nyc": "New York City",
}


def city_from_scope(location: str) -> str:
    """The place a tour is ABOUT, from the string the pipeline calls ``location``,
    which for a user-stops tour is the whole title: ``"Sophia's biking tour in
    Ho Chi Minh City"`` -> ``"Ho Chi Minh City"``; ``"Sophia's bike tour of HCMC"``
    -> ``"Ho Chi Minh City"``; ``"Ho Chi Minh City, Vietnam"`` -> ``"Ho Chi Minh
    City"``. Never returns the tour title."""
    s = (location or "").strip()
    if not s:
        return ""
    # Only a TITLE-shaped string ("<who>'s biking tour in <place>") needs the
    # in/of split; a plain place string ("Museum of Fine Arts, Boston") keeps its
    # first comma segment exactly as before.
    if re.search(r"(?i)\b(?:tour|walk|ride|trip)\b", s.split(",")[0]) or \
            re.search(r"(?i)\b(?:tour|walk|ride|trip)\b.*\b(?:in|of|around|through)\b", s):
        m = list(re.finditer(r"(?i)\b(?:in|of|around|through)\s+", s))
        if m:
            s = s[m[-1].end():]
    s = s.split(",")[0].strip()
    # A leftover tour phrase ("Sophia's biking tour") is not a place.
    if re.search(r"(?i)\b(?:tour|walk|ride|trip)\b", s):
        return ""
    s = re.sub(r"(?i)^(?:the)\s+", "", s).strip()
    return _CITY_ALIASES.get(s.lower(), s)

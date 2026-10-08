"""
Stop Pool Assembly (LOCAL-590) — build a bigger tour from pooled + new stops.
=============================================================================
Given the stops a venue has already delivered (the POOL, from stop_pool_store)
and the genuinely NEW stops generated for a larger request, assemble the final
tour per Michael's design (2026-10-05):

SINGLE-BUILDING tours (museum, facility — a contained venue):
  "for the one building tours you add 2 new stops before the 5, because you will
   need to generate the overall tour general description anyway, while the
   conclusion can be left alone … it should not be a big deal if you ask our
   listeners to return back if needed."
  → New stops go BEFORE the pooled ones. The orientation / overall description is
    regenerated (it now covers more). The pooled stops and the conclusion are
    reused as-is. One walk-back line is added so a listener who already saw the
    pooled stops knows to return to them.

OUTDOOR tours (walking / biking / driving):
  "you will have to identify the right sequential order and then rewrite the
   stops before and after the new stops to make sure they have the right
   directions: way more than extra 2 stops, potentially 4 stops will have to be
   rewritten instead of 2."
  → Compute the route order over pooled + new stops (stop_route_sequencer). The
    NARRATION BODIES of untouched stops are reused verbatim; ONLY the
    directions/transition text of the stops ADJACENT to each insertion is
    rewritten. Report how many stops were rewritten vs reused.

Why this module and not a rewrite of generate_tour_text: Directions and
Orientation are properties of a SEQUENCE, not of a stop (D581.1). They cannot be
cached with the pooled stop and must be recomputed for the delivered order. This
module does exactly that recomputation and nothing else — it never calls an LLM
for narration (narration is reused or supplied by the caller), so a reused stop
costs nothing. Directions rewrites use directions_generator when an API key is
available and fall back to the generator's own deterministic templates otherwise,
so the output is byte-compatible with a freshly generated tour.

The public entry points are `assemble_building_tour` and `assemble_outdoor_tour`.
Each returns an `AssemblyResult` (the final tour text + the reuse counts the cost
ledger needs).
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)


# ── House-style seam templates (mirror generate_tour_text render loop) ───────
# These are copied verbatim from the generator's render loop (:20790+ museum
# transitions, :20760 orientation prefix) so a merged tour is indistinguishable
# from a freshly generated one.

_ORIENTATION_PREFIX = "Orientation: "
_INTERIOR_TEMPLATES = (
    "Next: {name}.",
    "Proceed to {name}.",
    "Continue to {name}.",
)


def _museum_transition(i: int, n_stops: int, next_name: str, venue: str) -> str:
    """The museum/building transition line for position i → i+1 (0-based i).

    [r2] ``venue`` is cleaned with ``_venue_name`` so a themed-in-building request
    ("Art and Architectual tour in Boston Athenaeum") never leaks into the spoken
    hand-off — the line names the BUILDING, not the raw request string.
    """
    venue = _venue_name(venue)
    if venue and i == 0:
        return f"Continue through {venue} — next is {next_name}."
    if venue and i == n_stops - 2:
        return f"Your final stop in {venue}: {next_name}."
    return _INTERIOR_TEMPLATES[(i - 1) % len(_INTERIOR_TEMPLATES)].format(name=next_name)


def _venue_name(location: str) -> str:
    """Resolve the BUILDING name from a venue/request string for spoken seams.

    [LOCAL-585 r2] A themed-in-building request ("Art and Architectual tour in
    Boston Athenaeum, boston, ma") must say "Continue through Boston Athenaeum",
    not the whole request string. Delegates to about_museum_stop so the same rule
    governs the About stop and the Directions. Plain venue strings are returned
    unchanged apart from their trailing locality tail. Already-clean input (no
    theme prefix, no comma tail) passes straight through.
    """
    loc = (location or "").strip()
    if not loc:
        return ""
    try:
        from about_museum_stop import clean_venue_request_name
        cleaned = clean_venue_request_name(loc)
        if cleaned:
            return cleaned
    except Exception:
        pass
    return loc.split(",")[0].strip()


@dataclass
class AssemblyResult:
    tour_text: str
    reused_stops: int = 0
    new_stops: int = 0
    rewritten_transitions: int = 0
    order: List[str] = field(default_factory=list)  # delivered stop titles, in order
    about_stops: int = 0  # [LOCAL-592] 1 when an About+practical opening SECTION was folded into Stop 1 (adds ZERO stops)
    dedupe_dropped: int = 0  # [LOCAL-607] cross-stop fact sentences removed
    dedupe_log: List[str] = field(default_factory=list)  # [LOCAL-607] human-readable dedupe lines


# ── Stop-unit helpers ────────────────────────────────────────────────────────
#
# A "stop unit" here is a dict with at least:
#   title, narration            (required)
#   artist, year                (header decoration; optional)
#   orientation                 (per-stop orientation body WITHOUT the prefix)
#   address, coordinates, type_specialty, specific_examples, operational_details
#   _pool_reused                True for pooled stops, False/absent for new ones
#   latitude, longitude         (for outdoor route order; optional)


def _header_line(stop: Dict) -> str:
    """Build the 'Stop N:' header value (name + optional ' by artist' + ', year').

    The number is applied by the renderer; this returns the part after 'Stop N: '.
    """
    title = stop["title"]
    header = title
    artist = (stop.get("artist") or "").strip()
    year = (stop.get("year") or "").strip()
    if artist and artist.lower() != "unknown artist":
        header += f" by {artist}"
    if year:
        header += f", {year}"
    return header


def _render_stop_block(stop: Dict, stop_num: int, tour_category: str,
                       directions_line: Optional[str]) -> str:
    """Render one stop into the delivered-text block, in house format.

    Mirrors the generate_tour_text render loop field order:
      Stop N: {header}
      Address: ...
      Coordinates: ...
      Type/Specialty: ...
      Specific Examples: ...
      Operational Details: ...
      Orientation: ...
      {narration}
      Directions: ...   (omitted on the last stop; supplied by caller)
    """
    parts = [f"Stop {stop_num}: {_header_line(stop)}", ""]

    def _field(label, key):
        v = (stop.get(key) or "").strip()
        if v:
            parts.append(f"{label}: {v}")
            parts.append("")

    # [LOCAL-623 defect 3] Validate the Address before rendering. A mis-parsed
    # narrative fragment ("1922 by way, Essen, Germany" — a year + preposition,
    # not a street) must never reach the listener. If the address slot does not
    # hold a genuine street address, omit the Address line entirely rather than
    # ship garbage (the task's fallback-or-omit rule; the venue/corpus address is
    # resolved upstream by venue_bound_address when available).
    _addr = (stop.get("address") or "").strip()
    if _addr:
        try:
            from about_museum_stop import is_valid_street_address as _ivsa
            if not _ivsa(_addr):
                _addr = ""
        except Exception:
            pass
    if _addr:
        parts.append(f"Address: {_addr}")
        parts.append("")
    _field("Coordinates", "coordinates")
    if tour_category not in ("museum", "facility"):
        _field("Type/Specialty", "type_specialty")
        _field("Specific Examples", "specific_examples")
        _field("Operational Details", "operational_details")

    # [LOCAL-592 r2] The OPENING SECTION (About the venue + visiting information)
    # is the FIRST spoken section of Stop 1 — Michael's four-part order
    # (D611): (a) About the venue → (b) Visiting information → (c) the tour
    # overview / Orientation → (d) Stop 1's own narration. It is rendered BEFORE
    # the Orientation line so the About + hours/admission come first, exactly like
    # the walking-tour Overall section. It is carried on a dedicated field so it is
    # never confused with the stop's own narration and never read as an artwork.
    opening = (stop.get("_opening_section") or "").strip()
    if opening:
        parts.append(opening)
        parts.append("")

    orientation = (stop.get("orientation") or "").strip()
    if orientation:
        parts.append(f"{_ORIENTATION_PREFIX}{orientation}")
        parts.append("")

    parts.append((stop.get("narration") or "").strip())
    parts.append("")

    if directions_line:
        parts.append(f"Directions: {directions_line}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n\n"


def _title_line(location: str, tour_type: str, header_category: str,
                display_category: str) -> str:
    if (tour_type or "").lower() in (location or "").lower():
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {display_category} Tour"
    return tour_title + "\n" + f"Tour-Category: {header_category}" + "\n\n"


def _first_recap_sentence(stop: Dict) -> str:
    """Pick ONE short clause that recaps a stop, naming the work.

    Deterministic, no LLM. The clause names the stop's work and states its single
    most concrete fact — preferring a sentence that mentions the artist, a medium,
    a date, or what the work shows, and skipping museum-history / donation
    sentences (those belong to Stop 1, not the recap). Falls back to the stop's
    title alone when no suitable sentence is found, so the recap always names a
    real, delivered stop and never fabricates.
    """
    title = (stop.get("title") or "").strip()
    narration = (stop.get("narration") or "").strip()
    if not narration:
        return title

    sentences = re.split(r'(?<=[.!?])\s+', narration)
    # Museum-history / money / boilerplate openers we do NOT want to echo.
    _history_re = re.compile(
        r'\b(donat|renam|reloc|found|gift|bequest|acquir|'
        r'museum of art|boston college|devlin|mcmullen|lynch|'
        r'this account is drawn|public reference sources|check opening hours|'
        r'before we look|stand before|stand at|observe|position yourself|'
        r'from this vantage|take a moment)\b', re.IGNORECASE)
    # A good recap sentence describes the WORK: medium, subject, maker, date.
    _work_re = re.compile(
        r'\b(depict|portray|shows?|captur|paint|canvas|oil|scene|figure|'
        r'landscape|portrait|created|rendered|composition|measures|'
        r'immerses|biblical|surrealist|retrospective|mosaic|exhibition)\b',
        re.IGNORECASE)
    # Dangling openers: a recap line must stand alone, so reject sentences that
    # begin with a pronoun/connective whose antecedent is in a prior sentence.
    _dangling_re = re.compile(
        r'^(however|this|that|these|those|it|they|he|she|here|'
        r'such|moreover|thus|hence|as a result|before this)\b', re.IGNORECASE)

    best = ""
    for s in sentences:
        s = s.strip()
        if len(s) < 30 or len(s) > 220:
            continue
        if _history_re.search(s) or _dangling_re.match(s):
            continue
        if _work_re.search(s):
            best = s
            break
    if not best:
        # Second pass: first self-contained non-history sentence.
        for s in sentences:
            s = s.strip()
            if (30 <= len(s) <= 220 and not _history_re.search(s)
                    and not _dangling_re.match(s)):
                best = s
                break
    if not best:
        return title
    # One line, naming the stop: "{Title}: {clause}".
    clause = best.rstrip('.')
    # Avoid repeating the title if the sentence already opens with it.
    if clause.lower().startswith(title.lower()):
        return clause + "."
    return f"{title}: {clause}."


def _recap_pick_three(stops: List[Dict]) -> List[Dict]:
    """Choose up to 3 stops to recap, spread across the tour (first, middle, last).

    Recapping every stop reads as a list; Michael's rule is three, one line each.
    For <=3 stops all are used; for more, the first, a middle, and the last are
    taken so the recap spans the whole tour.
    """
    n = len(stops)
    if n <= 3:
        return list(stops)
    return [stops[0], stops[n // 2], stops[-1]]


def _closing_recap(ordered_stops: List[Dict],
                   venue_name: str = "",
                   walk_back_titles: Optional[List[str]] = None,
                   restaurant_offer: bool = True) -> str:
    """[LOCAL-607 defect 2] A real conclusion for an assembled tour.

    Michael heard the old stub ("…you have followed the thread of a single story.
    That's N stops.") as "started and abruptly stopped" — no thread named, no
    stops recapped. This replaces it with a conclusion that, in order:

      1. NAMES the tour's thread — the venue's own collection, so the listener
         hears what held the stops together ("the collection of {venue}").
      2. RECAPS three stops, ONE LINE each, naming the work and its single most
         concrete fact (``_first_recap_sentence``), spread across the tour.
      3. Ends with the RESTAURANT OFFER as the very last sentence — the same house
         wording fresh tours use (generate_tour_text ``_build_closing_offer``),
         so a pooled tour closes exactly like a freshly generated one.

    Deterministic, no LLM: every recapped fact is lifted verbatim from a delivered
    stop's narration, so the conclusion can never reference a stop that is not
    present or state a fact the tour did not deliver (the D177 rule). A walk-back
    line for building tours whose pooled stops sit after the new ones is kept.

    ``ordered_stops`` are the delivered stop units (dicts with title + narration),
    in delivered order.
    """
    if not ordered_stops:
        return ""
    # Accept bare titles too (LOCAL-602 r2 callers/tests pass a list of strings).
    ordered_stops = [s if isinstance(s, dict) else {"title": str(s), "narration": ""}
                     for s in ordered_stops]
    titles = [(s.get("title") or "").strip() for s in ordered_stops]
    first, last = titles[0], titles[-1]
    n = len(ordered_stops)
    stop_word = "stop" if n == 1 else "stops"
    # [LOCAL-602 r2 / D617 item 12] No "From X to X" recap for a 1-stop tour.
    if n < 2:
        lines = [f"That's {n} {stop_word}: {first}."]
        if walk_back_titles:
            names = ", ".join(walk_back_titles)
            lines += [
                "",
                f"If you have toured this place before, the later stops — {names} — "
                f"may already be familiar; feel free to walk back to them at your own pace.",
            ]
        if restaurant_offer:
            lines += ["", "If you would like to eat nearby we can build you a restaurant tour."]
        return "\n".join(lines)

    venue = (venue_name or "").strip()
    thread = f"the collection of {venue}" if venue else "a single collection"
    lines = [
        f"From {first} to {last}, you have followed the thread of {thread}.",
        "",
        f"That's {n} {stop_word} in all.",
    ]

    # One-line recap of three stops.
    recap_stops = _recap_pick_three(ordered_stops)
    recap_lines = []
    for s in recap_stops:
        clause = _first_recap_sentence(s)
        if clause:
            recap_lines.append(clause)
    if recap_lines:
        lines.append("")
        lines.append("Along the way:")
        for rl in recap_lines:
            lines.append(f"- {rl}")

    if walk_back_titles:
        names = ", ".join(walk_back_titles)
        lines += [
            "",
            f"If you have toured this place before, the later stops — {names} — "
            f"may already be familiar; feel free to walk back to them at your own pace.",
        ]

    # [LOCAL-607] The restaurant offer is the VERY LAST sentence — the exact house
    # wording fresh tours use (generate_tour_text._build_closing_offer).
    if restaurant_offer:
        lines += [
            "",
            "If you would like to eat nearby we can build you a restaurant tour.",
        ]

    return "\n".join(lines)


# ── SINGLE-BUILDING assembly ─────────────────────────────────────────────────

def assemble_building_tour(
    location: str,
    tour_type: str,
    tour_category: str,
    header_category: str,
    display_category: str,
    venue_name: str,
    new_stops: List[Dict],
    pooled_stops: List[Dict],
    overall_orientation: Optional[str] = None,
    sources_block: str = "",
    about_stop: Optional[Dict] = None,
    opening_section: str = "",
    venue_address: str = "",
) -> AssemblyResult:
    """Assemble a single-building tour: NEW stops then pooled, with the About +
    practical "opening section" FOLDED INTO Stop 1 (never a standalone stop).

    - [LOCAL-592] ``opening_section`` (from about_museum_stop.build_opening_section)
      is the museum's own story + the practical facts (hours/admission/closed days).
      It is placed at the START of Stop 1 — mirroring the walking-tour prolog that
      rides on Stop-1 Orientation — so a request for N stops delivers EXACTLY N.
      The opening section adds zero stops. ``about_stops`` is reported as 1 (for the
      ledger) when an opening section was folded, but it never changes the count.
    - [LOCAL-585, superseded] ``about_stop`` (a standalone "About <museum>" unit)
      is still accepted for backward compatibility, but it is NO LONGER placed as
      its own stop: if given and no ``opening_section`` is supplied, its narration
      (and any practical facts) are folded into Stop 1 the same way. This guarantees
      no tour ever gains an extra "About …" stop.
    - New stops lead the exhibition stops (so the regenerated overall description
      introduces them).
    - Pooled stop narration + orientation are reused verbatim.
    - Directions are museum/building templates recomputed for the delivered order
      (deterministic, no LLM) — every transition names the next delivered stop.
    - The conclusion is a recap over the full order plus a walk-back line for the
      pooled (now-later) stops.
    - `overall_orientation`, when supplied by the caller (regenerated by
      museum_overview), is injected as the FIRST stop's orientation prefix seed;
      otherwise each stop keeps its own orientation.
    """
    ordered = list(new_stops) + list(pooled_stops)

    # [LOCAL-625 item 3] Last-line guard: a museum stop must be an ARTWORK, never a
    # room/gallery/wing/floor/building. A pooled stop reused from an earlier tour,
    # or a space that slipped past the site-first builder, is dropped here so no
    # room ("Obergeschoss, Kabinett 1-2") ever ships narrated as building history.
    # Replacement happens upstream (corpus fill); shipping one fewer real stop is
    # correct over shipping a room. Opt out only for a space/architecture tour kind.
    if os.environ.get("ALLOW_MUSEUM_SPACE_STOPS", "").strip() != "1":
        try:
            from room_candidate_guard import is_room_or_space_title as _is_room
            _kept = [s for s in ordered
                     if not _is_room((s.get("title") or s.get("name") or ""), venue_name)]
            if len(_kept) != len(ordered):
                _dropped_rooms = [s.get("title") or s.get("name") for s in ordered
                                  if s not in _kept]
                logger.info(f"[LOCAL-625] dropped room/space stops (not artworks): "
                            f"{_dropped_rooms}")
                ordered = _kept
        except Exception as _rg_e:  # pragma: no cover
            logger.info(f"[LOCAL-625] room-stop guard skipped ({_rg_e})")

    n = len(ordered)

    # [LOCAL-592 r2] Address provenance (D611): in a contained venue every
    # exhibition stop is at the building, so its address is the sourced
    # ``venue_address`` — unless the stop's own page states a satellite gallery
    # address. ``venue_bound_address`` keeps a satellite address only when it is
    # supported by the stop's page text; otherwise it uses the venue address.
    # This replaces per-stop LLM-guessed addresses that drift to a town-centre
    # address no source supports (the "1 Washington St" defect).
    if (venue_address or "").strip():
        try:
            from about_museum_stop import venue_bound_address as _vba
        except Exception:
            _vba = None
        if _vba is not None:
            fixed = []
            for s in ordered:
                s2 = dict(s)
                s2["address"] = _vba(
                    s2.get("address", ""), venue_address,
                    stop_page_text=s2.get("_page_text", "") or s2.get("narration", ""))
                fixed.append(s2)
            ordered = fixed

    # [LOCAL-607 defect 3] Cross-stop FACT dedupe (deterministic, no LLM): the
    # donor/founding/relocation story was retold in stops 1,2,3,7. Keep the first
    # telling in tour order; museum-history facts belong to Stop 1's opening
    # section and are removed from later stops (one acquisition sentence about a
    # stop's OWN work is allowed). Runs on the stop NARRATION bodies only.
    try:
        from cross_stop_fact_dedupe import dedupe_stop_units as _dd_units
        ordered, _dd_dropped = _dd_units(ordered, stop1_owns_history=True)
    except Exception as _dd_e:  # pragma: no cover
        logger.info(f"[LOCAL-607] fact dedupe skipped ({_dd_e})")
        _dd_dropped = []
    # [LOCAL-616 item 4] Strip phantom cross-references: a pooled stop reused from
    # an earlier tour can carry a reference to a stop that is NOT in THIS tour
    # (414: "the earlier stops of this tour, such as La Vue du village"). Drop any
    # sentence that cross-references a title not present among the delivered stops.
    try:
        from cross_stop_reference_guard import strip_phantom_references as _spr
        ordered, _phantom_dropped = _spr(ordered)
    except Exception as _spr_e:  # pragma: no cover
        logger.info(f"[LOCAL-616] phantom-reference guard skipped ({_spr_e})")
        _phantom_dropped = []
    # [LOCAL-616 item 5] Drop era-contradicting sentences: a stop whose work date
    # is known must not carry a century/year claim >150y away unless framed as an
    # earlier tradition (414 Stop 3: "In the 13th century…" about a 1782 object).
    try:
        from wrong_era_guard import strip_wrong_era_sentences as _wes
        ordered, _era_dropped = _wes(ordered)
    except Exception as _wes_e:  # pragma: no cover
        logger.info(f"[LOCAL-616] wrong-era guard skipped ({_wes_e})")
        _era_dropped = []
    # [LOCAL-592] Resolve the opening-section text. Prefer the explicit
    # ``opening_section``; fall back to folding a legacy ``about_stop`` unit's
    # narration (+ practical facts) so no caller path can resurrect an extra stop.
    opening = (opening_section or "").strip()
    if not opening and about_stop:
        _about_bits = [(about_stop.get("narration") or "").strip()]
        _pf = (about_stop.get("practical_facts") or "").strip()
        if _pf:
            _about_bits.append(_pf if _pf.endswith((".", "!", "?")) else _pf + ".")
        opening = "\n\n".join(b for b in _about_bits if b).strip()
    folded_opening = bool(opening)

    # [LOCAL-592 r2] Place the opening section on Stop 1 as a DEDICATED field, not
    # inside the stop's narration. The renderer emits it BEFORE the Orientation
    # line, so the four-part order inside Stop 1 is (D611):
    #   (a) About the venue → (b) Visiting information  (the opening section)
    #   (c) the tour overview / Orientation             (overall_orientation)
    #   (d) Stop 1's own narration                       (the stop body)
    # When there are no stops at all, there is nothing to attach it to — the
    # opening is dropped (a no-stop tour is not created, D577).
    if folded_opening and ordered:
        s1 = dict(ordered[0])
        s1["_opening_section"] = opening
        ordered[0] = s1

    # Overall description: the caller regenerates it because it now covers more
    # stops. We seed it into stop 1's Orientation (house behaviour: the overall
    # prolog rides on Stop-1 Orientation). It now renders AFTER the opening section.
    if overall_orientation and ordered:
        s0 = dict(ordered[0])
        base = (s0.get("orientation") or "").strip()
        s0["orientation"] = (overall_orientation.strip() + ("\n\n" + base if base else "")).strip()
        ordered[0] = s0

    body = _title_line(location, tour_type, header_category, display_category)
    for i, stop in enumerate(ordered):
        if i < n - 1:
            directions = _museum_transition(i, n, ordered[i + 1]["title"], venue_name)
        else:
            directions = None
        body += _render_stop_block(stop, i + 1, tour_category, directions)

    walk_back = [s["title"] for s in pooled_stops] if pooled_stops and new_stops else None
    recap = _closing_recap(ordered, venue_name=_venue_name(venue_name or location),
                           walk_back_titles=walk_back)
    tail = recap
    if sources_block.strip():
        tail += ("\n\n" if tail else "") + sources_block.strip()
    body = body.rstrip() + "\n\n" + tail.strip() + "\n"

    return AssemblyResult(
        tour_text=body,
        reused_stops=len(pooled_stops),
        new_stops=len(new_stops),
        rewritten_transitions=0,  # building directions are templates, not LLM rewrites
        order=[s["title"] for s in ordered],
        about_stops=1 if folded_opening else 0,
        dedupe_dropped=len(_dd_dropped) + len(_phantom_dropped) + len(_era_dropped),
        dedupe_log=[
            f"[LOCAL-607] dedupe: dropped from Stop {d['stop']} "
            f"({d['reason']}): \"{d['sentence'][:90]}\"" for d in _dd_dropped]
        + [
            f"[LOCAL-616] phantom-ref: dropped from Stop {d['stop']} "
            f"(names {d['phantom']!r}, not in tour): \"{d['sentence'][:90]}\""
            for d in _phantom_dropped]
        + [
            f"[LOCAL-616] wrong-era: dropped from Stop {d['stop']} "
            f"({d['reason']}): \"{d['sentence'][:90]}\"" for d in _era_dropped],
    )


# ── OUTDOOR assembly ─────────────────────────────────────────────────────────

def _coord(stop: Dict):
    """Extract (lat, lng) from a stop for route ordering, or None."""
    for latk, lngk in (("latitude", "longitude"), ("wikidata_lat", "wikidata_lng")):
        if stop.get(latk) is not None and stop.get(lngk) is not None:
            try:
                return (float(stop[latk]), float(stop[lngk]))
            except (TypeError, ValueError):
                pass
    coords = (stop.get("coordinates") or "").strip()
    if coords:
        m = re.match(r'\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$', coords)
        if m:
            return (float(m.group(1)), float(m.group(2)))
    return None


def assemble_outdoor_tour(
    location: str,
    tour_type: str,
    tour_category: str,
    header_category: str,
    display_category: str,
    new_stops: List[Dict],
    pooled_stops: List[Dict],
    transport_mode: str = "on_foot",
    sources_block: str = "",
    directions_fn: Optional[Callable] = None,
    api_key: str = "",
    shortfall_sentence: str = "",
) -> AssemblyResult:
    """Assemble an outdoor tour: route-order pooled + new, rewrite only neighbours.

    1. Compute the walked order over ALL stops (pooled + new) with
       stop_route_sequencer.sequence_stops (geographic NN + 2-opt).
    2. Identify each insertion point (a new stop) and mark the stops ADJACENT to
       it (the one before and the one after) as needing a rewritten transition.
       Every other stop's narration AND its directions are reused verbatim.
    3. Rewrite only the marked transitions — with directions_fn (LLM) when
       available, else a deterministic "Continue to {name}." template.

    [LOCAL-612 / D616] ``shortfall_sentence`` — when the walked route delivers
    fewer stops than the listener asked for, the caller passes the one honest
    sentence from about_museum_stop.build_shortfall_sentence(mode='outdoor')
    ("We could confirm 4 stops along this route, so this tour has 4 stops rather
    than the 5 you asked for."). It leads Stop 1's opening section (rendered before
    the Orientation line, exactly like the museum opening section). Empty string
    (the default, and whenever the ask was met) adds nothing.

    Returns counts: reused_stops (untouched narration), new_stops, and
    rewritten_transitions (how many directions lines were regenerated).
    """
    try:
        from stop_route_sequencer import sequence_stops
    except Exception as e:  # pragma: no cover
        logger.error(f"[POOL] sequence_stops unavailable: {e}")
        sequence_stops = None

    new_titles = {s["title"] for s in new_stops}
    all_stops = list(pooled_stops) + list(new_stops)

    if sequence_stops is not None:
        ordered = sequence_stops(all_stops, tour_category=tour_category, venue_name="")
    else:  # fallback: pooled then new, no reordering
        ordered = [dict(s, position=i + 1) for i, s in enumerate(all_stops)]

    n = len(ordered)

    # Which positions are new stops (insertions)?
    new_positions = {i for i, s in enumerate(ordered) if s["title"] in new_titles}
    # A transition i→i+1 must be rewritten if either endpoint is new (the stop
    # before and after each insertion). This is the "potentially 4 rewritten for
    # 2 added" rule: each insertion touches its two neighbouring transitions.
    rewrite_transition_at = set()
    for p in new_positions:
        if p < n - 1:
            rewrite_transition_at.add(p)       # new stop → its successor
        if p - 1 >= 0:
            rewrite_transition_at.add(p - 1)   # predecessor → new stop

    # Stops whose NARRATION is reused verbatim = pooled stops that are not new.
    reused_narration = sum(1 for s in ordered if s["title"] not in new_titles)

    # [LOCAL-607 defect 3] Cross-stop FACT dedupe over the walked order. For an
    # outdoor tour there is no single-building "Stop 1 owns the history" rule, so
    # only cross-stop REPEATS are removed (first occurrence in walked order kept);
    # museum-history stripping is left off (stop1_owns_history=False).
    try:
        from cross_stop_fact_dedupe import dedupe_stop_units as _dd_units
        ordered, _dd_dropped = _dd_units(ordered, stop1_owns_history=False)
    except Exception as _dd_e:  # pragma: no cover
        logger.info(f"[LOCAL-607] fact dedupe skipped ({_dd_e})")
        _dd_dropped = []
    # [LOCAL-616 item 4] Strip phantom cross-references for the outdoor route too.
    try:
        from cross_stop_reference_guard import strip_phantom_references as _spr
        ordered, _phantom_dropped = _spr(ordered)
    except Exception as _spr_e:  # pragma: no cover
        logger.info(f"[LOCAL-616] phantom-reference guard skipped ({_spr_e})")
        _phantom_dropped = []

    # [LOCAL-616 item 5] Drop era-contradicting sentences for the outdoor route too.
    try:
        from wrong_era_guard import strip_wrong_era_sentences as _wes
        ordered, _era_dropped = _wes(ordered)
    except Exception as _wes_e:  # pragma: no cover
        logger.info(f"[LOCAL-616] wrong-era guard skipped ({_wes_e})")
        _era_dropped = []

    # [LOCAL-612 / D616] Lead Stop 1 with the honest shortfall sentence when the
    # route delivered fewer stops than asked. It is placed on the first walked
    # stop's dedicated opening-section field, so _render_stop_block renders it
    # before the Orientation line (identical mechanism to the museum opening
    # section) and it is never confused with the stop's own narration.
    _sf = (shortfall_sentence or "").strip()
    if _sf and ordered:
        _existing_open = (ordered[0].get("_opening_section") or "").strip()
        ordered[0]["_opening_section"] = (
            f"{_sf}\n\n{_existing_open}" if _existing_open else _sf)

    body = _title_line(location, tour_type, header_category, display_category)
    rewritten = 0
    for i, stop in enumerate(ordered):
        if i < n - 1:
            next_stop = ordered[i + 1]
            if i in rewrite_transition_at:
                directions = _rewrite_direction(
                    stop, next_stop, location, transport_mode, directions_fn, api_key
                )
                rewritten += 1
            else:
                # Reuse the stop's existing directions verbatim if present, else
                # the sequencer's deterministic hand-off.
                directions = (stop.get("directions") or "").strip() or f"Continue to {next_stop['title']}."
        else:
            directions = None
        body += _render_stop_block(stop, i + 1, tour_category, directions)

    recap = _closing_recap(ordered, venue_name=_venue_name(location))
    tail = recap
    if sources_block.strip():
        tail += ("\n\n" if tail else "") + sources_block.strip()
    body = body.rstrip() + "\n\n" + tail.strip() + "\n"

    return AssemblyResult(
        tour_text=body,
        reused_stops=reused_narration,
        new_stops=len(new_stops),
        rewritten_transitions=rewritten,
        order=[s["title"] for s in ordered],
        dedupe_dropped=len(_dd_dropped) + len(_phantom_dropped) + len(_era_dropped),
        dedupe_log=[
            f"[LOCAL-607] dedupe: dropped from Stop {d['stop']} "
            f"({d['reason']}): \"{d['sentence'][:90]}\"" for d in _dd_dropped]
        + [
            f"[LOCAL-616] phantom-ref: dropped from Stop {d['stop']} "
            f"(names {d['phantom']!r}, not in tour): \"{d['sentence'][:90]}\""
            for d in _phantom_dropped]
        + [
            f"[LOCAL-616] wrong-era: dropped from Stop {d['stop']} "
            f"({d['reason']}): \"{d['sentence'][:90]}\"" for d in _era_dropped],
    )


def _rewrite_direction(from_stop, to_stop, location, transport_mode, directions_fn, api_key):
    """Rewrite one transition's directions, LLM when possible else template."""
    if directions_fn and api_key:
        try:
            txt = directions_fn(
                {"name": from_stop["title"], "address": from_stop.get("address", "")},
                {"name": to_stop["title"], "address": to_stop.get("address", "")},
                location, api_key, transport_mode=transport_mode,
            )
            if txt and txt.strip():
                return txt.strip()
        except Exception as e:
            logger.info(f"[POOL] directions rewrite fell back to template: {e}")
    return f"Continue to {to_stop['title']}."

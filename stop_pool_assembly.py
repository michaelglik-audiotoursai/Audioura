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

    _field("Address", "address")
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


def _closing_recap(order_titles: List[str], walk_back_titles: Optional[List[str]] = None) -> str:
    """Deterministic closing recap in the generator's LOCAL-280 wording.

    The generator composes highlight clauses with an LLM; here we reuse the stable
    skeleton ("From {first} to {last}, you have followed the thread … That's N
    stops") so the recap names only delivered stops and never references a stop
    that is not present. A walk-back line is appended for building tours whose
    pooled stops now sit after the new ones.
    """
    if not order_titles:
        return ""
    first, last = order_titles[0], order_titles[-1]
    n = len(order_titles)
    stop_word = "stop" if n == 1 else "stops"
    # [LOCAL-602 r2 / D617 item 12] A "From {first} to {last}" recap only makes
    # sense across TWO OR MORE stops. With a single stop first == last, so the
    # generator shipped "From WNDR Museum — Overview to WNDR Museum — Overview,
    # you have followed the thread of a single story." — a nonsense sentence. For
    # a 1-stop tour, state the single stop plainly with no From→to clause (this
    # mirrors generate_tour_text._build_closing_recap, which skips the recap for
    # n_delivered < 2).
    if n < 2:
        lines = [f"That's {n} {stop_word}: {first}."]
        if walk_back_titles:
            names = ", ".join(walk_back_titles)
            lines += [
                "",
                f"If you have toured this place before, the later stops — {names} — "
                f"may already be familiar; feel free to walk back to them at your own pace.",
            ]
        return "\n".join(lines)
    lines = [
        f"From {first} to {last}, you have followed the thread of a single story.",
        "",
        f"That's {n} {stop_word}.",
    ]
    if walk_back_titles:
        names = ", ".join(walk_back_titles)
        lines += [
            "",
            f"If you have toured this place before, the later stops — {names} — "
            f"may already be familiar; feel free to walk back to them at your own pace.",
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
    recap = _closing_recap([s["title"] for s in ordered], walk_back_titles=walk_back)
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
) -> AssemblyResult:
    """Assemble an outdoor tour: route-order pooled + new, rewrite only neighbours.

    1. Compute the walked order over ALL stops (pooled + new) with
       stop_route_sequencer.sequence_stops (geographic NN + 2-opt).
    2. Identify each insertion point (a new stop) and mark the stops ADJACENT to
       it (the one before and the one after) as needing a rewritten transition.
       Every other stop's narration AND its directions are reused verbatim.
    3. Rewrite only the marked transitions — with directions_fn (LLM) when
       available, else a deterministic "Continue to {name}." template.

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

    recap = _closing_recap([s["title"] for s in ordered])
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

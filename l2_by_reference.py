"""
l2_by_reference.py — LOCAL-597: the L2 "by reference" tour path (D613).
========================================================================

An L2 (free) tour may only **reuse researched stops that already exist** — the
LOCAL-590 stop pool and the stops of existing non-test tours of the same venue
(or within an outdoor tour's radius). It re-sequences and re-narrates them
through the existing pool assembly (stop_pool_assembly), regenerating only the
orientation / adjacent transitions and folding the D611 opening section in from
STORED material. It must issue **zero grounded Gemini requests and zero Serper
queries** (SUBSCRIPTION_LEVELS.md §"L2 by reference"). If there is no reusable
material, the listener gets an actionable refusal — never a fresh generation.

This module has two public pieces:

  1. THE GUARD. `grounding_forbidden()` is a context manager that, for its
     duration, makes any grounded `story_leads` call and any `work_story_searcher`
     Serper query RAISE `GroundingForbiddenError` instead of hitting the network.
     The two choke points (story_leads._gemini / gemini_with_sources with
     grounded=True, and work_story_searcher._serp_search) consult
     `grounding_is_forbidden()` at call time and raise. This is the belt-and-braces
     proof that an L2 build cannot spend a cent on grounding or SERP: not only does
     the by-reference path never call them, but if some future refactor wired a
     grounded call into it, the build would fail loudly rather than silently bill.

  2. THE PATH. `build_by_reference_tour(...)` resolves reusable material, and
     either returns an assembled tour (reusing >= N stops, zero grounding) or a
     structured refusal (`by_reference_no_material`) carrying up to three nearby
     existing tours. `check_zero_grounding()` reads the LOCAL-594 counters so a
     caller/test can assert the build spent nothing on grounding.

The guard is a process-global toggle guarded by a lock and implemented as a depth
counter so nested `with` blocks compose. It is deliberately conservative: when
the flag is on, EVERY grounded request raises, no matter who issues it.
"""
import logging
import os
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# THE GUARD
# ─────────────────────────────────────────────────────────────────────────────
class GroundingForbiddenError(RuntimeError):
    """Raised when a grounded Gemini request or a Serper query is attempted while
    an L2 by-reference build is active. An L2 tour reuses already-researched
    material only; reaching the network for fresh grounding/SERP is a bug, and
    this error turns that bug into a hard, visible failure instead of a silent
    charge."""


# Depth counter (not a bool) so nested guard blocks compose correctly: the guard
# only lifts when the outermost block exits. Guarded by a lock because grounded
# calls fan out across worker threads (story pass / gates), and the by-reference
# path must forbid grounding on every one of them.
_guard_lock = threading.RLock()
_guard_depth = 0


def grounding_is_forbidden() -> bool:
    """True while any L2 by-reference build is active. The two grounding/SERP
    choke points consult this and raise GroundingForbiddenError when it is True."""
    with _guard_lock:
        return _guard_depth > 0


def _enter_guard() -> None:
    global _guard_depth
    with _guard_lock:
        _guard_depth += 1


def _exit_guard() -> None:
    global _guard_depth
    with _guard_lock:
        if _guard_depth > 0:
            _guard_depth -= 1


@contextmanager
def grounding_forbidden():
    """Context manager: forbid grounded Gemini + Serper for its duration.

    Also resets the LOCAL-594 grounding counters on entry so a caller/test can
    read them afterwards and assert they stayed at 0. Resetting is best-effort
    (story_leads may be unavailable in an isolated unit test); the raise-on-call
    guard does not depend on it.
    """
    _enter_guard()
    try:
        try:
            import story_leads
            story_leads.reset_grounding_requests()
        except Exception as e:  # pragma: no cover - counter reset is best-effort
            logger.info(f"[LOCAL-597] grounding counter reset skipped: {e}")
        yield
    finally:
        _exit_guard()


def _raise_if_forbidden(what: str) -> None:
    """Raise GroundingForbiddenError if a grounding/SERP guard is active.

    Called from the grounded-Gemini and Serper choke points. `what` names the
    attempted operation for the error message and the log line.
    """
    if grounding_is_forbidden():
        logger.error(f"[LOCAL-597] GUARD TRIPPED: {what} attempted during an L2 "
                     f"by-reference build — raising GroundingForbiddenError")
        raise GroundingForbiddenError(
            f"{what} is forbidden during an L2 by-reference build "
            f"(zero grounding, zero SERP)."
        )


def check_zero_grounding() -> Dict[str, int]:
    """Return the LOCAL-594 grounding meter: {requests, queries}. A by-reference
    build must leave both at 0. Best-effort: if story_leads is unavailable the
    meter is reported as 0 (nothing could have been counted)."""
    try:
        import story_leads
        return {
            "requests": int(story_leads.get_grounding_requests()),
            "queries": int(story_leads.get_grounding_queries()),
        }
    except Exception as e:  # pragma: no cover
        logger.info(f"[LOCAL-597] grounding meter read skipped: {e}")
        return {"requests": 0, "queries": 0}


# ─────────────────────────────────────────────────────────────────────────────
# THE REFUSAL (LOCAL-580 contract)
# ─────────────────────────────────────────────────────────────────────────────
# The exact user-facing copy D613 requires. Kept as constants so the test and the
# live path assert the same string.
NO_MATERIAL_MESSAGE = "This place hasn't been researched yet on the free level."
NO_MATERIAL_SUGGESTION_PREFIX = (
    "Buy a $10 pack for a freshly researched tour, or pick one of these nearby tours: "
)
NO_MATERIAL_SUGGESTION_NONE = (
    "Buy a $10 pack for a freshly researched tour."
)


def _refusal(nearby_tours: List[Dict]) -> Dict:
    """Build the by_reference_no_material refusal with up to 3 nearby tours.

    Follows the LOCAL-580 structured-refusal contract (allowed/error_code/error/
    message/suggestion) so the app renders it exactly like every other refusal.
    The suggestion names the nearby tours (id + name) when any were found; with
    none it drops the "or pick …" clause rather than dangle an empty list.
    """
    picks = nearby_tours[:3]
    if picks:
        listed = "; ".join(f"{t['name']} (#{t['id']})" for t in picks)
        suggestion = NO_MATERIAL_SUGGESTION_PREFIX + listed + "."
    else:
        suggestion = NO_MATERIAL_SUGGESTION_NONE
    return {
        "allowed": False,
        "error_code": "by_reference_no_material",
        "error": NO_MATERIAL_MESSAGE,       # legacy field for pre-LOCAL-581 clients
        "message": NO_MATERIAL_MESSAGE,
        "suggestion": suggestion,
        "nearby_tours": picks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL LOOKUP (stop pool + existing non-test tours)
# ─────────────────────────────────────────────────────────────────────────────
def _db_conn(db_url: str):
    import psycopg2
    return psycopg2.connect(db_url)


def _existing_tour_stops(location: str, tour_type: str, db_url: str,
                         identity: str) -> List[Dict]:
    """Parse reusable stop units from existing NON-TEST tours of the same venue.

    A tour qualifies when its normalised request_string OR tour_name resolves to
    the SAME venue identity as the request (the whole-tour cache's normalisation,
    which the pool identity also uses). Translations (original_tour_id NOT NULL)
    and test rows (is_test) are excluded — only originals of real tours are mined.
    Each tour's stored ``tour_content`` is parsed with the pool's own
    parse_delivered_stops, so the units are byte-compatible with pooled stops.

    No network, no LLM, no grounding — pure DB read + text parse. Returns [] on
    any error (treated as "no existing material", distinct from a crash).
    """
    try:
        import stop_pool_store as pool
    except Exception as e:
        logger.info(f"[LOCAL-597] pool store unavailable for existing-tour mining: {e}")
        return []

    rows = []
    try:
        conn = _db_conn(db_url)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tour_name, request_string, tour_content
                FROM audio_tours
                WHERE tour_content IS NOT NULL
                  AND (is_test IS NOT TRUE)
                  AND original_tour_id IS NULL
                """
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.info(f"[LOCAL-597] existing-tour read error: {e}")
        return []

    units: List[Dict] = []
    seen = set()
    for _id, tour_name, request_string, tour_content in rows:
        # Same-venue test: either the request string or the tour name normalises
        # to the request's venue identity (location-based identity, so it matches
        # whether or not a QID was ever resolved).
        rs_identity = pool.venue_identity(request_string or "")
        tn_identity = pool.venue_identity(tour_name or "")
        if identity not in (rs_identity, tn_identity):
            continue
        for u in pool.parse_delivered_stops(tour_content or ""):
            tnorm = pool._title_norm(u["title"])
            if not tnorm or tnorm in seen:
                continue
            seen.add(tnorm)
            u = dict(u)
            u["_source_tour_id"] = _id
            units.append(u)
    logger.info(f"[LOCAL-597] mined {len(units)} reusable stop(s) from existing "
                f"non-test tours for {identity}")
    return units


def _nearby_existing_tours(location: str, db_url: str, limit: int = 3) -> List[Dict]:
    """Return up to `limit` existing NON-TEST tours nearest the requested venue.

    Mirrors the tours-near query (map_delivery_service): originals only, test rows
    and translations excluded, lat/lng present. "Nearby" is ranked by haversine
    distance from the venue's resolved coordinates; when the venue cannot be
    geocoded (offline / unresolvable), it falls back to the most-requested tours
    so the refusal always offers something actionable. Pure DB + arithmetic.
    """
    try:
        conn = _db_conn(db_url)
    except Exception as e:
        logger.info(f"[LOCAL-597] nearby-tours DB connect failed: {e}")
        return []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tour_name, lat, lng, number_requested
                FROM audio_tours
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND (is_test IS NOT TRUE)
                  AND original_tour_id IS NULL
                """
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.info(f"[LOCAL-597] nearby-tours read error: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    anchor = _resolve_coords(location)
    scored = []
    for _id, name, lat, lng, popularity in rows:
        entry = {"id": _id, "name": name, "lat": lat, "lng": lng,
                 "popularity": popularity or 0}
        if anchor and lat is not None and lng is not None:
            entry["distance_km"] = _haversine_km(anchor, (float(lat), float(lng)))
        else:
            entry["distance_km"] = None
        scored.append(entry)

    # [LEAD 2026-10-06] "Nearby" must mean nearby. Without an anchor, or beyond
    # NEARBY_MAX_KM, list nothing: a Boston listener offered Nice and Abu Dhabi
    # tours as "nearby" (r1 live run) is worse than no list.
    if not anchor:
        return []
    _max_km = float(os.getenv("NEARBY_MAX_KM", "50"))
    scored = [e for e in scored if e["distance_km"] is not None and e["distance_km"] <= _max_km]
    scored.sort(key=lambda e: e["distance_km"])
    return scored[:limit]


def _resolve_coords(location: str):
    """Resolve a venue to (lat, lng) for nearby ranking, or None. Best-effort via
    venue_resolver; any failure (no network / unresolvable) returns None and the
    caller falls back to popularity ranking. This is a COORDINATE lookup, not a
    grounded research call — it issues no Gemini/Serper request."""
    try:
        from venue_resolver import resolve_venue
        ent = resolve_venue(location)
        if ent is not None:
            lat = getattr(ent, "lat", None)
            lng = getattr(ent, "lng", None)
            if lat is not None and lng is not None:
                return (float(lat), float(lng))
    except Exception as e:
        logger.info(f"[LOCAL-597] coord resolve for nearby ranking failed: {e}")
    return None


def _haversine_km(a, b) -> float:
    import math
    (lat1, lng1), (lat2, lng2) = a, b
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    x = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(x))


def gather_material(location: str, tour_type: str, db_url: str) -> List[Dict]:
    """All reusable stop units for this venue: pooled stops first, then stops of
    existing non-test tours of the same venue (deduped by title). No network.

    Pooled stops lead because they are already audio-independent units with a
    stable order_seq; existing-tour stops fill in anything the pool has not
    captured yet. The result is the pool of material the assembler re-sequences.
    """
    try:
        import stop_pool_store as pool
    except Exception as e:
        logger.info(f"[LOCAL-597] pool store unavailable: {e}")
        return []

    identity = pool.resolve_venue_identity(location)
    qid = identity[4:] if identity.startswith("qid:") else None

    pooled_rows = pool.get_pool_stops(location, tour_type, db_url, qid=qid)
    units = [_pooled_unit(r) for r in pooled_rows]
    seen = {pool._title_norm(r["title"]) for r in pooled_rows}

    # Mine existing non-test tours of the same venue (location identity, so it
    # matches whether or not a QID was resolved when the pool was written).
    loc_identity = pool.venue_identity(location)
    for u in _existing_tour_stops(location, tour_type, db_url, loc_identity):
        tnorm = pool._title_norm(u["title"])
        if tnorm in seen:
            continue
        seen.add(tnorm)
        units.append(_existing_unit(u))
    return units


def _pooled_unit(row: Dict) -> Dict:
    """A stop_pool row → an assembly stop unit (reuses the orchestrator's shape)."""
    import re
    orientation = ""
    raw = row.get("raw_block") or ""
    m = re.search(r'^Orientation:\s*(.+?)\s*$', raw, re.M)
    if m:
        orientation = m.group(1).strip()
    return {
        "title": row["title"],
        "artist": row.get("artist", ""),
        "year": row.get("year", ""),
        "narration": row["narration"],
        "orientation": orientation,
        "address": row.get("address", ""),
        "coordinates": row.get("coordinates", ""),
        "type_specialty": row.get("type_specialty", ""),
        "specific_examples": row.get("specific_examples", ""),
        "operational_details": row.get("operational_details", ""),
        "sources": row.get("sources", []) or [],
        # [LOCAL-609] carry the stored per-stop research cost so a by-reference
        # delivery can report research_cost_reused.
        "research_cost_usd": float(row.get("research_cost_usd", 0.0) or 0.0),
        "_pool_reused": True,
    }


def _existing_unit(stop: Dict) -> Dict:
    """A parsed existing-tour stop → an assembly stop unit."""
    import re
    orientation = ""
    raw = stop.get("raw_block") or ""
    m = re.search(r'^Orientation:\s*(.+?)\s*$', raw, re.M)
    if m:
        orientation = m.group(1).strip()
    return {
        "title": stop["title"],
        "artist": stop.get("artist", ""),
        "year": stop.get("year", ""),
        "narration": stop["narration"],
        "orientation": orientation,
        "address": stop.get("address", ""),
        "coordinates": stop.get("coordinates", ""),
        "type_specialty": stop.get("type_specialty", ""),
        "specific_examples": stop.get("specific_examples", ""),
        "operational_details": stop.get("operational_details", ""),
        "sources": [],
        "_pool_reused": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# THE PATH
# ─────────────────────────────────────────────────────────────────────────────
def build_by_reference_tour(
    location: str,
    tour_type: str,
    total_stops: int,
    db_url: str,
    output_file: Optional[str] = None,
) -> Dict:
    """Build an L2 by-reference tour, or return a structured refusal.

    The whole build runs inside `grounding_forbidden()`: any grounded Gemini
    request or Serper query raises GroundingForbiddenError. It reuses already-
    researched stops only (the stop pool + existing non-test tours of the venue),
    assembles them through stop_pool_assembly (re-sequence, regenerate orientation
    + adjacent transitions, fold the D611 opening from STORED material), and spends
    nothing on grounding/SERP.

    Returns one of:
      * an ALLOW dict:
          {allowed: True, mode: 'by_reference', text, reused_stops, new_stops: 0,
           rewritten_transitions, about_stops, grounding: {requests, queries},
           served_from_pool_only: True, new_cost: 0.0}
      * a REFUSAL dict (by_reference_no_material) with up to 3 nearby tours.

    N (total_stops) must be <= max_stops (5 for L2); the caller's levels check has
    already clamped/validated it. If fewer than N reusable stops exist, this
    REFUSES — it never triggers fresh research to top up (D613).
    """
    import stop_pool_assembly as asm
    import stop_pool_orchestrator as orch

    N = int(total_stops or 0)

    with grounding_forbidden():
        material = gather_material(location, tour_type, db_url)
        K = len(material)
        tour_category = orch._classify(location, tour_type)
        contained = orch._is_contained(tour_category)
        header_cat, display_cat = orch._header_categories(tour_category, tour_type)
        logger.info(f"[LOCAL-597] by-reference: venue={location!r} type={tour_type} "
                    f"category={tour_category} contained={contained} "
                    f"requested={N} reusable={K}")

        # Not enough reusable material → actionable refusal (never fresh research).
        if K < N or K == 0:
            nearby = _nearby_existing_tours(location, db_url, limit=3)
            refusal = _refusal(nearby)
            refusal["grounding"] = check_zero_grounding()
            logger.info(f"[LOCAL-597] by-reference REFUSED ({K} reusable < {N} "
                        f"requested); offering {len(refusal['nearby_tours'])} nearby")
            return refusal

        # Serve the best N from the reusable material. The D611 opening section is
        # folded from STORED material only (opening_from_material), never a web
        # fetch, so the build stays zero-grounding.
        chosen = material[:N]
        sources_block = _sources_block(chosen)
        if contained:
            opening = _opening_from_material(location, chosen)
            result = asm.assemble_building_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                venue_name=orch._venue_name(location),
                new_stops=[], pooled_stops=chosen,
                overall_orientation=None, sources_block=sources_block,
                opening_section=opening or "",
                venue_address="",   # no web fetch; stop addresses are reused as stored
            )
        else:
            result = asm.assemble_outdoor_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                new_stops=[], pooled_stops=chosen,
                transport_mode=orch._transport_mode(tour_type),
                sources_block=sources_block,
                directions_fn=None,   # deterministic templates only — no LLM
                api_key="",
            )

        if output_file:
            orch._write(output_file, result.tour_text)

        grounding = check_zero_grounding()
        logger.info(f"[LOCAL-597] by-reference DELIVERED: reused={result.reused_stops} "
                    f"rewritten_transitions={result.rewritten_transitions} "
                    f"about_stops={result.about_stops} grounding={grounding}")
        return {
            "allowed": True,
            "mode": "by_reference",
            "text": result.tour_text,
            "reused_stops": result.reused_stops,
            "new_stops": 0,
            "rewritten_transitions": result.rewritten_transitions,
            "about_stops": result.about_stops,
            "order": result.order,
            "grounding": grounding,
            "served_from_pool_only": True,
            "new_cost": 0.0,
            # [LOCAL-609] sum of the reused stops' original research cost
            "research_cost_reused": sum(
                float(u.get("research_cost_usd", 0.0) or 0.0) for u in chosen
            ),
        }


def _sources_block(units: List[Dict]) -> str:
    """A Sources block built from the stored per-stop sources (no new research)."""
    urls = []
    for u in units:
        for s in (u.get("sources") or []):
            if s and s not in urls:
                urls.append(s)
    if not urls:
        return ""
    return f"Sources: This tour draws on information from {', '.join(urls)}."


def _opening_from_material(location: str, units: List[Dict]) -> str:
    """Fold a D611-style opening section from STORED material only.

    D613 requires the opening to be folded "from stored material" with zero
    grounding — so, unlike the full generator (which fetches the venue's own
    pages), this composes a short orientation from the already-researched pooled
    stops: it names the venue and the stops the listener will reach. If a pooled
    stop already carried an opening/About section in its stored block, that text
    is preferred verbatim. Returns "" when nothing can be composed (then the tour
    simply opens on Stop 1, which is valid — D577).
    """
    import re
    # Prefer a stored opening/About section if one survives in a raw block.
    for u in units:
        raw = u.get("_opening_section") or ""
        if raw.strip():
            return raw.strip()
    venue = location.split(",")[0].strip() if location else ""
    if not venue or not units:
        return ""
    names = [u["title"] for u in units if u.get("title")]
    if not names:
        return ""
    if len(names) == 1:
        tour_of = names[0]
    else:
        tour_of = ", ".join(names[:-1]) + f", and {names[-1]}"
    return (f"Welcome to {venue}. This tour revisits {tour_of} — "
            f"stops drawn from tours already researched here.")

"""
Stop Pool Orchestrator (LOCAL-590) — reuse pooled stops, generate only the new.
================================================================================
This is the pool's entry point into tour generation. Given a request for N stops
of a venue, it:

  1. Resolves the venue identity (QID-first) and reads the pool (K stops).
  2. Classifies the tour as single-building (museum/facility — contained) or
     outdoor (walking/biking/driving), using the generator's own classifier.
  3. Decides reuse:
        N <= K  → serve the best N from the pool, no new generation at all.
        N >  K  → generate exactly N-K NEW stops (passing the pooled titles as an
                  exclusion so selection never re-picks them; R4 replenishment
                  still fills the count), then merge pooled + new.
  4. Hands pooled + new stop units to stop_pool_assembly, which places them per
     the building / outdoor rules and re-stitches orientation / directions /
     conclusion. Narration of reused stops is never regenerated — the saving.
  5. Stores the delivered tour back into the pool (adds the new stops).
  6. Returns the delivered text plus the reuse counts the cost ledger records
     (reused_stops / new_stops / rewritten_transitions).

It is deliberately OUTSIDE the generator's gate chain: the generator only ever
sees the fresh new stops (so every existence/scope/dedup gate runs on them
normally), and all merge logic lives in the pure, unit-tested assembly module.

Opt-in: `maybe_generate_with_pool` returns None when pooling does not apply (no
DB, pooling disabled, or an empty pool with a full-size request), so the caller
falls back to the normal single generation path unchanged.
"""
import contextlib
import logging
import os
import re
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _suppress_inline_shortfall():
    """[LOCAL-612] Suppress the main delivery loop's inline D616 shortfall sentence
    for the duration of a nested generate_fn call.

    The orchestrator re-assembles the tour after this nested call and folds the
    honest shortfall sentence into Stop 1 itself (the museum opening section, or
    the outdoor opening section via assemble_outdoor_tour), so the inner main loop
    must NOT also inject it — that would double-emit. A dedicated module flag on
    generate_tour_text is used (DISABLE_STOP_POOL is set by legitimate direct
    runners too, so it is not a safe discriminator). Best-effort: if the module is
    unavailable the context is a no-op.
    """
    gtt = None
    prev = None
    try:
        import generate_tour_text as gtt
        prev = getattr(gtt, "_SUPPRESS_INLINE_SHORTFALL", False)
        gtt._SUPPRESS_INLINE_SHORTFALL = True
    except Exception:
        gtt = None
    try:
        yield
    finally:
        if gtt is not None:
            gtt._SUPPRESS_INLINE_SHORTFALL = bool(prev)


def _is_contained(tour_category: str) -> bool:
    """Single-building (contained) venue: museum or facility."""
    return (tour_category or "").strip().lower() in ("museum", "facility")


def _looks_contained_request(location: str) -> bool:
    """[LOCAL-585] Lightweight contained-venue-request check for the pool layer.

    The pool runs BEFORE Phase-1 resolution, so it cannot call the generator's
    intent-based _is_contained_venue_request. But the SHAPE Michael flagged —
    "<theme> tour in/inside/at <named building>" where the building name ends in
    an institutional tail noun (museum, library, athenaeum, gallery, house …) —
    is decidable from the request text alone, and it is exactly the Boston
    Athenaeum case the shallow classifier mislabels 'walking'. This mirrors
    generate_tour_text._is_contained_venue_request's deterministic tail test so
    the About stop can lead a themed-in-building tour too. Conservative: both an
    interior preposition AND an institutional tail word must be present.
    """
    try:
        from generate_tour_text import _INTERIOR_PREP_RE, _CONTAINED_VENUE_TAIL
    except Exception:
        return False
    loc = location or ""
    if not _INTERIOR_PREP_RE.search(loc):
        return False
    words = re.findall(r"[a-z\u00e6\u00e9\u00e8\u00e2\u00ee\u00f4\u00fb]+", loc.lower())
    return any(w in _CONTAINED_VENUE_TAIL for w in words)


def _classify(location: str, tour_type: str) -> str:
    """Classify via the generator's own classifier; fall back to tour_type.

    [LOCAL-585] When the shallow classifier does not yield a contained category
    but the request is clearly a themed tour held INSIDE a named institution
    (Athenaeum case), treat it as a museum tour so the About stop can lead and the
    assembler renders museum-style blocks. This only promotes to 'museum'; it
    never demotes an already-contained verdict.
    """
    try:
        from generate_tour_text import _classify_tour_category
        cat = _classify_tour_category(location, tour_type)
    except Exception as e:
        logger.info(f"[POOL] classifier unavailable ({e}); using tour_type as category")
        cat = (tour_type or "").strip().lower()
    if not _is_contained(cat) and _looks_contained_request(location):
        logger.info(f"[LOCAL-585] contained-venue request detected; "
                    f"treating {location!r} as a museum tour (was {cat!r})")
        return "museum"
    return cat


def _pooled_unit_from_row(row: Dict) -> Dict:
    """Convert a stop_pool row into an assembly stop unit.

    Narration is the pooled body. Orientation is sequence-dependent and was NOT
    pooled, but the stop's ORIGINAL orientation text survives inside raw_block;
    we recover it so a reused stop keeps a sensible position aid (the delivered
    order may still differ, and the assembly recomputes directions regardless).
    """
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
        "_pool_reused": True,
    }


def _new_unit_from_parsed(stop: Dict) -> Dict:
    """Convert a parsed delivered stop (stop_pool_store.parse_delivered_stops) into
    an assembly stop unit, recovering the per-stop orientation from raw_block."""
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
        "_pool_reused": False,
    }


def _header_categories(tour_category: str, tour_type: str) -> Tuple[str, str]:
    """(header_category, display_category) mirroring the generator's header."""
    cat = (tour_category or tour_type or "museum").strip().lower()
    display = {
        "museum": "Museum", "facility": "Facility", "walking": "Walking",
        "restaurant": "Restaurant", "book": "Book",
    }.get(cat, cat.capitalize() or "Museum")
    return cat, display


def _extract_sources_block(tour_text: str) -> str:
    m = re.search(r'(?ms)^\s*Sources:\s.*\Z', tour_text or "")
    return m.group(0).strip() if m else ""


def maybe_generate_with_pool(
    location: str,
    tour_type: str,
    total_stops: int,
    db_url: str,
    generate_fn,
    output_file: Optional[str] = None,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    api_key: str = "",
) -> Optional[dict]:
    """Try to satisfy the request from the pool + only the new stops.

    Args:
        generate_fn: the generator entry (generate_tour_text), called as
            generate_fn(location, tour_type, output_file, total_stops,
                        user_id=..., job_id=..., exclude_titles=[...]).
        db_url: Postgres URL for the pool store.

    Returns a dict:
        {text, reused_stops, new_stops, rewritten_transitions, pooled_before,
         served_from_pool_only, new_cost}
    or None when pooling does not apply and the caller should generate normally.
    """
    if os.environ.get("DISABLE_STOP_POOL", "").strip() == "1":
        return None
    if not db_url or not total_stops:
        return None

    try:
        import stop_pool_store as pool
        import stop_pool_assembly as asm
    except Exception as e:
        logger.info(f"[POOL] modules unavailable ({e}); normal generation")
        return None

    identity = pool.resolve_venue_identity(location)
    qid = identity[4:] if identity.startswith("qid:") else None

    pooled_rows = pool.get_pool_stops(location, tour_type, db_url, qid=qid)
    K = len(pooled_rows)
    N = int(total_stops)
    tour_category = _classify(location, tour_type)
    contained = _is_contained(tour_category)
    header_cat, display_cat = _header_categories(tour_category, tour_type)
    print(f"  [LOCAL-590] pool: venue={identity} type={tour_type} category={tour_category} "
          f"contained={contained} requested={N} pooled={K}")

    # Nothing to reuse and a full request.
    if K == 0:
        # [LOCAL-585] First-ever tour of a CONTAINED venue (museum/facility): there
        # is nothing pooled to reuse, but the tour should still OPEN with the
        # museum's own story. Generate the N exhibition stops normally (so every
        # existence/scope/dedup gate runs on them), then re-assemble with an
        # "About <museum>" stop leading. If no story can be sourced, or anything
        # fails, fall through to normal generation unchanged (return None).
        if not contained or os.environ.get("DISABLE_ABOUT_STOP", "").strip() == "1":
            return None
        try:
            opening_section = _build_opening_section(
                location, tour_type, request_text=location,
                available_exhibition_stops=N, requested_stops=N)
            if not opening_section:
                return None
            # Guard against pool re-entry: the inner full generation must run the
            # NORMAL path (exclude_titles=[] is falsy and would re-trigger the pool
            # fast-path, recursing). Disable the pool just for this nested call.
            _prev_disable = os.environ.get("DISABLE_STOP_POOL")
            os.environ["DISABLE_STOP_POOL"] = "1"
            # [LOCAL-612] This nested run is a CONTAINED venue the orchestrator will
            # re-assemble with an opening section that folds in the shortfall
            # sentence itself. Suppress the main loop's own inline injection so the
            # sentence is emitted exactly once (not twice).
            try:
                with _suppress_inline_shortfall():
                    gen_text, _out, _coords = generate_fn(
                        location, tour_type, None, N,
                        user_id=user_id, job_id=job_id, exclude_titles=[],
                    )
            finally:
                if _prev_disable is None:
                    os.environ.pop("DISABLE_STOP_POOL", None)
                else:
                    os.environ["DISABLE_STOP_POOL"] = _prev_disable
            if not gen_text:
                return None
            try:
                from generate_tour_text import _LAST_GENERATION_COST as _nc
                # [LOCAL-615 item 3] The first-tour delivery cost MUST be the sum of
                # ALL provider channels (OpenAI + Serper + TTS + Gemini grounding +
                # Gemini Flash tokens + preflight), not OpenAI alone. The inner
                # generate_fn ran the NORMAL path (DISABLE_STOP_POOL=1), whose
                # reconcile sets _LAST_GENERATION_COST['tour_total_cost'] to exactly
                # that counted sum. Reading 'total_cost' here (OpenAI only) is what
                # made cost_ledger.our_cost_usd undercount by the whole grounding +
                # Flash + Serper bill on a first tour (D626: $0.5237 OpenAI-only vs
                # the real total). Prefer tour_total_cost; fall back to total_cost
                # only if the richer field is absent.
                first_cost = float(
                    (_nc or {}).get("tour_total_cost",
                                    (_nc or {}).get("total_cost", 0.0)) or 0.0)
            except Exception:
                first_cost = 0.0
            parsed = pool.parse_delivered_stops(gen_text)
            new_units = [_new_unit_from_parsed(s) for s in parsed]
            if not new_units:
                return None
            # [LOCAL-600 / D616] If the site-first exhibition path could not reach
            # the requested N from verified on-view material, say so in Stop 1's
            # opening section — one honest sentence from the real counts.
            _shortfall_sentence = _site_first_shortfall_sentence(
                location, len(new_units), N)
            # [LOCAL-615 item 2] Fold the LOCAL-603 preflight hours into the FRESH
            # path's opening section. The opening section was first built ABOVE,
            # BEFORE generate_fn ran — and generate_fn is where the venue preflight
            # runs and populates generate_tour_text._LAST_VENUE_PREFLIGHT. So the
            # first build could not see the preflight hours and fell back to
            # "Check opening hours and admission on <domain> before you go."
            # (D626 Bilbao: hours=y admission=y preflight, yet the fallback shipped).
            # Now that generation is done and the preflight result is populated,
            # rebuild the opening section unconditionally: _build_opening_section's
            # LOCAL-607 fold now sees the preflight and composes the real hours.
            # The shortfall sentence (if any) is folded in by the same rebuild, so
            # this replaces the former shortfall-only rebuild without losing it.
            _rebuilt_opening = _build_opening_section(
                location, tour_type, request_text=location,
                available_exhibition_stops=len(new_units), requested_stops=N,
                shortfall_sentence=_shortfall_sentence or "")
            if _rebuilt_opening:
                opening_section = _rebuilt_opening
                print(f"  [LOCAL-615] opening section rebuilt post-generation "
                      f"(preflight hours now available)")
            if _shortfall_sentence:
                print(f"  [LOCAL-600] D616 shortfall sentence folded into Stop 1: "
                      f"{_shortfall_sentence!r}")
            sources_block = _extract_sources_block(gen_text)
            result = asm.assemble_building_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                venue_name=_venue_name(location),
                new_stops=new_units, pooled_stops=[],
                overall_orientation=_overall_from_new(gen_text),
                sources_block=sources_block,
                opening_section=opening_section,
                venue_address=_resolve_venue_address(location),
            )
            # [LOCAL-615 item 2] Final guard on the delivered text: never ship the
            # "Check opening hours and admission on <domain>" fallback when the
            # preflight (just run inside generate_fn) has real hours.
            result.tour_text = _fold_preflight_hours_into_text(result.tour_text)
            _emit_result(output_file, result)
            # Store the exhibition stops to seed the pool (the opening section is
            # NOT pooled; it is a sequence-level opener, regenerated per tour like
            # orientation — LOCAL-590/592).
            try:
                pool.store_delivered_tour(location, tour_type, gen_text, db_url, qid=qid)
            except Exception as _se:
                logger.info(f"[LOCAL-592] pool store (first tour) skipped: {_se}")
            print(f"  [LOCAL-592] FIRST-TOUR opening section folded into Stop 1: "
                  f"about_stops={result.about_stops} exhibition_stops={len(new_units)}")
            return {
                "text": result.tour_text,
                "reused_stops": 0,
                "new_stops": len(new_units),
                "rewritten_transitions": 0,
                "about_stops": result.about_stops,
                "pooled_before": 0,
                "served_from_pool_only": False,
                "new_cost": first_cost,
                # [LOCAL-609] first-ever tour of this venue — nothing reused
                "research_cost_reused": 0.0,
                "new_breakdown": _new_breakdown_from_last(),
            }
        except Exception as e:
            logger.info(f"[LOCAL-592] first-tour opening-section fold failed ({e}); normal gen")
            return None

    # ─── N <= K : serve the best N from the pool, no new generation ───────────
    if N <= K:
        if contained:
            # [LOCAL-600 / D616] Re-group all pooled units (show→its works) BEFORE
            # selecting N, so slicing never splits a work from its show (the r3
            # pool stored them works-first). Then take the first N in group order.
            _all_units = _regroup_pooled_units(
                [_pooled_unit_from_row(r) for r in pooled_rows])
            pooled_units = _all_units[:N]
            _chosen_titles = {u["title"] for u in pooled_units}
            chosen = [r for r in pooled_rows if r["title"] in _chosen_titles]
        else:
            chosen = pooled_rows[:N]
            pooled_units = [_pooled_unit_from_row(r) for r in chosen]
        sources_block = _sources_from_rows(chosen)
        if contained:
            # [LOCAL-600] N <= K means the pool can satisfy the request in full, so
            # there is NO shortfall (D611 exact N). No shortfall sentence here.
            opening_section = _build_opening_section(
                location, tour_type, request_text=location,
                available_exhibition_stops=len(pooled_units),
                requested_stops=N)
            result = asm.assemble_building_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                venue_name=_venue_name(location),
                new_stops=[], pooled_stops=pooled_units,
                overall_orientation=None, sources_block=sources_block,
                opening_section=opening_section or "",
                venue_address=_resolve_venue_address(location),
            )
        else:
            result = asm.assemble_outdoor_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                new_stops=[], pooled_stops=pooled_units,
                transport_mode=_transport_mode(tour_type),
                sources_block=sources_block,
            )
        _emit_result(output_file, result)
        pool.bump_hit_counts(location, tour_type, [u["title"] for u in pooled_units], db_url, qid=qid)
        return {
            "text": result.tour_text,
            "reused_stops": result.reused_stops,
            "new_stops": 0,
            "rewritten_transitions": result.rewritten_transitions,
            "about_stops": result.about_stops,
            "pooled_before": K,
            "served_from_pool_only": True,
            "new_cost": 0.0,
            # [LOCAL-609] sum of the reused stops' original research cost
            "research_cost_reused": _sum_research_cost(chosen),
            "new_breakdown": {},
        }

    # ─── N > K : generate only the N-K new stops, excluding pooled titles ─────
    new_n = N - K
    pooled_titles = [r["title"] for r in pooled_rows]
    print(f"  [LOCAL-590] generating {new_n} NEW stop(s) (excluding {K} pooled); "
          f"reusing {K} pooled narration(s)")

    # [LOCAL-612] The orchestrator folds the shortfall into Stop 1 after this nested
    # call (museum opening section, or outdoor opening section below), so suppress
    # the main loop's inline injection to avoid double-emission.
    with _suppress_inline_shortfall():
        gen_text, _out, _coords = generate_fn(
            location, tour_type, None, new_n,
            user_id=user_id, job_id=job_id, exclude_titles=pooled_titles,
        )
    if not gen_text:
        # [LOCAL-600 / D616] For a CONTAINED exhibition museum, "no new stops" means
        # the venue has no more verified on-view material beyond the K already
        # pooled — a genuine shortfall, NOT a reason to abandon the pool and re-run
        # the whole pipeline. Serve the K pooled stops and announce the honest
        # shortfall in Stop 1. (Outdoor/other venues keep the normal fallback.)
        if not contained or K == 0:
            logger.info("[POOL] new-stop generation returned no text; normal fallback")
            return None
        print(f"  [LOCAL-600] N>K: no new on-view stops beyond the {K} pooled — "
              f"serving {K} with the honest shortfall (requested {N})")
        pooled_units = _regroup_pooled_units(
            [_pooled_unit_from_row(r) for r in pooled_rows])
        sources_block = _sources_from_rows(pooled_rows)
        _on_view_shows = sum(1 for u in pooled_units
                             if ':' not in (u.get('title') or ''))
        try:
            from about_museum_stop import build_shortfall_sentence
            _shortfall_sentence = build_shortfall_sentence(
                venue_name=_venue_name(location),
                exhibitions_on_view=_on_view_shows,
                delivered_stops=len(pooled_units), requested_stops=N)
        except Exception:
            _shortfall_sentence = ""
        opening_section = _build_opening_section(
            location, tour_type, request_text=location,
            available_exhibition_stops=len(pooled_units), requested_stops=N,
            shortfall_sentence=_shortfall_sentence)
        if _shortfall_sentence:
            print(f"  [LOCAL-600] D616 shortfall sentence folded into Stop 1 "
                  f"(pool-only shortfall): {_shortfall_sentence!r}")
        result = asm.assemble_building_tour(
            location, tour_type, tour_category, header_cat, display_cat,
            venue_name=_venue_name(location),
            new_stops=[], pooled_stops=pooled_units,
            overall_orientation=None, sources_block=sources_block,
            opening_section=opening_section or "",
            venue_address=_resolve_venue_address(location),
        )
        _emit_result(output_file, result)
        pool.bump_hit_counts(location, tour_type,
                             [u["title"] for u in pooled_units], db_url, qid=qid)
        return {
            "text": result.tour_text,
            "reused_stops": result.reused_stops,
            "new_stops": 0,
            "rewritten_transitions": result.rewritten_transitions,
            "about_stops": result.about_stops,
            "pooled_before": K,
            "served_from_pool_only": True,
            "new_cost": 0.0,
            # [LOCAL-609] every pooled stop is reused here
            "research_cost_reused": _sum_research_cost(pooled_rows),
            "new_breakdown": {},
        }

    # Capture the cost of the new-stop generation BEFORE we touch the pool again.
    try:
        from generate_tour_text import _LAST_GENERATION_COST as _new_cost_rec
        new_cost = float((_new_cost_rec or {}).get("total_cost", 0.0))
    except Exception:
        new_cost = 0.0
    # [LOCAL-609] Also capture the new stops' per-provider breakdown.
    _new_breakdown = _new_breakdown_from_last()

    parsed_new = pool.parse_delivered_stops(gen_text)
    # De-dup: never let a freshly generated stop collide with a pooled title.
    pooled_norm = {pool._title_norm(t) for t in pooled_titles}
    new_units = [_new_unit_from_parsed(s) for s in parsed_new
                 if pool._title_norm(s["title"]) not in pooled_norm]
    pooled_units = [_pooled_unit_from_row(r) for r in pooled_rows]
    if contained:
        # [LOCAL-600 / D616] Keep each pooled show ahead of its own works.
        pooled_units = _regroup_pooled_units(pooled_units)
    sources_block = _merge_sources(gen_text, pooled_rows)

    if contained:
        # [LOCAL-600 / D616] For an exhibition museum, the pool + whatever new
        # on-view stops could be generated may still fall short of N (the venue
        # simply has fewer verified on-view stops than asked). When the TOTAL
        # delivered is below N, announce the honest shortfall in Stop 1's opening
        # section — one sentence from the real counts. Prefer the engine's measured
        # on-view-show count; fall back to counting shows (non-work titles) among
        # the delivered units.
        _delivered_total = len(new_units) + len(pooled_units)
        _shortfall_sentence = ""
        if _delivered_total < N:
            _sf_counts = {}
            try:
                from generate_tour_text import _LAST_SITE_FIRST_COUNTS as _sfc
                _sf_counts = _sfc or {}
            except Exception:
                _sf_counts = {}
            _on_view_shows = _sf_counts.get('exhibitions_on_view')
            if not _on_view_shows:
                # A show's title has no "Artist: Work" separator; a work does.
                _on_view_shows = sum(
                    1 for u in (new_units + pooled_units)
                    if ':' not in (u.get('title') or ''))
            try:
                from about_museum_stop import build_shortfall_sentence
                _shortfall_sentence = build_shortfall_sentence(
                    venue_name=_venue_name(location),
                    exhibitions_on_view=_on_view_shows,
                    delivered_stops=_delivered_total,
                    requested_stops=N)
            except Exception as _sf_e:
                logger.info(f"[LOCAL-600] N>K shortfall sentence skipped ({_sf_e})")
        opening_section = _build_opening_section(
            location, tour_type, request_text=location,
            available_exhibition_stops=len(new_units) + len(pooled_units),
            requested_stops=N, shortfall_sentence=_shortfall_sentence)
        if _shortfall_sentence:
            print(f"  [LOCAL-600] D616 shortfall sentence folded into Stop 1 "
                  f"(N>K path): {_shortfall_sentence!r}")
        result = asm.assemble_building_tour(
            location, tour_type, tour_category, header_cat, display_cat,
            venue_name=_venue_name(location),
            new_stops=new_units, pooled_stops=pooled_units,
            overall_orientation=_overall_from_new(gen_text),
            sources_block=sources_block,
            opening_section=opening_section or "",
            venue_address=_resolve_venue_address(location),
        )
    else:
        _dir_fn = None
        try:
            from directions_generator import generate_walking_directions as _dir_fn
        except Exception:
            _dir_fn = None
        # [LOCAL-612 / D616] Outdoor (walking/biking/driving) pool reuse: when the
        # route (pooled + new) delivers fewer stops than asked, lead Stop 1 with the
        # honest shortfall sentence — the outdoor phrasing, no museum vocabulary.
        _outdoor_delivered = len(new_units) + len(pooled_units)
        _outdoor_shortfall = ""
        if _outdoor_delivered < N:
            try:
                from about_museum_stop import build_shortfall_sentence
                _outdoor_shortfall = build_shortfall_sentence(
                    venue_name=location or "",
                    exhibitions_on_view=0,
                    delivered_stops=_outdoor_delivered,
                    requested_stops=N,
                    mode='outdoor')
            except Exception as _of_e:
                logger.info(f"[LOCAL-612] outdoor N>K shortfall skipped ({_of_e})")
            if _outdoor_shortfall:
                print(f"  [LOCAL-612] D616 shortfall sentence folded into Stop 1 "
                      f"(outdoor N>K path): {_outdoor_shortfall!r}")
        result = asm.assemble_outdoor_tour(
            location, tour_type, tour_category, header_cat, display_cat,
            new_stops=new_units, pooled_stops=pooled_units,
            transport_mode=_transport_mode(tour_type),
            sources_block=sources_block,
            directions_fn=_dir_fn, api_key=api_key,
            shortfall_sentence=_outdoor_shortfall,
        )

    _emit_result(output_file, result)
    # Store the delivered tour back: adds the new stops to the pool (additive).
    pool.store_delivered_tour(location, tour_type, result.tour_text, db_url, qid=qid)
    pool.bump_hit_counts(location, tour_type, [u["title"] for u in pooled_units], db_url, qid=qid)

    return {
        "text": result.tour_text,
        "reused_stops": result.reused_stops,
        "new_stops": result.new_stops,
        "rewritten_transitions": result.rewritten_transitions,
        "about_stops": result.about_stops,
        "pooled_before": K,
        "served_from_pool_only": False,
        "new_cost": new_cost,
        # [LOCAL-609] the K pooled stops are reused alongside the new ones
        "research_cost_reused": _sum_research_cost(pooled_rows),
        "new_breakdown": _new_breakdown,
    }


# ── small helpers ────────────────────────────────────────────────────────────

# [LOCAL-590 step 5] Audio reuse. Audio is NOT part of the English pool — it is a
# rendering of a stop's TEXT in one voice/engine, synthesized downstream at
# delivery/translation time and keyed there on (text, voice_id, engine)
# (polly_tts_service / translation_service.generate_audio). The POOL's job is to
# guarantee the PRECONDITION for reuse: a reused stop's narration is byte-identical
# to the stored one, so a text+voice+engine-keyed renderer returns the SAME audio
# when the voice/engine match, while a new or transition-rewritten stop has
# different text and therefore gets NEW audio. `audio_reuse_identity` makes that
# contract explicit and testable: equal identities ⇒ audio is reusable.
_POLLY_NEURAL_VOICES = frozenset(["Joanna", "Matthew", "Amy", "Brian"])


def _sum_research_cost(rows) -> float:
    """[LOCAL-609] Sum the one-time research cost of the pooled stops being reused.

    Each pooled row carries `research_cost_usd` — the share of the ORIGINAL
    generation cost attributed to that stop when it was first pooled. A pool/cache
    delivery reuses these stops and pays ~nothing to generate them again; this sum
    is what that reuse SAVED, reported on the delivery row as `research_cost_reused`
    so a listener's price can later be shown as "this delivery" + "share of
    research". Robust to rows lacking the key (pre-LOCAL-609 rows -> 0)."""
    total = 0.0
    for r in (rows or []):
        try:
            total += float(r.get("research_cost_usd", 0.0) or 0.0)
        except (TypeError, ValueError, AttributeError):
            pass
    return total


def _new_breakdown_from_last() -> dict:
    """[LOCAL-609] The provider breakdown of the just-finished NEW-stop generation.

    The inner generate_fn call records its own counted 7-key breakdown in
    generate_tour_text._LAST_GENERATION_COST. Reading it here lets a pool delivery
    report WHAT the new stops cost per provider (not just a scalar new_cost).
    Returns {} when unavailable."""
    try:
        from generate_tour_text import _LAST_GENERATION_COST as _nc
        bd = (_nc or {}).get("breakdown")
        return dict(bd) if isinstance(bd, dict) else {}
    except Exception:
        return {}


def audio_reuse_identity(stop_text: str, voice_id: str = "Joanna",
                         engine: Optional[str] = None) -> tuple:
    """The identity a TTS layer keys audio on: (normalized_text, voice_id, engine).

    Two stops with the same identity may share one rendered audio file; a change
    in any component (the narration text, the chosen voice, or the engine) forces
    a fresh render. Engine defaults to the voice's natural engine (neural for the
    LOCAL-323 neural voices, else standard), mirroring the delivery layer.
    """
    eng = engine or ("neural" if voice_id in _POLLY_NEURAL_VOICES else "standard")
    norm_text = re.sub(r"\s+", " ", (stop_text or "").strip())
    return (norm_text, voice_id, eng)


def _venue_name(location: str) -> str:
    # [LOCAL-585] For a themed-in-building request ("Art and Architectual tour in
    # Boston Athenaeum, …") the venue is the BUILDING — strip the theme/tour prefix
    # so museum transitions read "Continue through Boston Athenaeum", not the whole
    # request string. Plain venue strings are unaffected.
    try:
        from about_museum_stop import clean_venue_request_name
        cleaned = clean_venue_request_name(location)
        if cleaned:
            return cleaned
    except Exception:
        pass
    return (location or "").split(",")[0].strip()


def _transport_mode(tour_type: str) -> str:
    t = (tour_type or "").lower()
    if "bik" in t or "cycl" in t:
        return "bike"
    if "driv" in t or "car" in t:
        return "vehicle"
    return "on_foot"


def _write(output_file, text):
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logger.warning(f"[POOL] could not write {output_file}: {e}")


def _emit_result(output_file, result):
    """[LOCAL-607] Write the assembled tour and print the cross-stop dedupe log.

    Michael asked for the dedupe log lines in the live run. The pure assembly
    module records what it dropped on the AssemblyResult; the orchestrator (which
    owns stdout for a generation) prints them here, next to the write."""
    _write(output_file, result.tour_text)
    _dropped = getattr(result, "dedupe_dropped", 0)
    print(f"  [LOCAL-607] cross-stop fact dedupe: {_dropped} sentence(s) removed")
    for ln in getattr(result, "dedupe_log", []) or []:
        print("  " + ln)


def _sources_from_rows(rows: List[Dict]) -> str:
    urls = []
    for r in rows:
        for u in (r.get("sources") or []):
            if u not in urls:
                urls.append(u)
    if not urls:
        return ""
    joined = ", ".join(urls)
    return f"Sources: This tour draws on information from {joined}."


def _merge_sources(new_text: str, pooled_rows: List[Dict]) -> str:
    """Prefer the freshly generated Sources block (it reflects the new stops);
    fall back to the pooled stops' stored sources."""
    block = _extract_sources_block(new_text)
    if block:
        return block
    return _sources_from_rows(pooled_rows)


def _overall_from_new(new_text: str) -> Optional[str]:
    """Recover the overall/orientation description from the freshly generated
    sub-tour's FIRST stop so the merged building tour's opening reflects the new
    (leading) stops. Returns the Stop-1 Orientation body, or None.

    [LOCAL-641] Scoped to the Stop-1 block ONLY. The previous implementation did a
    global ``re.search`` for the first ``Orientation:`` label anywhere in the text.
    When Stop 1's own orientation was folded into opening prose and carried no
    ``Orientation:`` label of its own, that search returned the FIRST LATER stop's
    orientation (Stop 2's) and injected it as Stop 1's overall seed — so a fresh
    tour opened Stop 1 with Stop 2's orientation (Courtauld R10: Stop 1 Van Gogh
    carried Seurat's "tapestry of discrete points / pointillist" orientation; the
    LOCAL-630 rename then masked it; Stop 2 lost its orientation to cross-stop
    dedupe). The reuse path passes ``overall_orientation=None`` and never did this,
    which is why the SAME stops reused scored 8–8.5 and fresh scored 4.

    Now the search is confined to the text BEFORE the second ``Stop N:`` header, so
    only Stop 1's own ``Orientation:`` can ever be returned. If Stop 1 has no such
    label, this returns None — nothing is pulled forward from a later stop — and
    the fresh delivery matches the reuse delivery (each stop keeps its own
    orientation; no later orientation is ever hoisted onto Stop 1).
    """
    text = new_text or ""
    headers = list(re.finditer(r'^Stop (\d+):\s*.+?\s*$', text, re.M))
    # Confine the search to the Stop-1 block: from the Stop-1 header to the Stop-2
    # header (or to end-of-text when there is only one stop). Falling back to the
    # whole text only when NO stop header exists at all keeps older callers working
    # while guaranteeing a later stop's Orientation is never returned.
    if headers:
        stop1_start = headers[0].end()
        stop1_end = headers[1].start() if len(headers) > 1 else len(text)
        search_region = text[stop1_start:stop1_end]
    else:
        search_region = text
    m = re.search(r'^Orientation:\s*(.+?)(?:\n\n|\Z)', search_region, re.M | re.S)
    if m:
        return m.group(1).strip()
    return None


def _discover_site_url_fallback(venue_string: str, locality: str = "") -> str:
    """[LOCAL-599B] Find a venue's official site when it has NO Wikidata entity.

    Reuses venue_resolver.discover_official_site (the LOCAL-599 Wikidata-independent
    web-search + parent-org discovery) so the opening section and the venue-address
    resolution can reach a no-Wikidata museum's own /visit and /about pages
    (MassArt → maam.massart.edu). Deterministic, honest: returns the discovered URL
    or "" (never a guess). Best-effort: any import/network failure returns "".
    """
    if os.environ.get("DISABLE_ABOUT_STOP", "").strip() == "1":
        return ""
    try:
        from venue_resolver import discover_official_site
    except Exception:
        return ""
    city = ""
    if locality:
        city = locality.split(",")[0].strip()
    elif "," in (venue_string or ""):
        city = venue_string.split(",")[1].strip()
    try:
        disc = discover_official_site(venue_string or "", city)
    except Exception as e:
        logger.info(f"[LOCAL-599B] official-site discovery for opening section "
                    f"failed ({e})")
        return ""
    if disc is not None and getattr(disc, "found", False):
        print(f"  [LOCAL-599B] opening-section site discovered (route="
              f"{getattr(disc, 'source', '?')}): {disc.official_url}")
        return disc.official_url or ""
    return ""


def _resolve_venue_address(location: str) -> str:
    """[LOCAL-592 r2] Resolve the venue's sourced street address for a contained
    tour, or "". Mirrors _build_opening_section's venue resolution (same site URL
    + locality), then lifts the main-gallery address from the venue's own pages.
    Best-effort and non-fatal: any failure returns "" (the stop keeps its address;
    nothing is invented).
    """
    if os.environ.get("DISABLE_ABOUT_STOP", "").strip() == "1":
        return ""
    try:
        from about_museum_stop import clean_venue_request_name
    except Exception:
        return ""
    clean_name = clean_venue_request_name(location)
    venue = clean_name or _venue_name(location)
    site_url = ""
    address = ""
    try:
        from venue_resolver import resolve_venue
        ent = resolve_venue(clean_name or location)
        if ent is not None:
            site_url = getattr(ent, "official_url", "") or ""
            venue = getattr(ent, "name", "") or venue
            address = getattr(ent, "address", "") or ""
    except Exception as e:
        logger.info(f"[LOCAL-592] venue resolve for address failed ({e})")
    locality = ""
    parts = [p.strip() for p in (location or "").split(",")[1:] if p.strip()]
    if parts:
        locality = ", ".join(parts[:2])
    # [LOCAL-599B] No-Wikidata venue → discover the official site so the venue's
    # own address can be lifted from its /visit page (parity with the opening
    # section). Best-effort; "" when nothing is discovered.
    if not site_url:
        site_url = _discover_site_url_fallback(clean_name or location, locality) or site_url
    sourced = _source_venue_address(venue, site_url, locality)
    # Prefer the page-sourced address; fall back to the entity address if present.
    return sourced or (address or "").strip()


def _regroup_pooled_units(units):
    """[LOCAL-600 / D616] Re-group pooled stop units so each exhibition stop leads
    its own works (works have an "Artist: Work" title; the show is the bare
    "Artist"). The LOCAL-599 r3 run pooled the stops works-first, so a pool read in
    stored order can still put a work before its show. This restores the grouping:

      * a unit whose title contains ": " is a WORK; the text before the first ": "
        is its show key (the artist / show title);
      * a unit with no ": " is a SHOW; its key is its whole title;
      * each show leads, immediately followed by its own works in pool order; shows
        appear in first-seen pool order; a work whose show is absent keeps position.

    Pure; returns a NEW list; order-stable. A list with no works, or already
    grouped, comes back unchanged (same contents, possibly re-ordered).
    """
    if not units:
        return units

    def _key(u):
        t = (u.get('title') or '').strip()
        if ': ' in t:
            return ('work', t.split(': ', 1)[0].strip().lower())
        return ('show', t.strip().lower())

    show_order = []          # show-key in first-seen order
    groups = {}              # show-key -> {'show': unit|None, 'works': [unit], 'order': int}
    for i, u in enumerate(units):
        kind, key = _key(u)
        if key not in groups:
            groups[key] = {'show': None, 'works': [], 'order': i}
            show_order.append(key)
        if kind == 'show' and groups[key]['show'] is None:
            groups[key]['show'] = u
        else:
            groups[key]['works'].append(u)

    out = []
    orphans = []
    for key in sorted(show_order, key=lambda k: groups[k]['order']):
        g = groups[key]
        if g['show'] is not None:
            out.append(g['show'])
            out.extend(g['works'])
        else:
            orphans.extend(g['works'])  # works whose show is absent — keep later
    out.extend(sorted(orphans, key=lambda u: units.index(u)))
    if len(out) != len(units):
        return units
    return out


def _site_first_shortfall_sentence(location, delivered_count, requested_n):
    """[LOCAL-600 / D616] The honest shortfall sentence for a site-first (exhibition
    museum) delivery, or "" when there is no shortfall / the path was not site-first.

    Reads the real counts the engine recorded for the LAST generation
    (generate_tour_text._LAST_SITE_FIRST_COUNTS). The sentence is emitted ONLY when
    the engine measured a site-first delivery (exhibitions_on_view present) AND the
    delivered count is below the request — the D611 exact-N exception. Pure w.r.t.
    the module state it reads; never raises.
    """
    try:
        from generate_tour_text import _LAST_SITE_FIRST_COUNTS as _sfc
    except Exception:
        return ""
    if not _sfc:
        return ""
    try:
        from about_museum_stop import build_shortfall_sentence
    except Exception:
        return ""
    try:
        return build_shortfall_sentence(
            venue_name=_venue_name(location),
            exhibitions_on_view=_sfc.get('exhibitions_on_view', 0),
            delivered_stops=_sfc.get('delivered_stops', delivered_count),
            requested_stops=_sfc.get('requested_stops', requested_n))
    except Exception:
        return ""


# [LOCAL-615 item 2] "Never say 'check… on <domain>' when the preflight has hours."
# [LOCAL-618 #4] Also recognise the honest "weren't published" line, so that if
# the preflight DID return hours they still override the fallback on the delivered
# text (when the About-stop facts were empty but the preflight was not).
_CHECK_HOURS_FALLBACK_RE = re.compile(
    r'(?i)(?:Check opening hours and admission on\b[^\n]*?before you go\.?'
    r'|Opening hours\s+(?:weren.?t|were not)\s+published[^\n.]*\.?)')


def _fold_preflight_hours_into_text(tour_text: str) -> str:
    """Belt-and-braces: replace a surviving "Check opening hours and admission on
    <domain> before you go." fallback with the LOCAL-603 preflight's real hours.

    The opening-section rebuild (above) is the primary fix — it composes the real
    hours into Stop 1 before assembly. This is the final guard that enforces
    Michael's rule literally on the delivered text: if the fallback sentence is
    STILL present AND the preflight has hours/admission, swap the fallback for the
    preflight's spoken sentence. Idempotent and non-fatal: when the preflight has
    no hours, or the fallback is absent, the text is returned unchanged (an honest
    pointer with no sourced hours is correct — never invent).
    """
    if not tour_text or not _CHECK_HOURS_FALLBACK_RE.search(tour_text):
        return tour_text
    try:
        import generate_tour_text as _gtt
        import venue_preflight as _vpf
        _pf = getattr(_gtt, "_LAST_VENUE_PREFLIGHT", None) or {}
        if not _pf or _pf.get("skipped") or _pf.get("error"):
            return tour_text
        _planb = _vpf.plan_b_opening_practicals(_pf)
        _speak = (_planb or {}).get("speak", "").strip()
        if not _speak:
            return tour_text
        _new_text, _n = _CHECK_HOURS_FALLBACK_RE.subn(_speak, tour_text)
        if _n:
            print(f"  [LOCAL-615] replaced {_n} 'check hours on <domain>' fallback(s) "
                  f"with preflight hours: {_speak!r}")
        return _new_text
    except Exception as _e:
        logger.info(f"[LOCAL-615] preflight-hours text fold skipped ({_e})")
        return tour_text


def _build_opening_section(location: str, tour_type: str, request_text: str,
                           available_exhibition_stops: int,
                           requested_stops: Optional[int],
                           shortfall_sentence: str = "") -> Optional[str]:
    """[LOCAL-592] Build the OPENING SECTION of Stop 1 for a contained venue: the
    museum's own story (founder/history/architecture) + the practical facts
    (opening hours, admission, closed days). Returns the section text, or None when
    no story can be sourced (then the tour is unchanged — D577).

    This supersedes the LOCAL-585 standalone "About <museum>" stop: the content is
    now the first SECTION of Stop 1 (mirroring the walking-tour prolog), so a
    request for N stops delivers EXACTLY N. The About narration is sourced from the
    venue's own About/history/mission pages; the practical facts are sourced from
    the venue's visit/hours/admission page and passed through the LOCAL-584 gate
    (venue-bound, dated, state-only-what-the-page-supports). Best-effort and
    non-fatal: any resolution/build failure returns None — never breaks a tour.
    """
    if os.environ.get("DISABLE_ABOUT_STOP", "").strip() == "1":
        return None
    try:
        from about_museum_stop import (build_about_stop, build_opening_section,
                                        clean_venue_request_name, default_wiki_provider)
    except Exception as e:
        logger.info(f"[LOCAL-592] about_museum_stop unavailable ({e}); no opening section")
        return None

    # Key the opening section on the BUILDING, not the theme words ("Art and
    # Architectual tour in Boston Athenaeum" → "Boston Athenaeum").
    clean_name = clean_venue_request_name(location)
    venue = clean_name or _venue_name(location)
    site_url = ""
    locality = ""
    address = ""
    try:
        from venue_resolver import resolve_venue
        ent = resolve_venue(clean_name or location)
        if ent is not None:
            site_url = getattr(ent, "official_url", "") or ""
            # [LOCAL-585 r2] VenueEntity exposes the resolved Wikidata display name
            # as `.name` (properly cased). Prefer it so the narration says the
            # venue's real name, not the request's casing. (`.venue_name`/`.address`
            # do not exist on the entity — the old getattrs always fell through.)
            venue = getattr(ent, "name", "") or getattr(ent, "venue_name", "") or venue
            address = getattr(ent, "address", "") or address
    except Exception as e:
        logger.info(f"[LOCAL-592] venue resolve for opening section failed ({e}); "
                    f"continuing without a site URL")
    # Derive a locality tail from the request ("..., City, ST"). The composer
    # properly-cases and state-expands it (normalise_locality), so a raw
    # "boston, ma" request tail is spoken as "Boston, Massachusetts".
    parts = [p.strip() for p in (location or "").split(",")[1:] if p.strip()]
    if parts:
        locality = ", ".join(parts[:2])

    # [LOCAL-599B] When the venue has NO Wikidata entity (MassArt), resolve_venue
    # returns None and site_url is empty — so the D611 opening section could not be
    # sourced from /visit and /about and Stop 1 shipped with no About/hours/
    # admission. Reuse the LOCAL-599 Wikidata-independent official-site discovery
    # here so the opening section reaches the venue's own pages exactly as the
    # exhibition path does. Best-effort: any failure leaves site_url as-is.
    if not site_url:
        site_url = _discover_site_url_fallback(clean_name or location,
                                               locality) or site_url

    # [LOCAL-592] Source the practical facts (hours/admission/closed days) from the
    # venue's own visit page and gate them (LOCAL-584). Fully best-effort: a failure
    # yields "" so the opening section carries only the About story (silence is
    # correct — never invent hours/prices).
    practical_facts = _source_practical_facts(venue, site_url, address)

    # [LOCAL-626 item 2] The live-site extraction can return a DEGENERATE practical
    # string — a single weekday with no range ("Monday, 10:00–18:00", the tour-485
    # defect, where the venue is actually open Monday–Sunday), or a bare "free"
    # that contradicts a real adult price. The LOCAL-603 preflight is the
    # authoritative, grounded source for hours/admission. Prefer it whenever (a) we
    # have NO live practicals, or (b) the live hours name only ONE weekday while the
    # preflight states a full day RANGE, or (c) the live admission reads "free"
    # while the preflight carries a concrete price. This fixes "why only one day was
    # kept" without inventing anything — the preflight text is used verbatim.
    def _hours_is_single_day(txt: str) -> bool:
        days = re.findall(
            r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            txt or "")
        has_range = bool(re.search(
            r"(?i)\b(?:to|through|–|-|daily|every day)\b.*?"
            r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|daily)",
            txt or "")) or "daily" in (txt or "").lower()
        return len(set(d.lower() for d in days)) == 1 and not has_range

    def _looks_bare_free(txt: str) -> bool:
        t = (txt or "").lower()
        return "free" in t and not re.search(r"[$€£¥]\s?\d", t)

    _pf_authoritative = False
    _live = (practical_facts or "").strip()
    try:
        import generate_tour_text as _gtt
        import venue_preflight as _vpf
        _pf = getattr(_gtt, "_LAST_VENUE_PREFLIGHT", None) or {}
        if _pf and not _pf.get("skipped") and not _pf.get("error"):
            _planb = _vpf.plan_b_opening_practicals(_pf)
            _h = (_planb or {}).get("hours", "").strip()
            _a = (_planb or {}).get("admission", "").strip()
            _pf_has_range = bool(_h) and (
                bool(re.search(r"(?i)\b(?:to|through|daily|every day)\b", _h))
                or "daily" in _h.lower())
            _pf_has_price = bool(re.search(r"[$€£¥]\s?\d", _a))
            # (a) nothing live, or (b) degenerate single-day live hours vs a ranged
            # preflight, or (c) bare-free live admission vs a priced preflight.
            if (not _live
                    or (_h and _pf_has_range and _hours_is_single_day(_live))
                    or (_a and _pf_has_price and _looks_bare_free(_live))):
                _bits = []
                if _h:
                    _bits.append(_h)
                if _a:
                    _bits.append(_a)
                if _bits:
                    practical_facts = ". ".join(_bits)
                    _pf_authoritative = True
                    print(f"  [LOCAL-626] Stop-1 hours/admission from LOCAL-603 "
                          f"preflight (authoritative): {practical_facts!r}")
    except Exception as _pf_e:
        logger.info(f"[LOCAL-626] preflight practicals fold skipped ({_pf_e})")

    try:
        about = build_about_stop(
            venue_name=venue,
            base_site_url=site_url,
            request_text=request_text or location or "",
            locality=locality,
            address=address,
            requested_stops=requested_stops,
            available_exhibition_stops=available_exhibition_stops,
            wiki_provider=default_wiki_provider,
            practical_facts=practical_facts,
        )
    except Exception as e:
        logger.info(f"[LOCAL-592] opening-section build failed ({e}); no opening section")
        return None
    if about is None or about.is_empty():
        return None
    section = build_opening_section(about, shortfall_sentence=shortfall_sentence)
    if not section or not section.strip():
        return None
    print(f"  [LOCAL-592] Opening section folded into Stop 1 for {venue!r}: "
          f"architecture={about.covers_architecture} "
          f"practical_facts={'yes' if practical_facts else 'none'} "
          f"sources={len(about.sources)}")
    return section


def _has_price_token(text: str) -> bool:
    """True when an admission segment carries a concrete price (so a priced
    admission is preferred over a bare 'Free'/condition when merging)."""
    return bool(re.search(r"[$€£]\s?\d|\b\d+\s?(?:usd|eur|gbp|dollars?|euros?)\b",
                          (text or ""), re.IGNORECASE))


# [LOCAL-592 r3] Anchor/href keywords that mark a venue's visiting-facts page. The
# venue states its hours/admission on whatever slug it chose (the live Griffin uses
# /about-the-griffin-2026/, not /about or /visit), so we follow the venue's OWN nav
# links by meaning rather than guessing fixed slugs.
_VISIT_LINK_RE = re.compile(
    r"(?i)(plan\s*your\s*visit|visit\s*us|\bvisit\b|hours|opening|admission|"
    r"tickets?|getting\s*here|about)"
)


def _discover_visiting_urls(site_url: str, fetch, max_links: int = 8) -> list:
    """[LOCAL-592 r3] Return same-domain URLs from the home page's own navigation
    that name Visit / Plan Your Visit / Hours / Admission / Tickets / About.

    Fetches the home page once and scans its anchors (``<a href=… >text</a>``):
    a link is kept when its href OR its anchor text matches a visiting keyword and
    it stays on the venue's domain. This reaches the venue's real visiting-facts
    page whatever its slug, without leaving the venue's own site. Pure/best-effort:
    returns [] on any failure. ``fetch`` is the same injectable (html, links) fetcher
    used elsewhere; links from the fetcher are honoured too when present.
    """
    from urllib.parse import urlparse, urljoin
    if "://" not in site_url:
        site_url = "https://" + site_url
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.lower()
    domain = domain[4:] if domain.startswith("www.") else domain

    try:
        html, links = fetch(root)
    except Exception:
        html, links = "", []
    if not html:
        return []

    # Anchors from the HTML (href + visible text), plus any links the fetcher gave.
    pairs = []  # (href, text)
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         html, re.IGNORECASE | re.DOTALL):
        href = m.group(1)
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        pairs.append((href, text))
    for lk in (links or []):
        if isinstance(lk, (list, tuple)) and len(lk) >= 1:
            pairs.append((lk[0], lk[1] if len(lk) > 1 else ""))

    out = []
    seen = set()
    for href, text in pairs:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if not (_VISIT_LINK_RE.search(href) or _VISIT_LINK_RE.search(text or "")):
            continue
        absu = urljoin(root + "/", href)
        pu = urlparse(absu)
        ud = pu.netloc.lower()
        ud = ud[4:] if ud.startswith("www.") else ud
        if ud and ud != domain:
            continue  # stay on the venue's own site
        norm = absu.split("#")[0].rstrip("/")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(absu)
        if len(out) >= max_links:
            break
    return out


# [LOCAL-599B] Compact clock format normaliser. Some venues render times as
# "12 – 8p" / "12 – 5p" (a bare 'p'/'a' suffix, en-dash, nbsp) — MAAM's /visit
# uses exactly this, one weekday per record-separated line
# ("Thursday 12 – 8p\x1eFriday 12 – 5p"). The LOCAL-592 visitor_facts_extractor
# keys on "am"/"pm" with BOTH range sides marked and the day on the SAME line, so
# the compact form yielded NO hours and Stop 1 lost its day-bound hours. This
# pure, deterministic normaliser rewrites ONLY tokens the page already states into
# the spelling the extractor recognises — it never invents a time:
#   * decode &nbsp;/&#160; and the nbsp/word-joiner code points to spaces;
#   * expand an unambiguous trailing 'p'/'a' on a clock number ("8p" → "8 pm");
#   * when a range's SECOND side has a meridiem but the FIRST is a bare clock
#     ("12 – 5 pm"), copy the meridiem onto the first side ("12 pm – 5 pm") so the
#     extractor's "both sides marked" rule is satisfied with the page's own value;
#   * turn the record-separator (\x1e) between day lines into ", " so each
#     "Day time–time" line is one parseable schedule entry.
_COMPACT_TIME_RE = re.compile(r'(?<!\d)(\d{1,2}(?::\d{2})?)\s*([ap])\b(?!m)',
                              re.IGNORECASE)
_BARE_START_RANGE_RE = re.compile(
    r'(?<!\d)(\d{1,2}(?::\d{2})?)\s*([-–—])\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)\b',
    re.IGNORECASE)


def _normalize_compact_times(text: str) -> str:
    if not text:
        return text
    import html as _html
    t = _html.unescape(text)                       # &nbsp; → \u00a0
    t = t.replace('\u00a0', ' ').replace('\u2060', ' ')  # nbsp / word-joiner
    t = t.replace('\x1e', ', ')                    # day-line record separator

    def _expand(m):
        clock, suffix = m.group(1), m.group(2).lower()
        return f"{clock} {'pm' if suffix == 'p' else 'am'}"

    t = _COMPACT_TIME_RE.sub(_expand, t)

    def _carry(m):
        start, dash, end, mer = m.group(1), m.group(2), m.group(3), m.group(4).lower()
        return f"{start} {mer} {dash} {end} {mer}"

    t = _BARE_START_RANGE_RE.sub(_carry, t)
    return t


# Weekday order for subsumption checks (the grouped "X through Y" segment).
_WEEKDAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                  'saturday', 'sunday']


def _expand_day_range(day_phrase: str) -> set:
    """Expand 'Friday through Sunday' / 'Mon-Wed' → {friday,saturday,sunday}."""
    dl = (day_phrase or '').lower()
    found = [d for d in _WEEKDAY_ORDER if d in dl]
    if not found:
        return set()
    if re.search(r'through|thru|to|[-–—]', dl) and len(found) >= 2:
        i, j = _WEEKDAY_ORDER.index(found[0]), _WEEKDAY_ORDER.index(found[-1])
        if i <= j:
            return set(_WEEKDAY_ORDER[i:j + 1])
    return set(found)


def _dedupe_hours_segments(segs: List[str]) -> List[str]:
    """[LOCAL-599B] Drop a grouped day-range hours segment ('Friday through Sunday,
    12 PM–5 PM') when every day it covers is ALREADY stated by individual-day
    segments with the SAME time. The LOCAL-592 extractor emits both the per-day
    rows and a grouped range; stating both reads as a stutter. Pure; preserves
    order and keeps the first representation seen for each (day,time)."""
    kept: List[str] = []
    covered = {}  # time_str -> set(days) already individually stated
    time_re = re.compile(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*[-–—]\s*'
                         r'\d{1,2}(?::\d{2})?\s*(?:AM|PM))', re.IGNORECASE)
    for seg in segs:
        tm = time_re.search(seg)
        time_key = re.sub(r'\s+', '', tm.group(1).upper()) if tm else seg
        days = _expand_day_range(seg)
        is_group = bool(re.search(r'through|thru|[-–—]|\bto\b', seg.lower())
                        and len(days) >= 2)
        if is_group and days and days.issubset(covered.get(time_key, set())):
            continue  # fully subsumed by already-stated individual days
        kept.append(seg)
        covered.setdefault(time_key, set()).update(days)
    return kept


def _source_practical_facts(venue: str, site_url: str, address: str = "",
                            fetcher=None) -> str:
    """[LOCAL-592 r3] Fetch + extract + GATE + MERGE the venue's practical facts, or "".

    Reuses the exact LOCAL-584 honesty contract per page: visitor_facts_extractor
    reads only the venue's own section (venue-bound hours), and
    practical_facts_gate.gate_formatted_facts drops anything not literally supported
    by that page (currency, days, amounts).

    r3 change — STATE WHAT IS KNOWN, merged across the venue's pages:
    the Griffin's /visit and /plan-your-visit state the HOURS but no price, while
    its About page ("about-the-griffin-2026") states BOTH the hours and the
    admission. r1/r2 took the FIRST gate-passing page and stopped, so the price was
    never reached and a hours-only result was discarded as "too short". r3 instead
    walks ALL the venue's own pages (About / history / plan-your-visit / visit /
    tickets / admission / home-page footer — the same `_STORY_SEEDS` the About
    section reads), gate-verifies each page's facts against THAT page, and MERGES
    the survivors by claim type: closed days, hours, and admission are filled from
    whichever page states them, preferring an admission segment that carries a
    concrete price. The "too short — omitting" rule is gone for the Stop-1 visiting
    section: hours without a price (or a price without hours) is still stated.

    Fully best-effort and non-fatal: no site URL, a fetch failure, or no
    gate-passing fact on any page all return "" (then the opening section carries
    only the About story + the website pointer — never invented).
    """
    if not site_url:
        return ""
    try:
        from about_museum_stop import _candidate_story_urls, _visible_text, _default_fetcher
        from visitor_facts_extractor import (_html_to_sectioned_text,
                                              extract_visitor_facts_from_text)
        from practical_facts_gate import gate_formatted_facts, _facts_segment_claim
    except Exception as e:
        logger.info(f"[LOCAL-592] practical-facts modules unavailable ({e})")
        return ""

    fetch = fetcher or _default_fetcher

    try:
        urls = _candidate_story_urls(site_url)
    except Exception:
        urls = [site_url]

    # [r3] The real visiting-facts page is often a venue-specific slug the fixed
    # `_STORY_SEEDS` miss — the live Griffin states its hours AND admission on
    # /about-the-griffin-2026/, which /about, /visit and /plan-your-visit (all
    # 200s) do NOT. Discover it from the home page's OWN navigation: follow the
    # same-domain links whose href or anchor text names Visit / Plan Your Visit /
    # Hours / Admission / Tickets / About. This keeps us on the venue's own pages
    # (no guessing, no other sites) and reaches whatever slug the venue actually
    # uses. Best-effort: any failure leaves `urls` as the seed list.
    try:
        discovered = _discover_visiting_urls(site_url, fetch)
        if discovered:
            urls = discovered + urls
    except Exception as e:
        logger.info(f"[LOCAL-592] visiting-link discovery failed ({e})")

    # Read the venue's own visit/hours/admission AND About/history pages — the
    # price frequently lives on the About page, the hours on /visit.
    def _visit_rank(u: str) -> int:
        ul = u.lower()
        for i, kw in enumerate(("about-the", "plan-your-visit", "/visit", "admission",
                                "tickets", "hours", "/about", "history", "mission")):
            if kw in ul:
                return i
        return 99
    urls = sorted(dict.fromkeys(urls), key=_visit_rank)[:10]

    # Merge the GATED survivors across pages, keyed by claim type. Order matters:
    # closed day, then hours, then admission — the natural reading order and the
    # order the LOCAL-584 suite asserts.
    merged = {"closed_day": "", "hours": "", "admission": ""}

    for u in urls:
        try:
            html, _ = fetch(u)
        except Exception:
            html = ""
        if not html or len(html) < 80:
            continue
        try:
            sectioned = _html_to_sectioned_text(html)
            sectioned = _normalize_compact_times(sectioned)
            facts = extract_visitor_facts_from_text(
                sectioned, 'en', venue_name=venue, venue_address=address)
            formatted = facts.format_en() if facts and not facts.is_empty() else ""
            if not formatted:
                continue
            # [LOCAL-599B] The gate re-checks each formatted fact against the page's
            # literal text. Normalise that text the SAME way the extractor's input
            # was normalised (compact "12 – 8p" → "12 pm – 8 pm"), so a day/time the
            # page genuinely states is not dropped merely because its on-page
            # spelling was compact. This never adds a fact the page lacks — it only
            # aligns the spelling the gate compares against.
            plain = _normalize_compact_times(_visible_text(html)).lower()
            gated, _dropped = gate_formatted_facts(formatted, plain, source_url=u)
            if not gated or not gated.strip():
                continue
            # Classify each surviving segment and fold it into the merge. A segment
            # fills its claim-type slot the first time; a priced admission upgrades
            # an earlier price-less admission. [LOCAL-599B] HOURS accumulate every
            # distinct day-schedule segment from the SAME page (Thu 12–8; Fri–Sun
            # 12–5) so the full weekly schedule is stated, not just the first day.
            _page_hours: List[str] = []
            for seg in re.split(r"\.\s+|;\s+", gated):
                seg = seg.strip().rstrip(".")
                if not seg:
                    continue
                claim = _facts_segment_claim(seg)
                ctype = getattr(claim, "claim_type", None) if claim else None
                if ctype == "closed_day":
                    if not merged["closed_day"]:
                        merged["closed_day"] = seg
                elif ctype == "hours":
                    if seg not in _page_hours:
                        _page_hours.append(seg)
                elif ctype in ("admission", "price_band"):
                    if not merged["admission"] or (
                            not _has_price_token(merged["admission"])
                            and _has_price_token(seg)):
                        merged["admission"] = seg
            # Keep the richest (most day-schedule segments) hours statement seen.
            if _page_hours:
                _page_hours = _dedupe_hours_segments(_page_hours)
                candidate = "; ".join(_page_hours)
                if candidate.count(";") > merged["hours"].count(";") or not merged["hours"]:
                    merged["hours"] = candidate
        except Exception as e:
            logger.info(f"[LOCAL-592] practical-facts extract/gate error on {u} ({e})")
            continue
        # Stop once we have both the hours and a priced admission — the fullest
        # statement. Otherwise keep reading more pages to fill the gaps.
        if merged["hours"] and merged["admission"] and _has_price_token(merged["admission"]):
            break

    parts = [merged["closed_day"], merged["hours"], merged["admission"]]
    return ". ".join(p for p in parts if p).strip()


def _source_venue_address(venue: str, site_url: str, locality: str = "") -> str:
    """[LOCAL-592 r2] Fetch the venue's own page and lift its street address, or "".

    The sourced venue address is used to bind every contained-venue stop's address
    to the BUILDING (D611), replacing per-stop LLM/geocode guesses that drift to a
    town-centre address no source supports (the Griffin "1 Washington St" defect).
    Best-effort and non-fatal: no site URL, a fetch failure, or no address on the
    page all return "" — then the stop keeps whatever address it had (never
    invented here). Only the venue's OWN pages are read, so a satellite gallery
    address elsewhere on the site is not mistaken for the main address: the
    extractor returns the FIRST street address, and the venue's main-gallery
    address leads its About/visit footer.
    """
    if not site_url:
        return ""
    try:
        from about_museum_stop import (_candidate_story_urls, _visible_text,
                                        _default_fetcher, extract_venue_address)
    except Exception as e:
        logger.info(f"[LOCAL-592] venue-address modules unavailable ({e})")
        return ""
    try:
        urls = _candidate_story_urls(site_url)
    except Exception:
        urls = [site_url]
    # Prefer visit/contact/about pages where the main address is stated.
    def _addr_rank(u: str) -> int:
        ul = u.lower()
        for i, kw in enumerate(("plan-your-visit", "/visit", "contact", "about")):
            if kw in ul:
                return i
        return 99
    urls = sorted(dict.fromkeys(urls), key=_addr_rank)[:6]
    fetch = _default_fetcher
    for u in urls:
        try:
            html, _ = fetch(u)
        except Exception:
            html = ""
        if not html or len(html) < 80:
            continue
        try:
            addr = extract_venue_address(_visible_text(html), locality=locality)
            if addr:
                return addr
        except Exception as e:
            logger.info(f"[LOCAL-592] venue-address extract error on {u} ({e})")
            continue
    return ""

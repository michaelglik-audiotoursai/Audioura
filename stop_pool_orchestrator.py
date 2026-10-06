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
import logging
import os
import re
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)


def _is_contained(tour_category: str) -> bool:
    """Single-building (contained) venue: museum or facility."""
    return (tour_category or "").strip().lower() in ("museum", "facility")


def _classify(location: str, tour_type: str) -> str:
    """Classify via the generator's own classifier; fall back to tour_type."""
    try:
        from generate_tour_text import _classify_tour_category
        return _classify_tour_category(location, tour_type)
    except Exception as e:
        logger.info(f"[POOL] classifier unavailable ({e}); using tour_type as category")
        return (tour_type or "").strip().lower()


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

    # Nothing to reuse and a full request → let the normal path run (and store).
    if K == 0:
        return None

    # ─── N <= K : serve the best N from the pool, no new generation ───────────
    if N <= K:
        chosen = pooled_rows[:N]
        pooled_units = [_pooled_unit_from_row(r) for r in chosen]
        sources_block = _sources_from_rows(chosen)
        if contained:
            result = asm.assemble_building_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                venue_name=_venue_name(location),
                new_stops=[], pooled_stops=pooled_units,
                overall_orientation=None, sources_block=sources_block,
            )
        else:
            result = asm.assemble_outdoor_tour(
                location, tour_type, tour_category, header_cat, display_cat,
                new_stops=[], pooled_stops=pooled_units,
                transport_mode=_transport_mode(tour_type),
                sources_block=sources_block,
            )
        _write(output_file, result.tour_text)
        pool.bump_hit_counts(location, tour_type, [u["title"] for u in pooled_units], db_url, qid=qid)
        return {
            "text": result.tour_text,
            "reused_stops": result.reused_stops,
            "new_stops": 0,
            "rewritten_transitions": result.rewritten_transitions,
            "pooled_before": K,
            "served_from_pool_only": True,
            "new_cost": 0.0,
        }

    # ─── N > K : generate only the N-K new stops, excluding pooled titles ─────
    new_n = N - K
    pooled_titles = [r["title"] for r in pooled_rows]
    print(f"  [LOCAL-590] generating {new_n} NEW stop(s) (excluding {K} pooled); "
          f"reusing {K} pooled narration(s)")

    gen_text, _out, _coords = generate_fn(
        location, tour_type, None, new_n,
        user_id=user_id, job_id=job_id, exclude_titles=pooled_titles,
    )
    if not gen_text:
        logger.info("[POOL] new-stop generation returned no text; normal fallback")
        return None

    # Capture the cost of the new-stop generation BEFORE we touch the pool again.
    try:
        from generate_tour_text import _LAST_GENERATION_COST as _new_cost_rec
        new_cost = float((_new_cost_rec or {}).get("total_cost", 0.0))
    except Exception:
        new_cost = 0.0

    parsed_new = pool.parse_delivered_stops(gen_text)
    # De-dup: never let a freshly generated stop collide with a pooled title.
    pooled_norm = {pool._title_norm(t) for t in pooled_titles}
    new_units = [_new_unit_from_parsed(s) for s in parsed_new
                 if pool._title_norm(s["title"]) not in pooled_norm]
    pooled_units = [_pooled_unit_from_row(r) for r in pooled_rows]
    sources_block = _merge_sources(gen_text, pooled_rows)

    if contained:
        result = asm.assemble_building_tour(
            location, tour_type, tour_category, header_cat, display_cat,
            venue_name=_venue_name(location),
            new_stops=new_units, pooled_stops=pooled_units,
            overall_orientation=_overall_from_new(gen_text),
            sources_block=sources_block,
        )
    else:
        _dir_fn = None
        try:
            from directions_generator import generate_walking_directions as _dir_fn
        except Exception:
            _dir_fn = None
        result = asm.assemble_outdoor_tour(
            location, tour_type, tour_category, header_cat, display_cat,
            new_stops=new_units, pooled_stops=pooled_units,
            transport_mode=_transport_mode(tour_type),
            sources_block=sources_block,
            directions_fn=_dir_fn, api_key=api_key,
        )

    _write(output_file, result.tour_text)
    # Store the delivered tour back: adds the new stops to the pool (additive).
    pool.store_delivered_tour(location, tour_type, result.tour_text, db_url, qid=qid)
    pool.bump_hit_counts(location, tour_type, [u["title"] for u in pooled_units], db_url, qid=qid)

    return {
        "text": result.tour_text,
        "reused_stops": result.reused_stops,
        "new_stops": result.new_stops,
        "rewritten_transitions": result.rewritten_transitions,
        "pooled_before": K,
        "served_from_pool_only": False,
        "new_cost": new_cost,
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
    sub-tour's first stop so the merged building tour's opening reflects the new
    (leading) stops. Returns the Stop-1 Orientation body, or None."""
    m = re.search(r'^Orientation:\s*(.+?)(?:\n\n|\Z)', new_text or "", re.M | re.S)
    if m:
        return m.group(1).strip()
    return None

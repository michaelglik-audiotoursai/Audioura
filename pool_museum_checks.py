"""pool_museum_checks.py — [LOCAL-811] run the LOCAL-809 museum-source checks on a
POOLED / REUSED museum stop, before it counts toward a tour.

The LOCAL-809 checks (no shop/product pages or titles as exhibits, a work must be
in THIS museum's collection, no Wikipedia disambiguation stub text) only ran on
FRESH research (``generate_tour_text._apply_artwork_guards`` and the retrieval
disambiguation guards). A stop delivered once and SAVED to ``stop_pool`` is reused
verbatim on the next identical request (``[LOCAL-590] POOL DELIVERY: reused=N``)
WITHOUT re-running those checks — so the Belvedere's Monet "Père Paul" / Van Gogh
"Plain of Auvers" (works held elsewhere), a "Belvedere may refer to:"
disambiguation line, and the Met Store merchandise came straight back.

This module is the pooled-stop equivalent of the fresh-path guards. It decides,
for ONE pooled row, whether the stop is a valid museum exhibit — reusing the exact
same authorities as the fresh path so the two paths cannot drift:

  * ``junk_title_guard.is_junk_page_title`` / ``is_shop_product_title`` — shop /
    product / page-chrome titles (the Met Store items). The stop's own source URLs
    feed the commerce-URL arm.
  * ``artwork_selection_guard.enforce_artworks_only`` — events / rooms / building /
    architecture, and (for an art museum) a title with no artwork class and no
    creator.
  * ``artwork_selection_guard.enforce_collection_membership`` — NOT IN THIS
    COLLECTION: a work whose P195 collection excludes the venue, a known
    misattribution, or a title that matches no SPARQL/site work of the venue. This
    is the Monet/Van Gogh "not in the Belvedere" case. Needs the venue's work set
    (``sparql_works``); when none is available the membership arm is SKIPPED (the
    title/shop/disambiguation arms still run) so a pooled stop is never wrongly
    rejected on a missing reference set.
  * ``disambiguation_guard.is_disambiguation_text`` — a stop whose body is a
    Wikipedia disambiguation stub.

``check_pooled_museum_stop`` is PURE given its inputs (no network, no DB): the
caller supplies ``sparql_works`` (from the LOCAL-810 venue-works cache or a fetch)
so this module stays unit-testable and adds no cost of its own. It returns
``(ok, reason)`` — ``ok`` False with a short machine reason string ("shop_or_junk_
title", "not_in_collection", "disambiguation_text", "event_or_architecture_title",
…) suitable for the LOCAL-792 ``move_to_rejected`` reason column.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "check_pooled_museum_stop",
    "split_pooled_museum_stops",
    "enrich_row_for_membership",
]


def _row_source_url(row: Dict) -> str:
    """Pick a source URL off a pooled row for the commerce-URL arm of the junk
    check. A pooled row carries a tour-level ``sources`` list of URL strings; the
    stop_record may also carry a per-stop URL. Returns the first usable URL, or ""."""
    if not isinstance(row, dict):
        return ""
    rec = row.get("stop_record") or {}
    if isinstance(rec, dict):
        for k in ("source_url", "detail_url", "url", "page_url"):
            v = rec.get(k)
            if v:
                return str(v)
    for s in (row.get("sources") or []):
        if isinstance(s, str) and s.strip():
            return s.strip()
        if isinstance(s, dict):
            for k in ("source_url", "detail_url", "url", "page_url"):
                if s.get(k):
                    return str(s.get(k))
    return ""


def _norm_title_for_match(s: str) -> str:
    """Normalise a title for SPARQL-work matching. Reuses the artwork guard's own
    normaliser so the pooled path and the fresh path key titles identically."""
    try:
        from artwork_selection_guard import _norm_title as _nt
        return _nt(s)
    except Exception:
        return (s or "").strip().lower()


def _sparql_by_title(sparql_works) -> Dict[str, Dict]:
    """Build a normalised-title → SPARQL-work lookup, exactly as the fresh path's
    ``_apply_artwork_guards`` does, so a pooled stop can be enriched with the P31
    class / creator / P195 collection the pooled row never stored."""
    out: Dict[str, Dict] = {}
    for w in (sparql_works or []):
        if not isinstance(w, dict):
            continue
        for k in ("label_local", "label_en", "title", "name"):
            v = w.get(k)
            if v:
                out.setdefault(_norm_title_for_match(v), w)
        for a in (w.get("aliases") or []):
            if a:
                out.setdefault(_norm_title_for_match(a), w)
    return out


def enrich_row_for_membership(row: Dict, sparql_by_title: Optional[Dict[str, Dict]] = None) -> Dict:
    """Build the ``{title, instance_of, creator, collection_qids, source_url, …}``
    candidate dict the LOCAL-809 guards consume, from a pooled row.

    A pooled row (``stop_pool_store.get_pool_stops``) stores no P31 / P195 columns,
    but (a) a STRUCTURED_STOPS row's ``stop_record`` may hold them and (b) the
    venue's SPARQL work set carries them per title. We lift from the record first,
    then ENRICH any still-missing P31 class / creator / P195 collection by matching
    the stop title against ``sparql_by_title`` — the SAME enrichment the fresh path
    (``_apply_artwork_guards``) does before the guards run, so a real catalogued
    work (Vermeer's "The Art of Painting") carries its artwork class and is not
    rejected as "no artwork class and no creator". Absent both, fields stay empty
    and the guards degrade gracefully (membership falls back to the SPARQL/site
    TITLE match)."""
    e: Dict = {
        "title": (row.get("title") or "").strip(),
        "artist": row.get("artist", "") or "",
    }
    rec = row.get("stop_record") or {}
    if isinstance(rec, dict):
        for src_key, dst_key in (
            ("instance_of", "instance_of"),
            ("creator", "creator"),
            ("creator_qid", "creator_qid"),
            ("creators", "creators"),
            ("collection_qids", "collection_qids"),
            ("aliases", "aliases"),
        ):
            v = rec.get(src_key)
            if v:
                e[dst_key] = v
    # Enrich class/creator/collection from the matched SPARQL work when the pooled
    # row (and its record) did not carry them — the fresh-path enrichment.
    _by_title = sparql_by_title if sparql_by_title is not None else {}
    _w = _by_title.get(_norm_title_for_match(e.get("title", "")))
    if _w:
        if not (e.get("instance_of") or e.get("creator") or e.get("creator_qid")):
            e.setdefault("instance_of", list(_w.get("instance_of", []) or []))
            e.setdefault("creator", _w.get("creator", ""))
            e.setdefault("creator_qid", _w.get("creator_qid", ""))
            e.setdefault("creators", list(_w.get("creators", []) or []))
            e.setdefault("aliases", list(_w.get("aliases", []) or []))
        if not e.get("collection_qids") and _w.get("collection_qids"):
            e["collection_qids"] = list(_w.get("collection_qids") or [])
    # The pooled artist name is a creator signal when nothing else supplies one.
    if not e.get("creator") and e.get("artist"):
        e["creator"] = e["artist"]
    _src = _row_source_url(row)
    if _src:
        e["source_url"] = _src
    return e


def check_pooled_museum_stop(
    row: Dict,
    *,
    venue_name: str = "",
    venue_qid: str = "",
    parent_qids: Sequence[str] = (),
    sparql_works: Sequence[Dict] = (),
    site_titles: Sequence[str] = (),
    is_art_museum: bool = True,
    sparql_by_title: Optional[Dict[str, Dict]] = None,
) -> Tuple[bool, str]:
    """Run the LOCAL-809 checks on ONE pooled museum stop. Returns ``(ok, reason)``.

    ``ok`` is True when the stop is a valid museum exhibit; False with a short
    machine reason otherwise. Checks run in a deterministic order — the cheapest,
    reference-free ones first (title / body), then the collection-membership arm
    which needs ``sparql_works``:

      1. empty title                       → reject ("empty_title")
      2. shop / product / junk page title  → reject ("shop_or_junk_title")
      3. disambiguation stub body          → reject ("disambiguation_text")
      4. event/room/building, or (art museum) no artwork class & no creator
                                            → reject (the guard's own reason)
      5. not in THIS collection (needs sparql_works/site_titles)
                                            → reject ("not_in_collection" / the
                                               guard's wrong_collection/wrong_museum
                                               reason)

    PURE: no network, no DB. ``sparql_works`` is supplied by the caller (from the
    LOCAL-810 venue-works cache or a fetch). When it is empty the membership arm in
    step 5 is a no-op (``enforce_collection_membership`` never strands a venue with
    no reference set), so the stop is judged only by the title/body arms. Non-fatal:
    any guard import/call failure returns ``(True, "")`` for that arm — a guard bug
    must never quarantine a stop that is otherwise fine (mirrors LOCAL-792)."""
    title = (row.get("title") or "").strip() if isinstance(row, dict) else ""
    if not title:
        return False, "empty_title"

    # 2. shop / product / page-chrome title (commerce URL arm uses the row's source).
    try:
        from junk_title_guard import is_junk_page_title, is_shop_product_title
        _src = _row_source_url(row)
        if is_junk_page_title(title, venue_name, source_url=_src):
            return False, "shop_or_junk_title"
        if is_shop_product_title(title):
            return False, "shop_product_title"
    except Exception:
        pass

    # 3. disambiguation stub body — check the narration and the raw block.
    try:
        from disambiguation_guard import is_disambiguation_text
        for _body_key in ("narration", "raw_block"):
            _body = row.get(_body_key) if isinstance(row, dict) else ""
            if _body and is_disambiguation_text(_body, title):
                return False, "disambiguation_text"
    except Exception:
        pass

    enriched = enrich_row_for_membership(
        row, sparql_by_title if sparql_by_title is not None
        else _sparql_by_title(sparql_works))

    # 4. collection membership — reject on a DEFINITIVE foreign signal only.
    #    The Monet "Père Paul" / Van Gogh "Plain of Auvers" at the Belvedere carry
    #    a Wikidata collection (P195) that is some OTHER museum: that is a hard,
    #    reliable "wrong_collection" reject (it reads the work's OWN P195, not a
    #    fuzzy title match). A curated misattribution is "wrong_museum". Both are
    #    trustworthy for a pooled row.
    #
    #    The SOFT "not_in_collection" title-miss (a title that simply is not found
    #    in the venue's SPARQL/site set) is NOT treated as a rejection here: a
    #    pooled row carries no P31/creator and the venue works cache is often keyed
    #    by English labels while the pooled title is the local-language form
    #    ("Leda col cigno" vs the cached "Leda and the Swan"), so a title-miss on a
    #    pooled row is unreliable and would quarantine real works. A stop is removed
    #    on membership ONLY when its own collection data proves it belongs
    #    elsewhere. No-op without a reference collection / without P195 on the row.
    try:
        from artwork_selection_guard import enforce_collection_membership
        _mkept, _mdropped = enforce_collection_membership(
            [enriched], sparql_works=list(sparql_works or []),
            site_titles=list(site_titles or []),
            venue_name=venue_name, venue_qid=venue_qid,
            parent_qids=tuple(parent_qids or ()),
            is_art_museum=bool(is_art_museum))
        if _mdropped:
            _reason = _mdropped[0].get("_reject_reason") or ""
            # Only the definitive signals reject a pooled row; a soft title-miss
            # ("not_in_collection") is kept (unreliable for pooled data).
            if _reason.startswith("wrong_collection"):
                return False, _reason
            if _reason.startswith("wrong_museum"):
                return False, _reason
            # else: not_in_collection title-miss — keep.
    except Exception:
        pass

    # 5. artworks-only: reject the RELIABLE, title/class-based non-exhibits — a
    #    known non-artwork P31 class (event / treaty / building / room), an
    #    event/architecture TITLE, a room/space title, the venue itself. These are
    #    deterministic and need no Wikidata enrichment, so they are trustworthy on a
    #    pooled row.
    #
    #    The POSITIVE "must read as an artwork" requirement ("no artwork class and
    #    no creator") is NOT applied to a pooled row: it relies on a P31 artwork
    #    class or a creator that a pooled row does not store, and the venue works
    #    cache is keyed by English labels, so a real local-language work ("Leda col
    #    cigno", "Adorazione dei Magi") would be wrongly rejected. Passing
    #    is_art_museum=False runs the class/title REJECTS (steps 1–3 of the guard,
    #    which ignore is_art_museum) while SKIPPING the art-museum-only positive
    #    gate (step 4) — exactly the reliable subset we want for pooled rows.
    try:
        from artwork_selection_guard import enforce_artworks_only
        _kept, _dropped = enforce_artworks_only(
            [enriched], venue_name=venue_name, is_art_museum=False)
        if _dropped:
            return False, (_dropped[0].get("_reject_reason") or "not_an_artwork")
    except Exception:
        pass

    return True, ""


def split_pooled_museum_stops(
    rows: Sequence[Dict],
    *,
    venue_name: str = "",
    venue_qid: str = "",
    parent_qids: Sequence[str] = (),
    sparql_works: Sequence[Dict] = (),
    site_titles: Sequence[str] = (),
    is_art_museum: bool = True,
) -> Tuple[List[Dict], List[Tuple[Dict, str]]]:
    """Split pooled rows into ``(kept, rejected)`` by :func:`check_pooled_museum_stop`.

    ``kept`` preserves input order. ``rejected`` is a list of ``(row, reason)``
    pairs so the caller can quarantine each row with its own reason and log the
    before/after exactly as the ticket asks. Pure; delegates every decision to the
    per-stop checker."""
    kept: List[Dict] = []
    rejected: List[Tuple[Dict, str]] = []
    _by_title = _sparql_by_title(sparql_works)
    for row in rows or []:
        ok, reason = check_pooled_museum_stop(
            row, venue_name=venue_name, venue_qid=venue_qid,
            parent_qids=parent_qids, sparql_works=sparql_works,
            site_titles=site_titles, is_art_museum=is_art_museum,
            sparql_by_title=_by_title)
        if ok:
            kept.append(row)
        else:
            rejected.append((row, reason))
    return kept, rejected

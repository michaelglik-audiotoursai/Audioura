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

import re
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


# [LOCAL-811B] P31 classes that mark a work as a MULTIPLE — a cast, print,
# impression or edition that exists, by its nature, in several collections. A
# bronze CAST of a Rodin, a Dürer/Hokusai PRINT, an etching impression, or a
# photographic print is held by many museums at once, so a single foreign P195 on
# the Wikidata item does NOT prove a particular museum's copy is "not in this
# collection". The LEAD rule: reject on P195 only when the work is UNIQUE and its
# single P195 is another museum; keep casts/prints/editions. These QIDs are the
# print/sculpture-cast/photograph classes a museum catalogues as a multiple.
_MULTIPLE_INSTANCE_QIDS = frozenset({
    "Q11060274",   # print (etching/engraving/woodcut — issued in an edition)
    "Q18887969",   # copper engraving print
    "Q18218093",   # etching print
    "Q18219090",   # woodcut print
    "Q1396354",    # color woodcut
    "Q23657281",   # drypoint print
    "Q133067",     # engraving (general)
    "Q189207",     # etching (medium alias)
    "Q11835431",   # lithograph (print)
    "Q22669539",   # aquatint (print)
    "Q860861",     # sculpture (bronzes are cast in editions — Rodin, Degas)
    "Q179700",     # statue (cast)
    "Q22669857",   # tapestry (woven in sets/editions)
    "Q125191",     # photograph (printed in editions)
    "Q11060274",   # dup (print)
    "Q15123870",   # lithograph (alt)
    "Q18761202",   # (watercolour is unique — intentionally NOT here)
})
# Remove the deliberately-excluded unique class if a dup slipped in.
_MULTIPLE_INSTANCE_QIDS = frozenset(
    q for q in _MULTIPLE_INSTANCE_QIDS if q != "Q18761202")

# Title/medium words that mark a multiple when P31 is absent (a pooled row rarely
# carries P31). "cast", "edition", "impression", "print", "proof" — the museum
# label words for a copy of a multiple. Matched case-insensitively as whole words.
_MULTIPLE_WORD_RE = re.compile(
    r"(?i)\b(cast|casting|edition|impression|proof|replica|"
    r"print|etching|engraving|woodcut|lithograph|aquatint|drypoint|"
    r"photograph|photogravure)\b")


def _is_multiple_or_edition(enriched: Dict) -> bool:
    """[LOCAL-811B] True when the (enriched) pooled row looks like an instance of a
    MULTIPLE — a cast, print, impression or edition — so a single foreign P195 must
    NOT reject it. Signals (any one): a multiple/edition P31 class, or a
    cast/edition/print/impression word in the title or an artist/medium field.
    Pure; conservative — a unique painting/drawing carries none of these."""
    if not isinstance(enriched, dict):
        return False
    try:
        from artwork_selection_guard import _qids as _q
        for q in _q(enriched.get("instance_of")):
            if q in _MULTIPLE_INSTANCE_QIDS:
                return True
    except Exception:
        pass
    for k in ("title", "medium", "type_specialty", "artist"):
        v = enriched.get(k)
        if isinstance(v, str) and _MULTIPLE_WORD_RE.search(v):
            return True
    return False


def _p195_count(enriched: Dict) -> int:
    """Number of distinct P195 (collection) QIDs on the (enriched) row."""
    if not isinstance(enriched, dict):
        return 0
    try:
        from artwork_selection_guard import _qid_norm
        qids = {_qid_norm(c) for c in (enriched.get("collection_qids") or [])}
        qids.discard("")
        return len(qids)
    except Exception:
        return len(enriched.get("collection_qids") or [])


def _title_is_site_listed(enriched: Dict, site_titles: Sequence[str],
                          sparql_works: Sequence[Dict]) -> bool:
    """[LOCAL-811B] True when the venue's OWN site (or SPARQL set) lists this title
    — the museum itself says the work is here, which overrides a stale/foreign
    Wikidata P195. Reuses the fresh-path title matcher so the two paths agree."""
    try:
        from artwork_selection_guard import _collection_title_set, _entry_is_collection_confirmed
        allowed = _collection_title_set(sparql_works or [], site_titles or [])
        if not allowed:
            return False
        return _entry_is_collection_confirmed(enriched, allowed)
    except Exception:
        return False


def check_pooled_museum_stop(
    row: Dict,
    *,
    venue_name: str = "",
    venue_qid: str = "",
    parent_qids: Sequence[str] = (),
    sparql_works: Sequence[Dict] = (),
    site_titles: Sequence[str] = (),
    is_art_museum: bool = True,
    contained: bool = True,
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
                # [LOCAL-811B] A single foreign P195 does NOT prove a MULTIPLE is
                # not here. Per the LEAD rule, reject on P195 only when the work is
                # UNIQUE with a SINGLE foreign P195. Keep it when it is an instance
                # of a multiple (cast/print/impression/edition), carries >= 2 P195
                # values (held by several collections), or the venue's own site /
                # SPARQL set lists the title. Rodin's "The Age of Bronze" (a bronze
                # cast whose Wikidata P195 names one museum) is kept here.
                if (_is_multiple_or_edition(enriched)
                        or _p195_count(enriched) >= 2
                        or _title_is_site_listed(enriched, site_titles, sparql_works)):
                    pass  # a multiple / multi-P195 / site-listed work — keep
                else:
                    return False, _reason
            elif _reason.startswith("wrong_museum"):
                # The curated known-home map is a hard, single-home masterpiece
                # signal (Ophelia → Tate), but a multiple with that title (a
                # print/cast edition) is still spared on the same rule.
                if (_is_multiple_or_edition(enriched)
                        or _p195_count(enriched) >= 2
                        or _title_is_site_listed(enriched, site_titles, sparql_works)):
                    pass
                else:
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
            _areason = _dropped[0].get("_reject_reason") or "not_an_artwork"
            # [LOCAL-811B] The room/space and venue-itself rejects are MUSEUM
            # (contained) concepts — a stop inside one building. A walking /
            # neighbourhood pool's stops ARE places: "Salem Witch Trials Memorial",
            # "Salem Common", "Salem Maritime National Historic Site", "Salem
            # Willows Park" are legitimate outdoor stops, not museum rooms. Per the
            # LEAD rule, apply `room_or_space_title` (and the sibling
            # `venue_itself_title`) ONLY to contained tours; for a non-contained
            # pool these two rejects are ignored (the stop is kept). The commerce,
            # disambiguation, event/non-artwork-class and collection rejects still
            # apply to every reused stop.
            if not contained and _areason in ("room_or_space_title",
                                              "venue_itself_title"):
                pass  # outdoor/walking pool — a named place, not a museum space
            else:
                return False, _areason
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
    contained: bool = True,
) -> Tuple[List[Dict], List[Tuple[Dict, str]]]:
    """Split pooled rows into ``(kept, rejected)`` by :func:`check_pooled_museum_stop`.

    ``kept`` preserves input order. ``rejected`` is a list of ``(row, reason)``
    pairs so the caller can quarantine each row with its own reason and log the
    before/after exactly as the ticket asks. Pure; delegates every decision to the
    per-stop checker.

    ``contained`` (default True) is passed through to each check: for a
    non-contained (walking / neighbourhood) pool the room/space and venue-itself
    rejects are skipped, so a named outdoor place ("Salem Common") is never moved
    out as a "room_or_space_title" (LOCAL-811B LEAD item 4)."""
    kept: List[Dict] = []
    rejected: List[Tuple[Dict, str]] = []
    _by_title = _sparql_by_title(sparql_works)
    for row in rows or []:
        ok, reason = check_pooled_museum_stop(
            row, venue_name=venue_name, venue_qid=venue_qid,
            parent_qids=parent_qids, sparql_works=sparql_works,
            site_titles=site_titles, is_art_museum=is_art_museum,
            contained=contained, sparql_by_title=_by_title)
        if ok:
            kept.append(row)
        else:
            rejected.append((row, reason))
    return kept, rejected

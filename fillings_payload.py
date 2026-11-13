#!/usr/bin/env python3
"""fillings_payload.py — LOCAL-907 (D772): the ADDITIVE ``fillings`` field of the tour payload.

    "fillings": [{"leg": 0, "after_stop": 1, "minutes": 37.4,
                  "items": [{"segment_id": 12, "title": "...", "theme": "history",
                             "minutes": 12.7, "audio_url": "...", "credit_line": "...",
                             "language": "en", "sources": [{"title": "...", "url": "..."}],
                             "source_url": "...|null", "sentence_ends": [4.2, 9.8]}]}]

``leg`` is 0-based (leg 0 = Stop 1 -> Stop 2); ``after_stop`` is the 1-based number of the stop
the leg follows. The first item is the default auto-play. Old apps ignore the key; nothing else in
the payload is touched (``attach_fillings`` only ADDS ``fillings``).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

import topic_library as tl
import topic_picker as tp

_STOP_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
_TYPE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")
_DIR_RE = re.compile(r"(?mi)^Directions:\s*(.+?)\s*$")
_STATED_KM = re.compile(r"(?i)\b(?:roughly|about|approximately|around)\s+(\d+(?:\.\d+)?)\s*(?:km|kilomet(?:er|re)s?)\b")


def stops_from_tour_text(tour_text: str) -> List[Dict[str, Any]]:
    """Stops (title, lat, lng, type_specialty) from the delivered tour text's block grammar."""
    heads = list(_STOP_RE.finditer(tour_text or ""))
    stops = []
    for i, m in enumerate(heads):
        block = tour_text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(tour_text)]
        stop: Dict[str, Any] = {"title": m.group(2)}
        c = _COORD_RE.search(block)
        if c:
            stop["lat"], stop["lng"] = float(c.group(1)), float(c.group(2))
        t = _TYPE_RE.search(block)
        if t:
            stop["type_specialty"] = t.group(1)
        stops.append(stop)
    for i, stop in enumerate(stops[:-1]):       # [LOCAL-909] a road distance the Directions state ("roughly 51 km")
        d = _DIR_RE.search(tour_text[heads[i].end(): heads[i + 1].start()])
        nxt = re.sub(r"\s*\(.*?\)\s*", " ", stops[i + 1]["title"]).strip().lower()
        for sent in re.split(r"(?<=[.!?])\s+", d.group(1)) if d else []:
            km = _STATED_KM.search(sent)
            if km and nxt and nxt in sent.lower():       # the sentence that names the NEXT stop and its distance
                stop["leg_distance_km"] = float(km.group(1))
    return stops


def audio_url(audio_path: Optional[str]) -> Optional[str]:
    if not audio_path:
        return None
    base = os.environ.get("TOPIC_AUDIO_BASE_URL", "/topic-audio")
    return base.rstrip("/") + "/" + audio_path.lstrip("/")


def clean_sources(sources: Any) -> List[Dict[str, str]]:
    """[LOCAL-907E] ``[{title, url}]`` from a row's ``sources`` JSON; http(s) urls only."""
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except ValueError:
            return []
    out = []
    for s in sources if isinstance(sources, list) else []:
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "").strip()
        if not re.match(r"(?i)^https?://\S+$", url):
            continue
        out.append({"title": str(s.get("title") or url), "url": url})
    return out


def clean_sentence_ends(ends: Any) -> List[float]:
    """[LOCAL-907E] seconds, one per sentence end, ascending; [] when not rendered with timing."""
    if isinstance(ends, str):
        try:
            ends = json.loads(ends)
        except ValueError:
            return []
    try:
        vals = [round(float(x), 2) for x in (ends or [])]
    except (TypeError, ValueError):
        return []
    return vals


def _item(p: Dict[str, Any]) -> Dict[str, Any]:
    sources = clean_sources(p.get("sources"))
    return {"segment_id": p["segment_id"], "title": p["title"], "theme": p["theme"],
            "minutes": p["minutes"], "audio_url": audio_url(p.get("audio_path")),
            "credit_line": p["credit_line"], "language": p.get("language") or "en",
            "sources": sources, "source_url": sources[0]["url"] if sources else None,
            "sentence_ends": clean_sentence_ends(p.get("sentence_ends"))}


def build_fillings(tour: Dict[str, Any], listener_weights: Optional[Dict[str, float]] = None, *,
                   segments=None, recent_segment_ids=(), store=None) -> List[Dict[str, Any]]:
    # [LOCAL-907E] the player cannot play text: a segment with no audio is never picked (so the
    # leg is filled with segments that DO have audio, not left short by items dropped afterwards)
    if segments is None and store is not None:
        segments = store.list_segments(None, tour.get("language") or "en", "ready")
    if segments is not None:
        segments = [s for s in segments if s.get("audio_path")]
    picks = tp.pick_fillings(tour, listener_weights, segments=segments,
                             recent_segment_ids=recent_segment_ids, store=store)
    out = []
    for leg in sorted(picks):
        items = picks[leg]
        mins, src = tp.leg_minutes_source(tour, leg)
        print(f"[LOCAL-909] leg {leg} {mins or 0.0:.1f} min (source: {src}; "
              f"mode {tp.normalise_mode(tour)})", flush=True)
        out.append({
            "leg": leg, "after_stop": leg + 1,
            "minutes": round(mins or 0.0, 1),
            "items": [_item(p) for p in items if p.get("audio_path")]})
    return out


def add_fillings_to_zip(zip_path: str, fillings: Optional[List[Dict[str, Any]]],
                        log: Callable[[str], None] = print) -> bool:
    """[LOCAL-907E] Append ``fillings.json`` (``{"fillings": [...]}``) to a tour ZIP.
    Append mode: every existing entry is left byte-identical. No fillings => no file.
    Never raises (a failure is logged and the tour is delivered as before)."""
    if not fillings:
        return False
    try:
        import zipfile
        with zipfile.ZipFile(zip_path, "a") as zf:
            if "fillings.json" in zf.namelist():
                return False
            zf.writestr("fillings.json",
                        json.dumps({"fillings": fillings}, ensure_ascii=False).encode("utf-8"))
        log(f"[LOCAL-907E] fillings.json: {len(fillings)} legs, "
            f"{sum(len(l.get('items') or []) for l in fillings)} items")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"[LOCAL-907E] fillings.json not written: {exc}")
        return False


def attach_fillings(payload: Dict[str, Any], fillings: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Add ``fillings`` to a response dict (in place) and return it. Every existing key is left
    exactly as it was. No fillings => the key is not added at all."""
    if fillings:
        payload["fillings"] = fillings
    return payload


def _connect():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"), database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"), password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"), connect_timeout=3)


def fillings_for_tour(tour_content: str, tour_type: str = "", user_id: Optional[str] = None,
                      language: str = "en", connect: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Fillings for a just-generated tour. READ-ONLY (SELECTs on topic_segments /
    listening_events / listener_theme_weights). Never raises: any failure (table not migrated
    yet, DB down, no stops) returns [] so tour delivery is never affected.
    Disabled with TOPIC_FILLINGS_ENABLED=false."""
    if os.environ.get("TOPIC_FILLINGS_ENABLED", "true").strip().lower() in ("0", "false", "no", "off"):
        return []
    conn = None
    try:
        stops = stops_from_tour_text(tour_content)
        if len(stops) < 2:
            return []
        import listening_events as le
        conn = (connect or _connect)()
        store = tl.PgSegmentStore(conn)
        repo = le.PgRepo(conn)
        weights = repo.get_weights(str(user_id)) if user_id else {}
        recent = repo.recent_segment_ids(str(user_id)) if user_id else []
        tour = {"stops": stops, "tour_type": tour_type, "language": language}
        segments = store.list_segments(None, language, "ready", light=True)
        return build_fillings(tour, weights, segments=segments, recent_segment_ids=recent)
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

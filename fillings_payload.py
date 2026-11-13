#!/usr/bin/env python3
"""fillings_payload.py — LOCAL-907 (D772): the ADDITIVE ``fillings`` field of the tour payload.

    "fillings": [{"leg": 0, "after_stop": 1, "minutes": 37.4,
                  "items": [{"segment_id": 12, "title": "...", "theme": "history",
                             "minutes": 12.7, "audio_url": "...|null", "credit_line": "..."}]}]

``leg`` is 0-based (leg 0 = Stop 1 -> Stop 2); ``after_stop`` is the 1-based number of the stop
the leg follows. The first item is the default auto-play. Old apps ignore the key; nothing else in
the payload is touched (``attach_fillings`` only ADDS ``fillings``).
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional

import topic_library as tl
import topic_picker as tp

_STOP_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
_TYPE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")


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
    return stops


def audio_url(audio_path: Optional[str]) -> Optional[str]:
    if not audio_path:
        return None
    base = os.environ.get("TOPIC_AUDIO_BASE_URL", "/topic-audio")
    return base.rstrip("/") + "/" + audio_path.lstrip("/")


def build_fillings(tour: Dict[str, Any], listener_weights: Optional[Dict[str, float]] = None, *,
                   segments=None, recent_segment_ids=(), store=None) -> List[Dict[str, Any]]:
    picks = tp.pick_fillings(tour, listener_weights, segments=segments,
                             recent_segment_ids=recent_segment_ids, store=store)
    out = []
    for leg in sorted(picks):
        items = picks[leg]
        out.append({
            "leg": leg, "after_stop": leg + 1,
            "minutes": round(tp.leg_minutes(tour, leg) or 0.0, 1),
            "items": [{"segment_id": p["segment_id"], "title": p["title"], "theme": p["theme"],
                       "minutes": p["minutes"], "audio_url": audio_url(p.get("audio_path")),
                       "credit_line": p["credit_line"]} for p in items]})
    return out


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

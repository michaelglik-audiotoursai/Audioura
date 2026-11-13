#!/usr/bin/env python3
"""topic_picker.py — LOCAL-907 (D772): choose the "fillings" for the legs of a tour.

    pick_fillings(tour, listener_weights=None, *, segments=..., recent_segment_ids=...)
        -> {leg_index: [segment ref, ...]}

A leg runs from Stop N to Stop N+1 (``leg_index`` is 0-based: leg 0 = Stop 1 -> Stop 2).
Only legs of MIN_LEG_MINUTES or more get fillings. Each gets a ranked list of up to
MAX_ITEMS segments whose TOTAL playing time stays within ``leg minutes + SLACK_MINUTES``
(so the queue never outlasts the drive); the first item is the default auto-play.

Pure and deterministic: no clock, no randomness, no I/O. Ties break on segment id.

``tour`` (dict):
    stops   [{title, lat, lng, type_specialty | type | specialty}]   in tour order
    mode    'car' | 'bike' | 'walk'   (or ``tour_type`` text such as "driving tour")
    area    'city' | 'rural'  (optional; car speed 25 vs 35 km/h. Default: a leg under
            CITY_LEG_KM road-km is treated as city, otherwise rural)
    legs    optional route data: [{minutes}] or [{distance_km}] per leg — overrides the
            estimate. A stop may also carry ``leg_minutes`` / ``leg_distance_km`` (to the next).
    language   'en' (default) — only segments in this language are offered
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import topic_library as tl

MIN_LEG_MINUTES = 8.0
MIN_ITEMS, MAX_ITEMS = 3, 5
SLACK_MINUTES = 5.0
CIRCUITY = 1.3                    # road km per straight-line km when no route data exists
CITY_LEG_KM = 6.0
SPEEDS_KMH = {"car_rural": 35.0, "car_city": 25.0, "bike": 14.0, "walk": 4.5}

W_REGION, W_THEME_FIT, W_LISTENER = 1.0, 1.5, 2.0
WEIGHT_CLAMP = 5.0


def normalise_mode(tour: Dict[str, Any]) -> str:
    raw = " ".join(str(tour.get(k, "")) for k in ("mode", "tour_type")).lower()
    if any(w in raw for w in ("car", "driv", "road", "auto", "motor", "scooter")):
        return "car"
    if any(w in raw for w in ("bik", "cycl", "bicycle")):
        return "bike"
    return "walk"


def _coord(stop: Dict[str, Any]):
    try:
        return float(stop["lat"]), float(stop["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def leg_minutes(tour: Dict[str, Any], i: int) -> Optional[float]:
    """Minutes from stop i to stop i+1, or None when it cannot be known."""
    stops = tour.get("stops") or []
    legs = tour.get("legs") or []
    route = legs[i] if i < len(legs) and isinstance(legs[i], dict) else {}
    mode = normalise_mode(tour)

    def _from_km(km: float) -> float:
        if mode == "car":
            area = tour.get("area")
            city = (str(area).lower() in ("city", "urban")) if area else km <= CITY_LEG_KM
            speed = SPEEDS_KMH["car_city" if city else "car_rural"]
        else:
            speed = SPEEDS_KMH[mode]
        return km / speed * 60.0

    if route.get("minutes") is not None:
        return float(route["minutes"])
    if stops[i].get("leg_minutes") is not None:
        return float(stops[i]["leg_minutes"])
    if route.get("distance_km") is not None:
        return _from_km(float(route["distance_km"]))
    if stops[i].get("leg_distance_km") is not None:
        return _from_km(float(stops[i]["leg_distance_km"]))
    a, b = _coord(stops[i]), _coord(stops[i + 1])
    if not a or not b:
        return None
    return _from_km(tl.haversine_km(a[0], a[1], b[0], b[1]) * CIRCUITY)


def _stop_text(stop: Dict[str, Any]) -> str:
    return " ".join(str(stop.get(k, "")) for k in ("type_specialty", "type", "specialty")).lower()


def stop_themes(stop: Dict[str, Any]) -> frozenset:
    text = _stop_text(stop)
    return frozenset(t for t, kws in tl.STOP_TYPE_AFFINITY.items() if any(k in text for k in kws))


def _rank_score(seg: Dict[str, Any], mid, fit: frozenset, weights: Dict[str, float]):
    """None when the segment is outside the leg's region; otherwise a score (higher = better)."""
    if seg.get("centroid_lat") is None or seg.get("centroid_lng") is None:
        return None
    radius = float(seg.get("radius_km") or 0)
    d = tl.haversine_km(mid[0], mid[1], float(seg["centroid_lat"]), float(seg["centroid_lng"]))
    if radius <= 0 or d > radius:
        return None
    region = 1.0 - d / radius
    w = max(-WEIGHT_CLAMP, min(WEIGHT_CLAMP, float(weights.get(seg["theme"], 0.0)))) / WEIGHT_CLAMP
    return (W_REGION * region + W_THEME_FIT * (1.0 if seg["theme"] in fit else 0.0) + W_LISTENER * w)


def segment_ref(seg: Dict[str, Any], score: float) -> Dict[str, Any]:
    return {"segment_id": seg["id"], "title": seg["title"], "theme": seg["theme"],
            "minutes": float(seg["est_minutes"]), "audio_path": seg.get("audio_path"),
            "credit_line": seg.get("credit_line", ""), "score": round(score, 4)}


def pick_fillings(tour: Dict[str, Any], listener_weights: Optional[Dict[str, float]] = None, *,
                  segments: Optional[Iterable[Dict[str, Any]]] = None,
                  recent_segment_ids: Iterable[int] = (), store: Any = None
                  ) -> Dict[int, List[Dict[str, Any]]]:
    """See module docstring. ``segments`` (dicts as in topic_segments) or a ``store`` with
    ``list_segments`` supplies the library; ``recent_segment_ids`` are the segments the listener
    heard in their last 5 tours (listening_events.recent_segment_ids)."""
    stops = tour.get("stops") or []
    if len(stops) < 2:
        return {}
    language = tour.get("language") or "en"
    if segments is None:
        segments = store.list_segments(None, language, "ready") if store is not None else []
    pool = [s for s in segments
            if s.get("status", "ready") == "ready" and s.get("language", "en") == language
            and float(s.get("est_minutes") or 0) > 0]
    weights = listener_weights or {}
    used = set(int(x) for x in recent_segment_ids)
    result: Dict[int, List[Dict[str, Any]]] = {}
    for i in range(len(stops) - 1):
        minutes = leg_minutes(tour, i)
        if minutes is None or minutes < MIN_LEG_MINUTES:
            continue
        a, b = _coord(stops[i]), _coord(stops[i + 1])
        if not a or not b:
            continue
        mid = tl.midpoint(a[0], a[1], b[0], b[1])
        fit = stop_themes(stops[i]) | stop_themes(stops[i + 1])
        ranked = []
        for s in pool:
            if s["id"] in used:
                continue
            score = _rank_score(s, mid, fit, weights)
            if score is not None:
                ranked.append((-score, s["id"], s, score))
        ranked.sort(key=lambda r: (r[0], r[1]))
        budget = minutes + SLACK_MINUTES
        picked, total = [], 0.0
        for _neg, _id, seg, score in ranked:
            m = float(seg["est_minutes"])
            if total + m <= budget + 1e-9:
                picked.append(segment_ref(seg, score))
                total += m
                if len(picked) == MAX_ITEMS:
                    break
        if picked:
            for p in picked:
                used.add(p["segment_id"])
            result[i] = picked
    return result

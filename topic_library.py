#!/usr/bin/env python3
"""topic_library.py — LOCAL-907 (D772): shared pieces of the Regional Topic Library.

The library fills the 20-60 minute legs between stops of long driving / biking /
walking tours with region-wide talk (history, food, transport, legends ...). Each
region's segments are written ONCE (topic_library_build.py) and reused on every tour
there (topic_picker.py); the listener's choices (listening_events.py) teach us their
preferences.

This module holds what the builder, the picker and the API share: the theme list,
region data (D769: no place names in code — see data/topic_regions.json), geometry,
the segment store interface (Postgres + in-memory), and small text helpers.
Everything here is pure or takes an injected connection: no network, no env needed.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional

WORDS_PER_MINUTE = 150
CREDIT_LINE = ("This segment is based on Wikipedia articles, used under the "
               "Creative Commons Attribution-ShareAlike licence.")
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

THEMES = ["history", "modern", "people_economy", "religion_customs", "food",
          "transport", "nature", "legends", "arts"]

# Generic (place-free) keyword cues that map a section / article title to a theme.
THEME_KEYWORDS: Dict[str, List[str]] = {
    "history": ["history", "histor", "colonial", "ancient", "medieval", "revolution",
                "war", "conquest", "founding", "origin", "empire", "dynasty", "era",
                "independence", "settlement", "early"],
    "modern": ["modern", "contemporary", "government", "administration", "politic",
               "province", "district", "municipal", "demograph", "urban", "development",
               "reform", "since", "21st", "20th", "city council", "law"],
    "people_economy": ["economy", "economic", "industry", "agriculture", "fishing",
                       "tourism", "trade", "business", "employment", "people", "population",
                       "ethnic", "community", "daily life", "education", "income",
                       "health", "demographics", "commerce", "finance", "port"],
    "religion_customs": ["religion", "religious", "church", "temple", "pagoda", "festival",
                         "custom", "tradition", "belief", "worship", "ritual", "carnival",
                         "holiday", "faith", "mission", "cathedral", "mosque"],
    "food": ["cuisine", "food", "recipe", "dish", "drink", "wine", "cooking", "culinary",
             "market", "sauce", "seafood", "restaurant", "bakery", "coffee", "tea"],
    "transport": ["transport", "transit", "railway", "rail", "road", "highway", "bridge",
                  "airport", "harbour", "harbor", "port", "ferry", "trolley", "tram",
                  "bus", "metro", "subway", "tunnel", "getting around", "cycling"],
    "nature": ["geography", "climate", "geology", "nature", "environment", "wildlife",
               "park", "beach", "coast", "river", "mountain", "dune", "lake", "forest",
               "flora", "fauna", "weather", "island", "bay", "sea", "topography"],
    "legends": ["legend", "myth", "folklore", "tale", "story", "stories", "mystery",
                "ghost", "saint", "hero", "epic", "lore", "in popular culture"],
    "arts": ["art", "arts", "architecture", "music", "museum", "theatre", "theater",
             "literature", "film", "cinema", "culture", "gallery", "design", "sculpture",
             "painting", "dance", "sport", "landmark", "monument"],
}

# Which themes fit a STOP, judged from its Type/Specialty text (picker "theme fit").
STOP_TYPE_AFFINITY: Dict[str, List[str]] = {
    "history": ["museum", "historic", "history", "fort", "castle", "palace", "memorial",
                "monument", "battle", "heritage", "ruins", "old town", "landmark"],
    "religion_customs": ["church", "cathedral", "temple", "pagoda", "mosque", "shrine",
                         "synagogue", "monastery", "chapel", "religio", "festival"],
    "food": ["restaurant", "food", "market", "cafe", "café", "bakery", "winery", "bar",
             "brewery", "street food", "cuisine"],
    "nature": ["park", "beach", "dune", "lake", "garden", "nature", "trail", "mountain",
               "waterfall", "forest", "viewpoint", "lighthouse", "coast", "bay", "river"],
    "arts": ["gallery", "art", "architecture", "theatre", "theater", "opera", "music",
             "sculpture", "library", "design"],
    "transport": ["station", "port", "pier", "harbor", "harbour", "bridge", "railway",
                  "ferry", "airport", "terminal"],
    "people_economy": ["market", "village", "neighborhood", "neighbourhood", "district",
                       "fishing", "farm", "industry", "factory", "plaza", "square"],
    "modern": ["skyline", "tower", "city hall", "downtown", "university", "campus", "plaza"],
    "legends": ["legend", "myth", "haunted", "folklore", "cave"],
}

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REGIONS_PATH = os.path.join(_REPO_ROOT, "data", "topic_regions.json")


# ── regions (data) ───────────────────────────────────────────────────────────
def load_regions(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """{region_key: region dict}. Each region gets default_themes filled in."""
    with open(path or REGIONS_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    defaults = list(raw.get("default_themes") or THEMES)
    out: Dict[str, Dict[str, Any]] = {}
    for r in raw.get("regions", []):
        r = dict(r)
        r.setdefault("default_themes", defaults)
        out[r["region_key"]] = r
    return out


def get_region(region_key: str, path: Optional[str] = None) -> Dict[str, Any]:
    regions = load_regions(path)
    if region_key not in regions:
        raise KeyError(f"unknown region {region_key!r}; known: {sorted(regions)}")
    return regions[region_key]


# ── geometry ─────────────────────────────────────────────────────────────────
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def midpoint(lat1: float, lng1: float, lat2: float, lng2: float):
    """Great-circle midpoint (good enough, and exact for short legs)."""
    p1, l1, p2 = math.radians(lat1), math.radians(lng1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    bx, by = math.cos(p2) * math.cos(dl), math.cos(p2) * math.sin(dl)
    pm = math.atan2(math.sin(p1) + math.sin(p2),
                    math.sqrt((math.cos(p1) + bx) ** 2 + by ** 2))
    lm = l1 + math.atan2(by, math.cos(p1) + bx)
    return math.degrees(pm), (math.degrees(lm) + 540) % 360 - 180


# ── text helpers ─────────────────────────────────────────────────────────────
def word_count(text: str) -> int:
    return len((text or "").split())


def est_minutes(words: int) -> float:
    return round(words / float(WORDS_PER_MINUTE), 2)


def classify_theme(*texts: str) -> Optional[str]:
    """Best theme for a title / heading by keyword cue (None when nothing matches).
    Earlier keywords in THEMES order win ties; whole-word match beats substring."""
    blob = " ".join(t for t in texts if t).lower()
    if not blob:
        return None
    best, best_score = None, 0
    for theme in THEMES:
        score = 0
        for kw in THEME_KEYWORDS[theme]:
            if re.search(r"\b" + re.escape(kw) + r"\b", blob):
                score += 2
            elif kw in blob:
                score += 1
        if score > best_score:
            best, best_score = theme, score
    return best


# ── segment store ────────────────────────────────────────────────────────────
SEGMENT_COLUMNS = ["id", "region_key", "theme", "title", "language", "text", "word_count",
                   "est_minutes", "sources", "credit_line", "centroid_lat", "centroid_lng",
                   "radius_km", "audio_path", "source_segment_id", "status", "cost_usd",
                   "created_at"]


class MemorySegmentStore:
    """In-memory store (tests, dry runs). Same interface as PgSegmentStore."""

    def __init__(self, segments: Optional[Iterable[Dict[str, Any]]] = None):
        self._rows: Dict[int, Dict[str, Any]] = {}
        self._next = 1
        for s in segments or []:
            self.insert_segment(dict(s))

    def insert_segment(self, seg: Dict[str, Any]) -> int:
        seg = dict(seg)
        sid = seg.get("id") or self._next
        self._next = max(self._next, int(sid)) + 1
        seg["id"] = int(sid)
        self._rows[seg["id"]] = seg
        return seg["id"]

    def get_segment(self, segment_id: int) -> Optional[Dict[str, Any]]:
        return dict(self._rows[segment_id]) if segment_id in self._rows else None

    def list_segments(self, region_key: Optional[str] = None, language: Optional[str] = None,
                      status: Optional[str] = None, light: bool = False) -> List[Dict[str, Any]]:
        out = []
        for s in self._rows.values():
            if region_key and s.get("region_key") != region_key:
                continue
            if language and s.get("language") != language:
                continue
            if status and s.get("status") != status:
                continue
            out.append(dict(s))
        return sorted(out, key=lambda r: r["id"])

    def set_audio_path(self, segment_id: int, audio_path: str) -> None:
        self._rows[segment_id]["audio_path"] = audio_path


class PgSegmentStore:
    """Postgres store over an injected psycopg2-style connection (never opened here).
    All SQL is parameterised. INSERT/UPDATE on topic_segments only."""

    def __init__(self, conn):
        self.conn = conn

    def _rows(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return [dict(zip(SEGMENT_COLUMNS, r)) for r in cur.fetchall()]
        finally:
            cur.close()

    _SELECT = "SELECT " + ", ".join(SEGMENT_COLUMNS) + " FROM topic_segments"
    # picker queries do not need the 12 KB body of every segment
    _SELECT_LIGHT = ("SELECT " + ", ".join("'' AS text" if c == "text" else c for c in SEGMENT_COLUMNS)
                     + " FROM topic_segments")

    def insert_segment(self, seg: Dict[str, Any]) -> int:
        cols = [c for c in SEGMENT_COLUMNS if c not in ("id", "created_at") and c in seg]
        vals = [json.dumps(seg[c]) if c == "sources" else seg[c] for c in cols]
        sql = ("INSERT INTO topic_segments (" + ", ".join(cols) + ") VALUES ("
               + ", ".join("%s" for _ in cols) + ") RETURNING id")
        cur = self.conn.cursor()
        try:
            cur.execute(sql, tuple(vals))
            sid = cur.fetchone()[0]
        finally:
            cur.close()
        self.conn.commit()
        return sid

    def get_segment(self, segment_id: int) -> Optional[Dict[str, Any]]:
        rows = self._rows(self._SELECT + " WHERE id = %s", (segment_id,))
        return rows[0] if rows else None

    def list_segments(self, region_key: Optional[str] = None, language: Optional[str] = None,
                      status: Optional[str] = None, light: bool = False) -> List[Dict[str, Any]]:
        where, params = [], []
        for col, val in (("region_key", region_key), ("language", language), ("status", status)):
            if val:
                where.append(f"{col} = %s")
                params.append(val)
        sql = (self._SELECT_LIGHT if light else self._SELECT) \
            + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
        return self._rows(sql, tuple(params))

    def set_audio_path(self, segment_id: int, audio_path: str) -> None:
        cur = self.conn.cursor()
        try:
            cur.execute("UPDATE topic_segments SET audio_path = %s WHERE id = %s",
                        (audio_path, segment_id))
        finally:
            cur.close()
        self.conn.commit()

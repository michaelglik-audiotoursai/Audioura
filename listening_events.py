#!/usr/bin/env python3
"""listening_events.py — LOCAL-907 (D772): what listeners do with fillings, and what it teaches.

Events: start | skip | finish | choose.  Each stored event also nudges the listener's weight
for the segment's theme (listener_theme_weights), which topic_picker uses to rank:

    finish                      +1.0
    skip before 60 s            -1.0
    skip at/after 60 s          -0.3
    choose (from the menu)      +0.5
    start                        0
    decay: every weight x0.95 when the listener begins a new tour; clamp to [-5, 5].

The math is pure (``weight_delta``, ``clamp``, ``decay``, ``replay``). Persistence goes through
a small repo interface: ``PgRepo`` (parameterised SQL, INSERT/UPDATE only — no DELETE) and
``MemoryRepo`` (tests). The caller owns the connection.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

ACTIONS = ("start", "skip", "finish", "choose")
FINISH_DELTA = 1.0
SKIP_EARLY_DELTA = -1.0
SKIP_LATE_DELTA = -0.3
CHOOSE_DELTA = 0.5
SKIP_EARLY_SECONDS = 60.0
DECAY_PER_TOUR = 0.95
WEIGHT_MIN, WEIGHT_MAX = -5.0, 5.0
RECENT_TOURS = 5
MAX_AT_SEC = 24 * 3600.0


class ValidationError(ValueError):
    """The posted event is malformed (HTTP 400)."""


# ── pure math ────────────────────────────────────────────────────────────────
def clamp(w: float) -> float:
    return max(WEIGHT_MIN, min(WEIGHT_MAX, float(w)))


def weight_delta(action: str, at_sec: float = 0.0) -> float:
    if action == "finish":
        return FINISH_DELTA
    if action == "skip":
        return SKIP_EARLY_DELTA if float(at_sec) < SKIP_EARLY_SECONDS else SKIP_LATE_DELTA
    if action == "choose":
        return CHOOSE_DELTA
    return 0.0


def decay(weights: Dict[str, float], tours: int = 1) -> Dict[str, float]:
    f = DECAY_PER_TOUR ** max(0, int(tours))
    return {t: clamp(w * f) for t, w in weights.items()}


def replay(events: Iterable[Dict[str, Any]], theme_of: Dict[Any, str],
           start: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Weights after a chronological stream of one listener's events. ``theme_of`` maps
    segment_id -> theme. The first event of each new tour_id decays all weights first."""
    weights = dict(start or {})
    seen = set()
    for ev in events:
        if ev["tour_id"] not in seen:
            if seen:                      # the listener's very first tour has nothing to decay
                weights = decay(weights)
            seen.add(ev["tour_id"])
        d = weight_delta(ev["action"], ev.get("at_sec", 0.0))
        theme = theme_of.get(ev["segment_id"])
        if d and theme:
            weights[theme] = clamp(weights.get(theme, 0.0) + d)
    return weights


# ── validation ───────────────────────────────────────────────────────────────
def validate_event(payload: Any) -> Dict[str, Any]:
    """Clean a POSTed event or raise ValidationError. Returns
    {user_id, tour_id, segment_id, action, at_sec}."""
    if not isinstance(payload, dict):
        raise ValidationError("JSON object required")
    out: Dict[str, Any] = {}
    for key in ("user_id", "tour_id"):
        v = payload.get(key)
        if isinstance(v, bool) or v is None or not str(v).strip():
            raise ValidationError(f"{key} is required")
        v = str(v).strip()
        if len(v) > 128:
            raise ValidationError(f"{key} is too long")
        out[key] = v
    seg = payload.get("segment_id")
    try:
        if isinstance(seg, bool) or isinstance(seg, float) and seg != int(seg):
            raise ValueError
        seg = int(seg)
    except (TypeError, ValueError):
        raise ValidationError("segment_id must be an integer")
    if seg <= 0:
        raise ValidationError("segment_id must be positive")
    out["segment_id"] = seg
    action = payload.get("action")
    if action not in ACTIONS:
        raise ValidationError(f"action must be one of {', '.join(ACTIONS)}")
    out["action"] = action
    at = payload.get("at_sec", 0)
    try:
        at = float(0 if at is None else at)
    except (TypeError, ValueError):
        raise ValidationError("at_sec must be a number")
    if isinstance(payload.get("at_sec"), bool) or at != at or at < 0 or at > MAX_AT_SEC:
        raise ValidationError(f"at_sec must be between 0 and {int(MAX_AT_SEC)}")
    out["at_sec"] = at
    return out


# ── repos ────────────────────────────────────────────────────────────────────
class MemoryRepo:
    def __init__(self, segment_themes: Optional[Dict[int, str]] = None):
        self.themes = dict(segment_themes or {})
        self.events: List[Dict[str, Any]] = []
        self.weights: Dict[str, Dict[str, float]] = {}

    def segment_theme(self, segment_id: int) -> Optional[str]:
        return self.themes.get(segment_id)

    def tour_seen(self, user_id: str, tour_id: str) -> bool:
        return any(e["user_id"] == user_id and e["tour_id"] == tour_id for e in self.events)

    def has_events(self, user_id: str) -> bool:
        return any(e["user_id"] == user_id for e in self.events)

    def insert_event(self, ev: Dict[str, Any]) -> int:
        self.events.append(dict(ev, id=len(self.events) + 1))
        return len(self.events)

    def decay_user(self, user_id: str, factor: float) -> None:
        w = self.weights.get(user_id, {})
        self.weights[user_id] = {t: clamp(v * factor) for t, v in w.items()}

    def bump_weight(self, user_id: str, theme: str, delta: float) -> None:
        w = self.weights.setdefault(user_id, {})
        w[theme] = clamp(w.get(theme, 0.0) + delta)

    def get_weights(self, user_id: str) -> Dict[str, float]:
        return dict(self.weights.get(user_id, {}))

    def commit(self) -> None:
        pass

    def recent_segment_ids(self, user_id: str, n_tours: int = RECENT_TOURS) -> List[int]:
        tours: List[str] = []
        for e in reversed([e for e in self.events if e["user_id"] == user_id]):
            if e["tour_id"] not in tours:
                tours.append(e["tour_id"])
        keep = set(tours[:n_tours])
        return sorted({e["segment_id"] for e in self.events
                       if e["user_id"] == user_id and e["tour_id"] in keep})


class PgRepo:
    """psycopg2-style connection; every statement is parameterised. Writes: INSERT into
    listening_events, UPSERT/UPDATE listener_theme_weights. Nothing is ever deleted."""

    def __init__(self, conn):
        self.conn = conn

    def _one(self, sql: str, params: tuple):
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            cur.close()

    def _exec(self, sql: str, params: tuple) -> None:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
        finally:
            cur.close()

    def segment_theme(self, segment_id: int) -> Optional[str]:
        row = self._one("SELECT theme FROM topic_segments WHERE id = %s", (segment_id,))
        return row[0] if row else None

    def tour_seen(self, user_id: str, tour_id: str) -> bool:
        return self._one("SELECT 1 FROM listening_events WHERE user_id = %s AND tour_id = %s LIMIT 1",
                         (user_id, tour_id)) is not None

    def has_events(self, user_id: str) -> bool:
        return self._one("SELECT 1 FROM listening_events WHERE user_id = %s LIMIT 1",
                         (user_id,)) is not None

    def insert_event(self, ev: Dict[str, Any]) -> int:
        row = self._one(
            "INSERT INTO listening_events (user_id, tour_id, segment_id, action, at_sec) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (ev["user_id"], ev["tour_id"], ev["segment_id"], ev["action"], ev["at_sec"]))
        return row[0]

    def decay_user(self, user_id: str, factor: float) -> None:
        self._exec("UPDATE listener_theme_weights SET weight = GREATEST(%s, LEAST(%s, weight * %s)), "
                   "updated_at = NOW() WHERE user_id = %s",
                   (WEIGHT_MIN, WEIGHT_MAX, factor, user_id))

    def bump_weight(self, user_id: str, theme: str, delta: float) -> None:
        self._exec(
            "INSERT INTO listener_theme_weights (user_id, theme, weight, updated_at) "
            "VALUES (%s, %s, GREATEST(%s, LEAST(%s, %s)), NOW()) "
            "ON CONFLICT (user_id, theme) DO UPDATE SET "
            "weight = GREATEST(%s, LEAST(%s, listener_theme_weights.weight + %s)), updated_at = NOW()",
            (user_id, theme, WEIGHT_MIN, WEIGHT_MAX, delta, WEIGHT_MIN, WEIGHT_MAX, delta))

    def get_weights(self, user_id: str) -> Dict[str, float]:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT theme, weight FROM listener_theme_weights WHERE user_id = %s", (user_id,))
            return {t: float(w) for t, w in cur.fetchall()}
        finally:
            cur.close()

    def commit(self) -> None:
        self.conn.commit()

    def recent_segment_ids(self, user_id: str, n_tours: int = RECENT_TOURS) -> List[int]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT DISTINCT segment_id FROM listening_events WHERE user_id = %s AND tour_id IN ("
                "SELECT tour_id FROM listening_events WHERE user_id = %s "
                "GROUP BY tour_id ORDER BY MAX(created_at) DESC LIMIT %s)",
                (user_id, user_id, int(n_tours)))
            return sorted(int(r[0]) for r in cur.fetchall())
        finally:
            cur.close()


# ── apply ────────────────────────────────────────────────────────────────────
class UnknownSegment(LookupError):
    """segment_id does not exist (HTTP 404)."""


def apply_event(repo, event: Dict[str, Any]) -> Dict[str, Any]:
    """Store one VALIDATED event and update the listener's theme weight. Order: (1) the segment
    must exist, (2) a listener's first event of a NEW tour decays their weights once (x0.95),
    (3) the event is stored, (4) the theme weight moves by the action's delta, clamped."""
    theme = repo.segment_theme(event["segment_id"])
    if theme is None:
        raise UnknownSegment(f"segment {event['segment_id']} not found")
    if not repo.tour_seen(event["user_id"], event["tour_id"]) and repo.has_events(event["user_id"]):
        repo.decay_user(event["user_id"], DECAY_PER_TOUR)
    event_id = repo.insert_event(event)
    delta = weight_delta(event["action"], event["at_sec"])
    if delta:
        repo.bump_weight(event["user_id"], theme, delta)
    repo.commit()
    return {"id": event_id, "theme": theme, "weight_delta": delta}

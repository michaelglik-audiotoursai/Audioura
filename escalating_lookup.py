"""escalating_lookup.py — LOCAL-784 / D722: the escalation ladder before any
"nothing found", with an escalation log and learned routing.

WHY THIS EXISTS
---------------
Michael, 2026-10-26 (D722): LOCAL-779B refused "Middle Eastern restaurants near
me, West Roxbury" because the FREE OpenStreetMap tool found nothing — while
Google lists three (Al Wadi, Stardust, Bread Thyme). His rule:

  "If the cheap tools find nothing, try a dearer one before refusing. If it
   really is nothing we spent little; if it was our mistake we avoided an
   embarrassment. Record each case and learn from it."

THE LADDER
----------
`escalating_lookup(kind, query, scope, needed, ...)` is the ONE sourcing entry
used at every point that would otherwise drop a stop or refuse for lack of
places: the business/restaurant search + refill, the existence-gate "no evidence"
for business POIs, the `no_matching_places_in_area` refusal, and the
by-reference "no material" path when the request names a place.

It runs tiers until the FIRST one yields >= `needed` verified results:

  (a) THE CHEAP PATH — today's behaviour. `dining_replenish_candidates` /
      `business_replenish_candidates` with Serper OFF resolves to the free
      Nominatim endpoint (or whatever the deployed cheap provider is). Costs
      nothing extra. D722_FORCE_CHEAP_MISS=1 forces this tier empty (test-only).

  (b) SERPER PLACES with `ll` — LOCAL-783. The same replenish functions with the
      Serper Places provider ON. Metered $0.002 per uncached query by `_meter`.
      This is the tier that rescues West Roxbury.

  (c) GEMINI with Google-Search grounding — a structured JSON list of real places
      (name, address). Each name is RE-VERIFIED on Places / geocode inside the
      scope before use; an unverifiable Gemini name is DROPPED. Metered per
      grounded request by `_meter` (the gemini network wrapper). SKIPPED when a
      grounding guard is active (an L2 by-reference build forbids grounding), so
      the by-reference path escalates only through the free/cheap tiers.

A per-request escalation BUDGET of $0.10 (D722_ESCALATION_BUDGET_USD) caps the
dearer tiers: before tier b or c we check `check_daily_limit()` AND the running
escalation spend; if the next tier would exceed the budget we stop and refuse
with what we have.

THE LOG (lookup_escalations, migration 055)
-------------------------------------------
One row per escalation EVENT: whenever a dearer tier (b/c) found what a cheaper
tier missed (so a free-OSM miss that Serper/Google rescued is visible), AND
whenever ALL tiers found nothing (tier_found='none', so a genuine absence is
visible too). A tier-a hit — the cheap path already sufficed — writes NO row;
there was no escalation to record.

LEARNED ROUTING (lookup_routing, migration 055)
-----------------------------------------------
region_key = geohash-5 of the scope centre (~5 km cell). Every cheap-tier (a)
miss increments misses_7d for (category, region_key). Once it is >= 3 in 7 days,
the ladder STARTS at the tier that worked (start_tier), skipping the known-empty
cheap call, and logs a `[D722] route hit` line. Every routing row is REVERSIBLE:
deleting it restores start-at-tier-a with no code change (a LEAD lever, never a
code path).

RESULTS GO INTO THE CACHE
-------------------------
A tier-b result is already in the LOCAL-783 24 h places cache (it came through
`places_search`). A tier-c result that re-verified on Places is likewise cached
by that verification call, so a repeat request is served cheaply. The found
candidates are returned to the caller, which puts them into the stop pool exactly
as the LOCAL-779B maps-first stops are today.

FAIL-OPEN
---------
Every DB write and meter read is wrapped; a failure here never blocks a tour.
The worst case is an escalation that is not logged or a budget check that fails
open. The ladder itself degrades to "tier a only" if the dearer providers are
unavailable, which is exactly today's behaviour.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "escalating_lookup",
    "EscalationResult",
    "region_key_for",
    "geohash5",
]

# ── Tunables (env-overridable; safe defaults) ────────────────────────────────

# Per-request escalation budget. The dearer tiers (b, c) are only attempted while
# the running escalation spend stays under this. 0 or unset keeps the default.
_BUDGET_USD = float(os.environ.get("D722_ESCALATION_BUDGET_USD", "0.10") or "0.10")

# How many cheap-tier misses in the window promote a (category, region_key) to
# start at the tier that worked.
_ROUTE_MISS_THRESHOLD = int(os.environ.get("D722_ROUTE_MISS_THRESHOLD", "3") or "3")
_ROUTE_WINDOW_DAYS = 7

# Rough per-tier cost estimates used ONLY to decide "would the next tier breach
# the budget?" before we spend. The real spend is metered by `_meter`; these are
# conservative upper bounds so we never start a tier we cannot afford.
_EST_TIER_B_USD = float(os.environ.get("D722_EST_TIER_B_USD", "0.004") or "0.004")
_EST_TIER_C_USD = float(os.environ.get("D722_EST_TIER_C_USD", "0.060") or "0.060")

# DB connect + statement timeout (seconds). The ladder must never stall a tour.
_DB_TIMEOUT_S = float(os.environ.get("D722_DB_TIMEOUT", "1") or "1")

_GEMINI_TIMEOUT_S = float(os.environ.get("D722_GEMINI_TIMEOUT", "30") or "30")


def _force_cheap_miss() -> bool:
    """D722_FORCE_CHEAP_MISS=1 forces tier a to return empty (test / live-proof
    only), so the ladder is exercised even where the free provider would answer.
    Never set in production."""
    return (os.environ.get("D722_FORCE_CHEAP_MISS", "") or "").strip() in ("1", "true", "yes")


# ── Result container ─────────────────────────────────────────────────────────

class EscalationResult:
    """The outcome of one escalating_lookup call.

    Attributes:
      results      — the verified candidate dicts (same shape the replenish
                     functions return), at most `needed` long, best first.
      tier_found   — 'a' | 'b' | 'c' | 'none' (which tier satisfied, or none).
      cost_usd     — metered escalation spend attributed to this request.
      results_by_tier — {'a':[names], 'b':[names], 'c':[names]} for the log.
      logged       — True if a lookup_escalations row was written.
    """

    __slots__ = ("results", "tier_found", "cost_usd", "results_by_tier", "logged")

    def __init__(self, results, tier_found, cost_usd, results_by_tier, logged):
        self.results = results
        self.tier_found = tier_found
        self.cost_usd = cost_usd
        self.results_by_tier = results_by_tier
        self.logged = logged

    def __repr__(self):
        return (f"EscalationResult(tier_found={self.tier_found!r}, "
                f"n={len(self.results)}, cost_usd={self.cost_usd:.6f}, "
                f"logged={self.logged})")


# ── geohash-5 (region_key) ───────────────────────────────────────────────────

_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash5(lat: float, lng: float) -> str:
    """Geohash of (lat, lng) truncated to 5 characters (~4.9 km x 4.9 km cell).

    A tiny, dependency-free geohash encoder — the standard algorithm, enough for
    a stable regional bucket. Returns '' on bad input."""
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return ""
    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    out = []
    bit = 0
    ch = 0
    even = True  # even bits bisect longitude, odd bits latitude
    while len(out) < 5:
        if even:
            mid = (lng_lo + lng_hi) / 2
            if lng >= mid:
                ch = (ch << 1) | 1
                lng_lo = mid
            else:
                ch = ch << 1
                lng_hi = mid
        else:
            mid = (lat_lo + lat_hi) / 2
            if lat >= mid:
                ch = (ch << 1) | 1
                lat_lo = mid
            else:
                ch = ch << 1
                lat_hi = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_GEOHASH_BASE32[ch])
            bit = 0
            ch = 0
    return "".join(out)


def region_key_for(scope_center: Optional[Tuple[float, float]], scope: str) -> str:
    """The region_key for a lookup: geohash-5 of the scope centre when known,
    else a normalised scope-text fallback so routing still buckets by place."""
    if scope_center:
        gh = geohash5(scope_center[0], scope_center[1])
        if gh:
            return gh
    # No geocode — fall back to a stable text key so routing still groups by the
    # scope string (lower, comma-normalised). Prefixed so it never collides with
    # a real geohash (geohashes use only base32 chars, never 't:').
    s = (scope or "").strip().lower()
    s = ",".join(p.strip() for p in s.split(",") if p.strip())
    return f"t:{s}" if s else ""


# ── DB helpers (dual connection style, never raise) ──────────────────────────

def _connect():
    """Open a psycopg2 connection with a bounded timeout, supporting BOTH the
    discrete DB_* env style and DATABASE_URL. Returns a connection or raises."""
    import psycopg2  # lazy: a DB-less caller can still import this module
    connect_timeout = max(1, int(round(_DB_TIMEOUT_S)))
    stmt_ms = max(1, int(_DB_TIMEOUT_S * 1000))
    options = f"-c statement_timeout={stmt_ms}"
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=connect_timeout,
                                options=options)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        database=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
        port=os.environ.get("DB_PORT", "5432"),
        connect_timeout=connect_timeout, options=options)


_SELF_HEAL_DDL = """
CREATE TABLE IF NOT EXISTS lookup_escalations (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    user_id         TEXT,
    request         TEXT,
    kind            TEXT,
    category        TEXT,
    scope           TEXT,
    scope_lat       DOUBLE PRECISION,
    scope_lng       DOUBLE PRECISION,
    tier_found      TEXT         NOT NULL,
    results_by_tier JSONB        NOT NULL DEFAULT '{}'::jsonb,
    cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS lookup_routing (
    category     TEXT         NOT NULL,
    region_key   TEXT         NOT NULL,
    start_tier   TEXT         NOT NULL DEFAULT 'a',
    misses_7d    INTEGER      NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (category, region_key)
);
"""

_INSERT_ESCALATION = """
INSERT INTO lookup_escalations
    (ts, user_id, request, kind, category, scope, scope_lat, scope_lng,
     tier_found, results_by_tier, cost_usd)
VALUES
    (%(ts)s, %(user_id)s, %(request)s, %(kind)s, %(category)s, %(scope)s,
     %(scope_lat)s, %(scope_lng)s, %(tier_found)s, %(results_by_tier)s,
     %(cost_usd)s)
"""


def _with_cursor(fn: Callable):
    """Run fn(cursor) inside a bounded, self-healing transaction. Never raises.
    Returns fn's value on success, or None on any failure."""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        try:
            out = fn(cur)
        except Exception:
            # A table may be missing on a DB that never ran migration 055.
            conn.rollback()
            cur.execute(_SELF_HEAL_DDL)
            conn.commit()
            out = fn(cur)
        conn.commit()
        cur.close()
        return out
    except Exception as e:
        logger.info(f"[D722] DB op skipped (fail-open): {type(e).__name__}: {e}")
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _log_escalation(row: Dict) -> bool:
    """Write one lookup_escalations row. Returns True iff the row landed."""
    def _do(cur):
        cur.execute(_INSERT_ESCALATION, row)
        return True
    return bool(_with_cursor(_do))


def _routing_start_tier(category: str, region_key: str) -> Optional[str]:
    """Return the promoted start_tier for (category, region_key) when it has
    missed the cheap tier >= threshold in the window; else None (start at a)."""
    if not category or not region_key:
        return None

    def _do(cur):
        cur.execute(
            "SELECT start_tier, misses_7d, updated_at FROM lookup_routing "
            "WHERE category = %s AND region_key = %s",
            (category, region_key))
        return cur.fetchone()
    row = _with_cursor(_do)
    if not row:
        return None
    start_tier, misses_7d, updated_at = row[0], row[1], row[2]
    try:
        if int(misses_7d or 0) >= _ROUTE_MISS_THRESHOLD and start_tier in ("b", "c"):
            return start_tier
    except (TypeError, ValueError):
        return None
    return None


def _record_cheap_miss(category: str, region_key: str, worked_tier: str) -> None:
    """Record that the cheap tier (a) missed for (category, region_key) and a
    dearer tier `worked_tier` ('b'/'c') ultimately worked. Increments misses_7d
    (decayed to the 7-day window) and, once the threshold is reached, promotes
    start_tier to the tier that worked. Idempotent upsert; never raises."""
    if not category or not region_key:
        return

    def _do(cur):
        # Count only misses within the window by resetting the counter when the
        # row is stale (older than the window) — a simple, self-correcting decay
        # that needs no per-event table.
        cur.execute(
            "SELECT misses_7d, updated_at, start_tier FROM lookup_routing "
            "WHERE category = %s AND region_key = %s",
            (category, region_key))
        existing = cur.fetchone()
        now = datetime.now(timezone.utc)
        if existing is None:
            misses = 1
        else:
            prev_misses, updated_at, _st = existing
            stale = False
            try:
                if updated_at is not None:
                    age_days = (now - updated_at).total_seconds() / 86400.0
                    stale = age_days > _ROUTE_WINDOW_DAYS
            except Exception:
                stale = False
            misses = (1 if stale else int(prev_misses or 0) + 1)
        # Promote the start tier once the threshold is reached; otherwise keep the
        # default 'a' so the cheap tier is still tried while we are still learning.
        new_start = worked_tier if misses >= _ROUTE_MISS_THRESHOLD else "a"
        cur.execute(
            "INSERT INTO lookup_routing (category, region_key, start_tier, "
            "misses_7d, updated_at) VALUES (%s, %s, %s, %s, now()) "
            "ON CONFLICT (category, region_key) DO UPDATE SET "
            "misses_7d = EXCLUDED.misses_7d, "
            "start_tier = CASE WHEN EXCLUDED.misses_7d >= %s "
            "                  THEN EXCLUDED.start_tier ELSE lookup_routing.start_tier END, "
            "updated_at = now()",
            (category, region_key, new_start, misses, _ROUTE_MISS_THRESHOLD))
        return misses
    _with_cursor(_do)


# ── meter: read running escalation spend for the budget cap ──────────────────

def _check_daily_limit() -> None:
    """Enforce the workspace daily paid-API limit before a dearer tier, exactly
    as the Serper/Gemini doors do. Fail-open: if the meter is unavailable we do
    not block. Re-raises the daily-limit stop so a hard cap still stops us."""
    try:
        import paid_api_meter as m
    except Exception:
        try:
            import sys
            here = os.path.dirname(os.path.abspath(__file__))
            md = os.path.join(here, "_meter")
            if md not in sys.path:
                sys.path.insert(0, md)
            import paid_api_meter as m
        except Exception:
            return
    try:
        if hasattr(m, "check_daily_limit"):
            m.check_daily_limit()
    except getattr(m, "DailyPaidLimitExceeded", ()):  # propagate the hard stop
        raise
    except Exception:
        pass


# ── tier c: Gemini with Google-Search grounding ──────────────────────────────

_TIER_C_PROMPT = (
    "List real, currently-operating {category} located in {scope}. "
    "Use Google Search to find them. Return ONLY a JSON array of objects, each "
    '{{"name": "...", "address": "..."}}, with the exact business name and its '
    "street address. Include only places that genuinely exist at a real address "
    "inside {scope}. Return at most {limit} places. No prose, no markdown — JSON "
    "array only."
)


def _parse_tier_c_json(text: str) -> List[Dict]:
    """Pull the JSON array of {name, address} out of a Gemini response. Tolerant
    of code fences and leading/trailing prose. Returns [] on anything unparseable."""
    if not text:
        return []
    s = text.strip()
    # Strip a ```json … ``` fence if present.
    if s.startswith("```"):
        s = s.split("```", 2)
        s = s[1] if len(s) >= 2 else text
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    # Find the outermost JSON array.
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(s[start:end + 1])
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        out.append({"name": name, "address": (item.get("address") or "").strip()})
    return out


def _tier_c_gemini(category: str, scope: str, limit: int) -> List[Dict]:
    """Ask Gemini (grounded with Google Search) for a JSON list of real places.
    Returns raw {name, address} dicts (NOT yet verified). [] on any failure or no
    key. Metered per grounded request by the network meter wrapper."""
    import requests
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        logger.info("[D722] tier c skipped: no GEMINI_API_KEY/GOOGLE_API_KEY")
        return []
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    prompt = _TIER_C_PROMPT.format(category=category or "places", scope=scope,
                                   limit=max(1, limit))
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {
                      "temperature": 0.2,
                      "maxOutputTokens": int(os.environ.get("GEMINI_MAX_TOKENS", "2000")),
                      "thinkingConfig": {"thinkingBudget": 0}},
                  "tools": [{"google_search": {}}]},
            timeout=_GEMINI_TIMEOUT_S)
    except Exception as e:
        logger.warning(f"[D722] tier c Gemini request failed: {type(e).__name__}: {e}")
        return []
    if r.status_code != 200:
        logger.warning(f"[D722] tier c Gemini HTTP {r.status_code}")
        return []
    try:
        d = r.json()
        cand = d["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, ValueError):
        return []
    return _parse_tier_c_json(text)


# ── the ladder ───────────────────────────────────────────────────────────────

def escalating_lookup(
    kind: str,
    query: str,
    scope: str,
    needed: int,
    *,
    tier_a: Callable[[], List[Dict]],
    tier_b: Optional[Callable[[], List[Dict]]] = None,
    verify: Optional[Callable[[str], Optional[Dict]]] = None,
    category: Optional[str] = None,
    scope_center: Optional[Tuple[float, float]] = None,
    user_id: Optional[str] = None,
    request_text: Optional[str] = None,
    allow_grounding: bool = True,
) -> EscalationResult:
    """Run the escalation ladder for a place/evidence lookup.

    Args:
      kind          — 'dining' | 'business' | 'by_reference' (the caller's path).
      query         — the free-text search ("middle eastern restaurants").
      scope         — the resolved scope text ("West Roxbury, MA").
      needed        — how many verified results satisfy the caller.
      tier_a        — callable returning the CHEAP path's candidates (dicts). The
                      caller supplies it already bound to its own arguments; the
                      ladder only decides WHETHER to call it (routing / force-miss).
      tier_b        — callable returning the Serper-Places candidates (dicts), or
                      None when the caller has no tier-b (then b is skipped).
      verify        — callable(name) -> a verified candidate dict (or None) used to
                      re-verify each tier-c Gemini name on Places/geocode inside the
                      scope. REQUIRED for tier c; without it tier c is skipped.
      category      — the routing category (cuisine / poi class). Defaults to query.
      scope_center  — (lat, lng) of the scope centre, for the region_key + ll.
      user_id       — listener id for the log row, when known.
      request_text  — the user's original request string, for the log row.
      allow_grounding — False (or an active grounding guard) skips tier c, so an
                      L2 by-reference build escalates only through a/b.

    Returns an EscalationResult. The caller uses `.results` exactly as it used the
    replenish output; a 'none' result means every tier came up empty and the
    caller refuses honestly (the refusal is now backed by a dearer search, and a
    'none' row records the real absence).
    """
    category = (category or query or "").strip().lower()
    region_key = region_key_for(scope_center, scope)
    results_by_tier: Dict[str, List[str]] = {}
    spent = 0.0

    def _names(cands: List[Dict]) -> List[str]:
        return [str((c or {}).get("name") or "").strip() for c in (cands or [])
                if (c or {}).get("name")]

    # Learned routing: start at the promoted tier when the cheap tier has missed
    # this (category, region_key) >= threshold in the window.
    promoted = _routing_start_tier(category, region_key)
    start_at_b = promoted in ("b", "c")
    if start_at_b:
        logger.info(f"[D722] route hit: ({category!r}, {region_key!r}) starts at "
                    f"tier {promoted} (>= {_ROUTE_MISS_THRESHOLD} cheap misses in "
                    f"{_ROUTE_WINDOW_DAYS}d); skipping the known-empty cheap call")

    # ── Tier a: the cheap path ────────────────────────────────────────────────
    tier_a_results: List[Dict] = []
    if not start_at_b:
        if _force_cheap_miss():
            logger.info("[D722] tier a forced empty (D722_FORCE_CHEAP_MISS=1)")
            tier_a_results = []
        else:
            try:
                tier_a_results = list(tier_a() or [])
            except Exception as e:
                logger.warning(f"[D722] tier a error (treated as empty): "
                               f"{type(e).__name__}: {e}")
                tier_a_results = []
        results_by_tier["a"] = _names(tier_a_results)
        if len(tier_a_results) >= needed:
            # The cheap path sufficed — NO escalation, NO row.
            return EscalationResult(tier_a_results[:needed], "a", 0.0,
                                    results_by_tier, logged=False)
    else:
        results_by_tier["a"] = []  # skipped by routing

    # ── Tier b: Serper Places with ll ─────────────────────────────────────────
    # Budget accounting: `spent` is a conservative running total that drives the
    # cap — each dearer tier we ATTEMPT adds its per-tier upper-bound estimate, so
    # the cap stops escalation deterministically even where no live meter hook is
    # present. `measured` is the real metered spend (the delta the meter recorded
    # for this request) when a hook exists; it is what we LOG as cost_usd, falling
    # back to the estimate so the row is never $0 for a tier that really ran.
    measured = 0.0
    tier_b_results: List[Dict] = []
    if tier_b is not None:
        if _budget_ok(spent, _EST_TIER_B_USD):
            spent += _EST_TIER_B_USD
            try:
                _check_daily_limit()
                before = _meter_spend_snapshot()
                tier_b_results = list(tier_b() or [])
                measured += _meter_spend_delta(before, _EST_TIER_B_USD)
            except _daily_limit_exc() as e:
                logger.warning(f"[D722] tier b stopped by daily paid limit: {e}")
            except Exception as e:
                logger.warning(f"[D722] tier b error (treated as empty): "
                               f"{type(e).__name__}: {e}")
                tier_b_results = []
            results_by_tier["b"] = _names(tier_b_results)
        else:
            logger.info(f"[D722] tier b skipped: escalation budget "
                        f"${_BUDGET_USD:.2f} would be exceeded (spent ${spent:.4f})")
            results_by_tier["b"] = []
        if len(tier_b_results) >= needed:
            _record_cheap_miss(category, region_key, "b")
            row = _build_log_row(user_id, request_text, kind, category, scope,
                                 scope_center, "b", results_by_tier, measured)
            logged = _log_escalation(row)
            logger.info(f"[D722] tier b rescued ({category!r} in {scope!r}): "
                        f"{len(tier_b_results)} found, cheaper tier missed; "
                        f"cost ${measured:.4f}")
            return EscalationResult(tier_b_results[:needed], "b", measured,
                                    results_by_tier, logged)

    # ── Tier c: Gemini grounded + re-verify ───────────────────────────────────
    tier_c_results: List[Dict] = []
    grounding_blocked = (not allow_grounding) or _grounding_guard_active()
    if verify is not None and not grounding_blocked and _budget_ok(spent, _EST_TIER_C_USD):
        spent += _EST_TIER_C_USD
        try:
            _check_daily_limit()
            before = _meter_spend_snapshot()
            raw = _tier_c_gemini(category or query, scope, max(needed * 3, needed + 2))
            measured += _meter_spend_delta(before, _EST_TIER_C_USD)
            # Re-verify EACH Gemini name on Places/geocode inside the scope; an
            # unverifiable name is DROPPED. This is what keeps tier c honest.
            seen = set()
            for item in raw:
                name = item.get("name", "")
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                before_v = _meter_spend_snapshot()
                try:
                    vrec = verify(name)
                except Exception as e:
                    logger.info(f"[D722] tier c verify error for {name!r}: {e}")
                    vrec = None
                measured += _meter_spend_delta(before_v, 0.0)
                if vrec:
                    tier_c_results.append(vrec)
                    if len(tier_c_results) >= needed:
                        break
                else:
                    logger.info(f"[D722] tier c dropped unverifiable Gemini name: "
                                f"{name!r}")
        except _daily_limit_exc() as e:
            logger.warning(f"[D722] tier c stopped by daily paid limit: {e}")
        except Exception as e:
            logger.warning(f"[D722] tier c error (treated as empty): "
                           f"{type(e).__name__}: {e}")
        results_by_tier["c"] = _names(tier_c_results)
    else:
        if grounding_blocked:
            logger.info("[D722] tier c skipped: grounding forbidden "
                        "(by-reference build) or disabled by caller")
        elif verify is None:
            logger.info("[D722] tier c skipped: no verify callable supplied")
        else:
            logger.info(f"[D722] tier c skipped: escalation budget "
                        f"${_BUDGET_USD:.2f} would be exceeded (spent ${spent:.4f})")
        results_by_tier["c"] = []

    if len(tier_c_results) >= needed:
        _record_cheap_miss(category, region_key, "c")
        row = _build_log_row(user_id, request_text, kind, category, scope,
                             scope_center, "c", results_by_tier, measured)
        logged = _log_escalation(row)
        logger.info(f"[D722] tier c rescued ({category!r} in {scope!r}): "
                    f"{len(tier_c_results)} verified of Gemini's list; "
                    f"cost ${measured:.4f}")
        return EscalationResult(tier_c_results[:needed], "c", measured,
                                results_by_tier, logged)

    # ── All tiers short of `needed` ───────────────────────────────────────────
    # Deliver the best partial we have (highest tier that returned anything), but
    # record tier_found honestly: if nothing came back at all it is a real absence
    # ('none'); otherwise the best tier that produced results, which the caller
    # may still accept as an honest partial.
    best = tier_c_results or tier_b_results or tier_a_results
    if best:
        best_tier = ("c" if tier_c_results else ("b" if tier_b_results else "a"))
        # A dearer tier produced SOME (but < needed) — still an escalation worth
        # recording when it beat the cheaper tier.
        if best_tier in ("b", "c"):
            _record_cheap_miss(category, region_key, best_tier)
            row = _build_log_row(user_id, request_text, kind, category, scope,
                                 scope_center, best_tier, results_by_tier, measured)
            logged = _log_escalation(row)
        else:
            logged = False
        return EscalationResult(best, best_tier, measured, results_by_tier, logged)

    # Genuinely nothing, anywhere. Record the 'none' so a real absence is visible.
    row = _build_log_row(user_id, request_text, kind, category, scope,
                         scope_center, "none", results_by_tier, measured)
    logged = _log_escalation(row)
    logger.info(f"[D722] all tiers empty for ({category!r} in {scope!r}) — honest "
                f"refusal; recorded 'none' row; cost ${measured:.4f}")
    return EscalationResult([], "none", measured, results_by_tier, logged)


# ── budget / meter plumbing ──────────────────────────────────────────────────

def _budget_ok(spent: float, next_tier_est: float) -> bool:
    """True if the next tier's estimated cost keeps the running escalation spend
    within the per-request budget. A non-positive budget disables the cap."""
    if _BUDGET_USD <= 0:
        return True
    return (spent + next_tier_est) <= _BUDGET_USD + 1e-9


_spend_lock = threading.Lock()


def _meter_module():
    try:
        import paid_api_meter as m
        return m
    except Exception:
        pass
    try:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        md = os.path.join(here, "_meter")
        if md not in sys.path:
            sys.path.insert(0, md)
        import paid_api_meter as m
        return m
    except Exception:
        return None


def _meter_spend_snapshot():
    """A best-effort snapshot of this process's escalation-attributable spend.

    The real ledger is the DB; reading it per call would be slow and racy, so for
    the per-request budget we track spend via a thread-local accumulator the meter
    fills when available. When the meter exposes no such hook we fall back to the
    per-tier cost ESTIMATES, which are conservative upper bounds — so the budget
    cap never UNDER-counts (it may stop one tier early, which is the safe
    direction). Returns an opaque token for _meter_spend_delta."""
    m = _meter_module()
    if m is not None and hasattr(m, "session_spend_usd"):
        try:
            return ("meter", float(m.session_spend_usd()))
        except Exception:
            pass
    return ("est", None)


def _meter_spend_delta(before, estimate: float) -> float:
    """Spend since `before`, for the LOGGED cost_usd. With a real meter hook
    (`session_spend_usd`) this is the measured delta the meter recorded for this
    request. Without such a hook we report the conservative per-tier `estimate`
    instead — so a row for a tier that really ran is never logged as $0, and the
    reported cost is an upper bound rather than an undercount."""
    try:
        kind, val = before
    except Exception:
        return estimate
    if kind == "meter" and val is not None:
        m = _meter_module()
        if m is not None and hasattr(m, "session_spend_usd"):
            try:
                return max(0.0, float(m.session_spend_usd()) - float(val))
            except Exception:
                return estimate
    return estimate


def _daily_limit_exc():
    """The meter's DailyPaidLimitExceeded class, or a never-matching tuple when the
    meter is unavailable (so `except _daily_limit_exc()` is always valid)."""
    m = _meter_module()
    if m is not None:
        exc = getattr(m, "DailyPaidLimitExceeded", None)
        if isinstance(exc, type):
            return exc
    return ()


def _grounding_guard_active() -> bool:
    """True while an L2 by-reference build forbids grounding (so tier c must be
    skipped — a grounded call would raise GroundingForbiddenError). Fail-safe: if
    the guard module is unavailable we assume grounding is allowed."""
    try:
        import l2_by_reference as l2
        return bool(l2.grounding_is_forbidden())
    except Exception:
        return False


def _build_log_row(user_id, request_text, kind, category, scope, scope_center,
                   tier_found, results_by_tier, cost_usd) -> Dict:
    lat = lng = None
    if scope_center:
        try:
            lat, lng = float(scope_center[0]), float(scope_center[1])
        except (TypeError, ValueError, IndexError):
            lat = lng = None
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": (str(user_id)[:255] if user_id is not None else None),
        "request": (str(request_text)[:4000] if request_text else None),
        "kind": (str(kind)[:64] if kind else None),
        "category": (str(category)[:255] if category else None),
        "scope": (str(scope)[:255] if scope else None),
        "scope_lat": lat,
        "scope_lng": lng,
        "tier_found": tier_found,
        "results_by_tier": json.dumps(results_by_tier, default=str),
        "cost_usd": round(float(cost_usd or 0.0), 6),
    }

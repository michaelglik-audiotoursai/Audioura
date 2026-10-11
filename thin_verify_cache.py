"""thin_verify_cache.py — LOCAL-668 deliverable #5 (cost cap for thin-verify).

LOCAL-667's thin-museum verification (thin_wikidata_fallback.verify_thin_candidates)
spends grounded / Serper VERIFICATION queries to reach the two-independent-source
bar. The LOCAL-667 live run cost $1.30 for one tour largely because of these.
LOCAL-668 bounds that cost two ways:

  1. A per-tour BUDGET of at most ``MAX_VERIFY_QUERIES`` (10) grounded/Serper
     verification queries. A VerificationBudget counts every grounded call and
     stops authorising them past the cap; the count is logged.

  2. A 30-day VENUE CACHE (mirrors venue_preflight's cache, same DB, same
     cache_key(venue,city) shape) of the thin-verify RESULT (the verified works +
     their sources), so a venue verified once is not re-verified — and re-verified
     at full grounded cost — for 30 days. A thin museum's catalogue does not change
     week to week; caching the verdict for a month is safe and turns the second and
     later tours of the same venue into ZERO verification queries.

Pure/DB-only; no LLM. All DB access is best-effort — a cache miss or a write
failure never fails a generation (it just means the verification runs). The cache
stores only POSITIVE, non-empty verification results (the works that reached the
bar); it never persists a transient zero so a flaky run is not frozen for 30 days.
"""
from __future__ import annotations

import json
import os
import threading
import unicodedata
from typing import Dict, List, Optional, Tuple

# Per-tour budget: at most this many grounded/Serper verification queries.
MAX_VERIFY_QUERIES = int(os.environ.get('THIN_VERIFY_MAX_QUERIES', '10'))
# 30-day venue cache TTL.
_CACHE_TTL_DAYS = int(os.environ.get('THIN_VERIFY_CACHE_TTL_DAYS', '30'))

_CACHE_LOCK = threading.RLock()


def _fold(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()


# [LEAD 2026-10-11] v2: entries written before LOCAL-669B lack the English title of each work,
# so the LOCAL-669C final identity gate could not bridge "Vườn xuân Trung Nam Bắc" to
# "North Central South Spring Garden" (HCMC tours 672/673 shipped it twice). Bumping the key
# version retires those entries without deleting any row.
_CACHE_SCHEMA = "v2"


def cache_key(venue: str, city: str) -> str:
    return f"{_CACHE_SCHEMA}|{_fold(venue)}|{_fold(city)}"


class VerificationBudget:
    """Per-tour grounded/Serper verification-query budget.

    ``spend()`` authorises ONE query if the budget is not exhausted and records
    it; it returns True when authorised, False when the cap is already reached.
    Pass ``budget.wrap(research_fn)`` a grounded callable to get one that counts
    every call and refuses (returns an empty result) once the cap is hit, so the
    cap holds even if a caller forgets to check. Thread-safe.
    """

    def __init__(self, max_queries: int = MAX_VERIFY_QUERIES):
        self.max_queries = max(0, int(max_queries))
        self.used = 0
        self._lock = threading.RLock()

    @property
    def remaining(self) -> int:
        return max(0, self.max_queries - self.used)

    def spend(self, n: int = 1) -> bool:
        with self._lock:
            if self.used + n > self.max_queries:
                return False
            self.used += n
            return True

    def wrap(self, research_fn):
        """Return a research callable that spends budget per call and returns an
        empty grounded result once the cap is reached (so callers past the cap
        get a safe miss rather than another paid query)."""
        if research_fn is None:
            return None

        def _wrapped(prompt):
            if not self.spend(1):
                return {"text": "", "sources": [], "supports": [],
                        "error": "verify_budget_exhausted"}
            return research_fn(prompt)

        return _wrapped

    def summary(self) -> str:
        return (f"[LOCAL-668] thin-verify verification queries: {self.used}/"
                f"{self.max_queries} used (cap {self.max_queries}/tour)")


def _db_conn(db_url: str):
    import psycopg2
    return psycopg2.connect(db_url)


def _ensure_table(conn) -> None:
    """Additive cache table; never DROPs/DELETEs. A stale row is ignored (TTL)
    and overwritten on refresh."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS thin_verify_cache (
                cache_key   TEXT PRIMARY KEY,
                venue       TEXT NOT NULL,
                city        TEXT NOT NULL,
                result_json TEXT NOT NULL,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


def cache_get(venue: str, city: str, db_url: Optional[str] = None
              ) -> Optional[List[Dict]]:
    """Return the cached verified-works list for (venue, city) if present and
    younger than the TTL, else None. Best-effort: any error is a miss."""
    db_url = db_url if db_url is not None else os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        with _CACHE_LOCK:
            conn = _db_conn(db_url)
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT result_json
                    FROM thin_verify_cache
                    WHERE cache_key = %s
                      AND fetched_at > NOW() - INTERVAL '%s days'
                    """,
                    (cache_key(venue, city), _CACHE_TTL_DAYS),
                )
                row = cur.fetchone()
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    try:
        res = json.loads(row[0])
        works = res.get("verified_works") if isinstance(res, dict) else None
        if isinstance(works, list):
            return works
    except (ValueError, TypeError):
        return None
    return None


def cache_put(venue: str, city: str, verified_works: List[Dict],
              db_url: Optional[str] = None) -> None:
    """Upsert the POSITIVE verification result for (venue, city). Additive upsert
    with a fresh fetched_at. Never raises; never persists an empty result (so a
    flaky zero is not frozen for 30 days)."""
    if not verified_works:
        return
    db_url = db_url if db_url is not None else os.environ.get('DATABASE_URL')
    if not db_url:
        return
    payload = json.dumps({"verified_works": verified_works})
    try:
        with _CACHE_LOCK:
            conn = _db_conn(db_url)
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO thin_verify_cache
                        (cache_key, venue, city, result_json, fetched_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (cache_key) DO UPDATE SET
                        venue = EXCLUDED.venue,
                        city = EXCLUDED.city,
                        result_json = EXCLUDED.result_json,
                        fetched_at = NOW()
                    """,
                    (cache_key(venue, city), venue, city, payload),
                )
            conn.commit()
            conn.close()
    except Exception:
        return

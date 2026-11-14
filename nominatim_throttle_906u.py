"""[LOCAL-906U] One process-wide Nominatim gate: throttle, 429 back-off, per-job answer cache, failure ledger.

Proof of 906T: 63 ``HTTP Error 429: Too many requests`` in one job. Five modules called the geocoder with their own
timers (or none), so the combined rate exceeded the usage policy (at most 1 request per second), lookups failed and
pins degraded.

Everything here is network-free and testable: the caller passes ``do_request`` (a zero-argument callable that
performs ONE HTTP request and returns its parsed result), and the clock and sleep are injectable.

  wait_turn()            block until at least ``MIN_INTERVAL_S`` has passed since the previous request, process-wide
  call(key, do_request)  cache lookup, throttle, request; on HTTP 429 honour ``Retry-After`` (capped) and retry
                         ``MAX_RETRIES`` times; cache the answer (an EMPTY answer too) for the job
  lookup_failed_for(n)   True when a request whose query mentions ``n`` failed with an error (not "no result")
  reset_job()            clear the cache and the ledger (call at the start of a tour job)
"""
import logging
import os
import re
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

# Nominatim usage policy: an absolute maximum of one request per second. The floor is not configurable downward.
_POLICY_FLOOR_S = 1.0
MIN_INTERVAL_S = max(_POLICY_FLOOR_S, float(os.getenv("NOMINATIM_MIN_INTERVAL_S", "1.0")))
MAX_RETRIES = 2                 # retries after the first 429 (so at most 3 requests per lookup)
RETRY_AFTER_CAP_S = 30.0        # a server asking for longer is not waited for
DEFAULT_BACKOFF_S = 2.0         # when a 429 carries no Retry-After: 2 s, then 4 s
FAIL_TTL_S = 60.0               # an errored lookup is not repeated for this long (the 429 window)

_lock = threading.Lock()
_last_request = 0.0
_cache: Dict[Any, Any] = {}                 # key -> ("ok", value) | ("fail", expires_at)
_failed_queries: List[str] = []
_MISS = object()


def _fold(text: str) -> str:
    t = (text or "").replace("\u0111", "d").replace("\u0110", "D")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def reset_job() -> None:
    """Forget the cached answers and the failure ledger (the start of a new job). The last-request time is kept:
    the 1 req/s limit is per process, not per job."""
    with _lock:
        _cache.clear()
        del _failed_queries[:]


def wait_turn(sleep: Callable[[float], None] = None, clock: Callable[[], float] = None,
              min_interval: Optional[float] = None) -> float:
    """Block until the process-wide minimum interval since the previous request has passed, then claim the slot.
    Returns the seconds slept. The lock is held while sleeping, so concurrent threads queue up one second apart."""
    global _last_request
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    gap = MIN_INTERVAL_S if min_interval is None else min_interval
    with _lock:
        now = clock()
        wait = gap - (now - _last_request) if _last_request else 0.0
        if wait > 0:
            sleep(wait)
        _last_request = clock()
        return max(0.0, wait)


def is_429(exc: BaseException) -> bool:
    if getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == 429:
        return True
    return getattr(getattr(exc, "response", None), "status_code", None) == 429


def retry_after_s(exc: BaseException, attempt: int) -> float:
    """Seconds to wait before retry ``attempt`` (0-based): the ``Retry-After`` header (seconds) when present, else
    exponential back-off; capped at ``RETRY_AFTER_CAP_S``."""
    headers = getattr(exc, "headers", None) or getattr(getattr(exc, "response", None), "headers", None) or {}
    raw = None
    try:
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    except Exception:
        raw = None
    try:
        secs = float(str(raw).strip()) if raw not in (None, "") else DEFAULT_BACKOFF_S * (2 ** attempt)
    except ValueError:                    # an HTTP-date form: not parsed, fall back to the back-off
        secs = DEFAULT_BACKOFF_S * (2 ** attempt)
    return max(0.0, min(secs, RETRY_AFTER_CAP_S))


def call(key: Any, do_request: Callable[[], Any], query: str = "", sleep: Callable[[float], None] = None,
         clock: Callable[[], float] = None, min_interval: Optional[float] = None, log: Callable = None,
         empty: Any = None) -> Any:
    """One throttled, cached Nominatim lookup. Returns ``do_request()``'s result; ``empty`` when every attempt
    failed (an errored lookup is remembered as FAILED, not as 'no such place'). Never raises."""
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    emit = log or (lambda m: logging.warning(m))
    with _lock:
        hit = _cache.get(key, _MISS)
    if hit is not _MISS:
        if hit[0] == "ok":
            return hit[1]
        if clock() < hit[1]:
            return empty
    for attempt in range(MAX_RETRIES + 1):
        wait_turn(sleep, clock, min_interval)
        try:
            val = do_request()
        except Exception as e:                                  # noqa: BLE001 - every failure is a failed lookup
            if is_429(e) and attempt < MAX_RETRIES:
                pause = retry_after_s(e, attempt)
                emit(f"[LOCAL-906U] geocoder 429 for {query!r}: retry {attempt + 1}/{MAX_RETRIES} after {pause:.0f}s")
                sleep(pause)
                continue
            emit(f"[GEOCODE] lookup failed for {query!r}: {e}")
            with _lock:
                _cache[key] = ("fail", clock() + FAIL_TTL_S)
                _failed_queries.append(_fold(query))
            return empty
        with _lock:
            _cache[key] = ("ok", val)                             # an empty answer is cached too
        return val
    return empty


def lookup_failed_for(name: str) -> bool:
    """True when a lookup whose query contains ``name`` ended in an ERROR (429, timeout) rather than an answer."""
    n = _fold(name)
    if not n:
        return False
    with _lock:
        return any(n in q for q in _failed_queries)

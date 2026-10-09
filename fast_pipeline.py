"""fast_pipeline.py — LOCAL-651 + LOCAL-656: overlap the INDEPENDENT up-front
waits and resolve the venue ONCE per tour (flag ``FAST_PIPELINE``).

This is the SINGLE fast_pipeline module. LOCAL-651 created it with ``is_enabled``
+ ``run_parallel`` (the concurrency primitive the OSM / knowledge-fallback / stop-
editor prefetch call sites use); LOCAL-656 adds the per-tour memo primitives
(``memoize_per_tour`` / ``seed`` / ``recall`` / ``reset_tour_memo``) used to
collapse the repeated identical resolve_venue / fetch_venue_works calls. There is
no second copy of either half.

Behind ``FAST_PIPELINE=1`` (default OFF). When OFF, ``is_enabled()`` returns False
and every call site keeps its existing serial code path, so behaviour is
byte-identical to today — nothing in this module changes what runs.

The LOCAL-651 profile (``~/audioura-worktrees/LOCAL-651/SUBMISSION_LOCAL-651.md``,
Step 1 table) found poi_selection spends ~44 s issuing INDEPENDENT waits one after
another, and that two of them are the SAME inputs fetched repeatedly:

  * ``resolve_venue`` (Wikidata) ran **4×** for the SAME venue (10.3 s total);
  * ``fetch_venue_works`` ran **3×** for the same QID (duplicates);
  * ``venue_preflight`` (14.3 s) and the up-front grounded ``gemini_with_sources``
    (9.7 s) run serially before anything else, yet depend only on the venue name.

This module provides the two primitives LOCAL-656 needs:

1. ``run_parallel`` — run a set of *independent* zero-argument callables
   concurrently and return their results IN SUBMIT ORDER, re-raising the first
   exception exactly as the serial code would have. The only behaviour change ON
   vs OFF is WHEN the identical calls are issued, never WHICH calls or in what
   order their results are consumed.

2. ``memoize_per_tour`` — a decorator that caches a function's result for the
   duration of ONE tour generation, keyed by its arguments, in a
   ``contextvars``-scoped store. Because a service job runs each tour in its own
   ``threading.Thread`` (fresh ``contextvars.Context``), the cache is automatically
   isolated per tour: a second tour starts with an EMPTY store and can never
   observe the first tour's cached object. This is NOT a cross-tour cache
   (Michael: "not yet" to caching across tours) — it is a within-one-generation
   memo that collapses the repeated identical calls to one. Guarded by the flag:
   when OFF the wrapper calls straight through, so every call still happens.

THREAD-SAFETY. The callables issue the same network/LLM calls the serial path
issues. Shared mutable state they touch (the paid-API meter, the ``[TIMING-SUB]``
SubTimer, the venue/OSM module caches) is each guarded in its own module.
``run_parallel`` adds no shared state of its own; each job owns its inputs and its
return value, and the caller assembles results after join. The per-tour memo store
is a ``contextvars.ContextVar`` whose value is a plain dict mutated only by the
owning context (one tour thread), guarded by a lock so a within-tour overlap group
that resolves the same venue concurrently still stores exactly one entry.
"""
from __future__ import annotations

import concurrent.futures
import contextvars
import functools
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

T = TypeVar("T")

FLAG_ENV = "FAST_PIPELINE"

# Pool ceiling for an overlap group. The groups we overlap are small (the up-front
# venue_preflight + grounded venue call + venue resolution — 3 independent waits);
# a modest cap keeps us well under the paid-API providers' concurrency and the
# box's resources.
DEFAULT_MAX_WORKERS = int(os.environ.get("FAST_PIPELINE_MAX_WORKERS", "6"))


def is_enabled() -> bool:
    """True only when FAST_PIPELINE=1 is explicitly set. Default OFF."""
    return os.environ.get(FLAG_ENV, "") == "1"


def run_parallel(jobs: List[Callable[[], T]],
                 max_workers: Optional[int] = None,
                 label: str = "") -> List[T]:
    """Run independent zero-arg callables concurrently; return results in order.

    * Results are returned in the SAME order as ``jobs`` (so the caller consumes
      them exactly as it would the serial results).
    * The FIRST exception raised by any job is re-raised to the caller after all
      jobs settle — matching "the same calls must happen"; a job that would have
      raised serially still raises here.
    * With 0 or 1 jobs the jobs are simply run inline in order (no thread pool) so
      there is no behavioural difference.

    This function does NOT check the flag itself — call sites decide whether to use
    it, so the OFF path never touches a thread pool.
    """
    if not jobs:
        return []
    if len(jobs) == 1:
        return [jobs[0]()]

    workers = max_workers or min(DEFAULT_MAX_WORKERS, len(jobs))
    results: List[Optional[T]] = [None] * len(jobs)
    first_exc: List[Optional[BaseException]] = [None]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        future_to_idx = {ex.submit(job): i for i, job in enumerate(jobs)}
        for fut in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                results[idx] = fut.result()
            except BaseException as e:  # noqa: BLE001 - preserve + re-raise below
                if first_exc[0] is None:
                    first_exc[0] = e

    if first_exc[0] is not None:
        raise first_exc[0]
    return results  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Per-tour memoization (contextvars-scoped; never cross-tour)
# ─────────────────────────────────────────────────────────────────────────────
#
# A single ``ContextVar`` holds a ``{namespace: {key: value}}`` dict for the
# current tour. ``contextvars`` values are isolated per ``contextvars.Context``,
# and a freshly-spawned ``threading.Thread`` runs with a fresh context in which
# the var holds its default (an empty mapping). The tour-generation service starts
# each job as its own thread, so each tour sees an empty store and its own writes
# only — exactly the "memoize within ONE tour generation, never across tours"
# requirement. Tests can call ``reset_tour_memo()`` to simulate a new tour on the
# same thread.
#
# The store is lock-guarded so that an overlap group (run_parallel) that issues the
# same resolve concurrently stores one entry and both callers get the same object.

_MEMO_VAR: "contextvars.ContextVar[Optional[Dict[str, Dict[Any, Any]]]]" = \
    contextvars.ContextVar("fast_pipeline_tour_memo", default=None)
_MEMO_LOCK = threading.Lock()

# A unique sentinel so a legitimately cached ``None`` result (resolve_venue returns
# None for an unresolvable venue) is still a cache HIT and not re-fetched.
_MISS = object()


def _memo_store() -> Dict[str, Dict[Any, Any]]:
    """Return the current context's memo store, creating it on first touch."""
    store = _MEMO_VAR.get()
    if store is None:
        store = {}
        _MEMO_VAR.set(store)
    return store


def reset_tour_memo() -> None:
    """Clear ALL per-tour memo entries for the current context.

    Call at the start of a tour generation to guarantee a clean slate even if the
    same thread/context is reused (a worker that serves two tours, or a test).
    After this, every memoized function re-fetches on its next call.

    [LOCAL-656B] The venue resolution memo is NOT a second cache: it lives in
    ``venue_resolver`` as the LOCAL-661 always-on 429-safety memo, and the
    LOCAL-656 FAST_PIPELINE speed path reads/writes THAT same store. So the single
    per-tour venue memo must be reset here too, otherwise a worker that served a
    previous tour (or a test re-using the main thread) would see the prior tour's
    resolved QIDs. Import-safe + non-fatal: a missing/!memo venue_resolver is a
    no-op.
    """
    _MEMO_VAR.set({})
    try:
        import venue_resolver as _vr
        _vr.reset_resolution_memo()
    except Exception:
        pass


def recall(namespace: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
    """Return the current tour's memoised value for ``fn(*args, **kwargs)`` in
    ``namespace``, or the ``_MISS`` sentinel when absent.

    The read half of ``memoize_per_tour`` / ``seed``, exposed so a hand-written
    wrapper (venue_resolver.fetch_venue_works) can collapse repeated identical
    calls to one within a tour when FAST_PIPELINE is ON. Returns ``_MISS`` (never
    raises) when the flag is OFF, so the caller's OFF path issues every call.
    """
    if not is_enabled():
        return _MISS
    key = _make_key(args, kwargs)
    with _MEMO_LOCK:
        store = _memo_store()
        ns = store.get(namespace)
        if ns is None:
            return _MISS
        return ns.get(key, _MISS)


def memo_miss_sentinel() -> Any:
    """Return the ``_MISS`` sentinel so callers of ``recall`` can test for a hit
    without importing a private name."""
    return _MISS


def seed(namespace: str, args: Tuple[Any, ...], kwargs: Dict[str, Any],
         value: Any) -> None:
    """Pre-populate the current context's memo for ``namespace`` with ``value``,
    keyed exactly as ``memoize_per_tour`` would key the call ``fn(*args, **kwargs)``.

    This is how an up-front OVERLAP group (which computes a resolve on a worker
    thread, in its own ``contextvars`` context) hands its result back to the main
    tour context so the first in-pipeline call is a memo HIT rather than a second
    network fetch. A no-op when FAST_PIPELINE is OFF (the memo is never consulted).
    """
    if not is_enabled():
        return
    key = _make_key(args, kwargs)
    with _MEMO_LOCK:
        store = _memo_store()
        ns = store.get(namespace)
        if ns is None:
            ns = {}
            store[namespace] = ns
        ns[key] = value


def _make_key(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
    """Build a hashable cache key from a call's positional + keyword arguments.

    Falls back to the ``repr`` of any unhashable argument so the memo degrades
    gracefully (still a stable key for the same inputs) instead of raising.
    """
    def _h(v: Any) -> Any:
        try:
            hash(v)
            return v
        except TypeError:
            return repr(v)

    key_args = tuple(_h(a) for a in args)
    key_kwargs = tuple(sorted((k, _h(v)) for k, v in kwargs.items()))
    return (key_args, key_kwargs)


def memoize_per_tour(namespace: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: memoize a function's result for the duration of ONE tour.

    * Keyed by the call's arguments — SAME arguments return the SAME result object
      within one tour; different arguments are distinct entries.
    * Scoped to the current ``contextvars.Context`` (one tour thread), so a second
      tour (a new thread / a ``reset_tour_memo()``) does NOT reuse the first's
      result. This is a per-generation memo, not a cross-tour cache.
    * Guarded by ``FAST_PIPELINE``: when the flag is OFF the wrapper calls straight
      through on EVERY call (no store touched), so the call count is unchanged and
      the code path is byte-identical to today.
    * A cached ``None`` is a real hit (resolve_venue returns None for an
      unresolvable venue): we store a sentinel so it is not re-fetched.

    ``namespace`` separates one memoized function's entries from another's in the
    shared per-tour store.
    """
    def _decorate(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def _inner(*args: Any, **kwargs: Any) -> T:
            if not is_enabled():
                return fn(*args, **kwargs)
            key = _make_key(args, kwargs)
            with _MEMO_LOCK:
                store = _memo_store()
                ns = store.get(namespace)
                if ns is None:
                    ns = {}
                    store[namespace] = ns
                cached = ns.get(key, _MISS)
            if cached is not _MISS:
                return cached  # type: ignore[return-value]
            # Compute OUTSIDE the lock so a slow network resolve does not serialise
            # unrelated keys; a concurrent duplicate for the SAME key may compute
            # twice in a rare race, but the last writer wins and both callers get a
            # consistent object. (In practice the up-front overlap issues each
            # distinct resolve once.)
            result = fn(*args, **kwargs)
            with _MEMO_LOCK:
                store = _memo_store()
                ns = store.get(namespace)
                if ns is None:
                    ns = {}
                    store[namespace] = ns
                ns[key] = result
            return result

        # Expose the undecorated function so tests / call sites can bypass the memo
        # when they genuinely need a fresh call.
        _inner.__wrapped_no_memo__ = fn  # type: ignore[attr-defined]
        return _inner

    return _decorate

"""dead_host_breaker.py — LOCAL-445-C: Michael's dead-host rule.

Michael's ruling (2026-08-12, BINDING):

> The trigger is not a duration — it is the FIRST timeout or 429 on a host.
> Mark that host cold for the remainder of the run; every subsequent call to
> it short-circuits immediately. Never retry a host that has already failed once
> this run.

Implementation:
  - Process-level (module-scope) cold set: once a host fails, it stays cold.
  - Thread-safe: uses a lock for the cold set.
  - The Wikimedia bucket rule: en.wikipedia.org, fr.wikipedia.org,
    query.wikidata.org, and *.wikipedia.org REST endpoints all share one
    per-IP rate-limit bucket. Failing over between them is a wasted round trip.
    They are treated as a single logical host group 'wikimedia'.

Public API:
  - mark_host_cold(host) — record first failure
  - is_host_cold(host) -> bool — check before any network call
  - get_cold_hosts() -> set — for diagnostics
  - reset_cold_hosts() — for test teardown
  - extract_host(url) -> str — normalise URL to host
  - WIKIMEDIA_HOSTS — the set of hosts sharing one bucket

LOCAL-572 (2026-10-03, BINDING clarification of Michael's rule):
  "the remainder of the run" means the remainder of ONE TOUR, not the lifetime
  of the long-lived container/Cloud-Run process. The module used to keep a single
  process-level cold set, so one Wikimedia 429 disabled Wikipedia + Wikidata for
  every later tour served by that process until restart (museum tours then
  clean-failed as "unresolvable"). The cold set is now scoped to a single
  top-level tour generation.

  Scoping is done with a contextvars.ContextVar holding the active tour's cold
  set. generate_tour_text() calls begin_tour_scope() at entry, installing a fresh
  set for that tour. Concurrency: the container may generate two tours at once;
  because the active set lives in a ContextVar, two concurrent tours each see
  their own set and a cold mark in one never leaks into the other. Worker threads
  spawned inside a tour do NOT inherit context vars automatically, so the
  per-stop/per-resolver thread pools capture the current context
  (copy_tour_context()) and run each task inside it, so a cold mark made in a
  worker thread is visible to the rest of that tour.

  When no tour scope is active (e.g. direct unit-test calls, or a caller that
  never enters a tour) the API transparently falls back to a module-level default
  set, so mark/is/get/reset behave exactly as before for those callers.

Content fallback chain (for fetches whose output becomes tour content):
  1. Institution's own site (tier1)
  2. POP/Joconde (tier2, French holdings)
  3. Wayback (web.archive.org) — different host, unaffected by Wikimedia 429
  4. SERP snippet (tier ~0.83/5, LAST not first, needs corroboration)
  5. Give up (absent, never fabricated)

For lookups whose only output is a tier/identity decision (e.g. _check_wikidata_p856):
  Take the existing failure value immediately (tier3). There is no substitute site.
"""
import concurrent.futures
import contextvars
import threading
import time
from typing import FrozenSet, Optional, Set
from urllib.parse import urlparse


# --- Wikimedia bucket rule ---
# These hosts share one per-IP rate-limit bucket. A 429 on any one means
# all are cold. Do NOT fail over between them.
WIKIMEDIA_HOSTS: FrozenSet[str] = frozenset({
    'en.wikipedia.org',
    'fr.wikipedia.org',
    'de.wikipedia.org',
    'es.wikipedia.org',
    'it.wikipedia.org',
    'pt.wikipedia.org',
    'ja.wikipedia.org',
    'zh.wikipedia.org',
    'ru.wikipedia.org',
    'query.wikidata.org',
    'www.wikidata.org',
    'wikidata.org',
    # REST API endpoints (same bucket)
    'en.wikipedia.org/api/rest_v1',
    'fr.wikipedia.org/api/rest_v1',
})

# Canonical name for the Wikimedia group
_WIKIMEDIA_GROUP = 'wikimedia'

# --- Cold-set state ---
# LOCAL-572: the cold set is scoped to one tour. The active set lives in a
# ContextVar so concurrent tours (and their worker threads, which copy the
# context) each see their own set. When no tour scope is active, callers fall
# back to the module-level default set below — this preserves the original
# process-level behaviour for direct unit-test calls and any caller that never
# enters a tour scope.
# The module-level default set is a dict host -> monotonic mark time so that
# entries can EXPIRE. This is the LOCAL-572 r2 safety net: any pool reachable
# from a tour that was somehow not converted to tour_executor/tour_thread falls
# back to this default set, and without expiry a single stray 429 recorded here
# would again poison the whole long-lived process. Entries older than
# _DEFAULT_COLD_TTL_SECONDS are treated as expired (purged on next read/write).
#
# IMPORTANT: both the module-level default set and the per-tour cold set now
# expire entries. The default set uses a 15-minute TTL (below); the per-tour set
# uses a short cool-down (_TOUR_COLD_COOLDOWN_SECONDS). [LOCAL-637] revised
# Michael's "cold for the rest of the tour" rule to a short COOL-DOWN after Bench
# R6 showed one Wikidata 429 permanently disabling Wikidata for the rest of a tour
# and discarding an already-resolved famous museum on a rate limit. See the
# _TOUR_COLD_COOLDOWN_SECONDS block for the full rationale.
_DEFAULT_COLD_TTL_SECONDS: float = 15 * 60  # 15 minutes
_default_cold_hosts: "dict[str, float]" = {}
_cold_lock = threading.RLock()

# [LOCAL-637] Per-tour cold cool-down.
#
# Michael's original rule (LOCAL-445-C) was "the FIRST 429/timeout keeps the host
# cold for the rest of the tour, never retry". Bench R6 showed the failure mode of
# a permanent-within-tour cold mark: six tours ran at once, one Wikidata 429 landed
# on the National Gallery's city-validation search, and because the mark never
# expired every later Wikidata call in that tour short-circuited to None. A famous,
# already-resolved museum (Q180788, 389 works) was then discarded on a RATE LIMIT.
#
# The cold mark is now a short COOL-DOWN, not a tour-long death sentence: a cold
# host is retried once the cool-down elapses. The cool-down still protects the
# shared Wikimedia rate-limit bucket (we stop hammering a 429ing host for a beat)
# but a single transient 429 can no longer sink the rest of the tour. This is the
# tour-scope analogue of the module-level TTL that already existed for the default
# set. Combined with the request-level 429/5xx retry+backoff in venue_resolver /
# story_miner (which only marks cold AFTER retries are exhausted), one 429 costs a
# bounded pause, never a run-wide failure.
_TOUR_COLD_COOLDOWN_SECONDS: float = 20.0

# Holds the active tour's cold set, or None when no tour scope is active. The set
# is a timestamped dict (host -> monotonic mark time) so a cold mark can expire
# after _TOUR_COLD_COOLDOWN_SECONDS and the host is retried. It is a shared mutable
# object re-bound into worker threads by run_in_tour_context(), so a cold mark made
# in one worker is still visible tour-wide (LOCAL-572 concurrency isolation holds).
_tour_cold_hosts: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar(
    'dead_host_breaker_tour_cold_hosts', default=None
)


def _purge_expired_tour_locked(cold: dict) -> None:
    """Drop cold marks older than the tour cool-down. Caller holds the lock."""
    if not cold:
        return
    cutoff = _now() - _TOUR_COLD_COOLDOWN_SECONDS
    for h in [h for h, t in cold.items() if t < cutoff]:
        del cold[h]


def _now() -> float:
    """Monotonic clock for TTL math (immune to wall-clock jumps)."""
    return time.monotonic()


def _purge_expired_default_locked() -> None:
    """Drop expired entries from the module-level default set. Caller holds lock.

    No-op semantics for tour sets: this only ever touches _default_cold_hosts.
    """
    if not _default_cold_hosts:
        return
    cutoff = _now() - _DEFAULT_COLD_TTL_SECONDS
    expired = [h for h, t in _default_cold_hosts.items() if t < cutoff]
    for h in expired:
        del _default_cold_hosts[h]


def _active_cold_set():
    """Return the cold set in effect for the current context.

    Inside a tour scope (begin_tour_scope / tour_scope), this is that tour's
    private timestamped dict (host -> monotonic mark time). Otherwise it is the
    module-level default dict (host -> mark time). Returning either is fine
    because the public API functions branch on whether a tour scope is active
    before touching it.
    """
    s = _tour_cold_hosts.get()
    if s is None:
        return _default_cold_hosts
    return s


def _in_tour_scope() -> bool:
    """True when a per-tour cold set is installed in the current context."""
    return _tour_cold_hosts.get() is not None


def extract_host(url: str) -> str:
    """Normalise a URL or hostname to its registrable host.

    Returns lowercase hostname. For Wikimedia hosts, returns the canonical
    group name 'wikimedia'.
    """
    if not url:
        return ''

    # If it looks like a bare hostname (no scheme), add one for parsing
    if '://' not in url:
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower().strip('.')
    except Exception:
        # Fallback: crude extraction
        host = url.lower().split('://')[1].split('/')[0].split(':')[0] if '://' in url else url.lower()

    # Wikimedia bucket rule: any Wikimedia host maps to the group
    if _is_wikimedia_host(host):
        return _WIKIMEDIA_GROUP

    return host


def _is_wikimedia_host(host: str) -> bool:
    """Check if a hostname belongs to the Wikimedia rate-limit bucket."""
    if host in WIKIMEDIA_HOSTS:
        return True
    # Catch any *.wikipedia.org or *.wikidata.org
    if host.endswith('.wikipedia.org') or host.endswith('.wikidata.org'):
        return True
    if host == 'wikipedia.org' or host == 'wikidata.org':
        return True
    return False


def mark_host_cold(host_or_url: str, reason: str = '') -> str:
    """Record that a host has failed (first timeout or 429). Thread-safe.

    Args:
        host_or_url: URL or hostname that failed
        reason: optional reason string for diagnostics

    Returns:
        The normalised host key that was marked cold.
    """
    host = extract_host(host_or_url)
    if not host:
        return ''

    with _cold_lock:
        if _in_tour_scope():
            # Tour set: timestamped dict with a short cool-down ([LOCAL-637]).
            cold = _active_cold_set()
            _purge_expired_tour_locked(cold)
            is_new = host not in cold
            cold[host] = _now()
        else:
            # Module-level default set: timestamped dict with 15-min TTL.
            _purge_expired_default_locked()
            is_new = host not in _default_cold_hosts
            _default_cold_hosts[host] = _now()
        if is_new:
            print(f"  [DEAD-HOST] Marked cold: {host}"
                  f"{f' ({reason})' if reason else ''}")

    return host


def is_host_cold(host_or_url: str) -> bool:
    """Check whether a host is cold (has failed this run). Thread-safe.

    Call this BEFORE making any network request. If True, short-circuit
    immediately with the appropriate failure value.
    """
    host = extract_host(host_or_url)
    if not host:
        return False

    with _cold_lock:
        if _in_tour_scope():
            # Tour set: expire stale cool-down marks first, then check.
            cold = _active_cold_set()
            _purge_expired_tour_locked(cold)
            return host in cold
        # Default set: expire stale entries first, then check.
        _purge_expired_default_locked()
        return host in _default_cold_hosts


def get_cold_hosts() -> Set[str]:
    """Return a copy of the current cold-host set (for diagnostics)."""
    with _cold_lock:
        if _in_tour_scope():
            cold = _active_cold_set()
            _purge_expired_tour_locked(cold)
            return set(cold)
        _purge_expired_default_locked()
        return set(_default_cold_hosts.keys())


def reset_cold_hosts() -> None:
    """Clear the cold hosts in effect for the current context.

    Inside a tour scope this clears only that tour's set; otherwise it clears
    the module-level default set. Used by test teardown and begin_tour_scope().
    """
    with _cold_lock:
        _active_cold_set().clear()


# --- LOCAL-572: per-tour scoping ---

def begin_tour_scope() -> "contextvars.Token":
    """Start a fresh cold-host scope for one top-level tour generation.

    Installs a new, empty cold set in the active context and returns the
    ContextVar token. Callers at the top-level tour entry (generate_tour_text)
    call this so a 429 in a previous tour served by the same long-lived process
    does not disable hosts for this tour. Concurrent tours each get their own
    set because the set lives in a ContextVar.

    The returned token may be passed to end_tour_scope() for symmetric cleanup,
    but is optional: when the tour's call stack unwinds the context var simply
    goes out of scope.
    """
    return _tour_cold_hosts.set({})


def end_tour_scope(token: "contextvars.Token") -> None:
    """Restore the cold-host scope that was active before begin_tour_scope().

    Optional symmetric cleanup for begin_tour_scope(). Safe to skip when the
    tour runs in its own call stack.
    """
    try:
        _tour_cold_hosts.reset(token)
    except (ValueError, LookupError):
        # Token belongs to a different context (e.g. set in another thread);
        # nothing to restore here.
        pass


class tour_scope:
    """Context manager form of begin_tour_scope()/end_tour_scope().

    Usage:
        with tour_scope():
            ... generate one tour ...
    """

    def __enter__(self) -> "tour_scope":
        self._token = begin_tour_scope()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        end_tour_scope(self._token)
        return False


def copy_tour_context() -> Optional[dict]:
    """Capture the active tour's cold set for propagation to worker threads.

    Worker threads and ThreadPoolExecutor workers do NOT inherit context vars
    automatically. A thread pool created inside a tour captures the active cold
    set here and re-binds it in each worker (run_in_tour_context) so that cold
    marks made in a worker thread land in — and are visible to — the active
    tour's set rather than the module-level default.

    Returns the active tour's cold set object, or None when no tour scope is
    active (in which case workers fall back to the module-level default set,
    preserving the pre-LOCAL-572 behaviour). The returned object is the shared,
    lock-guarded set itself: binding the same object in every worker is what
    makes a mark in one worker visible tour-wide.
    """
    return _tour_cold_hosts.get()


def run_in_tour_context(cold_set: Optional[dict], fn, *args, **kwargs):
    """Run fn(*args, **kwargs) with the captured tour cold set re-bound.

    Helper for thread-pool submissions:
        snap = copy_tour_context()
        executor.submit(run_in_tour_context, snap, worker, arg)

    Each worker thread binds the ContextVar to the SAME shared set object the
    tour is using, so marks made here are visible to the rest of the tour. When
    cold_set is None (no tour scope active) the worker leaves the ContextVar at
    its default and uses the module-level set, exactly as before LOCAL-572.

    Unlike sharing a single contextvars.Context (which cannot be entered by more
    than one thread at a time), re-binding the ContextVar per worker is safe for
    an arbitrary number of concurrent workers.
    """
    if cold_set is None:
        return fn(*args, **kwargs)
    token = _tour_cold_hosts.set(cold_set)
    try:
        return fn(*args, **kwargs)
    finally:
        _tour_cold_hosts.reset(token)


# --- LOCAL-572 r2: one helper used on the entire tour path ---
#
# r1 propagated the context by hand at three fan-out points. r2 makes that the
# default for EVERY pool/thread reachable from generate_tour_text(): any worker
# that does not copy the context falls back to the process-level default set,
# which is exactly the leak this task removes. These two helpers capture the
# active tour's cold set at construction time and re-bind it inside every
# worker, so a cold mark made off-thread lands in — and is visible to — the
# current tour's set.


class TourExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor whose submit()/map() run each callable inside the
    active tour's dead-host cold-set context.

    Drop-in replacement for ThreadPoolExecutor on the tour path:

        with tour_executor(max_workers=5) as ex:
            futs = [ex.submit(worker, item) for item in items]

    The active tour's cold set is captured ONCE, when the executor is created
    (which happens on the tour's own thread, inside the tour scope). Every task
    submitted afterwards — regardless of which thread calls submit() — re-binds
    that captured set in the worker, so a 429 marked by any worker stays cold
    for the rest of this tour and never touches the module-level default set.

    When no tour scope is active at construction time (captured context is
    None), submit()/map() behave exactly like a plain ThreadPoolExecutor and
    callables fall through to the module-level default set — preserving
    pre-LOCAL-572 behaviour for callers that never enter a tour.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Capture at construction: the constructor runs on the tour thread.
        self._dhb_cold_set = copy_tour_context()

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(
            run_in_tour_context, self._dhb_cold_set, fn, *args, **kwargs
        )

    def map(self, fn, *iterables, timeout=None, chunksize=1):
        def _wrapped(*call_args):
            return run_in_tour_context(self._dhb_cold_set, fn, *call_args)
        return super().map(_wrapped, *iterables, timeout=timeout, chunksize=chunksize)


def tour_executor(max_workers=None, **kwargs) -> "TourExecutor":
    """Create a TourExecutor (see class docstring).

    Preferred over `ThreadPoolExecutor(...)` for any pool reachable from
    `generate_tour_text()`. Accepts the same keyword arguments as
    ThreadPoolExecutor (max_workers, thread_name_prefix, …).
    """
    return TourExecutor(max_workers=max_workers, **kwargs)


def tour_thread(target=None, args=(), kwargs=None, **thread_kwargs) -> "threading.Thread":
    """threading.Thread whose target runs inside the active tour's cold-set
    context.

    Drop-in replacement for `threading.Thread(target=..., args=..., ...)` on the
    tour path. The active tour's cold set is captured now (on the calling
    thread, inside the tour scope) and re-bound inside the new thread, so a cold
    mark made by the thread lands in this tour's set.

    When no tour scope is active, the target runs with the module-level default
    set, exactly like a plain threading.Thread.
    """
    cold_set = copy_tour_context()
    kwargs = kwargs or {}

    if target is None:
        # No target: nothing to wrap; behave like a bare Thread.
        return threading.Thread(args=args, kwargs=kwargs, **thread_kwargs)

    def _run():
        return run_in_tour_context(cold_set, target, *args, **kwargs)

    return threading.Thread(target=_run, **thread_kwargs)

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
import contextvars
import threading
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
_default_cold_hosts: Set[str] = set()
_cold_lock = threading.RLock()

# Holds the active tour's cold set, or None when no tour scope is active.
_tour_cold_hosts: "contextvars.ContextVar[Optional[Set[str]]]" = contextvars.ContextVar(
    'dead_host_breaker_tour_cold_hosts', default=None
)


def _active_cold_set() -> Set[str]:
    """Return the cold set in effect for the current context.

    Inside a tour scope (begin_tour_scope / tour_scope), this is that tour's
    private set. Otherwise it is the module-level default set.
    """
    s = _tour_cold_hosts.get()
    if s is None:
        return _default_cold_hosts
    return s


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
        cold = _active_cold_set()
        if host not in cold:
            cold.add(host)
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
        return host in _active_cold_set()


def get_cold_hosts() -> Set[str]:
    """Return a copy of the current cold-host set (for diagnostics)."""
    with _cold_lock:
        return set(_active_cold_set())


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
    return _tour_cold_hosts.set(set())


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


def copy_tour_context() -> Optional[Set[str]]:
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


def run_in_tour_context(cold_set: Optional[Set[str]], fn, *args, **kwargs):
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

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

Content fallback chain (for fetches whose output becomes tour content):
  1. Institution's own site (tier1)
  2. POP/Joconde (tier2, French holdings)
  3. Wayback (web.archive.org) — different host, unaffected by Wikimedia 429
  4. SERP snippet (tier ~0.83/5, LAST not first, needs corroboration)
  5. Give up (absent, never fabricated)

For lookups whose only output is a tier/identity decision (e.g. _check_wikidata_p856):
  Take the existing failure value immediately (tier3). There is no substitute site.
"""
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

# --- Module-scope state (process-level, persists for the run) ---
_cold_hosts: Set[str] = set()
_cold_lock = threading.Lock()


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
        if host not in _cold_hosts:
            _cold_hosts.add(host)
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
        return host in _cold_hosts


def get_cold_hosts() -> Set[str]:
    """Return a copy of the current cold-host set (for diagnostics)."""
    with _cold_lock:
        return set(_cold_hosts)


def reset_cold_hosts() -> None:
    """Clear all cold hosts. For test teardown ONLY."""
    with _cold_lock:
        _cold_hosts.clear()

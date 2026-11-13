#!/usr/bin/env python3
"""wiki_client.py — LOCAL-907B: a polite Wikipedia API client.

Wikipedia API etiquette, in one place:
  * a descriptive User-Agent with a contact address;
  * requests run SERIALLY, at least ``min_interval`` (200 ms) apart;
  * ``maxlag=5`` on every call (the servers tell us when they are busy);
  * on 429 / 503 (or a ``maxlag`` error body) back off — honour ``Retry-After``, else
    2 / 4 / 8 / 16 s — and give up after 5 tries with WikiFetchError. Callers log and SKIP
    that page; nothing here crashes a plan.

Standard library + requests (imported lazily). The HTTP function and the clock are
injectable, so the tests run offline and instantly.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

USER_AGENT = "AudiouraTopicLibrary/1.0 (contact: audiotoursai@gmail.com)"
MIN_INTERVAL_S = 0.2
MAX_TRIES = 5
BACKOFF_S = (2, 4, 8, 16)
MAXLAG = 5
MAX_TITLES_PER_QUERY = 50
RETRY_STATUSES = (429, 503)

log = logging.getLogger("topic_library")


class WikiFetchError(RuntimeError):
    """A Wikipedia request failed even after the retries (callers skip the page)."""


def _default_getter(url: str, params: Dict[str, Any], headers: Dict[str, str], timeout: int):
    import requests
    return requests.get(url, params=params, headers=headers, timeout=timeout)


def _retry_after(resp: Any) -> Optional[float]:
    try:
        v = (getattr(resp, "headers", None) or {}).get("Retry-After")
        return float(v) if v is not None and float(v) >= 0 else None
    except (TypeError, ValueError):
        return None


class WikiClient:
    def __init__(self, user_agent: str = USER_AGENT, *, min_interval: float = MIN_INTERVAL_S,
                 max_tries: int = MAX_TRIES, backoff: tuple = BACKOFF_S,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 getter: Optional[Callable] = None, timeout: int = 30):
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.max_tries = max_tries
        self.backoff = backoff
        self._sleep = sleep
        self._clock = clock
        self._getter = getter or _default_getter
        self.timeout = timeout
        self._last = None            # clock time the last request started
        self._lock = threading.Lock()
        self.requests_made = 0

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _backoff(self, attempt: int) -> float:
        return float(self.backoff[min(attempt, len(self.backoff) - 1)])

    def get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """GET ``url`` and return the decoded JSON. Raises WikiFetchError after the retries."""
        p = dict(params)
        p.setdefault("maxlag", MAXLAG)
        p.setdefault("format", "json")
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip"}
        last_err = "no attempt"
        with self._lock:                                   # serial, always
            for attempt in range(self.max_tries):
                self._throttle()
                self.requests_made += 1
                wait: Optional[float] = None
                try:
                    resp = self._getter(url, p, headers, self.timeout)
                except Exception as e:                      # network error: retry too
                    last_err = f"{e.__class__.__name__}: {e}"
                    resp = None
                    wait = self._backoff(attempt)
                if resp is not None:
                    status = getattr(resp, "status_code", 200)
                    if status in RETRY_STATUSES:
                        last_err = f"HTTP {status}"
                        ra = _retry_after(resp)
                        wait = ra if ra is not None else self._backoff(attempt)
                    elif status >= 400:
                        raise WikiFetchError(f"HTTP {status} for {url}")
                    else:
                        try:
                            data = resp.json()
                        except ValueError as e:
                            raise WikiFetchError(f"bad JSON from {url}: {e}")
                        err = data.get("error") if isinstance(data, dict) else None
                        if err and err.get("code") == "maxlag":
                            last_err = "maxlag"
                            ra = _retry_after(resp)
                            wait = ra if ra is not None else self._backoff(attempt)
                        elif err:
                            raise WikiFetchError(f"API error {err.get('code')}: {err.get('info')}")
                        else:
                            return data
                if attempt + 1 >= self.max_tries:
                    break
                log.info("[LOCAL-907B] wikipedia %s; backing off %.1fs (try %d/%d)",
                         last_err, wait or 0, attempt + 1, self.max_tries)
                self._sleep(wait or 0)
        raise WikiFetchError(f"giving up after {self.max_tries} tries ({last_err}): {url}")


_default: Optional[WikiClient] = None


def default_client() -> WikiClient:
    global _default
    if _default is None:
        _default = WikiClient()
    return _default


def chunks(items: List[Any], n: int = MAX_TITLES_PER_QUERY):
    for i in range(0, len(items), n):
        yield items[i:i + n]

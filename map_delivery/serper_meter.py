"""serper_meter.py — the ONE metered door for every google.serper.dev call.

LOCAL-707.
==========
WHY THIS EXISTS
---------------
The paid-API network meter (`_meter/paid_api_meter.py`) patches requests / urllib
/ httpx / aiohttp so every call to a paid host writes a `paid_api_calls` row.
That worked for Serper from Oct 7 until Oct 12 (~5,000 rows). On **Oct 13** the
LOCAL-678 change added httpx/aiohttp patching to close the OpenAI/Gemini SDK
blind spot — and from that moment Serper rows STOPPED, while the httpx-based
OpenAI and Gemini rows kept being written every day. Serper is still used daily
(artist-life research, serper_plus walking research, the news endpoint), so the
meter was blind to it: a real problem because Michael estimates the prepaid
Serper balance from the ledger (D: no auto-recharge).

WHAT THIS GUARANTEES
--------------------
`serper_post()` makes the request AND writes exactly one `paid_api_calls` row for
it **directly** — via `paid_api_meter.record_call()` — so a row exists even in a
process/container where the network patch failed to install or was shadowed.
A thread-local marker (`_mark_explicit`/`_clear_explicit`) tells the network
wrapper "I already recorded this one", so when the patch IS live we still write
exactly ONE row, never two.

This is the belt (explicit) AND the suspenders (network patch, now hardened):
whichever is working, the call is metered exactly once; if both are working, it
is still metered exactly once.

FAIL-OPEN
---------
Metering must never break a tour. Every meter step is wrapped; a meter failure
leaves the real HTTP request untouched. If the meter module cannot be imported
at all, the request still goes out (just unmetered — same as before this fix).

USAGE
-----
    from serper_meter import serper_post
    status, body = serper_post(
        "https://google.serper.dev/search",
        {"q": query, "num": 8}, api_key=SERP_API_KEY)
    results = json.loads(body) if status == 200 else {}

`body` is the raw response bytes (or b"" on failure); `status` is the HTTP status
(0 on a transport error). Callers parse the JSON exactly as they did around their
old `urllib.request.urlopen(...)` call.
"""
import json
import os
import sys
import urllib.error
import urllib.request

SERPER_HOSTS = ("google.serper.dev", "serper.dev")
DEFAULT_TIMEOUT = 15


def _meter():
    """Import the network meter module (paid_api_meter) however it is reachable:
    containers put it on /opt/meter (PYTHONPATH); host callers have _meter/ next
    to this file. Returns the module or None — None means "unmetered, still send"
    (fail-open). Never raises."""
    try:
        import paid_api_meter as m  # /opt/meter on PYTHONPATH (containers)
        return m
    except Exception:
        pass
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        meter_dir = os.path.join(here, "_meter")
        if meter_dir not in sys.path:
            sys.path.insert(0, meter_dir)
        import paid_api_meter as m
        return m
    except Exception:
        return None


def is_serper_url(url):
    u = url or ""
    return any(h in u for h in SERPER_HOSTS)


def serper_post(url, payload, api_key=None, timeout=DEFAULT_TIMEOUT,
                extra_headers=None):
    """POST a JSON ``payload`` to a Serper endpoint and GUARANTEE one metered
    `paid_api_calls` row for the request.

    Args:
        url: a google.serper.dev endpoint (…/search, …/news, …).
        payload: dict, JSON-encoded as the request body.
        api_key: the Serper key. Defaults to SERP_API_KEY / SERPER_API_KEY env.
        timeout: socket timeout in seconds.
        extra_headers: optional dict merged over the default headers.

    Returns:
        (status, body_bytes). status is the HTTP status code, or 0 on a transport
        error. body_bytes is the raw response body (b"" on failure). The caller
        parses JSON itself, exactly as before.

    Metering: a row is written via record_call() with kind="serper" and
    $0.001 on a 200 (SERPER_PER_QUERY), $0 otherwise — the same costing the
    network meter applies. Fail-open: a meter error never affects the request.
    """
    key = api_key or os.environ.get("SERP_API_KEY") or os.environ.get("SERPER_API_KEY")
    headers = {"X-API-KEY": key or "", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    m = _meter()
    mark = None
    # Enforce the daily paid-API limit before sending, exactly like the network
    # wrappers do (fail-open inside check_daily_limit). Then mark this request as
    # explicitly metered so the network wrapper won't record it a second time.
    if m is not None:
        try:
            if hasattr(m, "check_daily_limit"):
                m.check_daily_limit()
        except getattr(m, "DailyPaidLimitExceeded", ()):  # propagate the stop
            raise
        except Exception:
            pass
        try:
            mark = m._mark_explicit(url)
        except Exception:
            mark = None

    status, body = 0, b""
    meter_body = b""  # what we hand the meter (real server body only, never the
                      # synthetic error text below)
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            meter_body = body
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as e:
        status = getattr(e, "code", 0) or 0
        try:
            body = e.read()
            meter_body = body
        except Exception:
            body = b""
    except Exception as e:
        # Transport error (timeout, DNS, connection refused). status stays 0 so
        # the meter prices it at $0. Surface the reason in the RETURNED body so a
        # caller can log WHY it failed (preserves the LOCAL-409 diagnostic), but
        # keep meter_body empty so the ledger row is a clean status-0 record.
        status = 0
        try:
            body = ("%s: %s" % (type(e).__name__, e)).encode("utf-8", "replace")
        except Exception:
            body = b""
    finally:
        # GUARANTEE the row — directly, independent of the network patch.
        if m is not None:
            try:
                m.record_call(url, status, meter_body, payload)
            except Exception:
                pass
            try:
                if mark is not None:
                    m._clear_explicit(mark)
            except Exception:
                pass

    return status, body


def serper_search(query, num=8, api_key=None, timeout=DEFAULT_TIMEOUT,
                  endpoint="https://google.serper.dev/search", **payload_extra):
    """Convenience wrapper for the common organic-search call. Returns the parsed
    JSON dict ({} on failure). Metered exactly once via serper_post()."""
    payload = {"q": query, "num": num}
    payload.update(payload_extra)
    status, body = serper_post(endpoint, payload, api_key=api_key, timeout=timeout)
    if status == 200 and body:
        try:
            return json.loads(body.decode("utf-8", "ignore"))
        except Exception:
            return {}
    return {}

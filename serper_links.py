"""serper_links.py — resolve Google ``google.com/goto`` redirect links in a
Serper search response, before anything in the pipeline opens or judges them.

LOCAL-849.
==========
WHY THIS EXISTS
---------------
Serper support (2026-10-30): since ~01:30 UTC on Oct 30, Google only exposes the
real destination for the FIRST FEW organic results. Everything after the top 3
now comes back as ``https://www.google.com/goto?url=CAES…`` — a Google host with
an OPAQUE reference in ``url=`` that CANNOT be decoded locally (confirmed by the
vendor and by scrapingbee / on-page.ai / the automdev google-goto-url-fix repo:
the destination lives only in the HTTP Location header). We already see such
links as sources in LOCAL-828/828B logs.

A goto link that reaches the pipeline is actively harmful:
  * FETCH   — ``_fetch(url)`` opens the opaque Google redirect, not the page.
  * JUDGE   — ``normalize_domain`` reads the host as ``google.com``; the source
              tier gate (work_story_searcher.classify_domain) then judges
              *google.com*, not the real publisher.
  * STORE   — the sources list cites ``google.com/goto?url=…``.
  * DEDUPE  — a set keyed on the URL dedupes on the goto string, not the target,
              so the same page behind two goto links counts twice.

WHAT THIS DOES
--------------
``resolve_links(search_json, ...)`` returns a COPY of the Serper response whose
result links (``organic`` / ``news`` / ``places``) are REAL destination URLs
wherever we could recover them:

  1. KEEP the top-3 organic links untouched — Serper already resolves them, they
     are never goto links, and a caller that only needs the top 3 pays nothing
     and waits for nothing (``need_beyond_top3=False`` stops here).
  2. LOCAL DECODE (free, instant): a few goto variants carry a plain
     ``url=https://realsite/…`` target in the query string — decode those with no
     network call. The CAES-style ``url=`` is opaque and is NOT decodable; it
     falls through to step 3.
  3. BATCH /resolve ONCE per search: collect every still-unresolved goto link and
     POST the search response to Serper's free ``/resolve`` endpoint (0 credits),
     with a bounded timeout, through the guaranteed-metered Serper door
     (``serper_meter.serper_post``) so the call is logged (kind=serper, $0) and
     obeys the budget/limit gates. The result is CACHED by query, so a repeated
     search in the same process resolves instantly.
  4. A link STILL unresolved is marked ``_unresolved_goto = True`` on the result
     dict and its ``link`` is left as-is. Callers treat an unresolved goto as an
     UNKNOWN host: never a domain to judge, never a page to fetch. The helper
     ``is_resolved(result)`` / ``usable_link(result)`` make that one check.

FAIL-OPEN: resolution must never break a tour. Any error (no key, /resolve down,
timeout, malformed response) leaves the goto links in place, marked unresolved —
exactly the safe "unknown host" state. The helper never raises.

NOTHING changes for a response with no goto links: ``resolve_links`` returns it
(copied) with every link untouched and zero network calls.
"""
import copy
import os
import threading
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

# Which organic ranks Google still resolves itself. Serper support: "the top 3".
TOP_N_ALREADY_RESOLVED = int(os.environ.get("SERPER_GOTO_TOP_N", "3"))
# Bounded wall-time for one /resolve batch. The vendor says it "takes about 30
# seconds"; we cap it a little above that so a real /resolve can complete, while a
# hung call can never block a tour beyond this. A caller beyond the top 3 waits at
# most this long, once per search.
RESOLVE_TIMEOUT = float(os.environ.get("SERPER_RESOLVE_TIMEOUT", "32"))
RESOLVE_ENDPOINT = os.environ.get(
    "SERPER_RESOLVE_ENDPOINT", "https://google.serper.dev/resolve")

# [LOCAL-849] Default policy for resolving goto links BEYOND the top 3. The
# /resolve round-trip is ~25-30 s, and a tour issues many searches, so blocking
# every search on it would add many minutes. By DEFAULT we take the no-wait fast
# path (keep the top 3, decode plain url= targets for free, DROP opaque post-top-3
# goto links as unknown) — the top results are the highest quality and the live
# proof delivers full tours this way. Set SERPER_RESOLVE_BEYOND_TOP3=1 to opt in
# to paying one bounded /resolve per search to recover the deeper links.
_RESOLVE_BEYOND_TOP3_DEFAULT = (
    os.environ.get("SERPER_RESOLVE_BEYOND_TOP3", "0").strip().lower()
    in ("1", "true", "yes", "on"))

# The result-list keys a Serper response can carry links under.
_LINK_LISTS = ("organic", "news", "places", "topStories", "images", "videos")

# Per-process cache: query -> {goto_url: resolved_url}. A resolved goto link does
# not change within a run, and the same stop is often searched more than once.
_resolve_cache: Dict[str, Dict[str, str]] = {}
_cache_lock = threading.Lock()

# [LOCAL-849] Process-level telemetry for the live-run report. Counts across all
# resolve_links calls in this process: goto links seen, how many were recovered
# (locally or via /resolve) vs left unresolved, how many /resolve batches were
# issued, and the total seconds spent waiting on /resolve. Never affects behaviour.
_METRICS = {
    "searches_with_goto": 0,   # searches that carried >=1 goto link
    "goto_seen": 0,            # total goto links observed (post top-3)
    "resolved_local": 0,       # recovered by free local decode
    "resolved_api": 0,         # recovered via the /resolve batch
    "unresolved": 0,           # left unknown (never fetched/judged)
    "resolve_calls": 0,        # /resolve batches actually issued
    "resolve_seconds": 0.0,    # wall-time spent in /resolve
}
_metrics_lock = threading.Lock()


def get_metrics() -> Dict:
    """A snapshot of the process-level goto telemetry (for live-run reporting)."""
    with _metrics_lock:
        return dict(_METRICS)


def reset_metrics() -> None:
    with _metrics_lock:
        for k in _METRICS:
            _METRICS[k] = 0 if k != "resolve_seconds" else 0.0


def _bump(key: str, n=1) -> None:
    try:
        with _metrics_lock:
            _METRICS[key] += n
    except Exception:
        pass


# ─── goto detection + local decode ────────────────────────────────────────────

def is_goto_link(url: str) -> bool:
    """True when ``url`` is a Google redirect (``/goto`` / ``/url`` / ``/aclk``)
    whose destination is not the Google host itself. Never raises."""
    if not url:
        return False
    try:
        u = url if "://" in url else "https://" + url
        p = urlparse(u)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not (host == "google.com" or host.endswith(".google.com")
                or host == "google." or host.endswith("google.")):
            return False
        path = p.path or ""
        return path.startswith("/goto") or path.startswith("/url") \
            or path.startswith("/aclk")
    except Exception:
        return False


def local_decode(url: str) -> str:
    """Return the real destination if the goto link carries a plain
    ``url=https://…`` (or ``q=https://…``) target that we can read WITHOUT a
    network call; '' when the target is opaque (the CAES-style ``url=``, which the
    vendor says cannot be decoded) or on any error. Never raises.

    The opaque reference starts with ``CAE`` / ``http`` is absent — we accept a
    target only when it parses as an absolute http(s) URL, so an opaque blob is
    never mistaken for a destination."""
    if not url:
        return ""
    try:
        u = url if "://" in url else "https://" + url
        q = parse_qs(urlparse(u).query or "")
        for key in ("url", "q", "u"):
            raw = (q.get(key) or [""])[0]
            if not raw:
                continue
            cand = unquote(raw)
            cp = urlparse(cand)
            if cp.scheme in ("http", "https") and cp.netloc:
                return cand
        return ""
    except Exception:
        return ""


# ─── per-result helpers callers use after resolve_links ───────────────────────

def _result_link(r: Dict) -> str:
    if not isinstance(r, dict):
        return ""
    return (r.get("link") or r.get("url") or "").strip()


def is_resolved(result: Dict) -> bool:
    """True when this result is safe to open/judge: it is NOT an unresolved goto
    link. An ordinary link, a locally-decoded link, or a /resolve-recovered link
    are all resolved; a goto link we could not recover is not."""
    if not isinstance(result, dict):
        return False
    if result.get("_unresolved_goto"):
        return False
    return not is_goto_link(_result_link(result))


def usable_link(result: Dict) -> str:
    """The real destination link to fetch/judge/cite, or '' when the result is an
    unresolved goto link (UNKNOWN host — never fetch, never judge, never cite)."""
    return _result_link(result) if is_resolved(result) else ""


# ─── the /resolve call (metered, bounded, fail-open) ──────────────────────────

def _parse_resolve_response(body_obj, goto_urls: List[str]) -> Dict[str, str]:
    """Pull a {goto_url: resolved_url} mapping out of a /resolve response.

    The real Serper /resolve contract (probed 2026-10-31): POST ``{"links":[…]}``
    returns ``{"links":[…]}`` with the resolved URLs IN THE SAME ORDER as the
    request; POST a single ``{"url": goto}`` returns ``{"url": resolved}``; POST
    the whole search response returns the search response with links rewritten in
    place. This parser handles all three, plus a flat {goto: resolved} mapping and
    a list of {from,to} pairs, defensively. Only absolute http(s) targets that are
    not themselves goto links are accepted. Never raises -> {} on anything odd."""
    mapping: Dict[str, str] = {}

    def _accept(src: str, dst: str) -> None:
        if not src or not dst or src == dst:
            return
        try:
            cp = urlparse(dst)
            if cp.scheme in ("http", "https") and cp.netloc \
                    and not is_goto_link(dst):
                mapping[src] = dst
        except Exception:
            pass

    try:
        obj = body_obj
        # Shape A: {"links": [resolved...]} — SAME ORDER as goto_urls (primary).
        if isinstance(obj, dict) and isinstance(obj.get("links"), list):
            resolved_list = obj["links"]
            for i, src in enumerate(goto_urls):
                if i < len(resolved_list) and isinstance(resolved_list[i], str):
                    _accept(src, resolved_list[i])
            if mapping:
                return mapping
        # Shape B: single {"url": resolved} for a one-link request.
        if isinstance(obj, dict) and isinstance(obj.get("url"), str) \
                and len(goto_urls) == 1:
            _accept(goto_urls[0], obj["url"])
            if mapping:
                return mapping
        # Shape C: the echoed search response — links rewritten in place, in the
        # same positions. Zip each result list's links back to the request order.
        if isinstance(obj, dict) and any(k in obj for k in _LINK_LISTS):
            flat = []
            for lk in _LINK_LISTS:
                seq = obj.get(lk)
                if isinstance(seq, list):
                    for r in seq:
                        if isinstance(r, dict):
                            flat.append((r.get("link") or r.get("url") or ""))
            # Align by order against goto_urls we asked about.
            for i, src in enumerate(goto_urls):
                if i < len(flat):
                    _accept(src, flat[i])
            if mapping:
                return mapping
        # Shape D: flat dict {goto_url: resolved_url}.
        if isinstance(obj, dict):
            goto_set = set(goto_urls)
            for k, v in obj.items():
                if isinstance(k, str) and isinstance(v, str) and k in goto_set:
                    _accept(k, v)
            if mapping:
                return mapping
        # Shape E: list of pairs.
        if isinstance(obj, list):
            for item in obj:
                if not isinstance(item, dict):
                    continue
                src = (item.get("from") or item.get("goto") or item.get("input")
                       or item.get("original") or "")
                dst = (item.get("to") or item.get("resolved") or item.get("url")
                       or item.get("link") or item.get("destination") or "")
                _accept(src, dst)
    except Exception:
        return {}
    return mapping


def _call_resolve(search_json: Dict, goto_urls: List[str],
                  timeout: float) -> Dict[str, str]:
    """POST the goto links to Serper /resolve and return a
    {goto_url: resolved_url} mapping. FREE (0 credits) but metered (kind=serper,
    $0) through the guaranteed-metered door. Fail-open: '' on no key / error /
    timeout -> {} (every goto stays unresolved = unknown). Never raises.

    Real contract (probed 2026-10-31): ``{"links":[…]}`` -> ``{"links":[…]}`` in
    the same order. We send the links list (leaner and order-stable than echoing
    the whole search response, which the vendor also accepts)."""
    if not goto_urls:
        return {}
    key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPER_API_KEY")
    if not key:
        return {}
    try:
        from serper_meter import serper_post
    except Exception:
        return {}
    payload = {"links": list(goto_urls)}
    try:
        status, raw = serper_post(RESOLVE_ENDPOINT, payload,
                                  api_key=key, timeout=timeout)
    except Exception:
        return {}
    if status != 200 or not raw:
        return {}
    try:
        import json
        body_obj = json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return {}
    return _parse_resolve_response(body_obj, goto_urls)


def _strip_private(search_json: Dict):
    """A copy of the search response without our private ``_unresolved_goto``
    markers, safe to send to the vendor. Never raises -> the input on error."""
    try:
        clean = copy.deepcopy(search_json)
        for lk in _LINK_LISTS:
            seq = clean.get(lk)
            if isinstance(seq, list):
                for r in seq:
                    if isinstance(r, dict):
                        r.pop("_unresolved_goto", None)
        return clean
    except Exception:
        return search_json


# ─── the main entry point ─────────────────────────────────────────────────────

def _collect_goto(search_json: Dict, skip_top_n: int) -> List[Tuple[Dict, str]]:
    """Every (result_dict, goto_url) in the response that still needs resolving.
    The first ``skip_top_n`` ORGANIC results are skipped (Google resolves those);
    news/places/etc. have no such guarantee, so all of theirs are considered."""
    out: List[Tuple[Dict, str]] = []
    for lk in _LINK_LISTS:
        seq = search_json.get(lk)
        if not isinstance(seq, list):
            continue
        skip = skip_top_n if lk == "organic" else 0
        for i, r in enumerate(seq):
            if not isinstance(r, dict):
                continue
            if i < skip:
                continue
            link = _result_link(r)
            if is_goto_link(link):
                out.append((r, link))
    return out


def resolve_links(search_json: Dict, *, query: str = "",
                  need_beyond_top3: Optional[bool] = None,
                  timeout: float = RESOLVE_TIMEOUT,
                  skip_top_n: int = TOP_N_ALREADY_RESOLVED,
                  _resolver=None) -> Dict:
    """Return a COPY of a Serper search response with goto result links resolved
    to their real destinations wherever possible.

    Args:
        search_json: the parsed Serper response (dict with organic/news/…).
        query: the search query, used as the per-process resolve cache key.
        need_beyond_top3: when False, only the top-3 organic results are needed,
            so NO /resolve call is made (plain url= targets are still decoded for
            free) — the fast, no-wait path. When True, one bounded /resolve
            recovers the deeper goto links. When None (default), the process
            policy SERPER_RESOLVE_BEYOND_TOP3 decides (default: False / fast).
        timeout: bounded wall-time for the single /resolve batch.
        skip_top_n: organic ranks Google already resolves (default 3).
        _resolver: test seam — a callable (search_json, goto_urls, timeout) ->
            {goto: resolved}; defaults to the metered /resolve call.

    Each result dict is updated IN THE COPY: a resolved goto link has its
    ``link`` (and ``url`` if present) rewritten to the destination; a goto link
    we could not resolve keeps its link and gains ``_unresolved_goto = True``.
    Use ``is_resolved(result)`` / ``usable_link(result)`` downstream.

    Never raises: on any failure the copy is returned with goto links marked
    unresolved (the safe unknown-host state)."""
    try:
        if not isinstance(search_json, dict):
            return search_json
        out = copy.deepcopy(search_json)
    except Exception:
        return search_json

    if need_beyond_top3 is None:
        need_beyond_top3 = _RESOLVE_BEYOND_TOP3_DEFAULT

    try:
        pending = _collect_goto(out, skip_top_n)
        if not pending:
            return out  # no goto links anywhere — nothing to do, zero calls.

        _bump("searches_with_goto")
        _bump("goto_seen", len(pending))

        # 1. Local decode first (free, instant).
        still: List[Tuple[Dict, str]] = []
        for r, link in pending:
            dest = local_decode(link)
            if dest:
                _apply(r, dest, was_goto=True)
                _bump("resolved_local")
            else:
                still.append((r, link))

        if not still:
            return out

        # A caller that only needs the top 3 never pays to resolve the rest; mark
        # them unresolved (unknown) and stop — no /resolve call.
        if not need_beyond_top3:
            for r, _link in still:
                r["_unresolved_goto"] = True
            _bump("unresolved", len(still))
            return out

        goto_urls = []
        seen = set()
        for _r, link in still:
            if link not in seen:
                seen.add(link)
                goto_urls.append(link)

        # 2. Cache (by query) — a repeated search resolves instantly.
        mapping: Dict[str, str] = {}
        qkey = (query or "").strip()
        if qkey:
            with _cache_lock:
                cached = _resolve_cache.get(qkey)
            if cached:
                mapping = dict(cached)

        # 3. Batch /resolve ONCE for whatever the cache did not already cover.
        missing = [g for g in goto_urls if g not in mapping]
        if missing:
            resolver = _resolver or _call_resolve
            import time as _t
            _t0 = _t.time()
            try:
                fresh = resolver(_strip_private(out), missing, timeout) or {}
            except Exception:
                fresh = {}
            _bump("resolve_calls")
            _bump("resolve_seconds", _t.time() - _t0)
            if fresh:
                mapping.update(fresh)
                if qkey:
                    with _cache_lock:
                        store = _resolve_cache.setdefault(qkey, {})
                        store.update(fresh)

        # 4. Apply; anything still unmapped is unresolved = unknown.
        for r, link in still:
            dest = mapping.get(link)
            if dest:
                _apply(r, dest, was_goto=True)
                _bump("resolved_api")
            else:
                r["_unresolved_goto"] = True
                _bump("unresolved")

        return out
    except Exception:
        # Last-resort fail-open: mark every goto unresolved in the copy.
        try:
            for r, _link in _collect_goto(out, skip_top_n):
                r["_unresolved_goto"] = True
        except Exception:
            pass
        return out


def _apply(result: Dict, dest: str, was_goto: bool = False) -> None:
    """Rewrite a result's link(s) to the resolved destination and clear the
    unresolved marker. When ``was_goto`` the result is tagged
    ``_resolved_from_goto`` so resolve_stats can count it. Never raises."""
    try:
        if "link" in result or "url" not in result:
            result["link"] = dest
        if "url" in result:
            result["url"] = dest
        result.pop("_unresolved_goto", None)
        if was_goto:
            result["_resolved_from_goto"] = True
    except Exception:
        pass


def resolve_stats(search_json: Dict, skip_top_n: int = TOP_N_ALREADY_RESOLVED
                  ) -> Dict[str, int]:
    """Count goto links in a response AFTER resolve_links ran, for live reporting:
    {goto_seen, resolved, unresolved}. goto_seen counts result links that were
    goto links originally — resolved ones no longer look like goto links, so this
    is computed from the ``_unresolved_goto`` marker plus any remaining goto host.
    Call on the RESOLVED copy. Never raises."""
    seen = resolved = unresolved = 0
    try:
        for lk in _LINK_LISTS:
            seq = search_json.get(lk)
            if not isinstance(seq, list):
                continue
            for r in seq:
                if not isinstance(r, dict):
                    continue
                if r.get("_unresolved_goto"):
                    seen += 1
                    unresolved += 1
                elif r.get("_resolved_from_goto"):
                    seen += 1
                    resolved += 1
    except Exception:
        pass
    return {"goto_seen": seen, "resolved": resolved, "unresolved": unresolved}

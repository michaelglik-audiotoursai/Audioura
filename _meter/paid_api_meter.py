"""Network-level meter for paid APIs (LEAD, 2026-10-08, D635).

Imported via sitecustomize (PYTHONPATH=/opt/meter). Patches requests.Session.send
and urllib.request.urlopen so EVERY call to a paid host is logged with its usage,
computed $, and the calling file:line — regardless of which module made it.
Never raises into the caller.
"""
import json, os, sys, time, threading, traceback

LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
SERVICE = os.environ.get("METER_SERVICE", os.path.basename(sys.argv[0]) if sys.argv else "?")
_lock = threading.Lock()
_INSTALLED = False  # guard so install() patches each HTTP client at most once

# $ per 1M tokens. OpenAI: published list prices. Gemini Flash: derived from our own Google
# invoice SKUs of 2026-10-05 (445,098 input tok = $0.33; 154,413 output tok = $0.58).
OPENAI = {  # longest key wins
    "gpt-4.1-nano": (0.10, 0.40, 0.025), "gpt-4.1-mini": (0.40, 1.60, 0.10), "gpt-4.1": (2.00, 8.00, 0.50),
    "gpt-4o-mini": (0.15, 0.60, 0.075), "gpt-4o": (2.50, 10.00, 1.25), "gpt-3.5-turbo": (0.50, 1.50, 0.50),
    "text-embedding-3-small": (0.02, 0.0, 0.02), "text-embedding-3-large": (0.13, 0.0, 0.13),
    "text-embedding-ada-002": (0.10, 0.0, 0.10),
}
GEMINI_IN, GEMINI_OUT, GROUNDING_PER_QUERY, SERPER_PER_QUERY = 0.75, 3.75, 0.014, 0.001
# RATE_TAG names the price card every record was costed with (Michael 2026-10-08: "keep the tag
# on the price we are using"). Bump it whenever any rate below changes; the history of tags and the
# bill reconciliation behind each lives in .continuous_dev/PRICE_CARD.md.
RATE_TAG = "2026-10-10-r5"  # r5: grounded request $0.053 (GCloud SKU report Oct 1-10; search billed per query at $0.014, ~3.8 billed queries per grounded request)
GROUNDED_REQUEST_USD = 0.053  # r5 2026-10-10: GCloud SKU "Generate content search query gemini 3" = $0.014 per billed QUERY (8,324 queries = $116.54, Oct 1-10); Oct 8-9 billed search / grounded requests = $0.053

def _host_kind(url):
    u = url or ""
    if "api.openai.com" in u: return "openai"
    if "generativelanguage.googleapis.com" in u: return "gemini"
    if "serper.dev" in u: return "serper"
    if "polly" in u and "amazonaws.com" in u: return "polly"
    if "translate" in u and "amazonaws.com" in u: return "aws_translate"
    return None

def _caller():
    for fr in reversed(traceback.extract_stack()[:-3]):
        f = fr.filename
        if ("site-packages" in f or "/lib/python" in f or "paid_api_meter" in f
                or "openai_cost_wrapper" in f
                or f.startswith("<")):
            continue
        return f"{os.path.basename(f)}:{fr.lineno}"
    return "?"

def _openai_cost(model, usage):
    key = max((k for k in OPENAI if k in (model or "")), key=len, default=None)
    if not key: return None, None
    i, o, c = OPENAI[key]
    pt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    ct = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    cached = ((usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}) .get("cached_tokens") or 0)
    return ((pt - cached) * i + cached * c + ct * o) / 1e6, key

def _record(url, status, body, req_body=None):
    kind = _host_kind(url)
    if not kind: return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, "status": status, "rate_tag": RATE_TAG,
           "service": SERVICE, "caller": _caller(), "url": (url or "").split("?")[0][-120:],
           "job": os.environ.get("METER_JOB", ""), "usd": None}
    try:
        d = json.loads(body) if isinstance(body, (bytes, str)) and body else {}
    except Exception:
        d = {}
    try:
        if kind == "openai":
            model = d.get("model") or ((req_body or {}).get("model") if isinstance(req_body, dict) else "")
            usage = d.get("usage") or {}
            usd, key = _openai_cost(model, usage)
            rec.update(model=model, usage=usage, usd=usd if status == 200 else 0.0, rate_key=key)
        elif kind == "gemini":
            um = d.get("usageMetadata") or {}
            q = 0
            grounded = False
            for c in d.get("candidates") or []:
                if c.get("groundingMetadata") is not None:
                    grounded = True
                q += len(((c.get("groundingMetadata") or {}).get("webSearchQueries")) or [])
            # toolUsePromptTokenCount = grounding search results injected into the prompt; billed as input (LEAD 2026-10-08)
            pin = (um.get("promptTokenCount") or 0) + (um.get("toolUsePromptTokenCount") or 0)
            pout = (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0)
            # [LEAD 2026-10-08] Calibrated to the real bill: Oct 8 00:30-05:57 EDT Google
            # took $10.25 while per-QUERY pricing metered $2.12 over 349 grounded calls
            # (only 109 reported queries). Google bills per grounded REQUEST: ~$0.028 each
            # implied. Charge whichever is larger until the SKU report pins it exactly.
            # [LEAD 2026-10-08 r2] Clean single-tour window (Courtauld, tour 485): Google took
            # $0.32 while only 3 of 26 search-enabled requests returned groundingMetadata.
            # Google bills every request that ENABLES the search tool. So charge per request
            # whose body carries tools:[{google_search}], at the rate that window implies.
            tool_on = isinstance(req_body, dict) and "google_search" in json.dumps(req_body.get("tools") or [])
            g = GROUNDED_REQUEST_USD if (tool_on or grounded) else 0.0
            usd = (pin * GEMINI_IN + pout * GEMINI_OUT) / 1e6 + g
            rec.update(model=url.split("/models/")[-1].split(":")[0] if "/models/" in url else "",
                       tokens_in=pin, tokens_out=pout, search_queries=q, usd=usd if status == 200 else 0.0)
        elif kind == "serper":
            rec.update(usd=SERPER_PER_QUERY if status == 200 else 0.0)
    except Exception as e:
        rec["meter_error"] = str(e)[:120]
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with _lock, open(LOG, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass
    # Synchronous (3 s connect timeout): a daemon thread is killed when a short-lived
    # script exits, which lost the DB copy for isolated test runs.
    _db_write(rec)


def _db_write(rec):
    """Also persist to the shared DB so isolated test containers (no log mount) are counted."""
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        conn = psycopg2.connect(url, connect_timeout=3) if url else psycopg2.connect(
            host=os.environ.get("DB_HOST", "postgres-2"), dbname=os.environ.get("DB_NAME", "audiotours"),
            user=os.environ.get("DB_USER", "admin"), password=os.environ.get("DB_PASSWORD", "password123"),
            port=os.environ.get("DB_PORT", "5432"), connect_timeout=3)
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO paid_api_calls (kind,status,service,caller,url,model,usd,detail,host) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (rec.get("kind"), rec.get("status"), rec.get("service"), rec.get("caller"),
                         rec.get("url"), rec.get("model"), rec.get("usd"), json.dumps(rec, default=str),
                         os.environ.get("HOSTNAME", "")))
        conn.close()
    except Exception:
        pass

# --------------------------------------------------------------------------- #
# Daily paid-API spend limit (LOCAL-673)
#
# Michael (2026-10-10): "Alerts would not do much if I am not at the desk." A
# STOP is needed, not an email. Before a paid request (OpenAI, Gemini, Serper,
# and the metered boto3 paths — AWS Translate, Polly) the caller/meter checks
# today's America/New_York total of billed (status 200) usd in paid_api_calls.
# If it is >= DAILY_PAID_LIMIT_USD the request is refused by raising
# DailyPaidLimitExceeded WITHOUT sending. The total is read through a 60-second
# cache so the check adds one short DB query per minute, not one per call.
#
# FAIL-OPEN: any error reading the limit or the DB -> allow and log. A meter bug
# must never block a tour. The limit is OFF when DAILY_PAID_LIMIT_USD is unset
# or non-positive.
# --------------------------------------------------------------------------- #
LIMIT_ENV = "DAILY_PAID_LIMIT_USD"
_LIMIT_CACHE_TTL = 60.0  # seconds
ALERTS_PATH = os.environ.get(
    "ALERTS_MD",
    os.path.join(os.path.expanduser("~"), "Audioura", ".continuous_dev", "ALERTS.md"))

# Cache: (expiry_epoch, total_usd, ny_day_str). Guarded by _limit_lock.
_limit_lock = threading.Lock()
_limit_cache = {"expiry": 0.0, "total": 0.0, "day": None}
# Day (YYYY-MM-DD, NY) on which we have already written an alert line.
_alerted_day = None


class DailyPaidLimitExceeded(Exception):
    """Raised instead of sending a paid request once today's billed spend has
    reached DAILY_PAID_LIMIT_USD. Callers already handle API failures, so the
    tour fails cleanly with an honest error rather than producing a half tour."""


def _limit_usd():
    """Configured limit as a float, or None when the limit is off (unset / <= 0 /
    unparseable). Never raises."""
    try:
        raw = os.environ.get(LIMIT_ENV)
        if raw is None or str(raw).strip() == "":
            return None
        val = float(raw)
        return val if val > 0 else None
    except Exception:
        return None


def _ny_now():
    """Current datetime in America/New_York. Falls back to a fixed EST/EDT guess
    only if zoneinfo is unavailable (it ships with Python 3.9+)."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # Last-resort fallback: approximate NY as UTC-4 (EDT). Correctness here
        # only affects the exact day-boundary minute; fail-open philosophy means
        # we would rather err than crash.
        from datetime import timezone, timedelta
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-4)))


def _query_today_total_usd(day_str):
    """Sum of billed (status 200) usd in paid_api_calls for the given NY calendar
    day. Raises on any DB problem so the caller can fail open."""
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(url, connect_timeout=3) if url else psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"), dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"), password=os.environ.get("DB_PASSWORD", "password123"),
        port=os.environ.get("DB_PORT", "5432"), connect_timeout=3)
    try:
        with conn, conn.cursor() as cur:
            # ts is timestamptz; compare its NY calendar date to the NY day we are
            # metering. Doing the AT TIME ZONE conversion in SQL keeps the day
            # boundary correct regardless of the DB session timezone.
            # [LEAD 2026-10-10] DAILY_PAID_LIMIT_SERVICES (comma list of `service` values) scopes
            # the limit to the listener-facing stack. Unscoped, a night of Kiro/bench test spend
            # (their own containers) tripped the shared stack's $8 limit at 23:20.
            svcs = [x.strip() for x in os.environ.get("DAILY_PAID_LIMIT_SERVICES", "").split(",") if x.strip()]
            if svcs:
                cur.execute(
                    "SELECT COALESCE(SUM(usd), 0) FROM paid_api_calls "
                    "WHERE status = 200 "
                    "AND (ts AT TIME ZONE 'America/New_York')::date = %s::date "
                    "AND service = ANY(%s)",
                    (day_str, svcs))
            else:
                cur.execute(
                    "SELECT COALESCE(SUM(usd), 0) FROM paid_api_calls "
                    "WHERE status = 200 "
                    "AND (ts AT TIME ZONE 'America/New_York')::date = %s::date",
                    (day_str,))
            row = cur.fetchone()
        return float(row[0] or 0.0)
    finally:
        try: conn.close()
        except Exception: pass


def _today_total_usd(now=None):
    """Cached today's (NY) billed total. The cache is keyed on the NY day so the
    first call after midnight re-queries even if the 60 s TTL has not expired."""
    now_ts = time.time()
    ny = now or _ny_now()
    day_str = ny.strftime("%Y-%m-%d")
    with _limit_lock:
        if (_limit_cache["day"] == day_str and now_ts < _limit_cache["expiry"]):
            return _limit_cache["total"], day_str
    total = _query_today_total_usd(day_str)  # may raise -> caller fails open
    with _limit_lock:
        _limit_cache["day"] = day_str
        _limit_cache["total"] = total
        _limit_cache["expiry"] = now_ts + _LIMIT_CACHE_TTL
    return total, day_str


def _write_alert_once(limit, day_str, ny):
    """Write '*** DAILY PAID LIMIT $X reached at HH:MM ***' to ALERTS.md at most
    once per NY day. LEAD's loop turns a non-empty ALERTS.md into a push. Never
    raises."""
    global _alerted_day
    with _limit_lock:
        if _alerted_day == day_str:
            return
        _alerted_day = day_str
    try:
        limit_txt = ("%g" % limit)
        line = "*** DAILY PAID LIMIT $%s reached at %s ***\n" % (limit_txt, ny.strftime("%H:%M"))
        os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
        with _lock, open(ALERTS_PATH, "a") as f:
            f.write(line)
    except Exception:
        # Alert failure must not undo the stop; the stop itself is the hard guard.
        pass


def check_daily_limit():
    """Enforce DAILY_PAID_LIMIT_USD before a paid request. Raises
    DailyPaidLimitExceeded when today's (NY) billed total is >= the limit;
    returns None (allow) otherwise. Fails OPEN on any meter/DB error.

    Call this immediately before sending any paid request (it is also invoked by
    the requests/urllib patches for OpenAI/Gemini/Serper)."""
    limit = _limit_usd()
    if limit is None:
        return  # limit off
    try:
        ny = _ny_now()
        total, day_str = _today_total_usd(ny)
    except Exception as e:
        # Fail-open: DB down / query error -> allow and log, never block.
        try:
            sys.stderr.write("[paid_api_meter] daily-limit check failed open: %s\n" % (str(e)[:200],))
        except Exception:
            pass
        return
    if total >= limit:
        _write_alert_once(limit, day_str, ny)
        raise DailyPaidLimitExceeded(
            "DAILY_PAID_LIMIT_USD reached: today's billed paid-API spend "
            "$%.4f >= limit $%g (America/New_York %s). Refusing paid request."
            % (total, limit, day_str))


def install():
    # Idempotent: patching each HTTP client more than once would stack wrappers
    # and record (and limit-check) every paid call N times. sitecustomize and
    # meter_bootstrap can both import+install, so guard against a second pass.
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    try:
        import requests
        _orig = requests.Session.send
        def send(self, request, **kw):
            # Enforce the daily limit BEFORE sending any paid request. The check
            # raises DailyPaidLimitExceeded (caught by callers as an API failure)
            # or fails open; non-paid hosts are never checked.
            if _host_kind(request.url):
                check_daily_limit()
            resp = _orig(self, request, **kw)
            try:
                if _host_kind(request.url):
                    rb = None
                    try: rb = json.loads(request.body) if request.body else None
                    except Exception: pass
                    body = resp.content if not kw.get("stream") else b""
                    _record(request.url, resp.status_code, body, rb)
            except Exception:
                pass
            return resp
        requests.Session.send = send
    except Exception:
        pass
    try:
        import urllib.request as ur
        _orig_open = ur.urlopen
        def urlopen(req, *a, **kw):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if not _host_kind(url):
                return _orig_open(req, *a, **kw)
            # Enforce the daily limit BEFORE sending the paid request.
            check_daily_limit()
            try:
                resp = _orig_open(req, *a, **kw)
            except Exception as e:
                try: _record(url, getattr(e, "code", 0), b"")
                except Exception: pass
                raise
            try:
                data = resp.read()
                import io
                _record(url, getattr(resp, "status", 200), data)
                resp.read = lambda *x: data if not x else data  # replay
                resp.fp = io.BytesIO(data)
            except Exception:
                pass
            return resp
        ur.urlopen = urlopen
    except Exception:
        pass
    # ----------------------------------------------------------------------- #
    # httpx (sync + async)  [LOCAL-678]
    #
    # The OpenAI python SDK (openai>=1) and the Google GenAI SDK send every
    # request through httpx, NOT requests/urllib. client.chat.completions.create
    # -> httpx.Client.send -> api.openai.com. Those calls were invisible to the
    # meter: on Oct 11 ~6.6k OpenAI requests (~$19) went unlogged this way.
    #
    # httpx.Client.send / httpx.AsyncClient.send are the single choke point every
    # request passes through (streaming and non-streaming alike), so patching
    # send() covers all higher-level helpers (.get/.post/.request and the SDKs).
    # When stream=True the body is not read yet (reading .content would raise and
    # would also consume the SDK's stream), so we record with an empty body in
    # that case — exactly as the requests patch does.
    # ----------------------------------------------------------------------- #
    def _httpx_req_body(request):
        try:
            raw = request.content
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def _httpx_resp_body(resp, stream):
        if stream:
            return b""
        try:
            # Non-streaming httpx responses are read eagerly before send() returns,
            # so .content is available and re-readable without consuming anything.
            if getattr(resp, "is_stream_consumed", True) or getattr(resp, "is_closed", True):
                return resp.content
        except Exception:
            pass
        return b""

    try:
        import httpx
        _orig_httpx_send = httpx.Client.send

        def _httpx_send(self, request, *, stream=False, **kw):
            url = str(getattr(request, "url", ""))
            if _host_kind(url):
                check_daily_limit()
            resp = _orig_httpx_send(self, request, stream=stream, **kw)
            try:
                if _host_kind(url):
                    _record(url, resp.status_code,
                            _httpx_resp_body(resp, stream), _httpx_req_body(request))
            except Exception:
                pass
            return resp
        httpx.Client.send = _httpx_send

        _orig_httpx_asend = httpx.AsyncClient.send

        async def _httpx_asend(self, request, *, stream=False, **kw):
            url = str(getattr(request, "url", ""))
            if _host_kind(url):
                check_daily_limit()
            resp = await _orig_httpx_asend(self, request, stream=stream, **kw)
            try:
                if _host_kind(url):
                    _record(url, resp.status_code,
                            _httpx_resp_body(resp, stream), _httpx_req_body(request))
            except Exception:
                pass
            return resp
        httpx.AsyncClient.send = _httpx_asend
    except Exception:
        pass
    # ----------------------------------------------------------------------- #
    # aiohttp  [LOCAL-678]
    #
    # aiohttp.ClientSession._request is the single internal choke point for
    # .get/.post/.request. We read the response body with resp.read() (aiohttp
    # caches it, so a later await resp.json()/read() in the caller still works)
    # and pass the outgoing json=/data= kwarg as the request body for costing.
    # ----------------------------------------------------------------------- #
    try:
        import aiohttp
        _orig_aiohttp_request = aiohttp.ClientSession._request

        async def _aiohttp_request(self, method, str_or_url, **kw):
            url = str(str_or_url)
            if _host_kind(url):
                check_daily_limit()
            resp = await _orig_aiohttp_request(self, method, str_or_url, **kw)
            try:
                if _host_kind(url):
                    rb = kw.get("json")
                    if rb is None:
                        d = kw.get("data")
                        if isinstance(d, (str, bytes)):
                            try: rb = json.loads(d)
                            except Exception: rb = None
                    body = b""
                    try:
                        body = await resp.read()  # cached by aiohttp; caller can re-read
                    except Exception:
                        pass
                    _record(url, resp.status, body, rb)
            except Exception:
                pass
            return resp
        aiohttp.ClientSession._request = _aiohttp_request
    except Exception:
        pass

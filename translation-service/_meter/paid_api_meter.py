"""Network-level meter for paid APIs (LEAD, 2026-10-08, D635).

Imported via sitecustomize (PYTHONPATH=/opt/meter). Patches requests.Session.send
and urllib.request.urlopen so EVERY call to a paid host is logged with its usage,
computed $, and the calling file:line — regardless of which module made it.
Never raises into the caller.
"""
import json, os, sys, time, threading, traceback, socket

LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
SERVICE = os.environ.get("METER_SERVICE", os.path.basename(sys.argv[0]) if sys.argv else "?")
_lock = threading.Lock()
_INSTALLED = False  # guard so install() patches each HTTP client at most once


# --------------------------------------------------------------------------- #
# Listener role (LOCAL-723)
#
# The daily limit (LOCAL-673) must count LISTENER spend only. Every row the meter
# writes carries a `role`; the limit query sums only role = 'listener'. A row is
# 'listener' ONLY when the container PROVES it is part of the real listener stack
# — being labelled is not enough.
#
# THREAT: the LOCAL-721/722 test containers copied the shared generator's whole
# env (including HOSTNAME, METER_SERVICE), so the meter mislabelled their spend as
# the shared host and it counted toward the $8 limit (LEAD, 2026-10-20). A copied
# env must therefore NOT be able to qualify a test container as a listener.
#
# PROOF (simplest robust mechanism — a mounted-file token):
#   * The override sets METER_ROLE=listener and METER_ROLE_TOKEN=<secret> on the
#     four listener-facing services, AND bind-mounts a file at METER_ROLE_TOKEN_FILE
#     whose contents are that same secret. The file is mounted ONLY into the shared
#     containers.
#   * A row is 'listener' iff METER_ROLE == 'listener' AND the env token is
#     non-empty AND it equals the file's contents.
#   * A test container that copies the env inherits METER_ROLE and the token VALUE,
#     but it does NOT inherit the bind-mounted file. env_token == file_contents is
#     then false (the file is absent / unreadable), so the row is NOT a listener
#     row. Copying env alone can never qualify.
#
# FAIL SAFE FOR LISTENERS: any error, or no proof, yields role None (not counted).
# Mislabelling a listener as a non-listener only relaxes the limit for that row; it
# never lets test spend count. The token is an anti-spoof proof of container
# identity, NOT a secret whose leak is dangerous — it only decides whether a row
# counts toward a spend cap.
# --------------------------------------------------------------------------- #
METER_ROLE_ENV = "METER_ROLE"
METER_ROLE_TOKEN_ENV = "METER_ROLE_TOKEN"
METER_ROLE_TOKEN_FILE_ENV = "METER_ROLE_TOKEN_FILE"


def _real_hostname():
    """The REAL hostname of the box/container (socket.gethostname()), never the
    copyable HOSTNAME env. LOCAL-721/722 copied HOSTNAME into test containers, so
    the meter stamped the shared host's name on test rows. Never raises."""
    try:
        return socket.gethostname() or ""
    except Exception:
        return ""


def _meter_role():
    """Return 'listener' only when this container PROVES it is a real listener
    (METER_ROLE=listener AND the env token equals the mounted token file's
    contents); otherwise None. Never raises — any problem -> None (not counted)."""
    try:
        if (os.environ.get(METER_ROLE_ENV) or "").strip().lower() != "listener":
            return None
        token = (os.environ.get(METER_ROLE_TOKEN_ENV) or "").strip()
        if not token:
            return None
        path = (os.environ.get(METER_ROLE_TOKEN_FILE_ENV) or "").strip()
        if not path:
            return None
        with open(path) as f:
            file_token = f.read().strip()
        # A copied env carries `token` but NOT this mounted file, so a test
        # container's read fails (-> except -> None) or mismatches here.
        if file_token and token == file_token:
            return "listener"
        return None
    except Exception:
        return None

# [LOCAL-707] Belt-and-suspenders explicit metering. Serper calls go out through
# urllib/requests, which the network patches below already wrap. But the Oct 13
# LOCAL-678 change (httpx/aiohttp patching) coincided with Serper DISAPPEARING
# from paid_api_calls while httpx-based OpenAI/Gemini kept logging — i.e. in the
# live container the urllib/requests patches stopped producing Serper rows. The
# fix routes every real Serper call through serper_meter.serper_post(), which
# records the row DIRECTLY via record_call() — independent of whether the network
# patch is live. To avoid double-counting when the network patch IS active, an
# explicit record sets a thread-local "already metered" marker keyed on the
# request's id; the HTTP wrappers skip a response whose marker is set. Fail-open
# throughout: the marker machinery never raises into a caller.
_explicit = threading.local()


def _mark_explicit(url):
    """Mark that the current thread is about to make (and will itself record) a
    paid call to ``url``, so the network wrapper does not record it a second
    time. Returns a token to clear with _clear_explicit()."""
    try:
        marks = getattr(_explicit, "marks", None)
        if marks is None:
            marks = _explicit.marks = {}
        key = _host_kind(url)
        marks[key] = marks.get(key, 0) + 1
        return key
    except Exception:
        return None


def _clear_explicit(key):
    try:
        marks = getattr(_explicit, "marks", None)
        if marks and key in marks:
            marks[key] -= 1
            if marks[key] <= 0:
                marks.pop(key, None)
    except Exception:
        pass


def _is_explicit(url):
    """True when the current thread has an outstanding explicit-record marker for
    this URL's host kind (so the network wrapper should not double-record)."""
    try:
        marks = getattr(_explicit, "marks", None)
        return bool(marks and marks.get(_host_kind(url), 0) > 0)
    except Exception:
        return False

# $ per 1M tokens. OpenAI: published list prices. Gemini Flash: derived from our own Google
# invoice SKUs of 2026-10-05 (445,098 input tok = $0.33; 154,413 output tok = $0.58).
OPENAI = {  # longest key wins
    "gpt-4.1-nano": (0.10, 0.40, 0.025), "gpt-4.1-mini": (0.40, 1.60, 0.10), "gpt-4.1": (2.00, 8.00, 0.50),
    "gpt-4o-mini": (0.15, 0.60, 0.075), "gpt-4o": (2.50, 10.00, 1.25), "gpt-3.5-turbo": (0.50, 1.50, 0.50),
    "text-embedding-3-small": (0.02, 0.0, 0.02), "text-embedding-3-large": (0.13, 0.0, 0.13),
    "text-embedding-ada-002": (0.10, 0.0, 0.10),
}
GEMINI_IN, GEMINI_OUT, GROUNDING_PER_QUERY, SERPER_PER_QUERY = 0.75, 3.75, 0.014, 0.001
# [LOCAL-712 / D674] Anthropic (Claude) $ per 1M tokens: (input, output, cache_read).
# Base-token list prices, standard tier. Source:
# https://docs.anthropic.com/en/docs/about-claude/pricing (read 2026-10-18).
#   Claude Haiku 4.5: $1.00 in / $5.00 out / $0.10 cache-read (0.1x base input).
#   Claude Sonnet 5:  $2.00 in / $10.00 out / $0.20 cache-read (0.2x base input).
# [LOCAL-712B / D674 addendum 2] CURRENT Claude lineup added as extra bake-off
# arms (model IDs from docs.anthropic.com/en/docs/about-claude/models/overview,
# read 2026-10-18), the LOCAL-712 rows above kept:
#   Claude Haiku 5.5 (claude-haiku-5-5):  $0.10 in / $0.50 out / $0.01 cache-read
#       for prompts <=100k tokens. ABOVE 100k it is $0.50 in / $2.50 out (our
#       narration prompts are ~3k tokens, so only the <=100k tier ever applies).
#   Claude Sonnet 5.5 (claude-sonnet-5-5): $2.00 in / $10.00 out / $0.10 cache-read.
#   Claude Opus 5.5 (claude-opus-5-5):    $4.00 in / $20.00 out / $0.20 cache-read.
#       (Opus "fast mode" $8/$40 is NOT used.)
# Longest matching key wins, so the dated ids (claude-haiku-4-5-20251001) price too,
# and claude-sonnet-5-5 wins over claude-sonnet-5 (claude-sonnet-5-5 is longer).
ANTHROPIC = {  # longest key wins
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),   # prompts <=100k; >100k is (0.50, 2.50)
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}
# RATE_TAG names the price card every record was costed with (Michael 2026-10-08: "keep the tag
# on the price we are using"). Bump it whenever any rate below changes; the history of tags and the
# bill reconciliation behind each lives in .continuous_dev/PRICE_CARD.md.
RATE_TAG = "2026-10-10-r5"  # r5: grounded request $0.053 (GCloud SKU report Oct 1-10; search billed per query at $0.014, ~3.8 billed queries per grounded request)
GROUNDED_REQUEST_USD = 0.053  # r5 2026-10-10: GCloud SKU "Generate content search query gemini 3" = $0.014 per billed QUERY (8,324 queries = $116.54, Oct 1-10); Oct 8-9 billed search / grounded requests = $0.053

def _host_kind(url):
    u = url or ""
    if "api.openai.com" in u: return "openai"
    if "api.anthropic.com" in u: return "anthropic"
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

def _anthropic_cost(model, usage):
    """[LOCAL-712] $ for one Anthropic /v1/messages call, read from the response
    `usage` block. Anthropic reports input_tokens (UNCACHED only — cache reads
    and cache writes are separate counters) and output_tokens; a cache hit is
    reported in cache_read_input_tokens and billed at the 0.1x/0.2x cache rate.
    Returns (usd, rate_key) or (None, None) for an unknown model."""
    key = max((k for k in ANTHROPIC if k in (model or "")), key=len, default=None)
    if not key: return None, None
    i, o, c = ANTHROPIC[key]
    pt = usage.get("input_tokens") or 0           # uncached input tokens
    ct = usage.get("output_tokens") or 0
    cached = usage.get("cache_read_input_tokens") or 0
    return (pt * i + cached * c + ct * o) / 1e6, key

# --------------------------------------------------------------------------- #
# botocore (AWS Polly, AWS Translate)  [LOCAL-769]
#
# WHY A SEPARATE PATH: the requests/urllib/httpx/aiohttp patches in install()
# never see a boto3 call — botocore ships its own vendored urllib3 and does not
# go through any of those clients. So Polly SynthesizeSpeech /
# StartSpeechSynthesisTask and Translate TranslateText wrote ZERO paid_api_calls
# rows on every service (GCloud_Storied wdvrdaz5yt, tour 446 -> es).
# check_daily_limit() already ran before these calls (LOCAL-673) so the cap could
# STOP them, but their cost never counted toward it and Michael's spend report
# missed them. This closes the gap.
#
# WHERE WE PATCH: botocore.client.BaseClient._make_api_call (see install()). That
# is the ONE choke point every operation of every boto3 client passes through —
# sync, retried or not — so a single patch covers Polly, its async long-form
# StartSpeechSynthesisTask, and Translate, on every client created before or after
# install(), with the request params AND the parsed response in hand. Registering
# per-service `after-call` event handlers would instead need hooking each client's
# event system via create_client, missing clients already built — _make_api_call
# is simpler and strictly more robust.
#
# BILLED CHARACTERS: AWS bills Polly and Translate per CHARACTER of the input text
# (Polly counts SSML tags too, and reports the exact figure as RequestCharacters
# in the response — we prefer it and fall back to len(Text)). Translate bills the
# source characters, len(Text). A non-200 / exception costs $0 (we were not
# billed) but still writes a row so failures are visible.
# --------------------------------------------------------------------------- #
def _polly_engine(params):
    """Lowercase Polly Engine from the request params; defaults to 'neural' (the
    deployed English voices). Never raises."""
    try:
        return ((params or {}).get("Engine") or "neural").strip().lower()
    except Exception:
        return "neural"


def _boto_billed_chars(kind, params, response):
    """Characters AWS bills for this call. Polly reports the exact figure as
    RequestCharacters (SSML tags included); we prefer it and fall back to the
    input Text length. Translate bills the source Text length. Never raises."""
    try:
        if kind == "polly":
            rc = (response or {}).get("RequestCharacters")
            if isinstance(rc, (int, float)) and rc >= 0:
                return int(rc)
            return len((params or {}).get("Text") or "")
        if kind == "aws_translate":
            return len((params or {}).get("Text") or "")
    except Exception:
        pass
    return 0


def _boto_cost(kind, chars, params):
    """USD for `chars` billed characters of a Polly / Translate call, priced from
    cost_rates (imported softly so a missing rate table never breaks TTS). Polly
    is priced by its Engine; Translate at the per-character rate. Returns
    (usd, model_str). Never raises -> (None, model)."""
    model = ""
    try:
        if kind == "polly":
            engine = _polly_engine(params)
            voice = (params or {}).get("VoiceId") or ""
            model = "%s/%s" % (engine, voice) if voice else engine
            import cost_rates
            return cost_rates.tts_cost(chars, engine=engine), model
        if kind == "aws_translate":
            model = "translate"
            import cost_rates
            return chars * cost_rates.AWS_TRANSLATE_COST_PER_CHAR, model
    except Exception:
        pass
    return None, model


def _record_boto(url, kind, status, operation, params, response):
    """[LOCAL-769] Write exactly one paid_api_calls row for a boto3 Polly/Translate
    call. Mirrors _record's row shape (ts, kind, status, service, caller, role,
    url, job, usd) plus model and billed `chars`, and reuses the same JSONL log
    and _db_write. Fail-open throughout: any error is captured on the row, never
    raised into the caller."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind,
           "status": status, "rate_tag": RATE_TAG, "service": SERVICE,
           "caller": _caller(), "url": (url or "").split("?")[0][-120:],
           "operation": operation, "job": os.environ.get("METER_JOB", ""),
           "role": _meter_role(), "usd": None}
    try:
        chars = _boto_billed_chars(kind, params, response)
        usd, model = _boto_cost(kind, chars, params)
        rec.update(model=model, chars=chars, usd=usd if status == 200 else 0.0)
    except Exception as e:
        rec["meter_error"] = str(e)[:120]
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with _lock, open(LOG, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass
    _db_write(rec)


def _record(url, status, body, req_body=None):
    kind = _host_kind(url)
    if not kind: return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, "status": status, "rate_tag": RATE_TAG,
           "service": SERVICE, "caller": _caller(), "url": (url or "").split("?")[0][-120:],
           "job": os.environ.get("METER_JOB", ""), "role": _meter_role(), "usd": None}
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
        elif kind == "anthropic":
            # Anthropic /v1/messages: the response carries `model` and a `usage`
            # block {input_tokens, output_tokens, cache_read_input_tokens?}. On an
            # error the model falls back to the request body's model so the row is
            # still attributable. Usage is read for the $; a non-200 costs $0.
            model = d.get("model") or ((req_body or {}).get("model") if isinstance(req_body, dict) else "")
            usage = d.get("usage") or {}
            usd, key = _anthropic_cost(model, usage)
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


def record_call(url, status, body=b"", req_body=None):
    """[LOCAL-707] Public, explicit metering entry point.

    Writes exactly one paid_api_calls row for a paid request, with the same
    costing, log and DB behaviour as the automatic network wrappers. Callers that
    want a GUARANTEED record regardless of whether the network patch is installed
    (e.g. serper_meter.serper_post) call this directly. Never raises.

    A non-paid host is ignored (one choke point: _record returns on kind=None), so
    passing a non-serper URL here is harmless. The paired _mark_explicit /
    _clear_explicit calls prevent the network wrapper from double-recording the
    same request on hosts where the patch is also live.
    """
    try:
        _record(url, status, body, req_body)
    except Exception:
        pass


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
            cur.execute("INSERT INTO paid_api_calls (kind,status,service,caller,url,model,usd,detail,host,role) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (rec.get("kind"), rec.get("status"), rec.get("service"), rec.get("caller"),
                         rec.get("url"), rec.get("model"), rec.get("usd"), json.dumps(rec, default=str),
                         _real_hostname(), rec.get("role")))
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
#
# [LOCAL-723] The total counts role = 'listener' rows ONLY. Earlier the scope was
# DAILY_PAID_LIMIT_SERVICES (a `service` list), but test/bench containers run the
# same services, so their spend tripped the listeners' limit (LEAD 2026-10-20).
# role is proven, not merely labelled (see _meter_role), so a test container that
# copies the listener env cannot be counted. DAILY_PAID_LIMIT_SERVICES is no
# longer read.
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
            #
            # [LOCAL-723] The limit counts LISTENER spend only. Earlier (LOCAL-673)
            # it scoped by `service`, but test/bench containers run the SAME
            # services as the listener stack, so their spend tripped the listeners'
            # $8 limit while listeners had spent $0 (LEAD 2026-10-20). Now the meter
            # stamps role = 'listener' on PROVEN listener rows only (see
            # _meter_role: env label + mounted-token-file proof) and the limit sums
            # exactly those. role NULL / anything-but-'listener' (old rows, every
            # test/bench row) is never counted — fail safe for listeners: test
            # spend can never trip their limit.
            cur.execute(
                "SELECT COALESCE(SUM(usd), 0) FROM paid_api_calls "
                "WHERE status = 200 "
                "AND (ts AT TIME ZONE 'America/New_York')::date = %s::date "
                "AND role = 'listener'",
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
                if _host_kind(request.url) and not _is_explicit(request.url):
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
                try:
                    if not _is_explicit(url):
                        _record(url, getattr(e, "code", 0), b"")
                except Exception: pass
                raise
            try:
                data = resp.read()
                import io
                if not _is_explicit(url):
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
                if _host_kind(url) and not _is_explicit(url):
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
                if _host_kind(url) and not _is_explicit(url):
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
                if _host_kind(url) and not _is_explicit(url):
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
    # ----------------------------------------------------------------------- #
    # botocore (AWS Polly, AWS Translate)  [LOCAL-769]
    #
    # boto3 does NOT use requests/urllib/httpx/aiohttp — botocore has its own
    # vendored urllib3 stack, so none of the patches above ever saw a Polly or
    # Translate call. We patch botocore.client.BaseClient._make_api_call, the one
    # choke point every operation of every client passes through (see the block
    # comment on _record_boto for the full rationale and why this beats per-service
    # after-call event handlers).
    #
    # The operation name is PascalCase (SynthesizeSpeech, StartSpeechSynthesisTask,
    # TranslateText); `api_params` holds the input (Text, Engine, VoiceId, …) and
    # the return value is the parsed response dict (with RequestCharacters for
    # Polly and ResponseMetadata.HTTPStatusCode when a real HTTP layer ran). We
    # derive kind from the client's endpoint host via the existing _host_kind, so
    # only Polly / Translate are metered and every other AWS service is ignored.
    #
    # Fail-open and non-blocking exactly like the other clients: check_daily_limit()
    # runs BEFORE the call (it may raise DailyPaidLimitExceeded, the intended STOP,
    # or fail open), the call itself is never altered, and recording never raises.
    # The response's AudioStream is NEVER read (that would consume the caller's
    # stream) — chars come from RequestCharacters or len(Text).
    # ----------------------------------------------------------------------- #
    try:
        import botocore.client as _bcli

        def _boto_kind(client):
            """'polly' / 'aws_translate' / None for a boto3 client, via the same
            _host_kind the network patches use (endpoint host), with a service-name
            fallback. Never raises."""
            try:
                url = getattr(getattr(client, "meta", None), "endpoint_url", "") or ""
                k = _host_kind(url)
                if k:
                    return k
            except Exception:
                pass
            try:
                svc = client._service_model.service_name
                if svc == "polly":
                    return "polly"
                if svc == "translate":
                    return "aws_translate"
            except Exception:
                pass
            return None

        _orig_make_api_call = _bcli.BaseClient._make_api_call

        def _make_api_call(self, operation_name, api_params):
            kind = _boto_kind(self)
            # Enforce the daily limit BEFORE the paid call (may raise the STOP, or
            # fail open). Non-paid AWS services are never checked or recorded.
            if kind:
                check_daily_limit()
            try:
                response = _orig_make_api_call(self, operation_name, api_params)
            except Exception as e:
                # Record a failed paid call at $0 so it is still visible, then
                # re-raise unchanged — the meter must never swallow a boto error.
                if kind:
                    try:
                        code = 0
                        resp = getattr(e, "response", None)
                        if isinstance(resp, dict):
                            code = (resp.get("ResponseMetadata") or {}).get(
                                "HTTPStatusCode", 0) or 0
                        url = getattr(getattr(self, "meta", None), "endpoint_url", "")
                        _record_boto(url, kind, code, operation_name, api_params, None)
                    except Exception:
                        pass
                raise
            if kind:
                try:
                    status = (response.get("ResponseMetadata") or {}).get(
                        "HTTPStatusCode", 200) if isinstance(response, dict) else 200
                    # A stubbed/successful response with no ResponseMetadata is a
                    # 200 (the call returned normally).
                    status = status or 200
                    url = getattr(getattr(self, "meta", None), "endpoint_url", "")
                    _record_boto(url, kind, status, operation_name, api_params, response)
                except Exception:
                    pass
            return response
        _bcli.BaseClient._make_api_call = _make_api_call
    except Exception:
        pass

"""Network-level meter for paid APIs (LEAD, 2026-10-08, D635).

Imported via sitecustomize (PYTHONPATH=/opt/meter). Patches requests.Session.send
and urllib.request.urlopen so EVERY call to a paid host is logged with its usage,
computed $, and the calling file:line — regardless of which module made it.
Never raises into the caller.
"""
import json, os, sys, time, threading, traceback, socket

LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")


def _default_service():
    """The `service` tag for every row this process writes. Precedence:
      1. METER_SERVICE                — explicit override (shared stack, harnesses)
      2. TASK_BUDGET_ID               — [LOCAL-819] a Kiro task's id. Every isolated
         task container already sets TASK_BUDGET_ID for the whole-task budget
         (LOCAL-817); reusing it here means each task's rows carry service=<task id>
         with ZERO per-runner wiring, so meter_report.py can total one task's spend
         across all its runs — "one sum covers everything".
      3. the script basename          — last-resort, legible default.
    Never raises."""
    try:
        svc = (os.environ.get("METER_SERVICE") or "").strip()
        if svc:
            return svc
        tb = (os.environ.get("TASK_BUDGET_ID") or "").strip()
        if tb:
            return tb
        return os.path.basename(sys.argv[0]) if sys.argv else "?"
    except Exception:
        return "?"


SERVICE = _default_service()
_lock = threading.Lock()


def _key_suffix():
    """[LOCAL-819] A NON-SENSITIVE tag identifying WHICH paid-API key a row was
    billed to, so meter_report.py can total per key and line up with the provider
    usage page (which is per-key). The meter deliberately never logs a key; a
    caller/container sets METER_KEY_SUFFIX to the key's LAST FEW characters only
    (e.g. 'k9sA' for the mac-mini key) — a 4-char suffix is not the key and cannot
    reconstruct it. Returns '' when unset. Never raises."""
    try:
        return (os.environ.get("METER_KEY_SUFFIX") or "").strip()[-8:]
    except Exception:
        return ""
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
# [LOCAL-783] Serper Places (https://google.serper.dev/places) returns the full
# page (~20 businesses), which the Serper credit rule prices at 2 credits
# ($0.002) — "> 10 results = 2 credits" (serper.dev credit model + Scrapingdog/
# Medium benchmark, read 2026-10-26; base $0.001/credit at the $50/50k tier).
# A /places call bills twice a /search call; priced separately so the ledger
# never under-counts the bulk place search / refill that LOCAL-783 added.
SERPER_PLACES_PER_QUERY = 0.002
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

def _openai_tokens(usage):
    """[LOCAL-819] (tokens_in, tokens_out) for an OpenAI response usage block, as
    plain ints for the top-level tokens_in/tokens_out row fields. Accepts both the
    chat/completions shape (prompt_tokens/completion_tokens) and the responses API
    shape (input_tokens/output_tokens). Never raises -> (0, 0)."""
    try:
        ti = usage.get("prompt_tokens")
        if ti is None:
            ti = usage.get("input_tokens")
        to = usage.get("completion_tokens")
        if to is None:
            to = usage.get("output_tokens")
        return int(ti or 0), int(to or 0)
    except Exception:
        return 0, 0


def _anthropic_tokens(usage):
    """[LOCAL-819] (tokens_in, tokens_out) for an Anthropic /v1/messages usage
    block. Anthropic reports input_tokens as UNCACHED input only; cache reads are a
    separate counter, so tokens_in folds cache_read_input_tokens back in to reflect
    the input actually processed. Never raises -> (0, 0)."""
    try:
        ti = (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
        to = usage.get("output_tokens") or 0
        return int(ti), int(to)
    except Exception:
        return 0, 0


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
           "role": _meter_role(), "key_suffix": _key_suffix(), "usd": None}
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
           "job": os.environ.get("METER_JOB", ""), "role": _meter_role(), "key_suffix": _key_suffix(), "usd": None}
    try:
        d = json.loads(body) if isinstance(body, (bytes, str)) and body else {}
    except Exception:
        d = {}
    try:
        if kind == "openai":
            model = d.get("model") or ((req_body or {}).get("model") if isinstance(req_body, dict) else "")
            usage = d.get("usage") or {}
            usd, key = _openai_cost(model, usage)
            # [LOCAL-819] Record the real token counts as TOP-LEVEL tokens_in /
            # tokens_out, not only nested inside `usage`. Every reporting tool
            # (meter_report.py, reconcile_paid_api.py) and Gemini rows already use
            # the top-level fields; before this, all 19,609 OpenAI rows showed
            # tokens_in/out = 0 because the counts lived only under usage.* . usd
            # is still computed from the same usage block, so the $ is unchanged.
            ti, to = _openai_tokens(usage)
            rec.update(model=model, usage=usage, tokens_in=ti, tokens_out=to,
                       usd=usd if status == 200 else 0.0, rate_key=key)
        elif kind == "anthropic":
            # Anthropic /v1/messages: the response carries `model` and a `usage`
            # block {input_tokens, output_tokens, cache_read_input_tokens?}. On an
            # error the model falls back to the request body's model so the row is
            # still attributable. Usage is read for the $; a non-200 costs $0.
            model = d.get("model") or ((req_body or {}).get("model") if isinstance(req_body, dict) else "")
            usage = d.get("usage") or {}
            usd, key = _anthropic_cost(model, usage)
            # [LOCAL-819] Same fix for Anthropic rows: surface tokens_in/out at the
            # top level. input_tokens is Anthropic's UNCACHED input; cache reads are
            # a separate counter, folded into tokens_in so the row's token total
            # matches what was processed.
            ti, to = _anthropic_tokens(usage)
            rec.update(model=model, usage=usage, tokens_in=ti, tokens_out=to,
                       usd=usd if status == 200 else 0.0, rate_key=key)
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
            # [LOCAL-783] The Places endpoint bills 2 credits ($0.002); every other
            # Serper endpoint (search, news, scholar) bills 1 credit ($0.001).
            _is_places = "/places" in (url or "")
            _rate = SERPER_PLACES_PER_QUERY if _is_places else SERPER_PER_QUERY
            rec.update(usd=_rate if status == 200 else 0.0)
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


# --------------------------------------------------------------------------- #
# Whole-task paid-API budget  (LOCAL-817)
#
# The daily limit above caps a CALENDAR DAY's listener spend. It does NOT cap a
# single Kiro task's TOTAL spend across its (often many) debugging re-runs, which
# is what a task file means by "Paid-API cap $X TOTAL across all runs". On
# 2026-10-29 that gap let tasks overspend 3x (LOCAL-810 $2.88 vs $1.00, …). This
# is the raw-door half of the fix: EVERY paid call that passes through this meter
# — including calls made OUTSIDE tests/live_run_meter.LiveRunMeter — refuses to go
# out once the task's recorded total has reached TASK_BUDGET_USD.
#
# Self-contained on purpose: this module ships to containers via /opt/meter with
# nothing else on the path, so it must NOT import the repo-root task_budget.py. It
# reads the SAME env contract (TASK_BUDGET_ID / TASK_BUDGET_USD) and the SAME
# append-only JSON ledger (~/.audioura_task_budgets/<id>.json, dir overridable
# with AUDIOURA_TASK_BUDGET_DIR) that task_budget.py and LiveRunMeter use, so the
# two halves agree. The ledger is written by LiveRunMeter at the end of each run;
# this door only READS the recorded total.
#
# FAIL-OPEN like the daily limit: any error reading the env or the ledger -> allow
# (a meter bug must never block a tour). The cap is OFF when TASK_BUDGET_ID is
# unset or TASK_BUDGET_USD is unset/negative. A budget of exactly $0 is a real cap
# (no paid spend allowed) — used by the LOCAL-817 $0 test.
# --------------------------------------------------------------------------- #
TASK_BUDGET_ID_ENV = "TASK_BUDGET_ID"
TASK_BUDGET_USD_ENV = "TASK_BUDGET_USD"
TASK_BUDGET_DIRNAME = ".audioura_task_budgets"


class TaskBudgetExceeded(Exception):
    """[LOCAL-817] Raised instead of sending a paid request once the task's
    recorded TOTAL paid-API spend (the ~/.audioura_task_budgets/<id>.json ledger)
    has reached TASK_BUDGET_USD. Callers already handle paid-API failures, so the
    tour fails cleanly with an honest error rather than overspending."""


def _task_budget_id():
    """Active task id, or None when the whole-task cap is off. Never raises."""
    try:
        raw = os.environ.get(TASK_BUDGET_ID_ENV)
        if raw is None:
            return None
        raw = raw.strip()
        return raw or None
    except Exception:
        return None


def _task_budget_usd():
    """Whole-task budget in USD, or None when off (unset/blank/unparseable/<0).
    $0 is kept (a real zero-spend cap). Never raises."""
    try:
        raw = os.environ.get(TASK_BUDGET_USD_ENV)
        if raw is None or str(raw).strip() == "":
            return None
        val = float(raw)
        return val if val >= 0 else None
    except Exception:
        return None


def _task_budget_dir():
    try:
        override = os.environ.get("AUDIOURA_TASK_BUDGET_DIR")
        if override:
            return override
        return os.path.join(os.path.expanduser("~"), TASK_BUDGET_DIRNAME)
    except Exception:
        return TASK_BUDGET_DIRNAME


def _task_budget_ledger_path(task_id):
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(task_id).strip()) or "task"
    return os.path.join(_task_budget_dir(), safe + ".json")


def _task_budget_spent(task_id):
    """Sum of recorded run dollars for ``task_id`` from the JSON ledger. A missing
    or unreadable ledger reads as $0 (fail-open). Never raises."""
    try:
        with open(_task_budget_ledger_path(task_id)) as f:
            data = json.load(f)
        total = 0.0
        for run in (data.get("runs") or []):
            try:
                total += float(run.get("usd") or 0.0)
            except (TypeError, ValueError):
                continue
        return total
    except Exception:
        return 0.0


def check_task_budget():
    """[LOCAL-817] Enforce TASK_BUDGET_USD before a paid request. Raises
    TaskBudgetExceeded when the task's recorded total has reached the budget;
    returns None (allow) otherwise. Fails OPEN on any error. No-op when the
    whole-task cap is off.

    Called immediately before sending any paid request (by every client patch in
    install(), alongside check_daily_limit). The precise spent+current accounting
    for an IN-PROGRESS run lives in LiveRunMeter's grounding guard; this raw-door
    check is the belt-and-suspenders catch for paid calls made OUTSIDE
    LiveRunMeter — it refuses once the recorded total has reached the budget."""
    task_id = _task_budget_id()
    if not task_id:
        return  # cap off
    budget = _task_budget_usd()
    if budget is None:
        return  # cap off
    try:
        spent = _task_budget_spent(task_id)
    except Exception:
        return  # fail-open: never block on a ledger read error
    if spent >= budget:
        raise TaskBudgetExceeded(
            "TASK_BUDGET_USD reached: task %s recorded paid-API spend "
            "$%.4f >= budget $%g. Refusing paid request (whole-task cap, "
            "LOCAL-817)." % (task_id, spent, budget))


# --------------------------------------------------------------------------- #
# Meter-log whole-task cap  (LOCAL-827)
#
# THE GAP LEFT BY LOCAL-817. The cap above reads the JSON ledger
# (~/.audioura_task_budgets/<id>.json), which only LiveRunMeter writes, and only
# at the END of a run. So:
#   * a container whose ledger dir was never bind-mounted wrote the ledger inside
#     the --rm container, which is destroyed — every run started from $0 and the
#     whole-task cap never accumulated across runs (LOCAL-821B spent $0.81 vs
#     $0.40; LOCAL-823/824 reported "No ledger … No runs recorded yet"), and
#   * even with the dir mounted (LOCAL-827 docker_meter_args), the ledger only
#     catches up at run END, so a single long run could overspend before its one
#     ledger row is written.
#
# This cap is INDEPENDENT of LiveRunMeter: it sums the `usd` of the task's OWN
# rows in the CANONICAL METER LOG (PAID_API_LOG) — the append-only JSONL the
# meter itself writes after every paid call, tagged service=<task id>. Because the
# log dir is bind-mounted to the host (the LOCAL-819/820 contract) and shared by
# every isolated run of a task, the sum is the task's TRUE spend across ALL its
# containers, updated the instant each call is recorded. Once that sum reaches
# TASK_BUDGET_USD the raw door refuses the next paid call. It is the mechanical
# cap the ticket asks for: "budget from the meter itself".
#
# ARMING — identical gate to the mount guard (LOCAL-822B), so a cap meant for Kiro
# task runs can NEVER refuse a production paid call:
#   * OFF unless TASK_BUDGET_ID is set AND TASK_BUDGET_USD resolves (>= 0).
#   * NEVER armed when K_SERVICE is set (Cloud Run) — belt and braces.
#   * Only the task's OWN rows count: a row is summed iff service == TASK_BUDGET_ID
#     (the same tag docker_meter_args / the .sh wrappers stamp), so the shared
#     stack's rows in the same log never count toward a task's cap and vice-versa.
#
# CACHING — summing the log on every call would reread a growing file each time.
# The sum is cached per (log path, task id) and re-read at most every 10 s, like
# the daily limit's 60 s DB cache. A budget breach is therefore enforced within
# ~10 s of the call that crossed it; for a $0.0002 live cap with calls seconds
# apart that still stops the run within a call or two, which the live proof shows.
#
# FAIL-OPEN — any error reading the env or the log -> allow (a meter bug must
# never block a tour), exactly like check_daily_limit and check_task_budget.
# A budget of exactly $0 is a real cap ($0 >= $0 refuses the first paid call).
# --------------------------------------------------------------------------- #
_METER_LOG_CAP_TTL = 10.0  # seconds: re-read the log at most this often
# Cache: {(log_path, task_id): (expiry_epoch, summed_usd)}. Guarded by _meterlog_lock.
_meterlog_lock = threading.Lock()
_meterlog_cap_cache = {}


def _meter_log_path_for_cap():
    """The canonical meter log this process writes/reads, matching LOG so the cap
    sums the SAME file the meter appends to. Never raises."""
    try:
        return os.environ.get("PAID_API_LOG") or LOG
    except Exception:
        return LOG


def _sum_meter_log_usd_for_service(task_id, log_path):
    """Sum of billed (status 200) `usd` for rows whose service == task_id in the
    canonical meter log at ``log_path``. A missing log reads as $0.0 (fail-open: a
    task with no rows yet has spent nothing). Raises only on an unexpected read
    error so the caller can fail open. Malformed lines and rows missing fields are
    skipped. Rows with no explicit status are counted (the meter writes status on
    every real row; a defensive default of 'billed' keeps the cap conservative)."""
    total = 0.0
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                if str(row.get("service") or "") != str(task_id):
                    continue
                status = row.get("status")
                # Only billed rows carry $ (a non-200 row's usd is 0 anyway, but
                # skip it explicitly so a future non-zero error row never counts).
                if status is not None and status != 200:
                    continue
                try:
                    total += float(row.get("usd") or 0.0)
                except (TypeError, ValueError):
                    continue
    except FileNotFoundError:
        return 0.0
    return total


def _meter_log_spent(task_id, log_path=None, now=None):
    """Cached sum of the task's own spend from the canonical meter log. Re-reads
    the file at most every _METER_LOG_CAP_TTL seconds per (log, task). Never
    raises -> on any error returns 0.0 (fail-open)."""
    try:
        path = log_path or _meter_log_path_for_cap()
        now_ts = now if now is not None else time.time()
        key = (path, str(task_id))
        with _meterlog_lock:
            cached = _meterlog_cap_cache.get(key)
            if cached is not None and now_ts < cached[0]:
                return cached[1]
        total = _sum_meter_log_usd_for_service(task_id, path)
        with _meterlog_lock:
            _meterlog_cap_cache[key] = (now_ts + _METER_LOG_CAP_TTL, total)
        return total
    except Exception:
        return 0.0


def _meter_log_cap_armed():
    """[LOCAL-827] True only for a Kiro task run with a budget: TASK_BUDGET_ID set
    and TASK_BUDGET_USD resolved, and NEVER on Cloud Run (K_SERVICE set). Mirrors
    the mount-guard arming so the cap can never stop production. Never raises ->
    False."""
    try:
        if _is_cloud_run():
            return False
        if not _task_budget_id():
            return False
        if _task_budget_usd() is None:
            return False
        return True
    except Exception:
        return False


def check_task_budget_meter_log():
    """[LOCAL-827] Enforce TASK_BUDGET_USD from the METER LOG itself. Raises
    TaskBudgetExceeded when the sum of the task's own billed `usd` rows in the
    canonical meter log (service == TASK_BUDGET_ID) has reached TASK_BUDGET_USD;
    returns None (allow) otherwise.

    This is the mechanical cap that accumulates across isolated run containers
    without depending on LiveRunMeter's end-of-run ledger: the meter writes a row
    after every paid call, the log dir is bind-mounted to the host and shared by
    every run of the task, so the sum is the task's true cross-run spend. The sum
    is cached and re-read at most every 10 s.

    Never armed without TASK_BUDGET_ID, and never on Cloud Run (K_SERVICE). Fails
    OPEN on any error. Called immediately before sending any paid request,
    alongside check_daily_limit, check_task_budget and check_meter_mount."""
    try:
        if not _meter_log_cap_armed():
            return  # cap off / production
        task_id = _task_budget_id()
        budget = _task_budget_usd()
        spent = _meter_log_spent(task_id)
    except Exception as e:
        # Fail-open: an env/log read error must never block a tour.
        try:
            sys.stderr.write("[paid_api_meter] meter-log task-budget check failed "
                             "open: %s\n" % (str(e)[:200],))
        except Exception:
            pass
        return
    if spent >= budget:
        raise TaskBudgetExceeded(
            "TASK_BUDGET_USD reached (meter log): task %s metered paid-API spend "
            "$%.4f >= budget $%g. Refusing paid request (whole-task cap across all "
            "run containers, LOCAL-827)." % (task_id, spent, budget))


# --------------------------------------------------------------------------- #
# Container meter-mount contract  (LOCAL-822 / LOCAL-822B)
#
# LOCAL-820 wired the .sh wrappers and isolated_test.py so a container's meter
# rows reach the HOST (bind-mount ~/Audioura/meterlogs -> /meterlogs, canonical
# PAID_API_LOG, service tag). But the guard test for that only SCANS source
# files — it cannot see a hand-typed ``docker run`` (LOCAL-818 launched its live
# tours that way), so the next hand-typed run can still write its rows to
# /meterlogs INSIDE the container, where ``--rm`` destroys them. LOCAL-818's two
# tours left ZERO rows on the host for exactly this reason.
#
# LOCAL-817 solved the same class of problem for the whole-task budget by making
# the meter itself refuse. We do the same for the meterlog mount: before a paid
# call MADE BY A TASK RUN, when we are INSIDE a container, REFUSE unless the
# directory holding PAID_API_LOG is a BIND MOUNT (os.path.ismount, or a
# /proc/self/mountinfo check) — a real host dir mounted in, not an ephemeral
# container path that --rm will delete.
#
# [LOCAL-822B — the BOUNCE]  The first cut armed the guard for EVERY container
# (anything with /.dockerenv). But the meter is baked into the generator image
# with ENV PYTHONPATH=/opt/meter, so it runs in Cloud Run (GCloud Subscribed),
# the Windows laptop's local Docker stack, AND the Mac shared stack — none of
# which are Kiro task runs. A guard meant to catch a forgotten bind-mount on a
# Kiro test run must NEVER be able to refuse a PRODUCTION paid call. So the guard
# now ARMS ONLY for task runs and allows everything else:
#
#   * ARMED when TASK_BUDGET_ID is set, OR METER_SERVICE matches ^LOCAL- (the two
#     signals a Kiro isolated-task run always carries). With neither -> NOT armed
#     -> ALLOW (today's behaviour for production: the shared stack, a plain image,
#     the laptop, any future host).
#   * NEVER armed when K_SERVICE is set — Cloud Run always sets it — belt and
#     braces, so a Cloud Run container is allowed even if some future task env
#     leaks in.
#   * An armed run inside a container STILL needs the bind mount -> refuse,
#     naming ``meter_container_env.docker_meter_args`` (the ONE helper that emits
#     the correct args), exactly as before. That is the whole point: a Kiro task's
#     hand-typed ``docker run`` that forgets the mount is stopped, $0 spent.
#
# FAIL-OPEN like the other doors: not armed -> allow; not in a container (no
# /.dockerenv) -> allow; any error deciding mount/arming -> allow and log. The
# guard is OFF entirely when METER_MOUNT_GUARD=0 (an escape hatch for a deliberate
# no-mount diagnostic). A missing PAID_API_LOG env defaults to /meterlogs/... just
# like LOG above.
# --------------------------------------------------------------------------- #
MOUNT_GUARD_ENV = "METER_MOUNT_GUARD"
CLOUD_RUN_ENV = "K_SERVICE"  # Cloud Run always sets this; its presence disarms the guard


class MeterMountMissing(Exception):
    """[LOCAL-822] Raised instead of making a paid call when a TASK RUN inside a
    container has NOT proven its meter rows will reach the host: the directory of
    PAID_API_LOG is not a bind mount, so the rows die inside the --rm container.
    The whole point is that a hand-typed ``docker run`` for a Kiro task that
    forgets the meterlogs bind-mount burns money whose rows vanish — so refuse,
    $0 spent, and tell the operator to build the run with
    meter_container_env.docker_meter_args. [LOCAL-822B] Only ever raised for a
    task run (TASK_BUDGET_ID set, or METER_SERVICE ^LOCAL-); a production
    container — Cloud Run, the Mac shared stack, the laptop — is never refused."""


def _in_container():
    """True when running inside a Docker container (``/.dockerenv`` exists). Never
    raises -> False (fail-open: a detection error must not block a host run)."""
    try:
        return os.path.exists("/.dockerenv")
    except Exception:
        return False


def _mount_guard_on():
    """The guard is ON unless METER_MOUNT_GUARD is explicitly '0'/'false'/'no'.
    Lets a deliberate diagnostic run opt out. Never raises -> True (guard on)."""
    try:
        raw = (os.environ.get(MOUNT_GUARD_ENV) or "").strip().lower()
        return raw not in ("0", "false", "no", "off")
    except Exception:
        return True


def _paid_api_log_path():
    """The PAID_API_LOG path this process writes, matching the module LOG default
    so the guard checks the SAME file the meter logs to. Never raises."""
    try:
        return os.environ.get("PAID_API_LOG") or LOG
    except Exception:
        return LOG


def _dir_is_bind_mount(path):
    """True when ``path`` (the directory of PAID_API_LOG) is a mount point — a
    host directory bind-mounted into the container, so rows written there survive
    ``docker run --rm``. Uses os.path.ismount first (works for a bind mount whose
    target is a directory), then falls back to a /proc/self/mountinfo scan for the
    rare case ismount misses (e.g. a bind mount onto an existing path on the same
    device, where the classic st_dev check can be fooled). Never raises -> False
    (fail SAFE for the mount question: an undecidable mount reads as 'not a
    mount', which only makes the guard stricter, never looser)."""
    try:
        d = path or ""
        # Normalise to the directory holding the log file.
        d = os.path.dirname(d) or d
        if not d:
            return False
        try:
            if os.path.ismount(d):
                return True
        except Exception:
            pass
        # Fallback: /proc/self/mountinfo lists every mount point as field 5. A
        # bind mount's target dir appears there verbatim even when os.path.ismount
        # was fooled. Linux-only; absent on mac/host, where _in_container is False
        # anyway so this path is not reached in the refusal case.
        try:
            real = os.path.realpath(d)
            with open("/proc/self/mountinfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 5:
                        mp = parts[4]
                        if mp == d or mp == real:
                            return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def _is_cloud_run():
    """[LOCAL-822B] True when running on Google Cloud Run, which ALWAYS sets
    K_SERVICE. The guard never arms on Cloud Run — belt and braces so a production
    paid call there can never be refused even if some task env leaked in. Never
    raises -> False."""
    try:
        return bool((os.environ.get(CLOUD_RUN_ENV) or "").strip())
    except Exception:
        return False


def _meter_service_is_task():
    """[LOCAL-822B] True when METER_SERVICE names a Kiro task — i.e. it starts with
    'LOCAL-' (case-insensitive). A Kiro isolated-task container tags its rows
    service=LOCAL-NNN; the shared stack sets METER_SERVICE to a host/service name
    that does NOT start with LOCAL-, so this stays False for production. Never
    raises -> False."""
    try:
        return (os.environ.get("METER_SERVICE") or "").strip().upper().startswith("LOCAL-")
    except Exception:
        return False


def _guard_armed():
    """[LOCAL-822B] True ONLY for a Kiro task run, which is the only run the
    mount guard applies to. Armed when TASK_BUDGET_ID is set OR METER_SERVICE
    matches ^LOCAL- ; NEVER armed on Cloud Run (K_SERVICE set). With neither task
    signal (the shared stack, a plain image, the laptop, any future production
    host) the guard is NOT armed and the call is allowed — a guard for Kiro's
    test runs must never be able to stop production. Never raises -> False
    (fail-open: an undecidable arming reads as 'not a task run' -> allow)."""
    try:
        if _is_cloud_run():
            return False
        if (os.environ.get(TASK_BUDGET_ID_ENV) or "").strip():
            return True
        if _meter_service_is_task():
            return True
        return False
    except Exception:
        return False


def check_meter_mount():
    """[LOCAL-822 / LOCAL-822B] Enforce the container meter-mount contract before
    a paid call — but ONLY for a Kiro TASK RUN.

    Raises MeterMountMissing only when ALL of these hold: the guard is on, the run
    is ARMED as a task run (TASK_BUDGET_ID set, or METER_SERVICE ^LOCAL-; and
    NEVER on Cloud Run, where K_SERVICE is set), we are INSIDE a container, and the
    directory of PAID_API_LOG is not a bind mount (so the rows would die inside the
    --rm container). Returns None (allow) in every other case.

    [LOCAL-822B] The arming gate is the fix for the bounce: the meter is baked into
    the generator image (PYTHONPATH=/opt/meter), so this code also runs in Cloud
    Run, the Mac shared stack and the laptop — none of which are task runs. A guard
    for Kiro's test runs must never refuse a PRODUCTION paid call, so a run that is
    not armed is always allowed.

    Fail-OPEN: not armed, not in a container, guard switched off, or any error
    deciding arming/mount -> allow. The only hard stop is the deliberate refusal
    for a TASK container that would lose its rows. Called immediately before
    sending any paid request, alongside check_daily_limit and check_task_budget."""
    try:
        if not _mount_guard_on():
            return
        if not _guard_armed():
            return  # not a Kiro task run (Cloud Run / shared stack / plain image) -> allow
        if not _in_container():
            return  # on the host — the guard does not apply
        log_path = _paid_api_log_path()
        mounted = _dir_is_bind_mount(log_path)
    except Exception as e:
        # Fail-open on a detection error: a guard bug must never block a tour.
        try:
            sys.stderr.write("[paid_api_meter] mount-guard check failed open: %s\n"
                             % (str(e)[:200],))
        except Exception:
            pass
        return
    if mounted:
        return  # contract satisfied — rows will reach the host
    log_dir = os.path.dirname(log_path) or log_path
    raise MeterMountMissing(
        "[LOCAL-822] refusing paid call: this task-run container has NOT proven "
        "its meter rows reach the host — the directory of PAID_API_LOG (%s) is not "
        "a host bind-mount, so its rows die inside the --rm container. Build the "
        "run with meter_container_env.docker_meter_args() (bind-mounts "
        "~/Audioura/meterlogs -> /meterlogs, sets the canonical PAID_API_LOG and "
        "METER_SERVICE=<task id>), or set METER_MOUNT_GUARD=0 for a deliberate "
        "no-mount diagnostic." % log_dir)


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
                check_task_budget()
                check_task_budget_meter_log()
                check_meter_mount()
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
            check_task_budget()
            check_task_budget_meter_log()
            check_meter_mount()
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
                check_task_budget()
                check_task_budget_meter_log()
                check_meter_mount()
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
                check_task_budget()
                check_task_budget_meter_log()
                check_meter_mount()
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
                check_task_budget()
                check_task_budget_meter_log()
                check_meter_mount()
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
        # botocore outlives this module: a reloaded or second copy of the meter
        # would wrap it again and write N rows per call. Mark the wrapper and
        # unwrap any earlier one so there is only ever ONE meter layer.
        _orig_make_api_call = getattr(_orig_make_api_call, "_paid_meter_orig",
                                      _orig_make_api_call)

        def _make_api_call(self, operation_name, api_params):
            kind = _boto_kind(self)
            # Enforce the daily limit BEFORE the paid call (may raise the STOP, or
            # fail open). Non-paid AWS services are never checked or recorded.
            if kind:
                check_daily_limit()
                check_task_budget()
                check_task_budget_meter_log()
                check_meter_mount()
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
        _make_api_call._paid_meter_orig = _orig_make_api_call
        _bcli.BaseClient._make_api_call = _make_api_call
    except Exception:
        pass

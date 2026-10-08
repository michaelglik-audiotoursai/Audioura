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
RATE_TAG = "2026-10-08-r3"
GROUNDED_REQUEST_USD = 0.0107  # per search-enabled Gemini request; calibrated 2026-10-08 on a clean 1-tour window ($0.32 billed, 26 requests)

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

def install():
    try:
        import requests
        _orig = requests.Session.send
        def send(self, request, **kw):
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

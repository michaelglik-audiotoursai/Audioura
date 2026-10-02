"""LOCAL-560 OpenAI recording harness (TEST-TIME ONLY — no production change).

Wraps two code paths that reach api.openai.com so that, for every chat-completion
call made during tour generation, we log:

  * caller file:line  (the real application call site, skipping stdlib / this module)
  * model             (the model string actually sent on the wire)
  * messages          (full message list)
  * temperature
  * max_tokens
  * response text      (choices[0].message.content)
  * usage              (prompt/completion/total tokens, when present)
  * http status

Two wire paths exist in this codebase:
  1. raw ``requests.post("https://api.openai.com/v1/chat/completions", json=...)``
     — the overwhelming majority of call sites.
  2. the ``openai`` python client ``client.chat.completions.create(...)``
     — e.g. story_element_extractor.py.

Both are intercepted. Non-OpenAI requests.post calls pass straight through
untouched (we only record when the URL host is api.openai.com).

API keys are NEVER written: Authorization headers are dropped and any obvious
``sk-`` token in recorded text is redacted before it is written.

Usage (import, then call install() BEFORE importing generate_tour_text):

    import openai_recorder
    rec = openai_recorder.install("recordings/mytour.jsonl")
    ...run generation...
    rec.uninstall()

Each record is appended as one JSON line. The file is flushed per call so a
crash mid-tour still leaves a usable partial recording.
"""
import json
import os
import re
import threading
import time
import traceback

_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

# files whose frames we skip when attributing a call site to application code
_SKIP_SUBSTRINGS = (
    "openai_recorder.py",
    "/requests/",
    "/urllib3/",
    "/http/client",
    "/openai/",            # openai client internals
    "/ssl.py",
    "site-packages/openai",
)


def _redact(obj):
    """Recursively redact sk- tokens from strings in a JSON-able structure."""
    if isinstance(obj, str):
        return _SK_RE.sub("sk-REDACTED", obj)
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items() if k.lower() != "authorization"}
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


def _caller_site():
    """Return 'file.py:lineno' for the nearest application frame."""
    for frame in reversed(traceback.extract_stack()[:-1]):
        fn = frame.filename
        if any(s in fn for s in _SKIP_SUBSTRINGS):
            continue
        return f"{os.path.basename(fn)}:{frame.lineno}"
    # fallback: outermost frame
    st = traceback.extract_stack()
    return f"{os.path.basename(st[0].filename)}:{st[0].lineno}"


class Recorder:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()
        self.count = 0
        self._orig_requests_post = None
        self._orig_chat_create = None

    # ---- recording -------------------------------------------------------
    def _write(self, record):
        record = _redact(record)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()
            self.count += 1

    # ---- requests.post path ---------------------------------------------
    def _extract_body(self, args, kwargs):
        """Return the request body dict regardless of how it was passed.

        Call sites use either ``json={...}`` (parsed dict) or
        ``data=json.dumps({...})`` (a JSON string). Both carry the same fields
        (model, messages, temperature, max_tokens); we normalise to a dict.
        """
        if kwargs.get("json") is not None:
            b = kwargs["json"]
            return b if isinstance(b, dict) else {}
        d = kwargs.get("data")
        if d is not None:
            try:
                parsed = json.loads(d) if isinstance(d, (str, bytes)) else d
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _patched_requests_post(self, url, *args, **kwargs):
        is_openai = isinstance(url, str) and "api.openai.com" in url and "chat/completions" in url
        if not is_openai:
            return self._orig_requests_post(url, *args, **kwargs)

        site = _caller_site()
        body = self._extract_body(args, kwargs)
        t0 = time.time()
        resp = self._orig_requests_post(url, *args, **kwargs)
        dt = time.time() - t0

        rec = {
            "path": "requests.post",
            "site": site,
            "ts": round(t0, 3),
            "latency_s": round(dt, 3),
            "model": body.get("model"),
            "temperature": body.get("temperature"),
            "max_tokens": body.get("max_tokens"),
            "messages": body.get("messages"),
            "response_format": body.get("response_format"),
            "status": getattr(resp, "status_code", None),
        }
        try:
            j = resp.json()
            rec["response_text"] = j.get("choices", [{}])[0].get("message", {}).get("content")
            rec["usage"] = j.get("usage")
            rec["actual_model"] = j.get("model")
        except Exception as e:  # pragma: no cover
            rec["response_text"] = None
            rec["parse_error"] = f"{type(e).__name__}: {e}"
        self._write(rec)
        return resp

    # ---- openai client path ---------------------------------------------
    def _patched_chat_create(self, *args, **kwargs):
        site = _caller_site()
        t0 = time.time()
        resp = self._orig_chat_create(*args, **kwargs)
        dt = time.time() - t0
        rec = {
            "path": "openai.client",
            "site": site,
            "ts": round(t0, 3),
            "latency_s": round(dt, 3),
            "model": kwargs.get("model"),
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
            "messages": kwargs.get("messages"),
            "response_format": kwargs.get("response_format"),
            "status": 200,
        }
        try:
            rec["response_text"] = resp.choices[0].message.content
            u = getattr(resp, "usage", None)
            if u is not None:
                rec["usage"] = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
            rec["actual_model"] = getattr(resp, "model", None)
        except Exception as e:  # pragma: no cover
            rec["response_text"] = None
            rec["parse_error"] = f"{type(e).__name__}: {e}"
        self._write(rec)
        return resp

    # ---- install / uninstall --------------------------------------------
    def install(self):
        import requests
        self._orig_requests_post = requests.post
        requests.post = self._patched_requests_post

        # Patch the openai client's chat.completions.create at the class level so
        # every client instance (created before or after) is covered.
        try:
            import openai
            from openai.resources.chat.completions import Completions
            self._orig_chat_create = Completions.create
            _recorder = self

            def _wrapper(self_inner, *a, **k):
                return _recorder._patched_chat_create_bound(self_inner, *a, **k)

            Completions.create = _wrapper
            self._Completions = Completions
        except Exception:
            self._Completions = None
        return self

    def _patched_chat_create_bound(self, completions_self, *args, **kwargs):
        site = _caller_site()
        t0 = time.time()
        resp = self._orig_chat_create(completions_self, *args, **kwargs)
        dt = time.time() - t0
        rec = {
            "path": "openai.client",
            "site": site,
            "ts": round(t0, 3),
            "latency_s": round(dt, 3),
            "model": kwargs.get("model"),
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
            "messages": kwargs.get("messages"),
            "status": 200,
        }
        try:
            rec["response_text"] = resp.choices[0].message.content
            u = getattr(resp, "usage", None)
            if u is not None:
                rec["usage"] = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
            rec["actual_model"] = getattr(resp, "model", None)
        except Exception as e:  # pragma: no cover
            rec["response_text"] = None
            rec["parse_error"] = f"{type(e).__name__}: {e}"
        self._write(rec)
        return resp

    def uninstall(self):
        if self._orig_requests_post is not None:
            import requests
            requests.post = self._orig_requests_post
        if self._orig_chat_create is not None and getattr(self, "_Completions", None):
            self._Completions.create = self._orig_chat_create
        try:
            self._fh.close()
        except Exception:
            pass


def install(path):
    return Recorder(path).install()

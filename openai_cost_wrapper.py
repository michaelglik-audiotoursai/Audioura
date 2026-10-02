"""
Single OpenAI HTTP choke point — every chat-completion call is priced here.
=============================================================================
[LOCAL-562]

The problem this solves
-----------------------
There are 77 OpenAI call sites across 44 files. Only ~5 of them (inside
``generate_tour_text``) ever added their cost to the per-tour total; the other
~70 (gates, extractors, writers in other modules) were invisible to the ledger,
so OpenAI was undercounted ~3x. Chasing every call site is a losing game — new
ones appear with every feature.

Instead we count at the ONE place every call must pass through: the HTTP request
to ``api.openai.com``. There are exactly two wire paths in this codebase (the
LOCAL-560 recorder documents both):

  1. raw ``requests.post("https://api.openai.com/v1/chat/completions", ...)``
     — the overwhelming majority of call sites.
  2. the ``openai`` python client ``client.chat.completions.create(...)``
     — e.g. story_element_extractor.py.

``install()`` monkey-patches both. For every OpenAI chat-completion response it
reads ``usage`` (prompt/completion tokens) and the model actually on the wire,
prices it with ``cost_rates`` via the per-tour accumulator
(``cost_accumulator.add_llm_usage``), and lets the response through untouched.

What it does NOT do
-------------------
* It does not change any request — same URL, same body, same model. Model choice
  is untouched (LOCAL-562 "Must not": do not change any model choice).
* Non-OpenAI ``requests.post`` calls (Polly service, Gemini, internal services)
  pass straight through without inspection.
* Outside a ``cost_accumulator.tour_scope`` it is a pure pass-through: usage is
  not attributed anywhere (``add_llm_usage`` is a no-op with no active scope).
* It never reads or logs API keys.

Idempotent: calling ``install()`` twice is safe (it detects its own patch and
does nothing). ``uninstall()`` restores the originals.

Thread-safety: the patch itself is installed once at process start. Attribution
is per-tour via the ContextVar in ``cost_accumulator`` — concurrent tours each
land in their own accumulator with no cross-talk.
"""

from __future__ import annotations

import json
import logging
import threading

import cost_accumulator

_log = logging.getLogger(__name__)

_OPENAI_HOST = "api.openai.com"
_CHAT_PATH = "chat/completions"

_install_lock = threading.Lock()
_state = {
    "installed": False,
    "orig_requests_post": None,
    "orig_chat_create": None,
    "Completions": None,
}


# ─── helpers ─────────────────────────────────────────────────────────────────
def _is_openai_chat_url(url) -> bool:
    return isinstance(url, str) and _OPENAI_HOST in url and _CHAT_PATH in url


def _body_from_call(args, kwargs) -> dict:
    """Normalise the request body regardless of json=/data= passing convention."""
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
    # positional data (requests.post(url, data))
    if args:
        d0 = args[0]
        if isinstance(d0, (str, bytes)):
            try:
                parsed = json.loads(d0)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        if isinstance(d0, dict):
            return d0
    return {}


def _attribute_from_response_json(j: dict, requested_model: str) -> None:
    """Price one response's usage into the current tour accumulator.

    ``model`` on the wire is preferred from the response body (``actual_model``),
    falling back to the requested model, so a gpt-4o call is never priced at mini
    rates. Robust to missing usage (streaming / errors): no usage => no charge.
    """
    try:
        usage = j.get("usage") or {}
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        if pt is None and ct is None:
            return
        model = j.get("model") or requested_model
        cost_accumulator.add_llm_usage(
            input_tokens=pt or 0,
            output_tokens=ct or 0,
            model=model,
        )
    except Exception as e:  # pragma: no cover - never break a real call over metering
        _log.warning("[LOCAL-562] cost attribution skipped: %s: %s", type(e).__name__, e)


# ─── requests.post path ──────────────────────────────────────────────────────
def _patched_requests_post(url, *args, **kwargs):
    orig = _state["orig_requests_post"]
    if not _is_openai_chat_url(url):
        return orig(url, *args, **kwargs)

    body = _body_from_call(args, kwargs)
    requested_model = body.get("model") if isinstance(body, dict) else None
    resp = orig(url, *args, **kwargs)
    # Only price successful completions with a parseable body.
    try:
        if getattr(resp, "status_code", None) == 200:
            j = resp.json()
            _attribute_from_response_json(j, requested_model)
    except Exception as e:  # pragma: no cover
        _log.warning("[LOCAL-562] requests.post metering skipped: %s", e)
    return resp


# ─── openai client path ──────────────────────────────────────────────────────
def _patched_chat_create(completions_self, *args, **kwargs):
    orig = _state["orig_chat_create"]
    requested_model = kwargs.get("model")
    resp = orig(completions_self, *args, **kwargs)
    try:
        u = getattr(resp, "usage", None)
        if u is not None:
            pt = getattr(u, "prompt_tokens", None)
            ct = getattr(u, "completion_tokens", None)
            model = getattr(resp, "model", None) or requested_model
            if pt is not None or ct is not None:
                cost_accumulator.add_llm_usage(
                    input_tokens=pt or 0,
                    output_tokens=ct or 0,
                    model=model,
                )
    except Exception as e:  # pragma: no cover
        _log.warning("[LOCAL-562] openai-client metering skipped: %s", e)
    return resp


# ─── install / uninstall ─────────────────────────────────────────────────────
def install() -> bool:
    """Patch both OpenAI wire paths to feed the per-tour accumulator.

    Idempotent and safe to call at import/startup. Returns True if the patch is
    active after the call.
    """
    with _install_lock:
        if _state["installed"]:
            return True

        import requests
        _state["orig_requests_post"] = requests.post
        requests.post = _patched_requests_post

        # Patch openai client at the class level so every client instance (made
        # before or after) is covered. Optional dependency: if openai is not
        # importable, the requests.post path still covers the majority of calls.
        try:
            from openai.resources.chat.completions import Completions
            _state["orig_chat_create"] = Completions.create

            def _wrapper(self_inner, *a, **k):
                return _patched_chat_create(self_inner, *a, **k)

            Completions.create = _wrapper
            _state["Completions"] = Completions
        except Exception:
            _state["Completions"] = None

        _state["installed"] = True
        _log.info("[LOCAL-562] OpenAI cost choke point installed")
        return True


def uninstall() -> None:
    """Restore the original ``requests.post`` and openai client (for tests)."""
    with _install_lock:
        if not _state["installed"]:
            return
        if _state["orig_requests_post"] is not None:
            import requests
            requests.post = _state["orig_requests_post"]
            _state["orig_requests_post"] = None
        if _state["orig_chat_create"] is not None and _state["Completions"] is not None:
            _state["Completions"].create = _state["orig_chat_create"]
        _state["orig_chat_create"] = None
        _state["Completions"] = None
        _state["installed"] = False
        _log.info("[LOCAL-562] OpenAI cost choke point uninstalled")


def is_installed() -> bool:
    return _state["installed"]

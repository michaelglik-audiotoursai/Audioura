#!/usr/bin/env python3
"""
test_local782_header_redaction.py — LOCAL-782 guard + unit tests
================================================================

Two independent questions:

  1. UNIT: does safe_headers() actually redact the secret headers (showing only
     the last 4 chars) while leaving ordinary headers untouched?

  2. GUARD (AST): does any shipped service module still log the *whole* header
     set -- print/log of ``dict(request.headers)`` or of ``request.headers``
     directly -- without first passing it through ``safe_headers``? Logging the
     raw mapping is what shipped X-Api-Key to Cloud Logging (LOCAL-782 evidence:
     map_delivery_service.py / map_delivery/app.py), so that pattern must not
     reappear anywhere.

Written red-first: before the fix both the unit test (no module) and the guard
(raw dict(request.headers) in the services) fail.

Run with pytest, or directly:
    python3 test_local782_header_redaction.py
"""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))

# Shipped service modules that log incoming requests and were cited in the
# LOCAL-782 evidence (or share the identical before_request logger).
SERVICE_FILES = [
    "map_delivery_service.py",
    os.path.join("map_delivery", "app.py"),
    "tour_orchestrator_service.py",
    os.path.join("coordinates_fromAI", "app.py"),
]


# ───────────────────────── unit tests: the helper ──────────────────────────

def _load_safe_headers():
    import importlib
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    mod = importlib.import_module("safe_headers")
    importlib.reload(mod)
    return mod.safe_headers


def test_redacts_x_api_key_last4():
    safe_headers = _load_safe_headers()
    out = safe_headers({"X-Api-Key": "supersecret1234"})
    assert out["X-Api-Key"] == "…1234"
    assert "supersecret" not in out["X-Api-Key"]


def test_redacts_authorization_cookie_and_tokens():
    safe_headers = _load_safe_headers()
    out = safe_headers(
        {
            "Authorization": "Bearer abcdefTAIL",
            "Cookie": "session=longvalueWXYZ",
            "Set-Cookie": "a=b; secure=zzzz",
            "X-Goog-Iap-Jwt-Assertion": "jwtvalueABCD",
            "X-Purchase-Token": "receipt-token-9876",
            "Some-Secret": "hidden-vvvv",
        }
    )
    assert out["Authorization"] == "…TAIL"
    assert out["Cookie"] == "…WXYZ"
    assert out["Set-Cookie"] == "…zzzz"
    assert out["X-Goog-Iap-Jwt-Assertion"] == "…ABCD"
    assert out["X-Purchase-Token"] == "…9876"
    assert out["Some-Secret"] == "…vvvv"


def test_preserves_non_sensitive_headers():
    safe_headers = _load_safe_headers()
    out = safe_headers(
        {
            "User-Agent": "Audioura/1.0",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "X-Request-ID": "abc123",
        }
    )
    assert out["User-Agent"] == "Audioura/1.0"
    assert out["Content-Type"] == "application/json"
    assert out["Accept"] == "*/*"
    assert out["X-Request-ID"] == "abc123"


def test_accepts_header_pair_iterable():
    """Flask's request.headers is an iterable of (k, v) pairs, not a dict."""
    safe_headers = _load_safe_headers()
    out = safe_headers([("X-Api-Key", "pairsecretPQRS"), ("Accept", "*/*")])
    assert out["X-Api-Key"] == "…PQRS"
    assert out["Accept"] == "*/*"


def test_short_secret_fully_hidden():
    safe_headers = _load_safe_headers()
    out = safe_headers({"X-Api-Key": "abcd"})
    assert "abcd" not in out["X-Api-Key"]


# ───────────────────────── guard test: the services ────────────────────────

def _is_request_headers_attr(node):
    """True if node is exactly the ``request.headers`` attribute access."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "headers"
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
    )


def _whole_header_nodes(root):
    """Yield AST nodes under ``root`` that use the ENTIRE header mapping.

    Counts:
      * ``dict(request.headers)`` — the dict() call node, and
      * a bare ``request.headers`` used as a value (f-string field, assignment,
        argument) — but NOT ``request.headers.get(...)`` or
        ``request.headers['X']`` where only one header is read.

    To distinguish, we record every ``request.headers`` node that is the
    ``.value`` of an enclosing Attribute (``.get``) or Subscript receiver;
    those are single-header reads and are excluded.
    """
    receiver_nodes = set()
    for node in ast.walk(root):
        if isinstance(node, ast.Attribute) and _is_request_headers_attr(node.value):
            receiver_nodes.add(id(node.value))  # request.headers.<attr>
        if isinstance(node, ast.Subscript) and _is_request_headers_attr(node.value):
            receiver_nodes.add(id(node.value))  # request.headers[...]

    for node in ast.walk(root):
        # dict(request.headers)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dict"
            and len(node.args) == 1
            and _is_request_headers_attr(node.args[0])
        ):
            yield node
        # bare request.headers used as a whole mapping
        elif _is_request_headers_attr(node) and id(node) not in receiver_nodes:
            yield node


def _find_raw_header_logs(path):
    """Return a list of 'file:line' where a print/log dumps all headers raw.

    A call to safe_headers(request.headers) is the sanctioned form and is NOT
    flagged (the Name/Attribute walk still sees request.headers, so we exclude
    any argument whose top node is a safe_headers(...) call).
    """
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    LOG_FUNCS = {"print"}
    LOG_METHODS = {"info", "debug", "warning", "error", "exception", "log"}
    offenders = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_log = (isinstance(func, ast.Name) and func.id in LOG_FUNCS) or (
            isinstance(func, ast.Attribute) and func.attr in LOG_METHODS
        )
        if not is_log:
            continue
        for arg in node.args:
            if _logs_raw_headers(arg):
                offenders.append(f"{os.path.relpath(path, ROOT)}:{arg.lineno}")
    return offenders


def _logs_raw_headers(arg):
    """True if ``arg`` embeds the whole header set NOT wrapped in safe_headers."""
    # Every whole-header node that is an argument to safe_headers(...) is OK.
    safe_nodes = set()
    for sub in ast.walk(arg):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "safe_headers"
        ):
            for a in sub.args:
                for inner in _whole_header_nodes(a):
                    safe_nodes.add(id(inner))

    for node in _whole_header_nodes(arg):
        if id(node) not in safe_nodes:
            return True
    return False


@pytest.mark.parametrize("rel", SERVICE_FILES)
def test_no_service_logs_raw_headers(rel):
    path = os.path.join(ROOT, rel)
    assert os.path.exists(path), f"missing service file: {rel}"
    offenders = _find_raw_header_logs(path)
    assert not offenders, (
        "Service logs the raw header set (leaks X-Api-Key/Authorization/etc). "
        "Wrap with safe_headers(request.headers): " + ", ".join(offenders)
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))

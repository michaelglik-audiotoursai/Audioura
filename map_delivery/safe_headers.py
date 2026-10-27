#!/usr/bin/env python3
"""
[LOCAL-782] Shared header-redaction helper.

Services log incoming request headers to Cloud Logging for debugging. Those
headers carry secrets - the client's X-Api-Key, Authorization bearer tokens,
Cookie/Set-Cookie, Google service auth (X-Goog-*), and app-specific purchase
tokens. The key ships inside the app anyway, but it must not sit in logs.

`safe_headers(headers)` returns a plain dict safe to print: sensitive values are
replaced with a redacted marker that keeps only the last 4 characters so a log
line still distinguishes "no key" from "wrong key" without disclosing the secret.

This module is intentionally dependency-free (stdlib only) so every service
image can copy the single file. A service whose image does not ship this module
should inline the 5-line equivalent (see the SENSITIVE check below).
"""

# Exact header names that always carry a secret (compared case-insensitively).
_SENSITIVE_EXACT = frozenset(
    h.lower()
    for h in (
        "X-Api-Key",
        "Authorization",
        "Proxy-Authorization",
        "Cookie",
        "Set-Cookie",
        "X-Attestation-Token",
        "X-App-Attestation",
    )
)

# Substrings that mark a header as sensitive wherever they appear in the name
# (case-insensitive): any token/secret/key header, plus Google auth (X-Goog-*).
_SENSITIVE_SUBSTRINGS = ("token", "secret", "key", "x-goog-", "password", "auth")

_REDACTED = "…redacted"


def is_sensitive(name):
    """Return True if a header name must be redacted."""
    if not name:
        return False
    low = str(name).lower()
    if low in _SENSITIVE_EXACT:
        return True
    return any(marker in low for marker in _SENSITIVE_SUBSTRINGS)


def redact_value(value):
    """Redact a single value, keeping only its last 4 characters as '…abcd'."""
    if value is None:
        return _REDACTED
    text = str(value)
    if len(text) <= 4:
        # Too short to reveal a usable tail; hide it entirely.
        return _REDACTED
    return "…" + text[-4:]


def safe_headers(headers):
    """Return a plain dict of headers with sensitive values redacted.

    Accepts a Werkzeug/Flask ``request.headers`` (an iterable of (key, value)
    pairs), a plain dict, or anything dict() can consume. Non-sensitive headers
    are passed through unchanged; sensitive ones show only their last 4 chars.
    """
    if headers is None:
        return {}
    try:
        items = dict(headers).items()
    except (TypeError, ValueError):
        items = list(headers)
    out = {}
    for key, value in items:
        out[key] = redact_value(value) if is_sensitive(key) else value
    return out

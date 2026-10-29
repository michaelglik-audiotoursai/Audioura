"""Check the paid services BEFORE spending a batch on them.

2026-09-22: a six-tour batch lost five tours and ~20 minutes to an OpenAI account
with no credits left. Every failure was per-call, discovered one stop at a time,
and the backoff added that morning made it worse — 125s of waiting per stop before
giving up. **Nothing checked the account first.** Two seconds of probing would have
said so before a single tour started.

Also records what today taught about probing the WRONG thing: `gemini-2.5-flash`
returns a deprecation 404 while the code's `gemini-flash-latest` is fine, and the
Serper key is `SERP_API_KEY`, not `SERPER_API_KEY`. A pre-flight that lies about a
healthy service is worse than none, so each probe here uses exactly what the
production code uses.
"""

import json
import os
import urllib.error
import urllib.request

GEMINI_MODEL = 'gemini-flash-latest'      # what story_leads actually calls
TIMEOUT = 20


# ── LOCAL-814B: feed the Gemini probe result into the process-wide breaker ─────
# The Gemini probe is a KEY-HEALTH check: it must ALWAYS run (it is the thing that
# detects "OUT OF CREDITS"), so it is NOT gated by the breaker. But when the probe
# itself gets a 402/429 that is authoritative account state, so it trips the
# breaker — a batch that starts after a failed probe then skips Gemini from the
# first stop instead of re-discovering the 402 on the first real call. Imported
# softly and fail-open: a missing/broken breaker never breaks the probe.
def _gemini_breaker_record(status_code, body=''):
    try:
        import gemini_breaker
        gemini_breaker.record_failure(int(status_code), body or '')
    except Exception:
        pass


def _quota_from_headers(headers):
    """Surface whatever the service says about what is left.

    Serper returns x-ratelimit-limit / -remaining / -reset on every call, so the
    number is free — we were throwing it away and reporting a bare "OK". OpenAI
    sends x-ratelimit-remaining-requests/-tokens. Neither is a CREDIT BALANCE;
    those live only on the billing dashboards.
    """
    rem = (headers.get('x-ratelimit-remaining')
           or headers.get('x-ratelimit-remaining-requests'))
    lim = (headers.get('x-ratelimit-limit')
           or headers.get('x-ratelimit-limit-requests'))
    if rem and lim:
        return f'{rem}/{lim} left in this window'
    if rem:
        return f'{rem} left in this window'
    return ''


def _probe(req):
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT)
        q = _quota_from_headers(r.headers)
        return True, (f'HTTP {r.status}' + (f' — {q}' if q else ''))
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if 'insufficient_quota' in body or 'credit_balance_exhausted' in body:
            return False, 'OUT OF CREDITS — add funds before running a batch'
        if e.code == 429:
            return False, 'rate limited (transient)'
        if e.code in (401, 403):
            return False, f'auth rejected (HTTP {e.code}) — check the key'
        return False, f'HTTP {e.code}: {body[:120]}'
    except Exception as e:
        return False, f'{type(e).__name__}: {str(e)[:100]}'


def check_openai():
    k = os.environ.get('OPENAI_API_KEY')
    if not k:
        return False, 'OPENAI_API_KEY missing from the environment'
    return _probe(urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=json.dumps({'model': 'gpt-4o',
                         'messages': [{'role': 'user', 'content': 'ok'}],
                         'max_tokens': 1}).encode(),
        headers={'Authorization': 'Bearer ' + k, 'Content-Type': 'application/json'}))


def check_gemini():
    k = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not k:
        return False, 'GEMINI_API_KEY missing from the environment'
    req = urllib.request.Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{GEMINI_MODEL}:generateContent?key={k}',
        data=json.dumps({'contents': [{'parts': [{'text': 'ok'}]}]}).encode(),
        headers={'Content-Type': 'application/json'})
    ok, msg = _probe(req)
    # [LOCAL-814B] A failed Gemini probe carries authoritative account state. If
    # it was a 402 (credit) or 429 (rate limit), trip the process-wide breaker so
    # the batch that follows skips Gemini from the first stop. The probe itself is
    # never gated by the breaker — it is the detector, so it always runs. Parsed
    # from the probe's own message, which already names the HTTP status and the
    # "OUT OF CREDITS" refusal; fail-open.
    if not ok:
        low = (msg or '').lower()
        if 'out of credits' in low or 'http 402' in low or '402' in low:
            _gemini_breaker_record(402, msg or '')
        elif 'rate limited' in low or 'http 429' in low or '429' in low:
            _gemini_breaker_record(429, msg or '')
    return ok, msg


def check_serper():
    k = os.environ.get('SERP_API_KEY')      # NOT SERPER_API_KEY — see the docstring
    if not k:
        return False, 'SERP_API_KEY missing from the environment'
    # [LOCAL-707] This probe spends one real Serper credit, so it must be metered
    # like every other Serper call. Route it through the guaranteed-metered door
    # (serper_meter.serper_post writes one paid_api_calls row regardless of the
    # network patch state). The header-based quota line is dropped (serper_post
    # returns status + body, not headers), which is acceptable for a probe.
    try:
        from serper_meter import serper_post
        status, body = serper_post(
            'https://google.serper.dev/search', {'q': 'ok'},
            api_key=k, timeout=TIMEOUT)
    except Exception as e:
        return False, f'{type(e).__name__}: {str(e)[:100]}'
    if status == 200:
        return True, 'HTTP 200'
    btxt = ''
    try:
        btxt = (body or b'').decode('utf-8', 'replace')[:300]
    except Exception:
        pass
    if 'insufficient_quota' in btxt or 'credit_balance_exhausted' in btxt:
        return False, 'OUT OF CREDITS — add funds before running a batch'
    if status == 429:
        return False, 'rate limited (transient)'
    if status in (401, 403):
        return False, f'auth rejected (HTTP {status}) — check the key'
    return False, f'HTTP {status}: {btxt[:120]}'


CHECKS = (('OpenAI', check_openai), ('Gemini', check_gemini), ('Serper', check_serper))


def preflight(required=('OpenAI', 'Gemini')):
    """Return (ok, rows). `ok` is False if any REQUIRED service is unusable.

    Serper is probed but not required — a tour degrades without it; it cannot be
    written at all without OpenAI or Gemini.
    """
    rows, ok = [], True
    for name, fn in CHECKS:
        good, detail = fn()
        rows.append((name, good, detail))
        if not good and name in required:
            ok = False
    return ok, rows


if __name__ == '__main__':
    import sys
    ok, rows = preflight()
    for name, good, detail in rows:
        print(f"  {name:<8} {'OK ' if good else 'DOWN'}  {detail}")
    print('\nREADY' if ok else '\nDO NOT RUN A BATCH — a required service is unusable')
    sys.exit(0 if ok else 1)

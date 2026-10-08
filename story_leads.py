#!/usr/bin/env python3
"""story_leads.py — ask a model what happened, then go and check it.

D438/D439. The order we had was: retrieve, then write. That loses, because a
keyword query has to get lucky. We retrieved "Miró decided to destroy the
lithographs" once and a near-identical query minutes later did not return it —
with the answer already in hand.

This inverts it:

    1. LEAD      ask a model for specific, dated, checkable events
    2. VERIFY    search each claim on its own — narrow, repeatable
    3. KEEP      only what a source confirms; everything else is dropped

A model's answer is a HYPOTHESIS. It is evidence for nothing. That is the same
CLAIMED-vs-GROUNDED line D435 drew for matrix slots, applied to prose.

CROSS-MODEL DISAGREEMENT IS A FABRICATION DETECTOR
--------------------------------------------------
Michael put one question to Meta.AI and Google. Meta said the 1971 edition
followed a DESTROYED 1967 printing; Google said it was four years of patient
technical work. They cannot both be right, and the disagreement is what sent LEAD
to the sources — which backed Meta. One model answering fluently proves nothing;
two models independently proposing the same dated event is real signal.

So providers are pluggable and the runner will use every one it has a key for.

    python3 story_leads.py --subject "Joan Miró" \\
        --work "Le Lézard aux plumes d'or" --venue "Museum of Fine Arts, Boston"
"""
import argparse
import json
import os
import re
import sys
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# [D549] A convenience, not a requirement. This unconditional open() raised
# FileNotFoundError at IMPORT TIME inside the container, where `.env` is
# correctly excluded by .dockerignore because secrets do not belong in an image.
# Every caller wrapping `from story_leads import ...` in a try/except therefore
# lost Gemini silently and fell back to OpenAI — which is why Gemini worked in
# every host test and had NEVER ONCE run in production. The container already
# receives its keys through the compose environment; the file is only needed
# when running from a shell that has not exported them.
_envfile = os.path.join(HERE, '.env')
if os.path.exists(_envfile):
    with open(_envfile) as _fh:
        for _l in _fh:
            _l = _l.strip()
            if _l and not _l.startswith('#') and '=' in _l:
                _k, _v = _l.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from story_opportunity_scan import _fold, _STAKES, _AGENCY_VERB   # noqa: E402


LEAD_PROMPT = """\
You are helping a museum audio tour find TRUE, CHECKABLE events.

Subject: {subject}
Work / place: {work}
Venue: {venue}

List up to 6 specific events involving the subject and this work. Each must be a
single concrete happening a researcher could confirm or refute — a decision, a
refusal, a destruction, a death, a meeting, a sale, a delay.

Rules:
- One event per line, no numbering, no commentary.
- Include a year whenever you know it.
- NO interpretation, NO significance, NO "this reflects" or "this symbolises",
  NO psychological states, NO predictions.
- If you are unsure whether something happened, include it anyway — it will be
  checked. Do NOT hedge with "may have" or "possibly"; state it plainly so it can
  be tested and thrown out.

Format each line as:
YEAR | what happened, in one clause
"""


# ── grounding request + query counters [LOCAL-533, LOCAL-594] ────────────────
# Google Search grounding was invisible in the pipeline's "Total API cost" line
# (that sums OpenAI only). Every grounded request in the live pipeline flows
# through the two functions below (_gemini(grounded=True) and
# gemini_with_sources(grounded=True)) — they are the only two sites that attach
# the `google_search` tool.
#
# [LOCAL-594] WHAT GOOGLE ACTUALLY BILLS. The request counter LOCAL-533 added was
# priced at a flat $0.035/request, which did not match Michael's bill. Google's
# invoice SKU is "Generate content search query gemini 3 paid" and it is measured
# in SEARCH QUERIES, not requests: on 2026-10-05 it was 1,653 queries for $23.14,
# i.e. ~$14 per 1,000 queries. The pricing page
#   https://ai.google.dev/gemini-api/docs/pricing  (read 2026-10-06)
# lists "Grounding with Google Search: 5,000 free search requests per month, then
# $14 per 1,000 requests" — but a single grounded REQUEST can issue SEVERAL search
# queries, which the response reports in `groundingMetadata.webSearchQueries`.
# Billing follows the queries (that is the invoice line), so we count BOTH: the
# request (for the per-request cap LOCAL-594 enforces) and the queries actually
# issued (for the dollar figure Michael sees). We increment at the exact moment a
# grounded HTTP request is ISSUED (after the API key check, so a keyless no-op is
# not counted, and only when grounded=True), and add the response's query count
# when the response is parsed. Pricing lives in cost_rates; this module only
# counts. A caller (generate_tour_text) resets the counters at the start of a
# generation and reads them at the end.
# [LOCAL-631] These two grounding counters are PER-JOB: generate_tour_text
# resets them at the start of a generation and reads them at the end (they feed
# the cache-path _LAST_GENERATION_COST grounding line). As plain module globals
# they were shared by every concurrent job thread, so one tour's grounded-query
# count leaked into another's cost ledger. They are now job-scoped via contextvars
# (fresh per service job-thread). Public API (reset/get) is unchanged.
import job_scoped_state as _jss
_J = _jss.attach_to_module(__name__, {
    "_GROUNDING_REQUESTS": lambda: 0,
    "_GROUNDING_QUERIES": lambda: 0,
})

# [LOCAL-613] Per-task hard spend cap for ISOLATED test runs.
# ----------------------------------------------------------------------------
# $14 of Gemini was burned overnight by ~20 Kiro tasks' isolated live runs with
# no ledger rows and no cap. From now on an isolated run installs a cap guard
# (tests/live_run_meter.install_grounding_cap) which registers a callback here.
# This module is where every billable Gemini search query is counted, so this is
# the one place that can stop a run the instant it would cross the line — the
# ticket's requirement that the cap be "enforced by the grounding counter".
#
# The guard is OFF by default: ordinary generation (the live stack, and any run
# that does not install a cap) never sees it. Only an isolated harness that opts
# in installs it. The cap applies to ALL PROVIDERS COMBINED (openai + gemini
# grounding + gemini tokens + serper + preflight): the callback returns the
# combined running spend INCLUDING the gemini grounding counted here, and if that
# meets or exceeds the task's cap, the next grounded step raises so the run stops
# before issuing the query that would cross the line.
_GROUNDING_CAP_CALLBACK = None  # Optional[Callable[[], None]] — raises if over cap


class TestRunCapExceeded(RuntimeError):
    """[LOCAL-613] Raised at the grounding counter when a task's isolated-run
    spend cap (TEST_GEMINI_MAX_USD, all providers combined) is reached. Stops the
    run before the next grounded Gemini query is issued."""


def set_grounding_cap_callback(callback) -> None:
    """[LOCAL-613] Install (or clear, with None) the per-run cap guard.

    `callback` is a zero-arg callable invoked right before a grounded request is
    issued and right after a grounded response's queries are counted. It must
    raise (typically TestRunCapExceeded) when the combined running spend has
    reached the task cap, and return normally otherwise. Installed only by an
    isolated test harness via tests/live_run_meter.install_grounding_cap; never by
    production generation."""
    global _GROUNDING_CAP_CALLBACK
    _GROUNDING_CAP_CALLBACK = callback


def _enforce_grounding_cap() -> None:
    """Invoke the installed cap guard, if any. No-op when none is installed."""
    cb = _GROUNDING_CAP_CALLBACK
    if cb is not None:
        cb()


def reset_grounding_requests() -> None:
    """Zero the grounded-request AND grounded-query counters. Call at the start
    of a generation. (Name kept for LOCAL-533 callers; now resets both.)"""
    # [LOCAL-631] job-scoped; no `global` — these isolate per service job-thread.
    _J._GROUNDING_REQUESTS = 0
    _J._GROUNDING_QUERIES = 0


def get_grounding_requests() -> int:
    """Return the number of grounded requests issued since the last reset."""
    return _J._GROUNDING_REQUESTS


def get_grounding_queries() -> int:
    """[LOCAL-594] Return the number of Google search queries (webSearchQueries)
    issued across all grounded responses since the last reset. This is the unit
    Google's invoice bills ("Generate content search query gemini 3 paid")."""
    return _J._GROUNDING_QUERIES


def _count_grounding_request() -> None:
    """Record one grounded request actually issued. Called only from the two
    grounded-request sites, guarded by grounded=True and a present API key."""
    # [LOCAL-613] Last chance to stop BEFORE this grounded request is issued: if
    # the task's combined spend cap is already reached, raise now so the query
    # that would cross the line is never sent. No-op unless a harness installed a
    # cap guard.
    _enforce_grounding_cap()
    _J._GROUNDING_REQUESTS += 1  # [LOCAL-631] job-scoped


def _raise_if_grounding_forbidden(what: str) -> None:
    """[LOCAL-597] Raise GroundingForbiddenError if an L2 by-reference build is
    active. Lazily imports the guard so story_leads has no hard dependency on it
    (and so a build without the module simply never forbids). Any import failure
    is treated as 'not forbidden' — the guard is an extra safety net, never a new
    way for ordinary generation to break."""
    try:
        import l2_by_reference
    except Exception:
        return
    l2_by_reference._raise_if_forbidden(what)



def _meter_gemini_call(d: dict, grounded: bool) -> None:
    """[LOCAL-609] Price one Gemini response into the per-tour cost accumulator.

    Reads the token counts from ``usageMetadata`` (promptTokenCount /
    candidatesTokenCount — the Flash TOKEN channel) and the grounded search-query
    count from ``candidates[0].groundingMetadata.webSearchQueries`` (the grounding
    channel, Google's billing unit). Delegates routing (ordinary vs preflight
    bucket) to ``cost_accumulator.add_gemini_call``. A no-op when the accumulator
    module is unavailable or there is no active tour scope. NEVER raises into a
    real generation — callers wrap it, and this is defensive on top.
    """
    try:
        import cost_accumulator as _ca
    except Exception:
        return
    um = (d or {}).get('usageMetadata', {}) or {}
    # Gemini reports promptTokenCount (input) and candidatesTokenCount (output).
    # thoughtsTokenCount, when present, is billed as output too; include it so the
    # token dollars match the invoice. Missing fields default to 0.
    in_tok = int(um.get('promptTokenCount', 0) or 0)
    out_tok = int(um.get('candidatesTokenCount', 0) or 0)
    out_tok += int(um.get('thoughtsTokenCount', 0) or 0)
    num_queries = 0
    if grounded:
        try:
            cand = (d.get('candidates') or [{}])[0]
            gm = cand.get('groundingMetadata', {}) or {}
            num_queries = len(gm.get('webSearchQueries', []) or [])
        except Exception:
            num_queries = 0
    _ca.add_gemini_call(
        input_tokens=in_tok,
        output_tokens=out_tok,
        num_queries=num_queries,
        grounded=grounded,
    )


def _count_grounding_queries(web_search_queries) -> None:
    """[LOCAL-594] Record the Google search queries a grounded response reported.

    `web_search_queries` is `groundingMetadata.webSearchQueries` — the list of
    strings the engine says it searched for. Billing follows these, so we tally
    their count. Called once per grounded response, after it is parsed. A grounded
    request that returned no `webSearchQueries` (e.g. the model answered without
    searching) contributes 0 queries and so costs nothing on this channel — which
    is exactly what Google bills."""
    # [LOCAL-631] job-scoped; no `global`.
    try:
        _J._GROUNDING_QUERIES += len(web_search_queries or [])
    except TypeError:
        pass
    # [LOCAL-613] The queries just issued are now on the counter, so the combined
    # running spend the cap guard reads is current. If this response pushed the
    # task over its cap, raise now so no FURTHER grounded step runs. No-op unless
    # a harness installed a cap guard.
    _enforce_grounding_cap()


# ── providers ────────────────────────────────────────────────────────────────

def _openai(prompt: str, model: str = 'gpt-4o') -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return ''
    r = requests.post('https://api.openai.com/v1/chat/completions',
                      headers={'Authorization': f'Bearer {key}',
                               'Content-Type': 'application/json'},
                      json={'model': model, 'temperature': 0.2, 'max_tokens': 600,
                            'messages': [{'role': 'user', 'content': prompt}]},
                      timeout=60)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _gemini(prompt: str, model: str = None, grounded: bool = False) -> str:
    """Google Gemini. ~17x cheaper on input than gpt-4o, ~8x on output.

    NOTE: Gemini 2.5 retires 2026-10-16, so the default is `gemini-flash-latest`
    rather than a pinned 2.5. Michael's key (verified 2026-08-14) exposes 38
    models incl. gemini-3-flash-preview.

    `grounded=True` turns on Grounding with Google Search — the toggle that was
    already ON in Michael's AI Studio console, and the likeliest reason his Google
    answer beat ours. The model searches and cites inside the call instead of
    reciting. It does NOT replace `validate_story`: Google's "tragic mood holding
    sway over Miró's psyche" came out of a grounded console session, so grounded
    output is still a hypothesis until our own verifier checks it.
    """
    model = model or os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')
    import requests
    # [LOCAL-597] Forbidden during an L2 by-reference build (zero grounding).
    # Check BEFORE the key short-circuit so a keyless build still fails hard
    # rather than silently returning ''.
    if grounded:
        _raise_if_grounding_forbidden('grounded Gemini request (_gemini)')
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not key:
        return ''
    # [LOCAL-533] A grounded request is a billable Google-Search request; count it
    # here, where the key exists and we are about to issue it. Ungrounded calls
    # (grounded=False) are free of the per-request grounding charge and not counted.
    if grounded:
        _count_grounding_request()
    r = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
        json={'contents': [{'parts': [{'text': prompt}]}],
              # [D506] 600 was a starvation budget, and step 4 has been running
              # on it since LOCAL-488. Current Gemini models spend
              # `maxOutputTokens` on INTERNAL REASONING first: measured
              # 2026-08-22, a 600 budget produced `thoughtsTokenCount: 582`,
              # `finishReason: MAX_TOKENS` and a **56-character answer**. Every
              # step-4 call has been truncated mid-sentence, which is the real
              # reason the log has said "0 leads with cross-model agreement" on
              # every run — there was nothing to agree with.
              #
              # 4000 with thinking off: same question, `finishReason: STOP`,
              # 720 characters, and the answer contained the entire Gris /
              # Reverdy / Tériade story including the 11 lithographs and 1955.
              'generationConfig': {
                  'temperature': 0.2,
                  'maxOutputTokens': int(os.environ.get('GEMINI_MAX_TOKENS', '4000')),
                  'thinkingConfig': {'thinkingBudget': 0},
              },
              **({'tools': [{'google_search': {}}]} if grounded else {})},
        timeout=90)
    r.raise_for_status()
    d = r.json()
    # [LOCAL-609] Meter this Gemini call: Flash input/output TOKENS (always) plus
    # the grounding search QUERIES (when grounded). usageMetadata carries the token
    # counts; webSearchQueries carries the query count. Routed to the preflight
    # bucket automatically when inside a preflight_scope. Wrapped so metering never
    # breaks a real generation; no-op outside a tour cost scope.
    try:
        _meter_gemini_call(d, grounded)
    except Exception:
        pass
    try:
        cand = d['candidates'][0]
        # [LOCAL-594] Count the Google search queries this grounded response
        # reported, so the dollar meter follows Google's actual billing unit.
        # Ungrounded calls carry no groundingMetadata and add 0.
        if grounded:
            _gm = cand.get('groundingMetadata', {}) or {}
            _count_grounding_queries(_gm.get('webSearchQueries', []))
        # ALL parts, not parts[0]. A grounded response is commonly split across
        # several, so taking the first silently truncates it.
        parts = cand.get('content', {}).get('parts', [])
        return ''.join(p.get('text', '') for p in parts)
    except (KeyError, IndexError):
        return ''



def _gemini_post(model, key, prompt, grounded, timeout):
    """One Gemini generateContent POST (LEAD 2026-10-08: split out so it can be retried)."""
    return requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
        json={'contents': [{'parts': [{'text': prompt}]}],
              'generationConfig': {
                  'temperature': 0.2,
                  'maxOutputTokens': int(os.environ.get('GEMINI_MAX_TOKENS', '4000')),
                  'thinkingConfig': {'thinkingBudget': 0}},
              **({'tools': [{'google_search': {}}]} if grounded else {})},
        timeout=timeout)

def gemini_with_sources(prompt: str, model: str = None,
                        resolve: bool = True, timeout: int = 90,
                        grounded: bool = True) -> Dict:
    """[D508] Grounded Gemini, returning its SOURCES as well as its text.

    Michael, 2026-08-22: *"could you add another column to your matrix: sources,
    so I can ask Gemini for verification?"*

    A grounded response carries `groundingMetadata`, which we were discarding:

      groundingChunks    the pages it actually read — domain + redirect URI
      groundingSupports  WHICH SENTENCE came from WHICH chunk
      webSearchQueries   what it searched for

    That is per-sentence attribution from the engine itself, and it is far
    better than asking the model to write brackets: on the 37-question run only
    2 of 37 answers carried a bracketed source, while the metadata was present
    on every one and being thrown away.

    Chunk URIs are `vertexaisearch.cloud.google.com` redirects. `resolve=True`
    follows each once to recover the real URL, so a source can be opened and
    checked — which is the whole point of the column.

    Returns {'text', 'sources': [{'domain','url'}], 'supports':
    [{'text','sources':[...]}], 'queries': [...], 'error': str}.
    """
    model = model or os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')
    import requests
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    out = {'text': '', 'sources': [], 'supports': [], 'queries': [], 'error': ''}
    # [LOCAL-597] A grounded request is forbidden during an L2 by-reference build
    # (zero grounding). Check BEFORE the key short-circuit and OUTSIDE the broad
    # try/except below (which would otherwise swallow the raise into out['error']),
    # so the guard is a hard failure the build cannot miss.
    if grounded:
        _raise_if_grounding_forbidden('grounded Gemini request (gemini_with_sources)')
    if not key:
        out['error'] = 'no GEMINI_API_KEY'
        return out
    try:
        # [LOCAL-533] Count the grounded request at the point it is issued. The
        # key check above has already returned for keyless calls, so we only get
        # here when a request is actually going out. Guarded by grounded=True so
        # an explicitly ungrounded call is not charged the per-request rate.
        if grounded:
            _count_grounding_request()
        # [LEAD 2026-10-08] Retry transient overload. Bench R2 (6 concurrent tours) lost
        # 33 of 108 Gemini calls to HTTP 503 "model overloaded", and those stops got no
        # research. Up to 3 retries on 429/500/502/503/504 with 2/5/10 s (+jitter) backoff.
        # A failed attempt is not billed by Google, so the meter is unaffected.
        import random as _rnd, time as _tm
        for _attempt in range(4):
            r = _gemini_post(model, key, prompt, grounded, timeout)
            if r.status_code not in (429, 500, 502, 503, 504) or _attempt == 3:
                break
            _tm.sleep((2, 5, 10)[_attempt] + _rnd.uniform(0, 1.5))
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out

    # [LOCAL-609] Meter this Gemini call (tokens always; grounding queries when
    # grounded). Routed to preflight bucket when inside a preflight_scope — the
    # LOCAL-603 preflight flows through here (grounded=True). Wrapped; no-op
    # outside a tour cost scope.
    try:
        _meter_gemini_call(d, grounded)
    except Exception:
        pass

    try:
        cand = d['candidates'][0]
    except (KeyError, IndexError):
        out['error'] = 'no candidates'
        return out

    out['text'] = ''.join(p.get('text', '')
                          for p in cand.get('content', {}).get('parts', []))
    gm = cand.get('groundingMetadata', {}) or {}
    out['queries'] = gm.get('webSearchQueries', []) or []
    # [LOCAL-594] Count the Google search queries this grounded response reported.
    # These are Google's billing unit; grounded=False responses carry none.
    if grounded:
        _count_grounding_queries(out['queries'])

    chunks = []
    for ch in gm.get('groundingChunks', []) or []:
        web = ch.get('web', {}) or {}
        uri = web.get('uri', '') or ''
        real = uri
        if resolve and uri:
            try:
                import requests as _rq
                real = _rq.head(uri, allow_redirects=True, timeout=20).url or uri
            except Exception:
                real = uri  # the redirect still identifies the source
        chunks.append({'domain': web.get('title', ''), 'url': real})
    # De-duplicated source list, order preserved — Gemini repeats chunks.
    seen = set()
    for c in chunks:
        if c['url'] and c['url'] not in seen:
            seen.add(c['url'])
            out['sources'].append(c)

    for sup in gm.get('groundingSupports', []) or []:
        seg = (sup.get('segment', {}) or {}).get('text', '')
        idx = sup.get('groundingChunkIndices', []) or []
        out['supports'].append({
            'text': seg,
            'sources': [chunks[i] for i in idx if 0 <= i < len(chunks)],
        })
    return out


def _gemini_grounded(prompt: str) -> str:
    return _gemini(prompt, grounded=True)


PROVIDERS = {'openai': _openai, 'gemini': _gemini,
             'gemini_grounded': _gemini_grounded}


def available_providers() -> List[str]:
    out = []
    if os.environ.get('OPENAI_API_KEY'):
        out.append('openai')
    if os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'):
        out.append('gemini')
        out.append('gemini_grounded')
    return out


# ── leads ────────────────────────────────────────────────────────────────────

_YEAR = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')


def parse_leads(text: str, provider: str) -> List[Dict]:
    leads = []
    for line in (text or '').splitlines():
        line = line.strip().lstrip('-•* ').strip()
        if not line or len(line) < 12:
            continue
        year, claim = '', line
        if '|' in line:
            a, b = line.split('|', 1)
            if _YEAR.search(a):
                year, claim = _YEAR.search(a).group(1), b.strip()
        if not year:
            m = _YEAR.search(line)
            year = m.group(1) if m else ''
        leads.append({'year': year, 'claim': claim.strip(), 'provider': provider})
    return leads


def provider_family(provider: str) -> str:
    """The MODEL behind a provider name.

    [LOCAL-488] `gemini` and `gemini_grounded` are two call styles onto the same
    model. A claim proposed by both is one model answering twice, and counting it
    as cross-model agreement is counting a model as its own corroboration —
    exactly the error this module's docstring warns about ("one model answering
    fluently proves nothing"). Measured on the first live fan-out: 1 lead showed
    "agreement", and it was gemini+gemini_grounded.

    Agreement is only evidence across FAMILIES.
    """
    p = (provider or '').lower()
    if p.startswith('gemini'):
        return 'gemini'
    if p.startswith('openai') or p.startswith('gpt'):
        return 'openai'
    return p or 'unknown'


def families_agreeing(lead: Dict) -> int:
    """How many distinct model families proposed this claim."""
    provs = lead.get('providers') or [lead.get('provider')]
    return len({provider_family(p) for p in provs if p})


def merge_leads(all_leads: List[Dict]) -> List[Dict]:
    """Group near-identical claims across providers. Agreement is the signal."""
    merged: List[Dict] = []
    for l in all_leads:
        key = set(w for w in _fold(l['claim']).split() if len(w) > 4)
        hit = None
        for m in merged:
            mk = set(w for w in _fold(m['claim']).split() if len(w) > 4)
            if key and mk and len(key & mk) / max(1, min(len(key), len(mk))) >= 0.5 \
                    and (not l['year'] or not m['year'] or l['year'] == m['year']):
                hit = m
                break
        if hit:
            hit['providers'] = sorted(set(hit['providers']) | {l['provider']})
            hit['year'] = hit['year'] or l['year']
        else:
            merged.append({'year': l['year'], 'claim': l['claim'],
                           'providers': [l['provider']]})
    merged.sort(key=lambda m: (-len(m['providers']), not m['year']))
    return merged


# ── verification ─────────────────────────────────────────────────────────────

_ENTITY = re.compile(r"\b[A-ZÀ-Þ][\wà-ÿ'’\-]+(?:\s+[A-ZÀ-Þ][\wà-ÿ'’\-]+)*")


def _principal(claim: str, work: str, subject: str) -> str:
    """The named party a claim is ABOUT, when that is not the subject or the work.

    D440: `verify()` appended the work title to every query, so the TRUE claim
    "Mourlot was founded in 1852 on rue de Chabrol" was searched as
    `Joan Miró "Le Lézard aux plumes d'or" 1852 Mourlot founded…` — a query about a
    book the printing house predates by a century. It came back UNVERIFIED. A claim
    about a COLLABORATOR needs a query built around the collaborator.
    """
    known = _fold(work + ' ' + subject)
    for e in _ENTITY.findall(claim or ''):
        f = _fold(e)
        if len(f) < 4 or f in known:
            continue
        # A name already inside the subject/work is not a separate party.
        if all(tok in known.split() for tok in f.split()):
            continue
        return e
    return ''


def verify(lead: Dict, work: str, subject: str) -> Dict:
    """One narrow search per claim, two at most. This is the repeatable part."""
    from work_story_searcher import _serp_search
    terms = [w for w in re.findall(r"[A-Za-zà-ÿ'’\-]{4,}", lead['claim'])][:8]

    # Query shapes, most likely first. The work-anchored shape is right for claims
    # about the object; it is actively wrong for claims about a collaborator, so
    # when the claim names a third party we ask about THEM first. The second shape
    # is only paid for when the first finds no carrier sentence.
    q_work = f'{subject} "{work}" {lead["year"]} {" ".join(terms)}'.strip()
    principal = _principal(lead['claim'], work, subject)
    queries = [q_work]
    if principal:
        rest = [t for t in terms if _fold(t) not in _fold(principal)]
        queries.insert(0, f'"{principal}" {lead["year"]} {" ".join(rest)}'.strip())
    # The evidence must be ONE sentence carrying the claim — not content words
    # scattered across eight unrelated results. Measured 2026-08-14: the claim
    # "included in a retrospective exhibition at the MFA in 1993" was CONFIRMED
    # against an AUCTION LISTING, because 'Lézard' appeared on one page and '1993'
    # on another. Nothing anywhere mentioned a retrospective. A verifier that
    # accepts a claim no single source makes is the failure it exists to prevent.
    # THE NAMED PARTY MUST BE IN THE CARRIER SENTENCE. Measured 2026-08-14, and it
    # is the same failure as the 1993 one in a new place: Gemini claimed "Leonard
    # Woolf accompanied Dalí to meet Freud in London, 1938", and this function
    # CONFIRMED it against
    #     "Salvador Dalí met Freud in London in 1938, Freud appeared more
    #      receptive to ... Moses and Monotheism."
    # which does not mention Leonard Woolf at all. The year matched, the content
    # words matched, an agency verb was present — and the actual assertion, the
    # only part anyone would repeat to a visitor, went unchecked. Counting words
    # is not reading a sentence.
    def _carries(sn):
        f = _fold(sn or '')
        if not f:
            return False
        if lead['year'] and lead['year'] not in (sn or ''):
            return False
        if principal:
            # Surname is enough — sources write "Woolf" as often as "Leonard Woolf".
            parts = [p for p in _fold(principal).split() if len(p) > 3]
            if parts and not any(p in f for p in parts):
                return False
        need = [t for t in terms if len(t) > 4]
        hit = sum(1 for t in need if _fold(t) in f)
        return hit >= max(2, (len(need) + 1) // 2) and (
            _AGENCY_VERB.search(sn) or _STAKES.search(sn))

    asked, res, carrier, q = [], [], '', queries[0]
    for cand in queries:
        q, res = cand, _serp_search(cand)[0]
        asked.append(cand)
        carrier = next((s.get('snippet') for s in res
                        if _carries(s.get('snippet'))), '')
        if carrier:
            break

    blob = ' '.join((s.get('title', '') + ' ' + (s.get('snippet') or '')) for s in res)
    fb = _fold(blob)
    content = [t for t in terms if len(t) > 4 and _fold(t) in fb]
    year_ok = (not lead['year']) or (lead['year'] in blob)
    # Recorded for diagnosis only: a page that merely repeats the title is not
    # confirmation, so `substantive` never decides the status on its own.
    substantive = any(_AGENCY_VERB.search(s.get('snippet') or '')
                      or _STAKES.search(s.get('snippet') or '') for s in res)

    return {**lead, 'query': q, 'queries_asked': asked, 'principal': principal,
            'results': len(res),
            'matched_terms': content[:6], 'year_confirmed': year_ok,
            'substantive': substantive,
            'status': 'CONFIRMED' if carrier else 'UNVERIFIED',
            'citations': [s.get('domain', '') for s in res
                          if _carries(s.get('snippet'))][:3],
            'evidence': carrier}


def run(subject: str, work: str, venue: str, providers: List[str] = None,
        verify_top: int = 6) -> Dict:
    providers = providers or available_providers()
    prompt = LEAD_PROMPT.format(subject=subject, work=work, venue=venue)
    raw, leads = {}, []
    for p in providers:
        try:
            txt = PROVIDERS[p](prompt)
        except Exception as e:
            raw[p] = f'ERROR {type(e).__name__}: {e}'
            continue
        raw[p] = txt
        leads += parse_leads(txt, p)
    merged = merge_leads(leads)
    checked = [verify(l, work, subject) for l in merged[:verify_top]]
    return {'providers': providers, 'raw': raw, 'leads': merged, 'checked': checked}


def report(r: Dict) -> None:
    print(f"\n{'=' * 78}\nSTORY LEADS — providers: {', '.join(r['providers']) or 'NONE'}\n{'=' * 78}")
    if len(r['providers']) < 2:
        print("\n  Only one provider available. Cross-model agreement — the strongest")
        print("  signal we have — needs a second. Add GEMINI_API_KEY to .env.")
    print(f"\n  {len(r['leads'])} distinct leads proposed\n")
    for c in r['checked']:
        mark = '  OK  ' if c['status'] == 'CONFIRMED' else ' ---- '
        agree = '+'.join(c.get('providers', []))
        print(f"  [{mark}] {c['year'] or '????'}  ({agree})  {c['claim'][:78]}")
        if c['status'] == 'CONFIRMED':
            print(f"           sources: {', '.join(c['citations'])}")
            if c['evidence']:
                print(f"           {c['evidence'][:150]}")
        else:
            print(f"           {c['results']} results · year={c['year_confirmed']} "
                  f"· substantive={c['substantive']} · matched {c['matched_terms']}")
    n = sum(1 for c in r['checked'] if c['status'] == 'CONFIRMED')
    print(f"\n{'=' * 78}\n  {n} of {len(r['checked'])} leads CONFIRMED — only these may reach a story.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--subject', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--venue', default='')
    p.add_argument('--providers', nargs='*')
    p.add_argument('--verify-top', type=int, default=6)
    p.add_argument('--json', dest='as_json', action='store_true')
    p.add_argument('--out', default='')
    a = p.parse_args()
    r = run(a.subject, a.work, a.venue, a.providers, a.verify_top)
    if a.as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        report(r)
    if a.out:
        json.dump(r, open(a.out, 'w'), ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

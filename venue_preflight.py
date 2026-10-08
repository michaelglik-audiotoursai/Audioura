#!/usr/bin/env python3
"""venue_preflight.py — LOCAL-603 (D618): one grounded Gemini question BEFORE we build.

WHY THIS EXISTS
---------------
On 2026-10-06 the pipeline shipped a "tour" of **WNDR Museum Boston**, which had
PERMANENTLY CLOSED on 2026-08-30. Our own sources read a JavaScript shell, a
founder biography and a list of URLs, and never learned the one fact that mattered.
A single grounded Gemini question answers it at once — the closure date, the last
admission ($29.99 adult / $26.99 child) and the last installations. Michael:
*"to come up with a tour we just did is full embarrassment… can you fix this for
this and all other requests."*

THE RULING (D618, LEAD)
-----------------------
Every SINGLE-VENUE request (a named museum / restaurant / attraction) starts with
ONE grounded Gemini call — the *venue preflight* — costing ~$0.02–0.05 (1 request,
1–3 Google searches at $0.014 each, plus Flash tokens). That is under 3% of a
$1.50 museum tour and the only reliable early guard against the most expensive
embarrassment: a full tour of a closed place. Its answer is used two ways:

  * A GATE. If the venue is permanently closed (or temporarily closed with no
    reopen date), stop before any further spend, with an actionable refusal
    (`error_code=venue_closed`).
  * PLAN B MATERIAL. When our OWN sources (Wikidata/Wikipedia, the official site,
    Serper) give no hours, no admission, or fewer than N stops, the preflight's
    sourced facts fill the gap — each carrying its grounding source URL. Never
    unsourced.

CONTRACT
--------
    preflight(venue, city) -> dict

The call flows through the existing `story_leads.gemini_with_sources(grounded=True)`
so the LOCAL-594 meter counts it. The dict is strict JSON:

    status        : 'open' | 'temporarily_closed' | 'permanently_closed' | 'unknown'
    closed_since  : str
    address       : str
    hours         : str (with days)
    admission     : str
    current_exhibitions_or_highlights : [{title, artist?, note}]
    sources       : {<field>: [urls]}   grounding chunk URLs, per field
    grounding_sources : [{domain, url}] the de-duped source list from the call
    cached        : bool                was this answer served from the 7-day cache
    error         : str

FALSE-CLOSURE GUARD
-------------------
A false closure is the costlier mistake (it refuses a live venue). So a closed
status is only honoured when at least ONE grounding source's title/URL (or the
answer's own text) carries a closure word ("closed", "permanently closed",
"shut down", …). Otherwise the status is downgraded to `unknown` and generation
continues — absence of evidence must never refuse a tour.

L2 GUARD (D613 / LOCAL-597)
---------------------------
An L2 "by reference" build must spend ZERO on grounding. `gemini_with_sources`
raises `GroundingForbiddenError` inside that build; `preflight` lets it propagate
to its caller (the generator's L2 path never calls preflight), and `safe_preflight`
turns it into an explicit "skipped: L2" marker for callers that prefer that shape.
"""
import json
import os
import re
import threading
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))

# ── closure vocabulary ───────────────────────────────────────────────────────
# A closed STATUS from the model is only acted on when a GROUNDING SOURCE (its
# title/url) or the answer text carries one of these words. This is the D539
# lesson applied to the preflight: a rebrand carries no closure word, and a model
# can hallucinate "closed"; the source must back it. "temporarily closed" and
# "permanently closed" are matched by the single word "closed".
_CLOSURE_WORDS = re.compile(
    r'(?i)(close[ds]?|closing|closure|shut(?:\s+down|tered)?|'
    r'permanently[\s_-]+closed|temporarily[\s_-]+closed|ceased\s+operations?|'
    r'out\s+of\s+business|no\s+longer\s+(?:open|operating|in\s+business))'
)

# Statuses that STOP generation (the gate). temporarily_closed only gates when it
# carries no reopen date (handled in gate()).
_CLOSED_STATUSES = frozenset({'permanently_closed', 'temporarily_closed'})
_VALID_STATUSES = frozenset(
    {'open', 'temporarily_closed', 'permanently_closed', 'unknown'})

# 7-day cache TTL per (venue, city).
_CACHE_TTL_DAYS = int(os.environ.get('PREFLIGHT_CACHE_TTL_DAYS', '7'))

# N below which the preflight's highlights are used to top up stop candidates.
# (The caller passes its own N; this is only a module default for convenience.)
DEFAULT_MIN_STOPS = 3


# ── name folding (mirrors scope_memory / restaurant_practicals) ──────────────
def _fold(s: str) -> str:
    """Accent-fold + punctuation-strip for matching. 'Musée' == 'Musee'."""
    n = unicodedata.normalize('NFKD', (s or '').lower())
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r"[^\w\s]", ' ', n)).strip()


# ── the grounded prompt ──────────────────────────────────────────────────────
# ── the two prompts ──────────────────────────────────────────────────────────
# WHY TWO PROMPTS, ONE GROUNDED CALL. Measured against gemini-flash-latest
# (2026-10-06): a prompt that DEMANDS a JSON object makes the model answer from
# memory and NOT invoke Google Search — webSearchQueries is empty, no grounding
# chunks, and it even hallucinated WNDR's closure year as 2024. A natural-language
# question ("using Google Search, tell me …") reliably triggers 2–3 searches and
# returns 8 grounding chunks with real source URLs. So the ONE grounded call asks
# the natural-language question (this is the billable Google-Search call the
# ruling mandates and the LOCAL-594 meter counts), and a cheap UNGROUNDED second
# call turns that grounded prose into strict JSON. The grounded answer's SOURCES
# are what the closure guard checks — exactly the ">= 1 grounding source with a
# closure word" the ticket requires.
_GROUNDED_QUESTION = """\
Using Google Search, tell me the CURRENT visitor status of this venue, and cite \
your sources:

Venue: {venue}
City: {city}

Report, based on what the search returns right now:
- Is it OPEN, TEMPORARILY CLOSED (renovation/seasonal), or PERMANENTLY CLOSED? \
If closed, since when (date)?
- Its street address.
- Its opening hours, with days.
- Its admission / ticket prices.
- Up to 6 exhibitions or highlights a visitor can see NOW (title, artist if any, \
a short note).

Answer in a few short sentences grounded in the sources — do not guess; if \
something is not in the sources, say it is not stated.
"""

_EXTRACT_PROMPT = """\
Convert the following venue report into a single strict JSON object. Use ONLY \
facts stated in the report; leave a field empty (or status "unknown") if the \
report does not state it. Output the JSON object and NOTHING else.

REPORT:
{report}

JSON keys (exactly these):
{{
  "status": "open" | "temporarily_closed" | "permanently_closed" | "unknown",
  "closed_since": "<date or empty>",
  "address": "<street address or empty>",
  "hours": "<opening hours with days, or empty>",
  "admission": "<admission/ticket prices, or empty>",
  "current_exhibitions_or_highlights": [
    {{"title": "<name>", "artist": "<artist or empty>", "note": "<short clause>"}}
  ]
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# JSON parsing
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> Optional[dict]:
    """Pull the first balanced JSON object out of the model's text, strictly.

    The prompt asks for JSON only, but grounded responses sometimes wrap it in a
    ```json fence or add a trailing sentence. We find the first '{' and scan to
    its matching '}', then json.loads that span. Returns None if nothing parses —
    a parse failure is treated as `unknown`, never as a closure.
    """
    if not text:
        return None
    # Strip a code fence if present.
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    # First balanced object by brace scan.
    start = text.find('{')
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
        break
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            continue
    return None


def _norm_status(raw) -> str:
    s = _fold(str(raw or '')).replace(' ', '_')
    if s in _VALID_STATUSES:
        return s
    # tolerate 'closed' / 'permanently' / 'temporarily'
    if 'permanent' in s and 'clos' in s:
        return 'permanently_closed'
    if 'temporar' in s and 'clos' in s:
        return 'temporarily_closed'
    if s in ('closed', 'permanently', 'permanent_closed'):
        return 'permanently_closed'
    if s in ('open', 'operating', 'operational'):
        return 'open'
    return 'unknown'


def _source_urls(sources: List[Dict]) -> List[str]:
    out = []
    for s in sources or []:
        u = (s.get('url') or '').strip() if isinstance(s, dict) else ''
        if u and u not in out:
            out.append(u)
    return out


def _closure_source_present(sources: List[Dict]) -> bool:
    """True if a closure word appears in any GROUNDING SOURCE's title/url.

    [D618] The requirement is ">= 1 grounding source whose snippet/title contains
    a closure word" — so we deliberately do NOT consult the model's own answer
    text here. The model's JSON always contains the status word ("permanently_
    closed"), which would make the check vacuous; the whole point is independent
    corroboration from a SOURCE the engine actually read. A closed status with no
    such source is downgraded to unknown by the caller."""
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        blob = f"{s.get('domain', '')} {s.get('url', '')}"
        if _CLOSURE_WORDS.search(blob):
            return True
    return False


def _blank_result() -> Dict:
    return {
        'status': 'unknown',
        'closed_since': '',
        'address': '',
        'hours': '',
        'admission': '',
        'current_exhibitions_or_highlights': [],
        'sources': {},
        'grounding_sources': [],
        'cached': False,
        'error': '',
    }


def _shape_result(parsed: Optional[dict], call_sources: List[Dict],
                  call_text: str) -> Dict:
    """Build the strict preflight dict from the parsed JSON + the call's sources.

    Per-field `sources` map: the model answers one object, and the grounding
    chunks apply to the answer as a whole, so each non-empty field is attributed
    to the full de-duped source list. (gemini_with_sources also returns per-
    sentence `supports`, but a short JSON object has no sentence structure to key
    on; the whole-answer source list is the honest attribution here.)
    """
    res = _blank_result()
    res['grounding_sources'] = [
        {'domain': s.get('domain', ''), 'url': s.get('url', '')}
        for s in (call_sources or []) if isinstance(s, dict) and s.get('url')
    ]
    urls = _source_urls(call_sources)

    if not parsed:
        res['error'] = 'unparseable preflight JSON'
        return res

    res['status'] = _norm_status(parsed.get('status'))
    res['closed_since'] = str(parsed.get('closed_since', '') or '').strip()
    res['address'] = str(parsed.get('address', '') or '').strip()
    res['hours'] = str(parsed.get('hours', '') or '').strip()
    res['admission'] = str(parsed.get('admission', '') or '').strip()

    highlights = []
    for h in (parsed.get('current_exhibitions_or_highlights') or []):
        if isinstance(h, dict):
            title = str(h.get('title', '') or '').strip()
            if not title:
                continue
            highlights.append({
                'title': title,
                'artist': str(h.get('artist', '') or '').strip(),
                'note': str(h.get('note', '') or '').strip(),
            })
        elif isinstance(h, str) and h.strip():
            highlights.append({'title': h.strip(), 'artist': '', 'note': ''})
    res['current_exhibitions_or_highlights'] = highlights[:6]

    # Per-field source attribution: every field that carries a value is attributed
    # to the grounding source list (the facts came from the one grounded answer).
    field_sources = {}
    for f in ('status', 'closed_since', 'address', 'hours', 'admission'):
        if res[f]:
            field_sources[f] = list(urls)
    if highlights:
        field_sources['current_exhibitions_or_highlights'] = list(urls)
    res['sources'] = field_sources

    # [D618] False-closure guard. A closed status survives only with >= 1 closure
    # source; otherwise downgrade to unknown and let generation continue.
    if res['status'] in _CLOSED_STATUSES:
        if not _closure_source_present(call_sources):
            res['_downgraded_from'] = res['status']
            res['status'] = 'unknown'
            res['closed_since'] = ''
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 7-day DB cache  (additive table, mirrors stop_pool_store conventions)
# ─────────────────────────────────────────────────────────────────────────────
_CACHE_LOCK = threading.RLock()


def _cache_key(venue: str, city: str) -> str:
    return f"{_fold(venue)}|{_fold(city)}"


def _db_conn(db_url: str):
    import psycopg2
    return psycopg2.connect(db_url)


def _ensure_cache_table(conn) -> None:
    """Create the small additive cache table if absent. Nothing here DROPs or
    DELETEs; a stale row is simply ignored (TTL) and overwritten on refresh."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS venue_preflight_cache (
                cache_key   TEXT PRIMARY KEY,
                venue       TEXT NOT NULL,
                city        TEXT NOT NULL,
                result_json TEXT NOT NULL,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


def _cache_get(venue: str, city: str, db_url: str) -> Optional[Dict]:
    """Return a cached result if present and younger than the TTL, else None.

    Best-effort: any DB error returns None (treated as a miss, so the preflight
    simply runs). A row older than the TTL is a miss too — the facts (hours,
    status) go stale and must be refreshed."""
    if not db_url:
        return None
    try:
        with _CACHE_LOCK:
            conn = _db_conn(db_url)
            _ensure_cache_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT result_json
                    FROM venue_preflight_cache
                    WHERE cache_key = %s
                      AND fetched_at > NOW() - INTERVAL '%s days'
                    """,
                    (_cache_key(venue, city), _CACHE_TTL_DAYS),
                )
                row = cur.fetchone()
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    try:
        res = json.loads(row[0])
        if isinstance(res, dict):
            res['cached'] = True
            return res
    except (ValueError, TypeError):
        return None
    return None


def _cache_put(venue: str, city: str, result: Dict, db_url: str) -> None:
    """Upsert the result for (venue, city). Additive: the same key is UPDATEd in
    place with a fresh fetched_at. Never raises — a cache write failure must not
    fail a generation."""
    if not db_url:
        return
    # Do not persist an errored call — we want a real answer in the cache, not a
    # transient failure that would then be served for 7 days.
    if result.get('error'):
        return
    stored = dict(result)
    stored['cached'] = False  # store the canonical shape; _cache_get sets True
    try:
        with _CACHE_LOCK:
            conn = _db_conn(db_url)
            _ensure_cache_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO venue_preflight_cache
                        (cache_key, venue, city, result_json, fetched_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (cache_key) DO UPDATE SET
                        venue = EXCLUDED.venue,
                        city = EXCLUDED.city,
                        result_json = EXCLUDED.result_json,
                        fetched_at = NOW()
                    """,
                    (_cache_key(venue, city), venue, city,
                     json.dumps(stored, ensure_ascii=False)),
                )
            conn.commit()
            conn.close()
    except Exception:
        return


def cache_row_count(db_url: str) -> int:
    """Report the cache table's row count (for the submission's DB report).
    Returns -1 if the table/connection is unavailable."""
    if not db_url:
        return -1
    try:
        conn = _db_conn(db_url)
        _ensure_cache_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM venue_preflight_cache")
            n = cur.fetchone()[0]
        conn.close()
        return int(n)
    except Exception:
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# known_closed_venues recording (D539/D547 mechanism)
# ─────────────────────────────────────────────────────────────────────────────
def _known_closed_paths() -> List[str]:
    return [os.path.join(HERE, 'tests', 'known_closed_venues.json'),
            '/app/tests/known_closed_venues.json']


def already_known_closed(venue: str, city: str) -> bool:
    """True if (venue, city) is already recorded `expect: closed` in
    known_closed_venues.json — a deterministic lookup that lets the next request
    skip the grounded call entirely (D539's reliable half). Containment match on
    both name and city, mirroring restaurant_practicals.known_bad_venue."""
    corpus = []
    for cand in _known_closed_paths():
        try:
            with open(cand, encoding='utf-8') as fh:
                corpus = json.load(fh).get('venues', [])
            break
        except Exception:
            continue
    if not corpus:
        return False
    n, c = _fold(venue), _fold(city)
    for v in corpus:
        if v.get('expect') != 'closed':
            continue
        vc = _fold(v.get('city', ''))
        if c and vc and vc not in c and c not in vc:
            continue
        for cand in [v.get('name', '')] + list(v.get('aliases', [])):
            f = _fold(cand)
            if f and (f == n or f in n or n in f):
                return True
    return False


def record_confirmed_closure(venue: str, city: str, result: Dict) -> Dict:
    """Record a confirmed closure in the known_closed_venues.json mechanism so the
    NEXT request skips the preflight call (D539/D547). Mirrors scope_memory's
    contract: it always PRINTS `[PREFLIGHT] NEW CLOSED ENTRY <json>` (so LEAD can
    commit it even when the container filesystem is ephemeral), and best-effort
    appends to the on-disk corpus. Never raises; returns the entry."""
    entry = {
        'name': venue,
        'aliases': [],
        'city': city,
        'expect': 'closed',
        'closed_on': result.get('closed_since', ''),
        'found_by': 'venue_preflight (LOCAL-603 D618)',
        'ground_truth': (f"preflight status={result.get('status')} "
                         f"since {result.get('closed_since') or 'unknown'}; "
                         f"sources: {', '.join(_source_urls(result.get('grounding_sources', [])))[:200]}"),
        'recorded': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    }
    print(f"   [PREFLIGHT] NEW CLOSED ENTRY {json.dumps(entry, ensure_ascii=False)}")
    # Best-effort append to the first writable corpus path.
    for path in _known_closed_paths():
        try:
            if not os.path.exists(path):
                continue
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            venues = data.setdefault('venues', [])
            # Avoid a duplicate entry for the same (name, city).
            if any(_fold(v.get('name', '')) == _fold(venue)
                   and _fold(v.get('city', '')) == _fold(city)
                   and v.get('expect') == 'closed' for v in venues):
                return entry
            venues.append(entry)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            break
        except Exception:
            continue
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# THE PREFLIGHT CALL
# ─────────────────────────────────────────────────────────────────────────────
def preflight(venue: str, city: str = '', db_url: Optional[str] = None,
              use_cache: bool = True) -> Dict:
    """One grounded Gemini question about a single venue, BEFORE we build.

    Returns the strict preflight dict (see module docstring). The one grounded
    call goes through `story_leads.gemini_with_sources(grounded=True)`, so the
    LOCAL-594 meter counts it. A 7-day per-(venue, city) cache makes a repeat
    request free (no call). The L2 guard (`GroundingForbiddenError`) is NOT
    swallowed here — it propagates so an L2 by-reference build fails loud rather
    than silently paying for grounding; use `safe_preflight` for the "skip on L2"
    shape.

    `db_url` defaults to the DATABASE_URL env var. `use_cache=False` forces a
    fresh call (used by tests that assert the call happens)."""
    if db_url is None:
        db_url = os.environ.get('DATABASE_URL')

    venue = (venue or '').strip()
    city = (city or '').strip()

    # Deterministic short-circuit: a human-confirmed closure needs no model call.
    if already_known_closed(venue, city):
        res = _blank_result()
        res['status'] = 'permanently_closed'
        res['error'] = ''
        res['_from_known_closed'] = True
        return res

    # 7-day cache: a hit makes NO grounded call.
    if use_cache:
        hit = _cache_get(venue, city, db_url)
        if hit is not None:
            return hit

    from story_leads import gemini_with_sources, _gemini

    # STEP 1 — the ONE grounded call: a natural-language question that reliably
    # triggers Google Search (JSON-demand prompts do not). GroundingForbiddenError
    # (L2 guard) propagates by design. This is the billable call the LOCAL-594
    # meter counts.
    question = _GROUNDED_QUESTION.format(venue=venue or '(unspecified)',
                                         city=city or '(unspecified)')
    call = gemini_with_sources(question, grounded=True)

    if call.get('error'):
        res = _blank_result()
        res['error'] = call['error']
        res['grounding_sources'] = call.get('sources', [])
        return res

    report_text = call.get('text', '') or ''
    call_sources = call.get('sources', []) or []

    # STEP 2 — turn the grounded prose into strict JSON. This is UNGROUNDED
    # (grounded=False): it costs only Flash tokens, nothing on the Google-Search
    # channel, and the LOCAL-594 grounding meter does not count it. It never
    # introduces new facts — it only reshapes STEP 1's grounded answer.
    parsed = None
    if report_text.strip():
        try:
            extract = _gemini(_EXTRACT_PROMPT.format(report=report_text[:6000]),
                              grounded=False)
            parsed = _extract_json(extract)
        except Exception:
            parsed = None
    # Fallback: if the formatting call failed, try to parse any JSON that might
    # already be in the grounded answer itself.
    if parsed is None:
        parsed = _extract_json(report_text)

    res = _shape_result(parsed, call_sources, report_text)

    # Persist a real answer for 7 days (errors are not cached).
    if use_cache and not res.get('error'):
        _cache_put(venue, city, res, db_url)

    # A confirmed closure teaches the deterministic corpus for next time.
    if res['status'] in _CLOSED_STATUSES:
        try:
            record_confirmed_closure(venue, city, res)
        except Exception:
            pass
    return res


def safe_preflight(venue: str, city: str = '', db_url: Optional[str] = None,
                   use_cache: bool = True) -> Dict:
    """Like `preflight`, but turns the L2 `GroundingForbiddenError` into an
    explicit, non-raising marker (`{'skipped': 'l2_by_reference', ...}`) and
    swallows any other unexpected error into `unknown` + continue. For callers
    that want "preflight when allowed, otherwise just carry on" in one line."""
    try:
        from l2_by_reference import GroundingForbiddenError
    except Exception:  # pragma: no cover - guard module optional
        GroundingForbiddenError = ()  # type: ignore
    try:
        return preflight(venue, city, db_url=db_url, use_cache=use_cache)
    except GroundingForbiddenError:
        res = _blank_result()
        res['skipped'] = 'l2_by_reference'
        return res
    except Exception as e:  # unknown + continue; never fail a build on preflight
        res = _blank_result()
        res['error'] = f'{type(e).__name__}: {e}'
        return res


# ─────────────────────────────────────────────────────────────────────────────
# THE CLOSURE GATE
# ─────────────────────────────────────────────────────────────────────────────
# The exact user-facing copy D618 requires for the WNDR case, kept as constants so
# the gate and the test assert the same string.
def _closed_message(venue: str, city: str, result: Dict) -> str:
    name = venue or 'This venue'
    where = f" in {city}" if city else ''
    since = (result.get('closed_since') or '').strip()
    when = f" on {since}" if since else ''
    kind = ('permanently' if result.get('status') == 'permanently_closed'
            else 'temporarily')
    return f"{name}{where} closed {kind}{when}."


_CLOSED_SUGGESTION = "Try a nearby museum, or a walking tour of the area."


def gate(venue: str, city: str, result: Dict) -> Optional[Dict]:
    """Return a structured `venue_closed` refusal when the preflight says the
    venue is closed, else None (continue to generation).

    A `permanently_closed` status always gates. A `temporarily_closed` status
    gates ONLY when it carries no reopen date (`closed_since` empty) — a venue
    that reopens on a known date is still worth a tour the listener can take then,
    so we do not refuse it here; the opening section can carry the date. The
    false-closure guard has already run in `_shape_result`, so a closed status
    reaching here is backed by >= 1 closure source (or by the known-closed
    corpus). Shape matches the LOCAL-580 structured-refusal contract."""
    status = result.get('status')
    if status == 'permanently_closed':
        gated = True
    elif status == 'temporarily_closed':
        gated = not (result.get('closed_since') or '').strip()
    else:
        gated = False
    if not gated:
        return None
    return {
        'allowed': False,
        'error_code': 'venue_closed',
        'error': _closed_message(venue, city, result),       # legacy field
        'message': _closed_message(venue, city, result),
        'suggestion': _CLOSED_SUGGESTION,
        'status': status,
        'closed_since': result.get('closed_since', ''),
        'sources': result.get('grounding_sources', []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLAN B HELPERS (consumed by the generator)
# ─────────────────────────────────────────────────────────────────────────────

# [LOCAL-628 / task 5] "Open daily" vs a named closed day. The KHM
# (Kunsthistorisches Museum) is closed on Mondays outside summer, but a grounded
# report that leads with "Open daily, 10:00–18:00" (summer phrasing, or a loose
# source) made the spoken Stop-1 sentence say the museum is open "daily" — a
# false claim on a Monday. The hours string is free text from the report; when it
# BOTH asserts daily/every-day AND names a closed weekday, the two contradict.
# Resolve in favour of the specific closed-day fact: drop the "daily"/"every day"
# claim so the spoken sentence never says the museum is open every day while the
# same text says it is closed on some day. Never invents a day or a range; if the
# text only says "daily" with no closed-day, it is left unchanged (we do not
# second-guess a genuine 7-day venue).
_CLOSED_DAY_RE = re.compile(
    r"(?i)\b(?:closed|except|not\s+open)\b[^.;\n]*?\b(mon|tue|wed|thu|fri|sat|sun)"
    r"(?:day|s|days|nesday|rsday|urday)?\b")
_DAILY_RE = re.compile(r"(?i)\b(?:open\s+)?(?:daily|every\s*day|all\s+days?)\b")


def _hours_names_closed_day(hours: str) -> bool:
    """True when the hours text names a specific closed weekday."""
    return bool(_CLOSED_DAY_RE.search(hours or ""))


def reconcile_daily_with_closed_days(hours: str) -> str:
    """Return `hours` with any "daily"/"every day" claim removed WHEN the same
    text also names a closed weekday. Otherwise `hours` is returned unchanged.

    Examples::

        "Open daily, 10:00–18:00, closed Mondays"  -> "10:00–18:00, closed Mondays"
        "Open daily 10:00–18:00"                   -> "Open daily 10:00–18:00"  (unchanged)
        "Tue–Sun 10:00–18:00, closed Monday"       -> unchanged (no "daily")
    """
    h = (hours or "").strip()
    if not h:
        return h
    if not _DAILY_RE.search(h) or not _hours_names_closed_day(h):
        return h
    # The "every day except <weekday>" idiom is self-qualifying and TRUTHFUL — it
    # does not falsely claim the venue is open every day; it names the exception.
    # Leave it intact (stripping it would produce ungrammatical text and lose the
    # exception). Only a daily claim that is NOT immediately qualified by "except"
    # is the false one we remove.
    if re.search(r"(?i)\b(?:daily|every\s*day|all\s+days?)\s*,?\s*except\b", h):
        return h
    # Drop the daily phrase (and a trailing comma/space it leaves behind) so the
    # closed-day fact stands alone. Collapse the whitespace/punctuation seam.
    out = _DAILY_RE.sub("", h)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"^[\s,;–-]+", "", out)          # leading junk
    out = re.sub(r"\s+([,;.])", r"\1", out)        # space before punctuation
    out = re.sub(r"([,;])\s*([,;])", r"\1", out)   # doubled separators
    return out.strip().strip(",;").strip()


def plan_b_opening_practicals(result: Dict) -> Dict:
    """Hours/admission to fold into the D611 opening section WHEN THE SITE GAVE
    NONE. Returns {hours, admission, speak, source_note}:

      * `speak`   — the sentence to SPEAK in Stop 1 (D617: hours/admission are
                    spoken, their SOURCE lives in the text view only, never read
                    aloud).
      * `source_note` — the source line for the TEXT VIEW only (not spoken).

    Empty strings when the preflight has neither. The caller only calls this when
    its own site extraction produced no hours/admission."""
    hours = (result.get('hours') or '').strip()
    # [LOCAL-628 task 5] Never speak "open daily" when the hours text itself names
    # a closed weekday (the KHM closed-Monday defect). Resolve in favour of the
    # specific closed-day fact. A genuine 7-day "daily" with no closed day is kept.
    hours = reconcile_daily_with_closed_days(hours)
    admission = (result.get('admission') or '').strip()
    # [LOCAL-633] The spoken sentence is composed ONCE, short and natural, from the
    # structured hours/admission — never the raw preflight paste that Bench R1
    # flagged ("The museum is open Tuesday to Sunday, 8:15 AM … (ticket office …);
    # … admission is General Admission: €12; Combined Ticket …"). The composer
    # applies D633's rules (day ranges, one adult price + at most one free group,
    # no parens/discounts, currency as a word). The caller still places it ONCE.
    speak = ''
    try:
        from practical_facts_gate import compose_practical_facts
        speak = compose_practical_facts({
            'name': result.get('name') or result.get('venue') or '',
            'hours': hours,
            'admission': admission,
        })
    except Exception:
        speak = ''
    # D617: the source goes in the text view only — it is NOT part of `speak`.
    srcs = result.get('sources', {}) or {}
    src_urls = []
    for f in ('hours', 'admission'):
        for u in srcs.get(f, []) or []:
            if u not in src_urls:
                src_urls.append(u)
    source_note = (f"Hours/admission source: {', '.join(src_urls)}"
                   if src_urls else '')
    return {
        'hours': hours,
        'admission': admission,
        'speak': speak,
        'source_note': source_note,
    }


def plan_b_stop_candidates(result: Dict, have: int, want: int,
                           min_stops: int = DEFAULT_MIN_STOPS) -> List[Dict]:
    """Preflight exhibitions/highlights as stop CANDIDATES, used only when our own
    extraction yielded fewer than `want` (and below `min_stops`). Each candidate
    carries its grounding source URL as the seed for the normal story pipeline —
    never an unsourced stop. Returns [] when the preflight has no highlights or
    when our own extraction already met the bar.

    Returns at most (want - have) candidates. Each: {name, artist, note,
    source_url, kind, _preflight_seed: True}."""
    if have >= want or have >= min_stops:
        return []
    highlights = result.get('current_exhibitions_or_highlights') or []
    if not highlights:
        return []
    srcs = result.get('sources', {}) or {}
    src_urls = srcs.get('current_exhibitions_or_highlights', []) or []
    # Every candidate must carry a source; without one, we cannot seed a sourced
    # stop (D618: never unsourced), so skip the whole set.
    if not src_urls:
        return []
    seed_url = src_urls[0]
    need = max(0, want - have)
    out = []
    for h in highlights[:need]:
        out.append({
            'name': h.get('title', ''),
            'artist': h.get('artist', ''),
            'note': h.get('note', ''),
            'source_url': seed_url,
            'kind': 'highlight',
            '_preflight_seed': True,
        })
    return [c for c in out if c['name']]


# ─────────────────────────────────────────────────────────────────────────────
# CLI (manual probing / live runs)
# ─────────────────────────────────────────────────────────────────────────────
def main():
    import argparse
    import story_leads
    p = argparse.ArgumentParser(description='LOCAL-603 venue preflight')
    p.add_argument('--venue', required=True)
    p.add_argument('--city', default='')
    p.add_argument('--no-cache', action='store_true')
    a = p.parse_args()

    story_leads.reset_grounding_requests()
    res = preflight(a.venue, a.city, use_cache=not a.no_cache)
    reqs = story_leads.get_grounding_requests()
    qs = story_leads.get_grounding_queries()
    from cost_rates import grounding_query_cost
    g = gate(a.venue, a.city, res)

    print(json.dumps(res, ensure_ascii=False, indent=2))
    print('\n--- gate ---')
    print(json.dumps(g, ensure_ascii=False, indent=2) if g else '(no gate — continue)')
    print(f"\nPreflight cost: requests={reqs} queries={qs} "
          f"${grounding_query_cost(qs):.4f}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""tour_short_title.py — LOCAL-711 / D673: a server-written SHORT tour title.

Tour names are often whole sentences the curator typed, e.g.
    "Walking tour in Boston dedicated to Massachusetts politics and current
     affairs, Boston, MA - walking Tour"
The share email (D672/D673) needs a short, faithful title. This module asks the
cheapest chat model the repo already uses (gpt-4o-mini class, ~$0.0001 per tour)
for a 2–6 word subject plus a clean type suffix:
    "Massachusetts Politics — Walking Tour"
    "Faneuil Hall Marketplace — Walking Tour"

It is written ONCE, when an ORIGINAL tour is created (the orchestrator calls
make_short_title after the tour succeeds, non-blocking), and backfilled for
existing originals from the autonomy tick (``--backfill``). Translations get the
short title translated by translation-service, the same way tour_name is.

Rules (D673), enforced by the prompt AND re-checked in Python:
  * 2–6 words naming the subject, then " — <Type> Tour", where <Type> is the
    real category (Walking / Museum / Restaurant / Cycling…). An empty type
    gives " — Tour".
  * No invented facts; no place unless the place IS the subject; no quotes.
  * The output must be ≤ 60 chars and non-empty, else make_short_title returns
    None and the column stays NULL (the app then falls back to shortTourTitle()).

It writes ONLY audio_tours.short_title (migration 040): never tour_name, never a
DELETE. On any failure the column stays NULL.

Usage:
    python3 tour_short_title.py --tour 557            # one tour: print + save
    python3 tour_short_title.py --tour 557 --dry-run  # print only
    python3 tour_short_title.py --backfill            # every original with NULL short_title
    python3 tour_short_title.py --backfill --dry-run  # print only, write nothing

Mirrors tour_editor_score.py (SDK-tolerant OpenAI client, DATABASE_URL conn,
per-run cost line). Self-contained — no import of llm_models — so the module
drops cleanly into the orchestrator / translation-service / generator images
whose explicit COPY lists do not carry llm_models.
"""
import argparse
import os
import re
import sys

import psycopg2

# The cheapest chat model the repo already uses for check/extract calls
# (llm_models.CHECK_LLM_MODEL_DEFAULT = "gpt-4o-mini"). Resolved self-contained
# so this module needs no extra COPY in the service images. A per-site override
# (SHORT_TITLE_MODEL) and the central CHECK_LLM_MODEL knob both win if set.
MODEL = (os.getenv('SHORT_TITLE_MODEL')
         or os.getenv('CHECK_LLM_MODEL')
         or 'gpt-4o-mini')

# D673: the validated output must be at most this many characters, non-empty.
MAX_CHARS = 60

# Price per 1M tokens (in, out) for the per-run cost line. gpt-4o-mini is the
# default; the others are here so an override still prints a real number.
PRICES = {'gpt-4o-mini': (0.15, 0.60), 'gpt-4.1-mini': (0.40, 1.60),
          'gpt-4o': (2.5, 10.0), 'gpt-4.1': (2.0, 8.0)}

PROMPT = """You write a SHORT title for an audio tour, for a share email. You are given the tour's full name (what the curator typed, often a whole sentence), the original request, and the tour TYPE.

Write a faithful short title in EXACTLY this shape:
    <Subject> — <Type> Tour
Rules:
- <Subject> is 2 to 6 words naming what the tour IS ABOUT, taken only from the name/request. Title Case.
- Do NOT invent facts. Do NOT add a place unless the place itself is the subject. No quotation marks, no trailing punctuation.
- <Type> is the given type, Title Case (Walking, Museum, Restaurant, Cycling, …). If the type is empty, write just " — Tour" with no type word.
- The whole title must be at most 60 characters.

Examples:
  name "Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA - walking Tour", type "walking" -> Massachusetts Politics — Walking Tour
  name "Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market ... - Walking Tour", type "walking" -> Faneuil Hall Marketplace — Walking Tour
  name "Museum of Fine Arts, Boston, MA - museum Tour", type "museum" -> Museum of Fine Arts — Museum Tour

Tour name: {name}
Request: {request}
Type: {type}

Reply with ONLY the short title, nothing else."""


def _capitalise_type(tour_type):
    """Title-case a tour type word ("walking" -> "Walking", "self guided" ->
    "Self Guided"). Mirrors the app's _capitalise so server and app agree."""
    t = (tour_type or '').strip()
    if not t:
        return ''
    return ' '.join(w[:1].upper() + w[1:] for w in t.split() if w)


def _call_model(name, request_string, tour_type):
    """One chat call at temperature 0. Returns the raw text (stripped) and a
    usage object with prompt_tokens / completion_tokens.

    SDK-tolerant exactly like tour_editor_score.judge(): prefer the modern
    ``from openai import OpenAI`` client, fall back to the legacy
    ``openai.ChatCompletion.create`` so the production container (which may ship
    the 0.x SDK) still produces a title.
    """
    messages = [{'role': 'user', 'content': PROMPT.format(
        name=(name or '')[:600],
        request=(request_string or '')[:600],
        type=(tour_type or '').strip() or '(none)')}]
    try:
        from openai import OpenAI  # modern SDK (>=1.0)
        client = OpenAI()
        resp = client.chat.completions.create(
            model=MODEL, temperature=0, messages=messages)
        content = resp.choices[0].message.content
        usage = resp.usage
    except (ImportError, AttributeError):
        import openai as _legacy
        _key = os.getenv('OPENAI_API_KEY')
        if _key:
            _legacy.api_key = _key
        resp = _legacy.ChatCompletion.create(
            model=MODEL, temperature=0, messages=messages)
        content = resp['choices'][0]['message']['content']
        _u = resp.get('usage', {}) if isinstance(resp, dict) else {}

        class _Usage:
            prompt_tokens = int((_u or {}).get('prompt_tokens', 0) or 0)
            completion_tokens = int((_u or {}).get('completion_tokens', 0) or 0)
        usage = _Usage()
    return (content or '').strip(), usage


def _sanitise(raw):
    """Clean the model's reply into a candidate short title, or '' if unusable.

    Strips surrounding quotes/backticks and any accidental leading label the
    model may emit; collapses whitespace; takes the first non-empty line. Does
    NOT enforce the 60-char / non-empty rule — that is validate()'s job so the
    caller can log WHY a title was rejected.
    """
    if not raw:
        return ''
    # First non-empty line only — the model should answer with the title alone.
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), '')
    # Drop a leading "Short title:" / "Title:" label if the model added one.
    line = re.sub(r'^(short\s+title|title)\s*[:\-]\s*', '', line, flags=re.I)
    # Strip wrapping quotes/backticks (D673: no quotes).
    line = line.strip().strip('"\u201c\u201d\u2018\u2019\'`').strip()
    # No trailing punctuation.
    line = line.rstrip('.。،,;:')
    # Collapse internal whitespace.
    line = re.sub(r'\s+', ' ', line).strip()
    return line


def validate(candidate):
    """D673 validator: a non-empty title of at most 60 chars. Returns the title
    on success, else None. Kept tiny and pure so the tests can drive it with a
    stub model (good / >60 / empty)."""
    if not candidate:
        return None
    c = candidate.strip()
    if not c:
        return None
    if len(c) > MAX_CHARS:
        return None
    return c


def make_short_title(tour_name, request_string, tour_type):
    """D673 entry point. One cheap LLM call → a validated short title, or None.

    Returns (title, usage) when called internally so the CLI can total cost;
    the orchestrator / translation callers use the thin make_short_title_only
    wrapper that returns just the title (or None) and never raises.

    ANY failure — an SDK error, an empty reply, a reply over 60 chars — returns
    (None, usage_or_None). The caller then leaves short_title NULL.
    """
    try:
        raw, usage = _call_model(tour_name, request_string, tour_type)
    except Exception as e:
        # Surfaced by the CLI's per-tour print; callers treat None as "leave NULL".
        return None, _Failure(str(e))
    title = validate(_sanitise(raw))
    return title, usage


class _Failure:
    """A stand-in usage object for a failed call so cost totals still add up
    (zero tokens) and the CLI can print the reason."""
    prompt_tokens = 0
    completion_tokens = 0

    def __init__(self, reason=''):
        self.reason = reason


def make_short_title_only(tour_name, request_string, tour_type):
    """Thin, never-raising wrapper for the orchestrator / translation callers:
    returns a validated short title string, or None. No cost accounting, no
    exceptions — exactly the "fill it or leave it NULL" contract D673 wants."""
    try:
        title, _usage = make_short_title(tour_name, request_string, tour_type)
        return title
    except Exception:
        return None


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


def _tour_type_from_name(tour_name):
    """Best-effort tour TYPE from a raw name's " - <Type> Tour" suffix
    ("… - Walking Tour" -> "walking"). Mirrors the app's tourTypeFromName so the
    server and the app agree on the type word. "" when there is no such suffix."""
    m = re.search(r'[-–—]\s*([^-–—]*?)\s*Tour\s*$', (tour_name or '').strip(), re.I)
    if not m:
        return ''
    return (m.group(1) or '').strip().lower()


def _count_null_originals(cur):
    cur.execute("""
        SELECT COUNT(*) FROM audio_tours
        WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
          AND short_title IS NULL""")
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tour', type=int, help='score ONE tour id')
    ap.add_argument('--backfill', action='store_true',
                    help='every original with short_title IS NULL')
    ap.add_argument('--batch-size', type=int, default=200,
                    help='backfill commit batch size')
    ap.add_argument('--limit', type=int, default=None,
                    help='cap how many tours the backfill processes')
    ap.add_argument('--dry-run', action='store_true', help='print, write nothing')
    a = ap.parse_args()
    if not (a.tour or a.backfill):
        ap.error('--tour ID or --backfill')

    conn = _conn()
    cur = conn.cursor()

    if a.tour:
        cur.execute(
            "SELECT id, tour_name, request_string FROM audio_tours WHERE id = %s",
            (a.tour,))
        rows = cur.fetchall()
        before = after = None
    else:
        before = _count_null_originals(cur)
        # Idempotent: only originals that still have NULL short_title. Re-running
        # after a partial run picks up exactly what is left.
        sql = """
            SELECT id, tour_name, request_string FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND short_title IS NULL
            ORDER BY id"""
        if a.limit:
            sql += f" LIMIT {int(a.limit)}"
        cur.execute(sql)
        rows = cur.fetchall()
        print(f'[short_title] backfill: {before} original(s) with NULL short_title'
              + (f' (limited to {len(rows)})' if a.limit else ''))

    tin = tout = 0
    written = 0
    for tid, name, request_string in rows:
        tour_type = _tour_type_from_name(name)
        title, usage = make_short_title(name, request_string, tour_type)
        tin += getattr(usage, 'prompt_tokens', 0) or 0
        tout += getattr(usage, 'completion_tokens', 0) or 0
        if title is None:
            reason = getattr(usage, 'reason', '') if isinstance(usage, _Failure) else 'rejected (empty/>60)'
            print(f"{tid:>5}  --  (left NULL: {reason})  {(name or '')[:48]}")
            continue
        print(f"{tid:>5}  {title!r:42}  <- {(name or '')[:48]}")
        if not a.dry_run:
            # Writes ONLY short_title. Never tour_name, never DELETE.
            cur.execute("UPDATE audio_tours SET short_title = %s WHERE id = %s",
                        (title, tid))
            written += 1
            if a.backfill and written % max(1, a.batch_size) == 0:
                conn.commit()
    if not a.dry_run:
        conn.commit()

    pin, pout = PRICES.get(MODEL, (0.15, 0.60))
    cost = (tin * pin + tout * pout) / 1e6
    tail = ' (dry run, nothing written)' if a.dry_run else f'; wrote {written}'
    print(f'[short_title] {len(rows)} tour(s); model {MODEL}; tokens in {tin}, '
          f'out {tout}; ~${cost:.4f}{tail}')
    if a.backfill and not a.dry_run:
        after = _count_null_originals(cur)
        print(f'[short_title] NULL originals before {before} -> after {after}')
    cur.close()
    conn.close()


if __name__ == '__main__':
    sys.exit(main())

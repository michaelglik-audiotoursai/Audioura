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

# ─── LOCAL-711B / D673 ──────────────────────────────────────────────────────
# Deterministic TYPE inference. When the stored name's " - <Type> Tour" suffix
# is blank (the curator left it as "… -  Tour"), the type is still usually named
# somewhere in the name/request ("restaurant tour of …", "WNDR museum"). We map
# those words to a canonical type BEFORE the LLM call and pass it as fixed, so
# the model never has to invent — and never produces a bare " — Tour" when the
# name actually says what kind of tour it is (368/370/372/397 in LOCAL-711).
#
# Order matters: the first keyword found (scanning the map in this order) wins,
# so a more specific word ("cycling") is listed before a weaker synonym it
# shares a stem with. Each entry maps a lowercase keyword/phrase to the
# canonical Title-Case type word used in the suffix.
TYPE_KEYWORDS = [
    ('restaurant', 'Restaurant'),
    ('dining', 'Restaurant'),
    ('food', 'Food'),
    ('museum', 'Museum'),
    ('gallery', 'Museum'),
    ('walking', 'Walking'),
    ('cycling', 'Cycling'),
    ('biking', 'Cycling'),
    ('bike', 'Cycling'),
    ('boat', 'Boat'),
    ('cruise', 'Boat'),
    ('art', 'Art'),
    ('history', 'History'),
    ('historical', 'History'),
]

# Generic category words that must never stand alone as the SUBJECT. If the
# model's subject is only these (e.g. "Restaurant Tour", "Museum"), the place
# becomes the subject instead (370: "restaurant tour, Boston" -> "Boston —
# Restaurant Tour"). These are matched case-insensitively against the whole
# subject after the type words are stripped.
_GENERIC_SUBJECT_WORDS = {
    'restaurant', 'restaurants', 'dining', 'food', 'museum', 'museums',
    'gallery', 'galleries', 'walking', 'walk', 'cycling', 'biking', 'bike',
    'boat', 'cruise', 'art', 'arts', 'history', 'historical', 'tour', 'tours',
    'of', 'the', 'a', 'an',
}

# The trailing " - <anything> Tour" suffix the curator's name carries, so we can
# strip it to read what is left as the real subject material.
_SUFFIX_RE = re.compile(r'\s*[-–—]\s*[^-–—]*?\s*tour\s*$', re.I)


def infer_tour_type(tour_name, request_string, stored_type):
    """Return the tour TYPE to put in the suffix.

    If ``stored_type`` (from the name's " - <Type> Tour" suffix) is non-empty,
    it wins, Title-Cased. Otherwise scan the name then the request for a keyword
    from TYPE_KEYWORDS and return the first canonical type found. When nothing
    names a type, return '' so the suffix is the plain " — Tour" (LOCAL-711's
    contract for a genuinely typeless tour).

    Deterministic and pure — the orchestrator and the backfill both call it
    before the LLM, and the tests drive it directly.
    """
    st = (stored_type or '').strip()
    if st:
        return _capitalise_type(st)
    haystack = f"{tour_name or ''} {request_string or ''}".lower()
    # Word-boundary match so "art" does not fire inside "Hartford" etc.
    for keyword, canonical in TYPE_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', haystack):
            return canonical
    return ''


def _strip_type_words(subject, tour_type):
    """Remove the type words from the model's subject so the suffix is not echoed
    inside it (368: "Buttermilk & Bourbon Restaurant Tour" -> "Buttermilk &
    Bourbon"). The canonical type word (e.g. "Restaurant"), the literal "Tour",
    and a leading generic phrase ("restaurant tour of") are stripped.

    "Museum" is special: it is kept when it is part of a proper name — i.e. when
    it is NOT the first word (397: "WNDR Museum" keeps Museum; a bare "Museum"
    is dropped). The same courtesy is not needed for the other categories.
    """
    s = (subject or '').strip()
    if not s:
        return ''
    # If the model echoed the whole "<Subject> — <Type> Tour", keep only the
    # part before the final " — … Tour" dash-suffix.
    m = re.match(r'^(.*?)\s*[-–—]\s*[^-–—]*?tours?\s*$', s, re.I)
    if m and m.group(1).strip():
        s = m.group(1).strip()
    # Drop a trailing standalone "Tour"/"Tours" the model may have appended.
    s = re.sub(r'\s+tours?\s*$', '', s, flags=re.I).strip()
    type_word = (tour_type or '').strip()
    if type_word:
        tw = type_word.lower()
        if tw == 'museum':
            # Keep "Museum" only when it is NOT the sole / leading token: a
            # trailing proper-name "… Museum" stays, a bare leading "Museum …"
            # (generic) is dropped.
            s = re.sub(r'^museum\b\s*', '', s, flags=re.I).strip()
        else:
            # Strip the category word wherever it appears (it is never part of a
            # proper name for these types).
            s = re.sub(r'\b' + re.escape(tw) + r's?\b', ' ', s, flags=re.I)
    # Drop a dangling leading/trailing "of"/"the" and collapse whitespace.
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'^(of|the)\s+', '', s, flags=re.I).strip()
    s = re.sub(r'\s+(of|the)$', '', s, flags=re.I).strip()
    return s


def _is_generic_subject(subject):
    """True when the subject is ONLY generic category words (so it names no real
    subject, e.g. "Restaurant Tour", "Museum"). Such a subject must be replaced
    by the place (370)."""
    s = (subject or '').strip()
    if not s:
        return True
    words = re.findall(r"[\w&']+", s.lower())
    return all(w in _GENERIC_SUBJECT_WORDS for w in words) if words else True


def _place_from_name(tour_name, request_string):
    """Best-effort PLACE to use as the subject when the real subject is only a
    generic category (370). Takes the first comma-separated chunk of the name
    (after stripping the " - … Tour" suffix and any leading generic phrase) that
    is not itself purely generic; else the first chunk of the request.

    "restaurant tour, Boston, MA -  Tour" -> "Boston". Deterministic, pure."""
    for source in (tour_name, request_string):
        text = _SUFFIX_RE.sub('', (source or '').strip()).strip()
        for chunk in re.split(r'[,\n]', text):
            cand = _strip_type_words(chunk.strip(), '')
            # Drop a US state abbreviation chunk ("MA", "Ma").
            if re.fullmatch(r'[A-Za-z]{2}', cand):
                continue
            if cand and not _is_generic_subject(cand):
                return _title_case(cand)
    return ''


def _title_case(text):
    """Title-case a short phrase, preserving all-caps acronyms (WNDR) and the
    ampersand word boundaries ("Buttermilk & Bourbon")."""
    out = []
    for w in (text or '').split():
        if w.isupper() and len(w) <= 5:
            out.append(w)               # acronym: WNDR, MASS
        elif w == '&':
            out.append('&')
        else:
            out.append(w[:1].upper() + w[1:])
    return ' '.join(out)


PROMPT = """You write a SHORT title for an audio tour, for a share email. You are given the tour's full name (what the curator typed, often a whole sentence), the original request, and the tour TYPE (already decided — do not change it).

Reply with ONLY the SUBJECT: 2 to 6 words naming what the tour IS ABOUT, in Title Case. The caller appends " — {type} Tour" itself, so:
- Do NOT write the word "Tour" and do NOT write the type word ("{type}") — give the subject alone.
- Take the subject only from the name/request; do NOT invent facts; no quotation marks, no trailing punctuation.
- Keep a proper name intact, including a trailing "Museum" when it is part of the name (e.g. "WNDR Museum", "McMullen Museum of Art").
- If the name only states the category and a place (e.g. "restaurant tour, Boston"), answer with the PLACE (e.g. "Boston").

Examples:
  name "Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA - walking Tour", type "Walking" -> Massachusetts Politics
  name "restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, Ma -  Tour", type "Restaurant" -> Buttermilk & Bourbon
  name "restaurant tour, Boston, MA -  Tour", type "Restaurant" -> Boston
  name "chart house restaurant tour, Boston, MA -  Tour", type "Restaurant" -> Chart House
  name "WNDR museum, Boston, MA -  Tour", type "Museum" -> WNDR Museum

Tour name: {name}
Request: {request}
Type: {type}

Reply with ONLY the subject, nothing else."""


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
    """D673 + LOCAL-711B validator. Returns the title on success, else None.

    Rejects, in addition to empty / > 60 chars:
      * a SUBJECT that ends with "Tour" — i.e. "<something> Tour — <Type> Tour"
        or a bare "Restaurant Tour — Tour" (the 711 weakness); the subject must
        name the thing, not repeat the type.
      * the literal doubled suffix "Tour — Tour" anywhere.
    Kept tiny and pure so the tests can drive it directly."""
    if not candidate:
        return None
    c = candidate.strip()
    if not c:
        return None
    if len(c) > MAX_CHARS:
        return None
    # "Tour — Tour" (any dash) is always wrong.
    if re.search(r'\btour\s*[-–—]\s*tour\b', c, re.I):
        return None
    # The subject is everything before the final " — <Type> Tour" suffix. If the
    # subject itself ends in "Tour", the type got echoed into it — reject.
    m = re.match(r'^(.*?)\s*[-–—]\s*[^-–—]*?tour\s*$', c, re.I)
    subject = (m.group(1) if m else c).strip()
    if re.search(r'\btours?\s*$', subject, re.I):
        return None
    return c


def compose_title(subject, tour_type):
    """Assemble the final "<Subject> — <Type> Tour" deterministically from a
    SUBJECT and the fixed type. The suffix is always built here, so the type can
    never be doubled or echoed inside the subject. An empty type gives the plain
    " — Tour" (LOCAL-711's typeless contract). Returns '' if there is no subject."""
    s = (subject or '').strip()
    if not s:
        return ''
    t = (tour_type or '').strip()
    return f'{s} — {t} Tour' if t else f'{s} — Tour'


def _subject_from_reply(raw, tour_name, request_string, tour_type):
    """Turn the model's reply into the final SUBJECT, applying the LOCAL-711B
    deterministic rules: sanitise → strip the type words out of it → if what is
    left is only a generic category, use the place instead. Pure; the stub-LLM
    tests drive it through make_short_title with a model that echoes a subject."""
    subject = _strip_type_words(_sanitise(raw), tour_type)
    if _is_generic_subject(subject):
        place = _place_from_name(tour_name, request_string)
        if place:
            subject = place
    return subject


def make_short_title(tour_name, request_string, tour_type):
    """D673 + LOCAL-711B entry point. Deterministic type inference, then one
    cheap LLM call for the subject, then deterministic assembly → a validated
    short title, or None.

    Steps:
      1. infer_tour_type: if the stored suffix type is blank, read the type from
         the name/request (keyword map). The fixed type is passed to the prompt.
      2. one chat call → a SUBJECT (2–6 words), never the type or "Tour".
      3. strip any type words the model still echoed; if the subject is only a
         generic category, use the place instead (place-as-subject).
      4. compose "<Subject> — <Type> Tour" and validate.

    Returns (title, usage); the orchestrator / translation callers use the thin
    make_short_title_only wrapper. ANY failure returns (None, usage_or_None) and
    the caller leaves short_title NULL.
    """
    effective_type = infer_tour_type(tour_name, request_string, tour_type)
    try:
        raw, usage = _call_model(tour_name, request_string, effective_type)
    except Exception as e:
        # Surfaced by the CLI's per-tour print; callers treat None as "leave NULL".
        return None, _Failure(str(e))
    subject = _subject_from_reply(raw, tour_name, request_string, effective_type)
    title = validate(compose_title(subject, effective_type))
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

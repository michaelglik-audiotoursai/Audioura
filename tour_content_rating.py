#!/usr/bin/env python3
"""tour_content_rating.py — LOCAL-687: a content rating for every tour.

Michael, 2026-10-14 (D656): guides will write and edit tours, and every tour
gets a content rating like a movie rating — decided by a model, not a bad-word
list (word lists flag "class", "Assisi", "Scunthorpe"). This routine reads a
tour's text, has gpt-4.1-mini classify it, and writes the rating.

Three ratings (the exact definitions the model is held to):
    general      — listed for everyone.
    mature       — strong language, alcohol-focused, crime, gambling, nightlife,
                   casinos. Listed ONLY to listeners who confirmed they are 18+.
    not_allowed  — sexual services / adult entertainment, explicit sex, hate,
                   encouraging illegal acts. Never listed.

Review gate: anything NOT clearly general waits for a human before it lists.
    general              -> review_status NULL  (lists immediately)
    mature | not_allowed -> review_status 'pending' (held for review)

Translations are NOT rated on their own — they inherit the ORIGINAL's rating,
read through original_tour_id (same as editor_score / ratings). So this only
rates originals.

Usage:
    python3 tour_content_rating.py --tour 557            # rate one, print, save
    python3 tour_content_rating.py --backfill            # every visible original with no rating
    python3 tour_content_rating.py --backfill --rescore  # every visible original
    add --dry-run to print without writing.

Writes audio_tours.content_rating / content_rating_reason / review_status /
content_rated_at (migration 027). NULL content_rating behaves as general in the
listing layer, so an un-run DB keeps working.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2

MODEL = os.getenv('CONTENT_RATING_MODEL', 'gpt-4.1-mini')
RATINGS = ('general', 'mature', 'not_allowed')
MAX_CHARS = 24000  # ~6k tokens; the size of ONE rating window (LOCAL-724: the
                   # whole tour is now covered by as many windows as it takes —
                   # see _chunk_text / rate_text — not truncated to the first one).

PROMPT = """You are a content-rating moderator for an audio-tour app, rating a tour script like a film classification board rates a film. Judge ONLY the three categories below. Do NOT use a word list — judge meaning and intent, not isolated words ("class", "Assisi", "Scunthorpe" are not profanity; a history of a red-light district is not itself adult entertainment).

Choose exactly one rating:
- "general": suitable to list for everyone. The default. Ordinary history, culture, architecture, nature, food, art — even when it mentions war, death, religion or politics factually and without dwelling on the lurid. Restaurants, cafés and markets are general even when they serve or describe wine, beer, cocktails or spirits, or have "bar"/"bourbon"/"brewery" in their name — a meal with drinks is not an alcohol-focused tour.
- "mature": fine for adults but not for a general audience — strong/frequent profanity; a tour whose PURPOSE is drinking (bar crawl, pub crawl, wine or spirits tasting, brewery-hopping) or nightlife/clubs; casinos or gambling; crime treated as entertainment. List ONLY to confirmed-18+ listeners.
- "not_allowed": must never be listed — sexual services or adult entertainment as a selling point, explicit sexual content, hate toward a protected group, or content that encourages illegal acts.

When a tour sits between two ratings, pick the HIGHER (more restrictive) one — a human reviews everything that is not clearly general.

Tour title: {title}
Stops: {stops}

Script:
\"\"\"{text}\"\"\"

Reply with JSON only:
{{"rating": "general" | "mature" | "not_allowed", "reason": "one sentence citing the specific evidence for this rating"}}"""

# Price per 1M tokens (in, out) for the cost line.
PRICES = {'gpt-4.1': (2.0, 8.0), 'gpt-4o-mini': (0.15, 0.60), 'gpt-4.1-mini': (0.40, 1.60)}

# LOCAL-724 item 3: judge the WHOLE text, not just the first MAX_CHARS. The text
# is split into windows of CHUNK_CHARS (= MAX_CHARS, so a short tour is still one
# call, unchanged from LOCAL-687), each window is classified on its own, and the
# tour takes the MOST RESTRICTIVE rating any window earns. Windows overlap by
# CHUNK_OVERLAP so a mature passage straddling a boundary is seen whole by at
# least one window. Chosen over tail-sampling because sampling can miss mature
# content in the middle of a long tour; chunking reads every character once.
CHUNK_CHARS = MAX_CHARS
CHUNK_OVERLAP = 500
# Severity order for "take the highest": not_allowed > mature > general.
_SEVERITY = {'general': 0, 'mature': 1, 'not_allowed': 2}


def _chunk_text(text, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Split text into overlapping windows that together cover EVERY character.

    A tour at or under `size` yields exactly one window equal to the whole text,
    so the common short-tour case costs one model call, exactly as before. Longer
    tours yield ceil-style windows stepping by (size - overlap)."""
    text = text or ''
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        if start + size >= len(text):
            break
        start += step
    return chunks


def classify(title, text, stops):
    """Classify ONE chunk of text. Returns (detail dict, usage).

    This judges exactly the `text` it is given (truncated defensively at
    CHUNK_CHARS). Whole-tour coverage is rate_text's job: it calls classify once
    per chunk. Kept single-chunk so callers and tests can mock one model call.

    [LOCAL-724B defect 1] SDK-tolerant, mirroring tour_editor_score.judge
    (LOCAL-692B). The modern ``from openai import OpenAI`` client is preferred,
    but the generator/tour-editing image (Dockerfile.generator) and anything
    sharing it ship the LEGACY ``openai`` SDK (0.27.0 — no ``OpenAI`` class), on
    which the modern import raised; rate_tour_row then caught it, returned None,
    and every tour was held instead of rated. We fall back to the legacy
    ``openai.ChatCompletion.create`` so the rater actually rates INSIDE the
    container — the only place the shipped SDK is what runs."""
    import re as _re
    _messages = [{'role': 'user', 'content': PROMPT.format(
        title=title, stops=stops or '?', text=text[:CHUNK_CHARS])}]
    try:
        from openai import OpenAI  # modern SDK (>=1.0)
        client = OpenAI()
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            response_format={'type': 'json_object'},
            messages=_messages,
        )
        content = resp.choices[0].message.content
        usage = resp.usage
    except (ImportError, AttributeError):
        # Legacy SDK (0.x): openai.ChatCompletion, no response_format support —
        # the PROMPT already demands JSON-only output ("Reply with JSON only").
        import openai as _legacy
        _key = os.getenv('OPENAI_API_KEY')
        if _key:
            _legacy.api_key = _key
        resp = _legacy.ChatCompletion.create(
            model=MODEL, temperature=0, messages=_messages)
        content = resp['choices'][0]['message']['content']
        _u = resp.get('usage', {}) if isinstance(resp, dict) else {}

        class _Usage:
            prompt_tokens = int((_u or {}).get('prompt_tokens', 0) or 0)
            completion_tokens = int((_u or {}).get('completion_tokens', 0) or 0)
        usage = _Usage()
    # Legacy output may wrap the JSON in prose/fences — extract the object.
    content = (content or '').strip()
    if not content.startswith('{'):
        _m = _re.search(r'\{.*\}', content, _re.S)
        if _m:
            content = _m.group(0)
    detail = json.loads(content)
    rating = str(detail.get('rating', '')).strip().lower()
    if rating not in RATINGS:
        # The model returned something off-menu. Fail SAFE: treat as not clearly
        # general, so it is held for review rather than silently listed.
        rating = 'not_allowed' if 'not' in rating or 'allow' in rating else 'mature'
    detail['rating'] = rating
    detail['reason'] = str(detail.get('reason', '')).strip()
    return detail, usage


def review_status_for(rating):
    """general lists immediately (NULL); anything else waits for a human."""
    return None if rating == 'general' else 'pending'


def rate_text(title, text, stops):
    """Rate a whole tour across ALL its text, returning (rating, detail).

    Classifies every chunk (see _chunk_text) and keeps the MOST RESTRICTIVE
    rating found, with the reason from the chunk that earned it. Token usage is
    summed across chunks so the cost line stays honest. detail['chunks'] records
    how many windows were judged (1 for an ordinary tour)."""
    chunks = _chunk_text(text or '')
    best_detail = None
    best_sev = -1
    tokens_in = tokens_out = 0
    for idx, chunk in enumerate(chunks):
        detail, usage = classify(title, chunk, stops)
        tokens_in += getattr(usage, 'prompt_tokens', 0) or 0
        tokens_out += getattr(usage, 'completion_tokens', 0) or 0
        sev = _SEVERITY.get(detail['rating'], 1)
        if sev > best_sev:
            best_sev = sev
            best_detail = detail
            if sev == _SEVERITY['not_allowed']:
                # Already the most restrictive possible; reading further windows
                # cannot change the verdict, so stop paying for them.
                break
    if best_detail is None:  # empty text: nothing to judge, fail safe to held.
        best_detail = {'rating': 'mature', 'reason': 'no text to rate'}
    best_detail.update({'model': MODEL, 'chunks': len(chunks),
                        'tokens_in': tokens_in, 'tokens_out': tokens_out})
    return best_detail['rating'], best_detail


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


# ─── LOCAL-724 items 1 & 2: rate in the SERVING path, before listing ──────────
# The orchestrator (and any other generation/edit path) calls this with an OPEN
# cursor, inside the SAME transaction that makes the tour listable, BEFORE it
# commits. The row therefore carries its rating the instant it becomes visible —
# a new tour is never listed before it is rated, and the rating does not depend
# on the Mac Mini launchd tick (which stays only as a backfill safety net, and
# never runs on GCloud). The OpenAI key is read from the environment by OpenAI()
# (on GCloud: injected from Secret Manager by name) — never written anywhere.
def rate_tour_row(cur, tour_id, tour_name, tour_content, stops_count,
                  model_override=None):
    """Rate one ORIGINAL tour and write its rating columns using `cur`.

    Does NOT commit — the caller owns the transaction, so the rating lands
    atomically with (or just before) the row becoming listable. Returns the
    detail dict on success, or None if it could not rate (too little text, a
    model error, or a schema without the content_rating columns) — in which case
    the row keeps whatever it had and the launchd backfill will pick it up later.
    Never raises: rating must never be able to fail a tour store/edit.

    A translation (original_tour_id set) must NOT be passed here — translations
    inherit their original's rating in the listing layer. Callers rate originals
    only.
    """
    text = tour_content or ''
    if len(text) < 200:
        # Too little text to classify meaningfully (same floor the backfill uses).
        return None
    global MODEL
    _saved_model = MODEL
    if model_override:
        MODEL = model_override
    try:
        rating, detail = rate_text(tour_name or '', text, stops_count)
    except Exception as e:
        print(f'[LOCAL-724] rate_tour_row: rating tour {tour_id} failed, left for '
              f'backfill: {e}')
        MODEL = _saved_model
        return None
    MODEL = _saved_model
    status = review_status_for(rating)
    # Schema-tolerant write: an older DB without the 027 columns must not abort
    # the caller's transaction. Guard with a SAVEPOINT so a failure here rolls
    # back only this UPDATE, leaving the tour store intact.
    try:
        cur.execute('SAVEPOINT content_rating_write')
        cur.execute(
            """UPDATE audio_tours SET content_rating = %s, content_rating_reason = %s,
               review_status = %s, content_rated_at = %s WHERE id = %s""",
            (rating, detail.get('reason'), status, datetime.now(timezone.utc), tour_id))
        cur.execute('RELEASE SAVEPOINT content_rating_write')
    except Exception as e:
        try:
            cur.execute('ROLLBACK TO SAVEPOINT content_rating_write')
        except Exception:
            pass
        print(f'[LOCAL-724] rate_tour_row: could not write rating for tour '
              f'{tour_id} (schema?): {e}')
        return None
    print(f'[LOCAL-724] rated tour {tour_id} {rating}'
          f'{"" if status is None else " [" + status + "]"} '
          f'({detail.get("chunks", 1)} window(s))')
    return detail


def clear_rating(cur, tour_id):
    """LOCAL-724 item 4: wipe a tour's rating so it is re-rated (and held until
    then). Used by edit paths that change a tour's text. Uses the caller's
    cursor/transaction; never commits; never raises. Setting review_status back
    to 'pending' means the edited tour is NOT listable until it is re-rated and,
    if still not clearly general, re-reviewed — the listing layer hides pending.
    """
    try:
        cur.execute('SAVEPOINT content_rating_clear')
        cur.execute(
            """UPDATE audio_tours SET content_rating = NULL, content_rating_reason = NULL,
               review_status = 'pending', content_rated_at = NULL WHERE id = %s""",
            (tour_id,))
        cur.execute('RELEASE SAVEPOINT content_rating_clear')
        return True
    except Exception as e:
        try:
            cur.execute('ROLLBACK TO SAVEPOINT content_rating_clear')
        except Exception:
            pass
        print(f'[LOCAL-724] clear_rating: could not clear rating for tour '
              f'{tour_id} (schema?): {e}')
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tour', type=int)
    ap.add_argument('--backfill', action='store_true')
    ap.add_argument('--rescore', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not (a.tour or a.backfill):
        ap.error('--tour ID or --backfill')

    conn = _conn()
    cur = conn.cursor()
    if a.tour:
        # Rate exactly the row asked for. If it is a translation, rate its
        # ORIGINAL instead (translations inherit; nothing is written to the
        # translation row itself).
        cur.execute("SELECT original_tour_id FROM audio_tours WHERE id = %s", (a.tour,))
        row = cur.fetchone()
        target = row[0] if row and row[0] is not None else a.tour
        if target != a.tour:
            print(f'{a.tour} is a translation; rating its original {target} instead')
        cur.execute("SELECT id, tour_name, tour_content, stops_count FROM audio_tours WHERE id = %s", (target,))
    else:
        cur.execute(f"""
            SELECT id, tour_name, tour_content, stops_count FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              {'' if a.rescore else 'AND content_rating IS NULL'}
            ORDER BY id""")
    rows = cur.fetchall()
    tin = tout = 0
    counts = {'general': 0, 'mature': 0, 'not_allowed': 0}
    pending = 0
    for tid, name, text, stops in rows:
        if not text:
            print(f'{tid}: no text, skipped')
            continue
        try:
            rating, detail = rate_text(name or '', text, stops)
        except Exception as e:
            print(f'{tid}: FAILED {e}')
            continue
        tin += detail['tokens_in']
        tout += detail['tokens_out']
        status = review_status_for(rating)
        counts[rating] += 1
        if status == 'pending':
            pending += 1
        flag = '' if status is None else f'  [{status}]'
        print(f"{tid:>4}  {rating:<12}{flag}  {(detail.get('reason') or '')[:80]}  — {(name or '')[:40]}")
        if not a.dry_run:
            cur.execute("""UPDATE audio_tours SET content_rating = %s, content_rating_reason = %s,
                           review_status = %s, content_rated_at = %s WHERE id = %s""",
                        (rating, detail.get('reason'), status, datetime.now(timezone.utc), tid))
            conn.commit()
    pin, pout = PRICES.get(MODEL, (0.40, 1.60))
    print(f"{len(rows)} tour(s): general={counts['general']} mature={counts['mature']} "
          f"not_allowed={counts['not_allowed']} ({pending} -> pending review); "
          f'tokens in {tin}, out {tout}; '
          f'~${(tin * pin + tout * pout) / 1e6:.4f}' + (' (dry run, nothing written)' if a.dry_run else ''))


if __name__ == '__main__':
    sys.exit(main())

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
MAX_CHARS = 24000  # ~6k tokens; long tours are judged on their first part

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


def classify(title, text, stops):
    """Ask the model for {rating, reason}. Returns (detail dict, usage)."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={'type': 'json_object'},
        messages=[{'role': 'user', 'content': PROMPT.format(
            title=title, stops=stops or '?', text=text[:MAX_CHARS])}],
    )
    detail = json.loads(resp.choices[0].message.content)
    rating = str(detail.get('rating', '')).strip().lower()
    if rating not in RATINGS:
        # The model returned something off-menu. Fail SAFE: treat as not clearly
        # general, so it is held for review rather than silently listed.
        rating = 'not_allowed' if 'not' in rating or 'allow' in rating else 'mature'
    detail['rating'] = rating
    detail['reason'] = str(detail.get('reason', '')).strip()
    return detail, resp.usage


def review_status_for(rating):
    """general lists immediately (NULL); anything else waits for a human."""
    return None if rating == 'general' else 'pending'


def rate_text(title, text, stops):
    detail, usage = classify(title, text, stops)
    detail.update({'model': MODEL,
                   'tokens_in': usage.prompt_tokens, 'tokens_out': usage.completion_tokens})
    return detail['rating'], detail


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


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

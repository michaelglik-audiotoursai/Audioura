#!/usr/bin/env python3
"""tour_editor_score.py — LOCAL-685: an evaluated starting score for every tour.

Michael, 2026-10-14: every unrated tour showed the same "7.5 · New", which
"looks very artificial — that it is". This routine reads a tour's text, has a
small model grade it on a fixed rubric, and maps the result to 5.0–8.0. The
number becomes the tour's PRIOR: shown while the tour has no ratings, blended
with the first 1–3 ratings, and used as the Bayesian rank prior. Real listener
ratings take over exactly as before (D647: median from 4 ratings on).

Why 5.0–8.0: below 5 would bury a tour nobody has heard yet; above 8 would
claim more than an unrated tour has earned. 9–10 stay reserved for listeners.

Rubric (each 1–10, judged from the text alone):
    story       — narrative pull: people, events, stakes, not a list of facts
    specificity — concrete names, dates, numbers, details a guide would know
    place       — tied to what the listener sees/does at each stop; directions
    flow        — stops connect; no repetition, no filler, consistent voice
    accuracy    — plausibility: no contradictions, no obviously invented claims

Usage:
    python3 tour_editor_score.py --tour 557            # score one, print, save
    python3 tour_editor_score.py --backfill            # every visible original with no score
    python3 tour_editor_score.py --backfill --rescore  # every visible original
    add --dry-run to print without writing.

Writes audio_tours.editor_score / editor_score_detail / editor_scored_at
(migration 025). Translations are not scored: they show their original's score.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2

MODEL = os.getenv('EDITOR_SCORE_MODEL', 'gpt-4.1')
SCORE_MIN, SCORE_MAX = 5.0, 8.0
# The rubric average that maps to the ends of 5.0–8.0. A small model's grades
# bunch between 5 and 9, so map that band (not 1–10) or every tour would land
# near 7 again — the very flatness this exists to remove.
RUBRIC_LOW, RUBRIC_HIGH = 4.5, 8.5
CRITERIA = ('story', 'specificity', 'place', 'flow', 'accuracy')
MAX_CHARS = 24000  # ~6k tokens; long tours are judged on their first part

PROMPT = """You are a demanding editor at a travel publisher, grading an audio tour script that a listener hears on a phone while walking, riding or visiting. You grade many scripts; your grades must SEPARATE good scripts from mediocre ones, so do not default to safe middle grades.

First write one specific sentence of evidence per criterion (quote or cite the script), then grade it from 1 to 10 in steps of 0.5.
Anchors: 3 = weak, 5 = mediocre / generic, 6.5 = competent, 8 = genuinely good, 9.5 = exceptional (rare).
- story: narrative pull — named people, events, stakes, surprise — versus a list of facts or tourist-brochure praise.
- specificity: concrete names, dates, numbers, details a real local guide would know, versus generic phrases ("rich history", "vibrant atmosphere").
- place: tied to what the listener actually sees or does at each stop, with usable directions between stops.
- flow: stops connect into one tour; penalise repetition, padding, filler, formulaic openings repeated at every stop.
- accuracy: internally consistent and plausible; penalise contradictions, vague hedging and claims that look invented.

Tour title: {title}
Stops: {stops}

Script:
\"\"\"{text}\"\"\"

Reply with JSON only:
{{"evidence": {{"story": "...", "specificity": "...", "place": "...", "flow": "...", "accuracy": "..."}},
  "story": n, "specificity": n, "place": n, "flow": n, "accuracy": n, "summary": "one sentence"}}"""

# Price per 1M tokens (in, out) for the cost line.
PRICES = {'gpt-4.1': (2.0, 8.0), 'gpt-4o-mini': (0.15, 0.60), 'gpt-4.1-mini': (0.40, 1.60)}


def map_to_range(avg):
    """Rubric average → 5.0–8.0, one decimal, clamped."""
    frac = (avg - RUBRIC_LOW) / (RUBRIC_HIGH - RUBRIC_LOW)
    frac = max(0.0, min(1.0, frac))
    return round(SCORE_MIN + frac * (SCORE_MAX - SCORE_MIN), 1)


def judge(title, text, stops):
    """Ask the model for the five grades. Returns (detail dict, usage)."""
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
    for c in CRITERIA:
        detail[c] = max(1.0, min(10.0, round(float(detail[c]) * 2) / 2))
    return detail, resp.usage


def score_text(title, text, stops):
    detail, usage = judge(title, text, stops)
    avg = sum(detail[c] for c in CRITERIA) / len(CRITERIA)
    detail.update({'rubric_avg': round(avg, 2), 'model': MODEL,
                   'tokens_in': usage.prompt_tokens, 'tokens_out': usage.completion_tokens})
    return map_to_range(avg), detail


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
        cur.execute("SELECT id, tour_name, tour_content, stops_count FROM audio_tours WHERE id = %s", (a.tour,))
    else:
        cur.execute(f"""
            SELECT id, tour_name, tour_content, stops_count FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              {'' if a.rescore else 'AND editor_score IS NULL'}
            ORDER BY id""")
    rows = cur.fetchall()
    tin = tout = 0
    for tid, name, text, stops in rows:
        if not text:
            print(f'{tid}: no text, skipped')
            continue
        try:
            score, detail = score_text(name or '', text, stops)
        except Exception as e:
            print(f'{tid}: FAILED {e}')
            continue
        tin += detail['tokens_in']
        tout += detail['tokens_out']
        grades = ' '.join(f"{c[:4]}={detail[c]}" for c in CRITERIA)
        print(f"{tid:>4}  {score:.1f}  ({grades}, avg {detail['rubric_avg']})  {(name or '')[:50]}")
        if not a.dry_run:
            cur.execute("""UPDATE audio_tours SET editor_score = %s, editor_score_detail = %s,
                           editor_scored_at = %s WHERE id = %s""",
                        (score, json.dumps(detail), datetime.now(timezone.utc), tid))
            conn.commit()
    pin, pout = PRICES.get(MODEL, (2.0, 8.0))
    print(f'{len(rows)} tour(s); tokens in {tin}, out {tout}; '
          f'~${(tin * pin + tout * pout) / 1e6:.4f}' + (' (dry run, nothing written)' if a.dry_run else ''))


if __name__ == '__main__':
    sys.exit(main())

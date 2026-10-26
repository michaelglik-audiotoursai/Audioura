#!/usr/bin/env python3
"""tour_editor_score.py — LOCAL-685/688: an evaluated starting score for every tour.

Michael, 2026-10-14: every unrated tour showed the same "7.5 · New", which
"looks very artificial — that it is". This routine reads a tour's text, has a
small model grade it on a fixed rubric, and maps the result to 5.0–8.0. The
number becomes the tour's PRIOR: shown while the tour has no ratings, blended
with the first 1–3 ratings, and used as the Bayesian rank prior. Real listener
ratings take over exactly as before (D647: median from 4 ratings on).

[LOCAL-688] A single rubric run wobbles ±0.4 at temperature 0 (the model is not
deterministic). The score is therefore the mean of THREE runs: each criterion is
graded three times and averaged before mapping. Every run's grades are kept in
editor_score_detail['runs'] so the published number is auditable, and the
detail now carries a rubric_version (2) that the "Why this score" explanation
surfaces to guides and listeners.

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
    python3 tour_editor_score.py --backfill --track beta,storied   # only those tracks
    add --dry-run to print without writing.

    # Read-only (no model call, no write) — how many visible originals already
    # score >= a threshold, e.g. the SUBSCRIBED_STABLE_MIN_SCORE gate (LOCAL-770):
    python3 tour_editor_score.py --count-min-score 7.2
    python3 tour_editor_score.py --count-min-score 7.2 --track beta,storied

Writes audio_tours.editor_score / editor_score_detail / editor_scored_at
(migration 025). Translations are not scored: they show their original's score.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2

MODEL = os.getenv('EDITOR_SCORE_MODEL', 'gpt-4.1')
# [LOCAL-688] A single run of the rubric wobbles ±0.4 even at temperature 0
# (the model is not deterministic). Grade the SAME script three times and
# average each criterion before mapping, so the published score is stable.
# Overridable for cost control in tests/backfills; must be >= 1.
RUBRIC_RUNS = max(1, int(os.getenv('EDITOR_SCORE_RUNS', '3')))
# Bumped from 1 (LOCAL-685) to 2 (LOCAL-688): the published number is now the
# mean of three runs, not one. Shown to guides/listeners in the explanation.
RUBRIC_VERSION = 2
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
    """Ask the model for the five grades ONCE. Returns (detail dict, usage).

    The returned detail has each criterion clamped to 1–10 in 0.5 steps, plus
    the model's per-criterion `evidence` and one-line `summary`.

    [LOCAL-692B] SDK-tolerant: the modern ``from openai import OpenAI`` client is
    preferred, but the generator container ships a LEGACY ``openai`` SDK (no
    ``OpenAI`` class), on which the import raised and the score came back None.
    We fall back to the legacy ``openai.ChatCompletion.create`` so the production
    editor (gpt-4.1, 3 runs) actually scores inside the container.
    """
    _messages = [{'role': 'user', 'content': PROMPT.format(
        title=title, stops=stops or '?', text=text[:MAX_CHARS])}]
    try:
        from openai import OpenAI  # modern SDK (>=1.0)
        client = OpenAI()
        resp = client.chat.completions.create(
            model=MODEL, temperature=0,
            response_format={'type': 'json_object'}, messages=_messages)
        content = resp.choices[0].message.content
        usage = resp.usage
    except (ImportError, AttributeError):
        # Legacy SDK (0.x): openai.ChatCompletion. No response_format support,
        # so the prompt itself instructs JSON-only output.
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
    # Legacy output may wrap JSON in prose/fences — extract the JSON object.
    content = (content or '').strip()
    if not content.startswith('{'):
        _m = re.search(r'\{.*\}', content, re.S)
        if _m:
            content = _m.group(0)
    detail = json.loads(content)
    for c in CRITERIA:
        detail[c] = max(1.0, min(10.0, round(float(detail[c]) * 2) / 2))
    return detail, usage


def _mean(values):
    return sum(values) / len(values)


def score_text(title, text, stops, runs=None):
    """Grade the script `runs` times (default RUBRIC_RUNS = 3), average each of
    the five criteria across the runs, then map that average to 5.0–8.0.

    [LOCAL-688] Averaging three runs removes the ±0.4 single-run wobble. Every
    run's five grades are kept in detail['runs'] so the number is auditable; the
    published per-criterion grades (detail['story'], …) and evidence/summary come
    from the averaged / first run respectively, so downstream shape is unchanged.
    """
    n = runs if runs is not None else RUBRIC_RUNS
    results = []
    tin = tout = 0
    for _ in range(n):
        d, usage = judge(title, text, stops)
        results.append(d)
        tin += usage.prompt_tokens
        tout += usage.completion_tokens

    # Average each criterion across runs, re-rounded to the same 0.5 grid so the
    # published grade reads like a single rubric grade.
    averaged = {}
    for c in CRITERIA:
        avg_c = _mean([r[c] for r in results])
        averaged[c] = max(1.0, min(10.0, round(avg_c * 2) / 2))

    rubric_avg = _mean([averaged[c] for c in CRITERIA])

    # Evidence and summary are qualitative; take them from the FIRST run (all
    # runs grade the same text, the sentences are interchangeable).
    first = results[0]
    detail = {c: averaged[c] for c in CRITERIA}
    detail['evidence'] = first.get('evidence', {})
    detail['summary'] = first.get('summary', '')
    detail['rubric_avg'] = round(rubric_avg, 2)
    detail['rubric_version'] = RUBRIC_VERSION
    detail['model'] = MODEL
    detail['runs'] = [
        {c: r[c] for c in CRITERIA} for r in results
    ]
    detail['run_count'] = len(results)
    detail['tokens_in'] = tin
    detail['tokens_out'] = tout
    return map_to_range(rubric_avg), detail


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


def _parse_tracks(raw):
    """Parse a --track value ('beta,storied') into a clean lowercase list, or
    None when unset. Unknown names are kept as-is (the caller's responsibility);
    we only split/trim/lowercase so the SQL scope matches audio_tours.track."""
    if not raw:
        return None
    tracks = [t.strip().lower() for t in raw.split(',') if t.strip()]
    return tracks or None


def _track_scope_sql(tracks):
    """(sql_fragment, params) scoping a backfill/count to specific tracks, via
    the SAME COALESCE(track,'beta') the map-delivery filter uses so a NULL-track
    row counts as 'beta'. Empty (no scope) when tracks is None."""
    if not tracks:
        return "", []
    placeholders = ', '.join(['%s'] * len(tracks))
    return f" AND COALESCE(track, 'beta') IN ({placeholders})", list(tracks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tour', type=int)
    ap.add_argument('--backfill', action='store_true')
    ap.add_argument('--rescore', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    # [LOCAL-770] Limit the backfill / count to specific deployment tracks, e.g.
    # --track beta,storied to score only the Stable tours a Subscribed listing
    # would surface. Unset = every track (unchanged default).
    ap.add_argument('--track', help="comma-separated tracks to scope to, e.g. 'beta,storied'")
    # [LOCAL-770] Read-only: count how many visible originals ALREADY score at or
    # above a threshold (the SUBSCRIBED_STABLE_MIN_SCORE gate). No model call, no
    # write — a safe dry-run count before turning the feature on.
    ap.add_argument('--count-min-score', type=float,
                    help='READ-ONLY count of visible originals with editor_score >= N (no scoring)')
    a = ap.parse_args()
    if not (a.tour or a.backfill or a.count_min_score is not None):
        ap.error('--tour ID, --backfill, or --count-min-score N')

    tracks = _parse_tracks(a.track)
    scope_sql, scope_params = _track_scope_sql(tracks)

    conn = _conn()
    cur = conn.cursor()

    # [LOCAL-770] Read-only count path: how many visible originals would qualify
    # at >= the threshold. Same visibility predicate as the backfill (original,
    # not test, located, has text) PLUS the score bar. Writes nothing.
    if a.count_min_score is not None:
        cur.execute(f"""
            SELECT COUNT(*) FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              AND editor_score IS NOT NULL AND editor_score >= %s
              {scope_sql}
        """, [a.count_min_score] + scope_params)
        qualifying = cur.fetchone()[0]
        cur.execute(f"""
            SELECT COUNT(*) FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              {scope_sql}
        """, scope_params)
        total_visible = cur.fetchone()[0]
        cur.execute(f"""
            SELECT COUNT(*) FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              AND editor_score IS NULL
              {scope_sql}
        """, scope_params)
        unscored = cur.fetchone()[0]
        scope_label = f" track={','.join(tracks)}" if tracks else ""
        print(f"[count-min-score{scope_label}] visible originals: {total_visible}; "
              f"scored >= {a.count_min_score}: {qualifying}; "
              f"still unscored: {unscored} (read-only, nothing written)")
        conn.close()
        return 0

    if a.tour:
        cur.execute("SELECT id, tour_name, tour_content, stops_count FROM audio_tours WHERE id = %s", (a.tour,))
    else:
        cur.execute(f"""
            SELECT id, tour_name, tour_content, stops_count FROM audio_tours
            WHERE original_tour_id IS NULL AND is_test IS NOT TRUE
              AND lat IS NOT NULL AND COALESCE(length(tour_content), 0) > 200
              {'' if a.rescore else 'AND editor_score IS NULL'}
              {scope_sql}
            ORDER BY id""", scope_params)
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

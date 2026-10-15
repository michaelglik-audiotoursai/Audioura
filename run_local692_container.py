#!/usr/bin/env python3
"""run_local692_container.py — LOCAL-692 evaluation (ISOLATED container).

Generates a museum venue on the CHEAP (Serper) arm in TWO versions and reports
the D659 metrics side by side:

  BEFORE — MUSEUM_RESEARCH unset: the object-only serper_research backend (the
           arm Michael heard).
  AFTER  — MUSEUM_RESEARCH=artist_life: the artist-life backend + person-first
           writer instruction + Vietnamese name fix & pronunciation aid.

Both arms use the cheap arm (CHEAP_ARM_CATEGORIES=museum, NARRATION_MODEL=
gpt-4.1-mini, RESEARCH_BACKEND=serper) and the FRESH forced-stops path
(cache off, pool off), exactly as LOCAL-668/669.

Per stop it reports: which of Michael's six questions are answered (keyword
detectors), the Sources line and whether each is Wikipedia or other, words/stop,
and the artist-name faults still present. Per tour: the editor score
(tour_editor_score.score_text, 3 runs) and the $ cost. Rows: additive is_test
only; never DELETE; row counts printed before/after.

Venue + stop count come from argv: VENUE and STOPS env, or defaults to HCMC 5.
HARD CAP for the WHOLE task is COST_HARD_LIMIT_USD (set by the shell driver),
with a RESERVE GATE before each arm.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-692')
except Exception as _meter_err:
    print(f"[LOCAL-692] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import json
import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
# Editor scorer: use the cheaper model to stay well under budget (the rubric
# still separates tours; see tour_editor_score PRICES).
_os.environ.setdefault('EDITOR_SCORE_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('EDITOR_SCORE_RUNS', '1')

HARD_CAP_USD = float(_os.environ.get('COST_HARD_LIMIT_USD', '3.00'))
RESERVE_USD = float(_os.environ.get('LOCAL692_RESERVE_USD', '0.45'))
HOST = socket.gethostname()

VENUE = _os.environ.get('LOCAL692_VENUE', 'Ho Chi Minh City Museum of Fine Arts, Vietnam')
STOPS = int(_os.environ.get('LOCAL692_STOPS', '5'))
SLUG = _os.environ.get('LOCAL692_SLUG', 'HCMC')

print(f"=== LOCAL-692 eval: {VENUE} ({STOPS} stops, museum) ===", flush=True)
print(f"host: {HOST}  HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=_os.environ.get('DB_PORT', '5432'),
        dbname=_os.environ.get('DB_NAME', 'audiotours'),
        user=_os.environ.get('DB_USER', 'admin'),
        password=_os.environ.get('DB_PASSWORD', 'password123'))


def _scalar(sql, args=()):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close(); return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True); return None


def _row_count():
    return _scalar("SELECT count(*) FROM audio_tours")


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


# ── per-stop detectors for Michael's six questions ───────────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_SOURCES_RE = re.compile(r"(?mi)^Sources?:\s*(.+)$")

# Each question -> a regex that signals it was answered with a concrete fact.
_Q = {
    'who_is_the_artist': re.compile(
        r"(?i)\b(was born|born in|painter|sculptor|artist)\b"),
    'where_lived_worked': re.compile(
        r"(?i)\b(lived|moved to|settled|based in|worked in|hometown|village|"
        r"returned to|in Hanoi|in Saigon|in Paris)\b"),
    'where_learned': re.compile(
        r"(?i)\b(studied at|graduated|trained|École|Ecole|Beaux-Arts|"
        r"academy|school of (fine )?art|taught by|apprenticed)\b"),
    'what_changed_life': re.compile(
        r"(?i)\b(turning point|war|exile|fled|imprisoned|arrested|moved|"
        r"after the|when (he|she)|changed (his|her)|first female|first to)\b"),
    'why_dedicated_to_art': re.compile(
        r"(?i)\b(dedicated|devoted|wanted to|dreamed of|chose to|"
        r"in (his|her) own words|said|believed|why (he|she) (paint|made))\b"),
    'work_story': re.compile(
        r"(?i)\b(commission|acquired|gift|gifted|donated|bequest|purchased|"
        r"first (shown|exhibited)|national treasure|added to the collection|"
        r"entered the (museum|collection))\b"),
}

_GENERIC = re.compile(
    r"(?i)\b(resilience|endurance|women's roles|national identity|"
    r"cultural memory|timeless|enduring (strength|spirit))\b")


def _stops(text):
    parts = re.split(r"(?mi)^Stop\s+\d+:", text)
    heads = _STOP_HEADER_RE.findall(text)
    bodies = parts[1:]
    out = []
    for i, b in enumerate(bodies):
        title = heads[i].strip() if i < len(heads) else f'stop{i+1}'
        out.append((title, b))
    return out


def _words(s):
    return len(re.findall(r"\S+", s))


def _classify_source(line):
    wiki = 'wikipedia' in line.lower()
    return 'wikipedia' if wiki else 'other'


def _report(slug, text):
    stops = _stops(text)
    print(f"  --- [{slug}] PER-STOP ---", flush=True)
    total_words = 0
    q_counts = {k: 0 for k in _Q}
    for title, body in stops:
        w = _words(body)
        total_words += w
        answered = [k for k, rx in _Q.items() if rx.search(body)]
        for k in answered:
            q_counts[k] += 1
        generic = len(_GENERIC.findall(body))
        print(f"   STOP: {title[:60]}", flush=True)
        print(f"     words={w}  Qs_answered({len(answered)})={answered}  "
              f"generic_theme_hits={generic}", flush=True)
    nstops = max(1, len(stops))
    print(f"  --- [{slug}] SOURCES ---", flush=True)
    srcs = _SOURCES_RE.findall(text)
    wiki_n = other_n = 0
    for s in srcs:
        kind = _classify_source(s)
        if kind == 'wikipedia':
            wiki_n += 1
        else:
            other_n += 1
        print(f"     SOURCES[{kind}]: {s.strip()[:160]}", flush=True)
    # Name faults still present (text side).
    faults = {
        'stripped_diacritics_Nguyen_Gia_Tri': len(re.findall(r"Nguyen Gia Tri", text)),
        'wrong_attr_Nguyen_Van_Tri': len(re.findall(r"Nguyen Van Tri", text)),
        'fragment_Luu_alone': len(re.findall(r"(?<![\wÀ-ỹ])Lựu(?![\wÀ-ỹ])", text)),
        'has_say_aid': len(re.findall(r"\(say:", text)),
    }
    print(f"  --- [{slug}] SUMMARY ---", flush=True)
    print(f"     words/stop={total_words/nstops:.0f} (total {total_words}, "
          f"{len(stops)} stops)", flush=True)
    print(f"     Qs answered across tour: "
          f"{ {k: v for k, v in q_counts.items() if v} }", flush=True)
    print(f"     distinct Michael-Qs answered >=1 stop: "
          f"{sum(1 for v in q_counts.values() if v)}/6", flush=True)
    print(f"     sources: wikipedia_lines={wiki_n} other_lines={other_n}",
          flush=True)
    print(f"     name_faults={faults}", flush=True)
    return {
        'words_per_stop': round(total_words / nstops, 1),
        'total_words': total_words, 'stops': len(stops),
        'q_counts': q_counts,
        'distinct_qs': sum(1 for v in q_counts.values() if v),
        'wiki_source_lines': wiki_n, 'other_source_lines': other_n,
        'name_faults': faults,
    }


def _editor_score(text):
    try:
        from tour_editor_score import score_text
        score, detail = score_text(VENUE, text, STOPS)
        return score, detail
    except Exception as e:
        print(f"  [editor] score failed: {e}", flush=True)
        return None, {}


def _store(text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-692 {VENUE.split(',')[0][:40]} {slug} {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full', %s)
                RETURNING id
                """,
                (name, VENUE, n_stops, text, n_stops,
                 f"LOCAL-692 eval ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_arm(slug, env_overrides):
    for k, v in env_overrides.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v
    spend = _spend_so_far()
    print(f"\n[reserve-gate] arm={slug} spend_so_far="
          f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
          f"vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return {'slug': slug, 'outcome': 'SKIPPED_CAP'}
    print(f"=== [{slug}] generating overrides="
          f"{ {k: v for k, v in env_overrides.items()} } ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            VENUE, 'museum', f"/app/tours/LOCAL692_{SLUG}_{slug}.txt", STOPS,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return {'slug': slug, 'outcome': f'ERROR:{e}'}
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME [{slug}]: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return {'slug': slug, 'outcome': 'NO_TEXT'}
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME [{slug}]: DELIVERED {len(text)} chars, {delivered} stops, "
          f"{elapsed:.1f}s", flush=True)
    metrics = _report(slug, text)
    tour_cost = 0.0
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost',
                                  _cc.get('total_cost', 0.0)) or 0.0)
    except Exception:
        pass
    score, detail = _editor_score(text)
    print(f"  [{slug}] editor_score={score} "
          f"(detail avg={detail.get('rubric_avg')}) tour_cost=${tour_cost:.4f}",
          flush=True)
    nid = _store(text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id={nid} (is_test=true)  "
              f"LOCAL692_TOUR_ID_{SLUG}_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL692_{SLUG}_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return {'slug': slug, 'outcome': 'DELIVERED', 'id': nid,
            'editor_score': score, 'cost': tour_cost, 'secs': elapsed,
            'metrics': metrics}


print(f"[db] audio_tours BEFORE: {_row_count()} (is_test {_test_row_count()})",
      flush=True)
print(f"[db] spend for host {HOST} BEFORE: ${_spend_so_far()}", flush=True)

# The cheap arm applies to BOTH versions (museum category). BEFORE leaves
# MUSEUM_RESEARCH unset (object backend); AFTER sets artist_life.
_os.environ['CHEAP_ARM_CATEGORIES'] = 'museum'
ARMS = [
    ("BEFORE", {"NARRATION_MODEL": "gpt-4.1-mini", "RESEARCH_BACKEND": "serper",
                "MUSEUM_RESEARCH": None}),
    ("AFTER", {"NARRATION_MODEL": "gpt-4.1-mini", "RESEARCH_BACKEND": "serper",
               "MUSEUM_RESEARCH": "artist_life"}),
]

results = []
for _slug, _env in ARMS:
    results.append(_run_arm(_slug, _env))

print(f"\n[db] audio_tours AFTER: {_row_count()} (is_test {_test_row_count()})",
      flush=True)
print(f"[db] spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
print("=== LOCAL-692 eval complete ===", flush=True)
print("LOCAL692_RESULTS_JSON=" + json.dumps(results, ensure_ascii=False),
      flush=True)
for r in results:
    print(f"RESULT {r.get('slug')}: id={r.get('id')} "
          f"outcome={r.get('outcome')} score={r.get('editor_score')} "
          f"cost=${r.get('cost', 0.0):.4f} "
          f"wps={r.get('metrics', {}).get('words_per_stop')} "
          f"distinctQs={r.get('metrics', {}).get('distinct_qs')} "
          f"wiki_src={r.get('metrics', {}).get('wiki_source_lines')} "
          f"other_src={r.get('metrics', {}).get('other_source_lines')}",
          flush=True)

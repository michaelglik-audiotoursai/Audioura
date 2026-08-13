#!/usr/bin/env python3
"""story_sweep.py — do real stories come out now?

Michael, 2026-08-13: "run story generation across the other stops in this exhibit
and on other tours, and see whether real stories come out."

For each stop this runs the whole chain end to end and reports the one thing that
matters — whether the two questions of D428 can now both be answered yes:

    S1  build the stop record the way production builds it (checklist-enriched)
    S2  synthesize_queries                       (deterministic, free)
    S3  search + the LOCAL-459 ranker            (live, ~$0.016/stop)
    Q1  story_opportunity_scan   does the delivered text need a story?
    Q2  story_material_check     can the surviving corpus source one?

Before LOCAL-459, stop 2 answered YES / SILENCE. The point of the sweep is to find
out whether that was one stop's bad luck or the system's normal state.

    python3 story_sweep.py --tour TOUR_MFA_20260812_2030.txt --venue-url https://www.mfa.org \
        --exhibition "Picasso, Miró, Dalí: Unbound" --stops 1 3
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _line in open(os.path.join(HERE, '.env')):
    _line = _line.strip()
    if _line and not _line.startswith('#') and '=' in _line:
        _k, _v = _line.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from story_lab import parse_tour                                    # noqa: E402
from story_opportunity_scan import measure, verdict                 # noqa: E402
from story_material_check import assess, load_corpus                # noqa: E402


def build_record(title, venue_name, city, works):
    """The stop record production builds — checklist-enriched (generate_tour_text.py:8859)."""
    from generate_tour_text import match_work_for_stop
    rec = {
        'canonical_title': title, 'artist': '', 'publisher': '',
        'credit_line': '', 'medium': '', 'english_title': title,
        'venue_name': venue_name, 'venue_city': city, 'venue_lang': 'en',
    }
    matched = match_work_for_stop(title, works or [])
    if matched:
        for f in ('publisher', 'credit_line', 'medium', 'artist'):
            if not rec[f]:
                rec[f] = matched.get(f, '') or ''
    return rec, bool(matched)


def run_stop(stop, venue_name, city, works, live, tour_type='contained'):
    from work_story_searcher import synthesize_queries, search_stories_for_stop
    from snippet_ranker import rank_and_cap_snippets

    title = stop['title']
    rec, matched = build_record(title, venue_name, city, works)
    queries = synthesize_queries(rec, tour_type)

    out = {'title': title, 'record': rec, 'checklist_matched': matched,
           'queries': len(queries), 'retrieved': 0, 'kept': 0, 'cost': 0.0}

    survivors = []
    if live:
        res = search_stories_for_stop(rec, tour_type=tour_type,
                                      generation_tier=os.environ.get('GENERATION_TIER', 'plus'))
        raw = res.get('results', [])
        out['retrieved'] = len(raw)
        out['cost'] = res.get('estimated_cost', 0) or 0
        survivors, _ = rank_and_cap_snippets(raw, rec.get('artist', ''),
                                             work_title=title, stop_record=rec)
        out['kept'] = len(survivors)
        out['survivor_domains'] = [s.get('domain', '') for s in survivors]

    text = (stop.get('orientation', '') + '\n' + stop.get('prose', '')).strip()
    m = measure(text)
    need = verdict(m)
    out['needs_story'] = need['needs_additional_story']
    out['need_why'] = need['why']

    corpus_path = os.path.join(HERE, 'story_lab_state', f"sweep_{abs(hash(title)) % 99999}.txt")
    os.makedirs(os.path.dirname(corpus_path), exist_ok=True)
    with open(corpus_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join((s.get('title', '') + '. ' + (s.get('snippet') or ''))
                           for s in survivors))
    corpus = load_corpus([corpus_path], {})

    # Anything not already carrying a story is a target. An earlier version took only
    # FLAT and DANGLING and reported 'sourceable: NONE' for stop 3 — while Juan Gris,
    # its protagonist, sat at MENTIONED and was SOURCEABLE the whole time.
    targets = [h['surface'] for h in m['handles'] if h['state'] != 'DEVELOPED']
    results = [assess(h, corpus) for h in targets[:8]]
    sourceable = [r for r in results if r['state'] == 'SOURCEABLE']
    out['sourceable'] = [r['handle'] for r in sourceable]
    out['material'] = results

    if out['needs_story'] and sourceable:
        out['verdict'] = 'WRITE'
    elif out['needs_story']:
        out['verdict'] = 'SILENCE'
    else:
        out['verdict'] = 'ALREADY HAS ONE'
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tour', required=True)
    p.add_argument('--venue-url', default='')
    p.add_argument('--venue-name', default='')
    p.add_argument('--city', default='')
    p.add_argument('--exhibition', default='')
    p.add_argument('--stops', nargs='*', type=int)
    p.add_argument('--live', action='store_true', default=True)
    p.add_argument('--out', default='')
    a = p.parse_args()

    works = []
    if a.venue_url and a.exhibition:
        from exhibition_checklist import find_exhibition_checklist
        r = find_exhibition_checklist(a.venue_url, a.exhibition,
                                      venue_name=a.venue_name, venue_language='en')
        works = getattr(r, 'works', []) or []
        print(f"\n  checklist: {len(works)} work(s) from {getattr(r, 'path', '?')}")

    stops = parse_tour(a.tour)
    if a.stops:
        stops = [s for s in stops if s['index'] in a.stops]

    rows = []
    for s in stops:
        print(f"\n{'=' * 78}\nSTOP {s['index']}: {s['title'][:60]}\n{'=' * 78}")
        try:
            row = run_stop(s, a.venue_name, a.city, works, a.live)
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            rows.append({'title': s['title'], 'verdict': f'ERROR {type(e).__name__}'})
            continue
        rows.append(row)
        print(f"  checklist match : {row['checklist_matched']}")
        print(f"  record filled   : {sum(1 for v in row['record'].values() if v)}/{len(row['record'])}")
        print(f"  queries         : {row['queries']}")
        print(f"  retrieved/kept  : {row['retrieved']} -> {row['kept']}   "
              f"({', '.join(row.get('survivor_domains', [])[:5])})")
        print(f"  needs a story   : {row['needs_story']}")
        print(f"  sourceable      : {', '.join(row['sourceable']) or 'NONE'}")
        print(f"  VERDICT         : {row['verdict']}")

    print(f"\n\n{'=' * 78}\nSWEEP SUMMARY\n{'=' * 78}")
    print(f"  {'stop':40} {'need':>5} {'kept':>5}  verdict")
    for r in rows:
        print(f"  {r['title'][:39]:40} {str(r.get('needs_story', '?')):>5} "
              f"{str(r.get('kept', '?')):>5}  {r.get('verdict', '?')}")
    total = sum(r.get('cost', 0) for r in rows)
    print(f"\n  total search cost: ${total:.4f}")

    if a.out:
        json.dump(rows, open(a.out, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
